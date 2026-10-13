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
