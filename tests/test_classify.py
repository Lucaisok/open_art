"""Tests for src/eligibility/classify.py. These load the real model and the
embedding model (downloaded once into ~/.cache/fastembed), so they take a few
seconds. Run with: uv run pytest"""

import pytest

from src.eligibility.classify import EligibilityClassifier


@pytest.fixture(scope="module")
def classifier():
    # loaded once for the whole file: loading the embedding model is the slow part
    return EligibilityClassifier()


def test_reproduces_the_notebook(classifier):
    """Same 4 sentences and results as the sanity check in
    notebooks/eligibility_classifier.ipynb (cell 30). If these differ, the
    product is not using the model the notebook evaluated."""
    expected = [
        ("Applicants must be resident in Scotland.", "RESIDENCE", 0.99),
        ("The residency is open to artists under the age of 35.", "AGE", 0.90),
        ("We welcome applications from painters, sculptors and printmakers.", "DISCIPLINE", 0.59),
        ("The selected artist will present their work at the end of the residency.", "OTHER_ELIGIBILITY", 0.37),
    ]
    predictions = classifier.predict([text for text, _, _ in expected])
    for (text, label, confidence), prediction in zip(expected, predictions):
        assert prediction.label == label, text
        assert round(prediction.confidence, 2) == confidence, text


def test_probabilities_cover_every_class(classifier):
    [prediction] = classifier.predict(["Applicants must be under 35."])
    assert set(prediction.probabilities) == set(classifier.metadata["labels"])
    assert sum(prediction.probabilities.values()) == pytest.approx(1.0)
    assert prediction.confidence == max(prediction.probabilities.values())


def test_empty_input(classifier):
    assert classifier.predict([]) == []


def test_refuses_a_different_library_version(classifier, monkeypatch):
    """A model pickled with one scikit-learn version can behave differently
    under another, without any error. The loader must refuse instead."""
    monkeypatch.setitem(classifier.metadata["versions"], "scikit-learn", "0.0.1")
    with pytest.raises(RuntimeError, match="scikit-learn"):
        classifier._check_versions()
