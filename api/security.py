"""
Login building blocks: password hashing, session tokens, the login throttle, the CSRF check.
"""

import hashlib
import secrets
import time
from collections import defaultdict, deque

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import HTTPException, Request

from api.config import allowed_origins

# -- passwords ---------------------------------------------------------------------------------------

MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 200   # long enough for any passphrase; stops huge inputs from costing hashing time

_hasher = PasswordHasher()  # argon2id with the library's recommended settings


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


# Checked when the email is unknown, so a wrong email takes as long as a wrong password
# and the response time doesn't reveal which emails have an account.
_DUMMY_HASH = _hasher.hash("not-a-real-password")


def waste_time_like_a_password_check(password: str) -> None:
    verify_password(_DUMMY_HASH, password)


# -- session tokens ----------------------------------------------------------------------------------

SESSION_COOKIE = "openart_session"
SESSION_DAYS = 30


def new_session_token() -> str:
    """The random value the browser keeps in its cookie (256 bits)."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """What the database stores. A plain SHA-256 is enough here: the token is random, not a password."""
    return hashlib.sha256(token.encode()).hexdigest()


# -- login throttle ----------------------------------------------------------------------------------
# Kept in memory: the API runs as one process, and a restart clearing the counters is harmless.

MAX_FAILED_LOGINS = 5
THROTTLE_SECONDS = 15 * 60

_failed_logins: dict[str, deque[float]] = defaultdict(deque)


def _recent_failures(email: str, now: float) -> deque[float]:
    failures = _failed_logins[email]
    while failures and now - failures[0] > THROTTLE_SECONDS:
        failures.popleft()
    return failures


def check_login_allowed(email: str) -> None:
    """Raises 429 after MAX_FAILED_LOGINS failures for this email in the last 15 minutes."""
    if len(_recent_failures(email, time.monotonic())) >= MAX_FAILED_LOGINS:
        raise HTTPException(429, "Too many failed attempts. Try again in 15 minutes.")


def record_failed_login(email: str) -> None:
    _failed_logins[email].append(time.monotonic())


def clear_failed_logins(email: str) -> None:
    _failed_logins.pop(email, None)


def reset_throttle() -> None:
    """For tests."""
    _failed_logins.clear()


# -- CSRF --------------------------------------------------------------------------------------------

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def check_origin(request: Request) -> None:
    """
    Refuses requests that change data when the browser says they come from another site.

    Browsers always send `Origin` on these requests, and a page can't fake it. Requests
    without the header don't come from a browser (curl, tests), so they can't carry a
    victim's cookie by surprise, and are let through. The SameSite=Lax cookie is a second
    layer on top of this.
    """
    origin = request.headers.get("origin")
    if request.method in UNSAFE_METHODS and origin is not None and origin.rstrip("/") not in allowed_origins():
        raise HTTPException(403, "Request refused: it doesn't come from the OpenArt site.")
