"""
OpenArt — list the requirement sentences that could reject an artist but have
not been reviewed yet.

Why: on unseen text about 1 in 4 parsed values was too strict (workflow.MD,
step 4), so the engine only rejects on a sentence that is in
dataset/labels/eligibility_constraints_reviewed.csv with decision confirm or
fix. Everything else is shown as CHECK. After new calls are ingested, run this
to see what is waiting for review, review it, and append the rows to that file
(same columns; decision = confirm / fix / drop, with a one-line reason).

A sentence "could reject" when all of these hold (the engine's own gate):
  class AGE / NATIONALITY / RESIDENCE / APPLICANT_TYPE / STUDENT_STATUS,
  classifier confidence >= 0.7, polarity REQUIRES or EXCLUDES, a parsed value.

Usage: uv run python scripts/review_queue.py [--out pending.csv]
"""

import argparse
import json
import os

import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONSTRAINTS_PATH = os.path.join(REPO_ROOT, "data", "processed", "eligibility_constraints.jsonl")
REVIEWED_PATH = os.path.join(REPO_ROOT, "dataset", "labels", "eligibility_constraints_reviewed.csv")

REJECT_CLASSES = {"AGE", "NATIONALITY", "RESIDENCE", "APPLICANT_TYPE", "STUDENT_STATUS"}
REJECT_CONFIDENCE = 0.7


def pending_review() -> pd.DataFrame:
    """One row per distinct sentence that could reject and has no review yet."""
    rows = pd.read_json(CONSTRAINTS_PATH, lines=True)
    could_reject = rows[
        rows["label"].isin(REJECT_CLASSES)
        & (rows["confidence"] >= REJECT_CONFIDENCE)
        & rows["polarity"].isin(["REQUIRES", "EXCLUDES"])
        & rows["value"].notna()
    ]
    reviewed = set(pd.read_csv(REVIEWED_PATH)["chunk_text"]) if os.path.exists(REVIEWED_PATH) else set()
    pending = could_reject[~could_reject["text"].isin(reviewed)]
    return (pending.groupby("text")
            .agg(label=("label", "first"), parsed_polarity=("polarity", "first"),
                 parsed_value=("value", lambda v: json.dumps(v.iloc[0], ensure_ascii=False)),
                 occurrences=("chunk_id", "size"), example_chunk_id=("chunk_id", "first"))
            .reset_index().rename(columns={"text": "chunk_text"}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", help="also write the pending sentences to this CSV")
    args = parser.parse_args()

    pending = pending_review()
    print(f"{len(pending)} sentence(s) could reject an artist and are not reviewed yet")
    for _, row in pending.iterrows():
        print(f"  {row['label']:15s} {row['parsed_polarity']:8s} {row['parsed_value']} | {row['chunk_text'][:100]}")
    if args.out:
        pending.to_csv(args.out, index=False)
        print(f"written to {args.out}")


if __name__ == "__main__":
    main()
