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


# -- projects for the application and for one text (sub-step 7) -----------------------------------------

def add_project(client, title, status):
    response = client.post("/api/projects", json={"title": title, "status": status, "summary": f"About {title}."})
    assert response.status_code == 201
    return response.json()["id"]


@pytest.fixture
def projects(artist):
    """Four saved projects. The fake matcher scores them all the same, so the suggestion keeps their order."""
    return {title: add_project(artist, title, status) for title, status in
            [("Tidal Bodies", "past"), ("Buried Rivers", "planned"), ("Rain Score", "past"),
             ("Underwater Choir", "past")]}


def test_the_suggestion_proposes_a_planned_project_and_ticks_three_more(artist, projects):
    body = artist.get("/api/applications/call").json()
    assert body["selection_chosen"] is False
    assert body["selection"]["proposing"] == projects["Buried Rivers"]
    assert body["selection"]["mention"] == [projects["Tidal Bodies"], projects["Rain Score"], projects["Underwater Choir"]]
    assert [p["title"] for p in body["projects"]][0] == "Buried Rivers" and all(p["suggested"] for p in body["projects"])


def test_the_agent_gets_only_the_chosen_projects(artist, projects, model):
    choice = {"proposing": projects["Buried Rivers"], "mention": [projects["Tidal Bodies"]]}
    body = artist.put("/api/applications/call/projects", json=choice).json()
    assert body["selection_chosen"] is True and body["selection"] == choice
    send(artist, QUESTION)
    data = model.sent[0][1]["content"]
    assert "PROPOSING (the project this application is about): Buried Rivers" in data
    assert "Past or related work: Tidal Bodies" in data and "Rain Score" not in data


def test_one_text_can_have_its_own_projects_and_go_back(artist, projects, model):
    artist.put("/api/applications/call/projects", json={"proposing": projects["Buried Rivers"], "mention": []})
    own = {"proposing": None, "mention": [projects["Rain Score"], projects["Underwater Choir"]]}
    body = artist.put(f"/api/applications/call/items/{STATEMENT}/projects", json={"selection": own}).json()
    assert next(i for i in body["to_draft"] if i["key"] == STATEMENT)["projects"] == own
    send(artist, STATEMENT)
    assert "No project is marked as the one being proposed." in model.sent[0][1]["content"]
    assert "Rain Score" in model.sent[0][1]["content"] and "Buried Rivers" not in model.sent[0][1]["content"]
    send(artist, QUESTION)                                       # the other texts keep the application's choice
    assert "PROPOSING (the project this application is about): Buried Rivers" in model.sent[1][1]["content"]
    body = artist.put(f"/api/applications/call/items/{STATEMENT}/projects", json={"selection": None}).json()
    assert next(i for i in body["to_draft"] if i["key"] == STATEMENT)["projects"] is None


def test_only_the_artists_own_projects_and_deleted_ones_drop_out(artist, projects):
    assert artist.put("/api/applications/call/projects",
                      json={"proposing": "00000000-0000-0000-0000-000000000000", "mention": []}).status_code == 422
    assert artist.put(f"/api/applications/call/items/{CV}/projects", json={"selection": None}).status_code == 422
    artist.put("/api/applications/call/projects", json={"proposing": projects["Buried Rivers"],
                                                        "mention": [projects["Tidal Bodies"]]})
    artist.delete(f"/api/projects/{projects['Buried Rivers']}")
    assert artist.get("/api/applications/call").json()["selection"] == {"proposing": None,
                                                                       "mention": [projects["Tidal Bodies"]]}


def test_only_a_planned_or_current_work_can_be_proposed():
    from api.applications import can_propose
    from api.models import Project
    assert can_propose(Project(kind="project", status="current", category="work"))
    assert can_propose(Project(kind="project", status="planned", category=None))       # saved before categories
    assert not can_propose(Project(kind="project", status="current", category="exhibition"))
    assert not can_propose(Project(kind="project", status="past", category="work"))


def test_a_reply_that_rewrote_the_draft_says_how_long_it_is(artist, model):
    body = send(artist, QUESTION).json()
    assert body["messages"][1]["wrote_words"] == 2                         # "Draft 1."
    assert body["messages"][0]["wrote_words"] is None                      # the artist's own message


def test_back_to_the_suggested_projects(artist, projects):
    artist.put("/api/applications/call/projects", json={"proposing": None, "mention": []})
    body = artist.delete("/api/applications/call/projects").json()
    assert body["selection_chosen"] is False and body["selection"]["proposing"] == projects["Buried Rivers"]
    choices = {p["title"]: p for p in body["projects"]}
    assert choices["Buried Rivers"]["can_propose"] is True and choices["Rain Score"]["can_propose"] is False


def test_the_page_header_knows_the_call_and_whether_it_is_saved(artist):
    body = artist.get("/api/applications/call").json()
    assert body["saved"] is False and "countries" in body and "organisation" in body
    artist.put(f"/api/applications/call/items/{CV}", json={"ticked": True})   # starting saves the call
    assert artist.get("/api/applications/call").json()["saved"] is True


# -- the artist's own texts (sub-step 8) -----------------------------------------------------------------

def add_text(client, title="Cover letter"):
    return client.post("/api/applications/call/texts", json={"title": title})


def test_an_own_text_is_added_renamed_and_deleted(artist):
    body = add_text(artist).json()
    own = body["to_draft"][-1]
    assert own["title"] == "Cover letter" and own["source"] == "artist" and own["key"].startswith("t-")
    assert [i["title"] for i in add_text(artist, "Note to the jury").json()["to_draft"]] == [
        "Why this residency?", "Artist statement", "Cover letter", "Note to the jury"]   # in the order added
    body = artist.put(f"/api/applications/call/texts/{own['key']}", json={"title": "Letter"}).json()
    assert body["to_draft"][2]["title"] == "Letter"
    body = artist.delete(f"/api/applications/call/texts/{own['key']}").json()
    assert [i["title"] for i in body["to_draft"]] == ["Why this residency?", "Artist statement", "Note to the jury"]
    assert artist.put(f"/api/applications/call/items/{own['key']}", json={"draft": "x"}).status_code == 404


def test_a_title_is_needed_and_the_calls_items_cant_be_renamed(artist):
    assert add_text(artist, "").status_code == 422
    assert add_text(artist, "   ").status_code == 422
    assert add_text(artist, "x" * 201).status_code == 422
    assert artist.put(f"/api/applications/call/texts/{QUESTION}", json={"title": "Mine"}).status_code == 404
    assert artist.delete(f"/api/applications/call/texts/{QUESTION}").status_code == 404


def test_an_own_text_is_reviewed_and_downloaded_like_the_others(artist, model):
    url = "/api/applications/call"
    key = add_text(artist).json()["to_draft"][-1]["key"]
    upload(artist, "cv", os.path.join(TOMAS, "cv.docx"))
    artist.put(f"{url}/items/{BUDGET}", json={"ticked": True})
    for k in (QUESTION, STATEMENT):
        artist.put(f"{url}/items/{k}", json={"draft": "Done."})
        artist.post(f"{url}/items/{k}/confirm")
    assert artist.get(url).json()["missing"] == ["1 text to review"]              # the own text, still empty
    body = send(artist, key).json()["application"]                                # the assistant drafts it
    assert states(body)[key] == "draft" and "Cover letter" in model.sent[0][1]["content"]
    artist.post(f"{url}/items/{key}/confirm")
    with zipfile.ZipFile(io.BytesIO(artist.get(f"{url}/download").content)) as z:
        assert z.read("texts/03 Cover letter.txt").decode() == "Draft 1.\n"


def test_another_artist_cant_see_or_touch_an_own_text(artist):
    key = add_text(artist).json()["to_draft"][-1]["key"]
    artist.post("/api/auth/logout")
    assert artist.post("/api/auth/signup", json={"email": "other@example.com", "password": PASSWORD}).status_code == 201
    assert len(artist.get("/api/applications/call").json()["to_draft"]) == 2
    assert artist.put(f"/api/applications/call/items/{key}", json={"draft": "x"}).status_code == 404
    assert artist.delete(f"/api/applications/call/texts/{key}").status_code == 404


def test_nothing_to_download_until_there_is_a_file(artist, monkeypatch):
    """A call that only asks for something to tick: ticked, the zip would hold no file of the artist's."""
    only = opp("call", title_en="Open studio", required_materials=[material("Signed form", "gather")])
    m = matcher([only], [[1.0, 0.0]], statuses={"call": "CHECK"})
    monkeypatch.setattr(discover, "get_matcher", lambda: m)
    url = "/api/applications/call"
    body = artist.put(f"{url}/items/{item_key('m', 'Signed form')}", json={"ticked": True}).json()
    assert body["missing"] == ["add a text (the zip would be empty)"]
    assert artist.get(f"{url}/download").status_code == 409
    key = artist.post(f"{url}/texts", json={"title": "Cover letter"}).json()["to_draft"][0]["key"]
    artist.put(f"{url}/items/{key}", json={"draft": "Hello."})
    assert artist.post(f"{url}/items/{key}/confirm").json()["missing"] == []
    assert artist.get(f"{url}/download").status_code == 200


# -- "Not needed" (sub-step 9) ------------------------------------------------------------------------------

def test_an_item_marked_not_needed_no_longer_blocks_and_stays_out_of_the_zip(artist):
    url = "/api/applications/call"
    artist.put(f"{url}/items/{QUESTION}", json={"draft": "Because the sea."})
    artist.post(f"{url}/items/{QUESTION}/confirm")
    artist.put(f"{url}/items/{STATEMENT}", json={"draft": "Half done."})    # a draft, then not needed after all
    for key in (STATEMENT, CV, BUDGET):
        body = artist.put(f"{url}/items/{key}", json={"skipped": True}).json()
    assert body["missing"] == [] and all(i["skipped"] for i in body["to_gather"])
    with zipfile.ZipFile(io.BytesIO(artist.get(f"{url}/download").content)) as z:
        assert sorted(z.namelist()) == ["application.docx", "checklist.txt", "texts/01 Why this residency.txt"]
        assert "Budget" not in z.read("checklist.txt").decode()
    body = artist.put(f"{url}/items/{BUDGET}", json={"skipped": False}).json()    # undone
    assert body["missing"] == ["1 item to gather"]


def test_only_the_calls_items_can_be_marked_not_needed(artist):
    key = artist.post("/api/applications/call/texts", json={"title": "Cover letter"}).json()["to_draft"][-1]["key"]
    assert artist.put(f"/api/applications/call/items/{key}", json={"skipped": True}).status_code == 422
