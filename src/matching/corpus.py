"""
OpenArt — load the published corpus (dataset/opportunities.csv) as ProcessedOpportunity rows.

The product runs from the published CSV, not from the private data/ repo, so
anyone with the repo can run matching. The CSV is a flattened copy of
data/processed/opportunities.jsonl (scripts/export_dataset.py): list columns
are written as Python literals ("['Residency']") and missing values as empty
cells, so both are turned back into proper values here.
"""

import ast
import csv
import os

from src.models.processed_opportunity import ProcessedOpportunity

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PUBLISHED_PATH = os.path.join(REPO_ROOT, "dataset", "opportunities.csv")

# columns holding a list (of strings, or of funding dicts), written as Python literals
LIST_COLUMNS = {"discipline_canonical", "opportunity_type_canonical", "career_stage_canonical",
                "country_canonical", "funding_components"}


def _parse_row(row: dict[str, str]) -> ProcessedOpportunity:
    values = {}
    for column, cell in row.items():
        if column in LIST_COLUMNS:
            # literal_eval only reads Python literals (lists, dicts, strings, numbers), it never runs code
            values[column] = ast.literal_eval(cell) if cell else []
        else:
            values[column] = cell if cell != "" else None  # empty cell = not stated
    return ProcessedOpportunity.model_validate(values)


def load_opportunities(path: str = PUBLISHED_PATH) -> list[ProcessedOpportunity]:
    """Every published opportunity, in file order."""
    with open(path, encoding="utf-8", newline="") as f:
        return [_parse_row(row) for row in csv.DictReader(f)]
