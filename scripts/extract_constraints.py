"""
OpenArt — eligibility engine, ingestion step: split every opportunity's
requirements_text_en into sentence chunks and classify each one with the RQ1
model, once, so the engine never has to run a model at request time.

    data/processed/opportunities.jsonl  ->  data/processed/eligibility_constraints.jsonl
                                            (one row per chunk, see src/models/classified_chunk.py)

The whole file is rebuilt on every run rather than updated incrementally:
classifying the full corpus takes about 5 minutes and has no API cost, and a
full rebuild guarantees every row was labeled by the same model.

Rows carry the class and confidence, a safety-net flag on NONE chunks that
may be requirements after all (src/eligibility/safety_net.py), the polarity
of every (possible) requirement (src/eligibility/polarity.py), and its parsed
value where a parser exists ("under 35" -> max age 34,
src/eligibility/values.py). See workflow.MD, "Eligibility engine — plan".

Usage: uv run python scripts/extract_constraints.py
"""

import os
import sys
from collections import Counter

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(REPO_ROOT)

from src.collectors.jsonl import load_jsonl, write_jsonl  # noqa: E402
from src.eligibility.chunking import chunk_requirements  # noqa: E402
from src.eligibility.classify import EligibilityClassifier  # noqa: E402
from src.eligibility.polarity import polarity  # noqa: E402
from src.eligibility.safety_net import flag_missed_requirement  # noqa: E402
from src.eligibility.values import parse_value  # noqa: E402
from src.models.classified_chunk import ClassifiedChunk  # noqa: E402
from src.models.processed_opportunity import ProcessedOpportunity  # noqa: E402

PROCESSED_PATH = os.path.join(REPO_ROOT, "data", "processed", "opportunities.jsonl")
OUT_PATH = os.path.join(REPO_ROOT, "data", "processed", "eligibility_constraints.jsonl")

# the engine's threshold for a constraint it may reject on (workflow.MD,
# "Design principle"); used here only to report how many chunks reach it
REJECT_CONFIDENCE = 0.7


def extract_constraints(processed_path: str = PROCESSED_PATH, out_path: str = OUT_PATH) -> list[ClassifiedChunk]:
    opportunities = load_jsonl(processed_path, ProcessedOpportunity)
    classifier = EligibilityClassifier()
    trained_on = classifier.metadata["trained_on"]

    # 1. split every opportunity into chunks
    chunks_per_opportunity = [(opp.id, chunk_requirements(opp.requirements_text_en)) for opp in opportunities]

    # 2. classify all non-heading chunks in one batch (much faster than one call per opportunity)
    to_classify = [c.text for _, chunks in chunks_per_opportunity for c in chunks if not c.is_heading]
    predictions = iter(classifier.predict(to_classify))

    # 3. one row per chunk; headings get no prediction. `predictions` is
    #    consumed in the same order the texts were collected above
    rows = []
    for opportunity_id, chunks in chunks_per_opportunity:
        for chunk in chunks:
            prediction = None if chunk.is_heading else next(predictions)
            # a NONE chunk may still be a requirement the model missed (step 2b)
            flag = None
            if prediction and prediction.label == "NONE":
                flag = flag_missed_requirement(chunk.text, prediction.probabilities)
            # direction of the requirement, for every chunk that is (or may be) one
            requirement_label = flag.suspected_label if flag else (prediction.label if prediction else None)
            direction = value = None
            if requirement_label and requirement_label != "NONE":
                direction = polarity(chunk.text, chunk.heading, requirement_label)
                # no value for a waived criterion (nothing to check), nor on a
                # safety-net row (a NONE chunk is only ever a CHECK item)
                if direction != "WAIVES" and not flag:
                    value = parse_value(requirement_label, chunk.text)
            rows.append(ClassifiedChunk(
                opportunity_id=opportunity_id,
                chunk_id=f"{opportunity_id}_{chunk.index}",
                chunk_index=chunk.index,
                text=chunk.text,
                is_heading=chunk.is_heading,
                heading=chunk.heading,
                label=prediction.label if prediction else None,
                confidence=prediction.confidence if prediction else None,
                probabilities=prediction.probabilities if prediction else None,
                suspected_label=flag.suspected_label if flag else None,
                safety_net_reason=flag.reason if flag else None,
                polarity=direction,
                value=value,
                model_trained_on=trained_on,
            ))

    write_jsonl(rows, out_path)
    print(f"{len(opportunities)} opportunities -> {len(rows)} chunks written to {out_path}")
    return rows


def print_report(rows: list[ClassifiedChunk]) -> None:
    """Sanity check of the output: how chunks spread over classes and how
    confident the model is. Not an evaluation (there are no gold labels for
    most of these chunks), just a check that nothing looks off."""
    classified = [r for r in rows if not r.is_heading]
    print(f"\n{len(rows) - len(classified)} bare headings skipped, {len(classified)} chunks classified")

    print(f"\n{'class':18s} {'chunks':>6s} {'share':>6s} {'mean conf':>9s} {'conf >= ' + str(REJECT_CONFIDENCE):>10s}")
    counts = Counter(r.label for r in classified)
    for label, n in counts.most_common():
        confidences = [r.confidence for r in classified if r.label == label]
        confident = sum(c >= REJECT_CONFIDENCE for c in confidences)
        print(f"{label:18s} {n:6d} {n / len(classified):6.1%} {sum(confidences) / n:9.2f} {confident / n:10.0%}")

    # opportunities where the model found no eligibility sentence at all: the
    # engine would call these ELIGIBLE for everyone, so they are worth a look
    with_constraint = {r.opportunity_id for r in classified if r.label != "NONE"}
    all_ids = {r.opportunity_id for r in rows}
    print(f"\n{len(all_ids - with_constraint)} / {len(all_ids)} opportunities have no eligibility chunk "
          f"(every chunk NONE, or no requirements text)")

    flagged = [r for r in classified if r.suspected_label]
    print(f"\nSafety net: {len(flagged)} NONE chunks flagged as possible requirements "
          f"({len(flagged) / len(all_ids):.2f} per opportunity)")
    for label, n in Counter(r.suspected_label for r in flagged).most_common():
        print(f"  {label:18s} {n:4d}")
    still_empty = all_ids - with_constraint - {r.opportunity_id for r in flagged}
    print(f"{len(still_empty)} opportunities have no eligibility chunk even after the safety net")

    with_polarity = [r for r in rows if r.polarity]
    print(f"\nPolarity of {len(with_polarity)} (possible) requirement chunks:")
    for direction, n in Counter(r.polarity for r in with_polarity).most_common():
        print(f"  {direction:9s} {n:4d} ({n / len(with_polarity):.1%})")

    # how often a value could be parsed, per class that has a parser
    print("\nParsed values (classes with a parser, polarity not WAIVES):")
    for label in ["AGE", "NATIONALITY", "RESIDENCE", "APPLICANT_TYPE", "STUDENT_STATUS"]:
        candidates = [r for r in with_polarity if (r.suspected_label or r.label) == label and r.polarity != "WAIVES"]
        parsed = sum(r.value is not None for r in candidates)
        print(f"  {label:15s} {parsed:4d} / {len(candidates):4d} ({parsed / max(len(candidates), 1):.0%})")


if __name__ == "__main__":
    print_report(extract_constraints())
