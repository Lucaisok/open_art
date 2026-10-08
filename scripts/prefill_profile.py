"""
Pre-fill an artist's eligibility profile from their CV, then confirm each value by hand.

    uv run python scripts/prefill_profile.py ilka_varga --document cv.pdf --out ilka_profile.json
    uv run python scripts/search_opportunities.py "printmaking residency" --profile ilka_profile.json

The documents must already be in the artist's knowledge base (scripts/search_artist_documents.py --add).
Every proposed value is shown with the quote it comes from; only the ones you accept are written.
Sends the retrieved passages (not the whole documents) to OpenAI: needs OPENAI_API_KEY in .env.
"""

import argparse
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from src.rag.knowledge_base import ArtistKnowledgeBase  # noqa: E402
from src.rag.profile_prefill import build_profile, prefill_profile  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("artist_id")
    parser.add_argument("--document", action="append", help="read only this file (normally the CV), repeatable")
    parser.add_argument("--out", required=True, help="profile JSON to write")
    parser.add_argument("--show-rejected", action="store_true", help="also list answers the checks dropped")
    args = parser.parse_args()

    kb = ArtistKnowledgeBase(args.artist_id)
    if not kb.documents:
        sys.exit(f"no documents for {args.artist_id!r} yet: add some with scripts/search_artist_documents.py --add")

    result = prefill_profile(kb, documents=args.document)
    print(f"{len(result.passages)} passages read, {len(result.proposals)} values proposed\n")
    if args.show_rejected:
        for name, reason in result.rejected:
            print(f"  dropped {name}: {reason}")

    accepted = []
    for proposal in result.proposals:
        derived = f"  ({proposal.note})" if proposal.note else ""
        print(f"{proposal.field}: {proposal.value}{derived}")
        print(f'   "{proposal.quote}"  — {proposal.citation}')
        if input("   accept? [y/N] ").strip().lower() == "y":
            accepted.append(proposal)

    profile = build_profile(accepted)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(profile.model_dump_json(indent=2, exclude_defaults=True))
    print(f"\n{len(accepted)} values written to {args.out}; fields left empty become CHECK items")


if __name__ == "__main__":
    main()
