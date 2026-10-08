"""
Check profile pre-fill (RAG step 3) with the real model on the two fictional personas' CVs.

    uv run python scripts/evaluate_profile_prefill.py

Compares the proposals with the personas' true profiles (written down from
scripts/make_example_artists.py) and counts, per field:
  right   - proposed and correct
  wrong   - proposed and incorrect
  missed  - stated in the CV but not proposed
  extra   - proposed although the CV doesn't state it
  ok-null - not stated and not proposed
Makes one OpenAI call per persona (needs OPENAI_API_KEY). 2 personas x 10 fields: a sanity check,
not a benchmark. The knowledge bases are built in a temporary folder.
"""

import os
import sys
import tempfile
from collections import Counter
from datetime import date

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from src.rag.knowledge_base import ArtistKnowledgeBase  # noqa: E402
from src.rag.profile_prefill import prefill_profile  # noqa: E402

TODAY = date(2026, 10, 8)   # fixed, so years_active has one right answer

# the true profile of each persona, as stated in their CV. None = the CV doesn't say.
# A set means any non-empty subset is acceptable (discipline names for sound art are a judgement call);
# a range means any value in it is acceptable (where "active since" starts is a judgement call too).
TRUTH = {
    ("ilka_varga", "cv.pdf"): {
        "birth_date": date(1994, 3, 12),
        "nationalities": ["HU"],
        "residence_country": "AT",
        "applicant_type": None,
        "disciplines": {"Visual Arts"},
        "years_active": range(4, 6),            # 2021 diploma show / prize (5) or 2022 (4)
        "currently_enrolled": None,
        "graduation_year": 2021,
        "has_degree": True,
        "degree_field": "painting and graphic arts",
    },
    ("tomas_ferreira", "cv.docx"): {
        "birth_date": date(1988, 7, 4),
        "nationalities": ["BR", "PT"],
        "residence_country": "PT",
        "applicant_type": "individual",
        "disciplines": {"Music", "Visual Arts", "Digital/New Media Arts", "Performing Arts", "Multidisciplinary"},
        "years_active": range(5, 8),            # 2019 residency (7) or 2021 performance (5)
        "currently_enrolled": False,
        "graduation_year": 2010,
        "has_degree": True,
        "degree_field": "music technology",
    },
}


def is_right(value, truth) -> bool:
    if isinstance(truth, set):
        return bool(value) and set(value) <= truth
    if isinstance(truth, range):
        return value in truth
    if isinstance(truth, str) and isinstance(value, str):
        return value.strip().lower() == truth.lower()
    return value == truth


def main() -> None:
    root, embedder, totals = tempfile.mkdtemp(), None, Counter()
    for (artist, cv), truth in TRUTH.items():
        kb = ArtistKnowledgeBase(artist, root=root, embedder=embedder)
        kb.add_document(os.path.join(REPO_ROOT, "examples", "artists", artist, cv))
        embedder = kb.embedder
        result = prefill_profile(kb, documents=[cv], today=TODAY)
        proposed = {p.field: p for p in result.proposals}

        print(f"\n{artist} ({cv}): {len(result.passages)} passages sent")
        for name, expected in truth.items():
            proposal = proposed.get(name)
            if proposal is None:
                outcome = "ok-null" if expected is None else "missed"
            elif expected is None:
                outcome = "extra"
            else:
                outcome = "right" if is_right(proposal.value, expected) else "wrong"
            totals[outcome] += 1
            shown = f'{proposal.value!r}  "{proposal.quote}"' if proposal else "-"
            print(f"  {outcome:8} {name:19} {shown}")
        for name, reason in result.rejected:
            print(f"  dropped  {name}: {reason}")

    print("\n" + "   ".join(f"{k}: {totals[k]}" for k in ["right", "wrong", "missed", "extra", "ok-null"]))


if __name__ == "__main__":
    main()
