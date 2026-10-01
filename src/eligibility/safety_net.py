"""
OpenArt — safety net for requirement sentences the classifier labels NONE.

About 1 in 10 real requirement sentences gets labeled NONE (out-of-fold, see
workflow.MD, "Step 2b"). The engine never sees those, so the artist could get
a wrong ELIGIBLE. This module turns a NONE sentence into a CHECK item when
either plain rule fires:

  1. keyword:    the sentence contains a strong eligibility cue
                 ("citizen", "based in", "students", "must be", ...)
  2. runner-up:  the model was torn: some requirement class got
                 probability >= RUNNER_UP_THRESHOLD

Chosen 2026-10-01 from the step 2b measurement ("keyword OR runner-up >= 0.3"):
catches about half of all misses (all STUDENT_STATUS / EDUCATION misses, 82%
of NATIONALITY) for ~0.6 extra CHECK items per opportunity.

    flag_missed_requirement("Open to artists based in Ukraine.", {"NONE": 0.86, "RESIDENCE": 0.05, ...})
    -> SafetyNetFlag(suspected_label="RESIDENCE", reason='keyword "based in"')
"""

import re
from dataclasses import dataclass

RUNNER_UP_THRESHOLD = 0.3

# one cue list per class, so a keyword hit also says which requirement the
# sentence probably is. \b on the left only, so stems match longer forms.
# GENERIC cues signal "this is a requirement" without naming a topic.
# Written from the class definitions in ANNOTATION_GUIDELINES.md before the
# step 2b measurement, not tuned on its results.
KEYWORD_CUES = {
    # "resid" but not "residency/residencies": almost every call in this corpus is one
    "RESIDENCE": r"\b(resid(?!enc[yi])|based in|living in|live and work|lives and works|located in)",
    "NATIONALITY": r"\b(citizen|nationalit|nationals?\b|passport)",
    "AGE": r"\b(aged?\b|years old|under (the age of )?\d|over (the age of )?\d|born (in|after|before)|age limit)",
    "STUDENT_STATUS": r"\b(students?\b|enrol|graduat|alumni|currently studying)",
    "EDUCATION": r"\b(degree|diploma|bachelor|master[’']?s\b|qualification)",
    "CAREER_STAGE": r"\b(emerging|early[- ]career|mid[- ]career|established artist|years of (professional )?experience)",
    "APPLICANT_TYPE": r"\b(individuals?\b|organi[sz]ations?\b|legal (entit|person)|natural person|collectives?\b)",
    "PRIOR_FUNDING": r"\b(previously (received|funded|awarded)|already (received|been awarded)|prior (funding|grant))",
    "GENERIC": r"\b(eligib|open to|can apply|may apply|cannot apply|may not apply|must be|must have)",
}
KEYWORD_RES = {name: re.compile(pattern, re.IGNORECASE) for name, pattern in KEYWORD_CUES.items()}


@dataclass
class SafetyNetFlag:
    suspected_label: str  # the requirement class this sentence probably is
    reason: str           # why it was flagged, shown to the artist / in audits


def keyword_hits(text: str) -> dict[str, str]:
    """Cue list name -> the words that matched, for every cue list that matches."""
    hits = {}
    for name, cue in KEYWORD_RES.items():
        found = cue.search(text)
        if found:
            hits[name] = found.group(0)
    return hits


def runner_up(probabilities: dict[str, float]) -> tuple[str, float]:
    """The most likely class other than NONE, and its probability."""
    return max(((label, p) for label, p in probabilities.items() if label != "NONE"), key=lambda item: item[1])


def flag_missed_requirement(text: str, probabilities: dict[str, float]) -> SafetyNetFlag | None:
    """For a chunk the classifier labeled NONE: return a flag if it may be a
    requirement after all, else None."""
    hits = keyword_hits(text)
    runner_label, runner_p = runner_up(probabilities)

    # a topic cue names the likely class; otherwise trust the model's runner-up
    topic_hits = {name: words for name, words in hits.items() if name != "GENERIC"}
    if topic_hits:
        # if several topic cues match, prefer the one the model rates highest
        label = max(topic_hits, key=lambda name: probabilities.get(name, 0.0))
        return SafetyNetFlag(suspected_label=label, reason=f'keyword "{topic_hits[label]}"')
    if "GENERIC" in hits:
        return SafetyNetFlag(suspected_label=runner_label, reason=f'keyword "{hits["GENERIC"]}"')
    if runner_p >= RUNNER_UP_THRESHOLD:
        return SafetyNetFlag(suspected_label=runner_label,
                             reason=f"classifier unsure: {runner_label} at {runner_p:.2f}")
    return None
