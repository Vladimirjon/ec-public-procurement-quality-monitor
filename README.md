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
reproducibility, resumability, and testability. Only the project skeleton
exists so far: the four layer packages are empty and the CLI only reports its
version. No domain behavior is claimed to exist yet.

See [the architecture](docs/architecture.md) and the accepted decisions:

- [ADR 0001: Modular monolith](docs/adr/0001-modular-monolith.md)
- [ADR 0002: Immutable raw storage](docs/adr/0002-immutable-raw-storage.md)
- [ADR 0003: No distributed infrastructure in v1](docs/adr/0003-no-distributed-infrastructure-in-v1.md)
- [ADR 0004: Python toolchain](docs/adr/0004-python-toolchain.md)

## Technologies

Implemented in the repository:

- Python 3.13 (`requires-python = ">=3.13"`), managed with `uv` and a
  committed `uv.lock` ([ADR 0004](docs/adr/0004-python-toolchain.md)).
- The `ec_procurement_quality` package under `src/` with the four empty layer
  packages and the `ec-procurement-quality` CLI, which only supports
  `--version`.
- `ruff` (lint and format), `mypy` (strict in `domain` only), `pytest` and
  `pytest-cov` as development-only dependencies.
- Two GitHub Actions workflows on pull requests: `feedback` (`ruff` and `mypy`,
  plus a secret scan) and `Tests` (unit tests with a coverage report).
- Git-based source and documentation management.

Planned, not implemented yet:

- PostgreSQL for normalized records, audit, and quality results.
- Docker Compose for local PostgreSQL execution.
- A SERCOP adapter and storage adapters.
- Real CLI commands beyond `--version`.

## Development commands

Run these from the repository root. They need [uv](https://docs.astral.sh/uv/).

| Task | Command |
|---|---|
| Install from the lockfile | `uv sync --locked` |
| Run the CLI | `uv run ec-procurement-quality --version` |
| Lint | `uv run ruff check .` |
| Check formatting | `uv run ruff format --check .` |
| Apply formatting | `uv run ruff format .` |
| Type check | `uv run mypy .` |
| Test | `uv run pytest` |
| Test with coverage report (what CI runs) | `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing` |

The `Tests` workflow runs the coverage command on every pull request and on
every push to `main`. It reports coverage only: no minimum percentage is
enforced, and a failing test fails the check. `Tests` is not yet a required
check of `main`; only `feedback` is.

The Stop hook (after each agent turn) and the pre-commit hook run `ruff` and
`mypy` on the touched or staged Python files only when `.venv` is on `PATH`.
When it is not, they skip those checks without failing. Activate the
environment (for example `.venv\Scripts\Activate.ps1` on PowerShell) or run
the commands above through `uv run` to get the same checks locally. CI does
not depend on this: the `feedback` workflow puts `.venv` on `PATH` itself.

No real downloaded responses will be committed to this repository. Fixtures
used for development must be minimal and deliberately selected.
