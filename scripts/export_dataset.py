"""
OpenArt — consolidates data/raw/*/opportunities.jsonl and
data/processed/opportunities.jsonl into flat CSVs for EDA and analysis.

No normalization happens here, just reshaping JSONL into one table per
stage - data/raw/opportunities.csv mirrors the raw fields from many
per-source files unchanged; data/processed/opportunities.csv mirrors
the single normalized file from src/processing/normalize.py.

data/ is its own nested local-only git repo (data/.git), so nothing
under it can be tracked or pushed from this repo. export_processed()
also copies its output to dataset/opportunities.csv, which is - the
one file this repo actually publishes.

Usage: uv run python scripts/export_dataset.py
"""

import glob
import os
import shutil
import sys

import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(REPO_ROOT)

from src.collectors.jsonl import load_jsonl  # noqa: E402
from src.models.opportunity import RawOpportunity  # noqa: E402
from src.models.processed_opportunity import ProcessedOpportunity  # noqa: E402

RAW_DIR = os.path.join(REPO_ROOT, "data", "raw")
RAW_OUT_PATH = os.path.join(REPO_ROOT, "data", "raw", "opportunities.csv")
PROCESSED_PATH = os.path.join(REPO_ROOT, "data", "processed", "opportunities.jsonl")
PROCESSED_OUT_PATH = os.path.join(REPO_ROOT, "data", "processed", "opportunities.csv")
PUBLISHED_OUT_PATH = os.path.join(REPO_ROOT, "dataset", "opportunities.csv")


def export_dataset(raw_dir: str = RAW_DIR, out_path: str = RAW_OUT_PATH) -> int:
    records: list[RawOpportunity] = []
    for path in sorted(glob.glob(os.path.join(raw_dir, "*", "opportunities.jsonl"))):
        records.extend(load_jsonl(path, RawOpportunity))

    df = pd.DataFrame([r.model_dump() for r in records])
    df.to_csv(out_path, index=False)
    print(f"Wrote {len(df)} opportunities to {out_path}")
    return len(df)


def export_processed(
    processed_path: str = PROCESSED_PATH,
    out_path: str = PROCESSED_OUT_PATH,
    published_path: str = PUBLISHED_OUT_PATH,
) -> int:
    records = load_jsonl(processed_path, ProcessedOpportunity)

    df = pd.DataFrame([r.model_dump() for r in records])
    df.to_csv(out_path, index=False)
    print(f"Wrote {len(df)} opportunities to {out_path}")

    os.makedirs(os.path.dirname(published_path), exist_ok=True)
    shutil.copy2(out_path, published_path)
    print(f"Copied to {published_path}")
    return len(df)


if __name__ == "__main__":
    export_dataset()
    export_processed()
