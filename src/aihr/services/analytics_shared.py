"""Shared query and date utilities for analytics domain services."""

from datetime import date, datetime, time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aihr.models import Job, ModelVersion, Recommendation, Recruiter


def rate(numerator: int | None, denominator: int | None) -> float:
    return round((numerator or 0) / denominator, 4) if denominator else 0.0


def add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def recent_month_periods(end_date: date, count: int = 12) -> list[str]:
    month_start = date(end_date.year, end_date.month, 1)
    return [add_months(month_start, offset).strftime("%Y-%m") for offset in range(1 - count, 1)]


def recommendation_query(
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
