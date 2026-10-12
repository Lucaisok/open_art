"""
OpenArt — extraction stage.

Consumes data/discovered/*.jsonl (produced by the crawler) and fills a
RawOpportunity per URL. This is where the crawler's known precision gap
gets resolved: the crawler is deliberately recall-oriented (it includes
a link when unsure whether it's a real open call vs. e.g. retrospective
news about an already-completed commission), because that distinction
is often undecidable from a link's anchor text alone. Extraction reads
the full page and can reject those cases with much more certainty - see
workflow.MD for the audit that established this split of responsibility.

Requires OPENAI_API_KEY in a .env file at the repo root (loaded via
python-dotenv) - fetching works without it, but extract_opportunity()
will raise openai.AuthenticationError if no credentials are configured.

Usage: uv run python -m src.collectors.extraction
"""

import io
import logging
import os
import re
import sys
import unicodedata
from datetime import date, datetime, timezone
from urllib.parse import unquote, urlsplit

import requests
import yaml
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI
from typing import Literal

from pydantic import BaseModel
from pypdf import PdfReader

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(REPO_ROOT)
load_dotenv(os.path.join(REPO_ROOT, ".env"))
logging.getLogger("pypdf").setLevel(logging.ERROR)   # silence warnings about malformed but readable PDFs

from src.collectors.crawler import HEADERS, gather_candidate_links, normalize_link  # noqa: E402
from src.collectors.ids import make_id  # noqa: E402
from src.collectors.jsonl import load_jsonl, load_seen_ids, write_jsonl  # noqa: E402
from src.models.discovered_url import DiscoveredUrl  # noqa: E402
from src.models.opportunity import ApplicationQuestion, RawOpportunity, RequiredMaterial  # noqa: E402
from src.models.rejected_url import RejectedUrl  # noqa: E402
from src.processing.deadline import parse_deadline  # noqa: E402

SOURCES_YAML = os.path.join(REPO_ROOT, "data", "sources.yaml")
DISCOVERED_DIR = os.path.join(REPO_ROOT, "data", "discovered")
RAW_DIR = os.path.join(REPO_ROOT, "data", "raw")
REJECTED_DIR = os.path.join(REPO_ROOT, "data", "rejected")

MODEL = "gpt-5.4-mini"  # same cost/tier reasoning as the crawler's classify_links
MAX_PAGE_CHARS = 8000  # ~2000 tokens - generous for one opportunity page, bounded for cost

# PDFs linked from an opportunity page (call text, guidelines, regulations): often the only
# place the eligibility rules are written down. Each one gets its own text budget, so the
# page text can't push them out of the prompt (see workflow.MD, "Linked PDFs").
MAX_LINKED_PDFS = 3
MAX_PDF_CHARS = 6000          # per PDF: 3 x 6000 + the 8000-char page = ~26k chars, ~6.5k tokens
MAX_PDF_BYTES = 10_000_000    # skip anything bigger - a call document is far smaller
MAX_PDF_PAGES = 20            # the rules are near the start; don't parse 200-page annual reports

# Word starts (matched at the start of a word, accents removed - see _pdf_words) that mark a PDF
# as the call's own document, in the corpus' languages (EN, IT, DE, FR, ES, NL, NO/DA/SV).
# A match ranks the PDF first.
PDF_CALL_WORDS = (
    "call", "guideline", "regulation", "rules", "terms", "condition", "eligib", "application",
    "apply", "brief", "criteria", "prospectus", "charter",
    "bando", "regolamento", "avviso", "candidatur",
    "ausschreibung", "richtlinie", "bewerbung", "merkblatt", "teilnahmebedingung", "foerderricht",
    "reglement", "appel", "charte",
    "convocatoria", "bases",
    "oproep", "voorwaarden", "regeling",
    "veileder", "soekerveileder", "sokerveileder", "retningslinje", "regelverk", "vilkar",
    "utlysning", "forskrift", "vejledning",
)
# PDFs that are never the call itself: site-wide legal/reporting documents, and the results of
# past rounds (commission minutes, winners lists) - those could make the model judge a live
# call as already decided.
PDF_SKIP_WORDS = (
    "privacy", "datenschutz", "impressum", "imprint", "cookie", "annual report", "jahresbericht",
    "rapporto annuale", "press", "presse", "menu", "statut", "satzung", "code of conduct",
    "pv", "proces verbal", "verbale", "protokoll", "minutes", "bilan", "result", "risultat",
    "ergebnis", "winner", "laureat", "selected", "selection", "vincitor", "preistrager",
)

# Site-wide PDFs: a document linked from many pages of the corpus is the organisation's general
# rules (e.g. fpu.sk's "principles and priorities", linked from 68 calls), not one call's own text;
# fed to the model it would copy the same general rules into every call's requirements. The list
# is written by scripts/refresh_pdf_extraction.py scan (PDFs linked from >= SITE_WIDE_MIN_PAGES
# pages) and read once here, so normal pipeline runs skip them too.
SITE_WIDE_PDFS_PATH = os.path.join(REPO_ROOT, "data", "site_wide_pdfs.txt")
SITE_WIDE_MIN_PAGES = 10


def load_site_wide_pdfs(path: str = SITE_WIDE_PDFS_PATH) -> set[str]:
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip() and not line.startswith("#")}


SITE_WIDE_PDFS = load_site_wide_pdfs()

# The model is told to use null when a field isn't stated (see
# build_extraction_system_prompt), but at least once it wrote out its own
# reasoning for the absence instead - "[not present in provided text]"
# landed in a raw deadline field verbatim (see workflow.MD). A prompt
# tweak alone isn't a guarantee against a repeat in different phrasing on
# some future page, so this is caught deterministically instead: any
# nullable field whose entire value is just the model explaining that the
# page doesn't state it gets normalized to a real null. Confirmed a second,
# more widespread variant while building canonicalize.py: the literal
# string "null" (the JSON keyword itself, not the field being actually
# null) landed in city (8), application_fee (8), country (2), and
# career_stage (1) - the model writing the keyword as if it were a value
# rather than emitting an actual null.
_PLACEHOLDER_LEAK = re.compile(
    r"^\[?\s*(?:"
    r"(?:not|no)\s+(?:present|stated|specified|provided|given|mentioned|available|found)"
    r"(?:\s+(?:in|on|within)\s+(?:the\s+)?(?:provided\s+)?(?:page\s+)?text)?"
    r"|n/a|not\s+applicable|none\s+(?:given|stated|provided)|null|none"
    r")\s*\]?\.?$",
    re.IGNORECASE,
)

_NULLABLE_FIELDS = (
    "organisation",
    "description",
    "discipline",
    "opportunity_type",
    "country",
    "city",
    "funding",
    "application_fee",
    "career_stage",
    "deadline",
    "application_url",
    "project_requirements",
    "how_to_apply",
    "selection_criteria",
    "application_language",
    "submission_method",
    "program_dates",
)


class ExtractedQuestion(BaseModel):
    question: str
    limit: str | None


class ExtractedMaterial(BaseModel):
    item: str
    details: str | None
    quote: str


class ExtractedOpportunity(BaseModel):
    is_open_call: bool
    rejection_reason: str | None
    title: str | None
    organisation: str | None
    description: str | None
    discipline: str | None
    opportunity_type: str | None
    country: str | None
    city: str | None
    funding: str | None
    application_fee: str | None
    career_stage: str | None
    open_to: list[Literal["individuals", "groups", "organisations"]]  # who may apply; checked in code
    applicant_requirements: str | None   # stored as RawOpportunity.requirements_text
    project_requirements: str | None
    how_to_apply: str | None
    application_questions: list[ExtractedQuestion]
    required_materials: list[ExtractedMaterial]
    selection_criteria: str | None
    application_language: str | None
    submission_method: str | None
    program_dates: str | None
    deadline: str | None
    rolling_deadline: bool
    rules_in_external_document: bool
    application_url: str | None


def _drop_placeholder_leaks(extracted: ExtractedOpportunity) -> None:
    for field in _NULLABLE_FIELDS:
        value = getattr(extracted, field)
        if isinstance(value, str) and _PLACEHOLDER_LEAK.match(value.strip()):
            setattr(extracted, field, None)


def build_extraction_system_prompt() -> str:
    """The extraction instructions (workflow.MD, "Step 3 — combined re-extraction").

    No date is given any more: the model misjudged past/future deadlines in both directions
    (it rejected a 12 November 2026 call as past on 2026-10-12, and accepted past ones), so
    closed-by-date is decided in code after extraction (see deadline_has_passed()). The model
    still rejects a page that explicitly says the call is closed.

    Requirements are split in three so that only conditions on the artist reach the eligibility
    classifier: project rules, duties and procedure used to land in one block and show up as
    false checks (about a fifth of all open points, measured 2026-10-12).
    """
    return (
        "You are extracting structured data from an arts/culture open-call page. "
        "The page text may end with the text of PDF documents linked from the "
        "page, each under an '--- Attached document: ... ---' heading: treat "
        "them as part of the same call (they often hold the full eligibility "
        "rules) and extract from them too.\n\n"

        "First decide is_open_call. It is true if the page is a specific open "
        "call currently soliciting new applications (residency, grant, "
        "commission, prize, fellowship, exhibition call...), with a way to apply.\n"
        "A call that states no conditions on who can apply is still an open "
        "call: accept it and leave applicant_requirements null.\n"
        "It is false for: an artist or work already selected, a navigational "
        "or procedural page, a call the page explicitly says is closed, or any "
        "other non-opportunity content. Do NOT judge whether the deadline has "
        "passed: report the deadline as written, dates are checked later. If "
        "false, give a short rejection_reason.\n\n"

        "VERBATIM means: copy the page's own sentences, in the page's "
        "language, without paraphrasing, summarizing, translating or "
        "reordering words. You may leave sentences out and join the kept ones "
        "with line breaks.\n\n"

        "If is_open_call is true, extract:\n"
        "- title: the specific opportunity's title\n"
        "- organisation: the organisation/institution running it\n"
        "- description: a short summary in ENGLISH, 2 to 4 sentences, of what "
        "the opportunity is and offers (theme, format, activity). This is the "
        "ONLY field you write in your own words. Do not repeat eligibility "
        "rules or the deadline here.\n"
        "- discipline: the artistic discipline(s) the opportunity is for (e.g. "
        "visual arts, dance, literature, music, film), exactly as stated, or "
        "null if not stated\n"
        "- opportunity_type: what kind of opportunity this is (e.g. residency, "
        "grant, commission, competition, prize, fellowship, exhibition), "
        "exactly as stated or clearly implied, or null if unclear\n"
        "- country: the country where the opportunity takes place (for a "
        "grant, the funder's country), exactly as stated, or null - not the "
        "country applicants must come from or live in, which belongs to "
        "applicant_requirements\n"
        "- city: the city the opportunity is based in, exactly as stated, or null\n"
        "- funding: the support offered (amount, stipend, grant size, "
        "accommodation, travel...) VERBATIM, or null\n"
        "- application_fee: any fee to apply, VERBATIM (including an explicit "
        "'no fee' statement), or null if not mentioned\n"
        "- career_stage: the career stage the opportunity targets (e.g. "
        "emerging, early-career, student, established), exactly as stated, or null\n"
        "- open_to: who is allowed to be the applicant, any of 'individuals' "
        "(a single person: artist, curator, writer, researcher...), 'groups' "
        "(collectives, duos, ensembles of persons) and 'organisations' "
        "(institutions, museums, companies, venues, festivals, associations). "
        "Judge by who the applicant is, not by who fills in the form: a call "
        "for museums is ['organisations'] even though a person submits it\n"
        "- applicant_requirements: VERBATIM, ONLY the conditions a PERSON must "
        "meet to be ALLOWED TO APPLY: residence, nationality, age, discipline "
        "or practice, career stage or years of practice, education, student "
        "status, applicant type (individual, collective, organisation), prior "
        "funding or past participation, language skills, and exclusions "
        "('X cannot apply'). Include sentences that widen eligibility ('open "
        "to all nationalities'). Leave OUT: what the project or work must be, "
        "duties if selected, documents to send, how selection works, "
        "deadlines, the different routes or steps to apply ('There are two ways "
        "to apply'), and list headers with nothing after them ('The residency "
        "is open to:' - copy it together with the items that follow it).\n"
        "- project_requirements: VERBATIM, conditions the PROJECT or WORK must "
        "meet to be eligible (theme, format, site, duration, budget rules) "
        "and duties if selected (be present, deliver a work, report), or null. "
        "Not what the call offers (studio, stipend, support): that is funding "
        "or description\n"
        "- how_to_apply: VERBATIM, the application procedure: steps, documents "
        "to send, how and where to submit, or null\n"
        "- application_questions: every question or prompt the application "
        "asks the applicant to answer in writing (e.g. 'Describe your "
        "project', 'Why this residency?'), each with question VERBATIM and "
        "limit VERBATIM ('max 300 words') or null. [] if none are stated\n"
        "- required_materials: every item the applicant must submit (CV, "
        "portfolio, project description, budget, letters, video link, ID...): "
        "item = a short name in English, details = the stated limits (pages, "
        "size, format) VERBATIM or null, quote = the page sentence asking for "
        "it VERBATIM. [] if none are stated\n"
        "- selection_criteria: VERBATIM, the criteria the jury or committee "
        "judges applications on, or null. Not who sits on the jury\n"
        "- application_language: the language(s) applications must be written "
        "in, only if the page says so explicitly, or null. Do not infer it from "
        "the language of the page or the form\n"
        "- submission_method: one of 'online form', 'email', 'portal', "
        "'post', 'other', or null if not stated\n"
        "- program_dates: VERBATIM, when the residency/project/programme itself "
        "takes place, or null. Not the selection timeline (jury meeting, "
        "results)\n"
        "- deadline: the application deadline VERBATIM, including the time and "
        "time zone if stated, and every round if there are several; do not "
        "compute or convert it; null if not stated\n"
        "- rolling_deadline: true if applications are accepted continuously "
        "with no closing date\n"
        "- rules_in_external_document: true if the page says the eligibility "
        "rules are in a document whose text you were NOT given (e.g. 'see the "
        "regulations'); false if that document is attached above or no such "
        "reference is made\n"
        "- application_url: if the page has a distinct application/submission "
        "link, copy its exact URL from the 'Links found on this page' list "
        "below - never the anchor text - or null if the page itself is the "
        "application page or no such link is given\n\n"

        "If is_open_call is false, leave every other field null, the lists "
        "empty and the booleans false."
    )


def extract_pdf_text(content: bytes, max_pages: int | None = None) -> str:
    try:
        reader = PdfReader(io.BytesIO(content))
        pages = reader.pages if max_pages is None else reader.pages[:max_pages]
        return " ".join((page.extract_text() or "") for page in pages)
    except Exception:
        return ""  # malformed/scanned/image-only PDF - let the empty text fall through
        # to the model's normal "not readable" rejection path rather than crashing


def _pdf_words(text: str) -> str:
    """Lower-case words, accents and punctuation removed, each preceded by a space.

    "PV_Commission_MIRA.pdf" -> " pv commission mira pdf", "Søkerveileder" -> " sokerveileder",
    so `f" {word}" in ...` matches a word start: "pv" matches the token pv, never "pvc" mid-word.
    """
    text = unicodedata.normalize("NFKD", text.lower().replace("ø", "o").replace("æ", "ae"))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " " + " ".join(re.findall(r"[a-z0-9]+", text))


def find_pdf_links(soup: BeautifulSoup, scope, page_url: str) -> list[tuple[str, str]]:
    """The page's most likely call documents: up to MAX_LINKED_PDFS (url, label) pairs, best first.

    Searches the whole document, not just <article>/<main>: call PDFs often sit in a sidebar
    "Downloads" box. Unlike gather_candidate_links(), a link with no anchor text is kept (PDFs
    are often linked by an icon); its file name stands in as the label.

    Ranking: +3 if the label or file name has a call word (bando, Ausschreibung, guidelines...),
    +2 if the link is inside the page's main content, +1 if it's on the same site. A PDF with
    neither of the first two (score <= 1) is a site-wide document and is dropped.
    """
    in_scope = {id(a) for a in scope.find_all("a", href=True)} if scope is not soup else None
    page_host = urlsplit(page_url).netloc

    scored: dict[str, tuple[int, str]] = {}   # url -> (score, label), first occurrence wins
    for a in soup.find_all("a", href=True):
        url = normalize_link(a["href"], page_url)
        if url is None or url in scored or not urlsplit(url).path.lower().endswith(".pdf"):
            continue
        if url in SITE_WIDE_PDFS:
            continue   # the organisation's general document, not this call's
        file_name = unquote(urlsplit(url).path.rsplit("/", 1)[-1])
        label = a.get_text(" ", strip=True) or file_name
        words = _pdf_words(f"{label} {file_name}")
        if any(f" {w}" in words for w in PDF_SKIP_WORDS):
            continue

        score = 0
        if any(f" {w}" in words for w in PDF_CALL_WORDS):
            score += 3
        if in_scope is None or id(a) in in_scope:
            score += 2
        if urlsplit(url).netloc == page_host:
            score += 1
        if score > 1:
            scored[url] = (score, label)

    ranked = sorted(scored.items(), key=lambda item: -item[1][0])   # stable: page order on ties
    return [(url, label) for url, (_, label) in ranked[:MAX_LINKED_PDFS]]


def fetch_pdf_text(url: str) -> str:
    """Download one linked PDF and return its text ("" if too big, not a PDF, or unreadable).

    Streamed, so a huge file is abandoned after MAX_PDF_BYTES instead of downloaded whole.
    Never raises: a broken attachment must not lose the page it's attached to.
    """
    try:
        with requests.get(url, headers=HEADERS, timeout=20, stream=True) as resp:
            resp.raise_for_status()
            content = b""
            for chunk in resp.iter_content(chunk_size=64_000):
                content += chunk
                if len(content) > MAX_PDF_BYTES:
                    print(f"  linked PDF skipped (over {MAX_PDF_BYTES // 1_000_000} MB): {url}")
                    return ""
    except requests.RequestException as e:
        print(f"  linked PDF skipped ({e.__class__.__name__}): {url}")
        return ""

    if not content.startswith(b"%PDF"):
        return ""   # a ".pdf" link that served an HTML error/login page
    text = extract_pdf_text(content, max_pages=MAX_PDF_PAGES).strip()
    if not text:
        print(f"  linked PDF has no text layer (scanned?): {url}")
    return text


def fetch_page(url: str) -> tuple[str, list[tuple[str, str]], list[str]]:
    """Fetch a page, returning (visible_text, candidate_links, pdf_urls).

    get_text() strips every href along with the rest of the markup, so
    without candidate_links the model is asked for an application_url
    it was never actually shown - it can only echo nearby anchor text
    (e.g. "Apply here"), which is how application_url ended up full of
    button labels instead of URLs. Link harvesting reuses the crawler's
    gather_candidate_links() so both stages filter mailto/social/etc.
    the same way.

    The text of the page's linked call PDFs (find_pdf_links) is appended,
    each under an "Attached document:" heading, and their URLs returned as
    pdf_urls - only those that actually yielded text.
    """
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()

    content_type = resp.headers.get("Content-Type", "")
    if "application/pdf" in content_type or url.lower().endswith(".pdf"):
        return extract_pdf_text(resp.content)[:MAX_PAGE_CHARS], [], []

    soup = BeautifulSoup(resp.text, "html.parser")
    scope = soup.find("article") or soup.find("main") or soup
    text = scope.get_text(" ", strip=True)[:MAX_PAGE_CHARS]
    links = gather_candidate_links(str(scope), url)

    pdf_urls = []
    for pdf_url, label in find_pdf_links(soup, scope, url):
        pdf_text = fetch_pdf_text(pdf_url)
        if pdf_text:
            text += f"\n\n--- Attached document: {label} ({pdf_url}) ---\n{pdf_text[:MAX_PDF_CHARS]}"
            pdf_urls.append(pdf_url)
    return text, links, pdf_urls


# -- checks done in code after the model answers ---------------------------------------------------

# Fields the prompt asks to copy VERBATIM. Each is checked against the text the model read.
VERBATIM_FIELDS = ("requirements_text", "project_requirements", "how_to_apply", "selection_criteria",
                   "program_dates", "funding", "application_fee", "deadline")
_QUOTE_CHARS = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
                              "\u2013": "-", "\u2014": "-", "\u00a0": " ", "\u00ad": ""})
# a field is split into pieces at line breaks and sentence ends: the model may leave sentences out
# and join the kept ones, so only each piece has to appear in the text, not the whole field
_PIECE_SPLIT = re.compile(r"\n+|(?<=[.!?;])\s+")
MIN_PIECE_WORDS = 3  # shorter pieces ("Yes.", "1)") are too generic to tell anything


def _flatten(text: str) -> str:
    """Lower case, typographic quotes/dashes made plain, every whitespace run one space."""
    return " ".join(text.translate(_QUOTE_CHARS).lower().split())


def _is_verbatim(value: str, flat_source: str) -> bool:
    """True if every piece of value (of MIN_PIECE_WORDS words or more) appears in the source."""
    pieces = [_flatten(p).strip(" -*\u2022") for p in _PIECE_SPLIT.split(value)]
    return all(p in flat_source for p in pieces if len(p.split()) >= MIN_PIECE_WORDS)


def verbatim_misses(record: RawOpportunity, source_text: str) -> list[str]:
    """Names of the verbatim fields whose text isn't in the page text: probably paraphrased.

    Questions and materials are checked one by one ("application_questions[2]"). Flagged, not
    removed: the report shows them, so a human decides whether the paraphrase matters.
    """
    flat_source = _flatten(source_text)
    misses = [f for f in VERBATIM_FIELDS if getattr(record, f) and not _is_verbatim(getattr(record, f), flat_source)]
    misses += [f"application_questions[{i}]" for i, q in enumerate(record.application_questions)
               if not _is_verbatim(q.question, flat_source)]
    misses += [f"required_materials[{i}]" for i, m in enumerate(record.required_materials)
               if not _is_verbatim(m.quote, flat_source)]
    return misses


_ANY_YEAR = re.compile(r"(?<!\d)20\d{2}(?!\d)")
# numeric day.month.year ("19.1.2026", "04.11. 2025"): read directly, because search_dates() misreads
# runs of them ("19.1.2026 16.2.2026 7.5.2026" came out as 16 October 2026 in the full run)
_NUMERIC_DATE = re.compile(r"(?<!\d)(\d{1,2})\.\s?(\d{1,2})\.\s?(20\d{2})(?!\d)")


def _numeric_dates(text: str) -> list[date]:
    found = []
    for day, month, year in _NUMERIC_DATE.findall(text):
        try:
            found.append(date(int(year), int(month), int(day)))
        except ValueError:
            pass   # not a real date (e.g. a version number): ignore it
    return found


def deadline_has_passed(record: RawOpportunity, language: str, today=None) -> bool:
    """True if the call's deadline is on or before today (author's rule, 2026-10-12).

    Decided here, not by the model (see build_extraction_system_prompt). Always the LATEST date in
    the text, so a call with several rounds is closed only after its last round. In order:
    - never closed: a rolling call, no deadline, or a deadline that names no year ("15.01. /
      15.05. / 15.09." are rounds that recur every year; the parser turns them into today);
    - closed if every year written is before this one ("1 February 2015": parse_deadline() drops
      dates more than 10 years away, so it would otherwise read as no date at all);
    - numeric D.M.YYYY dates are read by a plain regex;
    - otherwise parse_deadline(); a deadline it can't parse is never closed.
    """
    today = today or date.today()
    if record.rolling_deadline or not record.deadline:
        return False
    years = [int(y) for y in _ANY_YEAR.findall(record.deadline)]
    if not years:
        return False
    if max(years) < today.year:
        return True
    numeric = _numeric_dates(record.deadline)
    deadline_date = max(numeric) if numeric else parse_deadline(record.deadline, language, record.source)
    return deadline_date is not None and deadline_date <= today


_SOURCE_LANGUAGES: dict[str, str] = {}


def source_language(source_name: str) -> str:
    """The source's page language from sources.yaml (read once), for deadline parsing."""
    if not _SOURCE_LANGUAGES:
        with open(SOURCES_YAML, encoding="utf-8") as f:
            _SOURCE_LANGUAGES.update({s["name"]: s.get("language", "en") for s in (yaml.safe_load(f) or [])})
    return _SOURCE_LANGUAGES.get(source_name, "en")


def extract_opportunity(
    client: OpenAI, url: str, source_name: str
) -> tuple[RawOpportunity | None, str | None]:
    """Returns (record, rejection_reason) - record is None iff rejected. Writes no file."""
    text, links, pdf_urls = fetch_page(url)
    links_block = "\n".join(f"- [{text_}]({link_url})" for link_url, text_ in links) or "(none found)"

    response = client.chat.completions.parse(
        model=MODEL,
        temperature=0,  # accept/reject and field extraction should be repeatable for the
        # same page, not vary run to run - see workflow.MD for the audit that found this
        messages=[
            {"role": "system", "content": build_extraction_system_prompt()},
            {
                "role": "user",
                "content": (
                    f"Page URL: {url}\n\nPage text:\n{text}\n\n"
                    f"Links found on this page:\n{links_block}"
                ),
            },
        ],
        response_format=ExtractedOpportunity,
    )
    extracted = response.choices[0].message.parsed
    _drop_placeholder_leaks(extracted)

    if not extracted.is_open_call:
        return None, extracted.rejection_reason or "not an open call"
    if not extracted.title:
        return None, "is_open_call=True but title missing"

    application_url = extracted.application_url
    if application_url and not application_url.startswith(("http://", "https://")):
        application_url = None  # model echoed anchor text instead of a URL - drop, don't store garbage

    record = RawOpportunity(
        id=make_id(url, source_name),
        source=source_name,
        source_url=url,
        application_url=application_url,
        document_urls=pdf_urls,
        title=extracted.title,
        organisation=extracted.organisation,
        description=extracted.description,
        discipline=extracted.discipline,
        opportunity_type=extracted.opportunity_type,
        country=extracted.country,
        city=extracted.city,
        funding=extracted.funding,
        application_fee=extracted.application_fee,
        career_stage=extracted.career_stage,
        # "" = the page states no condition on who can apply (accepted since 2026-10-12; the
        # engine shows a CHECK: usually the rules are on another page, not absent)
        requirements_text=extracted.applicant_requirements or "",
        open_to=list(extracted.open_to),
        deadline=extracted.deadline,
        project_requirements=extracted.project_requirements,
        how_to_apply=extracted.how_to_apply,
        application_questions=[ApplicationQuestion(**q.model_dump()) for q in extracted.application_questions],
        required_materials=[RequiredMaterial(**m.model_dump()) for m in extracted.required_materials],
        selection_criteria=extracted.selection_criteria,
        application_language=extracted.application_language,
        submission_method=extracted.submission_method,
        program_dates=extracted.program_dates,
        rolling_deadline=extracted.rolling_deadline,
        rules_in_external_document=extracted.rules_in_external_document,
        source_text=text,
        collected_at=datetime.now(timezone.utc),
    )

    # individuals only (author, 2026-10-12): decided here from a fact the model reports, because
    # an accept/reject instruction in the prompt was not followed (a museums-only grant passed it)
    if extracted.open_to and "individuals" not in extracted.open_to:
        return None, f"not open to individuals (open to: {', '.join(extracted.open_to)})"
    if deadline_has_passed(record, source_language(source_name)):
        return None, f"deadline passed ({record.deadline})"
    record.verbatim_flags = verbatim_misses(record, text)
    return record, None


def extract_source(
    client: OpenAI, source_name: str, discovered: list[DiscoveredUrl], seen_ids: set[str]
) -> tuple[list[RawOpportunity], list[RejectedUrl]]:
    records: list[RawOpportunity] = []
    rejected: list[RejectedUrl] = []
    rejected_at = datetime.now(timezone.utc)

    for d in discovered:
        if d.id in seen_ids:
            continue
        try:
            record, reason = extract_opportunity(client, d.url, source_name)
        except Exception as e:
            reason = f"fetch/extract error: {e}"
            record = None

        if record is None:
            rejected.append(
                RejectedUrl(
                    id=d.id,
                    url=d.url,
                    source=source_name,
                    title_guess=d.title_guess,
                    reason=reason,
                    rejected_at=rejected_at,
                )
            )
            seen_ids.add(d.id)
            continue

        records.append(record)
        seen_ids.add(record.id)

    return records, rejected


def extract_all(
    discovered_dir: str = DISCOVERED_DIR,
    raw_dir: str = RAW_DIR,
    rejected_dir: str = REJECTED_DIR,
    sources_path: str = SOURCES_YAML,
    only: set[str] | None = None,
) -> dict[str, dict]:
    with open(sources_path, encoding="utf-8") as f:
        source_names = [s["name"] for s in (yaml.safe_load(f) or [])]
    if only is not None:
        source_names = [n for n in source_names if n in only]

    client = OpenAI()
    # Rejected ids are cached too, so a URL rejected once (closed call,
    # navigational page, unreadable PDF, ...) isn't re-fetched and
    # re-billed on every future run. Delete its line from
    # data/rejected/<source>.jsonl to force a re-check (e.g. after a
    # pipeline fix, as happened with the PDF support added earlier).
    seen_ids = load_seen_ids(raw_dir, rejected_dir)

    results = {}
    for name in source_names:
        discovered_path = os.path.join(discovered_dir, f"{name}.jsonl")
        discovered = load_jsonl(discovered_path, DiscoveredUrl)
        if not discovered:
            continue

        try:
            new_records, rejected = extract_source(client, name, discovered, seen_ids)
        except Exception as e:
            print(f"{name}: FAILED - {e}")
            results[name] = {"extracted": 0, "rejected": [], "error": str(e)}
            continue

        raw_path = os.path.join(raw_dir, name, "opportunities.jsonl")
        merged = {r.id: r for r in load_jsonl(raw_path, RawOpportunity)}
        merged.update({r.id: r for r in new_records})
        write_jsonl(list(merged.values()), raw_path)

        rejected_path = os.path.join(rejected_dir, f"{name}.jsonl")
        merged_rejected = {r.id: r for r in load_jsonl(rejected_path, RejectedUrl)}
        merged_rejected.update({r.id: r for r in rejected})
        write_jsonl(list(merged_rejected.values()), rejected_path)

        results[name] = {"extracted": len(new_records), "rejected": rejected}
        print(f"{name}: {len(new_records)} extracted, {len(rejected)} rejected -> {raw_path}")
        for r in rejected:
            print(f"  rejected: {r.title_guess!r} - {r.reason}")

    return results


if __name__ == "__main__":
    extract_all()
