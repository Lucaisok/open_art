"""
OpenArt — how well do the scope rules (src/eligibility/scope.py) agree with the labelled sample?
(workflow.MD, "Conclusive verdicts" step 1.)

The rules were written from the dev split only; the test split is scored to report them. What
matters most is the dangerous error: a sentence labelled APPLICANT that the rules call something
else, since the engine would then hide a real condition.

Usage: uv run python scripts/evaluate_scope.py [dev|test]   (default: both)
"""

import os
import sys

import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(REPO_ROOT)

from src.eligibility.scope import APPLICANT, scope  # noqa: E402

SCOPE_DIR = os.path.join(REPO_ROOT, "dataset", "labels", "scope")


def evaluate(split: str, show_errors: bool = True) -> None:
    sample = pd.read_csv(os.path.join(SCOPE_DIR, "scope_sample.csv"))
    labels = pd.read_csv(os.path.join(SCOPE_DIR, f"scope_labels_{split}.csv"))
    rows = labels.merge(sample, on="chunk_id")
    rows["predicted"] = [scope(r.chunk_text, r.heading if isinstance(r.heading, str) else None)
                         for r in rows.itertuples()]
    gold_other, pred_other = rows.scope != APPLICANT, rows.predicted != APPLICANT
    dangerous = rows[~gold_other & pred_other]
    print(f"== {split}: {len(rows)} sentences")
    print(f"exact scope agreement            {(rows.scope == rows.predicted).mean():.0%}")
    print(f"non-applicant found (recall)     {(gold_other & pred_other).sum()} / {gold_other.sum()}")
    print(f"non-applicant precision          {(gold_other & pred_other).sum()} / {pred_other.sum()}")
    print(f"APPLICANT hidden (dangerous)     {len(dangerous)} / {(~gold_other).sum()}")
    print(pd.crosstab(rows.scope, rows.predicted).to_string(), "\n")
    if show_errors:
        for r in rows[rows.scope != rows.predicted].itertuples():
            print(f"  gold {r.scope:16s} pred {r.predicted:16s} {r.chunk_text[:130]}")


if __name__ == "__main__":
    for split in sys.argv[1:] or ["dev", "test"]:
        evaluate(split)
