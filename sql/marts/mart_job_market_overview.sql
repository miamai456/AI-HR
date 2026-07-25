CREATE OR REPLACE VIEW mart_job_market_overview AS
SELECT
  p.first_seen_date,
  p.search_country,
  p.search_city,
  p.job_level,
  p.job_type,
  COUNT(*) AS job_postings,
  COUNT(DISTINCT p.company) AS companies,
  SUM(CASE WHEN s.job_skills IS NOT NULL THEN 1 ELSE 0 END) AS postings_with_skills
FROM stg_job_postings p
LEFT JOIN stg_job_skills s ON p.job_link = s.job_link
GROUP BY
  p.first_seen_date,
  p.search_country,
  p.search_city,
  p.job_level,
  p.job_type;
