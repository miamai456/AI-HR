from datetime import date

from aihr.database import Base, create_engine_and_session
from aihr.models import (
    AiEffectivenessMetric,
    CohortConversionMetric,
    DailyFunnelMetric,
    FeatureDriftMetric,
    MonitoringAlert,
)
from aihr.seed import SyntheticHiringConfig, seed_demo_data
from aihr.services.marts import refresh_analytics_marts

MART_CONFIG = SyntheticHiringConfig(
    seed=20260722,
    n_candidates=500,
    n_jobs=90,
    n_recommendations=6_000,
    start_date=date(2026, 3, 25),
    end_date=date(2026, 4, 10),
)
METRIC_VERSION = "test_metric_v1"


def _seeded_session(tmp_path):
    engine, session_factory = create_engine_and_session(f"sqlite:///{tmp_path / 'marts.db'}")
    Base.metadata.create_all(engine)
    with session_factory() as session:
        seed_demo_data(session, config=MART_CONFIG)
    return engine, session_factory


def _assert_metric_contract(row) -> None:
    assert row.numerator is not None
    assert row.denominator is not None
    assert row.sample_size is not None
    assert 0 <= row.rate <= 1
    assert row.denominator >= row.numerator
    assert row.sample_size >= row.denominator
    assert row.period_start <= row.period_end
    assert row.data_origin == "synthetic_event_rollup"
    assert row.metric_version == METRIC_VERSION


def _count_version(session, model) -> int:
    return session.query(model).filter(model.metric_version == METRIC_VERSION).count()


def _first_version(session, model):
    return session.query(model).filter(model.metric_version == METRIC_VERSION).first()


def test_refresh_analytics_marts_builds_all_marts_with_metric_contract(tmp_path):
    engine, session_factory = _seeded_session(tmp_path)

    with session_factory() as session:
        result = refresh_analytics_marts(
            session,
            as_of_date=date(2026, 7, 15),
            metric_version=METRIC_VERSION,
        )

        assert result == {
            "mart_daily_funnel": _count_version(session, DailyFunnelMetric),
            "mart_cohort_conversion": _count_version(session, CohortConversionMetric),
            "mart_ai_effectiveness": _count_version(session, AiEffectivenessMetric),
            "mart_feature_drift": _count_version(session, FeatureDriftMetric),
            "mart_monitoring_alert": _count_version(session, MonitoringAlert),
        }
        assert all(count > 0 for count in result.values())

        _assert_metric_contract(_first_version(session, DailyFunnelMetric))
        _assert_metric_contract(_first_version(session, CohortConversionMetric))
        _assert_metric_contract(_first_version(session, AiEffectivenessMetric))
        _assert_metric_contract(_first_version(session, FeatureDriftMetric))
        _assert_metric_contract(_first_version(session, MonitoringAlert))

    engine.dispose()


def test_refresh_analytics_marts_is_idempotent_for_same_metric_version(tmp_path):
    engine, session_factory = _seeded_session(tmp_path)

    with session_factory() as session:
        first = refresh_analytics_marts(
            session,
            as_of_date=date(2026, 7, 15),
            metric_version=METRIC_VERSION,
        )
        second = refresh_analytics_marts(
            session,
            as_of_date=date(2026, 7, 15),
            metric_version=METRIC_VERSION,
        )

        assert second == first
        assert _count_version(session, DailyFunnelMetric) == first["mart_daily_funnel"]
        assert _count_version(session, CohortConversionMetric) == first["mart_cohort_conversion"]
        assert _count_version(session, AiEffectivenessMetric) == first["mart_ai_effectiveness"]
        assert _count_version(session, FeatureDriftMetric) == first["mart_feature_drift"]
        assert _count_version(session, MonitoringAlert) == first["mart_monitoring_alert"]

    engine.dispose()
