from aihr.services.analysis_context import AnalysisContextService
from aihr.services.cache import MemoryJsonCache


def test_analysis_context_service_reuses_filter_snapshot() -> None:
    calls = []

    def loader(filters):
        calls.append(filters)
        return {"overview": {"summary": {"recommended": 120}}}

    service = AnalysisContextService(loader, MemoryJsonCache(), ttl_seconds=300)

    first, first_cached, first_latency = service.get({"source": "ai"})
    second, second_cached, second_latency = service.get({"source": "ai"})

    assert first == second
    assert calls == [{"source": "ai"}]
    assert first_cached is False
    assert first_latency >= 1
    assert second_cached is True
    assert second_latency == 0


def test_analysis_context_service_can_prewarm_common_scopes() -> None:
    calls = []
    service = AnalysisContextService(
        lambda filters: calls.append(filters) or {"scope": filters},
        MemoryJsonCache(),
        ttl_seconds=300,
    )

    service.prewarm([{}, {"source": "ai"}, {"source": "human"}])

    assert calls == [{}, {"source": "ai"}, {"source": "human"}]
    assert service.get({"source": "ai"})[1] is True
    assert service.status() == {"status": "ready", "processed_scopes": 3, "errors": 0}


def test_analysis_context_service_reads_materialized_snapshot_before_loader() -> None:
    class SnapshotStore:
        def get(self, filters, dataset_version):
            assert dataset_version == "dataset-v1"
            return {"scope": filters, "materialized": True}

        def set(self, filters, dataset_version, value):
            raise AssertionError("existing snapshot should not be replaced")

    service = AnalysisContextService(
        lambda filters: (_ for _ in ()).throw(AssertionError("loader should not run")),
        MemoryJsonCache(),
        ttl_seconds=300,
        snapshot_store=SnapshotStore(),
        dataset_version_loader=lambda: "dataset-v1",
    )

    context, cached, latency_ms = service.get({"source": "ai"})

    assert context["materialized"] is True
    assert cached is True
    assert latency_ms == 0
