"""
OpenArt — build the multi-label RQ1 dataset (round 4, ANNOTATION_GUIDELINES.md §7).

Rounds 1-3 gave every chunk ONE label, and a sentence stating two independent
requirements was split by hand into parts (chunk ids ending in a, b, ...).
The product never splits a sentence like that: it classifies whole sentences
(src/eligibility/chunking.py). So a sentence such as "Applicants must be over
18, ... and reside in Senegal" reached the single-label model whole, got AGE,
and its residence requirement was lost. Round 4 moves to one label SET per
sentence, built here from four sources:

  1. single      every round 1-3 row that was not split: its one label
  2. relabel     dataset/labels/review/round4_multilabel.csv: rows of (1) whose
                 sentence also states another requirement (or explicitly waives
                 one); the file holds the full label set, primary label first
  3. rejoined    every hand-split sentence, back as the WHOLE sentence the
                 product sees, labeled with the union of its parts' labels
                 (NONE dropped when a part has a real label)
  4. compound    dataset/labels/review/round4_compound_batch.csv: unlabelled
                 corpus sentences picked because they look compound (two
                 topic keywords, or a strong runner-up class), each given its
                 full label set, which may well be a single label or NONE

    -> dataset/labels/eligibility_annotations_multilabel.csv
       opportunity_id, chunk_id, chunk_text, labels ("AGE|RESIDENCE"), source, notes

eligibility_annotations.csv itself is left untouched, so the single-label
notebook (notebooks/eligibility_classifier.ipynb) still reproduces.

Usage: uv run python scripts/build_multilabel_dataset.py
"""

import os
import re
import sys

import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(REPO_ROOT)

from src.eligibility.chunking import split_into_chunks  # noqa: E402

LABELS_DIR = os.path.join(REPO_ROOT, "dataset", "labels")
SINGLE_PATH = os.path.join(LABELS_DIR, "eligibility_annotations.csv")
RELABEL_PATH = os.path.join(LABELS_DIR, "review", "round4_multilabel.csv")
COMPOUND_PATH = os.path.join(LABELS_DIR, "review", "round4_compound_batch.csv")
CORPUS_PATH = os.path.join(REPO_ROOT, "dataset", "opportunities.csv")
OUT_PATH = os.path.join(LABELS_DIR, "eligibility_annotations_multilabel.csv")

LABELS = ["RESIDENCE", "NATIONALITY", "AGE", "DISCIPLINE", "CAREER_STAGE", "EDUCATION",
          "STUDENT_STATUS", "APPLICANT_TYPE", "PRIOR_FUNDING", "OTHER_ELIGIBILITY", "NONE"]

SPLIT_ID_RE = re.compile(r"^(.*)_(\d+)([a-z])$")   # <opportunity_id>_<index><part letter>
CHUNK_ID_RE = re.compile(r"^(.*)_(\d+)$")


def union(labels: list[str]) -> list[str]:
    """Labels in first-seen order without repeats; NONE only if nothing else is there."""
    seen = list(dict.fromkeys(labels))
    real = [label for label in seen if label != "NONE"]
    return real or ["NONE"]


def check_label_set(chunk_id: str, labels: list[str]) -> None:
    unknown = set(labels) - set(LABELS)
    assert not unknown, f"{chunk_id}: unknown label(s) {unknown}"
    assert len(labels) == len(set(labels)), f"{chunk_id}: repeated label"
    assert labels == ["NONE"] or "NONE" not in labels, f"{chunk_id}: NONE next to a real label"


def build() -> pd.DataFrame:
    single = pd.read_csv(SINGLE_PATH)
    relabel = pd.read_csv(RELABEL_PATH).set_index("chunk_id")
    compound = pd.read_csv(COMPOUND_PATH)
    corpus = pd.read_csv(CORPUS_PATH).set_index("id")

    is_part = single["chunk_id"].str.match(SPLIT_ID_RE)
    rows = []

    # 1 + 2: unsplit rows, with round 4's extra labels where the review added some
    unknown = set(relabel.index) - set(single.loc[~is_part, "chunk_id"])
    assert not unknown, f"round4_multilabel.csv names chunks that are not unsplit rows: {unknown}"
    for row in single[~is_part].itertuples():
        if row.chunk_id in relabel.index:
            labels = relabel.at[row.chunk_id, "labels"].split("|")
            assert labels[0] == row.label, f"{row.chunk_id}: primary label changed ({row.label} -> {labels[0]})"
            source, note = "relabel", f"round 4: {relabel.at[row.chunk_id, 'reason']}"
        else:
            labels, source, note = [row.label], "single", ""
        rows.append(dict(opportunity_id=row.opportunity_id, chunk_id=row.chunk_id, chunk_text=row.chunk_text,
                         labels=labels, source=source, notes=note))

    # 3: hand-split parts back into the whole sentence the product sees
    parts = single[is_part].assign(base=lambda d: d["chunk_id"].str.replace(r"[a-z]$", "", regex=True))
    for base, group in parts.groupby("base", sort=False):
        opportunity_id, index = CHUNK_ID_RE.match(base).groups()
        sentence = split_into_chunks(str(corpus.at[opportunity_id, "requirements_text_en"]))[int(index)]
        rows.append(dict(opportunity_id=opportunity_id, chunk_id=base, chunk_text=sentence,
                         labels=union(group["label"].tolist()), source="rejoined",
                         notes=f"round 4: rejoined {len(group)} parts ({', '.join(group['chunk_id'])})"))

    # 4: new compound candidates from the unlabelled corpus
    for row in compound.itertuples():
        opportunity_id = CHUNK_ID_RE.match(row.chunk_id).group(1)
        rows.append(dict(opportunity_id=opportunity_id, chunk_id=row.chunk_id, chunk_text=row.chunk_text,
                         labels=row.labels.split("|"), source="compound", notes=f"round 4: {row.reason}"))

    out = pd.DataFrame(rows)
    for row in out.itertuples():
        check_label_set(row.chunk_id, row.labels)
    duplicated = out["chunk_id"][out["chunk_id"].duplicated()]
    assert duplicated.empty, f"chunk ids twice: {duplicated.tolist()}"
    out["labels"] = out["labels"].str.join("|")
    return out


def print_report(out: pd.DataFrame) -> None:
    sizes = out["labels"].str.count(r"\|") + 1
    print(f"{len(out)} chunks from {out['opportunity_id'].nunique()} opportunities -> {OUT_PATH}")
    print(out["source"].value_counts().to_string(), "\n")
    print(f"multi-label chunks: {(sizes > 1).sum()} ({(sizes > 1).mean():.0%}), labels per chunk: "
          f"{sizes.value_counts().sort_index().to_dict()}\n")
    per_label = out["labels"].str.split("|").explode().value_counts()
    print("chunks per label:\n" + per_label.to_string())


if __name__ == "__main__":
    dataset = build()
    dataset.to_csv(OUT_PATH, index=False)
    print_report(dataset)
