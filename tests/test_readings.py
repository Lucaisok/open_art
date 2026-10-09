"""Tests for src/eligibility/readings.py: one reading per requirement a sentence states.
Run with: uv run pytest"""

from src.eligibility.readings import sentence_readings

SENEGAL = ("Applicants must be over 18 years of age , be proficient in French or English, and reside in "
           "South Africa, Benin, Cameroon, Ghana, Guinea, Kenya, Mali, Mozambique, Uganda, the Republic of "
           "the Congo, Rwanda or Senegal.")


def test_each_label_gets_its_own_polarity_and_value():
    # the production sentence the single-label model read as AGE only
    readings = sentence_readings(SENEGAL, None, ["AGE", "RESIDENCE"], {"AGE": 0.9, "RESIDENCE": 0.8})
    assert [(r.label, r.polarity) for r in readings] == [("AGE", "REQUIRES"), ("RESIDENCE", "REQUIRES")]
    assert readings[0].value == {"min_age": 18}
    assert "SN" in readings[1].value["countries"] and "BJ" in readings[1].value["countries"]


def test_required_nationality_and_residence_are_one_reading():
    text = "Individuals with Austrian citizenship or permanent residence in Austria."
    readings = sentence_readings(text, None, ["RESIDENCE", "NATIONALITY"], {"RESIDENCE": 0.7, "NATIONALITY": 0.9})
    assert [r.label for r in readings] == ["NATIONALITY"]   # the more probable of the two
    assert readings[0].value == {"countries": ["AT"], "nationality_or_residence": True}


def test_a_waived_geo_label_stays_a_reading_of_its_own():
    # residence required, nationality waived: two readings, the waiver has no value to check
    text = "Applicants must be resident in Belgium, regardless of nationality."
    readings = sentence_readings(text, None, ["RESIDENCE", "NATIONALITY"], {"RESIDENCE": 0.9, "NATIONALITY": 0.6})
    assert [(r.label, r.polarity) for r in readings] == [("RESIDENCE", "REQUIRES"), ("NATIONALITY", "WAIVES")]
    assert readings[0].value["countries"] == ["BE"] and readings[1].value is None


def test_single_label_is_unchanged():
    readings = sentence_readings("Applicants must be under 35.", None, ["AGE"], {"AGE": 0.95})
    assert len(readings) == 1 and readings[0].value == {"max_age": 34}
