from datetime import date

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    app: str
    environment: str
    database: str
    database_backend: str


class SummaryMetrics(BaseModel):
    recommended: int
    contacted: int
    replied: int
    interviewed: int
    offered: int
    hired: int
    ai_share: float = Field(ge=0, le=1)
    contact_rate: float = Field(ge=0, le=1)
    interview_rate: float = Field(ge=0, le=1)
    qualified_interview_30d_rate: float = Field(ge=0, le=1)
    offer_rate: float = Field(ge=0, le=1)
    hire_rate: float = Field(ge=0, le=1)
    mature_queue_hire_rate: float = Field(ge=0, le=1)


class TrendPoint(BaseModel):
    period: str
    source: str
    recommended: int
    interview_rate: float
    hire_rate: float


class OpenAlert(BaseModel):
    alert_key: str
    severity: str
    metric_name: str
    evidence: str
    period_start: date
    period_end: date


class OverviewResponse(BaseModel):
    summary: SummaryMetrics
    trend: list[TrendPoint]
    open_alerts: list[OpenAlert]
    data_origin: str


class FunnelRow(BaseModel):
    source: str
    recommended: int
    contacted: int
    replied: int
    interviewed: int
    offered: int
    hired: int


class FilterOptions(BaseModel):
    date_min: date
    date_max: date
    sources: list[str]
    job_categories: list[str]
    regions: list[str]
    model_versions: list[str]
    recruiter_teams: list[str]


class MonitoringRow(BaseModel):
    source: str
    baseline_interview_rate: float
    current_interview_rate: float
    rate_change: float
    severity: str


class MonitoringResponse(BaseModel):
    baseline_start: date
    baseline_end: date
    current_start: date
    current_end: date
    rows: list[MonitoringRow]


class EffectivenessResponse(BaseModel):
    metric: str
    ai_rate: float = Field(ge=0, le=1)
    human_rate: float = Field(ge=0, le=1)
    difference: float
    confidence_interval_low: float
    confidence_interval_high: float
    ai_sample_size: int
    human_sample_size: int
    data_origin: str
