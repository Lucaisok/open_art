"""Tests for src/matching/filters.py. Run with: uv run pytest"""

from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from src.matching.filters import MatchFilters, passes
from src.models.processed_opportunity import ProcessedOpportunity

TODAY = date(2026, 10, 5)


def opp(**fields) -> ProcessedOpportunity:
    base = dict(id="opp", source="test", source_url="https://example.org/call", language="en", title="t",
                title_en="t", requirements_text="", requirements_text_en="", processed_at=datetime.now(timezone.utc))
    return ProcessedOpportunity(**{**base, **fields})


def test_default_filters_only_hide_closed_calls():
    assert passes(opp(deadline_date=date(2026, 11, 1)), MatchFilters(), TODAY)
    assert passes(opp(deadline_date=TODAY), MatchFilters(), TODAY)  # closes today: still open
    assert not passes(opp(deadline_date=date(2026, 9, 1)), MatchFilters(), TODAY)
    assert passes(opp(deadline_date=date(2026, 9, 1)), MatchFilters(open_only=False), TODAY)


def test_unknown_values_are_kept():
    unknown = opp()  # no deadline, no type, no discipline, no country, fee unknown
    strict = MatchFilters(opportunity_types=["Residency"], disciplines=["Music"], countries=["Norway"],
                          no_fee_only=True)
    assert passes(unknown, strict, TODAY)


def test_type_discipline_and_country_need_an_overlap():
    call = opp(opportunity_type_canonical=["Residency"], discipline_canonical=["Visual Arts", "Photography"],
               country_canonical=["Germany"])
    assert passes(call, MatchFilters(disciplines=["Photography", "Music"]), TODAY)
    assert not passes(call, MatchFilters(disciplines=["Music"]), TODAY)
    assert not passes(call, MatchFilters(opportunity_types=["Grant/Funding"]), TODAY)
    assert not passes(call, MatchFilters(countries=["Norway"]), TODAY)


def test_multidisciplinary_and_international_match_any_filter():
    call = opp(discipline_canonical=["Multidisciplinary"], country_canonical=["International/Global"])
    assert passes(call, MatchFilters(disciplines=["Dance"], countries=["Norway"]), TODAY)


def test_no_fee_only_hides_known_fees_only():
    assert not passes(opp(application_fee_has_fee=True), MatchFilters(no_fee_only=True), TODAY)
    assert passes(opp(application_fee_has_fee=False), MatchFilters(no_fee_only=True), TODAY)
    assert passes(opp(application_fee_has_fee=True), MatchFilters(), TODAY)


def test_unknown_filter_values_are_rejected():
    with pytest.raises(ValidationError):
        MatchFilters(disciplines=["Pottery"])
    with pytest.raises(ValidationError):
        MatchFilters(countries=["NO"])  # filters use the corpus's country names, not ISO codes
