"""
OpenArt — read the artist's projects (past, current, planned) and interests out of their documents
with plain rules. Nothing leaves the machine, as for the profile pre-fill (cv_rules.py).

    found = extract_projects([("cv", "cv.pdf", cv_chunks), ("statement", "statement.docx", st_chunks)])
    found.projects   # ProjectSuggestion(title, status, years, summary, medium, venues, sources)
    found.interests  # Interest(text, quote, citation)

Why projects: 64% of open calls ask mainly for a new project (workflow.MD, "Projects page — plan"),
and the application agent needs to know which one. The artist reviews every suggestion; nothing is
saved without that, and they can add projects by hand (a planned project is often in no document).

Rules, per document kind:

  cv          lines with a year in a works section (exhibitions, performances, works, projects,
              commissions, screenings, concerts, productions; not "group" shows, whose title isn't the
              artist's work): "2025 | Tidal Bodies (installation) | Venue" or
              "2025 Low Tide Archive, Galerie Nord, Vienna" -> title, year, medium, venue
  portfolio   a "Title, 2025" line, and the lines under it up to the next one as its summary
  statement   "Title (2024-) is ..." -> a titled project (open range = current); a section named
              current / ongoing / upcoming / future / plans / next, or a sentence saying "currently",
              "I am developing", "my next project", "I plan" -> an untitled current / planned project;
              a "Themes" / "Interests" section or "I am interested in" -> an interest

The same title in several documents is one project (CV year and venue + portfolio description).
"""

import re
from dataclasses import dataclass, field
from datetime import date

from src.rag.cv_rules import SENTENCE_END, _citation, _Line, _lines
from src.rag.documents import Chunk

PAST, CURRENT, PLANNED = "past", "current", "planned"
STATUS_ORDER = {CURRENT: 0, PLANNED: 1, PAST: 2}


@dataclass
class Source:
    quote: str        # the line or sentence the suggestion was read from
    citation: str     # "cv.pdf · p. 1 · EXHIBITIONS"


@dataclass
class ProjectSuggestion:
    title: str | None             # None: a statement sentence about an unnamed project
    status: str                   # past / current / planned
    years: str | None             # "2025", "2024–"
    summary: str | None = None    # the artist's own words (portfolio description, statement sentence)
    medium: str | None = None     # "8-channel installation"
    venues: list[str] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)

    @property
    def key(self) -> str:
        """What two mentions of the same project share: the title, lower case, letters and digits only."""
        return re.sub(r"[^a-z0-9]", "", (self.title or self.summary or "").lower())


@dataclass
class Interest:
    text: str
    citation: str


@dataclass
class Found:
    projects: list[ProjectSuggestion]
    interests: list[Interest]


# -- shared patterns ---------------------------------------------------------------------------------

YEAR = r"(?:19[5-9]\d|20\d\d)"
# a works section of a CV; "group" shows are left out (their title is the show's, not the artist's work)
WORKS_SECTION = re.compile(r"\b(exhibitions?|shows?|performances?|works|projects?|commissions?|screenings?|"
                           r"concerts?|productions?)\b", re.I)
GROUP_SECTION = re.compile(r"\bgroup\b", re.I)
# "2025 | Tidal Bodies (8-channel installation) | Venue"  or  "2025 Low Tide Archive, Galerie Nord, Vienna"
CV_WORK_LINE = re.compile(rf"^(?P<years>{YEAR}(?:\s*[–-]\s*(?:{YEAR}|present|today|now)?)?)\s*[|:,]?\s*(?P<rest>.+)$", re.I)
TRAILING_MEDIUM = re.compile(r"\s*\((?P<medium>[^()]{3,60})\)\s*$")
# "Tidal Bodies, 2025" (a portfolio work's heading line)
PORTFOLIO_HEADING = re.compile(rf"^(?P<title>[^.!?|]{{2,80}}?),\s*(?P<years>{YEAR}(?:\s*[–-]\s*{YEAR})?)\.?\s*$")
# "Low Tide Archive (2024-) is a series ..." (a titled project in prose; an open range = ongoing)
TITLED_IN_PROSE = re.compile(rf"^(?P<title>[A-Z][^()]{{2,60}}?)\s*\((?P<years>{YEAR}\s*(?:[–-]\s*(?:{YEAR})?)?)\)")
CURRENT_SECTION = re.compile(r"\b(current|ongoing|in progress|work in progress)\b", re.I)
PLANNED_SECTION = re.compile(r"\b(upcoming|future|plans?|next)\b", re.I)
INTEREST_SECTION = re.compile(r"\b(themes?|interests?|research)\b", re.I)
CURRENT_CUE = re.compile(r"\b(currently|at the moment|I am (?:now )?(?:developing|working on|making|preparing)|"
                         r"in progress)\b", re.I)
PLANNED_CUE = re.compile(r"\b(my next (?:project|work)|I plan to|I am planning|I would like to (?:develop|make|create)|"
                         r"upcoming|I will (?:develop|make|create))\b", re.I)
INTEREST_CUE = re.compile(r"\b(I am interested in|I want to explore|I would like to explore|my interests?)\b", re.I)


def _status_from_years(years: str, today: date) -> str:
    """"2024–" / "2024–present" -> current; a start year after this one -> planned; else past."""
    numbers = [int(y) for y in re.findall(YEAR, years)]
    if re.search(r"[–-]\s*(present|today|now)?\s*$", years.strip(), re.I) and len(numbers) == 1:
        return CURRENT
    if numbers and numbers[0] > today.year:
        return PLANNED
    if numbers and max(numbers) >= today.year:
        return CURRENT
    return PAST


def _tidy_years(years: str) -> str:
    """"2024 - present" -> "2024–", "2019-2021" -> "2019–2021"."""
    years = re.sub(r"\s*[–-]\s*(present|today|now)?\s*$", "–", years.strip(), flags=re.I)
    return re.sub(r"\s*[–-]\s*", "–", years)


# -- per document kind ----------------------------------------------------------------------------------

def _from_cv(lines: list[_Line], document: str, today: date) -> list[ProjectSuggestion]:
    found = []
    for line in lines:
        if not (line.section and WORKS_SECTION.search(line.section)) or GROUP_SECTION.search(line.section):
            continue
        match = CV_WORK_LINE.match(line.text)
        if not match:
            continue   # a heading row ("Year | Work | Venue") or prose
        parts = [p.strip() for p in re.split(r"\s*\|\s*", match["rest"]) if p.strip()]
        if len(parts) == 1:   # "Low Tide Archive, Galerie Nord, Vienna": title, then where
            parts = [p.strip() for p in match["rest"].split(",", 1)]
        title, venue = parts[0], ", ".join(parts[1:]) or None
        medium = None
        if m := TRAILING_MEDIUM.search(title):
            medium, title = m["medium"], title[:m.start()].strip()
        years = _tidy_years(match["years"])
        found.append(ProjectSuggestion(title=title, status=_status_from_years(years, today), years=years,
                                       medium=medium, venues=[venue] if venue else [],
                                       sources=[Source(line.text, _citation(document, line))]))
    return found


def _from_portfolio(lines: list[_Line], document: str, today: date) -> list[ProjectSuggestion]:
    found: list[ProjectSuggestion] = []
    for line in lines:
        if match := PORTFOLIO_HEADING.match(line.text):
            years = _tidy_years(match["years"])
            found.append(ProjectSuggestion(title=match["title"].strip(), status=_status_from_years(years, today),
                                           years=years, sources=[Source(line.text, _citation(document, line))]))
        elif found and line.section == _section_of(found[-1]):
            # a description line under the last heading (same section): part of its summary
            found[-1].summary = f"{found[-1].summary} {line.text}" if found[-1].summary else line.text
    return found


def _section_of(project: ProjectSuggestion) -> str | None:
    citation = project.sources[0].citation.split(" · ")
    return citation[-1] if len(citation) > 1 and not citation[-1].startswith("p. ") else None


def _from_statement(lines: list[_Line], document: str, today: date) -> tuple[list[ProjectSuggestion], list[Interest]]:
    projects, interests = [], []
    # statements are often hard-wrapped ("I am interested in residencies by\nwater, ..."): join the
    # lines of one section back into a paragraph before cutting it into sentences
    paragraphs: list[_Line] = []
    for line in lines:
        if paragraphs and paragraphs[-1].section == line.section:
            paragraphs[-1] = _Line(f"{paragraphs[-1].text} {line.text}", line.section, paragraphs[-1].page)
        else:
            paragraphs.append(line)
    sentences = [_Line(s.strip(), p.section, p.page)
                 for p in paragraphs for s in SENTENCE_END.split(p.text) if s.strip()]
    for s in sentences:
        section = s.section or ""
        source = Source(s.text, _citation(document, s))
        if match := TITLED_IN_PROSE.match(s.text):
            years = _tidy_years(match["years"])
            projects.append(ProjectSuggestion(title=match["title"].strip(), status=_status_from_years(years, today),
                                              years=years, summary=s.text, sources=[source]))
        elif PLANNED_CUE.search(s.text) or (PLANNED_SECTION.search(section) and not INTEREST_CUE.search(s.text)):
            projects.append(ProjectSuggestion(title=None, status=PLANNED, years=None, summary=s.text, sources=[source]))
        elif CURRENT_CUE.search(s.text) or CURRENT_SECTION.search(section):
            projects.append(ProjectSuggestion(title=None, status=CURRENT, years=None, summary=s.text, sources=[source]))
        elif INTEREST_CUE.search(s.text) or INTEREST_SECTION.search(section):
            interests.append(Interest(s.text, source.citation))
    # sentences that continue a titled project ("I am looking for residencies with an etching press to
    # extend the project") stay with it, not as a project of their own
    merged: list[ProjectSuggestion] = []
    for p in projects:
        previous = merged[-1] if merged else None
        if (p.title is None and previous is not None and previous.title is not None
                and _section_of(p) == _section_of(previous)):
            previous.summary = f"{previous.summary} {p.summary}"
            previous.sources += p.sources
        else:
            merged.append(p)
    return merged, interests


# -- all documents -------------------------------------------------------------------------------------

def _merge(projects: list[ProjectSuggestion]) -> list[ProjectSuggestion]:
    """One project per title: years from the first mention (the CV comes first), the longest summary,
    any medium, every venue and source."""
    by_key: dict[str, ProjectSuggestion] = {}
    for p in projects:
        same = by_key.get(p.key) if p.title else None
        if same is None:
            by_key[p.key or str(id(p))] = p
            continue
        # a range ("2024–", from the statement) says more than one show's year (the CV's "2025")
        if not same.years or (p.years and "–" in p.years and "–" not in same.years):
            same.years = p.years
        same.medium = same.medium or p.medium
        if p.summary and len(p.summary) > len(same.summary or ""):
            same.summary = p.summary
        if STATUS_ORDER[p.status] < STATUS_ORDER[same.status]:
            same.status = p.status   # "ongoing" in the statement beats a past CV line
        same.venues += [v for v in p.venues if v not in same.venues]
        same.sources += p.sources
    return list(by_key.values())


def _sort_key(p: ProjectSuggestion):
    first_year = int(m.group()) if p.years and (m := re.search(YEAR, p.years)) else 0
    return STATUS_ORDER[p.status], -first_year


def extract_projects(documents: list[tuple[str, str, list[Chunk]]], today: date | None = None) -> Found:
    """documents: (kind, file name, chunks), kind one of cv / statement / portfolio. CV first gives
    the merged projects the CV's years and venues."""
    today = today or date.today()
    order = {"cv": 0, "portfolio": 1, "statement": 2}
    projects, interests = [], []
    for kind, name, chunks in sorted(documents, key=lambda d: order.get(d[0], 3)):
        lines = _lines(chunks)
        if kind == "cv":
            projects += _from_cv(lines, name, today)
        elif kind == "portfolio":
            projects += _from_portfolio(lines, name, today)
        else:
            found, found_interests = _from_statement(lines, name, today)
            projects += found
            interests += found_interests
    return Found(projects=sorted(_merge(projects), key=_sort_key), interests=interests)
