"""
OpenArt — deadline normalization.

Parses RawOpportunity.deadline's free text (mixed languages and
formats - single dates, ranges, prose, multiple application rounds)
into a structured date. Deliberately one simple heuristic, not an
attempt at full calendar semantics: search_dates() finds every
date-like span in the string, and the LATEST one is taken as
deadline_date - matching the common shape (an opening date followed by
a closing/cutoff date, or a single bare date). Never guesses when
nothing parses; deadline_date stays None and deadline_raw is kept so a
human can resolve it later.

dateparser's language list is deliberately restricted to
[source_language, "en"] rather than left unrestricted (200+ locales) -
unrestricted search misparses cross-language tokens. Confirmed case:
Spanish "31 Ago 2023" (31 August 2023) with no language restriction
matched only the "2023" token and silently filled in today's day/month
- a wrong-but-plausible-looking date, not an honest parse failure.
Restricting to ["es", "en"] parses it correctly. See workflow.MD.
"""

from datetime import date

from dateparser.search import search_dates

SETTINGS = {"PREFER_DATES_FROM": "future"}

# Content language and numeric date-format locale aren't always the same
# thing: kunst_dk_denmark's pages are tagged language "en" (the prose is
# English) but dates use Danish DD.MM.YYYY ("24.09.2026, 2:00 PM"), which
# even an unrestricted search_dates() silently misparses (drops day/month,
# keeps only the year - same failure mode as the cross-language case this
# module's language restriction exists to prevent). Adding "da" specifically
# fixes it; kept as an explicit per-source hint rather than broadening every
# source's language list, which would reintroduce that same collision risk
# corpus-wide for one source's quirk.
EXTRA_DATE_LANGUAGES: dict[str, list[str]] = {
    "kunst_dk_denmark": ["da"],
}


def parse_deadline(deadline_raw: str | None, language: str, source: str | None = None) -> date | None:
    if not deadline_raw or not deadline_raw.strip():
        return None

    languages = [language, "en"] if language != "en" else ["en"]
    for extra in EXTRA_DATE_LANGUAGES.get(source, []):
        if extra not in languages:
            languages.append(extra)

    matches = search_dates(deadline_raw, languages=languages, settings=SETTINGS)
    if not matches:
        return None

    return max(dt.date() for _, dt in matches)
