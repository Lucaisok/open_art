"""
OpenArt — merge the round-5 structured re-review of the dropped reviews into
dataset/labels/eligibility_constraints_reviewed.csv (ANNOTATION_GUIDELINES.md §10; workflow.MD,
"Conclusive verdicts" step 2).

Each of the 400 drops was re-reviewed (Claude Code subagents, no human spot check, by the author's
decision) into dataset/labels/review/round5/drops_reviewed_batch*.csv. This script checks every row
before anything is written, then updates the matching review row (same chunk_text + label):

- scope is one of the §9 scopes; a non-APPLICANT row has decision "scope" and no value;
- applies_to is empty or a JSON list of applicant types;
- a fix has polarity REQUIRES / EXCLUDES and a value in the §8 / §10 formats: known keys, ISO
  country codes, known broad regions, ages as integers, alternatives each with a known label.

Adds the columns scope and applies_to (empty on older rows = APPLICANT, everyone). Re-runnable.

Round 6 (2026-10-10, `--round 6`): the reviews about where the artist studied, rewritten with the
education values (institutions / study_places / study_countries, src/eligibility/study.py) in
dataset/labels/review/round6/. Unlike round 5 it may also rewrite confirm / fix rows.

Usage: uv run python scripts/apply_structured_reviews.py [--round 5|6]
"""

import argparse
import csv
import glob
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(REPO_ROOT)

from src.eligibility.engine import REVIEWED_PATH  # noqa: E402
from src.eligibility.geo import BROAD_REGIONS, COUNTRIES  # noqa: E402
from src.eligibility.scope import APPLICANT, SCOPES  # noqa: E402

ROUNDS = {
    "5": (os.path.join(REPO_ROOT, "dataset", "labels", "review", "round5", "drops_reviewed_batch*.csv"),
          "Claude Code (claude-opus-5-5) round 5 structured re-review, no human spot check"),
    "6": (os.path.join(REPO_ROOT, "dataset", "labels", "review", "round6", "*.csv"),
          "Claude Code (claude-opus-5-5) round 6 study reviews, no human spot check"),
}
TYPES = {"individual", "group", "organisation"}
LABELS = {"AGE", "NATIONALITY", "RESIDENCE", "APPLICANT_TYPE", "STUDENT_STATUS", "DISCIPLINE", "CAREER_STAGE",
          "EDUCATION", "PRIOR_FUNDING", "OTHER_ELIGIBILITY"}
REVIEWED_ON = "2026-10-10"


def check_value(value: dict, where: str, alternative: bool = False) -> None:
    """Raise ValueError if a value isn't in the §8 / §10 formats."""
    if "any_of" in value:
        if alternative or set(value) != {"any_of"} or not value["any_of"]:
            raise ValueError(f"{where}: any_of must be the only key, non-empty and not nested")
        for alt in value["any_of"]:
            if alt.get("label") not in LABELS:
                raise ValueError(f"{where}: alternative without a known label: {alt}")
            check_value({k: v for k, v in alt.items() if k != "label"}, where, alternative=True)
        return
    allowed = {"min_age", "max_age", "countries", "nationality_or_residence", "broad_regions", "types",
               "enrolled", "graduated_within_years", "also_requires", "institutions", "study_places",
               "study_countries"}
    if unknown := set(value) - allowed:
        raise ValueError(f"{where}: unknown keys {unknown}")
    for key in ("min_age", "max_age", "graduated_within_years"):
        if key in value and not isinstance(value[key], int):
            raise ValueError(f"{where}: {key} must be an integer")
    if bad := [c for c in value.get("countries", []) + value.get("study_countries", []) if c not in COUNTRIES]:
        raise ValueError(f"{where}: unknown country codes {bad}")
    if bad := [r for r in value.get("broad_regions", []) if r not in BROAD_REGIONS]:
        raise ValueError(f"{where}: unknown broad regions {bad}")
    if bad := set(value.get("types", [])) - TYPES:
        raise ValueError(f"{where}: unknown applicant types {bad}")
    if not alternative and not (set(value) - {"also_requires"}):
        raise ValueError(f"{where}: a value with nothing to check")


def check_row(row: dict, where: str) -> None:
    if row["scope"] not in SCOPES:
        raise ValueError(f"{where}: unknown scope {row['scope']!r}")
    if row["applies_to"] and (set(json.loads(row["applies_to"])) - TYPES):
        raise ValueError(f"{where}: bad applies_to {row['applies_to']}")
    if row["scope"] != APPLICANT:
        if row["decision"] != "scope" or row["value"]:
            raise ValueError(f"{where}: a {row['scope']} row must have decision 'scope' and no value")
        return
    if row["decision"] == "fix":
        if row["polarity"] not in ("REQUIRES", "EXCLUDES"):
            raise ValueError(f"{where}: a fix needs polarity REQUIRES / EXCLUDES")
        check_value(json.loads(row["value"]), where)
    elif row["decision"] != "drop":
        raise ValueError(f"{where}: an APPLICANT row must be a fix or a drop, not {row['decision']!r}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--round", choices=sorted(ROUNDS), default="5")
    round_ = parser.parse_args().round
    round_glob, reviewed_by = ROUNDS[round_]
    updates = {}
    for path in sorted(glob.glob(round_glob)):
        with open(path, encoding="utf-8", newline="") as f:
            for number, row in enumerate(csv.DictReader(f), start=2):
                check_row(row, f"{os.path.basename(path)} line {number}")
                updates[(row["chunk_text"], row["label"])] = row
    with open(REVIEWED_PATH, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames)
        reviews = list(reader)
    for column in ("scope", "applies_to"):
        if column not in fields:
            fields.insert(fields.index("reason"), column)
    applied = 0
    for review in reviews:
        review.setdefault("scope", "")
        review.setdefault("applies_to", "")
        update = updates.get((review["chunk_text"], review["label"]))
        if update is None:
            continue
        if round_ == "5" and review["decision"] != "drop" and review["reviewed_by"] != reviewed_by:
            raise ValueError(f"round 5 only re-reviews drops: {review['chunk_text'][:60]!r} is a {review['decision']}")
        review.update(decision=update["decision"], polarity=update["polarity"], value=update["value"],
                      reason=update["reason"], scope="" if update["scope"] == APPLICANT else update["scope"],
                      applies_to=update["applies_to"], reviewed_by=reviewed_by, reviewed_on=REVIEWED_ON)
        applied += 1
    if applied != len(updates):
        raise ValueError(f"{len(updates) - applied} round-{round_} rows match no review row")
    with open(REVIEWED_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(reviews)
    print(f"{applied} reviews updated in {os.path.relpath(REVIEWED_PATH, REPO_ROOT)}")


if __name__ == "__main__":
    main()
