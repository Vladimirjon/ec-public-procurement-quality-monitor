# Execution Plan: Ingest command (F4)

Revision: 5
Approval: Approved revision 5 by Vladimirjon on 2026-10-17 (the corrections F-1, F-2 and F-3 found during O1 to O5, including the F-3 read-back rule; no claim that F4 is implemented or tested). Revision 4 was approved by Vladimirjon on 2026-10-15 (gate 1: design, criteria and execution order)
Intent: [intent.md](intent.md) Revision 7 (the implementation findings F-1 to F-3 resolved on Revision 6; Revision 6 added the coverage condition of `last-page-reached` and the definitive confirmations of 2026-10-15 added to Revision 5; AC1 to AC25; Q1 to Q15 and findings 1 to 22 decided by the human on 2026-10-14; the plan's findings P-1 to P-5, the hierarchy test, the P-3 consequences and the validation of `last-page-reached` decided on 2026-10-15)

## Guidance consulted
- `specs/ingest-command/intent.md` Revision 6 (Revision 3 plus the decisions of 2026-10-15 on P-1 to P-5, the hierarchy test, the P-3 consequences, the validation of `last-page-reached` and its coverage condition), read in full, including the AC25 correction applied by the coordinator: `<T>` is a synthetic repository root holding its own copy of `migrations/`, and the default relative `--migrations-dir` is used.
- `AGENTS.md`: layer boundaries; no dependency, infrastructure, framework or service without approval; no secrets, `.env` contents or real SERCOP data anywhere; minimal synthetic fixtures; run verification after every change.
- ADRs:
  - 0001: modular monolith, ports and adapters, CLI over bounded batches.
  - 0002 and 0005: immutable raw storage and the store layout.
  - 0003: no distributed infrastructure.
  - 0004: toolchain; strict `mypy` in `domain`.
  - 0006: the caller owns retries.
  - 0007: `psycopg` only in `infrastructure`; migrations forward-only.
- `docs/architecture.md` (§ Processing model, § Open questions), `docs/glossary.md` (§ Ingestion execution), `docs/sources/sercop-observations.md`, `README.md`, `docs/learning/plan.md`:
  - § 4: F4 row;
  - § 5: D-09, `argparse`;
  - Days 19 to 21, including Day 19 "Implementa tú el caso de uso en application" and the Day 21 experiments (Ctrl+C and resume, repeat with no duplicates, corrupt a raw file).
- `harny-sync` lookup: `specs/current/_index.md`, `cli.md`, `persistence.md`, `raw-evidence.md`, `source-access.md`, `project-toolchain.md`. This plan contradicts none of them silently; the changes are listed in intent § Constraints "Current-truth notes" and in § Ownership below.
- Archived plans: `specs/archived/raw-evidence-store/execution-plan.md`, `specs/archived/sercop-source-adapter/execution-plan.md` (§ Consumers and migration, F4 rules) and `specs/archived/postgres-persistence/execution-plan.md` (§ Binding constraints "Tests", § Consumers "F4 (consumer rules)").
- Code read:
  - `src/ec_procurement_quality/interfaces/cli.py`: `main(argv) -> None`, which ends through `SystemExit`;
  - `application/` ports: `RawEvidenceStore`, `ProcurementSource`, `IngestionRepository`;
  - `domain/raw_evidence.py`: `validate_execution_id`, `validate_sequence`, `Observation`;
  - `domain/ingestion_audit.py`: `RunStatus`, `IngestionRun`, `AuditEvent`, `JsonValue`, `same_json`;
  - `domain/persistence_errors.py`: one `MigrationError` class for every runner failure;
  - `domain/source_response.py`;
  - `infrastructure/local_disk_raw_evidence_store.py`: `_observation_path` is `observations/<id>/<sequence>.json`, and `read_observation` checks the record against its path;
  - `infrastructure/postgres_ingestion_repository.py`: one transaction per operation, `_require_usable`, no reconnect;
  - `infrastructure/postgres_migrations.py`: `MIGRATION_LOCK_KEY`, and the fixed message `"another migration run holds the lock"`;
  - `infrastructure/postgres_settings.py` and `infrastructure/sercop_source.py`: `DEFAULT_BASE_URL`, the injectable `now`, `monotonic`, `sleep` and `transport`, and the one-thread docstring;
  - `migrations/0001_initial_schema.sql`;
  - `tests/unit/test_layers.py`;
  - `tests/unit/test_sercop_source.py`: the F2 socket guard is `autouse` and local to that file;
  - `tests/integration/conftest.py`: throwaway databases, `empty_database` and `migrated_database`, the admin connection, and skip or fail by policy.
- Plan evidence, checked on 2026-10-14 in `.venv`, not outcome evidence:
  - `argparse` with a required subparser turns `--bogus` into `the following arguments are required`, so the subcommand must be optional (intent § Constraints);
  - `psycopg` 3.3.6 `_conninfo_attempts._resolve_hostnames` calls `socket.getaddrinfo` in Python for a host that is not an IP address and skips it for `127.0.0.1`, while the connection itself is opened by `libpq`, not through Python's `socket`. A Python socket guard therefore blocks `httpx` but not `libpq`, and it must allow `getaddrinfo` for the configured database host (§ Binding constraints "Tests").
- The human's decisions of 2026-10-15 on P-1 to P-5, recorded in intent Revision 4 § Decisions on the execution-plan findings and in § Decisions below.
- Tests read for P-1 on 2026-10-15:
  - `tests/integration/test_postgres_migrations.py`: `test_runner_lock_held_elsewhere_fails_at_once_and_creates_nothing` is the PS-4 test (`pytest.raises(MigrationError)` and a `lock` message check); three other lock tests and the failure and integrity tests use `pytest.raises(MigrationError)`;
  - `tests/unit/test_postgres_migration_files.py`: the name and content checks use `pytest.raises(MigrationError)`;
  - `tests/unit/test_ingestion_audit.py`: `test_persistence_errors_are_direct_subclasses_of_persistence_error` lists the four direct subclasses and checks each one's `__bases__`.
  - No existing test counts the persistence errors (no `__subclasses__()`, no length check), and `tests/unit/test_layers.py` does not mention them.
- For Revision 5 (2026-10-17): `tasks.md` Revision 1 § Working state (findings F-1 to F-3), `docs/learning/journal.md` Day 19, `git diff main -- pyproject.toml` on `feat/ingest-command` (the two `[tool.mypy]` keys and their comment, nothing else), the read-back branch of P step 3 in `application/ingest_use_case.py` (it catches `EvidenceNotFoundError` and `OSError`), and `specs/current/raw-evidence.md` (N2) and `project-toolchain.md` (PT-5, PT-11).
- Baseline: `main` at `2e6edcd`, 1307 tests (1132 passed and 175 skipped without a database; all pass with `--env-file .env`), PT-6.

## Ownership
New modules:
- `src/ec_procurement_quality/domain/ingestion_catalogue.py`: the closed catalogues, the scope value, the execution id rule.
- `src/ec_procurement_quality/application/ingest_ports.py`: clock, execution id source, repository opener, reporter.
- `src/ec_procurement_quality/application/ingest_use_case.py`: requests, outcome and `run_ingest`, written by the human (🧑, Day 19).
- `src/ec_procurement_quality/infrastructure/system_clock.py`: the real clock and the real execution id source.
- `src/ec_procurement_quality/interfaces/ingest_command.py`: the composition root, the environment, the exit codes and the output.

Modified modules:
- `src/ec_procurement_quality/application/raw_evidence_store.py` and `infrastructure/local_disk_raw_evidence_store.py`: the F1 listing (Q14).
- `src/ec_procurement_quality/application/ingestion_repository.py` and `infrastructure/postgres_ingestion_repository.py`: the F3 listing of runs by status and the ingest exclusion (Q4).
- `src/ec_procurement_quality/interfaces/cli.py`: the `ingest` subparser and its delegation.
- `src/ec_procurement_quality/domain/persistence_errors.py`: the new `MigrationLockError(MigrationError)` (decision P-1).
- `src/ec_procurement_quality/infrastructure/postgres_migrations.py`: raises `MigrationLockError` at the one busy-lock branch (decision P-1).

Tests, all in new files:
- `tests/unit/ingest/` with its own `conftest.py`.
- `tests/unit/test_local_disk_raw_evidence_store_listing.py`.
- `tests/integration/ingest/` with its own `conftest.py`.
- `tests/unit/test_persistence_error_hierarchy.py` (new, decision P-1).
- One existing test file is edited, and only by one added assertion (intent AC20, decision P-1): `tests/integration/test_postgres_migrations.py`, in `test_runner_lock_held_elsewhere_fails_at_once_and_creates_nothing`. `tests/unit/test_ingestion_audit.py` is not edited: its hierarchy test checks only the four direct subclasses, stays true, and must not list `MigrationLockError`, which is not a direct subclass.

Documentation:
- `README.md`, `AGENTS.md` § Current commands, `docs/architecture.md`, `CHANGELOG.md`.
- `docs/learning/journal.md`, written by the human as a deliverable of the spec work (intent § Scope In).

Configuration: `pyproject.toml` gains only `explicit_package_bases = true` and `mypy_path = "src"` under `[tool.mypy]`, with their comment (decision F-1 of the human, 2026-10-16), so that `uv run mypy .` checks the several `conftest.py` files of the test folders; no dependency table changes.

Unchanged: `migrations/` (no new migration file, § Binding constraints "No schema change"), `uv.lock`, `compose.yaml`, `.env.example`, F2 modules and tests, ADRs, `docs/glossary.md`.

Affected `specs/current` capabilities, updated by `harny-sync` at archive:
- `cli`: new requirements for `ingest`, its exit codes and its output; the CLI-2 scenario's usage line gains the subcommand; Invariant 3 is answered.
- `persistence`: PS-7 and PS-13 modified (two port operations); a new requirement for the listing of runs and the exclusion; Invariant 8 retired; reservation N5 noted as safe under the exclusion; PS-4 modified (a busy lock raises `MigrationLockError`); PS-13 modified (six errors: `PersistenceError`, its four direct subclasses, and `MigrationLockError`, a subclass of `MigrationError`).
- `raw-evidence`: RE-12 modified (the listing); a new requirement for the listing; Invariant 7 modified (a listing exists; still no indexing, bulk verification or cleanup).
- `source-access`: no requirement changes. The F4 consumer rules are met, and the reservations R-7 and R-11 may be marked as handled by F4.
- `project-toolchain`: PT-6 and PT-10 counts; PT-3 unchanged; PT-5 keeps its rule, with the F-1 `[tool.mypy]` settings noted.
- A new capability `ingestion` (suggested prefix `IG-`) for the use case: page loop, write order, failure, interruption, reconciliation, resumption, catalogue.

## Binding constraints

### Layer placement (source: ADR 0001, `AGENTS.md`, PT-3, intent AC18)
| Layer | New or changed | May import |
|---|---|---|
| `domain` | `ingestion_catalogue.py` | standard library, `domain` (strict `mypy`) |
| `application` | `ingest_ports.py`, `ingest_use_case.py`; the two ports extended | standard library, `domain`, `application` |
| `infrastructure` | listing in `LocalDiskRawEvidenceStore`; listing and exclusion in `PostgresIngestionRepository`; `system_clock.py` | anything approved; only here `httpx` and `psycopg` |
| `interfaces` | `cli.py`, `ingest_command.py` | `application`, `domain`, `infrastructure`, the standard library; never `httpx` or `psycopg` |

No module under `src/ec_procurement_quality/application/` contains SQL (the upper-case keywords `SELECT `, `INSERT `, `UPDATE `, `DELETE `), a piece of the store layout (`objects/`, `observations/`, `.json`), or the words `advisory` or `pg_` (intent AC18). None does today (checked with `grep` on 2026-10-14; `list_observations` has no slash and is not a layout piece). `application` reaches the store only through `RawEvidenceStore` and the database only through `IngestionRepository` (intent AC12). No new file is added directly under `src/ec_procurement_quality/` (PT Invariant 3).

### Public names and signatures
These are fixed because the test-writer, the executor and the human (who writes the use case) write separate parts that import each other (F1 to F3 precedent). Every annotation is required. Below, `Mapping`, `Sequence` and `Callable` come from `collections.abc`, `datetime` is `datetime.datetime` and `Path` is `pathlib.Path`.

**`ec_procurement_quality.domain.ingestion_catalogue`** (strict `mypy`):
```python
class AuditEventType(enum.StrEnum):
    RUN_STARTED = "run-started"
    PAGE_COMPLETED = "page-completed"
    PAGE_FAILED = "page-failed"
    STORAGE_FAILED = "storage-failed"
    LAST_PAGE_REACHED = "last-page-reached"
    RUN_INTERRUPTED = "run-interrupted"
    UNEXPECTED_ERROR = "unexpected-error"
    OBSERVATION_RECONCILED = "observation-reconciled"
    RUN_CLOSED_BY_RECONCILIATION = "run-closed-by-reconciliation"
    RECONCILIATION_FAILED = "reconciliation-failed"


class PageFailure(enum.StrEnum):
    STATUS = "status"
    INCOMPLETE = "incomplete"
    TRANSPORT = "transport"


class EvidenceStoreName(enum.StrEnum):
    RAW_EVIDENCE = "raw-evidence"
    POSTGRESQL = "postgresql"


class ReconciliationProblem(enum.StrEnum):
    LOCAL_OBSERVATION_MISSING = "local-observation-missing"
    LOCAL_OBSERVATION_DIFFERENT = "local-observation-different"
    LOCAL_OBSERVATION_UNREADABLE = "local-observation-unreadable"
    OBJECT_MISSING = "object-missing"
    OBJECT_INTEGRITY = "object-integrity"
    SEQUENCE_GAP = "sequence-gap"
    POSTGRESQL_OBSERVATION_CONFLICT = "postgresql-observation-conflict"
    LOCAL_LISTING_FAILED = "local-listing-failed"


SCOPE_VERSION = 1
SCOPE_SOURCE = "sercop-search-ocds"
WINDOWS_RESERVED_NAMES: frozenset[str]


@dataclass(frozen=True, kw_only=True)
class IngestScope:
    base_url: str
    buyer: str
    year: int
    first_page: int
    last_page: int

    def to_json(self) -> dict[str, JsonValue]: ...

    @classmethod
    def from_json(cls, scope: Mapping[str, JsonValue]) -> "IngestScope": ...


def validate_ingest_execution_id(execution_id: str) -> str: ...
```
- `WINDOWS_RESERVED_NAMES` is `con`, `prn`, `aux`, `nul`, `com0` to `com9` and `lpt0` to `lpt9`, lowercase.
- `IngestScope` construction raises `ValueError` (naming the field, never its value) when:
  - `base_url` or `buyer` is not a non-empty `str`;
  - `year`, `first_page` or `last_page` is not an `int` (a `bool` is rejected) of at least 1;
  - `first_page > last_page`.
- `to_json()` returns exactly `{"scope_version": 1, "source": "sercop-search-ocds", "base_url", "buyer", "year", "first_page", "last_page"}` (intent AC13, Q6).
- `from_json` accepts only a mapping with exactly those seven keys, `scope_version` the `int` 1 and `source` that string, and raises `ValueError` otherwise. A resumption uses it to read its original's scope (AC24 "malformed").
- `validate_ingest_execution_id` returns the id when it matches `ingest-[0-9]{8}t[0-9]{6}z-[0-9a-f]{8}` (32 characters), passes F1's `validate_execution_id`, and is not in `WINDOWS_RESERVED_NAMES`; otherwise `ValueError`.
- `pages_left_to_request(scope: IngestScope, completed: frozenset[int], last_reached: int | None) -> tuple[int, ...]` returns, in increasing order, the pages of `[scope.first_page, scope.last_page]` that are not in `completed` and are not above `last_reached`. `last_reached` is the `page` of the chain's one valid `last-page-reached` event (§ State machine H, step 3), or `None` when the chain has none. An event that fails that validation is never passed here: it makes the chain malformed. § State machine H uses it to compute the resumption's pages and to validate every `first_page` (decision P-4).

**`ec_procurement_quality.domain.persistence_errors`** gains (decision P-1):
```python
class MigrationLockError(MigrationError):
    """Another migration run holds the migration lock."""
```
- It is the only subclass of `MigrationError`; the four direct subclasses of `PersistenceError` are unchanged. There are six errors in all.
- `apply_migrations` raises it exclusively at the branch where `pg_try_advisory_lock(MIGRATION_LOCK_KEY)` returned false, with exactly the existing message `another migration run holds the lock` (fixed text, nothing from the driver; PS-12 holds).
- Every other refusal stays a plain `MigrationError`:
  - the directory, file and history checks (PS-3);
  - a failed file (PS-2);
  - the lock that cannot be taken because the server refused the statement;
  - the bookkeeping table that cannot be created or read.
- `PersistenceConnectionError` cases are unchanged.

**`ec_procurement_quality.application.ingest_ports`**:
```python
class Clock(Protocol):
    def now(self) -> datetime: ...


class ExecutionIdSource(Protocol):
    def new_execution_id(self, started_at: datetime) -> str: ...


class ClosableIngestionRepository(IngestionRepository, Protocol):
    def close(self) -> None: ...


class RepositoryOpener(Protocol):
    def __call__(self) -> ClosableIngestionRepository: ...


class IngestReporter(Protocol):
    def run_started(self, execution_id: str) -> None: ...

    def progress(self, message: str) -> None: ...
```
- `Clock.now()` returns a `datetime` with a UTC offset.
- `RepositoryOpener()` raises `PersistenceConnectionError` when the database cannot be reached.
- The use case passes `IngestReporter.progress` only text it built from fixed words, integers, content hashes, execution ids and `str()` of a project error (F1, F2 and F3 messages are fixed text). For any other exception it passes only `type(error).__name__`.

**`ec_procurement_quality.application.ingest_use_case`** (🧑 the human writes `run_ingest`; names and types pinned here):
```python
@dataclass(frozen=True, kw_only=True)
class IngestRequest:
    scope: IngestScope


@dataclass(frozen=True, kw_only=True)
class ResumeRequest:
    execution_id: str


class IngestEnd(enum.Enum):
    SUCCEEDED = enum.auto()
    RUN_FAILED = enum.auto()
    NOT_STARTED = enum.auto()
    INVALID_TARGET = enum.auto()
    INTERRUPTED = enum.auto()


@dataclass(frozen=True, kw_only=True)
class IngestOutcome:
    end: IngestEnd
    execution_id: str | None
    run_status: RunStatus | None
    message: str


def run_ingest(
    request: IngestRequest | ResumeRequest,
    *,
    source: ProcurementSource,
    store: RawEvidenceStore,
    open_repository: RepositoryOpener,
    clock: Clock,
    execution_ids: ExecutionIdSource,
    reporter: IngestReporter,
) -> IngestOutcome: ...
```
- `run_ingest` opens the repository itself through `open_repository`, at most twice per call (the second time only under § State machine C), and closes every repository it opened before returning or raising.
- `execution_id` and `run_status` describe the run this call created, or are `None` when none was created.
- `RUN_FAILED` covers a created run that is `failed` or left `running`.
- `NOT_STARTED` covers an operational or integrity failure with no run created.
- `INVALID_TARGET` covers a `--resume` target that names no run or is `succeeded`.
- `INTERRUPTED` covers Ctrl+C, with or without a run.
- `run_ingest` returns an outcome for every ending except a `KeyboardInterrupt` raised during its own interruption cleanup and `SystemExit`, which propagate (Q11).

**`ec_procurement_quality.application.raw_evidence_store.RawEvidenceStore`** gains (Q14, intent AC22):
```python
def list_observation_sequences(self, execution_id: str) -> tuple[int, ...]: ...
```

**`ec_procurement_quality.application.ingestion_repository.IngestionRepository`** gains (Q4, intent AC23):
```python
def list_runs(self, status: RunStatus) -> tuple[IngestionRun, ...]: ...


def try_acquire_ingest_exclusion(self) -> bool: ...
```
The eight existing operations keep their exact signatures and behavior (PS-7 to PS-13).

**`ec_procurement_quality.infrastructure.postgres_ingestion_repository`** gains `INGEST_EXCLUSION_KEY: int`, a constant in the signed 64-bit range different from `MIGRATION_LOCK_KEY`. Suggested value: the ASCII bytes of `ecpqingx`, `0x6563_7071_696E_6778`. Integration tests use it to hold the exclusion from outside. It never appears in a message.

**`ec_procurement_quality.infrastructure.system_clock`**: `SystemClock()` with `now()` returning `datetime.now().astimezone()`, and `RandomExecutionIdSource()` with `new_execution_id(started_at)`. The id is `ingest-` + the UTC form of `started_at` as `%Y%m%dt%H%M%Sz` + `-` + `secrets.token_hex(4)`.

**`ec_procurement_quality.interfaces.ingest_command`**:
```python
class ClosableSource(ProcurementSource, Protocol):
    def close(self) -> None: ...


@dataclass(frozen=True, kw_only=True)
class IngestWiring:
    base_url: str
    make_source: Callable[[Callable[[], datetime]], ClosableSource]
    make_store: Callable[[Path], RawEvidenceStore]
    make_repository: Callable[[PostgresSettings], ClosableIngestionRepository]
    migrate: Callable[[PostgresSettings, Path], tuple[str, ...]]
    clock: Clock
    execution_ids: ExecutionIdSource


def default_wiring() -> IngestWiring: ...


def run_ingest_command(
    arguments: argparse.Namespace,
    *,
    environ: Mapping[str, str],
    wiring: IngestWiring,
    stdout: TextIO,
    stderr: TextIO,
) -> int: ...
```
- `default_wiring()` uses `DEFAULT_BASE_URL` and `SercopSource(base_url=..., now=...)` with the F2 defaults, `LocalDiskRawEvidenceStore`, `PostgresIngestionRepository`, `apply_migrations`, `SystemClock()` and `RandomExecutionIdSource()`.
- `run_ingest_command` returns the exit code.
- Tests inject a wiring. The simulated source is a `make_source` that builds `SercopSource` with an `httpx.MockTransport`, `min_interval=0`, `cooldown=0` and a no-op `sleep`. The test store is a `make_store` that ignores the path it is given and returns a store on `tmp_path`.
- `interfaces` itself never imports `httpx`.

**`ec_procurement_quality.interfaces.cli`**:
- `main(argv: list[str] | None = None) -> None` keeps CLI-3.
- `build_parser()` gains an optional subparser `ingest`: `add_subparsers(dest="command")` without `required=True`.
- For `ingest`, `main` calls `run_ingest_command(..., environ=os.environ, wiring=default_wiring(), stdout=sys.stdout, stderr=sys.stderr)` and ends with `raise SystemExit(code)`, so every path ends through `SystemExit` (CLI-3).
- A bare command calls `parser.print_usage(sys.stderr)` and raises `SystemExit(2)`.
- `--version` and `--bogus` are unchanged (CLI-1, CLI-2).

### CLI arguments (intent Q9, AC14)
- Fresh run: `ingest --year <int> --buyer <text> --last-page <int> [--first-page <int>] [--migrations-dir <path>]`. `--first-page` defaults to 1, `--migrations-dir` to `migrations`.
- Resumption: `ingest --resume <execution id> [--migrations-dir <path>]`.
- `argparse` types parse integers. Every rule `argparse` cannot express ends with `parser.error(...)`, which is exit 2 with the usage line, on stderr, before anything else happens:
  - a missing `--year`, `--buyer` or `--last-page` on a fresh run;
  - `--resume` together with any of `--year`, `--buyer`, `--first-page`, `--last-page`;
  - an `IngestScope` rule;
  - a `--resume` id outside the F1 pattern.
- There is no `--raw-root` option and no base-URL option (Q8). `argparse` reports an unknown option as `unrecognized arguments` (exit 2).

### Configuration (intent Q8, AC14, AC25)
- `run_ingest_command` reads only `environ`; nothing reads `.env`.
  - Required: `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`.
  - Optional: `POSTGRES_HOST` (absent -> `127.0.0.1`) and `POSTGRES_PORT` (absent -> `5432`; present but not a decimal integer -> exit 2).
  - `PostgresSettings` validates the rest (a port outside 1 to 65535 -> `ValueError` -> exit 2).
  - Messages name the variable or field and never the value.
- Paths are resolved once, at the start of `run_ingest_command`, before anything else is touched:
  - `store_root = Path.cwd() / "data" / "raw"`;
  - the migrations directory is `Path.cwd() / <--migrations-dir>` when relative, or as given when absolute.
  - Both are absolute from then on; nothing later reads the current directory (intent AC25).
  - There is no detection of the repository root (finding 21).

### Order of an invocation (intent Q9; exit code of each step's failure in brackets)
1. Arguments (2), environment (2), absolute paths.
2. Keep the `httpcore` logger above `DEBUG`: if `logging.getLogger("httpcore").getEffectiveLevel() <= logging.DEBUG`, set that logger's own level to `logging.WARNING` and restore it when the invocation ends. No handler is added and nothing else is configured (R-7, intent AC15).
3. `wiring.migrate(settings, migrations_dir)`, which names the applied files on stderr. The outcomes:
   - `MigrationLockError` (the migration lock held by another session) -> 1;
   - any other `MigrationError` (a directory, file or history mismatch) -> 2. `interfaces` catches `MigrationLockError` before `MigrationError`;
   - `PersistenceConnectionError` or `PersistenceError` -> 1.
4. `make_source(clock.now)` and `make_store(store_root)`, then `run_ingest(...)` with `open_repository = lambda: wiring.make_repository(settings)`.
5. Inside `run_ingest`:
   1. Open the repository (`NOT_STARTED`).
   2. `try_acquire_ingest_exclusion()`; `False` -> `NOT_STARTED`, nothing written.
   3. For `--resume`, the target check of § State machine T (`INVALID_TARGET`).
   4. Reconciliation of every `running` run (§ State machine R; `NOT_STARTED` on a problem).
   5. For `--resume`, the chain checks (§ State machine H; `NOT_STARTED`).
   6. `started_at = clock.now()`, then a new id (§ State machine I; `NOT_STARTED`).
   7. `start_run`, then `reporter.run_started(id)`, then `run-started`.
   8. The page loop (§ State machine P).
   9. `finish_run`.
6. Map the outcome to an exit code and write stdout (§ Output).
7. Close the source in a `finally`.

### Exit codes (intent Q9; finding 22)
| Code | When |
|---|---|
| 0 | `IngestEnd.SUCCEEDED`: the run is `succeeded`, including a run confirmed `succeeded` by the exact repeat of its final `finish_run` after a lost connection (§ State machine C, decision P-2) |
| 1 | `RUN_FAILED`: a run was created and is `failed` or left `running`; this covers every connection loss except the P-2 case. `NOT_STARTED`: no run created, because the database was unreachable, the migration lock was busy (`MigrationLockError`), the exclusion was held, reconciliation failed, the chain was cyclic, malformed or contradictory, or no free id was drawn. Any exception escaping `run_ingest` other than `KeyboardInterrupt` and `SystemExit` |
| 2 | Usage, argument, environment or migrations-history errors (steps 1 and 3); `INVALID_TARGET` (a well-formed id that names no run, a `succeeded` run) |
| 130 | `INTERRUPTED`, or a `KeyboardInterrupt` that escapes `run_ingest` or interrupts steps 1 to 4 |

### Output (intent AC15)
- stdout:
  - exactly one line `<execution_id> <status>` when the outcome names a run, whatever the exit code, where `<status>` is the outcome's `run_status` value (`succeeded`, `failed` or `running`);
  - `<status>` is the last status this process confirmed for its run. `running` means that closing was not confirmed, not a claim that PostgreSQL still holds `running` (decision P-5);
  - nothing otherwise;
  - when a `KeyboardInterrupt` escapes `run_ingest` after `reporter.run_started(id)` was called, the line is `<id> running`, even if a `finish_run` may have committed unseen (decision P-5);
  - after the P-2 case of § State machine C, the line is `<id> succeeded` with exit 0.
- stderr:
  - `argparse` usage and errors;
  - the applied migration names;
  - `IngestReporter.progress` lines;
  - one final line with `IngestOutcome.message`;
  - for an exception that escapes, only its class name.
- Never on stderr or stdout: a traceback, an exception chain or `__context__` (R-6, raw-evidence N3), a URL, a header value, body bytes, a setting value or the password.
- The progress format is free; it names pages, sequences, statuses and content hashes only.

### Audit details (intent Q6, AC13; closed)
| Event type | Detail keys and types | Appended to |
|---|---|---|
| `run-started` | `resumes`: execution id `str` or `None`; `first_page`: `int` | the new run, right after `start_run` |
| `page-completed` | `page`: `int`; `sequence`: `int`; `content_hash`: 64-hex `str` | the run, after the page's observation is in both stores |
| `page-failed` | `page`: `int`; `sequence`: `int` or `None`; `failure`: `PageFailure`; `status`: `int` or `None` | the run |
| `storage-failed` | `page`: `int`; `sequence`: `int` or `None`; `store`: `EvidenceStoreName` | the run |
| `last-page-reached` | `page`: `int`; `pages`: `int` | the run |
| `run-interrupted` | `page`: `int` | the run |
| `unexpected-error` | `page`: `int`; `error_type`: class name `str` | the run |
| `observation-reconciled` | `sequence`: `int` | the run being reconciled |
| `run-closed-by-reconciliation` | `reconciled_observations`: `int` | the run being reconciled |
| `reconciliation-failed` | `sequence`: `int` or `None`; `problem`: `ReconciliationProblem` | the run being reconciled |

- Enum values are stored as their `str` value.
- `page` is the page being processed, or the first page the run would request when none was requested yet.
- `failure` comes from the error class: `SourceStatusError` -> `status` (with the response status); `IncompleteResponseError` -> `incomplete` (status 200); `SourceTransportError` -> `transport` (the partial response's status, or `None`).
- No detail holds a URL, a header value, body bytes, a setting or exception text.

### State machine P: one page (intent AC1 to AC6, AC17)
`next_sequence` starts at 1. Each page `p`, from the run's first page to request up to `scope.last_page`:

1. **Request.** `outcome = source.search_page(year=..., buyer=..., page=p)`. Catch `SourceError` only, and leave the `except` block before anything else (F2 consumer rules). `response = result.response` or `error.response`.
2. **No response** (`SourceTransportError` with `response is None`) -> `page-failed` (sequence `None`, `transport`, status `None`) -> step 7. No sequence is used (intent AC5).
3. **Store locally.** `observation = store.store(execution_id=..., sequence=next_sequence, **fields of response)`:
   - `OSError` or `EvidenceIntegrityError` -> ask `store.read_observation(id, next_sequence)`;
     - found -> `record_observation` of it (step 4, errors as there), then `storage-failed` (`raw-evidence`, sequence) -> step 7;
     - the read-back itself raises `EvidenceNotFoundError`, `OSError` or `EvidenceIntegrityError` -> treat the observation as not recorded: `storage-failed` (`raw-evidence`, page, sequence) -> step 7 (raw-evidence N2, intent AC6 a, b and d). The use case cannot tell whether a file was published and cannot record an observation it cannot read. This is not a claim that nothing was written. Nothing is lost: a resumption requests that page again, and an unreadable or orphan file counts for nothing (RE-9, intent AC9). For example, a regular file at `<root>/observations` makes the read-back raise `NotADirectoryError` (an `OSError`) on Linux and `EvidenceNotFoundError` on Windows; both end here.
     - `KeyboardInterrupt`, `SystemExit` and `MemoryError` from the read-back are not caught by this rule; they keep the handling of § State machine K (SA-11, Q11).
   - Once `store` returns, `next_sequence += 1`.
4. **Record in PostgreSQL.** `record_observation(observation)`:
   - `PersistenceConnectionError` -> § State machine C with this operation pending;
   - any other `PersistenceError` -> `storage-failed` (`postgresql`, sequence) -> step 7.
5. **Decide.**
   - Error with a response -> `page-failed` (sequence, failure, status) -> step 7.
   - Result -> `page-completed` (page, sequence, content hash).
   - Then, if `p >= result.pages` -> `last-page-reached` (page `p`, `result.pages`) and finish `succeeded` (step 6). There is no condition on `scope.last_page` (decision P-3, intent AC3). The order is binding, and § State machine H validates against it: `page-completed` for `p`, then `last-page-reached` for the same `p`, then `finish_run`. This covers:
     - a beyond-the-last-page result (`is_beyond_last_page`, `p > pages`);
     - the reported last page itself (`p == pages`), also when it equals `scope.last_page`;
     - `pages` 0 with scope 1 to 1.

     No further request is sent, so AC17 (at most one request per page per run) is unaffected.
   - Otherwise (`p < result.pages`) go to the next page; after `scope.last_page`, step 6.
6. **End of range.** Once every page has been processed, `finish_run(SUCCEEDED, clock.now())`, keeping that `finished_at` value for any repeat.
7. **Failure path.** `finish_run(FAILED, clock.now())`, keeping that value, then `RUN_FAILED`. No further request is sent (no retries, Q12).

Every `append_audit_event` and `finish_run` above follows § State machine C on `PersistenceConnectionError`.

### State machine C: after `PersistenceConnectionError` (intent AC8, Q3; PS-11, persistence Invariant 7)
Before the new run exists (reconciliation, chain checks, id draw), no new connection is opened: `NOT_STARTED`, exit 1.

From `start_run` on, with pending operation `X` and its exact arguments kept:
1. Close the lost repository quietly. If this call already opened its second repository -> stop: the run is left `running`, `RUN_FAILED` with `run_status=RUNNING`.
2. Open the second repository through `open_repository()`. A failure -> left `running`.
3. `try_acquire_ingest_exclusion()`. `False` or an error -> close it; the run is not touched (no event, no `finish_run`); left `running`.
4. Resolve `X`:

   | `X` | Safe to repeat | Resolution |
   |---|---|---|
   | `start_run`, `record_observation`, `finish_run` | yes | repeat with the same values (same scope and `started_at`; same `Observation`; same status and `finished_at`) |
   | `read_run`, `read_observation`, `list_*` | yes (reads) | repeat |
   | `append_audit_event(type, detail, occurred_at)` | **no** | `list_audit_events(id)`; if an event with the same type, a `same_json` detail and the same `occurred_at` instant exists, treat it as stored; otherwise append once |

5. Continue the path that was interrupted:
   - on the normal path (P steps 1 to 6, or the opening `start_run` and `run-started`), append `storage-failed` (`postgresql`, page, sequence or `None`), then `finish_run(FAILED)`;
   - on a failure path, complete that path.
   - Exception (decision P-2, intent AC8): if `X` was the final `finish_run(SUCCEEDED)`, it is repeated with the same `finished_at`. No `storage-failed` is appended and no `finish_run(FAILED)` is attempted.
     - When the repeat returns the run with status `succeeded` and that `finished_at`, the run is **confirmed** `succeeded`: `SUCCEEDED`, exit 0. This holds whether the first attempt had committed or not: F3 returns the stored run for a repeat with the same status and instant, finishes a still-`running` run, and raises `PersistenceIntegrityError` for anything else (PS-7).
     - Confirmation is that successful repeat only. A separate `read_run` is not used: it would add a second path that still needs the repeat when the run is `running`.
     - A `PersistenceIntegrityError` from the repeat, which cannot happen under the exclusion, means `RUN_FAILED` with `run_status` from the stored run (exit 1).
     - If step 2 or 3 failed, the repeat is never made: left `running`, exit 1.
6. Any further `PersistenceConnectionError` -> left `running`; no third connection.

`started_at`, `finished_at` and `occurred_at` are read from the clock once and reused for every repeat, so that "exactly the same values" holds.

### State machine K: interruption and unexpected exceptions (intent AC7, AC15, Q11; best effort)
- `KeyboardInterrupt` raised inside the run:
  - if the interruption came after `store` was called for sequence `s` and before `record_observation` returned, ask `store.read_observation(id, s)` and record a found observation;
  - append `run-interrupted` (page);
  - `finish_run(FAILED)`;
  - return `INTERRUPTED`.
  - The cleanup opens no new connection. A `PersistenceError` stops the cleanup and returns `INTERRUPTED` with `run_status=RUNNING`. A second `KeyboardInterrupt` propagates.
  - Before `start_run` returned, there is nothing to clean: `INTERRUPTED` with no run. If `start_run` committed unseen, AC10 closes the run later.
- Any other `Exception` that is not a project error (a synthetic transport defect, `MemoryError`), raised inside the run:
  - append `unexpected-error` (page, class name);
  - `finish_run(FAILED)`;
  - return `RUN_FAILED`, best effort in the same way.
- `SystemExit` is never caught.

### State machine T: resumption target (intent AC9, AC14; finding 22)
`read_run(target)` gives one of:
- `PersistenceNotFoundError` -> `INVALID_TARGET`;
- `SUCCEEDED` -> `INVALID_TARGET`;
- `RUNNING` or `FAILED` -> continue.

Nothing is written in this step.

### State machine R: reconciliation (intent AC10, Q4, Q14)
For each run `X` in `list_runs(RUNNING)` (in its order), while the exclusion is held:
1. `local = store.list_observation_sequences(X)`; `EvidenceIntegrityError` or `OSError` -> problem `local-listing-failed` (sequence `None`).
2. `pg = {o.sequence: o for o in repository.list_observations(X)}`.
3. For each sequence in `sorted(set(local) | set(pg))`, the first problem found ends the step:
   - in `pg` but not `local` -> `local-observation-missing`;
   - `store.read_observation(X, s)` raises `EvidenceIntegrityError` -> `local-observation-unreadable`;
   - in `pg` and different from it -> `local-observation-different`;
   - `store.read_content(o.content_hash)` raises `EvidenceNotFoundError` -> `object-missing`; `EvidenceIntegrityError` -> `object-integrity`.
4. After every listed sequence is verified, the union must be exactly `1..max`; the smallest missing number (or a `0`) -> `sequence-gap` with that sequence. A later observation is verified before the gap is reported (intent AC10).
5. For each local-only sequence, in order: `record_observation(o)`; `PersistenceIntegrityError` -> `postgresql-observation-conflict`; then `observation-reconciled` (sequence).
6. `run-closed-by-reconciliation` (count of step 5), then `finish_run(X, FAILED, clock.now())`.

On a problem: `reconciliation-failed` (sequence, problem), `finish_run(X, FAILED)`, `NOT_STARTED`. Runs not yet examined stay `running` for the next invocation. Orphan objects are never looked for. A `PersistenceConnectionError` here -> `NOT_STARTED`, with no new connection.

### State machine H: resumption chain (intent AC9, AC24, Q13, Q14)
1. Starting at the target, follow `run-started.resumes` to a run whose `resumes` is `None`. For each run:
   - not found -> malformed;
   - already visited -> cyclic;
   - not exactly one `run-started` event, or its detail not exactly `{"resumes": str | None, "first_page": int >= 1}` (a `bool` rejected, `resumes` passing `validate_execution_id`) -> malformed;
   - scope not readable by `IngestScope.from_json`, or not `same_json` to the target's scope -> contradictory;
   - a run other than the target that is `succeeded` or `running` -> contradictory.
2. For every `page-completed` event in the chain, the detail must have exactly `page`, `sequence` and `content_hash`, with the page inside the scope range. That run's observation for that sequence must have status 200 and that content hash both in PostgreSQL (`read_observation`) and in the store (`read_observation`); otherwise -> contradictory.
3. **Validation of `last-page-reached`** (required by the human on 2026-10-15, intent AC24). Event order is the order `list_audit_events` returns (by `event_id`). Before any such event is used as a limit, every one in the chain must pass all of these, or the chain is malformed:
   - its detail has exactly the keys `page` and `pages`, each an `int` that is not a `bool` (floats cannot be stored, PS-10);
   - `scope.first_page <= page <= scope.last_page` (the chain shares one scope, step 1), `pages >= 0` and `page >= pages`;
   - it is the only `last-page-reached` event of its run, and the only one in the whole chain. Two events, in one run or in two, are rejected rather than ranked: no precedence rule exists (confirmed by the human on 2026-10-15), and the consequence below shows none is needed;
   - the same run holds a `page-completed` event for the same `page`, earlier in its event order, that passed step 2. This is the order State machine P writes (P step 5);
   - no `page-completed` and no `page-failed` event of that run comes after it in its event order. Other events may follow it: `run-interrupted`, `unexpected-error`, `storage-failed` (an interrupted or failed close; confirmed by the human on 2026-10-15), and the reconciliation events;
   - **coverage** (required by the human on 2026-10-15): at the point where the event for page `p` is reached, the set `covered` contains every page from `scope.first_page` to `p`. `scope` is the one scope the whole chain shares (step 1, `same_json`), not a run's `run-started.first_page`.
     - `covered` is built in one deterministic walk: runs from the oldest (`resumes` `None`) to the resumed target, and within each run its events in `list_audit_events` order.
     - Each `page-completed` that passed step 2 adds its page. Step 2 is the existing definition of a valid `page-completed`: a page inside `[scope.first_page, scope.last_page]` and the sequence of a `200` observation present in both stores with the same content hash (intent AC1, AC5, Q14).
     - A `page-completed` for a page below `scope.first_page` or above `scope.last_page` never reaches `covered`: step 2 already makes the chain malformed.
     - Any page of `[scope.first_page, p]` missing from `covered` -> malformed.

   **Consequence** (used by steps 4 and 5): after a valid event for page `p`, every page of `[scope.first_page, p]` is in `covered` and no page above `p` is left to request, so nothing is pending. Step 5 then forces every later run of the chain to be a sentinel run (`first_page = last_page + 1`, no page events). A sentinel run holds no `page-completed`, so it cannot hold the preceding `page-completed` that a second valid event needs; and a second event earlier in the chain would make the run that wrote this one a sentinel run too. So two events are never both valid, and a second one is always malformed.

   The event that passes is *the chain's valid `last-page-reached`*; its `page` is the `last_reached` of `pages_left_to_request`. An event that fails never limits anything: the resumption ends `NOT_STARTED` (exit 1) before any request.

   Interaction with reconciliation (§ State machine R): the order is fixed. R runs for every `running` run (invocation step 5.4) before this step (5.5). R reads observations only, never audit events, and appends only `observation-reconciled`, `run-closed-by-reconciliation` or `reconciliation-failed`, none of which is a page event. In particular, R never appends a `page-completed` (Q14: completeness is never decided from stored bytes), so `covered` holds only the `page-completed` events the runs wrote themselves. A run closed by R is validated here like any other, and R can neither create nor repair a `last-page-reached`.

   Interaction with the sentinel (P-4, step 5): a run whose `first_page` is `last_page + 1` holds no page events, so it adds nothing to `covered` and cannot hold a `last-page-reached`. Its own `first_page` is accepted only when step 4, applied to the chain before it, finds nothing left; a valid event earlier in the chain is one way that happens.
4. *Left to request*: a page of `[first_page, last_page]` that no run in the chain completed and that is not above the `page` of the chain's valid `last-page-reached` (step 3; intent AC3 across a chain).
   - The new run requests, in increasing order, every page left to request.
   - Its `run-started` gets `resumes` = target and `first_page` = the smallest page left to request.
   - When none is left, `first_page` is `last_page + 1` (decision P-4): a sentinel valid only for that case. The run then requests nothing and finishes `succeeded`.
5. Validation of every `first_page` already in the chain (decision P-4, intent AC24), applied to each run in step 1, after step 3:
   - a run with `resumes` `None` must have `first_page == scope.first_page`;
   - a run with `resumes` = R must have `first_page` equal to what step 4 computes from the chain that starts at R. That is the smallest page left to request after R's chain, counting R's chain's valid `last-page-reached` if any, or `last_page + 1` exactly when none was left.
   - Any other value is malformed, inside the range or out of it (for example `0`, `last_page + 2`, or `last_page + 1` while a page was still left).
   - A run whose `first_page` is `last_page + 1` must hold no `page-completed` and no `page-failed` event; otherwise it is malformed.

   The same domain function both computes and validates, so the check is pure: `domain/ingestion_catalogue.py` gains `pages_left_to_request(scope: IngestScope, completed: frozenset[int], last_reached: int | None) -> tuple[int, ...]`.

Any failure -> `NOT_STARTED`, with a fixed message naming the execution id; nothing is appended to any run (Q5; reconciliation events already written by R stay).

### State machine I: new execution id (intent AC12, Q7)
Up to three draws:
- `id = execution_ids.new_execution_id(started_at)`;
- `validate_ingest_execution_id(id)` (`ValueError` -> `NOT_STARTED`);
- `read_run(id)` must raise `PersistenceNotFoundError`;
- `store.list_observation_sequences(id)` must be `()`.

After three taken ids -> `NOT_STARTED`. The check and `start_run` happen under the exclusion. Sequences start at 1, with no gaps (P step 3).

### F1 port extension: `list_observation_sequences` (intent AC22, Q14)
- Returns the sequence numbers of the files `observations/<execution_id>/<n>.json` under the root, as a sorted tuple, where `<n>` is the canonical decimal form of a non-negative integer (no sign, no leading zero except `0` itself). It does not stop at a gap.
- `ValueError` for an id that fails `validate_execution_id`, before any file system access.
- `()` when `observations/<execution_id>` does not exist; nothing is created.
- `EvidenceIntegrityError` naming the execution, and no content, for:
  - an entry of that directory that is not a regular file named `<n>.json` (`x.json`, `01.json`, a subdirectory);
  - a non-directory at that path.
- `OSError` from listing propagates unwrapped (RE-7).
- It reads no file contents, follows the existing layout only, never lists `tmp/` or `objects/`, and writes, renames or deletes nothing.
- Unchanged guarantees: RE-1 to RE-11, write-once publication, no deletion, integrity on read (RE-7, RE-8, RE-10), and `store`, `read_content` and `read_observation` byte for byte.

### F3 port extension: `list_runs` and the ingest exclusion (intent AC23, Q4)
- `list_runs(status)`:
  - `ValueError` before any SQL when `status` is not a `RunStatus`;
  - otherwise one read transaction, ordered by `started_at` then `execution_id`, `()` when there is none;
  - rows are mapped with the existing `_run_from_row`;
  - errors as PS-11 and PS-12.
- `try_acquire_ingest_exclusion()`:
  - a session-level `pg_try_advisory_lock(INGEST_EXCLUSION_KEY)` on the repository's own connection (never the `_xact_` form, never the waiting `pg_advisory_lock`), committed as one operation; it writes no row;
  - `True` when acquired or already held by this repository (a flag prevents a second, stacked acquisition), `False` when another session holds it;
  - held until `close()` or the end of the session, with no release operation;
  - a lost connection -> `PersistenceConnectionError`, and a call after `close()` -> `RuntimeError`, both as PS-11;
  - independent of `MIGRATION_LOCK_KEY` (PS-4);
  - the key, the SQL and the words of the PostgreSQL mechanism never appear in a message, `repr` or `args` (PS-12).
- Unchanged: the eight existing operations, their transactions, their errors, and the "one thread at a time" docstring.

### No schema change
F4 adds no migration file: `migrations/` keeps `0001_initial_schema.sql` only (intent AC20).
- The exclusion is session state of PostgreSQL, not schema.
- `list_runs` reads existing columns. The runs table is small for a bounded batch CLI, so no index on `status` is added; a later migration can add one if it is ever measured as needed.
- The catalogue is enforced by the use case and the domain enums, not by a `CHECK` on `event_type`, which would need a new migration and make the catalogue a schema change.

### Port types keep satisfying their adapters
`LocalDiskRawEvidenceStore` implements `list_observation_sequences`, and `PostgresIngestionRepository` implements `list_runs` and `try_acquire_ingest_exclusion`, in the same change that extends each port. So the existing annotated assignments keep passing `mypy` unchanged:
- `tests/unit/test_local_disk_raw_evidence_store.py`: `LocalDiskRawEvidenceStore` assigned to `RawEvidenceStore`;
- the F3 `satisfies_port` test: `PostgresIngestionRepository` assigned to `IngestionRepository`.

No other class implements either protocol today (checked with `grep` on 2026-10-14). The in-memory doubles in `tests/unit/ingest/` implement the extended ports from the start.

### Tests
- **Tiers.** Unit tests (`tests/unit/`) use in-memory doubles, or a `tmp_path` store for F1, and open no socket. Integration tests (`tests/integration/`, marker `integration`) use throwaway databases exactly as PT-13 (`migrated_database`, `empty_database`, the admin connection), test stores on `tmp_path`, and skip or fail by policy. CLI tests call `run_ingest_command` with an injected wiring, or `main([...])` with `default_wiring` replaced through `monkeypatch`.
- **Network guard.**
  - `tests/unit/ingest/conftest.py` holds an `autouse` guard like F2's (it patches `socket.socket.connect`, `connect_ex`, `socket.create_connection` and `socket.getaddrinfo`).
  - `tests/integration/ingest/conftest.py` holds the same guard, except that `getaddrinfo` is allowed for the configured `POSTGRES_HOST` only. `libpq` opens its own sockets outside Python (§ Guidance consulted), so PostgreSQL works while any `httpx` attempt fails.
  - F2's guard and file are not touched.
  - Source URLs use `https://source.invalid/PLATAFORMA`.
- **No real `data/raw/`.**
  - Every test store lives on `tmp_path`.
  - AC25 uses a synthetic repository root `<T>` under `tmp_path`, holding a copy of the repository's `migrations/` files, entered with `monkeypatch.chdir`.
  - A session fixture in `tests/integration/ingest/conftest.py` records the names, sizes and modification times under the repository's real `data/raw/` at session start and asserts that they are unchanged at session end.
- **Fault-injection seams**, all in test code:

  | Seam | Supplied by | Used for |
  |---|---|---|
  | `KeyboardInterrupt`, `MemoryError` or a synthetic exception while page `p` is requested | the `MockTransport` handler (SA-11: propagates unchanged) or a `FakeSource` double | AC7, AC15 |
  | the store fails after publication (`OSError` after the real `store` returned) | `PublishThenFailStore`, wrapping the in-memory or the real store | AC6 (b) |
  | a regular file at `<root>/observations` | the real store on `tmp_path` | AC6 (a) |
  | the read-back fails after a failed `store` (`OSError` or `EvidenceIntegrityError` from `read_observation`) | a store double whose `store` raises `OSError` and whose `read_observation` then raises | AC6 (d) |
  | an interrupt after the local store, before PostgreSQL | a store wrapper raising `KeyboardInterrupt` after delegating | AC7 |
  | a second interrupt during cleanup | a repository wrapper raising `KeyboardInterrupt` on the `run-interrupted` append | AC7 |
  | commit-then-raise, or raise-before-commit, of a chosen operation | `FlakyRepository`, wrapping the in-memory repository: it delegates (or not) and then raises `PersistenceConnectionError` on the n-th call of an operation | AC8 (unit) |
  | P-2, before commit: the connection lost before the final `finish_run(SUCCEEDED)` commits | unit: `FlakyRepository` raising `PersistenceConnectionError` on that call without delegating. Integration: `KillBeforeFinishRepository`, wrapping the real adapter; on `finish_run(SUCCEEDED)` it first calls `pg_terminate_backend` for its own backend through the admin connection, then delegates (the delegate raises `PersistenceConnectionError`; nothing was written) | AC8 (P-2) |
  | P-2, after commit: the final `finish_run(SUCCEEDED)` committed, then the reply was lost | unit: `FlakyRepository` delegating, then raising `PersistenceConnectionError`. Integration: `KillAfterFinishRepository`, wrapping the real adapter; it delegates (the commit happens), then terminates its own backend and raises `PersistenceConnectionError` itself, standing in for the reply lost on the wire (persistence U1: the real commit-in-flight loss is not deterministic) | AC8 (P-2) |
  | P-2, recovery refused | the same wrappers plus admin `ALTER DATABASE <db> ALLOW_CONNECTIONS false`, or a test session holding `INGEST_EXCLUSION_KEY`, before the repeat | AC8 (P-2) |
  | the adapter's session killed in the middle of a run | the `MockTransport` handler of page 2 calls `pg_terminate_backend` through the admin connection for the backend of the throwaway database other than the admin | AC8 (integration) |
  | new connections refused | admin `ALTER DATABASE <db> ALLOW_CONNECTIONS false` in the same handler (F3 probe: `DROP DATABASE ... WITH (FORCE)` still drops it) | AC8 b |
  | the exclusion held by another session | a test connection running `pg_try_advisory_lock(INGEST_EXCLUSION_KEY)` | AC8 c, AC9, AC10, AC23 |
  | the migration lock held | a test connection holding `pg_advisory_lock(MIGRATION_LOCK_KEY)` | AC16 |
  | taken ids | `ScriptedExecutionIds` returning a fixed list | AC12 |
  | time | `FixedClock` stepping by one second per call | every row |
  | dead `running` runs, local-only observations, gaps, tampering | direct writes through the real ports (`start_run`, `store`) and file edits under `tmp_path` | AC10, AC22, AC24 |
  | the current directory changed during a run | `monkeypatch.chdir(<U>)` inside the page 1 handler | AC25 |

- **Data.** Synthetic only: buyer `SYNTHETIC BUYER S.A.`, page bodies built in the observed shape or read from `tests/fixtures/sercop/`, markers `synthetic-password-marker`, `synthetic-body-marker` and `synthetic-header-marker`. JSON details and scopes are compared with `same_json`.

### Other constraints
- No dependency is added (`AGENTS.md`, PT-11, intent AC18): `uv.lock` is unchanged, and `pyproject.toml` changes only by the two `[tool.mypy]` keys of decision F-1 and their comment (§ Ownership).
- One `SercopSource` per invocation, built by `interfaces` and closed in a `finally`. At most two repositories per invocation, opened by `run_ingest`. One thread. No injected callable calls back into the source (SA-13, R-11, PS-13).
- `SercopSource` is built with the wiring clock's `now`, so `captured_at` comes from the one clock (intent AC12).

## Proposed approach
Revisable by the executor if it records why, except where a passage cites a gate 1 decision (Qn) or a finding: only the human changes those.
- Decision: the use case opens the repository through `RepositoryOpener` — rationale: Q3 needs exactly one new connection created by the code that knows which operation is pending; `interfaces` still decides which adapter is built (intent AC18); rejected: `interfaces` passing a ready repository plus a reconnect callback (two objects for one concern).
- Decision: `IngestReporter` instead of `print` in `application` — rationale: `application` holds no I/O, and `interfaces` needs to learn the run id before the outcome so it can print `<id> running` after a second Ctrl+C; rejected: returning the id only in `IngestOutcome` (lost when the cleanup is interrupted).
- Decision: the listing returns sequence numbers, not observations — rationale: a corrupt record is reported per sequence by `read_observation` and never hides later ones (Q14, intent AC22); rejected: returning `Observation` objects (the first corrupt file would stop the listing).
- Decision (decision P-3 of the human, 2026-10-15; not revisable by the executor): `last-page-reached` is appended whenever the completed page `p` satisfies `p >= result.pages`, with no condition on `scope.last_page`, after that page's `page-completed`, and the run then ends `succeeded` — rationale: the event records that the source has no page after `p`, which is true whatever the scope says, and a resumption relies on it (intent AC3, AC24); rejected: the Revision 1 rule, which added a condition on `scope.last_page` (the no-results scope 1 to 1 would end without the event).
- Decision: the gap check runs after every listed sequence is verified — rationale: intent AC10 says a later observation is verified and not hidden by the gap.
- Decision: reconciliation stops at the first run with a problem — rationale: a problem means a human must look; continuing would add closures that hide the order of events; the remaining `running` runs are reconciled by the next invocation.
- Decision: the CLI keeps its parser in `cli.py` and delegates to `ingest_command.py` — rationale: CLI-3 stays where it is, and `cli.py` stays thin.
- Suggestion: `tests/unit/ingest/conftest.py` provides `InMemoryRawEvidenceStore` (keeps objects and observations in dicts and applies F1's `Observation` validation), `InMemoryIngestionRepository` (applies the same identity and idempotency rules as PS-7 to PS-9, models the exclusion with a shared flag), `FakeSource`, `FixedClock`, `ScriptedExecutionIds`, `RecordingReporter` and the wrappers of the seams table.
- Suggestion: suggested test files and `-k` tokens:
  - `tests/unit/ingest/test_ingestion_catalogue.py`: `catalogue`, `scope`, `execution_id`;
  - `tests/unit/ingest/test_ingest_use_case.py`: `success`, `repeat`, `last_page`, `failure_with_response`, `failure_without_response`, `storage`, `interrupt`, `connection_loss`, `resume`, `reconcile`, `closed_run`, `identity`, `chain`, `no_retry`, `unexpected`;
  - `tests/unit/ingest/test_ingest_command.py`: `usage`, `environment`, `exit_code`, `output`, `logger`, `paths`;
  - `tests/unit/ingest/test_ingest_layers.py`: `layer`;
  - `tests/unit/test_local_disk_raw_evidence_store_listing.py`: `listing`;
  - `tests/integration/ingest/test_postgres_runs_and_exclusion.py`: `list_runs`, `exclusion`;
  - `tests/integration/ingest/test_ingest_end_to_end.py`: `e2e_`;
  - `tests/integration/ingest/test_ingest_connection_loss.py`: `connection_loss`;
  - `tests/integration/ingest/test_ingest_cli.py`: `cli_`, `root`, `migrations`;
  - P-1: `tests/unit/test_persistence_error_hierarchy.py` (`hierarchy`) and `tests/integration/test_postgres_migration_lock_error.py` (`lock_error`), plus the one assertion added to `tests/integration/test_postgres_migrations.py`;
  - P-2: `connection_loss_final_finish` in `tests/unit/ingest/test_ingest_use_case.py`, and `final_finish` in `tests/integration/ingest/test_ingest_connection_loss.py`;
  - P-3: `last_page_p3` in `tests/unit/ingest/test_ingest_use_case.py`, and `e2e_last_page` in `tests/integration/ingest/test_ingest_end_to_end.py`;
  - the validation of `last-page-reached`: `chain_last_page` in `tests/unit/ingest/test_ingest_use_case.py`, and `e2e_chain_last_page` in `tests/integration/ingest/test_ingest_end_to_end.py`.

  Basenames are unique across directories (pytest's default import mode).

### Decisions (decided by the human on 2026-10-15)
The five findings of Revision 1 are closed; intent Revision 4 § Decisions on the execution-plan findings records them.

- **P-1, accepted.** `MigrationLockError(MigrationError)` in `domain/persistence_errors.py`, raised by `apply_migrations` exclusively for a busy migration lock, with the same fixed message (§ Public names and signatures). `interfaces` maps it to exit 1 and any other `MigrationError` to exit 2 (§ Order of an invocation, step 3).
- **P-2, accepted, with a contract change to intent AC8.** A run is confirmed `succeeded` only by the successful exact repeat of its final `finish_run(SUCCEEDED)` on the one new connection: exit 0. Every other connection loss exits 1 (§ State machine C, step 5).
- **P-3, the Revision 1 reading not accepted.** `last-page-reached` is appended whenever `p >= result.pages`, with no condition on `scope.last_page`, and the run ends `succeeded` (§ State machine P, step 5). Pages above the chain's valid `last-page-reached` are never requested, also across a resumption chain (§ State machine H, steps 3 and 4).
- **P-4, accepted.** `first_page = last_page + 1` only for a resumption with nothing left to request; `pages_left_to_request` validates every `first_page` of a chain, so any other unjustified value is a malformed chain (§ State machine H, steps 4 and 5).
- **P-5, accepted.** stdout `<id> running` after an interrupted cleanup means "last status confirmed by the process; closing not confirmed" (§ Output).
- **Hierarchy test, confirmed by the human on 2026-10-15.** The existing direct-subclass test in `tests/unit/test_ingestion_audit.py` is not edited. The new `tests/unit/test_persistence_error_hierarchy.py` pins `MigrationLockError.__bases__ == (MigrationError,)`, six errors in total, and the four direct descendants of `PersistenceError` unchanged. The separate `tests/integration/test_postgres_migration_lock_error.py` pins that only a busy lock produces `MigrationLockError`: its non-lock `MigrationError` cases must not be a `MigrationLockError`.
- **P-3 consequences, accepted by the human on 2026-10-15.** No page above the chain's valid `last-page-reached` is requested; page bodies report `pages` 9 in the other scenarios (intent AC conventions); an unjustified `first_page` and a sentinel run holding page events are malformed.
- **Validation of `last-page-reached`, required by the human on 2026-10-15.** § State machine H, step 3.
- **Confirmed definitively by the human on 2026-10-15:**
  - the new hierarchy test `tests/unit/test_persistence_error_hierarchy.py`;
  - `storage-failed` may follow a valid `last-page-reached`;
  - two `last-page-reached` events anywhere in the chain are rejected, with no precedence rule.
- **Coverage of `last-page-reached`, required by the human on 2026-10-15.** § State machine H, step 3, the coverage bullet and its consequence.

### Implementation findings (2026-10-16 and 2026-10-17)
Recorded in intent Revision 7 § Findings raised during implementation; no earlier decision is reopened.

- **F-1, decided by the human on 2026-10-16 (option a).** The two `[tool.mypy]` keys in `pyproject.toml` (§ Ownership, § Other constraints, § Consumers, the AC18 and AC20 rows).
- **F-2, documentation.** The ingest execution id has 32 characters (§ Public names and signatures).
- **F-3, proposed in Revision 5 and approved by the human on 2026-10-17.** A read-back that raises `EvidenceNotFoundError`, `OSError` or `EvidenceIntegrityError` counts as not recorded (§ State machine P, step 3; the seams table; the AC6 row).

### Rollout order (for `tasks.md` to slice into outcomes)
1. **M1, the F1 listing.** Port operation and `LocalDiskRawEvidenceStore` implementation with `test_local_disk_raw_evidence_store_listing.py` (AC22, AC20). It lands first because both reconciliation and the id check need it.
2. **M2, the F3 extension.** `list_runs`, `try_acquire_ingest_exclusion` and `INGEST_EXCLUSION_KEY`, with `test_postgres_runs_and_exclusion.py` (AC23, AC20); and the new error `MigrationLockError` with its runner branch, the one added assertion in `tests/integration/test_postgres_migrations.py`, `tests/unit/test_persistence_error_hierarchy.py` and `tests/integration/test_postgres_migration_lock_error.py` (AC16, AC20, P-1).
3. **M3, the vocabulary.** `domain/ingestion_catalogue.py`, `application/ingest_ports.py`, and the types of `ingest_use_case.py` (requests, `IngestEnd`, `IngestOutcome`, the `run_ingest` stub), `infrastructure/system_clock.py`, and the doubles in `tests/unit/ingest/conftest.py`. The test-writer then writes every F4 test in red against these names (gate 2, Day 19).
4. **M4 🧑, the use case.** The human implements `run_ingest` in `application` by hand (Day 19: "Implementa tú el caso de uso en application", intent § Constraints), against the unit tests with doubles (AC1 to AC13, AC17, AC24). The executor does not write this module's body; it may review and point to failing tests.
5. **M5, the CLI.** `interfaces/ingest_command.py` and the `cli.py` subparser (AC14, AC15, AC16, AC25), unit tests first, then integration and CLI tests (AC8, AC10, AC19).
6. **M6, documentation.** AC21 and the `harny-sync` notes. The human writes `docs/learning/journal.md` in his own words: the Day 17 "Siguiente paso" correction and the Day 18 entry when the three specs close; later days as they happen.
7. **After gate 3.** The Day 20 live run (Q10) is the human's manual step, outside the suite.

## Consumers and migration
- **Existing tests.** The 1307 tests keep passing (intent AC20).
  - One test is edited, by one added assertion (decision P-1): in `tests/integration/test_postgres_migrations.py`, `test_runner_lock_held_elsewhere_fails_at_once_and_creates_nothing` gains `assert type(caught.value) is MigrationLockError` (and the import).
  - Every other `pytest.raises(MigrationError)` in `tests/integration/test_postgres_migrations.py` and `tests/unit/test_postgres_migration_files.py` keeps passing unchanged, because the plain error is still `MigrationError`, and so do the three other lock tests, because `MigrationLockError` is a `MigrationError`.
  - The new tests check that those other cases are **not** a `MigrationLockError`, so the existing files need no edit for that.
  - `test_persistence_errors_are_direct_subclasses_of_persistence_error` in `tests/unit/test_ingestion_audit.py` is not edited: it asserts `__bases__ == (PersistenceError,)` for the four direct subclasses only, which stays true, and adding `MigrationLockError` there would be wrong. No existing test counts the errors. The count of six is pinned by the new `tests/unit/test_persistence_error_hierarchy.py`. `tests/unit/test_cli.py` keeps passing because the subparser is optional and `--bogus` still reports `unrecognized arguments: --bogus`. `tests/unit/test_layers.py` is unchanged; its `application` and `interfaces` checks now also cover the new modules (no `httpx` or `psycopg` outside `infrastructure`). `tests/integration/conftest.py` is unchanged; the F4 integration subdirectory reuses its fixtures through pytest's conftest inheritance.
- **Port implementers.** Only `LocalDiskRawEvidenceStore` and `PostgresIngestionRepository` (§ Binding constraints "Port types keep satisfying their adapters").
- **Tooling configuration.** Every runner of `uv run mypy .` (the hooks, the `feedback` CI job, PT-7) picks up the two `[tool.mypy]` keys of decision F-1 from `pyproject.toml`; strictness stays in `domain` only (PT-5). `uv.lock` and the dependency tables are unchanged, so `uv sync --locked` is unaffected.
- **`specs/current` at archive.** See § Ownership. The `cli` CLI-2 scenario's quoted usage line changes to include `{ingest}`.
- **Docs.**
  - `README.md` § Technologies and § Development commands: the `ingest` command and the rule that it is run from the repository root; `uv run --env-file .env ec-procurement-quality ingest ...`; `--resume`; the fixed `data/raw/`; the optional `POSTGRES_HOST` and `POSTGRES_PORT`; the exit codes 0, 1, 2 and 130; how to end a stale session that holds the exclusion (a `psql` query on `pg_locks` with `locktype = 'advisory'` and `pg_terminate_backend`, documented without the key's value); the sentences "nothing calls ... yet" replaced.
  - `AGENTS.md` § Current commands: the ingest command.
  - `docs/architecture.md` § Open questions: the minimum audit events and the scope answered for ingestion; § Infrastructure boundary: the ingestion now uses the database.
  - `CHANGELOG.md` § Unreleased: the `ingest` command (Added); the two port extensions and `MigrationLockError` (Changed; the runner still raises a `MigrationError`, now the subclass for a busy lock). Known limitations:
    - the best-effort cleanup;
    - a stale session can hold the exclusion;
    - a page whose `page-completed` event was lost is requested again;
    - the command is supported only from the repository root;
    - the commit-in-flight case is still not tested against PostgreSQL.
  - `docs/learning/journal.md`: 🧑.
- **Consumers (F5 and later).** F4 leaves:
  - every response as an observation in both stores;
  - the `page-completed` events, which name the sequence and content hash of each complete page, the only F4 statement that a `200` body passed F2's checks;
  - the `run-started.resumes` chain;
  - the scope.

  F5 should take its inputs from `page-completed` and not from every `200` observation (F2 consumer rule), and must keep normalized records free of duplicates when a scope is repeated (intent § Constraints, the human's rule). `api/record` is not fetched by F4 (Q15). Nothing here designs F5.

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Carried, persistence U1: a lost commit leaves the outcome unknown, and the real commit-in-flight case cannot be made deterministic against PostgreSQL | Low | Med | § State machine C repeats only safe operations and checks before re-appending an event; unit tests simulate commit-then-raise with `FlakyRepository`; integration covers the deterministic loss cases |
| Carried, raw-evidence N2: `OSError` after publication | Low | Med | P step 3 asks the port and records a published observation (AC6 b) |
| Carried, source-access R-6 and raw-evidence N3: an exception chain holds protocol text or a record | Low | Med | Only `str()` of project errors and class names of other exceptions are printed; AC15 markers |
| Carried, R-7: `httpcore` at `DEBUG` writes header values | Low | Med | Invocation step 2; AC15 test lowers the root logger to `DEBUG` first |
| Carried, R-11: one source shared or re-entered | Low | High | One source per invocation, one thread; the AC25 chdir handler does not call the source |
| Carried, source-access U1: the real portal answers differently | Med | Low | Day 20 live run by the human; every response kept and typed |
| Carried, persistence N5: reconciliation reads run in separate snapshots | Low | Low | Safe because the exclusion keeps every other ingest out |
| New: the integration guard's allowance of `getaddrinfo` for the database host depends on `psycopg` internals (§ Guidance consulted) | Low | Low | `uv.lock` pins `psycopg` 3.3.6; the guard proof test fails loudly if `httpx` gets through or PostgreSQL is blocked |
| New: `os.chdir` in the AC25 handler is process-wide and could leak into other tests | Med | Low | `monkeypatch.chdir` restores it; that test does not run in parallel (the suite is serial) |
| New: after a second Ctrl+C, stdout `<id> running` may be wrong if `finish_run` had committed just before | Low | Low | Documented as "last status confirmed by the process; closing not confirmed" (decision P-5, § Output); AC10 fixes the state on the next run |
| New (P-2): exit 0 after a database failure could hide an unconfirmed finish | Low | Med | Exit 0 only when the exact repeat of the final `finish_run` returns the stored `succeeded` run with the same `finished_at`; every other loss is exit 1 (§ State machine C); stderr still reports the lost connection |
| New (P-1): a future runner change raises `MigrationLockError` for a case that is not the busy lock, or the reverse | Low | Med | `test_postgres_migration_lock_error.py` pins the only lock case and the non-lock cases by exact type |
| New: a stale backend keeps the exclusion after a host crash | Low | Med | README procedure; the refusal writes nothing |
| New: the in-memory doubles drift from the real adapters' rules | Med | Med | Doubles implement PS-7 to PS-9 and F1's validation; the integration end-to-end rows re-run the main paths on the real adapters |

## Validation
Cwd: the repository root for every row. Setup for every row: `uv sync --locked`. Integration rows also need the Compose database (`docker compose up -d --wait`) and run with `--env-file .env`; each test runs in its own throwaway database (PT-13). Unit rows run under the `tests/unit/ingest/conftest.py` guard and integration rows under the `tests/integration/ingest/conftest.py` guard. No row touches the real `data/raw/` or the database named by `POSTGRES_DB`. Broader commands:
- unit rows: `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing`;
- integration rows: `uv run --env-file .env pytest --cov=ec_procurement_quality --cov-report=term-missing`.

| AC | Demonstrated by | Tests to write | Tier | Framework | Setup | Focused command | Broader command | Cwd |
|---|---|---|---|---|---|---|---|---|
| AC1 | a two-page scope ends `succeeded` with both stores and events in order | `success` (unit, doubles): requests 1 then 2, sequences 1 and 2, events `run-started`, `page-completed` x2, `finish_run(SUCCEEDED)`, outcome `SUCCEEDED`; `e2e_success` (integration): through `run_ingest_command` with the simulated source, the real store on `tmp_path` and the migrated database; files `observations/<A>/1.json`, `2.json`; rows by direct SQL; exit 0; stdout `<A> succeeded` | unit, integration | pytest, httpx `MockTransport`, psycopg | doubles; migrated database | `uv run pytest tests/unit/ingest -q -k success`; `uv run --env-file .env pytest tests/integration/ingest -q -k e2e_success` | both broader commands | repo root |
| AC2 | a repeat makes a new run, no new object or `raw_evidence` row, its own observations and events | `repeat` (unit); `e2e_repeat` (integration): two invocations, ids differ, `objects/` bytes and mtimes unchanged, `raw_evidence` count unchanged, 4 observation rows; changed page 2 body -> one more object and row | unit, integration | pytest, psycopg | as AC1 | `... -k repeat`; `... -k e2e_repeat` | both | repo root |
| AC3 | no request above the reported last page; not a failure | `last_page` (unit): scope 1 to 5 with `pages` 2 -> 2 requests and `last-page-reached`; scope 4 to 5 -> 1 request, completed, `last-page-reached` (page 4, `pages` 2); `pages` 9 for every other row, so no early end; see the P-3 row | unit | pytest | doubles | `uv run pytest tests/unit/ingest -q -k last_page` | unit broader | repo root |
| AC4 | a response to a failed page is stored first, then the failure, then stop | `failure_with_response` (unit, parametrized `429` HTML, `500` empty, half body, cut-off after 100 bytes): order local store -> `record_observation` -> `page-failed` -> `finish_run(FAILED)` from a recording double; no page 3 request; `e2e_failure` (integration) for `429` and the cut-off body with the real adapters; exit 1; stdout `<A> failed` | unit, integration | pytest, httpx, psycopg | as AC1 | `... -k failure_with_response`; `... -k e2e_failure` | both | repo root |
| AC5 | a failure with no response records an event and uses no sequence | `failure_without_response` (unit): connect error before the status and status `600` through `SercopSource` with `MockTransport`; no observation 2 in either store; `page-failed` with sequence `None`, `transport`, status `None` | unit | pytest, httpx | doubles | `... -k failure_without_response` | unit broader | repo root |
| AC6 | store and integrity failures stop the run; `OSError` is never read as nothing written; a failed read-back counts as not recorded | `storage` (unit): (a) real store on `tmp_path` with a file at `observations` -> `storage-failed` (page 2, sequence 2, `raw-evidence`) on every platform, whether the read-back raises `EvidenceNotFoundError` (Windows) or `NotADirectoryError` (Linux); (b) `PublishThenFailStore` -> observation recorded in the repository before `finish_run`; (c) repository double refusing `record_observation` with `PersistenceIntegrityError` -> `storage-failed` `postgresql`; stderr names operation and identity only; (d) a store double whose `store` raises `OSError` and whose `read_observation` for that sequence then raises `OSError`, and a second case where it raises `EvidenceIntegrityError` -> `storage-failed` (page 2, sequence 2, `raw-evidence`), no observation 2 in the repository, `finish_run(FAILED)`, outcome `RUN_FAILED` with `run_status` `failed` (exit 1 at the CLI tier) | unit | pytest | doubles, `tmp_path` | `... -k storage` | unit broader | repo root |
| AC7 | Ctrl+C keeps completed pages, best-effort close, exit 130 | `interrupt` (unit): `KeyboardInterrupt` from the transport at page 2 -> `run-interrupted`, `failed`, `INTERRUPTED`; after the local store and before PostgreSQL -> recorded first; a second interrupt during cleanup -> propagates, the run stays `running`; `exit_code` (unit, command): 130 and stdout `<A> failed`, or `<A> running` after a second interrupt ("closing not confirmed", decision P-5) | unit | pytest | doubles | `... -k "interrupt or exit_code"` | unit broader | repo root |
| AC8 | after a lost connection: one new connection, the exclusion again, safe repeats only, close `failed`; else left `running`; exit 1 except the P-2 case (own row) | `connection_loss` (unit, `FlakyRepository`): commit-then-raise on `record_observation` and on `finish_run` (repeated with the same values, same `finished_at`); commit-then-raise on `append_audit_event` -> event once; raise-before-commit -> appended once; second loss -> no third connection. `connection_loss` (integration): `pg_terminate_backend` from the page 2 handler; (a) reconnect works -> `storage-failed` `postgresql`, `failed`, exit 1; (b) `ALLOW_CONNECTIONS false` -> `running`, exit 1, stdout `<A> running`, store intact; (c) a test session takes the exclusion after the kill -> run untouched, `running`, exit 1 | unit, integration | pytest, psycopg | doubles; migrated database, admin connection | `uv run pytest tests/unit/ingest -q -k connection_loss`; `uv run --env-file .env pytest tests/integration/ingest/test_ingest_connection_loss.py -q` | both | repo root |
| AC9 | explicit resume: same scope, link event, no completed page requested; invalid targets exit 2 | `resume` (unit): A completed 1 and 2, failed on 3 -> B requests 3 and 4, `run-started` `{"resumes": A, "first_page": 3}`, sequences from 1; B fails on 4 -> C requests 4 only; a page stored without `page-completed`, and a page with only an orphan object, are requested again; all pages completed but `running` -> closed by R, nothing requested, `first_page` `last_page + 1` (decision P-4), `succeeded`; a chain whose earlier run recorded a valid `last-page-reached` (page 2, after its `page-completed` for page 2) for scope 1 to 4 and was left `running` -> nothing requested, `first_page` 5, `succeeded`; `e2e_resume` (integration) for the first case; targets: unknown well-formed id and `succeeded` run -> `INVALID_TARGET`, exit 2, nothing written; the exclusion held -> exit 1 | unit, integration | pytest, psycopg | doubles; migrated database | `... -k resume`; `... -k e2e_resume` | both | repo root |
| AC10 | every `running` run is reconciled with the fixed store and the listing before a new run; problems closed list | `reconcile` (unit): local {1,2,3}, PostgreSQL {1,2} -> observation 3 recorded, `observation-reconciled`, `run-closed-by-reconciliation` 1, `failed`, then the new run; one case per problem value (missing, different, unreadable, object missing, object tampered, gap {1,3} with 3 verified, PostgreSQL conflict, listing failure); a problem -> `reconciliation-failed`, `failed`, `NOT_STARTED`; `e2e_reconcile` (integration): the crash case with the real store and database; the exclusion held elsewhere -> exit 1, A `running`, no file, no run | unit, integration | pytest, psycopg | doubles; `tmp_path`; migrated database | `... -k reconcile`; `... -k e2e_reconcile` | both | repo root |
| AC11 | nothing added to a finished run | `closed_run` (unit): event and observation counts of A unchanged after the resume of AC9 and after an AC24 refusal | unit | pytest | doubles | `... -k closed_run` | unit broader | repo root |
| AC12 | ids new, valid, off reserved names, checked in both ports; sequences from 1 without gaps; one clock | `execution_id` (unit, catalogue): form, F1 pattern, every reserved name rejected; `RandomExecutionIdSource` gives two different valid ids; `identity` (unit): `ScriptedExecutionIds` returning an id known to the repository, then one listed by the store, then a free one -> `start_run` only with the free one; three taken -> `NOT_STARTED`; every recorded time comes from `FixedClock` and carries an offset | unit | pytest | doubles | `... -k "execution_id or identity"` | unit broader | repo root |
| AC13 | scope keys exact, no float; event types and values from the closed lists; no forbidden content in details | `scope` and `catalogue` (unit): `IngestScope.to_json` exact, `from_json` rejections, enums' values exact; `success`, `failure_*`, `reconcile` assert every appended detail against the § Audit details table with `same_json` | unit | pytest | none | `... -k "scope or catalogue"` | unit broader | repo root |
| AC14 | invalid command, argument, configuration or target -> exit 2 before anything is requested or started | `usage` and `environment` (unit, `run_ingest_command` and `main`): every AC14 case including `--raw-root`, `--resume` with `--year`, `--resume Synthetic_Id`, missing required variables, `POSTGRES_PORT` `abc` and `70000`, a missing migrations directory; the `make_repository` and `make_source` doubles fail the test if called; a `.env` in the current directory is ignored; bare command -> usage, exit 2; unknown and `succeeded` targets are AC9 rows | unit | pytest | wiring doubles, `tmp_path` | `uv run pytest tests/unit/ingest -q -k "usage or environment"` | unit broader | repo root |
| AC15 | stdout one result line; stderr safe; no tracebacks; `httpcore` above `DEBUG` | `output` (unit): markers in the password, a body, a header value and a `Set-Cookie` absent from stdout, stderr and every stored detail; no `https://` on stderr; a synthetic exception from the transport -> class name only, `unexpected-error`, exit 1; `MemoryError` -> the same, best effort; the P-2 case prints `<A> succeeded` with exit 0; after a second interrupt, `<A> running` (decision P-5); `logger`: root logger set to `DEBUG` before the call, the transport handler records `getLogger("httpcore").getEffectiveLevel() > DEBUG`, no handler added | unit | pytest, httpx, `caplog`, `capsys` | wiring doubles | `... -k "output or logger"` | unit broader | repo root |
| AC16 | migrations applied before the repository; any `MigrationError` other than `MigrationLockError` 2; `MigrationLockError` 1 (P-1 row) | `migrations` (integration, `empty_database`): applies `0001` (named on stderr) then runs; migrated -> nothing applied; a changed applied file in a temporary copy of the directory -> exit 2; `MIGRATION_LOCK_KEY` held -> exit 1 (`MigrationLockError`); a call-order recording wiring shows `migrate` returning before `make_repository` | integration | pytest, psycopg | empty and migrated databases | `uv run --env-file .env pytest tests/integration/ingest -q -k migrations` | integration broader | repo root |
| AC17 | one request per page per run | `no_retry` (unit): for every AC4 and AC5 case, the transport saw exactly one page 2 request | unit | pytest, httpx | doubles | `... -k no_retry` | unit broader | repo root |
| AC18 | layers and ports hold; no dependency | `layer` (unit, new file): no module in `application/` contains `advisory`, `pg_`, `SELECT `, `INSERT `, `UPDATE `, `DELETE `, `objects/`, `observations/` or `.json`; `ingest_use_case` imports only the standard library, `domain` and `application`; `interfaces` imports neither `httpx` nor `psycopg` (existing test); `use_case` runs with doubles only (the unit guard proves no socket, and no `tmp_path` is used); `uv run mypy .` accepts the doubles as the extended ports; one source closed per invocation (wiring double counts `close`) | unit, static | pytest, mypy | none | `uv run pytest tests/unit -q -k layer` | `uv run mypy .`; `git diff main --stat -- uv.lock` (empty); `git diff main -- pyproject.toml` (only the added `explicit_package_bases = true` and `mypy_path = "src"` under `[tool.mypy]` and their comment lines; no dependency line) | repo root |
| AC19 | no network, no real `data/raw/`, no configured database | the two guards (each with a proof test: an `httpx` call to `source.invalid` is blocked; a PostgreSQL connection still works in integration); the session fixture comparing the real `data/raw/` before and after; no `ecpq_test_` database left (PT-13 check) | unit, integration | pytest | as the tiers | `uv run --env-file .env pytest tests/unit/ingest tests/integration/ingest -q` | integration broader | repo root |
| AC20 | everything still works; ports keep their guarantees | none new; the existing 1307 tests pass, F1 store tests and the F3 `satisfies_port` test unchanged; the one P-1 assertion added in `test_postgres_migrations.py` | unit, integration, command | pytest, ruff, mypy, doctor, git | `uv sync --locked` | `uv run --env-file .env pytest -q` | `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy .`; `uv run node .sdd/doctor/run-doctor.mjs` (`0 warned, 0 failed`); `uv run ec-procurement-quality --version`; `git diff main --stat -- migrations tests/unit/test_cli.py tests/unit/test_layers.py tests/unit/test_ingestion_audit.py tests/unit/test_postgres_migration_files.py tests/unit/test_local_disk_raw_evidence_store.py tests/unit/test_sercop_source.py tests/integration/test_postgres_ingestion_repository.py tests/integration/test_postgres_schema.py tests/integration/test_postgres_isolation.py tests/integration/conftest.py src/ec_procurement_quality/infrastructure/sercop_source.py src/ec_procurement_quality/application/procurement_source.py src/ec_procurement_quality/domain/source_response.py uv.lock` (empty); `git diff main -- pyproject.toml` (only the two `[tool.mypy]` keys of decision F-1 and their comment, additions only; no dependency line); `git diff main --numstat -- tests/integration/test_postgres_migrations.py` (additions only, 0 deletions); `git ls-files .env` (empty); `git diff --check` | repo root |
| AC21 | docs say what exists | none (inspection at audit) | manual | git | none | `git grep -n -e "ingest" -- README.md AGENTS.md docs/architecture.md CHANGELOG.md` | by inspection against the AC21 list | repo root |
| AC22 | the F1 listing finds every observation, gaps included, read-only | `listing` (unit, `tmp_path`): 1, 2 and 5 for one id and 1 for another; empty for an unknown id, with no directory created; `ValueError` for `../escape` and `Synthetic-Exec` before any access (no directory created); `x.json`, `01.json`, a subdirectory, a file at the directory path -> `EvidenceIntegrityError` naming the execution, no content; `tmp/` and objects never listed; every file's bytes and mtime unchanged; a corrupted `2.json` still listed, reading 2 fails, 5 reads | unit | pytest | `tmp_path` | `uv run pytest tests/unit/test_local_disk_raw_evidence_store_listing.py -q` | unit broader | repo root |
| AC23 | F3 lists runs by status and holds an exclusion | `list_runs` (integration, migrated database): 001 and 003 `running`, 002 `failed`, stable order, `()` for none, `ValueError` for `"running"` as plain `str`; `exclusion`: first repository `True` and `True` again; second repository `False` at once, nothing written; after `close()` or `pg_terminate_backend` of the first, the second gets `True`; `MIGRATION_LOCK_KEY` held does not block it, and holding the exclusion does not block `apply_migrations`; after a loss -> `PersistenceConnectionError`; no key, SQL or setting in `str`, `repr`, `args` | integration | pytest, psycopg | migrated database, admin connection | `uv run --env-file .env pytest tests/integration/ingest/test_postgres_runs_and_exclusion.py -q` | integration broader | repo root |
| AC24 | a chain that exists but is cyclic, malformed or contradictory -> exit 1, no new run, nothing appended | `chain` (unit): one case per AC24 bullet (link to no run, A<->B cycle, zero or two `run-started`, bad detail types, a different scope, a `page-completed` without a matching `200` observation in both stores, a `succeeded` run in the middle, and the P-4 cases: a fresh run whose `first_page` differs from the scope's, a resumption whose `first_page` is `0`, `last_page + 2`, or `last_page + 1` while a page is still left, and a `last_page + 1` run holding a `page-completed`; the `last-page-reached` cases have their own row); outcome `NOT_STARTED`, no `start_run`, event counts unchanged except AC10 events when the target was `running` | unit | pytest | doubles | `... -k chain` | unit broader | repo root |
| AC25 | `data/raw/` resolved once to an absolute path from a synthetic repository root; host and port defaults | `root` (integration CLI): current directory `<T>` with a copy of the repository's `migrations/`, default `--migrations-dir`, default store; the page 1 handler changes to `<U>`; every file under `<T>/data/raw/`, nothing under `<U>`; page 2 fails; a later `--resume` from `<T>` finds page 1 through the listing and does not request it; `paths` (unit): the store root given to `make_store` is absolute and equals `Path.cwd() / "data" / "raw"` at the call; `environment` (unit): `POSTGRES_HOST` and `POSTGRES_PORT` unset -> the `PostgresSettings` given to `make_repository` has `127.0.0.1` and `5432` | unit, integration | pytest, psycopg | `tmp_path`, `monkeypatch.chdir`, migrated database | `uv run pytest tests/unit/ingest -q -k "paths or environment"`; `uv run --env-file .env pytest tests/integration/ingest -q -k root` | both | repo root |
| AC16 (P-1) | `MigrationLockError` only for the busy lock; every other runner refusal a plain `MigrationError`; six errors | `test_persistence_error_hierarchy.py` (unit, new) pins exactly: (1) `MigrationLockError.__bases__ == (MigrationError,)`; (2) six errors in total (`PersistenceError` and its subclasses at any depth: exactly six classes); (3) the four direct descendants of `PersistenceError` unchanged (`PersistenceError.__subclasses__()` is exactly `PersistenceConnectionError`, `PersistenceIntegrityError`, `PersistenceNotFoundError`, `MigrationError`). The existing `test_persistence_errors_are_direct_subclasses_of_persistence_error` is not edited. (4) That only a busy lock produces `MigrationLockError` is pinned by the separate integration file. `test_postgres_migration_lock_error.py` (integration, new, `empty_database`): the lock held by a test connection -> `type(error) is MigrationLockError`, message exactly `another migration run holds the lock`, no `__cause__`, no setting or password marker in `str`, `repr` or `args`; caught by `except MigrationError`; parametrized non-lock cases (changed applied file, missing applied file, failed file `SELECT 1/0`, gap in numbering, missing directory) -> `type(error) is MigrationError`, not a `MigrationLockError`. Edited existing test: `test_runner_lock_held_elsewhere_fails_at_once_and_creates_nothing` gains `type(caught.value) is MigrationLockError`. CLI: `migrations` rows above (exit 1 versus 2) | unit, integration | pytest, psycopg | none; empty database, test connection | `uv run pytest tests/unit/test_persistence_error_hierarchy.py -q`; `uv run --env-file .env pytest tests/integration/test_postgres_migration_lock_error.py tests/integration/test_postgres_migrations.py -q -k "lock or runner"` | both | repo root |
| AC8 (P-2) | a lost connection during the final `finish_run(SUCCEEDED)`: confirmed by the exact repeat -> exit 0; recovery refused -> `running`, exit 1 | `connection_loss_final_finish` (unit, `FlakyRepository`): (a) raise before delegating -> the repeat on the second repository finishes the run, `SUCCEEDED`, `run_status` `succeeded`, the same `finished_at`, no `storage-failed`; (b) delegate then raise -> the repeat returns the stored run unchanged, `SUCCEEDED`; (c) the second open fails, or the exclusion returns `False` -> no repeat, `RUN_FAILED`, `run_status` `running`. `connection_loss_final_finish` (integration, migrated database): `KillBeforeFinishRepository` -> exit 0, stdout `<A> succeeded`, the stored run `succeeded` with that `finished_at`, no `storage-failed` event; `KillAfterFinishRepository` -> exit 0, stdout `<A> succeeded`, exactly one stored finish (the row unchanged by the repeat); `KillBeforeFinishRepository` with `ALLOW_CONNECTIONS false` -> exit 1, stdout `<A> running`, the stored run `running`; with the exclusion held by a test session -> exit 1, stdout `<A> running`, the run untouched | unit, integration | pytest, psycopg | doubles; migrated database, admin connection | `uv run pytest tests/unit/ingest -q -k connection_loss_final_finish`; `uv run --env-file .env pytest tests/integration/ingest/test_ingest_connection_loss.py -q -k final_finish` | both | repo root |
| AC3 (P-3) | `last-page-reached` whenever `p >= pages`, whatever the scope's last page; then `succeeded`, no more requests | `last_page_p3` (unit, doubles): `pages` 0 (`total` 0) with scope 1 to 1 -> one request, `page-completed` (page 1), `last-page-reached` (page 1, `pages` 0), `succeeded`, exit 0; scope 1 to 2 with `pages` 2 -> two requests, `last-page-reached` (page 2, `pages` 2), `succeeded`, no third request; scope 1 to 2 with `pages` 3 (AC1) -> no `last-page-reached`; a beyond result on page 4 (`pages` 2, scope 4 to 5) -> exactly one request (AC17 holds: no page requested twice, none after the event); a resumption of a chain that recorded `last-page-reached` requests no page above it. `e2e_last_page` (integration): the scope 1 to 1, `pages` 0 case through the CLI with the real adapters | unit, integration | pytest, httpx, psycopg | doubles; migrated database | `uv run pytest tests/unit/ingest -q -k last_page_p3`; `uv run --env-file .env pytest tests/integration/ingest -q -k e2e_last_page` | both | repo root |
| AC24 (`last-page-reached`) | no stored `last-page-reached` limits a resumption unless it is valid; an invalid one makes the chain malformed and never makes a page be skipped | `chain_last_page` (unit, doubles; each case built by appending events through the in-memory repository): run A, scope 1 to 4, `failed`, with `page-completed` for pages 1 and 2, then one of: detail `{"page": 2}` (missing key), `{"page": 2, "pages": 2, "x": 1}` (extra key), `{"page": True, "pages": 1}`, `{"page": 2, "pages": False}`, `{"page": 5, "pages": 2}` (above `last_page`), `{"page": 2, "pages": 3}` (`page < pages`), `{"page": 2, "pages": -1}`; two events in A; one valid event in A and another in a later run B of the chain; an event for page 3 with no `page-completed` for page 3; an event for page 2 whose `page-completed` for page 2 comes only after it; a valid event followed in A by a `page-completed` or by a `page-failed`; coverage: run A, scope 1 to 4, with valid `page-completed` for pages 1 and 4 only, then `last-page-reached` (page 4, `pages` 4) and no `page-completed` for page 2 or 3 anywhere in the chain. Each -> `ingest --resume <A>` (or `<B>`) gives `NOT_STARTED`: exit 1, no request to the source, no `start_run`, every run's event and observation counts unchanged. Control cases, which must not be rejected and each request nothing and succeed with `first_page` 5: (i) A's valid event (page 2, `pages` 2) after its `page-completed` for pages 1 and 2, followed only by `storage-failed`; (ii) pages 1 and 2 completed by A (failed on page 3), pages 3 and 4 by B, then B's event (page 4, `pages` 4), B left `running` and closed by reconciliation -> `ingest --resume <B>`; (iii) pages 1 and 2 by A and page 3 by B, then B's event (page 3, `pages` 3). `e2e_chain_last_page` (integration, migrated database): the `bool` page case, the coverage case (pages 1 and 4) and the two-run control through `run_ingest_command` with the real adapters | unit, integration | pytest, psycopg | doubles; migrated database | `uv run pytest tests/unit/ingest -q -k chain_last_page`; `uv run --env-file .env pytest tests/integration/ingest -q -k e2e_chain_last_page` | both | repo root |

## Revision log
- Revision 1 (2026-10-14): First draft, based on intent Revision 3 (with the coordinator's AC25 correction).
- Revision 2 (2026-10-15): Based on intent Revision 4 and the human's decisions of 2026-10-15 on P-1 to P-5.
  - P-1: `MigrationLockError(MigrationError)`, its placement and the one runner branch that raises it, in Public names and signatures. Also exit 1 versus 2 in invocation step 3 and the exit table, the edited PS-4 test and the new hierarchy and lock-error tests, Ownership, the persistence capability notes, M2, Consumers, and the AC16 and AC16 (P-1) rows.
  - P-2: State machine C step 5 defines "confirmed" as the successful exact repeat of the final `finish_run`, giving exit 0. Also the exit table, the Output section, the seams table (kill before and after the finish), and the AC8 and AC8 (P-2) rows.
  - P-3: State machine P step 5 emits `last-page-reached` whenever `p >= pages`; State machine H does not request pages above a recorded `last-page-reached`; the AC3 and AC3 (P-3) rows.
  - P-4: State machine H step 3 gives the sentinel and step 4 validates `first_page`, with a new domain helper `pages_left_to_request`; the AC9 and AC24 rows.
  - P-5: the Output section and the AC7, AC15 and risk rows.
  - The "Findings for the human" section is replaced by § Decisions.
- Revision 3 (2026-10-15): Based on intent Revision 5 and the human's decisions of 2026-10-15.
  - Correction A: the Proposed-approach decision that still conditioned the event on `scope.last_page` is replaced by the P-3 rule; P step 5 states the binding event order.
  - Correction B: State machine H gains step 3, the validation of every `last-page-reached` (exact detail, range, one per run and per chain, a preceding valid `page-completed` of the same page, no page event after it), with its interaction with reconciliation. Old steps 3 and 4 become 4 and 5, and their references are updated. `pages_left_to_request` takes only a validated `last_reached`.
  - The hierarchy-test specification in the AC16 (P-1) row and § Decisions.
  - The AC9 and AC24 rows, the new AC24 (`last-page-reached`) row, and the suggested tokens `chain_last_page` and `e2e_chain_last_page`.
- Revision 4 (2026-10-15): Based on intent Revision 6.
  - State machine H step 3 gains the coverage condition: a deterministic `covered` set (oldest run first, events in `list_audit_events` order, valid `page-completed` only, pages inside the shared scope) must hold every page from `scope.first_page` to `p`. It also gains the consequence with its proof sketch, the fixed order with reconciliation (R first; R never appends `page-completed`), and the interaction with the P-4 sentinel.
  - § Decisions records the definitive confirmations of 2026-10-15 and the coverage rule.
  - The AC24 (`last-page-reached`) row gains the coverage case and three control cases, two of them across two runs.
- Revision 5 (2026-10-17): Based on intent Revision 7, which resolves the findings F-1 to F-3 raised during implementation. Pending the human's approval.
  - F-2: § Public names and signatures says 32 characters instead of 33 (documentation only; the pattern is unchanged).
  - F-3: State machine P step 3 states that a read-back raising `EvidenceNotFoundError`, `OSError` or `EvidenceIntegrityError` counts as not recorded (`storage-failed` `raw-evidence`, step 7), and that `KeyboardInterrupt`, `SystemExit` and `MemoryError` keep the State machine K handling. The seams table gains the failing read-back; the AC6 row gains case (d) and the platform note for case (a).
  - F-1 consequence: § Ownership (new "Configuration" line; `pyproject.toml` leaves the "Unchanged" list), the `project-toolchain` note, § Other constraints, § Consumers ("Tooling configuration"), and the AC18 and AC20 rows, whose commands now check `uv.lock` for no diff and `pyproject.toml` for only the two `[tool.mypy]` keys.
  - § Guidance consulted gains the Revision 5 inputs; new subsection § Implementation findings.
