# Tasks: PostgreSQL persistence (F3)

## Status
Gate 1 approved on Revision 2 by the human on 2026-10-13. The human made the gate 1 decisions on 2026-10-13: question 2 approved (`psycopg[binary]>=3.3.6`); question 6 option B (the executor writes `migrations/0001_initial_schema.sql`, and the human reviews it line by line); questions 1, 3, 4, 5, 7, 8 and 9 accepted as recommended; question 10 handled outside F3. Revision 2 records those decisions and fixes review findings P1 (AC11), P2 (isolation) and P2 (JSON equality). The approval is recorded in the `Approval` line of `intent.md`. No code, test or configuration has changed. The spec set has 17 acceptance criteria (AC1 to AC17) and 12 outcomes (O1 to O12); O5 includes the human's review step.

## Baseline
- Base commit: `e74a41a` (`main`, "Merge pull request #22 from Vladimirjon/docs/day-16-f3-postgres-persistence-specs"). Updated on 2026-10-13 (Day 17); the earlier base was `3aac942`.
- Branch: `feat/postgres-persistence`, cut from `main` at `e74a41a`.
- Interpreter: Python 3.13.9 (`uv run python --version`), uv 0.12.23, ruff 0.17.0, `uv_build` `>=0.13.0,<0.14`. PostgreSQL 18.6 in the Compose service `postgres` (Docker Desktop, `healthy`).
- Cwd: the repository root, `ec-public-procurement-quality-monitor`.
- Commands:
  - Install: `uv sync --locked`
  - Database: `docker compose up -d --wait`
  - Unit and skipped integration: `uv run pytest`
  - All tiers locally: `uv run --env-file .env pytest`
  - CI form: `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing` (with the job's PostgreSQL service)
  - Lint and format: `uv run ruff check .` and `uv run ruff format --check .`
  - Type check: `uv run mypy .`
  - Readiness: `uv run node .sdd/doctor/run-doctor.mjs`
- Pre-existing failures: none. On 2026-10-13 at `e74a41a` (replaces the `3aac942` baseline): `uv run pytest -q` -> `961 passed`; `uv run ruff check .` -> `All checks passed!`; `uv run ruff format --check .` -> `81 files already formatted`; `uv run mypy .` -> `Success: no issues found in 20 source files`; `uv run node .sdd/doctor/run-doctor.mjs` -> `summary: 31 ok, 0 skipped, 0 warned, 0 failed`.

## Outcomes
Order and ownership:
1. **O1 (executor) first**, once the human approves Revision 2 and before any red test. The dependency itself was approved on 2026-10-13. Adding it first makes the red tests fail because the F3 modules are missing, not because `psycopg` is.
2. **O2 (test-writer)** writes the red tests for O3 to O8 (files and `-k` tokens from `execution-plan.md` § Proposed approach), including `tests/integration/conftest.py`, and fills the Tests and Red lines. The conftest holds the per-test throwaway databases, the migrated template, the skip or fail policy and the leftover check.
   - The correct red reason is that a pinned module or name does not exist yet (`ModuleNotFoundError` or `ImportError` naming it), or, for the schema tests, that `migrations/0001_initial_schema.sql` does not exist. It is never a missing database (the red run is made with the Compose database up and `--env-file .env`) and never a typo.
   - The human reviews the red tests at gate 2.
3. **O3, O4, O5, O6 and O7 (executor)**, in that order, each relying only on `execution-plan.md` § Binding constraints. O5 includes the executor writing the first migration (resolved question 6, option B).
4. **Human review of the migration (O5).** At the executor's hand-off of O5, the human reviews `migrations/0001_initial_schema.sql` line by line before O6 continues. The executor explains each constraint and each trigger in plain words: what it enforces, which AC it serves (AC5 or AC6), and which schema test shows it. The human may ask for changes; the file is not yet applied anywhere except throwaway test databases, so it may still be edited. The review result is recorded in O5.
5. Then **O8 to O11 (executor)** and **O12 (auditor)**.
6. No role reads, prints or commits `.env`, or edits `compose.yaml`, `.env.example`, `.github/dependabot.yml`, ADR 0006, ADR 0007, or the F1 and F2 modules. The Dependabot correction (resolved question 10) is a separate change by the human's session, not an F3 outcome.

- [x] **O1** (AC13, AC16) — executor: add the approved dependency (human, 2026-10-13) with `uv add "psycopg[binary]>=3.3.6"`, and declare the `integration` marker in `[tool.pytest]` of `pyproject.toml`. Expected lock change: `psycopg` 3.3.6, `psycopg-binary` 3.3.6 and `tzdata` 2026.5 added (25 packages).
  - Evidence (2026-10-13): `uv add "psycopg[binary]>=3.3.6"` installed `psycopg==3.3.6`, `psycopg-binary==3.3.6`, `tzdata==2026.5` (resolved 25 packages).
    - `git diff main --stat -- pyproject.toml uv.lock`: `pyproject.toml` +4, `uv.lock` +74/-2. `pyproject.toml` gains `"psycopg[binary]>=3.3.6"` in `dependencies` and `markers = ["integration: needs a real PostgreSQL 18 (see README)"]` in `[tool.pytest]` (`testpaths` kept).
    - `uv sync --locked` exit 0; `uv lock --check` exit 0 (`Resolved 25 packages`).
    - `uv run python -c "import psycopg; print(psycopg.__version__, psycopg.pq.__impl__)"` -> `3.3.6 binary`.
    - `uv run pytest -q` -> `961 passed`; `uv run ruff check .` -> `All checks passed!`; `uv run ruff format --check .` -> `81 files already formatted`; `uv run mypy .` -> `Success: no issues found in 20 source files`.
    - Nothing left: no other dependency and no other file changed; not committed.
- [ ] **O2** (AC14) — test-writer: the red tests of O3 to O8 and the integration harness in `tests/integration/conftest.py`:
  - settings from the five `POSTGRES_*` variables;
  - the admin connection;
  - one throwaway database per test, from `template0` for runner tests or copied from the migrated session template for all other tests;
  - the template created once, closed to connections, and dropped at session end;
  - the skip or fail policy;
  - the session-end leftover check.
  - Tests (written 2026-10-13, not committed; all synthetic data, `.invalid` URLs, password markers; `integration` marker on every integration file; every unit file under an autouse socket guard):
    - `tests/unit/test_ingestion_audit.py` (27 test functions; `same_json`, `run_status`, `ingestion_run`, `audit_event`, `json`, `invalid`, the five errors): AC7, AC9, AC10 at the domain tier, including every `same_json` case of § Validation AC7.
    - `tests/unit/test_postgres_settings.py` (`settings`, `password`): AC12 (field named, value never; `repr` and `str` hide the password), keyword-only, immutability, boundaries.
    - `tests/unit/test_postgres_migration_files.py` (`migration_files`): AC3 name checks before any connection (settings at `127.0.0.1` port 1; `MigrationError`, never `PersistenceConnectionError`), and the type of `MIGRATION_LOCK_KEY`.
    - `tests/unit/test_layers.py`: new `test_layer_only_infrastructure_imports_psycopg` (AC13); the AST helper is generalized to `_names_library(source, library)`, and `_names_http_client_library` keeps its name and behavior.
    - `tests/integration/conftest.py`: the five `POSTGRES_*` settings; skip locally and fail when `CI` is `true`; the admin connection (autocommit); `database_factory`, `empty_database` (from `template0`) and `migrated_database` (a copy of the session template); the template created once, `ALLOW_CONNECTIONS false`, dropped with `FORCE` at session end; the session-end leftover check. The F3 modules are imported lazily inside fixtures.
    - `tests/integration/test_postgres_migrations.py` (`runner_applies`, `runner_failure`, `runner_integrity`, `runner_lock`): AC1 to AC4.
    - `tests/integration/test_postgres_schema.py` (`schema_rejects`, `append_only`, `run_transition`, plus `schema_accepts` and `schema_defaults`): AC5, AC6; it imports no F3 module at run time.
    - `tests/integration/test_postgres_ingestion_repository.py` (`run_`, `observation_`, `audit_event_`, `invalid`, `connection`, `leak`, `satisfies_port`): AC7 to AC13, including the two deterministic AC11 cases (backend terminated before the call; backend terminated while the transaction waits on a lock).
    - `tests/integration/test_postgres_isolation.py` (`isolation`): AC14.
  - Red (2026-10-13, base `59f5253`, Compose database up, `.env` never read or printed; the F3 modules and `migrations/` do not exist yet):
    - `uv run pytest tests/unit/test_ingestion_audit.py -q` -> 1 error at collection: `ModuleNotFoundError: No module named 'ec_procurement_quality.domain.ingestion_audit'` (the module is missing).
    - `uv run pytest tests/unit/test_postgres_settings.py -q` -> 1 error at collection: `ModuleNotFoundError: No module named 'ec_procurement_quality.infrastructure.postgres_settings'`.
    - `uv run pytest tests/unit/test_postgres_migration_files.py -q` -> 1 error at collection: `ModuleNotFoundError: No module named 'ec_procurement_quality.domain.persistence_errors'` (`postgres_migrations` is missing too).
    - `uv run pytest tests/unit/test_layers.py -q -k layer` -> `1 failed, 7 passed`: `test_layer_only_infrastructure_imports_psycopg` fails with `AssertionError: an infrastructure module must import psycopg` (no `infrastructure` module imports it yet); the seven existing layer tests pass.
    - `uv run --env-file .env pytest tests/integration/test_postgres_migrations.py -q` -> 1 error at collection: `ModuleNotFoundError: No module named 'ec_procurement_quality.domain.persistence_errors'`.
    - `uv run --env-file .env pytest tests/integration/test_postgres_ingestion_repository.py -q` -> 1 error at collection: `ModuleNotFoundError: No module named 'ec_procurement_quality.application.ingestion_repository'`.
    - `uv run --env-file .env pytest tests/integration/test_postgres_isolation.py -q` -> 1 error at collection: `ModuleNotFoundError: No module named 'ec_procurement_quality.infrastructure.postgres_settings'`.
    - `uv run --env-file .env pytest tests/integration/test_postgres_schema.py -q` -> `62 errors` at setup of every test: `migrations/0001_initial_schema.sql does not exist, so the migrated template cannot be built` (the database is reached; the template fixture stops before creating anything).
    - Default run, `uv run pytest -q` -> `Interrupted: 6 errors during collection` (nothing else runs). With `--continue-on-collection-errors`: `1 failed, 961 passed, 62 skipped, 6 errors`. The 961 earlier tests still pass, and the 62 skipped are the schema tests without `--env-file`, with the reason naming `uv run --env-file .env pytest tests/integration`.
    - Policy by command: `uv run pytest tests/integration/test_postgres_schema.py -q -rs` (no variables) -> `62 skipped` with that reason; the same with `CI=true` -> `62 errors` (`Failed: ... not set ...`), non-zero exit.
    - Harness check outside the repository (a scratch copy with a throwaway prototype of the schema and a stub runner, never committed): `test_postgres_schema.py` and `test_postgres_isolation.py` -> `67 passed`, so the conftest mechanics, the expected SQLSTATEs and the leftover check work against a real PostgreSQL 18.6. Afterwards a count of `pg_database` names starting with `ecpq_test_` -> `0`.
    - `uv run ruff format --check .` -> `89 files already formatted`. `uv run ruff check .` -> 6 `I001` import-order findings, all in the new test files and all caused by the F3 modules not existing yet (ruff treats a missing first-party module as third-party); in the scratch copy with empty stubs for the six modules, `ruff check tests` and `ruff format --check tests` pass. `uv run mypy .` -> 19 errors, all `import-untyped` on the missing F3 modules; with `Any` stubs in the scratch copy, `mypy tests` -> `Success`.
- [ ] **O3** (AC7, AC9, AC10, AC13) — executor: `src/ec_procurement_quality/domain/ingestion_audit.py` (`JsonValue`, `same_json`, `RunStatus`, `IngestionRun`, `AuditEvent`, the JSON object rule, and record equality through `same_json`) and `src/ec_procurement_quality/domain/persistence_errors.py` (the five errors). Standard library and `domain` only; strict `mypy`.
  - Tests: `tests/unit/test_ingestion_audit.py`, including the `same_json` cases of `execution-plan.md` § Validation AC7: `1`/`True`, `0`/`False`, `{"x": [1]}`/`{"x": [True]}`, `{"x": {"y": 0}}`/`{"x": {"y": False}}`, list order, key order, `{"x": [1, {"y": True}]}` with itself, and `ValueError` for a `float`. Also run and event equality through `same_json`, and the rejection of a plain `str` status.
  - Red: see O2 Red: `tests/unit/test_ingestion_audit.py` fails at collection with `ModuleNotFoundError` for `ec_procurement_quality.domain.ingestion_audit`.
  - Green: (to fill)
- [ ] **O4** (AC13) — executor: the port `IngestionRepository` in `src/ec_procurement_quality/application/ingestion_repository.py`, exactly as pinned. Standard library and `domain` only.
  - Tests: `tests/unit/test_layers.py` (existing `application` check), `satisfies_port` in `tests/integration/test_postgres_ingestion_repository.py` (checked by `mypy`)
  - Red: see O2 Red: `satisfies_port` is in `tests/integration/test_postgres_ingestion_repository.py`, which fails at collection with `ModuleNotFoundError` for `ec_procurement_quality.application.ingestion_repository`.
  - Green: (to fill)
- [ ] **O5** (AC5, AC6) — executor writes `migrations/0001_initial_schema.sql` (resolved question 6, option B). It holds the tables, constraints, indexes and triggers of `execution-plan.md` § Binding constraints "Schema", follows the authoring rules of § Runner contract, and has a short comment above each constraint group and trigger.
  - Tests: `tests/integration/test_postgres_schema.py`
  - Red: see O2 Red: `tests/integration/test_postgres_schema.py` -> 62 errors, `migrations/0001_initial_schema.sql does not exist`.
  - Green: (to fill)
  - [ ] Human review (step 4 of the order above): the human reviews the file line by line with the executor. Each constraint and trigger is explained in plain words: what it enforces, which AC it serves, and which schema test shows it.
    - Recorded result: (to fill: date, the human's decision, any change requested and how it was resolved)
- [ ] **O6** (AC1, AC2, AC3, AC4, AC11, AC12) — executor: `src/ec_procurement_quality/infrastructure/postgres_settings.py` (`PostgresSettings`) and `src/ec_procurement_quality/infrastructure/postgres_migrations.py` (`apply_migrations`, `MIGRATION_LOCK_KEY`) with the runner contract. Each file's transaction is atomic; the commit-in-flight outcome is documented, not tested.
  - Tests: `tests/unit/test_postgres_settings.py`, `tests/unit/test_postgres_migration_files.py`, `tests/integration/test_postgres_migrations.py`
  - Red: see O2 Red: the two unit files and `test_postgres_migrations.py` fail at collection with `ModuleNotFoundError` for `postgres_settings`, `postgres_migrations` and `persistence_errors`.
  - Green: (to fill)
- [ ] **O7** (AC7, AC8, AC9, AC10, AC11, AC12, AC13) — executor: `src/ec_procurement_quality/infrastructure/postgres_ingestion_repository.py` (`PostgresIngestionRepository`) with the adapter behavior, error mapping and output rules of § Binding constraints, including `start_run` comparing scopes with `same_json`.
  - Tests: `tests/integration/test_postgres_ingestion_repository.py`, including:
    - the AC7 JSON-type cases (`{"x": 1}` then `{"x": True}`, and the nested and repeated cases) -> `PersistenceIntegrityError`, or the stored run unchanged where the values match;
    - the two deterministic AC11 cases (backend terminated before the call; backend terminated while the transaction waits on a lock), each leaving nothing written.

    The commit-in-flight case is not tested (documented in intent AC11).
  - Red: see O2 Red: `tests/integration/test_postgres_ingestion_repository.py` fails at collection with `ModuleNotFoundError` for the F3 modules.
  - Green: (to fill)
- [ ] **O8** (AC15) — executor: the `postgres:18` service and the job environment in `.github/workflows/tests.yml` (resolved question 5), with a placeholder password that is not a secret.
  - Evidence: `gh pr checks <number>` and `gh run view <run-id> --log` on the F3 pull request (to fill)
- [ ] **O9** Migration (AC13, AC14, AC16): existing consumers keep working.
  - `tests/unit/test_layers.py` gains `test_layer_only_infrastructure_imports_psycopg`; the existing tests keep their names and behavior.
  - These stay unchanged: the F1 and F2 modules and tests, `compose.yaml`, `.env.example`, `.github/dependabot.yml`, ADR 0006 and ADR 0007.
  - No new file directly in `src/ec_procurement_quality/`.
  - The AC14 commands show the skip and fail policy.
  - `isolation` shows one database per test, the template unreachable, nothing left behind, and the configured database untouched.
  - Evidence: (to fill)
- [ ] **O10** Docs (AC17): `README.md` (including the query to remove leftover `ecpq_test_` databases), `AGENTS.md` § Current commands, `docs/architecture.md`, `CHANGELOG.md`. `CHANGELOG.md` includes the known limitations: unknown outcome after a connection lost during a commit, audit events not idempotent, and triggers that do not bind a superuser.
  - Evidence: (to fill)
- [ ] **O11** Broader suite vs baseline (AC16):
  - `uv run --env-file .env pytest --cov=ec_procurement_quality --cov-report=term-missing` passes with the 961 baseline tests plus the new ones, none skipped;
  - `uv run pytest -q` passes with the integration tests skipped and their reason shown;
  - `uv run ruff check .`, `uv run ruff format --check .` and `uv run mypy .` exit 0;
  - the doctor reports `0 warned, 0 failed`;
  - `git diff --check` is clean;
  - no `ecpq_test_` database remains after the run;
  - on the F3 pull request, `tests` and `feedback` are green.
  - Evidence: (to fill)
- [ ] **O12** Independent audit: verdict from `specs/postgres-persistence/audit.md` (to fill by the auditor).

## Working state
- Updated: 2026-10-13
- Outcome: O1 done and committed (`59f5253`); O2 written (working tree, not committed), awaiting the human's review at gate 2
- Phase: red phase written and verified red for the right reason; next is gate 2, then O3
- In progress: nothing
- Last command: `uv run mypy .` -> 19 errors, all `import-untyped` on the missing F3 modules (expected until O3 to O7); `.env` never read.
- Next step: the human reviews the red tests at gate 2; then the executor does O3 to O7 in order.
- Notes for the architect (spec gaps found while writing the tests; none blocks gate 2):
  - AC6 says `TRUNCATE` on `raw_evidence` and on `ingestion_run` -> SQLSTATE `23000`. PostgreSQL checks foreign keys before it fires `BEFORE TRUNCATE` triggers, so a plain `TRUNCATE` of a referenced table fails with `0A000` (probed on 18.6 in a scratch database, dropped afterwards). The tests expect `23000` for `TRUNCATE ... CASCADE` on those two tables and for a plain `TRUNCATE` of `observation` and `audit_event`; for a plain `TRUNCATE` of `raw_evidence` or `ingestion_run` they accept `23000` or `0A000` and require that no row changes.
  - O5's green needs the O6 runner: the migrated template is built with `apply_migrations` (as pinned), which O6 delivers after O5. The schema tests can run only once `postgres_migrations` exists, so O5 and O6 may need to be verified together.
  - Until O3 and O6 land, `uv run pytest -q` stops with collection errors for the six new files, because pytest aborts a run on collection errors. Ruff reports `I001` on those files until the modules exist (checked with stubs, see O2 Red).

## Finding responses
| Finding | Response | Evidence |
|---|---|---|
| P1 (review of Revision 1): AC11 claimed a lost connection writes nothing | Revision 2: AC11 separates atomicity (never partial) from the unknown outcome of a commit in flight. `PersistenceConnectionError` is no longer proof that nothing was written. The deterministic cases are kept and a lock-wait test is added for a loss while the transaction is open. The commit-in-flight case is documented, not tested, with the reason. F4 is told which operations are safe to repeat. The plan's runner and adapter rules, consumer rules and risks, and AC9 and AC17, are aligned | `intent.md` AC11; `execution-plan.md` § Runner contract, § Adapter behavior, § Proposed approach, § Consumers, § Risks, § Validation AC11 |
| P2 (review of Revision 1): isolation inconsistent (per-test database in AC14, shared session database in the plan) | Revision 2: one throwaway database per test is the contract. Runner tests start from `template0`. Every other test starts from a copy of a migrated session template, which refuses connections, is copied only from the admin connection, and is dropped at session end. The template constraint was checked on PostgreSQL 18.6. The leftover check covers the template | `intent.md` AC14; `execution-plan.md` § Guidance consulted (template probe), § Binding constraints "Tests", § Validation AC14 |
| P2 (review of Revision 1): JSON equality under-specified (`True == 1` in Python) | Revision 2: `same_json` is pinned in `domain`, with the reason recorded. `start_run`, `IngestionRun` equality and `AuditEvent` equality use it. A plain `str` status is rejected. Other comparisons checked: headers (`str`), status, sequence and size (`bool` already rejected by `Observation`), hashes and instants have no gap | `intent.md` AC7, AC9; `execution-plan.md` § Binding constraints, § Adapter behavior, § Validation AC7, AC9, AC10 |

## Checkpoint
Specs Revision 2 written on `docs/day-16-f3-postgres-persistence-specs`; nothing implemented. Revision 2 is approved. Resume at the test-writer's red phase (gate 2), then O1.
