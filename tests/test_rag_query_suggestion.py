"""Tests for src/rag/query_suggestion.py on the fictional example artists. No model download: the
keyword fake embedder from test_rag_retrieval. Run with: uv run pytest"""

import os

from src.rag.knowledge_base import ArtistKnowledgeBase
from src.rag.query_suggestion import PASSAGES_PER_QUERY, QUERIES, suggest_query
from tests.test_rag_retrieval import ILKA, KeywordEmbedder


def make_kb(tmp_path):
    kb = ArtistKnowledgeBase("ilka_varga", root=str(tmp_path), embedder=KeywordEmbedder())
    kb.add_document(os.path.join(ILKA, "cv.pdf"))
    kb.add_document(os.path.join(ILKA, "statement.docx"))
    return kb


def test_query_is_the_chosen_documents_passages_in_document_order_each_once(tmp_path):
    suggestion = suggest_query(make_kb(tmp_path), documents=["statement.docx"])
    assert {p.chunk.document for p in suggestion.passages} == {"statement.docx"}
    indexes = [p.chunk.index for p in suggestion.passages]
    assert indexes == sorted(set(indexes))
    assert len(indexes) <= PASSAGES_PER_QUERY * len(QUERIES)
    assert suggestion.query == "\n".join(p.chunk.text for p in suggestion.passages)


def test_no_documents_gives_an_empty_query(tmp_path):
    kb = ArtistKnowledgeBase("nobody", root=str(tmp_path), embedder=KeywordEmbedder())
    suggestion = suggest_query(kb)
    assert suggestion.query == "" and suggestion.passages == []
