# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
The project has not been released yet, so every entry is under `Unreleased`.

## [Unreleased]

### Added

- Project skeleton (F0): an installable Python 3.13 package,
  `ec-procurement-quality` 0.1.0, built with `uv_build` and managed with `uv`
  and a committed `uv.lock`. No runtime dependencies.
- `src/ec_procurement_quality/` with the empty `domain`, `application`,
  `infrastructure` and `interfaces` layer packages.
- CLI `ec-procurement-quality`, standard library only. `--version` prints
  `ec-procurement-quality 0.1.0` and exits 0; an unknown option exits 2 with a
  usage error on stderr. Any other behavior is not implemented yet. (The
  `ingest` command of F4, below, adds the first other command.)
- Configuration for `ruff` (lint and format), `mypy` (strict in `domain` only)
  and `pytest`, all in `pyproject.toml`, and 7 unit tests under `tests/unit/`.
- `Tests` GitHub Actions workflow (`.github/workflows/tests.yml`): runs the unit
  tests with a `pytest-cov` coverage report on pull requests and on pushes to
  `main`, installing with `uv sync --locked`. There is no coverage threshold.
- `pytest-cov` as a development-only dependency.
- Local raw evidence store (F1), following
  [ADR 0005](docs/adr/0005-raw-evidence-store-layout.md): the `ContentHash`
  value object, the `Observation` record and the evidence errors in `domain`;
  the `RawEvidenceStore` port in `application`; and `LocalDiskRawEvidenceStore`
  in `infrastructure`, which keeps response bytes once under their SHA-256 and
  one JSON observation per response obtained, publishes files write-once and
  atomically, never persists `Set-Cookie` headers, and verifies integrity on
  read. No CLI command or use case calls it yet (F4, below, now does), and no
  dependency was added.
- SERCOP source adapter (F2), following
  [ADR 0006](docs/adr/0006-http-client-for-source-access.md): `RawResponse` and
  the source errors (`SourceError`, `SourceTransportError`,
  `SourceStatusError`, `IncompleteResponseError`) in `domain`; the
  `ProcurementSource` port with `SearchPage` and `RecordResponse` in
  `application`; and `SercopSource` in `infrastructure`, on a synchronous
  `httpx.Client`. One call makes one request, to the buyer-name search
  (`search_ocds`) or to `api/record`, and returns the response exactly as
  received or raises a typed error that carries the valid response that arrived
  (a status outside 100 to 599 is reported without a response), so that failed
  and partial responses can be stored through the raw evidence store. It never
  retries, spaces requests from the `X-RateLimit-Remaining`
  header, sets explicit timeouts, and rejects a base URL with user
  information. Its tests use `httpx.MockTransport` and a network guard, and
  never reach the network. It is a library only: no CLI command or use case
  calls it yet (F4, below, now does).
- `httpx` as the first runtime dependency (`httpx>=0.28.1` in
  `[project] dependencies`, resolved to 0.28.1 in `uv.lock`), imported only in
  `infrastructure`. The development dependencies do not change.
- Local PostgreSQL environment, following
  [ADR 0007](docs/adr/0007-postgresql-persistence.md): `compose.yaml` with one
  service (`postgres:18`, port published on `127.0.0.1` only, named volume) and
  `.env.example` with fake values; `.env` is git-ignored. Nothing in the
  application uses the database yet (F4, below, now does), and no dependency
  was added.
- PostgreSQL persistence (F3), following
  [ADR 0007](docs/adr/0007-postgresql-persistence.md):
  - `migrations/0001_initial_schema.sql` with the tables `ingestion_run`,
    `raw_evidence`, `observation` and `audit_event`, their constraints, and
    triggers that make evidence, observations and audit events append-only and
    let a run change only from `running` to `succeeded` or `failed`;
  - in `domain`, the run status, `IngestionRun`, `AuditEvent`, the JSON value
    rule with `same_json` (booleans are not numbers), and the five persistence
    errors; in `application`, the `IngestionRepository` port; and in
    `infrastructure`, `PostgresSettings`, `apply_migrations` and
    `PostgresIngestionRepository`, on `psycopg`, with typed errors that carry
    no secret, setting or stored value;
  - input that the domain or PostgreSQL cannot store as given is rejected with
    `ValueError` before anything is written: a float, text with U+0000 or a lone
    surrogate, or an integer of more than 4300 digits in a scope or detail.
    Non-ASCII text is stored and read back unchanged. Connection settings with a
    lone surrogate are refused, and a migration file that is empty,
    whitespace-only, holds U+0000 or is not UTF-8 is refused before any
    connection is opened;
  - integration tests under `tests/integration/` with one throwaway
    `ecpq_test_<hex>` database per test, skipped with a reason when the
    variables are unset and failing when `CI` is `true`, the `integration`
    pytest marker, and a layer test that only `infrastructure` imports
    `psycopg`;
  - a `postgres:18` service and its environment in the `tests` job of
    `.github/workflows/tests.yml`.
  It is a library only: no CLI command or use case calls the runner or the
  adapter yet (F4, below, now does), and the response bytes stay in the local
  raw evidence store.
- `psycopg[binary]` as the second runtime dependency (`psycopg[binary]>=3.3.6`
  in `[project] dependencies`, resolved to 3.3.6 with `psycopg-binary` 3.3.6 and
  `tzdata` 2026.5 in `uv.lock`), imported only in `infrastructure`. The
  development dependencies do not change.
- `ingest` command (F4): `uv run --env-file .env ec-procurement-quality ingest`,
  supported only when run from the repository root. A fresh run takes `--year`,
  `--buyer` and `--last-page`, with an optional `--first-page` (1 by default) and
  `--migrations-dir` (`migrations` by default). `--resume <execution id>` starts
  a new run that continues the pages a failed or interrupted run did not
  complete, and cannot be combined with the scope options. The command:
  - reads `POSTGRES_DB`, `POSTGRES_USER` and `POSTGRES_PASSWORD` (required) and
    `POSTGRES_HOST` and `POSTGRES_PORT` (optional, `127.0.0.1` and `5432`) from
    the process environment only; no code reads `.env`;
  - applies the pending migrations, takes the ingest exclusion (one ingest per
    database) and closes any run left `running` by an earlier invocation, as
    `failed`, after copying to PostgreSQL the observations that only the local
    store holds;
  - requests the search pages one by one without retrying, keeps every response
    in the local raw evidence store (the fixed `data/raw/`, resolved once to an
    absolute path) and in PostgreSQL, and records the run and its audit events
    from a closed catalogue;
  - writes the single result line `<execution id> <status>` to stdout and the
    progress and errors to stderr, and ends with exit code 0 (succeeded), 1
    (failed, not started or broken resumption chain), 2 (usage, environment,
    migration error other than a busy lock, or invalid resumption target) or 130
    (Ctrl+C).

  The use case lives in `application` (`run_ingest` and its ports), the
  catalogue and scope in `domain`, and the composition in `interfaces`. No
  migration, dependency or `compose.yaml` change was needed. Its tests use
  in-memory doubles and simulated transports and never reach the network.

### Changed

- Dependabot version updates now also cover the `uv` ecosystem
  (`pyproject.toml` and `uv.lock`), weekly. Until now only `github-actions` was
  configured, although ADR 0006 and ADR 0007 described the lockfile as watched;
  both ADRs now name the entry.
- The `feedback` CI job now installs the locked dependencies and puts `.venv`
  on `PATH` through three hand-maintained steps, so `ruff` and `mypy` actually
  run (`2 of 2 command(s) ran`) instead of being skipped. These steps must be
  restored after any `harny init` or `update`; see
  `docs/repository-settings.md`.
- `README.md` and `AGENTS.md` list the real install, CLI, lint, type and test
  commands, and document that the Stop and pre-commit hooks run `ruff` and
  `mypy` only when `.venv` is on `PATH`.
- `docs/architecture.md` no longer lists the Python compatibility range as an
  open question; it is answered by ADR 0004.
- `README.md` and `docs/architecture.md` describe the raw evidence store and
  link ADR 0005; the raw-storage paths and metadata question is answered there
  for local storage, while compression and retention stay open.
- The `RawEvidenceStore` port and `LocalDiskRawEvidenceStore` gain
  `list_observation_sequences`, a read-only listing of the observations of one
  execution; the `IngestionRepository` port and `PostgresIngestionRepository`
  gain `list_runs` (runs by status) and `try_acquire_ingest_exclusion` (the
  ingest exclusion, held for the rest of the connection and kept inside
  `infrastructure`).
- `apply_migrations` still raises a `MigrationError` for every failure. A busy
  migration lock now raises `MigrationLockError`, a new subclass of
  `MigrationError` with the same message, so the persistence errors are six.
  Existing handlers of `MigrationError` keep working.
- `[tool.mypy]` in `pyproject.toml` gains `explicit_package_bases = true` and
  `mypy_path = "src"`, so that `uv run mypy .` accepts the several `conftest.py`
  files of the test folders. No dependency was added and `uv.lock` is unchanged.
- `README.md`, `AGENTS.md` and `docs/architecture.md` describe the `ingest`
  command and replace the sentences that said nothing calls the adapters. The
  minimum audit events and the run scope are answered for ingestion in
  `docs/architecture.md`.

### Known limitations

- Accepted at audit (APPROVED WITH RESERVATIONS): the CI-side checks that a lint
  error fails `feedback` and that a failing test fails `tests` were verified
  locally only, not on a throwaway pull request. The local Stop and pre-commit
  hooks skip `ruff` and `mypy` when `.venv` is not on `PATH`.
- No coverage threshold is enforced yet; it is decided once real domain code
  exists.
- SERCOP source adapter (F2), accepted at audit (APPROVED WITH RESERVATIONS):
  - An instance holds the state of the request in progress and the pacing
    state. It must be used by one thread at a time and must not be called from
    inside its own call (from its transport or from its clock and sleeper).
    Nothing enforces this, and two calls that share an instance can mix their
    evidence without an error.
  - With the real transport, the `httpcore` logger writes response header
    values at `DEBUG`. The adapter configures no logging, so the caller must
    keep that logger above `DEBUG`.
  - `httpx` does not map the closing of a response stream, so a rare `OSError`
    from closing the socket propagates unchanged. It is not a source outcome.
  - No test pins that the adapter drops a later `httpx.HTTPError` that caller
    code raises once the status and headers were captured (for example a test
    double's `httpx.Response` subclass). The behavior is specified and was
    confirmed by an audit probe; the test is deferred.
  - The adapter was tested only with fixtures and simulated transports. That
    the real source answers its requests as it answered the earlier
    observations is not verified until the first real ingestion.
- PostgreSQL persistence (F3):
  - A connection lost while a commit is in flight leaves the outcome unknown:
    the write may or may not have happened, so `PersistenceConnectionError` is
    not proof that nothing was written. This case is documented and not tested.
    A connection lost before the statements are sent, or while the transaction
    is open, writes nothing (tested).
  - Audit events are not idempotent: appending the same event twice stores two
    events. An idempotency key is not part of F3.
  - The append-only and run-transition triggers do not bind a superuser or the
    table owner, who can disable them, and the migration bookkeeping table can
    be edited the same way. No least-privilege database role exists yet.
  - Nothing calls the runner or the adapter, so no ingestion, reconnection,
    retry or pooling behavior exists; an adapter that lost its connection must be
    closed and replaced. (Since F4 the `ingest` command calls them. It reconnects
    once; see the F4 limitations below.)
- `ingest` command (F4):
  - The cleanup after Ctrl+C (or `MemoryError`) is best effort. When it does not
    finish, the run stays `running` and the next `ingest` closes it.
  - The ingest exclusion belongs to a database session. A session of a process
    that died without PostgreSQL noticing (a host crash, a network partition)
    can keep it, and every later `ingest` refuses to start until PostgreSQL
    drops the session. The README shows how to find and end it by hand.
  - When the `page-completed` event of a page is lost (a crash, or a commit
    whose outcome is unknown), the page is requested again on resumption. The
    repeat costs one request and, with identical bytes, no new object.
  - The command is supported only when run from the repository root: `data/raw/`
    and `migrations/` resolve against the current directory.
  - A connection lost while a commit is in flight leaves the outcome unknown.
    The use case reconnects once and repeats the operation, but the
    commit-in-flight case itself is still not tested against PostgreSQL.
  - No run against the real SERCOP source has been made yet, so the live
    responses have not been compared with the earlier observations (source
    access, first real ingestion). The command was tested only with simulated
    sources.
