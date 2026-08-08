# ADR 0005: Stream assistant responses over SSE

## Status

Accepted

## Context

The assistant page previously waited for the complete DeepSeek response before showing any answer.
It also loaded five analytics resources separately, which increased first-render latency and could mix
snapshots calculated at slightly different times.

## Decision

- Expose one cached `/api/v1/assistant/context` endpoint for a filter-consistent analysis snapshot.
- Expose `/api/v1/assistant/analyze/stream` as a server-sent events endpoint.
- Send `metadata` first, incremental `delta` events during generation, and `done` or `error` last.
- Keep provider credentials and DeepSeek stream parsing in FastAPI.
- Keep the existing structured JSON endpoint for integrations that need strict fields.
- Render trust metadata as a collapsed Chinese disclosure above the final Streamlit answer.

## Consequences

The first visible response arrives before the full model answer. Cache hits can be served in
milliseconds, but an uncached complete model answer still depends on provider and database latency.
The application now maintains two presentation contracts: structured JSON and streamed Markdown.
