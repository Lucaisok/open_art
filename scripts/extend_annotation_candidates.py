"""
OpenArt — second annotation round: extend the RQ1 candidate pool without
touching what's already sampled or labeled (ANNOTATION_GUIDELINES.md §6,
2026-09-29 entry).

select_annotation_candidates.py can't simply be re-run with a bigger
--target: it overwrites candidate_chunks.csv, and its per-source cap is
derived from --target, so a new target reshuffles which opportunities get
picked instead of adding to them. This script only ever *appends*, and
draws only from opportunities not yet in the pool.

Two batches, both tagged in a new `batch` column so they can be reported
separately in the write-up:

1. round2_random — whole opportunities sampled at random, every chunk of
   each kept, same source cap as round 1 but applied to the *combined*
   pool (existing + new). Same method as round 1, so the class mix stays
   representative of what the model sees in the product.
2. round2_targeted — single chunks keyword-matched to the classes that are
   still thin (EDUCATION, NATIONALITY, CAREER_STAGE), drawn from
   opportunities that neither round has sampled, at most 2 per opportunity
   so one call can't dominate a class. Same move as round 1's AGE /
   EDUCATION / NATIONALITY top-ups, just scripted. A keyword hit is only a
   candidate: the label is still decided per chunk against the guidelines.

Round 3 (2026-09-30) reuses the targeted batch only, for the classes still
thin after the taxonomy revision, with batch names prefixed round3_:
    --round 3 --random-target 0 --classes EDUCATION PRIOR_FUNDING --targeted-per-class 40
EDUCATION's round-3 pattern is narrower than round 2's (which mostly hit
current-enrolment STUDENT_STATUS chunks); PRIOR_FUNDING is new.

Usage: uv run python scripts/extend_annotation_candidates.py [--random-target 350] [--targeted-per-class 35] [--seed 7]
                                                            [--round 2] [--classes EDUCATION NATIONALITY CAREER_STAGE]
"""

import argparse
import os
import random
import re

import pandas as pd

from select_annotation_candidates import (
    DATASET_PATH,
    EXCLUDED_OPPORTUNITY_IDS,
    OUT_PATH,
    split_into_chunks,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANNOTATIONS_PATH = os.path.join(REPO_ROOT, "dataset", "labels", "eligibility_annotations.csv")

# keyword heuristics for the targeted batch - deliberately broad (recall over
# precision): false hits cost one quick read, missed chunks cost nothing but
# are simply not candidates
TARGET_KEYWORDS = {
    "EDUCATION": r"\b(degree|diploma|bachelor|master'?s?|graduat\w*|qualification\w*|academy|university|conservato\w+|art school)\b",
    "NATIONALITY": r"\b(citizens?|citizenship|nationals?|nationality|passport)\b",
    # "established(?! by)": the bare word also matches legal-form boilerplate ("organisation
    # established by a municipality"), which flooded the first draw with near-duplicates
    "CAREER_STAGE": r"\b(emerging|early[- ]career|mid[- ]career|established(?! by)|years? of (?:professional )?(?:practice|experience)|debut)\b",
    # round 3: degree/qualification wording only - "graduate"/"academy"/"university" mostly
    # matched current enrolment or recent graduation (STUDENT_STATUS) in round 2
    "EDUCATION_R3": r"\b(degree in|(?:hold|have|completed) an? (?:\w+ )?(?:degree|diploma|qualification)|diploma|bachelor'?s? degree|master'?s? degree|formal (?:art |artistic )?(?:education|training)|qualification\w*|self[- ]taught)\b",
    "PRIOR_FUNDING": r"\b(previous(?:ly)? (?:recipients?|awarded|supported|funded|participat\w*|rejected|received)|previous (?:grants?|support|funding|applications?)|already (?:receiv\w+|been awarded|hold\w*)|fixed annual|(?:annual|operating) (?:state )?(?:grants?|subsid\w+|funding)|more than (?:once|one grant|twice)|at the same time|re-?apply\w*|rejected)\b",
}
MAX_TARGETED_PER_OPPORTUNITY = 2
MIN_CHUNK_WORDS = 4  # bare headings ("Who can apply?") are excluded per §6, don't pick them as targets


def extend_candidates(random_target: int, targeted_per_class: int, source_cap: float, seed: int,
                      round_no: int = 2, classes: tuple = ("EDUCATION", "NATIONALITY", "CAREER_STAGE")) -> pd.DataFrame:
    corpus = pd.read_csv(DATASET_PATH)
    existing = pd.read_csv(OUT_PATH)
    if "batch" not in existing.columns:
        existing["batch"] = "round1"  # everything sampled before this script existed

    # anything already in the pool or already labeled is off limits - including
    # round 1's top-up opportunities, which live in both files
    used = set(existing["opportunity_id"]) | set(pd.read_csv(ANNOTATIONS_PATH)["opportunity_id"])
    usable = corpus[~corpus["id"].isin(EXCLUDED_OPPORTUNITY_IDS | used)].copy()
    print(f"{len(corpus)} opportunities in corpus, {len(used)} already used, {len(usable)} available")

    # ---- batch 1: random whole opportunities, source cap over the combined pool ----
    final_size = len(existing) + random_target
    max_per_source = max(1, round(final_size * source_cap))
    source_counts = existing["source"].value_counts().to_dict()
    print(f"Source cap: {source_cap:.0%} of the combined pool (~{final_size}) = {max_per_source} chunks per source")

    rng = random.Random(seed)
    order = list(usable.index)
    rng.shuffle(order)

    records, taken_opps, n_random = [], set(), 0
    for idx in order:
        if n_random >= random_target:
            break
        row = usable.loc[idx]
        chunks = split_into_chunks(str(row["requirements_text_en"]))
        if not chunks or source_counts.get(row["source"], 0) + len(chunks) > max_per_source:
            continue  # no fallback relaxation here: 400 available opportunities is plenty
        for i, text in enumerate(chunks):
            records.append(_record(row, i, text, f"round{round_no}_random"))
        source_counts[row["source"]] = source_counts.get(row["source"], 0) + len(chunks)
        taken_opps.add(row["id"])
        n_random += len(chunks)
    print(f"round{round_no}_random: {n_random} chunks from {len(taken_opps)} opportunities")

    # ---- batch 2: keyword-targeted single chunks, from opportunities neither round used ----
    remaining = usable[~usable["id"].isin(taken_opps)]
    pool = [(row, i, text)
            for _, row in remaining.iterrows()
            for i, text in enumerate(split_into_chunks(str(row["requirements_text_en"])))
            if len(text.split()) >= MIN_CHUNK_WORDS]
    rng.shuffle(pool)

    per_opp, picked_ids = {}, set()
    for target_class in classes:
        regex, n = re.compile(TARGET_KEYWORDS[target_class], re.IGNORECASE), 0
        for row, i, text in pool:
            if n >= targeted_per_class:
                break
            chunk_id = f"{row['id']}_{i}"
            if chunk_id in picked_ids or per_opp.get(row["id"], 0) >= MAX_TARGETED_PER_OPPORTUNITY:
                continue
            if regex.search(text):
                records.append(_record(row, i, text, f"round{round_no}_targeted", keyword_class=target_class))
                picked_ids.add(chunk_id)
                per_opp[row["id"]] = per_opp.get(row["id"], 0) + 1
                n += 1
        print(f"round{round_no}_targeted / {target_class}: {n} chunks")

    new = pd.DataFrame(records)
    combined = pd.concat([existing, new], ignore_index=True)
    assert not combined["chunk_id"].duplicated().any(), "chunk_id collision - pool would double-count a chunk"
    combined.to_csv(OUT_PATH, index=False)
    print(f"\n{len(new)} new candidate chunks appended -> {OUT_PATH} ({len(combined)} total)")
    return new


def _record(row: pd.Series, i: int, text: str, batch: str, keyword_class: str = "") -> dict:
    """One candidate row, same columns as round 1 plus batch / keyword_class for traceability."""
    return {
        "opportunity_id": row["id"],
        "chunk_id": f"{row['id']}_{i}",
        "chunk_index": i,
        "chunk_text": text,
        "source": row["source"],
        "opportunity_type_canonical": row["opportunity_type_canonical"],
        "discipline_canonical": row["discipline_canonical"],
        "batch": batch,
        "keyword_class": keyword_class,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--random-target", type=int, default=350, help="chunks to add from random whole opportunities")
    parser.add_argument("--targeted-per-class", type=int, default=35, help="keyword-targeted chunks per thin class")
    parser.add_argument("--source-cap", type=float, default=0.18, help="max share of the combined pool per source")
    parser.add_argument("--seed", type=int, default=7, help="random seed (differs from round 1's 42 on purpose)")
    parser.add_argument("--round", type=int, default=2, dest="round_no", help="round number, used in the batch names")
    parser.add_argument("--classes", nargs="+", default=["EDUCATION", "NATIONALITY", "CAREER_STAGE"],
                        choices=list(TARGET_KEYWORDS), help="keyword patterns for the targeted batch")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    extend_candidates(args.random_target, args.targeted_per_class, args.source_cap, args.seed,
                      args.round_no, tuple(args.classes))
