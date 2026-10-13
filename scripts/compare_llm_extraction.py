"""
OpenArt — would one GPT call that returns structured requirements beat the eligibility pipeline?
(workflow.MD, "LLM extraction vs the classifier pipeline", 2026-10-13)

The question came from an outside suggestion: let GPT return each call's requirements as structured
data, compare them with the profile in Python, and drop the classifier. Four ways to reach a verdict
are scored on the gold verdicts, with the same numbers as scripts/measure_verdicts.py:

  pipeline, reviewed     today's engine: classifier + reviewed values (what the corpus has)
  pipeline, no review    today's engine on a NEW call, before anyone reviews it
  GPT alone              GPT's requirements, run through the real engine as if reviewed
  agreement              the classifier's sentences, where GPT found the same requirement in the same
                         sentence (same label): GPT's value counts as the review; elsewhere unreviewed

Two gold samples:
  live      engine_gold_verdicts_live.csv: the prompt and the converter were adjusted on its errors
  unseen    the step 6, fresh and blind sets, minus any call in the live set: never looked at while tuning

GPT answers are cached in notebooks/cache/llm_requirements.jsonl (one line per call), so a re-run
costs nothing; a call missing from the cache is asked once (gpt-5.4-mini, needs OPENAI_API_KEY).

Usage: uv run --env-file .env python scripts/compare_llm_extraction.py
"""

import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

import pandas as pd
from openai import OpenAI
from pydantic import BaseModel

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(REPO_ROOT)
sys.path.append(os.path.join(REPO_ROOT, "scripts"))

from evaluate_engine import (  # noqa: E402
    BLIND_GOLD_PATH, FRESH_GOLD_PATH, GOLD_PATH, LIVE_GOLD_PATH, PERSONAS, TODAY, load_opportunities)

from src.eligibility.engine import EligibilityEngine, Review, evaluate_chunks, load_constraints  # noqa: E402
from src.models.classified_chunk import ClassifiedChunk  # noqa: E402
from src.processing.canonicalize import CANONICAL_CAREER_STAGES, CANONICAL_DISCIPLINES  # noqa: E402

CACHE_PATH = os.path.join(REPO_ROOT, "notebooks", "cache", "llm_requirements.jsonl")
MODEL = "gpt-5.4-mini"  # same model and settings as the rest of the pipeline's LLM calls


# -- 1. what GPT returns (no defaults: OpenAI strict mode wants every field present) ---------------------

class Requirement(BaseModel):
    topic: Literal["RESIDENCE", "NATIONALITY", "AGE", "DISCIPLINE", "CAREER_STAGE", "EDUCATION",
                   "STUDENT_STATUS", "APPLICANT_TYPE", "PRIOR_FUNDING", "OTHER_ELIGIBILITY"]
    quote: str                       # the sentence it comes from, verbatim
    strength: Literal["must", "may", "preferred"]  # only "must" can reject anyone
    group: int | None                # requirements sharing a group number are alternatives (any one is enough)
    excluded: bool                   # True: the listed values are EXCLUDED ("not open to residents of X")
    countries: list[str]             # ISO 3166-1 alpha-2, for RESIDENCE / NATIONALITY
    min_age: int | None
    max_age: int | None
    applicant_types: list[Literal["individual", "group", "organisation"]]
    disciplines: list[Literal[tuple(CANONICAL_DISCIPLINES)]]
    career_stages: list[Literal[tuple(CANONICAL_CAREER_STAGES)]]
    must_be_student: bool | None     # True: must be enrolled; False: students may not apply
    degree_required: bool | None


class Requirements(BaseModel):
    requirements: list[Requirement]


# the third version: the first two read permissions ("groups are welcome") and preferences as hard rules
SYSTEM_PROMPT = """You read an art open call and list its ELIGIBILITY requirements: conditions on WHO
may apply (where they live, nationality, age, discipline, career stage, education, student status,
whether a person / group / organisation, prior funding, anything else about the applicant).
Do NOT list conditions on the project, the application materials, the budget or the deadline.

For each requirement fill the fields that apply and leave the rest empty / null:
- countries: ISO 3166-1 alpha-2 codes. Expand regions into their member countries
  (EU = the 27 member states, EEA, Nordic countries, etc.).
- excluded = true when the call excludes the listed values instead of requiring them.
- applicant_types: who may apply (individual = one person, group = duo/collective, organisation).
- disciplines / career_stages: only the canonical values offered; leave empty if none fits.
- group: give the same number to requirements that are alternatives ("live in X OR be a citizen of X").
  Requirements that must all hold get group = null.
- quote: the sentence the requirement comes from, copied verbatim.
List only HARD conditions, ones that make an applicant ineligible if unmet.
NOT requirements: permissions ("groups are welcome", "duos may also apply"), preferences
("preferably", "it seems preferable"), descriptions of the typical audience, and priorities
("priority is given to"). Never list who MAY apply as if it were who MUST apply: "individuals,
duos or groups can apply" -> applicant_types = all three listed values.
- strength: "must" only when an applicant who does not meet it cannot apply. Use "may" for a
  permission or an option ("groups are welcome", "duos may also apply", "collectives of up to two
  people may apply") and "preferred" for a preference or priority.
- APPLICANT_TYPE: say who is accepted in total. If the call accepts individuals and also allows
  groups, list both. Use "must" only when the call clearly limits who may apply
  ("only organisations", "applications from individuals only").
If the call states no requirement on who may apply, return an empty list."""


def ask(client: OpenAI, opp) -> dict:
    """One GPT call on the call's title, requirements and description."""
    text = (f"Title: {opp.title_en}\n\nRequirements:\n{opp.requirements_text_en or '(none)'}\n\n"
            f"Description:\n{opp.description_en or '(none)'}")
    response = client.chat.completions.parse(
        model=MODEL, temperature=0, response_format=Requirements,
        messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": text}])
    return {"opportunity_id": opp.id, **response.choices[0].message.parsed.model_dump()}


def load_or_ask(opportunities: dict, ids: list[str]) -> dict[str, list[Requirement]]:
    """GPT's requirements for each call: from the cache, asking only for the calls not in it."""
    cached = {}
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, encoding="utf-8") as f:
            cached = {row["opportunity_id"]: row for row in map(json.loads, f)}
    todo = [i for i in ids if i not in cached]
    if todo:
        print(f"asking GPT for {len(todo)} calls ...")
        client = OpenAI(max_retries=10)
        with ThreadPoolExecutor(4) as pool:  # 4 workers: the account's rate limit (workflow.MD, model 4)
            answers = list(pool.map(lambda i: ask(client, opportunities[i]), todo))
        with open(CACHE_PATH, "a", encoding="utf-8") as f:
            for row in answers:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                cached[row["opportunity_id"]] = row
    return {i: [Requirement(**r) for r in cached[i]["requirements"]] for i in ids}


# -- 2. GPT's requirements in the engine's own formats -----------------------------------------------------

def to_engine(reqs: list[Requirement], opp_id: str) -> tuple[list[ClassifiedChunk], dict[tuple[str, str], Review]]:
    """Each "must" requirement becomes a sentence (its quote) plus a confirmed review holding GPT's value."""
    # "may" and "preferred" never reject: they only widen who is accepted, so all applicant types
    # the call mentions become one accepted set ("individuals can apply" + "groups are welcome")
    allowed = sorted({t for r in reqs if r.topic == "APPLICANT_TYPE" and not r.excluded for t in r.applicant_types})
    reqs = [r for r in reqs if r.strength == "must"]
    # alternatives (same group) get consecutive positions, so the engine's adjacency rule makes them an
    # OR group; separate requirements are 2 apart, so they never merge into one by accident
    reqs = sorted(reqs, key=lambda r: (r.group is None, r.group or 0))
    chunks, reviews, index, last_group = [], {}, 0, object()
    for r in reqs:
        index += 1 if (r.group is not None and r.group == last_group) else 2
        last_group = r.group
        polarity, value = "EXCLUDES" if r.excluded else "REQUIRES", None
        if r.topic == "AGE" and (r.min_age is not None or r.max_age is not None):
            value = {k: v for k, v in (("min_age", r.min_age), ("max_age", r.max_age)) if v is not None}
        elif r.topic in ("RESIDENCE", "NATIONALITY") and r.countries:
            value = {"countries": r.countries}
        elif r.topic == "APPLICANT_TYPE" and r.applicant_types:
            value = {"types": r.applicant_types if r.excluded else allowed}
        elif r.topic == "STUDENT_STATUS" and r.must_be_student is not None:
            # GPT writes "students are excluded" as must_be_student=True + excluded=True
            value = {"enrolled": True}
            polarity = "REQUIRES" if r.must_be_student and not r.excluded else "EXCLUDES"
        chunks.append(ClassifiedChunk(opportunity_id=opp_id, chunk_id=f"{opp_id}_{index}", chunk_index=index,
                                      text=r.quote, is_heading=False, label=r.topic, confidence=1.0,
                                      sentence_labels=[r.topic], polarity=polarity, value=value,
                                      model_trained_on="gpt"))
        # without a value the engine shows the requirement as an "unreadable" CHECK
        reviews[(r.quote, r.topic)] = Review(label=r.topic, decision="confirm", polarity=polarity,
                                             value=value, reason="GPT")
    return chunks, reviews


# -- 3. agreement: GPT's value counts only where the classifier found the same requirement ----------------

def _words(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.lower()))


def same_sentence(quote: str, sentence: str) -> bool:
    """GPT's quote and the classifier's sentence are the same text (a quote may be cut or merged)."""
    q, s = _words(quote), _words(sentence)
    return bool(q and s) and len(q & s) / min(len(q), len(s)) >= 0.8


def _family(label: str) -> str:
    return "GEO" if label in ("RESIDENCE", "NATIONALITY") else label  # the engine treats the two together


def agreement_reviews(chunks: list[ClassifiedChunk], reqs: list[Requirement], opp_id: str) -> dict:
    """Reviews for the classifier's own sentences, taken from GPT where both found the same requirement."""
    _, gpt_reviews = to_engine(reqs, opp_id)
    reviews = {}
    for chunk in chunks:
        labels = chunk.sentence_labels or ([chunk.label] if chunk.label else [])
        for (quote, topic), review in gpt_reviews.items():
            if same_sentence(quote, chunk.text) and any(_family(topic) == _family(label) for label in labels):
                key_label = chunk.label if _family(chunk.label or "") == _family(topic) else topic
                reviews[(chunk.text, key_label)] = review
    return reviews


# -- 4. scoring --------------------------------------------------------------------------------------------

def score(gold: pd.DataFrame, column: str) -> dict:
    """The four numbers of scripts/measure_verdicts.py, plus the share of conclusive verdicts."""
    judged_no, judged_yes = gold[gold.expected == "NOT_ELIGIBLE"], gold[gold.expected == "ELIGIBLE"]
    wrong_no = ((gold[column] == "LIKELY_NOT_ELIGIBLE") & (gold.expected != "NOT_ELIGIBLE")).sum()
    return {
        "wrong NOT ELIGIBLE": f"{wrong_no} / {(gold.expected != 'NOT_ELIGIBLE').sum()}",
        "wrong ELIGIBLE": f"{(judged_no[column] == 'ELIGIBLE').sum()} / {len(judged_no)}",
        "eligible found": f"{(judged_yes[column] == 'ELIGIBLE').sum()} / {len(judged_yes)}",
        "rejections found": f"{(judged_no[column] == 'LIKELY_NOT_ELIGIBLE').sum()} / {len(judged_no)}",
        "conclusive": f"{(gold[column] != 'CHECK').mean():.0%}",
    }


def compare(name: str, gold: pd.DataFrame, opportunities: dict, engine: EligibilityEngine, chunks_by: dict) -> None:
    reqs = load_or_ask(opportunities, sorted(gold.opportunity_id.unique()))

    def on_chunks(row, reviews) -> str:
        """The engine on the classifier's sentences, with the reviews given (as EligibilityEngine.evaluate)."""
        o = opportunities[row.opportunity_id]
        if not o.requirements_text.strip() or o.id not in chunks_by:
            return "CHECK"
        return evaluate_chunks(PERSONAS[row.persona], chunks_by[o.id], reviews, opportunity_id=o.id,
                               deadline=o.deadline_date, today=TODAY).status

    def gpt_alone(row) -> str:
        o = opportunities[row.opportunity_id]
        if not reqs[o.id]:
            return "CHECK"  # nothing found: like the engine, don't claim "open to everyone"
        chunks, reviews = to_engine(reqs[o.id], o.id)
        return evaluate_chunks(PERSONAS[row.persona], chunks, reviews, opportunity_id=o.id,
                               deadline=o.deadline_date, today=TODAY).status

    rows = list(gold.itertuples())
    gold = gold.assign(
        reviewed=[engine.evaluate(PERSONAS[r.persona], opportunities[r.opportunity_id], today=TODAY).status
                  for r in rows],
        no_review=[on_chunks(r, {}) for r in rows],
        gpt_alone=[gpt_alone(r) for r in rows],
        agreement=[on_chunks(r, agreement_reviews(chunks_by.get(r.opportunity_id, []), reqs[r.opportunity_id],
                                                  r.opportunity_id)) for r in rows],
    )
    print(f"\n{name}: {len(gold)} pairs, {gold.opportunity_id.nunique()} calls")
    columns = {"pipeline, reviewed": "reviewed", "pipeline, no review": "no_review",
               "GPT alone": "gpt_alone", "agreement": "agreement"}
    print(pd.DataFrame({title: score(gold, col) for title, col in columns.items()}).to_string())
    for col in ("gpt_alone", "agreement"):
        wrong = gold[(gold[col] == "LIKELY_NOT_ELIGIBLE") & (gold.expected != "NOT_ELIGIBLE")]
        if len(wrong):
            print(f"\n  wrong rejections, {col}:")
            print(wrong[["persona", "opportunity_id", "expected", "reason"]].to_string(max_colwidth=80))


if __name__ == "__main__":
    opportunities = load_opportunities()
    engine, chunks_by = EligibilityEngine(), load_constraints()

    live = pd.read_csv(LIVE_GOLD_PATH)
    older = pd.concat([pd.read_csv(path) for path in (GOLD_PATH, FRESH_GOLD_PATH, BLIND_GOLD_PATH)])
    unseen = older[~older.opportunity_id.isin(live.opportunity_id)].drop_duplicates(["persona", "opportunity_id"])
    for name, gold in [("live (tuned on)", live), ("unseen", unseen)]:
        # a re-extraction can drop a judged call from the corpus: skip it
        compare(name, gold[gold.opportunity_id.isin(opportunities)], opportunities, engine, chunks_by)
