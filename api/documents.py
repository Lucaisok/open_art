"""
The artist's documents: CV, statement, portfolio. One slot each; uploading into a
filled slot replaces the file.

An upload is read, chunked and embedded in the request (a CV takes about a second). The CV's
stored passages are what /profile reads its suggestions from (api/profile.py).
Only when that works are the old rows and file replaced, so a bad upload leaves
the previous document untouched.

Files are kept at <UPLOADS_DIR>/<user id>/<document id><.ext>. Nothing in the path
comes from the artist: their file name is only stored, to be shown back.
"""

import os
import shutil
import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from api.auth import DB, CurrentUser
from api.config import uploads_dir
from api.knowledge_base import build_chunks
from api.models import Document
from src.rag.documents import MAX_FILE_BYTES, SUPPORTED_EXTENSIONS, DocumentError, read_chunks

router = APIRouter(prefix="/api/documents", tags=["documents"])

Kind = Literal["cv", "statement", "portfolio"]   # same as models.DOCUMENT_KINDS

READ_PIECE_BYTES = 1024 * 1024   # the upload is copied to disk 1 MB at a time


class DocumentOut(BaseModel):
    kind: Kind
    file_name: str
    size_bytes: int
    chunk_count: int
    uploaded_at: datetime


# -- files on disk -----------------------------------------------------------------------------------

def user_folder(user_id: uuid.UUID) -> str:
    return os.path.join(uploads_dir(), str(user_id))


def stored_path(document: Document) -> str:
    extension = os.path.splitext(document.file_name)[1].lower()
    return os.path.join(user_folder(document.user_id), f"{document.id}{extension}")


def delete_user_files(user_id: uuid.UUID) -> None:
    """Removes every file of this user (called when the account is deleted)."""
    shutil.rmtree(user_folder(user_id), ignore_errors=True)


def clean_file_name(raw: str | None) -> str:
    """The artist's file name, for display only: no folders, no control characters, not too long."""
    name = os.path.basename((raw or "").replace("\\", "/"))
    name = "".join(ch for ch in name if ch.isprintable()).strip()
    if len(name) > 120:
        stem, extension = os.path.splitext(name)
        name = stem[:120 - len(extension)] + extension
    return name


def save_upload(upload: UploadFile, path: str) -> int:
    """Copies the upload to `path` piece by piece and returns its size.
    Stops (and deletes the copy) as soon as it passes the size cap."""
    size = 0
    with open(path, "wb") as out:
        while piece := upload.file.read(READ_PIECE_BYTES):
            size += len(piece)
            if size > MAX_FILE_BYTES:
                out.close()
                os.remove(path)
                raise HTTPException(413, f"The file is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB.")
            out.write(piece)
    return size


# -- routes ------------------------------------------------------------------------------------------

@router.get("")
def list_documents(user: CurrentUser, db: DB) -> list[DocumentOut]:
    documents = db.scalars(select(Document).where(Document.user_id == user.id).order_by(Document.kind))
    return [DocumentOut.model_validate(d, from_attributes=True) for d in documents]


@router.put("/{kind}")
def upload_document(kind: Kind, file: UploadFile, user: CurrentUser, db: DB) -> DocumentOut:
    file_name = clean_file_name(file.filename)
    extension = os.path.splitext(file_name)[1].lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(400, "Upload a PDF, DOCX, TXT or MD file.")

    old = db.scalar(select(Document).where(Document.user_id == user.id, Document.kind == kind))
    # the RAG steps pick documents by file name, so two slots can't hold the same name
    clash = db.scalar(select(Document.kind).where(Document.user_id == user.id, Document.kind != kind,
                                                  Document.file_name == file_name))
    if clash is not None:
        raise HTTPException(409, f"A file with this name is already uploaded as your {clash}. Rename it first.")

    # 1. copy the upload to disk under its final name (the new document's id)
    document = Document(id=uuid.uuid4(), user_id=user.id, kind=kind, file_name=file_name)
    path = stored_path(document)
    os.makedirs(user_folder(user.id), exist_ok=True)
    document.size_bytes = save_upload(file, path)

    # 2. read, chunk and embed it; 3. swap the rows. Any failure removes the new file.
    try:
        chunks = read_chunks(path)
        document.chunks = build_chunks(chunks, user.id)
        document.chunk_count = len(document.chunks)

        if old is not None:
            db.delete(old)          # its chunks go with it (cascade)
            db.flush()              # before the insert, which would clash on (user, kind)
        db.add(document)
        db.commit()
    except DocumentError as error:
        os.remove(path)
        raise HTTPException(400, f"We couldn't read this file: {error}.") from None
    except IntegrityError:
        # another upload into the same slot finished first
        os.remove(path)
        raise HTTPException(409, "Another upload into this slot just finished. Reload the page.") from None
    except Exception:
        os.remove(path)
        raise

    # 4. only now that the new document is saved, remove the old file
    if old is not None and os.path.exists(stored_path(old)):
        os.remove(stored_path(old))
    return DocumentOut.model_validate(document, from_attributes=True)


@router.delete("/{kind}", status_code=204)
def delete_document(kind: Kind, user: CurrentUser, db: DB) -> None:
    document = db.scalar(select(Document).where(Document.user_id == user.id, Document.kind == kind))
    if document is None:
        raise HTTPException(404, "There is no document in this slot.")
    path = stored_path(document)
    db.delete(document)
    db.commit()
    if os.path.exists(path):
        os.remove(path)
