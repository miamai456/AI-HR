from datetime import date, timedelta
from math import sqrt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aihr.models import DailyFunnelMetric


def _rate(numerator: int | None, denominator: int | None) -> float:
    return round((numerator or 0) / denominator, 4) if denominator else 0.0


def _conditions(
    start_date: date | None = None,
    end_date: date | None = None,
    source: str | None = None,
    job_category: str | None = None,
    region: str | None = None,
) -> list:
    conditions = []
    if start_date:
        conditions.append(DailyFunnelMetric.metric_date >= start_date)
    if end_date:
        conditions.append(DailyFunnelMetric.metric_date <= end_date)
    if source:
        conditions.append(DailyFunnelMetric.source == source)
    if job_category:
        conditions.append(DailyFunnelMetric.job_category == job_category)
    if region:
        conditions.append(DailyFunnelMetric.region == region)
    return conditions


def get_filter_options(session: Session) -> dict:
    date_min, date_max = session.execute(
        select(
            func.min(DailyFunnelMetric.metric_date),
            func.max(DailyFunnelMetric.metric_date),
        )
    ).one()
    if date_min is None or date_max is None:
        raise ValueError("No analytics data is available")

    def distinct_values(column) -> list[str]:
        return list(session.scalars(select(column).distinct().order_by(column)))

    return {
        "date_min": date_min,
        "date_max": date_max,
        "sources": distinct_values(DailyFunnelMetric.source),
        "job_categories": distinct_values(DailyFunnelMetric.job_category),
        "regions": distinct_values(DailyFunnelMetric.region),
    }


def get_overview(session: Session, **filters) -> dict:
    conditions = _conditions(**filters)
    total = session.execute(
        select(
            func.sum(DailyFunnelMetric.recommended),
            func.sum(DailyFunnelMetric.contacted),
            func.sum(DailyFunnelMetric.replied),
            func.sum(DailyFunnelMetric.interviewed),
            func.sum(DailyFunnelMetric.offered),
            func.sum(DailyFunnelMetric.hired),
        ).where(*conditions)
    ).one()
    recommended, contacted, replied, interviewed, offered, hired = [value or 0 for value in total]

    trend_rows = session.execute(
        select(
            DailyFunnelMetric.metric_date,
            DailyFunnelMetric.source,
            func.sum(DailyFunnelMetric.recommended),
            func.sum(DailyFunnelMetric.interviewed),
            func.sum(DailyFunnelMetric.hired),
        )
        .where(*conditions)
        .group_by(DailyFunnelMetric.metric_date, DailyFunnelMetric.source)
        .order_by(DailyFunnelMetric.metric_date, DailyFunnelMetric.source)
    ).all()

    return {
        "summary": {
            "recommended": recommended,
            "contacted": contacted,
            "replied": replied,
            "interviewed": interviewed,
            "offered": offered,
            "hired": hired,
            "contact_rate": _rate(contacted, recommended),
            "interview_rate": _rate(interviewed, recommended),
            "offer_rate": _rate(offered, recommended),
            "hire_rate": _rate(hired, recommended),
        },
        "trend": [
            {
                "metric_date": metric_date,
                "source": source,
                "recommended": daily_recommended,
                "interview_rate": _rate(daily_interviewed, daily_recommended),
                "hire_rate": _rate(daily_hired, daily_recommended),
            }
            for metric_date, source, daily_recommended, daily_interviewed, daily_hired in trend_rows
        ],
        "data_origin": "synthetic",
    }


def get_funnel(session: Session, **filters) -> list[dict]:
    rows = session.execute(
        select(
            DailyFunnelMetric.source,
            func.sum(DailyFunnelMetric.recommended),
            func.sum(DailyFunnelMetric.contacted),
            func.sum(DailyFunnelMetric.replied),
            func.sum(DailyFunnelMetric.interviewed),
            func.sum(DailyFunnelMetric.offered),
            func.sum(DailyFunnelMetric.hired),
        )
        .where(*_conditions(**filters))
        .group_by(DailyFunnelMetric.source)
        .order_by(DailyFunnelMetric.source)
    ).all()
    return [
        {
            "source": source,
            "recommended": recommended or 0,
            "contacted": contacted or 0,
            "replied": replied or 0,
            "interviewed": interviewed or 0,
            "offered": offered or 0,
            "hired": hired or 0,
        }
        for source, recommended, contacted, replied, interviewed, offered, hired in rows
    ]


def get_monitoring(session: Session) -> dict:
    max_date = session.scalar(select(func.max(DailyFunnelMetric.metric_date)))
    if max_date is None:
        raise ValueError("No analytics data is available")

    current_start = max_date - timedelta(days=29)
    baseline_end = current_start - timedelta(days=1)
    baseline_start = baseline_end - timedelta(days=29)

    def rates(start: date, end: date) -> dict[str, float]:
        rows = session.execute(
            select(
                DailyFunnelMetric.source,
                func.sum(DailyFunnelMetric.interviewed),
                func.sum(DailyFunnelMetric.recommended),
            )
            .where(DailyFunnelMetric.metric_date.between(start, end))
            .group_by(DailyFunnelMetric.source)
        ).all()
        return {
            source: _rate(interviewed, recommended) for source, interviewed, recommended in rows
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
    job_category: str | None = None,
    region: str | None = None,
) -> dict:
    shared_filters = {
        "start_date": start_date,
        "end_date": end_date,
        "job_category": job_category,
        "region": region,
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
