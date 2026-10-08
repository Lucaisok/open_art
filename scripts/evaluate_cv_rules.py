"""
Check the rule-based profile extractor (src/rag/cv_rules.py) against CVs with known answers.

    uv run python scripts/evaluate_cv_rules.py

Two sets, reported apart:
  dev       - the two example artists (examples/artists/), which the rules were written against
  held-out  - five CVs in examples/cv_eval/, written with their answers (truth.json) BEFORE
              the rules and not used to develop them: the honest estimate

Per field, as in scripts/evaluate_profile_prefill.py:
  right / wrong (proposed, correct or not) · missed (stated, not proposed) ·
  extra (proposed, not stated) · ok-null (not stated, not proposed)
No network, no model: runs in a second.
"""

import json
import os
import sys
from collections import Counter
from datetime import date

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from src.rag.cv_rules import extract_profile  # noqa: E402
from src.rag.documents import read_chunks  # noqa: E402

TODAY = date(2026, 10, 8)   # fixed, so the answers don't move with the calendar
FIELDS = ["birth_date", "nationalities", "residence_country", "applicant_type", "disciplines", "active_since",
          "currently_enrolled", "graduation_year", "has_degree", "degree_field"]

# the dev CVs' answers (same facts as TRUTH in evaluate_profile_prefill.py, in truth.json's format)
DEV = {
    "examples/artists/ilka_varga/cv.pdf": {
        "birth_date": "1994-03-12", "nationalities": ["HU"], "residence_country": "AT", "applicant_type": None,
        "disciplines": ["Visual Arts"], "active_since": [2021, 2022], "currently_enrolled": None,
        "graduation_year": 2021, "has_degree": True, "degree_field": ["painting and graphic arts"],
    },
    "examples/artists/tomas_ferreira/cv.docx": {
        "birth_date": "1988-07-04", "nationalities": ["BR", "PT"], "residence_country": "PT",
        "applicant_type": "individual",
        "disciplines": ["Music", "Visual Arts", "Digital/New Media Arts", "Performing Arts", "Multidisciplinary"],
        "active_since": [2019, 2021], "currently_enrolled": False, "graduation_year": 2010, "has_degree": True,
        "degree_field": ["music technology"],
    },
}


def is_right(field: str, value, truth) -> bool:
    if field == "disciplines":
        return bool(value) and set(value) <= set(truth)
    if field == "active_since":
        return truth[0] <= value <= truth[1]
    if field == "degree_field":
        return value.strip().lower() in truth
    if field == "nationalities":
        return sorted(value) == sorted(truth)
    return value == truth


def score(name: str, cvs: dict[str, dict]) -> Counter:
    totals = Counter()
    print(f"\n#### {name}")
    for path, truth in cvs.items():
        found = {s.field: s for s in extract_profile(read_chunks(os.path.join(REPO_ROOT, path)),
                                                     os.path.basename(path), TODAY)}
        print(f"\n{os.path.basename(path)}")
        for field in FIELDS:
            expected, proposal = truth[field], found.get(field)
            stated = expected not in (None, [])
            if proposal is None:
                outcome = "missed" if stated else "ok-null"
            elif not stated:
                outcome = "extra"
            else:
                outcome = "right" if is_right(field, proposal.value, expected) else "wrong"
            totals[outcome] += 1
            shown = f'{proposal.value!r}  "{proposal.quote[:60]}"' if proposal else "-"
            print(f"  {outcome:8} {field:19} {shown}")
    print("\n" + "   ".join(f"{k}: {totals[k]}" for k in ["right", "wrong", "missed", "extra", "ok-null"]))
    return totals


def main() -> None:
    with open(os.path.join(REPO_ROOT, "examples", "cv_eval", "truth.json"), encoding="utf-8") as f:
        truth = {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    score("dev (rules written against these)", DEV)
    score("held-out (written before the rules)", {f"examples/cv_eval/{k}": v for k, v in truth.items()})


if __name__ == "__main__":
    main()
