"""
OpenArt — round 7 reviews: the requirement sentences of the re-extracted corpus that have no review
(workflow.MD, "Step 3 — combined re-extraction", re-review).

Reviews are keyed by the exact sentence text (engine.load_reviews). The combined re-extraction copies
the calls' rules with different line breaks and list splits, so most sentences lost their review and
fell back to "not checked yet". This round reviews them again, in two kinds of batch:

- full   sentences in a class the engine may reject on (AGE, NATIONALITY, RESIDENCE, APPLICANT_TYPE,
         STUDENT_STATUS) with no review: scope, then fix (value + polarity) or drop, as in
         ANNOTATION_GUIDELINES.md §8-§10. The same queue as scripts/review_queue.py.
- scope  check-only (DISCIPLINE, CAREER_STAGE, EDUCATION, PRIOR_FUNDING, OTHER_ELIGIBILITY) and
         safety-net sentences with no review that the scope rules keep as APPLICANT: only the §9 scope.
         These are the false requirements the author wants gone; an APPLICANT one stays a check.

    queue  write dataset/labels/review/round7/{full,scope}_batch<N>.csv (with the call's title, the
           heading and the sentences around each one)
    apply  check every reviewed row (*_reviewed.csv in the same folder, same checks as round 5) and
           append it to dataset/labels/eligibility_constraints_reviewed.csv. A scope-only APPLICANT
           row is not written: it changes nothing.

Usage:
    uv run python scripts/review_round7.py queue
    uv run python scripts/review_round7.py apply
    uv run python scripts/review_round7.py queue --prefix pass2_   # a later pass, own batch files
    uv run python scripts/review_round7.py queue --round 8         # a later round, own folder and label

Round 8 (2026-10-13) reviews the calls added from the author's hand-collected list
(workflow.MD, "Adding a hand-collected list of calls").
"""

import argparse
import csv
import glob
import json
import os
import sys
from datetime import date

import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(REPO_ROOT)
sys.path.append(os.path.join(REPO_ROOT, "scripts"))

from apply_structured_reviews import check_row  # noqa: E402
from review_queue import OPPORTUNITIES_PATH, pending_review  # noqa: E402

from src.eligibility.engine import CHECK_ONLY_CLASSES, CONSTRAINTS_PATH, REVIEWED_PATH, load_reviews  # noqa: E402
from src.eligibility.scope import APPLICANT, scope as sentence_scope  # noqa: E402

ROUND_DIR = os.path.join(REPO_ROOT, "dataset", "labels", "review", "round7")
BATCH_SIZE = 60
REVIEWED_BY = "Claude Code (claude-opus-5-5) round 7 review of the re-extracted corpus, no human spot check"
REVIEWED_ON = "2026-10-12"


def scope_queue(full_texts: set[str]) -> pd.DataFrame:
    """One row per distinct check-only / safety-net sentence with no review that the rules keep APPLICANT."""
    rows = pd.read_json(CONSTRAINTS_PATH, lines=True).sort_values(["opportunity_id", "chunk_index"])
    sentences = rows.drop_duplicates("chunk_id")[["opportunity_id", "chunk_id", "text"]].copy()
    by_call = sentences.groupby("opportunity_id")["text"]
    sentences["previous_text"], sentences["next_text"] = by_call.shift(1), by_call.shift(-1)
    rows = rows.merge(sentences[["chunk_id", "previous_text", "next_text"]], on="chunk_id")
    rows["title"] = rows["opportunity_id"].map(pd.read_json(OPPORTUNITIES_PATH, lines=True).set_index("id")["title_en"])

    # the label the engine shows: the class, or the safety net's suspected class for a flagged NONE
    suspected = rows["suspected_label"] if "suspected_label" in rows else pd.Series(None, index=rows.index)
    rows["shown_label"] = rows["label"].where(rows["label"] != "NONE", suspected)
    reviewed_texts = {text for text, _ in load_reviews()}
    # sentences already read in any round: a scope-only APPLICANT answer is not written to the
    # reviews file (it changes nothing), so it is only remembered in the round folders
    for path in glob.glob(os.path.join(REPO_ROOT, "dataset", "labels", "review", "round*", "*_reviewed.csv")):
        reviewed_texts |= set(pd.read_csv(path, keep_default_na=False)["chunk_text"])
    # check-only sentences, and every safety-net sentence: one whose suspected class could reject is
    # in no other queue (pending_review() only takes classified sentences), found after the first pass
    safety_net = (rows["label"] == "NONE") & rows["shown_label"].notna()
    keep = ((rows["shown_label"].isin(CHECK_ONLY_CLASSES) | safety_net) & (rows["polarity"] != "WAIVES")
            & ~rows["text"].isin(reviewed_texts) & ~rows["text"].isin(full_texts)
            & ~rows["is_heading"].fillna(False).astype(bool))
    rows = rows[keep]
    rows = rows[[sentence_scope(t, h if isinstance(h, str) else None) == APPLICANT  # NaN = no heading
                 for t, h in zip(rows["text"], rows["heading"])]]
    return (rows.groupby("text", as_index=False, sort=False)
            .agg(label=("shown_label", "first"), occurrences=("chunk_id", "size"),
                 example_chunk_id=("chunk_id", "first"), title=("title", "first"), heading=("heading", "first"),
                 previous_text=("previous_text", "first"), next_text=("next_text", "first"))
            .rename(columns={"text": "chunk_text"}))


def write_batches(frame: pd.DataFrame, kind: str) -> int:
    for start in range(0, len(frame), BATCH_SIZE):
        frame.iloc[start:start + BATCH_SIZE].to_csv(
            os.path.join(ROUND_DIR, f"{kind}_batch{start // BATCH_SIZE + 1}.csv"), index=False)
    return -(-len(frame) // BATCH_SIZE)


def queue(prefix: str) -> None:
    """prefix names a later pass ("pass2_"), so its batches don't overwrite applied ones."""
    os.makedirs(ROUND_DIR, exist_ok=True)
    full = pending_review()
    scope = scope_queue(set(full["chunk_text"]))
    print(f"full:  {len(full)} sentence/label rows -> {write_batches(full, prefix + 'full')} batch(es)")
    print(f"scope: {len(scope)} sentences -> {write_batches(scope, prefix + 'scope')} batch(es)  in {ROUND_DIR}")


def apply(prefix: str) -> None:
    queued = {}
    for path in glob.glob(os.path.join(ROUND_DIR, f"{prefix}*_batch*.csv")):
        if not path.endswith("_reviewed.csv"):
            for row in pd.read_csv(path, keep_default_na=False).to_dict("records"):
                queued[(row["chunk_text"], row["label"])] = row
    new_rows, kept_applicant = [], 0
    for path in sorted(glob.glob(os.path.join(ROUND_DIR, f"{prefix}*_reviewed.csv"))):
        if not prefix and os.path.basename(path).startswith("pass"):
            continue   # a later pass, applied with its own --prefix
        with open(path, encoding="utf-8", newline="") as f:
            for number, row in enumerate(csv.DictReader(f), start=2):
                where = f"{os.path.basename(path)} line {number}"
                source = queued.get((row["chunk_text"], row["label"]))
                if source is None:
                    raise ValueError(f"{where}: not a queued (sentence, label): {row['chunk_text'][:60]!r}")
                if "scope_batch" in os.path.basename(path) and row["scope"] == APPLICANT:
                    kept_applicant += 1   # stays a check, as before: nothing to write
                    continue
                row = {"polarity": "", "value": "", "applies_to": "", **row}
                check_row(row, where)
                new_rows.append({
                    "chunk_text": row["chunk_text"], "label": row["label"],
                    "parsed_polarity": source.get("parsed_polarity", ""), "parsed_value": source.get("parsed_value", ""),
                    "decision": row["decision"], "polarity": row["polarity"], "value": row["value"],
                    "scope": "" if row["scope"] == APPLICANT else row["scope"], "applies_to": row["applies_to"],
                    "reason": row["reason"], "occurrences": source.get("occurrences", ""),
                    "example_chunk_id": source.get("example_chunk_id", ""),
                    "reviewed_by": REVIEWED_BY, "reviewed_on": REVIEWED_ON})
    with open(REVIEWED_PATH, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fields, existing = reader.fieldnames, {(r["chunk_text"], r["label"]) for r in reader}
    if clash := [r["chunk_text"][:60] for r in new_rows if (r["chunk_text"], r["label"]) in existing]:
        raise ValueError(f"{len(clash)} row(s) already reviewed, e.g. {clash[0]!r}")
    with open(REVIEWED_PATH, "a", encoding="utf-8", newline="") as f:
        csv.DictWriter(f, fieldnames=fields).writerows(new_rows)
    print(f"{len(new_rows)} review rows appended to {os.path.relpath(REVIEWED_PATH, REPO_ROOT)}; "
          f"{kept_applicant} scope-only sentences confirmed APPLICANT (unchanged)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stage", choices=["queue", "apply"])
    parser.add_argument("--prefix", default="", help='a later pass, e.g. "pass2_" (its own batch files)')
    parser.add_argument("--round", type=int, default=7, help="review round: its folder and reviewed_by label")
    args = parser.parse_args()
    if args.round != 7:
        ROUND_DIR = os.path.join(REPO_ROOT, "dataset", "labels", "review", f"round{args.round}")
        REVIEWED_BY = f"Claude Code (claude-opus-5-5) round {args.round} review of newly added calls, no human spot check"
        REVIEWED_ON = date.today().isoformat()
    {"queue": queue, "apply": apply}[args.stage](args.prefix)
