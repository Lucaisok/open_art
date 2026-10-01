"""
OpenArt — eligibility engine step 2b: measure a "safety net" for requirement
sentences the classifier wrongly labels NONE.

The problem: the engine only sees what the classifier labels as a
requirement. A real requirement labeled NONE ("…based in Ukraine and across
Europe…", NONE at 0.86) is simply dropped, and the artist gets a wrong
ELIGIBLE. The fix under test: turn some NONE sentences into CHECK items
using two plain, deterministic rules:

  1. keyword rule:     a NONE sentence containing a strong eligibility cue
                       ("citizen", "based in", "students", ...) -> CHECK
  2. runner-up rule:   a NONE sentence whose best non-NONE class has
                       probability >= t -> CHECK (the model was torn)

To measure them honestly the classifier must label sentences it was NOT
trained on, so this uses cross-validation on the 696 labeled chunks, with the
same model and the same fold scheme as the notebook (5-fold
StratifiedGroupKFold by opportunity), repeated over 10 fold seeds because the
counts are small. For each rule it reports:

  caught       real requirements labeled NONE that the rule turns into CHECK
  false alarms real NONE sentences the rule turns into CHECK
  corpus       how many extra CHECK items it would add on the full corpus

The keyword cues (src/eligibility/safety_net.py) were written from the class
definitions in ANNOTATION_GUIDELINES.md BEFORE looking at any result, so the
list is not tuned to the very misses it is measured on. The rule chosen from
this measurement (2026-10-01): keyword OR runner-up >= 0.3.

Usage: uv run python scripts/evaluate_none_safety_net.py   (~2 min, embeds the labeled chunks)
"""

import os
import sys

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.model_selection import StratifiedGroupKFold, cross_val_predict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(REPO_ROOT)

from src.eligibility.classify import EligibilityClassifier  # noqa: E402
# the cues live in src/ so the measured rule is exactly the shipped one
from src.eligibility.safety_net import KEYWORD_CUES, keyword_hits  # noqa: E402

LABELS_PATH = os.path.join(REPO_ROOT, "dataset", "labels", "eligibility_annotations.csv")
CORPUS_CHUNKS_PATH = os.path.join(REPO_ROOT, "data", "processed", "eligibility_constraints.jsonl")

SEEDS = range(10)
RUNNER_UP_THRESHOLDS = [0.2, 0.3, 0.4]

def runner_up(probabilities: np.ndarray, labels: list[str]) -> float:
    """Highest probability among the non-NONE classes (array version of
    safety_net.runner_up, for the cross-validation matrices)."""
    return max(p for label, p in zip(labels, probabilities) if label != "NONE")


def out_of_fold_probabilities(classifier, X, y, groups) -> list[np.ndarray]:
    """One probability matrix per seed: every chunk scored by a model that
    never saw its opportunity during training."""
    results = []
    for seed in SEEDS:
        cv = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=seed)
        model = clone(classifier.model)  # same pipeline and C as the shipped model, unfitted
        results.append(cross_val_predict(model, X, y, groups=groups, cv=cv, method="predict_proba", n_jobs=-1))
    return results


def main() -> None:
    labeled = pd.read_csv(LABELS_PATH)
    classifier = EligibilityClassifier()
    labels = classifier.labels
    none_column = labels.index("NONE")

    print(f"Embedding {len(labeled)} labeled chunks...")
    X = classifier.embed(labeled["chunk_text"].tolist())
    y = labeled["label"]
    gold_requirement = (y != "NONE").to_numpy()
    hits = labeled["chunk_text"].map(keyword_hits)
    has_cue = hits.map(bool).to_numpy()

    print(f"Cross-validating over {len(SEEDS)} fold seeds...\n")
    all_probabilities = out_of_fold_probabilities(classifier, X, y, labeled["opportunity_id"])

    # --- 1. how big is the problem, and how well does each rule fix it ---------
    rules = {"keyword": lambda p: has_cue}
    for t in RUNNER_UP_THRESHOLDS:
        rules[f"runner-up >= {t}"] = lambda p, t=t: np.array([runner_up(row, labels) >= t for row in p])
        rules[f"keyword OR runner-up >= {t}"] = lambda p, t=t: has_cue | np.array([runner_up(row, labels) >= t for row in p])

    missed_per_seed = []
    table = {name: {"caught": [], "false_alarms": []} for name in rules}
    for probabilities in all_probabilities:
        predicted_none = probabilities.argmax(axis=1) == none_column
        missed = predicted_none & gold_requirement           # the wrong-ELIGIBLE cases
        true_none = predicted_none & ~gold_requirement       # NONE, correctly
        missed_per_seed.append(missed.sum())
        for name, rule in rules.items():
            flagged = rule(probabilities)
            table[name]["caught"].append((flagged & missed).sum())
            table[name]["false_alarms"].append((flagged & true_none).sum())

    n_requirements = gold_requirement.sum()
    n_missed = np.mean(missed_per_seed)
    n_true_none = (~gold_requirement).sum()
    print(f"Real requirement sentences: {n_requirements}. Labeled NONE by the classifier "
          f"(out of fold, mean over seeds): {n_missed:.1f} ({n_missed / n_requirements:.1%})\n")
    print(f"{'rule':30s} {'caught':>14s} {'false alarms':>22s}")
    for name, counts in table.items():
        caught, false_alarms = np.mean(counts["caught"]), np.mean(counts["false_alarms"])
        print(f"{name:30s} {caught:5.1f} / {n_missed:4.1f} ({caught / n_missed:4.0%})"
              f" {false_alarms:6.1f} of ~{n_true_none} NONE ({false_alarms / n_true_none:4.0%})")

    # --- 1b. misses by class: a missed AGE/RESIDENCE/... sentence is worse than
    # a missed DISCIPLINE one, because only the first kind could ever reject
    print(f"\nMisses by gold class (mean over seeds), and share caught by "
          f"'keyword' / 'keyword OR runner-up >= 0.3':")
    print(f"  {'class':17s} {'missed':>6s} {'keyword':>8s} {'kw+ru0.3':>9s}")
    for label in sorted(set(y) - {"NONE"}):
        is_class = (y == label).to_numpy()
        missed_n, kw_n, both_n = [], [], []
        for probabilities in all_probabilities:
            missed = (probabilities.argmax(axis=1) == none_column) & is_class
            runner = np.array([runner_up(row, labels) >= 0.3 for row in probabilities])
            missed_n.append(missed.sum())
            kw_n.append((missed & has_cue).sum())
            both_n.append((missed & (has_cue | runner)).sum())
        m = np.mean(missed_n)
        if m == 0:
            print(f"  {label:17s} {m:6.1f}")
            continue
        print(f"  {label:17s} {m:6.1f} {np.mean(kw_n) / m:8.0%} {np.mean(both_n) / m:9.0%}")

    # --- 2. which keyword cue lists pay off (seed 0, for readability) ----------
    probabilities = all_probabilities[0]
    predicted_none = probabilities.argmax(axis=1) == none_column
    missed = predicted_none & gold_requirement
    true_none = predicted_none & ~gold_requirement
    print("\nPer cue list (seed 0): caught misses / false alarms")
    for name in KEYWORD_CUES:
        matches = hits.map(lambda h: name in h).to_numpy()
        print(f"  {name:15s} {(matches & missed).sum():3d} / {(matches & true_none).sum():3d}")

    # --- 3. the misses no rule catches (seed 0), to see what is left ----------
    any_rule = has_cue | np.array([runner_up(row, labels) >= min(RUNNER_UP_THRESHOLDS) for row in probabilities])
    left = labeled[missed & ~any_rule]
    print(f"\nMisses caught by no rule (seed 0): {len(left)}")
    for _, row in left.iterrows():
        print(f"  {row['label']:17s} | {row['chunk_text'][:100]}")

    # --- 4. cost on the real corpus: extra CHECK items per opportunity ---------
    corpus = pd.read_json(CORPUS_CHUNKS_PATH, lines=True)
    corpus_none = corpus[corpus["label"] == "NONE"]
    corpus_cue = corpus_none["text"].map(keyword_hits).map(bool)
    print(f"\nFull corpus: {len(corpus_none)} NONE chunks in {corpus['opportunity_id'].nunique()} opportunities")
    for t in RUNNER_UP_THRESHOLDS:
        corpus_runner_up = corpus_none["probabilities"].map(
            lambda p: max(v for k, v in p.items() if k != "NONE") >= t)
        flagged = corpus_cue | corpus_runner_up
        print(f"  keyword OR runner-up >= {t}: {flagged.sum()} chunks -> CHECK, "
              f"{flagged.sum() / corpus['opportunity_id'].nunique():.2f} per opportunity")
    print(f"  keyword only: {corpus_cue.sum()} chunks -> CHECK, "
          f"{corpus_cue.sum() / corpus['opportunity_id'].nunique():.2f} per opportunity")


if __name__ == "__main__":
    main()
