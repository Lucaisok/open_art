"""
OpenArt — the eligibility engine: can this artist apply to this call, and why?

    engine = EligibilityEngine()                 # loads the two files below once
    verdict = engine.evaluate(profile, opportunity)

Plain, deterministic Python (CLAUDE.md): no model and no LLM at request time.
It reads
  data/processed/eligibility_constraints.jsonl        every sentence of every call, classified at
                                                      ingestion (scripts/extract_constraints.py): one
                                                      row per (sentence, label), since a sentence can
                                                      state several requirements
  dataset/labels/eligibility_constraints_reviewed.csv the reviewed polarity + value of every
                                                      (sentence, label) that may reject (workflow.MD, step 4b)

Three verdicts (decision 1, workflow.MD):
  LIKELY_NOT_ELIGIBLE  at least one certain fail; shown, never hidden, with the quoted sentence
  CHECK                nothing certain fails, but something needs the artist's own reading
  ELIGIBLE             "nothing in this call rules you out" (the classifier can miss a sentence)
                       A call with no requirement sentence at all is CHECK, not ELIGIBLE.

Asymmetric on purpose: a wrong "not eligible" hides a real opportunity, a
wrong "check" costs a minute. So a sentence can only FAIL when it has a
confirm/fix review row for its current class AND the profile field it needs is
filled; anything else becomes CHECK, quoting the sentence. (Since step 6b the
review, which also confirms the class, replaces the 0.7 confidence gate.)

How one (sentence, label) row is read (in this order). A sentence with two labels gives two
items, each judged on its own: "over 18 ... and reside in Senegal" can PASS on age and FAIL on
residence.
  heading, NONE                 ignored (a NONE flagged by the safety net -> CHECK)
  polarity WAIVES               NO_RESTRICTION ("no restriction on age")
  DISCIPLINE                    PASS if a REQUIRES sentence names one of the artist's disciplines
                                (src/eligibility/disciplines.py), else CHECK; never FAIL
  CAREER_STAGE, EDUCATION,      CHECK: never verified automatically
  PRIOR_FUNDING,
  OTHER_ELIGIBILITY
  AGE, NATIONALITY, RESIDENCE,  CHECK unless reviewed (confirm / fix); then the reviewed value
  APPLICANT_TYPE,               names a set S of artists and the polarity says S is required or
  STUDENT_STATUS                excluded. With "also_requires" the real set is only part of S:
                                  REQUIRES + outside S -> FAIL     inside S -> CHECK
                                  EXCLUDES + inside S  -> CHECK    outside S -> PASS

How sentences combine: consecutive sentences of the same class (a reject class
or DISCIPLINE) are an OR group ("• Individuals • Organisations"), and so is a run of adjacent NATIONALITY /
RESIDENCE sentences ("citizens of X" / "or residents of Y"). Only items of the same class family are
chained: in "• Citizens of X • Over 18 and residents of Y" the two geo items group, the age item stands
alone. Labels of ONE sentence never group with each other (they are all required), except a nationality +
residence pair, which ingestion already merges into one item (src/eligibility/readings.py). A group:
  FAIL   if every sentence in it fails for certain;
  PASS   if every EXCLUDES sentence in it passes (misses the artist) and, when it states any
         requirement, the artist meets one of them. So a stated exclusion that hits the artist is
         never overruled, and "not excluded" alone never counts as meeting an alternative;
  CHECK  otherwise.
"""

import csv
import json
import os
from datetime import date
from typing import Literal

from pydantic import BaseModel

from src.eligibility.career import career_check, education_check, parse_career, parse_education
from src.eligibility.disciplines import discipline_match, disciplines_named, excluded_disciplines, narrowing_word
from src.eligibility.languages import languages_check, parse_languages
from src.eligibility.study import parse_study, study_check
from src.eligibility.geo import BROAD_REGIONS, broad_regions_named, describe_countries
from src.eligibility.polarity import polarity as parse_polarity
from src.eligibility.scope import APPLICANT, WIDENING, scope as sentence_scope
from src.eligibility.values import parse_value
from src.eligibility.profile import ArtistProfile
from src.eligibility.safety_net import keyword_hits
from src.models.classified_chunk import ClassifiedChunk
from src.models.processed_opportunity import ProcessedOpportunity

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONSTRAINTS_PATH = os.path.join(REPO_ROOT, "data", "processed", "eligibility_constraints.jsonl")
REVIEWED_PATH = os.path.join(REPO_ROOT, "dataset", "labels", "eligibility_constraints_reviewed.csv")

# the classes a reviewed sentence may reject on (also used by scripts/review_queue.py,
# so the review queue and the engine always agree on what needs a review)
REJECT_CLASSES = {"AGE", "NATIONALITY", "RESIDENCE", "APPLICANT_TYPE", "STUDENT_STATUS"}
CHECK_ONLY_CLASSES = {"DISCIPLINE", "CAREER_STAGE", "EDUCATION", "PRIOR_FUNDING", "OTHER_ELIGIBILITY"}
# classes whose adjacent sentences form OR groups (DISCIPLINE: lists like "• visual arts • literature")
GROUPED_CLASSES = REJECT_CLASSES | {"DISCIPLINE"}
GEO_LABELS = ("NATIONALITY", "RESIDENCE")

TOPIC = {
    "AGE": "age", "NATIONALITY": "nationality", "RESIDENCE": "residence",
    "APPLICANT_TYPE": "applicant type", "STUDENT_STATUS": "student status",
    "DISCIPLINE": "discipline", "CAREER_STAGE": "career stage", "EDUCATION": "education",
    "PRIOR_FUNDING": "prior funding", "OTHER_ELIGIBILITY": "other conditions",
    "LANGUAGE": "language",  # not a classifier label: read from any sentence by src/eligibility/languages.py
}

# what the artist should look for in a CHECK-only sentence
CHECK_ONLY_HINT = {
    "DISCIPLINE": "read it and make sure your discipline fits",
    "CAREER_STAGE": "the app compares years of practice and words like emerging / established with your profile, "
                    "but couldn't read this one; read it and make sure your career stage fits",
    "EDUCATION": "the app compares a required degree with your profile, but couldn't read this one; "
                 "read it and compare it with your studies",
    "PRIOR_FUNDING": "read it and compare it with grants or prizes you have had",
    "OTHER_ELIGIBILITY": "read it and make sure you meet this condition",
}

# INFO: a sentence that isn't about who can apply (scope, src/eligibility/scope.py); shown apart, never counted
Outcome = Literal["PASS", "FAIL", "CHECK", "NO_RESTRICTION", "INFO"]
Status = Literal["ELIGIBLE", "CHECK", "LIKELY_NOT_ELIGIBLE"]


class Review(BaseModel):
    """One row of eligibility_constraints_reviewed.csv (only the columns the engine uses)."""
    label: str
    decision: str              # confirm / fix / drop
    polarity: str | None       # final polarity; None on a drop
    value: dict | None         # final value; None on a drop
    reason: str | None
    scope: str = APPLICANT     # ANNOTATION_GUIDELINES.md §10: only APPLICANT reviews count
    applies_to: list[str] = [] # the applicant types the condition concerns; [] = everyone


class Item(BaseModel):
    """One sentence the engine found, with what it means for this artist."""
    chunk_id: str
    chunk_index: int
    text: str                  # quoted verbatim in every reason shown to the artist
    label: str                 # requirement class (the safety net's suspected class for a flagged NONE)
    confidence: float | None
    polarity: str | None
    outcome: Outcome
    reason: str
    scope: str = APPLICANT     # ANNOTATION_GUIDELINES.md §9; anything else has outcome INFO or NO_RESTRICTION
    review: str | None = None  # the review decision this outcome rests on, if any
    # why a CHECK is a check (None otherwise): safety_net, check_only_class, discipline_mismatch, not_reviewed,
    # dropped, unreadable, narrower_set (also_requires), missing_profile_field, uncertain_match
    check_kind: str | None = None
    group: int | None = None   # set when the sentence is part of an OR group of 2+
    group_outcome: Outcome | None = None


class Verdict(BaseModel):
    opportunity_id: str
    title: str | None
    source_url: str | None     # always linked, so the artist can read the call itself
    status: Status
    summary: str
    items: list[Item]          # every sentence found, in call order, including passes

    @property
    def deciding_items(self) -> list[Item]:
        """The items behind the status: the fails for LIKELY_NOT_ELIGIBLE, the checks for CHECK."""
        wanted = {"LIKELY_NOT_ELIGIBLE": "FAIL", "CHECK": "CHECK"}.get(self.status)
        return [item for item in self.items if _effective(item) == wanted]


# -- loading ---------------------------------------------------------------------------------------------

def load_constraints(path: str = CONSTRAINTS_PATH) -> dict[str, list[ClassifiedChunk]]:
    """opportunity_id -> its chunks, in call order."""
    by_opportunity: dict[str, list[ClassifiedChunk]] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            chunk = ClassifiedChunk.model_validate_json(line)
            by_opportunity.setdefault(chunk.opportunity_id, []).append(chunk)
    for chunks in by_opportunity.values():
        chunks.sort(key=lambda c: c.chunk_index)
    return by_opportunity


def load_reviews(path: str = REVIEWED_PATH) -> dict[tuple[str, str], Review]:
    """(sentence text, label) -> its review. Keyed by text, not chunk id, so it survives corpus
    rebuilds; and by label, since one sentence can hold several requirements, each reviewed apart."""
    reviews = {}
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            reviews[(row["chunk_text"], row["label"])] = Review(
                label=row["label"], decision=row["decision"],
                polarity=row["polarity"] or None,
                value=json.loads(row["value"]) if row["value"] else None,
                reason=row["reason"] or None,
                scope=row.get("scope") or APPLICANT,
                applies_to=json.loads(row["applies_to"]) if row.get("applies_to") else [],
            )
    return reviews


# -- does the artist belong to the set S a reviewed value names? ------------------------------------------
# Each returns (True / False / None, what the profile says). None = can't tell -> CHECK.

def _age_on(birth: date, day: date) -> int:
    return day.year - birth.year - ((day.month, day.day) < (birth.month, birth.day))


def _reference_dates(deadline: date | None, today: date) -> list[tuple[date, str]]:
    """The dates an age or a graduation year is checked on. A call usually counts it "at the time of
    application", i.e. some day between today and the deadline, so a result is only certain if it holds
    on both. A deadline already passed leaves only the deadline."""
    if deadline is None:
        return [(today, "today")]
    if deadline < today:
        return [(deadline, f"on the deadline ({deadline})")]
    return [(today, "today"), (deadline, f"on the deadline ({deadline})")]


def _all_or_nothing(results: list[bool | None]) -> bool | None:
    """True if every date says True, False if every date says False, else None."""
    if all(r is True for r in results):
        return True
    if all(r is False for r in results):
        return False
    return None


def _age_membership(value: dict, profile: ArtistProfile, dates, deadline_known: bool):
    if profile.birth_date is None:
        return None, "your birth date is not in your profile"
    low, high = value.get("min_age", 0), value.get("max_age", 999)
    ages = [_age_on(profile.birth_date, day) for day, _ in dates]
    detail = "you are " + " and ".join(f"{age} {when}" for age, (_, when) in zip(ages, dates))
    inside = _all_or_nothing([low <= age <= high for age in ages])
    if inside is False and not deadline_known and all(age < low for age in ages):
        # too young today, but with no known deadline they may be old enough when they apply
        return None, detail + "; the deadline is unknown, so you may reach the minimum age in time"
    return inside, detail


def _country_membership(label: str, value: dict, profile: ArtistProfile):
    countries = set(value.get("countries", []))
    residence = [profile.residence_country] if profile.residence_country else []
    if value.get("nationality_or_residence"):
        fields = [("nationality", profile.nationalities), ("residence", residence)]
    elif label == "NATIONALITY":
        fields = [("nationality", profile.nationalities)]
    else:
        fields = [("residence", residence)]
    detail = "; ".join(f"your {name}: {', '.join(codes) or 'not in your profile'}" for name, codes in fields)
    if any(code in countries for _, codes in fields for code in codes):
        return True, detail
    # a broad region ("and across Europe") can let the artist in, never keep them out (step 5)
    broad = {code for region in value.get("broad_regions", []) for code in BROAD_REGIONS.get(region, [])}
    if any(code in broad for _, codes in fields for code in codes):
        return True, detail
    if all(codes for _, codes in fields) and not value.get("broad_regions"):
        return False, detail
    return None, detail


def _applicant_type_membership(value: dict, profile: ArtistProfile):
    if profile.applicant_type is None:
        return None, "your applicant type (individual / group / organisation) is not in your profile"
    return profile.applicant_type in value.get("types", []), f"you apply as: {profile.applicant_type}"


def _student_membership(value: dict, profile: ArtistProfile, dates):
    if "graduated_within_years" in value:
        years = value["graduated_within_years"]
        if profile.graduation_year is None:
            return None, "your graduation year is not in your profile"

        def within(day: date) -> bool | None:
            # only the year is known: a difference of exactly `years` could go either way
            since = day.year - profile.graduation_year
            if since < 0 or since == years:
                return None
            return since < years

        inside = _all_or_nothing([within(day) for day, _ in dates])
        detail = f"you graduated in {profile.graduation_year}"
        if inside and value.get("institutions"):
            # "graduated from Villa Arson less than 3 years ago": the school must match too; no match is a check
            met, reason = study_check({"institutions": value["institutions"]}, profile.education)
            return (True if met else None), f"{detail}; {reason}"
        return inside, detail
    if profile.currently_enrolled is None:
        return None, "whether you are currently enrolled is not in your profile"
    return profile.currently_enrolled, "you are " + ("" if profile.currently_enrolled else "not ") + "currently enrolled"


def _membership(label: str, value: dict, profile: ArtistProfile, deadline: date | None, today: date):
    if "any_of" in value:
        # alternatives (§10): in if the artist meets any one, out only if they certainly meet none.
        # An alternative with also_requires can't be certain either way when the artist is inside it.
        results = []
        for alternative in value["any_of"]:
            alt_label = alternative.get("label", label)
            inside, detail = _membership(alt_label, alternative, profile, deadline, today)
            if inside and alternative.get("also_requires"):
                inside = None
            results.append((inside, detail))
        details = "; ".join(dict.fromkeys(detail for _, detail in results))
        if any(inside is True for inside, _ in results):
            return True, details
        if all(inside is False for inside, _ in results):
            return False, details
        return None, details
    if label == "EDUCATION" and any(key in value for key in ("institutions", "study_places", "study_countries")):
        # where the artist studied: a match lets them in; no match is never certain (a CV can omit a school)
        met, reason = study_check(value, profile.education)
        return (True if met else None), reason
    if label not in REJECT_CLASSES:
        # an alternative the profile can't check ("a studio in Ghent"): never certain either way
        return None, f"{TOPIC[label]}: {value.get('also_requires', 'not checked')}"
    dates = _reference_dates(deadline, today)
    if label == "AGE":
        return _age_membership(value, profile, dates, deadline is not None)
    if label in ("NATIONALITY", "RESIDENCE"):
        return _country_membership(label, value, profile)
    if label == "APPLICANT_TYPE":
        return _applicant_type_membership(value, profile)
    return _student_membership(value, profile, dates)


def _describe(label: str, value: dict) -> str:
    """The set S in words, e.g. 'age 18-34', 'residence in NO, SE'."""
    if "any_of" in value:
        return " or ".join(_describe(alt.get("label", label), alt) for alt in value["any_of"])
    if label == "EDUCATION" and (where := value.get("institutions") or value.get("study_places")
                                 or value.get("study_countries")):
        shown = describe_countries(where) if where is value.get("study_countries") else " or ".join(where)
        return f"studies at / in {shown}"
    if label not in REJECT_CLASSES:
        # an alternative the profile can't check: say what it is ("a studio or gallerist in Ghent")
        return value.get("also_requires") or TOPIC.get(label, label.lower())
    if label == "AGE":
        low, high = value.get("min_age"), value.get("max_age")
        if low is not None and high is not None:
            return f"age {low}-{high}"
        return f"age {low} or over" if low is not None else f"age {high} or under"
    if label in ("NATIONALITY", "RESIDENCE"):
        codes = value.get("countries", [])
        shown = describe_countries(codes)
        topic = "nationality or residence" if value.get("nationality_or_residence") else TOPIC[label]
        regions = value.get("broad_regions", [])
        return f"{topic} in " + ", ".join(([shown] if codes else []) + regions)
    if label == "APPLICANT_TYPE":
        return "applicants of type " + " / ".join(value.get("types", []))
    if "graduated_within_years" in value:
        school = f" from {' or '.join(value['institutions'])}" if value.get("institutions") else ""
        return f"a graduation{school} within the last {value['graduated_within_years']} years"
    return "applicants currently enrolled as students"


# -- one sentence ----------------------------------------------------------------------------------------

def _item(chunk: ClassifiedChunk, label: str, outcome: Outcome, reason: str, **extra) -> Item:
    return Item(chunk_id=chunk.chunk_id, chunk_index=chunk.chunk_index, text=chunk.text, label=label,
                confidence=chunk.confidence, polarity=chunk.polarity, outcome=outcome, reason=reason, **extra)


def find_review(reviews: dict[tuple[str, str], Review], text: str, label: str) -> Review | None:
    """The review of this requirement. A nationality / residence sentence counts as reviewed under either
    geo label: ingestion keeps one of the two (src/eligibility/readings.py), and the reviewed value says
    which field(s) it checks ("nationality_or_residence"), so the review applies whichever was kept."""
    review = reviews.get((text, label))
    if review is None and label in GEO_LABELS:
        other = next(geo for geo in GEO_LABELS if geo != label)
        review = reviews.get((text, other))
    return review


def _discipline_reason(text: str, disciplines: list[str]) -> str:
    """Why a discipline sentence that doesn't match the artist is a CHECK, in the artist's terms."""
    yours = ", ".join(disciplines)
    if word := narrowing_word(text):
        return f'asks for a specific role or kind of applicant ("{word}"), not only a discipline; ' \
               f"check whether you fit (your disciplines: {yours})"
    named = disciplines_named(text)
    if named:
        asked = ", ".join(f'{canonical} ("{words}")' for canonical, words in named)
        return f"asks for {asked}; your disciplines: {yours}. Not among them, unless your practice also covers it"
    return f"names a field the app can't match to a discipline; read it to check whether your work ({yours}) fits"


def _assess_discipline(chunk: ClassifiedChunk, profile: ArtistProfile) -> Item:
    """A discipline sentence against the disciplines in the artist's profile (the Practice pills).
    It can PASS or be a CHECK, never FAIL: the term table can't be sure enough to reject."""
    label = "DISCIPLINE"
    if not profile.disciplines:
        return _item(chunk, label, "CHECK", "your disciplines are not in your profile; check that yours fits",
                     check_kind="missing_profile_field")
    yours = ", ".join(profile.disciplines)
    # "all sectors except audiovisual": a pass when the artist has a discipline that isn't left out
    # (they can apply with that one), a check otherwise; never a fail
    if (excluded := excluded_disciplines(chunk.text)) is not None:
        if open_ := [d for d in profile.disciplines if d not in excluded and d != "Other/Non-Arts"]:
            return _item(chunk, label, "PASS", f"open to every discipline except {', '.join(sorted(excluded))}; "
                         f"yours include {', '.join(open_)}")
        return _item(chunk, label, "CHECK", f"open to every discipline except {', '.join(sorted(excluded))}; "
                     f"your disciplines: {yours}", check_kind="discipline_mismatch")
    if chunk.polarity == "REQUIRES":
        if match := discipline_match(chunk.text, profile.disciplines):
            return _item(chunk, label, "PASS", f'names your discipline ({match[0]}: "{match[1]}")')
        # no match: say what the sentence asks for
        return _item(chunk, label, "CHECK", _discipline_reason(chunk.text, profile.disciplines),
                     check_kind="discipline_mismatch")
    # any other polarity (EXCLUDES, UNCLEAR): name the artist's disciplines, so the check is concrete
    return _item(chunk, label, "CHECK", f"the app can't check this for you: read it and make sure your "
                 f"disciplines ({yours}) fit", check_kind="discipline_mismatch")


# what a sentence that isn't about who can apply means for the artist (scope, step 1)
SCOPE_REASON = {
    "OBLIGATION": "what the selected artist will have to do, not a condition to apply",
    "PROJECT": "about the project, not about who can apply",
    "PREFERENCE": "a preference, not a condition",
    "NOT_A_CONDITION": "not a condition on who can apply",
}


def _scope_item(chunk: ClassifiedChunk, label: str, found: str) -> Item | None:
    """The item for a sentence whose scope isn't APPLICANT; None when it is about the applicant."""
    if found == APPLICANT:
        return None
    if found == WIDENING:
        reason = ("open to artists at any stage of their career" if label == "CAREER_STAGE"
                  else "opens the call wider; it doesn't limit who can apply")
        return _item(chunk, label, "NO_RESTRICTION", reason, scope=found)
    return _item(chunk, label, "INFO", SCOPE_REASON[found], scope=found)


def _reviewed_scope(reviews: dict[tuple[str, str], Review], text: str) -> str | None:
    """The scope a reviewer gave this sentence under any of its labels, or None if it has no review.
    A non-APPLICANT scope under one label wins over APPLICANT under another: the reviewer who read the
    sentence for its scope decided it isn't about the applicant."""
    scopes = {review.scope for label in REJECT_CLASSES if (review := reviews.get((text, label))) is not None}
    if not scopes:
        return None
    others = sorted(scopes - {APPLICANT})
    return others[0] if others else APPLICANT


def _met_in_favour(chunk: ClassifiedChunk, label: str, profile: ArtistProfile,
                   deadline: date | None, today: date) -> Item | None:
    """A PASS for an unreviewed sentence whose condition the profile clearly meets, else None (step 5).
    Only ever resolves in the artist's favour: whatever isn't clearly met stays a CHECK, never a FAIL.
    The sentence must state one requirement only (no keyword of another class), since only that one
    is checked."""
    topics = {name for name in keyword_hits(chunk.text) if name != "GENERIC"}
    if topics - {label}:
        return None
    direction = parse_polarity(chunk.text, chunk.heading, label)
    if direction != "REQUIRES":
        return None
    if label == "DISCIPLINE":
        if match := discipline_match(chunk.text, profile.disciplines):
            return _item(chunk, label, "PASS", f'names your discipline ({match[0]}: "{match[1]}")')
        return None
    if label in ("CAREER_STAGE", "EDUCATION"):
        check = career_check if label == "CAREER_STAGE" else education_check
        parse = parse_career if label == "CAREER_STAGE" else parse_education
        value = parse(chunk.text)
        met, reason = check(value, profile)
        return _item(chunk, label, "PASS", reason) if value is not None and met else None
    if label not in REJECT_CLASSES:
        return None
    value = chunk.value if chunk.label == label and chunk.value else parse_value(label, chunk.text)
    if value is None and label in GEO_LABELS and (regions := broad_regions_named(chunk.text)):
        value = {"countries": [], "broad_regions": regions}
    if not value or value.get("also_requires"):
        return None
    inside, detail = _membership(label, value, profile, deadline, today)
    if inside is True:
        return _item(chunk, label, "PASS", f"requires {_describe(label, value)}; {detail}")
    return None


def _language_item(chunk: ClassifiedChunk, profile: ArtistProfile) -> Item | None:
    """A "Language" item for a sentence that asks the applicant for a language skill, else None.
    PASS when the artist works in the language(s), otherwise a CHECK; never a FAIL (levels are worded
    too loosely to reject on)."""
    value = parse_languages(chunk.text)
    if value is None:
        return None
    met, reason = languages_check(value, profile.languages)
    if met:
        return _item(chunk, "LANGUAGE", "PASS", reason)
    kind = "missing_profile_field" if "not in your profile" in reason else "uncertain_match"
    return _item(chunk, "LANGUAGE", "CHECK", reason, check_kind=kind)


def _assess_check_only(chunk: ClassifiedChunk, label: str, profile: ArtistProfile) -> Item:
    """CAREER_STAGE and EDUCATION are compared with the profile (step 3): PASS when clearly met,
    otherwise a CHECK that says what the call asks. An OTHER_ELIGIBILITY sentence asking for a language
    becomes a "Language" item. PRIOR_FUNDING and the other OTHER_ELIGIBILITY stay a check."""
    if label == "OTHER_ELIGIBILITY" and (item := _language_item(chunk, profile)):
        return item
    if label == "EDUCATION" and chunk.polarity == "REQUIRES" and parse_education(chunk.text) is None \
            and (study := parse_study(chunk.text)) is not None:
        # where the artist studied ("at a Flemish or Brussels Conservatoire"): a pass or a specific check
        met, reason = study_check(study, profile.education)
        kind = "missing_profile_field" if "not in your profile" in reason else "uncertain_match"
        return _item(chunk, label, "PASS", reason) if met else _item(chunk, label, "CHECK", reason, check_kind=kind)
    if label in ("CAREER_STAGE", "EDUCATION") and chunk.polarity == "REQUIRES":
        check = career_check if label == "CAREER_STAGE" else education_check
        value = (parse_career if label == "CAREER_STAGE" else parse_education)(chunk.text)
        met, reason = check(value, profile)
        if met:
            return _item(chunk, label, "PASS", reason)
        if value is not None:
            kind = "missing_profile_field" if "not in your profile" in reason else "uncertain_match"
            return _item(chunk, label, "CHECK", reason, check_kind=kind)
    hint = CHECK_ONLY_HINT[label]
    reason = hint if label in ("CAREER_STAGE", "EDUCATION") else f"the app can't check this for you: {hint}"
    return _item(chunk, label, "CHECK", reason, check_kind="check_only_class")


def assess_chunk(chunk: ClassifiedChunk, profile: ArtistProfile, reviews: dict[tuple[str, str], Review],
                 deadline: date | None, today: date) -> Item | None:
    """What one sentence means for this artist; None if the engine ignores it."""
    if chunk.is_heading or chunk.label is None:
        return None
    if chunk.label == "NONE":
        if chunk.suspected_label is None:
            return None
        # the cue that raised the flag (chunk.safety_net_reason) stays in the data for audits, not in the text
        label = chunk.suspected_label
        return (_scope_item(chunk, label, sentence_scope(chunk.text, chunk.heading))
                or (label == "OTHER_ELIGIBILITY" and _language_item(chunk, profile))
                or _met_in_favour(chunk, label, profile, deadline, today)
                or _item(chunk, label, "CHECK", "this may be a condition on who can apply; read it",
                         check_kind="safety_net"))
    label = chunk.label
    if chunk.polarity == "WAIVES":
        return _item(chunk, label, "NO_RESTRICTION", f"no restriction on {TOPIC[label]}")
    review = find_review(reviews, chunk.text, label) if label in REJECT_CLASSES else None

    # scope belongs to the sentence, not to one of its labels (§9: one scope per sentence). A reviewer's
    # scope for any label of the sentence wins over the rules ("events cannot take place in the home city
    # of the applicant organisations": PROJECT under RESIDENCE, so also under OTHER_ELIGIBILITY)
    reviewed_scope = _reviewed_scope(reviews, chunk.text)
    if reviewed_scope is not None and (item := _scope_item(chunk, label, reviewed_scope)):
        return item
    # an unreviewed sentence: the scope rules decide whether it is about the applicant at all
    if review is None and reviewed_scope is None:
        found = sentence_scope(chunk.text, chunk.heading)
        # "both emerging and established artists are encouraged": soft wording, but open to every
        # career stage, so it is a widening of the career condition, not a preference to list apart
        if found == "PREFERENCE" and label == "CAREER_STAGE" and parse_career(chunk.text) == {"any_stage": True}:
            found = WIDENING
        if item := _scope_item(chunk, label, found):
            return item
    if label == "DISCIPLINE":
        return _assess_discipline(chunk, profile)
    if label in CHECK_ONLY_CLASSES:
        return _assess_check_only(chunk, label, profile)

    # a class the engine may reject on: only through a reviewed sentence
    if review is None:
        return (_met_in_favour(chunk, label, profile, deadline, today)
                or _item(chunk, label, "CHECK", f"may limit who can apply by {TOPIC[label]}; not checked yet, "
                         "read it", check_kind="not_reviewed"))
    label = review.label  # the same, or the other geo label (find_review)
    if review.scope != APPLICANT:
        return _scope_item(chunk, label, review.scope)
    if review.applies_to and profile.applicant_type and profile.applicant_type not in review.applies_to:
        return _item(chunk, label, "NO_RESTRICTION", f"only concerns applicants of type "
                     f"{' / '.join(review.applies_to)}; you apply as: {profile.applicant_type}",
                     review=review.decision)
    if review.decision == "drop":
        return _item(chunk, label, "CHECK", f"may limit who can apply by {TOPIC[label]}, but not in a way the app "
                     "can check" + (f" ({review.reason})" if review.reason else "") + "; read it",
                     review="drop", check_kind="dropped")
    if review.polarity not in ("REQUIRES", "EXCLUDES") or not review.value:
        return _item(chunk, label, "CHECK", f"limits who can apply by {TOPIC[label]}, but couldn't be checked "
                     "automatically; read it", review=review.decision, check_kind="unreadable")

    value, polarity = review.value, review.polarity
    inside, detail = _membership(label, value, profile, deadline, today)
    narrower = value.get("also_requires")
    described = _describe(label, value)
    verb = "requires" if polarity == "REQUIRES" else "excludes"
    kind = None
    if inside is None:
        outcome, reason = "CHECK", f"{verb} {described}; {detail}"
        # every "can't tell" from a missing field says so in its detail; the rest are date / year edge cases
        kind = "missing_profile_field" if "not in your profile" in detail else "uncertain_match"
    elif polarity == "REQUIRES":
        if not inside:
            outcome, reason = "FAIL", f"requires {described}; {detail}"
        elif narrower:
            outcome, reason = "CHECK", f"requires {described} and also: {narrower}; {detail}, check the rest"
            kind = "narrower_set"
        else:
            outcome, reason = "PASS", f"requires {described}; {detail}"
    else:  # EXCLUDES
        if not inside:
            outcome, reason = "PASS", f"excludes {described}; {detail}"
        elif narrower:
            outcome, reason = ("CHECK", f"excludes some {described} ({narrower}); {detail}, "
                               "check whether the exclusion covers you")
            kind = "narrower_set"
        else:
            outcome, reason = "FAIL", f"excludes {described}; {detail}"
    item = _item(chunk, label, outcome, reason, review=review.decision, check_kind=kind)
    item.polarity = polarity  # the reviewed polarity, which may differ from the parsed one
    return item


# -- combining sentences ---------------------------------------------------------------------------------

def _family(label: str) -> str:
    """Classes that form one OR group when adjacent: nationality and residence go together."""
    return "GEO" if label in ("NATIONALITY", "RESIDENCE") else label


def _group_outcome(items: list[Item]) -> Outcome:
    if all(item.outcome == "FAIL" for item in items):
        return "FAIL"
    exclusions = [item for item in items if item.polarity == "EXCLUDES"]
    alternatives = [item for item in items if item.polarity != "EXCLUDES"]
    # PASS needs every exclusion in the group to miss the artist, and (if the group states any
    # requirement) one requirement they meet. Merely not being excluded is not meeting an alternative:
    # "legal entities may apply" + "foundations with other funding are excluded" must not pass a person.
    if (all(item.outcome == "PASS" for item in exclusions)
            and (not alternatives or any(item.outcome == "PASS" for item in alternatives))):
        return "PASS"
    return "CHECK"


def form_or_groups(items: list[Item]) -> None:
    """Mark runs of adjacent same-class sentences (reject classes, DISCIPLINE) as OR groups.
    Each class family keeps its own run, so another label of the same sentence doesn't break it."""
    runs: list[list[Item]] = []
    open_run: dict[str, list[Item]] = {}  # family -> its latest run
    for item in items:
        if item.label not in GROUPED_CLASSES or item.outcome in ("NO_RESTRICTION", "INFO"):
            continue
        run = open_run.get(_family(item.label))
        if run is not None and item.chunk_index == run[-1].chunk_index + 1:
            run.append(item)
        else:
            run = [item]
            runs.append(run)
            open_run[_family(item.label)] = run
    for number, run in enumerate(r for r in runs if len(r) > 1):
        outcome = _group_outcome(run)
        for item in run:
            item.group, item.group_outcome = number, outcome


def _effective(item: Item) -> Outcome:
    """What an item contributes to the verdict: its group's outcome if it is in one."""
    return item.group_outcome or item.outcome


# -- the verdict -----------------------------------------------------------------------------------------

def _add_language_items(items: list[Item], chunks: list[ClassifiedChunk], profile: ArtistProfile,
                        reviews: dict[tuple[str, str], Review]) -> list[Item]:
    """A language requirement is read from every sentence, whatever the classifier called it ("Proficiency
    in German and/or English is required" is often labelled NONE, or AGE when it shares a sentence with an
    age limit). One "Language" item per sentence that doesn't have one yet, in call order. Sentences that
    aren't about the applicant (scope) and waivers are skipped."""
    covered = {item.chunk_id for item in items if item.label == "LANGUAGE" or item.outcome == "INFO"}
    added = list(items)
    for chunk in chunks:
        if chunk.is_heading or chunk.chunk_id in covered or chunk.polarity == "WAIVES":
            continue
        scope_found = _reviewed_scope(reviews, chunk.text) or sentence_scope(chunk.text, chunk.heading)
        if scope_found == APPLICANT and (item := _language_item(chunk, profile)):
            added.append(item)
        covered.add(chunk.chunk_id)
    # a NONE sentence the language reader picked up replaces nothing; keep everything in call order
    return sorted(added, key=lambda item: item.chunk_index)


def evaluate_chunks(profile: ArtistProfile, chunks: list[ClassifiedChunk], reviews: dict[tuple[str, str], Review], *,
                    opportunity_id: str, title: str | None = None, source_url: str | None = None,
                    deadline: date | None = None, today: date | None = None) -> Verdict:
    """The engine itself, on already-loaded chunks and reviews (what the tests call)."""
    today = today or date.today()
    chunks = sorted(chunks, key=lambda c: c.chunk_index)
    items = [item for chunk in chunks if (item := assess_chunk(chunk, profile, reviews, deadline, today)) is not None]
    items = _add_language_items(items, chunks, profile, reviews)
    form_or_groups(items)

    fails = [item for item in items if _effective(item) == "FAIL"]
    checks = [item for item in items if _effective(item) == "CHECK"]
    if fails:
        status: Status = "LIKELY_NOT_ELIGIBLE"
        summary = f'Likely not eligible: "{fails[0].text}" ({fails[0].reason}).'
        if len(fails) > 1:
            summary += f" {len(fails) - 1} more reason(s) below."
    elif checks:
        status = "CHECK"
        summary = f"Nothing found rules you out, but {len(checks)} point(s) need your own check before applying."
    elif all(item.outcome == "INFO" for item in items):
        # no requirement sentence at all (only project notes and obligations, if anything): usually the rules live elsewhere ("the range of applicants
        # is set out in the regulations"), so "nothing rules you out" would be a guess -> CHECK
        status = "CHECK"
        summary = "No eligibility requirements were found in this call; read it to check who can apply."
    else:
        status = "ELIGIBLE"
        summary = "Nothing in this call rules you out."
    return Verdict(opportunity_id=opportunity_id, title=title, source_url=source_url,
                   status=status, summary=summary, items=items)


class EligibilityEngine:
    """Loads the constraints and the reviews once; evaluate() is then pure Python, no I/O."""

    def __init__(self, constraints_path: str = CONSTRAINTS_PATH, reviewed_path: str = REVIEWED_PATH):
        self.chunks_by_opportunity = load_constraints(constraints_path)
        self.reviews = load_reviews(reviewed_path)

    def evaluate(self, profile: ArtistProfile, opportunity: ProcessedOpportunity,
                 today: date | None = None) -> Verdict:
        common = dict(opportunity_id=opportunity.id, title=opportunity.title_en, source_url=opportunity.source_url)
        if opportunity.id not in self.chunks_by_opportunity:
            # never classified (ingested after the last extract_constraints run): say so, don't guess
            return Verdict(**common, status="CHECK", items=[],
                           summary="This call has not been analysed yet; read it to check eligibility.")
        return evaluate_chunks(profile, self.chunks_by_opportunity[opportunity.id], self.reviews,
                               deadline=opportunity.deadline_date, today=today, **common)
