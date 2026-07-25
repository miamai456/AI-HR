# Data Source Plan

AIHR's data layer will be split into real market data and experimental hiring outcomes.

## Source Choice

Primary source: Kaggle `1.3M LinkedIn Jobs & Skills 2024` zip.

Local files received:

| File | Raw table | Loaded rows |
|---|---:|---:|
| `data/raw/linkedin_job_postings.csv.zip` | `raw_linkedin_job_postings` | 1,348,454 |
| `data/raw/job_skills.csv.zip` | `raw_job_skills` | 1,296,381 |

Why this source:

- It is large enough to justify database storage and SQL marts.
- It contains real job-market fields such as job title, company, location, description, and skills.
- It supports useful analysis even before private ATS data exists: market demand, skill trends, location trends, company demand, salary coverage, and recommendation matching.

Boundary:

- Public job posting data is real.
- Candidate identities, recommendations, interviews, offers, and hires remain experimental unless the project receives a real ATS export.
- Dashboard labels must not describe experimental funnel outcomes as real hiring outcomes.

## Local File Convention

Place the downloaded Kaggle zip files here:

```text
data/raw/linkedin_job_postings.csv.zip
data/raw/job_skills.csv.zip
```

`data/raw/` is ignored by Git, so large raw files stay local.

## Load Flow

1. Inspect the zip:

```powershell
python scripts/import_kaggle_jobs.py data/raw/linkedin_jobs_skills_2024.zip --list
python scripts/import_kaggle_jobs.py data/raw/linkedin_job_postings.csv.zip data/raw/job_skills.csv.zip --list
```

2. Load CSV files into raw database tables:

```powershell
python scripts/import_kaggle_jobs.py data/raw/linkedin_jobs_skills_2024.zip --load
python scripts/import_kaggle_jobs.py data/raw/linkedin_job_postings.csv.zip data/raw/job_skills.csv.zip --load
```

3. Build staging models:

```text
raw_*
  -> raw_linkedin_job_postings / raw_job_skills
  -> stg_job_postings / stg_job_skills
  -> dim_job / dim_company / dim_skill / bridge_job_skill
  -> marts for dashboard and recommendation matching
```

Current raw tables are loaded into the local SQLite database `aihr.db`. The same script can target MySQL by passing `--database-url` or setting `AIHR_DATABASE_URL`.

Local validation result:

- Raw table load completed successfully.
- `raw_linkedin_job_postings.job_link`, `raw_linkedin_job_postings.first_seen`, and `raw_job_skills.job_link` have indexes.
- Staging views can return samples from the real data.
- Full `mart_job_market_overview` aggregation is heavy in SQLite at this data size; for production-style demos, build the mart in MySQL or materialize it as a table before the dashboard reads it.

## What Unlocks Next

After raw job data is loaded, AIHR can build:

- real job volume trends;
- job category and location distribution charts;
- skill demand rankings;
- company hiring activity views;
- TF-IDF or embedding-based job matching;
- drift analysis on job category, location, skills, and recommendation scores.
