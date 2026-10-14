"""
OpenArt — images of the artist's works: read from their PDF, or uploaded by hand. Nothing leaves the
machine and no model looks at them: they are shown to the artist and sent where the artist chooses.

    pages, images = read_pdf_images("portfolio.pdf")    # each page's text lines; (page, PIL image) pairs
    owner = works_by_page(["Surplus", "Memorias"], pages)  # {3: "Surplus", 4: "Memorias", 5: "Memorias"...}
    width, height = save_jpeg(image, "full.jpg", "thumb.jpg")

Which work an image belongs to: the work whose title is a line of the image's page, or, on a page
without a title, the last work titled before it (stills and installation views often follow their
work's page). Images before the first titled page (a CV, a cover) belong to no work.

Every image is re-encoded once as a JPEG: browsers can't show the JPEG 2000 that PDFs often hold, a
too-large image is scaled down, and the camera / location metadata of the original is not copied.
"""

import re
import warnings

from PIL import Image, ImageOps
from pypdf import PdfReader

MAX_PIXELS = 40_000_000      # refuse anything larger (a "decompression bomb" is a tiny file that expands)
MAX_IMAGES_PER_DOCUMENT = 60
MIN_SIDE = 200               # smaller is a logo, an icon or a rule line: not a picture of a work
FULL_SIDE = 2400             # the long side of the image kept (enough for any application form)
THUMB_SIDE = 480             # the long side of the thumbnail shown on cards
MAX_PAGE_LINES = 200         # per page, for matching titles


class ImageError(ValueError):
    """An image we refuse or can't read; the message is safe to show the artist."""


def _letters(text: str) -> str:
    """Lower case, letters and digits only: "Tríptico Difuso  (from…)" and "tríptico difuso (from…)" agree."""
    return re.sub(r"[^\w]", "", text.lower()).replace("_", "")


def read_pdf_images(path: str) -> tuple[list[list[str]], list[tuple[int, Image.Image]]]:
    """(each page's non-empty text lines, [(1-based page, image)]). Small images, ones too large to
    decode safely and ones the PDF holds in a format we can't decode are skipped, not errors."""
    reader = PdfReader(path)
    pages: list[list[str]] = []
    images: list[tuple[int, Image.Image]] = []
    for number, page in enumerate(reader.pages, start=1):
        lines = [line.strip() for line in (page.extract_text() or "").splitlines() if line.strip()]
        pages.append(lines[:MAX_PAGE_LINES])
        if len(images) >= MAX_IMAGES_PER_DOCUMENT:
            continue
        try:
            found = list(page.images)
        except Exception:
            continue          # a page whose images pypdf can't list: its text is still read
        for found_image in found:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("error", Image.DecompressionBombWarning)
                    image = found_image.image
                    width, height = image.size
            except Exception:
                continue
            if min(width, height) < MIN_SIDE or width * height > MAX_PIXELS:
                continue
            images.append((number, image))
            if len(images) >= MAX_IMAGES_PER_DOCUMENT:
                break
    return pages, images


def _same_title(key: str, line: str) -> bool:
    """The line is the title, its start (the title had a subtitle added), or the title then only
    digits ("Tidal Bodies, 2025")."""
    return key == line or key.startswith(line) or (line.startswith(key) and line[len(key):].isdigit())


def works_by_page(titles: list[str], pages: list[list[str]]) -> dict[int, str]:
    """{1-based page: the work its images belong to} (module docstring). A line matches a title when
    it is the title, its start ("To Twist The Course of Signs" for the title with its subtitle) or the
    title and its years ("Tidal Bodies, 2025"); lines under 4 letters never match."""
    keys = [(title, _letters(title)) for title in titles if _letters(title)]
    owner: dict[int, str] = {}
    current = None
    for number, lines in enumerate(pages, start=1):
        for line in lines:
            letters = _letters(line)
            if len(letters) < 4:
                continue
            match = next((title for title, key in keys if _same_title(key, letters)), None)
            if match:
                current = match
                break
        if current:
            owner[number] = current
    return owner


def open_upload(path: str) -> Image.Image:
    """An image the artist uploaded, checked: a real JPEG / PNG / WebP / GIF, not too large to decode."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(path)
            if image.format not in ("JPEG", "PNG", "WEBP", "GIF", "MPO"):
                raise ImageError("upload a JPEG, PNG, WebP or GIF image")
            if image.width * image.height > MAX_PIXELS:
                raise ImageError("this image is too large")
            image.load()
    except ImageError:
        raise
    except Exception:
        raise ImageError("this file isn't an image we can read") from None
    return ImageOps.exif_transpose(image)   # a phone photo the right way up, before its metadata goes


def _rgb(image: Image.Image) -> Image.Image:
    """JPEG has no transparency: a transparent background becomes white."""
    if image.mode in ("RGBA", "LA", "P"):
        image = image.convert("RGBA")
        background = Image.new("RGB", image.size, "white")
        background.paste(image, mask=image.split()[-1])
        return background
    return image.convert("RGB")


def save_jpeg(image: Image.Image, full_path: str, thumb_path: str) -> tuple[int, int]:
    """Writes the kept image and its thumbnail as JPEG (no metadata copied); returns the kept size."""
    image = _rgb(image)
    full = image.copy()
    full.thumbnail((FULL_SIDE, FULL_SIDE))
    full.save(full_path, "JPEG", quality=88, optimize=True)
    thumb = image.copy()
    thumb.thumbnail((THUMB_SIDE, THUMB_SIDE))
    thumb.save(thumb_path, "JPEG", quality=80, optimize=True)
    return full.size
