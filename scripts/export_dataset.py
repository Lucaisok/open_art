"""
OpenArt — consolidates data/raw/*/opportunities.jsonl into one flat CSV
for EDA and analysis.

Not the "processed" stage from workflow.MD - no normalization happens
here, just reshaping the same raw fields from many per-source files
into one table.

Usage: uv run python scripts/export_dataset.py
"""

import glob
import os
import sys

import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(REPO_ROOT)

from src.collectors.jsonl import load_jsonl  # noqa: E402
from src.models.opportunity import RawOpportunity  # noqa: E402

RAW_DIR = os.path.join(REPO_ROOT, "data", "raw")
OUT_PATH = os.path.join(REPO_ROOT, "data", "raw", "opportunities.csv")


def export_dataset(raw_dir: str = RAW_DIR, out_path: str = OUT_PATH) -> int:
    records: list[RawOpportunity] = []
    for path in sorted(glob.glob(os.path.join(raw_dir, "*", "opportunities.jsonl"))):
        records.extend(load_jsonl(path, RawOpportunity))

    df = pd.DataFrame([r.model_dump() for r in records])
    df.to_csv(out_path, index=False)
    print(f"Wrote {len(df)} opportunities to {out_path}")
    return len(df)


if __name__ == "__main__":
    export_dataset()
