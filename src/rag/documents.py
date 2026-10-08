"""
OpenArt — read an artist's documents (CV, statement, portfolio) into chunks for the knowledge base.

Two steps:
1. read_lines(path)  - PDF, DOCX, TXT or MD -> plain lines, each marked as heading or not,
                       with the page number for PDFs (so a quote can be cited back)
2. chunk_lines(...)  - lines -> chunks of at most ~MAX_CHUNK_CHARS, never crossing a heading,
                       each remembering the section it sits in ("Education", "Exhibitions")

CVs are lists of short entries under headings, not prose, so this does not
reuse the eligibility sentence chunker: a chunk here is a run of entries
under one heading. Long paragraphs (an artist statement) are split at
sentence ends.

Uploaded files are untrusted input, so: only the four extensions below,
a size cap, a cap on extracted text (a small zipped .docx can expand a lot),
and nothing in a file is ever executed. python-docx parses with
resolve_entities=False, so a .docx can't pull in external XML entities.
"""

import os
import re
from dataclasses import dataclass

from docx import Document as read_docx
from docx.table import Table
from pypdf import PdfReader

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}
MAX_FILE_BYTES = 10 * 1024 * 1024    # 10 MB: far above any CV or statement
MAX_TEXT_CHARS = 200_000             # ~40 pages of text; anything past this is ignored
MAX_CHUNK_CHARS = 800                # well inside bge's 512-token limit, small enough to quote

# common CV / portfolio section titles. Used to spot headings in PDFs and plain text,
# where there are no heading styles to read (compared lowercased, without a trailing ":")
CV_SECTIONS = {
    "about", "artist statement", "statement", "biography", "bio", "short bio", "contact", "personal details",
    "education", "training", "exhibitions", "solo exhibitions", "group exhibitions", "selected exhibitions",
    "awards", "prizes", "grants", "awards and grants", "grants and awards", "scholarships", "fellowships",
    "residencies", "publications", "bibliography", "press", "collections", "public collections",
    "commissions", "projects", "selected works", "works", "portfolio", "performances", "screenings",
    "experience", "work experience", "professional experience", "teaching", "workshops", "talks",
    "languages", "skills", "memberships", "curatorial projects",
}


class DocumentError(ValueError):
    """A file we refuse or can't read; the message is safe to show the artist."""


@dataclass
class Line:
    text: str
    heading: bool = False
    page: int | None = None   # 1-based page number, PDFs only


@dataclass
class Chunk:
    index: int                # position within its document
    section: str | None       # nearest heading above it, if any
    text: str
    page: int | None          # page the chunk starts on (PDFs only)

    @property
    def embedded_text(self) -> str:
        """What gets embedded: the section title gives the entries their meaning ("2019 MFA" under Education)."""
        return f"{self.section}\n{self.text}" if self.section else self.text


def looks_like_heading(text: str) -> bool:
    """A short line with no digits that is either ALL CAPS or a known CV section name."""
    stripped = text.strip().rstrip(":").strip()
    if not stripped or len(stripped.split()) > 5 or any(c.isdigit() for c in stripped):
        return False
    if stripped[-1] in ".,;!?":
        return False
    return stripped.lower() in CV_SECTIONS or (stripped.isupper() and len(stripped) > 2)


# -- 1. reading ------------------------------------------------------------------------------------------

def _read_text_file(path: str) -> list[Line]:
    with open(path, encoding="utf-8", errors="replace") as f:
        raw = f.read(MAX_TEXT_CHARS)
    lines = []
    for text in raw.splitlines():
        if text.lstrip().startswith("#"):  # markdown heading
            lines.append(Line(text.lstrip("# ").strip(), heading=True))
        else:
            lines.append(Line(text))
    return lines


def _read_docx(path: str) -> list[Line]:
    document = read_docx(path)
    lines = []
    # paragraphs and tables in document order: CVs often lay out exhibitions as a table
    for block in document.iter_inner_content():
        if isinstance(block, Table):
            for row in block.rows:
                cells = []
                for cell in row.cells:
                    if cell.text.strip() and cell.text.strip() not in cells:  # merged cells repeat their text
                        cells.append(cell.text.strip())
                lines.append(Line(" | ".join(cells)))
        else:
            style = block.style.name if block.style is not None else ""
            lines.append(Line(block.text, heading=style.startswith("Heading") or style == "Title"))
    return lines


def _read_pdf(path: str) -> list[Line]:
    reader = PdfReader(path)
    if reader.is_encrypted:
        raise DocumentError("this PDF is password-protected; please upload an unprotected copy")
    lines = []
    for number, page in enumerate(reader.pages, start=1):
        for text in (page.extract_text() or "").splitlines():
            lines.append(Line(text, page=number))
    return lines


def read_lines(path: str) -> list[Line]:
    """Read one document into non-empty lines, headings marked, total text capped at MAX_TEXT_CHARS."""
    extension = os.path.splitext(path)[1].lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise DocumentError(f"unsupported file type {extension!r}; upload PDF, DOCX, TXT or MD")
    if os.path.getsize(path) > MAX_FILE_BYTES:
        raise DocumentError(f"file is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB")

    try:
        if extension == ".pdf":
            lines = _read_pdf(path)
        elif extension == ".docx":
            lines = _read_docx(path)
        else:
            lines = _read_text_file(path)
    except DocumentError:
        raise
    except Exception as error:  # a corrupt or disguised file: report it, don't crash
        raise DocumentError(f"could not read this {extension[1:].upper()} file ({type(error).__name__})") from error

    kept, total = [], 0
    for line in lines:
        text = " ".join(line.text.split())  # collapse runs of whitespace
        if not text:
            continue
        total += len(text)
        if total > MAX_TEXT_CHARS:
            break
        kept.append(Line(text, heading=line.heading or looks_like_heading(text), page=line.page))
    if not kept:
        raise DocumentError("no text found in this file (a scanned PDF needs to be converted to text first)")
    return kept


# -- 2. chunking -----------------------------------------------------------------------------------------

def _split_long(text: str, limit: int) -> list[str]:
    """Split a paragraph longer than `limit` at sentence ends (and hard-cut a sentence that is longer still)."""
    pieces, current = [], ""
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        while len(sentence) > limit:
            pieces.append(sentence[:limit])
            sentence = sentence[limit:]
        if current and len(current) + 1 + len(sentence) > limit:
            pieces.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)
    return pieces


def chunk_lines(lines: list[Line], max_chars: int = MAX_CHUNK_CHARS) -> list[Chunk]:
    chunks: list[Chunk] = []
    section: str | None = None
    current: list[str] = []
    current_page: int | None = None

    def flush() -> None:
        nonlocal current, current_page
        if current:
            chunks.append(Chunk(index=len(chunks), section=section, text="\n".join(current), page=current_page))
        current, current_page = [], None

    for line in lines:
        if line.heading:
            flush()                       # a chunk never spans two sections
            section = line.text.rstrip(":")
            continue
        for piece in _split_long(line.text, max_chars):
            if current and sum(len(t) + 1 for t in current) + len(piece) > max_chars:
                flush()
            if not current:
                current_page = line.page
            current.append(piece)
    flush()
    return chunks


def read_chunks(path: str) -> list[Chunk]:
    return chunk_lines(read_lines(path))
