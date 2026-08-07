import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session

from aihr import __version__
from aihr.config import get_settings
from aihr.database import Base, create_engine_and_session, get_db
from aihr.schemas import (
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
from aihr.services.analytics import (
    get_data_quality,
    get_effectiveness,
    get_filter_options,
    get_funnel,
    get_monitoring,
    get_overview,
    get_prediction_insights,
)
from aihr.services.assistant import AssistantClient, AssistantService, AssistantServiceError
from aihr.services.assistant_trust import apply_trust_guard, build_assistant_trust

DbSession = Annotated[Session, Depends(get_db)]
LOGGER = logging.getLogger(__name__)


def database_backend_for_url(database_url: str) -> str:
    return make_url(database_url).get_backend_name()


def create_app(database_url: str | None = None) -> FastAPI:
    settings = get_settings()
    resolved_database_url = database_url or settings.database_url
    engine, session_factory = create_engine_and_session(resolved_database_url)
    prediction_cache: dict[tuple, tuple[float, dict]] = {}
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
        yield
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
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
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
            },
        }

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

    return application


app = create_app()
