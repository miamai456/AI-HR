from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
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
        UniqueConstraint(
            "metric_date",
            "source",
            "job_category",
            "region",
            name="uq_daily_funnel_segment",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    metric_date: Mapped[date] = mapped_column(Date, index=True)
    source: Mapped[str] = mapped_column(String(16), index=True)
    job_category: Mapped[str] = mapped_column(String(32), index=True)
    region: Mapped[str] = mapped_column(String(32), index=True)
    recommended: Mapped[int] = mapped_column(Integer)
    contacted: Mapped[int] = mapped_column(Integer)
    replied: Mapped[int] = mapped_column(Integer)
    interviewed: Mapped[int] = mapped_column(Integer)
    offered: Mapped[int] = mapped_column(Integer)
    hired: Mapped[int] = mapped_column(Integer)
    data_origin: Mapped[str] = mapped_column(String(16), default="synthetic")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
