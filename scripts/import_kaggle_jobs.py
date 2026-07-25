from __future__ import annotations

import argparse
import re
import zipfile
from pathlib import Path

import pandas as pd

from aihr.config import get_settings
from aihr.database import create_engine_and_session


def csv_members(zip_path: Path) -> list[str]:
    with zipfile.ZipFile(zip_path) as archive:
        return sorted(
            member
            for member in archive.namelist()
            if member.lower().endswith(".csv") and not member.endswith("/")
        )


def raw_table_name(member: str) -> str:
    stem = Path(member).stem.lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", stem).strip("_")
    if normalized.startswith("linkedin_"):
        normalized = normalized.removeprefix("linkedin_")
    if normalized == "job_postings":
        return "raw_linkedin_job_postings"
    if normalized == "job_skills":
        return "raw_job_skills"
    return f"raw_linkedin_{normalized}"


def load_zip_to_database(zip_paths: list[Path], database_url: str, chunksize: int = 50_000) -> None:
    engine, _ = create_engine_and_session(database_url)
    try:
        for zip_path in zip_paths:
            members = csv_members(zip_path)
            if not members:
                raise ValueError(f"No CSV files found in {zip_path}")

            with zipfile.ZipFile(zip_path) as archive:
                for member in members:
                    table_name = raw_table_name(member)
                    print(f"Loading {zip_path.name}:{member} -> {table_name}")
                    with archive.open(member) as csv_file:
                        reader = pd.read_csv(csv_file, chunksize=chunksize, low_memory=False)
                        for chunk_index, chunk in enumerate(reader):
                            mode = "replace" if chunk_index == 0 else "append"
                            chunk.to_sql(table_name, engine, if_exists=mode, index=False)
                            print(f"  wrote chunk {chunk_index + 1}: {len(chunk)} rows")
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect or load Kaggle LinkedIn jobs zip data.")
    parser.add_argument("zip_paths", nargs="+", type=Path)
    parser.add_argument("--list", action="store_true", help="List CSV files inside the zip.")
    parser.add_argument(
        "--load",
        action="store_true",
        help="Load CSV files into raw database tables.",
    )
    parser.add_argument("--database-url", default=None, help="Override AIHR_DATABASE_URL.")
    parser.add_argument("--chunksize", type=int, default=50_000)
    args = parser.parse_args()

    for zip_path in args.zip_paths:
        if not zip_path.exists():
            raise FileNotFoundError(f"Zip file not found: {zip_path}")

    if args.list:
        for zip_path in args.zip_paths:
            for member in csv_members(zip_path):
                print(f"{zip_path.name}:{member} -> {raw_table_name(member)}")

    if args.load:
        database_url = args.database_url or get_settings().database_url
        load_zip_to_database(args.zip_paths, database_url, args.chunksize)

    if not args.list and not args.load:
        parser.error("Choose --list or --load.")


if __name__ == "__main__":
    main()
