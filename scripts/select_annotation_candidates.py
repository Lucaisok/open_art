"""
OpenArt — stratified sampling of candidate sentence-chunks for RQ1 eligibility
annotation. Implements ANNOTATION_GUIDELINES.md §0 (excluded rows), §1
(sentence-level chunking) and §4 (source/opportunity diversity caps).

Samples whole opportunities at random (never cherry-picked for "looks
eligibility-rich") so the NONE class isn't silently underrepresented, then
takes every sentence-chunk from each selected opportunity. Caps any single
source's share of the final chunk pool against --target directly, rather
than trusting the guideline's own stale 32%-of-371-rows figure — recomputed
live against the current corpus every run.

Output is an intermediate working file, not the annotation deliverable
itself (that's data/labels/eligibility_annotations.csv, written by
label_chunks.py as you label).

Usage: uv run python scripts/select_annotation_candidates.py [--target 260] [--source-cap 0.18] [--seed 42]
"""

import argparse
import os
import random
import re

import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATASET_PATH = os.path.join(REPO_ROOT, "dataset", "opportunities.csv")
# dataset/ (not data/) is deliberate: this is derived from already-published
# requirements_text_en, not raw scraped content, so it's meant to be published
# alongside opportunities.csv for RQ1 reproducibility. See workflow.MD.
OUT_PATH = os.path.join(REPO_ROOT, "dataset", "labels", "candidate_chunks.csv")

# ANNOTATION_GUIDELINES.md §0 — broken requirements_text, not real eligibility prose
EXCLUDED_OPPORTUNITY_IDS = {
    "cite_internationale_des_arts_f26918d6e623",
    "dgartes_portugal_4fe806b71e57",
    "dgartes_portugal_cc9be82e728f",
}

BULLET_SPLIT_RE = re.compile(r"[\r\n]+|(?:(?<=\s)|^)[•▪◦*]\s+")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.;!?])\s+(?=[A-Z0-9(\"'])")
LEADING_MARKER_RE = re.compile(
    r"^[\-–—•▪◦*]+\s*"                    # dash/bullet glyphs
    r"|^\(?[0-9]{1,2}(?:\.[0-9]{1,2})*[.)]\s+"       # 1.  1.1.  2.3)  (1)
    r"|^[a-zA-Z][.)]\s+"                             # a.  b)
)


def split_into_chunks(text: str) -> list[str]:
    """Sentence-level chunking per ANNOTATION_GUIDELINES.md §1: one sentence =
    one chunk, splitting on '.', ';', or a clear clause break like a bullet
    point. Imperfect on abbreviations and other edge cases by design — a
    human reviews every chunk during labeling and can skip a malformed one
    rather than this being tuned further."""
    chunks = []
    for block in BULLET_SPLIT_RE.split(text.strip()):
        block = LEADING_MARKER_RE.sub("", block.strip()).strip()
        if not block:
            continue
        for sentence in SENTENCE_SPLIT_RE.split(block):
            sentence = sentence.strip()
            if sentence:
                chunks.append(sentence)
    return chunks


def select_candidates(
    dataset_path: str = DATASET_PATH,
    out_path: str = OUT_PATH,
    target: int = 260,
    source_cap: float = 0.18,
    seed: int = 42,
) -> pd.DataFrame:
    df = pd.read_csv(dataset_path)
    usable = df[~df["id"].isin(EXCLUDED_OPPORTUNITY_IDS)].copy()
    print(f"{len(df)} opportunities total, {len(usable)} usable after excluding "
          f"{len(EXCLUDED_OPPORTUNITY_IDS)} broken row(s) (§0)")

    max_chunks_per_source = max(1, round(target * source_cap))
    print(f"Source cap: {source_cap:.0%} of target ({target}) = {max_chunks_per_source} chunks max per source\n")

    rng = random.Random(seed)
    order = list(usable.index)
    rng.shuffle(order)

    source_chunk_counts: dict[str, int] = {}
    selected: list[tuple[pd.Series, list[str]]] = []
    total_chunks = 0
    deferred: list[tuple[pd.Series, list[str]]] = []

    for idx in order:
        if total_chunks >= target:
            break
        row = usable.loc[idx]
        chunks = split_into_chunks(str(row["requirements_text_en"]))
        if not chunks:
            continue
        source = row["source"]
        projected = source_chunk_counts.get(source, 0) + len(chunks)
        if projected > max_chunks_per_source:
            deferred.append((row, chunks))
            continue
        selected.append((row, chunks))
        source_chunk_counts[source] = projected
        total_chunks += len(chunks)

    # Fallback: if the cap left the target short, relax it rather than looping
    # forever — pull from deferred candidates in the same shuffled order.
    if total_chunks < target and deferred:
        print(f"Only reached {total_chunks}/{target} chunks under the source cap — relaxing it to fill the rest")
        for row, chunks in deferred:
            if total_chunks >= target:
                break
            selected.append((row, chunks))
            source_chunk_counts[row["source"]] = source_chunk_counts.get(row["source"], 0) + len(chunks)
            total_chunks += len(chunks)

    records = []
    for row, chunks in selected:
        if len(chunks) > 8:
            print(f"  note: {row['id']} ({row['source']}) contributes {len(chunks)} chunks on its own — "
                  f"§4 dominance check, review if this looks like a bulleted list worth subsampling")
        for i, chunk_text in enumerate(chunks):
            records.append({
                "opportunity_id": row["id"],
                "chunk_id": f"{row['id']}_{i}",
                "chunk_index": i,
                "chunk_text": chunk_text,
                "source": row["source"],
                "opportunity_type_canonical": row["opportunity_type_canonical"],
                "discipline_canonical": row["discipline_canonical"],
            })

    out_df = pd.DataFrame(records)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    out_df.to_csv(out_path, index=False)

    print(f"\n{len(selected)} opportunities selected, {len(out_df)} candidate chunks written to {out_path}")
    print("\nSource share of final pool:")
    share = out_df["source"].value_counts(normalize=True).sort_values(ascending=False)
    for source, pct in share.items():
        print(f"  {source:35s} {pct:.1%}")

    return out_df


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", type=int, default=260,
                         help="target chunk count (aim a bit above the 200-300 midpoint for skip/attrition headroom)")
    parser.add_argument("--source-cap", type=float, default=0.18,
                         help="max share of the final chunk pool any one source may contribute")
    parser.add_argument("--seed", type=int, default=42, help="random seed, for a reproducible sample")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    select_candidates(target=args.target, source_cap=args.source_cap, seed=args.seed)
