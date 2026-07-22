from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from aihr.db import Base


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
