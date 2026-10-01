"""
OpenArt — eligibility engine step 3: measure the polarity rule
(src/eligibility/polarity.py) against the `excludes` flag on the 696 labeled
chunks.

What counts as an error for the engine. Both directions can wrongly reject:
  - gold excludes, rule says REQUIRES: "Students are not eligible" read as
    "students required" -> every non-student rejected
  - gold not excludes, rule says EXCLUDES: "Open to students" read as
    "students excluded" -> every student rejected
UNCLEAR is safe (it becomes a CHECK item), only less useful. WAIVES can't be
checked against the labels (a waiver is `excludes = False` there), so every
WAIVES prediction is listed for a hand check.

Headings: each labeled chunk is re-located in its call with the shared
splitter to find the heading it sits under. Hand-split or edited chunks
(see workflow.MD, step 1) can't be re-located and are scored without one.

Usage: uv run python scripts/evaluate_polarity.py   (a few seconds, no model)
"""

import os
import re
import sys

import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(REPO_ROOT)

from src.eligibility.chunking import chunk_requirements  # noqa: E402
from src.eligibility.polarity import EXCLUDES, REQUIRES, UNCLEAR, WAIVES, polarity  # noqa: E402

LABELS_PATH = os.path.join(REPO_ROOT, "dataset", "labels", "eligibility_annotations.csv")
CORPUS_PATH = os.path.join(REPO_ROOT, "dataset", "opportunities.csv")

# the classes the engine may reject on (workflow.MD, "Per-class rules"): here a
# polarity error turns straight into a wrong verdict
GATING_CLASSES = {"AGE", "NATIONALITY", "RESIDENCE", "APPLICANT_TYPE", "STUDENT_STATUS", "EDUCATION", "CAREER_STAGE"}


def find_headings(labeled: pd.DataFrame) -> list[str | None]:
    """The bare heading each labeled chunk sits under, or None."""
    corpus = pd.read_csv(CORPUS_PATH).set_index("id")
    headings = []
    for chunk_id, text in zip(labeled["chunk_id"], labeled["chunk_text"]):
        found = re.match(r"^(.*)_(\d+)$", chunk_id)
        heading = None
        if found:
            chunks = chunk_requirements(str(corpus.at[found.group(1), "requirements_text_en"]))
            index = int(found.group(2))
            if index < len(chunks) and chunks[index].text == text:
                heading = chunks[index].heading
        headings.append(heading)
    return headings


def report(df: pd.DataFrame, title: str) -> None:
    gold = df["excludes"]
    predicted = df["polarity"]
    print(f"\n=== {title}: {len(df)} chunks, {gold.sum()} gold excludes ===")
    print(pd.crosstab(gold.map({True: "gold excludes", False: "gold not excludes"}), predicted)
          .reindex(columns=[REQUIRES, EXCLUDES, WAIVES, UNCLEAR], fill_value=0).to_string())

    true_positive = (predicted == EXCLUDES) & gold
    precision = true_positive.sum() / max((predicted == EXCLUDES).sum(), 1)
    recall = true_positive.sum() / max(gold.sum(), 1)
    # confidently wrong = would turn into a wrong verdict; UNCLEAR is not counted
    wrong = (gold & predicted.isin([REQUIRES, WAIVES])) | (~gold & (predicted == EXCLUDES))
    print(f"EXCLUDES precision {precision:.0%}, recall {recall:.0%}; "
          f"UNCLEAR {(predicted == UNCLEAR).mean():.1%}; "
          f"confidently wrong {wrong.sum()} ({wrong.mean():.1%})")


def main() -> None:
    labeled = pd.read_csv(LABELS_PATH)
    # kept as a plain list: in a DataFrame column pandas turns None into NaN
    headings = find_headings(labeled)
    labeled["heading"] = headings
    # the gold label is passed (not the classifier's), so this measures the
    # polarity rule on its own, separate from classification errors
    texts, labels = labeled["chunk_text"], labeled["label"]
    labeled["polarity"] = [polarity(t, h, l) for t, h, l in zip(texts, headings, labels)]
    labeled["polarity_no_heading"] = [polarity(t, None, l) for t, l in zip(texts, labels)]
    print(f"{labeled['heading'].notna().sum()} labeled chunks sit under a bare heading")

    requirements = labeled[labeled["label"] != "NONE"]
    report(labeled, "All labeled chunks")
    report(requirements, "Requirement chunks (label != NONE)")
    report(requirements[requirements["label"].isin(GATING_CLASSES)], "Classes the engine may reject on")

    changed = labeled[labeled["polarity"] != labeled["polarity_no_heading"]]
    print(f"\nThe heading rule changes {len(changed)} predictions "
          f"({(changed['excludes'] & (changed['polarity'] == EXCLUDES)).sum()} of them to a correct EXCLUDES)")

    print("\n--- Errors on requirement chunks (confidently wrong) ---")
    wrong = requirements[(requirements["excludes"] & requirements["polarity"].isin([REQUIRES, WAIVES]))
                         | (~requirements["excludes"] & (requirements["polarity"] == EXCLUDES))]
    for _, row in wrong.iterrows():
        gold = "excl" if row["excludes"] else "not"
        print(f"  gold {gold:4s} -> {row['polarity']:8s} {row['label']:17s} | {row['chunk_text'][:95]}")

    for kind in (WAIVES, UNCLEAR):
        rows = requirements[requirements["polarity"] == kind]
        print(f"\n--- {kind} on requirement chunks ({len(rows)}), for a hand check ---")
        for _, row in rows.iterrows():
            print(f"  {row['label']:17s} | {row['chunk_text'][:110]}")


if __name__ == "__main__":
    main()
