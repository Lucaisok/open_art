"""Database connection: one engine for the process, one session per request."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session

from api.config import database_url


class Base(DeclarativeBase):
    """Parent class of every table (api/models.py)."""


@lru_cache
def get_engine() -> Engine:
    # pool_pre_ping: replace connections the database closed (e.g. after a Postgres restart)
    return create_engine(database_url(), pool_pre_ping=True)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: a session per request, closed afterwards. Routes commit themselves."""
    with Session(get_engine()) as session:
        yield session
