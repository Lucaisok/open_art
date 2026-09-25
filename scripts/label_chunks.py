"""
OpenArt — interactive CLI for hand-labeling eligibility chunks against the
9-class taxonomy in ANNOTATION_GUIDELINES.md §2. Reads the candidate pool
built by select_annotation_candidates.py, skips chunks already labeled or
skipped in a prior session (safe to stop and resume anytime — every label
is flushed to disk immediately, no batching), and enforces the §7 20-chunk
pilot pause the first time this file's total labeled count crosses 20.

Output matches §5's exact schema:
  opportunity_id, chunk_id, chunk_text, label, excludes, notes
written to data/labels/eligibility_annotations.csv.

A malformed/degenerate chunk (bad sentence split, leftover form-field
residue, etc.) can be set aside with 's' rather than forced into a label —
skipped chunks are logged separately to data/labels/skipped_chunks.csv, kept
out of the labeled schema entirely.

Usage: uv run python scripts/label_chunks.py
Ctrl+C or 'q' at the label prompt quits at any point — progress already
written to disk is never lost.
"""

import csv
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# dataset/ (not data/) is deliberate: these are derived from already-published
# requirements_text_en, not raw scraped content, so they're meant to be
# published alongside opportunities.csv for RQ1 reproducibility. See workflow.MD.
CANDIDATES_PATH = os.path.join(REPO_ROOT, "dataset", "labels", "candidate_chunks.csv")
ANNOTATIONS_PATH = os.path.join(REPO_ROOT, "dataset", "labels", "eligibility_annotations.csv")
SKIPPED_PATH = os.path.join(REPO_ROOT, "dataset", "labels", "skipped_chunks.csv")

ANNOTATION_FIELDS = ["opportunity_id", "chunk_id", "chunk_text", "label", "excludes", "notes"]
SKIPPED_FIELDS = ["opportunity_id", "chunk_id", "chunk_text", "reason"]

# ANNOTATION_GUIDELINES.md §2, in menu order
LABELS = [
    "RESIDENCE", "NATIONALITY", "AGE", "DISCIPLINE", "CAREER_STAGE",
    "EDUCATION", "STUDENT_STATUS", "OTHER_ELIGIBILITY", "NONE",
]

PILOT_SIZE = 20


def load_candidates(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_seen_ids(*paths: str) -> set[str]:
    seen = set()
    for path in paths:
        if not os.path.exists(path):
            continue
        with open(path, newline="", encoding="utf-8") as f:
            seen.update(row["chunk_id"] for row in csv.DictReader(f))
    return seen


def ensure_header(path: str, fields: list[str]) -> None:
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=fields).writeheader()


def count_labeled(path: str) -> int:
    if not os.path.exists(path):
        return 0
    with open(path, newline="", encoding="utf-8") as f:
        return sum(1 for _ in csv.DictReader(f))


def print_label_menu() -> None:
    for i, label in enumerate(LABELS, start=1):
        print(f"  {i}  {label}")


def prompt_label() -> str | None:
    while True:
        raw = input("label> ").strip().lower()
        if raw in ("q", "quit"):
            return None
        if raw in ("s", "skip"):
            return "SKIP"
        if raw.isdigit() and 1 <= int(raw) <= len(LABELS):
            return LABELS[int(raw) - 1]
        print(f"  enter 1-{len(LABELS)}, 's' to skip this chunk, or 'q' to quit")


def prompt_yes_no(prompt: str, default: bool = False) -> bool:
    suffix = "[y/N]" if not default else "[Y/n]"
    raw = input(f"{prompt} {suffix} ").strip().lower()
    if not raw:
        return default
    return raw.startswith("y")


def print_distribution(path: str) -> None:
    if not os.path.exists(path):
        return
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["label"]] = counts.get(row["label"], 0) + 1
    print(f"\nLabel distribution so far ({len(rows)} labeled):")
    for label in LABELS:
        n = counts.get(label, 0)
        print(f"  {label:20s} {n:4d}  ({n / len(rows):.0%})")
    print()


def label_chunks(
    candidates_path: str = CANDIDATES_PATH,
    annotations_path: str = ANNOTATIONS_PATH,
    skipped_path: str = SKIPPED_PATH,
) -> None:
    if not os.path.exists(candidates_path):
        print(f"No candidate pool at {candidates_path} — run select_annotation_candidates.py first")
        return

    candidates = load_candidates(candidates_path)
    ensure_header(annotations_path, ANNOTATION_FIELDS)
    ensure_header(skipped_path, SKIPPED_FIELDS)
    seen = load_seen_ids(annotations_path, skipped_path)

    todo = [c for c in candidates if c["chunk_id"] not in seen]
    total_pool = len(candidates)
    already_done = total_pool - len(todo)
    print(f"{already_done}/{total_pool} chunks already labeled or skipped — {len(todo)} remaining\n")

    already_labeled_count = count_labeled(annotations_path)
    pilot_triggered = already_labeled_count >= PILOT_SIZE

    for i, chunk in enumerate(todo, start=1):
        print(f"[{already_done + i}/{total_pool}] source: {chunk['source']}")
        print(f"  \"{chunk['chunk_text']}\"\n")
        print_label_menu()

        choice = prompt_label()
        if choice is None:
            print("\nStopped. Resume anytime — already-labeled chunks won't be shown again.")
            return

        if choice == "SKIP":
            reason = input("  reason (optional)> ").strip()
            with open(skipped_path, "a", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=SKIPPED_FIELDS).writerow({
                    "opportunity_id": chunk["opportunity_id"],
                    "chunk_id": chunk["chunk_id"],
                    "chunk_text": chunk["chunk_text"],
                    "reason": reason,
                })
        else:
            excludes = prompt_yes_no("  excludes (states who is NOT eligible)?", default=False)
            notes = input("  notes (optional)> ").strip()
            with open(annotations_path, "a", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=ANNOTATION_FIELDS).writerow({
                    "opportunity_id": chunk["opportunity_id"],
                    "chunk_id": chunk["chunk_id"],
                    "chunk_text": chunk["chunk_text"],
                    "label": choice,
                    "excludes": excludes,
                    "notes": notes,
                })
            already_labeled_count += 1

        print()

        if not pilot_triggered and already_labeled_count >= PILOT_SIZE:
            pilot_triggered = True
            print("=" * 60)
            print(f"§7 pilot checkpoint — {PILOT_SIZE} chunks labeled.")
            print_distribution(annotations_path)
            print("Check: is this wildly skewed toward one label (e.g. mostly NONE)?")
            print("Did you hit an edge case not in §3? Add it there before continuing.")
            print("=" * 60)
            if not prompt_yes_no("Continue labeling now?", default=True):
                print("Stopped for review. Resume anytime.")
                return

    print("All candidate chunks labeled or skipped.")
    print_distribution(annotations_path)


if __name__ == "__main__":
    try:
        label_chunks()
    except (KeyboardInterrupt, EOFError):
        print("\n\nStopped. Resume anytime — already-labeled chunks won't be shown again.")
