"""Tests for src/eligibility/values.py. Run with: uv run pytest"""

import pytest

from scripts.evaluate_values import evaluate
from src.eligibility.values import parse_value


@pytest.mark.parametrize("label, text, expected", [
    # AGE
    ("AGE", "Under 35 years old at the time of the application.", {"max_age": 34}),
    ("AGE", "be between 25 and 40 years old at the closing of the call", {"min_age": 25, "max_age": 40}),
    ("AGE", "Auditions are open to young artists aged 14 to 21: dancers, actors.", {"min_age": 14, "max_age": 21}),
    ("AGE", "aged 18–26 years.", {"min_age": 18, "max_age": 26}),
    ("AGE", "Age limit: up to 45 years old ( born after the 1st of July 1982 ).", {"max_age": 45}),
    ("AGE", "The candidate must be over 18 years old at the time of application", {"min_age": 18}),
    ("AGE", "Eligibility: Persons of legal age", {"min_age": 18}),
    ("AGE", "for learners aged 3 – 16 years.", None),                         # the audience's age
    ("AGE", "ensembles with a maximum average age of 35.", None),             # not per person
    # NATIONALITY / RESIDENCE
    ("NATIONALITY", "Artists who hold Austrian citizenship.", {"countries": ["AT"]}),
    ("RESIDENCE", "you must be a resident of the Nordic Region (Denmark, Finland, the Faroe Islands, "
                  "Greenland, Iceland, Norway, Sweden, or Åland) or the Baltic countries (Estonia, Latvia, or Lithuania)",
     {"countries": ["AX", "DK", "EE", "FI", "FO", "GL", "IS", "LT", "LV", "NO", "SE"]}),
    ("RESIDENCE", "artists with their primary residence in North Rhine-Westphalia",
     {"countries": ["DE"], "also_requires": "North Rhine-Westphalia"}),
    ("RESIDENCE", "1 artist residing in Europe", None),                       # no member list
    ("RESIDENCE", "for artists based in Ukraine and across Europe", None),    # list would be incomplete
    ("NATIONALITY", "For artists with a non-Dutch nationality, proof of registration is required.", None),
    ("RESIDENCE", "non-commercial art spaces based in Belgium", {"countries": ["BE"]}),
    # APPLICANT_TYPE
    ("APPLICANT_TYPE", "The eligible applicant is exclusively a natural person.", {"types": ["individual"]}),
    ("APPLICANT_TYPE", "Both individuals and organisations can apply.", {"types": ["individual", "organisation"]}),
    ("APPLICANT_TYPE", "Group applications (duo, collective) are accepted.", None),  # widens, doesn't restrict
    # STUDENT_STATUS
    ("STUDENT_STATUS", "students are excluded from applying", {"enrolled": True}),
    ("STUDENT_STATUS", "The call is open to artists who graduated from Villa Arson less than three years ago.",
     {"graduated_within_years": 3, "also_requires": "graduated from a named institution"}),
    ("STUDENT_STATUS", "You are pursuing a master's degree or have just graduated", None),  # an OR
    # v2 rules, from the out-of-sample check of the corpus
    ("NATIONALITY", "Who are French-speaking and write in French", None),          # a language
    ("RESIDENCE", "You want to engage with the Belgian cultural landscape.", None),  # no place cue
    ("RESIDENCE", "The grant is primarily for artists who live and work in Norway", None),  # soft
    ("STUDENT_STATUS", "Students with a minority background are encouraged to apply.", None),  # soft
    ("NATIONALITY", "Natural persons with Bulgarian citizenship or the right of residence in Bulgaria.",
     {"countries": ["BG"], "nationality_or_residence": True}),
    ("NATIONALITY", "This call is intended for Belgian artists", {"countries": ["BE"]}),  # demonym + person
    ("RESIDENCE", "Applicants must be resident in Germany.", {"countries": ["DE"]}),  # "in" before a country is fine
    # v3 rules, from the development sample of unseen chunks (eligibility_values_unseen.csv)
    ("RESIDENCE", "Thematic, transdisciplinary residency program in Finland for artists.", None),   # "residency"
    ("RESIDENCE", "invites translators of Lithuanian literature living outside Lithuania to apply", None),
    ("AGE", "The leader can be older than 45.", None),                                            # a permission
    ("AGE", "artists under 30 years of age, as well as choreographers under 40 years of age", None),  # two limits
    ("APPLICANT_TYPE", "Self-portraits are permitted, as are group portraits.", None),
    ("APPLICANT_TYPE", "Grants may be applied for by private individuals and organizations.",
     {"types": ["individual", "organisation"]}),                                                  # passive, not a permission
    ("NATIONALITY", "The call is open to artists from Lebanon, Syria, Palestine, Yemen and Sudan, "
                    "whether they live in those countries or elsewhere.",
     {"countries": ["LB", "PS", "SD", "SY", "YE"]}),  # all five, none dropped
    ("STUDENT_STATUS", "You must not be a student for more than 50 per cent of your time.",
     {"enrolled": True, "also_requires": "a specific level or programme"}),
    # classes without a parser
    ("DISCIPLINE", "Open to painters and sculptors.", None),
])
def test_parse_value(label, text, expected):
    assert parse_value(label, text) == expected


def test_no_more_too_strict_values_on_the_gold_set():
    """Regression guard on dataset/labels/eligibility_values.csv: a 'too strict'
    value can wrongly reject an artist. 3 of 126 after the v2 rules
    (2026-10-01), all sentences that aren't really restrictions; this number
    must not grow."""
    outcomes = evaluate()["outcome"]
    assert (outcomes == "too strict").sum() <= 3
    assert (outcomes == "correct").sum() >= 118
