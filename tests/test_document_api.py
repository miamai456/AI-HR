from fastapi.testclient import TestClient

from aihr.api.main import create_app
from aihr.services.document_store import InMemoryDocumentStore


def test_document_api_saves_redacted_content_and_returns_it_by_id() -> None:
    app = create_app(
        "sqlite+pysqlite:///:memory:",
        document_store=InMemoryDocumentStore(),
    )

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/documents",
            json={
                "document_type": "job",
                "source_id": "ats-job-17",
                "title": "Senior data engineer",
                "content": "Contact owner@example.com or 13912345678. Python SQL required.",
                "metadata": {"postgres_job_id": 17},
            },
        )
        fetched = client.get(f"/api/v1/documents/{created.json()['document_id']}")

    assert created.status_code == 201
    assert fetched.status_code == 200
    payload = fetched.json()
    assert payload["source_id"] == "ats-job-17"
    assert payload["metadata"] == {"postgres_job_id": 17}
    assert "owner@example.com" not in payload["content"]
    assert "13912345678" not in payload["content"]


def test_document_api_exposes_search_and_backend_health() -> None:
    app = create_app(
        "sqlite+pysqlite:///:memory:",
        document_store=InMemoryDocumentStore(),
    )

    with TestClient(app) as client:
        client.post(
            "/api/v1/documents",
            json={
                "document_type": "knowledge_chunk",
                "source_id": "metric-dictionary#hire-rate",
                "title": "Hire rate definition",
                "content": "Hire rate uses the mature recommendation cohort.",
            },
        )
        search = client.get(
            "/api/v1/documents/search",
            params={"query": "mature cohort", "document_type": "knowledge_chunk"},
        )
        status = client.get("/api/v1/documents/status")

    assert search.status_code == 200
    assert search.json()["results"][0]["document"]["source_id"] == (
        "metric-dictionary#hire-rate"
    )
    assert status.json() == {"status": "available", "backend": "memory", "detail": ""}
