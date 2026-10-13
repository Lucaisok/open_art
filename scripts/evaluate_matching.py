"""
Evaluate "Matched to you": how many of an artist's top 10 calls are relevant to them?

The set (dataset/matching_eval/, workflow.MD "Matching evaluation"):
  personas.json    16 synthetic artists: a short statement (practice + what they look for) and the
                   profile the eligibility engine reads. Synthetic on purpose: they are test inputs,
                   so they can cover every discipline of the corpus.
  judgments.csv    persona_id, opportunity_id, grade (0/1/2), judge, note. Graded blind: the judge
                   saw the persona and the call, never the rank, the score or the variant.

Each persona is ranked the way the app ranks an artist: the statement goes into a knowledge base,
suggest_query picks its passages about practice and wishes, they are embedded, and the calls kept by
"Matched to you"'s starting filters (the profile's disciplines, open calls only) are ranked. Then
every ranking VARIANT below orders the same calls, and the top 10 of each is scored:

  P@10        share of the top 10 graded 1 or 2 ("worth showing")
  strict P@10 share graded 2 ("a clear fit")
  NDCG@10     like P@10, but a good call higher up counts more (gains 0/1/2)

    uv run python scripts/evaluate_matching.py pool      # rank (~10 min on a laptop CPU), write rankings.json
                                                         # and the calls still to judge (pool.json)
    uv run python scripts/evaluate_matching.py score     # the metrics table from rankings.json + judgments.csv

Re-run `pool` after any change to the ranking or the corpus: `score` only reads the saved rankings.

TODAY is fixed, so the set of open calls (and so the results) doesn't change from day to day.
"""

import csv
import json
import os
import random
import sys
import tempfile
from datetime import date

import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from src.eligibility.profile import ArtistProfile  # noqa: E402
from src.matching.filters import MatchFilters  # noqa: E402
from src.matching.index import embed_passages, embed_query  # noqa: E402
from src.matching.matcher import Matcher, discipline_mismatch  # noqa: E402
from src.rag.knowledge_base import ArtistKnowledgeBase  # noqa: E402
from src.rag.query_suggestion import suggest_query  # noqa: E402

EVAL_DIR = os.path.join(REPO_ROOT, "dataset", "matching_eval")
PERSONAS_PATH = os.path.join(EVAL_DIR, "personas.json")
JUDGMENTS_PATH = os.path.join(EVAL_DIR, "judgments.csv")
POOL_PATH = os.path.join(EVAL_DIR, "pool.json")
RANKINGS_PATH = os.path.join(EVAL_DIR, "rankings.json")   # persona -> {"status": {id: status}, "tops": {variant: ids}}

TODAY = date(2026, 10, 13)
K = 10                 # the first screen of results
RERANK_DEPTH = 30      # the cross-encoder variants reread this many of the best calls

STATUS_ORDER = {"ELIGIBLE": 0, "CHECK": 1, "LIKELY_NOT_ELIGIBLE": 2}
# bge-reranker-base was tried too: ~1 GB and minutes per persona on CPU, too heavy for the VPS
CROSS_ENCODERS = {"ce_minilm": "Xenova/ms-marco-MiniLM-L-6-v2"}


def rich_text(o) -> str:
    """Experiment: the call text with the call's own project themes, and without the "Type:" line
    (the type filter already handles type)."""
    parts = [o.title_en, o.description_en, o.project_requirements_en or o.project_requirements]
    if o.discipline_en:
        parts.append(f"Discipline: {o.discipline_en}")
    return "\n".join(p.strip() for p in parts if p and p.strip())


def persona_rows(matcher: Matcher, persona: dict, rich_vectors: dict, cross_encoders: dict) -> list[dict]:
    """Every call "Matched to you" keeps for this persona, with what each variant sorts on."""
    profile = ArtistProfile(**persona["profile"])
    # the statement goes through the same steps as an uploaded document in the app
    with tempfile.TemporaryDirectory() as root:
        path = os.path.join(root, "statement.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(persona["statement"])
        kb = ArtistKnowledgeBase(persona["id"], root=root, embedder=matcher.embedder)
        kb.add_document(path, "statement.md")
        query = suggest_query(kb, documents=["statement.md"]).query
    vector = embed_query(matcher.embedder, query)

    kept = matcher.kept(MatchFilters(disciplines=profile.disciplines), TODAY)
    rows = []
    for o in kept:
        verdict = matcher.engine.evaluate(profile, o, today=TODAY)
        rows.append({"id": o.id, "status": verdict.status, "mismatch": discipline_mismatch(o, verdict, profile),
                     "sim": float(matcher.index.vectors[matcher._row[o.id]] @ vector),
                     "rich_sim": float(rich_vectors[o.id] @ vector)})
    # the app's own order, whatever it is in the code right now
    shipped = [m.opportunity_id for m in matcher.search_vector(vector, profile, MatchFilters(
        disciplines=profile.disciplines), k=K, today=TODAY)]

    # cross-encoders reread (query, call text) pairs; only the best RERANK_DEPTH by similarity
    best = sorted(rows, key=lambda r: -r["sim"])[:RERANK_DEPTH]
    for name, model in cross_encoders.items():
        texts = [rich_text(matcher.get(r["id"])) for r in best]
        scores = dict(zip([r["id"] for r in best], model.rerank(query, texts)))
        for r in rows:
            r[name] = scores.get(r["id"], -1e9)   # outside the reread depth: after every reread call
    return rows, shipped


def variants(rows: list[dict], shipped: list[str]) -> dict[str, list[str]]:
    """Each ranking variant's top K ids. Lower sort key = shown first; ties keep corpus order."""
    def top(key) -> list[str]:
        return [r["id"] for r in sorted(rows, key=key)[:K]]

    nel = lambda r: r["status"] == "LIKELY_NOT_ELIGIBLE"           # noqa: E731
    group = lambda r: 2 if nel(r) else (1 if r["mismatch"] else 0)  # noqa: E731
    out = {
        "similarity only (no gates)": top(lambda r: -r["sim"]),
        "A. tiers: eligible first (2026-10-10)": top(lambda r: (STATUS_ORDER[r["status"]], -r["sim"])),
        "B. similarity, not-eligible last": top(lambda r: (nel(r), -r["sim"])),
        "C. B + other discipline down": top(lambda r: (group(r), -r["sim"])),
        "D. C + richer call text": top(lambda r: (group(r), -r["rich_sim"])),
    }
    for name in CROSS_ENCODERS:
        if name in rows[0]:
            out[f"E. C + cross-encoder {name[3:]}"] = top(lambda r, n=name: (group(r), -r[n]))
    out["app (Matcher today)"] = shipped
    return out


def load_judgments() -> dict[tuple[str, str], int]:
    if not os.path.exists(JUDGMENTS_PATH):
        return {}
    with open(JUDGMENTS_PATH, encoding="utf-8") as f:
        return {(r["persona_id"], r["opportunity_id"]): int(r["grade"]) for r in csv.DictReader(f)}


def ndcg(grades: list[int], ideal: list[int]) -> float:
    dcg = sum(g / np.log2(i + 2) for i, g in enumerate(grades))
    best = sum(g / np.log2(i + 2) for i, g in enumerate(sorted(ideal, reverse=True)[:K]))
    return dcg / best if best else 0.0


def call_for_judge(o) -> dict:
    """What the judge sees of a call: what it is about and who it is for, no score, no verdict."""
    return {"opportunity_id": o.id, "title": o.title_en, "organisation": o.organisation,
            "types": o.opportunity_type_canonical, "disciplines": o.discipline_canonical,
            "description": o.description_en,
            "project_requirements": o.project_requirements_en or o.project_requirements}


def rank_all(personas: list[dict], use_cross_encoders: bool) -> dict:
    """Every persona's kept calls ranked by every variant; saved to RANKINGS_PATH."""
    matcher = Matcher()
    print("embedding the richer call texts ...")
    rich = embed_passages(matcher.embedder, [rich_text(o) for o in matcher.opportunities])
    rich_vectors = {o.id: v for o, v in zip(matcher.opportunities, rich)}
    cross_encoders = {}
    if use_cross_encoders:
        from fastembed.rerank.cross_encoder import TextCrossEncoder
        from src.eligibility.classify import EMBEDDING_CACHE_DIR
        cross_encoders = {name: TextCrossEncoder(model, cache_dir=EMBEDDING_CACHE_DIR)
                          for name, model in CROSS_ENCODERS.items()}
    rankings = {}
    for persona in personas:
        rows, shipped = persona_rows(matcher, persona, rich_vectors, cross_encoders)
        rankings[persona["id"]] = {"status": {r["id"]: r["status"] for r in rows}, "tops": variants(rows, shipped)}
        print(f"  {persona['id']}: {len(rows)} calls kept")
    with open(RANKINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(rankings, f, indent=1)
    return rankings, matcher


def write_pool(personas: list[dict], rankings: dict, matcher: Matcher) -> None:
    """Every call any variant shows in a top 10, not judged yet, shuffled (the judge can't guess ranks)."""
    judged = load_judgments()
    rng = random.Random(0)
    pool = []
    for persona in personas:
        ids = sorted({i for top in rankings[persona["id"]]["tops"].values() for i in top
                      if (persona["id"], i) not in judged})
        rng.shuffle(ids)
        if ids:
            pool.append({"persona_id": persona["id"], "statement": persona["statement"],
                         "profile_disciplines": persona["profile"]["disciplines"],
                         "calls": [call_for_judge(matcher.get(i)) for i in ids]})
    with open(POOL_PATH, "w", encoding="utf-8") as f:
        json.dump(pool, f, ensure_ascii=False, indent=1)
    print(f"{sum(len(p['calls']) for p in pool)} calls to judge -> {os.path.relpath(POOL_PATH, REPO_ROOT)}")


def score(personas: list[dict], rankings: dict) -> None:
    """The mean over personas of each metric, per variant."""
    judged = load_judgments()
    names = list(next(iter(rankings.values()))["tops"])
    print(f"\n{len(personas)} personas, top {K}, {len(judged)} judgments\n")
    print(f"{'variant':42} {'P@10':>6} {'strict':>7} {'NDCG@10':>8} {'not-elig.':>9} {'unjudged':>9}")
    for name in names:
        p, strict, n, nel, missing = [], [], [], 0, 0
        for persona in personas:
            pid = persona["id"]
            status, top_ids = rankings[pid]["status"], rankings[pid]["tops"][name]
            grades = []
            for i in top_ids:
                if (pid, i) not in judged:
                    missing += 1
                grades.append(judged.get((pid, i), 0))   # unjudged counts as not relevant
                nel += status[i] == "LIKELY_NOT_ELIGIBLE"
            pool_grades = [g for (q, _), g in judged.items() if q == pid]
            p.append(sum(g >= 1 for g in grades) / K)
            strict.append(sum(g == 2 for g in grades) / K)
            n.append(ndcg(grades, pool_grades))
        print(f"{name:42} {np.mean(p):6.2f} {np.mean(strict):7.2f} {np.mean(n):8.3f} {nel:9d} {missing:9d}")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("pool", "score"):
        sys.exit("usage: evaluate_matching.py pool|score [--no-cross-encoders]")
    personas = json.load(open(PERSONAS_PATH, encoding="utf-8"))
    if sys.argv[1] == "pool":
        rankings, matcher = rank_all(personas, use_cross_encoders="--no-cross-encoders" not in sys.argv)
        write_pool(personas, rankings, matcher)
    else:
        if not os.path.exists(RANKINGS_PATH):
            sys.exit(f"{RANKINGS_PATH} not found: run `evaluate_matching.py pool` first")
        score(personas, json.load(open(RANKINGS_PATH, encoding="utf-8")))
