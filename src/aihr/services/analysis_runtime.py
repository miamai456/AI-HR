from typing import Any

from aihr.services.analysis_context import AnalysisContextService
from aihr.services.analysis_snapshots import (
    DatabaseAnalysisSnapshotStore,
    get_dataset_version,
)
from aihr.services.analytics_effectiveness import get_effectiveness
from aihr.services.analytics_ml import get_prediction_insights
from aihr.services.analytics_monitoring import get_monitoring
from aihr.services.analytics_overview import get_overview
from aihr.services.analytics_quality import get_data_quality
from aihr.services.cache import JsonCache


def build_analysis_context_service(
    session_factory,
    cache: JsonCache,
    *,
    ttl_seconds: int,
) -> AnalysisContextService:
    snapshot_store = DatabaseAnalysisSnapshotStore(session_factory)

    def load_dataset_version() -> str:
        with session_factory() as session:
            return get_dataset_version(session)

    def load_analysis_context(filters: dict[str, Any]) -> dict:
        start_date = filters.get("start_date")
        end_date = filters.get("end_date")
        active_filters = {
            key: value
            for key, value in filters.items()
            if key not in {"start_date", "end_date"} and value is not None
        }
        with session_factory() as session:
            return {
                "analysis_scope": {
                    "start_date": start_date,
                    "end_date": end_date,
                    "filters": active_filters,
                },
                "overview": get_overview(session, **filters),
                "effectiveness": get_effectiveness(session, **filters),
                "monitoring": get_monitoring(session, **filters),
                "data_quality": get_data_quality(session, **filters),
                "prediction": get_prediction_insights(session, **filters),
            }

    return AnalysisContextService(
        load_analysis_context,
        cache,
        ttl_seconds=ttl_seconds,
        snapshot_store=snapshot_store,
        dataset_version_loader=load_dataset_version,
    )
