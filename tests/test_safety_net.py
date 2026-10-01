"""Tests for src/eligibility/safety_net.py. Run with: uv run pytest"""

from src.eligibility.safety_net import RUNNER_UP_THRESHOLD, flag_missed_requirement

LABELS = ["AGE", "APPLICANT_TYPE", "CAREER_STAGE", "DISCIPLINE", "EDUCATION", "NATIONALITY",
          "NONE", "OTHER_ELIGIBILITY", "PRIOR_FUNDING", "RESIDENCE", "STUDENT_STATUS"]


def confident_none(**overrides: float) -> dict[str, float]:
    """Probabilities for a sentence the model calls NONE with high confidence:
    NONE gets whatever the other classes leave over."""
    probabilities = {label: 0.01 for label in LABELS if label != "NONE"}
    probabilities.update(overrides)
    probabilities["NONE"] = 1 - sum(probabilities.values())
    return probabilities


def test_topic_keyword_names_the_class():
    # the real miss from step 2: labeled NONE at 0.86, actually a residence rule
    flag = flag_missed_requirement(
        "We invite artists and researchers based in Ukraine and across Europe to apply.",
        confident_none(),
    )
    assert flag.suspected_label == "RESIDENCE"
    assert flag.reason == 'keyword "based in"'


def test_several_topic_keywords_pick_the_class_the_model_rates_higher():
    flag = flag_missed_requirement(
        "Students and citizens of Norway are welcome.",
        confident_none(NATIONALITY=0.08, STUDENT_STATUS=0.02),
    )
    assert flag.suspected_label == "NATIONALITY"


def test_generic_keyword_uses_the_runner_up_class():
    flag = flag_missed_requirement(
        "The call is open to everyone working with sound.",
        confident_none(DISCIPLINE=0.12),
    )
    assert flag.suspected_label == "DISCIPLINE"
    assert flag.reason == 'keyword "open to"'


def test_unsure_model_is_flagged_without_keyword():
    flag = flag_missed_requirement(
        "A call for Villa Arson's former members.",
        confident_none(STUDENT_STATUS=RUNNER_UP_THRESHOLD + 0.1),
    )
    assert flag.suspected_label == "STUDENT_STATUS"
    assert flag.reason.startswith("classifier unsure")


def test_plain_none_is_not_flagged():
    assert flag_missed_requirement(
        "The selected artist will present their work at the end of the residency.",
        confident_none(),
    ) is None
