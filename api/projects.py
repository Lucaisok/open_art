"""
OpenArt API — the artist's projects (past, current, planned) and interests (workflow.MD, "Projects page").

    GET    /api/projects                 saved projects and interests, and suggestions read from the
                                         artist's documents by rules (src/rag/project_rules.py)
    POST   /api/projects                 save one: added by hand, or a suggestion accepted (as is or edited)
    PUT    /api/projects/{id}            edit a saved one
    DELETE /api/projects/{id}            delete a saved one
    POST   /api/projects/dismiss         decline a suggestion: not offered again

Suggestions are computed on every GET from the documents' chunks (no model call, nothing leaves the
server) and are never stored: only what the artist accepts is. An accepted suggestion keeps its source
quotes, copied here from the suggestion itself, not from the browser.
"""

import re
import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from api.auth import DB, CurrentUser
from api.models import DismissedSuggestion, Document, KnowledgeChunkRow, Project
from src.rag.documents import Chunk
from src.rag.project_rules import extract_projects

router = APIRouter(prefix="/api/projects", tags=["projects"])

Kind = Literal["project", "interest"]
Status = Literal["past", "current", "planned"]


class SourceOut(BaseModel):
    quote: str
    citation: str


class ProjectIn(BaseModel):
    kind: Kind = "project"
    title: str | None = Field(default=None, max_length=200)
    status: Status | None = None
    years: str | None = Field(default=None, max_length=30)
    summary: str | None = Field(default=None, max_length=3000)
    medium: str | None = Field(default=None, max_length=200)
    venues: list[str] = Field(default=[], max_length=30)
    suggestion_key: str | None = Field(default=None, max_length=300)   # set when accepting a suggestion

    @field_validator("title", "years", "summary", "medium")
    @classmethod
    def _tidy(cls, value: str | None) -> str | None:
        value = " ".join(value.split()) if value else None
        return value or None

    @field_validator("venues")
    @classmethod
    def _tidy_venues(cls, values: list[str]) -> list[str]:
        return [" ".join(v.split())[:200] for v in values if v and v.strip()]


class ProjectOut(ProjectIn):
    id: uuid.UUID | None = None          # None on a suggestion
    sources: list[SourceOut] = []
    from_documents: bool = False


class ProjectsOut(BaseModel):
    projects: list[ProjectOut]           # saved, current first, then planned, then past (newest first)
    interests: list[ProjectOut]          # saved
    suggestions: list[ProjectOut]        # read from the documents, not saved, not dismissed


class DismissIn(BaseModel):
    key: str = Field(max_length=300)


STATUS_ORDER = {"current": 0, "planned": 1, "past": 2, None: 3}


def _check(body: ProjectIn) -> None:
    """A project needs a status and a title or summary; an interest needs its text (summary)."""
    if body.kind == "project" and (body.status is None or not (body.title or body.summary)):
        raise HTTPException(422, "A project needs a status and a title or a description.")
    if body.kind == "interest" and not body.summary:
        raise HTTPException(422, "An interest needs its text.")


def _out(p: Project) -> ProjectOut:
    return ProjectOut(id=p.id, kind=p.kind, title=p.title, status=p.status, years=p.years, summary=p.summary,
                      medium=p.medium, venues=p.venues, sources=p.sources, suggestion_key=p.suggestion_key,
                      from_documents=bool(p.sources))


def _first_year(years: str | None) -> int:
    found = re.search(r"\d{4}", years or "")
    return int(found.group()) if found else 0


def _suggestions(db, user_id: uuid.UUID) -> list[ProjectOut]:
    """Everything the rules read from the artist's documents, each with a stable key."""
    documents = []
    for document in db.scalars(select(Document).where(Document.user_id == user_id)):
        rows = db.scalars(select(KnowledgeChunkRow).where(KnowledgeChunkRow.document_id == document.id)
                          .order_by(KnowledgeChunkRow.index))
        documents.append((document.kind, document.file_name,
                          [Chunk(index=r.index, section=r.section, text=r.text, page=r.page) for r in rows]))
    found = extract_projects(documents)
    out = [ProjectOut(kind="project", title=p.title, status=p.status, years=p.years, summary=p.summary,
                      medium=p.medium, venues=p.venues, suggestion_key=f"project:{p.key}"[:300],
                      sources=[SourceOut(quote=s.quote, citation=s.citation) for s in p.sources], from_documents=True)
           for p in found.projects]
    out += [ProjectOut(kind="interest", summary=i.text, sources=[SourceOut(quote=i.text, citation=i.citation)],
                       suggestion_key=("interest:" + re.sub(r"[^a-z0-9]", "", i.text.lower()))[:300],
                       from_documents=True)
            for i in found.interests]
    return out


def _projects_out(db, user_id: uuid.UUID) -> ProjectsOut:
    saved = list(db.scalars(select(Project).where(Project.user_id == user_id)))
    taken = {p.suggestion_key for p in saved if p.suggestion_key}
    taken |= set(db.scalars(select(DismissedSuggestion.key).where(DismissedSuggestion.user_id == user_id)))
    projects = sorted((p for p in saved if p.kind == "project"),
                      key=lambda p: (STATUS_ORDER[p.status], -_first_year(p.years)))
    return ProjectsOut(projects=[_out(p) for p in projects],
                       interests=[_out(p) for p in saved if p.kind == "interest"],
                       suggestions=[s for s in _suggestions(db, user_id) if s.suggestion_key not in taken])


@router.get("")
def list_projects(user: CurrentUser, db: DB) -> ProjectsOut:
    return _projects_out(db, user.id)


@router.post("", status_code=201)
def add_project(body: ProjectIn, user: CurrentUser, db: DB) -> ProjectOut:
    _check(body)
    sources = []
    if body.suggestion_key:
        # the quotes come from the suggestion as read on the server, never from the request
        suggestion = next((s for s in _suggestions(db, user.id) if s.suggestion_key == body.suggestion_key), None)
        if suggestion is None:
            raise HTTPException(404, "That suggestion is no longer in your documents.")
        sources = [s.model_dump() for s in suggestion.sources]
    project = Project(user_id=user.id, sources=sources, **body.model_dump())
    db.add(project)
    db.commit()
    return _out(project)


def _owned(db, user_id: uuid.UUID, project_id: uuid.UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.user_id != user_id:   # someone else's id looks like a missing one
        raise HTTPException(404, "No such project.")
    return project


@router.put("/{project_id}")
def edit_project(project_id: uuid.UUID, body: ProjectIn, user: CurrentUser, db: DB) -> ProjectOut:
    _check(body)
    project = _owned(db, user.id, project_id)
    for name, value in body.model_dump(exclude={"suggestion_key", "kind"}).items():
        setattr(project, name, value)
    db.commit()
    return _out(project)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: uuid.UUID, user: CurrentUser, db: DB) -> None:
    db.delete(_owned(db, user.id, project_id))
    db.commit()


@router.post("/dismiss", status_code=204)
def dismiss(body: DismissIn, user: CurrentUser, db: DB) -> None:
    if db.get(DismissedSuggestion, (user.id, body.key)) is None:
        db.add(DismissedSuggestion(user_id=user.id, key=body.key))
        db.commit()
