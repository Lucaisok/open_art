"""
OpenArt — converts hand-collected opportunities into raw JSONL.

Building the RQ1 annotation corpus (200-300 hand-labeled spans) doesn't
need scrapers at this volume: copying eligibility text straight from the
browser into data/manual/intake.csv is faster than debugging selectors
per source, and guarantees clean requirements_text. See workflow.MD for
the full rationale and the raw/processed split this feeds into.

Usage: fill data/manual/intake.csv by hand (one row per opportunity),
then run `uv run python -m src.collectors.manual_entry`. Each row is
validated against RawOpportunity and assigned a deterministic id
derived from source_url (stable across re-runs, unlike Python's
built-in hash()). The CSV is the source of truth, so the output file is
fully regenerated from it each run rather than appended to — re-running
after fixing a typo in the CSV corrects the record instead of
duplicating it.
"""

import csv
import os
import sys
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(REPO_ROOT)

from src.collectors.ids import make_id  # noqa: E402
from src.collectors.storage import write_jsonl  # noqa: E402
from src.models.opportunity import RawOpportunity  # noqa: E402

INTAKE_CSV = os.path.join(REPO_ROOT, "data", "manual", "intake.csv")
OUT_PATH = os.path.join(REPO_ROOT, "data", "raw", "manual", "opportunities.jsonl")

REQUIRED_COLUMNS = {"title", "requirements_text", "source", "source_url"}


def row_to_opportunity(row: dict, collected_at: datetime) -> RawOpportunity | None:
    row = {k: (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
    if not row.get("title") or not row.get("requirements_text") or not row.get("source_url"):
        return None

    return RawOpportunity(
        id=make_id(row["source_url"], "manual"),
        source=row.get("source") or "manual",
        source_url=row["source_url"],
        application_url=row.get("application_url") or None,
        title=row["title"],
        organisation=row.get("organisation") or None,
        requirements_text=row["requirements_text"],
        deadline=row.get("deadline") or None,
        collected_at=collected_at,
    )


def convert(intake_path: str = INTAKE_CSV, out_path: str = OUT_PATH) -> int:
    collected_at = datetime.now(timezone.utc)

    with open(intake_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"intake.csv is missing required columns: {sorted(missing)}")

        by_id: dict[str, RawOpportunity] = {}
        for i, row in enumerate(reader, start=2):  # header is row 1
            opp = row_to_opportunity(row, collected_at)
            if opp is None:
                print(f"Skipping row {i}: missing title/requirements_text/source_url")
                continue
            by_id[opp.id] = opp  # last row for a given source_url wins

    write_jsonl(list(by_id.values()), out_path)
    print(f"Wrote {len(by_id)} opportunities to {out_path}")
    return len(by_id)


if __name__ == "__main__":
    convert()
