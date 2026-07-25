CREATE OR REPLACE VIEW mart_cohort_maturity AS
SELECT
  s.recommendation_month,
  s.source,
  s.job_category,
  s.job_region AS region,
  COUNT(*) AS recommended,
  SUM(CASE WHEN DATEDIFF(CURRENT_DATE, s.recommended_at) >= 30 THEN 1 ELSE 0 END)
    AS interview_matured_denominator,
  SUM(
    CASE
      WHEN DATEDIFF(CURRENT_DATE, s.recommended_at) >= 30
        AND interviewed.status = 'completed'
        AND TIMESTAMPDIFF(DAY, s.recommended_at, interviewed.event_at) <= 30
      THEN 1 ELSE 0
    END
  ) AS interviewed_within_30d,
  SUM(CASE WHEN DATEDIFF(CURRENT_DATE, s.recommended_at) >= 90 THEN 1 ELSE 0 END)
    AS hire_matured_denominator,
  SUM(
    CASE
      WHEN DATEDIFF(CURRENT_DATE, s.recommended_at) >= 90
        AND hired.status = 'completed'
        AND TIMESTAMPDIFF(DAY, s.recommended_at, hired.event_at) <= 90
      THEN 1 ELSE 0
    END
  ) AS hired_within_90d
FROM stg_recommendations s
LEFT JOIN fact_funnel_event interviewed
  ON s.recommendation_id = interviewed.recommendation_id AND interviewed.stage = 'interviewed'
LEFT JOIN fact_funnel_event hired
  ON s.recommendation_id = hired.recommendation_id AND hired.stage = 'hired'
GROUP BY s.recommendation_month, s.source, s.job_category, s.job_region;
