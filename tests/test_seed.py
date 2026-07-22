from sqlalchemy.orm import Session

from aihr.database import Base, create_engine_and_session
from aihr.seed import seed_demo_data


def test_seed_is_idempotent(tmp_path):
    engine, session_factory = create_engine_and_session(f"sqlite:///{tmp_path / 'seed.db'}")
    Base.metadata.create_all(engine)

    with session_factory() as session:
        assert seed_demo_data(session) > 0
        assert seed_demo_data(session) == 0

    engine.dispose()


def test_session_factory_returns_session(tmp_path):
    engine, session_factory = create_engine_and_session(f"sqlite:///{tmp_path / 'session.db'}")
    Base.metadata.create_all(engine)

    with session_factory() as session:
        assert isinstance(session, Session)

    engine.dispose()
