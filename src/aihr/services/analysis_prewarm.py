import logging
from dataclasses import dataclass
from threading import Thread
from typing import Any

from aihr.jobs import prewarm_analysis_context_job
from aihr.services.analysis_context import AnalysisContextService

LOGGER = logging.getLogger(__name__)


@dataclass
class AnalysisPrewarmHandle:
    mode: str
    service: AnalysisContextService
    job: Any | None = None
    fallback_reason: str = ""

    def status(self) -> dict:
        if self.mode == "disabled":
            return {"mode": "disabled", **self.service.status()}
        if self.mode == "local":
            return {
                "mode": "local",
                "fallback_reason": self.fallback_reason or None,
                **self.service.status(),
            }

        try:
            queue_status = self.job.get_status(refresh=True)
            status_value = getattr(queue_status, "value", str(queue_status))
        except Exception as exc:
            LOGGER.warning("analysis_prewarm_status_unavailable error=%s", exc)
            return {
                "mode": "queue",
                "status": "unknown",
                "job_id": self.job.id,
            }
        status_map = {
            "queued": "queued",
            "deferred": "queued",
            "scheduled": "queued",
            "started": "running",
            "finished": "ready",
            "failed": "degraded",
            "stopped": "degraded",
            "canceled": "degraded",
        }
        return {
            "mode": "queue",
            "status": status_map.get(status_value, status_value),
            "job_id": self.job.id,
        }


def start_analysis_prewarm(
    *,
    enabled: bool,
    queue_enabled: bool,
    queue_name: str,
    database_url: str,
    cache_url: str,
    cache_prefix: str,
    ttl_seconds: int,
    service: AnalysisContextService,
    scopes: list[dict],
) -> AnalysisPrewarmHandle:
    if not enabled:
        return AnalysisPrewarmHandle(mode="disabled", service=service)

    fallback_reason = ""
    if queue_enabled and cache_url.startswith(("redis://", "rediss://")):
        try:
            from redis import Redis
            from rq import Queue

            connection = Redis.from_url(
                cache_url,
                socket_connect_timeout=1,
                socket_timeout=2,
            )
            connection.ping()
            job = Queue(queue_name, connection=connection).enqueue_call(
                func=prewarm_analysis_context_job,
                args=(
                    database_url,
                    cache_url,
                    cache_prefix,
                    ttl_seconds,
                    scopes,
                ),
                timeout=1800,
                result_ttl=86400,
            )
            return AnalysisPrewarmHandle(mode="queue", service=service, job=job)
        except Exception as exc:
            fallback_reason = type(exc).__name__
            LOGGER.warning(
                "analysis_prewarm_queue_unavailable fallback=local error=%s",
                exc,
            )

    Thread(
        target=service.prewarm,
        args=(scopes,),
        name="aihr-analysis-prewarm",
        daemon=True,
    ).start()
    return AnalysisPrewarmHandle(
        mode="local",
        service=service,
        fallback_reason=fallback_reason,
    )
