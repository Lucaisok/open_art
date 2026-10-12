"""
OpenArt — the call's details in English, lightly formatted, for the opportunity page.

The combined re-extraction (workflow.MD, "Step 3") stores the call's own details verbatim in the
call's language: project requirements, how to apply, application questions, required materials,
selection criteria, application language, programme dates. The page is in English, so this stage
writes an English copy of each (*_en fields on ProcessedOpportunity). The originals stay untouched.

One model call per record (every record, English ones too), which also does a little formatting,
because the extraction joins list items with spaces or line breaks inconsistently: list items go
on their own lines, starting with "• ". The prompt forbids adding, dropping or summarising anything.
These texts are shown to the artist only; eligibility never reads them.

Re-runnable: only records with details and no details_translated_at are done (same "already
processed" pattern as extract_funding.py). WORKERS records at a time.

Usage: uv run python -m src.processing.translate_details
"""

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(REPO_ROOT)
load_dotenv(os.path.join(REPO_ROOT, ".env"))

from src.collectors.jsonl import load_jsonl, write_jsonl  # noqa: E402
from src.models.opportunity import ApplicationQuestion, RequiredMaterial  # noqa: E402
from src.models.processed_opportunity import ProcessedOpportunity  # noqa: E402

PROCESSED_PATH = os.path.join(REPO_ROOT, "data", "processed", "opportunities.jsonl")
MODEL = "gpt-5.4-mini"
WORKERS = 6

TEXT_FIELDS = ("project_requirements", "how_to_apply", "selection_criteria", "application_language",
               "program_dates")

SYSTEM_PROMPT = (
    "You translate the details of an arts open call into English for display. Translate each "
    "field faithfully: keep every condition, number, date, limit and name; do not add, drop, "
    "summarise or explain anything. If a field is already in English, keep its wording. "
    "Light formatting only: when a field is a list (items run together, separated by bullets, "
    "dashes, semicolons or 'o'), put each item on its own line starting with '• '; otherwise keep "
    "it as plain sentences, with a line break between paragraphs. Return a field as null when it "
    "is null. Return the lists in the same order and length as given."
)


class QuestionEn(BaseModel):
    question: str
    limit: str | None


class MaterialEn(BaseModel):
    item: str               # a short English name ("Application form"): extraction sometimes left it untranslated
    details: str | None
    quote: str


class DetailsEn(BaseModel):
    project_requirements: str | None
    how_to_apply: str | None
    selection_criteria: str | None
    application_language: str | None
    program_dates: str | None
    application_questions: list[QuestionEn]
    required_materials: list[MaterialEn]


def has_details(r: ProcessedOpportunity) -> bool:
    return any(getattr(r, f) for f in TEXT_FIELDS) or bool(r.application_questions or r.required_materials)


def translate_details(client: OpenAI, r: ProcessedOpportunity) -> None:
    """Fills the *_en fields of one record in place."""
    payload = DetailsEn(
        **{f: getattr(r, f) for f in TEXT_FIELDS},
        application_questions=[QuestionEn(question=q.question, limit=q.limit) for q in r.application_questions],
        required_materials=[MaterialEn(item=m.item, details=m.details, quote=m.quote) for m in r.required_materials],
    )
    response = client.chat.completions.parse(
        model=MODEL,
        temperature=0,
        messages=[{"role": "system", "content": SYSTEM_PROMPT},
                  {"role": "user", "content": payload.model_dump_json(indent=1)}],
        response_format=DetailsEn,
    )
    en = response.choices[0].message.parsed
    for f in TEXT_FIELDS:
        # a field the call doesn't state stays None, whatever the model returned
        setattr(r, f"{f}_en", getattr(en, f) if getattr(r, f) else None)
    # lists: kept only if the model returned one item per original item, else the original is shown
    if len(en.application_questions) == len(r.application_questions):
        r.application_questions_en = [ApplicationQuestion(question=q.question, limit=q.limit)
                                      for q in en.application_questions]
    if len(en.required_materials) == len(r.required_materials):
        r.required_materials_en = [RequiredMaterial(item=t.item, details=t.details, quote=t.quote)
                                   for t in en.required_materials]
    r.details_translated_at = datetime.now(timezone.utc)


def translate_all(processed_path: str = PROCESSED_PATH) -> dict:
    records: list[ProcessedOpportunity] = load_jsonl(processed_path, ProcessedOpportunity)
    todo = [r for r in records if has_details(r) and r.details_translated_at is None]
    print(f"{len(todo)} record(s) to translate")
    client = OpenAI()
    failed = []

    def one(r: ProcessedOpportunity) -> None:
        try:
            translate_details(client, r)
        except Exception as e:  # one failure must not lose the others' paid calls: retried next run
            failed.append((r.id, str(e)[:120]))

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        list(pool.map(one, todo))
    write_jsonl(records, processed_path)
    for record_id, error in failed:
        print(f"  FAILED {record_id}: {error}")
    print(f"Translated {len(todo) - len(failed)} record(s) -> {processed_path}")
    return {"translated": len(todo) - len(failed), "failed": len(failed)}


if __name__ == "__main__":
    translate_all()
