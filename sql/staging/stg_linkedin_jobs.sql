CREATE OR REPLACE VIEW stg_linkedin_jobs AS
SELECT
  p.job_link,
  p.job_title,
  p.company,
  p.job_location,
  p.first_seen,
  p.search_city,
  p.search_country,
  p.search_position,
  p.job_level,
  p.job_type,
  s.job_skills,
  CASE
    WHEN LOWER(p.job_type) LIKE '%remote%' THEN 'remote'
    WHEN LOWER(p.job_type) LIKE '%hybrid%' THEN 'hybrid'
    WHEN LOWER(p.job_type) LIKE '%onsite%' THEN 'onsite'
    ELSE 'unknown'
  END AS work_mode
FROM raw_linkedin_job_postings p
LEFT JOIN raw_job_skills s ON p.job_link = s.job_link
WHERE p.job_link IS NOT NULL;
