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
    """Same 4 sentences and results as the sanity check at the end of
    notebooks/eligibility_multilabel.ipynb. If these differ, the product is
    not using the model the notebook evaluated."""
    senegal = ("Applicants must be over 18 years of age , be proficient in French or English, and reside in "
               "South Africa, Benin, Cameroon, Ghana, Guinea, Kenya, Mali, Mozambique, Uganda, the Republic of "
               "the Congo, Rwanda or Senegal.")
    expected = [
        ("Applicants must be resident in Scotland.", ["RESIDENCE"], {"RESIDENCE": 0.99}),
        ("The residency is open to artists under the age of 35.", ["AGE"], {"AGE": 1.0}),
        # the production sentence the single-label model read as AGE only
        (senegal, ["AGE", "RESIDENCE", "OTHER_ELIGIBILITY"], {"AGE": 0.99, "RESIDENCE": 0.96}),
        # a known false positive (an obligation after selection, not a requirement): kept as a reference
        ("The selected artist will present their work at the end of the residency.", ["OTHER_ELIGIBILITY"],
         {"OTHER_ELIGIBILITY": 0.76}),
    ]
    predictions = classifier.predict([text for text, _, _ in expected])
    for (text, labels, probabilities), prediction in zip(expected, predictions):
        assert prediction.labels == labels, text
        for label, p in probabilities.items():
            assert round(prediction.probabilities[label], 2) == p, (text, label)


def test_no_label_means_none(classifier):
    [prediction] = classifier.predict(["The residency lasts three months and includes a studio."])
    assert prediction.labels == [] and prediction.label == "NONE"
    assert max(prediction.probabilities.values()) < 0.5


def test_probabilities_cover_every_requirement_label(classifier):
    [prediction] = classifier.predict(["Applicants must be under 35."])
    assert set(prediction.probabilities) == set(classifier.metadata["labels"])
    assert "NONE" not in prediction.probabilities
    assert prediction.label == "AGE" and prediction.labels[0] == "AGE"
    # labels are the ones at or above their threshold, most probable first
    fired = [l for l, p in prediction.probabilities.items() if p >= classifier.thresholds[l]]
    assert sorted(fired) == sorted(prediction.labels)
    assert [prediction.probabilities[l] for l in prediction.labels] == sorted(
        (prediction.probabilities[l] for l in prediction.labels), reverse=True)


def test_results_come_back_in_input_order(classifier):
    """predict() embeds texts sorted by length for speed; the results must
    still line up with the texts as they were passed in."""
    texts = [
        "The residency is open to artists under the age of 35 who live and work in Europe.",
        "Students are not eligible.",
        "Applicants must be resident in Scotland.",
    ]
    together = classifier.predict(texts)
    one_by_one = [classifier.predict([text])[0] for text in texts]
    assert [p.labels for p in together] == [p.labels for p in one_by_one]
    for a, b in zip(together, one_by_one):
        assert a.probabilities == pytest.approx(b.probabilities)


def test_empty_input(classifier):
    assert classifier.predict([]) == []


def test_refuses_a_different_library_version(classifier, monkeypatch):
    """A model pickled with one scikit-learn version can behave differently
    under another, without any error. The loader must refuse instead."""
    monkeypatch.setitem(classifier.metadata["versions"], "scikit-learn", "0.0.1")
    with pytest.raises(RuntimeError, match="scikit-learn"):
        classifier._check_versions()
