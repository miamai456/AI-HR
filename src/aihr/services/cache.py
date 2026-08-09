import json
import logging
import time
from collections.abc import Callable
from hashlib import sha256
from threading import Lock
from typing import Any, Generic, Protocol, TypeVar

T = TypeVar("T")
LOGGER = logging.getLogger(__name__)


class JsonCache(Protocol):
    def get(self, key: str) -> Any | None: ...

    def set(self, key: str, value: Any, *, ttl_seconds: int) -> None: ...

    def delete(self, key: str) -> None: ...


class MemoryJsonCache:
    backend_name = "memory"

    def __init__(self):
        self._entries: dict[str, tuple[float, Any]] = {}
        self._lock = Lock()

    def get(self, key: str) -> Any | None:
        now = time.monotonic()
        with self._lock:
            cached = self._entries.get(key)
            if not cached:
                return None
            if now - cached[0] >= 0:
                self._entries.pop(key, None)
                return None
            return cached[1]

    def set(self, key: str, value: Any, *, ttl_seconds: int) -> None:
        with self._lock:
            self._entries[key] = (time.monotonic() + ttl_seconds, value)

    def delete(self, key: str) -> None:
        with self._lock:
            self._entries.pop(key, None)


class RedisJsonCache:
    backend_name = "redis"

    def __init__(self, client: Any, *, prefix: str = "aihr"):
        self.client = client
        self.prefix = prefix

    def _key(self, key: str) -> str:
        digest = sha256(key.encode("utf-8")).hexdigest()
        return f"{self.prefix}:{digest}"

    def get(self, key: str) -> Any | None:
        value = self.client.get(self._key(key))
        if value is None:
            return None
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        return json.loads(value)

    def set(self, key: str, value: Any, *, ttl_seconds: int) -> None:
        serialized = json.dumps(value, ensure_ascii=False, default=str)
        self.client.setex(self._key(key), ttl_seconds, serialized)

    def delete(self, key: str) -> None:
        self.client.delete(self._key(key))


class FallbackJsonCache:
    backend_name = "redis"

    def __init__(self, primary: JsonCache, fallback: JsonCache):
        self.primary = primary
        self.fallback = fallback

    def get(self, key: str) -> Any | None:
        try:
            value = self.primary.get(key)
        except Exception as exc:
            LOGGER.warning("cache_read_failed fallback=memory error=%s", type(exc).__name__)
            return self.fallback.get(key)
        return value if value is not None else self.fallback.get(key)

    def set(self, key: str, value: Any, *, ttl_seconds: int) -> None:
        self.fallback.set(key, value, ttl_seconds=ttl_seconds)
        try:
            self.primary.set(key, value, ttl_seconds=ttl_seconds)
        except Exception as exc:
            LOGGER.warning("cache_write_failed fallback=memory error=%s", type(exc).__name__)

    def delete(self, key: str) -> None:
        self.fallback.delete(key)
        try:
            self.primary.delete(key)
        except Exception as exc:
            LOGGER.warning("cache_delete_failed fallback=memory error=%s", type(exc).__name__)


def create_json_cache(cache_url: str, *, prefix: str = "aihr") -> JsonCache:
    if not cache_url:
        return MemoryJsonCache()
    try:
        from redis import Redis

        client = Redis.from_url(
            cache_url,
            socket_connect_timeout=1,
            socket_timeout=1,
            health_check_interval=30,
        )
        client.ping()
        return FallbackJsonCache(
            RedisJsonCache(client, prefix=prefix),
            MemoryJsonCache(),
        )
    except Exception as exc:
        LOGGER.warning(
            "redis_cache_unavailable fallback=memory error=%s", type(exc).__name__
        )
        return MemoryJsonCache()


class TTLCache(Generic[T]):
    def __init__(self, *, ttl_seconds: int = 60, max_entries: int = 128):
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._entries: dict[tuple, tuple[float, T]] = {}
        self._lock = Lock()
        self._load_locks: dict[tuple, Lock] = {}

    def get_or_load(
        self,
        key: tuple,
        loader: Callable[[], T],
        *,
        force_refresh: bool = False,
    ) -> tuple[T, bool, int]:
        now = time.monotonic()
        if not force_refresh:
            with self._lock:
                cached = self._entries.get(key)
                if cached and now - cached[0] < self.ttl_seconds:
                    return cached[1], True, 0

        with self._lock:
            load_lock = self._load_locks.setdefault(key, Lock())

        with load_lock:
            now = time.monotonic()
            if not force_refresh:
                with self._lock:
                    cached = self._entries.get(key)
                    if cached and now - cached[0] < self.ttl_seconds:
                        return cached[1], True, 0

            started = time.perf_counter()
            value = loader()
            latency_ms = max(round((time.perf_counter() - started) * 1000), 1)
            with self._lock:
                self._entries[key] = (time.monotonic(), value)
                if len(self._entries) > self.max_entries:
                    oldest_key = min(self._entries, key=lambda item: self._entries[item][0])
                    self._entries.pop(oldest_key, None)
            return value, False, latency_ms

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
