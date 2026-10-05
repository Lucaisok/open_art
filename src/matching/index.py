"""
OpenArt — the semantic-matching index: one embedding per opportunity.

Each opportunity is turned into one English text (what the call is about:
title, description, discipline, type) and embedded once with the same
fastembed model the RQ1 classifier uses. The vectors are saved to
artifacts/opportunity_index.npz; at request time only the artist's query is
embedded and compared against them (src/matching/matcher.py).

requirements_text is deliberately left out: it says who may apply, not what
the call is about, and the eligibility engine already reads it.

Build or refresh the index with: uv run python scripts/build_match_index.py
"""

import hashlib
import os
from dataclasses import dataclass
from importlib.metadata import version

import numpy as np
from fastembed import TextEmbedding

from src.eligibility.classify import EMBEDDING_BATCH_SIZE, EMBEDDING_CACHE_DIR
from src.models.processed_opportunity import ProcessedOpportunity

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INDEX_PATH = os.path.join(REPO_ROOT, "artifacts", "opportunity_index.npz")

# same model as the RQ1 classifier: one embedding stack for the whole product (workflow.MD)
EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"

# BGE is trained to put this instruction in front of a search query (not in front of the
# passages being searched). fastembed's query_embed does not add it for BGE, so we do.
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


def opportunity_text(opp: ProcessedOpportunity) -> str:
    """The text embedded for one opportunity: what it is about, in English."""
    parts = [opp.title_en, opp.description_en]
    if opp.discipline_en:
        parts.append(f"Discipline: {opp.discipline_en}")
    if opp.opportunity_type_en:
        parts.append(f"Type: {opp.opportunity_type_en}")
    return "\n".join(part.strip() for part in parts if part and part.strip())


def text_hash(text: str) -> str:
    """Short fingerprint of an embedded text, so a stale index (text changed since) is caught."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _normalize(vectors: np.ndarray) -> np.ndarray:
    """Scale every row to length 1, so a dot product is the cosine similarity."""
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.where(norms == 0, 1, norms)


def load_embedder(model: str = EMBEDDING_MODEL) -> TextEmbedding:
    return TextEmbedding(model, cache_dir=EMBEDDING_CACHE_DIR)


def embed_passages(embedder: TextEmbedding, texts: list[str]) -> np.ndarray:
    """Embed opportunity texts, one normalized row per text, in the caller's order."""
    # shortest to longest, so each batch pads little (same trick as EligibilityClassifier.embed)
    order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
    sorted_vectors = list(embedder.passage_embed([texts[i] for i in order], batch_size=EMBEDDING_BATCH_SIZE))
    vectors = np.empty((len(texts), len(sorted_vectors[0])), dtype=np.float32)
    for position, i in enumerate(order):
        vectors[i] = sorted_vectors[position]
    return _normalize(vectors)


def embed_query(embedder: TextEmbedding, query: str) -> np.ndarray:
    """Embed the artist's query as one normalized vector."""
    vector = next(iter(embedder.query_embed(QUERY_INSTRUCTION + query.strip())))
    return _normalize(np.asarray(vector, dtype=np.float32)[None, :])[0]


@dataclass
class OpportunityIndex:
    ids: list[str]
    hashes: list[str]        # text_hash(opportunity_text(...)) at build time, same order as ids
    vectors: np.ndarray      # (n, 768), normalized rows
    model: str
    fastembed_version: str

    def save(self, path: str = INDEX_PATH) -> None:
        np.savez(path, ids=np.array(self.ids), hashes=np.array(self.hashes), vectors=self.vectors,
                 model=np.array(self.model), fastembed_version=np.array(self.fastembed_version))

    @classmethod
    def load(cls, path: str = INDEX_PATH) -> "OpportunityIndex":
        if not os.path.exists(path):
            raise FileNotFoundError(f"{path} not found: build it with `uv run python scripts/build_match_index.py`")
        # allow_pickle=False: only plain arrays are read, nothing in the file can run code
        with np.load(path, allow_pickle=False) as data:
            return cls(ids=data["ids"].tolist(), hashes=data["hashes"].tolist(), vectors=data["vectors"],
                       model=str(data["model"]), fastembed_version=str(data["fastembed_version"]))

    def check_matches(self, opportunities: list[ProcessedOpportunity]) -> None:
        """Fail loudly if the index was built from a different corpus or fastembed version.
        Either would make the scores silently wrong, so refuse instead (as the classifier does)."""
        installed = version("fastembed")
        if installed != self.fastembed_version:
            raise RuntimeError(f"index built with fastembed {self.fastembed_version}, {installed} is installed: "
                               "rebuild with `uv run python scripts/build_match_index.py`")
        built = dict(zip(self.ids, self.hashes))
        stale = [o.id for o in opportunities if built.get(o.id) != text_hash(opportunity_text(o))]
        if stale:
            raise RuntimeError(f"{len(stale)} opportunities are new or changed since the index was built "
                               f"(e.g. {stale[0]}): rebuild with `uv run python scripts/build_match_index.py`")


def build_index(opportunities: list[ProcessedOpportunity], embedder: TextEmbedding | None = None) -> OpportunityIndex:
    embedder = embedder or load_embedder()
    texts = [opportunity_text(o) for o in opportunities]
    return OpportunityIndex(ids=[o.id for o in opportunities], hashes=[text_hash(t) for t in texts],
                            vectors=embed_passages(embedder, texts), model=EMBEDDING_MODEL,
                            fastembed_version=version("fastembed"))
