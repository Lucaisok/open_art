# one sentence chunk of an opportunity's requirements_text_en, as split by
# src/eligibility/chunking.py and labeled by the RQ1 classifier
# (src/eligibility/classify.py). Written by scripts/extract_constraints.py to
# data/processed/eligibility_constraints.jsonl, one row per chunk, so every
# verdict the engine gives can be traced back to the sentence it came from.
# Step 4 adds the parsed value to these rows.
from pydantic import BaseModel


class ClassifiedChunk(BaseModel):
    opportunity_id: str
    chunk_id: str      # "<opportunity_id>_<chunk_index>", same scheme as the RQ1 labels
    chunk_index: int   # position in split_into_chunks(requirements_text_en)
    text: str

    # bare headings ("Who can apply?") are kept for context but never classified
    is_heading: bool
    heading: str | None = None  # nearest bare heading above this chunk, if any

    # classifier output; all None for a heading
    label: str | None = None                       # e.g. "AGE", "NONE"
    confidence: float | None = None                # probability of `label`, 0-1
    probabilities: dict[str, float] | None = None  # every class -> probability

    # safety net (src/eligibility/safety_net.py): set only on NONE chunks that
    # may be a requirement after all; the engine shows them as CHECK items
    suspected_label: str | None = None  # e.g. "RESIDENCE"
    safety_net_reason: str | None = None  # e.g. 'keyword "based in"'

    # polarity (src/eligibility/polarity.py): REQUIRES / EXCLUDES / WAIVES /
    # UNCLEAR, set on every chunk that is (or may be) a requirement
    polarity: str | None = None

    model_trained_on: str  # eligibility_classifier.json "trained_on", to know which model labeled this
