"""Tests for src/rag/documents.py and src/rag/knowledge_base.py, on the fictional example artists
(examples/artists/, written by scripts/make_example_artists.py). No model download: a fake embedder.
Run with: uv run pytest"""

import os

import numpy as np
import pytest

from src.rag.documents import (
    MAX_CHUNK_CHARS,
    DocumentError,
    Line,
    chunk_lines,
    looks_like_heading,
    read_chunks,
)
from src.rag.knowledge_base import ArtistKnowledgeBase

EXAMPLES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples", "artists")
ILKA = os.path.join(EXAMPLES, "ilka_varga")
TOMAS = os.path.join(EXAMPLES, "tomas_ferreira")


def sections(path):
    return [c.section for c in read_chunks(path)]


# -- reading each format ---------------------------------------------------------------------------------

def test_pdf_cv_headings_found_by_section_name_with_page_numbers():
    chunks = read_chunks(os.path.join(ILKA, "cv.pdf"))
    assert "EDUCATION" in [c.section for c in chunks]
    education = next(c for c in chunks if c.section == "EDUCATION")
    assert "MFA in Painting" in education.text and education.page == 1


def test_docx_heading_styles_become_sections():
    assert sections(os.path.join(ILKA, "statement.docx")) == ["Artist statement", "Practice", "Current project",
                                                               "Methods"]


def test_docx_tables_are_read_row_by_row_in_document_order():
    chunks = read_chunks(os.path.join(TOMAS, "cv.docx"))
    table = next(c for c in chunks if c.section == "Exhibitions and performances")
    assert "2023 | Underwater Choir (installation) | Kunsthall Bergen, Norway" in table.text
    assert [c.section for c in chunks].index("Exhibitions and performances") < \
        [c.section for c in chunks].index("Residencies")


def test_markdown_and_plain_text():
    assert sections(os.path.join(TOMAS, "statement.md")) == ["Statement", "Themes", "Collaborations"]
    assert sections(os.path.join(TOMAS, "portfolio.txt")) == ["SELECTED WORKS"]


# -- heading rule and chunk sizes ------------------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("Education", True), ("Group exhibitions:", True), ("RESIDENCIES", True),
    ("2019 MFA Painting", False),                 # digits: a CV entry
    ("I paint.", False), ("Galerie Nord, Vienna", False),
])
def test_looks_like_heading(text, expected):
    assert looks_like_heading(text) is expected


def test_chunks_respect_the_size_limit_and_never_cross_a_heading():
    long_statement = " ".join(f"Sentence number {i} about my practice." for i in range(200))
    lines = [Line("Statement", heading=True), Line(long_statement), Line("Education", heading=True), Line("2019 MFA")]
    chunks = chunk_lines(lines)
    assert all(len(c.text) <= MAX_CHUNK_CHARS for c in chunks)
    assert chunks[-1].section == "Education" and chunks[-1].text == "2019 MFA"
    assert {c.section for c in chunks[:-1]} == {"Statement"}
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_embedded_text_carries_the_section():
    chunk = chunk_lines([Line("Education", heading=True), Line("2019 MFA")])[0]
    assert chunk.embedded_text == "Education\n2019 MFA"


# -- refusing files --------------------------------------------------------------------------------------

def test_unsupported_empty_and_corrupt_files_are_refused(tmp_path):
    (tmp_path / "cv.exe").write_bytes(b"MZ")
    (tmp_path / "empty.txt").write_text("   \n\n")
    (tmp_path / "fake.docx").write_text("not a zip file")
    (tmp_path / "fake.pdf").write_text("not a pdf")
    for name, message in [("cv.exe", "unsupported"), ("empty.txt", "no text"),
                          ("fake.docx", "could not read"), ("fake.pdf", "could not read")]:
        with pytest.raises(DocumentError, match=message):
            read_chunks(str(tmp_path / name))


# -- knowledge base --------------------------------------------------------------------------------------

class FakeEmbedder:
    """A deterministic 4-number vector per text, no model."""
    def passage_embed(self, texts, **kwargs):
        for text in texts:
            yield np.array([len(text), text.count("a"), text.count("e"), 1.0])


def test_knowledge_base_add_replace_remove_and_reload(tmp_path):
    kb = ArtistKnowledgeBase("ilka_varga", root=str(tmp_path), embedder=FakeEmbedder())
    added = kb.add_document(os.path.join(ILKA, "cv.pdf"))
    kb.add_document(os.path.join(ILKA, "statement.docx"))
    assert kb.documents == ["cv.pdf", "statement.docx"]
    assert len(kb.chunks) == len(kb.vectors)
    assert added[1].chunk_id == "cv.pdf#1"
    assert os.path.exists(tmp_path / "ilka_varga" / "raw" / "cv.pdf")  # the untouched original is kept

    n = len(kb.chunks)
    kb.add_document(os.path.join(ILKA, "cv.pdf"))  # same name again: replaced, not duplicated
    assert len(kb.chunks) == n

    reloaded = ArtistKnowledgeBase("ilka_varga", root=str(tmp_path))
    assert reloaded.documents == kb.documents and np.allclose(reloaded.vectors, kb.vectors)

    reloaded.remove_document("cv.pdf")
    assert reloaded.documents == ["statement.docx"] and len(reloaded.chunks) == len(reloaded.vectors)
    assert not os.path.exists(tmp_path / "ilka_varga" / "raw" / "cv.pdf")


@pytest.mark.parametrize("artist_id", ["../escape", "Ilka", "", "a/b", ".hidden"])
def test_artist_ids_that_could_escape_their_folder_are_refused(tmp_path, artist_id):
    with pytest.raises(ValueError):
        ArtistKnowledgeBase(artist_id, root=str(tmp_path))


@pytest.mark.parametrize("name", ["../cv.pdf", ".cv.pdf", "a/b.pdf"])
def test_file_names_that_could_escape_their_folder_are_refused(tmp_path, name):
    kb = ArtistKnowledgeBase("ilka_varga", root=str(tmp_path), embedder=FakeEmbedder())
    with pytest.raises(DocumentError, match="invalid file name"):
        kb.add_document(os.path.join(ILKA, "cv.pdf"), name=name)
