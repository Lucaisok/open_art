"""
OpenArt — read profile values out of a CV with plain rules. Nothing leaves the machine.

    suggestions = extract_profile(read_chunks("cv.pdf"), document="cv.pdf")
    for s in suggestions:
        print(s.field, s.value, s.quote, s.citation)

Replaces the OpenAI pre-fill (profile_prefill.py, RAG step 3) in the web app: the
product owner chose deterministic rules so no CV text is sent anywhere (workflow.MD,
web app step 4b). Like the eligibility engine, every value comes from a visible rule
and the exact line it was read from, and the artist checks it before saving.

Works line by line on the chunks of src/rag/documents.py, which already know the
CV section each line sits in ("Education", "Exhibitions"). Per field:

  name                a line of 2-4 capitalised words that the CV's email address spells
                      ("Elena Moretti" + elena.moretti@...), or, in a CV, its opening heading ("ILKA VARGA")
  birth_date          a full date on a line with "born" / "b." / "date of birth" / "DOB"
  birth_year          "b. 1988" / "born in 1988" when no full date is given: never put in the profile
                      (the engine needs the full date), the form shows it as a hint under the birth date
  nationalities       country names or adjectives on a "citizenship" / "nationality" line
  residence_country   the country (or a known city) after "lives in" / "based in" / "resident in";
                      otherwise a line that is only a place in the CV's contact block ("Berlin")
  residence_city      the city on that same line: a known city ("Berlin") or the name before
                      ", <country>" ("Lives in Leipzig, Germany")
  applicant_type      "we are a collective" -> group, "individual artist" -> individual, ...
  disciplines         discipline words (the engine's table) in the CV's opening lines
  active_since        the earliest year of an exhibition / performance / residency / award /
                      publication line, or "founded in YYYY"
  languages           the languages under a "Languages" heading or on a "Languages:" line, except those
                      marked basic / beginner / A1-B1 (the profile holds working languages only)
  education           one school per degree line: the institution after the degree and subject, the city
                      and country after it ("MFA in Painting, Academy of Fine Arts Vienna, Austria")
  has_degree, graduation_year, degree_field, currently_enrolled
                      degree entries (MFA, BA, PhD...) in the Education section: their dates on
                      the same line or the next few (templates often put "09/2013 – 06/2016" on
                      a line of its own), the subject after the degree (joined across a line
                      break), and any Education date range ending in "Present"

extract_all runs these rules and the prose ones (extract_practice) on any document, so a CV
inside a portfolio file is read too (api/profile.py does this for every upload).

A rule that doesn't fire leaves the field empty: the artist fills it in. Wrong values are
the risk to keep low, so the rules only read the places a CV states these facts.
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from typing import Any

from src.eligibility.disciplines import TERMS
from src.eligibility.geo import (COUNTRIES, COUNTRY_RE, NAME_TO_COUNTRY, SUBNATIONAL_CITIES, SUBNATIONAL_LOOKUP,
                                 SUBNATIONAL_RE)
from src.eligibility.languages import LANGUAGE_RE, NAME_TO_LANGUAGE
from src.rag.documents import Chunk


@dataclass
class Suggestion:
    field: str            # a ProfileValues field (api/profile.py)
    value: Any
    quote: str            # the CV line the value was read from
    citation: str         # "cv.pdf · p. 1 · EDUCATION"
    note: str | None = None


@dataclass
class _Line:
    text: str
    section: str | None
    page: int | None


# -- sections ------------------------------------------------------------------------------------

EDUCATION_SECTION = re.compile(r"\b(education|training|studies|academic|degrees?|qualifications?)\b", re.I)
CAREER_SECTION = re.compile(
    r"\b(exhibitions?|shows?|performances?|works|productions?|screenings?|concerts?|festivals?|residenc\w*|"
    r"awards?|prizes?|grants?|fellowships?|scholarships?|publications?|bibliography|commissions?|projects?|"
    r"curatorial|support|collections?)\b", re.I)
KNOWN_SECTION = re.compile(EDUCATION_SECTION.pattern + "|" + CAREER_SECTION.pattern +
                           r"|\b(personal|contact|details|about|bio(graphy)?|languages?|skills?|statement|teaching|"
                           r"experience|workshops?|talks?|press|memberships?|collaborations?)\b", re.I)


# a section title the reader didn't mark as a heading ("Selection of exhibitions and screenings",
# "Residencies and programs"): a short line that starts with a known section word
INLINE_HEADING = re.compile(r"^((selected|selection of|solo|group|recent|other)\s+)?(" + KNOWN_SECTION.pattern + ")",
                            re.I)


def _inline_heading(text: str) -> bool:
    return (len(text.split()) <= 6 and text[:1].isupper() and not re.search(r"[\d,;\"“”]", text)
            and text[-1] not in ".!?" and bool(INLINE_HEADING.match(text))
            and not RESIDENCE_PHRASE.search(text))      # "Works in Berlin" is not a heading


def _lines(chunks: list[Chunk]) -> list[_Line]:
    """Every non-empty line with its section. A heading found inside the text replaces the stored
    one until the reader's next heading: PDFs only get the headings in documents.CV_SECTIONS, so
    without this a whole CV can sit under "Education" (exhibitions read as studies, and not as
    career). Works on chunks already stored, so documents uploaded earlier benefit too."""
    out, stored, found = [], None, None
    for c in chunks:
        if c.section != stored:            # the reader's next heading: a new section
            stored, found = c.section, None
        for text in c.text.split("\n"):
            text = text.strip(" -•\t")
            if not text:
                continue
            if _inline_heading(text):
                found = text.rstrip(":").strip()
            out.append(_Line(text, found or c.section, c.page))
    return out


def _intro(lines: list[_Line]) -> list[_Line]:
    """The CV's opening lines (name, title, contact): before any heading, or under the name heading
    ("ILKA VARGA"). At most 8 lines: past that it's a profile text, not the header."""
    if not lines:
        return []
    first = lines[0].section
    if first is not None and KNOWN_SECTION.search(first):
        return []
    return [line for line in lines if line.section == first][:8]


def _citation(document: str, line: _Line) -> str:
    return " · ".join([document] + ([f"p. {line.page}"] if line.page else []) + ([line.section] if line.section else []))


# -- birth date ----------------------------------------------------------------------------------

MONTHS = {name: i for i, names in enumerate(
    [("january", "jan"), ("february", "feb"), ("march", "mar"), ("april", "apr"), ("may",), ("june", "jun"),
     ("july", "jul"), ("august", "aug"), ("september", "sep", "sept"), ("october", "oct"),
     ("november", "nov"), ("december", "dec")], start=1) for name in names}
_MONTH = r"(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\.?"

BORN_LINE = re.compile(r"\b(born|birth ?date|date of birth|d\.?o\.?b)\b|(?<![\w.])b\.", re.I)
# only the year: "(b. 1988, Buenos Aires", "born in 1988", "Born in Osaka, Japan, 1985" (same clause)
BORN_YEAR = re.compile(r"(?:\bborn\b[^.;\d]{0,40}?|(?<![\w.])b\.\s*)((?:19|20)\d\d)\b", re.I)
DATE_PATTERNS = [
    (re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+" + _MONTH + r",?\s+(\d{4})\b", re.I), ("d", "m", "y")),  # 12 March 1994
    (re.compile(r"\b" + _MONTH + r"\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b", re.I), ("m", "d", "y")),  # March 12, 1994
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), ("y", "m", "d")),                                         # 1994-03-12
    (re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b"), ("d", "m", "y")),                               # 12.03.1994
]


def _birth_date(lines: list[_Line], today: date) -> tuple[date, _Line] | None:
    """Day, month and year are all needed: "b. 1997" alone is not a birth date."""
    for line in lines:
        if not BORN_LINE.search(line.text):
            continue
        for pattern, order in DATE_PATTERNS:
            if match := pattern.search(line.text):
                parts = dict(zip(order, match.groups()))
                month = MONTHS.get(parts["m"].lower().rstrip(".")) if not parts["m"].isdigit() else int(parts["m"])
                try:
                    found = date(int(parts["y"]), month, int(parts["d"]))
                except (TypeError, ValueError):
                    continue
                # at least 14 years ago: "the festival was born on 3 May 2019" is not the artist
                if date(1900, 1, 1) <= found and found.year <= today.year - 14:
                    return found, line
    return None


def _birth_year(lines: list[_Line], today: date) -> tuple[int, _Line] | None:
    """The year alone ("b. 1988"), for the form's hint: not a birth date, so never a profile value."""
    for line in lines:
        if (match := BORN_YEAR.search(line.text)) and 1900 <= int(match.group(1)) <= today.year - 14:
            return int(match.group(1)), line
    return None


# -- name -----------------------------------------------------------------------------------------

# lower-case words a name can hold between its capitalised ones ("Julieta Ortiz de Latierro")
NAME_PARTICLES = {"de", "da", "di", "del", "della", "der", "den", "van", "von", "le", "la", "du", "dos", "das",
                  "y", "bin", "ibn", "al"}
NAME_WORD = re.compile(r"^[A-ZÀ-Ý][A-Za-zÀ-ÿ'’-]+$")
EMAIL = re.compile(r"\b([\w.+-]+)@[\w-]+\.[\w.-]+")
DOCUMENT_TITLE = re.compile(r"\b(curriculum|vitae?|cv|resume|résumé|portfolio|dossier)\b", re.I)


def _fold(text: str) -> str:
    """Lower case without accents: "Tomás" -> "tomas", to compare with an email address."""
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).lower()


def _looks_like_name(text: str) -> bool:
    """2-4 words, each capitalised (or a particle like "de"), starting with a capitalised one, no
    digits, and not a section title, a document title ("Curriculum Vitae") or a place."""
    words = text.split()
    if not 2 <= len(words) <= 4 or KNOWN_SECTION.search(text) or DOCUMENT_TITLE.search(text) or PLACE_RE.search(text):
        return False
    proper = [w for w in words if w not in NAME_PARTICLES]
    return len(proper) >= 2 and words[0] in proper and all(NAME_WORD.match(w) for w in proper)


def _name(chunks: list[Chunk], lines: list[_Line], is_cv: bool) -> tuple[str, _Line] | None:
    """The artist's name. A wrong name is worse than none, so a name-like line alone isn't enough:
    1. a name-like line whose words are all in the document's email address (elena.moretti@...): the
       document says twice that this is its author, whatever kind of document it is
    2. in a CV, its opening heading, when it looks like a name ("ILKA VARGA", "Tomás Ferreira")
    ALL CAPS is written as a name ("Ilka Varga")."""
    tidy = lambda text: text.title() if text.isupper() else text
    addresses = [_fold(m.group(1)) for line in lines for m in EMAIL.finditer(line.text)]
    for line in lines:
        if addresses and _looks_like_name(line.text):
            parts = [_fold(w) for w in line.text.split() if w not in NAME_PARTICLES]
            if any(all(part in address for part in parts) for address in addresses):
                return tidy(line.text), line
    heading = chunks[0].section if chunks else None
    if is_cv and heading and _looks_like_name(heading):
        return tidy(heading), _Line(heading, heading, chunks[0].page)
    return None


# -- countries ------------------------------------------------------------------------------------

NATIONALITY_LINE = re.compile(r"\b(citizenships?|nationalit(y|ies)|citizen|passport)\b", re.I)
RESIDENCE_PHRASE = re.compile(r"\b(lives and works (in|between)|lives in|living in|based in|resident in|"
                              r"residing in|resides in|works in)\s+", re.I)


def _countries_in(text: str) -> list[str]:
    codes = []
    for match in COUNTRY_RE.finditer(text):
        code = NAME_TO_COUNTRY[match.group(0).lower()]
        if code not in codes:
            codes.append(code)
    return codes


# Prose talks about citizenship too ("a work about citizenship in Mexico"), so the countries must be
# tied to the word: a "Nationality:" label starting the line, or right next to it ("Swedish citizen",
# "Brazilian/Portuguese citizenship", "citizen of Italy")
NATIONALITY_LABEL = re.compile(r"^\W*(nationalit(y|ies)|citizenships?|passports?)\b", re.I)
_COUNTRY_CHAIN = rf"(?:{COUNTRY_RE.pattern})(?:\s*(?:,|/|&|and)\s*(?:{COUNTRY_RE.pattern}))*"
COUNTRIES_BEFORE = re.compile(_COUNTRY_CHAIN + r"\s*$", re.I)
COUNTRIES_AFTER = re.compile(r"^\s*(?:of|:)\s*" + _COUNTRY_CHAIN, re.I)


def _nationalities(lines: list[_Line]) -> tuple[list[str], _Line] | None:
    for line in lines:
        # "Swedish citizen, living in Berlin": only the part before a residence phrase
        text = RESIDENCE_PHRASE.split(line.text)[0]
        if NATIONALITY_LABEL.search(text):
            if codes := _countries_in(text):
                return sorted(codes), line
            continue
        for word in NATIONALITY_LINE.finditer(text):
            near = (COUNTRIES_BEFORE.search(text[:word.start()]) or COUNTRIES_AFTER.search(text[word.end():]))
            if near and (codes := _countries_in(near.group(0))):
                return sorted(codes), line
    return None


# -- languages ------------------------------------------------------------------------------------

LANGUAGES_SECTION = re.compile(r"^\W*languages?\b", re.I)          # a "LANGUAGES" heading
LANGUAGES_LINE = re.compile(r"^\W*languages?\s*[:\-–]", re.I)      # "Languages: Italian (native), ..."
# a level below working level: the language is left out ("German (basic)", "Spanish A2")
BELOW_WORKING = re.compile(r"\b(basic|beginner|elementary|notions?|some|school|a1|a2|b1|learning)\b", re.I)


def _working_languages(text: str) -> list[str]:
    """Each language is judged on its own stretch of text, up to the next language:
    "Hungarian (native), German (basic)" -> Hungarian only."""
    found = list(LANGUAGE_RE.finditer(text))
    codes = []
    for i, match in enumerate(found):
        stretch = text[match.end():found[i + 1].start() if i + 1 < len(found) else len(text)]
        code = NAME_TO_LANGUAGE[match.group(0).lower()]
        if not BELOW_WORKING.search(stretch) and code not in codes:
            codes.append(code)
    return codes


def _languages(lines: list[_Line]) -> tuple[list[str], _Line] | None:
    """The working languages on a "Languages:" line, or on every line under a Languages heading (one
    language per line is common). The quote shown is every line that named one, joined with " · "."""
    for line in lines:
        if LANGUAGES_LINE.search(line.text) and (codes := _working_languages(line.text)):
            return sorted(codes), line
    section = [line for line in lines if line.section and LANGUAGES_SECTION.search(line.section)]
    codes, read = [], []
    for line in section:
        if LANGUAGE_RE.search(line.text):
            read.append(line)
            codes += [code for code in _working_languages(line.text) if code not in codes]
    if not codes:
        return None
    return sorted(codes), _Line(" · ".join(line.text for line in read), read[0].section, read[0].page)


# country NAMES, not adjectives: a contact line "Germany" is a place, "German" is a language or nationality
PLACE_NAMES = {name.lower() for names in COUNTRIES.values() for i, name in enumerate(names)
               if i == 0 or " " in name or name.isupper()}
PLACE_RE = re.compile(r"\b(" + "|".join(re.escape(n) for n in sorted(PLACE_NAMES | set(SUBNATIONAL_LOOKUP),
                                                                     key=len, reverse=True)) + r")\b", re.I)
CONTACT_SECTION = re.compile(r"\b(personal|contact|details|about)\b", re.I)


def _place_only(text: str) -> str | None:
    """The country of a line that is nothing but a place: "Berlin", "Vienna, Austria", "London (UK)"."""
    if len(text.split()) > 5 or not PLACE_RE.search(text):
        return None
    # "Lisbon, Portugal": any city name before a country, as long as it looks like one (no digits)
    city, _, country = text.rpartition(",")
    if city and not re.search(r"\d", city) and len(city.split()) <= 3 and city.strip()[:1].isupper():
        country = country.strip(" .")
        if country.lower() in PLACE_NAMES and country.lower() in NAME_TO_COUNTRY:
            return NAME_TO_COUNTRY[country.lower()]
    if re.sub(r"[\s,;/|()·.\-–]+", "", PLACE_RE.sub("", text)):
        return None                       # something else on the line: an address, a sentence, a venue
    places = [m.group(0).lower() for m in PLACE_RE.finditer(text)]
    countries = [NAME_TO_COUNTRY[p] for p in places if p in NAME_TO_COUNTRY]
    return countries[0] if countries else SUBNATIONAL_LOOKUP[places[0]]


def _city_in(text: str) -> str | None:
    """The city in a residence text: a known one ("Berlin", "Vienna") or the name right before
    ", <country>" ("Leipzig, Germany"). Only what the text plainly says; None otherwise."""
    if known := SUBNATIONAL_RE.search(text):
        name = known.group(0).lower()
        return next(n for n in SUBNATIONAL_CITIES if n.lower() == name) if name in CITY_NAMES else None
    if found := CITY_BEFORE_COUNTRY.match(text.strip()):
        if found.group(2).lower() in NAME_TO_COUNTRY and not re.search(r"\d", found.group(1)):
            return found.group(1).strip()
    return None


# "Leipzig, Germany": up to three capitalised words, a comma, then the country
CITY_BEFORE_COUNTRY = re.compile(r"([A-ZÀ-Ý][\w'\-]*(?: [A-ZÀ-Ý][\w'\-]*){0,2}),\s*([A-Za-z][\w .]+?)[\s.;)]*$")
CITY_NAMES = {name.lower() for name in SUBNATIONAL_CITIES}


# "lives in" / "resident in" are said of people only. "based in" / "works in" are said of projects
# too ("a performance based in Lisbon"), so they count only after a person: the start of the line or
# a clause ("Painter, based in Vienna"), a pronoun, or a name ("Paloma is based in")
PERSON_VERB = re.compile(r"^(liv|resid)", re.I)
PERSON_BEFORE = re.compile(r"(^|[(;,:.|/–—-]|\b(i|she|he|they|we|who|currently|now|also|mainly|am|artists?))\s*$",
                           re.I)
NAME_IS = re.compile(r"\b(she|he|they|we|[A-ZÀ-Ý][\w'\-]+)\s+(is|are)\s*$")
NOT_A_NAME = {"It", "This", "That", "The", "There", "Which", "What"}


def _residence_phrase(text: str) -> re.Match | None:
    """The first residence phrase in `text` that is about the artist."""
    for match in RESIDENCE_PHRASE.finditer(text):
        before = text[:match.start()]
        if PERSON_VERB.match(match.group(0)) or PERSON_BEFORE.search(before):
            return match
        if (name := NAME_IS.search(before)) and name.group(1) not in NOT_A_NAME:
            return match
    return None


def _residence(lines: list[_Line], intro: list[_Line]) -> tuple[str, str | None, _Line] | None:
    """(country, city, line): the first country after a residence phrase; a known city ("Lives in
    Amsterdam") if no country; else a line in the contact block that is only a place (CV templates put
    "Berlin" under the name). The city is read from the same words (_city_in), None if not stated."""
    city_only = None
    for line in lines:
        match = _residence_phrase(line.text)
        if not match:
            continue
        rest = line.text[match.end():]
        if codes := _countries_in(rest):
            # "between Berlin, Germany and Oslo, Norway": two countries, so no one city
            return codes[0], (_city_in(rest) if len(codes) == 1 else None), line
        if city_only is None and (cities := SUBNATIONAL_RE.findall(rest)):
            # "between Berlin and Oslo": the first gives the country, but neither is the one city
            city_only = SUBNATIONAL_LOOKUP[cities[0].lower()], (_city_in(cities[0]) if len(cities) == 1 else None), line
    if city_only:
        return city_only
    contact = intro + [line for line in lines if line.section and CONTACT_SECTION.search(line.section)]
    for line in contact:
        if code := _place_only(line.text):
            return code, _city_in(line.text), line
    return None


# -- who applies ----------------------------------------------------------------------------------

INDIVIDUAL = re.compile(r"\b(individual artist|works as an individual|independent artist|solo artist)\b", re.I)
GROUP = re.compile(r"\b(we are|is) an? ([\w-]+ ){0,2}(collective|duo|trio|ensemble|company|group|band)\b|"
                   r"\b(collective|duo|trio|ensemble) of (two|three|four|five|six|\d+)\b", re.I)
ORGANISATION = re.compile(r"\b(we are|is) an? ([\w-]+ ){0,2}(organi[sz]ation|association|foundation|"
                          r"non-?profit|charity|institution)\b", re.I)


def _applicant_type(lines: list[_Line]) -> tuple[str, _Line] | None:
    for line in lines:
        for value, pattern in (("individual", INDIVIDUAL), ("group", GROUP), ("organisation", ORGANISATION)):
            if pattern.search(line.text):
                return value, line
    return None


# -- disciplines ----------------------------------------------------------------------------------

# the engine's discipline words, plus how artists describe themselves in a CV
CV_TERMS = {
    "Visual Arts": [r"installations?", r"visual artists?", r"sculptors?"],
    "Music": [r"sound artists?", r"musicians?", r"sound installations?"],
    "Performing Arts": [r"performances?", r"performance artists?"],
}
DISCIPLINE_RES = {canonical: re.compile(r"\b(" + "|".join(TERMS.get(canonical, []) + CV_TERMS.get(canonical, [])) + r")\b",
                                        re.I)
                  for canonical in TERMS}


def _disciplines(intro: list[_Line]) -> tuple[list[str], _Line] | None:
    """From the first opening line that names any ("Painter and printmaker", "Dancer and choreographer")."""
    for line in intro[:4]:
        found = sorted((match.start(), canonical) for canonical, pattern in DISCIPLINE_RES.items()
                       if (match := pattern.search(line.text)))
        if found:
            return [canonical for _, canonical in found], line
    return None


# -- career start ---------------------------------------------------------------------------------

YEAR = re.compile(r"\b(19[5-9]\d|20\d\d)\b")
FOUNDED = re.compile(r"\b(founded|established|formed)\b[^.]*?\b(19[5-9]\d|20\d\d)\b", re.I)


# a dated entry has its year at the start ("2015 Venice Biennale", "Mar 2019 Solo show") or the end
# ("Venice Biennale (2015)"); a year mid-line is prose ("Low Tide Archive (2024-) is a series...")
ENTRY_YEAR = re.compile(r"^\W*(?:[A-Za-z]{3,9}\.?\s+)?(19[5-9]\d|20\d\d)\b|\b(19[5-9]\d|20\d\d)\W*$")


def _active_since(lines: list[_Line], intro: list[_Line], today: date) -> tuple[int, _Line] | None:
    candidates = []
    for line in lines:
        section = line.section or ""
        if CAREER_SECTION.search(section) and not EDUCATION_SECTION.search(section):
            if match := ENTRY_YEAR.search(line.text):
                candidates.append((int(match.group(1) or match.group(2)), line))
    for line in intro:
        if match := FOUNDED.search(line.text):
            candidates.append((int(match.group(2)), line))
    candidates = [(year, line) for year, line in candidates if year <= today.year]
    return min(candidates, key=lambda c: c[0]) if candidates else None


# -- education ------------------------------------------------------------------------------------

# case-sensitive on purpose: "MA" is a degree, "ma" is not
DEGREE = re.compile(r"\b(Ph\.?D\.?|DPhil|Doctorate|M\.?F\.?A\.?|M\.?A\.?|MMus|M\.?Sc\.?|MArch|M\.?Des|"
                    r"B\.?F\.?A\.?|B\.?A\.?|BMus|B\.?Sc\.?|BArch|B\.?Des|Bachelor(?:'s)?(?: of \w+)?|"
                    r"Master(?:'s)?(?: of \w+)?|Diploma)(?=[\s,(]|$)")
# a date range that hasn't ended: "2022 - present", "06/2026 – Present", "since 2024", "(ongoing)"
STILL_RUNNING = re.compile(r"((19|20)\d\d\s*[-–—]+\s*(present|now|today|ongoing|current)\b)|"
                           r"\bsince (19|20)\d\d\b|\((ongoing|in progress|current)\)|\bexpected (19|20)\d\d\b", re.I)
NOT_ENROLLED = re.compile(r"\bnot (currently )?(enrolled|a student|studying)\b", re.I)
CONNECTOR_END = re.compile(r"\b(and|of|in|for|the|&|with)$|[-–&]$", re.I)
LOOKAHEAD = 4   # lines after a degree line that can still hold its dates


def _degree_field(text: str, degree_end: int) -> str | None:
    """The subject after the degree: "MFA in Painting and Graphic Arts, Academy..." -> "Painting and Graphic Arts"."""
    rest = text[degree_end:]
    rest = re.sub(r"^\s*(\(hons\.?\))?\s*(in|of)?\s*", "", rest, flags=re.I)
    subject = re.split(r",|\s[-–—]\s|\(|\||;", rest)[0].strip(" .:")
    return subject or None


def _continues(line: str, following: str) -> bool:
    """Does `following` finish a degree title cut by a line break? ("...Science and International" /
    "Relations.") Yes if the title ends on a connector word, or the next line is a short end of sentence."""
    if any(ch.isdigit() for ch in following) or DEGREE.search(following):
        return False
    return bool(CONNECTOR_END.search(line.strip())) or (len(following.split()) <= 3 and following.endswith("."))


SCHOOL_WORD = re.compile(r"\b(academ\w*|universit\w*|universidad\w*|universidade|école|ecole|school|college|"
                         r"conservato\w*|institut\w*|hochschule|kunsthochschule|polytechnic|hzt)\b", re.I)
YEAR_ONLY = re.compile(r"^\W*(19|20)\d\d(\s*[-–—]\s*((19|20)\d\d|present|now))?\W*$", re.I)


def _place_code(text: str) -> str | None:
    """The country a short place names: a country ("Austria") or a known city ("Vienna", "London")."""
    found = PLACE_RE.search(text)
    if not found:
        return None
    name = found.group(0).lower()
    return NAME_TO_COUNTRY.get(name) or SUBNATIONAL_LOOKUP.get(name)


def _school(text: str, degree_end: int, skip_subject: bool = True) -> dict | None:
    """The school of a degree line: what follows the degree and its subject, split on commas.
    A segment that is only a country is the country; a short one before it, or a known city alone
    ("MA Fine Art, Berlin"), the city; years are skipped; the rest is the institution. The country
    can also come from a city in the name ("Academy of Fine Arts Vienna" -> AT). skip_subject=False
    for a line that is only the school (see _education)."""
    segments = [seg.strip(" .:") for seg in re.split(r",|\s[-–—|]\s", text[degree_end:])]
    segments = [seg for seg in segments[1 if skip_subject else 0:]               # [0] is the subject
                if seg and not YEAR_ONLY.match(seg)]
    institution, city, country = [], None, None
    for seg in segments:
        code = NAME_TO_COUNTRY.get(seg.lower()) if seg.lower() in PLACE_NAMES else None
        if code:
            country = code
        elif (institution or seg.lower() in CITY_NAMES) and not SCHOOL_WORD.search(seg) \
                and len(seg.split()) <= 3 and seg[:1].isupper() and not re.search(r"\d", seg):
            city = seg
        else:
            institution.append(seg)
    if not institution:
        return None
    name = ", ".join(institution)
    country = country or _place_code(city or "") or _place_code(name)
    return {"institution": name, "city": city, "country": country}


def _education(lines: list[_Line], today: date) -> list[tuple[str, Any, _Line]]:
    found: list[tuple[str, Any, _Line]] = []
    finished = []        # (end year, field, line)
    in_progress = None
    education = [line for line in lines if EDUCATION_SECTION.search(line.section or "")]

    for line in lines:
        if NOT_ENROLLED.search(line.text):
            found.append(("currently_enrolled", False, line))

    schools, school_lines = [], []
    for i, line in enumerate(education):
        if STILL_RUNNING.search(line.text) and not NOT_ENROLLED.search(line.text):
            in_progress = in_progress or line           # any programme still running: enrolled
        degree = DEGREE.search(line.text)
        if not degree:
            continue
        school, quoted = _school(line.text, degree.end()), line
        if school is None and i + 1 < len(education) and SCHOOL_WORD.search(education[i + 1].text) \
                and not DEGREE.search(education[i + 1].text):
            # "MA Kunst und Medien, Berlin" over "University of the Arts (UDK), Berlin": the school is below
            school = _school(education[i + 1].text, 0, skip_subject=False)
            quoted = _Line(f"{line.text} / {education[i + 1].text}", line.section, line.page)
        if school and school not in schools:
            schools.append(school)
            school_lines.append(quoted)
        # this degree's lines: its own, then the next few up to the next degree (dates on their own line)
        entry = [line]
        for following in education[i + 1:i + 1 + LOOKAHEAD]:
            if DEGREE.search(following.text):
                break
            entry.append(following)
        text = line.text
        if len(entry) > 1 and _continues(text, entry[1].text):
            text = f"{text} {entry[1].text}"
        dated = next((e for e in entry if YEAR.search(e.text)), None)
        if dated is None:
            continue
        if STILL_RUNNING.search(dated.text) or max(int(y) for y in YEAR.findall(dated.text)) > today.year:
            in_progress = in_progress or dated
            continue
        year = max(int(y) for y in YEAR.findall(dated.text))
        finished.append((year, _degree_field(text, degree.end()), line))

    if schools:
        quoted = _Line(" · ".join(line.text for line in school_lines), school_lines[0].section, school_lines[0].page)
        found.append(("education", schools, quoted))
    if in_progress and not any(f == "currently_enrolled" for f, _, _ in found):
        found.append(("currently_enrolled", True, in_progress))
    if finished:
        year, subject, line = max(finished, key=lambda f: f[0])   # the most recent finished degree
        found.append(("has_degree", True, line))
        found.append(("graduation_year", year, line))
        if subject:
            found.append(("degree_field", subject, line))
    return found


# -- statement and portfolio: the Practice fields -------------------------------------------------
# Prose mentions things in passing ("a live musician in the room"), so a discipline counts only
# if it is named at least twice, or in the document's first sentence.

SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
WORK_YEAR = re.compile(r"^[^.!?]{1,80}?,\s*(19[5-9]\d|20\d\d)\b\.?\s*$")   # "Rain Score, 2021"
MAX_DISCIPLINES = 3


def _sentences(lines: list[_Line]) -> list[_Line]:
    """Prose as sentences (keeping each one's section and page), for quoting."""
    out = []
    for line in lines:
        for sentence in SENTENCE_END.split(line.text):
            if sentence.strip():
                out.append(_Line(sentence.strip(), line.section, line.page))
    return out


def _prose_disciplines(sentences: list[_Line]) -> tuple[list[str], _Line] | None:
    counts: dict[str, int] = {}
    first_at: dict[str, _Line] = {}
    for i, sentence in enumerate(sentences):
        for canonical, pattern in DISCIPLINE_RES.items():
            hits = len(pattern.findall(sentence.text))
            if hits:
                counts[canonical] = counts.get(canonical, 0) + hits + (1 if i == 0 else 0)  # first sentence: +1
                first_at.setdefault(canonical, sentence)
    kept = sorted((c for c, n in counts.items() if n >= 2), key=lambda c: -counts[c])[:MAX_DISCIPLINES]
    if not kept:
        return None
    return kept, first_at[kept[0]]          # quoted: where the most-named discipline first appears


# "2021 Rain Score" / "2013–2015 Labor in a Single Shot": a year, then a title. Short lines only
# (a wrapped line of prose can start with a year too), and never in Education (years of study)
YEAR_FIRST_WORK = re.compile(r"^(19[5-9]\d|20\d\d)(?:\s*[-–—]\s*(?:19[5-9]\d|20\d\d))?:?\s+[\"“‘'A-ZÀ-Ý]")
MAX_WORK_WORDS = 10


def _earliest_work(lines: list[_Line], today: date) -> tuple[int, _Line] | None:
    """Portfolio entries are "Title, 2021" or "2021 Title": the earliest one. Year-first lines count
    only outside a named section or in a career one (not under Teaching, Experience...)."""
    works = []
    for line in lines:
        section = line.section or ""
        if match := WORK_YEAR.match(line.text):
            works.append((int(match.group(1)), line))
        elif (len(line.text.split()) <= MAX_WORK_WORDS and not EDUCATION_SECTION.search(section)
              and (not section or CAREER_SECTION.search(section))
              and (match := YEAR_FIRST_WORK.match(line.text))):
            works.append((int(match.group(1)), line))
    works = [(year, line) for year, line in works if year <= today.year]
    return min(works, key=lambda w: w[0]) if works else None


def extract_practice(chunks: list[Chunk], document: str, kind: str, today: date | None = None) -> list[Suggestion]:
    """The Practice fields prose can state: disciplines, applying as ("We are a theatre collective"),
    active since (the earliest dated work). Written for statements and portfolios; `kind` only picks
    the wording of the note. Career stage is never read: it's the artist's own call."""
    today = today or date.today()
    lines = _lines(chunks)
    sentences = _sentences(lines)
    suggestions: list[Suggestion] = []

    def add(field: str, result, note: str | None = None) -> None:
        if result:
            value, line = result
            suggestions.append(Suggestion(field, value, line.text, _citation(document, line), note))

    add("disciplines", _prose_disciplines(sentences),
        note="named in your works' descriptions" if kind == "portfolio" else "named more than once")
    add("applicant_type", _applicant_type(sentences[:6]))
    add("active_since", _earliest_work(lines, today), note=f"your earliest dated work in the {KIND_NAMES[kind]}")
    return suggestions


# -- all together ---------------------------------------------------------------------------------

KIND_NAMES = {"cv": "CV", "statement": "statement", "portfolio": "portfolio"}

def extract_profile(chunks: list[Chunk], document: str, today: date | None = None,
                    is_cv: bool = True) -> list[Suggestion]:
    """Profile values found by the CV rules, each with the line it comes from. Empty fields are left
    out. Safe on any document (see extract_all): each rule reads only where a CV states the fact.
    is_cv: the document is in the CV slot (only then is its opening heading taken as the name)."""
    today = today or date.today()
    lines = _lines(chunks)
    intro = _intro(lines)
    suggestions: list[Suggestion] = []

    def add(field: str, result, note: str | None = None) -> None:
        if result:
            value, line = result
            suggestions.append(Suggestion(field, value, line.text, _citation(document, line), note))

    add("name", _name(chunks, lines, is_cv))
    found_birth = _birth_date(lines, today)
    add("birth_date", (found_birth[0].isoformat(), found_birth[1]) if found_birth else None)
    if not found_birth:
        add("birth_year", _birth_year(lines, today), note="only the year: add the day and month yourself")
    add("nationalities", _nationalities(lines))
    if residence := _residence(lines, intro):
        country, city, line = residence
        add("residence_country", (country, line))
        add("residence_city", (city, line) if city else None)
    add("applicant_type", _applicant_type(intro + lines[:12]))
    add("disciplines", _disciplines(intro))
    add("active_since", _active_since(lines, intro, today),
        note="the earliest dated exhibition, performance, residency, award or publication in your CV")
    add("languages", _languages(lines))
    for field, value, line in _education(lines, today):
        add(field, (value, line))
    return suggestions


def extract_all(chunks: list[Chunk], document: str, kind: str, today: date | None = None) -> list[Suggestion]:
    """Every rule on any document: an artist may upload one file holding CV, statement and portfolio
    together ("CV-Portfolio.pdf"), whatever slot it goes in. In a CV the CV rules go first; in a
    statement or portfolio the prose rules do (their disciplines come from the whole text, not just
    the opening lines). One suggestion per field: the first found."""
    cv_rules = extract_profile(chunks, document, today, is_cv=kind == "cv")
    prose = extract_practice(chunks, document, kind, today)
    suggestions, taken = [], set()
    for suggestion in (cv_rules + prose if kind == "cv" else prose + cv_rules):
        if suggestion.field not in taken:
            suggestions.append(suggestion)
            taken.add(suggestion.field)
    return suggestions
