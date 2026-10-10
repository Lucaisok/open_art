"""Tests for where the artist studied (src/eligibility/study.py) and how the engine uses it: unreviewed
EDUCATION sentences, "any one of" alternatives in reviews, and graduates of a named school.
Run with: uv run pytest"""

from datetime import date

import pytest

from src.eligibility.engine import Review, evaluate_chunks
from src.eligibility.profile import ArtistProfile
from src.eligibility.study import EducationEntry, parse_study, study_check
from src.models.classified_chunk import ClassifiedChunk

VIENNA = EducationEntry(institution="Academy of Fine Arts Vienna", country="AT")
GHENT = EducationEntry(institution="KASK School of Arts", city="Ghent", country="BE")
VILLA = EducationEntry(institution="Villa Arson", city="Nice", country="FR")


@pytest.mark.parametrize("text, expected", [
    ("have studied or are studying at a Flemish or Brussels Conservatoire.",
     {"study_places": ["Brussels", "Flanders"], "study_countries": ["BE"]}),
    ("The call is open to artists who graduated from Villa Arson less than three years ago.",
     {"institutions": ["Villa Arson"]}),
    ("or study at an educational institution in Norway.", {"study_countries": ["NO"]}),
    # no place of study
    ("Individual persons with Austrian citizenship; associations, institutions or other legal entities", None),
    ("Applicants with a connection to NRW must have completed a university degree (Master or Diplom).", None),
])
def test_parse_study(text, expected):
    assert parse_study(text) == expected


def test_a_school_matches_by_name_then_place_then_country():
    assert study_check({"institutions": ["Villa Arson"]}, [VIENNA, VILLA])[0] is True
    assert study_check({"study_places": ["Flanders"], "study_countries": ["BE"]}, [GHENT])[0] is True  # Ghent
    assert study_check({"study_places": ["Flanders"], "study_countries": ["BE"]}, [VIENNA])[0] is False
    assert study_check({"study_countries": ["AT"]}, [VIENNA])[0] is True
    assert "not in your profile" in study_check({"study_countries": ["AT"]}, [])[1]


def chunk(text, label, polarity="REQUIRES"):
    return ClassifiedChunk(opportunity_id="opp", chunk_id="opp_0", chunk_index=0, text=text, is_heading=False,
                           label=label, confidence=0.9, polarity=polarity, model_trained_on="test")


def run(profile, chunks, reviews=None):
    return evaluate_chunks(profile, chunks, reviews or {}, opportunity_id="opp", today=date(2026, 10, 1))


def test_an_education_sentence_about_a_place_passes_or_stays_a_check():
    text = "have studied or are studying at a Flemish or Brussels Conservatoire."
    assert run(ArtistProfile(education=[GHENT]), [chunk(text, "EDUCATION")]).status == "ELIGIBLE"
    verdict = run(ArtistProfile(education=[VIENNA]), [chunk(text, "EDUCATION")])
    assert verdict.status == "CHECK"   # never a fail: a CV can leave a school out
    assert "Brussels or Flanders" in verdict.items[0].reason


def test_education_as_an_alternative_lets_the_artist_in():
    text = "You have a link to Belgium: either by residence, education or nationality."
    value = {"any_of": [{"label": "RESIDENCE", "countries": ["BE"]}, {"label": "NATIONALITY", "countries": ["BE"]},
                        {"label": "EDUCATION", "study_countries": ["BE"]}]}
    reviews = {(text, "RESIDENCE"): Review(label="RESIDENCE", decision="fix", polarity="REQUIRES", value=value,
                                           reason=None)}
    berlin = dict(nationalities=["IT"], residence_country="DE")
    assert run(ArtistProfile(**berlin, education=[GHENT]), [chunk(text, "RESIDENCE")], reviews).status == "ELIGIBLE"
    # no Belgian school in the profile: the education alternative is never certain, so a check, not a fail
    verdict = run(ArtistProfile(**berlin, education=[VIENNA]), [chunk(text, "RESIDENCE")], reviews)
    assert verdict.status == "CHECK"
    assert "studies at / in Belgium" in verdict.items[0].reason


def test_graduates_of_a_named_school():
    text = "The call is open to artists who graduated from Villa Arson less than three years ago."
    value = {"graduated_within_years": 3, "institutions": ["Villa Arson"]}
    reviews = {(text, "STUDENT_STATUS"): Review(label="STUDENT_STATUS", decision="fix", polarity="REQUIRES",
                                                value=value, reason=None)}
    alumna = ArtistProfile(graduation_year=2024, education=[VILLA])
    assert run(alumna, [chunk(text, "STUDENT_STATUS")], reviews).status == "ELIGIBLE"
    other_school = ArtistProfile(graduation_year=2024, education=[VIENNA])
    assert run(other_school, [chunk(text, "STUDENT_STATUS")], reviews).status == "CHECK"
    graduated_long_ago = ArtistProfile(graduation_year=2010, education=[VILLA])
    assert run(graduated_long_ago, [chunk(text, "STUDENT_STATUS")], reviews).status == "LIKELY_NOT_ELIGIBLE"


def test_profile_schools_are_tidied_and_checked():
    profile = ArtistProfile(education=[{"institution": "  Villa Arson ", "city": " ", "country": "fr"}])
    assert profile.education == [EducationEntry(institution="Villa Arson", city=None, country="FR")]
    with pytest.raises(ValueError):
        ArtistProfile(education=[{"institution": "   "}])
