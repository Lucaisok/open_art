"""
OpenArt API — the artist's projects (past, current, planned) and interests (workflow.MD, "Projects page").

    GET    /api/projects                 saved projects and interests, and suggestions read from the
                                         artist's documents by rules (src/rag/project_rules.py), each
                                         with its images (api/images.py, which also adds and removes them)
    POST   /api/projects                 save one: added by hand, or a suggestion accepted (as is or edited)
    PUT    /api/projects/{id}            edit a saved one
    DELETE /api/projects/{id}            delete a saved one
    POST   /api/projects/dismiss         decline a suggestion: not offered again
    POST   /api/projects/review          many at once: keep some (with their status), dismiss the others
                                         (the onboarding's Projects step; the profile's Save does the same)

Suggestions are computed on every GET from the documents' chunks (no model call, nothing leaves the
server) and are never stored: only what the artist accepts is. An accepted suggestion keeps its source
quotes, copied here from the suggestion itself, not from the browser. The profile page reviews the same
suggestions with its own Save (pending_suggestions, review_suggestions).
"""

import re
import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from api.auth import DB, CurrentUser
from api.images import ImageOut, files_of, image_out, project_images, remove_files, start_reading
from api.models import DismissedSuggestion, Document, KnowledgeChunkRow, Project, ProjectImage
from src.rag.images import works_by_page
from src.rag.documents import Chunk
from src.rag.project_rules import extract_projects

router = APIRouter(prefix="/api/projects", tags=["projects"])

Kind = Literal["project", "interest"]
Status = Literal["past", "current", "planned"]
Category = Literal["work", "exhibition", "performance", "commission"]   # project_rules.CATEGORY_OF_SECTION


class SourceOut(BaseModel):
    quote: str
    citation: str


class ProjectIn(BaseModel):
    kind: Kind = "project"
    title: str | None = Field(default=None, max_length=200)
    status: Status | None = None
    category: Category | None = None     # a project's; None for an interest
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
    images: list[ImageOut] = []          # a suggestion's: read from its pages; a saved project's: its own


class ProjectsOut(BaseModel):
    projects: list[ProjectOut]           # saved, current first, then planned, then past (newest first)
    interests: list[ProjectOut]          # saved
    suggestions: list[ProjectOut]        # read from the documents, not saved, not dismissed


class DismissIn(BaseModel):
    key: str = Field(max_length=300)


class AcceptIn(BaseModel):
    key: str = Field(max_length=300)
    status: Status | None = None       # a work's "Current project" tick; None keeps the rule's


class ReviewIn(BaseModel):
    accept: list[AcceptIn] = Field(default=[], max_length=500)
    dismiss: list[str] = Field(default=[], max_length=500)


STATUS_ORDER = {"current": 0, "planned": 1, "past": 2, None: 3}


def can_propose(p: Project) -> bool:
    """A project to apply with, and what "Matched to you" weighs most (api/discover.py): a planned or
    current work. An exhibition, performance or commission is track record, to mention, not a project
    to apply with. A project saved before categories (None) counts as a work."""
    return p.kind == "project" and p.status in ("planned", "current") and (p.category or "work") == "work"


def project_text(p: Project) -> str:
    """A project in words, for embedding: title, medium and the artist's description."""
    return " ".join(x for x in (p.title, p.medium, p.summary) if x) or "project"


def _check(body: ProjectIn) -> None:
    """A project needs a status and a title or summary (and is a work unless it says otherwise); an
    interest needs its text (summary) and has no category."""
    if body.kind == "project" and (body.status is None or not (body.title or body.summary)):
        raise HTTPException(422, "A project needs a status and a title or a description.")
    if body.kind == "interest" and not body.summary:
        raise HTTPException(422, "An interest needs its text.")
    body.category = (body.category or "work") if body.kind == "project" else None


def _out(p: Project, images: list[ProjectImage] | None = None) -> ProjectOut:
    return ProjectOut(id=p.id, kind=p.kind, title=p.title, status=p.status, category=p.category, years=p.years,
                      summary=p.summary, medium=p.medium, venues=p.venues, sources=p.sources,
                      suggestion_key=p.suggestion_key, from_documents=bool(p.sources),
                      images=[image_out(i) for i in images or []])


def _first_year(years: str | None) -> int:
    found = re.search(r"\d{4}", years or "")
    return int(found.group()) if found else 0


def _found_images(db, rows: list[Document], titles: list[str]) -> dict[str, list[ImageOut]]:
    """{work title: its images}, from the documents' images no project holds yet, each put with the
    work whose title page it is on (src/rag/images.py works_by_page). A document whose images aren't
    read yet (uploaded before images were) is queued now: its images show on a later visit."""
    found: dict[str, list[ImageOut]] = {}
    for document in rows:
        start_reading(document)
        if not document.page_lines:
            continue
        owner = works_by_page(titles, document.page_lines)
        loose = db.scalars(select(ProjectImage).where(ProjectImage.document_id == document.id,
                                                      ProjectImage.project_id.is_(None))
                           .order_by(ProjectImage.page, ProjectImage.created_at))
        for image in loose:
            if title := owner.get(image.page):
                found.setdefault(title, []).append(image_out(image))
    return found


def _suggestions(db, user_id: uuid.UUID) -> list[ProjectOut]:
    """Everything the rules read from the artist's documents, each with a stable key."""
    documents, rows = [], list(db.scalars(select(Document).where(Document.user_id == user_id)))
    for document in rows:
        chunks = db.scalars(select(KnowledgeChunkRow).where(KnowledgeChunkRow.document_id == document.id)
                            .order_by(KnowledgeChunkRow.index))
        documents.append((document.kind, document.file_name,
                          [Chunk(index=r.index, section=r.section, text=r.text, page=r.page) for r in chunks]))
    found = extract_projects(documents)
    images = _found_images(db, rows, [p.title for p in found.projects if p.category == "work" and p.title])
    out = [ProjectOut(kind="project", title=p.title, status=p.status, category=p.category, years=p.years,
                      summary=p.summary, medium=p.medium, venues=p.venues, suggestion_key=f"project:{p.key}"[:300],
                      sources=[SourceOut(quote=s.quote, citation=s.citation) for s in p.sources], from_documents=True,
                      images=images.get(p.title, []) if p.category == "work" else [])
           for p in found.projects]
    out += [ProjectOut(kind="interest", summary=i.text, sources=[SourceOut(quote=i.text, citation=i.citation)],
                       suggestion_key=("interest:" + re.sub(r"[^a-z0-9]", "", i.text.lower()))[:300],
                       from_documents=True)
            for i in found.interests]
    return out


def pending_suggestions(db, user_id: uuid.UUID, saved: list[Project] | None = None) -> list[ProjectOut]:
    """The suggestions not yet accepted or dismissed. Also used by the profile page (api/profile.py)."""
    if saved is None:
        saved = list(db.scalars(select(Project).where(Project.user_id == user_id)))
    taken = {p.suggestion_key for p in saved if p.suggestion_key}
    taken |= set(db.scalars(select(DismissedSuggestion.key).where(DismissedSuggestion.user_id == user_id)))
    return [s for s in _suggestions(db, user_id) if s.suggestion_key not in taken]


def claim_images(db, user_id: uuid.UUID, project: Project, suggestion: ProjectOut) -> None:
    """A suggestion saved as a project takes the images shown with it (only loose ones of this artist)."""
    for position, shown in enumerate(suggestion.images):
        image = db.get(ProjectImage, shown.id)
        if image is not None and image.user_id == user_id and image.project_id is None:
            image.project_id, image.position = project.id, position


def review_suggestions(db, user_id: uuid.UUID, accept: dict[str, str | None], dismiss: list[str]) -> None:
    """The profile page's Save: accept some suggestions as they are (key -> status, which the artist may
    have changed) and dismiss others. Everything else comes from the suggestion as read here, never from
    the browser. A key that isn't pending (already saved, gone from the documents) is skipped. Not
    committed: the caller commits it with the profile."""
    pending = {s.suggestion_key: s for s in pending_suggestions(db, user_id)}
    for key, status in accept.items():
        if (suggestion := pending.get(key)) is None:
            continue
        values = suggestion.model_dump(exclude={"id", "sources", "from_documents"})
        if suggestion.kind == "project" and status is not None:
            values["status"] = status
        values.pop("images")
        project = Project(id=uuid.uuid4(), user_id=user_id, sources=[s.model_dump() for s in suggestion.sources],
                          **values)
        db.add(project)
        db.flush()   # the images point at it
        claim_images(db, user_id, project, suggestion)
    for key in dismiss:
        if key in pending and key not in accept and db.get(DismissedSuggestion, (user_id, key)) is None:
            db.add(DismissedSuggestion(user_id=user_id, key=key))


def saved_projects(db, user_id: uuid.UUID, saved: list[Project] | None = None) -> list[ProjectOut]:
    """The saved projects (not interests) with their images: current first, then planned, then past
    (newest first). Also shown on the profile page (api/profile.py)."""
    if saved is None:
        saved = list(db.scalars(select(Project).where(Project.user_id == user_id)))
    projects = sorted((p for p in saved if p.kind == "project"),
                      key=lambda p: (STATUS_ORDER[p.status], -_first_year(p.years)))
    images: dict[uuid.UUID, list[ProjectImage]] = {}
    for image in db.scalars(select(ProjectImage).where(ProjectImage.user_id == user_id,
                                                       ProjectImage.project_id.is_not(None))
                            .order_by(ProjectImage.position, ProjectImage.created_at)):
        images.setdefault(image.project_id, []).append(image)
    return [_out(p, images.get(p.id)) for p in projects]


def _projects_out(db, user_id: uuid.UUID) -> ProjectsOut:
    saved = list(db.scalars(select(Project).where(Project.user_id == user_id)))
    return ProjectsOut(projects=saved_projects(db, user_id, saved),
                       interests=[_out(p) for p in saved if p.kind == "interest"],
                       suggestions=pending_suggestions(db, user_id, saved))


@router.get("")
def list_projects(user: CurrentUser, db: DB) -> ProjectsOut:
    return _projects_out(db, user.id)


@router.post("", status_code=201)
def add_project(body: ProjectIn, user: CurrentUser, db: DB) -> ProjectOut:
    _check(body)
    sources, suggestion = [], None
    if body.suggestion_key:
        # the quotes (and images) come from the suggestion as read on the server, never from the request
        suggestion = next((s for s in _suggestions(db, user.id) if s.suggestion_key == body.suggestion_key), None)
        if suggestion is None:
            raise HTTPException(404, "That suggestion is no longer in your documents.")
        sources = [s.model_dump() for s in suggestion.sources]
    project = Project(id=uuid.uuid4(), user_id=user.id, sources=sources, **body.model_dump())
    db.add(project)
    if suggestion is not None:
        db.flush()
        claim_images(db, user.id, project, suggestion)
    db.commit()
    return _out(project, project_images(db, project.id))


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
    return _out(project, project_images(db, project.id))


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: uuid.UUID, user: CurrentUser, db: DB) -> None:
    project = _owned(db, user.id, project_id)
    paths = files_of(project_images(db, project.id))   # their rows go with it (cascade), their files here
    db.delete(project)
    db.commit()
    remove_files(paths)


@router.post("/dismiss", status_code=204)
def dismiss(body: DismissIn, user: CurrentUser, db: DB) -> None:
    if db.get(DismissedSuggestion, (user.id, body.key)) is None:
        db.add(DismissedSuggestion(user_id=user.id, key=body.key))
        db.commit()


@router.post("/review")
def review(body: ReviewIn, user: CurrentUser, db: DB) -> ProjectsOut:
    """Keeps the accepted suggestions (with the artist's status) and dismisses the others, in one go."""
    review_suggestions(db, user.id, {a.key: a.status for a in body.accept}, body.dismiss)
    db.commit()
    return _projects_out(db, user.id)
