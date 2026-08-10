from aihr.services.prometheus_metrics import PrometheusMetrics


def test_prometheus_metrics_expose_http_cache_and_token_counters() -> None:
    metrics = PrometheusMetrics()
    metrics.record_http("GET", "/api/v1/ready", 200, 25)
    metrics.record_context(cached=True)
    metrics.record_assistant(mode="structured", success=True, tokens=42)

    payload = metrics.render().decode("utf-8")

    assert "aihr_http_requests_total" in payload
    assert 'path="/api/v1/ready"' in payload
    assert 'aihr_analysis_context_requests_total{cached="true"} 1.0' in payload
    assert "aihr_assistant_tokens_total 42.0" in payload
