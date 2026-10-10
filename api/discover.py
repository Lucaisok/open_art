"""
Discover and the opportunity page (web app step 5).

    GET  /api/discover/options          the filter lists (types, disciplines, countries)
    POST /api/discover/search           filters -> up to 30 calls, each with its verdict
    GET  /api/opportunities/{id}        one call's facts and its full verdict, every sentence quoted

Verdicts use the artist's SAVED profile only (to_artist_profile), never unsaved form values or
unreviewed document suggestions: nothing the artist hasn't saved decides anything. Checking every
open call takes ~50 ms, so verdicts are worked out on each request, not stored. Searches are not
stored either.

"Matched to you" ranks by the artist's own words: from each of their documents (statement, portfolio,
CV), the passages about their practice and wishes (suggest_query, RAG step 4), averaged; no
documents -> nearest deadline. Short matching terms were tried instead and ranked worse
(workflow.MD, step 5b).

The corpus, the index, the engine and the model are loaded once per process (get_matcher), sharing
the embedding model already loaded for the artist's documents: one copy in memory, not two.
"""

import uuid
from datetime import date
from functools import lru_cache
from typing import Literal

import numpy as np

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select

from api.auth import DB, CurrentUser
from api.knowledge_base import PgKnowledgeBase, get_embedder
from api.models import Document, Profile
from api.profile import ProfileValues, to_artist_profile
from src.eligibility.engine import TOPIC, Item, Status, Verdict
from src.eligibility.profile import ArtistProfile
from src.matching.filters import ANY_COUNTRY, NOT_FUNDING, MatchFilters, is_funded
from src.matching.index import EMBEDDING_MODEL, OpportunityIndex, embed_query
from src.matching.matcher import Match, Matcher
from src.models.processed_opportunity import FundingComponent, ProcessedOpportunity
from src.processing.canonicalize import CANONICAL_DISCIPLINES, CANONICAL_OPPORTUNITY_TYPES
from src.rag.query_suggestion import suggest_query

router = APIRouter(tags=["discover"])

MAX_RESULTS = 30
RANKING_KINDS = ["statement", "portfolio", "cv"]   # all of them rank "Matched to you" (listed in this order)

# document id -> its embedded ranking query (None: nothing to rank by). Building one takes ~1 s
# (retrieval + embedding ~2,000 characters), so it is done once per document, not per search. A new
# upload has a new id, so a replaced document is never ranked by its old text. Kept in memory only.
_query_vectors: dict[uuid.UUID, np.ndarray | None] = {}
MAX_CACHED_QUERIES = 1000


@lru_cache
def get_matcher() -> Matcher:
    """The one Matcher of this process, built on first use (the tests replace it with a small one)."""
    index = OpportunityIndex.load()
    # the shared model is EMBEDDING_MODEL: an index built with another one needs its own
    embedder = get_embedder() if index.model == EMBEDDING_MODEL else None
    return Matcher(index=index, embedder=embedder)


def saved_profile(db, user_id) -> tuple[ArtistProfile, bool]:
    """The profile the engine reads, and whether the artist has saved anything in it.
    Never saved, or saved empty: an empty profile (the page then says so)."""
    row = db.get(Profile, user_id)
    if row is None:
        return ArtistProfile(), False
    values = ProfileValues.model_validate(row.values)
    filled = any(v not in (None, []) for v in values.model_dump().values())
    return to_artist_profile(values), filled


def _place(o: ProcessedOpportunity) -> tuple[str | None, list[str]]:
    """City and countries as shown. The countries come from the controlled vocabulary: the literal
    translation (country_en) can read "of the Slovak Republic"."""
    countries = [c for c in o.country_canonical if c != ANY_COUNTRY]
    if not countries and ANY_COUNTRY in o.country_canonical:
        countries = ["International"]
    return o.city_en, countries


# -- options -----------------------------------------------------------------------------------------

class DiscoverOptions(BaseModel):
    types: list[str]
    disciplines: list[str]
    countries: list[str]        # the countries calls take place in (International calls match any)


@router.get("/api/discover/options")
def options(user: CurrentUser) -> DiscoverOptions:
    countries = {c for o in get_matcher().opportunities for c in o.country_canonical if c != ANY_COUNTRY}
    return DiscoverOptions(types=CANONICAL_OPPORTUNITY_TYPES, disciplines=CANONICAL_DISCIPLINES,
                           countries=sorted(countries))


# -- search ------------------------------------------------------------------------------------------

class SearchIn(BaseModel):
    mode: Literal["matched", "all"] = "matched"
    text: str = Field("", max_length=200)          # the search box: title, organisation, place, type
    types: list[str] = []
    disciplines: list[str] = []
    country: str | None = None
    funded_only: bool = False
    no_fee: bool = False


class ResultOut(BaseModel):
    id: str
    title: str
    organisation: str | None
    types: list[str]
    city: str | None
    countries: list[str]
    deadline: date | None
    status: Status              # ELIGIBLE / CHECK / LIKELY_NOT_ELIGIBLE
    reason: str                 # the verdict's one-line summary
    score: float | None         # None when ordered by deadline


class SearchOut(BaseModel):
    results: list[ResultOut]    # at most MAX_RESULTS; not-eligible calls last, never hidden
    total: int                  # every call the filters keep
    order: Literal["match", "deadline"]
    ranked_by: list[str]        # the documents "Matched to you" ranks by (file names); []: none
    profile_filled: bool        # False: the page asks the artist to fill in their profile


def _result(match: Match, o: ProcessedOpportunity) -> ResultOut:
    city, countries = _place(o)
    return ResultOut(id=o.id, title=o.title_en, organisation=o.organisation, types=o.opportunity_type_canonical,
                     city=city, countries=countries, deadline=o.deadline_date, status=match.verdict.status,
                     reason=match.verdict.summary, score=match.score)


@router.post("/api/discover/search")
def search(body: SearchIn, user: CurrentUser, db: DB) -> SearchOut:
    try:
        filters = MatchFilters(opportunity_types=body.types, disciplines=body.disciplines,
                               countries=[body.country] if body.country else [],
                               funded_only=body.funded_only, no_fee_only=body.no_fee, text=body.text)
    except ValidationError as error:
        raise HTTPException(422, "Unknown filter value.") from error

    matcher = get_matcher()
    profile, filled = saved_profile(db, user.id)
    ranked_by, vector = ranking_vector(db, user.id, matcher) if body.mode == "matched" else ([], None)
    if vector is not None:
        matches, order = matcher.search_vector(vector, profile, filters, k=MAX_RESULTS), "match"
    else:
        matches, order = matcher.by_deadline(profile, filters, k=MAX_RESULTS), "deadline"

    return SearchOut(results=[_result(m, matcher.get(m.opportunity_id)) for m in matches],
                     total=len(matcher.kept(filters)), order=order, ranked_by=ranked_by, profile_filled=filled)


def document_vector(db, user_id: uuid.UUID, document: Document, matcher: Matcher) -> np.ndarray | None:
    """One document's embedded query: its passages about the practice and wishes, in the artist's
    own words (suggest_query, RAG step 4). None when it gives no query. Cached by document id."""
    if document.id not in _query_vectors:
        query = suggest_query(PgKnowledgeBase(db, user_id), documents=[document.file_name]).query
        if len(_query_vectors) >= MAX_CACHED_QUERIES:
            _query_vectors.pop(next(iter(_query_vectors)))   # the oldest entry
        _query_vectors[document.id] = embed_query(matcher.embedder, query) if query else None
    return _query_vectors[document.id]


def ranking_vector(db, user_id: uuid.UUID, matcher: Matcher) -> tuple[list[str], np.ndarray | None]:
    """What "Matched to you" ranks by: every document the artist uploaded (statement, portfolio,
    CV), each embedded on its own and averaged, so each counts equally and none is cut off by the
    model's 512-token limit (workflow.MD step 5b: Ilka 6 -> 10 of 10, Tomás 9 -> 9).
    Returns (file names, vector); ([], None) when no document gives a query."""
    documents = sorted(db.scalars(select(Document).where(Document.user_id == user_id)),
                       key=lambda d: RANKING_KINDS.index(d.kind))
    used = [(d.file_name, v) for d in documents if (v := document_vector(db, user_id, d, matcher)) is not None]
    if not used:
        return [], None
    mean = np.mean([v for _, v in used], axis=0)
    return [name for name, _ in used], mean / np.linalg.norm(mean)   # back to length 1: a cosine again


# -- one opportunity ---------------------------------------------------------------------------------

class RequirementOut(BaseModel):
    outcome: Literal["FAIL", "CHECK", "PASS"]  # "Doesn't pass" / "To check" / "Passes"
    topic: str                  # "Age", "Residence", ...
    reason: str


class SentenceOut(BaseModel):
    quote: str                  # the call's own sentence, verbatim, shown once
    requirements: list[RequirementOut]  # one per requirement the sentence states (multi-label)


class VerdictOut(BaseModel):
    status: Status
    summary: str
    fails: int                  # how many rows don't pass / need a check / pass
    checks: int
    passes: int
    sentences: list[SentenceOut]  # failing sentences first (if any), then passing, then to check
    # sentences that aren't about who can apply (scope, src/eligibility/scope.py): never a check
    commitments: list[str]      # "What you'd commit to": what a selected artist has to do
    about_project: list[str]    # "About the project": project conditions, preferences, notes


class OpportunityOut(BaseModel):
    id: str
    title: str
    organisation: str | None
    types: list[str]
    city: str | None
    countries: list[str]
    deadline: date | None
    funding: str                # "EUR 1,300 per month + accommodation/housing", or "Not stated"
    funded: bool
    fee: str                    # "None", "EUR 25", "Yes, amount not stated" or "Not stated"
    description: str | None     # English
    source_url: str             # always linked: the artist reads the call itself before applying
    verdict: VerdictOut
    profile_filled: bool


def _amount(c: FundingComponent) -> str:
    """"EUR 1,300 per month", "EUR 500–2,000"."""
    amount = f"{c.currency} {c.amount_min:,.0f}"
    if c.amount_max is not None and c.amount_max != c.amount_min:
        amount += f"–{c.amount_max:,.0f}"
    if c.period and c.period != "one-time":
        amount += f" {c.period}"
    return amount


def funding_label(o: ProcessedOpportunity) -> str:
    """The funding in English, from the extracted components (the raw text is often in another
    language). Amounts first, then support without a figure. Falls back to the raw text."""
    if o.funding_components:
        with_amount = [_amount(c) for c in o.funding_components if c.amount_min is not None]
        # support without a figure: money or support in kind before mentoring and fee waivers
        without = sorted({c.category for c in o.funding_components if c.amount_min is None},
                         key=lambda category: (category in NOT_FUNDING, category))
        label = " + ".join(with_amount + [category.lower() for category in without])
        return label[0].upper() + label[1:]
    return o.funding or "Not stated"


def fee_label(o: ProcessedOpportunity) -> str:
    if o.application_fee_has_fee is None:
        return "Not stated"
    if not o.application_fee_has_fee:
        return "None"
    if o.application_fee_amount_min is None:
        return "Yes, amount not stated"
    return f"{o.application_fee_currency or ''} {o.application_fee_amount_min:,.0f}".strip()


def _outcome(item: Item) -> Literal["FAIL", "CHECK", "PASS"]:
    """A sentence in an OR group ("citizens of X or residents of Y") counts as its group's outcome;
    "no restriction" is shown as a pass."""
    outcome = item.group_outcome or item.outcome
    return "PASS" if outcome == "NO_RESTRICTION" else outcome


# CHECK rows that only say "read it": several of them in one sentence become one row. The other kinds
# (missing_profile_field, uncertain_match, narrower_set, discipline_mismatch) say something specific
# about the artist, so they keep their own row.
GENERIC_CHECKS = {"check_only_class", "safety_net", "not_reviewed", "unreadable", "dropped"}
# passes on top; failures above everything when there are any (author, 2026-10-09)
RANK = {"FAIL": 0, "PASS": 1, "CHECK": 2}


def _rows(items: list[Item]) -> list[RequirementOut]:
    """One row per requirement of a sentence, generic checks merged into one row."""
    rows = [RequirementOut(outcome=_outcome(item), topic=TOPIC[item.label].capitalize(), reason=item.reason)
            for item in items if not (_outcome(item) == "CHECK" and item.check_kind in GENERIC_CHECKS)]
    generic = [item for item in items if _outcome(item) == "CHECK" and item.check_kind in GENERIC_CHECKS]
    if len(generic) == 1:
        rows.append(RequirementOut(outcome="CHECK", topic=TOPIC[generic[0].label].capitalize(),
                                   reason=generic[0].reason))
    elif generic:
        topics = list(dict.fromkeys(TOPIC[item.label] for item in generic))
        rows.append(RequirementOut(outcome="CHECK", topic=", ".join(topics).capitalize(),
                                   reason="the app can't check this for you: read it and make sure you meet it"))
    return sorted(rows, key=lambda row: RANK[row.outcome])


def verdict_out(verdict: Verdict) -> VerdictOut:
    """Every sentence the engine found, quoted once, with each requirement it states and what it
    means for the artist. A sentence can state several (multi-label: "over 18 ... and reside in
    Senegal"), so the page shows the sentence once with a row per requirement, instead of repeating it."""
    by_sentence: dict[str, list[Item]] = {}
    commitments: dict[str, None] = {}   # dicts as ordered sets: a sentence with two labels is listed once
    about_project: dict[str, None] = {}
    for item in verdict.items:  # in call order
        if item.outcome == "INFO":
            (commitments if item.scope == "OBLIGATION" else about_project)[item.text] = None
        else:
            by_sentence.setdefault(item.chunk_id, []).append(item)

    sentences = [SentenceOut(quote=items[0].text, requirements=_rows(items)) for items in by_sentence.values()]
    sentences.sort(key=lambda sentence: RANK[sentence.requirements[0].outcome])  # stable: call order kept
    outcomes = [row.outcome for sentence in sentences for row in sentence.requirements]
    return VerdictOut(status=verdict.status, summary=verdict.summary, fails=outcomes.count("FAIL"),
                      checks=outcomes.count("CHECK"), passes=outcomes.count("PASS"), sentences=sentences,
                      commitments=list(commitments), about_project=[t for t in about_project if t not in commitments])


@router.get("/api/opportunities/{opportunity_id}")
def opportunity(opportunity_id: str, user: CurrentUser, db: DB) -> OpportunityOut:
    matcher = get_matcher()
    o = matcher.get(opportunity_id)
    if o is None:
        raise HTTPException(404, "No such call.")
    profile, filled = saved_profile(db, user.id)
    city, countries = _place(o)
    return OpportunityOut(
        id=o.id, title=o.title_en, organisation=o.organisation, types=o.opportunity_type_canonical,
        city=city, countries=countries, deadline=o.deadline_date, funding=funding_label(o), funded=is_funded(o),
        fee=fee_label(o), description=o.description_en, source_url=o.source_url,
        verdict=verdict_out(matcher.engine.evaluate(profile, o)), profile_filled=filled)
