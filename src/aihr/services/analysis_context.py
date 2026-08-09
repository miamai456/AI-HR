import json
import logging
import time
from collections.abc import Callable
from hashlib import sha256
from threading import Lock
from typing import Any

from aihr.services.cache import JsonCache

LOGGER = logging.getLogger(__name__)


class AnalysisContextService:
    def __init__(
        self,
        loader: Callable[[dict[str, Any]], dict],
        cache: JsonCache,
        *,
        ttl_seconds: int = 300,
        snapshot_store: Any | None = None,
        dataset_version_loader: Callable[[], str] | None = None,
    ):
        self.loader = loader
        self.cache = cache
        self.ttl_seconds = ttl_seconds
        self.snapshot_store = snapshot_store
        self.dataset_version_loader = dataset_version_loader or (lambda: "unversioned")
        self._locks: dict[str, Lock] = {}
        self._locks_guard = Lock()
        self._prewarm_status = "idle"
        self._prewarm_scopes = 0
        self._prewarm_errors = 0

    @staticmethod
    def _normalize_filters(filters: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in filters.items() if value is not None}

    @staticmethod
    def _cache_key(filters: dict[str, Any], dataset_version: str) -> str:
        normalized = AnalysisContextService._normalize_filters(filters)
        serialized = json.dumps(normalized, sort_keys=True, default=str, separators=(",", ":"))
        digest = sha256(serialized.encode("utf-8")).hexdigest()
        return f"analysis-context:{dataset_version}:{digest}"

    def get(
        self, filters: dict[str, Any], *, force_refresh: bool = False
    ) -> tuple[dict, bool, int]:
        dataset_version = self.dataset_version_loader()
        cache_key = self._cache_key(filters, dataset_version)
        normalized = self._normalize_filters(filters)
        if not force_refresh:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached, True, 0

        with self._locks_guard:
            load_lock = self._locks.setdefault(cache_key, Lock())
        with load_lock:
            if not force_refresh:
                cached = self.cache.get(cache_key)
                if cached is not None:
                    return cached, True, 0
                if self.snapshot_store is not None:
                    snapshot = self.snapshot_store.get(normalized, dataset_version)
                    if snapshot is not None:
                        self.cache.set(
                            cache_key,
                            snapshot,
                            ttl_seconds=self.ttl_seconds,
                        )
                        return snapshot, True, 0
            started = time.perf_counter()
            context = self.loader(normalized)
            latency_ms = max(round((time.perf_counter() - started) * 1000), 1)
            self.cache.set(cache_key, context, ttl_seconds=self.ttl_seconds)
            if self.snapshot_store is not None:
                self.snapshot_store.set(normalized, dataset_version, context)
            return context, False, latency_ms

    def prewarm(self, scopes: list[dict[str, Any]]) -> None:
        with self._locks_guard:
            self._prewarm_status = "running"
            self._prewarm_scopes = 0
            self._prewarm_errors = 0
        for filters in scopes:
            try:
                self.get(filters)
            except Exception:
                LOGGER.exception("analysis_context_prewarm_failed filters=%s", filters)
                with self._locks_guard:
                    self._prewarm_errors += 1
            finally:
                with self._locks_guard:
                    self._prewarm_scopes += 1
        with self._locks_guard:
            self._prewarm_status = (
                "degraded" if self._prewarm_errors else "ready"
            )

    def status(self) -> dict[str, int | str]:
        with self._locks_guard:
            return {
                "status": self._prewarm_status,
                "processed_scopes": self._prewarm_scopes,
                "errors": self._prewarm_errors,
            }
