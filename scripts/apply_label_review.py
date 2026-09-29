"""
OpenArt — apply the human review of round-2 pre-labels and measure
human-vs-LLM agreement (ANNOTATION_GUIDELINES.md §6, 2026-09-29 entry).

Round 2's 386 new rows were pre-labeled by a Claude Code session following
the guidelines. Two review files sit in dataset/labels/review/:

- round2_blind.csv   — a random ~10% of the new rows, WITHOUT the pre-label.
                       The reviewer labels them from scratch; comparing the two
                       gives an honest agreement score (Cohen's kappa), which is
                       what the write-up reports about label quality.
- round2_flagged.csv — every pre-label the session marked as uncertain, WITH
                       the pre-label and the reason it was flagged.

Fill `your_label` in both (one of the 9 labels, or SKIP to set a chunk aside;
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
5. saves the agreement numbers to dataset/labels/review/round2_agreement.json.

Safe to re-run: it recomputes from the review files each time, and rows it
already applied are recognised by their note.

Usage: uv run python scripts/apply_label_review.py
"""

import json
import os
from datetime import date

import pandas as pd
from sklearn.metrics import cohen_kappa_score

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LABELS_DIR = os.path.join(REPO_ROOT, "dataset", "labels")
REVIEW_DIR = os.path.join(LABELS_DIR, "review")
ANNOTATIONS_PATH = os.path.join(LABELS_DIR, "eligibility_annotations.csv")
SKIPPED_PATH = os.path.join(LABELS_DIR, "skipped_chunks.csv")
BLIND_PATH = os.path.join(REVIEW_DIR, "round2_blind.csv")
FLAGGED_PATH = os.path.join(REVIEW_DIR, "round2_flagged.csv")
AGREEMENT_PATH = os.path.join(REVIEW_DIR, "round2_agreement.json")
ADJUDICATION_PATH = os.path.join(REVIEW_DIR, "round2_adjudication.csv")  # optional

VALID = {"RESIDENCE", "NATIONALITY", "AGE", "DISCIPLINE", "CAREER_STAGE", "EDUCATION",
         "STUDENT_STATUS", "OTHER_ELIGIBILITY", "NONE", "SKIP"}
REVIEW_TAG = "human review"


def load_review(path: str) -> pd.DataFrame:
    """Read a review file and refuse to continue while any row is blank or invalid."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df["your_label"] = df["your_label"].str.strip().str.upper()
    bad = df[~df["your_label"].isin(VALID)]
    if len(bad):
        raise SystemExit(f"{os.path.basename(path)}: {len(bad)} row(s) with a missing or invalid your_label, "
                         f"e.g. {bad['chunk_id'].head(3).tolist()} - fill them in and re-run")
    return df


def main() -> None:
    blind, flagged = load_review(BLIND_PATH), load_review(FLAGGED_PATH)
    ann = pd.read_csv(ANNOTATIONS_PATH, keep_default_na=False)
    skipped = pd.read_csv(SKIPPED_PATH, keep_default_na=False)

    # the pre-label is still what's in the annotations file, unless an earlier run already
    # overwrote it - in that case recover it from the note this script left behind
    def pre_label(row):
        if REVIEW_TAG in row["notes"]:
            return row["notes"].split("pre-label was ")[1].split(")")[0] if "pre-label was " in row["notes"] else row["label"]
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
                                         "reason": f"set aside in {REVIEW_TAG} {today}" + (f": {d['your_note']}" if d["your_note"] else "")}
            ann = ann.drop(index=i)
            moved += 1
            continue
        base = ann.at[i, "notes"].split(f" | {REVIEW_TAG}")[0]  # drop an earlier run's review/adjudication notes
        verdict = "confirmed" if d["your_label"] == old else f"changed (pre-label was {old})"
        ann.at[i, "label"] = d["your_label"]
        ann.at[i, "notes"] = f"{base} | {REVIEW_TAG} {today}, {d['source']}: {verdict}" + (f" - {d['your_note']}" if d["your_note"] else "")
        changed += d["your_label"] != old
        confirmed += d["your_label"] == old

    # ---- 3. adjudication: reviewer answers that contradicted a written rule, settled afterwards ----
    # Applied after the review, never instead of it: the blind answers above stay untouched,
    # so the agreement score measures what the reviewer actually said.
    adjudicated = 0
    if os.path.exists(ADJUDICATION_PATH):
        for _, d in pd.read_csv(ADJUDICATION_PATH, keep_default_na=False).iterrows():
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

    with open(AGREEMENT_PATH, "w") as f:
        json.dump({"date": today, "blind_rows_scored": len(scored), "raw_agreement": round(agree, 4),
                   "cohen_kappa": round(kappa, 4), "disagreements": len(diff),
                   "flagged_reviewed": len(flagged), "flagged_changed": int((flagged["your_label"] != flagged["chunk_id"].map(pre)).sum())},
                  f, indent=2)
    print(f"Agreement saved to {AGREEMENT_PATH}")


if __name__ == "__main__":
    main()
