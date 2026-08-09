import math
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock


@dataclass
class OperationMetrics:
    latencies: deque[int]
    count: int = 0
    successes: int = 0
    cache_hits: int = 0
    cache_observations: int = 0
    total_tokens: int = 0
    errors: Counter[str] = field(default_factory=Counter)


class MetricsRegistry:
    def __init__(self, *, max_samples: int = 1_000):
        self.max_samples = max_samples
        self.started_at = datetime.now(UTC)
        self._operations: dict[str, OperationMetrics] = {}
        self._lock = Lock()

    def record(
        self,
        operation: str,
        *,
        latency_ms: int,
        success: bool,
        cached: bool | None = None,
        tokens: int | None = None,
        error_code: str | int | None = None,
    ) -> None:
        with self._lock:
            metrics = self._operations.setdefault(
                operation,
                OperationMetrics(deque(maxlen=self.max_samples)),
            )
            metrics.count += 1
            metrics.successes += int(success)
            metrics.latencies.append(max(latency_ms, 0))
            if cached is not None:
                metrics.cache_observations += 1
                metrics.cache_hits += int(cached)
            if tokens:
                metrics.total_tokens += tokens
            if error_code is not None:
                metrics.errors[str(error_code)] += 1

    @staticmethod
    def _percentile(values: deque[int], percentile: float) -> int:
        if not values:
            return 0
        ordered = sorted(values)
        index = max(math.ceil(percentile * len(ordered)) - 1, 0)
        return ordered[index]

    def snapshot(self) -> dict[str, dict]:
        with self._lock:
            return {
                name: {
                    "count": metrics.count,
                    "success_rate": (
                        metrics.successes / metrics.count if metrics.count else 0.0
                    ),
                    "cache_hit_rate": (
                        metrics.cache_hits / metrics.cache_observations
                        if metrics.cache_observations
                        else None
                    ),
                    "latency_ms": {
                        "p50": self._percentile(metrics.latencies, 0.50),
                        "p95": self._percentile(metrics.latencies, 0.95),
                        "p99": self._percentile(metrics.latencies, 0.99),
                    },
                    "total_tokens": metrics.total_tokens,
                    "errors": dict(metrics.errors),
                }
                for name, metrics in self._operations.items()
            }
