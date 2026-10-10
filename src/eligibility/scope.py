"""
OpenArt — scope of a requirement sentence: does it limit WHO can apply at all?
(ANNOTATION_GUIDELINES.md §9; workflow.MD, "Conclusive verdicts" step 1.)

The classifier gives the topic, polarity the direction; scope says whether the sentence is about the
applicant. Only APPLICANT sentences count toward the verdict. The others are shown to the artist
apart ("What you'd commit to", "About the project") and never make a call a CHECK:

  OBLIGATION       what a selected artist will have to do: "Participation must be in person for the
                   entire programme", "The selected artist will present their work"
  PROJECT          a condition on the project, its works, partners, events or budget: "Projects must
                   take place in Belgium", "Partners can include: charities"
  PREFERENCE       a wish or priority, not a limit: "Students with a minority background are encouraged"
  WIDENING         it only opens the call wider: "Group applications are accepted", "regardless of origin"
  NOT_A_CONDITION  a definition or a note: "X, Y, Z are considered Nordic countries in this context"
  APPLICANT        everything else

Plain rules, written from the 150 dev sentences of dataset/labels/scope/scope_sample.csv and scored
once on the 100 test sentences (scripts/evaluate_scope.py). They are tuned for precision: a wrong
non-applicant scope hides a real condition, a wrong APPLICANT only leaves a check. So any hard cue
about the applicant (a place, an exclusion, "only") keeps a sentence APPLICANT.

    scope("Participation in the lab sessions must be in person and for the entire duration.") -> "OBLIGATION"
    scope("Projects must take place in Belgium, unless they involve virtual collaboration.")  -> "PROJECT"
"""

import re

APPLICANT, PROJECT, OBLIGATION, PREFERENCE, WIDENING, NOT_A_CONDITION = (
    "APPLICANT", "PROJECT", "OBLIGATION", "PREFERENCE", "WIDENING", "NOT_A_CONDITION")
SCOPES = (APPLICANT, PROJECT, OBLIGATION, PREFERENCE, WIDENING, NOT_A_CONDITION)


def _re(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.IGNORECASE)


# a hard condition on the applicant: with one of these, a sentence stays APPLICANT whatever else it says
APPLICANT_CUE_RE = _re(
    r"\b(resid\w*(?<!residency)(?<!residencies)|citizen\w*|nationalit\w*|nationals?|passport|based in|living in|"
    r"live in|domiciled|registered (in|office)|born|aged?|years old|students?|graduat\w*|enrol\w*|"
    r"natural persons?|legal (entit|person)\w*|individuals?|collectives?|organi[sz]ations?|applicants?|applying)\b"
    r"|\b(only|exclusively|not eligible|ineligible|cannot apply|may not apply|can ?not apply|are excluded)\b")

# 1. after selection
OBLIGATION_RE = _re(
    r"\b(selected|chosen|successful|winning) (artists?|applicants?|candidates?|participants?|fellows?|residents?)\b"
    r".{0,80}\b(will|must|shall|are expected|is expected|agree)\b"
    r"|\b(grantees?|grant recipients?|award(ee|ed artist)s?|the artist-in-residence)\b.{0,40}\b(will|must|shall)\b"
    r"|\b(is|are) (obliged|expected|required) to (sign|attend|participate|take part|present|report|deliver|stay)"
    r"|\bin person (and )?for the (entire|whole|full) (duration|programme|program|period)"
    r"|\bmust (attend|participate in|take part in|submit a (final )?report|be present (during|at|for))"
    r"|^\W*(participate|take part|be present) in\b"
    r"|\byou will (design|organi[sz]e|work with|be part of|engage|deliver|lead|run|present|host|share)\b"
    r"|\bwe expect\b")

# 2. the project, its works, partners, events or budget as the subject
PROJECT_SUBJECT_RE = _re(
    r"^\W*(\w+:\s*)?(the |all |any |proposed |submitted |eligible |your )?"
    r"(projects?|works|artworks?|submissions?|translations?|concerts?|events?|performances?|productions?|"
    r"activities|partners?|partnerships?|the budget|budgets?|films?|publications?|books?|artworks?|"
    r"proposals?|co-productions?)\b(?! (by|from|of) (artists?|applicants?))"
    r"|\bmust be included in the budget\b"
    r"|\b(projects?|works?|concerts?|events?) (must|can|may|should|will) (take place|be (implemented|carried out|"
    r"presented|produced|realised|realized|shown|staged|held|suitable))")
PROJECT_HEADING_RE = _re(r"\b(partners? (can|may|must) include|artwork eligibility|project requirements|"
                         r"technical requirements|eligible (projects|costs|activities|works))\b")

# 3. soft wording
PREFERENCE_RE = _re(
    r"\b(are|is) (especially |particularly |strongly )?encouraged\b|\bwe encourage\b"
    r"|\b(especially|particularly) (welcome|encourage)\w*|\bpriority (will be|is|may be) given\b"
    r"|\b(should be submitted|is aimed) especially\b|\bwe (will )?value\b|\bplace (particular )?emphasis\b"
    r"|\bpreferabl\w*|\bpreference (will be|is) given\b|\bwe are (also |particularly )?interested in\b")

# 4. it only opens the call wider
WIDENING_RE = _re(
    r"\b(may|can) also (apply|be (accepted|eligible))|\b(are|is) also (eligible|accepted|welcome)\b"
    r"|\b(group|joint|collective) applications?( \([^)]*\))? (are|is) (also )?(accepted|possible|welcome)"
    r"|\bregardless of\b|\birrespective of\b|\bno (special |specific |particular )?(requirements?|restrictions?)\b"
    r"|\ball (artistic )?(disciplines|art forms) (are )?welcome|\bof all (stages|ages|backgrounds)\b"
    r"|\b(a )?wide range of\b|\bcan apply equally\b|\bcan be older than\b|\bwithout (the )?need\b"
    r"|\bthe exception is\b|\b(are|is) welcome to apply\b|\bas well as\b.{0,40}\bwelcome\b")
# a widening sentence that also narrows ("only", an exclusion) is APPLICANT
NARROWING_RE = _re(r"\b(only|exclusively|must|not eligible|ineligible|cannot|can ?not|may not|excluded|required|"
                   r"provided that|have (at least|benefited|been))\b")

# 5. definitions and notes
NOT_A_CONDITION_RE = _re(
    r"\b(are|is) (considered|understood|regarded|defined) (as|to)\b|\bin this context\b"
    r"|\bno legal (entitlement|right)\b|\btake a look at\b")


def scope(text: str, heading: str | None = None) -> str:
    """The §9 scope of one sentence (the heading it sits under helps with project lists)."""
    if NOT_A_CONDITION_RE.search(text) and not NARROWING_RE.search(text):
        return NOT_A_CONDITION
    if OBLIGATION_RE.search(text):
        return OBLIGATION
    # a heading like "Partners can include:" makes every item under it about the project
    if heading and PROJECT_HEADING_RE.search(heading):
        return PROJECT
    if not APPLICANT_CUE_RE.search(text) and PROJECT_SUBJECT_RE.search(text):
        return PROJECT
    if PREFERENCE_RE.search(text) and not NARROWING_RE.search(text):
        return PREFERENCE
    if WIDENING_RE.search(text) and not NARROWING_RE.search(text):
        return WIDENING
    return APPLICANT
