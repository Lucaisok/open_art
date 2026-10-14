"""
Web API: the artist's projects and interests (api/projects.py). Suggestions are read from the uploaded
documents by rules (src/rag/project_rules.py), saved only when the artist accepts them.

Uses the test database from tests/conftest.py and the keyword embedder from test_api_documents.py.
"""

import os

import pytest

from api import knowledge_base
from tests.conftest import PASSWORD
from tests.test_api_documents import TOMAS, KeywordEmbedder, upload

pytestmark = pytest.mark.usefixtures("api_database")


@pytest.fixture(autouse=True)
def fake_embedder(monkeypatch):
    embedder = KeywordEmbedder()
    monkeypatch.setattr(knowledge_base, "get_embedder", lambda: embedder)


@pytest.fixture
def artist(client):
    assert client.post("/api/auth/signup", json={"email": "artist@example.com", "password": PASSWORD}).status_code == 201
    for kind, name in [("cv", "cv.docx"), ("statement", "statement.md"), ("portfolio", "portfolio.txt")]:
        assert upload(client, kind, os.path.join(TOMAS, name)).status_code in (200, 201)
    return client


def suggestion(body, title):
    return next(s for s in body["suggestions"] if s["title"] == title)


def test_documents_give_suggestions_and_nothing_is_saved_until_accepted(artist):
    body = artist.get("/api/projects").json()
    assert body["projects"] == [] and body["interests"] == []
    tidal = suggestion(body, "Tidal Bodies")
    assert tidal["status"] == "past" and tidal["years"] == "2025" and len(tidal["sources"]) == 2
    assert any(s["kind"] == "interest" for s in body["suggestions"])


def test_accepting_keeps_the_servers_quotes_and_stops_suggesting_it(artist):
    tidal = suggestion(artist.get("/api/projects").json(), "Tidal Bodies")
    # an edited title is fine; the quotes come from the server, not from this request
    sent = {**tidal, "title": "Tidal Bodies (Lisbon)", "sources": [{"quote": "forged", "citation": "x"}]}
    saved = artist.post("/api/projects", json=sent)
    assert saved.status_code == 201
    assert saved.json()["title"] == "Tidal Bodies (Lisbon)" and "forged" not in str(saved.json()["sources"])
    body = artist.get("/api/projects").json()
    assert [p["title"] for p in body["projects"]] == ["Tidal Bodies (Lisbon)"]
    assert all(s["title"] != "Tidal Bodies" for s in body["suggestions"])


def test_a_dismissed_suggestion_is_not_offered_again(artist):
    interest = next(s for s in artist.get("/api/projects").json()["suggestions"] if s["kind"] == "interest")
    assert artist.post("/api/projects/dismiss", json={"key": interest["suggestion_key"]}).status_code == 204
    keys = [s["suggestion_key"] for s in artist.get("/api/projects").json()["suggestions"]]
    assert interest["suggestion_key"] not in keys


def test_add_by_hand_edit_and_delete(artist):
    planned = artist.post("/api/projects", json={"title": "Buried Rivers", "status": "planned", "years": "2027",
                                                "summary": "Sound walks above the hidden rivers of Lisbon."})
    assert planned.status_code == 201 and planned.json()["from_documents"] is False
    project_id = planned.json()["id"]
    edited = artist.put(f"/api/projects/{project_id}", json={"title": "Buried Rivers", "status": "current"})
    assert edited.json()["status"] == "current"
    assert artist.get("/api/projects").json()["projects"][0]["title"] == "Buried Rivers"   # current first
    assert artist.delete(f"/api/projects/{project_id}").status_code == 204
    assert artist.get("/api/projects").json()["projects"] == []


def test_incomplete_projects_are_refused(artist):
    assert artist.post("/api/projects", json={"title": "No status"}).status_code == 422
    assert artist.post("/api/projects", json={"status": "past"}).status_code == 422
    assert artist.post("/api/projects", json={"kind": "interest"}).status_code == 422


def test_another_artists_projects_are_out_of_reach(artist, client):
    project_id = artist.post("/api/projects", json={"title": "Mine", "status": "past"}).json()["id"]
    artist.post("/api/auth/logout")
    assert client.post("/api/auth/signup", json={"email": "other@example.com", "password": PASSWORD}).status_code == 201
    assert client.get("/api/projects").json()["projects"] == []
    assert client.delete(f"/api/projects/{project_id}").status_code == 404
    assert client.put(f"/api/projects/{project_id}", json={"title": "Taken", "status": "past"}).status_code == 404


def test_suggestions_say_what_they_are(artist):
    body = artist.get("/api/projects").json()
    assert suggestion(body, "Tidal Bodies")["category"] == "work"                 # CV show + portfolio work
    assert suggestion(body, "Listening to the Tagus")["category"] == "exhibition"  # only a CV exhibitions line
    assert all(s["category"] is None for s in body["suggestions"] if s["kind"] == "interest")


def test_a_project_is_a_work_unless_it_says_otherwise_and_an_interest_is_neither(artist):
    added = artist.post("/api/projects", json={"title": "Night Swim", "status": "current"}).json()
    assert added["category"] == "work"
    edited = artist.put(f"/api/projects/{added['id']}",
                        json={"title": "Night Swim", "status": "past", "category": "exhibition"}).json()
    assert edited["category"] == "exhibition"
    interest = artist.post("/api/projects", json={"kind": "interest", "summary": "Rivers", "category": "work"})
    assert interest.json()["category"] is None
    assert artist.post("/api/projects", json={"title": "X", "status": "past", "category": "poem"}).status_code == 422
