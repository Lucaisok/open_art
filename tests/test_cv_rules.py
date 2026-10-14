"""Tests for the rule-based profile extractor (src/rag/cv_rules.py) on the fictional CVs.

The development CVs (examples/artists/) and the held-out ones (examples/cv_eval/, answers in
truth.json, written before the rules). scripts/evaluate_cv_rules.py prints the full comparison;
these tests pin what it found, so a change to the rules can't silently break a field."""

import json
import os
from datetime import date

import pytest

from src.rag.cv_rules import extract_all, extract_practice, extract_profile
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
        "birth_date": "1994-03-12", "nationalities": ["HU"], "residence_country": "AT", "residence_city": "Vienna",
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


@pytest.mark.parametrize("line, country, city", [
    ("Lives and works in Berlin", "DE", "Berlin"),
    ("Lives and works in Leipzig, Germany", "DE", "Leipzig"),     # a city the app doesn't know, before a country
    ("Based in Germany", "DE", None),                             # only a country
    ("Lives and works between Berlin and Oslo", "DE", None),      # two cities: no one city
    ("Vienna, Austria", "AT", "Vienna"),                          # a contact-block line
])
def test_residence_city(line, country, city):
    found = {s.field: s.value for s in extract_profile(chunks("Ana Silva", line), "cv.pdf", TODAY)}
    assert found["residence_country"] == country
    assert found.get("residence_city") == city


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


# -- every rule on any document (extract_all) ---------------------------------------------------------

def test_a_cv_inside_a_portfolio_is_read():
    """One PDF holding bio, CV and works (like a real "CV-Portfolio.pdf"). The PDF reader marked only
    "Education", so the headings in the text are found too: exhibitions aren't read as studies."""
    doc = [Chunk(index=0, section=None, page=1,
                 text="Ana Ruiz (b. 1988, Buenos Aires; based in Berlin) is an artist working with film."),
           Chunk(index=1, section="Education", page=2,
                 text="2022-2025 MA Kunst und Medien, Berlin\nUniversity of the Arts (UDK), Berlin\n"
                      "Selection of exhibitions and screenings\n2025 New Fears Gallery, “Tender Is The Riot”, Berlin."),
           Chunk(index=2, section="Education", page=2,
                 text="2013 Faena Arts Center, Buenos Aires\nResidencies and programs\n2019 Hangar, Barcelona, Spain.")]
    found = {s.field: s for s in extract_all(doc, "cv-portfolio.pdf", "portfolio", TODAY)}
    assert found["residence_country"].value == "DE" and found["residence_city"].value == "Berlin"
    assert found["active_since"].value == 2013
    assert found["active_since"].citation == "cv-portfolio.pdf · p. 2 · Selection of exhibitions and screenings"
    assert found["graduation_year"].value == 2025 and found["degree_field"].value == "Kunst und Medien"
    # the school is on the line below the degree; both lines are quoted
    assert found["education"].value == [{"institution": "University of the Arts (UDK)", "city": "Berlin",
                                         "country": "DE"}]
    assert "University of the Arts" in found["education"].quote


CV_ONLY = {"birth_date", "nationalities", "residence_country", "residence_city"}


@pytest.mark.parametrize("text", [
    "The festival was born on 3 May 2019 in a squat.",
    "A work about citizenship in Mexico and Brazil.",
    "A performance based in Lisbon, Portugal, for one dancer.",
    "The project is based in Lisbon, Portugal.",
    "It works in Portugal and Spain alike.",
])
def test_prose_is_not_read_as_a_cv_fact(text):
    assert not {s.field for s in extract_all(chunks(text), "s.md", "statement", TODAY)} & CV_ONLY


@pytest.mark.parametrize("text, country", [
    ("Paloma Schnitzer (b. 1988; based in Berlin) is an artist.", "DE"),
    ("Paloma is based in Lisbon, Portugal.", "PT"),
    ("She works in Vienna, Austria.", "AT"),
])
def test_residence_said_of_the_artist(text, country):
    found = {s.field: s.value for s in extract_all(chunks(text), "s.md", "statement", TODAY)}
    assert found["residence_country"] == country


@pytest.mark.parametrize("text, codes", [
    ("Dual Brazilian/Portuguese citizenship", ["BR", "PT"]),
    ("I am a citizen of Italy.", ["IT"]),
    ("Swedish citizen, living in Berlin since 2019.", ["SE"]),
])
def test_nationality_tied_to_the_word(text, codes):
    found = {s.field: s.value for s in extract_all(chunks(text), "s.md", "statement", TODAY)}
    assert found["nationalities"] == codes


def test_a_year_inside_prose_is_not_a_career_start():
    """Ilka's statement: "Low Tide Archive (2024-) is a series..." sits under a heading but is prose."""
    path = "examples/artists/ilka_varga/statement.docx"
    found = extract_all(read_chunks(os.path.join(ROOT, path)), "statement.docx", "statement", TODAY)
    assert {s.field: s.value for s in found} == {"disciplines": ["Visual Arts"]}


def test_year_first_works():
    found = {s.field: s.value for s in extract_all(
        chunks("2021 Rain Score", "2018 Weserhalle, “Speculation”, Berlin.",
               "1969 was the year a film by Harun Farocki changed how I think about labour and images."),
        "p.txt", "portfolio", TODAY)}
    assert found["active_since"] == 2018             # the long prose line is not a work


def test_year_first_lines_outside_career_sections_are_not_works():
    found = extract_all(chunks("2015 Guest lecturer, Art Academy", section="Teaching"), "p.txt", "portfolio", TODAY)
    assert "active_since" not in {s.field for s in found}
