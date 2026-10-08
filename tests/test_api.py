"""Web API: step 1 only has the health check."""

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_docs_live_under_api():
    # the frontend only forwards /api/*, so the docs and schema must be there too
    assert client.get("/api/docs").status_code == 200
    assert client.get("/api/openapi.json").status_code == 200
