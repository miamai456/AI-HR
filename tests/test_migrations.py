from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_alembic_can_upgrade_downgrade_and_reapply(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "migration.db"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("AIHR_DATABASE_URL", database_url)
    config = Config("alembic.ini")

    command.upgrade(config, "head")
    engine = create_engine(database_url)
    tables = set(inspect(engine).get_table_names())
    assert {
        "alembic_version",
        "fact_recommendation",
        "system_data_version",
        "mart_analysis_context_snapshot",
    } <= tables
    assert "ix_recommendation_analysis_filters" in {
        index["name"] for index in inspect(engine).get_indexes("fact_recommendation")
    }
    assert "ix_funnel_event_analysis_lookup" in {
        index["name"] for index in inspect(engine).get_indexes("fact_funnel_event")
    }
    assert "ix_daily_funnel_analysis_filters" in {
        index["name"] for index in inspect(engine).get_indexes("mart_daily_funnel")
    }

    command.downgrade(config, "base")
    assert set(inspect(engine).get_table_names()) == {"alembic_version"}

    command.upgrade(config, "head")
    assert "mart_analysis_context_snapshot" in inspect(engine).get_table_names()
    engine.dispose()
