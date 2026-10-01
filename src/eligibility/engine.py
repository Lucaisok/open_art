"""
OpenArt — the eligibility engine: can this artist apply to this call, and why?

    engine = EligibilityEngine()                 # loads the two files below once
    verdict = engine.evaluate(profile, opportunity)

Plain, deterministic Python (CLAUDE.md): no model and no LLM at request time.
It reads
  data/processed/eligibility_constraints.jsonl        every sentence of every call, classified at
                                                      ingestion (scripts/extract_constraints.py)
  dataset/labels/eligibility_constraints_reviewed.csv the reviewed polarity + value of every sentence
                                                      that may reject (workflow.MD, step 4b)

Three verdicts (decision 1, workflow.MD):
  LIKELY_NOT_ELIGIBLE  at least one certain fail; shown, never hidden, with the quoted sentence
  CHECK                nothing certain fails, but something needs the artist's own reading
  ELIGIBLE             "nothing in this call rules you out" (the classifier can miss a sentence)

Asymmetric on purpose: a wrong "not eligible" hides a real opportunity, a
wrong "check" costs a minute. So a sentence can only FAIL when it has a
confirm/fix review row AND the profile field it needs is filled; anything else
becomes CHECK, quoting the sentence.

How one sentence is read (in this order):
  heading, NONE                 ignored (a NONE flagged by the safety net -> CHECK)
  polarity WAIVES               NO_RESTRICTION ("no restriction on age")
  DISCIPLINE, CAREER_STAGE,     CHECK: never verified automatically
  EDUCATION, PRIOR_FUNDING,
  OTHER_ELIGIBILITY
  AGE, NATIONALITY, RESIDENCE,  CHECK unless reviewed (confirm / fix); then the reviewed value
  APPLICANT_TYPE,               names a set S of artists and the polarity says S is required or
  STUDENT_STATUS                excluded. With "also_requires" the real set is only part of S:
                                  REQUIRES + outside S -> FAIL     inside S -> CHECK
                                  EXCLUDES + inside S  -> CHECK    outside S -> PASS

How sentences combine: consecutive sentences of the same class are an OR group
("• Individuals • Organisations"), and so is a run of adjacent NATIONALITY /
RESIDENCE sentences ("citizens of X" / "or residents of Y"). A group:
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

from src.eligibility.profile import ArtistProfile
from src.models.classified_chunk import ClassifiedChunk
from src.models.processed_opportunity import ProcessedOpportunity

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONSTRAINTS_PATH = os.path.join(REPO_ROOT, "data", "processed", "eligibility_constraints.jsonl")
REVIEWED_PATH = os.path.join(REPO_ROOT, "dataset", "labels", "eligibility_constraints_reviewed.csv")

# the gate a sentence must pass before it may reject (also used by scripts/review_queue.py,
# so the review queue and the engine always agree on what needs a review)
REJECT_CLASSES = {"AGE", "NATIONALITY", "RESIDENCE", "APPLICANT_TYPE", "STUDENT_STATUS"}
REJECT_CONFIDENCE = 0.7
CHECK_ONLY_CLASSES = {"DISCIPLINE", "CAREER_STAGE", "EDUCATION", "PRIOR_FUNDING", "OTHER_ELIGIBILITY"}

TOPIC = {
    "AGE": "age", "NATIONALITY": "nationality", "RESIDENCE": "residence",
    "APPLICANT_TYPE": "applicant type", "STUDENT_STATUS": "student status",
    "DISCIPLINE": "discipline", "CAREER_STAGE": "career stage", "EDUCATION": "education",
    "PRIOR_FUNDING": "prior funding", "OTHER_ELIGIBILITY": "other conditions",
}

# what the artist should look for in a CHECK-only sentence
CHECK_ONLY_HINT = {
    "DISCIPLINE": "check that your discipline fits",
    "CAREER_STAGE": "check that your career stage fits",
    "EDUCATION": "check your education against this",
    "PRIOR_FUNDING": "check your past funding against this rule",
    "OTHER_ELIGIBILITY": "check this condition",
}

Outcome = Literal["PASS", "FAIL", "CHECK", "NO_RESTRICTION"]
Status = Literal["ELIGIBLE", "CHECK", "LIKELY_NOT_ELIGIBLE"]


class Review(BaseModel):
    """One row of eligibility_constraints_reviewed.csv (only the columns the engine uses)."""
    label: str
    decision: str              # confirm / fix / drop
    polarity: str | None       # final polarity; None on a drop
    value: dict | None         # final value; None on a drop
    reason: str | None


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
    review: str | None = None  # the review decision this outcome rests on, if any
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


def load_reviews(path: str = REVIEWED_PATH) -> dict[str, Review]:
    """sentence text -> its review (the file is keyed by text, so it survives corpus rebuilds)."""
    reviews = {}
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            reviews[row["chunk_text"]] = Review(
                label=row["label"], decision=row["decision"],
                polarity=row["polarity"] or None,
                value=json.loads(row["value"]) if row["value"] else None,
                reason=row["reason"] or None,
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
    if all(codes for _, codes in fields):
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

        return _all_or_nothing([within(day) for day, _ in dates]), f"you graduated in {profile.graduation_year}"
    if profile.currently_enrolled is None:
        return None, "whether you are currently enrolled is not in your profile"
    return profile.currently_enrolled, "you are " + ("" if profile.currently_enrolled else "not ") + "currently enrolled"


def _membership(label: str, value: dict, profile: ArtistProfile, deadline: date | None, today: date):
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
    if label == "AGE":
        low, high = value.get("min_age"), value.get("max_age")
        if low is not None and high is not None:
            return f"age {low}-{high}"
        return f"age {low} or over" if low is not None else f"age {high} or under"
    if label in ("NATIONALITY", "RESIDENCE"):
        codes = sorted(value.get("countries", []))
        shown = ", ".join(codes) if len(codes) <= 8 else ", ".join(codes[:8]) + f", … ({len(codes)} countries)"
        topic = "nationality or residence" if value.get("nationality_or_residence") else TOPIC[label]
        return f"{topic} in {shown}"
    if label == "APPLICANT_TYPE":
        return "applicants of type " + " / ".join(value.get("types", []))
    if "graduated_within_years" in value:
        return f"a graduation within the last {value['graduated_within_years']} years"
    return "applicants currently enrolled as students"


# -- one sentence ----------------------------------------------------------------------------------------

def _item(chunk: ClassifiedChunk, label: str, outcome: Outcome, reason: str, **extra) -> Item:
    return Item(chunk_id=chunk.chunk_id, chunk_index=chunk.chunk_index, text=chunk.text, label=label,
                confidence=chunk.confidence, polarity=chunk.polarity, outcome=outcome, reason=reason, **extra)


def assess_chunk(chunk: ClassifiedChunk, profile: ArtistProfile, reviews: dict[str, Review],
                 deadline: date | None, today: date) -> Item | None:
    """What one sentence means for this artist; None if the engine ignores it."""
    if chunk.is_heading or chunk.label is None:
        return None
    if chunk.label == "NONE":
        if chunk.suspected_label is None:
            return None
        return _item(chunk, chunk.suspected_label, "CHECK",
                     f"may be a {TOPIC[chunk.suspected_label]} requirement the classifier missed "
                     f"({chunk.safety_net_reason}); read it")
    label = chunk.label
    if chunk.polarity == "WAIVES":
        return _item(chunk, label, "NO_RESTRICTION", f"no restriction on {TOPIC[label]}")
    if label in CHECK_ONLY_CLASSES:
        return _item(chunk, label, "CHECK", f"{TOPIC[label]} is not verified automatically; {CHECK_ONLY_HINT[label]}")

    # a class the engine may reject on: only through a reviewed sentence
    review = reviews.get(chunk.text)
    if review is None or review.label != label:
        return _item(chunk, label, "CHECK", f"{TOPIC[label]} requirement not reviewed yet; read it")
    if chunk.confidence is None or chunk.confidence < REJECT_CONFIDENCE:
        return _item(chunk, label, "CHECK", f"the classifier is unsure this is about {TOPIC[label]}; read it",
                     review=review.decision)
    if review.decision == "drop":
        return _item(chunk, label, "CHECK", f"reviewed: not a strict {TOPIC[label]} restriction"
                     + (f" ({review.reason})" if review.reason else "") + "; read it", review="drop")
    if review.polarity not in ("REQUIRES", "EXCLUDES") or not review.value:
        return _item(chunk, label, "CHECK", f"{TOPIC[label]} requirement could not be read; read it",
                     review=review.decision)

    value, polarity = review.value, review.polarity
    inside, detail = _membership(label, value, profile, deadline, today)
    narrower = value.get("also_requires")
    described = _describe(label, value)
    verb = "requires" if polarity == "REQUIRES" else "excludes"
    if inside is None:
        outcome, reason = "CHECK", f"{verb} {described}; {detail}"
    elif polarity == "REQUIRES":
        if not inside:
            outcome, reason = "FAIL", f"requires {described}; {detail}"
        elif narrower:
            outcome, reason = "CHECK", f"requires {described} and also: {narrower}; {detail}, check the rest"
        else:
            outcome, reason = "PASS", f"requires {described}; {detail}"
    else:  # EXCLUDES
        if not inside:
            outcome, reason = "PASS", f"excludes {described}; {detail}"
        elif narrower:
            outcome, reason = ("CHECK", f"excludes some {described} ({narrower}); {detail}, "
                               "check whether the exclusion covers you")
        else:
            outcome, reason = "FAIL", f"excludes {described}; {detail}"
    item = _item(chunk, label, outcome, reason, review=review.decision)
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
    """Mark runs of adjacent same-class sentences (classes the engine may reject on) as OR groups."""
    runs: list[list[Item]] = []
    for item in items:
        if item.label not in REJECT_CLASSES or item.outcome == "NO_RESTRICTION":
            continue
        previous = runs[-1][-1] if runs else None
        if (previous is not None and item.chunk_index == previous.chunk_index + 1
                and _family(item.label) == _family(previous.label)):
            runs[-1].append(item)
        else:
            runs.append([item])
    for number, run in enumerate(r for r in runs if len(r) > 1):
        outcome = _group_outcome(run)
        for item in run:
            item.group, item.group_outcome = number, outcome


def _effective(item: Item) -> Outcome:
    """What an item contributes to the verdict: its group's outcome if it is in one."""
    return item.group_outcome or item.outcome


# -- the verdict -----------------------------------------------------------------------------------------

def evaluate_chunks(profile: ArtistProfile, chunks: list[ClassifiedChunk], reviews: dict[str, Review], *,
                    opportunity_id: str, title: str | None = None, source_url: str | None = None,
                    deadline: date | None = None, today: date | None = None) -> Verdict:
    """The engine itself, on already-loaded chunks and reviews (what the tests call)."""
    today = today or date.today()
    items = [item for chunk in sorted(chunks, key=lambda c: c.chunk_index)
             if (item := assess_chunk(chunk, profile, reviews, deadline, today)) is not None]
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
    else:
        status = "ELIGIBLE"
        summary = "Nothing in this call rules you out." if items else (
            "No eligibility requirements were found in this call; read it to be sure.")
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
