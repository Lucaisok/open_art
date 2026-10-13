"""
OpenArt — the match percentage on a card: "how likely is this call a clear fit for you?"

Cosine similarity can't be shown as a percentage: good matches sit around 0.45-0.6 for everyone.
So a small logistic regression turns three plain signals into a probability, trained on the
matching evaluation set (dataset/matching_eval/, 420 calls graded for 16 personas) by
scripts/train_match_score.py, which saves its weights to artifacts/match_score.json:

  z         how much closer this call is to the artist than their average call: the cosine minus
            the mean over every call in the index, divided by the standard deviation. Comparable
            across artists, and the same whatever the filters (they don't change the index)
  shared    how many specific words the call shares with the artist's documents (explain.py),
            capped at MAX_SHARED
  mismatch  1 if the call is probably for other disciplines (matcher.discipline_mismatch)

It is shown, never used: the ranking stays the measured one (cosine in three groups) and the
eligibility verdict never sees it (workflow.MD "Match percentage").
"""

import json
import math
import os
from dataclasses import dataclass

import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCORE_PATH = os.path.join(REPO_ROOT, "artifacts", "match_score.json")

MAX_SHARED = 5               # more shared words than this add nothing
FEATURES = ["z", "shared", "mismatch"]


@dataclass
class ArtistStats:
    """The artist's similarity to every call in the index: what z is measured against."""
    mean: float
    std: float

    @classmethod
    def of(cls, index_vectors: np.ndarray, query_vector: np.ndarray) -> "ArtistStats":
        scores = index_vectors @ query_vector
        return cls(mean=float(scores.mean()), std=float(scores.std()) or 1.0)


def features(cosine: float, stats: ArtistStats, shared: int, mismatch: bool) -> list[float]:
    """The model's inputs, in FEATURES order. Training and the app both build them here."""
    return [(cosine - stats.mean) / stats.std, float(min(shared, MAX_SHARED)), float(mismatch)]


class MatchScore:
    """The trained weights (artifacts/match_score.json): plain numbers, read as JSON, nothing pickled."""

    def __init__(self, path: str = SCORE_PATH):
        if not os.path.exists(path):
            raise FileNotFoundError(f"{path} not found: train it with `uv run python scripts/train_match_score.py`")
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)
        if saved["features"] != FEATURES:
            raise RuntimeError(f"{path} was trained on {saved['features']}, the code builds {FEATURES}: retrain it")
        self.coefficients = saved["coefficients"]
        self.intercept = saved["intercept"]

    def probability(self, x: list[float]) -> float:
        """The logistic regression's probability for one call, 0 to 1."""
        logit = self.intercept + sum(w * v for w, v in zip(self.coefficients, x))
        return 1 / (1 + math.exp(-logit))
