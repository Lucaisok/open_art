"""
OpenArt — end-to-end evaluation of the eligibility engine (workflow.MD, step 6):
5 personas x 30 opportunities, the engine's verdict against an expected
verdict judged by reading the call.

Two modes:
  uv run python scripts/evaluate_engine.py --packet out.json
      writes what the judge needs (persona descriptions + the full text of the
      30 sampled calls). The judge never sees the engine's output.
  uv run python scripts/evaluate_engine.py
      runs the engine on every persona x call and compares it with
      dataset/labels/engine_gold_verdicts.csv (persona, opportunity_id,
      expected, rule_class, quote, reason, judged_by).

Expected verdicts (ANNOTATION_GUIDELINES-style definitions, also given to the judge):
  NOT_ELIGIBLE  the call clearly rules the persona out, on a who-may-apply rule that covers the whole call
  UNCLEAR       it depends on something the profile doesn't say, or the text is ambiguous
  ELIGIBLE      nothing in the call rules the persona out

The headline number is the FALSE "NOT ELIGIBLE" rate: the engine says
LIKELY_NOT_ELIGIBLE where the judge did not say NOT_ELIGIBLE. It must be ~0.
"""

import argparse
import collections
import json
import os
import random
import sys
from datetime import date

import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(REPO_ROOT)

from src.eligibility.engine import REJECT_CLASSES, EligibilityEngine  # noqa: E402
from src.eligibility.profile import ArtistProfile  # noqa: E402
from src.models.processed_opportunity import ProcessedOpportunity  # noqa: E402

PROCESSED_PATH = os.path.join(REPO_ROOT, "data", "processed", "opportunities.jsonl")
PUBLISHED_PATH = os.path.join(REPO_ROOT, "dataset", "opportunities.csv")
GOLD_PATH = os.path.join(REPO_ROOT, "dataset", "labels", "engine_gold_verdicts.csv")

TODAY = date(2026, 10, 1)  # fixed, so ages and the results are reproducible
SEED = 2026
SAMPLE_SIZE = 30
MAX_PER_SOURCE = 3  # kunsten_be_flanders alone is 1 in 4 calls; keep the sample varied

# Five personas chosen to exercise every class the engine may reject on, plus
# two profiles with gaps (an organisation has no birth date or enrolment; the
# duo didn't fill them in), because missing fields are the normal case.
PERSONAS = {
    "belgian_painter": ArtistProfile(
        birth_date=date(1998, 3, 1), nationalities=["BE"], residence_country="BE",
        applicant_type="individual", disciplines=["Visual Arts"], career_stage="Emerging/Early-Career",
        years_active=5, currently_enrolled=False, graduation_year=2021, has_degree=True,
        degree_field="Fine Arts"),
    "norwegian_dance_company": ArtistProfile(
        residence_country="NO", applicant_type="organisation", disciplines=["Dance"],
        career_stage="Established/Professional", years_active=12),
    "vienna_music_student": ArtistProfile(
        birth_date=date(2001, 5, 15), nationalities=["IT"], residence_country="AT",
        applicant_type="individual", disciplines=["Music"], career_stage="Student", years_active=2,
        currently_enrolled=True, graduation_year=2024, has_degree=True, degree_field="Music (bachelor)"),
    "ukrainian_writer_in_germany": ArtistProfile(
        birth_date=date(1974, 9, 20), nationalities=["UA"], residence_country="DE",
        applicant_type="individual", disciplines=["Literature/Writing"], career_stage="Established/Professional",
        years_active=25, currently_enrolled=False, graduation_year=1998, has_degree=True,
        degree_field="Philology"),
    "dutch_photo_duo": ArtistProfile(
        nationalities=["NL"], residence_country="NL", applicant_type="group",
        disciplines=["Photography"], career_stage="Mid-Career", years_active=8),
}

# how each persona is described to the judge: the profile fields only, so the judge
# knows exactly what the engine knows (and that anything else is unknown)
PERSONA_NOTES = {
    "norwegian_dance_company": "A dance company (an organisation) based in Norway.",
    "dutch_photo_duo": "Two photographers applying together as a duo; they left several fields empty.",
}


def load_opportunities() -> dict[str, ProcessedOpportunity]:
    with open(PROCESSED_PATH, encoding="utf-8") as f:
        rows = [ProcessedOpportunity.model_validate_json(line) for line in f]
    published = set(pd.read_csv(PUBLISHED_PATH, usecols=["id"])["id"])  # only calls the product shows
    return {row.id: row for row in rows if row.id in published}


def select_sample(engine: EligibilityEngine, opportunities: dict[str, ProcessedOpportunity]) -> list[str]:
    """30 calls, fixed seed: half that contain a reviewed sentence the engine could reject on
    (otherwise a random sample has too few possible rejections to measure), half from the rest.
    The split uses the inputs (sentences + reviews), never a verdict."""
    def can_reject(opp_id: str) -> bool:
        for chunk in engine.chunks_by_opportunity.get(opp_id, []):
            review = engine.reviews.get(chunk.text)
            if chunk.label in REJECT_CLASSES and review and review.decision in ("confirm", "fix"):
                return True
        return False

    rng = random.Random(SEED)
    ids = sorted(opportunities)
    rng.shuffle(ids)
    picked, per_source = [], {}
    for want_reject in (True, False):
        taken = 0
        for opp_id in ids:
            source = opportunities[opp_id].source
            if (taken < SAMPLE_SIZE // 2 and opp_id not in picked and can_reject(opp_id) == want_reject
                    and per_source.get(source, 0) < MAX_PER_SOURCE):
                picked.append(opp_id)
                per_source[source] = per_source.get(source, 0) + 1
                taken += 1
    return picked


def write_packet(path: str, sample: list[str], opportunities: dict[str, ProcessedOpportunity]) -> None:
    personas = {name: {"profile": json.loads(p.model_dump_json(exclude_defaults=True)),
                       "note": PERSONA_NOTES.get(name, "")} for name, p in PERSONAS.items()}
    calls = []
    for opp_id in sample:
        o = opportunities[opp_id]
        calls.append({"opportunity_id": o.id, "title": o.title_en, "organisation": o.organisation,
                      "deadline": str(o.deadline_date) if o.deadline_date else None,
                      "description": o.description_en, "requirements": o.requirements_text_en})
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"today": str(TODAY), "personas": personas, "calls": calls}, f, ensure_ascii=False, indent=2)
    print(f"packet with {len(personas)} personas x {len(calls)} calls written to {path}")


ENGINE_TO_GOLD = {"ELIGIBLE": "ELIGIBLE", "CHECK": "UNCLEAR", "LIKELY_NOT_ELIGIBLE": "NOT_ELIGIBLE"}


def evaluate(engine: EligibilityEngine, opportunities: dict[str, ProcessedOpportunity]) -> None:
    # the 30 calls are frozen in the gold file: select_sample() depends on the review file, which grows,
    # so re-running it later would pick other calls than the ones that were judged
    gold = pd.read_csv(GOLD_PATH)
    rows = []
    for _, g in gold.iterrows():
        verdict = engine.evaluate(PERSONAS[g["persona"]], opportunities[g["opportunity_id"]], today=TODAY)
        deciding = verdict.deciding_items
        rows.append({**g.to_dict(), "engine": ENGINE_TO_GOLD[verdict.status], "verdict": verdict,
                     "engine_reason": " | ".join(f"{i.label}: {i.reason}" for i in deciding[:3]),
                     "engine_quote": deciding[0].text if deciding else ""})
    df = pd.DataFrame(rows)
    order = ["ELIGIBLE", "UNCLEAR", "NOT_ELIGIBLE"]

    print(f"{len(df)} persona x call pairs ({df['persona'].nunique()} personas, {df['opportunity_id'].nunique()} calls)\n")
    print("rows = judged, columns = engine (CHECK shown as UNCLEAR)")
    print(pd.crosstab(df["expected"], df["engine"]).reindex(index=order, columns=order, fill_value=0), "\n")

    engine_no = df[df["engine"] == "NOT_ELIGIBLE"]
    false_no = engine_no[engine_no["expected"] != "NOT_ELIGIBLE"]
    not_no = df[df["expected"] != "NOT_ELIGIBLE"]
    print(f"FALSE NOT ELIGIBLE: {len(false_no)} of {len(engine_no)} engine rejections "
          f"({len(false_no) / max(len(engine_no), 1):.0%}); {len(false_no)} of {len(not_no)} pairs "
          f"the judge did not reject ({len(false_no) / max(len(not_no), 1):.1%})")

    gold_no = df[df["expected"] == "NOT_ELIGIBLE"]
    print(f"judged NOT_ELIGIBLE: {len(gold_no)}; engine rejects {sum(gold_no['engine'] == 'NOT_ELIGIBLE')}, "
          f"says CHECK {sum(gold_no['engine'] == 'UNCLEAR')}, says ELIGIBLE {sum(gold_no['engine'] == 'ELIGIBLE')} "
          "(a wrong ELIGIBLE)")
    reject_class = gold_no["rule_class"].isin(REJECT_CLASSES)
    print(f"  of which on a class the engine may reject on: {reject_class.sum()} "
          f"(engine rejects {sum(gold_no[reject_class]['engine'] == 'NOT_ELIGIBLE')}); "
          f"on a CHECK-only class: {(~reject_class).sum()}")
    print("  by rule class:", gold_no.groupby("rule_class")["engine"].value_counts().unstack(fill_value=0).to_dict("index"))

    gold_yes = df[df["expected"] == "ELIGIBLE"]
    print(f"judged ELIGIBLE: {len(gold_yes)}; engine ELIGIBLE {sum(gold_yes['engine'] == 'ELIGIBLE')}, "
          f"CHECK {sum(gold_yes['engine'] == 'UNCLEAR')} (the cost of caution)\n")

    print("per persona (judged NOT_ELIGIBLE / engine rejections / false rejections):")
    for name, part in df.groupby("persona"):
        false = sum((part["engine"] == "NOT_ELIGIBLE") & (part["expected"] != "NOT_ELIGIBLE"))
        print(f"  {name:28s} {sum(part['expected'] == 'NOT_ELIGIBLE'):3d} / "
              f"{sum(part['engine'] == 'NOT_ELIGIBLE'):3d} / {false}")

    diagnose(df)

    print("\nevery false NOT ELIGIBLE:")
    for _, r in false_no.iterrows():
        print(f"  [{r['persona']}] {r['opportunity_id']} judged {r['expected']}: {r['reason']}\n"
              f"      engine quoted: {r['engine_quote'][:160]}\n      engine reason: {r['engine_reason'][:200]}")
    print("\nevery wrong ELIGIBLE (judged NOT_ELIGIBLE):")
    for _, r in gold_no[gold_no["engine"] == "ELIGIBLE"].iterrows():
        print(f"  [{r['persona']}] {r['opportunity_id']} ({r['rule_class']}): {str(r['quote'])[:160]}")


def _missed_cause(row) -> str:
    """Why the engine did not reject a pair the judge rejected on a class it may reject on."""
    if row["where"] != "requirements":
        return f"rule only in the {row['where'] if isinstance(row['where'], str) else 'title'} (engine reads requirements)"
    family = {"NATIONALITY", "RESIDENCE"} if row["rule_class"] in ("NATIONALITY", "RESIDENCE") else {row["rule_class"]}
    items = [i for i in row["verdict"].items if i.label in family]
    if not items:
        return "no sentence of that class found (classifier)"
    kinds = [i.check_kind for i in items if i.check_kind]
    if kinds:
        return collections.Counter(kinds).most_common(1)[0][0]
    return "sentence read as a pass (" + "/".join(sorted({i.outcome for i in items})) + ")"


def diagnose(df: pd.DataFrame) -> None:
    """Where the CHECKs come from: the two costs of caution."""
    missed = df[(df["expected"] == "NOT_ELIGIBLE") & (df["engine"] == "UNCLEAR") & df["rule_class"].isin(REJECT_CLASSES)]
    print(f"\njudged NOT_ELIGIBLE on a rejectable class, engine CHECK ({len(missed)}), by cause:")
    for cause, n in collections.Counter(missed.apply(_missed_cause, axis=1)).most_common():
        print(f"  {n:3d}  {cause}")

    over = df[(df["expected"] == "ELIGIBLE") & (df["engine"] == "UNCLEAR")]
    kinds = collections.Counter(k for v in over["verdict"] for k in {i.check_kind for i in v.deciding_items})
    only = collections.Counter(next(iter(ks)) for v in over["verdict"]
                               if len(ks := {i.check_kind for i in v.deciding_items}) == 1)
    print(f"judged ELIGIBLE, engine CHECK ({len(over)}): pairs with at least one check of each kind "
          f"(and pairs where it is the only kind)")
    for kind, n in kinds.most_common():
        print(f"  {n:3d} ({only.get(kind, 0):2d})  {kind}")
    print(f"  mean number of checks per pair: {over['verdict'].map(lambda v: len(v.deciding_items)).mean():.1f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--packet", help="write the judging packet to this JSON file instead of evaluating")
    args = parser.parse_args()

    engine = EligibilityEngine()
    opportunities = load_opportunities()
    if args.packet:
        write_packet(args.packet, select_sample(engine, opportunities), opportunities)
    else:
        evaluate(engine, opportunities)


if __name__ == "__main__":
    main()
