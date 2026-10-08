"""
Web API step 2: sign up, log in, log out, sessions, password change, account deletion, CSRF.

Runs against a separate database, `openart_test`, inside the project's Postgres container
(created here on first use, emptied before every test), so it never touches real data.
Skipped when the container isn't running: start it with `docker compose up -d db`.
"""

import hashlib
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from fastapi.testclient import TestClient
from sqlalchemy import select, text, update

from api import config, db, security
from api.main import app
from api.models import User, UserSession

SITE = "http://localhost:3040"
PASSWORD = "correct horse battery"


@pytest.fixture(scope="module", autouse=True)
def test_database():
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
        _clear_cached_settings()
        command.upgrade(Config("api/alembic.ini"), "head")   # the real migrations, not create_all()
        yield
        db.get_engine().dispose()
    _clear_cached_settings()


def _clear_cached_settings():
    for cached in (config.database_url, config.cookie_secure, config.allowed_origins, db.get_engine):
        cached.cache_clear()


@pytest.fixture
def client():
    with db.get_engine().begin() as conn:
        conn.execute(text("TRUNCATE users CASCADE"))
    security.reset_throttle()
    return TestClient(app)


def signup(client, email="artist@example.com", password=PASSWORD):
    return client.post("/api/auth/signup", json={"email": email, "password": password})


def login(client, email="artist@example.com", password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def rows(model):
    with db.get_engine().connect() as conn:
        return conn.execute(select(model)).all()


# -- sign up -----------------------------------------------------------------------------------------

def test_signup_logs_in_and_lowercases_email(client):
    response = signup(client, email="  Artist@Example.COM ")
    assert response.status_code == 201
    assert client.get("/api/auth/me").json()["email"] == "artist@example.com"


def test_signup_twice_with_same_email_is_refused(client):
    signup(client)
    assert signup(TestClient(app), email="ARTIST@example.com").status_code == 409


@pytest.mark.parametrize("email, password", [("artist@example.com", "short"), ("not-an-email", PASSWORD)])
def test_signup_validates_input(client, email, password):
    assert signup(client, email=email, password=password).status_code == 422
    assert rows(User) == []


def test_password_is_hashed_and_cookie_is_protected(client):
    response = signup(client)
    user = rows(User)[0]
    assert PASSWORD not in user.password_hash and user.password_hash.startswith("$argon2id$")
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie


def test_database_stores_only_the_token_hash(client):
    signup(client)
    token = client.cookies[security.SESSION_COOKIE]
    stored = rows(UserSession)[0].token_hash
    assert stored != token
    assert stored == hashlib.sha256(token.encode()).hexdigest()


# -- log in / log out --------------------------------------------------------------------------------

def test_logout_ends_the_session(client):
    signup(client)
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    assert rows(UserSession) == []


def test_login_with_right_and_wrong_password(client):
    signup(client)
    client.post("/api/auth/logout")
    wrong = login(client, password="wrong password!")
    assert wrong.status_code == 401
    assert login(client).status_code == 200
    assert client.get("/api/auth/me").status_code == 200


def test_unknown_email_gets_the_same_answer_as_wrong_password(client):
    signup(client)
    wrong_password = login(TestClient(app), password="wrong password!")
    unknown_email = login(TestClient(app), email="nobody@example.com")
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


def test_too_many_failed_logins_pause_the_email(client):
    signup(client)
    for _ in range(security.MAX_FAILED_LOGINS):
        assert login(TestClient(app), password="wrong password!").status_code == 401
    # even the right password is refused during the pause
    assert login(TestClient(app)).status_code == 429


def test_expired_session_is_refused(client):
    signup(client)
    with db.get_engine().begin() as conn:
        conn.execute(update(UserSession).values(expires_at=datetime.now(UTC) - timedelta(minutes=1)))
    assert client.get("/api/auth/me").status_code == 401


def test_me_without_cookie_is_refused(client):
    assert client.get("/api/auth/me").status_code == 401


# -- account -----------------------------------------------------------------------------------------

def test_change_password_logs_out_other_browsers(client):
    signup(client)
    other_browser = TestClient(app)
    login(other_browser)

    wrong = client.post("/api/account/password", json={"current_password": "nope nope nope",
                                                       "new_password": "a new passphrase"})
    assert wrong.status_code == 400
    ok = client.post("/api/account/password", json={"current_password": PASSWORD,
                                                    "new_password": "a new passphrase"})
    assert ok.status_code == 204

    assert client.get("/api/auth/me").status_code == 200          # this browser stays logged in
    assert other_browser.get("/api/auth/me").status_code == 401   # the other one is logged out
    assert login(TestClient(app), password="a new passphrase").status_code == 200


def test_delete_account_removes_user_and_sessions(client):
    signup(client)
    assert client.request("DELETE", "/api/account", json={"password": "wrong password!"}).status_code == 400
    assert client.request("DELETE", "/api/account", json={"password": PASSWORD}).status_code == 204
    assert rows(User) == [] and rows(UserSession) == []
    assert client.get("/api/auth/me").status_code == 401


# -- CSRF --------------------------------------------------------------------------------------------

def test_requests_from_another_site_are_refused(client):
    response = client.post("/api/auth/signup", json={"email": "a@example.com", "password": PASSWORD},
                           headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    assert rows(User) == []


def test_requests_from_our_site_are_accepted(client):
    response = client.post("/api/auth/signup", json={"email": "a@example.com", "password": PASSWORD},
                           headers={"Origin": SITE})
    assert response.status_code == 201

