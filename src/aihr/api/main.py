from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session

from aihr.config import get_settings
from aihr.database import Base, create_engine_and_session, get_db
from aihr.schemas import (
    DataQualityResponse,
    EffectivenessResponse,
    FilterOptions,
    FunnelRow,
    HealthResponse,
    MonitoringResponse,
    OverviewResponse,
)
from aihr.seed import SyntheticHiringConfig, seed_demo_metrics
from aihr.services.analytics import (
    get_data_quality,
    get_effectiveness,
    get_filter_options,
    get_funnel,
    get_monitoring,
    get_overview,
)

DbSession = Annotated[Session, Depends(get_db)]


def database_backend_for_url(database_url: str) -> str:
    return make_url(database_url).get_backend_name()


def create_app(database_url: str | None = None) -> FastAPI:
    settings = get_settings()
    resolved_database_url = database_url or settings.database_url
    engine, session_factory = create_engine_and_session(resolved_database_url)

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
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET"],
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
            "environment": settings.environment,
            "database": "ok",
            "database_backend": database_backend_for_url(resolved_database_url),
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
