"""Projects read from an artist's documents by rules (src/rag/project_rules.py). Run with: uv run pytest"""
import glob
import os
from datetime import date

from src.rag.documents import Chunk, read_chunks
from src.rag.project_rules import CURRENT, PAST, PLANNED, extract_projects

TODAY = date(2026, 10, 12)
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def example(artist: str):
    paths = sorted(glob.glob(os.path.join(REPO_ROOT, "examples", "artists", artist, "*")))
    return extract_projects([(os.path.basename(p).split(".")[0], os.path.basename(p), read_chunks(p)) for p in paths],
                            today=TODAY)


def chunk(section, text):
    return Chunk(index=0, section=section, text=text, page=None)


def test_cv_and_portfolio_mentions_become_one_project():
    found = example("tomas_ferreira")
    tidal = next(p for p in found.projects if p.title == "Tidal Bodies")
    assert (tidal.status, tidal.years, tidal.medium) == (PAST, "2025", "8-channel installation")
    assert tidal.venues == ["Galeria Zé dos Bois, Lisbon"] and tidal.summary.startswith("8-channel sound installation")
    assert len(tidal.sources) == 2   # the CV line and the portfolio heading
    assert [p.title for p in found.projects] == ["Tidal Bodies", "Listening to the Tagus", "Underwater Choir", "Rain Score"]


def test_an_open_range_in_the_statement_makes_a_current_project():
    found = example("ilka_varga")
    archive = found.projects[0]
    assert (archive.title, archive.status, archive.years) == ("Low Tide Archive", CURRENT, "2024–")


def test_hard_wrapped_statement_sentences_are_read_whole():
    interests = [i.text for i in example("tomas_ferreira").interests]
    assert "I am interested in residencies by water, in commissions for public space, and in collaborations " \
           "with ecologists and hydrologists." in interests


def test_group_shows_and_table_headings_are_not_projects():
    found = extract_projects([("cv", "cv.pdf", [
        chunk("Group exhibitions", "2024 New Positions in Print, Künstlerhaus Graz"),
        chunk("Exhibitions", "Year | Work | Venue\n2023 | Paper Weather | Studio Kapu, Budapest")])], today=TODAY)
    assert [p.title for p in found.projects] == ["Paper Weather"]


def test_planned_and_current_wording_in_a_statement():
    found = extract_projects([("statement", "statement.md", [
        chunk("Practice", "I paint rivers. My next project is a series about the Sava delta."),
        chunk("Now", "I am currently developing a sound walk for Ljubljana.")])], today=TODAY)
    assert [(p.title, p.status) for p in found.projects] == [(None, CURRENT), (None, PLANNED)]


def test_a_future_year_in_a_cv_is_planned():
    found = extract_projects([("cv", "cv.pdf", [chunk("Upcoming exhibitions", "2027 Salt Lines, Kunsthalle Wien")])],
                             today=TODAY)
    assert (found.projects[0].title, found.projects[0].status) == ("Salt Lines", PLANNED)


# -- a combined CV + portfolio file, any slot (the layout of a real "CV-Portfolio.pdf") -----------------

WORK_PAGES = """Paloma Schnitzer - Curriculum Vitae
3
Surplus
2026 - 1 channel video - 14'30'' - Color - Sound
A film essay composed of archival footage from fictional cinema.
Surplus, still frame
4
Memorias
Feature film- in post-production. 2026-2027
An audiovisual self-portrait.
5
To Twist The Course of Signs
(Torcer el rumbo de los signos)
2025 - 3-channel Video Installation - 20 min - no
sound - color - CRT monitors, MDF -
23 × 23 × 100 cm each.
Sourced from archive images coming from surveillance cameras.
Installation view at Halfsister, Berlin
City Loop
2018 - 6-Channel videoinstallation. CTR Monitors, Bricks, Debris.
Walk on rubbles."""


def test_work_pages_title_then_date_line():
    found = extract_projects([("portfolio", "p.pdf", [chunk(None, WORK_PAGES)])], today=TODAY)
    works = {p.title: p for p in found.projects}
    assert set(works) == {"Surplus", "Memorias", "To Twist The Course of Signs (Torcer el rumbo de los signos)",
                          "City Loop"}
    assert works["Surplus"].summary == "A film essay composed of archival footage from fictional cinema."  # caption ends it
    assert (works["Memorias"].status, works["Memorias"].years) == (CURRENT, "2026–2027")
    assert works["Memorias"].medium == "Feature film- in post-production"
    twist = works["To Twist The Course of Signs (Torcer el rumbo de los signos)"]
    assert twist.medium.endswith("no sound - color - CRT monitors, MDF 23 × 23 × 100 cm each")  # wrapped medium
    assert twist.summary == "Sourced from archive images coming from surveillance cameras."
    assert (works["City Loop"].status, works["City Loop"].years) == (PAST, "2018")


def test_a_degree_over_its_dates_is_not_a_work():
    found = extract_projects([("cv", "cv.txt", [chunk(None, "MFA Painting\n2016 - 2018")]),
                              ("cv", "cv2.txt", [chunk("Education", "Studio Practice\n2016 - 2018")])], today=TODAY)
    assert found.projects == []


def test_venue_first_exhibitions_take_the_quoted_title_across_a_wrapped_line():
    text = "2025 New Fears Gallery,\n“Tender Is The Riot” , Berlin.\n2019 Hangar, “Paratext n.40” , Barcelona."
    found = extract_projects([("portfolio", "p.pdf", [chunk("Selected exhibitions", text)])], today=TODAY)
    assert [(p.title, p.venues) for p in found.projects] == [("Tender Is The Riot", ["New Fears Gallery, Berlin"]),
                                                             ("Paratext n.40", ["Hangar, Barcelona"])]


def test_a_cvs_lists_are_not_read_as_statement_sentences():
    """"(Upcoming)" in an exhibition list or "not currently enrolled" under Education is no project."""
    found = extract_projects([("cv", "cv.txt", [
        chunk("Education", "2006–2010 BA in Music, University of Porto\nNot currently enrolled"),
        chunk("Exhibitions", "Bethanien Studio 1 “To Whom it May Concern”, Berlin (Upcoming)")])], today=TODAY)
    assert found.projects == []


def test_a_titled_study_in_education_is_not_a_work():
    found = extract_projects([("cv", "cv.txt", [chunk("EDUCATION", "BFA Photography, Tokyo Polytechnic University, 2008")])],
                             today=TODAY)
    assert found.projects == []


def test_collaborations_under_exhibitions_are_not_projects():
    text = "2019 Hangar, “Paratext n.40” , Barcelona.\nCollaborations\n2022 Film editor /assistant"
    found = extract_projects([("portfolio", "p.pdf", [chunk("Selection of exhibitions", text)])], today=TODAY)
    assert [p.title for p in found.projects] == ["Paratext n.40"]


def test_category_from_the_cv_section_and_work_wins_when_merged():
    found = extract_projects([
        ("cv", "cv.txt", [chunk("Solo exhibitions", "2023 Paper Weather, Studio Kapu, Budapest\n2025 Tidal Bodies, ZDB, Lisbon"),
                          chunk("Performances", "2024 Rain Score, Casa da Música, Porto"),
                          chunk("Commissions", "2022 River Wall, City of Porto"),
                          chunk("Productions", "2016 Premier Souffle, Friche, Marseille")]),
        ("portfolio", "p.txt", [chunk("Works", "Tidal Bodies, 2025\n8-channel sound installation.")])], today=TODAY)
    category = {p.title: p.category for p in found.projects}
    assert category == {"Paper Weather": "exhibition", "Tidal Bodies": "work", "Rain Score": "performance",
                        "River Wall": "commission", "Premier Souffle": "work"}
