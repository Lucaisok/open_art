"""
Try semantic matching from the command line: the same Matcher.search() the app will call.

    uv run python scripts/search_opportunities.py "I make sound installations about water"
    uv run python scripts/search_opportunities.py "figurative painter" --type Residency --discipline "Visual Arts"
    uv run python scripts/search_opportunities.py "..." --profile my_profile.json   # ArtistProfile fields as JSON

Without --profile every eligibility rule that needs a profile field comes back as CHECK.
"""

import argparse
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from src.eligibility.profile import ArtistProfile  # noqa: E402
from src.matching.filters import MatchFilters  # noqa: E402
from src.matching.matcher import Matcher  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("query")
    parser.add_argument("-k", type=int, default=10, help="number of results (default 10)")
    parser.add_argument("--type", action="append", default=[], help="opportunity type, repeatable")
    parser.add_argument("--discipline", action="append", default=[], help="discipline, repeatable")
    parser.add_argument("--country", action="append", default=[], help="country (corpus name), repeatable")
    parser.add_argument("--include-closed", action="store_true", help="also show calls whose deadline has passed")
    parser.add_argument("--no-fee", action="store_true", help="hide calls known to charge a fee")
    parser.add_argument("--profile", help="JSON file with ArtistProfile fields")
    args = parser.parse_args()

    profile = ArtistProfile()
    if args.profile:
        with open(args.profile, encoding="utf-8") as f:
            profile = ArtistProfile.model_validate_json(f.read())
    filters = MatchFilters(open_only=not args.include_closed, opportunity_types=args.type,
                           disciplines=args.discipline, countries=args.country, no_fee_only=args.no_fee)

    for rank, match in enumerate(Matcher().search(args.query, profile, filters, k=args.k), start=1):
        deadline = match.deadline.isoformat() if match.deadline else "no deadline stated"
        print(f"{rank:2}. [{match.score:.3f}] {match.title}  ({match.organisation or '?'})")
        print(f"    {', '.join(match.opportunity_types) or '?'} · {deadline} · {match.verdict.status}: "
              f"{match.verdict.summary}")
        print(f"    {match.source_url}")


if __name__ == "__main__":
    main()
