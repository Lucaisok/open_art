"""
Web API step 5: Discover search and the opportunity page.

Uses the test database from tests/conftest.py, and a small Matcher (fake corpus, index, engine and
embedder from test_matcher.py) in place of the real one, plus the keyword embedder from
test_api_documents.py for the artist's documents: no data files, no model download.
"""

from datetime import date, timedelta
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api import db, discover, knowledge_base
from api.main import app
from src.eligibility.engine import Item, Verdict
from src.eligibility.profile import ArtistProfile
from tests.conftest import PASSWORD
from tests.test_api_documents import ILKA, TOMAS, KeywordEmbedder, upload, user_id
from tests.test_matcher import matcher, opp

pytestmark = pytest.mark.usefixtures("api_database")

TODAY = date.today()   # the routes use today's date


def soon(days: int) -> date:
    return TODAY + timedelta(days=days)


def item(text: str, outcome: str, reason: str, group_outcome: str | None = None) -> Item:
    return Item(chunk_id=text, chunk_index=0, text=text, label="AGE", confidence=None, polarity=None,
                outcome=outcome, reason=reason, group_outcome=group_outcome)


class RecordingEngine:
    """Says "not eligible" to anyone under 30 for the call "young-only"; remembers the profiles it saw."""
    def __init__(self):
        self.profiles: list[ArtistProfile] = []

    def evaluate(self, profile, opportunity, today=None):
        self.profiles.append(profile)
        items = [item("Applicants must be under 35.", "CHECK", "your birth date is not in your profile"),
                 item("Open to all nationalities.", "NO_RESTRICTION", "no restriction"),
                 item("Citizens of Austria", "FAIL", "you are not Austrian", group_outcome="PASS")]
        status = "LIKELY_NOT_ELIGIBLE" if opportunity.id == "blocked" else "CHECK"
        return Verdict(opportunity_id=opportunity.id, title=opportunity.title_en, source_url=opportunity.source_url,
                       status=status, summary=f"summary of {opportunity.id}", items=items)


CALLS = [
    opp("near", title_en="Sound residency", deadline_date=soon(5), opportunity_type_canonical=["Residency"],
        country_canonical=["Norway"], city_en="Bergen"),
    opp("far", title_en="Print grant", deadline_date=soon(60), opportunity_type_canonical=["Grant/Funding"],
        country_canonical=["International/Global"],
        funding_components=[{"category": "Grant/Stipend", "amount_min": 1300, "amount_max": 1300,
                             "currency": "EUR", "period": "per month"}, {"category": "Accommodation/Housing"}],
        application_fee="none", application_fee_has_fee=False),
    opp("blocked", title_en="Blocked call", deadline_date=soon(1)),
    opp("closed", title_en="Closed call", deadline_date=soon(-1)),
]
# "near" is closest to the query (x axis), then "far"
VECTORS = [[1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [1.0, 0.1]]


@pytest.fixture(autouse=True)
def small_matcher(monkeypatch):
    m = matcher(CALLS, VECTORS)
    m.engine = RecordingEngine()
    monkeypatch.setattr(discover, "get_matcher", lambda: m)
    return m


@pytest.fixture(autouse=True)
def fake_document_embedder(monkeypatch):
    embedder = KeywordEmbedder()
    monkeypatch.setattr(knowledge_base, "get_embedder", lambda: embedder)


@pytest.fixture
def artist(client):
    assert client.post("/api/auth/signup", json={"email": "artist@example.com", "password": PASSWORD}).status_code == 201
    return client


def search(client, **body):
    response = client.post("/api/discover/search", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def ids(body) -> list[str]:
    return [r["id"] for r in body["results"]]


def test_logged_out_is_refused(client):
    assert client.post("/api/discover/search", json={}).status_code == 401
    assert client.get("/api/opportunities/near").status_code == 401
    assert client.get("/api/discover/options").status_code == 401


def test_options_list_the_corpus_countries(artist):
    body = artist.get("/api/discover/options").json()
    assert body["countries"] == ["Norway"]          # "International/Global" matches any country, not offered
    assert "Residency" in body["types"] and "Music" in body["disciplines"]


def test_all_calls_nearest_deadline_first_not_eligible_last_closed_hidden(artist):
    upload(artist, "statement", f"{TOMAS}/statement.md")   # "All calls" never ranks, documents or not
    body = search(artist, mode="all")
    assert ids(body) == ["near", "far", "blocked"]
    assert body["order"] == "deadline" and body["total"] == 3
    assert body["results"][2]["status"] == "LIKELY_NOT_ELIGIBLE"
    assert body["results"][2]["reason"] == "summary of blocked"


def test_matched_without_documents_orders_by_deadline(artist):
    body = search(artist, mode="matched")
    assert body["order"] == "deadline" and body["ranked_by"] == []
    assert ids(body) == ["near", "far", "blocked"]


def test_matched_ranks_by_every_document(artist):
    upload(artist, "cv", f"{ILKA}/cv.pdf")
    body = search(artist, mode="matched")
    assert body["order"] == "match" and body["ranked_by"] == ["cv.pdf"]
    assert ids(body) == ["near", "far", "blocked"]          # most similar first, not-eligible last
    assert body["results"][0]["score"] == pytest.approx(1.0)

    upload(artist, "portfolio", f"{TOMAS}/portfolio.txt")
    upload(artist, "statement", f"{TOMAS}/statement.md")
    assert search(artist, mode="matched")["ranked_by"] == ["statement.md", "portfolio.txt", "cv.pdf"]


def test_the_document_vectors_are_averaged(artist, small_matcher, monkeypatch):
    vectors = {"statement.md": np.array([1.0, 0.0]), "portfolio.txt": np.array([0.0, 1.0])}
    monkeypatch.setattr(discover, "embed_query", lambda embedder, query: vectors[query])
    monkeypatch.setattr(discover, "suggest_query", lambda kb, documents: SimpleNamespace(query=documents[0]))
    upload(artist, "statement", f"{TOMAS}/statement.md")
    upload(artist, "portfolio", f"{TOMAS}/portfolio.txt")
    with Session(db.get_engine()) as session:   # closed afterwards: an open one would block the next test
        _, vector = discover.ranking_vector(session, user_id(artist), small_matcher)
    assert vector == pytest.approx(np.array([1.0, 1.0]) / np.sqrt(2))   # the mean, back to length 1


def test_filters_apply(artist):
    assert ids(search(artist, mode="all", types=["Residency"])) == ["near", "blocked"]   # untyped call kept
    assert ids(search(artist, mode="all", funded_only=True)) == ["far"]
    assert ids(search(artist, mode="all", text="print")) == ["far"]
    # an International call matches any country
    assert ids(search(artist, mode="all", country="Norway")) == ["near", "far", "blocked"]


def test_unknown_filter_value_is_refused(artist):
    assert artist.post("/api/discover/search", json={"types": ["Pottery"]}).status_code == 422


def test_verdicts_use_the_saved_profile_only(artist, small_matcher):
    assert search(artist, mode="all")["profile_filled"] is False
    assert small_matcher.engine.profiles[-1] == ArtistProfile()

    saved = {"values": {"birth_date": "1994-03-12", "disciplines": ["Music"]}}
    assert artist.put("/api/profile", json=saved).status_code == 200
    assert search(artist, mode="all")["profile_filled"] is True
    assert small_matcher.engine.profiles[-1].disciplines == ["Music"]


def test_opportunity_page(artist):
    body = artist.get("/api/opportunities/far").json()
    assert body["title"] == "Print grant" and body["countries"] == ["International"]
    assert body["funding"] == "EUR 1,300 per month + accommodation/housing" and body["funded"] is True
    assert body["fee"] == "None"
    verdict = body["verdict"]
    assert (verdict["fails"], verdict["checks"], verdict["passes"]) == (0, 1, 2)
    # passes on top when nothing fails; a no-restriction sentence passes; a failing sentence in an OR
    # group that passes, passes
    outcomes = [(s["quote"], [r["outcome"] for r in s["requirements"]]) for s in verdict["sentences"]]
    assert outcomes == [("Open to all nationalities.", ["PASS"]), ("Citizens of Austria", ["PASS"]),
                        ("Applicants must be under 35.", ["CHECK"])]


def test_funding_label_puts_support_first():
    call = opp("x", funding_components=[{"category": "Mentorship/Training"}, {"category": "Grant/Stipend"}])
    assert discover.funding_label(call) == "Grant/stipend + mentorship/training"


def test_unknown_opportunity_is_404(artist):
    assert artist.get("/api/opportunities/nope").status_code == 404


def test_the_ranking_query_is_built_once_per_document(artist, monkeypatch):
    calls = []
    real = discover.suggest_query
    monkeypatch.setattr(discover, "suggest_query", lambda kb, documents: calls.append(documents) or real(kb, documents))

    upload(artist, "statement", f"{TOMAS}/statement.md")
    search(artist, mode="matched")
    search(artist, mode="matched", types=["Residency"])
    assert calls == [["statement.md"]]                     # the second search reused it

    upload(artist, "statement", f"{TOMAS}/statement.md", name="new-statement.md")   # a new upload, a new id
    assert search(artist, mode="matched")["ranked_by"] == ["new-statement.md"]
    assert calls == [["statement.md"], ["new-statement.md"]]
