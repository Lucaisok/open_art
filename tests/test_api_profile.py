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
    assert values["residence_country"] == "AT"
    assert values["degree_field"] == "Painting and Graphic Arts"
    assert values["birth_date"] == "1994-03-12" and values["active_since"] == 2021


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


# -- CV suggestions ----------------------------------------------------------------------------------

def suggestions(client):
    return client.get("/api/profile").json()["cv_suggestions"]


def test_no_cv_no_suggestions(artist):
    assert suggestions(artist) is None


def test_cv_upload_brings_quoted_suggestions_and_saves_nothing(artist):
    upload(artist, "cv", os.path.join(ILKA, "cv.pdf"))
    found = suggestions(artist)
    assert found["file_name"] == "cv.pdf"
    items = {s["field"]: s for s in found["items"]}
    assert items["birth_date"]["value"] == "1994-03-12"
    assert items["birth_date"]["quote"] == "Born 12 March 1994 in Debrecen, Hungary"
    assert items["birth_date"]["citation"].startswith("cv.pdf")
    assert items["nationalities"]["value"] == ["HU"] and items["active_since"]["value"] == 2021
    # human in the loop: suggesting is not saving
    assert artist.get("/api/profile").json()["updated_at"] is None
    assert profile_rows() == 0


def test_saving_after_review_stops_the_suggestions(artist):
    upload(artist, "cv", os.path.join(ILKA, "cv.pdf"))
    document_id = suggestions(artist)["document_id"]
    body = {"values": {"birth_date": "1994-03-12"}, "evidence": {}, "reviewed_document_id": document_id}
    assert artist.put("/api/profile", json=body).status_code == 200
    assert suggestions(artist) is None
    # a later Save without the id keeps the CV marked as reviewed
    save(artist, {"birth_date": "1994-03-12", "disciplines": ["Craft"]})
    assert suggestions(artist) is None


def test_a_new_cv_brings_new_suggestions(artist):
    upload(artist, "cv", os.path.join(ILKA, "cv.pdf"))
    artist.put("/api/profile", json={"values": {}, "reviewed_document_id": suggestions(artist)["document_id"]})
    upload(artist, "cv", os.path.join(TOMAS, "cv.docx"))
    found = suggestions(artist)
    assert found["file_name"] == "cv.docx"
    assert {s["field"]: s["value"] for s in found["items"]}["nationalities"] == ["BR", "PT"]


def test_a_cv_with_nothing_found_says_so(artist):
    artist.put("/api/documents/cv", files={"file": ("cv.txt", b"Portfolio on request.\nThank you for reading.")})
    found = suggestions(artist)
    assert found is not None and found["items"] == []


def test_only_cvs_are_read_for_suggestions(artist):
    upload(artist, "statement", os.path.join(ILKA, "statement.docx"))
    assert suggestions(artist) is None


def test_reviewed_id_of_another_users_document_is_ignored(artist):
    other = TestClient(app)
    other.post("/api/auth/signup", json={"email": "other@example.com", "password": PASSWORD})
    upload(other, "cv", os.path.join(ILKA, "cv.pdf"))
    foreign_id = suggestions(other)["document_id"]
    assert artist.put("/api/profile", json={"values": {}, "reviewed_document_id": foreign_id}).status_code == 200
    with Session(db.get_engine()) as session:
        assert session.scalar(select(Profile.reviewed_document_id)) is None


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
