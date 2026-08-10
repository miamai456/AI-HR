# ADR 0008: PostgreSQL migrations and observability runtime

## Status

Accepted

## Context

Production needs repeatable schema changes, shared background analysis, durable metrics, and
deployment secrets that are not stored in the repository. The workstation also requires all
persistent runtime data to remain off the C drive.

## Decision

- Keep PostgreSQL as the production database and SQLite as a lightweight local-test option.
- Use Alembic to version PostgreSQL schema changes. Alembic changes table structure; it does not
  replace PostgreSQL or move business data to another database engine.
- Run alembic upgrade head before the API process starts.
- Use Redis and RQ for shared analysis-context prewarming, with a local-thread fallback.
- Expose authenticated Prometheus metrics and OTLP traces from FastAPI.
- Provision Prometheus alert rules and a Grafana operations dashboard through Compose.
- Store PostgreSQL, Redis, Prometheus, Grafana, and deployment-secret files under E:\AIHRData.
- Mount PostgreSQL, Grafana, DeepSeek, and operations credentials as read-only secret files.
- Refuse to run the Compose integration script until an E-drive Docker Desktop data directory is
  explicitly declared.

## Consequences

Existing PostgreSQL installations need a one-time Alembic stamp at the baseline revision before
upgrading. New databases apply all migrations normally. Repository configuration contains only
secret paths. Docker Desktop's own image and VM storage must be moved to E separately because
Compose bind mounts cannot relocate it. OTel traces are currently emitted to the Collector debug
exporter; historical trace search requires a durable backend such as Tempo.
