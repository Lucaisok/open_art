# the processed schema: one RawOpportunity normalized into a uniform,
# English, structured-deadline record. Scoped to deadline + language for
# now - discipline/country/career_stage/etc. are carried through verbatim
# from RawOpportunity, untranslated and uncanonicalized; turning them into
# a controlled vocabulary is a separate, not-yet-built step. See workflow.MD.
from datetime import date, datetime

from pydantic import BaseModel


class ProcessedOpportunity(BaseModel):
    id: str

    source: str
    source_url: str
    application_url: str | None = None

    organisation: str | None = None

    description: str | None = None  # verbatim from RawOpportunity, untranslated
    discipline: str | None = None
    opportunity_type: str | None = None
    country: str | None = None
    city: str | None = None
    funding: str | None = None
    application_fee: str | None = None
    career_stage: str | None = None

    language: str  # ISO 639-1 code of the source page, from sources.yaml

    title: str
    requirements_text: str  # verbatim, original language - never overwritten
    title_en: str  # == title when language == "en"
    requirements_text_en: str  # == requirements_text when language == "en"

    deadline_raw: str | None = None  # verbatim from RawOpportunity.deadline
    deadline_date: date | None = None  # parsed; None if absent or unparseable

    processed_at: datetime
