CREATE OR REPLACE VIEW stg_job_skills AS
SELECT
  job_link,
  NULLIF(TRIM(job_skills), '') AS job_skills
FROM raw_job_skills
WHERE job_link IS NOT NULL;
