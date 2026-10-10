"""
The artist's eligibility profile (web app step 4).

    GET  /api/profile           what the artist saved, plus suggestions from documents not yet reviewed
    PUT  /api/profile           the artist's Save: replaces the whole profile
    GET  /api/profile/options   countries, disciplines, career stages for the form

The artist's documents are read for profile values when /profile opens: plain rules
(src/rag/cv_rules.py) on their stored passages, in milliseconds, nothing sent anywhere. The CV
gives any field; the statement and portfolio only the Practice fields the CV left empty
(disciplines, applying as, active since). Reading them then rather than at upload means an
improved rule applies to documents already uploaded. /profile shows the values filled into
the form, each marked "From your CV / statement / portfolio" with its quote. Human in the
loop: they become the profile only when the artist presses Save (PUT), the only route that
writes it. That Save also records which documents were reviewed, so their suggestions
aren't offered again until a new one is uploaded.

Stored as the artist sees it, with "active since" (a year) instead of ArtistProfile's
"years active", which would go stale every January: `to_artist_profile` does that
arithmetic when the engine needs the profile.
"""

import uuid
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ValidationError, field_validator
from sqlalchemy import select

from api.auth import DB, CurrentUser
from api.models import Document, KnowledgeChunkRow, Profile
from src.eligibility.geo import COUNTRIES
from src.eligibility.languages import LANGUAGES
from src.eligibility.study import EducationEntry
from src.eligibility.profile import ApplicantType, ArtistProfile
from src.processing.canonicalize import CANONICAL_DISCIPLINES
from src.rag.cv_rules import extract_practice, extract_profile
from src.rag.documents import Chunk

router = APIRouter(prefix="/api/profile", tags=["profile"])

# career stages an artist can pick for themselves ("Any/Open to All" and "Other/Unspecified"
# only make sense on the calls' side)
ARTIST_CAREER_STAGES = ["Student", "Emerging/Early-Career", "Mid-Career", "Established/Professional"]


# -- what is stored and sent -------------------------------------------------------------------------

class ProfileValues(BaseModel):
    """ArtistProfile as the artist fills it in. Every field optional; empty never rejects a call.
    Each check is attached to its field, so the form can show the message next to it."""
    birth_date: date | None = None
    nationalities: list[str] = []
    residence_country: str | None = None
    applicant_type: ApplicantType | None = None
    disciplines: list[str] = []
    career_stage: str | None = None
    active_since: int | None = None         # year of the first professional activity
    currently_enrolled: bool | None = None
    graduation_year: int | None = None
    has_degree: bool | None = None
    degree_field: str | None = None
    languages: list[str] = []               # ISO 639-1 codes: the languages the artist can work in
    education: list[EducationEntry] = []    # the schools the artist studied at

    @field_validator("birth_date")
    @classmethod
    def _check_birth_date(cls, value: date | None) -> date | None:
        if value is not None and value > date.today():
            raise ValueError("Birth date can't be in the future.")
        if value is not None and value.year < 1900:
            raise ValueError("Birth date must be after 1900.")
        return value

    @field_validator("active_since", "graduation_year")
    @classmethod
    def _check_year(cls, value: int | None) -> int | None:
        this_year = date.today().year
        if value is not None and not 1900 <= value <= this_year:
            raise ValueError(f"Enter a year between 1900 and {this_year}.")
        return value

    @field_validator("career_stage")
    @classmethod
    def _check_career_stage(cls, value: str | None) -> str | None:
        if value is not None and value not in ARTIST_CAREER_STAGES:
            raise ValueError("Pick one of the career stages listed.")
        return value

    # countries and disciplines: ArtistProfile's own validators decide (and normalise "hu" -> "HU"),
    # so the form, the pre-fill and the engine share one set of rules
    @field_validator("nationalities")
    @classmethod
    def _check_nationalities(cls, value: list[str]) -> list[str]:
        return _artist_profile_check("nationalities", value, "Pick countries from the list.")

    @field_validator("residence_country")
    @classmethod
    def _check_residence(cls, value: str | None) -> str | None:
        return _artist_profile_check("residence_country", value, "Pick a country from the list.")

    @field_validator("disciplines")
    @classmethod
    def _check_disciplines(cls, value: list[str]) -> list[str]:
        return _artist_profile_check("disciplines", value, "Pick disciplines from the list.")

    @field_validator("languages")
    @classmethod
    def _check_languages(cls, value: list[str]) -> list[str]:
        return _artist_profile_check("languages", value, "Pick languages from the list.")

    @field_validator("education")
    @classmethod
    def _check_education(cls, value: list[EducationEntry]) -> list[EducationEntry]:
        value = [entry for entry in value if entry.institution.strip()]   # an empty card on the form is no school
        if len(value) > 20:
            raise ValueError("List at most 20 schools.")
        if any(len(e.institution) > 200 or len(e.city or "") > 100 for e in value):
            raise ValueError("Keep names under 200 characters.")
        return _artist_profile_check("education", value, "Each school needs a name; pick countries from the list.")

    @field_validator("degree_field")
    @classmethod
    def _tidy_text(cls, value: str | None) -> str | None:
        value = (value or "").strip()
        if len(value) > 200:
            raise ValueError("Keep this under 200 characters.")
        return value or None


def _artist_profile_check(field: str, value: Any, message: str) -> Any:
    """Runs ArtistProfile's validator for one field; returns its normalised value or raises `message`."""
    try:
        return getattr(ArtistProfile(**{field: value}), field)
    except ValidationError:
        raise ValueError(message) from None


class Evidence(BaseModel):
    quote: str
    citation: str           # "cv.pdf · p. 1 · PERSONAL DETAILS"
    source: str | None = None   # "cv" / "statement" / "portfolio"


class ProfileIn(BaseModel):
    values: ProfileValues
    evidence: dict[str, Evidence] = {}   # field name -> where the accepted value came from
    reviewed_documents: list[uuid.UUID] = []   # the documents whose suggestions the page showed


class Suggestion(BaseModel):
    field: str              # a ProfileValues field name
    value: Any              # in ProfileValues' format
    quote: str              # the line it was read from
    citation: str           # "cv.pdf · p. 1 · EDUCATION"
    note: str | None = None
    source: str             # "cv" / "statement" / "portfolio": shown as "From your CV"


class SourceDocument(BaseModel):
    id: uuid.UUID
    kind: str
    file_name: str


class DocumentSuggestions(BaseModel):
    documents: list[SourceDocument]   # the documents read (not yet reviewed), even those that gave nothing
    items: list[Suggestion]


class ProfileOut(BaseModel):
    values: ProfileValues
    evidence: dict[str, Evidence] = {}
    updated_at: datetime | None = None              # None: never saved
    suggestions: DocumentSuggestions | None = None  # values from documents not reviewed yet


class Option(BaseModel):
    code: str
    name: str


class Options(BaseModel):
    countries: list[Option]
    disciplines: list[str]
    career_stages: list[str]
    languages: list[Option]


def to_artist_profile(values: ProfileValues, today: date | None = None) -> ArtistProfile:
    """What the eligibility engine reads: the same values, with years_active worked out today."""
    year = (today or date.today()).year
    data = values.model_dump(exclude={"active_since"})
    data["years_active"] = None if values.active_since is None else year - values.active_since
    return ArtistProfile(**data)


# -- routes ------------------------------------------------------------------------------------------

KIND_ORDER = ["cv", "statement", "portfolio"]   # the CV first: it states facts, the others describe


def _unreviewed_suggestions(db, user_id: uuid.UUID, profile: Profile | None) -> DocumentSuggestions | None:
    """Values read from the documents the artist hasn't reviewed yet. An empty item list is returned
    too: the page then says nothing was found, instead of saying nothing."""
    reviewed = set(profile.reviewed_documents) if profile is not None else set()
    documents = sorted(db.scalars(select(Document).where(Document.user_id == user_id)),
                       key=lambda d: KIND_ORDER.index(d.kind))
    documents = [d for d in documents if str(d.id) not in reviewed]
    if not documents:
        return None

    items: list[Suggestion] = []
    for document in documents:
        rows = db.scalars(select(KnowledgeChunkRow).where(KnowledgeChunkRow.document_id == document.id)
                          .order_by(KnowledgeChunkRow.index))
        chunks = [Chunk(index=r.index, section=r.section, text=r.text, page=r.page) for r in rows]
        found = (extract_profile(chunks, document.file_name) if document.kind == "cv"
                 else extract_practice(chunks, document.file_name, document.kind))
        taken = {item.field for item in items}
        items += [Suggestion(**vars(s), source=document.kind) for s in found if s.field not in taken]
    return DocumentSuggestions(
        documents=[SourceDocument(id=d.id, kind=d.kind, file_name=d.file_name) for d in documents], items=items)


def _out(db, user_id: uuid.UUID, profile: Profile | None) -> ProfileOut:
    suggestions = _unreviewed_suggestions(db, user_id, profile)
    if profile is None:
        return ProfileOut(values=ProfileValues(), suggestions=suggestions)
    return ProfileOut(values=profile.values, evidence=profile.evidence, updated_at=profile.updated_at,
                      suggestions=suggestions)


@router.get("")
def get_profile(user: CurrentUser, db: DB) -> ProfileOut:
    return _out(db, user.id, db.get(Profile, user.id))


@router.put("")
def save_profile(body: ProfileIn, user: CurrentUser, db: DB) -> ProfileOut:
    values = body.values.model_dump(mode="json")
    # evidence only for fields that exist and have a value: an emptied field loses its quote
    evidence = {name: e.model_dump() for name, e in body.evidence.items()
                if name in ProfileValues.model_fields and values.get(name) not in (None, [])}
    # the documents the page showed suggestions from: only this artist's own documents count
    own = {str(i) for i in db.scalars(select(Document.id).where(Document.id.in_(body.reviewed_documents),
                                                                 Document.user_id == user.id))}
    profile = db.get(Profile, user.id)
    if profile is None:
        profile = Profile(user_id=user.id, values=values, evidence=evidence, reviewed_documents=sorted(own))
        db.add(profile)
    else:
        profile.values, profile.evidence = values, evidence
        profile.reviewed_documents = sorted(set(profile.reviewed_documents) | own)
    db.commit()
    db.refresh(profile)
    return _out(db, user.id, profile)


@router.get("/options")
def options() -> Options:
    countries = sorted((Option(code=code, name=names[0]) for code, names in COUNTRIES.items()),
                       key=lambda option: option.name)
    languages = sorted((Option(code=code, name=names[0]) for code, names in LANGUAGES.items()),
                       key=lambda option: option.name)
    return Options(countries=countries, disciplines=CANONICAL_DISCIPLINES, career_stages=ARTIST_CAREER_STAGES,
                   languages=languages)
