"""The logged-in user's own account: change password, delete the account."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete

from api import security
from api.auth import DB, current_session, end_session_cookie
from api.documents import delete_user_files
from api.models import UserSession

router = APIRouter(prefix="/api/account", tags=["account"])

CurrentSession = Annotated[UserSession, Depends(current_session)]


class PasswordChangeIn(BaseModel):
    current_password: str = Field(max_length=security.MAX_PASSWORD_LENGTH)
    new_password: str = Field(min_length=security.MIN_PASSWORD_LENGTH, max_length=security.MAX_PASSWORD_LENGTH)


class DeleteAccountIn(BaseModel):
    password: str = Field(max_length=security.MAX_PASSWORD_LENGTH)


@router.post("/password", status_code=204)
def change_password(body: PasswordChangeIn, session: CurrentSession, db: DB) -> None:
    user = session.user
    if not security.verify_password(user.password_hash, body.current_password):
        raise HTTPException(400, "Your current password is wrong.")
    user.password_hash = security.hash_password(body.new_password)
    # log out every other browser: if the password leaked, the old sessions may be someone else's
    db.execute(delete(UserSession).where(UserSession.user_id == user.id, UserSession.id != session.id))
    db.commit()


@router.delete("", status_code=204)
def delete_account(body: DeleteAccountIn, session: CurrentSession, response: Response, db: DB) -> None:
    """Deletes the user and, through the database's cascades, everything that belongs to them,
    then their uploaded files."""
    user = session.user
    if not security.verify_password(user.password_hash, body.password):
        raise HTTPException(400, "Your password is wrong.")
    user_id = user.id
    db.delete(user)
    db.commit()
    delete_user_files(user_id)
    end_session_cookie(response)

