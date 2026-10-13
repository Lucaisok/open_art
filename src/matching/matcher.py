"""
OpenArt — semantic matching: rank open calls by how well they fit what the artist describes.

    matcher = Matcher()
    matcher.search("I make site-specific sound installations about water",
                   profile=ArtistProfile(...), filters=MatchFilters(opportunity_types=["Residency"]))
    -> [Match(score=0.71, verdict=Verdict(status="CHECK", ...)), ...]

Three steps, each kept separate so each stays auditable:
1. filters  - the artist's preferences (src/matching/filters.py), plain field checks
2. ranking  - cosine similarity between the query and each call's embedding (src/matching/index.py)
3. verdict  - the eligibility engine runs on every kept call. Its status is shown,
               never changed by the ranking, and puts each call in one of three groups:
                 fit               ELIGIBLE or CHECK: the artist can probably apply
                 other_discipline  probably for other disciplines (discipline_mismatch)
                 not_eligible      LIKELY_NOT_ELIGIBLE, at the bottom with its reason, never hidden
               Inside a group, the similarity (or deadline) order.

ELIGIBLE is no longer ranked above CHECK (author, 2026-10-13): with that tier first, the 10
calls most similar to an artist were pushed off the first screen by "eligible" calls that are
often eligible only because they state no rules (workflow.MD "Matching evaluation"). ELIGIBLE is
now a badge and an "Eligible only" filter (api/discover.py) instead.
"""

from datetime import date
from typing import Literal

import numpy as np
from pydantic import BaseModel

from src.eligibility.engine import EligibilityEngine, Verdict
from src.eligibility.profile import ArtistProfile

from src.matching.corpus import load_opportunities
from src.matching.explain import Explainer
from src.matching.filters import ANY_DISCIPLINE, MatchFilters, passes
from src.matching.index import OpportunityIndex, embed_query, load_embedder
from src.models.processed_opportunity import ProcessedOpportunity

# the three groups of the list, in display order (see the module docstring)
Group = Literal["fit", "other_discipline", "not_eligible"]
GROUP_ORDER = {"fit": 0, "other_discipline": 1, "not_eligible": 2}


def discipline_mismatch(o: ProcessedOpportunity, verdict: Verdict, profile: ArtistProfile) -> bool:
    """True when the call is probably for other disciplines than the artist's (profile Practice).
    Two signs, either is enough:
      - the call's own rules name a discipline or role the artist doesn't have: the engine's
        DISCIPLINE item is a CHECK with check_kind "discipline_mismatch" ("open to composers")
      - the call's disciplines (canonical) share none with the artist's, and it isn't
        Multidisciplinary. Unknown disciplines are not a mismatch (unknown is kept, as in filters.py).
    Never a verdict: the call stays CHECK or ELIGIBLE, it is only ranked lower (author, 2026-10-13).
    No disciplines in the profile: nothing to compare, never a mismatch."""
    if not profile.disciplines:
        return False
    for item in verdict.items:
        if item.check_kind == "discipline_mismatch" and (item.group_outcome or item.outcome) == "CHECK":
            return True
    call = set(o.discipline_canonical)
    return bool(call) and ANY_DISCIPLINE not in call and not call & set(profile.disciplines)


class Match(BaseModel):
    opportunity_id: str
    title: str
    organisation: str | None
    opportunity_types: list[str]
    deadline: date | None       # None = no deadline stated: the artist should check the call
    source_url: str             # always linked, so the artist can read the call itself
    score: float | None         # cosine similarity with the query, -1 to 1 (higher = closer); None by deadline
    verdict: Verdict
    group: Group                # where the call is listed (fit / other_discipline / not_eligible)


class Matcher:
    """Loads the corpus, the index, the engine and the embedding model once; search() is then fast.
    Building one takes about half a second plus the model, so build ONE per process (the API's
    is api/discover.py get_matcher()), never one per request.
    Each part can be passed in (tests pass small fakes instead of the real files and model)."""

    def __init__(self, opportunities: list[ProcessedOpportunity] | None = None,
                 index: OpportunityIndex | None = None, engine: EligibilityEngine | None = None,
                 embedder=None):
        self.opportunities = opportunities if opportunities is not None else load_opportunities()
        self.index = index or OpportunityIndex.load()
        self.index.check_matches(self.opportunities)  # refuse a stale index rather than score wrongly
        self.engine = engine or EligibilityEngine()
        self.embedder = embedder or load_embedder(self.index.model)
        self._row = {opp_id: i for i, opp_id in enumerate(self.index.ids)}
        # why a call is in an artist's results: the specific words they share (src/matching/explain.py)
        self.explainer = Explainer(self.opportunities)
        self._by_id = {o.id: o for o in self.opportunities}

    def get(self, opportunity_id: str) -> ProcessedOpportunity | None:
        """One call by id (None if there is no such call)."""
        return self._by_id.get(opportunity_id)

    def kept(self, filters: MatchFilters | None = None, today: date | None = None) -> list[ProcessedOpportunity]:
        """The calls the artist's filters keep, in corpus order."""
        filters = filters or MatchFilters()
        today = today or date.today()
        return [o for o in self.opportunities if passes(o, filters, today)]

    def search(self, query: str, profile: ArtistProfile | None = None, filters: MatchFilters | None = None,
               k: int | None = 10, today: date | None = None) -> list[Match]:
        """The kept calls most similar to the query first, in the three groups. k=None: all of them."""
        if not query or not query.strip():
            raise ValueError("query is empty: describe your practice or what you are looking for")
        return self.search_vector(embed_query(self.embedder, query), profile, filters, k, today)

    def search_vector(self, query_vector: np.ndarray, profile: ArtistProfile | None = None,
                      filters: MatchFilters | None = None, k: int | None = 10, today: date | None = None) -> list[Match]:
        """search() with the query already embedded (embed_query): the API keeps each artist's
        query vector, since embedding a whole statement is most of a search's time."""
        today = today or date.today()
        kept = self.kept(filters, today)
        if not kept:
            return []

        # vectors are normalized, so the dot product is the cosine similarity
        scores = self.index.vectors[[self._row[o.id] for o in kept]] @ query_vector

        matches = [self._match(o, float(score), profile, today) for o, score in zip(kept, scores)]
        # by group (fit, other discipline, not eligible), then most similar first; ties keep corpus order
        matches.sort(key=lambda m: (GROUP_ORDER[m.group], -m.score))
        return matches[:k]

    def by_deadline(self, profile: ArtistProfile | None = None, filters: MatchFilters | None = None,
                    k: int | None = 10, today: date | None = None) -> list[Match]:
        """The kept calls in the three groups, nearest deadline first in each (no deadline stated after them).
        Used when there is nothing to rank by: "All calls", or every matching term turned off."""
        today = today or date.today()
        matches = [self._match(o, None, profile, today) for o in self.kept(filters, today)]
        matches.sort(key=lambda m: (GROUP_ORDER[m.group], m.deadline is None, m.deadline or today))
        return matches[:k]

    def _match(self, o: ProcessedOpportunity, score: float | None, profile: ArtistProfile | None,
               today: date) -> Match:
        profile = profile or ArtistProfile()
        verdict = self.engine.evaluate(profile, o, today=today)
        if verdict.status == "LIKELY_NOT_ELIGIBLE":
            group = "not_eligible"
        elif discipline_mismatch(o, verdict, profile):
            group = "other_discipline"
        else:
            group = "fit"
        return Match(opportunity_id=o.id, title=o.title_en, organisation=o.organisation,
                     opportunity_types=o.opportunity_type_canonical, deadline=o.deadline_date,
                     source_url=o.source_url, score=None if score is None else round(score, 4),
                     verdict=verdict, group=group)
