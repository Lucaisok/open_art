"""Shared JSONL read/write helpers for collectors."""

import json
import os

from pydantic import BaseModel


def write_jsonl(records: list[BaseModel], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(record.model_dump_json())
            f.write("\n")


def load_jsonl(path: str, model: type[BaseModel]) -> list[BaseModel]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [model.model_validate_json(line) for line in f if line.strip()]


def load_seen_ids(*dirs: str) -> set[str]:
    """Scan directories of .jsonl files and collect every record's "id" field.

    Used across collector stages to dedup against ids already produced by
    an earlier stage (discovery, extraction, manual entry) regardless of
    which pydantic model wrote them.
    """
    seen: set[str] = set()
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for root, _, files in os.walk(d):
            for fname in files:
                if not fname.endswith(".jsonl"):
                    continue
                with open(os.path.join(root, fname), encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            seen.add(json.loads(line)["id"])
    return seen
