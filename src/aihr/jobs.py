from aihr.database import create_engine_and_session
from aihr.services.analysis_runtime import build_analysis_context_service
from aihr.services.cache import create_json_cache


def prewarm_analysis_context_job(
    database_url: str,
    cache_url: str,
    cache_prefix: str,
    ttl_seconds: int,
    scopes: list[dict],
) -> dict:
    engine, session_factory = create_engine_and_session(database_url)
    try:
        cache = create_json_cache(cache_url, prefix=cache_prefix)
        service = build_analysis_context_service(
            session_factory,
            cache,
            ttl_seconds=ttl_seconds,
        )
        service.prewarm(scopes)
        return service.status()
    finally:
        engine.dispose()
