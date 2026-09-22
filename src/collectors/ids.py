"""Deterministic id generation shared by all collectors.

Never use Python's built-in hash() for this - it's randomized per
process (PYTHONHASHSEED) and silently breaks dedup across runs.
"""

import hashlib


def make_id(source_url: str, prefix: str) -> str:
    digest = hashlib.sha256(source_url.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"
