"""Tests for language requirements (src/eligibility/languages.py), the engine's "Language" items, the
profile field and the CV's Languages section (src/rag/cv_rules.py). Run with: uv run pytest"""

from datetime import date

import pytest

from src.eligibility.engine import evaluate_chunks
from src.eligibility.languages import languages_check, parse_languages
from src.eligibility.profile import ArtistProfile
from src.models.classified_chunk import ClassifiedChunk
from src.rag.cv_rules import extract_profile
from src.rag.documents import Chunk


@pytest.mark.parametrize("text, expected", [
    ("Applicants must be proficient in French or English.", {"languages": ["en", "fr"], "all": False}),
    ("Demonstrate a professional-level command of French and/or English", {"languages": ["en", "fr"], "all": False}),
    ("Applicants must speak both Dutch and English.", {"languages": ["en", "nl"], "all": True}),
    ("English language skills are a prerequisite.", {"languages": ["en"], "all": False}),
    # not a skill asked of the applicant
    ("Please note that all sessions will be held in English.", None),
    ("It is not essential to speak or understand Italian, but it is an advantage.", None),
    ("Knowledge of English and French is welcome.", None),
    ("Grants for translations of Danish literature into English.", None),
    ("artists within the French-speaking art community of Belgium", None),
])
def test_parse_languages(text, expected):
    assert parse_languages(text) == expected


def test_languages_check_passes_only_when_met():
    either = {"languages": ["en", "fr"], "all": False}
    both = {"languages": ["en", "nl"], "all": True}
    assert languages_check(either, ["en", "it"])[0] is True
    assert languages_check(both, ["en", "it"])[0] is False
    assert "not in your profile" in languages_check(either, [])[1]


def chunk(index, text, label, polarity="REQUIRES"):
    return ClassifiedChunk(opportunity_id="opp", chunk_id=f"opp_{index}", chunk_index=index, text=text,
                           is_heading=False, label=label, confidence=0.9, polarity=polarity, model_trained_on="test")


def run(profile, chunks):
    return evaluate_chunks(profile, chunks, {}, opportunity_id="opp", today=date(2026, 10, 1))


def test_a_language_sentence_the_classifier_missed_is_still_read():
    sentence = chunk(0, "Proficiency in German and/or English is required.", "NONE", polarity=None)
    verdict = run(ArtistProfile(languages=["en"]), [sentence])
    assert [(i.label, i.outcome) for i in verdict.items] == [("LANGUAGE", "PASS")]
    assert verdict.status == "ELIGIBLE"
    # without the language: a check, never a fail
    assert run(ArtistProfile(languages=["it"]), [sentence]).status == "CHECK"


def test_a_language_item_replaces_the_generic_other_conditions_check():
    verdict = run(ArtistProfile(languages=["fr"]), [chunk(0, "Applicants must be proficient in French or English.",
                                                          "OTHER_ELIGIBILITY")])
    assert [(i.label, i.outcome) for i in verdict.items] == [("LANGUAGE", "PASS")]


def test_a_sentence_with_age_and_language_gets_both_items():
    text = "Applicants must be over 18 years of age and be proficient in French or English."
    verdict = run(ArtistProfile(languages=["en"]), [chunk(0, text, "AGE")])
    assert {i.label for i in verdict.items} == {"AGE", "LANGUAGE"}


def test_profile_languages_are_normalised_and_checked():
    assert ArtistProfile(languages=["EN", "it", "en"]).languages == ["en", "it"]
    with pytest.raises(ValueError):
        ArtistProfile(languages=["xx"])


@pytest.mark.parametrize("text, section, expected", [
    ("Hungarian (native), German (fluent), English (fluent)", "LANGUAGES", ["de", "en", "hu"]),
    ("Languages: Italian (mother tongue), English (C1), Spanish (A2)", None, ["en", "it"]),
    ("Italian - native\nEnglish - professional\nGerman - basic", "Languages", ["en", "it"]),
    ("Speaks Italian and English", None, None),   # not a Languages section or line
])
def test_cv_languages(text, section, expected):
    found = {s.field: s.value for s in extract_profile([Chunk(index=0, section=section, text=text, page=None)],
                                                       "cv.txt", date(2026, 10, 8))}
    assert found.get("languages") == expected
