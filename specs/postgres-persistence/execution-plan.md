# Execution Plan: PostgreSQL persistence (F3)

## Guidance consulted
- `specs/postgres-persistence/intent.md` Revision 2 (AC1 to AC17; open questions 1 to 10 resolved by the human at gate 1 on 2026-10-13), approved by the human at gate 1 on 2026-10-13 (Revision 2).
- `AGENTS.md` (layer boundaries, no dependency without approval, no secrets or `.env` contents anywhere, minimal synthetic fixtures, run verification after every change).
- `docs/adr/0007-postgresql-persistence.md` (Accepted 2026-10-13; binding), `0001` (modular monolith), `0002` (immutable raw storage), `0003` (no distributed infrastructure), `0004` (Python toolchain, integration tests against PostgreSQL announced), `0005` (raw evidence store layout; "finding who obtained a piece of content requires scanning observations until PostgreSQL indexes them (F3)"), `0006` (HTTP client; precedent for a first runtime dependency added by the first task).
- `docs/glossary.md` § Raw evidence, § Observation, § Ingestion execution (identity never reused, bounded scope, always ends with a recorded outcome, idempotent in effect).
- `docs/architecture.md` (layers; § Open questions keeps "minimum audit events" open), `README.md`, `CHANGELOG.md`, `docs/repository-settings.md` (required checks `feedback` and `tests`), `docs/learning/plan.md` § 4 (F3 row), § 5 (D-10 to D-12), § 6 (Day 17: integration tests with `services: postgres` in `tests.yml`) and Days 16 and 17 (the plan had the human write the first migrations; the human chose otherwise at gate 1, see resolved question 6), `docs/learning/journal.md` Day 15 (no `psql` and no `libpq` on the Windows machine; ADR 0007 leaves the schema, the variant and the runner contract to this spec).
- `harny-sync` lookup: `specs/current/_index.md`, `raw-evidence.md`, `source-access.md`, `project-toolchain.md`. Relevant current truth: RE-1 (`ContentHash`), RE-6 (`Set-Cookie` never persisted, `Observation` rejects it), RE-11 (`validate_execution_id`, `validate_sequence`; a `bool` sequence is rejected), RE-12 (port and layer placement); SA-3 (`RawResponse` headers decoded from bytes, names as received); PT-3 (only `infrastructure` imports `httpx`, enforced by a layer test), PT-6 (961 tests), PT-10 (`tests` job command), PT-11 and Invariant 4 (`httpx` the only approved runtime dependency), PT-12 (no coverage threshold), Invariant 3 (at most 2 files directly in `src/ec_procurement_quality/`). Nothing in the lookup is contradicted; the PT changes are listed in intent § Constraints.
- Code read: `src/ec_procurement_quality/domain/raw_evidence.py` (`Observation` rejects a `bool` status, sequence or size through `_is_plain_int`), `domain/content_hash.py`, `application/raw_evidence_store.py`, `infrastructure/sercop_source.py` (headers decoded as Latin-1 at line 524), `tests/unit/test_layers.py` (AST import checks; `_names_http_client_library`), `tests/unit/test_sercop_source.py` lines 114 to 150 (the F2 network guard is an `autouse` fixture local to that file, not a `conftest.py`), `pyproject.toml` (`[tool.pytest] testpaths = ["tests"]`, no markers), `.github/workflows/tests.yml`, `.github/dependabot.yml` (only `github-actions`), `compose.yaml`, `.env.example`, `.gitattributes` (`* text=auto eol=lf`), `.gitignore` (`.env`, `.env.*` ignored, `!.env.example`), `.sdd/shared/components.mjs` and `.sdd/doctor/checks.json` (source roots `src`, `lib`, `app`; a root `migrations/` folder is not a component). `tests/integration/`, `tests/contract/` and `tests/end_to_end/` exist on disk, empty and untracked.
- Baseline on 2026-10-13 at `3aac942` (branch `docs/day-16-f3-postgres-persistence-specs`): `uv run pytest -q` -> `961 passed`; `uv run ruff check .` -> `All checks passed!`; `uv run ruff format --check .` -> `78 files already formatted`; `uv run mypy .` -> `Success: no issues found in 20 source files`; `uv run node .sdd/doctor/run-doctor.mjs` -> `31 ok, 0 skipped, 0 warned, 0 failed`; working tree clean.
- PostgreSQL probe on 2026-10-13 against the local Compose service (`PostgreSQL 18.6 (Debian 18.6-1.pgdg13+2)`, encoding `UTF8`), in a scratch schema dropped afterwards (`schemas_left` 0; no object left; `.env` never read). Plan evidence, not outcome evidence. Observed:
  - the configured role has `rolsuper` and `rolcreatedb` true (throwaway databases are possible);
  - `'abc\n' ~ '^[a-z0-9][a-z0-9-]{0,63}$'` is false (PostgreSQL `$` does not accept a trailing newline), leading `-` and 65 characters are false;
  - the check constraints of § Binding constraints "Schema" reject each bad row with SQLSTATE `23514`, a missing run with `23503`; `jsonb_path_exists(headers, '$[*][0] ? (@ like_regex "^set-cookie$" flag "i")')` rejects `SET-COOKIE`;
  - a `jsonb` array keeps header order and repeated names;
  - `INSERT ... ON CONFLICT ... DO NOTHING RETURNING` returns no row on a conflict and writes nothing;
  - `BEFORE UPDATE OR DELETE ... FOR EACH ROW` and `BEFORE TRUNCATE ... FOR EACH STATEMENT` triggers raising `USING ERRCODE = 'integrity_constraint_violation'` reject the statement with SQLSTATE `23000`; `TRUNCATE ingestion_run CASCADE` is rejected by the trigger of the cascaded `observation` table;
  - a transition trigger lets `running` -> `succeeded` through and rejects every later update;
  - `GENERATED ALWAYS AS IDENTITY` rejects an explicit `event_id` (SQLSTATE `428C9`); a failed insert consumes an identity value (gaps are possible);
  - `timestamptz` keeps the instant and not the offset (`2026-10-09T10:15:00-05:00` reads back as `2026-10-09 15:15:00+00` with `TimeZone` `UTC`);
  - `jsonb` rejects `\u0000` (`22P05`), a lone surrogate (`22P02`) and `NaN`; duplicate keys keep the last value;
  - DDL inside a failed transaction is rolled back;
  - `pg_try_advisory_lock` returns at once; it is re-entrant inside one session;
  - **the server's error detail quotes the failing row** (`DETAIL: Failing row contains (synthetic-exec-001, 2, GET, https://source.invalid/a, 200, [["SET-COOKIE", "s=1"]], ...)`), which is why AC12 forbids passing any driver error text on.
- Template probe on 2026-10-13 (Revision 2), same server, with databases named `f3_probe_*` that were dropped afterwards (`probe_databases_left` 0). Observed:
  - `CREATE DATABASE <copy> TEMPLATE <template>` fails with `source database "<template>" is being accessed by other users` (`DETAIL: There is 1 other session using the database.`) when another session is connected to the template, after the server waits about 5 s;
  - the session that runs `CREATE DATABASE` is not counted, even when it is itself connected to the template;
  - once the other session has gone, the copy succeeds and holds the template's tables;
  - after `ALTER DATABASE <template> ALLOW_CONNECTIONS false`, a new connection to the template fails (`database "<template>" is not currently accepting connections`), and copying from it still succeeds, as for PostgreSQL's own `template0`;
  - `DROP DATABASE ... WITH (FORCE)` drops a database that refuses connections.
- Package facts checked on PyPI on 2026-10-13: `psycopg` 3.3.6 (`requires_python >=3.10`; on Windows it requires `tzdata`); `psycopg-binary` 3.3.6 has wheels for `cp313` on `win_amd64`, `manylinux` `x86_64` and `aarch64`, `musllinux` and macOS. The psycopg installation docs (`psycopg.org/psycopg3/docs/basic/install.html`) say the binary package "packages its own copy of the libpq" and is "the quickest way to start developing"; the pure Python package needs `libpq` installed on the client; `psycopg[c]` needs a compiler and `pg_config`. The psycopg 2-to-3 page says several statements separated by semicolons can run in one `execute()` only when no parameters are passed.
- Lockfile impact measured in a scratch copy of `pyproject.toml` and `uv.lock` (outside the repository) with `"psycopg[binary]>=3.3.6"` added: `uv lock` -> `Resolved 25 packages` (22 before), `Added psycopg v3.3.6`, `Added psycopg-binary v3.3.6`, `Added tzdata v2026.5`.
- `uv run --help` (uv 0.12.23) lists `--env-file <ENV_FILE>`: "Load environment variables from a `.env` file".
- Gate 1 decisions of the human, 2026-10-13 (recorded in intent § Open questions): question 2 approved; question 6 option B; questions 1, 3, 4, 5, 7, 8 and 9 accepted as recommended; question 10 handled by a separate change.

## Ownership
- `migrations/` (new, repository root): `0001_initial_schema.sql`, written by the executor and reviewed line by line by the human (resolved question 6).
- `src/ec_procurement_quality/domain/`: `ingestion_audit.py` (run status, ingestion run, audit event, JSON value rule, JSON comparison) and `persistence_errors.py` (new modules).
- `src/ec_procurement_quality/application/`: `ingestion_repository.py`, the persistence port (new module).
- `src/ec_procurement_quality/infrastructure/`: `postgres_settings.py`, `postgres_migrations.py` and `postgres_ingestion_repository.py` (new modules).
- `tests/unit/`: new unit test files and one new check in `tests/unit/test_layers.py`. `tests/integration/`: `conftest.py` and the integration test files (new).
- `pyproject.toml` and `uv.lock` (the `psycopg` dependency and the `integration` marker), `.github/workflows/tests.yml` (the PostgreSQL service and job environment).
- Documentation: `README.md`, `AGENTS.md` § Current commands, `docs/architecture.md`, `CHANGELOG.md`.
- Affected `specs/current` capabilities: a new capability for persistence (suggested name `persistence`, prefix `PS-`) created by `harny-sync` at archive; `project-toolchain` (PT-3: only `infrastructure` imports `psycopg`; PT-6: the suite includes `tests/integration/` and its count grows; PT-10: the `tests` job runs a `postgres:18` service and the integration tests; PT-11: `psycopg` is the second approved runtime dependency; a new requirement for the integration tier, one throwaway database per test, and the skip and fail policy). `cli`, `raw-evidence` and `source-access`: none.

## Binding constraints

### Public names and signatures
Fixed because the test-writer and the executor write separate parts that import each other (source: intent § Constraints; F1 and F2 precedent). Every annotation is required; in `domain` strict `mypy` enforces it.

- `ec_procurement_quality.domain.ingestion_audit`:
  - `JsonValue`: a type alias for `None | bool | int | str | list[JsonValue] | dict[str, JsonValue]` (no `float`, intent AC10).
  - `same_json(left: JsonValue, right: JsonValue) -> bool` (Revision 2). It is true exactly when, recursively:
    - both are `None`;
    - both are `bool` and equal;
    - both are `int` but not `bool`, and equal;
    - both are `str` and equal;
    - both are `list`, of the same length, and `same_json` holds for each pair in order;
    - both are `dict`, with the same set of keys, and `same_json` holds for each key.

    Any other pairing is false: `True` and `1`, `False` and `0`, a `list` and a `dict`, `1` and `"1"`. Key order never matters; list order always does. A value outside the JSON object rule below (a `float`, a `tuple`, a non-`str` key) raises `ValueError`.
  - `RunStatus`, a `enum.StrEnum` with exactly `RUNNING = "running"`, `SUCCEEDED = "succeeded"`, `FAILED = "failed"`.
  - `IngestionRun`, an immutable record (assigning an attribute raises), built with keyword arguments, with exactly `execution_id: str`, `scope: Mapping[str, JsonValue]`, `started_at: datetime`, `status: RunStatus`, `finished_at: datetime | None`. Construction raises `ValueError` when:
    - `execution_id` fails `validate_execution_id` (F1);
    - `scope` is not a JSON object under the rule below;
    - `started_at`, or a `finished_at` that is not `None`, is not a `datetime` with a UTC offset;
    - `status` is not a `RunStatus` instance (a plain `str` such as `"succeeded"` is rejected, Revision 2);
    - `finished_at` is `None` while `status` is not `RUNNING`, or not `None` while it is;
    - `finished_at` is before `started_at`.

    Two runs are equal when `execution_id`, `status`, `started_at` and `finished_at` are equal (`datetime` equality, so the same instant) and `same_json` holds for their scopes (Revision 2). Python's default `==` is not used for the scope, because it treats `True` as `1`.
  - `AuditEvent`, an immutable record with exactly `event_id: int`, `execution_id: str`, `occurred_at: datetime`, `event_type: str`, `detail: Mapping[str, JsonValue]`. `ValueError` when: `event_id` is not an `int` of at least 1 (a `bool` is rejected); `execution_id` fails `validate_execution_id`; `occurred_at` has no UTC offset; `event_type` is not a non-empty `str`; `detail` is not a JSON object under the rule below. Equality compares the other fields with `==` and the details with `same_json` (Revision 2).
  - JSON object rule: a `dict` whose keys are `str` and whose values are, recursively, `None`, `bool`, `int`, `str`, `list` or `dict` under the same rule. Anything else, `float`, `tuple` and `set` included, is `ValueError`. Hashing `IngestionRun` and `AuditEvent` is not required.
- `ec_procurement_quality.domain.persistence_errors`: `PersistenceError(Exception)`, and `PersistenceConnectionError`, `PersistenceIntegrityError`, `PersistenceNotFoundError` and `MigrationError`, each a direct subclass of `PersistenceError`.
- `ec_procurement_quality.application.ingestion_repository.IngestionRepository`, a `typing.Protocol` (it need not be `runtime_checkable`) with exactly:
  ```python
  def start_run(
      self, *, execution_id: str, scope: Mapping[str, JsonValue], started_at: datetime
  ) -> IngestionRun: ...


  def finish_run(
      self, *, execution_id: str, status: RunStatus, finished_at: datetime
  ) -> IngestionRun: ...


  def read_run(self, execution_id: str) -> IngestionRun: ...


  def record_observation(self, observation: Observation) -> Observation: ...


  def read_observation(self, execution_id: str, sequence: int) -> Observation: ...


  def list_observations(self, execution_id: str) -> tuple[Observation, ...]: ...


  def append_audit_event(
      self,
      *,
      execution_id: str,
      occurred_at: datetime,
      event_type: str,
      detail: Mapping[str, JsonValue],
  ) -> AuditEvent: ...


  def list_audit_events(self, execution_id: str) -> tuple[AuditEvent, ...]: ...
  ```
  `Mapping` is `collections.abc.Mapping`; `datetime` is `datetime.datetime`; `Observation` is F1's `ec_procurement_quality.domain.raw_evidence.Observation`, unchanged.
- `ec_procurement_quality.infrastructure.postgres_settings.PostgresSettings`, an immutable record built with keyword arguments only: `host: str`, `port: int`, `dbname: str`, `user: str`, `password: str`, `connect_timeout: int = 5`. `ValueError` when `host`, `dbname` or `user` is not a non-empty `str`; `password` is not a `str`; any of them contains U+0000; `port` is not an `int` from 1 to 65535 (a `bool` is rejected); `connect_timeout` is not an `int` from 2 to 60 (a `bool` is rejected; `libpq` treats 1 as 2). The message names the field and never its value. `repr()` and `str()` never contain the password.
- `ec_procurement_quality.infrastructure.postgres_migrations`:
  - `apply_migrations(settings: PostgresSettings, directory: pathlib.Path) -> tuple[str, ...]`, returning the file names applied by this call, in order.
  - `MIGRATION_LOCK_KEY: int`, a constant within the signed 64-bit range, the key of the runner's advisory lock (tests use it to hold the lock from outside).
- `ec_procurement_quality.infrastructure.postgres_ingestion_repository.PostgresIngestionRepository(settings: PostgresSettings)`. It satisfies `IngestionRepository` structurally; it connects when built; it has `close()` and works as a context manager (`__exit__` closes); its docstring states it is used by "one thread at a time" (as SA-13).

### Schema (`migrations/0001_initial_schema.sql`)
Source: the human's decisions of 2026-10-13, ADR 0002, ADR 0005, ADR 0007. Items marked "(addition)" were accepted by the human on 2026-10-13 (resolved question 9). The executor writes the file; the human reviews it line by line (resolved question 6). Constraint and function names are free; behavior is binding. All tables live in the connection's default schema (`public` in a fresh database), unqualified.

| Table | Column | Type and rule |
|---|---|---|
| `ingestion_run` | `execution_id` | `text` primary key; check `execution_id ~ '^[a-z0-9][a-z0-9-]{0,63}$'` (addition) |
| | `scope` | `jsonb NOT NULL`; check `jsonb_typeof(scope) = 'object'` (addition) |
| | `started_at` | `timestamptz NOT NULL` |
| | `finished_at` | `timestamptz NULL` |
| | `status` | `text NOT NULL`, check in (`'running'`, `'succeeded'`, `'failed'`) |
| | (table) | check `(finished_at IS NULL) = (status = 'running')`; check `finished_at >= started_at` |
| `raw_evidence` | `content_hash` | `text` primary key; check `content_hash ~ '^[0-9a-f]{64}$'` |
| | `size` | `bigint NOT NULL`, check `size >= 0` |
| `observation` | `execution_id` | `text NOT NULL`, foreign key to `ingestion_run` |
| | `sequence` | `integer NOT NULL`, check `sequence >= 0`; primary key (`execution_id`, `sequence`) |
| | `method`, `url` | `text NOT NULL`, each check `<> ''` |
| | `status` | `integer NOT NULL`, check between 100 and 599 |
| | `headers` | `jsonb NOT NULL`; check `jsonb_typeof(headers) = 'array'` and no element whose first item matches `^set-cookie$` ignoring case (addition: the database also guards RE-6) |
| | `captured_at` | `timestamptz NOT NULL` |
| | `content_hash` | `text NOT NULL`, foreign key to `raw_evidence` |
| `audit_event` | `event_id` | `bigint GENERATED ALWAYS AS IDENTITY` primary key |
| | `execution_id` | `text NOT NULL`, foreign key to `ingestion_run` |
| | `occurred_at` | `timestamptz NOT NULL` |
| | `event_type` | `text NOT NULL`, check `<> ''` |
| | `detail` | `jsonb NOT NULL DEFAULT '{}'`; check `jsonb_typeof(detail) = 'object'` (addition) |

- `observation` has no `size` column: the size is read from `raw_evidence` by join.
- Indexes (addition): `observation(content_hash)` and `audit_event(execution_id)`.
- Append-only (ADR 0002): a row trigger rejects `UPDATE` and `DELETE`, and a statement trigger rejects `TRUNCATE`, on `raw_evidence`, `observation` and `audit_event`. On `ingestion_run`, `DELETE` and `TRUNCATE` are rejected (addition), and a `BEFORE UPDATE` row trigger allows an update only when the old `status` is `running`, the new `status` is `succeeded` or `failed`, and `execution_id`, `scope` and `started_at` are unchanged; the check constraints then require `finished_at`. Every rejection raises SQLSTATE `23000` (`integrity_constraint_violation`).
- No audit event type catalogue and no content rule for `scope`: deliberate (intent § Scope Out).
- The file carries a short comment above each constraint group and each trigger saying which rule it enforces, so that the human's line-by-line review can follow it.

### Runner contract (resolved question 1)
- **Directory.** `migrations/` at the repository root, passed to `apply_migrations` as a path. Only regular files whose name ends in `.sql` (any case) directly in the directory are migrations; other files and subdirectories are ignored. A migration name matches `^(\d{4})_[a-z0-9_]+\.sql$`; its version is the number. Versions are unique and contiguous from `0001`; lexical order is application order. A missing directory, a bad name, a repeated or missing number, an empty file, or bytes that are not strict UTF-8 raise `MigrationError` naming the file (or "the migrations directory") **before any connection is opened**.
- **Checksum.** The SHA-256 of the file's exact bytes, lowercase hex. `.gitattributes` (`* text=auto eol=lf`) makes the checked-out bytes the same on Windows and Linux.
- **Lock.** On its own connection, the runner first calls `pg_try_advisory_lock(MIGRATION_LOCK_KEY)`. If it returns false, `MigrationError` ("another migration run holds the lock"), nothing created or applied. It never waits. The lock is released before the runner returns, and in any case when its connection closes.
- **Bookkeeping.** Under the lock, the runner creates, if absent, `schema_migration (version integer PRIMARY KEY CHECK (version >= 1), filename text NOT NULL UNIQUE, sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'), applied_at timestamptz NOT NULL DEFAULT now())`. It is not created by a numbered file.
- **Integrity of applied files.** Before applying anything: every recorded row must have a file with the same version, file name and checksum, and every file whose version is at most the highest recorded version must be recorded. Otherwise `MigrationError` naming the file, nothing applied.
- **Applying.** Each pending file, in order, runs in its own transaction together with the insert of its bookkeeping row: the file text is executed with no parameters (several statements allowed), the row is inserted, the transaction commits. On any database error the transaction is rolled back, `MigrationError` naming the file is raised, and later files are not attempted. A failed file is never recorded and may be corrected, since it was never applied.
- **Connection failures** while connecting or during a run raise `PersistenceConnectionError`, not `MigrationError`. Each file's transaction stays atomic: its effects and its bookkeeping row commit together or not at all. A connection lost before the commit leaves that file neither applied nor recorded. A connection lost while the commit is in flight leaves the outcome of that one file **unknown** (applied and recorded, or neither). Running the runner again resolves it either way, because it reads the bookkeeping table: a recorded file is skipped, an unrecorded one is applied. This case is documented, not tested (same reason as intent AC11).
- **Authoring rules** (checked at review and audit; the runner does not parse SQL): a migration file contains no transaction control (`BEGIN`, `COMMIT`, `ROLLBACK`, `SAVEPOINT`), no statement that cannot run inside a transaction (`CREATE INDEX CONCURRENTLY`, `VACUUM`, `CREATE DATABASE`), and no `SET` that outlives the transaction; it never edits `schema_migration`. An applied file is never edited (ADR 0007).
- **Invocation.** A library function only. F3 adds no CLI command; the integration tests are its only caller in F3.

### Adapter behavior
- **Transactions.** Every port operation is one transaction, so it is atomic: it is applied completely or not at all, never in part. Reads run in a transaction too, so a list and its joins see one snapshot. An error raised before the commit (validation, integrity, a connection lost before the statements are sent or while the transaction is open) leaves nothing written. **A connection lost while the commit is in flight leaves the outcome unknown** (intent AC11): `PersistenceConnectionError` is then raised even though the transaction may have committed in full. The adapter cannot tell which, and it does not try to find out.
- **Session.** The session time zone is UTC. Every `datetime` read back is aware, in UTC, and equal (same instant) to the one written. The UTC offset given is not stored (resolved question 7).
- **Validation before writing.** Every operation validates its input before any SQL is sent: the domain rules (through the domain types, `validate_execution_id`, `validate_sequence`), and the PostgreSQL limits of intent AC10 (U+0000 or a lone surrogate in any text, keys or strings of scope and detail; `sequence` above 2,147,483,647; `size` above 9,223,372,036,854,775,807). Each rejection is `ValueError` naming the field, never its value.
- **`start_run`.** Inserts a `running` run. If the execution id exists: when `same_json(stored scope, given scope)` holds and `started_at` is the same instant, it returns the stored run unchanged, whatever its status; otherwise `PersistenceIntegrityError`. The stored scope is read back from `jsonb`, which keeps `true` as `True` and integers as `int`, and then compared in Python with `same_json` (Revision 2).
- **`finish_run`.** `status` that is not a `RunStatus` instance, `status` `RUNNING`, or a naive `finished_at` -> `ValueError` before any SQL. Reads the run with a row lock: missing -> `PersistenceNotFoundError`; `running` -> builds the finished `IngestionRun` (a `finished_at` before `started_at` -> `ValueError`, nothing written) and updates; already finished with the same status and the same `finished_at` instant -> returns it unchanged; already finished otherwise -> `PersistenceIntegrityError`.
- **`record_observation`.** In one transaction:
  1. Insert the `raw_evidence` row if absent. An existing row with another size -> `PersistenceIntegrityError`.
  2. Insert the observation if absent.
  3. If one already exists for that execution and sequence, read it (with its size) and compare every field: method, URL, status, headers (an ordered list of pairs, names and values exact), the `captured_at` instant, content hash and size.
  4. Equal -> return the stored observation, nothing written. Different -> `PersistenceIntegrityError` naming execution and sequence, and the transaction is rolled back, so no new `raw_evidence` row remains.

  A missing run -> `PersistenceIntegrityError`, nothing written. `ON CONFLICT DO NOTHING` alone cannot compare content; the comparison above is what tells a repeat from a conflict. This comparison has no `bool`/`int` gap (checked for Revision 2): the header names and values are `str`; status, sequence and size are plain `int` on both sides, because `Observation` rejects a `bool` for each (`_is_plain_int`, RE-11) and the database returns `int`; content hashes compare their text; times compare instants.
- **`append_audit_event`.** Inserts and returns the event with the identity the database assigned. A missing run -> `PersistenceIntegrityError`. Not idempotent (resolved question 8): the same call made twice appends two events, and after a commit-in-flight `PersistenceConnectionError`, repeating it may append a duplicate.
- **Reads.** `read_run` and `read_observation` of an identity never written -> `PersistenceNotFoundError`. `list_observations` (by `sequence`) and `list_audit_events` (by `event_id`) of a run never started -> `PersistenceNotFoundError`; of a run with none -> `()`. A stored row that fails domain validation (only possible through direct SQL) -> `PersistenceIntegrityError`.
- **Connection.** Built with `psycopg.connect` and the settings as separate keyword arguments (`host`, `port`, `dbname`, `user`, `password`, `connect_timeout`), never a connection string. No reconnect and no retry: once the connection is lost, every later call raises `PersistenceConnectionError`. A call after `close()` raises `RuntimeError` before any SQL.
- **Closed set of outcomes.** Each operation ends in its result, one of the four `PersistenceError` subclasses other than `MigrationError`, `PersistenceError` itself for a database failure of any other kind, `ValueError` (invalid input) or `RuntimeError` (closed). Exceptions that are not database errors (`KeyboardInterrupt`, `MemoryError`) propagate unchanged.

### Errors and output (intent AC12)
- Messages are fixed text naming the operation and, where useful, an execution id, a sequence, a content hash or a migration file name. They never hold a password, host, port, database or user name, an SQL parameter, a stored value (URL, header, scope, detail) or any text from the driver or the server.
- Every error is raised outside the `except` block that caught the driver's exception, with no `from` clause, so no `psycopg` exception is reachable through `__cause__` or `__context__`. As in SA-8 Revision 5, the `__context__` may be an exception the caller was already handling when the call started; it belongs to the caller.
- The adapter and the runner write no log records of their own and configure no logging.

### Tests
- **Tiers.** Unit tests (`tests/unit/`) need no database and open no socket; every new F3 unit test file runs under a socket guard like F2's (`autouse` in the file; moving F2's guard to a shared `conftest.py` is out of scope). Integration tests (`tests/integration/`) carry the `integration` marker, declared in `[tool.pytest]` of `pyproject.toml`.
- **Settings for tests.** The integration fixtures read `POSTGRES_HOST` (default `127.0.0.1`), `POSTGRES_PORT` (default `5432`), `POSTGRES_DB`, `POSTGRES_USER` and `POSTGRES_PASSWORD` from the environment, which `uv run --env-file .env` loads locally and the workflow sets in CI. Only the fixtures read them; no code under `src/` reads the environment or `.env` (resolved question 3). The password lives only inside a `PostgresSettings`.
- **One throwaway database per test (Revision 2).** This is the contract. Every integration test runs in its own database, created for that test and dropped when it ends, whether it passes or fails, with `DROP DATABASE ... WITH (FORCE)`. No two tests share a database, and no test runs in the template.
  - Names start with `ecpq_test_` followed by random hex.
  - Databases are created and dropped through an *admin connection* to the configured database, in autocommit. Creating a database from there adds no object inside the configured database.
  - Tests of the migration runner (AC1 to AC4) and the connection tests that need an empty database start from `CREATE DATABASE <name> TEMPLATE template0`. `template0` is used rather than the default `template1`, which a developer may have changed.
  - Every other integration test starts from a copy of the session's migrated template: `CREATE DATABASE <name> TEMPLATE <template>`.
- **Migrated template (speed device only).** The fixtures manage it as follows:
  1. Once per session, they create `ecpq_test_template_<hex>` from `template0` and apply the repository's `migrations/` to it with `apply_migrations`. The runner's connection is closed when it returns.
  2. They then run `ALTER DATABASE ... ALLOW_CONNECTIONS false`, so no later connection, from a test or a mistaken fixture, can reach it.
  3. Copies are made only through the admin connection, which is connected to the configured database and not to the template. So no other session is connected to the template when it is copied, which `CREATE DATABASE ... TEMPLATE` requires (observed: otherwise it fails with "being accessed by other users" after about 5 s).
  4. At session end the template is dropped with `DROP DATABASE ... WITH (FORCE)` (observed to work on a database that refuses connections).

  A test never connects to the template or changes it.
- **Leftover check.** The session records every database it creates. At session end, after the template is dropped, it asserts that none of them remains (`pg_database`), and that the configured database's user objects (`pg_class` outside `pg_catalog`, `information_schema` and `pg_toast`) are the same as at session start. A test killed mid-run can leave `ecpq_test_` databases behind; the README documents the query to remove them.
- **Skip or fail** (resolved question 4). When a required variable is missing or the configured database cannot be reached within the connect timeout, every integration test is skipped with a reason naming `uv run --env-file .env pytest tests/integration`, unless `CI` is `true`, in which case it fails.
- **Network guard.** The F2 guard applies only to `tests/unit/test_sercop_source.py`, so the integration tests need no exception to it. Integration tests connect only to the configured host.
- **Data.** Synthetic only; URLs use `.invalid`; passwords in tests are markers such as `synthetic-password-marker`, never the developer's.
- **JSON values in assertions.** Tests compare scopes and details with `same_json` (directly, or through the record equality that uses it), never with `==` on the raw mappings.

### CI (resolved question 5)
- The existing `tests` job of `.github/workflows/tests.yml` gains a `postgres:18` service container (major version 18, as ADR 0007 requires) with a health check, and a job environment with the five variables. The service's password is a fixed, low-entropy placeholder that is not a secret (the service lives only for that job), like `.env.example`; no repository secret is created. `CI` is `true` on GitHub Actions, so a missing database fails the job. The test command stays `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing`; the job id `tests` does not change, so no required check changes.

### Other constraints
- **Layer imports** (source: `AGENTS.md`; ADR 0001; ADR 0007; PT-3): `domain` imports only the standard library and itself; `application` only the standard library, `domain` and itself; only `infrastructure` imports `psycopg` in any form, enforced by a new layer test like `test_layer_only_infrastructure_imports_httpx`.
- **Dependency** (source: `AGENTS.md`; ADR 0007; PT-11): exactly one entry added to `[project] dependencies`, `psycopg[binary]>=3.3.6`, approved by the human on 2026-10-13 (resolved question 2). No development dependency is added.
- **Package root**: no new file directly in `src/ec_procurement_quality/` (`project-toolchain` Invariant 3).
- **Unchanged files**: F1 and F2 modules and tests (except `tests/unit/test_layers.py`, which gains a test), `compose.yaml`, `.env.example`, `.github/dependabot.yml`, `harny-feedback.yml`, ADR 0006 and ADR 0007. The Dependabot correction to `dependabot.yml`, ADR 0006 and ADR 0007 is a separate change (resolved question 10), not part of F3.

## Proposed approach
Revisable by the executor if it records why, except the decisions marked "resolved question N": the human made those at gate 1 on 2026-10-13, and only the human changes them.

- Decision (resolved question 2, approved): `psycopg[binary]` — rationale: the Windows machine has no `libpq` (journal Day 15), the binary wheel bundles one, wheels exist for `cp313` on Windows, Linux and macOS, and the psycopg docs recommend it for development; rejected: the pure Python package (needs a system `libpq` on every machine and CI), `psycopg[c]` (needs a compiler and `pg_config`; the docs prefer it for production sites, which this project does not have). Lower bound `>=3.3.6`, the version checked; `uv.lock` pins it. Lock impact: `psycopg` 3.3.6, `psycopg-binary` 3.3.6, `tzdata` 2026.5 (Windows marker), 22 to 25 packages.
- Decision (resolved question 6, option B): the executor writes `migrations/0001_initial_schema.sql` from § Binding constraints "Schema", with a comment per constraint group and trigger. The human reviews it line by line at the executor's hand-off, where each constraint and trigger is explained to the human (what it enforces, which AC it serves, and what its schema test shows). This replaces "escribe tú las primeras migraciones SQL" of `docs/learning/plan.md` Day 17.
- Decision (resolved question 1): one transaction per migration file, holding its bookkeeping row — rationale: a failed file leaves no trace and is never recorded, and earlier files keep their progress; rejected: one transaction for all pending files (a late failure discards every earlier file, and long DDL batches hold locks longer).
- Decision (resolved question 1): `pg_try_advisory_lock`, fail at once — rationale: deterministic and testable, and a second run on a developer database is a mistake to report, not to wait for; rejected: the waiting `pg_advisory_lock` (can hang a CLI with no feedback), locking the bookkeeping table (it does not exist before the first run).
- Decision (resolved question 1): contiguous numbering from `0001` — rationale: a missing number reveals a deleted or misnamed file before anything runs; rejected: allowing gaps (a deleted pending file would go unnoticed).
- Decision (resolved question 1): the runner creates `schema_migration` — rationale: it must exist before the first file is recorded; rejected: creating it in `0001` (the runner could not record `0001` in the same transaction without special-casing).
- Decision (resolved question 1): `migrations/` at the repository root, passed as a path — rationale: ADR 0007 names `migrations/`, SQL reviews as SQL next to the code, and F4 runs from the repository with `uv run`; rejected for now: `src/ec_procurement_quality/infrastructure/migrations/` (it would ship in a wheel, a question that belongs to the release work D-13).
- Decision (resolved question 1): no CLI command in F3 — rationale: no acceptance criterion needs one and the `cli` capability stays `--version` only; F4 decides whether `ingest` applies pending migrations first or a `migrate` command exists.
- Decision (resolved question 3): a settings value built by the caller, passed as keyword arguments — rationale: no connection string can carry the password into a log or message; the environment belongs to `interfaces` (architecture § Interfaces: "translates command input, configuration"), and F4's CLI reads the same five names Compose uses; rejected: reading `POSTGRES_*` inside the adapter (configuration in `infrastructure`), `libpq`'s own `PG*` variables (a second set of names beside Compose's), a DSN string.
- Decision (resolved question 4): skip locally, fail in CI — rationale: `uv run pytest` keeps working on a machine without Docker, while CI can never pass with the integration tests silently skipped; rejected: always fail (every local run without Docker goes red), always skip (CI could pass without testing persistence). The tasks file must record an integration run with `--env-file .env` as evidence, never a skipped run.
- Decision (resolved question 5): the service in the existing `tests` job — rationale: one coverage report that includes the adapter, no new required check in GitHub settings; rejected: a separate `integration` job (a new check name to add to branch protection, two coverage reports). The plan's Day 17 wording "job de integración" is met by the integration step running inside `tests`.
- Decision (resolved question 7): store instants only — rationale: the human's column list has one `timestamptz` per time, and the exact offset already lives in the local observation record, which is the evidence (ADR 0005); rejected: an extra offset column per time. Consequence: for a repeat of the same observation with the same instant and another offset, F1 reports a conflict (it compares bytes) while PostgreSQL sees a repeat; F4 stores to the local store first, so F1's conflict comes first.
- Decision (resolved question 8): no idempotency key for audit events in F3 — rationale: the human fixed `event_id` as an identity and left the catalogue to F4; rejected now: a caller-supplied event key (a schema change better made with the catalogue). F4 must not retry `append_audit_event` blindly after `PersistenceConnectionError`.
- Decision (Revision 2, finding P1): document the commit-in-flight case and do not test it — rationale: it cannot be made deterministic without a test proxy that understands the PostgreSQL wire protocol and drops the server's reply to `COMMIT` after the server received it; the deterministic cases (lost before the statements are sent; lost while the transaction is open, held there by a lock) are tested, and the safety of a repeat is shown by the idempotency tests of AC7 and AC8; rejected: a protocol-aware proxy in the tests (out of proportion for F3), claiming "nothing written" for every connection error (false).
- Decision (Revision 2, finding P2): `same_json` lives in `domain` — rationale: deciding when two scopes are "the same scope" is a rule about run identity, not about storage; it needs only the standard library, so it is unit-tested without a database, and the domain records use it for their own equality; the adapter calls it after reading `jsonb` back; F4 can reuse it; `domain` stays free of `psycopg` and SQL. Rejected: comparing in the adapter only (the rule would hide in `infrastructure` and could be tested only against a database); comparing with SQL `jsonb` equality (`stored = %s::jsonb` also tells `true` from `1` and ignores key order, but the domain records would still compare with Python `==`, and the rule would have two homes).
- Decision (Revision 2, finding P2): one throwaway database per test, with a migrated template as a speed device — rationale: no test can see another test's rows, the runner tests always start empty, and copying a small template is cheap; rejected: one migrated database shared by the session with unique ids per test (Revision 1 suggestion; tests could still see each other's rows and constraint counts), creating and migrating a database per test from scratch (correct but slower).
- Decision: refuse floats in scope and detail (intent AC10) — rationale: exact read-back equality; NaN and infinities are not JSON; rejected: accepting floats and comparing approximately.
- Decision: insert-then-compare in one transaction for `start_run` and `record_observation` — rationale: the key decides identity, Python compares content (with `same_json` for scope), and a rollback guarantees no partial writes; rejected: `ON CONFLICT DO UPDATE` (an overwrite), comparing inside one SQL statement (harder to read, same result).
- Decision: the triggers raise SQLSTATE `23000` — rationale: the driver maps class `23` to its integrity error, so one mapping covers constraints and triggers; rejected: the default `P0001`.
- Suggestion: map driver errors by kind — connection failures and a broken connection after an error -> `PersistenceConnectionError`; integrity errors -> `PersistenceIntegrityError`; any other driver error -> `PersistenceError`.
- Suggestion: keep `scope` and `detail` from changing after construction (for example a deep copy taken at construction and exposed through `types.MappingProxyType`); what is pinned is that attributes cannot be assigned and that equality is the one in § Binding constraints. A `dataclass(frozen=True, eq=False)` with an explicit `__eq__` (and `__hash__ = None`) is one way.
- Suggestion (fixtures in `tests/integration/conftest.py`):
  - a session fixture that resolves the settings and applies the skip or fail policy;
  - a session fixture holding the admin connection and the migrated template (§ Binding constraints "Tests");
  - a function fixture `empty_database` (from `template0`) and a function fixture `migrated_database` (a copy of the template), each yielding `PostgresSettings` for its database and dropping it at teardown;
  - the session-end leftover check.
- Suggestion (AC11, lost before the statements are sent): in a test's database, from the admin connection, `SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = <test database>`, then call the adapter.
- Suggestion (AC11, lost while the transaction is open):
  1. A second test connection to the test's database runs `BEGIN; LOCK TABLE observation IN ACCESS EXCLUSIVE MODE`.
  2. A `concurrent.futures.ThreadPoolExecutor` with one worker calls `record_observation` (the adapter is still used by one thread at a time). It inserts its `raw_evidence` row and then waits on the lock.
  3. The test polls `pg_stat_activity` until a backend on that database other than the locker shows `wait_event_type = 'Lock'` (fail after 10 s), and terminates it.
  4. It rolls back the locker, collects the future (expected: `PersistenceConnectionError`), and counts rows from a fresh connection: no `raw_evidence` row for that content and no observation.

  Every wait has a timeout, so the test cannot hang.
- Suggestion (layer test): generalize the AST helper of `test_layers.py` to take a library name and add `test_layer_only_infrastructure_imports_psycopg`, which also requires one `infrastructure` module to import `psycopg` (so it cannot pass vacuously). The existing tests keep their names and behavior.
- Suggested test files and `-k` tokens (the focused commands below rely on them):
  - `tests/unit/test_ingestion_audit.py`: `run_status`, `ingestion_run`, `audit_event`, `json`, `same_json`, `invalid`;
  - `tests/unit/test_postgres_settings.py`: `settings`, `password`;
  - `tests/unit/test_postgres_migration_files.py` (name checks before any connection): `migration_files`;
  - `tests/unit/test_layers.py`: `layer`;
  - `tests/integration/test_postgres_migrations.py`: `runner_applies`, `runner_failure`, `runner_integrity`, `runner_lock`;
  - `tests/integration/test_postgres_schema.py`: `schema_rejects`, `append_only`, `run_transition`;
  - `tests/integration/test_postgres_ingestion_repository.py`: `run_`, `observation_`, `audit_event_`, `invalid`, `connection`, `leak`, `satisfies_port`;
  - `tests/integration/test_postgres_isolation.py`: `isolation` (one database per test, template not reachable, nothing left, configured database untouched).
- Suggestion (CI), to adapt:
  ```yaml
  jobs:
    tests:
      runs-on: ubuntu-latest
      services:
        postgres:
          image: postgres:18
          env:
            POSTGRES_DB: ecpq_ci
            POSTGRES_USER: ecpq_ci
            POSTGRES_PASSWORD: ci-placeholder
          ports:
            - 5432:5432
          options: >-
            --health-cmd "pg_isready -U ecpq_ci -d ecpq_ci"
            --health-interval 5s --health-timeout 3s --health-retries 10
      env:
        POSTGRES_HOST: 127.0.0.1
        POSTGRES_PORT: "5432"
        POSTGRES_DB: ecpq_ci
        POSTGRES_USER: ecpq_ci
        POSTGRES_PASSWORD: ci-placeholder
  ```

## Consumers and migration
- **Existing tests.** The 961 tests keep passing unchanged. `tests/unit/test_layers.py` gains the `psycopg` test; if its helper is generalized, `test_layer_only_infrastructure_imports_httpx` keeps its name and checks. F2's network guard is not touched.
- **`pyproject.toml` and `uv.lock`.** One dependency entry and the `integration` marker; `uv lock` adds three packages.
- **`.github/workflows/tests.yml`.** The service and job environment; steps and command unchanged; the `setup-uv` SHA unchanged (PT Invariant 5).
- **F1 and F2.** Not changed. F3 reuses `Observation`, `ContentHash`, `validate_execution_id` and `validate_sequence`. F2's headers are decoded as Latin-1, so they never hold a lone surrogate; a U+0000 in a header value is not expected with the real HTTP stack but is refused with `ValueError` if it arrives.
- **F4 (consumer rules, to carry into its spec).**
  - Apply migrations before using the adapter.
  - Catch `PersistenceError` subclasses; never retry `ValueError` or `RuntimeError`.
  - **`PersistenceConnectionError` is not proof that nothing was written.** If the connection was lost while the commit was in flight, the write may have committed in full. Repeat only what is safe to repeat, on a new adapter, with the same values: `start_run`, `finish_run` and `record_observation` are safe (a committed first attempt makes the repeat a no-op). `append_audit_event` is not safe and may duplicate an event (resolved question 8).
  - Store the response in the local store first, then `record_observation`.
  - Decide whether observations and events may be recorded after a run has finished, how interrupted (`running`) runs are closed, the event catalogue, and the contents of `scope`.
  - Use `same_json` when comparing a scope.
  - Use one adapter per thread.
- **`specs/current`.** At archive, `harny-sync` creates the persistence capability and modifies `project-toolchain` PT-3, PT-6, PT-10 and PT-11 (and adds the integration-tier requirement), as listed in § Ownership. `raw-evidence`, `source-access` and `cli` are not touched.
- **Docs.** `README.md` (§ Version 1 scope and § Technologies: the schema, runner and adapter exist, nothing calls them; § Development commands: the integration test command and the query to remove leftover `ecpq_test_` databases), `AGENTS.md` § Current commands (`uv run --env-file .env pytest tests/integration`), `docs/architecture.md` § Infrastructure boundary (the schema and runner contract exist; raw bytes stay local) and § Open questions (audit events catalogue still open), `CHANGELOG.md` § Unreleased (an `Added` entry, the `psycopg` dependency, and the known limitations: unknown outcome after a connection lost during a commit, audit events not idempotent, triggers do not bind a superuser).
- **ADR 0006, ADR 0007 and `.github/dependabot.yml`.** F3 touches none of them. Both ADRs say the lockfile is watched by Dependabot, while `.github/dependabot.yml` lists only `github-actions`. The human's session corrects this in a separate small change (resolved question 10): it adds the `uv` ecosystem to `.github/dependabot.yml` and corrects the Dependabot wording in ADR 0006 and ADR 0007. That change is not part of F3's ownership, and the F3 audit does not need it.
- **Glossary (optional, human).** The glossary term is "ingestion execution" and the code says `execution_id`; the human named the table `ingestion_run`. Adding "run" as the table's word for an ingestion execution would keep "one term, one meaning"; F3 does not require it.

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| A superuser bypasses the triggers (`ALTER TABLE ... DISABLE TRIGGER`, `session_replication_role = replica`); the Compose user is a superuser | Low | High | The guard protects against application and accidental writes, not a superuser; documented as a known limitation in `CHANGELOG.md`; a least-privilege role is out of scope until a deployment exists (ADR 0003) |
| Rows of `schema_migration` edited by hand | Low | Med | The checksums protect files, not rows; forward-only rule and review; documented |
| A migration file holds `COMMIT` or a statement that cannot run in a transaction, breaking per-file atomicity | Low | High | Authoring rule in § Runner contract, checked at the human's line-by-line review and at audit; a statement refused inside a transaction fails as `MigrationError` |
| The server's error text quotes rows (observed) and could leak URLs, headers or scope | Med | Med | No driver text in any message, nothing chained (AC12), marker tests on conflicts and connection errors |
| Connection lost while a commit is in flight: the write may have committed although `PersistenceConnectionError` was raised | Low | Med | Documented in intent AC11, the F4 consumer rules and `CHANGELOG.md`; the runner rerun is safe; `start_run`, `finish_run` and `record_observation` are idempotent; `append_audit_event` may duplicate (resolved question 8); not tested, for the reason in § Proposed approach |
| A boolean scope or detail value taken as the same as a number (`True == 1` in Python) | Low | Med | `same_json` (Revision 2) used by `start_run` and by record equality; unit and integration cases in § Validation AC7 and AC9 |
| Integration tests skipped locally give false confidence | Med | Med | CI fails instead of skipping; `tasks.md` must record a run with `--env-file .env` and its pass count; `-rs` shows skip reasons |
| A copy from the template fails because a session is connected to it | Low | Low | Only the runner connects to the template, before `ALLOW_CONNECTIONS false`; copies run from the admin connection on the configured database; a failure errors the test (never a skip) |
| Throwaway databases left after a killed test run | Low | Low | `ecpq_test_` prefix; never the configured database; the session-end check; a cleanup query documented in the README |
| The password appears in pytest output (for example with `--showlocals`) | Low | Med | The password lives only inside `PostgresSettings`, whose `repr` hides it; CI does not use `-l` |
| The CI placeholder password is flagged by gitleaks | Low | Low | Low-entropy placeholder like `.env.example`; an inline allow comment only if the scan flags it |
| Clock offsets lost: PostgreSQL treats the same instant with another offset as a repeat | Low | Low | The local observation keeps the offset; F1 compares bytes first (resolved question 7) |
| `psycopg-binary` has no wheel for a future Python or platform | Low | Med | Wheels for `cp313` on Windows, Linux and macOS checked on 2026-10-13; the pure Python variant with a system `libpq` is the fallback |
| An advisory lock key collides with another tool on the same database | Low | Low | The database belongs to this project; the key is one named constant |
| `migrations/` is not inside a built wheel | Med | Low | Out of scope until the release work (D-13); F3 and F4 run from the repository |

## Validation
One row per AC. Cwd: the repository root for every row. Setup for every row: `uv sync --locked` (after O1 adds the dependency). Integration rows also need the Compose database (`docker compose up -d --wait`) and run with `--env-file .env`, which loads the variables without printing them; in CI the job sets them. Every integration test runs in its own throwaway database (§ Binding constraints "Tests"): an *empty* database from `template0`, or a *migrated* database copied from the session template. Commands work in Git Bash and PowerShell. Broader command for unit rows: `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing` (what CI runs); for integration rows: `uv run --env-file .env pytest --cov=ec_procurement_quality --cov-report=term-missing`.

| AC | Demonstrated by | Tests to write | Tier | Framework | Setup | Focused command | Broader command | Cwd |
|---|---|---|---|---|---|---|---|---|
| AC1 | the real `migrations/` applied once to an empty throwaway database; second call a no-op | `runner_applies` (empty database): returns `("0001_initial_schema.sql",)`; the four tables exist (`to_regclass`); one bookkeeping row with version 1, that name and `hashlib.sha256` of the file bytes; a second call returns `()` and the rows are equal before and after; synthetic files `0001_a.sql`, `0002_b.sql` in `tmp_path` apply in order | integration | pytest, psycopg | Compose database, `--env-file .env` | `uv run --env-file .env pytest tests/integration/test_postgres_migrations.py -q -k runner_applies` | the integration coverage command | repo root |
| AC2 (failure) | a failing file is rolled back, not recorded, later files not attempted; correcting it works | `runner_failure` (empty database): the AC2 example (`synthetic_a` exists, `synthetic_b` and `synthetic_c` do not, only version 1 recorded, message names `0002_b.sql` and holds no server text); after rewriting `0002_b.sql`, the runner returns `("0002_b.sql", "0003_c.sql")` | integration | pytest, psycopg | as AC1 | `uv run --env-file .env pytest tests/integration/test_postgres_migrations.py -q -k runner_failure` | the integration coverage command | repo root |
| AC3 (failure) | mismatches stop the runner before anything is applied; name checks open no connection | `runner_integrity` (empty database): changed byte of an applied file, applied file deleted, applied file renamed, each with a pending file present -> `MigrationError` naming the file, the pending file not applied. `migration_files` (unit, under a socket guard, settings pointing at `127.0.0.1` on a port nobody listens on): `0001_a.sql` + `0003_c.sql`, `0001_a.sql` + `0001_b.sql`, `1_a.sql`, `0001_A.sql`, `0002_x.SQL`, an empty file, non-UTF-8 bytes, a missing directory -> `MigrationError` naming the file and no socket attempt; a `README.md` beside them is ignored | unit, integration | pytest, psycopg | unit: none; integration: as AC1 | `uv run pytest tests/unit/test_postgres_migration_files.py -q` and `uv run --env-file .env pytest tests/integration/test_postgres_migrations.py -q -k runner_integrity` | both coverage commands | repo root |
| AC4 (failure) | a held lock makes the runner fail at once | `runner_lock` (empty database): a test connection to it holds `pg_advisory_lock(MIGRATION_LOCK_KEY)`; the runner raises `MigrationError` within the connect timeout; `to_regclass('schema_migration')` is null; after `pg_advisory_unlock` the runner succeeds | integration | pytest, psycopg | as AC1 | `uv run --env-file .env pytest tests/integration/test_postgres_migrations.py -q -k runner_lock` | the integration coverage command | repo root |
| AC5 | each constraint rejects its bad row through direct SQL | `schema_rejects` (migrated database): one parametrized case per AC5 example, each expecting the driver's integrity error (SQLSTATE class `23`) or the identity error (`428C9`) and an unchanged row count; a duplicate primary key per table; an audit event without `detail` reads back `{}` | integration | pytest, psycopg | as AC1 | `uv run --env-file .env pytest tests/integration/test_postgres_schema.py -q -k schema_rejects` | the integration coverage command | repo root |
| AC6 | append-only triggers and the one allowed run transition | `append_only` (migrated database): `UPDATE`, `DELETE`, `TRUNCATE` on `raw_evidence`, `observation`, `audit_event`, and `DELETE`, `TRUNCATE` (also `CASCADE`) on `ingestion_run` -> SQLSTATE `23000`, rows unchanged. `run_transition`: `running` -> `succeeded` accepted; then `failed`, back to `running`, a new `finished_at`, a new `scope` -> `23000`; on a `running` run, changing `execution_id`, `scope` or `started_at` -> `23000` | integration | pytest, psycopg | as AC1 | `uv run --env-file .env pytest tests/integration/test_postgres_schema.py -q -k "append_only or run_transition"` | the integration coverage command | repo root |
| AC7 | runs through the port, with idempotent repeats; scopes compared as JSON values | `same_json` (unit, `test_ingestion_audit.py`): true for identical values, for `{"b": 1, "a": 2}` and `{"a": 2, "b": 1}`, and for `{"x": [1, {"y": True}]}` with itself; false for `1`/`True`, `0`/`False`, `{"x": 1}`/`{"x": True}`, `{"x": [1]}`/`{"x": [True]}`, `{"x": {"y": 0}}`/`{"x": {"y": False}}`, `[1, 2]`/`[2, 1]`, `1`/`"1"`, `[]`/`{}`, `None`/`False`; `ValueError` for a `float`. `ingestion_run` (unit): runs equal only when `same_json` holds for their scopes (`{"x": 1}` vs `{"x": True}` not equal); a plain `"succeeded"` status -> `ValueError`. `run_` (integration, migrated database): the AC7 example step by step (start, read, repeat, conflicting start, finish, repeat, conflicting finish, finish with `RUNNING` or with `"succeeded"` as a plain `str` -> `ValueError` and no change, unknown id -> `PersistenceNotFoundError`); times read back equal and have `utcoffset()` zero; the AC7 JSON-type example: `{"x": 1}` then `{"x": True}`, `{"x": [1]}` then `{"x": [True]}`, `{"x": {"y": 0}}` then `{"x": {"y": False}}`, `{"x": [1, 2]}` then `{"x": [2, 1]}` -> `PersistenceIntegrityError` and the stored scope unchanged; `{"x": [1, {"y": True}]}` repeated and `{"b": 1, "a": 2}` repeated as `{"a": 2, "b": 1}` -> the stored run unchanged | unit, integration | pytest | unit: none; integration: as AC1 | `uv run pytest tests/unit/test_ingestion_audit.py -q -k "same_json or ingestion_run"` and `uv run --env-file .env pytest tests/integration/test_postgres_ingestion_repository.py -q -k run_` | both coverage commands | repo root |
| AC8 | observations recorded once, read back equal, size by join; repeat no-op; conflict rolled back | `observation_` (migrated database): the AC8 example; counts of `raw_evidence` and `observation` rows by direct SQL; header order and repeat kept; `list_observations` ordered by sequence; conflicts (status `500`, swapped headers, `<empty>` content) -> `PersistenceIntegrityError`, stored row unchanged, no `<empty>` row; unknown run -> `PersistenceIntegrityError`, no `raw_evidence` row; unknown identity -> `PersistenceNotFoundError`; `read_observation("../escape", 1)` -> `ValueError` | integration | pytest | as AC1 | `uv run --env-file .env pytest tests/integration/test_postgres_ingestion_repository.py -q -k observation_` | the integration coverage command | repo root |
| AC9 | events appended with increasing ids and listed in order; not idempotent; details compared as JSON values | `audit_event` (unit): events equal only when `same_json` holds for their details (`{"page": True}` vs `{"page": 1}` not equal). `audit_event_` (integration, migrated database): the AC9 example; the same call made twice -> two events; empty type -> `ValueError`, no row; unknown run -> `PersistenceIntegrityError`; `list_audit_events` of an unknown run -> `PersistenceNotFoundError`, of a run without events -> `()`; a detail `{"page": True}` reads back `same_json`-equal to `{"page": True}` and not to `{"page": 1}` | unit, integration | pytest | unit: none; integration: as AC1 | `uv run pytest tests/unit/test_ingestion_audit.py -q -k audit_event` and `uv run --env-file .env pytest tests/integration/test_postgres_ingestion_repository.py -q -k audit_event_` | both coverage commands | repo root |
| AC10 (failure) | invalid or unstorable input rejected before any write | `invalid` (unit, `test_ingestion_audit.py`): every domain case of AC10 for `IngestionRun` and `AuditEvent` (including `2025.0`, NaN, `(1, 2)`, `{1, 2}`, a non-`str` key, naive times, `finished_at` before `started_at`, status/`finished_at` mismatch, a plain `str` status, `event_id` 0 and `True`) -> `ValueError`; `run_status`, `ingestion_run`, `audit_event`, `json`: valid records, equality, immutability. `invalid` (integration, migrated database): each PostgreSQL-limit case of AC10 through the port, and `finish_run` one second before `started_at` -> `ValueError`, row counts unchanged | unit, integration | pytest | unit: none; integration: as AC1 | `uv run pytest tests/unit/test_ingestion_audit.py -q` and `uv run --env-file .env pytest tests/integration/test_postgres_ingestion_repository.py -q -k invalid` | both coverage commands | repo root |
| AC11 (failure) | connection problems are typed; atomic transactions; deterministic loss cases leave nothing; no reconnect; closed adapter | `connection` (each in its own database): closed local port and wrong password -> `PersistenceConnectionError` at construction (also from `apply_migrations`); backend terminated before the call (suggestion in § Proposed approach) -> `record_observation` and then `read_run` raise `PersistenceConnectionError`, no row written (checked from a fresh connection); backend terminated while `record_observation` waits on a lock inside its open transaction (suggestion in § Proposed approach) -> `PersistenceConnectionError`, and neither its `raw_evidence` row nor its observation exists; after `close()` -> `RuntimeError`; the unknown-run observation leaves no `raw_evidence` row. Not tested, documented: a connection lost while the commit is in flight (intent AC11) | integration | pytest, psycopg | as AC1 | `uv run --env-file .env pytest tests/integration/test_postgres_ingestion_repository.py -q -k connection` | the integration coverage command | repo root |
| AC12 (failure) | no secret, setting or stored value leaks; nothing chained; no logs | `leak`: settings with `synthetic-password-marker` and a closed port; an AC8 conflict with `synthetic-url-marker` in the stored URL; an AC2 failure whose SQL holds `synthetic-sql-marker` -> no marker (nor the user, database or host) in `str`, `repr`, `args` or `traceback.format_exception`; `__cause__` is `None` and no `psycopg.Error` in the `__context__` chain; `caplog` holds no record from an `ec_procurement_quality` logger. `password` (unit): `repr` and `str` of `PostgresSettings` hide the password; `settings` (unit): each invalid field -> `ValueError` naming the field without its value | unit, integration | pytest | unit: none; integration: as AC1 | `uv run pytest tests/unit/test_postgres_settings.py -q` and `uv run --env-file .env pytest tests/integration -q -k leak` | both coverage commands | repo root |
| AC13 | layers hold; only `infrastructure` imports `psycopg`; adapter satisfies the port | `test_layer_only_infrastructure_imports_psycopg` in `tests/unit/test_layers.py`; the existing `domain` and `application` checks now cover the new modules; `satisfies_port` (integration file): `repository: IngestionRepository = PostgresIngestionRepository(settings)` in an annotated test | unit, static | pytest, mypy | none | `uv run pytest tests/unit -q -k layer` | `uv run mypy .` (exit 0; strict flags apply to the new `domain` modules) | repo root |
| AC14 | two tiers; one throwaway database per test; skip locally and fail in CI without a database; developer data untouched | unit files open no socket (guards, AC3 and AC10 rows). `isolation`: two tests in the same session see different database names, and a row one writes is absent from the other's database; a connection attempt to the session template is refused; at session end no database the session created remains (template included) and the configured database's user objects are unchanged. Policy by command evidence: with the variables unset, `uv run pytest tests/integration -q -rs` -> all skipped with the reason, exit 0; the same with `CI=true` -> non-zero exit, no skip. After a full local run, `docker compose exec -T postgres sh -c 'psql -X -At -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select count(*) from pg_database where datname like '"'"'ecpq\_test\_%'"'"'"'` prints `0` | unit, integration, command | pytest | Compose database for `isolation`; none for the skip commands | `uv run --env-file .env pytest tests/integration -q -k isolation`; `uv run pytest tests/integration -q -rs` (Git Bash: `CI=true uv run pytest tests/integration -q`; PowerShell: `$env:CI="true"; uv run pytest tests/integration -q`, then `Remove-Item Env:CI`) | `uv run --env-file .env pytest -q` (all tiers) | repo root |
| AC15 | CI runs the integration tests against `postgres:18`, none skipped | none new (workflow change) | CI | GitHub Actions | the `tests.yml` service and env | on the F3 pull request: `gh pr checks <number>`; `gh run view <run-id> --log` shows the service `postgres:18`, the integration test names passing, no `skipped` in the summary, and coverage rows for the three new `infrastructure` modules | `tests` and `feedback` both green | repo root |
| AC16 (compatibility) | everything still works; only the approved dependency added | none new (command checks) | unit, command | pytest, ruff, mypy, doctor, git, uv | `uv sync --locked` | `uv run pytest -q` (the 961 earlier tests pass; integration tests skipped without `--env-file`) | `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy .`; `uv run node .sdd/doctor/run-doctor.mjs` (`0 warned, 0 failed`); `uv run ec-procurement-quality --version`; `git diff main -- pyproject.toml` (only the dependency line and the marker); `uv lock --check`; `git diff main --stat -- compose.yaml .env.example .github/dependabot.yml docs/adr src/ec_procurement_quality/domain/raw_evidence.py src/ec_procurement_quality/domain/content_hash.py src/ec_procurement_quality/domain/source_response.py src/ec_procurement_quality/application/raw_evidence_store.py src/ec_procurement_quality/application/procurement_source.py src/ec_procurement_quality/infrastructure/local_disk_raw_evidence_store.py src/ec_procurement_quality/infrastructure/sercop_source.py` (empty against the base the F3 branch was cut from; the separate Dependabot change is not on the F3 branch); `git ls-files .env` (empty); `git diff --check`; `git grep -n -i -e datosabiertos -e compraspublicas -- tests` (no match) | repo root |
| AC17 (documentation) | docs describe what exists | none (inspection at audit) | manual | git | none | `git grep -n -i -e psycopg -e migration -- README.md AGENTS.md docs/architecture.md CHANGELOG.md` | by inspection: README says nothing calls the adapter and documents the leftover-database query; `docs/architecture.md` § Open questions still lists the audit events question; `CHANGELOG.md` lists the known limitations (unknown outcome after a connection lost during a commit, audit events not idempotent, triggers do not bind a superuser) | repo root |

## Revision log
- Revision 1 (2026-10-13): First draft, based on intent Revision 1.
- Revision 2 (2026-10-13): Based on intent Revision 2.
  - **Gate 1 decisions recorded.** The "open question" labels became "resolved question"; question 6 is option B (the executor writes the migration, the human reviews it line by line with each constraint and trigger explained; option A removed); question 2 is approved; question 10 is handled by a separate change covering `.github/dependabot.yml`, ADR 0006 and ADR 0007, which F3 does not touch (§ Consumers, § Other constraints, AC16 row).
  - **P1.** § Runner contract and § Adapter behavior now separate atomicity from the unknown outcome of a commit in flight; the F4 consumer rules say the error is not proof that nothing was written. AC11 gains the lock-wait test of a loss while the transaction is open, and the commit-in-flight case is documented as not tested, with the reason. The risk row is updated.
  - **P2, isolation.** § Binding constraints "Tests" pins one throwaway database per test (runner tests from `template0`; others from a migrated template that refuses connections, is copied only from the admin connection, and is dropped at session end), with the leftover check. This rests on the template probe in § Guidance consulted. The fixture suggestion and the AC14 row are updated.
  - **P2, JSON equality.** `same_json` is pinned in `domain` and the reason is recorded. `IngestionRun` and `AuditEvent` equality use it. `start_run` compares scopes with it, and `finish_run` and `IngestionRun` reject a plain `str` status. The other comparisons were checked and have no `bool`/`int` gap (stated in § Adapter behavior). The AC7, AC9 and AC10 rows gain the cases.
