from sqlalchemy.orm import Session

from aihr.database import Base, create_engine_and_session
from aihr.models import Candidate, FunnelEvent, Job, ModelVersion, Recommendation, Recruiter
from aihr.seed import seed_demo_data


def test_seed_is_idempotent(tmp_path):
    engine, session_factory = create_engine_and_session(f"sqlite:///{tmp_path / 'seed.db'}")
    Base.metadata.create_all(engine)

    with session_factory() as session:
        assert seed_demo_data(session) > 0
        assert seed_demo_data(session) == 0

    engine.dispose()


def test_seed_creates_event_level_dataset(tmp_path):
    engine, session_factory = create_engine_and_session(f"sqlite:///{tmp_path / 'events.db'}")
    Base.metadata.create_all(engine)

    with session_factory() as session:
        recommendation_count = seed_demo_data(session)
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
        assert set(stages) == {
            "recommended",
            "contacted",
            "replied",
            "interviewed",
            "offered",
            "hired",
        }

    engine.dispose()


def test_session_factory_returns_session(tmp_path):
    engine, session_factory = create_engine_and_session(f"sqlite:///{tmp_path / 'session.db'}")
    Base.metadata.create_all(engine)

    with session_factory() as session:
        assert isinstance(session, Session)

    engine.dispose()
