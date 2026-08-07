from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from aihr.db import Base


class Candidate(Base):
    __tablename__ = "dim_candidate"

    candidate_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    region: Mapped[str] = mapped_column(String(32), index=True)
    experience_years: Mapped[int] = mapped_column(Integer)
    education_level: Mapped[str] = mapped_column(String(32))
    current_title: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Job(Base):
    __tablename__ = "dim_job"

    job_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    job_category: Mapped[str] = mapped_column(String(32), index=True)
    region: Mapped[str] = mapped_column(String(32), index=True)
    seniority_level: Mapped[str] = mapped_column(String(32))
    opened_at: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Recruiter(Base):
    __tablename__ = "dim_recruiter"

    recruiter_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    recruiter_name: Mapped[str] = mapped_column(String(64))
    region: Mapped[str] = mapped_column(String(32), index=True)
    team: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ModelVersion(Base):
    __tablename__ = "dim_model_version"

    model_version_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    model_version: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    deployed_at: Mapped[date] = mapped_column(Date)
    description: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Recommendation(Base):
    __tablename__ = "fact_recommendation"
    __table_args__ = (
        Index(
            "ix_recommendation_analysis_filters",
            "recommended_at",
            "source",
            "model_version_id",
            "recruiter_id",
            "job_id",
        ),
    )

    recommendation_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("dim_candidate.candidate_id"), index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("dim_job.job_id"), index=True)
    recruiter_id: Mapped[str] = mapped_column(ForeignKey("dim_recruiter.recruiter_id"), index=True)
    model_version_id: Mapped[str] = mapped_column(
        ForeignKey("dim_model_version.model_version_id"),
        index=True,
    )
    source: Mapped[str] = mapped_column(String(16), index=True)
    recommendation_score: Mapped[float] = mapped_column(Float)
    recommended_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class FunnelEvent(Base):
    __tablename__ = "fact_funnel_event"
    __table_args__ = (
        Index(
            "ix_funnel_event_analysis_lookup",
            "recommendation_id",
            "stage",
            "status",
            "event_at",
        ),
        UniqueConstraint(
            "recommendation_id",
            "stage",
            name="uq_funnel_event_recommendation_stage",
        ),
    )

    event_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recommendation_id: Mapped[str] = mapped_column(
        ForeignKey("fact_recommendation.recommendation_id"),
        index=True,
    )
    stage: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    event_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class DailyFunnelMetric(Base):
    __tablename__ = "mart_daily_funnel"
    __table_args__ = (
        Index(
            "ix_daily_funnel_analysis_filters",
            "metric_date",
            "source",
            "job_category",
            "region",
            "metric_version",
        ),
        UniqueConstraint(
            "metric_date",
            "source",
            "job_category",
            "region",
            "metric_name",
            "metric_version",
            name="uq_daily_funnel_segment",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    metric_date: Mapped[date] = mapped_column(Date, index=True)
    source: Mapped[str] = mapped_column(String(16), index=True)
    job_category: Mapped[str] = mapped_column(String(32), index=True)
    region: Mapped[str] = mapped_column(String(32), index=True)
    metric_name: Mapped[str] = mapped_column(String(64), default="daily_interview_rate", index=True)
    numerator: Mapped[int] = mapped_column(Integer, default=0)
    denominator: Mapped[int] = mapped_column(Integer, default=0)
    rate: Mapped[float] = mapped_column(Float, default=0.0)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    period_start: Mapped[date] = mapped_column(Date, index=True)
    period_end: Mapped[date] = mapped_column(Date, index=True)
    recommended: Mapped[int] = mapped_column(Integer)
    contacted: Mapped[int] = mapped_column(Integer)
    replied: Mapped[int] = mapped_column(Integer)
    interviewed: Mapped[int] = mapped_column(Integer)
    offered: Mapped[int] = mapped_column(Integer)
    hired: Mapped[int] = mapped_column(Integer)
    data_origin: Mapped[str] = mapped_column(String(32), default="synthetic")
    metric_version: Mapped[str] = mapped_column(String(32), default="v1", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CohortConversionMetric(Base):
    __tablename__ = "mart_cohort_conversion"
    __table_args__ = (
        UniqueConstraint(
            "cohort_month",
            "source",
            "job_category",
            "region",
            "metric_name",
            "metric_version",
            name="uq_cohort_conversion_segment_metric",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cohort_month: Mapped[date] = mapped_column(Date, index=True)
    source: Mapped[str] = mapped_column(String(16), index=True)
    job_category: Mapped[str] = mapped_column(String(32), index=True)
    region: Mapped[str] = mapped_column(String(32), index=True)
    metric_name: Mapped[str] = mapped_column(String(64), index=True)
    numerator: Mapped[int] = mapped_column(Integer)
    denominator: Mapped[int] = mapped_column(Integer)
    rate: Mapped[float] = mapped_column(Float)
    sample_size: Mapped[int] = mapped_column(Integer)
    period_start: Mapped[date] = mapped_column(Date, index=True)
    period_end: Mapped[date] = mapped_column(Date, index=True)
    data_origin: Mapped[str] = mapped_column(String(32), default="synthetic_event_rollup")
    metric_version: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AiEffectivenessMetric(Base):
    __tablename__ = "mart_ai_effectiveness"
    __table_args__ = (
        UniqueConstraint(
            "period_start",
            "period_end",
            "job_category",
            "region",
            "metric_name",
            "metric_version",
            name="uq_ai_effectiveness_segment_metric",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_category: Mapped[str] = mapped_column(String(32), index=True)
    region: Mapped[str] = mapped_column(String(32), index=True)
    metric_name: Mapped[str] = mapped_column(String(64), index=True)
    numerator: Mapped[int] = mapped_column(Integer)
    denominator: Mapped[int] = mapped_column(Integer)
    rate: Mapped[float] = mapped_column(Float)
    sample_size: Mapped[int] = mapped_column(Integer)
    comparison_numerator: Mapped[int] = mapped_column(Integer)
    comparison_denominator: Mapped[int] = mapped_column(Integer)
    comparison_rate: Mapped[float] = mapped_column(Float)
    effect_size: Mapped[float] = mapped_column(Float)
    period_start: Mapped[date] = mapped_column(Date, index=True)
    period_end: Mapped[date] = mapped_column(Date, index=True)
    data_origin: Mapped[str] = mapped_column(String(32), default="synthetic_event_rollup")
    metric_version: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class FeatureDriftMetric(Base):
    __tablename__ = "mart_feature_drift"
    __table_args__ = (
        UniqueConstraint(
            "feature_name",
            "segment",
            "period_start",
            "period_end",
            "metric_version",
            name="uq_feature_drift_metric",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feature_name: Mapped[str] = mapped_column(String(64), index=True)
    segment: Mapped[str] = mapped_column(String(64), index=True)
    metric_name: Mapped[str] = mapped_column(String(64), index=True)
    numerator: Mapped[int] = mapped_column(Integer)
    denominator: Mapped[int] = mapped_column(Integer)
    rate: Mapped[float] = mapped_column(Float)
    sample_size: Mapped[int] = mapped_column(Integer)
    baseline_rate: Mapped[float] = mapped_column(Float)
    current_rate: Mapped[float] = mapped_column(Float)
    drift_score: Mapped[float] = mapped_column(Float)
    period_start: Mapped[date] = mapped_column(Date, index=True)
    period_end: Mapped[date] = mapped_column(Date, index=True)
    data_origin: Mapped[str] = mapped_column(String(32), default="synthetic_event_rollup")
    metric_version: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class MonitoringAlert(Base):
    __tablename__ = "mart_monitoring_alert"
    __table_args__ = (
        UniqueConstraint(
            "alert_key",
            "metric_version",
            name="uq_monitoring_alert_key_version",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_key: Mapped[str] = mapped_column(String(128), index=True)
    severity: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    metric_name: Mapped[str] = mapped_column(String(64), index=True)
    numerator: Mapped[int] = mapped_column(Integer)
    denominator: Mapped[int] = mapped_column(Integer)
    rate: Mapped[float] = mapped_column(Float)
    sample_size: Mapped[int] = mapped_column(Integer)
    evidence: Mapped[str] = mapped_column(String(512))
    period_start: Mapped[date] = mapped_column(Date, index=True)
    period_end: Mapped[date] = mapped_column(Date, index=True)
    data_origin: Mapped[str] = mapped_column(String(32), default="synthetic_event_rollup")
    metric_version: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
