"""
OpenArt — eligibility engine step 4: measure the value parsers
(src/eligibility/values.py) against hand-checked expected values in
dataset/labels/eligibility_values.csv (126 labeled chunks: all AGE and
NATIONALITY, a seed-42 sample of RESIDENCE / APPLICANT_TYPE / STUDENT_STATUS).

Like the engine, a sentence whose polarity is WAIVES gets no value (there's
nothing to check). The gold label is used, so this measures the parsers on
their own, separate from classifier errors.

Each chunk ends up as one of:
  correct        parsed value == expected (both None counts too)
  left as CHECK  parser returned None, a value was expected: safe, less useful
  wrong          parser returned a value that differs from the expected one
    too strict   ... and the difference could wrongly REJECT someone (a
                 country missing from the list, a tighter age bound, a type
                 missing). This is the number that must be ~0.

`also_requires` is compared separately (present or not), since it only
decides between a reject and a CHECK, never between pass and reject.

Usage: uv run python scripts/evaluate_values.py   (seconds, no model)
"""

import json
import os
import sys

import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(REPO_ROOT)

from src.eligibility.polarity import WAIVES, polarity  # noqa: E402
from src.eligibility.values import parse_value  # noqa: E402

GOLD_PATH = os.path.join(REPO_ROOT, "dataset", "labels", "eligibility_values.csv")


def core(value: dict | None) -> dict | None:
    """The value without also_requires, for the main comparison."""
    if value is None:
        return None
    return {k: v for k, v in value.items() if k != "also_requires"} or None


def too_strict(parsed: dict, expected: dict | None) -> bool:
    """Could the parsed value reject someone the expected value lets through?"""
    if expected is None:
        return True  # any value where none was expected may reject
    if "countries" in parsed:
        return not set(expected.get("countries", [])) <= set(parsed["countries"])
    if "types" in parsed:
        return not set(expected.get("types", [])) <= set(parsed["types"])
    if "min_age" in parsed or "max_age" in parsed:
        return (parsed.get("min_age", 0) > expected.get("min_age", 0)
                or parsed.get("max_age", 999) < expected.get("max_age", 999))
    return parsed != expected


def has_also_requires(value: dict | None) -> bool:
    return value is not None and "also_requires" in value


def evaluate() -> pd.DataFrame:
    """One row per gold chunk with its parsed value and outcome. Also used
    by tests/test_values.py as a regression guard."""
    gold = pd.read_csv(GOLD_PATH, keep_default_na=False)
    rows = []
    for _, row in gold.iterrows():
        expected = json.loads(row["expected_value"]) if row["expected_value"] else None
        waived = polarity(row["chunk_text"], label=row["label"]) == WAIVES
        parsed = None if waived else parse_value(row["label"], row["chunk_text"])
        if core(parsed) == core(expected):
            outcome = "correct"
        elif parsed is None:
            outcome = "left as CHECK"
        else:
            outcome = "too strict" if too_strict(core(parsed), core(expected)) else "wrong (looser)"
        rows.append({**row, "parsed": parsed, "expected": expected, "outcome": outcome,
                     "also_requires_ok": (has_also_requires(parsed) == has_also_requires(expected))
                     if outcome == "correct" else None})
    return pd.DataFrame(rows)


def main() -> None:
    df = evaluate()
    print(pd.crosstab(df["label"], df["outcome"], margins=True)
          .reindex(columns=["correct", "left as CHECK", "wrong (looser)", "too strict", "All"], fill_value=0)
          .to_string())
    print(f"\ncorrect {(df.outcome == 'correct').mean():.0%}, left as CHECK {(df.outcome == 'left as CHECK').mean():.0%}, "
          f"too strict {(df.outcome == 'too strict').sum()} of {len(df)}")
    correct = df[df.outcome == "correct"]
    print(f"also_requires present/absent as expected on {correct['also_requires_ok'].mean():.0%} "
          f"of the {len(correct)} correct values")

    print("\n--- Everything not correct ---")
    for _, row in df[df.outcome != "correct"].iterrows():
        print(f"  [{row['outcome']}] {row['label']}: expected {row['expected']}, parsed {row['parsed']}\n"
              f"      {row['chunk_text'][:140]}")


if __name__ == "__main__":
    main()
