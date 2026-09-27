# ADR 0001: Modular monolith

- Status: Accepted
- Date: 2026-08-03

## Context

The project needs an auditable data-quality workflow for Ecuadorian public
procurement records, beginning with Empresa Eléctrica Quito S.A. E.E.Q. The
initial workload and operational requirements do not justify independently
deployable services.

## Decision

Build version 1 as a modular monolith with explicit `domain`, `application`,
`infrastructure`, and `interfaces` layers. External systems and persistence
are accessed through ports and adapters. The first operational interface is a
CLI that runs bounded batch processing.

The domain must remain independent of SERCOP, PostgreSQL, local storage, and
interface frameworks.

## Consequences

This keeps deployment, debugging, testing, and audit tracing small enough for
the initial project while preserving boundaries that can support later
change. The monolith remains a single operational unit, so scaling and fault
isolation are limited until measured needs justify a different decision.

Microservices and framework-specific coupling are deferred, not prohibited
forever. A future change requires evidence and a new or superseding decision.
