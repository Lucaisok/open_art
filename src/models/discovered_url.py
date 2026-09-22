# a candidate opportunity link found by the crawler, pending extraction (id, url, source, title_guess, discovered_at).
from datetime import datetime

from pydantic import BaseModel


class DiscoveredUrl(BaseModel):
    id: str

    url: str
    source: str
    title_guess: str

    discovered_at: datetime
