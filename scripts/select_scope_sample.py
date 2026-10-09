"""
OpenArt — draw the sentences labelled for the scope rules (workflow.MD, "Conclusive verdicts" step 1;
ANNOTATION_GUIDELINES.md §9).

Only sentences that can become an open point are sampled, since those are what scope changes:
check-only classes (CAREER_STAGE, EDUCATION, PRIOR_FUNDING, OTHER_ELIGIBILITY, DISCIPLINE), NONE
sentences flagged by the safety net, and reject-class sentences whose review is a drop. Quotas
130 / 60 / 60, at most 2 sentences per call, no repeated text, fixed seed. The first 100 sentences
(random order) are the held-out test split: the rules in src/eligibility/scope.py are written from the
150 dev sentences only and scored on the test split once.

    -> dataset/labels/scope/scope_sample.csv  (chunk_id, opportunity_id, heading, chunk_text, label, source, split)

Usage: uv run python scripts/select_scope_sample.py
"""

import collections
import os
import random
import sys

import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(REPO_ROOT)

from src.eligibility.engine import CHECK_ONLY_CLASSES, EligibilityEngine, find_review  # noqa: E402

OUT_PATH = os.path.join(REPO_ROOT, "dataset", "labels", "scope", "scope_sample.csv")
PUBLISHED_PATH = os.path.join(REPO_ROOT, "dataset", "opportunities.csv")
SEED = 20261009
QUOTA = {"check_only": 130, "safety_net": 60, "dropped": 60}
TEST_SIZE = 100


def candidates(engine: EligibilityEngine) -> dict:
    """chunk_id -> (opportunity_id, text, heading, source, label) for every sentence that can be an open point."""
    published = set(pd.read_csv(PUBLISHED_PATH, usecols=["id"])["id"])
    found = {}
    for opportunity_id, chunks in engine.chunks_by_opportunity.items():
        if opportunity_id not in published:
            continue
        for c in chunks:
            if c.is_heading or c.label is None or c.chunk_id in found:
                continue
            if c.label == "NONE":
                source = "safety_net" if c.suspected_label else None
            elif c.polarity == "WAIVES":
                source = None
            elif c.label in CHECK_ONLY_CLASSES:
                source = f"check_only:{c.label}"
            else:
                review = find_review(engine.reviews, c.text, c.label)
                source = f"dropped:{c.label}" if review is not None and review.decision == "drop" else None
            if source:
                label = c.suspected_label if c.label == "NONE" else c.label
                found[c.chunk_id] = (opportunity_id, c.text, c.heading, source, label)
    return found


def main() -> None:
    items = list(candidates(EligibilityEngine()).items())
    random.Random(SEED).shuffle(items)
    per_call, taken, seen, picked = collections.Counter(), collections.Counter(), set(), []
    for chunk_id, (opportunity_id, text, heading, source, label) in items:
        family = source.split(":")[0]
        if taken[family] >= QUOTA[family] or per_call[opportunity_id] >= 2 or text in seen:
            continue
        taken[family] += 1
        per_call[opportunity_id] += 1
        seen.add(text)
        picked.append(dict(chunk_id=chunk_id, opportunity_id=opportunity_id, heading=heading or "",
                           chunk_text=text, label=label, source=source))
    sample = pd.DataFrame(picked)
    sample["split"] = ["test" if i < TEST_SIZE else "dev" for i in range(len(sample))]
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    sample.to_csv(OUT_PATH, index=False)
    print(f"{len(sample)} sentences -> {OUT_PATH}: {sample['split'].value_counts().to_dict()}")


if __name__ == "__main__":
    main()
