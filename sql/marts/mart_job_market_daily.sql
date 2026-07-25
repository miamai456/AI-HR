CREATE OR REPLACE VIEW mart_job_market_daily AS
SELECT
  first_seen AS metric_date,
  search_country,
  search_city,
  search_position,
  job_level,
  work_mode,
  COUNT(*) AS posting_count,
  COUNT(DISTINCT company) AS company_count
FROM stg_linkedin_jobs
WHERE first_seen IS NOT NULL
GROUP BY
  first_seen,
  search_country,
  search_city,
  search_position,
  job_level,
  work_mode;
