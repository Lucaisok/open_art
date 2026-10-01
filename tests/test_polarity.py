"""Tests for src/eligibility/polarity.py. Most cases are real sentences from
the labeled data (see workflow.MD, step 3). Run with: uv run pytest"""

import pytest

from src.eligibility.polarity import EXCLUDES, REQUIRES, UNCLEAR, WAIVES, polarity


@pytest.mark.parametrize("text, label, expected", [
    # plain requirements
    ("Applicants must be resident in Belgium.", "RESIDENCE", REQUIRES),
    ("Open to students enrolled in a master's programme.", "STUDENT_STATUS", REQUIRES),
    # exclusions
    ("students are excluded from applying", "STUDENT_STATUS", EXCLUDES),
    ("Applicants cannot be enrolled in study programmes.", "STUDENT_STATUS", EXCLUDES),
    ("Entities that have signed an addendum are not admitted to the tender procedure.", "PRIOR_FUNDING", EXCLUDES),
    ("Unfortunately, we cannot support applications from applicants outside of state-maintained schools.",
     "APPLICANT_TYPE", EXCLUDES),
    # waivers of the sentence's own class
    ("There is no age limit.", "AGE", WAIVES),
    ("although you do not need to be a Nordic or Baltic citizen.", "NATIONALITY", WAIVES),
    # ... but a waiver of ANOTHER class doesn't lift this one
    ("PhD candidates and emerging artists of any age may apply.", "CAREER_STAGE", REQUIRES),
    ("It is open to candidates of all nationalities residing within the European Union.", "RESIDENCE", REQUIRES),
    # hedged or mixed -> the engine must not reject on it
    ("Applicants who receive fixed annual state grants are normally not awarded grants from this scheme.",
     "PRIOR_FUNDING", UNCLEAR),
    ("Your practice does not have to be your main source of income, but you must work professionally.",
     "CAREER_STAGE", UNCLEAR),
    # mixed / conditional sentences from the corpus spot check (v2): reading the
    # first one as EXCLUDES would reject the adults it asks for
    ("Project leaders must be of legal age, capable of acting, and must not be subject to any of the prohibitions.",
     "AGE", UNCLEAR),
    ("Events featuring artists from at least 3 African countries (excluding the applicant's country of residence).",
     "RESIDENCE", UNCLEAR),
    ("The applicant does not need to be resident in the Nordic Region, as long as the Nordic dimension is met.",
     "RESIDENCE", UNCLEAR),
    ("Students are not granted mobility funding.", "STUDENT_STATUS", EXCLUDES),
    ("You are not (or no longer) studying.", "STUDENT_STATUS", EXCLUDES),
    ("Applicants still in education (with the exception of doctoral candidates) are excluded.",
     "STUDENT_STATUS", UNCLEAR),
    ("Individual artists should instead apply to the grant scheme for project support.", "APPLICANT_TYPE", EXCLUDES),
    # negations that don't exclude anyone
    ("Those eligible include but are not limited to: visual artists and curators.", "DISCIPLINE", REQUIRES),
    ("The applicant's total taxable income must not be higher than € 55,000.", "OTHER_ELIGIBILITY", REQUIRES),
    ("Able to commute to our studio (we can't provide accommodation).", "RESIDENCE", REQUIRES),
    # "generally" in a legal form name is not a hedge
    ("The applicant must be a non-profit organization providing generally beneficial services.",
     "APPLICANT_TYPE", REQUIRES),
])
def test_polarity(text, label, expected):
    assert polarity(text, label=label) == expected


def test_negative_heading_turns_a_list_item_into_an_exclusion():
    assert polarity("Students.", heading="Who may not apply?", label="STUDENT_STATUS") == EXCLUDES
    assert polarity("Students.", heading="Who can apply?", label="STUDENT_STATUS") == REQUIRES


def test_without_a_label_every_waiver_counts():
    assert polarity("Emerging artists of any age.") == WAIVES
