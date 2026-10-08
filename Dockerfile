# OpenArt API image (FastAPI). Built and run by docker-compose.yml.
# Python 3.13 lives in the image, so the server's own Python version doesn't matter.
FROM python:3.13-slim

# uv, copied from its official image: installs exactly the versions pinned in uv.lock
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv

WORKDIR /app

# 1. dependencies first, so this slow layer is reused until pyproject.toml / uv.lock change
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 2. then the code
COPY api/ api/
COPY src/ src/

# run as an unprivileged user, not root. /data/uploads (the artists' files) is a volume
# (docker-compose.yml); creating it here owned by that user makes the new volume writable by it
RUN useradd --create-home openart && mkdir -p /data/uploads && chown openart /data/uploads
USER openart

# download the embedding model now (~0.4 GB, into ~/.cache/fastembed), so the first
# upload after a deploy doesn't wait for it
RUN /app/.venv/bin/python -c "from src.matching.index import load_embedder; load_embedder()"

EXPOSE 8000
# bring the database schema up to date first (does nothing when it already is), then serve
CMD ["sh", "-c", "/app/.venv/bin/alembic -c api/alembic.ini upgrade head && exec /app/.venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000"]
