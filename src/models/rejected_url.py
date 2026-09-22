# a URL extraction decided isn't a real open call, cached so it's never re-billed on future runs
from datetime import datetime

from pydantic import BaseModel


class RejectedUrl(BaseModel):
    id: str

    url: str
    source: str
    title_guess: str
    reason: str

    rejected_at: datetime
