from aihr.services.metrics import MetricsRegistry


def test_metrics_registry_reports_latency_cache_tokens_and_errors() -> None:
    metrics = MetricsRegistry(max_samples=10)
    metrics.record("assistant", latency_ms=100, success=True, cached=False, tokens=20)
    metrics.record("assistant", latency_ms=20, success=True, cached=True, tokens=0)
    metrics.record("assistant", latency_ms=500, success=False, error_code="429")

    snapshot = metrics.snapshot()["assistant"]

    assert snapshot["count"] == 3
    assert snapshot["success_rate"] == 2 / 3
    assert snapshot["cache_hit_rate"] == 0.5
    assert snapshot["latency_ms"]["p50"] == 100
    assert snapshot["latency_ms"]["p95"] == 500
    assert snapshot["total_tokens"] == 20
    assert snapshot["errors"] == {"429": 1}
