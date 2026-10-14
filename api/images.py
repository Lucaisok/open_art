"""
OpenArt API — images of the artist's projects (workflow.MD, "Project images").

    GET    /api/images/{id}                      the image (JPEG, at most 2400 px), its owner only
    GET    /api/images/{id}/thumb                its thumbnail (480 px)
    POST   /api/projects/{id}/images             add images to a saved project (files, by hand)
    PUT    /api/projects/{id}/images             their order (the first leads in applications)
    DELETE /api/projects/{id}/images/{image_id}  remove one

Images come two ways. Read from the artist's PDFs (src/rag/images.py), in the background after the
upload answers (decoding a PDF's JPEG 2000 takes seconds), or on first use for a document uploaded
before images were read. Such an image belongs to no project until the artist saves the project it
was found with (api/projects.py claim_images); until then it only shows on the suggestion. Or uploaded
by hand onto a saved project. Either way it is re-encoded as a JPEG without metadata, stored at
<UPLOADS_DIR>/<user id>/images/<image id>.jpg (+ -thumb.jpg), served only to its owner, and deleted with
its project, its document (unless a project holds it) or the account.
"""

import logging
import os
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from api import db as database
from api.auth import DB, CurrentUser
from api.documents import save_upload, stored_path, user_folder
from api.models import Document, Project, ProjectImage
from src.rag.images import ImageError, open_upload, read_pdf_images, save_jpeg

router = APIRouter(tags=["images"])
log = logging.getLogger(__name__)

MAX_IMAGES_PER_PROJECT = 30
MAX_IMAGE_BYTES = 10 * 1024 * 1024   # one uploaded image (the same 10 MB as a document, and as nginx)
MAX_FILES_PER_REQUEST = 10


class ImageOut(BaseModel):
    id: uuid.UUID
    width: int
    height: int


def image_out(image: ProjectImage) -> ImageOut:
    return ImageOut(id=image.id, width=image.width, height=image.height)


# -- files on disk -----------------------------------------------------------------------------------

def image_folder(user_id: uuid.UUID) -> str:
    return os.path.join(user_folder(user_id), "images")


def image_path(image: ProjectImage, thumb: bool = False) -> str:
    return os.path.join(image_folder(image.user_id), f"{image.id}{'-thumb' if thumb else ''}.jpg")


def files_of(images: list[ProjectImage]) -> list[str]:
    """The files of rows about to be deleted: read before the commit (a deleted row can't be read after)."""
    return [image_path(image, thumb) for image in images for thumb in (False, True)]


def remove_files(paths: list[str]) -> None:
    """Call after the commit: a failed commit keeps the files with their rows."""
    for path in paths:
        if os.path.exists(path):
            os.remove(path)


def _new_image(user_id: uuid.UUID, picture, **fields) -> ProjectImage:
    """Writes one picture's files and returns its (not yet added) row."""
    image = ProjectImage(id=uuid.uuid4(), user_id=user_id, **fields)
    os.makedirs(image_folder(user_id), exist_ok=True)
    image.width, image.height = save_jpeg(picture, image_path(image), image_path(image, thumb=True))
    return image


# -- reading a document's images (in the background) ---------------------------------------------------

_reader = ThreadPoolExecutor(max_workers=1, thread_name_prefix="images")   # one at a time: decoding is heavy


def _read(document: Document) -> tuple[list[list[str]], list]:
    """(page lines, [(page, picture)]) of a PDF; nothing for other files or an unreadable PDF."""
    path = stored_path(document)
    if not document.file_name.lower().endswith(".pdf") or not os.path.exists(path):
        return [], []
    try:
        return read_pdf_images(path)
    except Exception:
        log.exception("could not read the images of document %s", document.id)
        return [], []


def read_document_images(document_id: uuid.UUID) -> None:
    """Reads one PDF's images and page lines into the database. Runs in the background with its own
    session. First it claims the document (images_read false -> true, one atomic UPDATE), so the same
    document is never read twice, even when the upload's task and a page's start_reading race, or run
    in two server processes. Never raises: a PDF whose images can't be read just has none."""
    written: list[ProjectImage] = []
    try:
        with Session(database.get_engine()) as session:
            claimed = session.execute(update(Document).where(Document.id == document_id,
                                                             Document.images_read.is_(False))
                                      .values(images_read=True))
            session.commit()
            if claimed.rowcount == 0:
                return          # read already, being read, or deleted
            document = session.get(Document, document_id)
            pages, pictures = _read(document)
            for page, picture in pictures:
                written.append(_new_image(document.user_id, picture, document_id=document.id, page=page))
            session.add_all(written)
            document.page_lines = pages   # [] when it has no text: read, nothing to match
            session.commit()
            written = []        # committed: the files stay
    except Exception:
        log.exception("reading images of document %s failed", document_id)
        _mark_read(document_id)   # done, with no images: the page stops waiting for them
    finally:
        remove_files(files_of(written))   # only if the commit didn't happen


def _mark_read(document_id: uuid.UUID) -> None:
    try:
        with Session(database.get_engine()) as session:
            session.execute(update(Document).where(Document.id == document_id, Document.page_lines.is_(None))
                            .values(page_lines=[]))
            session.commit()
    except Exception:
        log.exception("could not mark document %s as read", document_id)


def images_pending(document: Document) -> bool:
    """A PDF whose images aren't read yet (queued or being read): its page lines are set at the end."""
    return document.file_name.lower().endswith(".pdf") and document.page_lines is None


def start_reading(document: Document) -> None:
    """Queues read_document_images for a document not read yet (uploaded before images were read).
    A duplicate in the queue is harmless: the claim in read_document_images lets only one read."""
    if not document.images_read:
        _reader.submit(read_document_images, document.id)


def forget_document_images(db, document: Document) -> list[str]:
    """Before a document is deleted or replaced: its images that no saved project holds go with it.
    Returns their files, for the caller to remove after its commit (remove_files)."""
    loose = list(db.scalars(select(ProjectImage).where(ProjectImage.document_id == document.id,
                                                       ProjectImage.project_id.is_(None))))
    for image in loose:
        db.delete(image)
    return files_of(loose)


# -- routes --------------------------------------------------------------------------------------------

def _own_image(db, user_id: uuid.UUID, image_id: uuid.UUID) -> ProjectImage:
    image = db.get(ProjectImage, image_id)
    if image is None or image.user_id != user_id:   # someone else's id looks like a missing one
        raise HTTPException(404, "No such image.")
    return image


def _send(image: ProjectImage, thumb: bool) -> FileResponse:
    path = image_path(image, thumb)
    if not os.path.exists(path):
        raise HTTPException(404, "No such image.")
    # private: only the owner's browser keeps it; the id changes if the image does, so it can be kept long
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=604800"})


@router.get("/api/images/{image_id}")
def get_image(image_id: uuid.UUID, user: CurrentUser, db: DB) -> FileResponse:
    return _send(_own_image(db, user.id, image_id), thumb=False)


@router.get("/api/images/{image_id}/thumb")
def get_thumb(image_id: uuid.UUID, user: CurrentUser, db: DB) -> FileResponse:
    return _send(_own_image(db, user.id, image_id), thumb=True)


def _own_project(db, user_id: uuid.UUID, project_id: uuid.UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.user_id != user_id or project.kind != "project":
        raise HTTPException(404, "No such project.")
    return project


def project_images(db, project_id: uuid.UUID) -> list[ProjectImage]:
    return list(db.scalars(select(ProjectImage).where(ProjectImage.project_id == project_id)
                           .order_by(ProjectImage.position, ProjectImage.created_at)))


@router.post("/api/projects/{project_id}/images", status_code=201)
def add_images(project_id: uuid.UUID, files: list[UploadFile], user: CurrentUser, db: DB) -> list[ImageOut]:
    """Adds the uploaded images to a saved project, after its existing ones. All or nothing: one
    unreadable file refuses the request, with its name."""
    project = _own_project(db, user.id, project_id)
    existing = project_images(db, project.id)
    if not files or len(files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(422, f"Add between 1 and {MAX_FILES_PER_REQUEST} images at a time.")
    if len(existing) + len(files) > MAX_IMAGES_PER_PROJECT:
        raise HTTPException(422, f"A project holds at most {MAX_IMAGES_PER_PROJECT} images.")
    added: list[ProjectImage] = []
    try:
        for n, upload in enumerate(files):
            with tempfile.TemporaryDirectory() as folder:
                path = os.path.join(folder, "upload")
                save_upload(upload, path, max_bytes=MAX_IMAGE_BYTES)   # too large: 413, nothing kept
                try:
                    picture = open_upload(path)
                except ImageError as error:
                    name = os.path.basename(upload.filename or "an image")
                    raise HTTPException(400, f"{name}: {error}.") from None
                added.append(_new_image(user.id, picture, project_id=project.id, position=len(existing) + n))
        db.add_all(added)
        db.commit()
    except Exception:
        remove_files(files_of(added))
        raise
    return [image_out(i) for i in project_images(db, project.id)]


class ImageOrderIn(BaseModel):
    ids: list[uuid.UUID] = Field(max_length=MAX_IMAGES_PER_PROJECT)   # every image of the project, in order


@router.put("/api/projects/{project_id}/images")
def order_images(project_id: uuid.UUID, body: ImageOrderIn, user: CurrentUser, db: DB) -> list[ImageOut]:
    """The project's images in a new order: exactly its images, each once (else 422)."""
    project = _own_project(db, user.id, project_id)
    images = {image.id: image for image in project_images(db, project.id)}
    if sorted(map(str, body.ids)) != sorted(map(str, images)):
        raise HTTPException(422, "Send every image of the project, each once.")
    for position, image_id in enumerate(body.ids):
        images[image_id].position = position
    db.commit()
    return [image_out(i) for i in project_images(db, project.id)]


@router.delete("/api/projects/{project_id}/images/{image_id}", status_code=204)
def delete_image(project_id: uuid.UUID, image_id: uuid.UUID, user: CurrentUser, db: DB) -> None:
    project = _own_project(db, user.id, project_id)
    image = _own_image(db, user.id, image_id)
    if image.project_id != project.id:
        raise HTTPException(404, "No such image.")
    paths = files_of([image])
    db.delete(image)
    db.commit()
    remove_files(paths)
