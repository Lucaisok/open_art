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
import os
import sys
from datetime import datetime, timezone

import requests
import yaml
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel
from pypdf import PdfReader

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(REPO_ROOT)
load_dotenv(os.path.join(REPO_ROOT, ".env"))

from src.collectors.crawler import HEADERS, gather_candidate_links  # noqa: E402
from src.collectors.ids import make_id  # noqa: E402
from src.collectors.jsonl import load_jsonl, load_seen_ids, write_jsonl  # noqa: E402
from src.models.discovered_url import DiscoveredUrl  # noqa: E402
from src.models.opportunity import RawOpportunity  # noqa: E402
from src.models.rejected_url import RejectedUrl  # noqa: E402

SOURCES_YAML = os.path.join(REPO_ROOT, "data", "sources.yaml")
DISCOVERED_DIR = os.path.join(REPO_ROOT, "data", "discovered")
RAW_DIR = os.path.join(REPO_ROOT, "data", "raw")
REJECTED_DIR = os.path.join(REPO_ROOT, "data", "rejected")

MODEL = "gpt-5.4-mini"  # same cost/tier reasoning as the crawler's classify_links
MAX_PAGE_CHARS = 8000  # ~2000 tokens - generous for one opportunity page, bounded for cost


class ExtractedOpportunity(BaseModel):
    is_open_call: bool
    rejection_reason: str | None
    title: str | None
    organisation: str | None
    requirements_text: str | None
    deadline: str | None
    application_url: str | None


def build_extraction_system_prompt(today: str) -> str:
    """today (ISO date) lets the model reject calls whose stated deadline

    has already passed even when the page never says "closed" - a static
    prompt has no notion of "now" and can only catch explicit closure
    wording, which missed pages that just show a quietly-past date (see
    workflow.MD for the audit that found this).
    """
    return (
        f"Today's date is {today}. You are extracting structured data from "
        "an arts/culture open-call page. "
        "First decide: is this page CURRENTLY SOLICITING NEW APPLICATIONS from "
        "artists - a specific open call whose eligibility/requirements "
        "information is actually present in the page text given to you, with a "
        "way to apply? Or is it NOT one - e.g. it describes an artist or work "
        "already selected/completed, it's a navigational or procedural page, the "
        "call is closed/expired - either explicitly stated as such, or because "
        "its stated deadline falls on or before today's date given above, even "
        "if the page never says so explicitly and otherwise reads like a normal, "
        "live opportunity page - the given "
        "page text does not itself contain identifiable eligibility/restriction "
        "information - e.g. only a heading like 'Who can apply?' with no answer "
        "beneath it, or only deadline/procedural text and no actual "
        "restrictions - even though the page is otherwise clearly a real call, "
        "or it's some other non-opportunity content? Set is_open_call "
        "accordingly, and if false, give a short rejection_reason (for the "
        "missing-eligibility-content case, say so explicitly rather than citing "
        "a closed call or navigation page, so it's clear the page just wasn't "
        "readable this way rather than genuinely not being a live call).\n\n"
        "If is_open_call is true, extract:\n"
        "- title: the specific opportunity's title\n"
        "- organisation: the organisation/institution running it\n"
        "- requirements_text: the eligibility/requirements text copied VERBATIM "
        "from the page - who can apply and any restrictions (nationality, "
        "residence, age, discipline, career stage, education, student status, "
        "etc.). Copy the actual wording; do not paraphrase or summarize. Never "
        "substitute deadline/procedural text for this field.\n"
        "- deadline: the application deadline exactly as stated on the page "
        "(literal text, do not compute or convert it), or null if not stated\n"
        "- application_url: if the page has a distinct application/submission "
        "link, copy its exact URL from the 'Links found on this page' list "
        "below - never the anchor text - or null if the page itself is the "
        "application page or no such link is given\n\n"
        "If is_open_call is false, leave title/organisation/requirements_text/"
        "deadline/application_url as null."
    )


def extract_pdf_text(content: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(content))
        return " ".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        return ""  # malformed/scanned/image-only PDF - let the empty text fall through
        # to the model's normal "not readable" rejection path rather than crashing


def fetch_page(url: str) -> tuple[str, list[tuple[str, str]]]:
    """Fetch a page, returning (visible_text, candidate_links).

    get_text() strips every href along with the rest of the markup, so
    without candidate_links the model is asked for an application_url
    it was never actually shown - it can only echo nearby anchor text
    (e.g. "Apply here"), which is how application_url ended up full of
    button labels instead of URLs. Link harvesting reuses the crawler's
    gather_candidate_links() so both stages filter mailto/social/etc.
    the same way.
    """
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()

    content_type = resp.headers.get("Content-Type", "")
    if "application/pdf" in content_type or url.lower().endswith(".pdf"):
        return extract_pdf_text(resp.content)[:MAX_PAGE_CHARS], []

    soup = BeautifulSoup(resp.text, "html.parser")
    scope = soup.find("article") or soup.find("main") or soup
    text = scope.get_text(" ", strip=True)[:MAX_PAGE_CHARS]
    links = gather_candidate_links(str(scope), url)
    return text, links


def extract_opportunity(
    client: OpenAI, url: str, source_name: str
) -> tuple[RawOpportunity | None, str | None]:
    """Returns (record, rejection_reason) - record is None iff rejected."""
    text, links = fetch_page(url)
    links_block = "\n".join(f"- [{text_}]({link_url})" for link_url, text_ in links) or "(none found)"
    today = datetime.now(timezone.utc).date().isoformat()

    response = client.chat.completions.parse(
        model=MODEL,
        messages=[
            {"role": "system", "content": build_extraction_system_prompt(today)},
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

    if not extracted.is_open_call:
        return None, extracted.rejection_reason or "not an open call"
    if not extracted.title or not extracted.requirements_text:
        return None, "is_open_call=True but title/requirements_text missing"

    application_url = extracted.application_url
    if application_url and not application_url.startswith(("http://", "https://")):
        application_url = None  # model echoed anchor text instead of a URL - drop, don't store garbage

    record = RawOpportunity(
        id=make_id(url, source_name),
        source=source_name,
        source_url=url,
        application_url=application_url,
        title=extracted.title,
        organisation=extracted.organisation,
        requirements_text=extracted.requirements_text,
        deadline=extracted.deadline,
        collected_at=datetime.now(timezone.utc),
    )
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
