"""
OpenArt — the disciplines a call is for, read from its whole text, not only its stated discipline.

Extraction copies `discipline` only where a call states it as such, and canonicalize.py maps that
onto CANONICAL_DISCIPLINES. What the description says is lost: "contemporary art, design, science,
technology and society" gave no Digital/New Media Arts; "artists and researchers" gave only
Multidisciplinary (author's report, 2026-10-12). This stage reads the call's English texts (title,
stated discipline, description, applicant and project requirements) and adds the disciplines the
call is FOR, each with a quote that code checks is in the text (a discipline without one is dropped).

- Only adds, never removes: the result widens the Discover filter and the card chips. The
  eligibility engine never reads discipline_canonical (it checks requirement sentences), so a
  wrong addition can't reject or accept anyone.
- canonicalize.py rewrites discipline_canonical from its value map on every run, so the additions
  live in discipline_from_text and are merged in again on every run of this stage (no model call
  for a record already read: disciplines_read_at).

Usage: uv run python -m src.processing.disciplines_from_text
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

from src.collectors.extraction import _flatten  # noqa: E402
from src.collectors.jsonl import load_jsonl, write_jsonl  # noqa: E402
from src.models.processed_opportunity import ProcessedOpportunity  # noqa: E402
from src.processing.canonicalize import CANONICAL_DISCIPLINES  # noqa: E402

PROCESSED_PATH = os.path.join(REPO_ROOT, "data", "processed", "opportunities.jsonl")
MODEL = "gpt-5.4-mini"
WORKERS = 6
VOCABULARY = [d for d in CANONICAL_DISCIPLINES if d != "Other/Non-Arts"]
# what this stage may add: not Multidisciplinary, which the model gave to any call naming two
# disciplines (106 of 317 on the first run, a film-only fund among them); it stays reserved for
# calls whose stated discipline says so (canonicalize.py)
ADDABLE = [d for d in VOCABULARY if d != "Multidisciplinary"]

SYSTEM_PROMPT = (
    "You read an arts open call and say which artistic disciplines it is FOR: the disciplines whose "
    "artists can apply, or whose kind of work it supports. Choose only from this list: "
    + "; ".join(VOCABULARY) + ". "
    "Digital/New Media Arts covers art and technology, digital art, media art, new media, video art, "
    "sound art, AI and code-based work. Multidisciplinary means the call is open to any or several "
    "disciplines. Do not choose a discipline only mentioned in passing (a closing concert, a "
    "catalogue, a jury member's field). For each discipline give quote: the exact words from the text "
    "that show it, copied verbatim (a few words is enough). If nothing shows a discipline, return []."
)


class DisciplineFound(BaseModel):
    discipline: str
    quote: str


class DisciplinesFound(BaseModel):
    disciplines: list[DisciplineFound]


def call_text(r: ProcessedOpportunity) -> str:
    parts = [("Title", r.title_en), ("Stated discipline", r.discipline_en), ("Description", r.description_en),
             ("Who can apply", r.requirements_text_en), ("Project requirements", r.project_requirements_en)]
    return "\n\n".join(f"{name}: {text}" for name, text in parts if text)


def read_disciplines(client: OpenAI, r: ProcessedOpportunity) -> None:
    """Sets discipline_from_text: the vocabulary disciplines the model found, each with a quote that
    is really in the text (lower case, whitespace and quotes normalised, as the verbatim check)."""
    text = call_text(r)
    response = client.chat.completions.parse(
        model=MODEL,
        temperature=0,
        messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": text}],
        response_format=DisciplinesFound,
    )
    flat = _flatten(text)
    found = response.choices[0].message.parsed.disciplines
    r.discipline_from_text = list(dict.fromkeys(
        d.discipline for d in found
        if d.discipline in ADDABLE and d.quote.strip() and _flatten(d.quote) in flat))
    r.disciplines_read_at = datetime.now(timezone.utc)


def merge(r: ProcessedOpportunity) -> None:
    """discipline_canonical plus the ones read from the text, in vocabulary order, no repeats."""
    union = set(r.discipline_canonical) | set(r.discipline_from_text)
    r.discipline_canonical = [d for d in CANONICAL_DISCIPLINES if d in union]


def read_all(processed_path: str = PROCESSED_PATH) -> dict:
    records: list[ProcessedOpportunity] = load_jsonl(processed_path, ProcessedOpportunity)
    todo = [r for r in records if r.disciplines_read_at is None]
    print(f"{len(todo)} record(s) to read")
    client = OpenAI()
    failed = []

    def one(r: ProcessedOpportunity) -> None:
        try:
            read_disciplines(client, r)
        except Exception as e:  # retried on the next run; the others' paid calls are kept
            failed.append((r.id, str(e)[:120]))

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        list(pool.map(one, todo))
    before = {r.id: list(r.discipline_canonical) for r in records}
    for r in records:
        merge(r)
    added = sum(len(r.discipline_canonical) - len(before[r.id]) for r in records)
    write_jsonl(records, processed_path)
    for record_id, error in failed:
        print(f"  FAILED {record_id}: {error}")
    print(f"Read {len(todo) - len(failed)} record(s); {added} discipline(s) added -> {processed_path}")
    return {"read": len(todo) - len(failed), "added": added, "failed": len(failed)}


if __name__ == "__main__":
    read_all()
