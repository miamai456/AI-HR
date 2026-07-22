from fastapi.testclient import TestClient

from aihr.api.main import app


def test_health_and_overview() -> None:
    with TestClient(app) as client:
        health = client.get("/api/v1/health")
        assert health.status_code == 200
        assert health.json()["database"] == "ok"

        overview = client.get("/api/v1/overview")
        assert overview.status_code == 200
        payload = overview.json()
        assert payload["summary"]["recommended"] > 0
        assert 0 <= payload["summary"]["interview_rate"] <= 1
        assert payload["data_origin"] == "synthetic"


def test_unadjusted_effectiveness() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/effectiveness/unadjusted")
        assert response.status_code == 200
        payload = response.json()
        assert payload["ai_sample_size"] > 0
        assert payload["human_sample_size"] > 0
        assert payload["confidence_interval_low"] <= payload["difference"]
        assert payload["difference"] <= payload["confidence_interval_high"]


def test_funnel_is_monotonic() -> None:
    with TestClient(app) as client:
        rows = client.get("/api/v1/funnel").json()
        assert {row["source"] for row in rows} == {"ai", "human"}
        for row in rows:
            values = [
                row["recommended"],
                row["contacted"],
                row["replied"],
                row["interviewed"],
                row["offered"],
                row["hired"],
            ]
            assert values == sorted(values, reverse=True)
