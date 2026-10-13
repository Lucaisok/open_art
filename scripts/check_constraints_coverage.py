"""
OpenArt — does eligibility_constraints.jsonl cover every published call?

Run before copying the constraints file to the VPS (deploy/sync_data.sh does).
A call that states requirements but has no classified sentences shows "This
call has not been analysed yet" in the app. Exits 1 if there is any, so the
sync stops before a stale file is copied.

    python scripts/check_constraints_coverage.py
    -> OK: all 371 calls with requirements text are classified (396 published).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.eligibility.engine import EligibilityEngine  # noqa: E402
from src.matching.corpus import load_opportunities  # noqa: E402


def main() -> int:
    opportunities = load_opportunities()
    missing = EligibilityEngine().unanalysed(opportunities)
    with_text = sum(1 for o in opportunities if o.requirements_text.strip())
    if missing:
        print(f"NOT OK: {len(missing)} of {with_text} calls with requirements text have no constraints, "
              f"e.g. {', '.join(missing[:5])}.")
        print("Run scripts/extract_constraints.py first.")
        return 1
    print(f"OK: all {with_text} calls with requirements text are classified ({len(opportunities)} published).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
