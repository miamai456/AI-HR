# ADR 0006: Shared cache, prewarm, and assistant observability

## Status

Accepted

## Context

Analysis context calculation can take many seconds on a cold cache. The previous in-process caches
were lost on restart and could not be shared by multiple API workers. Assistant quality and latency
also lacked a repeatable release gate.

## Decision

- Use a small JSON cache interface for analysis snapshots and structured assistant answers.
- Use Redis with AOF persistence in Docker Compose and an in-memory fallback for local development.
- Prewarm the unfiltered, AI-source, and human-source analysis scopes with an RQ worker when Redis
  is available and `AIHR_ANALYSIS_QUEUE_ENABLED=true`.
- Fall back to a background thread for local development or temporary Redis outages.
- Coalesce concurrent in-process loads for the same expensive cache key.
- Expose process-level latency percentiles, success rates, cache hit rates, token totals, and error
  counts from `/api/v1/metrics/performance`.
- Maintain fixed assistant evaluation cases and run live model evaluation explicitly before release.

## Consequences

Warm responses survive API worker replacement when Redis is available. The API remains functional
when Redis is unavailable, but cache persistence and cross-worker sharing are then lost. Metrics are
process-local and are diagnostic rather than a replacement for Prometheus or another durable
monitoring system. Prometheus now scrapes the standard metrics endpoint for durable aggregation
and alert evaluation.
