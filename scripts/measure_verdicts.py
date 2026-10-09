"""
OpenArt — how useful are the eligibility verdicts? One table, run after every step of the
"conclusive verdicts" plan (workflow.MD, "Conclusive verdicts — plan"), so each change is judged on
the same numbers instead of on single sentences.

Two parts:

1. Corpus: every published call x each persona of scripts/evaluate_engine.py, plus one Berlin-based
   multidisciplinary artist shaped like the author's own profile. For each: the share of ELIGIBLE /
   CHECK / LIKELY_NOT_ELIGIBLE verdicts, the mean number of open points (CHECK rows) per call, and
   the share of calls with none. Then where the open points come from (check kind x label).
2. Gold verdicts (the step 6 and 6c sets, judged by reading the calls):
   - wrong NOT ELIGIBLE: engine rejects, judge did not      -> must stay 0
   - wrong ELIGIBLE: engine ELIGIBLE, judge NOT_ELIGIBLE     -> must not grow
   - eligible found: judged ELIGIBLE and engine ELIGIBLE     -> the number this plan raises
   - rejections found: judged NOT_ELIGIBLE and engine rejects

Usage: uv run python scripts/measure_verdicts.py
"""

import collections
import os
import sys
from datetime import date

import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(REPO_ROOT)
sys.path.append(os.path.join(REPO_ROOT, "scripts"))

from evaluate_engine import FRESH_GOLD_PATH, GOLD_PATH, PERSONAS, TODAY, load_opportunities  # noqa: E402

from src.eligibility.engine import EligibilityEngine  # noqa: E402
from src.eligibility.profile import ArtistProfile  # noqa: E402

CORPUS_PERSONAS = {
    **PERSONAS,
    # the author's profile shape: the case the plan was started from
    "berlin_multidisciplinary": ArtistProfile(
        birth_date=date(1990, 3, 1), nationalities=["IT"], residence_country="DE", applicant_type="individual",
        disciplines=["Visual Arts", "Music", "Film/Video", "Literature/Writing"], career_stage="Mid-Career",
        years_active=12, currently_enrolled=False, graduation_year=2014, has_degree=True),
}


def open_points(verdict) -> list:
    """The CHECK rows of a verdict: what the artist would still have to read for themselves."""
    return [item for item in verdict.items if (item.group_outcome or item.outcome) == "CHECK"]


def corpus_table(engine, opportunities) -> None:
    rows, sources = [], collections.Counter()
    for name, profile in CORPUS_PERSONAS.items():
        statuses, points = collections.Counter(), []
        for opportunity in opportunities.values():
            verdict = engine.evaluate(profile, opportunity, today=TODAY)
            statuses[verdict.status] += 1
            open_ = open_points(verdict)
            points.append(len(open_))
            sources.update((item.check_kind or "group", item.label) for item in open_)
        n = len(points)
        rows.append({"persona": name, "eligible": statuses["ELIGIBLE"] / n, "check": statuses["CHECK"] / n,
                     "not_eligible": statuses["LIKELY_NOT_ELIGIBLE"] / n,
                     "conclusive": (statuses["ELIGIBLE"] + statuses["LIKELY_NOT_ELIGIBLE"]) / n,
                     "open_points": sum(points) / n, "no_open_point": sum(p == 0 for p in points) / n})
    table = pd.DataFrame(rows).set_index("persona")
    table.loc["mean"] = table.mean()
    print(f"Corpus: {len(opportunities)} published calls x {len(CORPUS_PERSONAS)} personas\n")
    print(table.round(2).to_string(), "\n")
    total = sum(sources.values())
    print(f"Where the open points come from ({total} in all, all personas):")
    for (kind, label), count in sources.most_common(15):
        print(f"  {count:5d} ({count / total:4.0%})  {kind:22s} {label}")


def gold_table(engine, opportunities) -> None:
    print("\nGold verdicts (judged by reading the calls):")
    print(f"  {'set':6s} {'wrong NOT ELIGIBLE':>19s} {'wrong ELIGIBLE':>15s} {'eligible found':>15s} "
          f"{'rejections found':>17s}")
    for name, path in [("step 6", GOLD_PATH), ("fresh", FRESH_GOLD_PATH)]:
        gold = pd.read_csv(path)
        status = [engine.evaluate(PERSONAS[r.persona], opportunities[r.opportunity_id], today=TODAY).status
                  for r in gold.itertuples()]
        gold = gold.assign(engine=status)
        wrong_no = ((gold.engine == "LIKELY_NOT_ELIGIBLE") & (gold.expected != "NOT_ELIGIBLE")).sum()
        judged_no, judged_yes = gold[gold.expected == "NOT_ELIGIBLE"], gold[gold.expected == "ELIGIBLE"]
        wrong_yes = (judged_no.engine == "ELIGIBLE").sum()
        found_yes = (judged_yes.engine == "ELIGIBLE").sum()
        found_no = (judged_no.engine == "LIKELY_NOT_ELIGIBLE").sum()
        print(f"  {name:6s} {wrong_no:13d} / {(gold.expected != 'NOT_ELIGIBLE').sum():3d} "
              f"{wrong_yes:9d} / {len(judged_no):3d} {found_yes:9d} / {len(judged_yes):3d} "
              f"{found_no:11d} / {len(judged_no):3d}")


if __name__ == "__main__":
    engine = EligibilityEngine()
    opportunities = load_opportunities()
    corpus_table(engine, opportunities)
    gold_table(engine, opportunities)
