# ADR 0003: No distributed infrastructure in version 1

- Status: Accepted
- Date: 2026-08-03

## Context

Version 1 is an academic and portfolio project with an initially unmeasured
workload. It needs reliable batch ingestion and auditability, not a broad
operations platform.

## Decision

Run version 1 as a CLI-driven modular monolith with batch processing and
PostgreSQL. Docker Compose will be introduced later to run PostgreSQL
locally. Do not introduce microservices, Kafka, Redis, Kubernetes,
authentication, or a load balancer in this version.

This decision does not exclude future infrastructure. It requires measurable
evidence before adding it, such as sustained batch duration, volume,
concurrency, availability requirements, failure frequency, or operational
burden that the current design cannot handle.

## Consequences

The initial system has a smaller operational surface and simpler end-to-end
testing and tracing. It may have limits in throughput, availability, and
fault isolation. Ports and adapters must therefore keep future alternatives
possible without pre-building them.
