from collections import defaultdict
from datetime import date, datetime, time, timedelta
from math import sqrt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aihr.models import (
    FunnelEvent,
    Job,
    ModelVersion,
    Recommendation,
    Recruiter,
)

STAGE_COLUMNS = {
    "contacted": "contacted",
    "replied": "replied",
    "interviewed": "interviewed",
    "offered": "offered",
    "hired": "hired",
}


def _rate(numerator: int | None, denominator: int | None) -> float:
    return round((numerator or 0) / denominator, 4) if denominator else 0.0


def _recommendation_query(
    session: Session,
    start_date: date | None = None,
    end_date: date | None = None,
    source: str | None = None,
    job_category: str | None = None,
    region: str | None = None,
    model_version: str | None = None,
    recruiter_team: str | None = None,
):
    query = (
        session.query(
            Recommendation.recommendation_id,
            Recommendation.source,
            Recommendation.recommended_at,
        )
        .join(Job, Recommendation.job_id == Job.job_id)
        .join(ModelVersion, Recommendation.model_version_id == ModelVersion.model_version_id)
        .join(Recruiter, Recommendation.recruiter_id == Recruiter.recruiter_id)
    )
    if start_date:
        query = query.filter(
            Recommendation.recommended_at >= datetime.combine(start_date, time.min)
        )
    if end_date:
        query = query.filter(Recommendation.recommended_at <= datetime.combine(end_date, time.max))
    if source:
        query = query.filter(Recommendation.source == source)
    if job_category:
        query = query.filter(Job.job_category == job_category)
    if region:
        query = query.filter(Job.region == region)
    if model_version:
        query = query.filter(ModelVersion.model_version == model_version)
    if recruiter_team:
        query = query.filter(Recruiter.team == recruiter_team)
    return query


def get_filter_options(session: Session) -> dict:
    date_min_dt, date_max_dt = session.execute(
        select(
            func.min(Recommendation.recommended_at),
            func.max(Recommendation.recommended_at),
        )
    ).one()
    date_min = date_min_dt.date() if date_min_dt else None
    date_max = date_max_dt.date() if date_max_dt else None
    if date_min is None or date_max is None:
        raise ValueError("No analytics data is available")

    def distinct_values(column) -> list[str]:
        return list(session.scalars(select(column).distinct().order_by(column)))

    return {
        "date_min": date_min,
        "date_max": date_max,
        "sources": distinct_values(Recommendation.source),
        "job_categories": distinct_values(Job.job_category),
        "regions": distinct_values(Job.region),
        "model_versions": distinct_values(ModelVersion.model_version),
        "recruiter_teams": distinct_values(Recruiter.team),
    }


def get_overview(session: Session, **filters) -> dict:
    filtered_recommendations = _recommendation_query(session, **filters)
    recommendations = filtered_recommendations.all()
    recommendation_filter = filtered_recommendations.subquery()
    recommendation_ids = [row.recommendation_id for row in recommendations]
    recommended = len(recommendation_ids)
    ai_recommended = sum(1 for row in recommendations if row.source == "ai")
    stage_counts = {stage: 0 for stage in STAGE_COLUMNS}
    completed_stages_by_id: dict[str, dict[str, datetime]] = defaultdict(dict)

    if recommendation_ids:
        event_rows = (
            session.query(
                recommendation_filter.c.recommendation_id,
                FunnelEvent.stage,
                FunnelEvent.event_at,
            )
            .join(
                FunnelEvent,
                FunnelEvent.recommendation_id == recommendation_filter.c.recommendation_id,
            )
            .filter(
                FunnelEvent.status == "completed",
                FunnelEvent.stage.in_(list(STAGE_COLUMNS)),
            )
            .all()
        )
        for recommendation_id, stage, event_at in event_rows:
            stage_counts[stage] += 1
            completed_stages_by_id[recommendation_id][stage] = event_at

    max_date = max((row.recommended_at.date() for row in recommendations), default=None)
    maturity_cutoff = max_date - timedelta(days=30) if max_date else None
    mature_recommendations = [
        row
        for row in recommendations
        if maturity_cutoff and row.recommended_at.date() <= maturity_cutoff
    ]
    mature_ids = {row.recommendation_id for row in mature_recommendations}
    mature_interviewed = sum(
        1
        for row in mature_recommendations
        if (
            interview_at := completed_stages_by_id[row.recommendation_id].get("interviewed")
        )
        and interview_at <= row.recommended_at + timedelta(days=30)
    )
    mature_hired = sum(
        1
        for recommendation_id in mature_ids
        if "hired" in completed_stages_by_id[recommendation_id]
    )

    monthly = defaultdict(lambda: {"recommended": 0, "interviewed": 0, "hired": 0})
    for row in recommendations:
        period = row.recommended_at.strftime("%Y-%m")
        key = (period, row.source)
        monthly[key]["recommended"] += 1
        stages = completed_stages_by_id[row.recommendation_id]
        if "interviewed" in stages:
            monthly[key]["interviewed"] += 1
        if "hired" in stages:
            monthly[key]["hired"] += 1
    latest_periods = sorted({period for period, _source in monthly})[-12:]
    trend_rows = [
        (key, values)
        for key, values in sorted(monthly.items())
        if key[0] in latest_periods
    ]

    open_alerts = []
    if recommendations:
        monitoring = get_monitoring(session, **filters)
        open_alerts = [
            {
                "alert_key": f"monitoring:{row['source']}:{monitoring['current_end']}",
                "severity": row["severity"],
                "metric_name": "interview_rate_change",
                "evidence": f"{row['source']} interview rate changed {row['rate_change']:+.1%}",
                "period_start": monitoring["current_start"],
                "period_end": monitoring["current_end"],
            }
            for row in monitoring["rows"]
            if row["severity"] != "normal"
        ]

    return {
        "summary": {
            "recommended": recommended,
            "contacted": stage_counts["contacted"],
            "replied": stage_counts["replied"],
            "interviewed": stage_counts["interviewed"],
            "offered": stage_counts["offered"],
            "hired": stage_counts["hired"],
            "ai_share": _rate(ai_recommended, recommended),
            "contact_rate": _rate(stage_counts["contacted"], recommended),
            "interview_rate": _rate(stage_counts["interviewed"], recommended),
            "qualified_interview_30d_rate": _rate(mature_interviewed, len(mature_ids)),
            "offer_rate": _rate(stage_counts["offered"], recommended),
            "hire_rate": _rate(stage_counts["hired"], recommended),
            "mature_queue_hire_rate": _rate(mature_hired, len(mature_ids)),
        },
        "trend": [
            {
                "period": period,
                "source": source,
                "recommended": values["recommended"],
                "interview_rate": _rate(values["interviewed"], values["recommended"]),
                "hire_rate": _rate(values["hired"], values["recommended"]),
            }
            for (period, source), values in trend_rows
        ],
        "open_alerts": [
            {
                "alert_key": alert["alert_key"],
                "severity": alert["severity"],
                "metric_name": alert["metric_name"],
                "evidence": alert["evidence"],
                "period_start": alert["period_start"],
                "period_end": alert["period_end"],
            }
            for alert in open_alerts
        ],
        "data_origin": "synthetic",
    }


def get_funnel(session: Session, **filters) -> list[dict]:
    filtered_recommendations = _recommendation_query(session, **filters)
    recommendations = filtered_recommendations.all()
    recommendation_filter = filtered_recommendations.subquery()
    grouped = defaultdict(lambda: dict.fromkeys(["recommended", *STAGE_COLUMNS], 0))
    recommendation_sources = {
        row.recommendation_id: row.source
        for row in recommendations
    }
    for row in recommendations:
        grouped[row.source]["recommended"] += 1

    if recommendation_sources:
        event_rows = (
            session.query(recommendation_filter.c.recommendation_id, FunnelEvent.stage)
            .join(
                FunnelEvent,
                FunnelEvent.recommendation_id == recommendation_filter.c.recommendation_id,
            )
            .filter(
                FunnelEvent.status == "completed",
                FunnelEvent.stage.in_(list(STAGE_COLUMNS)),
            )
            .all()
        )
        for recommendation_id, stage in event_rows:
            grouped[recommendation_sources[recommendation_id]][stage] += 1

    return [
        {
            "source": source,
            "recommended": counts["recommended"],
            "contacted": counts["contacted"],
            "replied": counts["replied"],
            "interviewed": counts["interviewed"],
            "offered": counts["offered"],
            "hired": counts["hired"],
        }
        for source, counts in sorted(grouped.items())
    ]


def get_monitoring(session: Session, **filters) -> dict:
    max_date_dt = _recommendation_query(session, **filters).with_entities(
        func.max(Recommendation.recommended_at)
    ).scalar()
    max_date = max_date_dt.date() if max_date_dt else None
    if max_date is None:
        raise ValueError("No analytics data is available")

    current_start = max_date - timedelta(days=29)
    baseline_end = current_start - timedelta(days=1)
    baseline_start = baseline_end - timedelta(days=29)

    def rates(start: date, end: date) -> dict[str, float]:
        rows = get_funnel(session, **{**filters, "start_date": start, "end_date": end})
        return {
            row["source"]: _rate(row["interviewed"], row["recommended"]) for row in rows
        }

    baseline = rates(baseline_start, baseline_end)
    current = rates(current_start, max_date)
    result_rows = []
    for source in sorted(set(baseline) | set(current)):
        change = round(current.get(source, 0) - baseline.get(source, 0), 4)
        severity = "high" if change <= -0.02 else "medium" if change <= -0.01 else "normal"
        result_rows.append(
            {
                "source": source,
                "baseline_interview_rate": baseline.get(source, 0),
                "current_interview_rate": current.get(source, 0),
                "rate_change": change,
                "severity": severity,
            }
        )

    return {
        "baseline_start": baseline_start,
        "baseline_end": baseline_end,
        "current_start": current_start,
        "current_end": max_date,
        "rows": result_rows,
    }


def get_effectiveness(
    session: Session,
    start_date: date | None = None,
    end_date: date | None = None,
    source: str | None = None,
    job_category: str | None = None,
    region: str | None = None,
    model_version: str | None = None,
    recruiter_team: str | None = None,
) -> dict:
    shared_filters = {
        "start_date": start_date,
        "end_date": end_date,
        "job_category": job_category,
        "region": region,
        "model_version": model_version,
        "recruiter_team": recruiter_team,
    }
    empty = {"interview_rate": 0.0, "recommended": 0}
    ai = (
        get_overview(session, source="ai", **shared_filters)["summary"]
        if source in (None, "ai")
        else empty
    )
    human = (
        get_overview(session, source="human", **shared_filters)["summary"]
        if source in (None, "human")
        else empty
    )
    ai_rate = ai["interview_rate"]
    human_rate = human["interview_rate"]
    ai_n = ai["recommended"]
    human_n = human["recommended"]
    difference = ai_rate - human_rate
    standard_error = (
        sqrt(ai_rate * (1 - ai_rate) / ai_n + human_rate * (1 - human_rate) / human_n)
        if ai_n and human_n
        else 0.0
    )
    return {
        "metric": "unadjusted_cumulative_interview_rate",
        "ai_rate": ai_rate,
        "human_rate": human_rate,
        "difference": difference,
        "confidence_interval_low": difference - 1.96 * standard_error,
        "confidence_interval_high": difference + 1.96 * standard_error,
        "ai_sample_size": ai_n,
        "human_sample_size": human_n,
        "data_origin": "synthetic",
    }
