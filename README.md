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
migration runner and a `psycopg` adapter exist, and the `ingest` command uses
them to record each ingestion run in PostgreSQL. Version 1 does not include
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
stage: the layers hold the local raw evidence store, the SERCOP source adapter,
the PostgreSQL persistence and the ingestion use case that joins them, all
described under Technologies, and the CLI supports `--version` and `ingest`. No
normalization or quality behavior exists. The `ingest` command has been tested
only with simulated sources; no run against the real SERCOP source has been
made yet.

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
  packages and the `ec-procurement-quality` CLI, which supports `--version`
  and the `ingest` command ([Ingesting](#ingesting)).
- A local raw evidence store ([ADR 0005](docs/adr/0005-raw-evidence-store-layout.md)):
  the content hash, observation, and evidence errors in `domain`; the storage
  port in `application`; and a local-disk adapter in `infrastructure`. Under a
  root directory it keeps each response's exact bytes once, named by their
  SHA-256, plus one JSON observation record per response obtained, and it
  verifies integrity on read. It can also list the observations of one
  execution. The `ingest` command uses it with the fixed root `data/raw/`, which
  is git-ignored for this purpose.
- A SERCOP source adapter ([ADR 0006](docs/adr/0006-http-client-for-source-access.md)):
  the raw response and the source errors in `domain`; the source port and its
  two result types in `application`; and the `httpx` adapter in
  `infrastructure`. It makes one request per call, either the buyer-name
  search (`search_ocds`) or one record by `ocid` (`api/record`), and returns
  the response as received or raises a typed error that carries the valid
  response that arrived, so that it can be stored as evidence; a status
  outside 100 to 599 is reported without a response. It does not retry and
  only spaces its requests. The `ingest` command calls it for the buyer-name
  search; no command fetches `api/record` yet. Its tests use simulated
  transports and never reach the network. Whether the real source answers its
  requests as it answered the earlier observations has not been checked against
  the network. Its known limitations are listed in the
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

  The adapter can also list the runs that have a given status and take the
  ingest exclusion that allows one `ingest` at a time. The `ingest` command
  applies the migrations and uses the adapter. No code under `src/` reads
  `.env`; the command reads the connection settings from the process
  environment only (`uv run --env-file .env` puts them there). The adapter
  stores each response's content hash and size and the observation's metadata,
  never the response bytes, which stay in the local raw evidence store. Its
  known limitations are listed in the [changelog](CHANGELOG.md).
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
  ([ADR 0007](docs/adr/0007-postgresql-persistence.md)). The `ingest` command
  applies the pending migrations to the database named by `POSTGRES_DB`; the
  integration tests build throwaway databases on the same server instead.
- The `ingest` command: the search pages of one buyer and year, requested one
  by one from the SERCOP adapter, each response kept in the raw evidence store
  and in PostgreSQL, with the run and its audit events recorded. A failed run
  can be resumed. See [Ingesting](#ingesting).
- Git-based source and documentation management.

Planned, not implemented yet:

- The normalized and quality tables, and the normalization and quality
  commands.
- Fetching a record by `ocid` (`api/record`) in a command.

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
| Ingest the search pages of a buyer and year (needs the local database; see [Ingesting](#ingesting)) | `uv run --env-file .env ec-procurement-quality ingest --year 2025 --buyer "SYNTHETIC BUYER S.A." --last-page 3` |

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

## Ingesting

`ingest` requests the search pages of one buyer and year from SERCOP, keeps each
response in the raw evidence store and in PostgreSQL, and records the run and
its audit events. It is supported only when run from the repository root: it
resolves `data/raw/` and the default `migrations/` folder against the current
directory once, when it starts, and no option changes the evidence root. The
root is the fixed `data/raw/`, which is kept out of git.

Start the database, fill in `.env` as described above, and run it through `uv`
so that `--env-file` loads the environment:

```powershell
docker compose up -d --wait
uv run --env-file .env ec-procurement-quality ingest --year 2025 --buyer "SYNTHETIC BUYER S.A." --first-page 1 --last-page 3
```

| Option | Meaning |
|---|---|
| `--year` | The year to search. Required on a fresh run. |
| `--buyer` | The buyer name for the search. Required on a fresh run. |
| `--last-page` | The last search page to request. Required on a fresh run. |
| `--first-page` | The first page to request. Optional, `1` by default. |
| `--migrations-dir` | The folder of numbered SQL files, relative to the current directory. Optional, `migrations` by default. |
| `--resume <execution id>` | Resume a failed or interrupted run instead of starting from a scope. It cannot be combined with `--year`, `--buyer`, `--first-page` or `--last-page`. |

The command reads `POSTGRES_DB`, `POSTGRES_USER` and `POSTGRES_PASSWORD`, which
are required, and `POSTGRES_HOST` and `POSTGRES_PORT`, which are optional
(`127.0.0.1` and `5432` by default). It reads them from the process environment
only: `uv run --env-file .env` loads `.env`, and no code reads that file itself.

Before the first request it applies the migrations not yet recorded in the
database, takes the ingest exclusion (only one `ingest` can run against a
database at a time; a second one refuses to start) and closes any run an
earlier invocation left `running`, as `failed`, after copying to PostgreSQL any
observation that only the evidence store holds. It then requests the pages one
by one, does not retry a failed page, and stops at the first page that fails.
It also stops, with the run `succeeded`, at the page SERCOP reports as the last.

A failed run is resumed with its execution id, which `ingest` prints on stderr
when the run starts and on stdout when it ends:

```powershell
uv run --env-file .env ec-procurement-quality ingest --resume ingest-20250101t000000z-0123abcd
```

A resumption is a new run with its own execution id. It requests the pages of
the original scope that the chain of runs has not completed yet. The named run
must exist and must not be `succeeded`.

Output and exit codes:

- stdout holds a single result line, `<execution_id> <status>`, when the command
  created a run. The status is `succeeded` or `failed`, or `running` when the
  command could not confirm that it closed the run. When no run was created,
  stdout is empty.
- `running` does not claim that PostgreSQL still holds the run as `running`; it
  means that closing the run was not confirmed. It is printed in these cases:
  - Ctrl+C or an unexpected error such as `MemoryError`, when the cleanup that
    closes the run could not finish: a second Ctrl+C, the cleanup could not read
    the run, or one of its database operations was refused or lost;
  - a lost database connection that could not be recovered: the second
    connection could not be opened, the ingest exclusion was held elsewhere or
    could not be taken again, or the connection was lost a second time,
    including a lost `start_run` whose outcome is unknown;
  - a refused `finish_run` that closes a failed run;
  - a refused repeat of the final `finish_run` (`succeeded`) after a lost
    connection, when the stored status could not then be read;
  - any other exception that escaped after the run was announced.

  The next `ingest` closes such a run: it reconciles the run and finishes it as
  `failed`.
- stderr carries the progress and the errors, each as a fixed message that never
  includes a URL, a header, a body or a setting. It names each database
  operation that was refused or lost, with the run concerned (and the sequence
  or the event type when one applies); of the error it shows at most the class
  name.

| Code | Meaning |
|---|---|
| 0 | The run succeeded. |
| 1 | The run failed, or it did not start (another ingest is running, the database or the migration lock is unavailable, reconciliation failed), or the chain of a resumption is broken. A resumption target that the database could not read (refused, or the connection lost) is exit 1, not 2. |
| 2 | Usage error: an invalid or missing option, a missing or invalid environment variable, a proxy or certificate setting of the environment that the source cannot be built from (`HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY`, `SSL_CERT_FILE`, `SSL_CERT_DIR`), a migration error other than a busy lock, or an invalid resumption target (a malformed id, an id that names no run, or a run that already `succeeded`). |
| 130 | Interrupted with Ctrl+C. |

If `ingest` refuses to start with `another ingest is running` although none is,
a database session of a dead process may still hold the ingest exclusion. The
exclusion belongs to the session and ends when PostgreSQL drops it. To find the
session, open `psql` as shown above and list the advisory locks of the current
database:

```sql
SELECT l.pid, a.usename, a.state, a.backend_start
FROM pg_locks AS l
JOIN pg_stat_activity AS a ON a.pid = l.pid
WHERE l.locktype = 'advisory'
  AND l.granted
  AND l.database = (SELECT oid FROM pg_database WHERE datname = current_database());
```

The migration runner also takes an advisory lock, but only while it applies
migrations, so a session that stays in the list while no `ingest` or migration
is running holds the ingest exclusion. Check that its process is really gone,
then end it by its `pid`:

```sql
SELECT pg_terminate_backend(<pid>);
```

The first run against the real SERCOP source has not been made yet, so the
comparison of the live responses with the earlier observations is still pending.
