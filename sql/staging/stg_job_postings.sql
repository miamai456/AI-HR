CREATE OR REPLACE VIEW stg_job_postings AS
SELECT
  job_link,
  NULLIF(TRIM(job_title), '') AS job_title,
  NULLIF(TRIM(company), '') AS company,
  NULLIF(TRIM(job_location), '') AS job_location,
  NULLIF(TRIM(search_city), '') AS search_city,
  NULLIF(TRIM(search_country), '') AS search_country,
  NULLIF(TRIM(search_position), '') AS search_position,
  NULLIF(TRIM(job_level), '') AS job_level,
  NULLIF(TRIM(job_type), '') AS job_type,
  DATE(first_seen) AS first_seen_date,
  last_processed_time,
  got_summary,
  got_ner,
  is_being_worked
FROM raw_linkedin_job_postings
WHERE job_link IS NOT NULL;
