"""
Saved calls (api/saved.py): Discover's Save, and the Studio's list of saved calls in their stage —
saved, draft, completed, closed — with the application's progress.

Uses the test database from tests/conftest.py and small fixed calls (test_matcher.py): no data files.
"""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from api import discover, knowledge_base
from api.main import app
from src.agent.checklist import item_key
from src.models.opportunity import ApplicationQuestion, RequiredMaterial
from tests.conftest import PASSWORD
from tests.test_api_documents import KeywordEmbedder
from tests.test_matcher import matcher, opp

pytestmark = pytest.mark.usefixtures("api_database")

SOON, PAST = date.today() + timedelta(days=10), date.today() - timedelta(days=3)
OPEN = opp("open", title_en="Open residency", deadline_date=SOON,
           application_questions=[ApplicationQuestion(question="Why?", limit=None)],
           required_materials=[RequiredMaterial(item="Budget", quote="Send a budget.", kind="gather")])
CLOSED = opp("closed", title_en="Closed grant", deadline_date=PAST)
QUESTION, BUDGET = item_key("q", "Why?"), item_key("m", "Budget")


@pytest.fixture(autouse=True)
def calls(monkeypatch):
    embedder = KeywordEmbedder()
    monkeypatch.setattr(knowledge_base, "get_embedder", lambda: embedder)
    m = matcher([OPEN, CLOSED], [[1.0, 0.0], [0.0, 1.0]], statuses={"open": "CHECK", "closed": "CHECK"})
    monkeypatch.setattr(discover, "get_matcher", lambda: m)
    return m


@pytest.fixture
def artist(client):
    assert client.post("/api/auth/signup", json={"email": "artist@example.com", "password": PASSWORD}).status_code == 201
    return client


def listed(client) -> dict:
    return {c["id"]: c for c in client.get("/api/saved").json()["calls"]}


def test_save_and_unsave(artist):
    assert artist.put("/api/saved/open").status_code == 204
    assert artist.put("/api/saved/open").status_code == 204            # saving twice is one save
    call = listed(artist)["open"]
    assert (call["stage"], call["progress"], call["title"], call["deadline"]) == ("saved", None, "Open residency",
                                                                                  SOON.isoformat())
    assert artist.put("/api/saved/nope").status_code == 404
    assert artist.delete("/api/saved/open").status_code == 204
    assert listed(artist) == {}


def test_discover_and_the_call_page_say_whether_a_call_is_saved(artist):
    artist.put("/api/saved/open")
    results = {r["id"]: r["saved"] for r in artist.post("/api/discover/search", json={}).json()["results"]}
    assert results["open"] is True
    assert artist.get("/api/opportunities/open").json()["saved"] is True


def test_starting_an_application_saves_the_call_and_makes_it_a_draft(artist):
    artist.put(f"/api/applications/open/items/{BUDGET}", json={"ticked": True})
    call = listed(artist)["open"]
    assert call["stage"] == "draft"
    assert call["progress"] == {"texts_reviewed": 0, "texts": 1, "items_gathered": 1, "items": 1}


def test_every_text_reviewed_and_item_gathered_is_completed(artist):
    artist.put(f"/api/applications/open/items/{BUDGET}", json={"ticked": True})
    artist.put(f"/api/applications/open/items/{QUESTION}", json={"draft": "Because."})
    artist.post(f"/api/applications/open/items/{QUESTION}/confirm")
    body = artist.get("/api/saved").json()
    assert body["calls"][0]["stage"] == "completed" and body["counts"]["completed"] == 1


def test_a_passed_deadline_is_closed_and_a_call_gone_from_the_corpus_too(artist, calls, monkeypatch):
    artist.put("/api/saved/closed")
    artist.put("/api/saved/open")
    assert listed(artist)["closed"]["stage"] == "closed"
    # the corpus no longer has "open": still listed, from what was saved
    monkeypatch.setattr(discover, "get_matcher", lambda: matcher([CLOSED], [[0.0, 1.0]], statuses={"closed": "CHECK"}))
    gone = listed(artist)["open"]
    assert (gone["stage"], gone["listed"], gone["title"]) == ("closed", False, "Open residency")


def test_the_list_is_ordered_draft_saved_completed_closed_and_counted(artist):
    artist.put("/api/saved/closed")
    artist.put(f"/api/applications/open/items/{BUDGET}", json={"ticked": True})
    body = artist.get("/api/saved").json()
    assert [c["id"] for c in body["calls"]] == ["open", "closed"]
    assert body["counts"] == {"draft": 1, "saved": 0, "completed": 0, "closed": 1}


def test_saved_calls_are_private(artist):
    artist.put("/api/saved/open")
    other = TestClient(app)
    other.post("/api/auth/signup", json={"email": "other@example.com", "password": PASSWORD})
    assert other.get("/api/saved").json()["calls"] == []
    assert TestClient(app).get("/api/saved").status_code == 401


def test_a_closed_call_says_what_it_was(artist):
    artist.put("/api/saved/closed")
    call = listed(artist)["closed"]
    assert call["stage"] == "closed" and call["was"] == "saved"


def test_removing_a_draft_removes_its_application(artist):
    artist.put(f"/api/applications/open/items/{BUDGET}", json={"ticked": True})
    assert artist.delete("/api/saved/open").status_code == 204
    states = {i["key"]: i["state"] for i in artist.get("/api/applications/open").json()["to_gather"]}
    assert states[BUDGET] == "missing"                       # the tick went with it
    assert listed(artist) == {}


def test_no_match_without_anything_to_rank_by(artist):
    artist.put("/api/saved/open")
    assert listed(artist)["open"]["match"] is None
