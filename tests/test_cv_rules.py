"""Tests for the rule-based profile extractor (src/rag/cv_rules.py) on the fictional CVs.

The development CVs (examples/artists/) and the held-out ones (examples/cv_eval/, answers in
truth.json, written before the rules). scripts/evaluate_cv_rules.py prints the full comparison;
these tests pin what it found, so a change to the rules can't silently break a field."""

import json
import os
from datetime import date

import pytest

from src.rag.cv_rules import extract_practice, extract_profile
from src.rag.documents import Chunk, read_chunks

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TODAY = date(2026, 10, 8)


def extract(path: str) -> dict:
    found = extract_profile(read_chunks(os.path.join(ROOT, path)), os.path.basename(path), TODAY)
    return {s.field: s for s in found}


def chunks(*lines: str, section: str | None = None) -> list[Chunk]:
    return [Chunk(index=0, section=section, text="\n".join(lines), page=None)]


def test_ilka_cv():
    found = extract("examples/artists/ilka_varga/cv.pdf")
    assert {f: s.value for f, s in found.items()} == {
        "birth_date": "1994-03-12", "nationalities": ["HU"], "residence_country": "AT",
        "disciplines": ["Visual Arts"], "active_since": 2021, "has_degree": True, "graduation_year": 2021,
        "degree_field": "Painting and Graphic Arts", "languages": ["de", "en", "hu"],
        "education": [{"institution": "Academy of Fine Arts Vienna", "city": None, "country": "AT"},
                      {"institution": "Hungarian University of Fine Arts", "city": "Budapest", "country": "HU"}],
    }
    assert found["birth_date"].quote == "Born 12 March 1994 in Debrecen, Hungary"
    assert found["birth_date"].citation == "cv.pdf · p. 1 · PERSONAL DETAILS"


def test_tomas_cv():
    found = extract("examples/artists/tomas_ferreira/cv.docx")
    assert found["nationalities"].value == ["BR", "PT"]
    assert found["applicant_type"].value == "individual"
    assert found["currently_enrolled"].value is False
    assert found["active_since"].value == 2019


# every stated, held-out fact the rules found is right, and they invent nothing
with open(os.path.join(ROOT, "examples", "cv_eval", "truth.json"), encoding="utf-8") as f:
    HELD_OUT = {k: v for k, v in json.load(f).items() if not k.startswith("_")}


@pytest.mark.parametrize("name", sorted(HELD_OUT))
def test_held_out_cvs_have_no_wrong_or_invented_values(name):
    truth = HELD_OUT[name]
    for field, suggestion in extract(f"examples/cv_eval/{name}").items():
        expected = truth[field]
        assert expected not in (None, []), f"{field} invented: {suggestion.value!r}"
        if field == "disciplines":
            assert set(suggestion.value) <= set(expected)
        elif field == "active_since":
            assert expected[0] <= suggestion.value <= expected[1]
        elif field == "degree_field":
            assert suggestion.value.lower() in expected
        elif field == "education":
            # every school read is one the CV lists; a country left empty is fine, a wrong one is not
            schools = {school["institution"]: school["country"] for school in expected}
            for school in suggestion.value:
                assert school["institution"] in schools, school
                assert school["country"] in (None, schools[school["institution"]]), school
        else:
            assert suggestion.value == expected, field


@pytest.mark.parametrize("line, expected", [
    ("Born 12 March 1994 in Debrecen", "1994-03-12"),
    ("Date of birth: March 12, 1994", "1994-03-12"),
    ("DOB 1994-03-12", "1994-03-12"),
    ("Born: 12.03.1994", "1994-03-12"),
    ("b. 1994, Debrecen", None),                     # a year alone is not a birth date
    ("Born 12 March 2099", None),                    # in the future
    ("Exhibition opened 12 March 2020", None),       # a date, but not a birth date
])
def test_birth_dates(line, expected):
    found = {s.field: s.value for s in extract_profile(chunks(line), "cv.txt", TODAY)}
    assert found.get("birth_date") == expected


def test_language_lines_are_not_nationalities():
    found = {s.field for s in extract_profile(chunks("Hungarian (native), German (fluent)", section="LANGUAGES"),
                                              "cv.txt", TODAY)}
    assert "nationalities" not in found


def test_a_degree_in_progress_is_not_a_finished_degree():
    found = {s.field: s.value for s in extract_profile(
        chunks("2024 - present: MA Fine Art, Royal Academy Schools", section="EDUCATION"), "cv.txt", TODAY)}
    assert found == {"currently_enrolled": True,
                     "education": [{"institution": "Royal Academy Schools", "city": None, "country": None}]}


def test_nothing_found_in_an_empty_cv():
    assert extract_profile(chunks("Contact me for a portfolio."), "cv.txt", TODAY) == []


# -- layouts of CV templates (two columns, dates on their own line) -----------------------------------

def test_a_place_alone_in_the_contact_block_is_the_residence():
    found = {s.field: s for s in extract_profile(
        chunks("Ana Silva", "Visual artist", "ana@example.org", "Berlin"), "cv.pdf", TODAY)}
    assert found["residence_country"].value == "DE" and found["residence_country"].quote == "Berlin"
    found = {s.field: s.value for s in extract_profile(chunks("Ana Silva", "Lisbon, Portugal"), "cv.pdf", TODAY)}
    assert found["residence_country"] == "PT"


@pytest.mark.parametrize("line", ["German", "Berlin Biennale 2024", "Hauptstraße 5, 10115 Berlin"])
def test_not_a_place_line(line):
    found = {s.field for s in extract_profile(chunks("Ana Silva", line), "cv.pdf", TODAY)}
    assert "residence_country" not in found


def test_degree_title_over_two_lines_with_dates_below():
    found = {s.field: s.value for s in extract_profile(chunks(
        "B.A. in Political Science and International", "Relations.", "University of Rome", "09/2013 – 06/2016 | Rome",
        section="EDUCATION"), "cv.pdf", TODAY)}
    assert found == {"has_degree": True, "graduation_year": 2016,
                     "degree_field": "Political Science and International Relations"}


def test_a_programme_still_running_means_enrolled():
    found = {s.field: s.value for s in extract_profile(chunks(
        "AI Engineering bootcamp", "Spiced Academy", "06/2026 – Present | Berlin", section="EDUCATION"),
        "cv.pdf", TODAY)}
    assert found == {"currently_enrolled": True}


def test_dates_of_the_next_entry_are_not_taken():
    found = {s.field: s.value for s in extract_profile(chunks(
        "MFA Painting, Royal Academy", "BA Fine Art, Goldsmiths", "2010 – 2013", section="EDUCATION"),
        "cv.pdf", TODAY)}
    assert found["graduation_year"] == 2013 and found["degree_field"] == "Fine Art"


# -- statements and portfolios (extract_practice) -----------------------------------------------------

def practice(path: str, kind: str) -> dict:
    found = extract_practice(read_chunks(os.path.join(ROOT, path)), os.path.basename(path), kind, TODAY)
    return {s.field: s.value for s in found}


def test_dev_statements_and_portfolio():
    assert practice("examples/artists/ilka_varga/statement.docx", "statement") == {"disciplines": ["Visual Arts"]}
    tomas = practice("examples/artists/tomas_ferreira/portfolio.txt", "portfolio")
    assert tomas["active_since"] == 2021 and "Visual Arts" in tomas["disciplines"]


def test_a_discipline_named_once_in_passing_is_not_taken():
    found = practice("examples/cv_eval/jonas_lindqvist_statement.txt", "statement")
    assert found == {"disciplines": ["Dance"]}          # "a live musician in the room" isn't Music


def test_a_collective_statement():
    found = practice("examples/cv_eval/bruit_blanc_statement.md", "statement")
    assert found["applicant_type"] == "group" and found["disciplines"][0] == "Theatre"


def test_known_held_out_error_is_still_there():
    """Lucía's statement names photography twice while writing about archives (the trap): the rule
    takes it. Pinned so it shows up if a change fixes it, or makes it worse."""
    assert "Photography" in practice("examples/cv_eval/lucia_romero_statement.md", "statement")["disciplines"]


def test_career_stage_is_never_read():
    found = extract_practice(chunks("I am an emerging artist and an established painter."), "s.md", "statement", TODAY)
    assert "career_stage" not in {s.field for s in found}
