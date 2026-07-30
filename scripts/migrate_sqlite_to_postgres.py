from __future__ import annotations

import os
from collections.abc import Iterable
from io import StringIO

import pandas as pd
from sqlalchemy import Date, DateTime, create_engine, inspect, text
from sqlalchemy.engine import Engine

from aihr.database import Base
from aihr.models import (
    AiEffectivenessMetric,
    Candidate,
    CohortConversionMetric,
    DailyFunnelMetric,
    FeatureDriftMetric,
    FunnelEvent,
    Job,
    ModelVersion,
    MonitoringAlert,
    Recommendation,
    Recruiter,
)

SQLITE_URL = os.getenv("AIHR_SQLITE_URL", "sqlite+pysqlite:///./aihr.db")
POSTGRES_URL = os.environ["AIHR_POSTGRES_URL"]
CHUNK_SIZE = int(os.getenv("AIHR_MIGRATION_CHUNK_SIZE", "50000"))

MODEL_TABLES = [
    Candidate.__tablename__,
    Job.__tablename__,
    Recruiter.__tablename__,
    ModelVersion.__tablename__,
    Recommendation.__tablename__,
    FunnelEvent.__tablename__,
    DailyFunnelMetric.__tablename__,
    CohortConversionMetric.__tablename__,
    AiEffectivenessMetric.__tablename__,
    FeatureDriftMetric.__tablename__,
    MonitoringAlert.__tablename__,
]
RAW_TABLES = ["raw_job_skills", "raw_linkedin_job_postings"]


def _source_columns(engine: Engine, table_name: str) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns(table_name)}


def _target_columns(model) -> list[str]:
    return [column.name for column in model.__table__.columns]


def _model_for_table(table_name: str):
    return {
        Candidate.__tablename__: Candidate,
        Job.__tablename__: Job,
        Recruiter.__tablename__: Recruiter,
        ModelVersion.__tablename__: ModelVersion,
        Recommendation.__tablename__: Recommendation,
        FunnelEvent.__tablename__: FunnelEvent,
        DailyFunnelMetric.__tablename__: DailyFunnelMetric,
        CohortConversionMetric.__tablename__: CohortConversionMetric,
        AiEffectivenessMetric.__tablename__: AiEffectivenessMetric,
        FeatureDriftMetric.__tablename__: FeatureDriftMetric,
        MonitoringAlert.__tablename__: MonitoringAlert,
    }[table_name]


def _prepare_daily_funnel(chunk: pd.DataFrame) -> pd.DataFrame:
    if "metric_name" not in chunk:
        chunk["metric_name"] = "daily_interview_rate"
    if "numerator" not in chunk:
        chunk["numerator"] = chunk["interviewed"]
    if "denominator" not in chunk:
        chunk["denominator"] = chunk["recommended"]
    if "rate" not in chunk:
        chunk["rate"] = (chunk["numerator"] / chunk["denominator"]).fillna(0).round(6)
    if "sample_size" not in chunk:
        chunk["sample_size"] = chunk["recommended"]
    if "period_start" not in chunk:
        chunk["period_start"] = chunk["metric_date"]
    if "period_end" not in chunk:
        chunk["period_end"] = chunk["metric_date"]
    if "metric_version" not in chunk:
        chunk["metric_version"] = "seed_v1"
    return chunk


def _prepare_model_chunk(table_name: str, chunk: pd.DataFrame) -> pd.DataFrame:
    if table_name == DailyFunnelMetric.__tablename__:
        chunk = _prepare_daily_funnel(chunk)
    model = _model_for_table(table_name)
    target_columns = _target_columns(model)
    for column in target_columns:
        if column not in chunk:
            chunk[column] = None
    for column in model.__table__.columns:
        if column.name not in chunk:
            continue
        if isinstance(column.type, DateTime):
            chunk[column.name] = pd.to_datetime(chunk[column.name], errors="coerce")
        elif isinstance(column.type, Date):
            chunk[column.name] = pd.to_datetime(chunk[column.name], errors="coerce").dt.date
    return chunk[target_columns]


def _copy_chunk_to_postgres(
    target_engine: Engine,
    table_name: str,
    chunk: pd.DataFrame,
) -> None:
    buffer = StringIO()
    chunk.to_csv(buffer, index=False, header=False, na_rep="\\N")
    columns = ", ".join(f'"{column}"' for column in chunk.columns)
    copy_sql = (
        f'copy "{table_name}" ({columns}) '
        "from stdin with (format csv, null '\\N')"
    )
    raw_connection = target_engine.raw_connection()
    dbapi_connection = raw_connection.driver_connection
    try:
        with dbapi_connection.cursor() as cursor:
            with cursor.copy(copy_sql) as copy:
                copy.write(buffer.getvalue())
        dbapi_connection.commit()
    except Exception:
        dbapi_connection.rollback()
        raise
    finally:
        raw_connection.close()


def _copy_table(
    source_engine: Engine,
    target_engine: Engine,
    table_name: str,
    *,
    modeled: bool,
) -> int:
    total = 0
    for chunk in pd.read_sql_query(
        text(f'SELECT * FROM "{table_name}"'),
        source_engine,
        chunksize=CHUNK_SIZE,
    ):
        if modeled:
            chunk = _prepare_model_chunk(table_name, chunk)
        _copy_chunk_to_postgres(target_engine, table_name, chunk)
        total += len(chunk)
        print(f"{table_name}: copied {total}")
    return total


def _create_raw_table_from_source(
    source_engine: Engine,
    target_engine: Engine,
    table_name: str,
) -> None:
    source_columns = inspect(source_engine).get_columns(table_name)
    columns_sql = ", ".join(f'"{column["name"]}" text' for column in source_columns)
    with target_engine.begin() as connection:
        connection.execute(text(f'drop table if exists "{table_name}" cascade'))
        connection.execute(text(f'create table "{table_name}" ({columns_sql})'))


def _drop_existing_target_tables(target_engine: Engine) -> None:
    table_names = [*RAW_TABLES, *reversed(MODEL_TABLES)]
    with target_engine.begin() as connection:
        for table_name in table_names:
            connection.execute(text(f'drop table if exists "{table_name}" cascade'))


def _reset_sequences(target_engine: Engine, tables: Iterable[str]) -> None:
    inspector = inspect(target_engine)
    with target_engine.begin() as connection:
        for table_name in tables:
            columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column in ["id", "event_id"]:
                if column not in columns:
                    continue
                result = connection.execute(
                    text(
                        "select pg_get_serial_sequence(:table_name, :column_name)"
                    ),
                    {"table_name": table_name, "column_name": column},
                ).scalar()
                if not result:
                    continue
                connection.execute(
                    text(
                        f"""
                        select setval(
                            :sequence_name,
                            coalesce((select max("{column}") from "{table_name}"), 1),
                            true
                        )
                        """
                    ),
                    {"sequence_name": result},
                )


def main() -> None:
    source_engine = create_engine(SQLITE_URL)
    target_engine = create_engine(POSTGRES_URL)
    source_tables = set(inspect(source_engine).get_table_names())

    print(f"source={SQLITE_URL}")
    print(f"target={target_engine.url.render_as_string(hide_password=True)}")

    _drop_existing_target_tables(target_engine)
    Base.metadata.create_all(target_engine)

    copied: dict[str, int] = {}
    for table_name in MODEL_TABLES:
        if table_name not in source_tables:
            copied[table_name] = 0
            continue
        copied[table_name] = _copy_table(
            source_engine,
            target_engine,
            table_name,
            modeled=True,
        )

    for table_name in RAW_TABLES:
        if table_name not in source_tables:
            copied[table_name] = 0
            continue
        columns = _source_columns(source_engine, table_name)
        if not columns:
            copied[table_name] = 0
            continue
        _create_raw_table_from_source(source_engine, target_engine, table_name)
        copied[table_name] = _copy_table(
            source_engine,
            target_engine,
            table_name,
            modeled=False,
        )

    _reset_sequences(target_engine, MODEL_TABLES)

    print("migration complete")
    for table_name, count in copied.items():
        print(f"{table_name}={count}")

    source_engine.dispose()
    target_engine.dispose()


if __name__ == "__main__":
    main()
