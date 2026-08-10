from aihr.database import Base, create_engine_and_session
from aihr.jobs import prewarm_analysis_context_job
from aihr.seed import SyntheticHiringConfig, seed_demo_metrics
from aihr.services.analysis_snapshots import (
    DatabaseAnalysisSnapshotStore,
    get_dataset_version,
)


def test_analysis_prewarm_job_materializes_common_scopes(tmp_path) -> None:
    database_path = tmp_path / "worker.db"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    engine, session_factory = create_engine_and_session(database_url)
    Base.metadata.create_all(engine)
    with session_factory() as session:
        seed_demo_metrics(
            session,
            config=SyntheticHiringConfig(
                seed=42,
                n_candidates=300,
                n_jobs=54,
                n_recommendations=1_200,
            ),
        )
    engine.dispose()

    status = prewarm_analysis_context_job(
        database_url,
        "",
        "test",
        300,
        [{}, {"source": "ai"}, {"source": "human"}],
    )

    check_engine, check_session_factory = create_engine_and_session(database_url)
    with check_session_factory() as session:
        dataset_version = get_dataset_version(session)
    snapshot_status = DatabaseAnalysisSnapshotStore(check_session_factory).status(
        dataset_version
    )
    check_engine.dispose()

    assert status == {"status": "ready", "processed_scopes": 3, "errors": 0}
    assert snapshot_status["current_snapshots"] == 3
