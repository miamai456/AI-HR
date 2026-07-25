CREATE OR REPLACE VIEW stg_recommendations AS
SELECT
  r.recommendation_id,
  r.candidate_id,
  r.job_id,
  r.recruiter_id,
  r.model_version_id,
  r.source,
  r.recommendation_score,
  r.recommended_at,
  DATE(r.recommended_at) AS recommended_date,
  DATE_FORMAT(r.recommended_at, '%Y-%m-01') AS recommendation_month,
  c.region AS candidate_region,
  c.experience_years,
  c.education_level,
  j.job_category,
  j.region AS job_region,
  j.seniority_level,
  m.model_version
FROM fact_recommendation r
JOIN dim_candidate c ON r.candidate_id = c.candidate_id
JOIN dim_job j ON r.job_id = j.job_id
JOIN dim_model_version m ON r.model_version_id = m.model_version_id;
