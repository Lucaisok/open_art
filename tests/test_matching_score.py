"""Tests for src/matching/score.py, the match percentage. Run with: uv run pytest"""

import json

import numpy as np
import pytest

from src.matching.score import FEATURES, MAX_SHARED, ArtistStats, MatchScore, features


def test_z_is_measured_against_every_call_in_the_index():
    stats = ArtistStats.of(np.array([[1.0, 0.0], [0.0, 1.0]]), np.array([1.0, 0.0]))   # scores 1 and 0
    assert (stats.mean, stats.std) == (0.5, 0.5)
    assert features(1.0, stats, shared=9, mismatch=True) == [1.0, float(MAX_SHARED), 1.0]   # shared capped


def test_probability_is_the_logistic_of_the_saved_weights(tmp_path):
    path = tmp_path / "score.json"
    path.write_text(json.dumps({"features": FEATURES, "coefficients": [1.0, 0.5, -1.0], "intercept": -1.0}))
    score = MatchScore(str(path))
    assert score.probability([1.0, 0.0, 0.0]) == pytest.approx(0.5)     # logit 0
    assert score.probability([3.0, 2.0, 0.0]) > score.probability([3.0, 2.0, 1.0])   # a mismatch lowers it


def test_weights_for_other_features_are_refused(tmp_path):
    path = tmp_path / "score.json"
    path.write_text(json.dumps({"features": ["z"], "coefficients": [1.0], "intercept": 0.0}))
    with pytest.raises(RuntimeError, match="retrain"):
        MatchScore(str(path))


def test_the_shipped_weights_load_and_move_the_right_way():
    score = MatchScore()
    low, high = score.probability([0.0, 0.0, 0.0]), score.probability([3.0, 3.0, 0.0])
    assert 0 < low < high < 1   # closer than average and more shared words: more likely a clear fit
