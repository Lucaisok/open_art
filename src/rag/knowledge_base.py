"""
OpenArt — one artist's knowledge base: their documents, chunked and embedded.

    kb = ArtistKnowledgeBase("ilka_varga")
    kb.add_document("cv.pdf")          # read -> chunk -> embed -> save
    kb.documents                       # ["cv.pdf"]
    kb.remove_document("cv.pdf")
    kb.retrieve("Where did the artist study?", k=3, documents=["cv.pdf"])
    -> [RetrievedPassage(chunk=..., score=0.74), ...]   .citation -> "cv.pdf · p. 1 · EDUCATION"

On disk, under data/artists/<artist_id>/ (inside the private, gitignored data/
repo: CVs are personal data and are never published):

    raw/<file>       the uploaded file, untouched (raw kept apart from processed)
    chunks.jsonl     one KnowledgeChunk per line
    vectors.npz      one normalized embedding per chunk, same order as chunks.jsonl,
                     with the model name and fastembed version that made them

Uses the same embedding model and helpers as semantic matching
(src/matching/index.py), so one embedding stack serves the whole product.
Re-uploading a file with the same name replaces it.

Retrieval runs locally (nothing leaves the machine): the question is embedded
with embed_query (BGE's search instruction in front) and compared with every
chunk by cosine similarity. An artist has a few dozen chunks at most, so a
plain NumPy dot product is instant; no vector database is needed.
"""

import os
import re
import shutil
from importlib.metadata import version

import numpy as np
from pydantic import BaseModel

from src.matching.index import EMBEDDING_MODEL, embed_passages, embed_query, load_embedder
from src.rag.documents import DocumentError, read_chunks

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTISTS_DIR = os.path.join(REPO_ROOT, "data", "artists")

# artist ids and file names become paths: only allow plain characters, so neither
# can point outside the artist's own folder ("../", absolute paths, hidden files)
ARTIST_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
FILE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._()-]{0,120}$")


class KnowledgeChunk(BaseModel):
    chunk_id: str             # "<document>#<index>", stable while the document isn't re-uploaded
    document: str             # file name, e.g. "cv.pdf"
    index: int
    section: str | None
    text: str
    page: int | None


class RetrievedPassage(BaseModel):
    chunk: KnowledgeChunk
    score: float              # cosine similarity with the question, -1 to 1 (higher = closer)

    @property
    def citation(self) -> str:
        """Where the passage comes from, for showing next to a quote: "cv.pdf · p. 1 · EDUCATION"."""
        parts = [self.chunk.document]
        if self.chunk.page is not None:
            parts.append(f"p. {self.chunk.page}")
        if self.chunk.section:
            parts.append(self.chunk.section)
        return " · ".join(parts)


class ArtistKnowledgeBase:
    def __init__(self, artist_id: str, root: str = ARTISTS_DIR, embedder=None):
        if not ARTIST_ID_PATTERN.match(artist_id):
            raise ValueError(f"invalid artist id {artist_id!r}: lowercase letters, digits, _ and - only")
        self.artist_id = artist_id
        self.folder = os.path.join(root, artist_id)
        self._embedder = embedder          # loaded on first use: listing documents needs no model
        self.chunks, self.vectors = self._load()

    # -- storage ---------------------------------------------------------------------------------------

    @property
    def _chunks_path(self) -> str:
        return os.path.join(self.folder, "chunks.jsonl")

    @property
    def _vectors_path(self) -> str:
        return os.path.join(self.folder, "vectors.npz")

    def _load(self) -> tuple[list[KnowledgeChunk], np.ndarray]:
        if not os.path.exists(self._chunks_path):
            return [], np.empty((0, 0), dtype=np.float32)
        with open(self._chunks_path, encoding="utf-8") as f:
            chunks = [KnowledgeChunk.model_validate_json(line) for line in f]
        # allow_pickle=False: only plain arrays are read, nothing in the file can run code
        with np.load(self._vectors_path, allow_pickle=False) as data:
            vectors, model = data["vectors"], str(data["model"])
            built_with = str(data["fastembed_version"]) if "fastembed_version" in data else None
        # a different model or fastembed version would make the scores silently wrong (as in
        # OpportunityIndex.check_matches): refuse instead
        if model != EMBEDDING_MODEL or built_with != version("fastembed") or len(vectors) != len(chunks):
            raise RuntimeError(f"knowledge base for {self.artist_id!r} is out of date or damaged: "
                               "re-upload its documents")
        return chunks, vectors

    def _save(self) -> None:
        os.makedirs(self.folder, exist_ok=True)
        with open(self._chunks_path, "w", encoding="utf-8") as f:
            for chunk in self.chunks:
                f.write(chunk.model_dump_json() + "\n")
        np.savez(self._vectors_path, vectors=self.vectors, model=np.array(EMBEDDING_MODEL),
                 fastembed_version=np.array(version("fastembed")))

    @property
    def embedder(self):
        if self._embedder is None:
            self._embedder = load_embedder(EMBEDDING_MODEL)
        return self._embedder

    # -- documents -------------------------------------------------------------------------------------

    @property
    def documents(self) -> list[str]:
        return sorted({chunk.document for chunk in self.chunks})

    def add_document(self, path: str, name: str | None = None) -> list[KnowledgeChunk]:
        """Read, chunk and embed one file, replacing any earlier upload with the same name.
        `name` is the file name to store it under (default: the file's own name)."""
        name = name or os.path.basename(path)
        if not FILE_NAME_PATTERN.match(name):
            raise DocumentError(f"invalid file name {name!r}: use letters, digits, spaces and . _ - ( )")

        chunks = read_chunks(path)          # raises DocumentError on anything we won't read
        new = [KnowledgeChunk(chunk_id=f"{name}#{c.index}", document=name, index=c.index, section=c.section,
                              text=c.text, page=c.page) for c in chunks]
        new_vectors = embed_passages(self.embedder, [c.embedded_text for c in chunks])

        self._drop(name)
        self.chunks += new
        self.vectors = new_vectors if self.vectors.size == 0 else np.vstack([self.vectors, new_vectors])

        raw_dir = os.path.join(self.folder, "raw")
        os.makedirs(raw_dir, exist_ok=True)
        if os.path.abspath(path) != os.path.abspath(os.path.join(raw_dir, name)):
            shutil.copyfile(path, os.path.join(raw_dir, name))
        self._save()
        return new

    def remove_document(self, name: str) -> None:
        if name not in self.documents:
            raise KeyError(f"no document named {name!r}")
        self._drop(name)
        raw = os.path.join(self.folder, "raw", name)
        if os.path.exists(raw):
            os.remove(raw)
        self._save()

    def _drop(self, name: str) -> None:
        keep = [i for i, chunk in enumerate(self.chunks) if chunk.document != name]
        self.chunks = [self.chunks[i] for i in keep]
        self.vectors = self.vectors[keep] if self.vectors.size else self.vectors

    # -- retrieval -------------------------------------------------------------------------------------

    def retrieve(self, question: str, k: int = 5, documents: list[str] | None = None) -> list[RetrievedPassage]:
        """The k chunks closest to the question, best first.
        `documents` limits the search to some files (e.g. only the CV for profile pre-fill).
        No score threshold: with a few dozen chunks a small k keeps the list short, and
        whoever uses the passages (the artist, or the LLM in step 3) must quote them anyway."""
        if not question or not question.strip():
            raise ValueError("question is empty")
        if documents is not None:
            unknown = set(documents) - set(self.documents)
            if unknown:
                raise KeyError(f"no document named {sorted(unknown)[0]!r}")
        rows = [i for i, chunk in enumerate(self.chunks) if documents is None or chunk.document in documents]
        if not rows or k <= 0:
            return []

        scores = self.vectors[rows] @ embed_query(self.embedder, question)   # unit vectors: dot = cosine
        best = np.argsort(-scores, kind="stable")[:k]                       # stable: ties keep file order
        return [RetrievedPassage(chunk=self.chunks[rows[i]], score=float(scores[i])) for i in best]
