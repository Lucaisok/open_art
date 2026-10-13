"""
OpenArt — the artist's search filters, applied before semantic ranking.

These are preferences ("only residencies", "no application fee"), not
eligibility: who may apply is the eligibility engine's job. Every filter is
plain field comparison, deterministic and testable.

One rule throughout, the same asymmetry as the engine: a call whose field is
unknown is KEPT. A missing deadline, discipline or fee is "not stated", not
"doesn't match", and hiding it would drop calls the artist might want.

One exception, on purpose: "funded only" asks for evidence of support, so a
call whose funding is not stated is hidden by it (keeping it would make the
filter mean nothing: 122 of the 479 calls state no funding).

"Open only" also hides a call whose title names only past years ("ICO FEDS 2017", "Open Call for
2023 Grant Applications"): the deadline parser rolls a deadline without a year ("3 January") to its
next date, so these looked open. Product only: the corpus and the RQ1 data keep every call.
"""

import re
from datetime import date

from pydantic import BaseModel, field_validator

from src.models.processed_opportunity import ProcessedOpportunity
from src.processing.canonicalize import CANONICAL_COUNTRIES, CANONICAL_DISCIPLINES, CANONICAL_OPPORTUNITY_TYPES

# a call labelled with one of these matches any discipline / any country filter
ANY_DISCIPLINE = "Multidisciplinary"
ANY_COUNTRY = "International/Global"

# funding categories that are not money or support in kind: a call offering only these is not "funded"
NOT_FUNDING = {"Mentorship/Training", "Fee Waiver"}


def _check_vocabulary(values: list[str], vocabulary: list[str], field: str) -> list[str]:
    unknown = [v for v in values if v not in vocabulary]
    if unknown:
        raise ValueError(f"unknown {field} {unknown}; expected one of {vocabulary}")
    return values


class MatchFilters(BaseModel):
    open_only: bool = True                 # hide calls whose deadline has passed (no deadline: kept)
    opportunity_types: list[str] = []      # any of these (CANONICAL_OPPORTUNITY_TYPES); [] = all
    disciplines: list[str] = []            # any of these (CANONICAL_DISCIPLINES); [] = all
    countries: list[str] = []              # where the call takes place (CANONICAL_COUNTRIES); [] = all
    no_fee_only: bool = False              # hide calls known to charge an application fee
    funded_only: bool = False              # hide calls with no stated money or support in kind
    text: str = ""                         # words to find in title, organisation, place or type; "" = all

    @field_validator("opportunity_types")
    @classmethod
    def _check_types(cls, values: list[str]) -> list[str]:
        return _check_vocabulary(values, CANONICAL_OPPORTUNITY_TYPES, "opportunity type(s)")

    @field_validator("disciplines")
    @classmethod
    def _check_disciplines(cls, values: list[str]) -> list[str]:
        return _check_vocabulary(values, CANONICAL_DISCIPLINES, "discipline(s)")

    @field_validator("countries")
    @classmethod
    def _check_countries(cls, values: list[str]) -> list[str]:
        return _check_vocabulary(values, CANONICAL_COUNTRIES, "country/countries")


def _overlaps(call_values: list[str], wanted: list[str], wildcard: str | None = None) -> bool:
    """True if the filter is off, the call's value is unknown, or they share a value."""
    if not wanted or not call_values:
        return True
    return wildcard in call_values or bool(set(call_values) & set(wanted))


def is_funded(opp: ProcessedOpportunity) -> bool:
    """True if the call states money or support in kind (grant, travel, housing, materials...)."""
    return any(c.category not in NOT_FUNDING for c in opp.funding_components)


def _contains_text(opp: ProcessedOpportunity, text: str) -> bool:
    """Case-insensitive substring search on what a result card shows: title (English and
    original), organisation, city, country and type."""
    fields = [opp.title_en, opp.title, opp.organisation, opp.city_en, opp.city,
              *opp.country_canonical, *opp.opportunity_type_canonical]
    return text.casefold() in " | ".join(f for f in fields if f).casefold()


# a year in a title: "2025", or the end of a season "2025-26" / "2015/16"; years before 2010 are about
# the content ("immigrants to Norway 1970–2000"), not the call
_TITLE_YEAR_RE = re.compile(r"(?<!\d)(20[1-9]\d)(?:\s?[-/–]\s?(\d{2}))?(?!\d)")
_FULL_YEAR_RE = re.compile(r"(?<!\d)20\d{2}(?!\d)")


def title_says_past(opp: ProcessedOpportunity, today: date) -> bool:
    """True if the title names a year and every one is before this year, and the deadline text
    doesn't name this year or a later one ("Call for pitches—Mayday 2022"). No year: False."""
    years = []
    for title in (opp.title_en, opp.title):
        for start, end in _TITLE_YEAR_RE.findall(title or ""):
            years.append(int(start[:2] + end) if end else int(start))
    if not years or max(years) >= today.year:
        return False
    return not any(int(y) >= today.year for y in _FULL_YEAR_RE.findall(opp.deadline_raw or ""))


def passes(opp: ProcessedOpportunity, filters: MatchFilters, today: date) -> bool:
    """True if the artist's filters keep this call."""
    if filters.open_only and opp.deadline_date is not None and opp.deadline_date < today:
        return False
    if filters.open_only and title_says_past(opp, today):
        return False
    if filters.no_fee_only and opp.application_fee_has_fee is True:
        return False
    if filters.funded_only and not is_funded(opp):
        return False
    if filters.text.strip() and not _contains_text(opp, filters.text.strip()):
        return False
    return (_overlaps(opp.opportunity_type_canonical, filters.opportunity_types)
            and _overlaps(opp.discipline_canonical, filters.disciplines, ANY_DISCIPLINE)
            and _overlaps(opp.country_canonical, filters.countries, ANY_COUNTRY))
