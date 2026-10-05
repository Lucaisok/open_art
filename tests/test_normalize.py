"""Tests for the per-row language detection in src/processing/normalize.py. Run with: uv run pytest"""

from datetime import datetime

import pytest

from src.models.opportunity import RawOpportunity
from src.processing.normalize import row_language


def raw(title: str, requirements_text: str) -> RawOpportunity:
    return RawOpportunity(id="x", source="test", source_url="https://example.org", title=title,
                          requirements_text=requirements_text, collected_at=datetime(2026, 10, 5))


@pytest.mark.parametrize("title, text, source_language, expected", [
    # an "en" source with an English row stays "en"
    ("Open call for residencies", "Applicants must be based in Belgium and over 18 years old.", "en", "en"),
    # an "en" source publishing a Spanish row (matadero_madrid) -> translated as Spanish
    ("Convocatoria", "Solo podrán presentarse aquellas personas físicas, mayores de edad, con residencia en España.",
     "en", "es"),
    # langdetect says "no" for Norwegian; the pipeline (dateparser) needs "nb"
    ("Tilskudd", "Søkere må være bosatt i Norge og ha norsk organisasjonsnummer for å kunne søke.", "en", "nb"),
    # a non-"en" source tag was confirmed by hand and is never overridden
    ("Open call", "Applicants must be based in Belgium.", "fr", "fr"),
    # nothing to detect from -> keep "en"
    ("2026", "123", "en", "en"),
])
def test_row_language(title, text, source_language, expected):
    assert row_language(raw(title, text), source_language) == expected
