# Ecuador Public Procurement Data Quality Monitor

**Status: Architecture and initial development**

## Problem

Public procurement records need a reproducible way to identify incomplete,
inconsistent, and otherwise questionable data while preserving the evidence
used to produce each result. This project establishes an auditable data
quality workflow for Ecuadorian public procurement records.

Empresa Eléctrica Quito S.A. E.E.Q. is the first case study. The project is
academic and independent; it is not affiliated with or endorsed by SERCOP or
Empresa Eléctrica Quito.

## Version 1 scope

Version 1 will be a modular monolith executed through a CLI and batch
processing. It will preserve source responses in immutable raw storage and
use PostgreSQL for normalized data, audit records, and quality results.
Docker Compose is planned for local PostgreSQL infrastructure in a later
task. Version 1 does not include microservices, Kafka, Redis, Kubernetes,
authentication, or a load balancer.

The first vertical flow will define concrete raw-storage paths, compression,
retention, metadata schema, and source-specific contracts. Those details are
intentionally not fixed by this baseline.

## Architecture

The system is separated into `domain`, `application`, `infrastructure`, and
`interfaces`. Ports and adapters prevent the domain from depending directly
on SERCOP, PostgreSQL, CLI frameworks, or local storage.

The design prioritizes auditability, idempotency, traceability,
reproducibility, resumability, and testability. No application functionality
is claimed to exist yet.

See [the architecture](docs/architecture.md) and the accepted decisions:

- [ADR 0001: Modular monolith](docs/adr/0001-modular-monolith.md)
- [ADR 0002: Immutable raw storage](docs/adr/0002-immutable-raw-storage.md)
- [ADR 0003: No distributed infrastructure in v1](docs/adr/0003-no-distributed-infrastructure-in-v1.md)
- [ADR 0004: Python toolchain](docs/adr/0004-python-toolchain.md)

## Technologies

Implemented in the repository:

- Python 3.13.9 is available in the local virtual environment.
- Git-based source and documentation management.

Planned, not implemented by this baseline:

- Python application modules and a CLI.
- PostgreSQL for normalized records, audit, and quality results.
- Docker Compose for local PostgreSQL execution.
- A SERCOP adapter and storage adapters.

No real downloaded responses will be committed to this repository. Fixtures
used for development must be minimal and deliberately selected.
