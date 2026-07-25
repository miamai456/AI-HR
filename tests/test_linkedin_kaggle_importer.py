import zipfile
from pathlib import Path

from aihr.data_sources.linkedin_kaggle import (
    RAW_POSTINGS_TABLE,
    RAW_SKILLS_TABLE,
    inspect_csv_zip,
    raw_table_for_zip,
)


def _write_zip(path: Path, csv_name: str, content: str) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(csv_name, content)


def test_inspect_csv_zip_reads_member_columns_and_samples(tmp_path: Path) -> None:
    zip_path = tmp_path / "linkedin_job_postings.csv.zip"
    _write_zip(
        zip_path,
        "linkedin_job_postings.csv",
        "job_link,job_title,company\nhttps://example.com/1,Analyst,Example Inc\n",
    )

    inspection = inspect_csv_zip(zip_path)

    assert inspection.csv_name == "linkedin_job_postings.csv"
    assert inspection.columns == ["job_link", "job_title", "company"]
    assert inspection.sample_rows == [
        {
            "job_link": "https://example.com/1",
            "job_title": "Analyst",
            "company": "Example Inc",
        }
    ]


def test_raw_table_for_zip_uses_stable_raw_layer_names() -> None:
    assert raw_table_for_zip(Path("linkedin_job_postings.csv.zip")) == RAW_POSTINGS_TABLE
    assert raw_table_for_zip(Path("job_skills.csv.zip")) == RAW_SKILLS_TABLE
