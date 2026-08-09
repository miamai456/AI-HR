import threading
import time
from datetime import date

from aihr.services.cache import (
    FallbackJsonCache,
    MemoryJsonCache,
    RedisJsonCache,
    TTLCache,
)


def test_memory_json_cache_expires_values() -> None:
    cache = MemoryJsonCache()
    cache.set("answer", {"value": 1}, ttl_seconds=1)

    assert cache.get("answer") == {"value": 1}
    cache._entries["answer"] = (time.monotonic() - 2, {"value": 1})
    assert cache.get("answer") is None


def test_redis_json_cache_serializes_dates() -> None:
    stored = {}

    class FakeRedis:
        def get(self, key):
            return stored.get(key)

        def setex(self, key, ttl_seconds, value):
            stored[key] = value

        def delete(self, key):
            stored.pop(key, None)

    cache = RedisJsonCache(FakeRedis(), prefix="test")
    cache.set("scope", {"start_date": date(2026, 1, 1)}, ttl_seconds=60)

    assert cache.get("scope") == {"start_date": "2026-01-01"}


def test_ttl_cache_coalesces_concurrent_loads() -> None:
    cache: TTLCache[dict] = TTLCache(ttl_seconds=60)
    barrier = threading.Barrier(3)
    calls = 0
    results = []

    def loader() -> dict:
        nonlocal calls
        calls += 1
        time.sleep(0.05)
        return {"value": 1}

    def run() -> None:
        barrier.wait()
        results.append(cache.get_or_load(("key",), loader))

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()

    assert calls == 1
    assert [cached for _, cached, _ in results].count(True) == 1


def test_fallback_json_cache_survives_primary_failure() -> None:
    class FailingCache:
        def get(self, key):
            raise ConnectionError

        def set(self, key, value, *, ttl_seconds):
            raise ConnectionError

        def delete(self, key):
            raise ConnectionError

    cache = FallbackJsonCache(FailingCache(), MemoryJsonCache())
    cache.set("answer", {"value": 1}, ttl_seconds=60)

    assert cache.get("answer") == {"value": 1}
    cache.delete("answer")
    assert cache.get("answer") is None
