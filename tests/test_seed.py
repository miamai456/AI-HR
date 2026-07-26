import pytest
from sqlalchemy import func
from sqlalchemy.orm import Session

from aihr.database import Base, create_engine_and_session
from aihr.models import (
    Candidate,
    DailyFunnelMetric,
    FunnelEvent,
    Job,
    ModelVersion,
    Recommendation,
    Recruiter,
)
from aihr.seed import SyntheticHiringConfig, detect_synthetic_scenarios, seed_demo_data

SMALL_SYNTHETIC_CONFIG = SyntheticHiringConfig(
    seed=20260722,
    n_candidates=500,
    n_jobs=90,
    n_recommendations=1_000,
)
LARGE_SYNTHETIC_CONFIG = SyntheticHiringConfig(
    seed=20260722,
    n_candidates=10_000,
    n_jobs=300,
    n_recommendations=100_000,
)
EXPECTED_STAGE_ORDER = ["recommended", "contacted", "replied", "interviewed", "offered", "hired"]


def _new_session_factory(tmp_path, name: str):
    engine, session_factory = create_engine_and_session(f"sqlite:///{tmp_path / name}")
    Base.metadata.create_all(engine)
    return engine, session_factory


@pytest.fixture(scope="module")
def large_synthetic_database(tmp_path_factory):
    database_path = tmp_path_factory.mktemp("synthetic") / "large_synthetic.db"
    engine, session_factory = create_engine_and_session(f"sqlite:///{database_path}")
    Base.metadata.create_all(engine)

    with session_factory() as session:
        seed_demo_data(session, config=LARGE_SYNTHETIC_CONFIG)

    yield session_factory

    engine.dispose()


def test_seed_is_idempotent(tmp_path):
    engine, session_factory = _new_session_factory(tmp_path, "seed.db")

    with session_factory() as session:
        assert seed_demo_data(session, config=SMALL_SYNTHETIC_CONFIG) > 0
        assert seed_demo_data(session, config=SMALL_SYNTHETIC_CONFIG) == 0

    engine.dispose()


def test_seed_creates_event_level_dataset(tmp_path):
    engine, session_factory = _new_session_factory(tmp_path, "events.db")

    with session_factory() as session:
        recommendation_count = seed_demo_data(session, config=SMALL_SYNTHETIC_CONFIG)
        assert recommendation_count > 0
        assert session.query(Candidate).count() > 0
        assert session.query(Job).count() > 0
        assert session.query(Recruiter).count() > 0
        assert session.query(ModelVersion).count() == 3
        assert session.query(Recommendation).count() == recommendation_count
        assert session.query(FunnelEvent).count() == recommendation_count * 6

        recommendation = session.query(Recommendation).first()
        stages = {
            event.stage: event.status
            for event in session.query(FunnelEvent).filter_by(
                recommendation_id=recommendation.recommendation_id
            )
        }
        assert stages["recommended"] == "completed"
        assert set(stages) == set(EXPECTED_STAGE_ORDER)

    engine.dispose()


def test_synthetic_generator_meets_mvp_volume(large_synthetic_database):
    with large_synthetic_database() as session:
        recommendation_count = session.query(Recommendation).count()

        assert recommendation_count >= 100_000
        assert session.query(FunnelEvent).count() == recommendation_count * 6


def test_synthetic_generator_is_reproducible_for_fixed_seed(tmp_path):
    summaries = []

    for database_name in ["synthetic_repro_a.db", "synthetic_repro_b.db"]:
        engine, session_factory = _new_session_factory(tmp_path, database_name)
        with session_factory() as session:
            seed_demo_data(session, config=SMALL_SYNTHETIC_CONFIG)
            summaries.append(
                session.query(
                    Recommendation.source,
                    func.count(Recommendation.recommendation_id),
                    func.round(func.avg(Recommendation.recommendation_score), 4),
                )
                .group_by(Recommendation.source)
                .order_by(Recommendation.source)
                .all()
            )
        engine.dispose()

    assert summaries[0] == summaries[1]


def test_synthetic_generator_preserves_funnel_event_order(large_synthetic_database):
    with large_synthetic_database() as session:
        sample_ids = [
            row[0]
            for row in session.query(Recommendation.recommendation_id)
            .order_by(Recommendation.recommendation_id)
            .limit(1000)
            .all()
        ]
        for recommendation_id in sample_ids:
            completed_events = (
                session.query(FunnelEvent)
                .filter_by(recommendation_id=recommendation_id, status="completed")
                .order_by(FunnelEvent.event_at)
                .all()
            )
            completed_stages = [event.stage for event in completed_events]
            assert completed_stages == [
                stage for stage in EXPECTED_STAGE_ORDER if stage in set(completed_stages)
            ]


def test_synthetic_generator_embeds_detectable_demo_scenarios(large_synthetic_database):
    with large_synthetic_database() as session:
        detected = detect_synthetic_scenarios(session)

    assert len([scenario for scenario, is_detected in detected.items() if is_detected]) >= 4
    assert detected["selection_bias"]
    assert detected["model_version_degradation"]
    assert detected["recruiter_contact_delay"]
    assert detected["feature_drift"]
    assert detected["immature_cohort"]


def test_metric_data_origin_values_fit_declared_column_width():
    data_origin_length = DailyFunnelMetric.__table__.c.data_origin.type.length

    assert len("synthetic") <= data_origin_length
    assert len("synthetic_event_rollup") <= data_origin_length


def test_session_factory_returns_session(tmp_path):
    engine, session_factory = create_engine_and_session(f"sqlite:///{tmp_path / 'session.db'}")
    Base.metadata.create_all(engine)

    with session_factory() as session:
        assert isinstance(session, Session)

    engine.dispose()
