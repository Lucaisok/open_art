"""
One artist's knowledge base, stored in Postgres (pgvector): the web app's version of
src/rag/knowledge_base.py.

    kb = PgKnowledgeBase(db, user_id)
    kb.documents                              # ["cv-2026.pdf", "statement.docx"]
    kb.retrieve("Where did the artist study?", k=3, documents=["cv-2026.pdf"])
    -> [RetrievedPassage(chunk=..., score=0.74), ...]

`documents` and `retrieve` behave exactly like the file version's, so the RAG steps
(profile_prefill, query_suggestion) work with either. Adding and removing documents
is done by api/documents.py, which also handles the uploaded file; this module only
turns a file into chunk rows (`build_chunks`) and searches them.

The file version stays for the offline scripts and the RAG evaluation (workflow.MD,
web app step 3). Both share the reader/chunker (src/rag/documents.py), the embedding
model and its helpers (src/matching/index.py).

Retrieval is exact: Postgres compares the question with every chunk of this artist
(`<=>`, cosine distance). An artist has a few dozen chunks, so no vector index is needed.
"""

import uuid
from functools import lru_cache
from importlib.metadata import version

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.models import Document, KnowledgeChunkRow
from src.matching.index import EMBEDDING_MODEL, embed_passages, embed_query, load_embedder
from src.rag.documents import read_chunks
from src.rag.knowledge_base import KnowledgeChunk, RetrievedPassage


@lru_cache
def get_embedder():
    """The embedding model, loaded once per API process on first use (~1 s, ~0.5 GB of RAM).
    The Docker image downloads it at build time, so this never waits for a download."""
    return load_embedder(EMBEDDING_MODEL)


def build_chunks(path: str, user_id: uuid.UUID, embedder=None) -> list[KnowledgeChunkRow]:
    """Read, chunk and embed one file into rows (not yet saved).
    Raises src.rag.documents.DocumentError, with a message safe to show, on a file we won't read."""
    chunks = read_chunks(path)
    vectors = embed_passages(embedder or get_embedder(), [c.embedded_text for c in chunks])
    fastembed_version = version("fastembed")
    return [
        KnowledgeChunkRow(user_id=user_id, index=c.index, section=c.section, text=c.text, page=c.page,
                          embedding=vector, model=EMBEDDING_MODEL, fastembed_version=fastembed_version)
        for c, vector in zip(chunks, vectors)
    ]


class PgKnowledgeBase:
    def __init__(self, db: Session, user_id: uuid.UUID, embedder=None):
        self.db = db
        self.user_id = user_id
        self._embedder = embedder    # tests pass a fake one; otherwise the shared model

    @property
    def embedder(self):
        return self._embedder or get_embedder()

    @property
    def documents(self) -> list[str]:
        """The artist's documents, by file name (as in the file version)."""
        return sorted(self.db.scalars(select(Document.file_name).where(Document.user_id == self.user_id)))

    def retrieve(self, question: str, k: int = 5, documents: list[str] | None = None) -> list[RetrievedPassage]:
        """The k chunks closest to the question, best first. `documents` limits the search to some
        files (by file name). Same rules as ArtistKnowledgeBase.retrieve."""
        if not question or not question.strip():
            raise ValueError("question is empty")
        if documents is not None:
            unknown = set(documents) - set(self.documents)
            if unknown:
                raise KeyError(f"no document named {sorted(unknown)[0]!r}")
        if k <= 0:
            return []

        query_vector = embed_query(self.embedder, question)
        distance = KnowledgeChunkRow.embedding.cosine_distance(query_vector)
        statement = (
            select(KnowledgeChunkRow, Document.file_name, distance)
            .join(Document, KnowledgeChunkRow.document_id == Document.id)
            .where(KnowledgeChunkRow.user_id == self.user_id)
            # ties keep file order, as in the file version
            .order_by(distance, Document.uploaded_at, KnowledgeChunkRow.index)
            .limit(k)
        )
        if documents is not None:
            statement = statement.where(Document.file_name.in_(documents))
        rows = self.db.execute(statement).all()

        # a different model or fastembed version would make the scores silently wrong: refuse
        if any(row.model != EMBEDDING_MODEL or row.fastembed_version != version("fastembed")
               for row, _, _ in rows):
            raise RuntimeError("knowledge base is out of date: re-upload the documents")

        return [
            RetrievedPassage(
                chunk=KnowledgeChunk(chunk_id=f"{file_name}#{row.index}", document=file_name, index=row.index,
                                     section=row.section, text=row.text, page=row.page),
                score=1.0 - float(dist),     # cosine distance -> cosine similarity
            )
            for row, file_name, dist in rows
        ]
