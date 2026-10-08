"""
OpenArt — the web API (FastAPI).

The Next.js frontend forwards every /api/* request here (see web/next.config.ts),
so all routes live under /api. The interactive docs are at /api/docs.

Step 1 of the web app (workflow.MD, "Web app — plan"): only a health check,
to prove the frontend → API wiring and the deployment work.
"""

from fastapi import APIRouter, FastAPI

app = FastAPI(
    title="OpenArt API",
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",  # also the input for the generated TypeScript types
)

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness check: answers as soon as the API process is up."""
    return {"status": "ok"}


app.include_router(router)
