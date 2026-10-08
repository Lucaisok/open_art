"""
Accounts and sessions: sign up, log in, log out, "who am I".

Flow: a successful sign-up or login creates a random token. The browser gets it in an
httpOnly cookie (JavaScript can't read it), the database keeps only its hash. Every later
request is matched to its user through `current_user`.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from api import security
from api.config import cookie_secure
from api.db import get_db
from api.models import User, UserSession

router = APIRouter(prefix="/api/auth", tags=["auth"])

DB = Annotated[Session, Depends(get_db)]


# -- request / response shapes ---------------------------------------------------------------------

class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=security.MIN_PASSWORD_LENGTH, max_length=security.MAX_PASSWORD_LENGTH)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=security.MAX_PASSWORD_LENGTH)   # no minimum: just check it


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    created_at: datetime


# -- helpers ---------------------------------------------------------------------------------------

def normalize_email(email: str) -> str:
    return email.strip().lower()


def start_session(db: Session, user: User, response: Response) -> None:
    """Creates a session row and puts its token in the response's cookie."""
    token = security.new_session_token()
    expires_at = datetime.now(UTC) + timedelta(days=security.SESSION_DAYS)
    db.add(UserSession(user_id=user.id, token_hash=security.hash_token(token), expires_at=expires_at))
    response.set_cookie(
        security.SESSION_COOKIE, token,
        max_age=security.SESSION_DAYS * 24 * 3600,
        httponly=True,              # not readable by JavaScript
        secure=cookie_secure(),     # HTTPS only (on the VPS)
        samesite="lax",             # not sent along with requests started by other sites
        path="/",
    )


def end_session_cookie(response: Response) -> None:
    response.delete_cookie(security.SESSION_COOKIE, path="/", httponly=True, secure=cookie_secure(),
                           samesite="lax")


def current_session(request: Request, db: DB) -> UserSession:
    """FastAPI dependency: the logged-in session, or 401."""
    token = request.cookies.get(security.SESSION_COOKIE)
    if token:
        session = db.scalar(select(UserSession).where(
            UserSession.token_hash == security.hash_token(token),
            UserSession.expires_at > datetime.now(UTC),
        ))
        if session is not None:
            return session
    raise HTTPException(401, "Not logged in.")


def current_user(session: Annotated[UserSession, Depends(current_session)]) -> User:
    """FastAPI dependency: the logged-in user, or 401. Every private route uses this."""
    return session.user


CurrentUser = Annotated[User, Depends(current_user)]


# -- routes ----------------------------------------------------------------------------------------

@router.post("/signup", status_code=201)
def signup(body: SignupIn, response: Response, db: DB) -> UserOut:
    email = normalize_email(body.email)
    if db.scalar(select(User).where(User.email == email)) is not None:
        raise HTTPException(409, "An account with this email already exists.")
    user = User(email=email, password_hash=security.hash_password(body.password))
    db.add(user)
    db.flush()                       # gives the user its id, needed by the session row
    start_session(db, user, response)
    db.commit()
    return UserOut.model_validate(user, from_attributes=True)


@router.post("/login")
def login(body: LoginIn, response: Response, db: DB) -> UserOut:
    email = normalize_email(body.email)
    security.check_login_allowed(email)

    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        security.waste_time_like_a_password_check(body.password)
    if user is None or not security.verify_password(user.password_hash, body.password):
        security.record_failed_login(email)
        # one message for both cases, so it doesn't tell which emails have an account
        raise HTTPException(401, "Wrong email or password.")

    security.clear_failed_logins(email)
    # housekeeping: this user's expired sessions are never usable again
    db.execute(delete(UserSession).where(UserSession.user_id == user.id,
                                         UserSession.expires_at <= datetime.now(UTC)))
    start_session(db, user, response)
    db.commit()
    return UserOut.model_validate(user, from_attributes=True)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: DB) -> None:
    """Ends this browser's session. Works (and does nothing) when already logged out."""
    token = request.cookies.get(security.SESSION_COOKIE)
    if token:
        db.execute(delete(UserSession).where(UserSession.token_hash == security.hash_token(token)))
        db.commit()
    end_session_cookie(response)


@router.get("/me")
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user, from_attributes=True)
