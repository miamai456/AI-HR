# ADR 0009: MongoDB document center and React assistant workbench

## Status

Accepted

## Context

PostgreSQL is well suited to hiring facts, funnel events, metric marts, and relational analysis. Resumes, job descriptions, RAG chunks, conversations, and controlled-tool audit records have variable nested structures and different retention requirements. The Streamlit dashboard remains useful for internal analytics, but the assistant needs a dedicated typed interface for streaming answers, citations, and execution state.

## Decision

- Keep PostgreSQL as the only source of truth for structured hiring facts and metrics.
- Add MongoDB for redacted non-relational recruitment documents.
- Link documents to structured entities with a stable `source_id` and metadata such as `postgres_candidate_id` or `postgres_job_id`.
- Redact email addresses, mainland mobile numbers, and national ID numbers before persistence.
- Make writes idempotent on `(document_type, source_id)`.
- Use MongoDB text indexes for retrieval and a TTL index only for conversations and tool-audit records.
- Fall back to an in-memory document store when MongoDB is missing or unavailable, and expose the degradation through a health endpoint.
- Add a React/TypeScript/Vite workbench that consumes FastAPI SSE responses. Streamlit remains the analytics dashboard.
- Keep provider credentials and controlled Agent authorization on the FastAPI server.

## Consequences

The system now operates two databases, so backup, health checks, retention, and cross-store identifiers must be explicit. MongoDB failure can reduce document retrieval quality but must not make PostgreSQL analytics unavailable. The in-memory fallback is intentionally non-durable and reports `optional` or `degraded`; it is not presented as equivalent to MongoDB. The React workbench adds a Node build stage but is served as static files by Nginx in production.
