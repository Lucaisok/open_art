"""
OpenArt — runs the full pipeline (crawl -> extract -> normalize ->
canonicalize -> extract_funding -> export) in one command.

Cost/safety note: crawling and extraction each call an LLM per URL. Every
stage is already incremental (id-based caching - see each module's own
docstring), so a plain re-run only pays for genuinely new URLs. But a
newly added, unverified source can still produce a batch of bad links at
once (wrong selector, wrong listing page, etc.), which would otherwise
get silently extracted (and billed) right along with everything else. So
by default this pauses after crawling if it finds a source with no
raw/rejected data yet - i.e. one that's never been through extraction -
so you can check data/discovered/<source>.jsonl before paying to extract
it. Pass --yes to skip that pause, or --only to test a single source in
isolation (mirrors crawl_all()/extract_all()'s own `only` param).

Usage:
  uv run python scripts/run_pipeline.py                     # full run, pauses on new sources
  uv run python scripts/run_pipeline.py --yes                # full run, no pause
  uv run python scripts/run_pipeline.py --only kunst_dk_denmark  # single source, no pause
"""

import argparse
import os
import sys

import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(REPO_ROOT)

from scripts.export_dataset import export_dataset, export_processed  # noqa: E402
from src.collectors.crawler import crawl_all  # noqa: E402
from src.collectors.extraction import extract_all  # noqa: E402
from src.processing.canonicalize import canonicalize_all  # noqa: E402
from src.processing.extract_funding import extract_all as extract_funding_all  # noqa: E402
from src.processing.normalize import normalize_all  # noqa: E402

SOURCES_YAML = os.path.join(REPO_ROOT, "data", "sources.yaml")
RAW_DIR = os.path.join(REPO_ROOT, "data", "raw")
REJECTED_DIR = os.path.join(REPO_ROOT, "data", "rejected")


def never_extracted_sources(sources_path: str = SOURCES_YAML) -> list[str]:
    """Source names with no raw or rejected file yet - i.e. never run through extraction."""
    with open(sources_path, encoding="utf-8") as f:
        names = [s["name"] for s in (yaml.safe_load(f) or [])]
    return [
        name
        for name in names
        if not os.path.exists(os.path.join(RAW_DIR, name, "opportunities.jsonl"))
        and not os.path.exists(os.path.join(REJECTED_DIR, f"{name}.jsonl"))
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", nargs="+", default=None, help="limit to these source name(s)")
    parser.add_argument("--yes", action="store_true", help="skip the new-source confirmation pause")
    args = parser.parse_args()
    only = set(args.only) if args.only else None

    print("=== Crawling ===")
    crawl_all(only=only)

    if only is None and not args.yes:
        new_sources = never_extracted_sources()
        if new_sources:
            print(
                f"\nFound source(s) never run through extraction yet: {new_sources}\n"
                f"Check data/discovered/<source>.jsonl before paying to extract them.\n"
                f"Re-run with --yes to continue anyway, or --only <source> to test one first."
            )
            return

    print("\n=== Extracting ===")
    extract_all(only=only)

    print("\n=== Normalizing ===")
    normalize_all()

    print("\n=== Canonicalizing discipline/opportunity_type/career_stage/country/city ===")
    canonicalize_all()

    print("\n=== Extracting structured funding/application_fee ===")
    extract_funding_all()

    print("\n=== Exporting CSVs ===")
    export_dataset()
    export_processed()


if __name__ == "__main__":
    main()
