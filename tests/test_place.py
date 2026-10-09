"""Tests for src/processing/place.py. Run with: uv run pytest"""

from datetime import datetime, timezone

from src.models.processed_opportunity import ProcessedOpportunity
from src.processing.canonicalize import CANONICAL_COUNTRIES
from src.processing.place import CITY_COUNTRY, PLACE_CORRECTIONS, correct_places, place_countries


def opp(**fields) -> ProcessedOpportunity:
    base = dict(id="opp", source="test", source_url="https://example.org/call", language="en", title="t",
                title_en="t", requirements_text="", requirements_text_en="", processed_at=datetime.now(timezone.utc))
    return ProcessedOpportunity(**{**base, **fields})


def test_every_country_is_in_the_vocabulary():
    places = list(CITY_COUNTRY.values()) + [c for countries, _ in PLACE_CORRECTIONS.values() for c in countries]
    assert set(places) <= set(CANONICAL_COUNTRIES)


def test_the_city_decides_over_who_may_apply():
    # Gasworks: a residency in London for artists based in Brazil
    assert place_countries(opp(city_en="London", country_canonical=["Brazil"])) == ["United Kingdom"]
    assert place_countries(opp(city_en="Brussels", country_canonical=[])) == ["Belgium"]


def test_unknown_city_or_no_city_keeps_the_extracted_country():
    assert place_countries(opp(city_en="Linz, Marseille, Košice", country_canonical=["Austria", "France"])) == [
        "Austria", "France"]
    assert place_countries(opp(country_canonical=["Norway"])) == ["Norway"]


def test_a_reviewed_correction_wins():
    call = opp(id="kunstlerhaus_bethanien_ad1d16a215d9", country_canonical=["Sweden"])
    assert place_countries(call) == ["Germany"]


def test_correct_places_counts_changes():
    records = [opp(city_en="Paris", country_canonical=["Morocco"]), opp(city_en="Paris", country_canonical=["France"])]
    assert correct_places(records) == 1
    assert [r.country_canonical for r in records] == [["France"], ["France"]]
