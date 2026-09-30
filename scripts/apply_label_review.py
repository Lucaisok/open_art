"""
OpenArt — apply the human review of a round's pre-labels and measure
human-vs-LLM agreement (ANNOTATION_GUIDELINES.md §6, 2026-09-29 and
2026-09-30 entries). Written for round 2, reused for round 3 via --round.

Round 2's 386 new rows were pre-labeled by a Claude Code session following
the guidelines. Two review files sit in dataset/labels/review/:

- round2_blind.csv   — a random ~10% of the new rows, WITHOUT the pre-label.
                       The reviewer labels them from scratch; comparing the two
                       gives an honest agreement score (Cohen's kappa), which is
                       what the write-up reports about label quality.
- round2_flagged.csv — every pre-label the session marked as uncertain, WITH
                       the pre-label and the reason it was flagged.

Round 3 uses the same file names with `round3_` (flagged file optional).

Fill `your_label` in both (one of the labels in label_chunks.LABELS, or SKIP to set a chunk aside;
`your_note` is optional), then run this script. It:

1. checks every row is filled in with a valid label,
2. reports agreement on the blind sample (raw % and Cohen's kappa) and lists
   each disagreement,
3. writes the reviewer's label into eligibility_annotations.csv — the human
   decision always wins, including on blind rows — and moves SKIPs to
   skipped_chunks.csv,
4. applies round2_adjudication.csv, if present: reviewer answers that turned
   out to contradict a written rule, settled afterwards (chunk_id,
   final_label, reason). Applied *after* the review and recorded in notes;
   the blind answers themselves are never edited, so the agreement score
   stays a measure of what the reviewer actually said,
5. saves the agreement numbers to dataset/labels/review/round<N>_agreement.json.

Safe to re-run: it recomputes from the review files each time, and rows it
already applied are recognised by their note.

Order matters when re-running older rounds: round 2 rewrites its rows with
9-class labels and drops every note after its own, so re-run
revise_taxonomy.py and then round 3 afterwards.

Usage: uv run python scripts/apply_label_review.py [--round 2|3]
"""

import argparse
import json
import os
from datetime import date

import pandas as pd
from sklearn.metrics import cohen_kappa_score

from label_chunks import LABELS

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LABELS_DIR = os.path.join(REPO_ROOT, "dataset", "labels")
REVIEW_DIR = os.path.join(LABELS_DIR, "review")
ANNOTATIONS_PATH = os.path.join(LABELS_DIR, "eligibility_annotations.csv")
SKIPPED_PATH = os.path.join(LABELS_DIR, "skipped_chunks.csv")
VALID = set(LABELS) | {"SKIP"}


def review_paths(round_no: int) -> dict:
    name = lambda part: os.path.join(REVIEW_DIR, f"round{round_no}_{part}")
    return {"blind": name("blind.csv"), "flagged": name("flagged.csv"),  # flagged optional from round 3
            "agreement": name("agreement.json"), "adjudication": name("adjudication.csv")}  # adjudication optional


def review_tag(round_no: int) -> str:
    # round 2's notes predate --round and say just "human review"; notes are always
    # written as " | <tag>", so "| human review" never matches a round-3 note
    return "human review" if round_no == 2 else f"round{round_no} human review"


def load_review(path: str) -> pd.DataFrame:
    """Read a review file and refuse to continue while any row is blank or invalid."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df["your_label"] = df["your_label"].str.strip().str.upper()
    bad = df[~df["your_label"].isin(VALID)]
    if len(bad):
        raise SystemExit(f"{os.path.basename(path)}: {len(bad)} row(s) with a missing or invalid your_label, "
                         f"e.g. {bad['chunk_id'].head(3).tolist()} - fill them in and re-run")
    return df


def main(round_no: int) -> None:
    paths, tag = review_paths(round_no), review_tag(round_no)
    marker = f"| {tag}"
    blind = load_review(paths["blind"])
    flagged = load_review(paths["flagged"]) if os.path.exists(paths["flagged"]) else blind.iloc[0:0].assign(claude_label="")
    ann = pd.read_csv(ANNOTATIONS_PATH, keep_default_na=False)
    skipped = pd.read_csv(SKIPPED_PATH, keep_default_na=False)

    # the pre-label is still what's in the annotations file, unless an earlier run already
    # overwrote it - in that case recover it from the note this script left behind
    def pre_label(row):
        if marker in row["notes"]:
            this_round = row["notes"].split(marker)[1]  # an earlier round's note has its own "pre-label was"
            return this_round.split("pre-label was ")[1].split(")")[0] if "pre-label was " in this_round else row["label"]
        return row["label"]

    pre = ann.set_index("chunk_id").apply(pre_label, axis=1)
    missing = set(blind["chunk_id"]) - set(pre.index) - set(skipped["chunk_id"])
    assert not missing, f"blind rows not found in annotations: {sorted(missing)[:5]}"

    # ---- 1. agreement on the blind sample (rows the reviewer set aside are left out) ----
    scored = blind[blind["your_label"] != "SKIP"].copy()
    scored["claude_label"] = scored["chunk_id"].map(pre)
    agree = (scored["claude_label"] == scored["your_label"]).mean()
    kappa = cohen_kappa_score(scored["claude_label"], scored["your_label"])
    print(f"Blind sample: {len(scored)} rows scored ({len(blind) - len(scored)} set aside by the reviewer)")
    print(f"  raw agreement: {agree:.1%}   Cohen's kappa: {kappa:.3f}")
    diff = scored[scored["claude_label"] != scored["your_label"]]
    for _, r in diff.iterrows():
        print(f"  - {r['chunk_id']}: claude={r['claude_label']}  you={r['your_label']}  | {r['chunk_text'][:90]}")

    # ---- 2. apply the reviewer's decisions (human wins, blind rows included) ----
    decisions = pd.concat([blind.assign(source="blind"), flagged.assign(source="flagged")])
    today = date.today().isoformat()
    changed = confirmed = moved = 0
    for _, d in decisions.iterrows():
        hit = ann.index[ann["chunk_id"] == d["chunk_id"]]
        if not len(hit):
            continue  # already moved to skipped by an earlier run
        i, old = hit[0], pre[d["chunk_id"]]
        if d["your_label"] == "SKIP":
            skipped.loc[len(skipped)] = {"opportunity_id": ann.at[i, "opportunity_id"], "chunk_id": d["chunk_id"],
                                         "chunk_text": ann.at[i, "chunk_text"],
                                         "reason": f"set aside in {tag} {today}" + (f": {d['your_note']}" if d["your_note"] else "")}
            ann = ann.drop(index=i)
            moved += 1
            continue
        base = ann.at[i, "notes"].split(f" {marker}")[0]  # drop an earlier run's review/adjudication notes
        verdict = "confirmed" if d["your_label"] == old else f"changed (pre-label was {old})"
        ann.at[i, "label"] = d["your_label"]
        ann.at[i, "notes"] = f"{base} {marker} {today}, {d['source']}: {verdict}" + (f" - {d['your_note']}" if d["your_note"] else "")
        changed += d["your_label"] != old
        confirmed += d["your_label"] == old

    # ---- 3. adjudication: reviewer answers that contradicted a written rule, settled afterwards ----
    # Applied after the review, never instead of it: the blind answers above stay untouched,
    # so the agreement score measures what the reviewer actually said.
    adjudicated = 0
    if os.path.exists(paths["adjudication"]):
        for _, d in pd.read_csv(paths["adjudication"], keep_default_na=False).iterrows():
            hit = ann.index[ann["chunk_id"] == d["chunk_id"]]
            assert len(hit), f"adjudicated chunk not in annotations: {d['chunk_id']}"
            i = hit[0]
            ann.at[i, "notes"] += f" | adjudicated {today}: {ann.at[i, 'label']} -> {d['final_label']}, {d['reason']}"
            ann.at[i, "label"] = d["final_label"]
            adjudicated += 1

    ann.to_csv(ANNOTATIONS_PATH, index=False, lineterminator="\r\n")
    skipped.to_csv(SKIPPED_PATH, index=False, lineterminator="\r\n")
    print(f"\nApplied: {confirmed} confirmed, {changed} changed, {moved} moved to skipped_chunks.csv, "
          f"{adjudicated} adjudicated")

    with open(paths["agreement"], "w") as f:
        json.dump({"date": today, "blind_rows_scored": len(scored), "raw_agreement": round(agree, 4),
                   "cohen_kappa": round(kappa, 4), "disagreements": len(diff),
                   "flagged_reviewed": len(flagged), "flagged_changed": int((flagged["your_label"] != flagged["chunk_id"].map(pre)).sum())},
                  f, indent=2)
    print(f"Agreement saved to {paths['agreement']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--round", type=int, default=2, dest="round_no", help="annotation round to apply (default 2)")
    main(parser.parse_args().round_no)
