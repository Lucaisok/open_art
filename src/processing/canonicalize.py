"""
OpenArt — canonicalizes discipline/opportunity_type/career_stage/country,
and translates city.

These fields are carried through from RawOpportunity as free text,
exactly as each source page phrased them - see
src/models/processed_opportunity.py. Confirmed how fragmented that gets
at this corpus size: 278 distinct `discipline` values, many of them the
same concept split by case/plural ("visual arts" / "Visual arts" /
"visual art" / "visual artists"), by language ("Musikk" / "Música e
Ópera" / "Mūzika"), or bundled as a comma-separated list of several
disciplines in one field; `country` the same way ("Norge" / "Noreg" /
"Norway", "Republika Hrvatska" / "Hrvatska" / "Republike Hrvatske"). See
workflow.MD.

Two separate LLM-touching steps per field, not one combined leap
straight from raw text to a category - deliberately mirroring the
title/requirements_text pattern in normalize.py (translate, keep the
original, never conflate translation with a further judgment call):

  1. translate_values() - a literal English translation of each
     DISTINCT raw value (not per-row - this corpus's ~500+ distinct
     values across these fields is far cheaper than 371 rows would be).
     Skipped for values that occur on an "en"-language source (see
     normalize.load_source_languages), matching normalize.py's own
     per-row translation skip. Stored as *_en alongside the original,
     same as title_en/requirements_text_en - never overwritten, and
     independently useful (e.g. for display) even before any
     categorization happens.
  2. canonicalize_values() - maps each distinct *English* value onto
     one or more labels from a small, fixed, hand-picked vocabulary
     (CANONICAL_DISCIPLINES etc., below) - multi-label, since many
     source values genuinely name several categories at once (e.g.
     "Nordic Region" -> its actual member countries, not one vague
     "Nordic" label - see CANONICAL_COUNTRIES). Stored as *_canonical (a
     list, [] if the source field was null or nothing in the vocabulary
     genuinely fit - never a forced bad match). Skipped entirely for
     `city`, which has no vocabulary entry in FIELDS (None) - a city
     doesn't reduce to a small fixed set the way a discipline or a
     country does, so it only gets step 1 (translation/spelling
     standardization: "Wien" -> "Vienna", "Lisboa" -> "Lisbon"), no
     city_canonical field.

Both steps are pure LLM-judgment calls (unavoidable: hand-building a
synonym dictionary across 15+ languages and free-text phrasing isn't
"simple," it's a bigger lift than one batched call per field), but the
RESULT of each step is cached to a small JSON file under
data/processed/canonical/ - auditable, hand-correctable, and reused
across runs so only genuinely new distinct values get paid for again.

career_stage in particular skews towards long, sentence-like eligibility
conditions ("professionally active for at least 1 year", "18-26") more
than a clean category - CANONICAL_CAREER_STAGES's "Other/Unspecified"
bucket is expected to absorb a real share of these; that's this field
being a genuinely poorer fit for a small fixed vocabulary, not a mapping
bug. Precise career-stage conditions are the eligibility classifier's
job (the CAREER_STAGE label on requirements_text spans - see CLAUDE.md),
not this opportunity-metadata field's.

`funding`/`application_fee` are deliberately NOT handled here - both are
free-text amounts (currencies, per-month vs. total, in-kind support
described in full sentences) that don't reduce to a controlled
vocabulary the way discipline/country do; canonicalizing those would be
a structured-extraction task (parse an amount + currency), a materially
different and bigger piece of work - see workflow.MD.

Usage: uv run python -m src.processing.canonicalize
"""

import json
import os
import sys

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(REPO_ROOT)
load_dotenv(os.path.join(REPO_ROOT, ".env"))

from src.collectors.jsonl import load_jsonl, write_jsonl  # noqa: E402
from src.models.processed_opportunity import ProcessedOpportunity  # noqa: E402
from src.processing.normalize import load_source_languages  # noqa: E402

PROCESSED_PATH = os.path.join(REPO_ROOT, "data", "processed", "opportunities.jsonl")
MAPS_DIR = os.path.join(REPO_ROOT, "data", "processed", "canonical")

MODEL = "gpt-5.4-mini"  # same cost/tier reasoning as the rest of the pipeline's LLM calls

CANONICAL_DISCIPLINES = [
    "Visual Arts",
    "Performing Arts",
    "Music",
    "Dance",
    "Theatre",
    "Film/Video",
    "Literature/Writing",
    "Design/Architecture",
    "Digital/New Media Arts",
    "Craft",
    "Photography",
    "Curating/Art Criticism",
    "Cultural Heritage",
    "Circus/Street Arts",
    "Multidisciplinary",
    "Other/Non-Arts",
]

CANONICAL_OPPORTUNITY_TYPES = [
    "Residency",
    "Grant/Funding",
    "Open Call",
    "Commission",
    "Competition/Prize",
    "Fellowship",
    "Exhibition/Showcase",
    "Workshop/Training",
    "Other",
]

CANONICAL_CAREER_STAGES = [
    "Student",
    "Emerging/Early-Career",
    "Mid-Career",
    "Established/Professional",
    "Any/Open to All",
    "Other/Unspecified",
]

# Individual member countries, not umbrella region names - "Nordic
# Region"/"Benelux region"/"Baltic countries" etc. get expanded to their
# actual members (see COUNTRY_EXTRA_INSTRUCTIONS below), which is more
# useful downstream (e.g. filtering "does this apply to Norway") than a
# vague regional bucket. Only genuinely un-enumerable cases (a page that
# just says "Europe" or "international" with no specific countries
# implied) fall through to the three catch-alls at the end.
CANONICAL_COUNTRIES = [
    "Albania", "Armenia", "Austria", "Belgium", "Brazil", "China",
    "Croatia", "Cyprus", "Czech Republic", "Denmark", "Estonia",
    "Faroe Islands", "Finland", "France", "Germany", "Greece",
    "Greenland", "Hungary", "Iceland", "India", "Ireland", "Italy",
    "Latvia", "Lithuania", "Luxembourg", "Mexico", "Morocco",
    "Netherlands", "New Zealand", "Norway", "Poland", "Portugal",
    "Romania", "Serbia", "Slovakia", "Slovenia", "South Korea", "Spain",
    "Sweden", "Ukraine", "United Kingdom", "Åland Islands",
    "Europe (unspecified)", "International/Global", "Other/Unspecified",
]  # fmt: skip

COUNTRY_EXTRA_INSTRUCTIONS = (
    "A well-known regional grouping (Nordic countries, Baltic countries, "
    "Benelux, the EU) should expand to its actual member countries from "
    "the list above, not stay as one vague regional label - e.g. 'Nordic "
    "Region' -> Denmark, Finland, Iceland, Norway, Sweden (and Faroe "
    "Islands/Greenland/Åland Islands only if the value names them "
    "specifically). Only fall back to 'Europe (unspecified)' or "
    "'International/Global' when no specific countries are implied at all."
)

# (raw field, English-translation field, canonical field, vocabulary, extra prompt instructions, cache file)
# canonical field / vocabulary are None for a translate-only field (city) - no fixed vocabulary applies.
FIELDS = [
    ("discipline", "discipline_en", "discipline_canonical", CANONICAL_DISCIPLINES, "", "discipline.json"),
    (
        "opportunity_type",
        "opportunity_type_en",
        "opportunity_type_canonical",
        CANONICAL_OPPORTUNITY_TYPES,
        "",
        "opportunity_type.json",
    ),
    (
        "career_stage",
        "career_stage_en",
        "career_stage_canonical",
        CANONICAL_CAREER_STAGES,
        "",
        "career_stage.json",
    ),
    (
        "country",
        "country_en",
        "country_canonical",
        CANONICAL_COUNTRIES,
        COUNTRY_EXTRA_INSTRUCTIONS,
        "country.json",
    ),
    ("city", "city_en", None, None, "", "city.json"),
]


class TranslationItem(BaseModel):
    index: int
    en: str


class TranslationBatch(BaseModel):
    items: list[TranslationItem]


class CanonicalItem(BaseModel):
    index: int
    labels: list[str]


class CanonicalBatch(BaseModel):
    items: list[CanonicalItem]


def load_map(path: str) -> dict:
    if not os.path.exists(path):
        return {"translations": {}, "canonical": {}}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_map(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True, ensure_ascii=False)


def translate_values(client: OpenAI, values: list[str]) -> dict[str, str]:
    """One LLM call: literal English translation for a batch of distinct
    field values (short category words up to full sentences). Not a
    summary or interpretation - a comma-separated list of disciplines
    stays a comma-separated list, just in English.
    """
    if not values:
        return {}

    numbered = "\n".join(f"{i}: {v}" for i, v in enumerate(values))
    response = client.chat.completions.parse(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "Translate each numbered value to English, literally - do "
                    "not summarize, generalize, or interpret it, and preserve "
                    "its original structure (e.g. a comma-separated list of "
                    "terms stays a comma-separated list of terms, just in "
                    "English). Each item may be in a different language - "
                    "detect it per item. If a value is already in English, "
                    "return it completely unchanged."
                ),
            },
            {"role": "user", "content": numbered},
        ],
        response_format=TranslationBatch,
    )

    result: dict[str, str] = {}
    for item in response.choices[0].message.parsed.items:
        if 0 <= item.index < len(values):
            result[values[item.index]] = item.en
    return result


def canonicalize_values(
    client: OpenAI, values: list[str], vocabulary: list[str], field_label: str, extra_instructions: str = ""
) -> dict[str, list[str]]:
    """One LLM call: map each (English) value onto every label from
    `vocabulary` that genuinely applies - zero, one, or several.
    """
    if not values:
        return {}

    numbered = "\n".join(f"{i}: {v}" for i, v in enumerate(values))
    vocab_list = "\n".join(f"- {label}" for label in vocabulary)
    extra = f" {extra_instructions}" if extra_instructions else ""
    response = client.chat.completions.parse(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    f"Each numbered value describes the {field_label} of an "
                    "arts/culture open call, already in English. Map each one "
                    "onto every label from this fixed list that genuinely "
                    f"applies - many values name several at once:\n{vocab_list}\n\n"
                    "Use only labels from this list, spelled exactly as given. "
                    "If nothing in the list genuinely fits, return an empty "
                    "list for that item rather than forcing a bad match. If a "
                    "value is a broad, generic catch-all with no SPECIFIC "
                    "disciplines/types actually named (e.g. 'artists', 'all "
                    "disciplines', 'arts and culture', 'artistic practice'), "
                    "return only the single most general/'multidisciplinary'-"
                    "style label available, NOT every label that could "
                    "technically apply - reserve multiple labels for values "
                    "that actually name multiple specific things (e.g. "
                    f"'literature, music, and visual arts').{extra}"
                ),
            },
            {"role": "user", "content": numbered},
        ],
        response_format=CanonicalBatch,
    )

    result: dict[str, list[str]] = {}
    for item in response.choices[0].message.parsed.items:
        if 0 <= item.index < len(values):
            result[values[item.index]] = [label for label in item.labels if label in vocabulary]
    return result


def canonicalize_field(
    client: OpenAI,
    records: list[ProcessedOpportunity],
    raw_field: str,
    en_field: str,
    canonical_field: str | None,
    vocabulary: list[str] | None,
    extra_instructions: str,
    map_path: str,
    source_languages: dict[str, str],
) -> int:
    """Updates `records` in place. Returns how many new distinct values
    (translation + canonicalization combined) got LLM-mapped this run.

    `canonical_field`/`vocabulary` are None for a translate-only field
    (city) - step 2 (canonicalize_values) is skipped entirely and no
    canonical field is set.
    """
    cache = load_map(map_path)
    translations: dict[str, str] = cache["translations"]
    canonical: dict[str, list[str]] = cache["canonical"]

    # Whether each distinct raw value occurs on at least one "en"-language
    # source - same skip-translation logic as normalize.py's per-row case.
    is_english_value: dict[str, bool] = {}
    for r in records:
        value = getattr(r, raw_field)
        if not value:
            continue
        value = value.strip()
        lang = source_languages.get(r.source, "en")
        is_english_value.setdefault(value, False)
        if lang == "en":
            is_english_value[value] = True

    new_values = [v for v in is_english_value if v not in translations]
    to_translate = [v for v in new_values if not is_english_value[v]]
    for v in new_values:
        if is_english_value[v]:
            translations[v] = v
    if to_translate:
        translations.update(translate_values(client, to_translate))
    for v in new_values:
        translations.setdefault(v, v)  # safety net if the model skipped an index

    new_en_values = []
    if vocabulary is not None:
        distinct_en_values = sorted({translations[v] for v in is_english_value})
        new_en_values = [v for v in distinct_en_values if v not in canonical]
        if new_en_values:
            canonical.update(
                canonicalize_values(client, new_en_values, vocabulary, raw_field.replace("_", " "), extra_instructions)
            )
        for v in new_en_values:
            canonical.setdefault(v, [])

    save_map(map_path, {"translations": translations, "canonical": canonical})

    for r in records:
        value = getattr(r, raw_field)
        if not value:
            # Explicitly reset, not skipped: this same function runs
            # again on every pipeline re-run, and a raw field can go
            # from having a value to not having one (e.g. a later fix
            # nulls out a leaked placeholder string - confirmed on
            # career_stage, see workflow.MD). Leaving en_field/
            # canonical_field untouched here would keep whatever was
            # computed from the OLD value forever, silently
            # inconsistent with the now-empty raw field.
            setattr(r, en_field, None)
            if canonical_field is not None:
                setattr(r, canonical_field, [])
            continue
        en = translations[value.strip()]
        setattr(r, en_field, en)
        if canonical_field is not None:
            setattr(r, canonical_field, canonical.get(en, []))

    return len(new_values) + len(new_en_values)


def canonicalize_all(processed_path: str = PROCESSED_PATH, maps_dir: str = MAPS_DIR) -> dict:
    records = load_jsonl(processed_path, ProcessedOpportunity)
    source_languages = load_source_languages()
    client = OpenAI()

    counts = {}
    for raw_field, en_field, canonical_field, vocabulary, extra_instructions, map_filename in FIELDS:
        new_count = canonicalize_field(
            client,
            records,
            raw_field,
            en_field,
            canonical_field,
            vocabulary,
            extra_instructions,
            os.path.join(maps_dir, map_filename),
            source_languages,
        )
        counts[raw_field] = new_count
        print(f"{raw_field}: {new_count} new distinct value(s) mapped")

    write_jsonl(records, processed_path)
    print(f"Updated {len(records)} record(s) -> {processed_path}")
    return counts


if __name__ == "__main__":
    canonicalize_all()
