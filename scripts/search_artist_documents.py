"""
Try RAG retrieval from the command line: the same ArtistKnowledgeBase.retrieve() the app will call.

    # add documents to an artist's knowledge base (stored under data/artists/<artist_id>/), then search
    uv run python scripts/search_artist_documents.py ilka_varga "where did she study" --add examples/artists/ilka_varga/*
    uv run python scripts/search_artist_documents.py ilka_varga "residencies abroad" -k 3 --document cv.pdf

Prints each passage with its similarity score and where it comes from (file, page, section).
"""

import argparse
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from src.rag.knowledge_base import ArtistKnowledgeBase  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("artist_id")
    parser.add_argument("question")
    parser.add_argument("-k", type=int, default=5, help="number of passages (default 5)")
    parser.add_argument("--document", action="append", help="search only this file (by name), repeatable")
    parser.add_argument("--add", nargs="+", default=[], help="files to add (or replace) before searching")
    args = parser.parse_args()

    kb = ArtistKnowledgeBase(args.artist_id)
    for path in args.add:
        print(f"added {os.path.basename(path)}: {len(kb.add_document(path))} chunks")
    if not kb.documents:
        sys.exit(f"no documents for {args.artist_id!r} yet: add some with --add")

    for rank, passage in enumerate(kb.retrieve(args.question, k=args.k, documents=args.document), start=1):
        print(f"\n{rank}. [{passage.score:.3f}] {passage.citation}")
        print("   " + passage.chunk.text.replace("\n", "\n   "))


if __name__ == "__main__":
    main()
