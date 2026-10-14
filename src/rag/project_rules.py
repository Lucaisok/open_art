"""
OpenArt — read the artist's projects (past, current, planned) and interests out of their documents
with plain rules. Nothing leaves the machine, as for the profile pre-fill (cv_rules.py).

    found = extract_projects([("cv", "cv.pdf", cv_chunks), ("statement", "statement.docx", st_chunks)])
    found.projects   # ProjectSuggestion(title, status, years, summary, medium, venues, sources)
    found.interests  # Interest(text, quote, citation)

Why projects: 64% of open calls ask mainly for a new project (workflow.MD, "Projects page — plan"),
and the application agent needs to know which one. The artist reviews every suggestion; nothing is
saved without that, and they can add projects by hand (a planned project is often in no document).

Rules, each run on every document whatever its slot (one file may hold CV, statement and works):

  CV lists    lines with a year in a works section (exhibitions, performances, works, projects,
              commissions, screenings, concerts, productions; not "group" shows, whose title isn't the
              artist's work): "2025 | Tidal Bodies (installation) | Venue" or
              "2025 Low Tide Archive, Galerie Nord, Vienna" -> title, year, medium, venue;
              "2025 New Fears Gallery, “Tender Is The Riot”, Berlin" (venue first) -> the quoted title.
              A line ending in a comma or an open quote continues on the next one
  works       a "Title, 2025" line, and the lines under it up to the next one as its summary; or a work
              page: a title line, then a date line ("2026 - 1 channel video", "2025 - 2026", "Feature
              film, in post-production. 2026-2027"), then its description up to a caption ("Installation
              view at...", "..., still frame") or a page number. Never under Education, never a degree
  prose       "Title (2024-) is ..." -> a titled project (open range = current); a section named
              current / ongoing / upcoming / future / plans / next, or a sentence saying "currently",
              "I am developing", "my next project", "I plan" -> an untitled current / planned project;
              a "Themes" / "Interests" section or "I am interested in" -> an interest. Not in a CV's
              lists (Education, Exhibitions...): "(Upcoming)" there is not a project

The same title in several documents is one project (CV year and venue + portfolio description).
Each has a category: a CV list line takes its section's (Exhibitions -> exhibition, Performances ->
performance, Commissions -> commission, Works / Projects / Productions -> work); everything else is a
work. When mentions merge, work wins.
"""

import re
from dataclasses import dataclass, field
from datetime import date

from src.rag.cv_rules import CAREER_SECTION, DEGREE, EDUCATION_SECTION, SENTENCE_END, _citation, _Line, _lines
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
    category: str = "work"        # work / exhibition / performance / commission (CATEGORY_OF_SECTION)

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
# what a CV list line is, from its section. The first word that appears in the section name decides
# ("Exhibitions and performances" -> exhibition). A production is a company's own piece: a work.
WORK, EXHIBITION, PERFORMANCE, COMMISSION = "work", "exhibition", "performance", "commission"
CATEGORY_OF_SECTION = [
    (re.compile(r"\b(works|projects?|productions?)\b", re.I), WORK),
    (re.compile(r"\b(exhibitions?|shows?|screenings?|festivals?)\b", re.I), EXHIBITION),
    (re.compile(r"\b(performances?|concerts?)\b", re.I), PERFORMANCE),
    (re.compile(r"\b(commissions?)\b", re.I), COMMISSION),
]


def _category_of(section: str) -> str:
    found = [(match.start(), category) for pattern, category in CATEGORY_OF_SECTION
             if (match := pattern.search(section))]
    return min(found)[1] if found else WORK
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

# "2025 New Fears Gallery, “Tender Is The Riot”, Berlin": the venue first, the title in quotes
QUOTED_TITLE = re.compile(r"[“\"](?P<title>[^”\"]{2,80})[”\"]")


def _unfinished(text: str) -> bool:
    """A CV entry wrapped onto the next line: it ends with a comma or leaves a quote open."""
    return text.rstrip().endswith(",") or text.count("“") > text.count("”")


def _from_cv(lines: list[_Line], document: str, today: date) -> list[ProjectSuggestion]:
    found = []
    for i, line in enumerate(lines):
        if not (line.section and WORKS_SECTION.search(line.section)) or GROUP_SECTION.search(line.section):
            continue
        match = CV_WORK_LINE.match(line.text)
        if not match:
            continue   # a heading row ("Year | Work | Venue") or prose
        rest, text = match["rest"], line.text
        if _unfinished(rest) and i + 1 < len(lines) and not CV_WORK_LINE.match(lines[i + 1].text):
            rest, text = f"{rest} {lines[i + 1].text}", f"{line.text} {lines[i + 1].text}"
        if quoted := QUOTED_TITLE.search(rest):
            title = quoted["title"].strip()
            venue = ", ".join(p for p in (rest[:quoted.start()].strip(" ,"), rest[quoted.end():].strip(" ,.*"))
                              if p) or None
        else:
            parts = [p.strip() for p in re.split(r"\s*\|\s*", rest) if p.strip()]
            if len(parts) == 1:   # "Low Tide Archive, Galerie Nord, Vienna": title, then where
                parts = [p.strip() for p in rest.split(",", 1)]
            title, venue = parts[0], ", ".join(parts[1:]) or None
        medium = None
        if m := TRAILING_MEDIUM.search(title):
            medium, title = m["medium"], title[:m.start()].strip()
        years = _tidy_years(match["years"])
        found.append(ProjectSuggestion(title=title, status=_status_from_years(years, today), years=years,
                                       medium=medium, venues=[venue] if venue else [],
                                       sources=[Source(text, _citation(document, line))],
                                       category=_category_of(line.section)))
    return found


def _from_portfolio(lines: list[_Line], document: str, today: date) -> list[ProjectSuggestion]:
    found: list[ProjectSuggestion] = []
    for line in lines:
        if EDUCATION_SECTION.search(line.section or "") or DEGREE.search(line.text):
            continue   # "BFA Photography, Tokyo Polytechnic University, 2008" is a study, not a work
        if match := PORTFOLIO_HEADING.match(line.text):
            years = _tidy_years(match["years"])
            found.append(ProjectSuggestion(title=match["title"].strip(), status=_status_from_years(years, today),
                                           years=years, sources=[Source(line.text, _citation(document, line))]))
        elif found and line.section == _section_of(found[-1]):
            # a description line under the last heading (same section): part of its summary
            found[-1].summary = f"{found[-1].summary} {line.text}" if found[-1].summary else line.text
    return found


# A work page in a portfolio: the title on its own line, then a date line, then the description.
#   Surplus                                          City Loop                 Memorias
#   2026 - 1 channel video - 14'30'' - Color         2018 - 6-Channel video... Feature film- in post-production. 2026-2027
#   A film essay composed of archival footage...     Walk on rubbles. ...      An audiovisual self-portrait...
# the date line: years first ("2025 - 2026", "2026 - 1 channel video"), or a short medium then the years
DATE_FIRST_LINE = re.compile(rf"^(?P<years>{YEAR}(?:\s*[–-]\s*{YEAR})?)\s*(?:$|[–-]\s+(?P<medium>.+)$)")
DATE_LAST_LINE = re.compile(rf"^(?P<medium>[^\d,]{{3,60}}?)[\s.;–-]+(?P<years>{YEAR}(?:\s*[–-]\s*{YEAR})?)\.?$")
NOT_A_MEDIUM = re.compile(r"\b(since|from|in|until|born)\s*$", re.I)    # "Lives in Vienna since 2018"
# image captions and page numbers end a work's description
CAPTION = re.compile(r"^(installation view|exhibition view|still|video stills?|images?\s*:|photo(graph)?s?\s*:)|"
                     r",\s*(video\s+)?stills?(\s+frames?)?\s*$", re.I)
PAGE_NUMBER = re.compile(r"^\d{1,3}$")
DIMENSIONS = re.compile(r"^\d+(?:[.,]\d+)?\s*(?:cm|m|mm)?\s*[×x]\s*\d")   # "23 × 23 × 100 cm each."
SUBTITLE = re.compile(r"^\(.+\)$")                    # "(Torcer el rumbo de los signos)" under the title
MAX_TITLE_WORDS = 12


def _date_line(text: str) -> re.Match | None:
    if match := DATE_FIRST_LINE.match(text):
        return match
    match = DATE_LAST_LINE.match(text)
    if match and len(text.split()) <= 8 and not NOT_A_MEDIUM.search(match["medium"]):
        return match
    return None


def _is_title(line: _Line) -> bool:
    """A work's title line: short, capitalised, no comma ("Tidal Bodies, 2025" is the other rule), not a
    sentence, caption, page number or degree ("MFA Painting" over "2016 - 2018" is a study, not a work)."""
    text = line.text
    return (len(text.split()) <= MAX_TITLE_WORDS and text[:1].isupper() and "," not in text
            and text[-1] not in ".;:" and not PAGE_NUMBER.match(text) and not CAPTION.search(text)
            and not DEGREE.search(text) and not EDUCATION_SECTION.search(line.section or ""))


def _from_work_pages(lines: list[_Line], document: str, today: date) -> list[ProjectSuggestion]:
    # first the works: (index of the date line, index of the title line, title, date match)
    works = []
    for i, line in enumerate(lines):
        if not (match := _date_line(line.text)):
            continue
        j, subtitle = i - 1, None
        if j >= 0 and SUBTITLE.match(lines[j].text):
            subtitle, j = lines[j].text, j - 1
        if j >= 0 and _is_title(lines[j]):
            works.append((i, j, lines[j].text + (f" {subtitle}" if subtitle else ""), match))
    # then each work's description: the lines after its date line, up to a caption, a page number or
    # the next work's title
    found = []
    for n, (i, j, title, match) in enumerate(works):
        end = works[n + 1][1] if n + 1 < len(works) else len(lines)
        medium, k = match["medium"] or "", i + 1
        # "2025 - 3-channel Video Installation - 20 min - no" / "sound - color - CRT monitors, MDF -" / "23 × ..."
        while medium and k < end and (lines[k].text[:1].islower() or DIMENSIONS.match(lines[k].text)):
            medium, k = f"{medium} {lines[k].text}", k + 1
        summary = []
        for line in lines[k:end]:
            if CAPTION.search(line.text) or PAGE_NUMBER.match(line.text):
                break
            summary.append(line.text)
        years = _tidy_years(match["years"])
        medium = medium.strip(" .–-") or None
        found.append(ProjectSuggestion(
            title=title, status=_status_from_years(years, today), years=years, medium=medium,
            summary=" ".join(summary) or None,
            sources=[Source(f"{lines[j].text} / {lines[i].text}", _citation(document, lines[j]))]))
    return found


def _section_of(project: ProjectSuggestion) -> str | None:
    citation = project.sources[0].citation.split(" · ")
    return citation[-1] if len(citation) > 1 and not citation[-1].startswith("p. ") else None


def _cv_list_section(section: str | None) -> bool:
    """A CV list (Education, Exhibitions...): its "(Upcoming)" or "not currently enrolled" is not a
    project. A "Current project" / "Future plans" section stays prose."""
    section = section or ""
    return bool(EDUCATION_SECTION.search(section) or CAREER_SECTION.search(section)) \
        and not (CURRENT_SECTION.search(section) or PLANNED_SECTION.search(section))


def _from_statement(lines: list[_Line], document: str, today: date) -> tuple[list[ProjectSuggestion], list[Interest]]:
    projects, interests = [], []
    # statements are often hard-wrapped ("I am interested in residencies by\nwater, ..."): join the
    # lines of one section back into a paragraph before cutting it into sentences
    paragraphs: list[_Line] = []
    for line in lines:
        if _cv_list_section(line.section):
            continue
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
        if p.category == WORK:
            same.category = WORK     # a CV's exhibition line + the portfolio's work: one work, shown there
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
        # every rule on every document, whatever its slot: one file may hold CV, statement and works
        # (as for the profile, cv_rules.extract_all). Each rule only reads its own layout.
        lines = _lines(chunks)
        projects += _from_cv(lines, name, today)
        projects += _from_portfolio(lines, name, today)
        projects += _from_work_pages(lines, name, today)
        found, found_interests = _from_statement(lines, name, today)
        projects += found
        interests += found_interests
    return Found(projects=sorted(_merge(projects), key=_sort_key), interests=interests)
