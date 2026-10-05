"""Tests for src/matching/matcher.py, with a fake embedder and engine (no model, no data files).
Run with: uv run pytest"""

from datetime import date, datetime, timezone
from importlib.metadata import version

import numpy as np
import pytest

from src.eligibility.engine import Verdict
from src.matching.filters import MatchFilters
from src.matching.index import OpportunityIndex, opportunity_text, text_hash
from src.matching.matcher import Matcher
from src.models.processed_opportunity import ProcessedOpportunity

TODAY = date(2026, 10, 5)


def opp(id, **fields) -> ProcessedOpportunity:
    base = dict(id=id, source="test", source_url=f"https://example.org/{id}", language="en", title=id,
                title_en=id, requirements_text="", requirements_text_en="", processed_at=datetime.now(timezone.utc))
    return ProcessedOpportunity(**{**base, **fields})


class FakeEmbedder:
    """Every query embeds to the x axis, so a call's score is the x component of its vector."""
    def query_embed(self, query):
        yield np.array([1.0, 0.0])


class FakeEngine:
    def __init__(self, statuses):
        self.statuses = statuses

    def evaluate(self, profile, opportunity, today=None):
        return Verdict(opportunity_id=opportunity.id, title=opportunity.title_en, source_url=opportunity.source_url,
                       status=self.statuses.get(opportunity.id, "CHECK"), summary="", items=[])


def matcher(calls, vectors, statuses=None) -> Matcher:
    vectors = np.array(vectors, dtype=np.float32)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    index = OpportunityIndex(ids=[c.id for c in calls], hashes=[text_hash(opportunity_text(c)) for c in calls],
                             vectors=vectors, model="fake", fastembed_version=version("fastembed"))
    return Matcher(opportunities=calls, index=index, engine=FakeEngine(statuses or {}), embedder=FakeEmbedder())


CALLS = [opp("far"), opp("close"), opp("middle")]
VECTORS = [[0.1, 1.0], [1.0, 0.0], [1.0, 1.0]]  # scores ~0.10, 1.00, 0.71


def test_most_similar_first():
    results = matcher(CALLS, VECTORS).search("anything", today=TODAY)
    assert [m.opportunity_id for m in results] == ["close", "middle", "far"]
    assert results[0].score == pytest.approx(1.0)


def test_not_eligible_goes_last_but_is_not_hidden():
    results = matcher(CALLS, VECTORS, {"close": "LIKELY_NOT_ELIGIBLE", "far": "ELIGIBLE"}).search("x", today=TODAY)
    assert [m.opportunity_id for m in results] == ["middle", "far", "close"]  # CHECK and ELIGIBLE share one order
    assert results[-1].verdict.status == "LIKELY_NOT_ELIGIBLE"


def test_filters_run_before_ranking_and_k_limits():
    calls = [opp("closed", deadline_date=date(2026, 1, 1)), opp("open", deadline_date=date(2026, 12, 1)),
             opp("unknown")]
    m = matcher(calls, [[1, 0], [1, 1], [0.1, 1]])
    assert [r.opportunity_id for r in m.search("x", today=TODAY)] == ["open", "unknown"]
    assert [r.opportunity_id for r in m.search("x", filters=MatchFilters(open_only=False), k=1, today=TODAY)] == ["closed"]


def test_nothing_left_after_filters_returns_empty():
    m = matcher([opp("a", opportunity_type_canonical=["Residency"])], [[1, 0]])
    assert m.search("x", filters=MatchFilters(opportunity_types=["Commission"]), today=TODAY) == []


def test_empty_query_is_refused():
    with pytest.raises(ValueError):
        matcher(CALLS, VECTORS).search("   ")


def test_stale_index_is_refused():
    with pytest.raises(RuntimeError, match="new or changed"):
        index = OpportunityIndex(ids=["a"], hashes=["old"], vectors=np.ones((1, 2), dtype=np.float32),
                                 model="fake", fastembed_version=version("fastembed"))
        Matcher(opportunities=[opp("a")], index=index, engine=FakeEngine({}), embedder=FakeEmbedder())
