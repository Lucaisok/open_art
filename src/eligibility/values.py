"""
OpenArt — parse the VALUE of a requirement sentence: "under 35" -> max age
34, "resident in the Nordic Region" -> the 8 Nordic countries.

Plain rules only (decision 2, workflow.MD). Every parser follows one rule:
when in doubt, return None. A None value turns the requirement into a CHECK
item, which costs the artist a minute; a wrong value can reject them from an
opportunity they could have won.

Value formats (also in workflow.MD, step 4):
  AGE             {"min_age": int, "max_age": int}  inclusive, either may be absent
  NATIONALITY /   {"countries": [ISO codes]}, plus "nationality_or_residence": True
  RESIDENCE       when the sentence accepts either ("citizenship or residence in Bulgaria")
  APPLICANT_TYPE  {"types": [...]} from "individual", "group", "organisation"
  STUDENT_STATUS  {"enrolled": True} or {"graduated_within_years": N}
any class         "also_requires": a narrower condition the engine can't verify
                  ("North Rhine-Westphalia", "for at least three years")

The value names WHO the sentence is about; whether they are required or
excluded is the polarity's job (src/eligibility/polarity.py).

    parse_value("AGE", "Under 35 years old at the time of application.") -> {"max_age": 34}
"""

import re

from src.eligibility.geo import (
    COUNTRY_RE,
    LANGUAGES,
    NAME_TO_COUNTRY,
    REGION_LOOKUP,
    REGION_RE,
    SUBNATIONAL_LOOKUP,
    SUBNATIONAL_RE,
    VAGUE_REGION_RE,
)


def _re(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.IGNORECASE)


# small numbers are often spelled out ("less than three years ago")
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                "eight": 8, "nine": 9, "ten": 10}
NUMBER = r"(\d{1,2}|" + "|".join(NUMBER_WORDS) + r")"


def _number(text: str) -> int:
    return int(text) if text.isdigit() else NUMBER_WORDS[text.lower()]


def _normalize(text: str) -> str:
    """Unify dashes and apostrophes so the patterns stay short."""
    return text.replace("–", "-").replace("—", "-").replace("’", "'")


# --- AGE ------------------------------------------------------------------------

# an age that belongs to someone other than the applicant, or isn't a limit
NOT_APPLICANT_AGE_RE = _re(r"\b(learners|pupils|children|audiences?|visitors|average age|if you are under)\b")

# "between 25 and 40", "aged 14 to 21", "18-26 years"
AGE_RANGE_RE = _re(r"\b(?:between|aged)\s+(\d{1,2})\s*(?:-|to|and)\s*(\d{1,2})\b"
                   r"|\b(\d{1,2})\s*(?:-|to)\s*(\d{1,2})\s*(?:years|year-olds)")
AGE_UNDER_RE = _re(r"\b(?:under|below|younger than)\s+(?:the age of\s+)?(\d{1,2})\b")
AGE_MAX_RE = _re(r"\b(?:up to|maximum(?: age)?(?: of)?|max\.?|not older than|no older than)\s+(\d{1,2})\b"
                 r"|\b(\d{1,2})\s+(?:years old\s+)?(?:or younger|and under|or under)")
# "over 18" is read as "18 and over", the everyday meaning and the looser one
AGE_MIN_RE = _re(r"\b(?:over|older than|at least|minimum(?: age)?(?: of)?)\s+(?:the age of\s+)?(\d{1,2})\b"
                 r"|\b(\d{1,2})\s+(?:years\s+)?(?:and above|and over|or older|or over)|\baged\s+(\d{1,2})\s*\+")
LEGAL_AGE_RE = _re(r"\b(legal age|age of majority|full age)\b")


def parse_age(text: str) -> dict | None:
    text = _normalize(text)
    if NOT_APPLICANT_AGE_RE.search(text):
        return None
    # two different limits of the same kind ("artists under 30, as well as
    # choreographers under 40") apply to different people: no single value
    for pattern in (AGE_UNDER_RE, AGE_MAX_RE, AGE_MIN_RE):
        limits = {next(g for g in found.groups() if g) for found in pattern.finditer(text)}
        if len(limits) > 1:
            return None
    value = {}
    if found := AGE_RANGE_RE.search(text):
        low, high = [int(g) for g in found.groups() if g]
        value = {"min_age": low, "max_age": high}
    else:
        if found := AGE_UNDER_RE.search(text):
            value["max_age"] = int(found.group(1)) - 1
        elif found := AGE_MAX_RE.search(text):
            value["max_age"] = int(found.group(1) or found.group(2))
        if found := AGE_MIN_RE.search(text):
            value["min_age"] = int(next(g for g in found.groups() if g))
        elif LEGAL_AGE_RE.search(text):
            value["min_age"] = 18
    # sanity: a limit outside 0-99, or min above max, means a misread
    ages = list(value.values())
    if not value or any(not 0 < a < 100 for a in ages):
        return None
    if "min_age" in value and "max_age" in value and value["min_age"] > value["max_age"]:
        return None
    return value


# --- NATIONALITY / RESIDENCE ------------------------------------------------------

# "artists with a non-Dutch nationality": the sentence is about everyone
# EXCEPT that country, which a plain country list would turn upside down
# case-sensitive on purpose: "non-commercial" and "non-professional" are not countries
NON_COUNTRY_RE = re.compile(r"\bnon-[A-Z]")

# 1. a country only counts if the sentence says where someone lives, is
# based or registered, is a citizen of, or comes from. Without such a cue the
# country is context ("engage with the Belgian cultural landscape", "trips to
# countries outside the Nordic region"), not a requirement.
PLACE_CUE_RE = _re(
    # "resid" but not "residency": where the residency is held says nothing
    # about the applicant ("a residency program in Finland for artists")
    r"\b(resid(?!enc[yi])\w*|live|lives|living|based|domiciled|located|registered|active in|work(s|ing)? in"
    r"|career in|practi[cs]e in|activit(y|ies) in"
    r"|citizens?|citizenship|nationals?|nationality|passport holders?"
    r"|(artists?|applicants?|candidates?|persons?|people|participants?|organi[sz]ations?|individuals?"
    r"|institutions?|entities|groups?|collectives?) (from|of|in)\b)"
)
# ... or a demonym right before a person noun ("Belgian artists")
DEMONYM_PERSON_RE = re.compile(
    r"\b[A-Z][a-zé]+ (artists?|citizens?|nationals?|applicants?|authors?|creators?|musicians?|writers?"
    r"|curators?|designers?|filmmakers?|organi[sz]ations?|institutions?)\b")

# 3. a demonym used as a language: "French-speaking", "write in French"
# (only checked for names in geo.LANGUAGES, never for "resident in Belgium")
LANGUAGE_CONTEXT_RE = _re(r"(\b(in|into)\s+$)|(^[- ]?(speaking|language))")

# 4. citizenship OR residence in one sentence ("Bulgarian citizenship or the
# right of residence in Bulgaria"): the engine must accept either
NATIONALITY_CUE_RE = _re(r"\b(citizens?|citizenship|nationals?|nationality)\b")
RESIDENCE_CUE_RE = _re(r"\b(resid(?!enc[yi])\w*|live|lives|living|based|domiciled)\b")

# "translators living outside Lithuania", "any country other than Norway": a
# country list would turn these upside down
OUTSIDE_RE = _re(r"\b(outside|other than|apart from)\b")

DURATION_RE = _re(r"\bfor (at least|a minimum of|more than)\s+" + NUMBER + r"\s+(years?|months?)")


def parse_countries(text: str, label: str = "RESIDENCE") -> dict | None:
    text = _normalize(text)
    if NON_COUNTRY_RE.search(text):
        return None
    if not (PLACE_CUE_RE.search(text) or DEMONYM_PERSON_RE.search(text)):
        return None
    if OUTSIDE_RE.search(text):
        return None
    countries = set()
    also_requires = []

    # regions first, then blank them out so "Nordic Region (Denmark, ...)"
    # isn't counted twice and "European Union" isn't read as vague "European"
    for found in REGION_RE.finditer(text):
        countries.update(REGION_LOOKUP[found.group(0).lower()])
    rest = REGION_RE.sub(" ", text)
    for found in SUBNATIONAL_RE.finditer(rest):
        countries.add(SUBNATIONAL_LOOKUP[found.group(0).lower()])
        also_requires.append(found.group(0))
    rest = SUBNATIONAL_RE.sub(" ", rest)
    for found in COUNTRY_RE.finditer(rest):
        name = found.group(0).lower()
        before, after = rest[:found.start()], rest[found.end():]
        if name in LANGUAGES and (LANGUAGE_CONTEXT_RE.search(before[-6:]) or LANGUAGE_CONTEXT_RE.search(after[:10])):
            continue  # a language, not a country
        countries.add(NAME_TO_COUNTRY[found.group(0).lower()])

    # a vague region next to the countries ("from Ukraine and across Europe")
    # means the list is incomplete: rejecting on it could exclude eligible people
    if not countries or VAGUE_REGION_RE.search(rest):
        return None
    value = {"countries": sorted(countries)}
    if NATIONALITY_CUE_RE.search(text) and RESIDENCE_CUE_RE.search(text):
        value["nationality_or_residence"] = True
    if found := DURATION_RE.search(text):
        also_requires.append(found.group(0))
    if also_requires:
        value["also_requires"] = " / ".join(also_requires)
    return value


# --- APPLICANT_TYPE --------------------------------------------------------------

APPLICANT_TYPE_CUES = {
    "individual": _re(r"\b(individuals?|natural persons?|private persons?|self-employed|sole traders?)\b"),
    "group": _re(r"\b(groups?|collectives?|duos?|ensembles?)\b"),
    "organisation": _re(
        r"\b(organi[sz]ations?|institutions?|legal (entit(y|ies)|persons?)|entit(y|ies)|compan(y|ies)"
        r"|associations?|foundations?|enterprises?|municipalit(y|ies)|local authorit(y|ies)|schools?"
        r"|universit(y|ies)|publish(ers?|ing houses?)|galler(y|ies)|festivals?|venues?|non-profits?|NGOs?"
        r"|charit(y|ies)|units?)\b"),
}
# the sentence widens who may apply ("Group applications are also accepted")
# or sets a condition on some applicants, rather than listing who may apply
WIDENS_RE = _re(r"\b(also|accepted|welcome|possible|in order to apply)\b")
LEGAL_FORM_RE = _re(r"\b(legal forms?|registered|authori[sz]ation)\b")


def parse_applicant_type(text: str) -> dict | None:
    if WIDENS_RE.search(text):
        return None
    types = sorted(t for t, cue in APPLICANT_TYPE_CUES.items() if cue.search(text))
    if not types:
        return None
    value = {"types": types}
    if LEGAL_FORM_RE.search(text):
        value["also_requires"] = "legal form / registration"
    return value


# --- STUDENT_STATUS --------------------------------------------------------------

GRADUATED_WITHIN_RE = _re(r"\bgraduat\w*\b.*?\b(?:less than|within(?: the last)?|in the last|no more than)\s+"
                          + NUMBER + r"\s+years?")
ENROLLED_RE = _re(r"\b(students?|enrolled|enrolment|studying|study programmes?|educational (programs?|programmes?"
                  r"|institutions?)|undergraduates?|master'?s thesis)\b")
# alternatives inside one sentence ("pursuing a master's or have just
# graduated", "students, doctoral candidates, researchers"): no single value
ALTERNATIVE_RE = _re(r"\b(graduat\w*|researchers?)\b")
NARROWER_RE = _re(r"\b(bachelor'?s|master'?s|undergraduate|year of|relevant|thesis|semester|per ?cent|part-time"
                  r"|full-time)\b|%")


def parse_student_status(text: str) -> dict | None:
    text = _normalize(text)
    if found := GRADUATED_WITHIN_RE.search(text):
        value = {"graduated_within_years": _number(found.group(1))}
        # graduated from a named school, not from any school
        if re.search(r"\bgraduat\w* from\b", text, re.IGNORECASE):
            value["also_requires"] = "graduated from a named institution"
        return value
    if not ENROLLED_RE.search(text) or ALTERNATIVE_RE.search(text):
        return None
    value = {"enrolled": True}
    if NARROWER_RE.search(text):
        value["also_requires"] = "a specific level or programme"
    return value


# --- entry point -----------------------------------------------------------------

PARSERS = {
    "AGE": parse_age,
    "NATIONALITY": parse_countries,
    "RESIDENCE": parse_countries,
    "APPLICANT_TYPE": parse_applicant_type,
    "STUDENT_STATUS": parse_student_status,
}


# a preference, not a requirement ("students are encouraged to apply", "the
# grant is primarily for artists who live in Norway"): nothing to reject on
SOFT_RE = _re(r"\b(encouraged|especially|particularly|in particular|priority|prioriti[sz]\w*|preference"
              r"|preferably|primarily|mainly|welcome[ds]?)\b")


# a permission, not a limit ("the leader can be older than 45", "group
# portraits are permitted"): it widens who may apply, so nothing to reject on
# ("may be provided to entities", "may be applied for by individuals" are
# passive verbs naming who may apply, not permissions, so they don't count)
PERMISSION_RE = _re(r"\b(can|may) be (?!(provided|applied|submitted|awarded|granted|given|used|made|paid)\b)"
                    r"|\b(permitted|allowed|depending on)\b")


def parse_value(label: str, text: str) -> dict | None:
    """The value of a requirement sentence of class `label`, or None if the
    class has no parser (DISCIPLINE, PRIOR_FUNDING, ...), the wording is soft,
    or the text can't be parsed with confidence."""
    parser = PARSERS.get(label)
    if parser is None or SOFT_RE.search(text) or PERMISSION_RE.search(text):
        return None
    return parser(text) if label not in ("NATIONALITY", "RESIDENCE") else parser(text, label)
