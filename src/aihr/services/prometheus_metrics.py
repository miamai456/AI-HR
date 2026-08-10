from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest


class PrometheusMetrics:
    def __init__(self):
        self.registry = CollectorRegistry()
        self.http_requests = Counter(
            "aihr_http_requests_total",
            "HTTP requests handled by AIHR",
            ("method", "path", "status"),
            registry=self.registry,
        )
        self.http_latency = Histogram(
            "aihr_http_request_duration_seconds",
            "AIHR HTTP request duration",
            ("method", "path"),
            buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
            registry=self.registry,
        )
        self.assistant_requests = Counter(
            "aihr_assistant_requests_total",
            "AIHR assistant requests",
            ("mode", "outcome", "cached"),
            registry=self.registry,
        )
        self.assistant_tokens = Counter(
            "aihr_assistant_tokens_total",
            "Tokens consumed by uncached assistant requests",
            registry=self.registry,
        )
        self.context_requests = Counter(
            "aihr_analysis_context_requests_total",
            "Analysis context cache outcomes",
            ("cached",),
            registry=self.registry,
        )

    def record_http(self, method: str, path: str, status: int, latency_ms: int) -> None:
        self.http_requests.labels(method=method, path=path, status=str(status)).inc()
        self.http_latency.labels(method=method, path=path).observe(latency_ms / 1000)

    def record_assistant(
        self,
        *,
        mode: str,
        success: bool,
        cached: bool = False,
        tokens: int = 0,
    ) -> None:
        self.assistant_requests.labels(
            mode=mode,
            outcome="success" if success else "error",
            cached=str(cached).lower(),
        ).inc()
        if tokens:
            self.assistant_tokens.inc(tokens)

    def record_context(self, *, cached: bool) -> None:
        self.context_requests.labels(cached=str(cached).lower()).inc()

    def render(self) -> bytes:
        return generate_latest(self.registry)
