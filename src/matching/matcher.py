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
               never changed: LIKELY_NOT_ELIGIBLE calls go to the bottom with their
               reason, but are not hidden. ELIGIBLE and CHECK are not split into
               tiers, they share one similarity order (nearly every call is CHECK,
               see workflow.MD step 6d, so a tier would carry no information).
"""

from datetime import date

import numpy as np
from pydantic import BaseModel

from src.eligibility.engine import EligibilityEngine, Verdict
from src.eligibility.profile import ArtistProfile
from src.matching.corpus import load_opportunities
from src.matching.filters import MatchFilters, passes
from src.matching.index import OpportunityIndex, embed_query, load_embedder
from src.models.processed_opportunity import ProcessedOpportunity


class Match(BaseModel):
    opportunity_id: str
    title: str
    organisation: str | None
    opportunity_types: list[str]
    deadline: date | None       # None = no deadline stated: the artist should check the call
    source_url: str             # always linked, so the artist can read the call itself
    score: float                # cosine similarity with the query, -1 to 1 (higher = closer)
    verdict: Verdict


class Matcher:
    """Loads the corpus, the index, the engine and the embedding model once; search() is then fast.
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

    def search(self, query: str, profile: ArtistProfile | None = None, filters: MatchFilters | None = None,
               k: int = 10, today: date | None = None) -> list[Match]:
        if not query or not query.strip():
            raise ValueError("query is empty: describe your practice or what you are looking for")
        profile = profile or ArtistProfile()
        filters = filters or MatchFilters()
        today = today or date.today()

        kept = [o for o in self.opportunities if passes(o, filters, today)]
        if not kept:
            return []

        # vectors are normalized, so the dot product is the cosine similarity
        query_vector = embed_query(self.embedder, query)
        scores = self.index.vectors[[self._row[o.id] for o in kept]] @ query_vector

        matches = [
            Match(opportunity_id=o.id, title=o.title_en, organisation=o.organisation,
                  opportunity_types=o.opportunity_type_canonical, deadline=o.deadline_date,
                  source_url=o.source_url, score=round(float(score), 4),
                  verdict=self.engine.evaluate(profile, o, today=today))
            for o, score in zip(kept, scores)
        ]
        # not-eligible last, then most similar first; ties keep corpus order (sort is stable)
        matches.sort(key=lambda m: (m.verdict.status == "LIKELY_NOT_ELIGIBLE", -m.score))
        return matches[:k]
