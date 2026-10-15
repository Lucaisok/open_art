"""
OpenArt API — the calls an artist saved (workflow.MD, "Saved calls"): the Studio's centre column.

    PUT    /api/saved/{opportunity_id}     save a call (Discover's Save; starting an application also does)
    DELETE /api/saved/{opportunity_id}     remove it from the list, with its application (draft) if started
    GET    /api/saved                      every saved call, in its stage, with its application's progress

Stages, decided here on every request from the corpus and the artist's application:
    saved       saved, no application started
    draft       an application started (a draft, a tick, chosen images or projects, a message)
    completed   started, and every text reviewed and every item gathered (api/applications.missing:
                the same rule that opens the download)
    closed      the deadline has passed, or the call is no longer in the corpus, whatever was done
                (`was` keeps the stage it had: "Closed · 30 Sep · was in draft")

Each listed call also has its match percentage, as on Discover's cards (the same ranking vector:
documents and current projects), when anything ranks the artist.
"""

import uuid
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from api import applications, discover   # by module: the tests replace discover.get_matcher
from api.auth import DB, CurrentUser
from api.models import Application, SavedCall
from src.matching.explain import ArtistText, explain
from src.matching.matcher import discipline_mismatch
from src.matching.score import ArtistStats
from src.eligibility.engine import Status

router = APIRouter(prefix="/api/saved", tags=["saved"])

Stage = Literal["saved", "draft", "completed", "closed"]
STAGE_ORDER = {"draft": 0, "saved": 1, "completed": 2, "closed": 3}


class Progress(BaseModel):
    texts_reviewed: int
    texts: int
    items_gathered: int
    items: int


class SavedCallOut(BaseModel):
    id: str
    title: str
    organisation: str | None = None
    types: list[str] = []
    city: str | None = None
    countries: list[str] = []
    deadline: date | None
    funding: str | None = None        # the headline sum, as on Discover's cards
    status: Status | None = None      # the engine's verdict on the saved profile; None when the call is gone
    stage: Stage
    was: Stage | None = None          # a closed call's stage before closing
    match: int | None = None          # "86% match", as on Discover; None when nothing ranks the artist
    listed: bool                      # still in the corpus (False: gone, shown from what was saved)
    progress: Progress | None = None  # None until an application is started
    saved_at: datetime


class SavedCallsOut(BaseModel):
    calls: list[SavedCallOut]          # draft first, then saved, completed, closed; by deadline within each
    counts: dict[str, int]             # per stage, for the tabs


def save_call(db, user_id: uuid.UUID, call) -> None:
    """Saves the call (no commit) unless it is saved already. Used by the route and by
    api/applications.py when an application is started."""
    if db.get(SavedCall, (user_id, call.id)) is None:
        db.add(SavedCall(user_id=user_id, opportunity_id=call.id, title=call.title_en, deadline=call.deadline_date))


def saved_ids(db, user_id: uuid.UUID) -> set[str]:
    return set(db.scalars(select(SavedCall.opportunity_id).where(SavedCall.user_id == user_id)))


@router.put("/{opportunity_id}", status_code=204)
def save(opportunity_id: str, user: CurrentUser, db: DB) -> None:
    call = discover.get_matcher().get(opportunity_id)
    if call is None:
        raise HTTPException(404, "No such call.")
    save_call(db, user.id, call)
    db.commit()


@router.delete("/{opportunity_id}", status_code=204)
def unsave(opportunity_id: str, user: CurrentUser, db: DB) -> None:
    """Removes the call and, as the Studio's confirmation says, its application: drafts, ticks, chat
    (their rows cascade). Saving it again starts afresh."""
    saved = db.get(SavedCall, (user.id, opportunity_id))
    if saved is not None:
        db.delete(saved)
    application = db.scalar(select(Application).where(Application.user_id == user.id,
                                                      Application.opportunity_id == opportunity_id))
    if application is not None:
        db.delete(application)
    db.commit()


def _progress(application) -> Progress:
    application = applications.without_skipped(application)   # "Not needed" items don't count
    return Progress(texts_reviewed=sum(i.state == "confirmed" for i in application.to_draft),
                    texts=len(application.to_draft),
                    items_gathered=sum(i.state in ("uploaded", "chosen", "ticked") for i in application.to_gather),
                    items=len(application.to_gather))


@router.get("")
def list_saved(user: CurrentUser, db: DB) -> SavedCallsOut:
    matcher = discover.get_matcher()
    today = date.today()
    started = set(db.scalars(select(Application.opportunity_id).where(Application.user_id == user.id)))
    # the match percentage's inputs, once (as Discover's search): nothing ranks the artist -> no match
    profile, _ = discover.saved_profile(db, user.id)
    _, vector = discover.ranking_vector(db, user.id, matcher)
    artist = ArtistText(discover.ranking_documents(db, user.id, matcher)) if vector is not None else None
    stats = ArtistStats.of(matcher.index.vectors, vector) if vector is not None else None
    calls = []
    for saved in db.scalars(select(SavedCall).where(SavedCall.user_id == user.id)):
        call = matcher.get(saved.opportunity_id)
        if call is None:
            # gone from the corpus: what was copied at saving
            calls.append(SavedCallOut(id=saved.opportunity_id, title=saved.title, deadline=saved.deadline,
                                      stage="closed", listed=False, saved_at=saved.saved_at))
            continue
        # the corpus may have been updated since saving (a corrected deadline): keep the copy current
        saved.title, saved.deadline = call.title_en, call.deadline_date
        application = applications.application_out(db, user.id, call)
        progress = _progress(application) if call.id in started else None
        if progress is None:
            stage = "saved"
        elif not applications.missing(application):
            stage = "completed"
        else:
            stage = "draft"
        was = None
        if call.deadline_date and call.deadline_date < today:
            stage, was = "closed", stage
        match = None
        if vector is not None:
            verdict = matcher.engine.evaluate(profile, call)
            shared = len(explain(matcher.explainer, artist, call).shared)
            match = discover.match_percent(matcher, call, vector, stats, shared,
                                           discipline_mismatch(call, verdict, profile))
        city, countries = discover.place(call)
        calls.append(SavedCallOut(
            id=call.id, title=call.title_en, organisation=call.organisation, types=call.opportunity_type_canonical,
            city=city, countries=countries, deadline=call.deadline_date, funding=discover.headline_funding(call),
            status=application.verdict_status, stage=stage, was=was, match=match, listed=True, progress=progress,
            saved_at=saved.saved_at))
    db.commit()   # the refreshed copies
    # within a stage: the nearest deadline first (none last); closed ones: the most recent first
    far = date.max.toordinal()
    calls.sort(key=lambda c: (STAGE_ORDER[c.stage],
                              -(c.deadline.toordinal() if c.deadline else 0) if c.stage == "closed"
                              else (c.deadline.toordinal() if c.deadline else far)))
    counts = {stage: sum(c.stage == stage for c in calls) for stage in STAGE_ORDER}
    return SavedCallsOut(calls=calls, counts=counts)
