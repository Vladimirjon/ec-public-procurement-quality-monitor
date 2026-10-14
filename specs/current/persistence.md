# Persistence Specification

> Last synced: 2026-10-14. Owned artifacts: `migrations/0001_initial_schema.sql`, `src/ec_procurement_quality/domain/ingestion_audit.py`, `src/ec_procurement_quality/domain/persistence_errors.py`, `src/ec_procurement_quality/application/ingestion_repository.py`, `src/ec_procurement_quality/infrastructure/postgres_settings.py`, `src/ec_procurement_quality/infrastructure/postgres_migrations.py`, `src/ec_procurement_quality/infrastructure/postgres_ingestion_repository.py`, `tests/unit/test_ingestion_audit.py`, `tests/unit/test_postgres_settings.py`, `tests/unit/test_postgres_migration_files.py`, `tests/integration/`.

## Purpose

How the audit trail of ingestion is kept in PostgreSQL 18, following ADR 0007:
each ingestion run, each piece of raw evidence by content hash and size, each
observation that ties a response to the run that obtained it, and an
append-only list of audit events per run. The raw bytes stay in the local store
of `raw-evidence` (ADR 0005); PostgreSQL holds identity, metadata and audit
only. It is its own capability because it owns the database schema, the
migration runner and the `psycopg` adapter, which neither `raw-evidence` nor
`source-access` describes. It is a library only: no CLI command or use case
calls the runner or the adapter yet.

## Requirements

### Requirement: PS-1 — The migration runner applies pending files once, in order

The system SHALL provide `apply_migrations(settings, directory)` in
`infrastructure`, which applies every pending file of the migrations directory
once, in the lexical order of their names, records each one in the
`schema_migration` table (version, file name, SHA-256 of the file's exact
bytes, time applied), and returns the names of the files it applied in that
call. Running it again SHALL apply nothing and change nothing.

**Source:** postgres-persistence · intent.md § AC1; execution-plan.md § Binding constraints "Runner contract"

#### Scenario: Apply, then repeat
- **WHEN** `apply_migrations` is run on an empty throwaway database with the repository's `migrations/`, then run again
- **THEN** the first call returns `("0001_initial_schema.sql",)`, the tables `ingestion_run`, `raw_evidence`, `observation` and `audit_event` exist, and `schema_migration` has one row (version `1`, that file name, the SHA-256 of its bytes); the second call returns `()` and the rows are unchanged

### Requirement: PS-2 — A failed migration leaves no trace

The system SHALL run each migration file in one transaction together with its
bookkeeping row, and when a file fails SHALL roll it back, not record it, not
attempt the files after it, keep the files applied before it, and raise
`MigrationError` naming the file with fixed text and nothing from the
database's message. A failed file, once corrected, SHALL be applied by a later
run.

**Source:** postgres-persistence · intent.md § AC2

#### Scenario: Failure in the middle
- **WHEN** `0001_a.sql` creates `synthetic_a`, `0002_b.sql` creates `synthetic_b` and then runs `SELECT 1/0`, and `0003_c.sql` creates `synthetic_c`
- **THEN** `MigrationError` names `0002_b.sql`; `synthetic_a` exists, `synthetic_b` and `synthetic_c` do not, and `schema_migration` holds only version `1`; with `0002_b.sql` corrected, the next call returns `("0002_b.sql", "0003_c.sql")`

### Requirement: PS-3 — The directory and applied files are checked before anything is applied

The system SHALL check the migrations directory and every applied file before
applying anything and SHALL raise `MigrationError` naming the file, applying
nothing, on: an applied file whose bytes changed, an applied file that is
missing or renamed, a `.sql` file whose name is not `NNNN_description.sql`, two
files with the same number, a gap in the numbering, a file that is empty, holds
only whitespace, holds U+0000 or is not UTF-8, or a missing directory. The
checks of the directory and of the file names and contents SHALL run before any
connection is opened.

**Source:** postgres-persistence · intent.md § AC3, Revision 2 clarification of 2026-10-14; execution-plan.md § Binding constraints "Runner contract" "Directory" and "Integrity of applied files"

#### Scenario: Changed applied file
- **WHEN** one byte of an applied `0001_a.sql` is changed and `0002_b.sql` is added
- **THEN** `MigrationError` names `0001_a.sql` and `synthetic_b` does not exist

#### Scenario: Bad names or contents, no connection
- **WHEN** the directory holds `0001_a.sql` and `0003_c.sql`, or `0001_a.sql` and `0001_b.sql`, or `1_a.sql`, or a file holding only whitespace, or a file holding U+0000
- **THEN** `MigrationError` names the offending file and no connection attempt is made

### Requirement: PS-4 — One migration run at a time

The system SHALL take the session advisory lock `pg_try_advisory_lock(MIGRATION_LOCK_KEY)`
before creating the bookkeeping table, SHALL fail at once with `MigrationError`
when another session holds it, creating and applying nothing, SHALL never wait,
and SHALL release it before returning.

**Source:** postgres-persistence · intent.md § AC4

#### Scenario: Lock held elsewhere
- **WHEN** a separate connection to an empty throwaway database holds the lock with `MIGRATION_LOCK_KEY` and `apply_migrations` is called
- **THEN** `MigrationError` says another migration run holds the lock, `schema_migration` does not exist, and after the lock is released the call succeeds

### Requirement: PS-5 — The schema enforces identities and rules

The system SHALL define in `0001_initial_schema.sql` the tables `ingestion_run`,
`raw_evidence`, `observation` and `audit_event` with the keys and checks that
make the database refuse invalid rows even when written with direct SQL: the
execution id and content hash formats, the run status and its `finished_at`
rule, `scope` and `detail` as JSON objects, `headers` as a JSON array without a
`Set-Cookie` header in any case, non-negative size and sequence, a status from
100 to 599, non-empty method, URL and event type, foreign keys, and an
`audit_event.event_id` the database assigns (an explicit value is refused). An
audit event inserted without `detail` SHALL be stored with `{}`.

**Source:** postgres-persistence · intent.md § AC5; execution-plan.md § Binding constraints "Schema"

#### Scenario: Rows the database rejects
- **WHEN** direct SQL inserts a run with execution id `Synthetic-Exec`, a `running` run with a `finished_at`, a `raw_evidence` row whose hash has 63 characters, an observation with a header named `SET-COOKIE`, or an audit event with an explicit `event_id`
- **THEN** each is rejected and the table is unchanged

### Requirement: PS-6 — Evidence and audit are append-only; a run changes once

The system SHALL make the database refuse `UPDATE` and `DELETE` on
`raw_evidence`, `observation` and `audit_event`, `TRUNCATE` on `observation` and
`audit_event`, `TRUNCATE ... CASCADE` on `raw_evidence` and `ingestion_run`,
and `DELETE` on `ingestion_run`, each with SQLSTATE `23000` and no row changed; a plain
`TRUNCATE` of `raw_evidence` or `ingestion_run` SHALL be refused with `23000` or
`0A000` (PostgreSQL's foreign key check may refuse it first), no row changed;
and SHALL let a run change only once, from `running` to `succeeded` or
`failed`, with `execution_id`, `scope` and `started_at` unchanged.

**Source:** postgres-persistence · intent.md § AC6, Revision 2 clarification of 2026-10-14; execution-plan.md § Binding constraints "Schema"

#### Scenario: Run transition
- **WHEN** a `running` run is set to `succeeded` with a `finished_at`, and then updated again (to `failed`, back to `running`, a new `finished_at` or a new `scope`)
- **THEN** the first update is accepted and each later update is rejected with SQLSTATE `23000`

### Requirement: PS-7 — Runs through the port, repeats safe, scopes compared as JSON values

The system SHALL start, finish and read runs through `IngestionRepository`
(`start_run`, `finish_run`, `read_run`), return the stored run unchanged for a
repeat with the same values, and raise `PersistenceIntegrityError` for a
different value under an existing identity. Two scopes SHALL be the same only
when `same_json` holds: types are compared at every depth (`True` is not `1`,
`False` is not `0`), object key order does not matter and list order does. A
`finish_run` with status `running` or with a plain string instead of a
`RunStatus` SHALL raise `ValueError` before anything is written; an unknown
execution id SHALL raise `PersistenceNotFoundError`. Times read back SHALL be
the same instants, in UTC.

**Source:** postgres-persistence · intent.md § AC7, Revision 2; execution-plan.md § Binding constraints "Public names and signatures" (`same_json(left: object, right: object)`), § Adapter behavior

#### Scenario: Repeat and conflict
- **WHEN** `start_run` of `synthetic-exec-001` with scope `{"source": "synthetic", "year": 2025}` is repeated with the same scope and start instant, and then with another scope
- **THEN** the repeat returns the stored run and changes nothing, and the other scope raises `PersistenceIntegrityError`

#### Scenario: JSON types
- **WHEN** a run started with scope `{"x": 1}` is started again with `{"x": True}` (or `{"x": [1]}` then `{"x": [True]}`, or `{"x": [1, 2]}` then `{"x": [2, 1]}`)
- **THEN** `PersistenceIntegrityError` is raised and the stored scope is unchanged, while `{"b": 1, "a": 2}` repeated as `{"a": 2, "b": 1}` returns the same run

### Requirement: PS-8 — Observations recorded once, read back equal

The system SHALL record, read and list observations through the port with one
`raw_evidence` row per content whatever the number of observations and one
`observation` row per response obtained, the size read from `raw_evidence`;
repeating the identical observation SHALL be a no-op; a different observation
under an existing (execution, sequence), an unknown run, or a different size
for an existing content SHALL raise `PersistenceIntegrityError` with its
transaction rolled back, so no new `raw_evidence` row remains. Headers SHALL
keep their order and repeats, and text outside ASCII SHALL be stored and read
back unchanged. Reading an identity never recorded SHALL raise
`PersistenceNotFoundError`, and an execution id outside the F1 pattern
`ValueError`.

**Source:** postgres-persistence · intent.md § AC8, Revision 2 clarification of 2026-10-14; execution-plan.md § Binding constraints "Adapter behavior"

#### Scenario: Two runs, one content
- **WHEN** the same observation (sequence `1`, content `b"abc"`, size `3`) is recorded for `synthetic-exec-001` and `synthetic-exec-002`
- **THEN** there is one `raw_evidence` row and two observation rows, `read_observation("synthetic-exec-001", 1)` equals the observation given, and `list_observations` returns it alone, in sequence order

#### Scenario: Conflict rolled back
- **WHEN** the same identity is recorded with status `500`, another header order, or content `<empty>` of size `0`
- **THEN** `PersistenceIntegrityError` is raised, the stored row is unchanged and no `raw_evidence` row exists for `<empty>`

### Requirement: PS-9 — Audit events appended and listed in order

The system SHALL append audit events through the port with the identity
assigned by the database, list them by `event_id`, and require only a non-empty
type and a JSON object as detail (the catalogue of event types is not defined
here). Appending SHALL NOT be idempotent: the same call made twice appends two
events. Details SHALL be compared as JSON values; an empty type SHALL raise
`ValueError` before anything is written; an unknown run SHALL raise
`PersistenceIntegrityError`, and listing the events of a run never started
`PersistenceNotFoundError`.

**Source:** postgres-persistence · intent.md § AC9; execution-plan.md § Binding constraints "Adapter behavior" "`append_audit_event`"

#### Scenario: Two events in order
- **WHEN** `append_audit_event` is called for `synthetic-exec-001` with type `synthetic-run-started`, detail `{}`, then type `synthetic-page-stored`, detail `{"page": 1}`
- **THEN** two events with increasing `event_id` are returned, `list_audit_events` returns them in that order, and `{"page": True}` is not equal to `{"page": 1}`

### Requirement: PS-10 — Input the domain or PostgreSQL cannot accept is a `ValueError` before any write

The system SHALL reject with `ValueError`, before anything is written, naming
the field and never its value: an execution id outside the F1 pattern, a time
without a UTC offset, a `finished_at` before `started_at`, a scope or detail
that is not a JSON object of `None`, `bool`, `int`, `str`, `list` and `dict`
with `str` keys (a `float` is rejected anywhere), text holding U+0000 or a lone
surrogate anywhere, a sequence above 2,147,483,647, a size above
9,223,372,036,854,775,807, and an integer in scope or detail of more than 4300
decimal digits. `PostgresSettings` SHALL reject a `host`, `dbname`, `user` or
`password` that holds U+0000 or a lone surrogate, a `port` outside 1 to 65535
and a `connect_timeout` outside 2 to 60.

**Source:** postgres-persistence · intent.md § AC10, Revision 2 clarification of 2026-10-14; execution-plan.md § Binding constraints "`PostgresSettings`", § Adapter behavior "Validation before writing"

#### Scenario: Unstorable input
- **WHEN** a scope `{"year": 2025.0}`, an observation URL containing `"\x00"`, a header value `"\ud800"`, a sequence `2**31`, or a detail `{"n": 10**5000}` is given
- **THEN** `ValueError` is raised and the row counts are unchanged

#### Scenario: Lone surrogate in a setting
- **WHEN** `PostgresSettings` is built with a password that holds `"\ud800"`
- **THEN** `ValueError` names `password`, shows no part of the value, and chains no `UnicodeEncodeError`

### Requirement: PS-11 — Connection problems are typed and each operation is atomic

The system SHALL raise `PersistenceConnectionError` when the database cannot be
reached or refuses the credentials (at construction) and when a connection is
lost during an operation, SHALL NOT reconnect (every later call raises the same
error), and SHALL raise `RuntimeError` for a call after `close()`. Each
operation SHALL be one transaction, applied completely or not at all.
`PersistenceConnectionError` SHALL NOT be read as proof that nothing was
written: a connection lost while the commit is in flight leaves the outcome
unknown. `start_run`, `finish_run` and `record_observation` are safe to repeat
with the same values; `append_audit_event` is not.

**Source:** postgres-persistence · intent.md § AC11; execution-plan.md § Adapter behavior "Transactions", "Connection"

#### Scenario: Connection lost before the statements are sent
- **WHEN** the adapter's server session is terminated from a test connection and `record_observation` is called
- **THEN** `PersistenceConnectionError` is raised, no row is written, and the next `read_run` raises `PersistenceConnectionError`

#### Scenario: Connection lost while the transaction is open
- **WHEN** `record_observation` inserts its `raw_evidence` row and waits on a table lock, and its server session is then terminated
- **THEN** `PersistenceConnectionError` is raised and neither its `raw_evidence` row nor its observation exists

### Requirement: PS-12 — Nothing leaks secrets or stored content

The system SHALL keep the password, connection settings, SQL parameters and
stored values (header values, URLs, scope, detail) out of every error message,
`str()`, `repr()`, `args` and formatted traceback, naming only the operation
and, where useful, an identity (execution id, sequence, content hash,
migration file name); SHALL make no driver exception reachable through
`__cause__` or `__context__`; SHALL never show the password in the settings'
`repr()` or `str()`; and SHALL write no log records of its own.

**Source:** postgres-persistence · intent.md § AC12; execution-plan.md § Errors and output

#### Scenario: Conflict with a stored marker
- **WHEN** an observation conflict occurs on a stored URL that holds `synthetic-url-marker`
- **THEN** `PersistenceIntegrityError` names the execution and sequence, the marker appears nowhere in its message, `repr`, `args` or traceback, and no `psycopg` exception is in its chain

### Requirement: PS-13 — Layer placement and the port

The system SHALL keep the run status, `IngestionRun`, `AuditEvent`, `JsonValue`,
`same_json` and the five persistence errors (`PersistenceError` and its direct
subclasses `PersistenceConnectionError`, `PersistenceIntegrityError`,
`PersistenceNotFoundError` and `MigrationError`) in `domain` (standard library
only, strict `mypy`); the `IngestionRepository` protocol in `application`
(standard library and `domain` only); and `PostgresSettings`,
`apply_migrations` and `PostgresIngestionRepository` in `infrastructure`, the
only layer that imports `psycopg`. The adapter SHALL satisfy the port
structurally and be used by one thread at a time.

**Source:** postgres-persistence · intent.md § AC13; execution-plan.md § Binding constraints "Public names and signatures", "Other constraints"

#### Scenario: Adapter typed as the port
- **WHEN** a test assigns `PostgresIngestionRepository(settings)` to a variable annotated `IngestionRepository`, and `uv run mypy .` and `uv run pytest tests/unit -q -k layer` are run
- **THEN** both succeed, including `test_layer_only_infrastructure_imports_psycopg`

## Invariants

1. An applied migration file is never edited: its recorded SHA-256 must match
   or the runner refuses to continue (ADR 0007, forward-only).
2. Raw bytes never go to PostgreSQL. It holds identity, metadata and audit;
   keeping the local store and PostgreSQL consistent after a crash between the
   two writes is F4's job.
3. The triggers guard the application and accidental writes, not a superuser or
   the table owner, who can disable them or edit `schema_migration`. No
   least-privilege role exists yet.
4. Every error is raised outside the `except` block that caught the driver's
   exception, with fixed text and no `from` clause, so no driver text or stored
   value passes on (the server's own error text quotes the failing row).
5. Instants are stored, not UTC offsets; a `float` is never stored in a scope or
   detail (`jsonb` does not read every float back equal).
6. Scopes and details are compared with `same_json`, never with `==` on the raw
   mappings, which treats `True` as `1`.
7. Audit events are not idempotent and have no idempotency key; a caller must
   not retry `append_audit_event` blindly after `PersistenceConnectionError`.
8. Nothing calls the runner or the adapter yet: no CLI command, no use case, no
   code under `src/` reads the environment or `.env`.

## Open reservations

| ID | Reservation | Severity | Source |
|---|---|---|---|
| U1 | The outcome of a connection lost while the commit is in flight is unknown and is documented, not tested (a deterministic test needs a protocol-aware proxy) | LOW (impact Med) | postgres-persistence · intent.md § AC11; audit.md § AC11 |
| F5 | The record does not show that the per-turn Stop hook fired during implementation; only the CI gate and the reruns are shown (accepted by the human as an environment observation) | LOW | postgres-persistence · audit.md § Findings F5 |
| N3 | `open_connection` and `connection_was_lost` live in `postgres_settings.py`; a dedicated connection module could be considered when F4 adds consumers (recommendation) | LOW | postgres-persistence · audit.md § Notes N3 |
| N5 | An existence check followed by a list runs in two statement snapshots under READ COMMITTED; safe today because runs cannot be deleted; F4 may use REPEATABLE READ for reads if it needs one snapshot (recommendation) | LOW | postgres-persistence · audit.md § Notes N5 |

## Contributing features

| Feature | Shipped | What it established |
|---|---|---|
| postgres-persistence (F3) | 2026-10-14 | The schema `0001_initial_schema.sql`, the migration runner, the domain types and errors, the `IngestionRepository` port and the `psycopg` adapter, with append-only triggers, idempotent repeats, typed errors and no leaks (PS-1 to PS-13) |

## Related ADRs

None registered here. The binding decisions are the project-level ADRs in
`docs/adr/`, which carry no `Capability:` field: ADR 0007 (PostgreSQL
persistence, migrations and local environment, Accepted on 2026-10-13), with
ADR 0002 (immutable raw storage) and ADR 0005 (raw evidence store layout).
