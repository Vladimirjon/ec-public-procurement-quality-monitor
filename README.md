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

The layout of the local raw evidence store (paths, observation metadata, and
integrity rules) is fixed by
[ADR 0005](docs/adr/0005-raw-evidence-store-layout.md). Compression, retention,
and source-specific contracts are intentionally not fixed yet; the first
vertical flow will define them.

## Architecture

The system is separated into `domain`, `application`, `infrastructure`, and
`interfaces`. Ports and adapters prevent the domain from depending directly
on SERCOP, PostgreSQL, CLI frameworks, or local storage.

The design prioritizes auditability, idempotency, traceability,
reproducibility, resumability, and testability. Development is at an early
stage: the layers hold only the local raw evidence store and the SERCOP
source adapter described under Technologies, and the CLI only reports its
version. Nothing calls the adapter yet, and no ingestion, normalization, or
quality behavior exists.

See [the architecture](docs/architecture.md) and the accepted decisions:

- [ADR 0001: Modular monolith](docs/adr/0001-modular-monolith.md)
- [ADR 0002: Immutable raw storage](docs/adr/0002-immutable-raw-storage.md)
- [ADR 0003: No distributed infrastructure in v1](docs/adr/0003-no-distributed-infrastructure-in-v1.md)
- [ADR 0004: Python toolchain](docs/adr/0004-python-toolchain.md)
- [ADR 0005: Raw evidence store layout](docs/adr/0005-raw-evidence-store-layout.md)
- [ADR 0006: HTTP client for source access](docs/adr/0006-http-client-for-source-access.md)

## Technologies

Implemented in the repository:

- Python 3.13 (`requires-python = ">=3.13"`), managed with `uv` and a
  committed `uv.lock` ([ADR 0004](docs/adr/0004-python-toolchain.md)).
- The `ec_procurement_quality` package under `src/` with the four layer
  packages and the `ec-procurement-quality` CLI, which only supports
  `--version`.
- A local raw evidence store ([ADR 0005](docs/adr/0005-raw-evidence-store-layout.md)):
  the content hash, observation, and evidence errors in `domain`; the storage
  port in `application`; and a local-disk adapter in `infrastructure`. Under a
  root directory it keeps each response's exact bytes once, named by their
  SHA-256, plus one JSON observation record per response obtained, and it
  verifies integrity on read. It is a library only: no CLI command or use case
  calls it yet, and no default root path is wired in code (`data/raw/` is
  git-ignored for this purpose).
- A SERCOP source adapter ([ADR 0006](docs/adr/0006-http-client-for-source-access.md)):
  the raw response and the source errors in `domain`; the source port and its
  two result types in `application`; and the `httpx` adapter in
  `infrastructure`. It makes one request per call, either the buyer-name
  search (`search_ocds`) or one record by `ocid` (`api/record`), and returns
  the response as received or raises a typed error that carries the valid
  response that arrived, so that it can be stored as evidence; a status
  outside 100 to 599 is reported without a response. It does not retry and
  only spaces its requests. It is a library only: it has no CLI
  command, nothing calls it yet, and its tests use simulated transports and
  never reach the network.
- `httpx`, the first runtime dependency, used only in `infrastructure`
  (ADR 0006). The other dependencies are development-only: `ruff` (lint and
  format), `mypy` (strict in `domain` only), `pytest` and `pytest-cov`.
- Two GitHub Actions workflows on pull requests: `feedback` (`ruff` and `mypy`,
  plus a secret scan) and `Tests` (unit tests with a coverage report).
- Git-based source and documentation management.

Planned, not implemented yet:

- PostgreSQL for normalized records, audit, and quality results.
- Docker Compose for local PostgreSQL execution.
- The ingestion that will call the SERCOP adapter and the raw evidence store.
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
enforced, and a failing test fails the check. `tests` and `feedback` are both
required checks of `main`.

The Stop hook (after each agent turn) and the pre-commit hook run `ruff` and
`mypy` on the touched or staged Python files only when `.venv` is on `PATH`.
When it is not, they skip those checks without failing. Activate the
environment (for example `.venv\Scripts\Activate.ps1` on PowerShell) or run
the commands above through `uv run` to get the same checks locally. CI does
not depend on this: the `feedback` workflow puts `.venv` on `PATH` itself.

No real downloaded responses will be committed to this repository. Fixtures
used for development must be minimal and deliberately selected.
