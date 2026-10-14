"""
Web API step 4: the artist profile (save, read, validation) and the CV's suggestions, read at
upload by rules (src/rag/cv_rules.py) and offered until the artist saves after seeing them.

Uses the test database from tests/conftest.py, and the keyword embedder from
test_api_documents.py (no model download).
"""

import os
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api import db, knowledge_base
from api.main import app
from api.models import Profile
from api.profile import ProfileValues, to_artist_profile
from tests.conftest import PASSWORD
from tests.test_api_documents import ILKA, TOMAS, KeywordEmbedder, upload

pytestmark = pytest.mark.usefixtures("api_database")

THIS_YEAR = date.today().year


@pytest.fixture(autouse=True)
def fake_embedder(monkeypatch):
    embedder = KeywordEmbedder()
    monkeypatch.setattr(knowledge_base, "get_embedder", lambda: embedder)


@pytest.fixture
def artist(client):
    assert client.post("/api/auth/signup", json={"email": "artist@example.com", "password": PASSWORD}).status_code == 201
    return client


FULL = {
    "birth_date": "1994-03-12",
    "nationalities": ["hu", "AT", "HU"],
    "residence_country": "at",
    "residence_city": " Vienna ",
    "applicant_type": "individual",
    "disciplines": ["Visual Arts", "Craft"],
    "career_stage": "Emerging/Early-Career",
    "active_since": 2021,
    "currently_enrolled": False,
    "graduation_year": 2021,
    "has_degree": True,
    "degree_field": "  Painting and Graphic Arts ",
}


def save(client, values, evidence=None):
    return client.put("/api/profile", json={"values": values, "evidence": evidence or {}})


def profile_rows() -> int:
    with Session(db.get_engine()) as session:
        return session.scalar(select(func.count()).select_from(Profile))


# -- save and read -----------------------------------------------------------------------------------

def test_empty_profile_before_the_first_save(artist):
    body = artist.get("/api/profile").json()
    assert body["updated_at"] is None and body["evidence"] == {}
    assert body["values"]["nationalities"] == [] and body["values"]["birth_date"] is None


def test_save_normalises_and_reads_back(artist):
    response = save(artist, FULL)
    assert response.status_code == 200
    values = artist.get("/api/profile").json()["values"]
    assert values["nationalities"] == ["AT", "HU"]        # upper-cased, sorted, no duplicates
    assert values["residence_country"] == "AT" and values["residence_city"] == "Vienna"
    assert values["degree_field"] == "Painting and Graphic Arts"
    assert values["birth_date"] == "1994-03-12" and values["active_since"] == 2021


def test_languages_and_schools_are_saved_tidied(artist):
    values = {**FULL, "languages": ["EN", "hu", "en"],
              "education": [{"institution": " Academy of Fine Arts Vienna ", "city": "", "country": "at"},
                            {"institution": "  ", "city": None, "country": None}]}   # an empty card on the form
    assert save(artist, values).status_code == 200
    saved = artist.get("/api/profile").json()["values"]
    assert saved["languages"] == ["en", "hu"]
    assert saved["education"] == [{"institution": "Academy of Fine Arts Vienna", "city": None, "country": "AT"}]
    assert save(artist, {**FULL, "languages": ["xx"]}).status_code == 422


def test_save_replaces_the_whole_profile(artist):
    save(artist, FULL)
    save(artist, {"disciplines": ["Music"]})
    values = artist.get("/api/profile").json()["values"]
    assert values["disciplines"] == ["Music"] and values["birth_date"] is None
    assert profile_rows() == 1


@pytest.mark.parametrize("values", [
    {"nationalities": ["XX"]},
    {"residence_country": "Narnia"},
    {"disciplines": ["Juggling"]},
    {"career_stage": "Any/Open to All"},
    {"applicant_type": "company"},
    {"birth_date": f"{THIS_YEAR + 1}-01-01"},
    {"active_since": 1800},
    {"graduation_year": THIS_YEAR + 1},
    {"degree_field": "x" * 201},
])
def test_invalid_values_are_refused(artist, values):
    assert save(artist, values).status_code == 422
    assert profile_rows() == 0


def test_evidence_is_kept_only_for_filled_fields(artist):
    evidence = {
        "birth_date": {"quote": "Born 12 March 1994", "citation": "cv.pdf · p. 1"},
        "residence_country": {"quote": "Lives in Vienna", "citation": "cv.pdf · p. 1"},   # field left empty
        "favourite_colour": {"quote": "blue", "citation": "cv.pdf"},                     # not a field
    }
    save(artist, {"birth_date": "1994-03-12"}, evidence)
    assert list(artist.get("/api/profile").json()["evidence"]) == ["birth_date"]


def test_years_active_is_worked_out_when_needed():
    values = ProfileValues(active_since=2014, nationalities=["hu"])
    assert to_artist_profile(values, today=date(2026, 10, 8)).years_active == 12
    assert to_artist_profile(values, today=date(2027, 1, 2)).years_active == 13
    assert to_artist_profile(ProfileValues()).years_active is None


# -- suggestions from the artist's documents -------------------------------------------------------

def suggestions(client):
    return client.get("/api/profile").json()["suggestions"]


def review_and_save(client, values=None):
    """Save the way the page does: the values plus the documents whose suggestions it showed."""
    ids = [d["id"] for d in suggestions(client)["documents"]]
    return client.put("/api/profile", json={"values": values or {}, "reviewed_documents": ids})


def test_no_documents_no_suggestions(artist):
    assert suggestions(artist) is None


def test_cv_upload_brings_quoted_suggestions_and_saves_nothing(artist):
    upload(artist, "cv", os.path.join(ILKA, "cv.pdf"))
    found = suggestions(artist)
    assert [d["file_name"] for d in found["documents"]] == ["cv.pdf"]
    items = {s["field"]: s for s in found["items"]}
    assert items["birth_date"]["value"] == "1994-03-12" and items["birth_date"]["source"] == "cv"
    assert items["birth_date"]["quote"] == "Born 12 March 1994 in Debrecen, Hungary"
    assert items["birth_date"]["citation"].startswith("cv.pdf")
    assert items["nationalities"]["value"] == ["HU"] and items["active_since"]["value"] == 2021
    # human in the loop: suggesting is not saving
    assert artist.get("/api/profile").json()["updated_at"] is None
    assert profile_rows() == 0


def test_statement_and_portfolio_fill_only_what_the_cv_left_empty(artist):
    upload(artist, "statement", os.path.join(TOMAS, "statement.md"))
    upload(artist, "portfolio", os.path.join(TOMAS, "portfolio.txt"))
    items = {s["field"]: s for s in suggestions(artist)["items"]}
    assert items["disciplines"]["source"] == "statement" and "Music" in items["disciplines"]["value"]
    assert items["active_since"] == {**items["active_since"], "value": 2021, "source": "portfolio"}
    assert "birth_date" not in items                          # a statement doesn't state that
    upload(artist, "cv", os.path.join(TOMAS, "cv.docx"))
    items = {s["field"]: s for s in suggestions(artist)["items"]}
    assert items["disciplines"]["source"] == "cv"             # the CV first
    assert items["active_since"]["source"] == "cv" and items["active_since"]["value"] == 2019


def test_saving_after_review_stops_the_suggestions(artist):
    upload(artist, "cv", os.path.join(ILKA, "cv.pdf"))
    assert review_and_save(artist, {"birth_date": "1994-03-12"}).status_code == 200
    assert suggestions(artist) is None
    # a later Save without ids keeps the documents marked as reviewed
    save(artist, {"birth_date": "1994-03-12", "disciplines": ["Craft"]})
    assert suggestions(artist) is None


def test_a_new_document_brings_new_suggestions(artist):
    upload(artist, "cv", os.path.join(ILKA, "cv.pdf"))
    review_and_save(artist)
    upload(artist, "statement", os.path.join(ILKA, "statement.docx"))
    found = suggestions(artist)
    assert [d["kind"] for d in found["documents"]] == ["statement"]       # the reviewed CV isn't read again
    upload(artist, "cv", os.path.join(TOMAS, "cv.docx"))                 # a new CV: a new id
    found = suggestions(artist)
    assert [d["kind"] for d in found["documents"]] == ["cv", "statement"]
    assert {s["field"]: s["value"] for s in found["items"]}["nationalities"] == ["BR", "PT"]


def test_a_cv_uploaded_as_portfolio_is_read_as_a_cv(artist):
    """Every document gets every rule: one file holding the CV can go in any slot."""
    upload(artist, "portfolio", os.path.join(ILKA, "cv.pdf"))
    items = {s["field"]: s for s in suggestions(artist)["items"]}
    assert items["birth_date"]["value"] == "1994-03-12" and items["birth_date"]["source"] == "portfolio"
    assert items["nationalities"]["value"] == ["HU"] and items["residence_country"]["value"] == "AT"


def test_documents_with_nothing_found_say_so(artist):
    artist.put("/api/documents/cv", files={"file": ("cv.txt", b"Portfolio on request.\nThank you for reading.")})
    found = suggestions(artist)
    assert found is not None and found["items"] == [] and len(found["documents"]) == 1


def test_reviewed_ids_of_another_users_documents_are_ignored(artist):
    other = TestClient(app)
    other.post("/api/auth/signup", json={"email": "other@example.com", "password": PASSWORD})
    upload(other, "cv", os.path.join(ILKA, "cv.pdf"))
    foreign = [d["id"] for d in suggestions(other)["documents"]]
    assert artist.put("/api/profile", json={"values": {}, "reviewed_documents": foreign}).status_code == 200
    with Session(db.get_engine()) as session:
        assert session.scalar(select(Profile.reviewed_documents)) == []


def test_removing_the_cv_removes_its_suggestions(artist):
    upload(artist, "cv", os.path.join(ILKA, "cv.pdf"))
    artist.delete("/api/documents/cv")
    assert suggestions(artist) is None


# -- privacy -----------------------------------------------------------------------------------------

def test_logged_out_visitors_get_nothing(client):
    assert client.get("/api/profile").status_code == 401
    assert save(client, FULL).status_code == 401


def test_other_users_profiles_are_invisible(artist):
    save(artist, FULL)
    other = TestClient(app)
    other.post("/api/auth/signup", json={"email": "other@example.com", "password": PASSWORD})
    assert other.get("/api/profile").json()["updated_at"] is None


def test_deleting_the_account_deletes_the_profile(artist):
    save(artist, FULL)
    assert artist.request("DELETE", "/api/account", json={"password": PASSWORD}).status_code == 204
    assert profile_rows() == 0


# -- options -----------------------------------------------------------------------------------------

def test_options_for_the_form(client):
    body = client.get("/api/profile/options").json()
    names = [c["name"] for c in body["countries"]]
    assert names == sorted(names) and {"code": "HU", "name": "Hungary"} in body["countries"]
    assert "Visual Arts" in body["disciplines"]
    assert body["career_stages"] == ["Student", "Emerging/Early-Career", "Mid-Career", "Established/Professional"]


# -- the Projects group: reviewed with the profile's Save ---------------------------------------------

def found_projects(client) -> dict:
    return {s["title"] or s["summary"]: s for s in client.get("/api/profile").json()["projects"]["suggestions"]}


def test_projects_found_in_documents_come_with_the_profile_and_nothing_is_saved(artist):
    upload(artist, "portfolio", os.path.join(TOMAS, "portfolio.txt"))
    body = artist.get("/api/profile").json()
    assert body["projects"]["saved"] == 0
    rain = found_projects(artist)["Rain Score"]
    assert (rain["category"], rain["status"], rain["sources"][0]["quote"]) == ("work", "past", "Rain Score, 2021")


def test_save_keeps_the_ticked_projects_with_their_status_and_dismisses_the_rest(artist):
    upload(artist, "portfolio", os.path.join(TOMAS, "portfolio.txt"))
    found = found_projects(artist)
    rain, choir, tidal = found["Rain Score"], found["Underwater Choir"], found["Tidal Bodies"]
    review = {"accept": [{"key": tidal["suggestion_key"], "status": "current"},     # ticked as current
                         {"key": rain["suggestion_key"]}],                          # kept as the rule read it
              "dismiss": [choir["suggestion_key"]]}
    assert artist.put("/api/profile", json={"values": {}, "projects": review}).status_code == 200
    saved = {p["title"]: p for p in artist.get("/api/projects").json()["projects"]}
    assert saved["Tidal Bodies"]["status"] == "current" and saved["Rain Score"]["status"] == "past"
    assert saved["Rain Score"]["sources"][0]["quote"] == "Rain Score, 2021"     # quotes from the server
    assert "Underwater Choir" not in saved
    body = artist.get("/api/profile").json()
    assert body["projects"]["suggestions"] == [] and body["projects"]["saved"] == 2   # nothing offered again
    # the saved ones are shown on the profile too, current first
    assert [p["title"] for p in body["projects"]["projects"]] == ["Tidal Bodies", "Rain Score"]
    # saving again with the same ticks adds nothing
    artist.put("/api/profile", json={"values": {}, "projects": review})
    assert len(artist.get("/api/projects").json()["projects"]) == 2


def test_unknown_or_forged_project_keys_are_ignored(artist):
    upload(artist, "portfolio", os.path.join(TOMAS, "portfolio.txt"))
    review = {"accept": [{"key": "project:invented", "status": "current"}], "dismiss": ["project:other"]}
    assert artist.put("/api/profile", json={"values": {}, "projects": review}).status_code == 200
    assert artist.get("/api/projects").json()["projects"] == []
    assert len(found_projects(artist)) == 3
    bad = {"accept": [{"key": "project:x", "status": "finished"}]}
    assert artist.put("/api/profile", json={"values": {}, "projects": bad}).status_code == 422


def test_the_profile_says_when_images_are_still_being_read(artist, monkeypatch):
    """A PDF whose images aren't read yet (queued in the background): the page shows a note and asks again."""
    from api import images
    monkeypatch.setattr(images, "read_document_images", lambda document_id: None)   # the background task does nothing
    monkeypatch.setattr(images, "start_reading", lambda document: None)
    upload(artist, "cv", os.path.join(ILKA, "cv.pdf"))
    assert artist.get("/api/profile").json()["projects"]["images_pending"] is True
    # once read, it isn't
    from api.models import Document
    with Session(db.get_engine()) as session:
        document = session.scalar(select(Document))
        document.page_lines = []
        session.commit()
    assert artist.get("/api/profile").json()["projects"]["images_pending"] is False


def test_the_artists_name_is_saved_tidied_and_not_given_to_the_engine(artist):
    saved = save(artist, {"name": "  Paloma   Schnitzer "}).json()
    assert saved["values"]["name"] == "Paloma Schnitzer"
    assert to_artist_profile(ProfileValues(name="Paloma")).model_dump().get("name") is None
    assert save(artist, {"name": "x" * 121}).status_code == 422
