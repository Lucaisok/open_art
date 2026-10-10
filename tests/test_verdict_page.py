"""Tests for how the call page shows a verdict (api/discover.py verdict_out): each sentence quoted once,
one row per requirement it states, generic checks merged, failures first, then passes, then checks.
Run with: uv run pytest"""

from datetime import date

from api.discover import verdict_out
from src.eligibility.engine import Item, Review, Verdict, evaluate_chunks
from src.eligibility.profile import ArtistProfile
from src.models.classified_chunk import ClassifiedChunk

SENEGAL = ("Applicants must be over 18 years of age , be proficient in French or English, and reside in "
           "South Africa, Benin, Cameroon, Ghana, Guinea, Kenya, Mali, Mozambique, Uganda, the Republic of "
           "the Congo, Rwanda or Senegal.")


def chunk(label):
    return ClassifiedChunk(opportunity_id="opp", chunk_id="opp_0", chunk_index=0, text=SENEGAL, is_heading=False,
                           label=label, confidence=0.9, polarity="REQUIRES", model_trained_on="test")


def test_the_page_shows_the_sentence_once_with_one_row_per_requirement():
    reviews = {(SENEGAL, "AGE"): Review(label="AGE", decision="confirm", polarity="REQUIRES",
                                        value={"min_age": 18}, reason=None),
               (SENEGAL, "RESIDENCE"): Review(label="RESIDENCE", decision="confirm", polarity="REQUIRES",
                                              value={"countries": ["SN"]}, reason=None)}
    verdict = evaluate_chunks(ArtistProfile(birth_date=date(1990, 3, 1), residence_country="DE"),
                              [chunk("AGE"), chunk("RESIDENCE"), chunk("OTHER_ELIGIBILITY")], reviews,
                              opportunity_id="opp", deadline=date(2026, 10, 13), today=date(2026, 10, 9))
    out = verdict_out(verdict)
    assert out.status == "LIKELY_NOT_ELIGIBLE" and (out.fails, out.checks, out.passes) == (1, 1, 1)
    [sentence] = out.sentences
    assert sentence.quote == SENEGAL
    # a failure first, then passes, then checks
    assert [(r.outcome, r.topic) for r in sentence.requirements] == [
        ("FAIL", "Residence"), ("PASS", "Age"), ("CHECK", "Language")]  # "proficient in French or English"


def item(index, text, label, outcome="CHECK", kind="check_only_class", reason="read it"):
    return Item(chunk_id=f"opp_{index}", chunk_index=index, text=text, label=label, confidence=0.9,
                polarity="REQUIRES", outcome=outcome, reason=reason, check_kind=kind)


def test_generic_checks_of_one_sentence_become_one_row_and_passes_come_first():
    text = "Professional artists over 18 who work with communities."
    verdict = Verdict(opportunity_id="opp", title=None, source_url=None, status="CHECK", summary="", items=[
        item(0, text, "CAREER_STAGE"), item(0, text, "OTHER_ELIGIBILITY"),
        item(0, text, "AGE", outcome="PASS", kind=None, reason="requires age 18 or over"),
        item(1, "Applicants must be under 35.", "AGE", kind="missing_profile_field",
             reason="your birth date is not in your profile"),
    ])
    out = verdict_out(verdict)
    first, second = out.sentences
    assert first.quote == text  # it has a pass, so it comes before the sentence that is only a check
    assert [(r.outcome, r.topic) for r in first.requirements] == [("PASS", "Age"),
                                                                   ("CHECK", "Career stage, other conditions")]
    assert second.requirements[0].reason == "your birth date is not in your profile"  # specific: own row
