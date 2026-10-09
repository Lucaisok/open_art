"""
OpenArt — list the requirement sentences that could reject an artist but have
not been reviewed yet.

Why: on unseen text about 1 in 4 parsed values was too strict (workflow.MD,
step 4), so the engine only rejects on a sentence that is in
dataset/labels/eligibility_constraints_reviewed.csv with decision confirm or
fix. Everything else is shown as CHECK. After new calls are ingested, run this
to see what is waiting for review, review it, and append the rows to that file
(same columns; decision = confirm / fix / drop, with a one-line reason).

A (sentence, label) "could reject" when its label is AGE / NATIONALITY / RESIDENCE /
APPLICANT_TYPE / STUDENT_STATUS and its polarity isn't WAIVES. Since step 6b
this includes low classifier confidence, UNCLEAR polarity and sentences with no
parsed value: the reviewer confirms the class (or drops the sentence) and
supplies the value and polarity, so the review, not the parsers or the 0.7
gate, is what a reject rests on. Each pending row carries the call's title,
the heading and the sentences around it, because a sentence alone can hide
its scope ("To apply for network funding, you must be ...").

Usage: uv run python scripts/review_queue.py [--out pending.csv]
"""

import argparse
import json
import os

import sys

import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(REPO_ROOT)

# the engine's own gate, imported so the queue and the engine can never disagree
from src.eligibility.engine import (  # noqa: E402
    CONSTRAINTS_PATH,
    REJECT_CLASSES,
    REVIEWED_PATH,
    find_review,
    load_reviews,
)

OPPORTUNITIES_PATH = os.path.join(REPO_ROOT, "data", "processed", "opportunities.jsonl")


def pending_review() -> pd.DataFrame:
    """One row per distinct sentence that could reject and has no review yet, with its context."""
    rows = pd.read_json(CONSTRAINTS_PATH, lines=True).sort_values(["opportunity_id", "chunk_index"])
    # the sentence before / after, within the same call (headings included: they are context).
    # A sentence with several labels has several rows, so the neighbours come from one row per sentence
    sentences = rows.drop_duplicates("chunk_id")[["opportunity_id", "chunk_id", "text"]].copy()
    by_call = sentences.groupby("opportunity_id")["text"]
    sentences["previous_text"], sentences["next_text"] = by_call.shift(1), by_call.shift(-1)
    rows = rows.merge(sentences[["chunk_id", "previous_text", "next_text"]], on="chunk_id")
    titles = pd.read_json(OPPORTUNITIES_PATH, lines=True).set_index("id")["title_en"]
    rows["title"] = rows["opportunity_id"].map(titles)

    could_reject = rows[rows["label"].isin(REJECT_CLASSES) & (rows["polarity"] != "WAIVES") & rows["polarity"].notna()]
    # reviewed per (sentence, label): a second requirement found in an already reviewed sentence still
    # needs its own review. A geo sentence reviewed under the other geo label counts (engine.find_review)
    reviews = load_reviews() if os.path.exists(REVIEWED_PATH) else {}
    done = could_reject.apply(lambda r: find_review(reviews, r["text"], r["label"]) is not None, axis=1)
    pending = could_reject[~done] if len(could_reject) else could_reject
    return (pending.groupby(["text", "label"], as_index=False, sort=False)
            .agg(confidence=("confidence", lambda c: round(c.iloc[0], 2)),
                 parsed_polarity=("polarity", "first"),
                 parsed_value=("value", lambda v: json.dumps(v.iloc[0], ensure_ascii=False) if v.iloc[0] else ""),
                 occurrences=("chunk_id", "size"), example_chunk_id=("chunk_id", "first"),
                 title=("title", "first"), heading=("heading", "first"),
                 previous_text=("previous_text", "first"), next_text=("next_text", "first"))
            .rename(columns={"text": "chunk_text"}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", help="also write the pending sentences to this CSV")
    args = parser.parse_args()

    pending = pending_review()
    print(f"{len(pending)} sentence(s) could reject an artist and are not reviewed yet")
    for _, row in pending.iterrows():
        print(f"  {row['label']:15s} {row['parsed_polarity']:9s} {row['parsed_value'] or '-'} | {row['chunk_text'][:100]}")
    if args.out:
        pending.to_csv(args.out, index=False)
        print(f"written to {args.out}")


if __name__ == "__main__":
    main()
