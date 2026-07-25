SELECT 'job_postings_missing_job_link' AS check_name, COUNT(*) AS failed_rows
FROM raw_linkedin_job_postings
WHERE job_link IS NULL OR TRIM(job_link) = '';

SELECT 'job_skills_missing_job_link' AS check_name, COUNT(*) AS failed_rows
FROM raw_job_skills
WHERE job_link IS NULL OR TRIM(job_link) = '';

SELECT 'job_postings_duplicate_job_link' AS check_name, COUNT(*) AS failed_rows
FROM (
  SELECT job_link, COUNT(*) AS row_count
FROM raw_linkedin_job_postings
  GROUP BY job_link
  HAVING COUNT(*) > 1
) duplicates;

SELECT 'skill_rows_without_posting' AS check_name, COUNT(*) AS failed_rows
FROM raw_job_skills s
LEFT JOIN raw_linkedin_job_postings p ON s.job_link = p.job_link
WHERE p.job_link IS NULL;
