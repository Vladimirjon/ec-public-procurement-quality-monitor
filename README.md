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
Docker Compose runs that PostgreSQL locally for development
([ADR 0007](docs/adr/0007-postgresql-persistence.md)). The first schema, a
migration runner and a `psycopg` adapter exist as a library; nothing calls them
yet, so the application does not use the database. Version 1 does not include
microservices, Kafka, Redis, Kubernetes, authentication, or a load balancer.

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
stage: the layers hold only the local raw evidence store, the SERCOP source
adapter and the PostgreSQL persistence described under Technologies, and the
CLI only reports its version. Nothing calls these adapters yet, and no
ingestion, normalization, or quality behavior exists.

See [the architecture](docs/architecture.md) and the accepted decisions:

- [ADR 0001: Modular monolith](docs/adr/0001-modular-monolith.md)
- [ADR 0002: Immutable raw storage](docs/adr/0002-immutable-raw-storage.md)
- [ADR 0003: No distributed infrastructure in v1](docs/adr/0003-no-distributed-infrastructure-in-v1.md)
- [ADR 0004: Python toolchain](docs/adr/0004-python-toolchain.md)
- [ADR 0005: Raw evidence store layout](docs/adr/0005-raw-evidence-store-layout.md)
- [ADR 0006: HTTP client for source access](docs/adr/0006-http-client-for-source-access.md)
- [ADR 0007: PostgreSQL persistence, migrations and local environment](docs/adr/0007-postgresql-persistence.md)

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
  only spaces its requests. It is a library only: it has no CLI command,
  nothing calls it yet, and its tests use simulated transports and never
  reach the network. Whether the real source answers its requests as it
  answered the earlier observations has not been checked against the
  network. Its known limitations are listed in the
  [changelog](CHANGELOG.md).
- PostgreSQL persistence for ingestion runs, observations and audit events
  ([ADR 0007](docs/adr/0007-postgresql-persistence.md)):
  - `migrations/0001_initial_schema.sql`: the tables `ingestion_run`,
    `raw_evidence`, `observation` and `audit_event`, with constraints and
    triggers that keep the evidence, observations and audit events append-only
    and let a run change only once, from `running` to `succeeded` or `failed`;
  - a migration runner in `infrastructure` (`apply_migrations`), a library
    function that applies the numbered SQL files not yet recorded, each in its
    own transaction, and checks the checksum of the files already applied;
  - the `IngestionRepository` port in `application`, the run, audit event and
    error types in `domain`, and the `psycopg` adapter in `infrastructure`.

  It is a library only: it has no CLI command, nothing calls the runner or the
  adapter yet, and no code under `src/` reads `.env` or the environment. The
  adapter stores each response's content hash and size and the observation's
  metadata, never the response bytes, which stay in the local raw evidence
  store. Its known limitations are listed
  in the [changelog](CHANGELOG.md).
- `httpx` and `psycopg[binary]`, the runtime dependencies, each imported only in
  `infrastructure` (ADR 0006, ADR 0007). The other dependencies are
  development-only: `ruff` (lint and format), `mypy` (strict in `domain` only),
  `pytest` and `pytest-cov`.
- Two GitHub Actions workflows on pull requests: `feedback` (`ruff` and `mypy`,
  plus a secret scan) and `Tests` (the unit and integration tests with a
  coverage report; its `tests` job starts a `postgres:18` service for the
  integration tests).
- A local PostgreSQL 18 defined in `compose.yaml` (one service, port on
  `127.0.0.1` only, named volume), with credentials in `.env` (git-ignored) and
  fake values in `.env.example`
  ([ADR 0007](docs/adr/0007-postgresql-persistence.md)). Nothing applies the
  migrations to it outside the tests: the integration tests build throwaway
  databases on the same server.
- Git-based source and documentation management.

Planned, not implemented yet:

- The ingestion that will call the SERCOP adapter, the raw evidence store and
  the PostgreSQL persistence, and the normalized and quality tables.
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
| Test (integration tests are skipped without a database) | `uv run pytest` |
| Test with coverage report (what CI runs, with its PostgreSQL service) | `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing` |
| Integration tests against the local database | `uv run --env-file .env pytest tests/integration` |

The local database needs Docker. Copy `.env.example` to `.env`, put your own
local password in it, then:

| Task | Command |
|---|---|
| Start PostgreSQL and wait until it is healthy | `docker compose up -d --wait` |
| Open `psql` inside the container | `docker compose exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'` |
| Stop it, keeping the data | `docker compose down` |
| Stop it and delete the data | `docker compose down -v` |

PostgreSQL stores the password in the data volume the first time it starts.
Changing `POSTGRES_PASSWORD` in `.env` afterwards does not change it: delete the
volume with `down -v`, or run `ALTER ROLE` in the database.

The integration tests under `tests/integration/` need that database. With the
variables unset (plain `uv run pytest`) they are skipped and the reason is
shown; when the `CI` variable is `true` they fail instead of skipping.
`--env-file .env` loads `POSTGRES_DB`, `POSTGRES_USER` and `POSTGRES_PASSWORD`
(and optionally `POSTGRES_HOST`, `POSTGRES_PORT`). Each test works in its own
throwaway database named `ecpq_test_<hex>`, created and dropped on the same
server, so no table is created in the database named by `POSTGRES_DB`. If a run is
killed, such databases can remain. List them in `psql` (opened with the command
above), then drop each one by name:

```sql
SELECT datname FROM pg_database WHERE datname LIKE 'ecpq\_test\_%';
DROP DATABASE "ecpq_test_<hex>" WITH (FORCE);
```

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
