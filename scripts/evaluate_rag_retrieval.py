"""
Sanity check of RAG retrieval with the real model, on the two fictional personas (examples/artists/).

    uv run python scripts/evaluate_rag_retrieval.py

Each question has one section where the answer is. Reports how often that section comes first
(top-1) and how often it is among the first three (top-3). Two sets:
- OPEN:    natural questions over all of an artist's documents
- PROFILE: short field-style queries over the CV only, the way profile pre-fill (step 3) will ask

20 + 12 hand-written questions on 22 chunks: this shows retrieval works and where it confuses
sections, it is not a benchmark. The knowledge bases are built in a temporary folder.
"""

import glob
import os
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from src.rag.knowledge_base import ArtistKnowledgeBase  # noqa: E402

CV = {"ilka_varga": "cv.pdf", "tomas_ferreira": "cv.docx"}

# (artist, question, expected document, expected section)
OPEN = [
    ("ilka_varga", "What is the artist's nationality or citizenship?", "cv.pdf", "PERSONAL DETAILS"),
    ("ilka_varga", "When was the artist born?", "cv.pdf", "PERSONAL DETAILS"),
    ("ilka_varga", "In which country does the artist live?", "cv.pdf", "PERSONAL DETAILS"),
    ("ilka_varga", "What degrees does the artist hold?", "cv.pdf", "EDUCATION"),
    ("ilka_varga", "Which residencies has the artist done?", "cv.pdf", "RESIDENCIES"),
    ("ilka_varga", "Has the artist received grants or public funding before?", "cv.pdf", "AWARDS AND GRANTS"),
    ("ilka_varga", "Where has the artist had solo shows?", "cv.pdf", "SOLO EXHIBITIONS"),
    ("ilka_varga", "Which languages does the artist speak?", "cv.pdf", "LANGUAGES"),
    ("ilka_varga", "What techniques and materials does the artist use?", "statement.docx", "Methods"),
    ("ilka_varga", "What is the artist's current project about?", "statement.docx", "Current project"),
    ("tomas_ferreira", "What is the artist's nationality or citizenship?", "cv.docx", "Personal details"),
    ("tomas_ferreira", "When was the artist born?", "cv.docx", "Personal details"),
    ("tomas_ferreira", "Is the artist currently a student?", "cv.docx", "Education"),
    ("tomas_ferreira", "Does the artist apply as an individual or as a collective?", "cv.docx", "Personal details"),
    ("tomas_ferreira", "What degrees does the artist hold?", "cv.docx", "Education"),
    ("tomas_ferreira", "Which residencies has the artist done?", "cv.docx", "Residencies"),
    ("tomas_ferreira", "Has the artist received grants or public funding before?", "cv.docx", "Grants"),
    ("tomas_ferreira", "Where has the artist exhibited or performed?", "cv.docx", "Exhibitions and performances"),
    ("tomas_ferreira", "What themes does the artist's work explore?", "statement.md", "Themes"),
    ("tomas_ferreira", "Which collectives does the artist work with?", "statement.md", "Collaborations"),
]

PROFILE = [
    (artist, query, CV[artist], section)
    for artist, section in [("ilka_varga", "PERSONAL DETAILS"), ("tomas_ferreira", "Personal details")]
    for query in ["nationality, citizenship", "date of birth", "country of residence, where I live and work"]
] + [
    ("ilka_varga", "degrees, education, currently enrolled as a student", "cv.pdf", "EDUCATION"),
    ("tomas_ferreira", "degrees, education, currently enrolled as a student", "cv.docx", "Education"),
    ("ilka_varga", "grants, awards and public funding received", "cv.pdf", "AWARDS AND GRANTS"),
    ("tomas_ferreira", "grants, awards and public funding received", "cv.docx", "Grants"),
    ("ilka_varga", "exhibitions", "cv.pdf", "SOLO EXHIBITIONS"),
    ("tomas_ferreira", "exhibitions", "cv.docx", "Exhibitions and performances"),
]


def run(name: str, cases: list, kbs: dict, cv_only: bool) -> None:
    top1 = top3 = 0
    print(f"\n{name}")
    for artist, question, document, section in cases:
        passages = kbs[artist].retrieve(question, k=3, documents=[CV[artist]] if cv_only else None)
        found = [(p.chunk.document, p.chunk.section) for p in passages]
        rank = found.index((document, section)) + 1 if (document, section) in found else None
        top1 += rank == 1
        top3 += rank is not None
        mark = "ok  " if rank == 1 else (f"#{rank}  " if rank else "MISS")
        print(f"  {mark} {artist:15} {question:60} -> {passages[0].citation} ({passages[0].score:.3f})")
    print(f"  top-1: {top1}/{len(cases)}   top-3: {top3}/{len(cases)}")


def main() -> None:
    root, embedder, kbs = tempfile.mkdtemp(), None, {}
    for artist in CV:
        kb = ArtistKnowledgeBase(artist, root=root, embedder=embedder)
        for path in sorted(glob.glob(os.path.join(REPO_ROOT, "examples", "artists", artist, "*"))):
            kb.add_document(path)
        embedder, kbs[artist] = kb.embedder, kb   # load the model once, share it
    run("OPEN - natural questions, all documents", OPEN, kbs, cv_only=False)
    run("PROFILE - field-style queries, CV only", PROFILE, kbs, cv_only=True)


if __name__ == "__main__":
    main()
