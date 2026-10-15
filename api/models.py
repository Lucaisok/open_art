"""
Database tables. Every change here needs an Alembic migration (api/migrations/versions/).

Ids are random UUIDs, so they don't reveal how many users exist or let anyone
guess another user's id.
"""

import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True)   # stored lowercased
    password_hash: Mapped[str] = mapped_column(String(255))        # argon2, never the password itself
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # set by the last onboarding step ("Continue to Discover"); None while onboarding
    onboarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

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
    # a PDF's text lines per page (puts a work's images with its title page) and whether its images
    # were read (api/images.py read_document_images: at upload, or on first use for older documents)
    page_lines: Mapped[list | None] = mapped_column(JSONB)
    images_read: Mapped[bool] = mapped_column(Boolean, server_default="false")

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
    # ids of the documents whose suggestions the artist has seen and saved: not offered again.
    # A new upload has a new id, so its suggestions are offered. (Ids of deleted documents just linger.)
    reviewed_documents: Mapped[list] = mapped_column(JSONB, server_default="[]")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())


# -- projects: past, current and planned work, and interests (workflow.MD, "Projects page") ------------

class Project(Base):
    """One project or interest the artist saved: added by hand, or a suggestion read from their
    documents by rules (src/rag/project_rules.py) that they accepted. Nothing is stored unreviewed."""
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10))              # "project" or "interest"
    title: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(String(10))     # past / current / planned; None for an interest
    category: Mapped[str | None] = mapped_column(String(12))   # work / exhibition / performance / commission
    years: Mapped[str | None] = mapped_column(String(30))      # "2025", "2024–"
    summary: Mapped[str | None] = mapped_column(Text)
    medium: Mapped[str | None] = mapped_column(Text)
    venues: Mapped[list] = mapped_column(JSONB, server_default="[]")
    sources: Mapped[list] = mapped_column(JSONB, server_default="[]")   # [{quote, citation}] when from documents
    suggestion_key: Mapped[str | None] = mapped_column(Text)            # the suggestion it was accepted from
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())


class ProjectImage(Base):
    """One image of a project: read from the artist's PDF (document_id, page) or uploaded by hand. The
    files are on disk (api/images.py: image_path), re-encoded as JPEG without metadata. An image read
    from a document belongs to no project until the artist saves the project it was found with."""
    __tablename__ = "project_images"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"),
                                                          index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"),
                                                         index=True)
    page: Mapped[int | None] = mapped_column(Integer)                    # 1-based, in its document
    position: Mapped[int] = mapped_column(Integer, server_default="0")  # order within its project
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DismissedSuggestion(Base):
    """A suggestion the artist declined: not offered again (until its text changes)."""
    __tablename__ = "dismissed_suggestions"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    key: Mapped[str] = mapped_column(Text, primary_key=True)


# -- step 6: the application agent (workflow.MD, "Step 6 — Application agent") -------------------------

class Application(Base):
    """An artist's application to one call: created on the first draft, tick or message. What the call
    asks for is not stored: src/agent/checklist.py reads it from the corpus every time."""
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("user_id", "opportunity_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    opportunity_id: Mapped[str] = mapped_column(String(100))     # ProcessedOpportunity.id in the corpus
    # the projects the artist chose for this application: {"proposing": id | None, "mention": [ids]}.
    # None = not chosen yet: the suggested ones are used (api/applications.py suggested_projects)
    projects: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    items: Mapped[list["ApplicationItem"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)


class ApplicationItem(Base):
    """The artist's work on one checklist item (ChecklistItem.key): a draft and its review status for
    an item to write, or the artist's own tick for an item to gather."""
    __tablename__ = "application_items"

    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"),
                                                      primary_key=True)
    key: Mapped[str] = mapped_column(String(20), primary_key=True)
    draft: Mapped[str | None] = mapped_column(Text)
    # None (no draft yet) -> "draft" -> "confirmed". Only the artist's "I have reviewed this" sets
    # "confirmed", and any later change to the text sets it back to "draft"
    status: Mapped[str | None] = mapped_column(String(10))
    ticked: Mapped[bool] = mapped_column(Boolean, server_default="false")   # "I have this" (gather items)
    # the artist's "Not needed" on an item the call seems to ask for (the extraction can be wrong):
    # it no longer blocks the download and stays out of the zip, until the artist undoes it
    skipped: Mapped[bool] = mapped_column(Boolean, server_default="false")
    # this text's own choice of projects, same shape as Application.projects; None = the application's
    projects: Mapped[dict | None] = mapped_column(JSONB)
    # the images chosen for an image item (ChecklistItem.images): [image id, ...]; None = none chosen
    images: Mapped[list | None] = mapped_column(JSONB)
    # a text the artist added themselves (key "t-..."), with their own title; None = a checklist item
    title: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())


class SavedCall(Base):
    """A call the artist saved (Discover's Save, or by starting an application). The title and
    deadline are copied from the corpus at saving: the Studio still lists a call that is gone."""
    __tablename__ = "saved_calls"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    deadline: Mapped[date | None] = mapped_column(Date)
    saved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AgentMessage(Base):
    """One message of the chat about one item: the artist's, or the agent's reply."""
    __tablename__ = "agent_messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"),
                                                      index=True)
    item_key: Mapped[str] = mapped_column(String(20))
    role: Mapped[str] = mapped_column(String(10))                  # "artist" or "agent"
    content: Mapped[str] = mapped_column(Text)
    # the agent's: the citations of the passages it relied on ("cv.pdf · p. 1 · EDUCATION")
    sources: Mapped[list] = mapped_column(JSONB, server_default="[]")
    # an agent reply that changed the draft: the new version's length in words; None otherwise
    wrote_words: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
