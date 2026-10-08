"""
Settings, read from environment variables (set by docker-compose.yml from .env).

Read when first needed, not at import, so code that never touches the database
(the health check, its tests) runs without any of them set.
"""

import os
from functools import lru_cache


@lru_cache
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set (docker-compose.yml builds it from .env)")
    return url


@lru_cache
def cookie_secure() -> bool:
    # True on the VPS (HTTPS only). False locally, where the site is plain http://localhost
    return os.environ.get("COOKIE_SECURE", "true").lower() != "false"


@lru_cache
def allowed_origins() -> frozenset[str]:
    # the site's own address(es); requests that change data from anywhere else are refused
    raw = os.environ.get("ALLOWED_ORIGINS", "")
    return frozenset(origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip())


@lru_cache
def uploads_dir() -> str:
    # where the artists' original files are kept: a Docker volume in production
    # (docker-compose.yml), a temporary folder in the tests
    return os.environ.get("UPLOADS_DIR", "/data/uploads")
