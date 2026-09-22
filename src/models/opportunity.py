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

    requirements_text: str

    deadline: str | None = None

    collected_at: datetime
