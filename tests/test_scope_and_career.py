"""Tests for the "conclusive verdicts" layers (workflow.MD): scope (src/eligibility/scope.py), career stage and
education (src/eligibility/career.py), structured reviews with alternatives / applies_to / broad regions in the
engine, and the page's two extra lists. Run with: uv run pytest"""

from datetime import date

import pytest

from api.discover import verdict_out
from src.eligibility.career import career_check, education_check, parse_career, parse_education
from src.eligibility.engine import Review, evaluate_chunks
from src.eligibility.geo import broad_regions_named
from src.eligibility.profile import ArtistProfile
from src.eligibility.scope import scope
from src.models.classified_chunk import ClassifiedChunk

TODAY = date(2026, 10, 1)
BERLIN = ArtistProfile(birth_date=date(1990, 3, 1), nationalities=["IT"], residence_country="DE",
                       applicant_type="individual", disciplines=["Visual Arts"], career_stage="Mid-Career",
                       years_active=12, has_degree=True)


def chunk(index, text, label, polarity="REQUIRES", **extra):
    return ClassifiedChunk(opportunity_id="opp", chunk_id=f"opp_{index}", chunk_index=index, text=text,
                           is_heading=False, label=label, confidence=0.9, polarity=polarity,
                           model_trained_on="test", **extra)


def run(profile, chunks, reviews=None):
    return evaluate_chunks(profile, chunks, reviews or {}, opportunity_id="opp", today=TODAY)


# -- scope -------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text, heading, expected", [
    ("Participation in the lab sessions must be in person and for the entire duration of the programme.", None,
     "OBLIGATION"),
    ("Projects must take place in Belgium, unless they involve virtual collaboration.", None, "PROJECT"),
    ("Charities or not-for-profit organisations", "Partners can include:", "PROJECT"),
    ("Students with a minority background are encouraged to apply.", None, "PREFERENCE"),
    ("Group applications (duo, collective) are accepted.", None, "WIDENING"),
    ("In this context, Norway, Denmark and Sweden are considered as Nordic countries.", None, "NOT_A_CONDITION"),
    # a hard condition on the applicant keeps a sentence APPLICANT
    ("Applicants must be resident in Norway.", None, "APPLICANT"),
    ("Projects by artists resident in Flanders only.", None, "APPLICANT"),
    ("Work grant (target language German)", None, "APPLICANT"),
])
def test_scope(text, heading, expected):
    assert scope(text, heading) == expected


def test_a_project_sentence_is_listed_apart_and_never_a_check():
    verdict = run(BERLIN, [chunk(0, "Projects must take place in Belgium.", "OTHER_ELIGIBILITY"),
                           chunk(1, "The selected artist will present their work at the end of the residency.",
                                 "OTHER_ELIGIBILITY"),
                           chunk(2, "Open to visual artists.", "DISCIPLINE")])
    assert [i.outcome for i in verdict.items] == ["INFO", "INFO", "PASS"]
    assert verdict.status == "ELIGIBLE"
    out = verdict_out(verdict)
    assert out.about_project == ["Projects must take place in Belgium."]
    assert out.commitments == ["The selected artist will present their work at the end of the residency."]
    assert [s.quote for s in out.sentences] == ["Open to visual artists."]


def test_a_call_with_only_project_notes_still_says_no_requirements_found():
    verdict = run(BERLIN, [chunk(0, "Projects must take place in Belgium.", "OTHER_ELIGIBILITY")])
    assert verdict.status == "CHECK" and "No eligibility requirements" in verdict.summary


# -- career stage and education ----------------------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("Applicants must have been professionally active for at least three years.", {"min_years": 3}),
    ("Artist Start grants are for visual artists who have been working professionally for at least 1 and no "
     "more than 4 years.", {"min_years": 1, "max_years": 4}),
    ("This call is aimed at emerging artists.", {"stages": ["Emerging/Early-Career"]}),
    ("Open to emerging and mid career visual artists.", {"any_stage": True}),
    ("Applicant organisations must have been in existence for a minimum of three years.", None),
    ("The completion of the artistic training must not be more than five years in the past.", None),
])
def test_parse_career(text, expected):
    assert parse_career(text) == expected


def test_career_passes_only_when_clearly_met():
    assert career_check({"min_years": 3}, BERLIN)[0] is True
    assert career_check({"min_years": 12}, BERLIN)[0] is False      # exactly on the limit: not certain
    assert career_check({"max_years": 4}, BERLIN)[0] is False
    assert career_check({"stages": ["Emerging/Early-Career"]}, BERLIN)[0] is False
    assert career_check({"min_years": 3}, ArtistProfile())[0] is False


def test_career_and_education_never_fail():
    verdict = run(BERLIN, [chunk(0, "This call is aimed at emerging artists.", "CAREER_STAGE"),
                           chunk(1, "Applicants must hold a degree.", "EDUCATION")])
    assert [i.outcome for i in verdict.items] == ["CHECK", "PASS"]
    assert verdict.status == "CHECK"
    assert "your profile says Mid-Career" in verdict.items[0].reason


def test_education():
    assert parse_education("Applicants must hold a bachelor's degree.") == {"degree": True}
    assert parse_education("A master's degree in fine arts is required.") is None   # a field the profile can't check
    assert parse_education("Projects proposed by the French diplomatic representations.") is None  # not "diploma"
    assert education_check({"degree": True}, BERLIN)[0] is True


# -- structured reviews ------------------------------------------------------------------------------------

def review(label, value, polarity="REQUIRES", decision="fix", **extra):
    return Review(label=label, decision=decision, polarity=polarity, value=value, reason=None, **extra)


def test_alternatives_pass_on_any_and_fail_only_on_none():
    text = "You have a link to Belgium: either by residence, education or nationality."
    value = {"any_of": [{"label": "RESIDENCE", "countries": ["BE"]}, {"label": "NATIONALITY", "countries": ["BE"]},
                        {"label": "EDUCATION", "also_requires": "education in Belgium"}]}
    reviews = {(text, "RESIDENCE"): review("RESIDENCE", value)}
    belgian = ArtistProfile(nationalities=["FR"], residence_country="BE")
    assert run(belgian, [chunk(0, text, "RESIDENCE")], reviews).status == "ELIGIBLE"
    # outside the checkable alternatives, but they may have studied in Belgium: a check, never a fail
    assert run(BERLIN, [chunk(0, text, "RESIDENCE")], reviews).status == "CHECK"
    value = {"any_of": [{"label": "RESIDENCE", "countries": ["BE"]}, {"label": "NATIONALITY", "countries": ["BE"]}]}
    reviews = {(text, "RESIDENCE"): review("RESIDENCE", value)}
    assert run(BERLIN, [chunk(0, text, "RESIDENCE")], reviews).status == "LIKELY_NOT_ELIGIBLE"


def test_a_condition_on_organisations_does_not_concern_an_individual():
    text = "Organisations must be registered in Norway."
    reviews = {(text, "RESIDENCE"): review("RESIDENCE", {"countries": ["NO"]}, applies_to=["organisation"])}
    assert run(BERLIN, [chunk(0, text, "RESIDENCE")], reviews).items[0].outcome == "NO_RESTRICTION"
    company = ArtistProfile(residence_country="SE", applicant_type="organisation")
    assert run(company, [chunk(0, text, "RESIDENCE")], reviews).status == "LIKELY_NOT_ELIGIBLE"


def test_a_review_scope_hides_the_sentence_from_the_verdict():
    text = "Partnerships must involve at least one organisation from Ukraine."
    reviews = {(text, "RESIDENCE"): review("RESIDENCE", None, polarity="", decision="scope", scope="PROJECT")}
    verdict = run(BERLIN, [chunk(0, text, "RESIDENCE")], reviews)
    assert verdict.items[0].outcome == "INFO" and verdict.items[0].scope == "PROJECT"


def test_broad_regions_only_let_an_artist_in():
    text = "1 artist residing in Europe"
    reviews = {(text, "RESIDENCE"): review("RESIDENCE", {"countries": [], "broad_regions": ["Europe"]})}
    assert run(BERLIN, [chunk(0, text, "RESIDENCE")], reviews).status == "ELIGIBLE"
    brazil = ArtistProfile(residence_country="BR")
    assert run(brazil, [chunk(0, text, "RESIDENCE")], reviews).status == "CHECK"   # never a fail


def test_broad_regions_named():
    assert broad_regions_named("artists from Ukraine and across Europe") == ["Europe"]
    assert broad_regions_named("open to applicants from all over the world") == ["worldwide"]
    assert broad_regions_named("open to non-European artists") == []
    assert broad_regions_named("artists based in South Africa") == []
