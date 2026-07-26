from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from aihr.models import (
    AiEffectivenessMetric,
    Candidate,
    CohortConversionMetric,
    DailyFunnelMetric,
    FeatureDriftMetric,
    FunnelEvent,
    Job,
    MonitoringAlert,
    Recommendation,
)

STAGE_COLUMNS = {
    "contacted": "contacted",
    "replied": "replied",
    "interviewed": "interviewed",
    "offered": "offered",
    "hired": "hired",
}
DATA_ORIGIN = "synthetic_event_rollup"


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _date_floor(value: datetime) -> date:
    return value.date()


def _month_floor(value: date) -> date:
    return date(value.year, value.month, 1)


def _delete_metric_version(session: Session, metric_version: str) -> None:
    for model in [
        DailyFunnelMetric,
        CohortConversionMetric,
        AiEffectivenessMetric,
        FeatureDriftMetric,
        MonitoringAlert,
    ]:
        session.execute(delete(model).where(model.metric_version == metric_version))


def _recommendation_stage_map(session: Session) -> dict[str, dict[str, object]]:
    recommendations = (
        session.query(
            Recommendation.recommendation_id,
            Recommendation.source,
            Recommendation.recommended_at,
            Recommendation.recommendation_score,
            Candidate.experience_years,
            Job.job_category,
            Job.region,
        )
        .join(Candidate, Recommendation.candidate_id == Candidate.candidate_id)
        .join(Job, Recommendation.job_id == Job.job_id)
        .all()
    )
    records = {
        row.recommendation_id: {
            "recommendation_id": row.recommendation_id,
            "source": row.source,
            "recommended_at": row.recommended_at,
            "recommendation_score": row.recommendation_score,
            "experience_years": row.experience_years,
            "job_category": row.job_category,
            "region": row.region,
            "stages": {"recommended": True},
        }
        for row in recommendations
    }

    events = (
        session.query(FunnelEvent.recommendation_id, FunnelEvent.stage, FunnelEvent.status)
        .filter(FunnelEvent.status == "completed")
        .all()
    )
    for recommendation_id, stage, _ in events:
        if recommendation_id in records:
            records[recommendation_id]["stages"][stage] = True
    return records


def _build_daily_funnel(
    records: dict[str, dict[str, object]],
    metric_version: str,
) -> list[dict[str, object]]:
    grouped = defaultdict(lambda: defaultdict(int))
    for record in records.values():
        metric_date = _date_floor(record["recommended_at"])
        key = (metric_date, record["source"], record["job_category"], record["region"])
        grouped[key]["recommended"] += 1
        stages = record["stages"]
        for stage, column in STAGE_COLUMNS.items():
            if stages.get(stage):
                grouped[key][column] += 1

    rows = []
    for (metric_date, source, job_category, region), counts in grouped.items():
        recommended = counts["recommended"]
        interviewed = counts["interviewed"]
        rows.append(
            {
                "metric_date": metric_date,
                "source": source,
                "job_category": job_category,
                "region": region,
                "metric_name": "daily_interview_rate",
                "numerator": interviewed,
                "denominator": recommended,
                "rate": _rate(interviewed, recommended),
                "sample_size": recommended,
                "period_start": metric_date,
                "period_end": metric_date,
                "recommended": recommended,
                "contacted": counts["contacted"],
                "replied": counts["replied"],
                "interviewed": interviewed,
                "offered": counts["offered"],
                "hired": counts["hired"],
                "data_origin": DATA_ORIGIN,
                "metric_version": metric_version,
            }
        )
    return rows


def _build_cohort_conversion(
    records: dict[str, dict[str, object]],
    as_of_date: date,
    metric_version: str,
) -> list[dict[str, object]]:
    grouped = defaultdict(lambda: defaultdict(int))
    for record in records.values():
        recommended_at = _date_floor(record["recommended_at"])
        cohort_month = _month_floor(recommended_at)
        is_mature = recommended_at <= as_of_date - timedelta(days=30)
        key = (cohort_month, record["source"], record["job_category"], record["region"])
        grouped[key]["sample_size"] += 1
        if is_mature:
            grouped[key]["denominator"] += 1
            if record["stages"].get("interviewed"):
                grouped[key]["numerator"] += 1

    rows = []
    for (cohort_month, source, job_category, region), counts in grouped.items():
        numerator = counts["numerator"]
        denominator = counts["denominator"]
        rows.append(
            {
                "cohort_month": cohort_month,
                "source": source,
                "job_category": job_category,
                "region": region,
                "metric_name": "30d_interview_mature_rate",
                "numerator": numerator,
                "denominator": denominator,
                "rate": _rate(numerator, denominator),
                "sample_size": counts["sample_size"],
                "period_start": cohort_month,
                "period_end": as_of_date,
                "data_origin": DATA_ORIGIN,
                "metric_version": metric_version,
            }
        )
    return rows


def _build_ai_effectiveness(
    records: dict[str, dict[str, object]],
    metric_version: str,
) -> list[dict[str, object]]:
    grouped = defaultdict(lambda: defaultdict(int))
    period_start = min(_date_floor(record["recommended_at"]) for record in records.values())
    period_end = max(_date_floor(record["recommended_at"]) for record in records.values())

    for record in records.values():
        key = (record["job_category"], record["region"], record["source"])
        grouped[key]["denominator"] += 1
        if record["stages"].get("interviewed"):
            grouped[key]["numerator"] += 1

    rows = []
    segments = {(job_category, region) for job_category, region, _ in grouped}
    for job_category, region in segments:
        ai = grouped[(job_category, region, "ai")]
        human = grouped[(job_category, region, "human")]
        ai_rate = _rate(ai["numerator"], ai["denominator"])
        human_rate = _rate(human["numerator"], human["denominator"])
        sample_size = ai["denominator"] + human["denominator"]
        if not ai["denominator"] or not human["denominator"]:
            continue
        rows.append(
            {
                "job_category": job_category,
                "region": region,
                "metric_name": "ai_vs_human_interview_rate",
                "numerator": ai["numerator"],
                "denominator": ai["denominator"],
                "rate": ai_rate,
                "sample_size": sample_size,
                "comparison_numerator": human["numerator"],
                "comparison_denominator": human["denominator"],
                "comparison_rate": human_rate,
                "effect_size": round(ai_rate - human_rate, 6),
                "period_start": period_start,
                "period_end": period_end,
                "data_origin": DATA_ORIGIN,
                "metric_version": metric_version,
            }
        )
    return rows


def _build_feature_drift(
    records: dict[str, dict[str, object]],
    metric_version: str,
) -> list[dict[str, object]]:
    baseline = [
        record
        for record in records.values()
        if _date_floor(record["recommended_at"]) < date(2026, 4, 1)
    ]
    current = [
        record
        for record in records.values()
        if _date_floor(record["recommended_at"]) >= date(2026, 4, 1)
    ]
    rows = []
    for feature_name, predicate in [
        ("recommendation_score_high", lambda record: record["recommendation_score"] >= 0.75),
        ("experienced_candidate", lambda record: record["experience_years"] >= 5),
    ]:
        baseline_numerator = sum(1 for record in baseline if predicate(record))
        current_numerator = sum(1 for record in current if predicate(record))
        baseline_rate = _rate(baseline_numerator, len(baseline))
        current_rate = _rate(current_numerator, len(current))
        rows.append(
            {
                "feature_name": feature_name,
                "segment": "all",
                "metric_name": "distribution_shift",
                "numerator": current_numerator,
                "denominator": len(current),
                "rate": current_rate,
                "sample_size": len(current),
                "baseline_rate": baseline_rate,
                "current_rate": current_rate,
                "drift_score": round(abs(current_rate - baseline_rate), 6),
                "period_start": date(2026, 4, 1),
                "period_end": max(_date_floor(record["recommended_at"]) for record in current),
                "data_origin": DATA_ORIGIN,
                "metric_version": metric_version,
            }
        )
    return rows


def _build_monitoring_alerts(
    effectiveness_rows: list[dict[str, object]],
    drift_rows: list[dict[str, object]],
    metric_version: str,
) -> list[dict[str, object]]:
    rows = []
    for row in effectiveness_rows:
        if row["effect_size"] <= -0.02:
            rows.append(
                {
                    "alert_key": f"effectiveness:{row['job_category']}:{row['region']}",
                    "severity": "high" if row["effect_size"] <= -0.05 else "medium",
                    "status": "open",
                    "metric_name": "ai_effectiveness_drop",
                    "numerator": row["numerator"],
                    "denominator": row["denominator"],
                    "rate": row["rate"],
                    "sample_size": row["sample_size"],
                    "evidence": f"AI minus human effect size {row['effect_size']:.3f}",
                    "period_start": row["period_start"],
                    "period_end": row["period_end"],
                    "data_origin": DATA_ORIGIN,
                    "metric_version": metric_version,
                }
            )

    for row in drift_rows:
        if row["drift_score"] >= 0.05:
            rows.append(
                {
                    "alert_key": f"drift:{row['feature_name']}:{row['segment']}",
                    "severity": "medium",
                    "status": "open",
                    "metric_name": "feature_drift",
                    "numerator": row["numerator"],
                    "denominator": row["denominator"],
                    "rate": row["rate"],
                    "sample_size": row["sample_size"],
                    "evidence": f"Drift score {row['drift_score']:.3f}",
                    "period_start": row["period_start"],
                    "period_end": row["period_end"],
                    "data_origin": DATA_ORIGIN,
                    "metric_version": metric_version,
                }
            )
    if rows:
        return rows

    return [
        {
            "alert_key": "monitoring:normal",
            "severity": "normal",
            "status": "open",
            "metric_name": "monitoring_status",
            "numerator": 0,
            "denominator": 1,
            "rate": 0.0,
            "sample_size": 1,
            "evidence": "No configured alert thresholds crossed",
            "period_start": date.today(),
            "period_end": date.today(),
            "data_origin": DATA_ORIGIN,
            "metric_version": metric_version,
        }
    ]


def refresh_analytics_marts(
    session: Session,
    as_of_date: date,
    metric_version: str,
) -> dict[str, int]:
    _delete_metric_version(session, metric_version)
    records = _recommendation_stage_map(session)
    if not records:
        session.commit()
        return {
            "mart_daily_funnel": 0,
            "mart_cohort_conversion": 0,
            "mart_ai_effectiveness": 0,
            "mart_feature_drift": 0,
            "mart_monitoring_alert": 0,
        }

    daily_rows = _build_daily_funnel(records, metric_version)
    cohort_rows = _build_cohort_conversion(records, as_of_date, metric_version)
    effectiveness_rows = _build_ai_effectiveness(records, metric_version)
    drift_rows = _build_feature_drift(records, metric_version)
    alert_rows = _build_monitoring_alerts(effectiveness_rows, drift_rows, metric_version)

    session.bulk_insert_mappings(DailyFunnelMetric, daily_rows)
    session.bulk_insert_mappings(CohortConversionMetric, cohort_rows)
    session.bulk_insert_mappings(AiEffectivenessMetric, effectiveness_rows)
    session.bulk_insert_mappings(FeatureDriftMetric, drift_rows)
    session.bulk_insert_mappings(MonitoringAlert, alert_rows)
    session.commit()

    return {
        "mart_daily_funnel": len(daily_rows),
        "mart_cohort_conversion": len(cohort_rows),
        "mart_ai_effectiveness": len(effectiveness_rows),
        "mart_feature_drift": len(drift_rows),
        "mart_monitoring_alert": len(alert_rows),
    }
