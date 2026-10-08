"""
Database tables. Every change here needs an Alembic migration (api/migrations/versions/).

Ids are random UUIDs, so they don't reveal how many users exist or let anyone
guess another user's id.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True)   # stored lowercased
    password_hash: Mapped[str] = mapped_column(String(255))        # argon2, never the password itself
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # deleting a user deletes their sessions (and, in later steps, everything else of theirs)
    sessions: Mapped[list["UserSession"]] = relationship(back_populates="user", cascade="all, delete-orphan",
                                                         passive_deletes=True)


class UserSession(Base):
    """A login. The browser holds the token; only its SHA-256 hash is stored here."""
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="sessions")
