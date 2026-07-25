CREATE OR REPLACE VIEW mart_daily_funnel_from_events AS
SELECT
  s.recommended_date AS metric_date,
  s.source,
  s.job_category,
  s.job_region AS region,
  COUNT(*) AS recommended,
  SUM(CASE WHEN contacted.status = 'completed' THEN 1 ELSE 0 END) AS contacted,
  SUM(CASE WHEN replied.status = 'completed' THEN 1 ELSE 0 END) AS replied,
  SUM(CASE WHEN interviewed.status = 'completed' THEN 1 ELSE 0 END) AS interviewed,
  SUM(CASE WHEN offered.status = 'completed' THEN 1 ELSE 0 END) AS offered,
  SUM(CASE WHEN hired.status = 'completed' THEN 1 ELSE 0 END) AS hired,
  'event_rollup' AS data_origin
FROM stg_recommendations s
LEFT JOIN fact_funnel_event contacted
  ON s.recommendation_id = contacted.recommendation_id AND contacted.stage = 'contacted'
LEFT JOIN fact_funnel_event replied
  ON s.recommendation_id = replied.recommendation_id AND replied.stage = 'replied'
LEFT JOIN fact_funnel_event interviewed
  ON s.recommendation_id = interviewed.recommendation_id AND interviewed.stage = 'interviewed'
LEFT JOIN fact_funnel_event offered
  ON s.recommendation_id = offered.recommendation_id AND offered.stage = 'offered'
LEFT JOIN fact_funnel_event hired
  ON s.recommendation_id = hired.recommendation_id AND hired.stage = 'hired'
GROUP BY s.recommended_date, s.source, s.job_category, s.job_region;
