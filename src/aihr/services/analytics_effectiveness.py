"""AI versus human effectiveness analytics service."""

from datetime import date
from math import sqrt

from sqlalchemy.orm import Session

from aihr.services.analytics_core import (
    _effectiveness_records,
    _propensity_adjustment,
    get_overview,
)


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

__all__ = ["get_effectiveness"]
