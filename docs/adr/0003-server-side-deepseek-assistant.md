# ADR 0003: Server-Side DeepSeek Assistant

## Status

Accepted

## Context

The Streamlit dashboard previously called the Kimi-compatible endpoint directly.
That exposed provider configuration to the presentation layer, made authentication
failures visible as raw HTTP errors, and allowed repeated clicks to create duplicate
requests. The assistant also returned free-form text, which made the dashboard hard
to render consistently.

## Decision

The FastAPI service owns all DeepSeek calls. The Streamlit dashboard calls the
internal assistant endpoint and never receives the provider API key. The service
uses bounded timeouts, retries for transient failures, explicit handling for
authentication, rate-limit, and balance errors, and a short-lived in-memory cache.

Assistant responses use a stable JSON object with `conclusion`, `evidence`,
`risks`, and `recommendations`. Each request logs provider model, latency, token
usage, cache status, and error status when applicable.

DeepSeek settings are injected through `AIHR_ASSISTANT_*` environment variables.
Local development may read `.streamlit/secrets.toml`; that file remains ignored
and is never copied into the dashboard container.

## Consequences

The API becomes the single integration boundary and can later add persistent
cache storage, request tracing, or another provider without changing dashboard
pages. The current cache is process-local and therefore resets on restart and is
not shared across multiple API replicas.
