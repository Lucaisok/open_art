# one (sentence, label) pair of an opportunity's requirements_text_en: the
# sentence as split by src/eligibility/chunking.py, the label from the RQ1
# multi-label classifier (src/eligibility/classify.py). Written by
# scripts/extract_constraints.py to data/processed/eligibility_constraints.jsonl,
# so every verdict the engine gives can be traced back to the sentence it came from.
#
# A sentence stating two requirements ("over 18 ... and reside in Senegal")
# gives TWO rows, same chunk_id / chunk_index / text, one per label, each with
# its own polarity and value: the engine checks each one. A sentence with no
# requirement gives one NONE row, and so does a bare heading (label None).
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
    label: str | None = None                       # this row's label, e.g. "AGE", or "NONE"
    # probability of `label`, 0-1; on a NONE row, 1 - the highest requirement probability
    confidence: float | None = None
    # every requirement label -> its own probability (one-vs-rest: they don't sum to 1)
    probabilities: dict[str, float] | None = None
    sentence_labels: list[str] | None = None       # every label of the sentence, e.g. ["RESIDENCE", "AGE"]

    # safety net (src/eligibility/safety_net.py): set only on NONE chunks that
    # may be a requirement after all; the engine shows them as CHECK items
    suspected_label: str | None = None  # e.g. "RESIDENCE"
    safety_net_reason: str | None = None  # e.g. 'keyword "based in"'

    # polarity (src/eligibility/polarity.py): REQUIRES / EXCLUDES / WAIVES /
    # UNCLEAR, set on every chunk that is (or may be) a requirement
    polarity: str | None = None

    # parsed value (src/eligibility/values.py), e.g. {"max_age": 34} or
    # {"countries": ["NO"]}; None if the class has no parser, the sentence
    # waives the criterion, or the parser wasn't sure
    value: dict | None = None

    model_trained_on: str  # eligibility_classifier_multilabel.json "trained_on", to know which model labeled this
