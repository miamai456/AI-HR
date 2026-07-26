from fastapi.testclient import TestClient

from aihr.api.main import app, database_backend_for_url


def test_database_backend_for_url_reports_driver_backend() -> None:
    assert database_backend_for_url("sqlite+pysqlite:///./aihr.db") == "sqlite"
    assert (
        database_backend_for_url("postgresql+psycopg://aihr_app:345678@localhost:5432/aihr")
        == "postgresql"
    )


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


def test_overview_supports_unified_filters_and_executive_metrics() -> None:
    with TestClient(app) as client:
        filters = client.get("/api/v1/meta/filters")
        assert filters.status_code == 200
        options = filters.json()
        assert options["model_versions"]
        assert options["recruiter_teams"]

        params = {
            "start_date": options["date_min"],
            "end_date": options["date_max"],
            "source": "ai",
            "job_category": options["job_categories"][0],
            "region": options["regions"][0],
            "model_version": options["model_versions"][0],
            "recruiter_team": options["recruiter_teams"][0],
        }
        response = client.get("/api/v1/overview", params=params)
        assert response.status_code == 200
        payload = response.json()

        summary = payload["summary"]
        assert 0 <= summary["ai_share"] <= 1
        assert 0 <= summary["qualified_interview_30d_rate"] <= 1
        assert 0 <= summary["mature_queue_hire_rate"] <= 1
        assert len({point["period"] for point in payload["trend"]}) <= 12
        assert "open_alerts" in payload

        monitoring = client.get("/api/v1/monitoring", params=params)
        assert monitoring.status_code == 200

        effectiveness = client.get("/api/v1/effectiveness/unadjusted", params=params)
        assert effectiveness.status_code == 200


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
