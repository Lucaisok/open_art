# the processed schema: one RawOpportunity normalized into a uniform,
# English, structured-deadline record. discipline/opportunity_type/
# career_stage/country additionally get a literal English translation
# (*_en) and a controlled-vocabulary mapping (*_canonical) - see
# src/processing/canonicalize.py. city gets a translation only
# (city_en) - it's an open field with no natural fixed vocabulary, see
# that module's docstring. funding/application_fee get a structured
# extraction (amount + currency + category, not just a vocabulary
# label - see src/processing/extract_funding.py, since a controlled
# vocabulary alone would lose the amount). description gets a literal
# translation (description_en) via normalize.py, same mechanism as
# title_en/requirements_text_en.
from datetime import date, datetime

from pydantic import BaseModel

from src.models.opportunity import ApplicationQuestion, RequiredMaterial


class FundingComponent(BaseModel):
    """One distinct piece of support named in a `funding` value - many
    values describe several at once (e.g. a travel allowance AND a
    daily allowance AND on-site accommodation), so `funding_components`
    is a list of these, not one flattened amount. See
    src/processing/extract_funding.py.
    """

    category: str  # one of CANONICAL_FUNDING_CATEGORIES
    amount_min: float | None = None  # None if this component has no stated figure (e.g. "mentorship")
    amount_max: float | None = None  # == amount_min for a fixed amount; higher for a range or "up to X"
    currency: str | None = None  # ISO 4217 code (EUR, NOK, HUF, ...); None iff amount_min is None
    period: str | None = None  # "one-time" | "per month" | "per week" | "per day" | "per year" | None
    note: str | None = None  # only when something doesn't fit cleanly (e.g. domestic vs international rate)


class ProcessedOpportunity(BaseModel):
    id: str

    source: str
    source_url: str
    application_url: str | None = None
    document_urls: list[str] = []  # linked PDFs read at extraction, copied from RawOpportunity

    organisation: str | None = None

    description: str | None = None  # verbatim from RawOpportunity, untranslated
    discipline: str | None = None
    opportunity_type: str | None = None
    country: str | None = None
    city: str | None = None
    funding: str | None = None
    application_fee: str | None = None
    career_stage: str | None = None

    description_en: str | None = None  # literal translation; == description when language == "en"
    discipline_en: str | None = None  # literal translation, same granularity as discipline
    opportunity_type_en: str | None = None
    career_stage_en: str | None = None
    country_en: str | None = None
    city_en: str | None = None  # translation only - no city_canonical, see canonicalize.py docstring
    discipline_canonical: list[str] = []  # mapped onto CANONICAL_DISCIPLINES; [] if discipline is None
    opportunity_type_canonical: list[str] = []  # mapped onto CANONICAL_OPPORTUNITY_TYPES
    career_stage_canonical: list[str] = []  # mapped onto CANONICAL_CAREER_STAGES
    country_canonical: list[str] = []  # mapped onto CANONICAL_COUNTRIES; a list - some values name several
    # disciplines read from the call's whole text (src/processing/disciplines_from_text.py), merged into
    # discipline_canonical on every run of that stage; disciplines_read_at = already read
    discipline_from_text: list[str] = []
    disciplines_read_at: datetime | None = None

    funding_components: list[FundingComponent] = []  # [] if funding is None OR nothing extractable was stated
    funding_extracted_at: datetime | None = None  # set whenever extraction runs, even if it found nothing -
    # an empty funding_components is a legitimate terminal result (see extract_funding.py), so it alone can't
    # tell "not yet processed" from "processed, nothing there"; this timestamp is the actual signal for that.
    application_fee_has_fee: bool | None = None  # None iff application_fee itself is None (unknown, NOT "no fee") -
    # doubles as its own "not yet processed" signal, since a processed row always gets true/false, never stays None
    application_fee_amount_min: float | None = None
    application_fee_amount_max: float | None = None
    application_fee_currency: str | None = None

    language: str  # ISO 639-1 code of the source page, from sources.yaml

    title: str
    requirements_text: str  # verbatim, original language - never overwritten
    title_en: str  # == title when language == "en"
    requirements_text_en: str  # == requirements_text when language == "en"

    deadline_raw: str | None = None  # verbatim from RawOpportunity.deadline
    deadline_date: date | None = None  # parsed; None if absent or unparseable

    # copied as-is from RawOpportunity (original language, not translated): see opportunity.py
    open_to: list[str] = []
    project_requirements: str | None = None
    how_to_apply: str | None = None
    application_questions: list[ApplicationQuestion] = []
    required_materials: list[RequiredMaterial] = []
    selection_criteria: str | None = None
    application_language: str | None = None
    submission_method: str | None = None
    program_dates: str | None = None
    rolling_deadline: bool = False
    rules_in_external_document: bool = False
    verbatim_flags: list[str] = []

    # the details above in English, list items one per line (src/processing/translate_details.py);
    # shown on the page instead of the originals. None / [] = not translated yet
    project_requirements_en: str | None = None
    how_to_apply_en: str | None = None
    selection_criteria_en: str | None = None
    application_language_en: str | None = None
    program_dates_en: str | None = None
    application_questions_en: list[ApplicationQuestion] = []
    required_materials_en: list[RequiredMaterial] = []
    details_translated_at: datetime | None = None

    processed_at: datetime
