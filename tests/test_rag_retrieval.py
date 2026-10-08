"""Tests for ArtistKnowledgeBase.retrieve (src/rag/knowledge_base.py) on the fictional example artists.
No model download: a fake embedder that counts a few keywords, so the expected ranking is obvious.
Run with: uv run pytest"""

import os

import numpy as np
import pytest

from src.rag.knowledge_base import ArtistKnowledgeBase, KnowledgeChunk, RetrievedPassage

EXAMPLES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples", "artists")
ILKA = os.path.join(EXAMPLES, "ilka_varga")

KEYWORDS = ["education", "mfa", "residenc", "exhibition", "statement", "paint"]


class KeywordEmbedder:
    """One count per keyword, plus a small constant so no vector is all zeros."""
    def _vector(self, text):
        text = text.lower()
        return np.array([text.count(word) for word in KEYWORDS] + [0.1], dtype=np.float32)

    def passage_embed(self, texts, **kwargs):
        for text in texts:
            yield self._vector(text)

    def query_embed(self, query, **kwargs):
        yield self._vector(query)


@pytest.fixture
def kb(tmp_path):
    kb = ArtistKnowledgeBase("ilka_varga", root=str(tmp_path), embedder=KeywordEmbedder())
    kb.add_document(os.path.join(ILKA, "cv.pdf"))
    kb.add_document(os.path.join(ILKA, "statement.docx"))
    return kb


def test_best_match_first_with_scores_in_descending_order(kb):
    passages = kb.retrieve("education and degrees", k=3)
    assert passages[0].chunk.section == "EDUCATION"
    scores = [p.score for p in passages]
    assert scores == sorted(scores, reverse=True) and len(passages) == 3


def test_document_filter_searches_only_those_files(kb):
    passages = kb.retrieve("education", k=50, documents=["statement.docx"])
    assert passages and {p.chunk.document for p in passages} == {"statement.docx"}
    with pytest.raises(KeyError):
        kb.retrieve("education", documents=["portfolio.pdf"])


def test_k_larger_than_the_knowledge_base_returns_every_chunk(kb):
    assert len(kb.retrieve("residencies", k=1000)) == len(kb.chunks)


def test_citation_names_file_page_and_section():
    chunk = KnowledgeChunk(chunk_id="cv.pdf#1", document="cv.pdf", index=1, section="EDUCATION",
                           text="2019 MFA", page=1)
    assert RetrievedPassage(chunk=chunk, score=0.5).citation == "cv.pdf · p. 1 · EDUCATION"
    no_page = chunk.model_copy(update={"document": "statement.md", "page": None, "section": None})
    assert RetrievedPassage(chunk=no_page, score=0.5).citation == "statement.md"


def test_empty_question_is_refused_and_empty_knowledge_base_returns_nothing(kb, tmp_path):
    with pytest.raises(ValueError):
        kb.retrieve("   ")
    empty = ArtistKnowledgeBase("nobody", root=str(tmp_path), embedder=KeywordEmbedder())
    assert empty.retrieve("education") == []


def test_vectors_from_another_fastembed_version_are_refused(kb, tmp_path):
    path = tmp_path / "ilka_varga" / "vectors.npz"
    with np.load(path, allow_pickle=False) as data:
        vectors, model = data["vectors"], data["model"]
    np.savez(path, vectors=vectors, model=model, fastembed_version=np.array("0.0.1"))
    with pytest.raises(RuntimeError, match="out of date"):
        ArtistKnowledgeBase("ilka_varga", root=str(tmp_path))
