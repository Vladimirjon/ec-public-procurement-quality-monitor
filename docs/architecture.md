# Architecture

## Status and scope

This document describes the accepted baseline for version 1. It is an
architectural guide, not evidence that the application has been implemented.
The first case study is Empresa Eléctrica Quito S.A. E.E.Q. public
procurement data.

Version 1 is a modular monolith, operated through a CLI and executed in
batches. It includes immutable raw evidence, PostgreSQL for normalized data,
auditing, and quality results, and a future Docker Compose setup for local
PostgreSQL infrastructure. It excludes microservices, Kafka, Redis,
Kubernetes, authentication, and a load balancer.

## Logical layers

### Domain

Owns procurement concepts, quality concepts, invariants, and domain rules.
It has no dependency on SERCOP, PostgreSQL, local files, Docker, or CLI
frameworks.

### Application

Coordinates ingestion, normalization, audit recording, quality evaluation,
and batch resumption through use cases and ports. It does not implement
transport or storage details.

### Infrastructure

Implements adapters for source access, raw storage, PostgreSQL persistence,
clocking, hashing, and other external concerns. Adapter contracts must be
based on approved observations rather than invented SERCOP behavior.

### Interfaces

Provides the CLI and translates command input, configuration, and exit
outcomes at the application boundary. It does not contain domain rules.

## Processing model

The intended batch flow is:

1. Accept a bounded ingestion request.
2. Retrieve and preserve the original source response.
3. Identify the response and execution using stable, auditable metadata.
4. Normalize records through application use cases.
5. Persist audit events and quality results in PostgreSQL.
6. Record success, failure, quarantine, or resumable progress.

The flow must be idempotent, resumable, traceable, reproducible, and
verifiable through tests. Exact command syntax, database schema, and source
contract belong to the first vertical flow.

## Raw evidence boundary

Raw storage is append-only from the application's perspective. Original
responses must remain recoverable, identifiable, associated with their
source and execution context, and protected from silent replacement.

[ADR 0005](adr/0005-raw-evidence-store-layout.md) fixes the layout of the
local raw evidence store: the exact response bytes are kept once under their
SHA-256 (an object), and each response obtained is recorded by a separate JSON
observation. The ADR also defines the observation fields, the rule that
`Set-Cookie` headers are never kept, and the integrity checks. The `domain`
layer holds the content hash, observation, and evidence errors, the
`application` layer holds the storage port, and the `infrastructure` layer
holds the local-disk adapter. Compression and retention are not decided.

## Infrastructure boundary

PostgreSQL is the planned system of record for normalized procurement data,
audit information, and quality results. Docker Compose will later provide
the local PostgreSQL execution environment; it is part of the v1 operational
architecture but outside this documentation task.

No distributed infrastructure is justified until measurable workload,
reliability, or operational requirements demonstrate a need. See
[ADR 0003](adr/0003-no-distributed-infrastructure-in-v1.md).

## Open questions

- Which SERCOP endpoints and response variants are required for the first
  E.E.Q. flow? (Answered for the endpoints: the first flow uses `search_ocds`
  with the buyer-name query and `api/record`, as recorded in
  [the source observations](sources/sercop-observations.md) and implemented by
  the source adapter. Other response variants stay open until observed.)
- What are the minimum audit events and quality-rule contracts?
- Which raw-storage compression and retention policies are supported by
  observed usage and legal or operational requirements? (The paths and
  metadata fields of the local store are answered by
  [ADR 0005](adr/0005-raw-evidence-store-layout.md).)

The open questions are intentionally not resolved by this baseline.
