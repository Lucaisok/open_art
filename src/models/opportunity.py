# the core schema, this is what every other file ultimately produces.
from datetime import datetime

from pydantic import BaseModel


class RawOpportunity(BaseModel):
    id: str

    source: str
    source_url: str
    application_url: str | None = None

    title: str
    organisation: str | None = None

    description: str | None = None
    discipline: str | None = None
    opportunity_type: str | None = None
    country: str | None = None
    city: str | None = None
    funding: str | None = None
    application_fee: str | None = None
    career_stage: str | None = None

    requirements_text: str

    deadline: str | None = None

    collected_at: datetime
