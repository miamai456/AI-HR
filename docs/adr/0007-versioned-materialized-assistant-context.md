# ADR 0007: Versioned materialized assistant context

## Status

Accepted

## Context

Redis and in-memory caches improve repeated requests but do not remove expensive cold calculation
after a local restart without Redis. Fixed TTL expiration also cannot determine whether hiring facts
actually changed.

## Decision

- Store common assistant analysis results in `mart_analysis_context_snapshot`.
- Maintain the current hiring-facts version in `system_data_version`.
- Include the dataset version in memory and Redis cache keys.
- Read a version-matching database snapshot before running analytics queries.
- Refresh missing or stale snapshots through the existing background prewarm process.
- Bump the hiring-facts version after synthetic recommendation and funnel facts are first created.
- Do not bump this version for LinkedIn job-market imports because those rows are not hiring outcomes.
- Expose snapshot and prewarm state from `/api/v1/assistant/context/status`.

## Consequences

The three common scopes remain fast across local API restarts after their first materialization.
Custom filter combinations materialize on first use. Future ATS importers must call
`bump_dataset_version` in the same transaction that commits changed hiring facts. Old cache entries
remain harmless because their keys contain the previous version; database snapshots are overwritten
when the same scope is refreshed.
