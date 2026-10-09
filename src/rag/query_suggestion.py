"""
OpenArt — suggest the semantic-matching query from the artist's statement (RAG step 4).

    suggestion = suggest_query(kb, documents=["statement.md"])
    suggestion.query      # the statement passages about the practice and its wishes, as written
    suggestion.passages   # where they come from, with citations

In the web app the query is not shown as a text box: Discover's "Matched to you" ranks by it
directly (api/discover.py, workflow.MD step 5b). The artist steers the results with the filters;
opportunity-type filters are left to the artist (product-owner decision, see workflow.MD).

No LLM: an LLM-written query was compared with the passages themselves and ranked no better
(workflow.MD, RAG step 4), so the query is the artist's own words. Runs locally, costs nothing.
"""

from dataclasses import dataclass, field

from src.rag.knowledge_base import ArtistKnowledgeBase, RetrievedPassage

PASSAGES_PER_QUERY = 3
QUERIES = [
    "artistic practice, themes, subjects, materials and methods",
    "kinds of opportunities the artist is looking for: residencies, grants, commissions, exhibitions",
]


@dataclass
class QuerySuggestion:
    query: str                                                         # "" = nothing to suggest
    passages: list[RetrievedPassage] = field(default_factory=list)    # what the query is made of


def gather_passages(kb: ArtistKnowledgeBase, documents: list[str] | None = None) -> list[RetrievedPassage]:
    """Top passages for every query, each once, in document order (so the text reads as written)."""
    found = {}
    for query in QUERIES:
        for passage in kb.retrieve(query, k=PASSAGES_PER_QUERY, documents=documents):
            found[passage.chunk.chunk_id] = passage
    return sorted(found.values(), key=lambda p: (p.chunk.document, p.chunk.index))


def suggest_query(kb: ArtistKnowledgeBase, documents: list[str] | None = None) -> QuerySuggestion:
    """The query for the artist to review. `documents` limits the search (normally the statement).
    The passages are joined as written; the embedder reads the first 512 tokens (~2,000 characters),
    which covers a typical statement's practice and wishes."""
    passages = gather_passages(kb, documents)
    return QuerySuggestion(query="\n".join(p.chunk.text for p in passages), passages=passages)
