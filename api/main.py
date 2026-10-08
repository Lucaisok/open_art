"""
OpenArt — the web API (FastAPI).

The Next.js frontend forwards every /api/* request here (see web/next.config.ts),
so all routes live under /api. The interactive docs are at /api/docs.

Routes so far (workflow.MD, "Web app — plan"):
- step 1: health check
- step 2: sign up / log in / log out (api/auth.py), change password / delete account (api/account.py)
- step 3: upload / list / delete the artist's documents (api/documents.py)
"""

from fastapi import APIRouter, Depends, FastAPI

from api import account, auth, documents
from api.security import check_origin

app = FastAPI(
    title="OpenArt API",
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",  # also the input for the generated TypeScript types
    dependencies=[Depends(check_origin)],   # CSRF check on every request that changes data
)

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness check: answers as soon as the API process is up."""
    return {"status": "ok"}


app.include_router(router)
app.include_router(auth.router)
app.include_router(account.router)
app.include_router(documents.router)
