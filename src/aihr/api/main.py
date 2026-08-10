import json
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session

from aihr import __version__
from aihr.config import get_settings
from aihr.database import Base, create_engine_and_session, get_db
from aihr.schemas import (
    AssistantContextResponse,
    AssistantRequest,
    AssistantResponse,
    AssistantStatusResponse,
    DataQualityResponse,
    EffectivenessResponse,
    FilterOptions,
    FunnelRow,
    HealthResponse,
    MonitoringResponse,
    OverviewResponse,
    PredictionInsightsResponse,
    ReadyResponse,
)
from aihr.seed import SyntheticHiringConfig, seed_demo_metrics
from aihr.services.analysis_prewarm import start_analysis_prewarm
from aihr.services.analysis_runtime import build_analysis_context_service
from aihr.services.analytics_effectiveness import get_effectiveness
from aihr.services.analytics_ml import get_prediction_insights
from aihr.services.analytics_monitoring import get_monitoring
from aihr.services.analytics_overview import get_filter_options, get_funnel, get_overview
from aihr.services.analytics_quality import get_data_quality
from aihr.services.assistant import AssistantClient, AssistantService, AssistantServiceError
from aihr.services.assistant_trust import apply_trust_guard, build_assistant_trust
from aihr.services.cache import create_json_cache
from aihr.services.metrics import MetricsRegistry
from aihr.services.operations_auth import (
    load_operations_token,
    require_operations_access,
)
from aihr.services.prometheus_metrics import PrometheusMetrics
from aihr.services.telemetry import configure_telemetry

DbSession = Annotated[Session, Depends(get_db)]
LOGGER = logging.getLogger(__name__)


def database_backend_for_url(database_url: str) -> str:
    return make_url(database_url).get_backend_name()


def create_app(database_url: str | None = None) -> FastAPI:
    settings = get_settings()
    resolved_database_url = database_url or settings.database_url
    engine, session_factory = create_engine_and_session(resolved_database_url)
    prediction_cache: dict[tuple, tuple[float, dict]] = {}
    shared_cache = create_json_cache(settings.cache_url, prefix=settings.cache_prefix)
    metrics = MetricsRegistry()
    prometheus_metrics = PrometheusMetrics()
    operations_token = load_operations_token(
        settings.operations_token,
        settings.operations_token_file,
    )
    analysis_context_service = build_analysis_context_service(
        session_factory,
        shared_cache,
        ttl_seconds=settings.analysis_context_cache_ttl_seconds,
    )
    snapshot_store = analysis_context_service.snapshot_store
    load_dataset_version = analysis_context_service.dataset_version_loader
    assistant_service = None
    if settings.assistant_api_key and not settings.assistant_api_key.startswith("replace-with-"):
        assistant_service = AssistantService(
            AssistantClient(
                api_key=settings.assistant_api_key,
                base_url=settings.assistant_base_url,
                model=settings.assistant_model,
                max_attempts=settings.assistant_max_attempts,
            ),
            ttl_seconds=settings.assistant_cache_ttl_seconds,
            cache_backend=shared_cache,
        )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        Base.metadata.create_all(engine)
        if settings.seed_demo_data:
            with session_factory() as session:
                seed_demo_metrics(
                    session,
                    config=SyntheticHiringConfig(
                        seed=settings.synthetic_seed,
                        n_candidates=settings.synthetic_seed_candidates,
                        n_jobs=settings.synthetic_seed_jobs,
                        n_recommendations=settings.synthetic_seed_recommendations,
                    ),
                )
        if settings.analysis_prewarm:
            application.state.analysis_prewarm = start_analysis_prewarm(
                enabled=True,
                queue_enabled=settings.analysis_queue_enabled,
                queue_name=settings.analysis_queue_name,
                database_url=resolved_database_url,
                cache_url=settings.cache_url,
                cache_prefix=settings.cache_prefix,
                ttl_seconds=settings.analysis_context_cache_ttl_seconds,
                service=analysis_context_service,
                scopes=[{}, {"source": "ai"}, {"source": "human"}],
            )
        yield
        telemetry_provider = getattr(
            application.state,
            "telemetry_provider",
            None,
        )
        if telemetry_provider is not None:
            telemetry_provider.shutdown()
        engine.dispose()

    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="AI recruitment recommendation effectiveness analytics API",
        lifespan=lifespan,
    )
    application.state.engine = engine
    application.state.session_factory = session_factory
    application.state.assistant_service = assistant_service
    application.state.analysis_context_service = analysis_context_service
    application.state.cache_backend = shared_cache
    application.state.metrics = metrics
    application.state.prometheus_metrics = prometheus_metrics
    application.state.analysis_prewarm = start_analysis_prewarm(
        enabled=False,
        queue_enabled=False,
        queue_name=settings.analysis_queue_name,
        database_url=resolved_database_url,
        cache_url=settings.cache_url,
        cache_prefix=settings.cache_prefix,
        ttl_seconds=settings.analysis_context_cache_ttl_seconds,
        service=analysis_context_service,
        scopes=[],
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @application.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse(url="/docs")

    @application.middleware("http")
    async def record_http_metrics(request: Request, call_next):
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            latency_ms = round((time.perf_counter() - started) * 1000)
            metrics.record(
                f"http:{request.method}:{request.url.path}",
                latency_ms=latency_ms,
                success=False,
                error_code="exception",
            )
            prometheus_metrics.record_http(
                request.method,
                request.url.path,
                500,
                latency_ms,
            )
            raise
        latency_ms = round((time.perf_counter() - started) * 1000)
        metrics.record(
            f"http:{request.method}:{request.url.path}",
            latency_ms=latency_ms,
            success=response.status_code < 400,
            error_code=response.status_code if response.status_code >= 400 else None,
        )
        prometheus_metrics.record_http(
            request.method,
            request.url.path,
            response.status_code,
            latency_ms,
        )
        return response

    def operations_access(
        authorization: str | None = Header(default=None),
    ) -> None:
        require_operations_access(
            configured_token=operations_token,
            authorization=authorization,
            environment=settings.environment,
        )

    @application.get("/api/v1/health", response_model=HealthResponse, tags=["system"])
    def health(session: DbSession) -> dict:
        try:
            session.execute(text("SELECT 1"))
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Database is unavailable") from exc
        return {
            "status": "ok",
            "app": settings.app_name,
            "version": __version__,
            "environment": settings.environment,
            "database": "ok",
            "database_backend": database_backend_for_url(resolved_database_url),
        }

    @application.get("/api/v1/ready", response_model=ReadyResponse, tags=["system"])
    def ready(session: DbSession) -> dict:
        try:
            session.execute(text("SELECT 1"))
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Database is not ready") from exc
        return {
            "status": "ready",
            "app": settings.app_name,
            "version": __version__,
            "checks": {
                "database": "ready",
                "assistant": (
                    "configured"
                    if application.state.assistant_service is not None
                    else "optional"
                ),
                "cache": getattr(shared_cache, "backend_name", "unknown"),
            },
        }

    @application.get(
        "/api/v1/metrics/performance",
        tags=["system"],
        dependencies=[Depends(operations_access)],
    )
    def performance_metrics() -> dict:
        return {
            "service_version": __version__,
            "started_at": metrics.started_at,
            "operations": metrics.snapshot(),
        }

    @application.get(
        "/metrics",
        include_in_schema=False,
        dependencies=[Depends(operations_access)],
    )
    def prometheus_endpoint() -> Response:
        return Response(
            content=prometheus_metrics.render(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    @application.get(
        "/api/v1/assistant/status",
        response_model=AssistantStatusResponse,
        tags=["assistant"],
    )
    def assistant_status() -> dict:
        return {
            "configured": application.state.assistant_service is not None,
            "provider": settings.assistant_provider,
            "model": settings.assistant_model,
        }

    @application.get(
        "/api/v1/assistant/context",
        response_model=AssistantContextResponse,
        tags=["assistant"],
    )
    def assistant_context(
        start_date: date | None = None,
        end_date: date | None = None,
        source: str | None = Query(default=None, pattern="^(ai|human)$"),
        job_category: str | None = None,
        region: str | None = None,
        model_version: str | None = None,
        recruiter_team: str | None = None,
    ) -> dict:
        filters = {
            "start_date": start_date,
            "end_date": end_date,
            "source": source,
            "job_category": job_category,
            "region": region,
            "model_version": model_version,
            "recruiter_team": recruiter_team,
        }
        context, cached, latency_ms = analysis_context_service.get(filters)
        metrics.record(
            "analysis_context",
            latency_ms=latency_ms,
            success=True,
            cached=cached,
        )
        prometheus_metrics.record_context(cached=cached)
        return {**context, "cached": cached, "latency_ms": latency_ms}

    @application.get("/api/v1/dashboard/overview", tags=["dashboard"])
    def dashboard_overview(
        start_date: date | None = None,
        end_date: date | None = None,
        source: str | None = Query(default=None, pattern="^(ai|human)$"),
        job_category: str | None = None,
        region: str | None = None,
        model_version: str | None = None,
        recruiter_team: str | None = None,
    ) -> dict:
        """Return the prewarmed analysis snapshot without the ML payload."""
        filters = {
            "start_date": start_date,
            "end_date": end_date,
            "source": source,
            "job_category": job_category,
            "region": region,
            "model_version": model_version,
            "recruiter_team": recruiter_team,
        }
        context, cached, latency_ms = analysis_context_service.get(filters)
        metrics.record(
            "dashboard_context",
            latency_ms=latency_ms,
            success=True,
            cached=cached,
        )
        prometheus_metrics.record_context(cached=cached)
        dashboard_context = {
            key: value for key, value in context.items() if key != "prediction"
        }
        return {**dashboard_context, "cached": cached, "latency_ms": latency_ms}

    @application.get(
        "/api/v1/assistant/context/status",
        tags=["assistant"],
        dependencies=[Depends(operations_access)],
    )
    def assistant_context_status() -> dict:
        dataset_version = load_dataset_version()
        return {
            "dataset_version": dataset_version,
            "prewarm": application.state.analysis_prewarm.status(),
            "materialized": snapshot_store.status(dataset_version),
            "cache_backend": getattr(shared_cache, "backend_name", "unknown"),
        }

    @application.post(
        "/api/v1/assistant/analyze",
        response_model=AssistantResponse,
        tags=["assistant"],
    )
    def assistant_analyze(request: AssistantRequest) -> dict:
        service = application.state.assistant_service
        if service is None:
            raise HTTPException(
                status_code=503,
                detail="AI assistant is not configured",
            )
        started = time.perf_counter()
        try:
            answer, cached, latency_ms = service.analyze(
                request.context,
                [message.model_dump() for message in request.messages],
                force_refresh=request.force_refresh,
            )
        except AssistantServiceError as exc:
            status_code = exc.status_code
            metrics.record(
                "assistant_analyze",
                latency_ms=round((time.perf_counter() - started) * 1000),
                success=False,
                error_code=status_code or "provider_error",
            )
            prometheus_metrics.record_assistant(
                mode="structured",
                success=False,
            )
            LOGGER.warning("assistant_request_failed status_code=%s", status_code)
            if status_code == 401:
                raise HTTPException(
                    status_code=401, detail="DeepSeek authentication failed"
                ) from exc
            if status_code == 429:
                raise HTTPException(
                    status_code=429, detail="DeepSeek rate limit or balance limit"
                ) from exc
            if status_code == 402:
                raise HTTPException(
                    status_code=402, detail="DeepSeek balance is insufficient"
                ) from exc
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        total_latency_ms = latency_ms or round((time.perf_counter() - started) * 1000)
        trust = build_assistant_trust(request.context)
        answer = apply_trust_guard(answer, trust)
        metrics.record(
            "assistant_analyze",
            latency_ms=total_latency_ms,
            success=True,
            cached=cached,
            tokens=0 if cached else answer.total_tokens,
        )
        prometheus_metrics.record_assistant(
            mode="structured",
            success=True,
            cached=cached,
            tokens=0 if cached else answer.total_tokens or 0,
        )
        return {
            "conclusion": answer.conclusion,
            "evidence": answer.evidence,
            "risks": answer.risks,
            "recommendations": answer.recommendations,
            "model": settings.assistant_model,
            "cached": cached,
            "latency_ms": total_latency_ms,
            "total_tokens": answer.total_tokens,
            "trust": trust,
        }

    @application.post("/api/v1/assistant/analyze/stream", tags=["assistant"])
    def assistant_analyze_stream(request: AssistantRequest) -> StreamingResponse:
        service = application.state.assistant_service
        if service is None:
            raise HTTPException(status_code=503, detail="AI assistant is not configured")

        messages = [message.model_dump() for message in request.messages]
        trust = build_assistant_trust(request.context)

        def event(event_name: str, payload: dict) -> str:
            return (
                f"event: {event_name}\n"
                f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"
            )

        def generate():
            started = time.perf_counter()
            first_delta_recorded = False
            yield event(
                "metadata",
                {"model": settings.assistant_model, "trust": trust},
            )
            parts: list[str] = []
            try:
                for part in service.stream_markdown(request.context, messages):
                    if not first_delta_recorded:
                        metrics.record(
                            "assistant_stream_ttft",
                            latency_ms=round((time.perf_counter() - started) * 1000),
                            success=True,
                        )
                        first_delta_recorded = True
                    parts.append(part)
                    yield event("delta", {"content": part})
                metrics.record(
                    "assistant_stream_total",
                    latency_ms=round((time.perf_counter() - started) * 1000),
                    success=True,
                )
                prometheus_metrics.record_assistant(mode="stream", success=True)
                yield event(
                    "done",
                    {"content": "".join(parts), "model": settings.assistant_model, "trust": trust},
                )
            except AssistantServiceError as exc:
                metrics.record(
                    "assistant_stream_total",
                    latency_ms=round((time.perf_counter() - started) * 1000),
                    success=False,
                    error_code=exc.status_code or "provider_error",
                )
                prometheus_metrics.record_assistant(mode="stream", success=False)
                LOGGER.warning("assistant_stream_failed status_code=%s", exc.status_code)
                yield event(
                    "error",
                    {"detail": str(exc), "status_code": exc.status_code},
                )

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @application.get("/api/v1/meta/filters", response_model=FilterOptions, tags=["analytics"])
    def filters(session: DbSession) -> dict:
        return get_filter_options(session)

    @application.get("/api/v1/overview", response_model=OverviewResponse, tags=["analytics"])
    def overview(
        session: DbSession,
        start_date: date | None = None,
        end_date: date | None = None,
        source: str | None = Query(default=None, pattern="^(ai|human)$"),
        job_category: str | None = None,
        region: str | None = None,
        model_version: str | None = None,
        recruiter_team: str | None = None,
    ) -> dict:
        return get_overview(
            session,
            start_date=start_date,
            end_date=end_date,
            source=source,
            job_category=job_category,
            region=region,
            model_version=model_version,
            recruiter_team=recruiter_team,
        )

    @application.get("/api/v1/funnel", response_model=list[FunnelRow], tags=["analytics"])
    def funnel(
        session: DbSession,
        start_date: date | None = None,
        end_date: date | None = None,
        source: str | None = Query(default=None, pattern="^(ai|human)$"),
        job_category: str | None = None,
        region: str | None = None,
        model_version: str | None = None,
        recruiter_team: str | None = None,
    ) -> list[dict]:
        return get_funnel(
            session,
            start_date=start_date,
            end_date=end_date,
            source=source,
            job_category=job_category,
            region=region,
            model_version=model_version,
            recruiter_team=recruiter_team,
        )

    @application.get(
        "/api/v1/monitoring",
        response_model=MonitoringResponse,
        tags=["analytics"],
    )
    def monitoring(
        session: DbSession,
        start_date: date | None = None,
        end_date: date | None = None,
        source: str | None = Query(default=None, pattern="^(ai|human)$"),
        job_category: str | None = None,
        region: str | None = None,
        model_version: str | None = None,
        recruiter_team: str | None = None,
    ) -> dict:
        return get_monitoring(
            session,
            start_date=start_date,
            end_date=end_date,
            source=source,
            job_category=job_category,
            region=region,
            model_version=model_version,
            recruiter_team=recruiter_team,
        )

    @application.get(
        "/api/v1/data-quality",
        response_model=DataQualityResponse,
        tags=["analytics"],
    )
    def data_quality(
        session: DbSession,
        start_date: date | None = None,
        end_date: date | None = None,
        source: str | None = Query(default=None, pattern="^(ai|human)$"),
        job_category: str | None = None,
        region: str | None = None,
        model_version: str | None = None,
        recruiter_team: str | None = None,
    ) -> dict:
        return get_data_quality(
            session,
            start_date=start_date,
            end_date=end_date,
            source=source,
            job_category=job_category,
            region=region,
            model_version=model_version,
            recruiter_team=recruiter_team,
        )

    @application.get(
        "/api/v1/prediction-insights",
        response_model=PredictionInsightsResponse,
        tags=["analytics"],
    )
    def prediction_insights(
        session: DbSession,
        start_date: date | None = None,
        end_date: date | None = None,
        source: str | None = Query(default=None, pattern="^(ai|human)$"),
        job_category: str | None = None,
        region: str | None = None,
        model_version: str | None = None,
        recruiter_team: str | None = None,
        anomaly_limit: int = Query(default=12, ge=1, le=100),
        anomaly_offset: int = Query(default=0, ge=0),
    ) -> dict:
        filters = {
            "start_date": start_date,
            "end_date": end_date,
            "source": source,
            "job_category": job_category,
            "region": region,
            "model_version": model_version,
            "recruiter_team": recruiter_team,
            "anomaly_limit": anomaly_limit,
            "anomaly_offset": anomaly_offset,
        }
        cache_key = tuple(filters.items())
        now = time.monotonic()
        cached = prediction_cache.get(cache_key)
        if cached and now - cached[0] < 60:
            return cached[1]
        result = get_prediction_insights(session, **filters)
        prediction_cache[cache_key] = (now, result)
        if len(prediction_cache) > 64:
            oldest_key = min(prediction_cache, key=lambda key: prediction_cache[key][0])
            prediction_cache.pop(oldest_key, None)
        return result


    @application.get(
        "/api/v1/effectiveness/unadjusted",
        response_model=EffectivenessResponse,
        tags=["analytics"],
    )
    def effectiveness(
        session: DbSession,
        start_date: date | None = None,
        end_date: date | None = None,
        source: str | None = Query(default=None, pattern="^(ai|human)$"),
        job_category: str | None = None,
        region: str | None = None,
        model_version: str | None = None,
        recruiter_team: str | None = None,
    ) -> dict:
        return get_effectiveness(
            session,
            start_date=start_date,
            end_date=end_date,
            source=source,
            job_category=job_category,
            region=region,
            model_version=model_version,
            recruiter_team=recruiter_team,
        )

    application.state.telemetry_provider = configure_telemetry(
        application,
        endpoint=settings.otel_exporter_endpoint,
        service_name=settings.otel_service_name,
    )
    return application


app = create_app()
