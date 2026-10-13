"""Checks done in code after the extraction model answers (workflow.MD, "Step 3 — combined re-extraction")."""
from datetime import date, datetime, timezone

from src.collectors.extraction import deadline_has_passed, verbatim_misses
from src.models.opportunity import ApplicationQuestion, RawOpportunity, RequiredMaterial

PAGE = """Who can apply
The residency is open to artists living in Norway.
Applicants must be over 18 years old.   Send a CV and a “portfolio” (max 10 pages).
Question: Why do you want to join this residency? (max 300 words)"""


def make(**fields) -> RawOpportunity:
    base = dict(id="x", source="kulturdirektoratet_norway", source_url="https://example.org", title="T",
                requirements_text="The residency is open to artists living in Norway.",
                collected_at=datetime.now(timezone.utc))
    return RawOpportunity(**{**base, **fields})


def test_verbatim_text_passes_even_with_spacing_quotes_and_dropped_sentences():
    record = make(requirements_text="The residency is open to artists living in Norway.\n"
                                    "Applicants must be over 18 years old.",
                  how_to_apply='Send a CV and a "portfolio" (max 10 pages).',
                  application_questions=[ApplicationQuestion(question="Why do you want to join this residency?",
                                                             limit="max 300 words")],
                  required_materials=[RequiredMaterial(item="CV", quote="Send a CV and a “portfolio”")])
    assert verbatim_misses(record, PAGE) == []


def test_paraphrase_is_flagged_per_field_and_per_item():
    record = make(requirements_text="Only Norwegian residents may apply.",
                  application_questions=[ApplicationQuestion(question="Explain your motivation for the residency")])
    assert verbatim_misses(record, PAGE) == ["requirements_text", "application_questions[0]"]


def test_deadline_passed_today_or_before():
    today = date(2026, 10, 12)
    assert deadline_has_passed(make(deadline="1 October 2026"), "en", today)
    assert deadline_has_passed(make(deadline="12 October 2026"), "en", today)
    assert not deadline_has_passed(make(deadline="12 November 2026"), "en", today)


def test_several_rounds_closed_only_after_the_last():
    today = date(2026, 10, 12)
    assert not deadline_has_passed(make(deadline="Round 1: 1 March 2026; round 2: 1 December 2026"), "en", today)


def test_rolling_missing_or_unparsed_deadline_is_never_passed():
    today = date(2026, 10, 12)
    assert not deadline_has_passed(make(deadline="1 October 2026", rolling_deadline=True), "en", today)
    assert not deadline_has_passed(make(deadline=None), "en", today)
    assert not deadline_has_passed(make(deadline="ongoing"), "en", today)


def test_yearly_rounds_without_a_year_are_never_passed():
    # deutscher_uebersetzerfonds: parsed as today's date before the fix
    deadline = "Frühjahr (Einreichungsfrist 15.01.) Sommer (Einreichungsfrist 15.05.) Herbst (Einreichungsfrist 15.09.)"
    assert not deadline_has_passed(make(source="deutscher_uebersetzerfonds", deadline=deadline), "de")


def test_years_before_this_one_are_passed_even_when_too_old_to_parse():
    assert deadline_has_passed(make(deadline="1 February 2015"), "en", date(2026, 10, 12))


def test_numeric_dates_are_read_directly_latest_one_counts():
    today = date(2026, 10, 12)
    assert deadline_has_passed(make(deadline="19.1.2026 16.2.2026 7.5.2026"), "sk", today)
    assert deadline_has_passed(make(deadline="04.11. 2025"), "nb", today)
    assert not deadline_has_passed(make(deadline="19.1.2026 16.2.2026 7.11.2026"), "sk", today)


def test_a_bare_year_is_not_a_deadline_of_today():
    # "le 1er novembre 2026" on an "en" source: only "2026" was understood, and dateparser filled
    # the day and month from today, so a call open until November was rejected as past
    today = date.today()
    assert not deadline_has_passed(make(deadline="le 1er novembre 2026 minuit"), "en", today)
    assert not deadline_has_passed(make(deadline=str(today.year)), "en", today)


def test_french_ordinal_day_is_read():
    from src.processing.deadline import parse_deadline
    assert parse_deadline("le 1er novembre 2026 minuit", "fr") == date(2026, 11, 1)


def test_yearless_deadline_takes_the_year_named_in_the_title():
    today = date(2026, 10, 13)
    past = make(title="Concurs d'Arts Visuals Premi Miquel Casablancas 2019", deadline="15 de març a les 24h")
    assert deadline_has_passed(past, "ca", today)
    this_year = make(title="Convocatòria Miquel Casablancas 2026", deadline="1 March at 23:59")
    assert deadline_has_passed(this_year, "en", today)
    upcoming = make(title="Open Call 2027", deadline="15 March")
    assert not deadline_has_passed(upcoming, "en", today)
    # no year anywhere: recurring rounds, kept as before
    assert not deadline_has_passed(make(title="Translation grants", deadline="15.01. / 15.05."), "de", today)


def test_a_period_in_the_title_is_not_an_edition_year():
    research = make(title="Practices among immigrants to Norway 1970–2000", deadline="Neste søknadsfrist ikke bestemt")
    assert not deadline_has_passed(research, "no", date(2026, 10, 13))
