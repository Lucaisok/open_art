"""
OpenArt — interactive CLI for the round-2 label review (ANNOTATION_GUIDELINES.md
§6, 2026-09-29). Fills in `your_label` / `your_note` in the two review files,
one chunk at a time, so they never need editing by hand.

Two passes, in this order:
1. blind   — dataset/labels/review/round2_blind.csv. The pre-label is NOT
             shown: label each chunk from scratch. This is what measures
             human-vs-LLM agreement, so the order matters - do it first,
             before seeing any of the session's reasoning in the flagged pass.
2. flagged — dataset/labels/review/round2_flagged.csv. The pre-label and the
             reason it was flagged are shown: press Enter to confirm it, or
             type a number to change it.

Every answer is written to disk immediately, and chunks already answered are
skipped, so it's safe to quit (q) and resume anytime. 'u' undoes the previous
answer. Neighbouring sentences from the same call are shown as context, since
many chunks are hard to judge alone.

When both passes are done, run scripts/apply_label_review.py.

Usage: uv run python scripts/review_labels.py [--only blind|flagged]
"""

import argparse
import os
import re

import pandas as pd

from label_chunks import LABELS

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REVIEW_DIR = os.path.join(REPO_ROOT, "dataset", "labels", "review")
CANDIDATES_PATH = os.path.join(REPO_ROOT, "dataset", "labels", "candidate_chunks.csv")
PASSES = {
    "blind": os.path.join(REVIEW_DIR, "round2_blind.csv"),
    "flagged": os.path.join(REVIEW_DIR, "round2_flagged.csv"),
}

SPLIT_SUFFIX_RE = re.compile(r"^(.*_\d+)([a-z])$")  # Option-B split rows: <chunk_id>a, <chunk_id>b, ...
DIM, BOLD, RESET = "\033[2m", "\033[1m", "\033[0m"


class Context:
    """Looks up the sentences around a chunk in its original call, from the candidate pool."""

    def __init__(self, path: str):
        cands = pd.read_csv(path, keep_default_na=False)
        self.by_id = cands.set_index("chunk_id")
        self.by_opp = {opp: grp.sort_values("chunk_index") for opp, grp in cands.groupby("opportunity_id")}

    def show(self, chunk_id: str) -> None:
        match = SPLIT_SUFFIX_RE.match(chunk_id)
        base_id = match.group(1) if match and match.group(1) in self.by_id.index else chunk_id
        if base_id not in self.by_id.index:
            return
        row = self.by_id.loc[base_id]
        if base_id != chunk_id:  # a split part: show the full sentence it was cut from
            print(f"{DIM}  split from: \"{row['chunk_text']}\"{RESET}")
        siblings = self.by_opp[row["opportunity_id"]]
        idx = int(row["chunk_index"])
        for offset, tag in ((-1, "before"), (1, "after")):
            near = siblings[siblings["chunk_index"] == idx + offset]
            if len(near):
                print(f"{DIM}  {tag}: \"{_short(near.iloc[0]['chunk_text'])}\"{RESET}")


def _short(text: str, limit: int = 160) -> str:
    return text if len(text) <= limit else text[:limit] + "…"


def print_menu() -> None:
    print("  " + "   ".join(f"{i} {label}" for i, label in enumerate(LABELS[:5], start=1)))
    print("  " + "   ".join(f"{i} {label}" for i, label in enumerate(LABELS[5:], start=6)))
    print(f"{DIM}  s SKIP (set aside)   u undo previous   q quit{RESET}")


def ask(prompt: str, default: str | None) -> str:
    """Returns a label, 'SKIP', 'UNDO' or 'QUIT'. With a default, Enter accepts it."""
    while True:
        raw = input(prompt).strip().lower()
        if not raw and default:
            return default
        if raw in ("q", "quit"):
            return "QUIT"
        if raw in ("u", "undo"):
            return "UNDO"
        if raw in ("s", "skip"):
            return "SKIP"
        if raw.isdigit() and 1 <= int(raw) <= len(LABELS):
            return LABELS[int(raw) - 1]
        print(f"  enter 1-{len(LABELS)}, s, u or q" + (" (Enter confirms)" if default else ""))


def review(name: str, path: str, context: Context) -> bool:
    """Runs one pass. Returns False if the reviewer quit early."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    flagged = name == "flagged"
    history = []  # row indices answered in this session, for undo

    while True:
        todo = df.index[df["your_label"].str.strip() == ""]
        if not len(todo):
            print(f"{BOLD}{name}: all {len(df)} rows done.{RESET}\n")
            return True
        i = todo[0]
        row = df.loc[i]
        print(f"\n{BOLD}[{name} {len(df) - len(todo) + 1}/{len(df)}]{RESET}  {DIM}{row['chunk_id']}{RESET}")
        context.show(row["chunk_id"])
        print(f"\n  {BOLD}\"{row['chunk_text']}\"{RESET}\n")
        if flagged:
            print(f"  pre-label: {BOLD}{row['claude_label']}{RESET}")
            print(f"{DIM}  why flagged: {row['why_flagged']}{RESET}\n")
        print_menu()

        choice = ask("label (Enter = confirm)> " if flagged else "label> ", row["claude_label"] if flagged else None)
        if choice == "QUIT":
            print("\nStopped. Resume anytime - answered rows won't be shown again.")
            return False
        if choice == "UNDO":
            if history:
                last = history.pop()
                df.loc[last, ["your_label", "your_note"]] = ""
                df.to_csv(path, index=False)
                print("  undone - showing the previous chunk again")
            else:
                print("  nothing to undo in this session")
            continue

        # a note is only asked for when it adds something: a change or a skip
        note = ""
        if choice == "SKIP" or (flagged and choice != row["claude_label"]):
            note = input("  note, why (optional, Enter to skip)> ").strip()
        df.loc[i, ["your_label", "your_note"]] = [choice, note]
        df.to_csv(path, index=False)  # saved after every answer
        history.append(i)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", choices=list(PASSES), help="run just one pass")
    args = parser.parse_args()

    context = Context(CANDIDATES_PATH)
    for name, path in PASSES.items():
        if args.only and name != args.only:
            continue
        if not review(name, path, context):
            return
    if not args.only:
        print("Both passes done. Next: uv run python scripts/apply_label_review.py")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\n\nStopped. Resume anytime - answered rows won't be shown again.")
