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
        assert health.json()["version"] == "0.1.0"

        ready = client.get("/api/v1/ready")
        assert ready.status_code == 200
        assert ready.json()["status"] == "ready"
        assert ready.json()["version"] == "0.1.0"
        assert ready.json()["checks"]["database"] == "ready"
        assert ready.json()["checks"]["assistant"] in {"configured", "optional"}

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
        assert len({point["period"] for point in payload["trend"]}) == 12
        assert "open_alerts" in payload

        monitoring = client.get("/api/v1/monitoring", params=params)
        assert monitoring.status_code == 200

        effectiveness = client.get("/api/v1/effectiveness/unadjusted", params=params)
        assert effectiveness.status_code == 200

        data_quality = client.get("/api/v1/data-quality", params=params)
        assert data_quality.status_code == 200
        assert data_quality.json()["checks"]


def test_unadjusted_effectiveness() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/effectiveness/unadjusted")
        assert response.status_code == 200
        payload = response.json()
        assert payload["ai_sample_size"] > 0
        assert payload["human_sample_size"] > 0
        assert payload["confidence_interval_low"] <= payload["difference"]
        assert payload["difference"] <= payload["confidence_interval_high"]


def test_effectiveness_reports_observational_adjustment_diagnostics() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/effectiveness/unadjusted")
        assert response.status_code == 200
        payload = response.json()

    assert payload["analysis_type"] == "observational_adjusted_association"
    assert payload["causal_claim"] is False
    assert payload["limitation_note"]
    assert payload["proportion_difference"] == payload["difference"]
    assert payload["adjusted_ai_rate"] is not None
    assert payload["adjusted_human_rate"] is not None
    assert payload["adjusted_difference"] is not None
    assert payload["propensity_method"] == "logistic_regression_iptw"
    assert payload["weighting_method"] == "stabilized_iptw"
    assert payload["extreme_weight_handling"]["method"] == "clip"
    assert payload["extreme_weight_handling"]["max_weight_after"] <= 10
    assert payload["common_support"]["has_overlap"] is True
    assert payload["common_support"]["retained_sample_size"] > 0
    assert payload["balance_diagnostics"]
    for row in payload["balance_diagnostics"]:
        assert {"covariate", "smd_before", "smd_after"} <= set(row)


def test_effectiveness_keeps_ai_and_human_comparison_when_source_filter_is_present() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/effectiveness/unadjusted", params={"source": "ai"})
        assert response.status_code == 200
        payload = response.json()

    assert payload["ai_sample_size"] > 0
    assert payload["human_sample_size"] > 0


def test_prediction_insights_reports_ml_model_explanation_and_anomalies() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/prediction-insights")
        assert response.status_code == 200
        payload = response.json()

    assert payload["model_summary"]["model_name"] == "logistic_regression_conversion"
    assert payload["model_summary"]["target"] == "interviewed"
    assert payload["model_summary"]["sample_size"] > 0
    assert 0 <= payload["model_summary"]["auc"] <= 1
    assert 0 <= payload["model_summary"]["accuracy"] <= 1
    assert payload["probability_bands"]
    assert payload["top_features"]
    assert payload["segment_performance"]
    assert payload["anomaly_findings"]
    assert payload["method_notes"]

    for band in payload["probability_bands"]:
        assert band["band"]
        assert band["recommendations"] >= 0
        assert 0 <= band["predicted_conversion_rate"] <= 1
        assert 0 <= band["actual_conversion_rate"] <= 1

    for feature in payload["top_features"]:
        assert feature["feature"]
        assert feature["direction"] in {"positive", "negative"}
        assert feature["importance"] >= 0


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


def test_monitoring_reports_model_version_trends_and_drift_diagnostics() -> None:
    with TestClient(app) as client:
        filters = client.get("/api/v1/meta/filters").json()
        params = {
            "model_version": filters["model_versions"][0],
            "job_category": filters["job_categories"][0],
            "region": filters["regions"][0],
        }
        response = client.get("/api/v1/monitoring", params=params)
        assert response.status_code == 200
        payload = response.json()

    assert payload["baseline_start"] <= payload["baseline_end"]
    assert payload["current_start"] <= payload["current_end"]
    assert payload["thresholds"]["psi"]["medium"] == 0.1
    assert payload["thresholds"]["jsd"]["high"] == 0.2
    assert payload["model_version_trends"]
    assert payload["drift_metrics"]

    trend = payload["model_version_trends"][0]
    assert {
        "period",
        "model_version",
        "job_category",
        "region",
        "recommendations",
        "traffic_share",
        "interview_rate",
    } <= set(trend)
    assert trend["model_version"] == params["model_version"]
    assert trend["job_category"] == params["job_category"]
    assert trend["region"] == params["region"]

    metric_types = {metric["metric_type"] for metric in payload["drift_metrics"]}
    assert {"psi", "jsd", "score_drift"} <= metric_types
    for metric in payload["drift_metrics"]:
        assert metric["severity"] in {"normal", "medium", "high"}
        assert metric["threshold_medium"] <= metric["threshold_high"]
        assert metric["baseline_sample_size"] >= 0
        assert metric["current_sample_size"] >= 0


def test_monitoring_reports_alert_and_anomaly_diagnostic_conclusions() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/monitoring")
        assert response.status_code == 200
        payload = response.json()

    conclusions = payload["diagnostic_conclusions"]
    assert conclusions
    categories = {row["category"] for row in conclusions}
    assert categories <= {
        "data_issue",
        "traffic_structure",
        "model",
        "recruiter_operation",
        "hiring_process",
    }
    assert "recruiter_operation" in categories
    assert {"effect_drop", "data_anomaly"} <= {row["conclusion_type"] for row in conclusions}

    for conclusion in conclusions:
        assert conclusion["severity"] in {"normal", "medium", "high"}
        assert conclusion["evidence_metric"]
        assert conclusion["baseline_value"] is not None
        assert conclusion["current_value"] is not None
        assert conclusion["period_start"] <= conclusion["period_end"]
        assert conclusion["baseline_sample_size"] >= 0
        assert conclusion["current_sample_size"] >= 0
        assert conclusion["sample_size"] == (
            conclusion["baseline_sample_size"] + conclusion["current_sample_size"]
        )
        breakdown = conclusion["breakdown"]
        assert {"job_category", "region", "recruiter_team", "model_version"} <= set(breakdown)


def test_monitoring_returns_empty_payload_for_empty_filter_combination() -> None:
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/monitoring",
            params={
                "start_date": "2026-01-01",
                "end_date": "2026-06-29",
                "source": "human",
                "job_category": "技术",
                "region": "华北",
                "model_version": "ai_ranker_2026_q2",
                "recruiter_team": "华东招聘组",
            },
        )
        assert response.status_code == 200
        payload = response.json()

    assert payload["current_end"] == "2026-06-29"
    assert payload["rows"] == []
    assert payload["model_version_trends"] == []
    assert payload["drift_metrics"] == []
    assert payload["diagnostic_conclusions"] == []


def test_data_quality_reports_structured_layer_freshness_and_checks() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/data-quality")
        assert response.status_code == 200
        payload = response.json()

    layers = payload["layers"]
    assert layers
    assert {"dim_candidate", "fact_recommendation", "fact_funnel_event"} <= {
        layer["layer_name"] for layer in layers
    }
    for layer in layers:
        assert layer["record_count"] >= 0
        assert layer["last_updated_at"] is None or "T" in layer["last_updated_at"]

    expected_check_types = {
        "duplicate_primary_key",
        "missing_critical_field",
        "orphan_event",
        "illegal_event_order",
        "future_timestamp",
        "negative_duration",
        "invalid_enum",
        "data_latency",
        "queue_maturity",
    }
    checks = payload["checks"]
    assert expected_check_types <= {check["check_type"] for check in checks}
    assert payload["summary"]["total_checks"] == len(checks)
    assert payload["summary"]["failed_checks"] == sum(
        1 for check in checks if check["status"] == "fail"
    )

    for check in checks:
        assert check["status"] in {"pass", "warn", "fail"}
        assert check["severity"] in {"normal", "medium", "high"}
        assert check["evidence_metric"]
        assert check["affected_count"] >= 0
        assert check["sample_size"] >= check["affected_count"]
        assert check["period_start"] <= check["period_end"]
        assert isinstance(check["details"], dict)


def test_data_quality_reports_freshness_duplicate_and_anomaly_ratio_alerts() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/data-quality")

    assert response.status_code == 200
    checks = {check["check_type"]: check for check in response.json()["checks"]}
    assert {"data_freshness", "duplicate_data", "anomaly_ratio"} <= set(checks)
    assert checks["data_freshness"]["details"]["latest_data_at"]
    assert checks["duplicate_data"]["evidence_metric"] == "duplicate_record_groups"
    assert 0 <= checks["anomaly_ratio"]["details"]["anomaly_ratio"] <= 1
