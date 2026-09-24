"""
OpenArt — content-based deduplication for the exported/published dataset.

The id scheme (sha256(source_url), see src/collectors/ids.py) only
dedupes an opportunity crawled at one URL twice; it doesn't catch the
same real opportunity published at two different URLs. Confirmed
instances: deutscher_uebersetzerfonds's "Hieronymus Program 2026" (an
announcement PDF and a separate application-form PDF for the same
call), kunsten_be_flanders's "Prima La Musica..." (same post under two
slugs), and cyprus_funding_programmes_culture's "Circulation of
European Literary Works" (same title and deadline, two portal URLs) -
found while building this, previously undocumented.

Deliberately exact-match on (source, title_en), not fuzzy/near-duplicate
matching: every confirmed case above is an exact match once title_en is
normalized, and scanning the full processed corpus for this found zero
other collisions of any kind - no evidence yet that near-duplicate
matching is needed, and adding it without evidence risks false
positives (e.g. two legitimately distinct recurring rounds that happen
to share a title). Revisit if a near-duplicate case turns up. Matched on
title_en specifically (not title) so it's comparable across source
languages post-translation - see src/processing/normalize.py.

Runs on data/processed/ data, applied only at the export/publish step
(scripts/export_dataset.py) - data/raw/ and data/processed/
opportunities.jsonl themselves are left untouched, since both crawled
URLs are legitimate provenance worth keeping there, and so re-running
normalize_all() never needs to "un-drop" anything.
"""

from src.models.processed_opportunity import ProcessedOpportunity


def _dedupe_key(record: ProcessedOpportunity) -> tuple[str, str]:
    return (record.source, record.title_en.strip().lower())


def drop_content_duplicates(
    records: list[ProcessedOpportunity],
) -> tuple[list[ProcessedOpportunity], list[tuple[ProcessedOpportunity, ProcessedOpportunity]]]:
    """Groups records by (source, normalized title_en) and keeps only the
    one with the longest requirements_text per group - the fullest
    eligibility text, which is what annotation/classification actually
    needs; ties broken by id for determinism.

    Returns (kept_records, dropped_pairs), where each dropped_pairs
    entry is (dropped_record, kept_record_it_duplicates) for logging.
    """
    groups: dict[tuple[str, str], list[ProcessedOpportunity]] = {}
    for r in records:
        groups.setdefault(_dedupe_key(r), []).append(r)

    kept: list[ProcessedOpportunity] = []
    dropped: list[tuple[ProcessedOpportunity, ProcessedOpportunity]] = []
    for group in groups.values():
        if len(group) == 1:
            kept.append(group[0])
            continue
        best = max(group, key=lambda r: (len(r.requirements_text or ""), r.id))
        kept.append(best)
        dropped.extend((r, best) for r in group if r.id != best.id)

    return kept, dropped
