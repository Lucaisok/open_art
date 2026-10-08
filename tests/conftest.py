"""
Shared by the web API tests (test_api_auth.py, test_api_documents.py).

They run against a separate database, `openart_test`, inside the project's Postgres container
(created here on first use, emptied before every test), so they never touch real data, and
keep uploads in a temporary folder. Skipped when the container isn't running: start it with
`docker compose up -d db`. A test module opts in with
    pytestmark = pytest.mark.usefixtures("api_database")
"""

import shutil

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from fastapi.testclient import TestClient
from sqlalchemy import text

from api import config, db, security
from api.main import app

SITE = "http://localhost:3040"
PASSWORD = "correct horse battery"


@pytest.fixture(scope="session")
def api_database(tmp_path_factory):
    env = dotenv_values(".env")
    if not env.get("POSTGRES_PASSWORD"):
        pytest.skip("no POSTGRES_* settings in .env (see .env.example)")
    user, password, main_db = env["POSTGRES_USER"], env["POSTGRES_PASSWORD"], env["POSTGRES_DB"]

    # create the test database the first time (CREATE DATABASE can't run inside a transaction)
    try:
        with psycopg.connect(host="127.0.0.1", port=5434, user=user, password=password, dbname=main_db,
                             autocommit=True, connect_timeout=3) as conn:
            if conn.execute("SELECT 1 FROM pg_database WHERE datname = 'openart_test'").fetchone() is None:
                conn.execute("CREATE DATABASE openart_test")
    except psycopg.OperationalError:
        pytest.skip("Postgres container not running (docker compose up -d db)")

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("DATABASE_URL", f"postgresql+psycopg://{user}:{password}@127.0.0.1:5434/openart_test")
        mp.setenv("ALLOWED_ORIGINS", SITE)
        mp.setenv("COOKIE_SECURE", "false")      # the test client talks plain http
        mp.setenv("UPLOADS_DIR", str(tmp_path_factory.mktemp("uploads")))
        _clear_cached_settings()
        command.upgrade(Config("api/alembic.ini"), "head")   # the real migrations, not create_all()
        yield
        db.get_engine().dispose()
    _clear_cached_settings()


def _clear_cached_settings():
    for cached in (config.database_url, config.cookie_secure, config.allowed_origins, config.uploads_dir,
                   db.get_engine):
        cached.cache_clear()


@pytest.fixture
def client(api_database):
    """A fresh API client on an empty database and an empty uploads folder."""
    with db.get_engine().begin() as conn:
        conn.execute(text("TRUNCATE users CASCADE"))
    shutil.rmtree(config.uploads_dir(), ignore_errors=True)
    security.reset_throttle()
    return TestClient(app)
