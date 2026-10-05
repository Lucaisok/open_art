"""
Build the semantic-matching index: embed every published opportunity once.

Reads dataset/opportunities.csv, writes artifacts/opportunity_index.npz.
Re-run after every export_dataset.py run; the matcher refuses to use an index
whose opportunities are missing or have changed text.

    uv run python scripts/build_match_index.py
"""

import os
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from src.matching.corpus import load_opportunities  # noqa: E402
from src.matching.index import INDEX_PATH, build_index  # noqa: E402


def main() -> None:
    opportunities = load_opportunities()
    print(f"embedding {len(opportunities)} opportunities ...")
    start = time.time()
    index = build_index(opportunities)
    index.save(INDEX_PATH)
    print(f"saved {index.vectors.shape[0]} x {index.vectors.shape[1]} vectors ({index.model}) "
          f"to {os.path.relpath(INDEX_PATH, REPO_ROOT)} in {time.time() - start:.0f}s")


if __name__ == "__main__":
    main()
