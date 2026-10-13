"""
OpenArt — follows every call of a hand-collected list through the pipeline, so none is lost silently.

Input: the research table made when the list was added as sources
(data/manual/curated/research_<date>.json, one row per call of the author's CSV: its
organiser's source_name and the call page found, `call_url`). For each row it reports the
furthest stage the call reached:

  not added    no organiser page was found (the row never became a source)
  not crawled  the call page is not in data/discovered/ (run the crawler)
  pending      discovered but not extracted yet
  rejected     data/rejected/, with the reason (deadline passed, not open to individuals, ...)
  raw          accepted by extraction, not normalized yet
  published    in data/processed/opportunities.csv (the app's corpus)

A call is "lost" only when it is in none of these states for a reason the report can't
name; rejections are the pipeline's policy at work and are listed with their reason.

Usage: uv run python scripts/check_curated_list.py [data/manual/curated/research_2026-10-13.json]
"""

import csv
import json
import os
import sys
from collections import Counter

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(REPO_ROOT)

from src.collectors.ids import make_id  # noqa: E402

DEFAULT_TABLE = os.path.join(REPO_ROOT, "data", "manual", "curated", "research_2026-10-13.json")


def ids_in_jsonl(path: str) -> dict[str, dict]:
    """id -> record for one JSONL file ({} if it doesn't exist)."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return {r["id"]: r for r in (json.loads(line) for line in f if line.strip())}


def stage_of(row: dict, published: set[str]) -> tuple[str, str]:
    """(stage, detail) for one row of the research table."""
    if not row.get("call_url"):
        return "not added", row.get("notes") or ""
    source, url = row["source_name"], row["call_url"]
    call_id = make_id(url, source)
    data = os.path.join(REPO_ROOT, "data")

    if call_id in published:
        return "published", call_id
    raw = ids_in_jsonl(os.path.join(data, "raw", source, "opportunities.jsonl"))
    if call_id in raw:
        return "raw", raw[call_id]["title"]
    rejected = ids_in_jsonl(os.path.join(data, "rejected", f"{source}.jsonl"))
    if call_id in rejected:
        return "rejected", rejected[call_id]["reason"]
    if call_id in ids_in_jsonl(os.path.join(data, "discovered", f"{source}.jsonl")):
        return "pending", url
    return "not crawled", url


def main() -> None:
    table = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TABLE
    with open(table, encoding="utf-8") as f:
        rows = json.load(f)
    with open(os.path.join(REPO_ROOT, "data", "processed", "opportunities.csv"), encoding="utf-8") as f:
        published = {r["id"] for r in csv.DictReader(f)}

    stages = Counter()
    for row in rows:
        stage, detail = stage_of(row, published)
        stages[stage] += 1
        print(f"{row['ID']:>4}  {stage:<11}  {row['Opportunity'][:45]:<45}  {detail[:110]}")
    print("\n" + ", ".join(f"{n} {s}" for s, n in stages.most_common()))


if __name__ == "__main__":
    main()
