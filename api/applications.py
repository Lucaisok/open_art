"""
OpenArt API — an artist's application to one call (workflow.MD, "Step 6 — Application agent").

    GET  /api/applications/{opportunity_id}                         the checklist with the artist's
                                                                    drafts, ticks and documents
    PUT  /api/applications/{opportunity_id}/items/{key}             save a draft (back to "draft") or a tick
    POST /api/applications/{opportunity_id}/items/{key}/confirm     "I have reviewed this"
    GET  /api/applications/{opportunity_id}/items/{key}/messages    the chat about one item
    POST /api/applications/{opportunity_id}/items/{key}/messages    a message to the agent: its reply
                                                                    and a new draft (src/agent/drafting.py)
    GET  /api/applications/{opportunity_id}/download                the complete application as a zip: the
                                                                    reviewed texts + the requested documents

What the call asks for comes from the corpus every time (src/agent/checklist.py); only the artist's
own work is stored (api/models.py: Application, ApplicationItem, AgentMessage), created on their first save.
Human in the loop: only the confirm route sets "confirmed", and only on a draft the artist can see;
any later change to the text, the agent's included, sets it back to "draft". The agent's model call
(OpenAI) is the only thing that leaves the server, and nothing is ever sent to the call itself.
"""

import io
import os
import re
import uuid
import zipfile
from datetime import date, datetime, timezone
from functools import lru_cache
from typing import Literal

from docx import Document as DocxDocument
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from openai import OpenAI, OpenAIError
from pydantic import BaseModel, Field
from sqlalchemy import select

from api.auth import DB, CurrentUser
from api import discover   # discover.get_matcher(), not imported by name: the tests replace it
from api.documents import stored_path
from api.knowledge_base import PgKnowledgeBase
from api.models import AgentMessage, Application, ApplicationItem, Document, Profile, Project
from src.agent.checklist import ChecklistItem, build_checklist
from src.agent.drafting import Passage, TurnContext, agent_turn
from src.eligibility.engine import Status
from src.models.processed_opportunity import ProcessedOpportunity

router = APIRouter(prefix="/api/applications", tags=["applications"])

MAX_DRAFT_CHARS = 20_000   # far above any call's limit; only stops abuse


class ItemOut(BaseModel):
    key: str
    kind: Literal["write", "gather"]
    source: Literal["question", "material"]
    title: str
    limit: str | None
    document: str | None        # "cv" / "statement" / "portfolio" that covers it (uploaded or not)
    # write: "empty" / "draft" / "confirmed"; gather: "uploaded" (its document is) / "ticked" / "missing"
    state: Literal["empty", "draft", "confirmed", "uploaded", "ticked", "missing"]
    draft: str | None


class ApplicationDocumentOut(BaseModel):
    kind: str
    file_name: str


class ApplicationOut(BaseModel):
    opportunity_id: str
    title: str
    deadline: date | None
    source_url: str
    how_to_apply: str | None
    application_language: str | None
    submission_method: str | None
    verdict_status: Status            # the engine's, as on the opportunity page: never changed here
    to_draft: list[ItemOut]
    to_gather: list[ItemOut]
    documents: list[ApplicationDocumentOut]
    # what stands before the download ("2 texts to review"); [] = complete. Same rule as the download route
    missing: list[str] = []


class ItemIn(BaseModel):
    """Either field, or both. A draft only for an item to write, a tick only for one to gather."""
    draft: str | None = Field(default=None, max_length=MAX_DRAFT_CHARS)
    ticked: bool | None = None


def _call(opportunity_id: str) -> ProcessedOpportunity:
    call = discover.get_matcher().get(opportunity_id)
    if call is None:
        raise HTTPException(404, "No such call.")
    return call


def _application(db, user_id: uuid.UUID, opportunity_id: str, create: bool = False) -> Application | None:
    application = db.scalar(select(Application).where(Application.user_id == user_id,
                                                      Application.opportunity_id == opportunity_id))
    if application is None and create:
        application = Application(user_id=user_id, opportunity_id=opportunity_id)
        db.add(application)
        db.flush()   # gives it its id
    return application


def _state(item: ChecklistItem, saved: ApplicationItem | None, uploaded: set[str]) -> str:
    if item.kind == "write":
        return saved.status if saved and saved.status else "empty"
    if item.document in uploaded:
        return "uploaded"
    return "ticked" if saved and saved.ticked else "missing"


def _item_out(item: ChecklistItem, saved: ApplicationItem | None, uploaded: set[str]) -> ItemOut:
    return ItemOut(key=item.key, kind=item.kind, source=item.source, title=item.title, limit=item.limit,
                   document=item.document, state=_state(item, saved, uploaded),
                   draft=saved.draft if saved else None)


def _application_out(db, user_id: uuid.UUID, call: ProcessedOpportunity) -> ApplicationOut:
    documents = list(db.scalars(select(Document).where(Document.user_id == user_id).order_by(Document.kind)))
    uploaded = {d.kind for d in documents}
    application = _application(db, user_id, call.id)
    saved = {i.key: i for i in application.items} if application else {}
    items = [_item_out(i, saved.get(i.key), uploaded) for i in build_checklist(call)]
    profile, _ = discover.saved_profile(db, user_id)
    out = ApplicationOut(
        opportunity_id=call.id, title=call.title_en, deadline=call.deadline_date, source_url=call.source_url,
        how_to_apply=call.how_to_apply_en or call.how_to_apply,
        application_language=call.application_language_en or call.application_language,
        submission_method=call.submission_method,
        verdict_status=discover.get_matcher().engine.evaluate(profile, call).status,
        to_draft=[i for i in items if i.kind == "write"], to_gather=[i for i in items if i.kind == "gather"],
        documents=[ApplicationDocumentOut(kind=d.kind, file_name=d.file_name) for d in documents])
    out.missing = missing(out)
    return out


def _checklist_item(call: ProcessedOpportunity, key: str) -> ChecklistItem:
    item = next((i for i in build_checklist(call) if i.key == key), None)
    if item is None:
        raise HTTPException(404, "This call doesn't ask for that item.")
    return item


def _saved_item(db, application: Application, key: str) -> ApplicationItem:
    saved = db.get(ApplicationItem, (application.id, key))
    if saved is None:
        saved = ApplicationItem(application_id=application.id, key=key, ticked=False)
        db.add(saved)
    return saved


@router.get("/{opportunity_id}")
def get_application(opportunity_id: str, user: CurrentUser, db: DB) -> ApplicationOut:
    return _application_out(db, user.id, _call(opportunity_id))


@router.put("/{opportunity_id}/items/{key}")
def save_item(opportunity_id: str, key: str, body: ItemIn, user: CurrentUser, db: DB) -> ApplicationOut:
    call = _call(opportunity_id)
    item = _checklist_item(call, key)
    if body.draft is not None and item.kind != "write":
        raise HTTPException(422, "Only an item to write has a draft.")
    if body.ticked is not None and item.kind != "gather":
        raise HTTPException(422, "Only an item to gather can be ticked.")
    saved = _saved_item(db, _application(db, user.id, call.id, create=True), key)
    if body.draft is not None and body.draft != saved.draft:
        saved.draft = body.draft
        saved.status = "draft" if body.draft.strip() else None   # a changed text needs a new review
    if body.ticked is not None:
        saved.ticked = body.ticked
    db.commit()
    return _application_out(db, user.id, call)


@router.post("/{opportunity_id}/items/{key}/confirm")
def confirm_item(opportunity_id: str, key: str, user: CurrentUser, db: DB) -> ApplicationOut:
    call = _call(opportunity_id)
    _checklist_item(call, key)
    application = _application(db, user.id, call.id)
    saved = db.get(ApplicationItem, (application.id, key)) if application else None
    if saved is None or saved.status is None:
        raise HTTPException(409, "There is no draft to confirm yet.")
    saved.status = "confirmed"
    db.commit()
    return _application_out(db, user.id, call)


# -- the agent (sub-step 4) ----------------------------------------------------------------------------

PASSAGES = 6             # the artist's passages closest to the item
STATEMENT_PASSAGES = 4   # plus, when adapting the uploaded statement, its own closest passages


@lru_cache
def get_openai() -> OpenAI:
    """One client per process; reads OPENAI_API_KEY (docker-compose.yml). The tests replace it."""
    return OpenAI()


class MessageOut(BaseModel):
    role: Literal["artist", "agent"]
    content: str
    sources: list[str]          # the agent's: citations of the passages it relied on
    created_at: datetime


class MessageIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    # the text in the draft box now, saved or not: the agent revises what the artist sees
    draft: str | None = Field(default=None, max_length=MAX_DRAFT_CHARS)


class TurnOut(BaseModel):
    application: ApplicationOut
    messages: list[MessageOut]


def _messages(db, application: Application | None, key: str) -> list[AgentMessage]:
    if application is None:
        return []
    return list(db.scalars(select(AgentMessage).where(AgentMessage.application_id == application.id,
                                                      AgentMessage.item_key == key)
                           .order_by(AgentMessage.created_at, AgentMessage.id)))


def _message_out(m: AgentMessage) -> MessageOut:
    return MessageOut(role=m.role, content=m.content, sources=m.sources, created_at=m.created_at)


def _passages(db, user_id: uuid.UUID, query: str, statement_file: str | None) -> list[Passage]:
    """The artist's passages closest to the item, plus the statement's own when adapting it."""
    kb = PgKnowledgeBase(db, user_id)
    try:
        found = kb.retrieve(query, k=PASSAGES)
        if statement_file:
            found += kb.retrieve(query, k=STATEMENT_PASSAGES, documents=[statement_file])
    except RuntimeError:
        raise HTTPException(409, "Your documents need to be uploaded again before the assistant can use them.")
    unique = {p.chunk.chunk_id: p for p in found}   # a statement passage can be in both lists
    return [Passage(id=f"P{i}", citation=p.citation, text=p.chunk.text)
            for i, p in enumerate(unique.values(), start=1)]


def _profile(db, user_id: uuid.UUID) -> dict[str, object]:
    row = db.get(Profile, user_id)
    return {k: v for k, v in (row.values if row else {}).items() if v not in (None, [], "")}


def _projects(db, user_id: uuid.UUID) -> list[str]:
    lines = []
    for p in db.scalars(select(Project).where(Project.user_id == user_id)):
        if p.kind == "interest":
            lines.append(f"Interest: {p.summary}")
        else:
            when = ", ".join(x for x in (p.status, p.years, p.medium) if x)
            lines.append(f"{p.title or 'Untitled project'} ({when}): {p.summary or ''}".strip())
    return lines


@router.get("/{opportunity_id}/items/{key}/messages")
def get_messages(opportunity_id: str, key: str, user: CurrentUser, db: DB) -> list[MessageOut]:
    call = _call(opportunity_id)
    _checklist_item(call, key)
    return [_message_out(m) for m in _messages(db, _application(db, user.id, call.id), key)]


@router.post("/{opportunity_id}/items/{key}/messages")
def send_message(opportunity_id: str, key: str, body: MessageIn, user: CurrentUser, db: DB) -> TurnOut:
    call = _call(opportunity_id)
    item = _checklist_item(call, key)
    if item.kind != "write":
        raise HTTPException(422, "The assistant only drafts items to write.")
    application = _application(db, user.id, call.id, create=True)
    saved = _saved_item(db, application, key)
    history = _messages(db, application, key)

    # the application's memory: the other items' current drafts, by their titles
    titles = {i.key: i.title for i in build_checklist(call)}
    other_drafts = [(titles[i.key], i.draft) for i in application.items
                    if i.key != key and i.key in titles and i.draft and i.draft.strip()]
    statement = db.scalar(select(Document).where(Document.user_id == user.id, Document.kind == "statement"))
    adapt = item.document == "statement" and statement is not None
    passages = _passages(db, user.id, f"{item.title}. {call.title_en}", statement.file_name if adapt else None)

    context = TurnContext(
        item_title=item.title, item_limit=item.limit,
        call={"Title": call.title_en, "Organisation": call.organisation, "Description": call.description_en,
              "Project requirements": call.project_requirements_en or call.project_requirements,
              "Selection criteria": call.selection_criteria_en or call.selection_criteria,
              "Application language": call.application_language_en or call.application_language},
        passages=passages, profile=_profile(db, user.id), projects=_projects(db, user.id),
        other_drafts=other_drafts, history=[(m.role, m.content) for m in history],
        current_draft=body.draft if body.draft is not None else saved.draft,
        message=body.message, adapt_statement=adapt)
    # times set here, not by the database: both rows are saved in one transaction, where now() is one instant
    asked_at = datetime.now(timezone.utc)
    try:
        answer = agent_turn(get_openai(), context)
    except OpenAIError:
        raise HTTPException(503, "The assistant isn't available right now. Please try again in a moment.")

    by_id = {p.id: p.citation for p in passages}
    sources = list(dict.fromkeys(by_id[i] for i in answer.used_passages if i in by_id))   # unique, in order
    db.add(AgentMessage(application_id=application.id, item_key=key, role="artist", content=body.message,
                        created_at=asked_at))
    db.add(AgentMessage(application_id=application.id, item_key=key, role="agent", content=answer.reply,
                        sources=sources, created_at=datetime.now(timezone.utc)))
    saved.draft = answer.draft
    saved.status = "draft" if answer.draft.strip() else None   # the artist reviews it: never "confirmed" here
    db.commit()
    return TurnOut(application=_application_out(db, user.id, call),
                   messages=[_message_out(m) for m in _messages(db, application, key)])


# -- download (sub-step 6) -----------------------------------------------------------------------------

def missing(application: ApplicationOut) -> list[str]:
    """What still stands between the artist and a complete application: texts not reviewed, items
    neither uploaded nor ticked. [] = complete."""
    to_review = sum(i.state != "confirmed" for i in application.to_draft)
    to_gather = sum(i.state not in ("uploaded", "ticked") for i in application.to_gather)
    out = []
    if to_review:
        out.append(f"{to_review} text{'s' if to_review > 1 else ''} to review")
    if to_gather:
        out.append(f"{to_gather} item{'s' if to_gather > 1 else ''} to gather")
    return out


def _call_lines(call: ProcessedOpportunity, application: ApplicationOut) -> list[str]:
    lines = [call.title_en, f"Call: {call.source_url}"]
    if application.deadline:
        lines.append(f"Deadline: {application.deadline.isoformat()}")
    if application.submission_method:
        lines.append(f"Submit by: {application.submission_method}")
    return lines


def _to_send(application: ApplicationOut) -> list[str]:
    return [i.title + (f" ({i.limit})" if i.limit else "")
            + (f": in this folder ({i.document})" if i.state == "uploaded" else ": you have it")
            for i in application.to_gather]


def checklist_text(call: ProcessedOpportunity, application: ApplicationOut, text_files: list[str]) -> str:
    """checklist.txt: the call, and every file or thing that goes into the application."""
    lines = _call_lines(call, application) + ["", "Texts (reviewed by you):"]
    lines += [f"- {name}" for name in text_files]
    if application.to_gather:
        lines += ["", "To send with them:"] + [f"- {line}" for line in _to_send(application)]
    return "\n".join(lines) + "\n"


def application_docx(call: ProcessedOpportunity, application: ApplicationOut) -> bytes:
    """application.docx: every reviewed text under its own heading, for calls that want a document."""
    document = DocxDocument()
    document.add_heading(call.title_en, level=1)
    for line in _call_lines(call, application)[1:]:
        document.add_paragraph(line)
    for item in application.to_draft:
        document.add_heading(item.title + (f" ({item.limit})" if item.limit else ""), level=2)
        for paragraph in re.split(r"\n\s*\n", (item.draft or "").strip()):   # the text's own paragraphs
            document.add_paragraph(paragraph.strip())
    if application.to_gather:
        document.add_heading("To send with it", level=2)
        for line in _to_send(application):
            document.add_paragraph(line, style="List Bullet")
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


def _safe_name(text: str) -> str:
    """A file name from free text: letters (accents too), digits, spaces and dashes only."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\- ]+", " ", text)).strip()[:60].strip() or "application"


@router.get("/{opportunity_id}/download")
def download(opportunity_id: str, user: CurrentUser, db: DB) -> Response:
    """The complete application as a zip. Refused until every text is reviewed and every item is
    uploaded or ticked: the review is enforced here, not only on the page. Holds each text as a .txt
    (to paste into forms), all of them in application.docx (to attach), checklist.txt, and for each item
    covered by an upload that original file (only the documents the call asks for)."""
    call = _call(opportunity_id)
    application = _application_out(db, user.id, call)
    gaps = missing(application)
    if gaps:
        raise HTTPException(409, "Not complete yet: " + ", ".join(gaps) + ".")

    requested = {i.document for i in application.to_gather if i.state == "uploaded"}
    documents = db.scalars(select(Document).where(Document.user_id == user.id, Document.kind.in_(requested)))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        # one plain text per item, numbered in the call's order: clean to paste into the call's form
        text_files = [f"{n:02d} {_safe_name(item.title)}.txt" for n, item in enumerate(application.to_draft, start=1)]
        for name, item in zip(text_files, application.to_draft):
            zip_file.writestr(f"texts/{name}", (item.draft or "").strip() + "\n")
        zip_file.writestr("application.docx", application_docx(call, application))
        zip_file.writestr("checklist.txt", checklist_text(call, application, text_files))
        for d in documents:
            # "cv - my_cv.pdf": the slot first, so two uploads with the same name can't collide
            zip_file.write(stored_path(d), f"{d.kind} - {os.path.basename(d.file_name)}")
    name = _safe_name(call.title_en).replace(" ", "-")
    return Response(buffer.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{name}.zip"'})
