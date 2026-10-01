"""Tests for src/eligibility/engine.py and src/eligibility/profile.py. Run with: uv run pytest"""

import json
from datetime import date

import pytest
from pydantic import ValidationError

from src.eligibility.engine import (
    EligibilityEngine,
    Review,
    evaluate_chunks,
    load_reviews,
)
from src.eligibility.profile import ArtistProfile
from src.models.classified_chunk import ClassifiedChunk
from src.models.processed_opportunity import ProcessedOpportunity

TODAY = date(2026, 10, 1)


# -- helpers: build a call sentence by sentence, with its review rows --------------------------------------

def chunk(index, text, label, polarity="REQUIRES", confidence=0.95, **extra) -> ClassifiedChunk:
    return ClassifiedChunk(opportunity_id="opp", chunk_id=f"opp_{index}", chunk_index=index, text=text,
                           is_heading=False, label=label, confidence=confidence, polarity=polarity,
                           model_trained_on="test", **extra)


def reviewed(text, label, value, polarity="REQUIRES", decision="confirm") -> tuple[str, Review]:
    return text, Review(label=label, decision=decision, polarity=polarity, value=value, reason=None)


def run(profile, chunks, reviews=(), deadline=None):
    return evaluate_chunks(profile, chunks, dict(reviews), opportunity_id="opp",
                           source_url="https://example.org/call", deadline=deadline, today=TODAY)


def one(profile, label, value, polarity="REQUIRES", deadline=None):
    """A call with a single reviewed sentence -> (item outcome, verdict status)."""
    text = f"{label} sentence"
    verdict = run(profile, [chunk(0, text, label, polarity)], [reviewed(text, label, value, polarity)], deadline)
    return verdict.items[0].outcome, verdict.status


BELGIAN = ArtistProfile(birth_date=date(1998, 3, 1), nationalities=["BE"], residence_country="BE",
                        applicant_type="individual", currently_enrolled=False, graduation_year=2021)
EMPTY = ArtistProfile()


# -- what is ignored, what is always CHECK ------------------------------------------------------------------

def test_headings_none_and_waivers_never_count_against_the_artist():
    heading = ClassifiedChunk(opportunity_id="opp", chunk_id="opp_0", chunk_index=0, text="Who can apply?",
                              is_heading=True, model_trained_on="test")
    chunks = [heading,
              chunk(1, "The residency lasts three months.", "NONE", polarity=None),
              chunk(2, "There is no age limit.", "AGE", polarity="WAIVES")]
    verdict = run(BELGIAN, chunks)
    assert [i.outcome for i in verdict.items] == ["NO_RESTRICTION"]
    assert verdict.items[0].reason == "no restriction on age"
    assert verdict.status == "ELIGIBLE"
    assert verdict.summary == "Nothing in this call rules you out."
    assert verdict.source_url == "https://example.org/call"


def test_a_call_with_no_requirements_says_so():
    verdict = run(BELGIAN, [chunk(0, "Deadline: 1 December.", "NONE", polarity=None)])
    assert verdict.status == "ELIGIBLE" and verdict.items == []
    assert "No eligibility requirements were found" in verdict.summary


def test_safety_net_sentence_is_a_check():
    flagged = chunk(0, "for artists based in Ukraine and across Europe", "NONE", polarity="REQUIRES",
                    suspected_label="RESIDENCE", safety_net_reason='keyword "based in"')
    verdict = run(BELGIAN, [flagged])
    assert verdict.status == "CHECK"
    assert verdict.items[0].label == "RESIDENCE" and 'keyword "based in"' in verdict.items[0].reason


@pytest.mark.parametrize("label", ["DISCIPLINE", "CAREER_STAGE", "EDUCATION", "PRIOR_FUNDING", "OTHER_ELIGIBILITY"])
def test_check_only_classes_never_reject(label):
    # even an exclusion with a review row can't reject: these classes are never verified automatically
    text = "Not eligible: anyone who does not fit."
    verdict = run(BELGIAN, [chunk(0, text, label, polarity="EXCLUDES")],
                  [reviewed(text, label, {"types": ["individual"]}, "EXCLUDES")])
    assert verdict.status == "CHECK" and verdict.items[0].outcome == "CHECK"


def test_unreviewed_sentence_is_a_check():
    verdict = run(BELGIAN, [chunk(0, "Applicants must be based in Norway.", "RESIDENCE")])
    assert verdict.status == "CHECK" and "not reviewed" in verdict.items[0].reason


def test_dropped_review_is_a_check():
    text = "Applicants with a link to Belgium (residence, education or nationality)."
    verdict = run(ArtistProfile(residence_country="NO"), [chunk(0, text, "RESIDENCE")],
                  [reviewed(text, "RESIDENCE", None, polarity=None, decision="drop")])
    assert verdict.status == "CHECK" and verdict.items[0].review == "drop"


def test_review_for_a_different_label_does_not_count():
    # the model was retrained and now labels the sentence differently: the review no longer applies
    text = "Open to artists living in Norway."
    verdict = run(ArtistProfile(residence_country="BE"), [chunk(0, text, "NATIONALITY")],
                  [reviewed(text, "RESIDENCE", {"countries": ["NO"]})])
    assert verdict.status == "CHECK"


def test_low_confidence_is_a_check_even_when_reviewed():
    text = "Open to artists living in Norway."
    verdict = run(ArtistProfile(residence_country="BE"), [chunk(0, text, "RESIDENCE", confidence=0.6)],
                  [reviewed(text, "RESIDENCE", {"countries": ["NO"]})])
    assert verdict.status == "CHECK"


def test_reviewed_polarity_overrides_the_parsed_one():
    # parsed as REQUIRES, review fixed it to EXCLUDES ("Applications from students are not possible.")
    text = "Applications from students are not possible."
    verdict = run(ArtistProfile(currently_enrolled=True), [chunk(0, text, "STUDENT_STATUS", polarity="REQUIRES")],
                  [reviewed(text, "STUDENT_STATUS", {"enrolled": True}, "EXCLUDES", decision="fix")])
    assert verdict.status == "LIKELY_NOT_ELIGIBLE" and verdict.items[0].polarity == "EXCLUDES"


# -- per class --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("birth, value, deadline, expected", [
    (date(1998, 3, 1), {"max_age": 34}, None, "PASS"),                     # 28
    (date(1980, 1, 1), {"max_age": 34}, None, "FAIL"),                     # 46
    (date(1998, 3, 1), {"min_age": 18, "max_age": 30}, date(2026, 12, 1), "PASS"),
    # 34 today, 35 on the deadline: depends on which date the call counts -> CHECK, not FAIL
    (date(1991, 11, 1), {"max_age": 34}, date(2026, 12, 1), "CHECK"),
    # too old on both dates -> certain
    (date(1990, 1, 1), {"max_age": 34}, date(2026, 12, 1), "FAIL"),
    # 17 today, deadline unknown: may be 18 by the time they apply
    (date(2009, 3, 1), {"min_age": 18}, None, "CHECK"),
    # 17 today and still 17 on the known deadline -> certain
    (date(2009, 3, 1), {"min_age": 18}, date(2026, 12, 1), "FAIL"),
    # deadline already passed: only the age on the deadline counts (35 then, 36 now)
    (date(1990, 6, 1), {"max_age": 35}, date(2026, 1, 1), "PASS"),
])
def test_age(birth, value, deadline, expected):
    assert one(ArtistProfile(birth_date=birth), "AGE", value, deadline=deadline)[0] == expected


@pytest.mark.parametrize("profile, label, value, expected", [
    (BELGIAN, "NATIONALITY", {"countries": ["BE", "NL"]}, "PASS"),
    (BELGIAN, "NATIONALITY", {"countries": ["AT"]}, "FAIL"),
    (ArtistProfile(nationalities=["IT", "AT"]), "NATIONALITY", {"countries": ["AT"]}, "PASS"),  # dual citizen
    (BELGIAN, "RESIDENCE", {"countries": ["NO", "SE"]}, "FAIL"),
    (BELGIAN, "RESIDENCE", {"countries": ["BE"]}, "PASS"),
    # nationality OR residence: either one is enough
    (ArtistProfile(nationalities=["IT"], residence_country="AT"), "NATIONALITY",
     {"countries": ["AT"], "nationality_or_residence": True}, "PASS"),
    (ArtistProfile(nationalities=["IT"], residence_country="BE"), "NATIONALITY",
     {"countries": ["AT"], "nationality_or_residence": True}, "FAIL"),
    # ... but with one of the two unknown, a non-match on the other is not certain
    (ArtistProfile(nationalities=["IT"]), "RESIDENCE",
     {"countries": ["AT"], "nationality_or_residence": True}, "CHECK"),
])
def test_countries(profile, label, value, expected):
    assert one(profile, label, value)[0] == expected


@pytest.mark.parametrize("applicant_type, polarity, expected", [
    ("individual", "REQUIRES", "PASS"),
    ("organisation", "REQUIRES", "FAIL"),
    ("organisation", "EXCLUDES", "PASS"),
    ("individual", "EXCLUDES", "FAIL"),
])
def test_applicant_type(applicant_type, polarity, expected):
    profile = ArtistProfile(applicant_type=applicant_type)
    assert one(profile, "APPLICANT_TYPE", {"types": ["individual", "group"]}, polarity)[0] == expected


@pytest.mark.parametrize("profile, value, polarity, expected", [
    (ArtistProfile(currently_enrolled=True), {"enrolled": True}, "EXCLUDES", "FAIL"),   # "Students are excluded."
    (ArtistProfile(currently_enrolled=False), {"enrolled": True}, "EXCLUDES", "PASS"),
    (ArtistProfile(currently_enrolled=False), {"enrolled": True}, "REQUIRES", "FAIL"),
    (ArtistProfile(graduation_year=2025), {"graduated_within_years": 3}, "REQUIRES", "PASS"),
    (ArtistProfile(graduation_year=2020), {"graduated_within_years": 3}, "REQUIRES", "FAIL"),
    # graduated exactly 3 calendar years ago: within 3 years or not depends on the month
    (ArtistProfile(graduation_year=2023), {"graduated_within_years": 3}, "REQUIRES", "CHECK"),
])
def test_student_status(profile, value, polarity, expected):
    assert one(profile, "STUDENT_STATUS", value, polarity)[0] == expected


# -- missing profile fields -------------------------------------------------------------------------------

@pytest.mark.parametrize("label, value", [
    ("AGE", {"max_age": 34}),
    ("NATIONALITY", {"countries": ["AT"]}),
    ("RESIDENCE", {"countries": ["NO"]}),
    ("APPLICANT_TYPE", {"types": ["organisation"]}),
    ("STUDENT_STATUS", {"enrolled": True}),
    ("STUDENT_STATUS", {"graduated_within_years": 3}),
])
@pytest.mark.parametrize("polarity", ["REQUIRES", "EXCLUDES"])
def test_missing_profile_field_is_a_check_never_a_reject(label, value, polarity):
    assert one(EMPTY, label, value, polarity) == ("CHECK", "CHECK")


def test_empty_profile_is_never_rejected_by_any_reviewed_sentence():
    # every real review row, one sentence at a time: with nothing in the profile, none may reject
    reviews = load_reviews()
    chunks = [chunk(i, text, review.label) for i, (text, review) in enumerate(reviews.items())]
    for c in chunks:
        verdict = run(EMPTY, [c], reviews)
        assert verdict.status != "LIKELY_NOT_ELIGIBLE", c.text


# -- also_requires (the narrower set) ---------------------------------------------------------------------

NRW = {"countries": ["DE"], "also_requires": "North Rhine-Westphalia"}


@pytest.mark.parametrize("residence, polarity, expected", [
    ("BE", "REQUIRES", "FAIL"),    # outside Germany -> certainly outside NRW
    ("DE", "REQUIRES", "CHECK"),   # in Germany, but maybe not in NRW
    ("DE", "EXCLUDES", "CHECK"),   # an exclusion of part of Germany may not cover them
    ("BE", "EXCLUDES", "PASS"),    # outside the excluded set altogether
])
def test_also_requires(residence, polarity, expected):
    outcome, _ = one(ArtistProfile(residence_country=residence), "RESIDENCE", NRW, polarity)
    assert outcome == expected


def test_exclusion_of_specific_organisations_does_not_reject_every_organisation():
    value = {"types": ["organisation"], "also_requires": "large institutional theatres"}
    assert one(ArtistProfile(applicant_type="organisation"), "APPLICANT_TYPE", value, "EXCLUDES")[0] == "CHECK"


# -- OR groups --------------------------------------------------------------------------------------------

def bullet_list(*parts):
    """Sentences + review rows for a list of reviewed sentences, adjacent in one call."""
    chunks, reviews = [], []
    for i, (text, label, value, *polarity) in enumerate(parts):
        p = polarity[0] if polarity else "REQUIRES"
        chunks.append(chunk(i, text, label, p))
        reviews.append(reviewed(text, label, value, p))
    return chunks, reviews


def test_bullet_list_is_an_or_group():
    chunks, reviews = bullet_list(("• Individuals", "APPLICANT_TYPE", {"types": ["individual"]}),
                                  ("• Organisations", "APPLICANT_TYPE", {"types": ["organisation"]}))
    verdict = run(ArtistProfile(applicant_type="organisation"), chunks, reviews)
    assert [i.outcome for i in verdict.items] == ["FAIL", "PASS"]
    assert {i.group_outcome for i in verdict.items} == {"PASS"}
    assert verdict.status == "ELIGIBLE"


def test_nationality_then_residence_is_an_or_group():
    chunks, reviews = bullet_list(("Citizens of Austria", "NATIONALITY", {"countries": ["AT"]}),
                                  ("or residents of Austria", "RESIDENCE", {"countries": ["AT"]}))
    resident = ArtistProfile(nationalities=["IT"], residence_country="AT")
    assert run(resident, chunks, reviews).status == "ELIGIBLE"
    outsider = ArtistProfile(nationalities=["IT"], residence_country="IT")
    assert run(outsider, chunks, reviews).status == "LIKELY_NOT_ELIGIBLE"   # every member fails


def test_sentences_apart_are_not_grouped():
    chunks, reviews = bullet_list(("Individuals only", "APPLICANT_TYPE", {"types": ["individual"]}),
                                  ("The residency lasts a month.", "NONE", None),
                                  ("Organisations may apply", "APPLICANT_TYPE", {"types": ["organisation"]}))
    chunks[1] = chunk(1, "The residency lasts a month.", "NONE", polarity=None)
    verdict = run(ArtistProfile(applicant_type="organisation"), chunks, reviews)
    assert verdict.status == "LIKELY_NOT_ELIGIBLE"
    assert all(i.group is None for i in verdict.items)


def test_group_with_a_check_and_fails_is_a_check():
    chunks, reviews = bullet_list(("Individuals", "APPLICANT_TYPE", {"types": ["individual"]}))
    chunks.append(chunk(1, "Organisations registered in Norway", "APPLICANT_TYPE"))   # not reviewed
    verdict = run(ArtistProfile(applicant_type="organisation"), chunks, reviews)
    assert verdict.status == "CHECK"


def test_a_stated_exclusion_is_not_overruled_by_its_group():
    # "Residents of the Nordic countries can apply. Residents of Iceland cannot." -> an Icelander
    chunks, reviews = bullet_list(
        ("Residents of the Nordic countries", "RESIDENCE", {"countries": ["DK", "FI", "IS", "NO", "SE"]}),
        ("Residents of Iceland cannot apply", "RESIDENCE", {"countries": ["IS"]}, "EXCLUDES"))
    verdict = run(ArtistProfile(residence_country="IS"), chunks, reviews)
    assert [i.outcome for i in verdict.items] == ["PASS", "FAIL"]
    assert verdict.status == "CHECK"


def test_not_being_excluded_is_not_meeting_an_alternative():
    # corpus case: "Private legal entities … may apply" + "Private foundations with other ongoing
    # funding are excluded" -> a person fails the first and is merely not excluded by the second
    chunks, reviews = bullet_list(
        ("Private legal entities with headquarters in the Alentejo region", "APPLICANT_TYPE",
         {"types": ["organisation"]}),
        ("Private foundations that have another type of ongoing funding are excluded", "APPLICANT_TYPE",
         {"types": ["organisation"], "also_requires": "foundations with other ongoing funding"}, "EXCLUDES"))
    verdict = run(ArtistProfile(applicant_type="individual"), chunks, reviews)
    assert [i.outcome for i in verdict.items] == ["FAIL", "PASS"]
    assert verdict.status == "CHECK"


# -- verdict ----------------------------------------------------------------------------------------------

def test_fail_beats_check_and_is_quoted():
    chunks, reviews = bullet_list(("Applicants must live in Norway.", "RESIDENCE", {"countries": ["NO"]}))
    chunks.append(chunk(1, "Applicants must be professional artists.", "CAREER_STAGE"))
    verdict = run(BELGIAN, chunks, reviews)
    assert verdict.status == "LIKELY_NOT_ELIGIBLE"
    assert '"Applicants must live in Norway."' in verdict.summary
    assert len(verdict.items) == 2                        # every item is listed, not only the deciding one
    assert [i.text for i in verdict.deciding_items] == ["Applicants must live in Norway."]


# -- profile ----------------------------------------------------------------------------------------------

def test_profile_normalizes_and_validates_countries():
    assert ArtistProfile(nationalities=["be", "BE", "nl"], residence_country="no").model_dump()["nationalities"] == ["BE", "NL"]
    with pytest.raises(ValidationError):
        ArtistProfile(residence_country="Belgium")
    with pytest.raises(ValidationError):
        ArtistProfile(disciplines=["Painting"])            # not a canonical discipline


# -- loading the two files --------------------------------------------------------------------------------

def test_engine_reads_the_files(tmp_path):
    text = "Only artists based in Belgium are eligible"
    constraints = tmp_path / "constraints.jsonl"
    constraints.write_text(chunk(0, text, "RESIDENCE").model_dump_json() + "\n", encoding="utf-8")
    review_file = tmp_path / "reviewed.csv"
    review_file.write_text(
        "chunk_text,label,decision,polarity,value,reason\n"
        f'{text},RESIDENCE,confirm,REQUIRES,"{json.dumps({"countries": ["BE"]}).replace(chr(34), chr(34) * 2)}",\n',
        encoding="utf-8")
    engine = EligibilityEngine(str(constraints), str(review_file))

    def opportunity(opp_id):
        return ProcessedOpportunity(id=opp_id, source="test", source_url="https://example.org", language="en",
                                    title="t", requirements_text="r", title_en="t", requirements_text_en="r",
                                    processed_at="2026-10-01T00:00:00")

    assert engine.evaluate(ArtistProfile(residence_country="NO"), opportunity("opp")).status == "LIKELY_NOT_ELIGIBLE"
    assert engine.evaluate(ArtistProfile(residence_country="BE"), opportunity("opp")).status == "ELIGIBLE"
    # a call that was never classified is not silently ELIGIBLE
    assert engine.evaluate(BELGIAN, opportunity("unknown")).status == "CHECK"
