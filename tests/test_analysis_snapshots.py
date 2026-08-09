from aihr.database import Base, create_engine_and_session
from aihr.services.analysis_snapshots import (
    DatabaseAnalysisSnapshotStore,
    bump_dataset_version,
    get_dataset_version,
)


def test_dataset_version_changes_only_when_explicitly_bumped() -> None:
    engine, session_factory = create_engine_and_session("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with session_factory() as session:
        initial = get_dataset_version(session)
        changed = bump_dataset_version(session, reason="test_import")
        session.commit()
    with session_factory() as session:
        persisted = get_dataset_version(session)

    assert initial == "unversioned"
    assert changed != initial
    assert persisted == changed


def test_database_snapshot_store_survives_service_instances() -> None:
    engine, session_factory = create_engine_and_session("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    store = DatabaseAnalysisSnapshotStore(session_factory)
    filters = {"source": "ai"}

    store.set(filters, "dataset-v1", {"overview": {"recommended": 120}})

    second_store = DatabaseAnalysisSnapshotStore(session_factory)
    assert second_store.get(filters, "dataset-v1") == {
        "overview": {"recommended": 120}
    }
    assert second_store.get(filters, "dataset-v2") is None
