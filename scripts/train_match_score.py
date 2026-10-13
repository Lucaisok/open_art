"""
Train the match percentage (src/matching/score.py) on the matching evaluation set.

Reads dataset/matching_eval/rankings.json (every kept call's features, written by
`evaluate_matching.py pool`) and judgments.csv (the graded calls). The label is LABEL below.
Writes artifacts/match_score.json: the logistic regression's weights as plain JSON, plus the
cross-validated metrics, so the number on a card can be traced back to how it was tested.

    uv run python scripts/train_match_score.py

Evaluation: grouped cross-validation by persona (GroupKFold): every fold is scored on artists the
model never saw, as in the app. Reported: ROC AUC (does it rank clear fits above the rest?), Brier
score and log loss (are the probabilities right?), against two baselines, and a calibration table
(of the calls given ~70%, are ~70% clear fits?).

No class_weight="balanced" here, on purpose: it would shift every probability towards 50%, and the
point of this model is that its percentages are calibrated.
"""

import csv
import json
import os
import sys
from datetime import date

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import GroupKFold

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from src.matching.score import FEATURES, SCORE_PATH  # noqa: E402

EVAL_DIR = os.path.join(REPO_ROOT, "dataset", "matching_eval")
FOLDS = 4                    # 4 artists held out per fold
BINS = 5                     # calibration table rows (equal-count bins)

# what the percentage means: the chance the call is a CLEAR fit (grade 2). "Worth showing" (grade 1 or
# 2) was tried too: ~80% of the judged calls are, so every card would read 75-95% and say nothing.
LABEL = "clear fit (grade 2)"


def load() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rankings = json.load(open(os.path.join(EVAL_DIR, "rankings.json"), encoding="utf-8"))
    X, y, groups = [], [], []
    with open(os.path.join(EVAL_DIR, "judgments.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            found = rankings.get(row["persona_id"], {}).get("features", {}).get(row["opportunity_id"])
            if found is None:     # no longer kept for this persona (closed, or filtered out): skip
                continue
            X.append(found)
            y.append(int(row["grade"]) == 2)
            groups.append(row["persona_id"])
    return np.array(X), np.array(y, dtype=int), np.array(groups)


def out_of_fold(X: np.ndarray, y: np.ndarray, groups: np.ndarray, columns: list[int]) -> np.ndarray:
    """Every call's probability from a model trained without its persona."""
    p = np.zeros(len(y))
    for train, test in GroupKFold(n_splits=FOLDS).split(X, y, groups):
        model = LogisticRegression().fit(X[train][:, columns], y[train])
        p[test] = model.predict_proba(X[test][:, columns])[:, 1]
    return p


def report(name: str, y: np.ndarray, p: np.ndarray) -> dict:
    auc = roc_auc_score(y, p) if len(set(p)) > 1 else 0.5
    metrics = {"roc_auc": round(auc, 3), "brier": round(brier_score_loss(y, p), 4),
               "log_loss": round(log_loss(y, np.clip(p, 1e-6, 1 - 1e-6)), 4)}
    print(f"  {name:34} AUC {metrics['roc_auc']:.3f}   Brier {metrics['brier']:.4f}   log loss {metrics['log_loss']:.4f}")
    return metrics


def calibration(y: np.ndarray, p: np.ndarray) -> list[dict]:
    """Equal-count bins of the predicted probability: the mean prediction vs the share of clear fits."""
    order = np.argsort(p)
    table = []
    for chunk in np.array_split(order, BINS):
        table.append({"calls": int(len(chunk)), "predicted": round(float(p[chunk].mean()), 3),
                      "observed": round(float(y[chunk].mean()), 3)})
    return table


def main() -> None:
    X, y, groups = load()
    print(f"{len(y)} judged calls, {y.sum()} clear fits ({y.mean():.0%}), {len(set(groups))} personas; "
          f"features {FEATURES}\n")
    print(f"grouped {FOLDS}-fold cross-validation (by persona):")
    base = report("base rate (same % for every call)", y, np.full(len(y), y.mean()))
    z_only = report("z only", y, out_of_fold(X, y, groups, [0]))
    p = out_of_fold(X, y, groups, list(range(len(FEATURES))))
    full = report("z + shared words + mismatch", y, p)

    table = calibration(y, p)
    print("\ncalibration (out of fold):")
    print("  calls  predicted  observed")
    for row in table:
        print(f"  {row['calls']:5d}  {row['predicted']:9.0%}  {row['observed']:8.0%}")

    model = LogisticRegression().fit(X, y)
    coefficients = [round(float(w), 4) for w in model.coef_[0]]
    print("\ncoefficients (all data):", dict(zip(FEATURES, coefficients)), "intercept", round(float(model.intercept_[0]), 4))
    with open(SCORE_PATH, "w", encoding="utf-8") as f:
        json.dump({"features": FEATURES, "coefficients": coefficients, "intercept": round(float(model.intercept_[0]), 4),
                   "label": LABEL, "trained_on": {"calls": int(len(y)), "positives": int(y.sum()),
                                                  "personas": len(set(groups)), "date": date.today().isoformat()},
                   "cross_validation": {"folds": FOLDS, "grouped_by": "persona", "base_rate": base, "z_only": z_only,
                                        "model": full, "calibration": table}}, f, indent=1)
    print(f"saved -> {os.path.relpath(SCORE_PATH, REPO_ROOT)}")


if __name__ == "__main__":
    main()
