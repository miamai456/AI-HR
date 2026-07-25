# Data Sources

AIHR uses the Kaggle `1.3M LinkedIn Jobs & Skills 2024` files as the real external job-market source.

## Local Files

Place these files in the project root:

| File | Role | Raw table |
|---|---|---|
| `linkedin_job_postings.csv.zip` | Job posting master data | `raw_linkedin_job_postings` |
| `job_skills.csv.zip` | Skills extracted per job posting | `raw_job_skills` |
| `dataset.csv` | Candidate resume/interview/JD decision samples | `raw_candidate_decisions` |

The LinkedIn job files join on `job_link`. `dataset.csv` is a separate algorithm evaluation source.

## Import

Inspect the zip files without importing:

```powershell
python -m aihr.data_sources.linkedin_kaggle --inspect-only
```

Import a small local sample first:

```powershell
python -m aihr.data_sources.linkedin_kaggle --limit 10000
```

Import the full dataset:

```powershell
python -m aihr.data_sources.linkedin_kaggle
```

By default the importer uses `AIHR_DATABASE_URL` from `.env`, or `sqlite+pysqlite:///./aihr.db`.
For MySQL, set `AIHR_DATABASE_URL` before running the import.

## Modeling Boundary

The Kaggle files are real job-market data. They are suitable for:

- job volume analysis
- company and location analysis
- job level and work mode analysis
- skills analysis
- market drift monitoring
- recommendation matching experiments

`dataset.csv` is suitable for resume/JD/interview text modeling because it includes a decision label. It should not be treated as a full enterprise ATS event log because it does not include recommendation timestamps, recruiter workflow timestamps, offer events, or hire events.

The LinkedIn files are not real ATS funnel data. AIHR must continue to label recommendation, interview, offer, and hire funnel outcomes as synthetic or experimental unless a private authorized ATS source is connected.

## Database Layers

| Layer | Object | Purpose |
|---|---|---|
| raw | `raw_linkedin_job_postings` | One row per job posting record from Kaggle |
| raw | `raw_job_skills` | Skills string joined to postings by `job_link` |
| raw | `raw_candidate_decisions` | One row per candidate decision sample from `dataset.csv` |
| staging | `stg_linkedin_jobs` | Cleaned joined job posting view |
| mart | `mart_job_market_daily` | Daily job-market volume by country, city, role, level, and work mode |

The current importer creates raw tables with pandas `to_sql`. The SQL files document the intended schema and downstream views for MySQL-style deployment.
