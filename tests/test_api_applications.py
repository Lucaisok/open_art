"""
Web API step 6: an artist's application to one call (api/applications.py) — the checklist with the
artist's uploaded documents, drafts and ticks, and the review step (draft -> confirmed).

Uses the test database from tests/conftest.py, a one-call Matcher (test_matcher.py) and the keyword
embedder from test_api_documents.py: no data files, no model download, no model call.
"""

import io
import os
import zipfile
from types import SimpleNamespace

import pytest
from docx import Document
from openai import OpenAIError

from api import applications, discover, knowledge_base
from src.agent.checklist import item_key
from src.agent.drafting import AgentAnswer
from src.models.opportunity import ApplicationQuestion, RequiredMaterial
from tests.conftest import PASSWORD
from tests.test_api_documents import TOMAS, KeywordEmbedder, upload
from tests.test_matcher import matcher, opp

pytestmark = pytest.mark.usefixtures("api_database")


def material(item, kind):
    return RequiredMaterial(item=item, quote=f"Send your {item}.", kind=kind)


CALL = opp("call", title_en="Sound residency", how_to_apply="Apply online.",
           application_questions=[ApplicationQuestion(question="Why this residency?", limit="max 300 words")],
           required_materials=[material("CV", "gather"), material("Budget", "gather"),
                               material("Artist statement", "write")])
QUESTION, CV, BUDGET, STATEMENT = (item_key("q", "Why this residency?"), item_key("m", "CV"),
                                   item_key("m", "Budget"), item_key("m", "Artist statement"))


@pytest.fixture(autouse=True)
def one_call(monkeypatch):
    m = matcher([CALL], [[1.0, 0.0]], statuses={"call": "CHECK"})
    monkeypatch.setattr(discover, "get_matcher", lambda: m)


@pytest.fixture(autouse=True)
def fake_embedder(monkeypatch):
    embedder = KeywordEmbedder()
    monkeypatch.setattr(knowledge_base, "get_embedder", lambda: embedder)


@pytest.fixture
def artist(client):
    assert client.post("/api/auth/signup", json={"email": "artist@example.com", "password": PASSWORD}).status_code == 201
    return client


def states(body) -> dict[str, str]:
    return {i["key"]: i["state"] for i in body["to_draft"] + body["to_gather"]}


def test_logged_out_is_refused(client):
    assert client.get("/api/applications/call").status_code == 401


def test_unknown_call_or_item_is_404(artist):
    assert artist.get("/api/applications/nope").status_code == 404
    assert artist.put("/api/applications/call/items/m-0000000000", json={"ticked": True}).status_code == 404


def test_the_checklist_before_anything_is_saved(artist):
    body = artist.get("/api/applications/call").json()
    assert body["title"] == "Sound residency" and body["verdict_status"] == "CHECK" and body["documents"] == []
    assert [i["title"] for i in body["to_draft"]] == ["Why this residency?", "Artist statement"]
    assert [i["title"] for i in body["to_gather"]] == ["CV", "Budget"]
    assert states(body) == {QUESTION: "empty", STATEMENT: "empty", CV: "missing", BUDGET: "missing"}


def test_an_uploaded_document_covers_its_item(artist):
    assert upload(artist, "cv", os.path.join(TOMAS, "cv.docx")).status_code in (200, 201)
    body = artist.get("/api/applications/call").json()
    assert states(body)[CV] == "uploaded" and states(body)[BUDGET] == "missing"
    assert body["documents"] == [{"kind": "cv", "file_name": "cv.docx"}]


def test_ticks_only_for_items_to_gather(artist):
    assert states(artist.put(f"/api/applications/call/items/{BUDGET}", json={"ticked": True}).json())[BUDGET] == "ticked"
    assert artist.put(f"/api/applications/call/items/{QUESTION}", json={"ticked": True}).status_code == 422
    assert artist.put(f"/api/applications/call/items/{BUDGET}", json={"draft": "x"}).status_code == 422


def test_draft_review_and_a_change_needs_a_new_review(artist):
    url = f"/api/applications/call/items/{QUESTION}"
    assert artist.post(f"{url}/confirm").status_code == 409            # nothing to confirm yet
    body = artist.put(url, json={"draft": "Because the sea."}).json()
    assert states(body)[QUESTION] == "draft"
    assert states(artist.post(f"{url}/confirm").json())[QUESTION] == "confirmed"
    assert states(artist.put(url, json={"draft": "Because the sea."}).json())[QUESTION] == "confirmed"   # unchanged
    assert states(artist.put(url, json={"draft": "Because of the sea."}).json())[QUESTION] == "draft"
    assert states(artist.put(url, json={"draft": "  "}).json())[QUESTION] == "empty"


def test_each_artist_sees_only_their_own_application(artist):
    artist.put(f"/api/applications/call/items/{QUESTION}", json={"draft": "Mine."})
    artist.post("/api/auth/logout")
    assert artist.post("/api/auth/signup", json={"email": "other@example.com", "password": PASSWORD}).status_code == 201
    body = artist.get("/api/applications/call").json()
    assert states(body)[QUESTION] == "empty" and body["to_draft"][0]["draft"] is None


# -- the agent (sub-step 4): a fake OpenAI client, no model call -------------------------------------------


class FakeOpenAI:
    """Answers every call with a draft naming the turn; records what it was sent."""
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail
        self.chat = SimpleNamespace(completions=SimpleNamespace(parse=self._parse))

    def _parse(self, **kwargs):
        if self.fail:
            raise OpenAIError("down")
        self.sent.append(kwargs["messages"])
        parsed = AgentAnswer(reply=f"Reply {len(self.sent)}.", draft=f"Draft {len(self.sent)}.", used_passages=["P1", "P9"])
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed))])


@pytest.fixture
def model(monkeypatch):
    fake = FakeOpenAI()
    monkeypatch.setattr(applications, "get_openai", lambda: fake)
    return fake


def send(client, key, message="Write a first draft.", **body):
    return client.post(f"/api/applications/call/items/{key}/messages", json={"message": message, **body})


def test_a_message_gives_a_reply_and_a_draft_to_review(artist, model):
    upload(artist, "cv", os.path.join(TOMAS, "cv.docx"))
    response = send(artist, QUESTION)
    assert response.status_code == 200, response.text
    body = response.json()
    assert [(m["role"], m["content"]) for m in body["messages"]] == [("artist", "Write a first draft."),
                                                                      ("agent", "Reply 1.")]
    assert body["messages"][1]["sources"] and body["messages"][1]["sources"][0].startswith("cv.docx")  # P9 unknown: dropped
    item = next(i for i in body["application"]["to_draft"] if i["key"] == QUESTION)
    assert item["draft"] == "Draft 1." and item["state"] == "draft"
    assert artist.get(f"/api/applications/call/items/{QUESTION}/messages").json() == body["messages"]


def test_the_agent_never_confirms(artist, model):
    artist.put(f"/api/applications/call/items/{QUESTION}", json={"draft": "Mine."})
    artist.post(f"/api/applications/call/items/{QUESTION}/confirm")
    assert states(send(artist, QUESTION).json()["application"])[QUESTION] == "draft"


def test_the_other_drafts_and_the_unsaved_text_reach_the_model(artist, model):
    artist.put(f"/api/applications/call/items/{STATEMENT}", json={"draft": "I listen to tides."})
    send(artist, QUESTION, draft="My unsaved edit")
    data = model.sent[0][1]["content"]
    assert "## Artist statement\nI listen to tides." in data and "<current_draft>\nMy unsaved edit" in data
    send(artist, QUESTION, "Shorter please.")
    assert [m["content"] for m in model.sent[1][2:]] == ["Write a first draft.", "Reply 1.", "Shorter please."]


def test_each_item_has_its_own_chat(artist, model):
    send(artist, QUESTION)
    assert artist.get(f"/api/applications/call/items/{STATEMENT}/messages").json() == []


def test_only_items_to_write_and_a_failing_model_saves_nothing(artist, monkeypatch):
    assert send(artist, CV).status_code == 422
    monkeypatch.setattr(applications, "get_openai", lambda: FakeOpenAI(fail=True))
    assert send(artist, QUESTION).status_code == 503
    assert artist.get(f"/api/applications/call/items/{QUESTION}/messages").json() == []


# -- download (sub-step 6) -------------------------------------------------------------------------------

def test_the_download_waits_for_a_complete_application(artist):
    url = "/api/applications/call"
    assert artist.get(url).json()["missing"] == ["2 texts to review", "2 items to gather"]
    upload(artist, "cv", os.path.join(TOMAS, "cv.docx"))
    upload(artist, "portfolio", os.path.join(TOMAS, "portfolio.txt"))        # not asked for by the call
    for key in (QUESTION, STATEMENT):
        artist.put(f"{url}/items/{key}", json={"draft": f"Text of {key}."})
    artist.post(f"{url}/items/{QUESTION}/confirm")
    refused = artist.get(f"{url}/download")
    assert refused.status_code == 409 and "1 text to review, 1 item to gather" in refused.json()["detail"]

    artist.post(f"{url}/items/{STATEMENT}/confirm")
    body = artist.put(f"{url}/items/{BUDGET}", json={"ticked": True}).json()
    assert body["missing"] == []
    response = artist.get(f"{url}/download")
    assert response.status_code == 200 and response.headers["content-type"] == "application/zip"
    assert 'filename="Sound-residency.zip"' in response.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        # the portfolio is uploaded but not asked for: it stays out
        assert sorted(z.namelist()) == ["application.docx", "checklist.txt", "cv - cv.docx",
                                        "texts/01 Why this residency.txt", "texts/02 Artist statement.txt"]
        assert z.read("texts/01 Why this residency.txt").decode() == f"Text of {QUESTION}.\n"
        checklist = z.read("checklist.txt").decode()
        docx = Document(io.BytesIO(z.read("application.docx")))
        with open(os.path.join(TOMAS, "cv.docx"), "rb") as f:
            assert z.read("cv - cv.docx") == f.read()                            # the original file
    assert "- 01 Why this residency.txt" in checklist
    assert "- CV: in this folder (cv)" in checklist and "- Budget: you have it" in checklist
    paragraphs = [p.text for p in docx.paragraphs]
    assert "Why this residency? (max 300 words)" in paragraphs and f"Text of {QUESTION}." in paragraphs


def test_an_edit_after_review_blocks_the_download_again(artist):
    url = "/api/applications/call"
    upload(artist, "cv", os.path.join(TOMAS, "cv.docx"))
    artist.put(f"{url}/items/{BUDGET}", json={"ticked": True})
    for key in (QUESTION, STATEMENT):
        artist.put(f"{url}/items/{key}", json={"draft": "Done."})
        artist.post(f"{url}/items/{key}/confirm")
    assert artist.get(f"{url}/download").status_code == 200
    artist.put(f"{url}/items/{QUESTION}", json={"draft": "Done, changed."})
    assert artist.get(f"{url}/download").status_code == 409


def test_another_artist_gets_only_their_own_incomplete_application(artist):
    url = "/api/applications/call"
    upload(artist, "cv", os.path.join(TOMAS, "cv.docx"))
    artist.put(f"{url}/items/{BUDGET}", json={"ticked": True})
    for key in (QUESTION, STATEMENT):
        artist.put(f"{url}/items/{key}", json={"draft": "Done."})
        artist.post(f"{url}/items/{key}/confirm")
    artist.post("/api/auth/logout")
    assert artist.post("/api/auth/signup", json={"email": "other@example.com", "password": PASSWORD}).status_code == 201
    assert artist.get(f"{url}/download").status_code == 409
