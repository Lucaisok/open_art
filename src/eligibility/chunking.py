"""
OpenArt — split an opportunity's requirements text into sentence chunks.

This is the ONE splitter used everywhere: by the annotation scripts that built
the RQ1 training data and by the eligibility engine in the product. Sharing it
matters because the classifier only works on input that looks like what it was
trained on: same sentence boundaries, and no bare headings (see below).

    chunk_requirements("Who can apply? Artists under 35. Students are not eligible.")
    -> Chunk(0, "Who can apply?", is_heading=True,  heading=None)
       Chunk(1, "Artists under 35.", is_heading=False, heading="Who can apply?")
       Chunk(2, "Students are not eligible.", is_heading=False, heading="Who can apply?")
"""

import re
from dataclasses import dataclass

# --- Sentence splitting (ANNOTATION_GUIDELINES.md §1) ---------------------------
# Moved verbatim from scripts/select_annotation_candidates.py: chunk_id
# "<opportunity_id>_<n>" in the labels means "the n-th chunk this splitter
# returns", so changing these regexes would silently break that link.

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


# --- Bare headings (ANNOTATION_GUIDELINES.md, 2026-09-29 entry) -----------------
# "Who can apply?", "Eligible applicants", "We are looking for" are section
# titles that the splitter cuts out as if they were sentences. They were
# removed from the training data (they taught the model that "apply" /
# "eligible" means NONE), so the product must not classify them either.
#
# A word count alone can't spot them: many real constraints are short too
# ("Ukrainian citizens", "or residents of Norway"). So a chunk is a bare
# heading only if ALL of these hold:
#   1. it is short (at most MAX_HEADING_WORDS words);
#   2. it is shaped like a title: ends in "?", ":" or "!", or has no final
#      punctuation at all (a real sentence usually ends in "." or ";");
#   3. it contains a heading cue word (who, eligible, apply, ...);
#   4. it names no constraint topic (citizen, student, age, ...): a lead-in
#      like "Applications are open to students who:" states a topic, keeps
#      its label in the training data, and so must reach the classifier.

MAX_HEADING_WORDS = 10

# \b on the left only, so a stem also matches its longer forms
# ("eligib" -> eligible, eligibility; "requirement" -> requirements).
# "who" counts only in question/lead-in forms ("Who can apply?", "for those
# who:"): list items like "Who are French-speaking and write in French" are
# real constraints and must not be dropped.
HEADING_CUE_RE = re.compile(
    r"\b(who\s+(?:may|can|cannot|is it)|who[’']s|those who|for whom"
    r"|what|eligib|ineligib|requirement|criteri|apply|looking for"
    r"|attention|include|is it for)",
    re.IGNORECASE,
)

TOPIC_WORD_RE = re.compile(
    r"\b("
    r"citizen|national|passport|resid|live|living|based"       # NATIONALITY / RESIDENCE
    r"|age\b|aged|born|old\b|young"                             # AGE
    r"|student|enrol|study|studies|graduat|degree|diploma"      # STUDENT_STATUS / EDUCATION
    r"|bachelor|master|educat|universit|academ|school"
    r"|emerging|established|professional|experience|years"     # CAREER_STAGE
    r"|individual|person|natural|legal|entit|organi[sz]ation"   # APPLICANT_TYPE
    r"|institution|compan|collective|group"
    r")",
    re.IGNORECASE,
)


def is_bare_heading(chunk: str) -> bool:
    """True if the chunk is a section title that names no constraint topic
    (rules 1-4 above). Such chunks are skipped by the classifier."""
    text = chunk.strip()
    if len(text.split()) > MAX_HEADING_WORDS:
        return False
    looks_like_title = text.endswith(("?", ":", "!")) or not text.endswith((".", ";"))
    return (
        looks_like_title
        and HEADING_CUE_RE.search(text) is not None
        and TOPIC_WORD_RE.search(text) is None
    )


# --- Chunks for the engine ----------------------------------------------------


@dataclass
class Chunk:
    index: int             # position in split_into_chunks(), same n as in chunk_id
    text: str
    is_heading: bool       # bare heading: kept for context, never classified
    heading: str | None    # nearest bare heading above this chunk, if any


def chunk_requirements(text: str) -> list[Chunk]:
    """Split requirements text into chunks, flag bare headings, and attach to
    every chunk the heading it sits under.

    Headings are kept rather than thrown away because they can carry meaning
    the sentence itself lacks: under "Who may not apply?", "Students." is an
    exclusion. The polarity rule (engine step 3) reads `heading` for that."""
    chunks = []
    current_heading = None
    for index, sentence in enumerate(split_into_chunks(text)):
        heading_here = is_bare_heading(sentence)
        chunks.append(Chunk(
            index=index,
            text=sentence,
            is_heading=heading_here,
            # a heading's own `heading` is the one above it, not itself
            heading=current_heading,
        ))
        if heading_here:
            current_heading = sentence
    return chunks
