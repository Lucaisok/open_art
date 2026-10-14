"""
OpenArt — sets `kind` ("write" / "gather") on the required materials of the existing corpus
(workflow.MD, "Step 6 — Application agent", sub-step 0).

New calls get `kind` from the extraction itself. The calls extracted before that have
kind = None, so this script asks the same model, once per call, which of its materials are a text
the applicant writes for the application (the agent can draft it) and which are something they
already have or must obtain (the checklist). It changes ONLY `kind`: every other field, and so every
eligibility verdict, stays exactly as it was.

Written to:
  - data/raw/**/opportunities.jsonl            required_materials[i].kind
  - data/processed/opportunities.jsonl         required_materials[i].kind and required_materials_en[i].kind
                                               (same position: the English list is a copy of the original)

Re-runnable: a call whose materials all have a kind already is skipped, so nothing is billed twice.
data/ is a git repo, so a run can be undone there.

Usage:
    uv run python scripts/backfill_material_kinds.py [--limit N]
"""

import argparse
import glob
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(REPO_ROOT)
load_dotenv(os.path.join(REPO_ROOT, ".env"))

from src.collectors.jsonl import load_jsonl, write_jsonl  # noqa: E402
from src.models.opportunity import RawOpportunity  # noqa: E402
from src.models.processed_opportunity import ProcessedOpportunity  # noqa: E402

RAW_GLOB = os.path.join(REPO_ROOT, "data", "raw", "*", "opportunities.jsonl")
PROCESSED_PATH = os.path.join(REPO_ROOT, "data", "processed", "opportunities.jsonl")
MODEL = "gpt-5.4-mini"   # the extraction's model, so old and new calls are classified alike
WORKERS = 6

# same definition as the extraction prompt (src/collectors/extraction.py, required_materials)
SYSTEM_PROMPT = (
    "You classify the materials an arts open call asks applicants to submit. For each item, in "
    "the same order, return kind = 'write' if it is a text the applicant writes for this "
    "application (statement, project description, proposal, motivation or cover letter, "
    "biography, synopsis), 'gather' if it is something they already have or must obtain (CV, "
    "portfolio, images, video, budget, letters of reference, ID, certificates, forms). Items may "
    "be in any language."
)


class Kinds(BaseModel):
    kinds: list[Literal["write", "gather"]]   # one per material, same order


def needs_kinds(r: RawOpportunity) -> bool:
    return any(m.kind is None for m in r.required_materials)


def classify(client: OpenAI, r: RawOpportunity) -> list[str] | None:
    """One model call: a kind per material, or None if the model returned the wrong number."""
    lines = [f"{i + 1}. {m.item}" + (f" ({m.details})" if m.details else "") + f" — call says: \"{m.quote}\""
             for i, m in enumerate(r.required_materials)]
    response = client.chat.completions.parse(
        model=MODEL,
        temperature=0,
        messages=[{"role": "system", "content": SYSTEM_PROMPT},
                  {"role": "user", "content": "\n".join(lines)}],
        response_format=Kinds,
    )
    kinds = response.choices[0].message.parsed.kinds
    return kinds if len(kinds) == len(r.required_materials) else None


def main(limit: int | None) -> None:
    client = OpenAI()

    # 1. classify the raw records (the source of truth; normalize.py copies their materials as is)
    raw_files = {path: load_jsonl(path, RawOpportunity) for path in sorted(glob.glob(RAW_GLOB))}
    todo = [r for records in raw_files.values() for r in records if needs_kinds(r)]
    if limit:
        todo = todo[:limit]
    print(f"{len(todo)} calls to classify")
    with ThreadPoolExecutor(WORKERS) as pool:
        results = list(pool.map(lambda r: classify(client, r), todo))

    done = set()
    for r, kinds in zip(todo, results):
        if kinds is None:
            print(f"  skipped {r.id}: wrong number of kinds returned")
            continue
        for m, kind in zip(r.required_materials, kinds):
            m.kind = kind
        done.add(r.id)
    for path, records in raw_files.items():
        if any(r.id in done for r in records):
            write_jsonl(records, path)

    # 2. copy the kinds of every fully classified raw record to its processed record, by position
    #    (all of them, not only this run's: an interrupted run is completed here)
    kinds_by_id = {r.id: [m.kind for m in r.required_materials]
                   for records in raw_files.values() for r in records
                   if r.required_materials and not needs_kinds(r)}
    processed = load_jsonl(PROCESSED_PATH, ProcessedOpportunity)
    copied = 0
    for p in processed:
        kinds = kinds_by_id.get(p.id)
        if kinds is None or len(p.required_materials) != len(kinds):
            continue
        for m, kind in zip(p.required_materials, kinds):
            m.kind = kind
        if len(p.required_materials_en) == len(kinds):
            for m, kind in zip(p.required_materials_en, kinds):
                m.kind = kind
        copied += 1
    write_jsonl(processed, PROCESSED_PATH)

    counts = {k: sum(ks.count(k) for ks in kinds_by_id.values()) for k in ("write", "gather")}
    print(f"classified {len(done)} calls now; corpus total {counts}; {copied} processed records set")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="classify only the first N calls (a pilot)")
    main(parser.parse_args().limit)
