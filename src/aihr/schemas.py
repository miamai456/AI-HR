from datetime import date, datetime

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


class MonitoringThresholdBand(BaseModel):
    medium: float
    high: float


class MonitoringThresholds(BaseModel):
    psi: MonitoringThresholdBand
    jsd: MonitoringThresholdBand
    score_drift: MonitoringThresholdBand


class ModelVersionTrendPoint(BaseModel):
    period: str
    model_version: str
    job_category: str
    region: str
    recommendations: int
    traffic_share: float
    interview_rate: float


class DriftMetric(BaseModel):
    metric_type: str
    feature_name: str
    baseline_value: float
    current_value: float
    drift_value: float
    threshold_medium: float
    threshold_high: float
    severity: str
    baseline_sample_size: int
    current_sample_size: int


class DiagnosticBreakdown(BaseModel):
    job_category: str | None = None
    region: str | None = None
    recruiter_team: str | None = None
    model_version: str | None = None


class DiagnosticConclusion(BaseModel):
    conclusion_type: str
    category: str
    severity: str
    message: str
    breakdown: DiagnosticBreakdown
    evidence_metric: str
    baseline_value: float
    current_value: float
    change_value: float
    period_start: date
    period_end: date
    baseline_sample_size: int
    current_sample_size: int
    sample_size: int


class MonitoringResponse(BaseModel):
    baseline_start: date
    baseline_end: date
    current_start: date
    current_end: date
    rows: list[MonitoringRow]
    thresholds: MonitoringThresholds
    model_version_trends: list[ModelVersionTrendPoint]
    drift_metrics: list[DriftMetric]
    diagnostic_conclusions: list[DiagnosticConclusion]


class CommonSupportDiagnostics(BaseModel):
    has_overlap: bool
    lower_bound: float
    upper_bound: float
    retained_sample_size: int
    original_sample_size: int


class ExtremeWeightHandling(BaseModel):
    method: str
    lower_clip: float
    upper_clip: float
    max_weight_before: float
    max_weight_after: float


class BalanceDiagnostic(BaseModel):
    covariate: str
    smd_before: float
    smd_after: float


class EffectivenessResponse(BaseModel):
    metric: str
    analysis_type: str
    causal_claim: bool
    limitation_note: str
    ai_rate: float = Field(ge=0, le=1)
    human_rate: float = Field(ge=0, le=1)
    difference: float
    proportion_difference: float
    confidence_interval_low: float
    confidence_interval_high: float
    ai_sample_size: int
    human_sample_size: int
    adjusted_ai_rate: float | None = Field(default=None, ge=0, le=1)
    adjusted_human_rate: float | None = Field(default=None, ge=0, le=1)
    adjusted_difference: float | None = None
    propensity_method: str
    weighting_method: str
    common_support: CommonSupportDiagnostics
    extreme_weight_handling: ExtremeWeightHandling
    balance_diagnostics: list[BalanceDiagnostic]
    data_origin: str


class DataQualityLayer(BaseModel):
    layer_name: str
    layer_type: str
    record_count: int
    last_updated_at: datetime | None = None


class DataQualityCheck(BaseModel):
    check_type: str
    check_name: str
    status: str
    severity: str
    evidence_metric: str
    affected_count: int
    sample_size: int
    period_start: date
    period_end: date
    details: dict


class DataQualitySummary(BaseModel):
    total_checks: int
    failed_checks: int
    warning_checks: int
    generated_at: datetime


class DataQualityResponse(BaseModel):
    summary: DataQualitySummary
    layers: list[DataQualityLayer]
    checks: list[DataQualityCheck]
    data_origin: str


class PredictionModelSummary(BaseModel):
    model_name: str
    target: str
    sample_size: int
    positive_rate: float = Field(ge=0, le=1)
    auc: float = Field(ge=0, le=1)
    accuracy: float = Field(ge=0, le=1)
    anomaly_model: str


class ProbabilityBand(BaseModel):
    band: str
    recommendations: int
    predicted_conversion_rate: float = Field(ge=0, le=1)
    actual_conversion_rate: float = Field(ge=0, le=1)
    lift_vs_average: float


class FeatureContribution(BaseModel):
    feature: str
    direction: str
    importance: float
    average_contribution: float


class SegmentPerformance(BaseModel):
    segment_type: str
    segment_value: str
    recommendations: int
    predicted_conversion_rate: float = Field(ge=0, le=1)
    actual_conversion_rate: float = Field(ge=0, le=1)
    lift_vs_average: float


class AnomalyFinding(BaseModel):
    recommendation_id: str
    anomaly_score: float
    predicted_conversion_probability: float = Field(ge=0, le=1)
    actual_outcome: int
    source: str
    job_category: str
    region: str
    model_version: str
    recruiter_team: str
    evidence: str


class PredictionInsightsResponse(BaseModel):
    model_summary: PredictionModelSummary
    probability_bands: list[ProbabilityBand]
    top_features: list[FeatureContribution]
    segment_performance: list[SegmentPerformance]
    anomaly_findings: list[AnomalyFinding]
    method_notes: list[str]
    data_origin: str
