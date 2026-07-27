from collections import defaultdict
from datetime import date, datetime, time, timedelta
from math import sqrt

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import OneHotEncoder
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aihr.models import (
    AiEffectivenessMetric,
    Candidate,
    CohortConversionMetric,
    DailyFunnelMetric,
    FeatureDriftMetric,
    FunnelEvent,
    Job,
    ModelVersion,
    MonitoringAlert,
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
WEIGHT_LOWER_CLIP = 0.1
WEIGHT_UPPER_CLIP = 10.0
MONITORING_THRESHOLDS = {
    "psi": {"medium": 0.1, "high": 0.25},
    "jsd": {"medium": 0.05, "high": 0.2},
    "score_drift": {"medium": 0.05, "high": 0.1},
}
EVENT_STAGE_ORDER = {
    "contacted": 1,
    "replied": 2,
    "interviewed": 3,
    "offered": 4,
    "hired": 5,
}
VALID_SOURCES = {"ai", "human"}
VALID_EVENT_STATUSES = {"completed", "skipped"}


def _rate(numerator: int | None, denominator: int | None) -> float:
    return round((numerator or 0) / denominator, 4) if denominator else 0.0


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def _recent_month_periods(end_date: date, count: int = 12) -> list[str]:
    month_start = date(end_date.year, end_date.month, 1)
    return [_add_months(month_start, offset).strftime("%Y-%m") for offset in range(1 - count, 1)]


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
    trend_end = filters.get("end_date") or max_date or datetime.now().date()
    latest_periods = _recent_month_periods(trend_end)
    trend_sources = [filters["source"]] if filters.get("source") else sorted(
        {row.source for row in recommendations} or set(get_filter_options(session)["sources"])
    )
    trend_rows = [
        (
            (period, source),
            monthly[(period, source)],
        )
        for period in latest_periods
        for source in trend_sources
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


def _severity(metric_type: str, value: float) -> str:
    thresholds = MONITORING_THRESHOLDS[metric_type]
    if value >= thresholds["high"]:
        return "high"
    if value >= thresholds["medium"]:
        return "medium"
    return "normal"


def _distribution(values: list[str]) -> dict[str, float]:
    if not values:
        return {}
    counts = defaultdict(int)
    for value in values:
        counts[value] += 1
    total = len(values)
    return {key: count / total for key, count in counts.items()}


def _jsd(baseline_values: list[str], current_values: list[str]) -> float:
    baseline = _distribution(baseline_values)
    current = _distribution(current_values)
    categories = sorted(set(baseline) | set(current))
    if not categories:
        return 0.0

    baseline_probs = np.array([baseline.get(category, 0.0) for category in categories])
    current_probs = np.array([current.get(category, 0.0) for category in categories])
    midpoint = (baseline_probs + current_probs) / 2

    def kl_divergence(left: np.ndarray, right: np.ndarray) -> float:
        mask = left > 0
        return float(np.sum(left[mask] * np.log2(left[mask] / right[mask])))

    divergence = (
        kl_divergence(baseline_probs, midpoint)
        + kl_divergence(current_probs, midpoint)
    ) / 2
    return round(divergence, 4)


def _psi(baseline_values: list[float], current_values: list[float], buckets: int = 10) -> float:
    if not baseline_values or not current_values:
        return 0.0
    baseline_array = np.array(baseline_values, dtype=float)
    current_array = np.array(current_values, dtype=float)
    quantiles = np.linspace(0, 1, buckets + 1)
    edges = np.unique(np.quantile(baseline_array, quantiles))
    if len(edges) < 2:
        return 0.0
    edges[0] = -np.inf
    edges[-1] = np.inf
    baseline_counts, _ = np.histogram(baseline_array, bins=edges)
    current_counts, _ = np.histogram(current_array, bins=edges)
    epsilon = 1e-6
    baseline_rates = np.maximum(baseline_counts / baseline_counts.sum(), epsilon)
    current_rates = np.maximum(current_counts / current_counts.sum(), epsilon)
    psi = np.sum(
        (current_rates - baseline_rates)
        * np.log(current_rates / baseline_rates)
    )
    return round(float(psi), 4)


def _monitoring_records(session: Session, **filters) -> list[dict]:
    query = (
        session.query(
            Recommendation.recommendation_id,
            Recommendation.source,
            Recommendation.recommended_at,
            Recommendation.recommendation_score,
            Candidate.experience_years,
            Candidate.education_level,
            Job.job_category,
            Job.region,
            Job.seniority_level,
            ModelVersion.model_version,
            Recruiter.team,
        )
        .join(Candidate, Recommendation.candidate_id == Candidate.candidate_id)
        .join(Job, Recommendation.job_id == Job.job_id)
        .join(ModelVersion, Recommendation.model_version_id == ModelVersion.model_version_id)
        .join(Recruiter, Recommendation.recruiter_id == Recruiter.recruiter_id)
    )
    start_date = filters.get("start_date")
    end_date = filters.get("end_date")
    if start_date:
        query = query.filter(
            Recommendation.recommended_at >= datetime.combine(start_date, time.min)
        )
    if end_date:
        query = query.filter(Recommendation.recommended_at <= datetime.combine(end_date, time.max))
    if source := filters.get("source"):
        query = query.filter(Recommendation.source == source)
    if job_category := filters.get("job_category"):
        query = query.filter(Job.job_category == job_category)
    if region := filters.get("region"):
        query = query.filter(Job.region == region)
    if model_version := filters.get("model_version"):
        query = query.filter(ModelVersion.model_version == model_version)
    if recruiter_team := filters.get("recruiter_team"):
        query = query.filter(Recruiter.team == recruiter_team)

    recommendation_filter = query.subquery()
    interviewed_ids = {
        recommendation_id
        for recommendation_id, in session.query(recommendation_filter.c.recommendation_id)
        .join(
            FunnelEvent,
            FunnelEvent.recommendation_id == recommendation_filter.c.recommendation_id,
        )
        .filter(FunnelEvent.stage == "interviewed", FunnelEvent.status == "completed")
        .all()
    }
    return [
        {
            "recommendation_id": row.recommendation_id,
            "source": row.source,
            "recommended_at": row.recommended_at,
            "recommendation_score": row.recommendation_score,
            "experience_years": row.experience_years,
            "education_level": row.education_level,
            "job_category": row.job_category,
            "region": row.region,
            "seniority_level": row.seniority_level,
            "model_version": row.model_version,
            "recruiter_team": row.team,
            "interviewed": row.recommendation_id in interviewed_ids,
        }
        for row in query.all()
    ]


def _model_version_trends(records: list[dict]) -> list[dict]:
    monthly_totals = defaultdict(int)
    grouped = defaultdict(lambda: {"recommendations": 0, "interviewed": 0})
    for record in records:
        period = record["recommended_at"].strftime("%Y-%m")
        monthly_totals[period] += 1
        key = (period, record["model_version"], record["job_category"], record["region"])
        grouped[key]["recommendations"] += 1
        if record["interviewed"]:
            grouped[key]["interviewed"] += 1
    return [
        {
            "period": period,
            "model_version": model_version,
            "job_category": job_category,
            "region": region,
            "recommendations": values["recommendations"],
            "traffic_share": _rate(values["recommendations"], monthly_totals[period]),
            "interview_rate": _rate(values["interviewed"], values["recommendations"]),
        }
        for (period, model_version, job_category, region), values in sorted(grouped.items())
    ]


def _drift_metrics(baseline_records: list[dict], current_records: list[dict]) -> list[dict]:
    baseline_n = len(baseline_records)
    current_n = len(current_records)

    def metric_row(
        metric_type: str,
        feature_name: str,
        baseline_value: float,
        current_value: float,
        drift_value: float,
    ) -> dict:
        thresholds = MONITORING_THRESHOLDS[metric_type]
        return {
            "metric_type": metric_type,
            "feature_name": feature_name,
            "baseline_value": round(baseline_value, 4),
            "current_value": round(current_value, 4),
            "drift_value": round(drift_value, 4),
            "threshold_medium": thresholds["medium"],
            "threshold_high": thresholds["high"],
            "severity": _severity(metric_type, drift_value),
            "baseline_sample_size": baseline_n,
            "current_sample_size": current_n,
        }

    baseline_scores = [record["recommendation_score"] for record in baseline_records]
    current_scores = [record["recommendation_score"] for record in current_records]
    baseline_experience = [record["experience_years"] for record in baseline_records]
    current_experience = [record["experience_years"] for record in current_records]
    score_baseline_mean = float(np.mean(baseline_scores)) if baseline_scores else 0.0
    score_current_mean = float(np.mean(current_scores)) if current_scores else 0.0

    rows = [
        metric_row(
            "psi",
            "experience_years",
            float(np.mean(baseline_experience)) if baseline_experience else 0.0,
            float(np.mean(current_experience)) if current_experience else 0.0,
            _psi(baseline_experience, current_experience),
        ),
        metric_row(
            "score_drift",
            "recommendation_score",
            score_baseline_mean,
            score_current_mean,
            abs(score_current_mean - score_baseline_mean),
        ),
    ]
    for feature_name in ["job_category", "region", "seniority_level", "education_level", "source"]:
        rows.append(
            metric_row(
                "jsd",
                feature_name,
                0.0,
                0.0,
                _jsd(
                    [record[feature_name] for record in baseline_records],
                    [record[feature_name] for record in current_records],
                ),
            )
        )
    return rows


def _effect_drop_severity(change: float) -> str:
    if change <= -0.02:
        return "high"
    if change <= -0.01:
        return "medium"
    return "normal"


def _diagnostic_row(
    conclusion_type: str,
    category: str,
    severity: str,
    message: str,
    breakdown: dict,
    evidence_metric: str,
    baseline_value: float,
    current_value: float,
    period_start: date,
    period_end: date,
    baseline_sample_size: int,
    current_sample_size: int,
) -> dict:
    return {
        "conclusion_type": conclusion_type,
        "category": category,
        "severity": severity,
        "message": message,
        "breakdown": {
            "job_category": breakdown.get("job_category"),
            "region": breakdown.get("region"),
            "recruiter_team": breakdown.get("recruiter_team"),
            "model_version": breakdown.get("model_version"),
        },
        "evidence_metric": evidence_metric,
        "baseline_value": round(baseline_value, 4),
        "current_value": round(current_value, 4),
        "change_value": round(current_value - baseline_value, 4),
        "period_start": period_start,
        "period_end": period_end,
        "baseline_sample_size": baseline_sample_size,
        "current_sample_size": current_sample_size,
        "sample_size": baseline_sample_size + current_sample_size,
    }


def _segment_effect_conclusions(
    baseline_records: list[dict],
    current_records: list[dict],
    period_start: date,
    period_end: date,
) -> list[dict]:
    def aggregate_row() -> dict:
        baseline_n = len(baseline_records)
        current_n = len(current_records)
        baseline_interviewed = sum(1 for record in baseline_records if record["interviewed"])
        current_interviewed = sum(1 for record in current_records if record["interviewed"])
        baseline_rate = _rate(baseline_interviewed, baseline_n)
        current_rate = _rate(current_interviewed, current_n)
        change = current_rate - baseline_rate
        return _diagnostic_row(
            conclusion_type="effect_drop",
            category="hiring_process",
            severity=_effect_drop_severity(change),
            message=f"Overall interview rate changed {change:+.1%}.",
            breakdown={
                "job_category": None,
                "region": None,
                "recruiter_team": None,
                "model_version": None,
            },
            evidence_metric="interview_rate_change",
            baseline_value=baseline_rate,
            current_value=current_rate,
            period_start=period_start,
            period_end=period_end,
            baseline_sample_size=baseline_n,
            current_sample_size=current_n,
        )

    grouped = defaultdict(
        lambda: {
            "baseline_n": 0,
            "baseline_interviewed": 0,
            "current_n": 0,
            "current_interviewed": 0,
        }
    )
    for period_name, records in [("baseline", baseline_records), ("current", current_records)]:
        for record in records:
            key = (
                record["job_category"],
                record["region"],
                record["recruiter_team"],
                record["model_version"],
            )
            grouped[key][f"{period_name}_n"] += 1
            if record["interviewed"]:
                grouped[key][f"{period_name}_interviewed"] += 1

    rows = []
    for (job_category, region, recruiter_team, model_version), values in grouped.items():
        baseline_n = values["baseline_n"]
        current_n = values["current_n"]
        if not baseline_n or not current_n:
            continue
        baseline_rate = _rate(values["baseline_interviewed"], baseline_n)
        current_rate = _rate(values["current_interviewed"], current_n)
        change = current_rate - baseline_rate
        rows.append(
            _diagnostic_row(
                conclusion_type="effect_drop",
                category="model" if model_version.startswith("ai_") else "hiring_process",
                severity=_effect_drop_severity(change),
                message=(
                    f"{model_version} / {job_category} / {region} / {recruiter_team} "
                    f"interview rate changed {change:+.1%}."
                ),
                breakdown={
                    "job_category": job_category,
                    "region": region,
                    "recruiter_team": recruiter_team,
                    "model_version": model_version,
                },
                evidence_metric="interview_rate_change",
                baseline_value=baseline_rate,
                current_value=current_rate,
                period_start=period_start,
                period_end=period_end,
                baseline_sample_size=baseline_n,
                current_sample_size=current_n,
            )
        )

    if not rows:
        return [aggregate_row()]
    rows.sort(key=lambda row: row["change_value"])
    return rows[:8]


def _traffic_structure_conclusion(
    baseline_records: list[dict],
    current_records: list[dict],
    period_start: date,
    period_end: date,
) -> dict | None:
    baseline_total = len(baseline_records)
    current_total = len(current_records)
    if not baseline_total or not current_total:
        return None

    grouped = defaultdict(lambda: {"baseline": 0, "current": 0})
    for period_name, records in [("baseline", baseline_records), ("current", current_records)]:
        for record in records:
            key = (
                record["job_category"],
                record["region"],
                record["recruiter_team"],
                record["model_version"],
            )
            grouped[key][period_name] += 1

    best_key = None
    best_change = 0.0
    best_values = None
    for key, values in grouped.items():
        baseline_share = values["baseline"] / baseline_total
        current_share = values["current"] / current_total
        change = current_share - baseline_share
        if abs(change) >= abs(best_change):
            best_key = key
            best_change = change
            best_values = (baseline_share, current_share, values)

    if best_key is None or best_values is None:
        return None
    job_category, region, recruiter_team, model_version = best_key
    baseline_share, current_share, values = best_values
    severity = (
        "high"
        if abs(best_change) >= 0.1
        else "medium"
        if abs(best_change) >= 0.05
        else "normal"
    )
    return _diagnostic_row(
        conclusion_type="traffic_shift",
        category="traffic_structure",
        severity=severity,
        message=(
            f"Traffic share changed {best_change:+.1%} for "
            f"{model_version} / {job_category} / {region} / {recruiter_team}."
        ),
        breakdown={
            "job_category": job_category,
            "region": region,
            "recruiter_team": recruiter_team,
            "model_version": model_version,
        },
        evidence_metric="traffic_share_change",
        baseline_value=baseline_share,
        current_value=current_share,
        period_start=period_start,
        period_end=period_end,
        baseline_sample_size=values["baseline"],
        current_sample_size=values["current"],
    )


def _data_anomaly_conclusion(
    baseline_records: list[dict],
    current_records: list[dict],
    period_start: date,
    period_end: date,
) -> dict:
    baseline_n = len(baseline_records)
    current_n = len(current_records)
    ratio = current_n / baseline_n if baseline_n else 0.0
    severity = (
        "high"
        if ratio < 0.5 or ratio > 1.5
        else "medium"
        if ratio < 0.75 or ratio > 1.25
        else "normal"
    )
    return _diagnostic_row(
        conclusion_type="data_anomaly",
        category="data_issue",
        severity=severity,
        message=f"Current sample volume is {ratio:.2f}x the baseline sample volume.",
        breakdown={
            "job_category": None,
            "region": None,
            "recruiter_team": None,
            "model_version": None,
        },
        evidence_metric="sample_volume_ratio",
        baseline_value=1.0,
        current_value=ratio,
        period_start=period_start,
        period_end=period_end,
        baseline_sample_size=baseline_n,
        current_sample_size=current_n,
    )


def _recruiter_operation_conclusion(
    baseline_records: list[dict],
    current_records: list[dict],
    period_start: date,
    period_end: date,
) -> dict | None:
    grouped = defaultdict(
        lambda: {
            "baseline_n": 0,
            "baseline_interviewed": 0,
            "current_n": 0,
            "current_interviewed": 0,
        }
    )
    for period_name, records in [("baseline", baseline_records), ("current", current_records)]:
        for record in records:
            team = record["recruiter_team"]
            grouped[team][f"{period_name}_n"] += 1
            if record["interviewed"]:
                grouped[team][f"{period_name}_interviewed"] += 1

    best_team = None
    best_change = 0.0
    best_values = None
    for team, values in grouped.items():
        if not values["baseline_n"] or not values["current_n"]:
            continue
        baseline_rate = _rate(values["baseline_interviewed"], values["baseline_n"])
        current_rate = _rate(values["current_interviewed"], values["current_n"])
        change = current_rate - baseline_rate
        if best_team is None or change < best_change:
            best_team = team
            best_change = change
            best_values = (baseline_rate, current_rate, values)

    if best_team is None or best_values is None:
        baseline_n = len(baseline_records)
        current_n = len(current_records)
        baseline_rate = _rate(
            sum(1 for record in baseline_records if record["interviewed"]),
            baseline_n,
        )
        current_rate = _rate(
            sum(1 for record in current_records if record["interviewed"]),
            current_n,
        )
        change = current_rate - baseline_rate
        return _diagnostic_row(
            conclusion_type="recruiter_operation_change",
            category="recruiter_operation",
            severity=_effect_drop_severity(change),
            message=f"Overall recruiter follow-up outcome changed {change:+.1%}.",
            breakdown={
                "job_category": None,
                "region": None,
                "recruiter_team": None,
                "model_version": None,
            },
            evidence_metric="recruiter_team_interview_rate_change",
            baseline_value=baseline_rate,
            current_value=current_rate,
            period_start=period_start,
            period_end=period_end,
            baseline_sample_size=baseline_n,
            current_sample_size=current_n,
        )
    baseline_rate, current_rate, values = best_values
    return _diagnostic_row(
        conclusion_type="recruiter_operation_change",
        category="recruiter_operation",
        severity=_effect_drop_severity(best_change),
        message=f"{best_team} interview rate changed {best_change:+.1%}.",
        breakdown={
            "job_category": None,
            "region": None,
            "recruiter_team": best_team,
            "model_version": None,
        },
        evidence_metric="recruiter_team_interview_rate_change",
        baseline_value=baseline_rate,
        current_value=current_rate,
        period_start=period_start,
        period_end=period_end,
        baseline_sample_size=values["baseline_n"],
        current_sample_size=values["current_n"],
    )


def _model_score_conclusion(
    drift_metrics: list[dict],
    baseline_records: list[dict],
    current_records: list[dict],
    period_start: date,
    period_end: date,
) -> dict | None:
    score_metric = next(
        (metric for metric in drift_metrics if metric["metric_type"] == "score_drift"),
        None,
    )
    if score_metric is None:
        return None
    return _diagnostic_row(
        conclusion_type="score_drift",
        category="model",
        severity=score_metric["severity"],
        message=(
            "Recommendation score mean changed "
            f"{score_metric['current_value'] - score_metric['baseline_value']:+.3f}."
        ),
        breakdown={
            "job_category": None,
            "region": None,
            "recruiter_team": None,
            "model_version": None,
        },
        evidence_metric="recommendation_score_mean_change",
        baseline_value=score_metric["baseline_value"],
        current_value=score_metric["current_value"],
        period_start=period_start,
        period_end=period_end,
        baseline_sample_size=len(baseline_records),
        current_sample_size=len(current_records),
    )


def _diagnostic_conclusions(
    baseline_records: list[dict],
    current_records: list[dict],
    drift_metrics: list[dict],
    period_start: date,
    period_end: date,
) -> list[dict]:
    conclusions = [
        _data_anomaly_conclusion(baseline_records, current_records, period_start, period_end)
    ]
    conclusions.extend(
        _segment_effect_conclusions(
            baseline_records,
            current_records,
            period_start,
            period_end,
        )
    )
    if traffic_row := _traffic_structure_conclusion(
        baseline_records,
        current_records,
        period_start,
        period_end,
    ):
        conclusions.append(traffic_row)
    if recruiter_row := _recruiter_operation_conclusion(
        baseline_records,
        current_records,
        period_start,
        period_end,
    ):
        conclusions.append(recruiter_row)
    if model_row := _model_score_conclusion(
        drift_metrics,
        baseline_records,
        current_records,
        period_start,
        period_end,
    ):
        conclusions.append(model_row)
    return conclusions


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
    monitoring_records = _monitoring_records(session, **filters)
    baseline_records = [
        record
        for record in monitoring_records
        if baseline_start <= record["recommended_at"].date() <= baseline_end
    ]
    current_records = [
        record
        for record in monitoring_records
        if current_start <= record["recommended_at"].date() <= max_date
    ]

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
    drift_metrics = _drift_metrics(baseline_records, current_records)

    return {
        "baseline_start": baseline_start,
        "baseline_end": baseline_end,
        "current_start": current_start,
        "current_end": max_date,
        "rows": result_rows,
        "thresholds": MONITORING_THRESHOLDS,
        "model_version_trends": _model_version_trends(monitoring_records),
        "drift_metrics": drift_metrics,
        "diagnostic_conclusions": _diagnostic_conclusions(
            baseline_records,
            current_records,
            drift_metrics,
            baseline_start,
            max_date,
        ),
    }


def _count_rows(session: Session, model) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def _max_created_at(session: Session, model) -> datetime | None:
    if "created_at" not in model.__table__.columns:
        return None
    return session.scalar(select(func.max(model.created_at)))


def _quality_period(session: Session) -> tuple[date, date]:
    min_dt, max_dt = session.execute(
        select(func.min(Recommendation.recommended_at), func.max(Recommendation.recommended_at))
    ).one()
    if min_dt and max_dt:
        return min_dt.date(), max_dt.date()
    today = datetime.now().date()
    return today, today


def _quality_status(affected_count: int, sample_size: int, warn_ratio: float = 0.01) -> str:
    if affected_count == 0:
        return "pass"
    if sample_size and affected_count / sample_size <= warn_ratio:
        return "warn"
    return "fail"


def _quality_severity(status: str, affected_count: int, sample_size: int) -> str:
    if status == "pass":
        return "normal"
    if status == "warn":
        return "medium"
    if sample_size and affected_count / sample_size < 0.05:
        return "medium"
    return "high"


def _quality_check(
    *,
    check_type: str,
    check_name: str,
    evidence_metric: str,
    affected_count: int,
    sample_size: int,
    period_start: date,
    period_end: date,
    details: dict,
    status: str | None = None,
) -> dict:
    resolved_status = status or _quality_status(affected_count, sample_size)
    return {
        "check_type": check_type,
        "check_name": check_name,
        "status": resolved_status,
        "severity": _quality_severity(resolved_status, affected_count, sample_size),
        "evidence_metric": evidence_metric,
        "affected_count": affected_count,
        "sample_size": sample_size,
        "period_start": period_start,
        "period_end": period_end,
        "details": details,
    }


def _duplicate_primary_key_count(session: Session, model) -> int:
    primary_keys = list(model.__table__.primary_key.columns)
    if not primary_keys:
        return 0
    duplicate_groups = (
        select(func.count())
        .select_from(model)
        .group_by(*primary_keys)
        .having(func.count() > 1)
        .subquery()
    )
    return session.scalar(select(func.count()).select_from(duplicate_groups)) or 0


def _event_scope(statement, recommendation_ids: list[str]):
    if recommendation_ids:
        return statement.where(FunnelEvent.recommendation_id.in_(recommendation_ids))
    return statement


def _missing_critical_field_count(session: Session, recommendation_ids: list[str]) -> int:
    statement = _event_scope(
        select(func.count())
        .select_from(FunnelEvent)
        .where(FunnelEvent.status == "completed", FunnelEvent.event_at.is_(None)),
        recommendation_ids,
    )
    return session.scalar(statement) or 0


def _orphan_event_count(session: Session, recommendation_ids: list[str]) -> int:
    statement = (
        select(func.count())
        .select_from(FunnelEvent)
        .outerjoin(
            Recommendation,
            FunnelEvent.recommendation_id == Recommendation.recommendation_id,
        )
        .where(Recommendation.recommendation_id.is_(None))
    )
    statement = _event_scope(statement, recommendation_ids)
    return (
        session.scalar(statement)
        or 0
    )


def _illegal_event_order_count(session: Session, recommendation_ids: list[str]) -> int:
    statement = (
        select(FunnelEvent.recommendation_id, FunnelEvent.stage, FunnelEvent.event_at)
        .where(
            FunnelEvent.status == "completed",
            FunnelEvent.stage.in_(list(EVENT_STAGE_ORDER)),
            FunnelEvent.event_at.is_not(None),
        )
        .order_by(FunnelEvent.recommendation_id, FunnelEvent.event_at)
    )
    rows = session.execute(_event_scope(statement, recommendation_ids)).all()
    latest_stage_rank_by_recommendation: dict[str, int] = {}
    invalid_recommendations = set()
    for recommendation_id, stage, _event_at in rows:
        stage_rank = EVENT_STAGE_ORDER[stage]
        previous_rank = latest_stage_rank_by_recommendation.get(recommendation_id, 0)
        if stage_rank < previous_rank:
            invalid_recommendations.add(recommendation_id)
        latest_stage_rank_by_recommendation[recommendation_id] = max(previous_rank, stage_rank)
    return len(invalid_recommendations)


def _future_timestamp_count(
    session: Session,
    generated_at: datetime,
    recommendation_ids: list[str],
) -> int:
    recommendation_statement = (
        select(func.count())
        .select_from(Recommendation)
        .where(Recommendation.recommended_at > generated_at)
    )
    if recommendation_ids:
        recommendation_statement = recommendation_statement.where(
            Recommendation.recommendation_id.in_(recommendation_ids)
        )
    event_statement = _event_scope(
        select(func.count()).select_from(FunnelEvent).where(FunnelEvent.event_at > generated_at),
        recommendation_ids,
    )
    recommendation_count = session.scalar(recommendation_statement) or 0
    event_count = session.scalar(event_statement) or 0
    return recommendation_count + event_count


def _negative_duration_count(session: Session, recommendation_ids: list[str]) -> int:
    statement = (
        select(func.count())
        .select_from(FunnelEvent)
        .join(
            Recommendation,
            FunnelEvent.recommendation_id == Recommendation.recommendation_id,
        )
        .where(
            FunnelEvent.event_at.is_not(None),
            FunnelEvent.event_at < Recommendation.recommended_at,
        )
    )
    statement = _event_scope(statement, recommendation_ids)
    return session.scalar(statement) or 0


def _invalid_enum_count(session: Session, recommendation_ids: list[str]) -> int:
    source_statement = (
        select(func.count())
        .select_from(Recommendation)
        .where(Recommendation.source.not_in(VALID_SOURCES))
    )
    if recommendation_ids:
        source_statement = source_statement.where(
            Recommendation.recommendation_id.in_(recommendation_ids)
        )
    invalid_event_stage_statement = _event_scope(
        select(func.count())
        .select_from(FunnelEvent)
        .where(FunnelEvent.stage.not_in(set(EVENT_STAGE_ORDER))),
        recommendation_ids,
    )
    invalid_event_status_statement = _event_scope(
        select(func.count())
        .select_from(FunnelEvent)
        .where(FunnelEvent.status.not_in(VALID_EVENT_STATUSES)),
        recommendation_ids,
    )
    invalid_sources = session.scalar(source_statement) or 0
    invalid_event_stages = session.scalar(invalid_event_stage_statement) or 0
    invalid_event_statuses = session.scalar(invalid_event_status_statement) or 0
    return invalid_sources + invalid_event_stages + invalid_event_statuses


def _data_latency_days(
    session: Session,
    generated_at: datetime,
    recommendation_ids: list[str],
) -> int:
    event_statement = select(func.max(FunnelEvent.event_at))
    recommendation_statement = select(func.max(Recommendation.recommended_at))
    if recommendation_ids:
        event_statement = event_statement.where(
            FunnelEvent.recommendation_id.in_(recommendation_ids)
        )
        recommendation_statement = recommendation_statement.where(
            Recommendation.recommendation_id.in_(recommendation_ids)
        )
    latest_event = session.scalar(event_statement)
    latest_recommendation = session.scalar(recommendation_statement)
    latest_observed = max(
        [value for value in [latest_event, latest_recommendation] if value is not None],
        default=None,
    )
    if latest_observed is None:
        return 0
    return max((generated_at.date() - latest_observed.date()).days, 0)


def _queue_maturity(session: Session, recommendation_ids: list[str]) -> tuple[int, int, float]:
    max_statement = select(func.max(Recommendation.recommended_at))
    if recommendation_ids:
        max_statement = max_statement.where(
            Recommendation.recommendation_id.in_(recommendation_ids)
        )
    max_recommended_at = session.scalar(max_statement)
    total_recommendations = len(recommendation_ids)
    if not max_recommended_at or not total_recommendations:
        return 0, total_recommendations, 0.0
    mature_cutoff = max_recommended_at - timedelta(days=30)
    mature_statement = (
        select(func.count())
        .select_from(Recommendation)
        .where(Recommendation.recommended_at <= mature_cutoff)
    )
    if recommendation_ids:
        mature_statement = mature_statement.where(
            Recommendation.recommendation_id.in_(recommendation_ids)
        )
    mature_count = session.scalar(mature_statement) or 0
    return mature_count, total_recommendations, round(mature_count / total_recommendations, 4)


def get_data_quality(session: Session, **filters) -> dict:
    generated_at = datetime.now()
    default_period_start, default_period_end = _quality_period(session)
    period_start = filters.get("start_date") or default_period_start
    period_end = filters.get("end_date") or default_period_end
    layer_models = [
        ("dim_candidate", "dimension", Candidate),
        ("dim_job", "dimension", Job),
        ("dim_recruiter", "dimension", Recruiter),
        ("dim_model_version", "dimension", ModelVersion),
        ("fact_recommendation", "fact", Recommendation),
        ("fact_funnel_event", "fact", FunnelEvent),
        ("mart_daily_funnel", "mart", DailyFunnelMetric),
        ("mart_cohort_conversion", "mart", CohortConversionMetric),
        ("mart_ai_effectiveness", "mart", AiEffectivenessMetric),
        ("mart_feature_drift", "mart", FeatureDriftMetric),
        ("mart_monitoring_alert", "mart", MonitoringAlert),
    ]
    layers = [
        {
            "layer_name": layer_name,
            "layer_type": layer_type,
            "record_count": _count_rows(session, model),
            "last_updated_at": _max_created_at(session, model),
        }
        for layer_name, layer_type, model in layer_models
    ]

    filtered_recommendations = _recommendation_query(session, **filters).all()
    recommendation_ids = [row.recommendation_id for row in filtered_recommendations]
    recommendation_count = len(recommendation_ids)
    if recommendation_ids:
        event_count_statement = (
            select(func.count())
            .select_from(FunnelEvent)
            .where(FunnelEvent.recommendation_id.in_(recommendation_ids))
        )
        event_count = session.scalar(event_count_statement) or 0
    else:
        event_count = 0
    duplicate_pk_count = sum(
        _duplicate_primary_key_count(session, model) for _, _, model in layer_models
    )
    if recommendation_ids:
        missing_critical_count = _missing_critical_field_count(session, recommendation_ids)
        orphan_event_count = _orphan_event_count(session, recommendation_ids)
        illegal_order_count = _illegal_event_order_count(session, recommendation_ids)
        future_timestamp_count = _future_timestamp_count(session, generated_at, recommendation_ids)
        negative_duration_count = _negative_duration_count(session, recommendation_ids)
        invalid_enum_count = _invalid_enum_count(session, recommendation_ids)
        latency_days = _data_latency_days(session, generated_at, recommendation_ids)
        mature_count, total_queue_count, mature_share = _queue_maturity(session, recommendation_ids)
    else:
        missing_critical_count = 0
        orphan_event_count = 0
        illegal_order_count = 0
        future_timestamp_count = 0
        negative_duration_count = 0
        invalid_enum_count = 0
        latency_days = 0
        mature_count, total_queue_count, mature_share = 0, 0, 0.0

    checks = [
        _quality_check(
            check_type="duplicate_primary_key",
            check_name="Duplicate primary keys across modeled tables",
            evidence_metric="duplicate_primary_key_groups",
            affected_count=duplicate_pk_count,
            sample_size=sum(layer["record_count"] for layer in layers),
            period_start=period_start,
            period_end=period_end,
            details={"tables_checked": len(layer_models)},
        ),
        _quality_check(
            check_type="missing_critical_field",
            check_name="Missing critical fields",
            evidence_metric="completed_events_missing_event_at",
            affected_count=missing_critical_count,
            sample_size=event_count,
            period_start=period_start,
            period_end=period_end,
            details={"critical_rule": "completed funnel events must include event_at"},
        ),
        _quality_check(
            check_type="orphan_event",
            check_name="Funnel events without recommendations",
            evidence_metric="orphan_funnel_events",
            affected_count=orphan_event_count,
            sample_size=event_count,
            period_start=period_start,
            period_end=period_end,
            details={"parent_table": "fact_recommendation"},
        ),
        _quality_check(
            check_type="illegal_event_order",
            check_name="Illegal funnel event order",
            evidence_metric="recommendations_with_stage_regression",
            affected_count=illegal_order_count,
            sample_size=recommendation_count,
            period_start=period_start,
            period_end=period_end,
            details={"expected_order": list(EVENT_STAGE_ORDER)},
        ),
        _quality_check(
            check_type="future_timestamp",
            check_name="Future recommendation or event timestamps",
            evidence_metric="future_timestamp_rows",
            affected_count=future_timestamp_count,
            sample_size=recommendation_count + event_count,
            period_start=period_start,
            period_end=period_end,
            details={"generated_at": generated_at.isoformat()},
        ),
        _quality_check(
            check_type="negative_duration",
            check_name="Negative duration from recommendation to event",
            evidence_metric="events_before_recommendation",
            affected_count=negative_duration_count,
            sample_size=event_count,
            period_start=period_start,
            period_end=period_end,
            details={"duration_rule": "event_at must be on or after recommended_at"},
        ),
        _quality_check(
            check_type="invalid_enum",
            check_name="Invalid source, stage, or status enums",
            evidence_metric="invalid_enum_rows",
            affected_count=invalid_enum_count,
            sample_size=recommendation_count + event_count,
            period_start=period_start,
            period_end=period_end,
            details={
                "valid_sources": sorted(VALID_SOURCES),
                "valid_event_stages": list(EVENT_STAGE_ORDER),
                "valid_event_statuses": sorted(VALID_EVENT_STATUSES),
            },
        ),
        _quality_check(
            check_type="data_latency",
            check_name="Data latency",
            evidence_metric="days_since_latest_event_or_recommendation",
            affected_count=latency_days,
            sample_size=max(latency_days, 1),
            period_start=period_start,
            period_end=period_end,
            details={"warning_threshold_days": 7, "failure_threshold_days": 30},
            status="fail" if latency_days > 30 else "warn" if latency_days > 7 else "pass",
        ),
        _quality_check(
            check_type="queue_maturity",
            check_name="Queue maturity for delayed funnel outcomes",
            evidence_metric="immature_queue_records",
            affected_count=max(total_queue_count - mature_count, 0),
            sample_size=total_queue_count,
            period_start=period_start,
            period_end=period_end,
            details={"mature_share": mature_share, "maturity_window_days": 30},
            status="pass" if mature_share >= 0.5 else "warn" if mature_share >= 0.25 else "fail",
        ),
    ]
    return {
        "summary": {
            "total_checks": len(checks),
            "failed_checks": sum(1 for check in checks if check["status"] == "fail"),
            "warning_checks": sum(1 for check in checks if check["status"] == "warn"),
            "generated_at": generated_at,
        },
        "layers": layers,
        "checks": checks,
        "data_origin": "synthetic",
    }


def _weighted_rate(outcome: np.ndarray, weights: np.ndarray) -> float:
    total_weight = weights.sum()
    return round(float(np.dot(outcome, weights) / total_weight), 4) if total_weight else 0.0


def _smd(treatment: np.ndarray, values: np.ndarray, weights: np.ndarray | None = None) -> float:
    treated = treatment == 1
    control = treatment == 0
    if not treated.any() or not control.any():
        return 0.0

    if weights is None:
        treated_mean = float(values[treated].mean())
        control_mean = float(values[control].mean())
        treated_var = float(values[treated].var())
        control_var = float(values[control].var())
    else:
        treated_weights = weights[treated]
        control_weights = weights[control]
        treated_mean = float(np.average(values[treated], weights=treated_weights))
        control_mean = float(np.average(values[control], weights=control_weights))
        treated_var = float(
            np.average((values[treated] - treated_mean) ** 2, weights=treated_weights)
        )
        control_var = float(
            np.average((values[control] - control_mean) ** 2, weights=control_weights)
        )

    pooled_sd = sqrt((treated_var + control_var) / 2)
    return round((treated_mean - control_mean) / pooled_sd, 4) if pooled_sd else 0.0


def _effectiveness_records(session: Session, **filters) -> list[dict]:
    query = (
        session.query(
            Recommendation.recommendation_id,
            Recommendation.source,
            Candidate.experience_years,
            Job.job_category,
            Job.region,
            Job.seniority_level,
            Recruiter.team,
        )
        .join(Candidate, Recommendation.candidate_id == Candidate.candidate_id)
        .join(Job, Recommendation.job_id == Job.job_id)
        .join(ModelVersion, Recommendation.model_version_id == ModelVersion.model_version_id)
        .join(Recruiter, Recommendation.recruiter_id == Recruiter.recruiter_id)
    )
    start_date = filters.get("start_date")
    end_date = filters.get("end_date")
    if start_date:
        query = query.filter(
            Recommendation.recommended_at >= datetime.combine(start_date, time.min)
        )
    if end_date:
        query = query.filter(Recommendation.recommended_at <= datetime.combine(end_date, time.max))
    if job_category := filters.get("job_category"):
        query = query.filter(Job.job_category == job_category)
    if region := filters.get("region"):
        query = query.filter(Job.region == region)
    if model_version := filters.get("model_version"):
        query = query.filter(ModelVersion.model_version == model_version)
    if recruiter_team := filters.get("recruiter_team"):
        query = query.filter(Recruiter.team == recruiter_team)

    recommendation_filter = query.subquery()
    outcomes = {
        recommendation_id
        for recommendation_id, in session.query(recommendation_filter.c.recommendation_id)
        .join(
            FunnelEvent,
            FunnelEvent.recommendation_id == recommendation_filter.c.recommendation_id,
        )
        .filter(FunnelEvent.stage == "interviewed", FunnelEvent.status == "completed")
        .all()
    }

    return [
        {
            "recommendation_id": row.recommendation_id,
            "source": row.source,
            "treatment": 1 if row.source == "ai" else 0,
            "outcome": 1 if row.recommendation_id in outcomes else 0,
            "experience_years": row.experience_years,
            "job_category": row.job_category,
            "region": row.region,
            "seniority_level": row.seniority_level,
            "team": row.team,
        }
        for row in query.all()
        if row.source in {"ai", "human"}
    ]


def _propensity_adjustment(records: list[dict]) -> dict:
    original_sample_size = len(records)
    empty_support = {
        "has_overlap": False,
        "lower_bound": 0.0,
        "upper_bound": 0.0,
        "retained_sample_size": 0,
        "original_sample_size": original_sample_size,
    }
    empty_weights = {
        "method": "clip",
        "lower_clip": WEIGHT_LOWER_CLIP,
        "upper_clip": WEIGHT_UPPER_CLIP,
        "max_weight_before": 0.0,
        "max_weight_after": 0.0,
    }
    if not records or {record["treatment"] for record in records} != {0, 1}:
        return {
            "adjusted_ai_rate": None,
            "adjusted_human_rate": None,
            "adjusted_difference": None,
            "common_support": empty_support,
            "extreme_weight_handling": empty_weights,
            "balance_diagnostics": [],
        }

    treatment = np.array([record["treatment"] for record in records], dtype=int)
    outcome = np.array([record["outcome"] for record in records], dtype=float)
    numeric = np.array([[record["experience_years"]] for record in records], dtype=float)
    categorical = np.array(
        [
            [record["job_category"], record["region"], record["seniority_level"], record["team"]]
            for record in records
        ],
        dtype=object,
    )
    encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    encoded = encoder.fit_transform(categorical)
    feature_names = ["experience_years", *encoder.get_feature_names_out().tolist()]
    features = np.hstack([numeric, encoded])

    model = LogisticRegression(max_iter=1000, solver="lbfgs")
    model.fit(features, treatment)
    propensity = np.clip(model.predict_proba(features)[:, 1], 0.01, 0.99)

    ai_scores = propensity[treatment == 1]
    human_scores = propensity[treatment == 0]
    lower_bound = float(max(ai_scores.min(), human_scores.min()))
    upper_bound = float(min(ai_scores.max(), human_scores.max()))
    support_mask = (propensity >= lower_bound) & (propensity <= upper_bound)
    has_overlap = bool(lower_bound < upper_bound and support_mask.any())
    if not has_overlap:
        return {
            "adjusted_ai_rate": None,
            "adjusted_human_rate": None,
            "adjusted_difference": None,
            "common_support": {
                **empty_support,
                "lower_bound": round(lower_bound, 4),
                "upper_bound": round(upper_bound, 4),
            },
            "extreme_weight_handling": empty_weights,
            "balance_diagnostics": [],
        }

    treatment = treatment[support_mask]
    outcome = outcome[support_mask]
    features = features[support_mask]
    propensity = propensity[support_mask]
    treatment_share = float(treatment.mean())
    raw_weights = np.where(
        treatment == 1,
        treatment_share / propensity,
        (1 - treatment_share) / (1 - propensity),
    )
    weights = np.clip(raw_weights, WEIGHT_LOWER_CLIP, WEIGHT_UPPER_CLIP)
    adjusted_ai_rate = _weighted_rate(outcome[treatment == 1], weights[treatment == 1])
    adjusted_human_rate = _weighted_rate(outcome[treatment == 0], weights[treatment == 0])

    balance_diagnostics = [
        {
            "covariate": feature_name,
            "smd_before": _smd(treatment, features[:, index]),
            "smd_after": _smd(treatment, features[:, index], weights),
        }
        for index, feature_name in enumerate(feature_names)
    ]

    return {
        "adjusted_ai_rate": adjusted_ai_rate,
        "adjusted_human_rate": adjusted_human_rate,
        "adjusted_difference": round(adjusted_ai_rate - adjusted_human_rate, 4),
        "common_support": {
            "has_overlap": True,
            "lower_bound": round(lower_bound, 4),
            "upper_bound": round(upper_bound, 4),
            "retained_sample_size": int(support_mask.sum()),
            "original_sample_size": original_sample_size,
        },
        "extreme_weight_handling": {
            "method": "clip",
            "lower_clip": WEIGHT_LOWER_CLIP,
            "upper_clip": WEIGHT_UPPER_CLIP,
            "max_weight_before": round(float(raw_weights.max()), 4),
            "max_weight_after": round(float(weights.max()), 4),
        },
        "balance_diagnostics": balance_diagnostics,
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
    ai = get_overview(session, source="ai", **shared_filters)["summary"]
    human = get_overview(session, source="human", **shared_filters)["summary"]
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
    adjustment = _propensity_adjustment(_effectiveness_records(session, **shared_filters))
    return {
        "metric": "unadjusted_cumulative_interview_rate",
        "analysis_type": "observational_adjusted_association",
        "causal_claim": False,
        "limitation_note": (
            "This is an observational comparison with propensity-score adjustment; "
            "it reports association, not a causal effect of AI recommendations."
        ),
        "ai_rate": ai_rate,
        "human_rate": human_rate,
        "difference": difference,
        "proportion_difference": difference,
        "confidence_interval_low": difference - 1.96 * standard_error,
        "confidence_interval_high": difference + 1.96 * standard_error,
        "ai_sample_size": ai_n,
        "human_sample_size": human_n,
        **adjustment,
        "propensity_method": "logistic_regression_iptw",
        "weighting_method": "stabilized_iptw",
        "data_origin": "synthetic",
    }
