"""Tests for src/matching/corpus.py and src/matching/index.py (no model download needed). Run with: uv run pytest"""

from datetime import datetime, timezone

import numpy as np
import pytest

from src.matching.corpus import load_opportunities
from src.matching.index import OpportunityIndex, opportunity_text, text_hash
from src.models.processed_opportunity import ProcessedOpportunity


def opp(id="opp", **fields) -> ProcessedOpportunity:
    base = dict(id=id, source="test", source_url="https://example.org/call", language="en",
                title="Titel", title_en="Summer residency", requirements_text="",
                requirements_text_en="Applicants must live in Norway.",
                description_en="Two months in a studio by the sea.", processed_at=datetime.now(timezone.utc))
    return ProcessedOpportunity(**{**base, **fields})


def test_text_is_what_the_call_is_about_not_who_may_apply():
    text = opportunity_text(opp(discipline_en="ceramics", opportunity_type_en="residency"))
    assert text == "Summer residency\nTwo months in a studio by the sea.\nDiscipline: ceramics\nType: residency"
    assert "Norway" not in text  # requirements_text_en is left to the eligibility engine


def test_missing_fields_are_skipped():
    assert opportunity_text(opp(description_en=None)) == "Summer residency"


def test_index_round_trip_and_staleness_check(tmp_path):
    from importlib.metadata import version
    call = opp()
    index = OpportunityIndex(ids=[call.id], hashes=[text_hash(opportunity_text(call))],
                             vectors=np.ones((1, 3), dtype=np.float32), model="m",
                             fastembed_version=version("fastembed"))
    path = str(tmp_path / "index.npz")
    index.save(path)
    loaded = OpportunityIndex.load(path)
    assert loaded.ids == ["opp"] and loaded.model == "m"
    loaded.check_matches([call])  # same text: fine

    with pytest.raises(RuntimeError, match="new or changed"):
        loaded.check_matches([opp(description_en="A different call now.")])
    with pytest.raises(RuntimeError, match="new or changed"):
        loaded.check_matches([call, opp(id="unseen")])


def test_published_corpus_loads():
    opportunities = load_opportunities()
    assert len(opportunities) > 0
    assert all(isinstance(o.discipline_canonical, list) for o in opportunities)
    assert len({o.id for o in opportunities}) == len(opportunities)
