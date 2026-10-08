"""
Suggest the matching query from an artist's statement, and optionally search with it.

    uv run python scripts/suggest_query.py tomas_ferreira --document statement.md
    uv run python scripts/suggest_query.py tomas_ferreira --document statement.md --search --type Residency

The documents must already be in the artist's knowledge base (scripts/search_artist_documents.py --add).
Runs locally, no API call. In the app the suggestion only fills the search box, for the artist to edit.
"""

import argparse
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from src.matching.filters import MatchFilters  # noqa: E402
from src.matching.matcher import Matcher  # noqa: E402
from src.rag.knowledge_base import ArtistKnowledgeBase  # noqa: E402
from src.rag.query_suggestion import suggest_query  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("artist_id")
    parser.add_argument("--document", action="append", help="read only this file (normally the statement)")
    parser.add_argument("--search", action="store_true", help="run semantic matching with the suggested query")
    parser.add_argument("--type", action="append", default=[], help="opportunity type filter for --search")
    parser.add_argument("-k", type=int, default=10, help="number of results for --search (default 10)")
    args = parser.parse_args()

    kb = ArtistKnowledgeBase(args.artist_id)
    if not kb.documents:
        sys.exit(f"no documents for {args.artist_id!r} yet: add some with scripts/search_artist_documents.py --add")

    matcher = Matcher() if args.search else None
    if matcher:
        kb._embedder = matcher.embedder   # same model: load it once
    suggestion = suggest_query(kb, documents=args.document)
    if not suggestion.query:
        sys.exit("nothing to suggest: no passages found")

    print("Suggested query, from:", ", ".join(p.citation for p in suggestion.passages))
    print("   " + suggestion.query.replace("\n", "\n   "))
    if matcher:
        print()
        for rank, match in enumerate(matcher.search(suggestion.query, filters=MatchFilters(opportunity_types=args.type),
                                                    k=args.k), start=1):
            print(f"{rank:2}. [{match.score:.3f}] {match.title}  ({', '.join(match.opportunity_types) or '?'})")


if __name__ == "__main__":
    main()
