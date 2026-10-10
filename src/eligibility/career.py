"""
OpenArt — read a CAREER_STAGE or EDUCATION sentence and compare it with the profile
(workflow.MD, "Conclusive verdicts" step 3).

These classes never reject: a sentence can only PASS when the profile clearly meets it, otherwise
it stays a CHECK, now with a reason that says what the call asks and what the profile says. A wrong
PASS costs the artist a read of the call; a wrong FAIL would hide a call they could win.

Career stage, two kinds of sentence:
  years   "at least 3 years of professional practice", "no more than 4 years", "1-4 years"
          -> {"min_years": 3} / {"max_years": 4}, compared with profile.years_active
  stage   "emerging", "at the beginning of their career", "established", "professional"
          -> {"stages": [...]}: the CANONICAL_CAREER_STAGES the sentence accepts,
          compared with profile.career_stage
Education:
  "a degree", "a bachelor's / master's", "higher education in the arts"
          -> {"degree": True}, compared with profile.has_degree

    parse_career("Applicants must have at least three years of professional practice.") -> {"min_years": 3}
    parse_career("This call is aimed at emerging artists.") -> {"stages": ["Emerging/Early-Career"]}
"""

import re

from src.eligibility.profile import ArtistProfile


def _re(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.IGNORECASE)


NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                "nine": 9, "ten": 10, "fifteen": 15, "twenty": 20}
NUMBER = r"(\d{1,2}|" + "|".join(NUMBER_WORDS) + r")"


def _number(text: str) -> int:
    return int(text) if text.isdigit() else NUMBER_WORDS[text.lower()]


# the years are about the artist's own practice, not about an organisation or a past degree
PRACTICE_RE = _re(r"\b(professional|practi[cs]\w*|active|activity|experience|working|worked|career|producing)\b")
NOT_PRACTICE_RE = _re(r"\b(exist\w*|organi[sz]ations?|enterprises?|entit(y|ies)|centres?|institutions?|"
                      r"in the past|since (graduat|complet)\w*|after completing|older than)\b")

MIN_YEARS_RE = _re(r"\b(?:at least|a minimum of|minimum|more than|over)\s+" + NUMBER + r"\s*\+?\s*years?"
                   r"|\b" + NUMBER + r"\s*\+?\s*years?\s+or more")
MAX_YEARS_RE = _re(r"\b(?:no more than|not more than|up to|at most|maximum of|less than)\s+" + NUMBER + r"\s+years?"
                   r"|\b" + NUMBER + r"\s+years\s+maximum")
RANGE_RE = _re(r"\b(?:at least\s+)?" + NUMBER + r"\s*(?:-|–|to|and no more than)\s*" + NUMBER + r"\s*\+?\s*years?")

# stage words -> the canonical stages that clearly meet them
EMERGING_RE = _re(r"\b(emerging|early[- ]career|beginning of (their|your|an?) (artistic )?career|start of (their|your|an?) "
                  r"(artistic )?career|young (artists?|professionals?)|newcomers?|first steps)\b")
ESTABLISHED_RE = _re(r"\b(established (artists?|practitioners?)|long-standing|solid professional career|"
                     r"national reputation|(already )?received (public )?recognition|renowned|acclaimed|"
                     r"significant (body of work|track record))\b")
PROFESSIONAL_RE = _re(r"\bprofessional(ly)?\b|\btrack record\b|\b(demonstrable|demonstratable|proven) experience\b")
# the sentence is open to every stage ("from amateurs to professionals", "at any stage of their career")
ANY_STAGE_RE = _re(r"\b(any|all|every) (stages?|levels?) (of|in) (their|your|the)? ?career|\bamateurs?\b.{0,40}\bprofessionals?\b"
                   r"|\bregardless of (career|experience|level)|\b(emerging|early[- ]career)\b.{0,40}\b(established|mid[- ]career)\b")

DEGREE_RE = _re(r"\b(degrees?|bachelor\w*|master[’']?s?|diplomas?|higher education|university education|"
                r"art (school|academy) education|graduated from|completed (their|your|an?) (artistic |art )?"
                r"(studies|education|training))\b")
# a degree in a field, at a level or from a place the profile doesn't hold: only "has a degree" is checkable
DEGREE_DETAIL_RE = _re(r"\b(phd|doctor\w*|in (the field of )?(fine arts|visual arts|music|architecture|design|"
                       r"\w+ studies)|from (a|an|the) \w+|recogni[sz]ed|accredited|equivalent)\b")


def parse_career(text: str) -> dict | None:
    """The career condition a sentence states, or None when it can't be read safely."""
    if ANY_STAGE_RE.search(text):
        return {"any_stage": True}
    if PRACTICE_RE.search(text) and not NOT_PRACTICE_RE.search(text):
        if found := RANGE_RE.search(text):
            return {"min_years": _number(found.group(1)), "max_years": _number(found.group(2))}
        value = {}
        if found := MIN_YEARS_RE.search(text):
            value["min_years"] = _number(found.group(1) or found.group(2))
        if found := MAX_YEARS_RE.search(text):
            value["max_years"] = _number(found.group(1) or found.group(2))
        if value:
            return value
    if re.search(r"\byears?\b", text, re.IGNORECASE):
        return None  # a number of years we couldn't read: never guess a stage from the words around it
    if EMERGING_RE.search(text) and ESTABLISHED_RE.search(text):
        return {"any_stage": True}
    if EMERGING_RE.search(text):
        return {"stages": ["Emerging/Early-Career"]}
    if ESTABLISHED_RE.search(text):
        return {"stages": ["Established/Professional"]}
    if PROFESSIONAL_RE.search(text):
        # "professional artists": a mid-career or established artist clearly is one
        return {"stages": ["Mid-Career", "Established/Professional"]}
    return None


def parse_education(text: str) -> dict | None:
    if DEGREE_RE.search(text) and not DEGREE_DETAIL_RE.search(text):
        return {"degree": True}
    return None


def career_check(value: dict | None, profile: ArtistProfile) -> tuple[bool, str]:
    """(clearly met, the reason shown). Not met is never a fail: the caller turns it into a CHECK."""
    if value is None:
        return False, "the app can't read this condition; read it and make sure your career stage fits"
    if value.get("any_stage"):
        return True, "open to artists at any stage of their career"
    if "stages" in value:
        asked = " or ".join(stage.split("/")[0].lower() for stage in value["stages"])
        if profile.career_stage is None:
            return False, f"asks for {asked} artists; your career stage is not in your profile"
        if profile.career_stage in value["stages"]:
            return True, f"asks for {asked} artists; your profile says {profile.career_stage}"
        return False, f"asks for {asked} artists; your profile says {profile.career_stage}, check whether you fit"
    low, high = value.get("min_years"), value.get("max_years")
    asked = (f"{low}-{high} years of practice" if low is not None and high is not None
             else f"at least {low} years of practice" if low is not None else f"at most {high} years of practice")
    if profile.years_active is None:
        return False, f"asks for {asked}; your years of practice are not in your profile"
    years = profile.years_active
    # years_active is a whole number: exactly on a limit can go either way, so it isn't "clearly met"
    met = (low is None or years > low) and (high is None or years < high)
    detail = f"asks for {asked}; you have been active for {years} years"
    return met, detail if met else detail + ", check whether you fit"


def education_check(value: dict | None, profile: ArtistProfile) -> tuple[bool, str]:
    if value is None:
        return False, "the app can't check this for you: read it and compare it with your studies"
    if profile.has_degree is None:
        return False, "asks for a degree; whether you have one is not in your profile"
    if profile.has_degree:
        return True, "asks for a degree; your profile says you have one"
    return False, "asks for a degree; your profile says you have none, check whether an equivalent counts"
