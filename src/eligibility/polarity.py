"""
OpenArt — polarity of a requirement sentence: does it say who CAN apply, who
CANNOT, or that a criterion does NOT apply?

The classifier gives the topic only: "Students are not eligible" and "Open to
students" are both STUDENT_STATUS. The engine also needs the direction, or it
would reject exactly the wrong people. Plain rules, checked in this order:

  WAIVES    the sentence lifts its own criterion: "There is no age limit"
            (AGE), "you do not need to be a Nordic citizen" (NATIONALITY).
            The engine skips it.
  EXCLUDES  the sentence names who is NOT eligible: "Students are not
            eligible", "Legal entities cannot apply", or any sentence listed
            under a negative heading such as "Who may not apply?".
  UNCLEAR   mixed, hedged or conditional: an exclusion next to a positive
            requirement ("must be ... and must not be ..."), "normally",
            "as long as", "excluding ...". The engine turns it into a
            CHECK item, never a reject.
  REQUIRES  everything else: the sentence states who can apply.

A waiver only counts for the sentence's own class: "emerging artists of any
age" (CAREER_STAGE) waives age but still REQUIRES an early career stage.

ANNOTATION_GUIDELINES.md marks only exclusions (`excludes`); a waiver is
`excludes = False` there (2026-09-24 entry), so WAIVES can't be checked
against the labels and is reviewed by hand instead (workflow.MD, step 3).

    polarity("Students are not eligible.")                     -> "EXCLUDES"
    polarity("Students.", heading="Who may not apply?")         -> "EXCLUDES"
    polarity("There is no age limit.", label="AGE")             -> "WAIVES"
    polarity("Emerging artists of any age.", label="CAREER_STAGE") -> "REQUIRES"
"""

import re

REQUIRES, EXCLUDES, WAIVES, UNCLEAR = "REQUIRES", "EXCLUDES", "WAIVES", "UNCLEAR"


def _re(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.IGNORECASE)


# --- waivers: "there is no limit on this criterion" ---------------------------
# Each waiver names the class it lifts; None = it lifts whatever the
# sentence is about ("there are no requirements regarding ...").
WAIVERS = [
    ("AGE", _re(r"\bno (upper |lower )?age (limit|restriction|criteri\w*)|\bnot age[- ]limited"
                r"|\b(of|at) any age|\bof all ages|\b(regardless|irrespective) of (their )?age")),
    ("NATIONALITY", _re(r"\b(do|does|need) not (need|have) to (be|hold) [\w ]{0,30}?(citizen|national)"
                        r"|\b(regardless|irrespective) of (their )?(nationality|citizenship)"
                        r"|\b(of|from) all (backgrounds and )?nationalities|\b(any|every) nationality")),
    ("RESIDENCE", _re(r"\b(regardless|irrespective) of (where they live|(their )?(place of )?residence)")),
    (None, _re(r"\bno (specific )?(requirements?|restrictions?|criteri\w*)\b"
               r"|\b(is|are) not (required|necessary|a requirement)"
               r"|\b(do|does|need) not (need|have) to\b")),
]

# --- exclusions: "these people are not eligible" ------------------------------
EXCLUSION_RE = _re(
    r"\bnot eligible|\bineligible|\bnot be eligible"
    r"|\bcannot\b|\bcan ?not\b|\bcan[’']t\b|\bmay not\b|\bmust not\b|\bshall not\b"
    r"|\bnot (be )?(accepted|considered|allowed|permitted|admitted|open to|awarded|funded|supported)"
    r"|\bexclud|\bexclusion"
    r"|\bdo(es)? not (accept|fund|support|provide|award|hold|have|cover)"
    r"|\bshould (instead|rather) apply|\bapply (instead|elsewhere)"
)

# negations that are not about who may apply; removed before looking for
# exclusions ("include but are not limited to", "income cannot exceed /
# must not be higher than", "we can't provide accommodation"). A value cap is
# a requirement on the value (step 4), not an exclusion of a group.
NOT_AN_EXCLUSION_RE = _re(
    r"\bnot limited to"
    r"|\b(cannot|can ?not|must not|may not|should not|shall not) (exceed|be (higher|more|greater) than)"
    # "we can't provide accommodation" is about the host, not the applicant,
    # unlike "we cannot support applications from ..."
    r"|\bwe (cannot|can ?not|can[’']t) (provide|offer|pay|cover|reimburse|guarantee)"
)

# softeners: the rule may have exceptions, so the engine must not reject on it
# ("generally" is left out: it mostly appears in "generally beneficial services")
HEDGE_RE = _re(r"\b(normally|usually|in principle|as a rule|in exceptional cases|exceptionally|preferably)\b")

# softeners that make a rule conditional ("does not need to be resident, as
# long as ..."), and carve-outs inside a requirement ("from at least 3
# countries, excluding the applicant's own"): both UNCLEAR
CONDITION_RE = _re(r"\b(as long as|provided that|on condition that|excluding|except)\b")

# a positive requirement in the same sentence ("must be of legal age ... and
# must not be subject to prohibitions"). With an exclusion or a topic-less
# waiver next to it, the sentence is mixed, so UNCLEAR: reading it as a pure
# exclusion would reject exactly the people it asks for.
# ("should instead apply" is an exclusion cue, not a requirement)
REQUIREMENT_CUE_RE = _re(r"\b(must|should)\b(?!\s+(not|instead|rather))|\b(is|are) open to|\b(is|are) eligible")

# a heading that announces a list of exclusions ("Who may not apply?",
# "Ineligible applicants", "What cannot receive funding?")
NEGATIVE_HEADING_RE = _re(r"\b(not|cannot|ineligib|exclu)")


def polarity(text: str, heading: str | None = None, label: str | None = None) -> str:
    """REQUIRES / EXCLUDES / WAIVES / UNCLEAR for one requirement sentence.

    heading  the bare heading the sentence sits under, if any (Chunk.heading)
    label    the sentence's class; a waiver of another class is ignored. With
             no label, every waiver counts."""
    # 1. find waivers of this sentence's own class, and blank out every waiver
    #    phrase so "do NOT need to" isn't read as an exclusion further down
    own_waiver = False      # a waiver of this sentence's class was found
    generic_waiver = False  # ... and it was a topic-less one ("no requirements")
    rest = text
    for waived_class, waiver_re in WAIVERS:
        if not waiver_re.search(rest):
            continue
        if waived_class is None or label is None or waived_class == label:
            own_waiver = True
            generic_waiver = generic_waiver or waived_class is None
        rest = waiver_re.sub(" ", rest)
    rest = NOT_AN_EXCLUSION_RE.sub(" ", rest)
    exclusion = EXCLUSION_RE.search(rest)

    # 2. decide
    if own_waiver and exclusion:
        return UNCLEAR
    if HEDGE_RE.search(rest) or CONDITION_RE.search(rest):
        return UNCLEAR
    if own_waiver:
        return UNCLEAR if generic_waiver and REQUIREMENT_CUE_RE.search(rest) else WAIVES
    if exclusion:
        return UNCLEAR if REQUIREMENT_CUE_RE.search(rest) else EXCLUDES
    if heading and NEGATIVE_HEADING_RE.search(heading):
        return EXCLUDES
    return REQUIRES
