from __future__ import annotations

import argparse
import csv
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from aihr.config import get_settings

RAW_POSTINGS_TABLE = "raw_linkedin_job_postings"
RAW_SKILLS_TABLE = "raw_job_skills"


@dataclass(frozen=True)
class CsvZipInspection:
    zip_path: Path
    csv_name: str
    columns: list[str]
    sample_rows: list[dict[str, str]]


def raw_table_for_zip(zip_path: Path) -> str:
    name = zip_path.name.lower()
    if name == "linkedin_job_postings.csv.zip":
        return RAW_POSTINGS_TABLE
    if name == "job_skills.csv.zip":
        return RAW_SKILLS_TABLE
    raise ValueError(f"Unsupported Kaggle LinkedIn zip file: {zip_path.name}")


def inspect_csv_zip(zip_path: Path, sample_size: int = 3) -> CsvZipInspection:
    if not zip_path.exists():
        raise FileNotFoundError(zip_path)

    with zipfile.ZipFile(zip_path) as archive:
        csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(csv_names) != 1:
            raise ValueError(f"Expected exactly one CSV in {zip_path.name}, found {csv_names}")

        csv_name = csv_names[0]
        with archive.open(csv_name) as raw_file:
            reader = csv.DictReader(line.decode("utf-8-sig") for line in raw_file)
            columns = list(reader.fieldnames or [])
            sample_rows = []
            for row in reader:
                sample_rows.append(dict(row))
                if len(sample_rows) >= sample_size:
                    break

    return CsvZipInspection(
        zip_path=zip_path,
        csv_name=csv_name,
        columns=columns,
        sample_rows=sample_rows,
    )


def _normalized_columns(columns: list[str]) -> list[str]:
    return [column.strip().lower().replace(" ", "_") for column in columns]


def _create_indexes(database_url: str) -> None:
    engine = create_engine(database_url)
    dialect = engine.dialect.name
    statements = [
        (
            "idx_raw_linkedin_job_postings_link",
            RAW_POSTINGS_TABLE,
            "job_link",
        ),
        (
            "idx_raw_linkedin_job_postings_seen",
            RAW_POSTINGS_TABLE,
            "first_seen",
        ),
        (
            "idx_raw_job_skills_link",
            RAW_SKILLS_TABLE,
            "job_link",
        ),
    ]

    with engine.begin() as connection:
        for index_name, table_name, column_name in statements:
            if dialect == "sqlite":
                sql = (
                    f"CREATE INDEX IF NOT EXISTS {index_name} "
                    f"ON {table_name} ({column_name})"
                )
            else:
                sql = f"CREATE INDEX {index_name} ON {table_name} ({column_name})"
            try:
                connection.execute(text(sql))
            except SQLAlchemyError:
                if dialect == "sqlite":
                    raise
    engine.dispose()


def import_csv_zip_to_raw_table(
    database_url: str,
    zip_path: Path,
    table_name: str,
    chunk_size: int = 50_000,
    limit: int | None = None,
) -> int:
    if not zip_path.exists():
        raise FileNotFoundError(zip_path)

    engine = create_engine(database_url)
    imported_rows = 0
    imported_at = datetime.now(timezone.utc).isoformat()
    if_exists = "replace"

    for chunk in pd.read_csv(zip_path, compression="zip", dtype=str, chunksize=chunk_size):
        if limit is not None:
            remaining = limit - imported_rows
            if remaining <= 0:
                break
            chunk = chunk.head(remaining)

        chunk.columns = _normalized_columns(list(chunk.columns))
        chunk["aihr_imported_at"] = imported_at
        chunk.to_sql(table_name, engine, if_exists=if_exists, index=False, chunksize=5_000)
        imported_rows += len(chunk)
        if_exists = "append"

    engine.dispose()
    return imported_rows


def import_linkedin_kaggle_dataset(
    database_url: str,
    postings_zip: Path,
    skills_zip: Path,
    chunk_size: int = 50_000,
    limit: int | None = None,
) -> dict[str, int]:
    results = {
        RAW_POSTINGS_TABLE: import_csv_zip_to_raw_table(
            database_url=database_url,
            zip_path=postings_zip,
            table_name=RAW_POSTINGS_TABLE,
            chunk_size=chunk_size,
            limit=limit,
        ),
        RAW_SKILLS_TABLE: import_csv_zip_to_raw_table(
            database_url=database_url,
            zip_path=skills_zip,
            table_name=RAW_SKILLS_TABLE,
            chunk_size=chunk_size,
            limit=limit,
        ),
    }
    _create_indexes(database_url)
    return results


def _print_inspection(inspection: CsvZipInspection) -> None:
    print(f"{inspection.zip_path.name}:")
    print(f"  csv: {inspection.csv_name}")
    print(f"  raw_table: {raw_table_for_zip(inspection.zip_path)}")
    print(f"  columns: {', '.join(inspection.columns)}")
    print(f"  sample_rows: {len(inspection.sample_rows)}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import Kaggle LinkedIn jobs data into AIHR raw tables."
    )
    parser.add_argument("--postings-zip", default="linkedin_job_postings.csv.zip")
    parser.add_argument("--skills-zip", default="job_skills.csv.zip")
    parser.add_argument("--database-url", default=get_settings().database_url)
    parser.add_argument("--chunk-size", type=int, default=50_000)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--inspect-only", action="store_true")
    args = parser.parse_args()

    postings_zip = Path(args.postings_zip)
    skills_zip = Path(args.skills_zip)
    inspections = [inspect_csv_zip(postings_zip), inspect_csv_zip(skills_zip)]

    for inspection in inspections:
        _print_inspection(inspection)

    if args.inspect_only:
        return

    results = import_linkedin_kaggle_dataset(
        database_url=args.database_url,
        postings_zip=postings_zip,
        skills_zip=skills_zip,
        chunk_size=args.chunk_size,
        limit=args.limit,
    )
    for table_name, row_count in results.items():
        print(f"imported {row_count} rows into {table_name}")


if __name__ == "__main__":
    main()
