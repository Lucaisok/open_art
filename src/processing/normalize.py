"""
OpenArt — processed stage: normalizes data/raw/** into data/processed/.

discipline/opportunity_type/career_stage/country's own translation and
canonicalization happen separately, in src/processing/canonicalize.py
(a distinct-value batch pass, not per-row like this module) - see that
module's docstring. country/city/funding/application_fee's remaining
canonicalization (country/city name normalization) is also
canonicalize.py's job, not this one's. For each RawOpportunity not
already in data/processed/opportunities.jsonl:

  - looks up its source's language from sources.yaml's `language` field
    (manual-entry rows, or any source missing from sources.yaml, default
    to "en" - see that file's field doc), then, for a source tagged "en"
    only, detects the row's own language (row_language() below)
  - parses `deadline` into a structured date (src/processing/deadline.py)
  - if the source language isn't English, translates title,
    requirements_text, and description (if given) to English with one
    LLM call, so RQ1 trains on uniform text regardless of source
    language. None of the three originals are ever overwritten -
    translation adds title_en / requirements_text_en / description_en
    alongside them.

Per-row detection exists because "en" tags were not reliable: several
"en" sources publish some calls in Greek / Spanish / French / Dutch /
Swedish, and the English-trained classifier could not read them. A
non-"en" source tag was confirmed by hand and is always kept.

Merges by id like every other stage: re-running only processes raw ids
not already present in data/processed/, plus stored rows whose language
decision has changed since (a sources.yaml fix, or detection now
finding a non-English row). So it never re-spends on translation for a
row it's already translated. Delete a specific line from
data/processed/opportunities.jsonl to force it to be reprocessed.

Usage: uv run python -m src.processing.normalize
"""

import glob
import os
import sys
from datetime import datetime, timezone

import yaml
from dotenv import load_dotenv
from langdetect import DetectorFactory, LangDetectException, detect_langs
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

DetectorFactory.seed = 0  # langdetect is random by default; fixed seed = same answer every run
DETECT_MIN_PROB = 0.9     # below this, keep the source tag (an Irish row came out "es" at 0.57)
# langdetect codes -> the codes the rest of the pipeline uses (dateparser has no "no", see sources.yaml)
DETECT_CODE_FIX = {"no": "nb"}


class Translation(BaseModel):
    title_en: str
    requirements_text_en: str
    description_en: str | None = None  # null iff no description was given to translate


def load_source_languages(sources_path: str = SOURCES_YAML) -> dict[str, str]:
    with open(sources_path, encoding="utf-8") as f:
        sources = yaml.safe_load(f) or []
    return {s["name"]: s.get("language", "en") for s in sources}


def row_language(raw: RawOpportunity, source_language: str) -> str:
    """The language this row is actually written in.

    A non-"en" source tag is trusted as is (confirmed by hand). For an "en"
    source, detect the row's title + requirements text and use the detected
    language only when langdetect is confident; otherwise keep "en".
    """
    if source_language != "en":
        return source_language
    try:
        best = detect_langs(f"{raw.title}\n{raw.requirements_text}")[0]
    except LangDetectException:  # no letters to detect from
        return "en"
    if best.lang == "en" or best.prob < DETECT_MIN_PROB:
        return "en"
    return DETECT_CODE_FIX.get(best.lang, best.lang)


def translate(
    client: OpenAI, title: str, requirements_text: str, description: str | None, language: str
) -> Translation:
    description_block = f"\n\nDescription:\n{description}" if description else ""
    response = client.chat.completions.parse(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    f"Translate the following arts open-call fields from language "
                    f"code '{language}' to English. This feeds a downstream "
                    "eligibility classifier, not general readability - preserve "
                    "every specific restriction (nationality, residence, age, "
                    "discipline, career stage, education, etc.) precisely in "
                    "requirements_text_en. Do not summarize, omit, or add "
                    "anything. Translate description literally too if one is "
                    "given below; leave description_en null if none is given."
                ),
            },
            {
                "role": "user",
                "content": f"Title: {title}\n\nRequirements text:\n{requirements_text}{description_block}",
            },
        ],
        response_format=Translation,
    )
    return response.choices[0].message.parsed


def normalize_record(client: OpenAI, raw: RawOpportunity, language: str) -> ProcessedOpportunity:
    if language == "en":
        title_en, requirements_text_en, description_en = raw.title, raw.requirements_text, raw.description
    else:
        translation = translate(client, raw.title, raw.requirements_text, raw.description, language)
        title_en, requirements_text_en = translation.title_en, translation.requirements_text_en
        description_en = translation.description_en if raw.description else None

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
        description_en=description_en,
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
    # the language each row should be processed as; a stored row processed as another
    # language (e.g. copied untranslated as "en") is redone
    row_languages = {r.id: row_language(r, languages.get(r.source, "en")) for r in raw_records}
    to_process = [r for r in raw_records
                  if r.id not in processed or processed[r.id].language != row_languages[r.id]]

    if not to_process:
        print("Nothing new to process.")
        return {"processed": 0, "translated": 0, "total": len(processed)}

    client = OpenAI()
    translated = 0
    failed = 0
    for raw in to_process:
        language = row_languages[raw.id]
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
