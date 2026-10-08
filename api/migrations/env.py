"""Alembic entry point: connects to DATABASE_URL and applies the migrations in versions/."""

from alembic import context
from sqlalchemy import create_engine

from api.config import database_url
from api.db import Base
import api.models  # noqa: F401  (registers the tables on Base.metadata, for `alembic check`)

target_metadata = Base.metadata

with create_engine(database_url()).connect() as connection:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()
