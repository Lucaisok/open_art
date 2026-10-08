"""
Database tables. Every change here needs an Alembic migration (api/migrations/versions/).

Ids are random UUIDs, so they don't reveal how many users exist or let anyone
guess another user's id.
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True)   # stored lowercased
    password_hash: Mapped[str] = mapped_column(String(255))        # argon2, never the password itself
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # deleting a user deletes their sessions, documents and chunks (ON DELETE CASCADE in the
    # database; passive_deletes lets Postgres do it instead of loading every row first)
    sessions: Mapped[list["UserSession"]] = relationship(back_populates="user", cascade="all, delete-orphan",
                                                         passive_deletes=True)
    documents: Mapped[list["Document"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)


class UserSession(Base):
    """A login. The browser holds the token; only its SHA-256 hash is stored here."""
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="sessions")


# -- step 3: documents and the knowledge base ---------------------------------------------------------

DOCUMENT_KINDS = ("cv", "statement", "portfolio")   # one slot each per artist
EMBEDDING_DIMENSIONS = 768                          # BAAI/bge-base-en-v1.5 (src/matching/index.py)


class Document(Base):
    """An uploaded file. The file itself is on disk (api/documents.py: stored_path); this row
    only describes it. `file_name` is the artist's own name for it, shown, never used as a path."""
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("user_id", "kind"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))           # one of DOCUMENT_KINDS
    file_name: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(Integer)
    chunk_count: Mapped[int] = mapped_column(Integer)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    chunks: Mapped[list["KnowledgeChunkRow"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)


class KnowledgeChunkRow(Base):
    """One passage of a document with its embedding: the Postgres form of
    src/rag/knowledge_base.py's KnowledgeChunk + its row in vectors.npz."""
    __tablename__ = "knowledge_chunks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    index: Mapped[int] = mapped_column(Integer)             # position within its document
    section: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    embedding = mapped_column(Vector(EMBEDDING_DIMENSIONS), nullable=False)   # normalized
    # what made the embedding: retrieval refuses rows made by another model or version
    model: Mapped[str] = mapped_column(String(100))
    fastembed_version: Mapped[str] = mapped_column(String(20))


# -- step 4: the artist profile -----------------------------------------------------------------------

class Profile(Base):
    """The artist's eligibility profile: one row per artist, written only by the artist's own Save.
    `values` is checked by api/profile.py (ArtistProfile's validators) before it is stored;
    `evidence` holds, for values accepted from the CV, the quote and where it is."""
    __tablename__ = "profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    values: Mapped[dict] = mapped_column(JSONB)
    evidence: Mapped[dict] = mapped_column(JSONB)
    # the CV whose suggestions the artist has seen and saved: they aren't offered again until a new CV
    reviewed_document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())
