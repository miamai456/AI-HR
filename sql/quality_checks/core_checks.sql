SELECT 'fact_recommendation_pk_null' AS check_name, COUNT(*) AS failed_rows
FROM fact_recommendation
WHERE recommendation_id IS NULL;

SELECT 'funnel_event_duplicate_stage' AS check_name, COUNT(*) AS failed_rows
FROM (
  SELECT recommendation_id, stage, COUNT(*) AS row_count
  FROM fact_funnel_event
  GROUP BY recommendation_id, stage
  HAVING COUNT(*) > 1
) duplicates;

SELECT 'funnel_event_missing_recommended' AS check_name, COUNT(*) AS failed_rows
FROM fact_recommendation r
LEFT JOIN fact_funnel_event e
  ON r.recommendation_id = e.recommendation_id
  AND e.stage = 'recommended'
  AND e.status = 'completed'
WHERE e.recommendation_id IS NULL;

SELECT 'completed_event_without_time' AS check_name, COUNT(*) AS failed_rows
FROM fact_funnel_event
WHERE status = 'completed' AND event_at IS NULL;
