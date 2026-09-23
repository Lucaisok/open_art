"""
OpenArt — processed stage: normalizes data/raw/** into data/processed/.

Scoped to deadline parsing and language handling only - the rest of
CLAUDE.md's processed schema (discipline, country, career_stage, etc.)
is separate, not-yet-built work. For each RawOpportunity not already in
data/processed/opportunities.jsonl:

  - looks up its source's language from sources.yaml's `language` field
    (manual-entry rows, or any source missing from sources.yaml, default
    to "en" - see that file's field doc)
  - parses `deadline` into a structured date (src/processing/deadline.py)
  - if the source language isn't English, translates title and
    requirements_text to English with one LLM call, so RQ1 trains on
    uniform text regardless of source language. requirements_text
    itself is never overwritten - translation adds title_en /
    requirements_text_en alongside it.

One language per source is a deliberate simplification, not a
guarantee - confirmed exception: wiels_brussels is tagged "en" (true
for its other opportunities) but has one Japanese-language row that
will NOT get translated by this scheme. Single-row edge case at this
corpus size, not worth a per-row override mechanism - see workflow.MD.

Merges by id like every other stage: re-running only processes raw ids
not already present in data/processed/, so it never re-spends on
translation for a row it's already translated. Delete a specific line
from data/processed/opportunities.jsonl to force it to be reprocessed.

Usage: uv run python -m src.processing.normalize
"""

import glob
import os
import sys
from datetime import datetime, timezone

import yaml
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(REPO_ROOT)
load_dotenv(os.path.join(REPO_ROOT, ".env"))

from src.collectors.jsonl import load_jsonl, write_jsonl  # noqa: E402
from src.models.opportunity import RawOpportunity  # noqa: E402
from src.models.processed_opportunity import ProcessedOpportunity  # noqa: E402
from src.processing.deadline import parse_deadline  # noqa: E402

SOURCES_YAML = os.path.join(REPO_ROOT, "data", "sources.yaml")
RAW_DIR = os.path.join(REPO_ROOT, "data", "raw")
PROCESSED_PATH = os.path.join(REPO_ROOT, "data", "processed", "opportunities.jsonl")

MODEL = "gpt-5.4-mini"  # same cost/tier reasoning as the collectors' LLM calls


class Translation(BaseModel):
    title_en: str
    requirements_text_en: str


def load_source_languages(sources_path: str = SOURCES_YAML) -> dict[str, str]:
    with open(sources_path, encoding="utf-8") as f:
        sources = yaml.safe_load(f) or []
    return {s["name"]: s.get("language", "en") for s in sources}


def translate(client: OpenAI, title: str, requirements_text: str, language: str) -> Translation:
    response = client.chat.completions.parse(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    f"Translate the following arts open-call title and eligibility/"
                    f"requirements text from language code '{language}' to English. "
                    "This feeds a downstream eligibility classifier, not general "
                    "readability - preserve every specific restriction (nationality, "
                    "residence, age, discipline, career stage, education, etc.) "
                    "precisely. Do not summarize, omit, or add anything."
                ),
            },
            {
                "role": "user",
                "content": f"Title: {title}\n\nRequirements text:\n{requirements_text}",
            },
        ],
        response_format=Translation,
    )
    return response.choices[0].message.parsed


def normalize_record(client: OpenAI, raw: RawOpportunity, language: str) -> ProcessedOpportunity:
    if language == "en":
        title_en, requirements_text_en = raw.title, raw.requirements_text
    else:
        translation = translate(client, raw.title, raw.requirements_text, language)
        title_en, requirements_text_en = translation.title_en, translation.requirements_text_en

    return ProcessedOpportunity(
        id=raw.id,
        source=raw.source,
        source_url=raw.source_url,
        application_url=raw.application_url,
        organisation=raw.organisation,
        description=raw.description,
        discipline=raw.discipline,
        opportunity_type=raw.opportunity_type,
        country=raw.country,
        city=raw.city,
        funding=raw.funding,
        application_fee=raw.application_fee,
        career_stage=raw.career_stage,
        language=language,
        title=raw.title,
        requirements_text=raw.requirements_text,
        title_en=title_en,
        requirements_text_en=requirements_text_en,
        deadline_raw=raw.deadline,
        deadline_date=parse_deadline(raw.deadline, language, raw.source),
        processed_at=datetime.now(timezone.utc),
    )


def normalize_all(
    raw_dir: str = RAW_DIR,
    sources_path: str = SOURCES_YAML,
    processed_path: str = PROCESSED_PATH,
) -> dict:
    languages = load_source_languages(sources_path)

    raw_records: list[RawOpportunity] = []
    for path in sorted(glob.glob(os.path.join(raw_dir, "*", "opportunities.jsonl"))):
        raw_records.extend(load_jsonl(path, RawOpportunity))

    processed = {p.id: p for p in load_jsonl(processed_path, ProcessedOpportunity)}
    to_process = [r for r in raw_records if r.id not in processed]

    if not to_process:
        print("Nothing new to process.")
        return {"processed": 0, "translated": 0, "total": len(processed)}

    client = OpenAI()
    translated = 0
    failed = 0
    for raw in to_process:
        language = languages.get(raw.source, "en")
        try:
            processed[raw.id] = normalize_record(client, raw, language)
        except Exception as e:
            # One bad record (translation error, an unparseable deadline
            # string, ...) must not discard every other record's already-
            # paid-for translation call in this run - skip it and retry on
            # the next run rather than crash write_jsonl() below entirely.
            print(f"  FAILED to normalize {raw.id} ({raw.source}): {e}")
            failed += 1
            continue
        if language != "en":
            translated += 1

    write_jsonl(list(processed.values()), processed_path)
    if failed:
        print(f"{failed} record(s) failed to normalize - left for the next run.")
    print(
        f"Processed {len(to_process)} new record(s) ({translated} translated) "
        f"-> {processed_path}"
    )
    return {"processed": len(to_process), "translated": translated, "total": len(processed)}


if __name__ == "__main__":
    normalize_all()
