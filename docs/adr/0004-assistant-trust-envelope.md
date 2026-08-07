# ADR 0004: Server-Owned Assistant Trust Envelope

## Status

Accepted

## Context

Structured model output alone does not make an analytical conclusion trustworthy.
Every conclusion needs the sample size, analysis period, active filters, data
freshness, data-quality status, confidence guidance, and an explicit distinction
between observational association and causal effect.

## Decision

FastAPI computes a trust envelope from the analysis context and appends it to every
assistant response. The model does not self-report or control these fields. The
envelope contains sample size, period, filters, latest data timestamp, quality
status, confidence, analysis type, and `causal_claim=false`.

When the sample contains fewer than 30 recommendations, a quality check fails, or
quality information is unavailable, the API forces the answer to an exploratory
finding and adds a limitation risk. Streamlit renders the envelope for both
DeepSeek answers and local-rule fallback answers.

## Consequences

Callers can render a consistent confidence statement and cannot accidentally treat
low-quality output as a strong conclusion. The current context still originates
from internal dashboard requests; a future external assistant interface should
accept filter parameters and assemble the analytical context entirely on the
server.
