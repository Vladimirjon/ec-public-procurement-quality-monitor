# ADR 0002: Immutable raw storage

- Status: Accepted
- Date: 2026-08-03

## Context

Quality findings must be reproducible and auditable. Normalized data alone
cannot preserve the exact source evidence used during ingestion.

## Decision

Preserve each original source response in raw storage before transformation.
From the application's perspective, raw evidence is append-only: an existing
response must not be silently overwritten or altered. Each preserved item
must be identifiable, associated with its source and ingestion execution,
integrity-checkable, and linkable to downstream processing and outcomes.

The baseline deliberately does not fix paths, compression, retention, or a
final metadata schema. Those details will be selected during the first
vertical flow using observed source behavior and approved operational
requirements.

## Consequences

The system can replay transformations, investigate quality findings, and
compare processing outcomes against source evidence. It must manage storage
growth, duplicate responses, incomplete responses, and access to potentially
sensitive downloaded content. These concerns will be addressed by the first
vertical flow and its tests.
