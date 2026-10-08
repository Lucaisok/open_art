"""
Web API step 3: upload / replace / delete documents, their files on disk, who can see them,
and retrieval from Postgres (api/knowledge_base.py) matching the file version.

Uses the test database from tests/conftest.py and the fictional example artists. No model
download: a fake embedder counts a few keywords (as in test_rag_retrieval.py), padded to the
768 dimensions of the database column.
"""

import os
import uuid

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api import config, db, knowledge_base
from api.knowledge_base import PgKnowledgeBase
from api.main import app
from api.models import Document, KnowledgeChunkRow
from src.rag.documents import MAX_FILE_BYTES
from src.rag.knowledge_base import ArtistKnowledgeBase
from tests.conftest import PASSWORD

pytestmark = pytest.mark.usefixtures("api_database")

EXAMPLES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples", "artists")
ILKA = os.path.join(EXAMPLES, "ilka_varga")
TOMAS = os.path.join(EXAMPLES, "tomas_ferreira")

KEYWORDS = ["education", "mfa", "residenc", "exhibition", "statement", "paint"]


class KeywordEmbedder:
    """One count per keyword, plus a small constant so no vector is all zeros; zeros up to 768."""
    def _vector(self, text):
        text = text.lower()
        counts = [text.count(word) for word in KEYWORDS] + [0.1]
        return np.array(counts + [0.0] * (768 - len(counts)), dtype=np.float32)

    def passage_embed(self, texts, **kwargs):
        for text in texts:
            yield self._vector(text)

    def query_embed(self, query, **kwargs):
        yield self._vector(query)


@pytest.fixture(autouse=True)
def fake_embedder(monkeypatch):
    embedder = KeywordEmbedder()
    monkeypatch.setattr(knowledge_base, "get_embedder", lambda: embedder)
    return embedder


@pytest.fixture
def artist(client):
    """A logged-in client."""
    assert client.post("/api/auth/signup", json={"email": "artist@example.com", "password": PASSWORD}).status_code == 201
    return client


def upload(client, kind, path, name=None):
    with open(path, "rb") as f:
        return client.put(f"/api/documents/{kind}", files={"file": (name or os.path.basename(path), f)})


def upload_bytes(client, kind, name, content: bytes):
    return client.put(f"/api/documents/{kind}", files={"file": (name, content)})


def user_id(client) -> uuid.UUID:
    return uuid.UUID(client.get("/api/auth/me").json()["id"])


def files_of(client) -> list[str]:
    folder = os.path.join(config.uploads_dir(), str(user_id(client)))
    return sorted(os.listdir(folder)) if os.path.isdir(folder) else []


def count(model) -> int:
    with Session(db.get_engine()) as session:
        return session.scalar(select(func.count()).select_from(model))


# -- upload, list, replace, delete -------------------------------------------------------------------

def test_upload_reads_the_file_and_lists_it(artist):
    response = upload(artist, "cv", os.path.join(ILKA, "cv.pdf"))
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "cv" and body["file_name"] == "cv.pdf" and body["chunk_count"] == 8
    assert [d["kind"] for d in artist.get("/api/documents").json()] == ["cv"]
    assert count(KnowledgeChunkRow) == 8
    assert len(files_of(artist)) == 1 and files_of(artist)[0].endswith(".pdf")


def test_upload_into_a_filled_slot_replaces_it(artist):
    upload(artist, "cv", os.path.join(ILKA, "cv.pdf"))
    old_files = files_of(artist)
    response = upload(artist, "cv", os.path.join(TOMAS, "cv.docx"))
    assert response.status_code == 200
    documents = artist.get("/api/documents").json()
    assert len(documents) == 1 and documents[0]["file_name"] == "cv.docx"
    assert count(KnowledgeChunkRow) == documents[0]["chunk_count"]
    assert len(files_of(artist)) == 1 and files_of(artist) != old_files   # the old file is gone


def test_three_slots_are_independent(artist):
    upload(artist, "cv", os.path.join(TOMAS, "cv.docx"))
    upload(artist, "statement", os.path.join(TOMAS, "statement.md"))
    upload(artist, "portfolio", os.path.join(TOMAS, "portfolio.txt"))
    assert [d["kind"] for d in artist.get("/api/documents").json()] == ["cv", "portfolio", "statement"]
    assert artist.delete("/api/documents/statement").status_code == 204
    assert [d["kind"] for d in artist.get("/api/documents").json()] == ["cv", "portfolio"]
    assert len(files_of(artist)) == 2


def test_delete_removes_rows_and_file(artist):
    upload(artist, "cv", os.path.join(ILKA, "cv.pdf"))
    assert artist.delete("/api/documents/cv").status_code == 204
    assert artist.get("/api/documents").json() == []
    assert count(Document) == 0 and count(KnowledgeChunkRow) == 0
    assert files_of(artist) == []
    assert artist.delete("/api/documents/cv").status_code == 404


def test_unknown_slot_is_refused(artist):
    assert upload(artist, "passport", os.path.join(ILKA, "cv.pdf")).status_code == 422


def test_same_file_name_in_two_slots_is_refused(artist):
    upload(artist, "cv", os.path.join(ILKA, "cv.pdf"))
    assert upload(artist, "portfolio", os.path.join(ILKA, "cv.pdf")).status_code == 409


# -- bad files ---------------------------------------------------------------------------------------

def test_wrong_file_type_is_refused(artist):
    response = upload_bytes(artist, "cv", "cv.exe", b"MZ...")
    assert response.status_code == 400
    assert count(Document) == 0 and files_of(artist) == []


def test_file_over_the_size_cap_is_refused(artist):
    response = upload_bytes(artist, "cv", "cv.txt", b"a" * (MAX_FILE_BYTES + 1))
    assert response.status_code == 413
    assert count(Document) == 0 and files_of(artist) == []


def test_unreadable_file_keeps_the_previous_document(artist):
    upload(artist, "cv", os.path.join(ILKA, "cv.pdf"))
    before = files_of(artist)
    response = upload_bytes(artist, "cv", "broken.pdf", b"this is not a pdf")
    assert response.status_code == 400
    assert "couldn't read" in response.json()["detail"]
    assert artist.get("/api/documents").json()[0]["file_name"] == "cv.pdf"
    assert files_of(artist) == before and count(KnowledgeChunkRow) == 8


def test_file_name_is_only_displayed(artist):
    response = upload(artist, "cv", os.path.join(ILKA, "cv.pdf"), name="../../etc/Lebenslauf é.pdf")
    assert response.json()["file_name"] == "Lebenslauf é.pdf"
    stored = files_of(artist)[0]
    assert stored != "Lebenslauf é.pdf" and uuid.UUID(stored.removesuffix(".pdf"))


# -- privacy -----------------------------------------------------------------------------------------

def test_logged_out_visitors_get_nothing(client):
    assert client.get("/api/documents").status_code == 401
    assert upload(client, "cv", os.path.join(ILKA, "cv.pdf")).status_code == 401


def test_other_users_documents_are_invisible(artist):
    upload(artist, "cv", os.path.join(ILKA, "cv.pdf"))
    other = TestClient(app)
    other.post("/api/auth/signup", json={"email": "other@example.com", "password": PASSWORD})
    assert other.get("/api/documents").json() == []
    assert other.delete("/api/documents/cv").status_code == 404
    assert len(artist.get("/api/documents").json()) == 1


def test_deleting_the_account_removes_documents_and_files(artist):
    upload(artist, "cv", os.path.join(ILKA, "cv.pdf"))
    folder = os.path.join(config.uploads_dir(), str(user_id(artist)))
    assert artist.request("DELETE", "/api/account", json={"password": PASSWORD}).status_code == 204
    assert count(Document) == 0 and count(KnowledgeChunkRow) == 0
    assert not os.path.exists(folder)


# -- retrieval from Postgres -------------------------------------------------------------------------

def test_postgres_retrieval_matches_the_file_version(artist, fake_embedder, tmp_path):
    upload(artist, "cv", os.path.join(ILKA, "cv.pdf"))
    upload(artist, "statement", os.path.join(ILKA, "statement.docx"))
    files = ArtistKnowledgeBase("ilka_varga", root=str(tmp_path), embedder=fake_embedder)
    files.add_document(os.path.join(ILKA, "cv.pdf"))
    files.add_document(os.path.join(ILKA, "statement.docx"))

    with Session(db.get_engine()) as session:
        pg = PgKnowledgeBase(session, user_id(artist), embedder=fake_embedder)
        assert pg.documents == files.documents
        for question, documents in [("Where did the artist study? Education, MFA", None),
                                    ("residencies", ["cv.pdf"]), ("painting statement", None)]:
            expected = files.retrieve(question, k=3, documents=documents)
            got = pg.retrieve(question, k=3, documents=documents)
            assert [p.chunk for p in got] == [p.chunk for p in expected]
            assert [p.score for p in got] == pytest.approx([p.score for p in expected], abs=1e-5)
        with pytest.raises(KeyError):
            pg.retrieve("education", documents=["missing.pdf"])
