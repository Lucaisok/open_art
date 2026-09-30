"""
OpenArt — apply the round-3 taxonomy revision to the labeled chunks
(ANNOTATION_GUIDELINES.md §6, 2026-09-30 entry; plan in workflow.MD,
"RQ1 improvement plan").

The revision splits the catch-all OTHER_ELIGIBILITY into two new classes,
APPLICANT_TYPE and PRIOR_FUNDING, and re-checks a few boundary rows against
the sharper NONE rule. Every decision lives in
dataset/labels/review/round3_relabel.csv (chunk_id, new_label, reason), so
the change is reviewable row by row; this script only applies it.

Each changed row keeps its previous label and the reason in `notes`. Safe to
re-run: a row whose note already records the revision is left alone.

Run it AFTER scripts/apply_label_review.py whenever that one is re-run:
round 2's review writes its own (9-class) decisions back into the
annotations, which would undo the revision on the 9 rows both touch.

Usage: uv run python scripts/revise_taxonomy.py
"""

import os
from datetime import date

import pandas as pd

from label_chunks import LABELS

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LABELS_DIR = os.path.join(REPO_ROOT, "dataset", "labels")
ANNOTATIONS_PATH = os.path.join(LABELS_DIR, "eligibility_annotations.csv")
RELABEL_PATH = os.path.join(LABELS_DIR, "review", "round3_relabel.csv")
TAG = "taxonomy revision"


def main() -> None:
    ann = pd.read_csv(ANNOTATIONS_PATH, keep_default_na=False)
    relabel = pd.read_csv(RELABEL_PATH, keep_default_na=False)

    bad = relabel[~relabel["new_label"].isin(LABELS)]
    assert bad.empty, f"invalid new_label: {bad['new_label'].unique().tolist()}"
    missing = set(relabel["chunk_id"]) - set(ann["chunk_id"])
    assert not missing, f"relabeled chunks not in annotations: {sorted(missing)[:5]}"

    today = date.today().isoformat()
    applied = already = 0
    for _, d in relabel.iterrows():
        i = ann.index[ann["chunk_id"] == d["chunk_id"]][0]
        if TAG in ann.at[i, "notes"]:
            already += 1
            continue
        old = ann.at[i, "label"]
        note = f"{TAG} {today}: {old} -> {d['new_label']}, {d['reason']}"
        ann.at[i, "notes"] = f"{ann.at[i, 'notes']} | {note}" if ann.at[i, "notes"] else note
        ann.at[i, "label"] = d["new_label"]
        applied += 1

    ann.to_csv(ANNOTATIONS_PATH, index=False, lineterminator="\r\n")
    print(f"{applied} rows relabeled, {already} already done")
    print(ann["label"].value_counts().to_string())


if __name__ == "__main__":
    main()
