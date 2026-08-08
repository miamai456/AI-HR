import time
from collections.abc import Callable
from threading import Lock
from typing import Generic, TypeVar

T = TypeVar("T")


class TTLCache(Generic[T]):
    def __init__(self, *, ttl_seconds: int = 60, max_entries: int = 128):
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._entries: dict[tuple, tuple[float, T]] = {}
        self._lock = Lock()

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
