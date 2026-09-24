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

import re
from datetime import date

from dateparser import parse as parse_date
from dateparser.search import search_dates

SETTINGS = {"PREFER_DATES_FROM": "future"}

# PDF text extraction sometimes inserts stray spaces around punctuation
# (e.g. "12 : 00", "May 18 , 2026", "( GMT+2 )"), which breaks
# search_dates() outright (no match at all, not just a wrong one) -
# confirmed on u_jazdowski_warsaw. Collapsing that whitespace back out
# before parsing is a safe no-op on already-clean strings.
_TIME_COLON_SPACING = re.compile(r"(?<=\d)\s*:\s*(?=\d)")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.;)])")
_SPACE_AFTER_OPEN_PAREN = re.compile(r"([(])\s+")

# Confirmed dateparser bug (search_dates, not parse()): for "D. Month"
# strings in some locales (nb, hr, ...), the matched span silently drops
# the leading day token, and the resulting day-of-month is either
# today's day (e.g. "7. oktober" -> "oktober" -> today's day + October)
# or a nearby unrelated number, such as a time-of-day digit (e.g.
# "8. april 2026 kl. 13.00" -> "april 2026 kl. 13" -> day 13, from the
# time, not the actual day 8). Reproduced directly; see workflow.MD.
#
# Recovered here by checking, whenever a match's text starts with a
# letter (i.e. it begins with a spelled-out month, not a digit - the
# signature of a chopped-off leading day), whether the raw text
# immediately before the match looks like that dropped day token
# ("D." or plain "D " - the plain form covers English "9 January 2026",
# which drops its day the same way), and if so overriding the parsed
# day with it. The "starts with a letter" gate matters: without it this
# "recovery" misfires on unrelated digits next to an already-correct
# match - confirmed on "Einreichungsfrist 15.01. / 15.05. / 15.09."
# (three already-correctly-parsed rounds; the trailing ".01."/".05." of
# one round, and the following match's own "/ 15" starting character,
# are not a dropped day before the next round) and on "od 8. 12. 2025"
# (a *different*, more severe search_dates failure that drops day AND
# month together, whose lone remaining match is a bare year with no
# leading letter - not this bug, and not safely recoverable by patching
# just the day).
_LEADING_DAY_TOKEN = re.compile(r"(\d{1,2})\.?\s*$")
_STARTS_WITH_LETTER = re.compile(r"^[^\W\d_]")

# A second, separately confirmed search_dates issue, on the common
# "opening date to closing date, YEAR" range shape this module's own
# design already assumes (see docstring): the year is stated once, next
# to the closing date, and search_dates gives the opening-date fragment
# its own match with no year in it - so PREFER_DATES_FROM="future"
# resolves that yearless fragment against *today*, not against the
# year actually stated a few words later, silently bumping it a full
# year ahead whenever that month/day has already passed this year (e.g.
# "March 27 - October 3, 2026" -> ('March 27', 2027-03-27), ('October 3,
# 2026', 2026-10-03) - the *opening* date now sorts as the latest of the
# two, so max() picks it over the real, later, correctly-dated closing
# date). Confirmed across can_serrat, cite_internationale_des_arts,
# nordic_culture_fund and others - this is a systemic range-parsing
# issue, not a single-source quirk like the day-drop bug above.
#
# Fixed the same way: a match whose own text carries no explicit
# four-digit year borrows one from elsewhere in the string, but ONLY
# when exactly one distinct explicit year appears there - with two or
# more (e.g. "Mid 2026 to end 2027"), which one applies is genuinely
# ambiguous, so it's left alone rather than guessed.
_EXPLICIT_YEAR = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")

# search_dates() often returns a redundant *extra* match that's nothing
# but that same bare year (e.g. "before 9 January 2026" ->
# ('January', ...), ('2026', ...)) - a leftover fragment of the very
# date already captured, with no day/month of its own, so whatever
# search_dates defaults its day/month to is noise, not a second
# candidate deadline. Confirmed it can still win max() over the
# already-fixed, more specific match otherwise. Dropped from
# consideration once there's a more specific match to prefer instead -
# gated on the same "exactly one explicit year" condition as the
# borrowing above, so it only fires when we're actually confident this
# bare year isn't itself the one distinct date being reported.
_BARE_YEAR = re.compile(r"^(?:19|20)\d{2}$")

# A bare "D.M.YYYY" string with nothing else around it (no surrounding
# word, no trailing time) confirmed to trip up search_dates() even
# though it's an unambiguous date - "15.10.2026" alone returns only a
# bare-year match ('2026', today's day/month), while the exact same
# text with any context around it ("Deadline: 15.10.2026") parses fine,
# and dateparser.parse() (not search) gets the bare string right on its
# own. Tried as one more candidate below - safe to try unconditionally,
# since parse() already returns None (not a wrong guess) on anything
# that isn't cleanly a single date, confirmed on every range/multi-round/
# vague string this module handles (a date range, "Continuous", etc.).
# Its matched-text marker is never a bare year, so it's exempt from the
# bare-year exclusion above.
_WHOLE_STRING_MARKER = "<whole-string-parse>"

# A single confirmed case of a bare time-of-day ("14.00 CET", no date at
# all) getting matched as if "00" were a 2-digit year, landing on 2100 -
# a search_dates misparse unrelated to the day-recovery bug above. Every
# other parsed year across the corpus falls within a few years of today;
# bounding the window rejects this kind of nonsense date deterministically
# instead of asserting a specific bogus year.
MAX_YEAR_DRIFT = 10

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


def _clean(text: str) -> str:
    text = _TIME_COLON_SPACING.sub(":", text)
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    text = _SPACE_AFTER_OPEN_PAREN.sub(r"\1", text)
    return text


def parse_deadline(deadline_raw: str | None, language: str, source: str | None = None) -> date | None:
    if not deadline_raw or not deadline_raw.strip():
        return None

    languages = [language, "en"] if language != "en" else ["en"]
    for extra in EXTRA_DATE_LANGUAGES.get(source, []):
        if extra not in languages:
            languages.append(extra)

    cleaned = _clean(deadline_raw)
    matches = search_dates(cleaned, languages=languages, settings=SETTINGS) or []

    string_years = {int(m.group()) for m in _EXPLICIT_YEAR.finditer(cleaned)}

    dates = []
    search_pos = 0
    for matched_text, dt in matches:
        idx = cleaned.find(matched_text, search_pos)
        if idx != -1:
            search_pos = idx + len(matched_text)
            if _STARTS_WITH_LETTER.match(matched_text):
                day_token = _LEADING_DAY_TOKEN.search(cleaned[:idx])
                if day_token:
                    recovered_day = int(day_token.group(1))
                    if recovered_day != dt.day and 1 <= recovered_day <= 31:
                        try:
                            dt = dt.replace(day=recovered_day)
                        except ValueError:
                            pass  # recovered day invalid for dt's month/year - keep search_dates' own parse
            if not _EXPLICIT_YEAR.search(matched_text) and len(string_years) == 1:
                (borrowed_year,) = string_years
                if borrowed_year != dt.year:
                    try:
                        dt = dt.replace(year=borrowed_year)
                    except ValueError:
                        pass  # Feb 29 into a non-leap borrowed year - keep search_dates' own parse
        dates.append((matched_text, dt))

    whole = parse_date(cleaned, languages=languages, settings=SETTINGS)
    if whole:
        dates.append((_WHOLE_STRING_MARKER, whole))

    if not dates:
        return None

    non_bare_year = [(t, d) for t, d in dates if not _BARE_YEAR.fullmatch(t.strip())]
    if non_bare_year and len(string_years) == 1:
        dates = non_bare_year

    today = date.today()
    plausible = [dt for _, dt in dates if abs(dt.year - today.year) <= MAX_YEAR_DRIFT]
    if not plausible:
        return None

    return max(dt.date() for dt in plausible)


def is_closed(deadline_date: date | None, as_of: date | None = None) -> bool:
    """True iff deadline_date is a real, parsed date that has already passed.

    Deliberately not wired into normalize.py or export_dataset.py: a
    call's eligibility requirements don't stop being valid RQ1 training
    signal just because its deadline passed, so the data pipeline keeps
    every row regardless of staleness (confirmed 151 of 371 processed
    rows would be dropped if it filtered here - RQ1's annotation pool
    can't afford that). This is the deterministic building block for
    wherever staleness *does* matter - the not-yet-built product/RAG
    layer, which must never recommend a closed call to an artist. See
    CLAUDE.md's principle for the eligibility engine (deterministic and
    auditable, not an LLM call) and workflow.MD's "Known open items".

    A missing/unparsed deadline_date is never "closed" - the absence of
    a parsed date says nothing about whether the call is still open (see
    the deadline-parsing-gaps discussion above), so this only asserts
    the affirmative, confirmed-past case.
    """
    if deadline_date is None:
        return False
    return deadline_date < (as_of or date.today())
