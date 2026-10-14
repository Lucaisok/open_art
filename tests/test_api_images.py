"""
Images of the artist's projects (api/images.py, src/rag/images.py): read from a PDF and put with the
work whose page they are on, saved with the project, uploaded by hand, served only to their owner,
deleted with what holds them, and chosen for an application's image item (api/applications.py).

Uses the test database from tests/conftest.py and the keyword embedder from test_api_documents.py.
The PDF reading itself is replaced by fixed pages and pictures (read_pdf_images is tested on its own).
"""

import io
import os
import zipfile

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from api import discover, images, knowledge_base
from api.main import app
from src.agent.checklist import item_key
from src.models.opportunity import RequiredMaterial
from src.rag.images import read_pdf_images, works_by_page
from tests.conftest import PASSWORD
from tests.test_api_documents import ILKA, TOMAS, KeywordEmbedder, upload
from tests.test_matcher import matcher, opp

pytestmark = pytest.mark.usefixtures("api_database")

CALL = opp("call", title_en="Photo residency", required_materials=[
    RequiredMaterial(item="Images of previous works", quote="Send images.", kind="gather"),
    RequiredMaterial(item="Identity photo", quote="Send an ID photo.", kind="gather")])
IMAGES_ITEM, ID_PHOTO = item_key("m", "Images of previous works"), item_key("m", "Identity photo")


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    embedder = KeywordEmbedder()
    monkeypatch.setattr(knowledge_base, "get_embedder", lambda: embedder)
    m = matcher([CALL], [[1.0, 0.0]], statuses={"call": "CHECK"})
    monkeypatch.setattr(discover, "get_matcher", lambda: m)


@pytest.fixture
def artist(client):
    assert client.post("/api/auth/signup", json={"email": "artist@example.com", "password": PASSWORD}).status_code == 201
    return client


def picture(colour="red", size=(640, 480), mode="RGB") -> Image.Image:
    return Image.new(mode, size, colour)


def png_bytes(**kwargs) -> bytes:
    out = io.BytesIO()
    picture(**kwargs).save(out, "PNG")
    return out.getvalue()


def fake_pdf(monkeypatch, pages, pictures):
    """The next document's "PDF" reads as these pages and pictures (whatever file it is)."""
    monkeypatch.setattr(images, "_read", lambda document: (pages, pictures))


# Tomás's portfolio.txt gives three works: Tidal Bodies, Underwater Choir, Rain Score
PAGES = [["Selected works"], ["Tidal Bodies, 2025", "8-channel sound installation."], ["Installation view"],
         ["Underwater Choir, 2023"]]


@pytest.fixture
def with_pictures(artist, monkeypatch):
    fake_pdf(monkeypatch, PAGES, [(1, picture("grey")), (2, picture("red")), (3, picture("green")),
                                  (4, picture("blue"))])
    upload(artist, "portfolio", os.path.join(TOMAS, "portfolio.txt"))
    return artist


def suggestion(client, title):
    return next(s for s in client.get("/api/projects").json()["suggestions"] if s["title"] == title)


# -- reading ---------------------------------------------------------------------------------------------

def test_images_go_with_the_work_whose_page_they_are_on():
    titles = ["Surplus", "To Twist The Course of Signs (Torcer el rumbo de los signos)", "City Loop"]
    pages = [["2", "CURRICULUM VITAE"], ["3", "Surplus"], ["4", "To Twist The Course of Signs"],
             ["5", "To Twist the Course of Signs , Video stills"], ["6", "Installation view", "City Loop"]]
    assert works_by_page(titles, pages) == {2: "Surplus", 3: titles[1], 4: titles[1], 5: "City Loop"}


def test_read_pdf_images_keeps_pictures_and_skips_small_ones(tmp_path):
    path = str(tmp_path / "p.pdf")
    picture("red").save(path, "PDF", save_all=True, append_images=[picture("blue", size=(120, 80))])
    pages, found = read_pdf_images(path)
    assert len(pages) == 2 and [(page, im.size) for page, im in found] == [(1, (640, 480))]   # the logo-sized one is skipped


# -- suggestions and saving ---------------------------------------------------------------------------

def test_a_suggested_work_shows_the_images_of_its_pages(with_pictures):
    tidal, choir = suggestion(with_pictures, "Tidal Bodies"), suggestion(with_pictures, "Underwater Choir")
    assert len(tidal["images"]) == 2 and len(choir["images"]) == 1      # page 3 has no title: Tidal Bodies'
    assert suggestion(with_pictures, "Rain Score")["images"] == []        # page 1 is before any work
    thumb = with_pictures.get(f"/api/images/{tidal['images'][0]['id']}/thumb")
    assert thumb.status_code == 200 and thumb.headers["content-type"] == "image/jpeg"
    assert max(Image.open(io.BytesIO(thumb.content)).size) == 480


def test_images_are_served_to_their_owner_only(with_pictures):
    image_id = suggestion(with_pictures, "Tidal Bodies")["images"][0]["id"]
    other = TestClient(app)
    other.post("/api/auth/signup", json={"email": "other@example.com", "password": PASSWORD})
    assert other.get(f"/api/images/{image_id}").status_code == 404
    assert TestClient(app).get(f"/api/images/{image_id}").status_code == 401


def test_saving_the_suggestion_keeps_its_images_and_replacing_the_document_keeps_them(with_pictures, monkeypatch):
    tidal = suggestion(with_pictures, "Tidal Bodies")
    review = {"accept": [{"key": tidal["suggestion_key"]}], "dismiss": []}
    assert with_pictures.put("/api/profile", json={"values": {}, "projects": review}).status_code == 200
    saved = with_pictures.get("/api/projects").json()["projects"][0]
    assert [i["id"] for i in saved["images"]] == [i["id"] for i in tidal["images"]]
    # a new portfolio: the loose images of the old one go, the saved project's stay
    choir_image = suggestion(with_pictures, "Underwater Choir")["images"][0]["id"]
    fake_pdf(monkeypatch, [], [])
    upload(with_pictures, "portfolio", os.path.join(TOMAS, "portfolio.txt"), name="portfolio-2.txt")
    assert with_pictures.get(f"/api/images/{choir_image}").status_code == 404
    assert with_pictures.get(f"/api/images/{saved['images'][0]['id']}").status_code == 200


def test_accepting_on_the_projects_page_keeps_the_images_too(with_pictures):
    choir = suggestion(with_pictures, "Underwater Choir")
    saved = with_pictures.post("/api/projects", json={**choir, "images": []}).json()
    assert [i["id"] for i in saved["images"]] == [i["id"] for i in choir["images"]]   # from the server, not the request


# -- by hand ---------------------------------------------------------------------------------------------

def test_add_and_remove_images_by_hand(artist):
    project = artist.post("/api/projects", json={"title": "Night Swim", "status": "current"}).json()
    exif = Image.Exif()
    exif[0x010F] = "SecretCam"                       # camera make: must not be kept
    jpeg = io.BytesIO()
    picture("white", size=(3000, 2000)).save(jpeg, "JPEG", exif=exif)
    files = [("files", ("a.jpg", jpeg.getvalue(), "image/jpeg")),
             ("files", ("b.png", png_bytes(mode="RGBA", colour=(0, 0, 0, 0)), "image/png"))]
    added = artist.post(f"/api/projects/{project['id']}/images", files=files)
    assert added.status_code == 201 and len(added.json()) == 2
    full = artist.get(f"/api/images/{added.json()[0]['id']}")
    kept = Image.open(io.BytesIO(full.content))
    assert kept.size == (2400, 1600) and not kept.getexif()          # scaled down, no metadata
    # a text file is refused, with its name
    bad = artist.post(f"/api/projects/{project['id']}/images", files=[("files", ("notes.txt", b"hello", "text/plain"))])
    assert bad.status_code == 400 and "notes.txt" in bad.json()["detail"]
    # remove one, then the project: no file left behind
    first = added.json()[0]["id"]
    assert artist.delete(f"/api/projects/{project['id']}/images/{first}").status_code == 204
    assert artist.get(f"/api/images/{first}").status_code == 404
    folder = images.image_folder(images.uuid.UUID(artist.get("/api/auth/me").json()["id"]))
    assert artist.delete(f"/api/projects/{project['id']}").status_code == 204
    assert os.listdir(folder) == []


def test_images_only_on_your_own_project(artist):
    project = artist.post("/api/projects", json={"title": "Night Swim", "status": "current"}).json()
    other = TestClient(app)
    other.post("/api/auth/signup", json={"email": "other@example.com", "password": PASSWORD})
    files = [("files", ("a.png", png_bytes(), "image/png"))]
    assert other.post(f"/api/projects/{project['id']}/images", files=files).status_code == 404


def test_a_real_pdf_upload_reads_its_images_without_failing(artist):
    """Ilka's CV is a real PDF: its (absent) images are read after the upload, nothing breaks."""
    assert upload(artist, "cv", os.path.join(ILKA, "cv.pdf")).status_code in (200, 201)
    assert artist.get("/api/projects").status_code == 200


# -- applications ------------------------------------------------------------------------------------------

def test_choose_images_for_an_image_item_and_download_them(artist):
    project = artist.post("/api/projects", json={"title": "Night Swim", "status": "current"}).json()
    ids = [i["id"] for i in artist.post(f"/api/projects/{project['id']}/images",
                                        files=[("files", ("a.png", png_bytes(), "image/png")),
                                               ("files", ("b.png", png_bytes(colour="blue"), "image/png"))]).json()]
    body = artist.get("/api/applications/call").json()
    items = {i["key"]: i for i in body["to_gather"]}
    assert items[IMAGES_ITEM]["images_wanted"] and not items[ID_PHOTO]["images_wanted"]   # a photo of you isn't
    assert [c["title"] for c in body["image_choices"]] == ["Night Swim"]
    assert [i["id"] for i in body["projects"][0]["images"]] == ids          # thumbnails in the project picker
    # an ID photo can't be given project images; a foreign id is refused
    assert artist.put(f"/api/applications/call/items/{ID_PHOTO}/images", json={"ids": ids}).status_code == 422
    assert artist.put(f"/api/applications/call/items/{IMAGES_ITEM}/images",
                      json={"ids": ["00000000-0000-0000-0000-000000000000"]}).status_code == 422
    chosen = artist.put(f"/api/applications/call/items/{IMAGES_ITEM}/images", json={"ids": ids[::-1]}).json()
    item = next(i for i in chosen["to_gather"] if i["key"] == IMAGES_ITEM)
    assert item["state"] == "chosen" and [i["id"] for i in item["images"]] == ids[::-1]   # the artist's order
    artist.put(f"/api/applications/call/items/{ID_PHOTO}", json={"ticked": True})
    download = artist.get("/api/applications/call/download")
    assert download.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(download.content)).namelist()
    assert "images/01 Images of previous works/01 Night Swim.jpg" in names
    assert "images/01 Images of previous works/02 Night Swim.jpg" in names
    # deleting the project: the item has nothing chosen any more
    artist.delete(f"/api/projects/{project['id']}")
    item = next(i for i in artist.get("/api/applications/call").json()["to_gather"] if i["key"] == IMAGES_ITEM)
    assert item["state"] == "missing" and item["images"] == []


def test_a_document_is_read_once_however_often_reading_starts(with_pictures):
    """The upload's background task and a page's start_reading can both ask: only the first reads."""
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from api import db
    from api.models import Document
    with Session(db.get_engine()) as session:
        document_id = session.scalar(select(Document.id))
    images.read_document_images(document_id)          # already read at upload: nothing more
    images.read_document_images(document_id)
    assert len(suggestion(with_pictures, "Tidal Bodies")["images"]) == 2


def test_reorder_a_projects_images(artist):
    project = artist.post("/api/projects", json={"title": "Night Swim", "status": "current"}).json()
    ids = [i["id"] for i in artist.post(f"/api/projects/{project['id']}/images",
                                        files=[("files", (f"{n}.png", png_bytes(colour=c), "image/png"))
                                               for n, c in enumerate(["red", "blue", "green"])]).json()]
    reordered = artist.put(f"/api/projects/{project['id']}/images", json={"ids": ids[::-1]})
    assert [i["id"] for i in reordered.json()] == ids[::-1]
    assert [i["id"] for i in artist.get("/api/projects").json()["projects"][0]["images"]] == ids[::-1]
    # every image, each once
    assert artist.put(f"/api/projects/{project['id']}/images", json={"ids": ids[:2]}).status_code == 422
    assert artist.put(f"/api/projects/{project['id']}/images", json={"ids": ids + ids[:1]}).status_code == 422


def test_documents_report_their_images(with_pictures):
    portfolio = next(d for d in with_pictures.get("/api/documents").json() if d["kind"] == "portfolio")
    assert portfolio["images"] == 4 and portfolio["reading_images"] is False


def test_review_keeps_and_dismisses_in_one_go(with_pictures):
    tidal, rain = suggestion(with_pictures, "Tidal Bodies"), suggestion(with_pictures, "Rain Score")
    body = with_pictures.post("/api/projects/review", json={
        "accept": [{"key": tidal["suggestion_key"], "status": "current"}], "dismiss": [rain["suggestion_key"]]}).json()
    assert [(p["title"], p["status"], len(p["images"])) for p in body["projects"]] == [("Tidal Bodies", "current", 2)]
    assert all(s["title"] not in ("Tidal Bodies", "Rain Score") for s in body["suggestions"])
