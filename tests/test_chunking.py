"""Tests for src/eligibility/chunking.py: the shared sentence splitter and the
bare-heading filter. Run with: uv run pytest"""

import os
import re

import pandas as pd
import pytest

from src.eligibility.chunking import chunk_requirements, is_bare_heading, split_into_chunks

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LABELS_DIR = os.path.join(REPO_ROOT, "dataset", "labels")


# --- Splitter ------------------------------------------------------------------


def test_splits_on_sentences_and_bullets():
    text = "Open to artists. Applicants must be over 18.\n• Students\n• 1. Graduates"
    assert split_into_chunks(text) == [
        "Open to artists.",
        "Applicants must be over 18.",
        "Students",
        "Graduates",  # leading "1." list marker removed
    ]


def test_labeled_chunk_ids_still_point_at_their_sentence():
    """chunk_id "<opportunity_id>_<n>" means "the n-th chunk of that call".
    If the splitter changes, these ids silently point at the wrong sentence.
    550 labeled chunks matched exactly when the splitter moved to src/
    (2026-10-01); the rest were hand-split ("_3a") or edited during
    annotation, so they can't be checked this way."""
    corpus = pd.read_csv(os.path.join(REPO_ROOT, "dataset", "opportunities.csv")).set_index("id")
    labels = pd.read_csv(os.path.join(LABELS_DIR, "eligibility_annotations.csv"))

    matches = 0
    for chunk_id, chunk_text in zip(labels["chunk_id"], labels["chunk_text"]):
        found = re.match(r"^(.*)_(\d+)$", chunk_id)
        if not found:
            continue  # hand-split chunk, e.g. "..._3a"
        opportunity_id, index = found.group(1), int(found.group(2))
        chunks = split_into_chunks(str(corpus.at[opportunity_id, "requirements_text_en"]))
        if index < len(chunks) and chunks[index] == chunk_text:
            matches += 1
    assert matches >= 550


# --- Bare-heading filter --------------------------------------------------------


@pytest.mark.parametrize("text", [
    "Who can apply?",
    "Who may not apply?",
    "Eligible applicants",
    "We are looking for",
    "Partners can include:",
    "ATTENTION!",
])
def test_bare_headings_are_flagged(text):
    assert is_bare_heading(text)


@pytest.mark.parametrize("text", [
    "Ukrainian citizens",                            # short, but a real constraint
    "or residents of Norway",
    "Applications are open to students who:",        # lead-in that names a topic
    "Eligible applicants: Legal entities",
    "Who are French-speaking and write in French",   # list item, not a question
    "Applicants must be resident in Belgium.",       # a normal sentence
])
def test_real_constraints_are_not_flagged(text):
    assert not is_bare_heading(text)


def test_headings_removed_during_annotation_are_flagged():
    """Every heading removed from the labeled set (skipped_chunks.csv, reason
    mentions "heading") must be caught, or the classifier gets input it was
    deliberately not trained on."""
    skipped = pd.read_csv(os.path.join(LABELS_DIR, "skipped_chunks.csv"))
    headings = skipped[skipped["reason"].str.contains("heading")]["chunk_text"]
    missed = [text for text in headings if not is_bare_heading(text)]
    assert missed == []


def test_labeled_chunks_are_not_flagged():
    """Labeled chunks are real sentences, so the filter should leave them in.
    The one exception is a lead-in that names no topic and was labeled NONE,
    exactly the kind of chunk the heading rule excludes, so dropping it is
    correct and costs nothing."""
    labels = pd.read_csv(os.path.join(LABELS_DIR, "eligibility_annotations.csv"))
    flagged = [text for text in labels["chunk_text"] if is_bare_heading(text)]
    assert flagged == ["Specifically, the workshop is intended for those who:"]


# --- chunk_requirements ---------------------------------------------------------


def test_chunks_carry_the_heading_they_sit_under():
    chunks = chunk_requirements(
        "Who can apply? Artists under 35. Who may not apply? Students."
    )
    assert [(c.text, c.is_heading, c.heading) for c in chunks] == [
        ("Who can apply?", True, None),
        ("Artists under 35.", False, "Who can apply?"),
        ("Who may not apply?", True, "Who can apply?"),
        ("Students.", False, "Who may not apply?"),
    ]


def test_nul_bytes_become_spaces():
    """A NUL byte in the source ("You\\x00are ...") made CSV readers truncate the
    sentence to "You"; chunk_requirements replaces it, keeping the same split."""
    chunks = chunk_requirements("Open to all. You\x00are based in Norway.")
    assert [c.text for c in chunks] == ["Open to all.", "You are based in Norway."]
