"""
OpenArt — the semantic-matching index: one embedding per opportunity.

Each opportunity is turned into one English text (what the call is about:
title, description, discipline, type) and embedded once with the same
fastembed model the RQ1 classifier uses. The vectors are saved to
artifacts/opportunity_index.npz; at request time only the artist's query is
embedded and compared against them (src/matching/matcher.py).

requirements_text is deliberately left out: it says who may apply, not what
the call is about, and the eligibility engine already reads it.

Next to the one vector per call, the index keeps one vector per SENTENCE of the call's
description (evidence_sentences). They don't change the ranking: they explain it. For a call
in the results, the sentence closest to the artist's query is shown as "why it's here"
(Matcher.evidence, workflow.MD "Why this call").

Build or refresh the index with: uv run python scripts/build_match_index.py
"""

import hashlib
import os
from dataclasses import dataclass, field
from importlib.metadata import version

import numpy as np
from fastembed import TextEmbedding

from src.eligibility.chunking import split_into_chunks
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


# a shorter "sentence" is a fragment or a heading ("Deadline:"), which explains nothing
MIN_EVIDENCE_WORDS = 5


def evidence_sentences(opp: ProcessedOpportunity) -> list[str]:
    """The sentences of the call's description that can explain a match, in order. Only the
    description: it is part of the embedded text (so of the score), and the card doesn't show it.
    Its text is covered by the call's text_hash, so a stale sentence is caught with the call."""
    return [s for s in split_into_chunks(opp.description_en or "") if len(s.split()) >= MIN_EVIDENCE_WORDS]


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
    if not texts:
        return np.zeros((0, 0), dtype=np.float32)
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
    # the evidence sentences of every call, one row each: whose they are (a row of ids), the text, the vector.
    # Empty by default (tests that don't need evidence build an index without them)
    sentence_owner: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.int32))
    sentence_texts: list[str] = field(default_factory=list)
    sentence_vectors: np.ndarray = field(default_factory=lambda: np.zeros((0, 0), dtype=np.float32))

    def save(self, path: str = INDEX_PATH) -> None:
        np.savez(path, ids=np.array(self.ids), hashes=np.array(self.hashes), vectors=self.vectors,
                 model=np.array(self.model), fastembed_version=np.array(self.fastembed_version),
                 sentence_owner=self.sentence_owner, sentence_texts=np.array(self.sentence_texts, dtype=str),
                 sentence_vectors=self.sentence_vectors)

    @classmethod
    def load(cls, path: str = INDEX_PATH) -> "OpportunityIndex":
        if not os.path.exists(path):
            raise FileNotFoundError(f"{path} not found: build it with `uv run python scripts/build_match_index.py`")
        # allow_pickle=False: only plain arrays are read, nothing in the file can run code
        with np.load(path, allow_pickle=False) as data:
            if "sentence_vectors" not in data:
                raise RuntimeError(f"{path} has no sentence vectors (built before 2026-10-13): "
                                   "rebuild with `uv run python scripts/build_match_index.py`")
            return cls(ids=data["ids"].tolist(), hashes=data["hashes"].tolist(), vectors=data["vectors"],
                       model=str(data["model"]), fastembed_version=str(data["fastembed_version"]),
                       sentence_owner=data["sentence_owner"], sentence_texts=data["sentence_texts"].tolist(),
                       sentence_vectors=data["sentence_vectors"])

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
    # every call's evidence sentences, flattened, each remembering whose it is
    owner, sentences = [], []
    for row, o in enumerate(opportunities):
        for sentence in evidence_sentences(o):
            owner.append(row)
            sentences.append(sentence)
    return OpportunityIndex(ids=[o.id for o in opportunities], hashes=[text_hash(t) for t in texts],
                            vectors=embed_passages(embedder, texts), model=EMBEDDING_MODEL,
                            fastembed_version=version("fastembed"),
                            sentence_owner=np.array(owner, dtype=np.int32), sentence_texts=sentences,
                            sentence_vectors=embed_passages(embedder, sentences))
