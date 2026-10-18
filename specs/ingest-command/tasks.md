# Tasks: Ingest command (F4)

Revision: 2
Approval: Approved revision 2 by Vladimirjon on 2026-10-17 (the corrections F-1, F-2 and F-3 found during O1 to O5, including the F-3 read-back rule; no claim that F4 is implemented or tested). Revision 1 was approved by Vladimirjon on 2026-10-15 (gate 1: design, criteria and execution order)
Intent: [intent.md](intent.md) Revision 7 · Plan: [execution-plan.md](execution-plan.md) Revision 5

## Status
Gate 1 approved on 2026-10-15. O1 to O5 are done (gate 2 passed on 2026-10-17); O6a is next. The spec revision for the implementation findings F-1 to F-3 was approved by the human on 2026-10-17.
- **The spec set:**
  - `intent.md` Revision 7 (AC1 to AC25; Q1 to Q15, findings 1 to 22 and P-1 to P-5 decided by the human on 2026-10-14 and 2026-10-15; F-1 decided on 2026-10-16; F-2 and F-3 resolved by the architect and approved by the human on 2026-10-17);
  - `execution-plan.md` Revision 5;
  - this file, Revision 2.
- **Approval:** the human closed gate 1 on 2026-10-15 for `intent.md` Revision 6, `execution-plan.md` Revision 4 and this file Revision 1, and confirmed Q14 (reconciliation never restores `page-completed`). The approval covers design, criteria and execution order; it does not claim that F4 is implemented or tested. The Day 18 journal entry and the Day 17 correction are written. PR #24 was merged, and the implementation runs on `feat/ingest-command`. `intent.md` Revision 7, `execution-plan.md` Revision 5 and this file Revision 2 were approved by the human on 2026-10-17; each file's `Approval` line says so.
- **Revision 2 (2026-10-17):** follows intent Revision 7 and plan Revision 5. F-2 and F-3 are recorded as architect proposals in § Finding responses; the § Constraints line on `pyproject.toml` and O7 now expect the two `[tool.mypy]` keys of decision F-1 and no `uv.lock` diff; § Status and § Working state are updated. No outcome box was checked or unchecked, and the recorded evidence is unchanged.
- **Implementation:** the work is split into outcomes O1 to O11, with O6 split into O6a, O6b and O6c (decision T-2 of the human, 2026-10-15). O1 to O5 hold their recorded evidence in § Outcomes.

## Baseline
- **Base commit:** `2e6edcd` (`main`, "Merge pull request #23 from Vladimirjon/feat/postgres-persistence"), verified on Day 18, 2026-10-14 and 2026-10-15.
- **Branch:** the specs live on `docs/day-18-f4-ingest-command-specs`. The executor cuts the implementation branch (suggested `feat/ingest-command`) from `main` after the specs are merged.
- **Interpreter and tools:**
  - Python 3.13.9 (`uv run python --version`), uv 0.12.23, ruff 0.17.0.
  - PostgreSQL 18 in the Compose service `postgres` (`postgres:18`). It had exited and was started with `docker compose up -d --wait`.
- **Cwd:** the repository root, `ec-public-procurement-quality-monitor`. F4 is supported only from there (intent finding 21).
- **Commands:**
  - Install: `uv sync --locked`
  - Database: `docker compose up -d --wait`
  - Unit, with integration skipped: `uv run pytest`
  - All tiers locally: `uv run --env-file .env pytest`
  - CI form: `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing` (with the job's PostgreSQL service)
  - Lint and format: `uv run ruff check .` and `uv run ruff format --check .`
  - Type check: `uv run mypy .`
  - Readiness: `uv run node .sdd/doctor/run-doctor.mjs`
- **Verified results on Day 18 at `2e6edcd`:**
  - `uv sync --locked` -> ok;
  - `uv run pytest -q` without a database -> `1132 passed`, `175 skipped`;
  - `uv run --env-file .env pytest --cov=ec_procurement_quality --cov-report=term` -> `1307 passed`, 0 skipped, total coverage 96 %;
  - `uv run ruff check .` -> clean;
  - `uv run ruff format --check .` -> clean (97 files before the specs, 99 with `intent.md` and `execution-plan.md`; `tasks.md` holds no Python fence);
  - `uv run mypy .` -> success on 34 source files;
  - `uv run node .sdd/doctor/run-doctor.mjs` -> `31 ok`, 0 warned, 0 failed.
- **Pre-existing failures:** none.
- **Re-recorded on Day 19, 2026-10-16, at `6b34374`** (`main` after the merge of PR #24; branch `feat/ingest-command`). The Docker Desktop daemon was stopped, so it was started and then `docker compose up -d --wait` brought the service to healthy.
  - `uv sync --locked` -> ok;
  - `uv run pytest -q` without a database -> `1132 passed`, `175 skipped` (same as Day 18);
  - `uv run --env-file .env pytest --cov=ec_procurement_quality --cov-report=term` -> `1307 passed`, total coverage 96 % (same as Day 18);
  - `uv run ruff check .` -> clean; `uv run ruff format --check .` -> `100 files already formatted` (97 before the specs, plus the Python fences of `intent.md`, `execution-plan.md` and the Day 18 files; the Day 18 note said 99);
  - `uv run mypy .` -> success on 34 source files;
  - `uv run node .sdd/doctor/run-doctor.mjs` -> `31 ok`, 0 warned, 0 failed;
  - Python 3.13.9. Nothing differs from the Day 18 results except the base commit and the ruff file count.
- **Re-record the baseline.** At the start of implementation the executor re-runs every command above on the commit it branches from and records the results here, because `main` may have moved since Day 18.

## Constraints (from `AGENTS.md`, intent § Constraints)
- **No new dependency, infrastructure, framework or service** without the human's approval. None is expected: `argparse` is in the standard library, and `httpx` and `psycopg[binary]` are already approved. `uv.lock` stays unchanged, and `pyproject.toml` changes only by `explicit_package_bases = true` and `mypy_path = "src"` under `[tool.mypy]`, with their comment (decision F-1 of the human, 2026-10-16; intent AC18).
- **No secrets or real data:** no secrets, credentials, connection strings or real SERCOP data in code, tests, fixtures, logs or docs. Data is synthetic, URLs use `.invalid`, and passwords are markers such as `synthetic-password-marker`.
- **No real network:** tests never reach the network (guards in `tests/unit/ingest/conftest.py` and `tests/integration/ingest/conftest.py`), never touch the real `data/raw/`, and never touch the database named by `POSTGRES_DB` (intent AC19).
- **Integration tests need the Compose PostgreSQL** (`docker compose up -d --wait`) and run as `uv run --env-file .env pytest tests/integration`. Without it they skip locally and fail when `CI` is `true` (PT-13).
- **`.env` belongs to the human:** no agent reads, prints, copies or commits it. Commands load it only through `uv run --env-file .env`.
- **No edits outside F4's files:** no role edits `compose.yaml`, `.env.example`, `migrations/0001_initial_schema.sql`, the ADRs, `docs/glossary.md` or the F2 modules. No migration file is added (plan § No schema change).
- **One existing test edit only:** the one assertion added to `tests/integration/test_postgres_migrations.py` (decision P-1, O2). No other pre-F4 test file is edited.
- **The executor never edits tests** (`docs/learning/plan.md` § 3: the executor reaches green without touching the tests). Every F4 test is written by the test-writer, red first (decision T-1 of the human, 2026-10-15).

## Gates and review stops (harny pipeline, `docs/learning/plan.md` § 3)
- **Gate 1, the specs** (human).
  - The human reviewed and approved this spec set on 2026-10-15; the approval is recorded in the `Approval` line of `intent.md`, of the plan and of this file.
  - Required: every AC maps to an outcome and to a Validation row; no open question is left.
  - 🧑 At gate 1 close, the human's words went into `docs/learning/journal.md`: the correction of the Day 17 "Siguiente paso" and the Day 18 entry (done on 2026-10-15). This was a deliverable of the spec work (intent § Scope In), not of the code.
- **Review stops of O1 and O2** (human).
  - The human reviews the recorded red evidence of the M1 and M2 tests (AC22; AC23 and AC16 P-1), then the green evidence.
  - Right red reasons: the missing operation or class (`AttributeError`, `ImportError` inside a test), never a missing database, a typo or a socket attempt.
- **Gate 2, the F4 red tests that M3 makes expressible** (human, after O4).
  - The human runs the O4 tests and reads the errors. Each must fail for the right **functional** reason against the contracts that M3 created: `NotImplementedError` from the `run_ingest` stub, or an assertion on behavior the stub does not have.
  - These are wrong reasons:
    - import or collection errors;
    - a missing database;
    - a typo;
    - a socket attempt;
    - a touch of the real `data/raw/`.
  - The human also checks that:
    - the test files and `-k` tokens are those of the plan;
    - the doubles implement the extended ports;
    - no test reads `.env`.
  - Gate 2 does **not** cover the CLI composition; that is the stop M5-red.
  - The human starts O5 only after gate 2.
- **Stop M5-red, the CLI red tests** (human, after O6b; decision T-2 of the human, 2026-10-15).
  - The human runs the O6b tests against the O6a skeleton and reviews that each fails for a **functional** reason: `NotImplementedError` from the skeleton of `run_ingest_command`, or an assertion on exit codes, stdout, stderr or stored state that the skeleton cannot meet.
  - These are wrong reasons:
    - "module does not exist";
    - a collection or import error;
    - a missing database (the run is made with the Compose database up and `--env-file .env`);
    - a socket attempt;
    - a touch of the real `data/raw/`.
  - `tests/unit/test_cli.py` must pass unchanged.
  - The executor starts O6c only after this stop.
- **Gate 3, the audit** (human, after O10). The human accepts or rejects the auditor's verdict in `specs/ingest-command/audit.md` (APPROVED, APPROVED WITH RESERVATIONS or REJECTED). A rejection sends the spec back to the architect, never to a weaker criterion.

## Outcomes
Order and ownership. This follows `execution-plan.md` Revision 5 § Rollout order (unchanged since Revision 4) and the human's decisions T-1 and T-2 of 2026-10-15.

1. **O1 (M1)** and **O2 (M2)** land *with* their tests. The test-writer writes them first and records them red; the executor goes to green without editing them; each outcome ends at a review stop.
2. **O3 (M3)**, executor: the catalogue, the ports, the types, the `run_ingest` stub and `system_clock`. M3 has no `ingest_command` stub. Then the executor stops.
3. **O4**, test-writer, after M3: the F4 red tests that M3 makes expressible (unit tier, use case, catalogue, layers) and the doubles of `tests/unit/ingest/conftest.py`; then **gate 2**.
4. **O5 (M4) 🧑:** the human writes `run_ingest`.
5. **O6a, O6b and O6c (M5)**, the CLI composition, with a second red phase:
   - O6a: the executor writes the skeleton.
   - O6b: the test-writer writes the CLI red tests, then the **stop M5-red**.
   - O6c: the executor goes to green.
6. **O7** (existing consumers), **O8 (M6)** (docs, with 🧑 the journal) and **O9** (broader suite).
7. **O10 (auditor)**, then **gate 3**, then **O11** (documentation and archive).
8. **After merge:** the Day 20 live run (human, not an outcome, not a test).

Where an AC has a use-case part and a CLI part, the use-case part is tested in O4 and made green in O5, and the CLI part (exit code, stdout, stderr, the integration end-to-end through `run_ingest_command`) is tested in O6b and made green in O6c.

- [x] **O1** (AC22; AC20 for F1) — M1, the F1 listing, with its tests.
  - Tests, test-writer first: `tests/unit/test_local_disk_raw_evidence_store_listing.py`, the AC22 row of plan § Validation. Right red reason: `AttributeError` for `list_observation_sequences` on `LocalDiskRawEvidenceStore`.
  - Code, executor, without editing the tests: `src/ec_procurement_quality/application/raw_evidence_store.py` (`list_observation_sequences` in the port) and `src/ec_procurement_quality/infrastructure/local_disk_raw_evidence_store.py` (its implementation, read-only), exactly as plan § F1 port extension.
  - Shipped capability touched, `raw-evidence`: write-once publication, no deletions and integrity on read stay unchanged. These existing tests must keep passing unchanged:
    - `tests/unit/test_local_disk_raw_evidence_store.py`, including the typed assignment to `RawEvidenceStore`;
    - `tests/unit/test_raw_evidence.py`;
    - `tests/unit/test_content_hash.py`;
    - the store-shape test in `tests/unit/test_sercop_source.py`;
    - `tests/unit/test_layers.py`.
  - Red: recorded on 2026-10-16 (test-writer, re-run by the conductor). `uv run pytest tests/unit/test_local_disk_raw_evidence_store_listing.py -q` -> `25 failed`, 0 passed, 0 errors; every failure is `AttributeError: 'LocalDiskRawEvidenceStore' object has no attribute 'list_observation_sequences'` (no collection, import, database or socket error). `tests/unit/test_local_disk_raw_evidence_store.py` -> 60 passed. `ruff check` and `ruff format --check` clean (101 files). `uv run mypy .` reports 21 `attr-defined` errors, all of that missing method in the new file and nothing else (expected in the red phase; no `type: ignore`).
  - Green: recorded on 2026-10-16 (executor, re-run by the conductor), awaiting the human's review stop.
    - `uv run pytest tests/unit/test_local_disk_raw_evidence_store_listing.py -q` -> `25 passed`;
    - the F1 and layer tests (`test_local_disk_raw_evidence_store.py`, `test_raw_evidence.py`, `test_content_hash.py`, `test_sercop_source.py`, `test_layers.py`) -> `915 passed`, unedited;
    - `uv run --env-file .env pytest --cov=ec_procurement_quality --cov-report=term-missing -q` -> `1332 passed` (1307 + 25), total coverage 96 %;
    - `uv run mypy .` -> success on 35 source files; `ruff check` clean; `ruff format --check` -> 101 files;
    - `git diff --stat -- src tests`: only `application/raw_evidence_store.py` (+2) and `infrastructure/local_disk_raw_evidence_store.py` (+33); the test file is unchanged.
  - Done-check: the listing tests pass; the F1 tests above are unchanged and pass; the executor's `git diff --stat` touches only the two modules. Review stop.
- [x] **O2** (AC23; AC16 runner part and decision P-1; AC20 for F3) — M2, the F3 extension and `MigrationLockError`, with their tests.
  - Tests, test-writer first:
    - `tests/integration/ingest/conftest.py`, the part that `test_postgres_runs_and_exclusion.py` needs: the guard that allows `getaddrinfo` only for `POSTGRES_HOST`, and the session check that the real `data/raw/` is unchanged. It is extended in O6b;
    - `tests/integration/ingest/test_postgres_runs_and_exclusion.py`, the AC23 row;
    - `tests/unit/test_persistence_error_hierarchy.py`. It pins `MigrationLockError.__bases__ == (MigrationError,)`, six errors in total, and the four direct descendants of `PersistenceError` unchanged;
    - `tests/integration/test_postgres_migration_lock_error.py`. It checks that only a busy lock produces `MigrationLockError`, and that the non-lock cases are not one;
    - the one edit to an existing test: `test_runner_lock_held_elsewhere_fails_at_once_and_creates_nothing` in `tests/integration/test_postgres_migrations.py` gains `assert type(caught.value) is MigrationLockError`. `MigrationLockError` is imported **inside that test function**, so the rest of `test_postgres_migrations.py` still collects and runs while the class does not exist yet.
    - `tests/unit/test_ingestion_audit.py` is not edited.
    - Right red reasons: `AttributeError` for `list_runs` and `try_acquire_ingest_exclusion`; an `ImportError` of `MigrationLockError` or `INGEST_EXCLUSION_KEY` inside a test; the hierarchy assertions failing.
  - Code, executor, without editing the tests:
    - `src/ec_procurement_quality/application/ingestion_repository.py`: `list_runs` and `try_acquire_ingest_exclusion` in the port;
    - `src/ec_procurement_quality/infrastructure/postgres_ingestion_repository.py`: both operations and `INGEST_EXCLUSION_KEY`, a session advisory lock on the repository's own connection, an infrastructure detail never named in `application`;
    - `src/ec_procurement_quality/domain/persistence_errors.py`: `MigrationLockError(MigrationError)`;
    - `src/ec_procurement_quality/infrastructure/postgres_migrations.py`: raises it only at the busy-lock branch, with the same fixed message `another migration run holds the lock` (PS-12).
    - No migration file.
  - Shipped capability touched, `persistence`. These existing tests must keep passing:
    - `tests/unit/test_ingestion_audit.py`, unedited;
    - `tests/unit/test_postgres_settings.py`;
    - `tests/unit/test_postgres_migration_files.py`;
    - `tests/integration/test_postgres_migrations.py`, with only the assertion above added;
    - `tests/integration/test_postgres_schema.py`;
    - `tests/integration/test_postgres_ingestion_repository.py`, including `satisfies_port`;
    - `tests/integration/test_postgres_isolation.py`.
  - Red: recorded on 2026-10-16 (test-writer, re-run by the conductor).
    - `uv run --env-file .env pytest tests/integration/ingest/test_postgres_runs_and_exclusion.py -q` -> `22 failed`, 2 passed (the 2 are the guard proof tests, which need no new code). Reasons: `AttributeError` for `list_runs` (11), `AttributeError` for `try_acquire_ingest_exclusion` (6), `ImportError` of `INGEST_EXCLUSION_KEY` inside the test (5);
    - `uv run pytest tests/unit/test_persistence_error_hierarchy.py -q` -> `3 failed`, all `ImportError` of `MigrationLockError` inside the test;
    - `uv run --env-file .env pytest tests/integration/test_postgres_migration_lock_error.py tests/integration/test_postgres_migrations.py -q -k "lock or runner"` -> `9 failed`, 14 passed; all 9 are `ImportError` of `MigrationLockError` inside the test (3 busy-lock, 5 non-lock cases, the edited PS-4 test);
    - `uv run --env-file .env pytest -q` -> `34 failed`, 1333 passed (1332 + the 2 guard proof tests); the 34 are exactly the tests above; no collection error, no missing database, no socket attempt, no touch of the real `data/raw/`; 0 `ecpq_test_` databases left; `git diff --numstat -- tests/integration/test_postgres_migrations.py` -> `3 0` (additions only); `ruff check` and `ruff format --check` clean (105 files);
    - `uv run mypy .` now aborts with `Duplicate module named "conftest"`: see Working state, finding F-1.
  - Green: recorded on 2026-10-17 (executor, full suite re-run by the conductor), awaiting the human's review stop:
    - `uv run --env-file .env pytest tests/integration/ingest/test_postgres_runs_and_exclusion.py -q` -> `24 passed`;
    - `uv run pytest tests/unit/test_persistence_error_hierarchy.py -q` -> `3 passed`;
    - `uv run --env-file .env pytest tests/integration/test_postgres_migration_lock_error.py tests/integration/test_postgres_migrations.py -q -k "lock or runner"` -> `23 passed`;
    - broader `uv run --env-file .env pytest --cov=ec_procurement_quality --cov-report=term-missing` -> `1367 passed`, total coverage 96 %; without a database, `uv run pytest -q` -> `1161 passed`, `206 skipped`;
    - `uv run mypy .` -> success on 39 source files (with the F-1 setting); `ruff check` clean; `ruff format --check` -> 105 files; 0 `ecpq_test_` databases left; `git diff --numstat -- tests` -> `3 0` (the one PS-4 edit, additions only);
    - the line coverage reports as missed in `postgres_migrations.py` is the old `_raise_for(...)` of a lock that cannot be taken; the `raise MigrationLockError` line is covered.
  - Done-check: the tests pass, with no `ecpq_test_` database left; the hierarchy test pins the AC16 (P-1) points; every non-lock case is not a `MigrationLockError`. Review stop.
- [x] **O3** (AC12 id rule; AC13 catalogue and scope; AC18; decision P-4 helper) — executor, M3, the production contracts of `domain`, `application` and `infrastructure`.
  - Files:
    - `src/ec_procurement_quality/domain/ingestion_catalogue.py`: the enums, `IngestScope`, `WINDOWS_RESERVED_NAMES`, `validate_ingest_execution_id`, `pages_left_to_request`;
    - `src/ec_procurement_quality/application/ingest_ports.py`: `Clock`, `ExecutionIdSource`, `ClosableIngestionRepository`, `RepositoryOpener`, `IngestReporter`;
    - `src/ec_procurement_quality/application/ingest_use_case.py`: the pinned types `IngestRequest`, `ResumeRequest`, `IngestEnd` and `IngestOutcome`, and a `run_ingest` stub with the pinned signature that raises `NotImplementedError`;
    - `src/ec_procurement_quality/infrastructure/system_clock.py`: `SystemClock` and `RandomExecutionIdSource`.
  - Nothing in `interfaces` changes in M3 (decision T-2).
  - No test files: these contracts are tested in O4.
  - Check: `uv run mypy .` (strict flags on the new `domain` module); `uv run ruff check .`; `uv run pytest -q` stays at the O2 count.
  - Done-check: every name of plan § Public names and signatures for these four modules exists with the pinned signature. The executor stops; the test-writer takes O4.
  - Evidence, recorded on 2026-10-17 (executor, re-run by the conductor): four new files only (`domain/ingestion_catalogue.py`, `application/ingest_ports.py`, `application/ingest_use_case.py`, `infrastructure/system_clock.py`); `run_ingest` only raises `NotImplementedError`; `interfaces` unchanged. `uv run mypy .` -> success on 43 source files; `ruff check` clean; `ruff format --check` -> 109 files; `uv run pytest -q` -> `1161 passed`, `206 skipped` (the O2 count); `uv run --env-file .env pytest -q` -> `1367 passed`; `uv run pytest tests/unit -q -k layer` -> `8 passed`; no SQL, `advisory`, `pg_`, `.json`, `objects/` or `observations/` string under `application/`. No test file was added.
- [x] **O4** (use-case parts of AC1 to AC13, AC17 and AC24; AC18; the unit guard of AC19; the use-case parts of P-2, P-3, P-4 and P-5) — test-writer, after M3: the F4 red tests that M3 makes expressible, and the doubles; then gate 2.
  - **Why now:** the doubles are the test-writer's job, but they are written only once the production contracts they must implement exist (O1 to O3). That way the red phase shows the expected functional failures, not import or collection errors (decision of the human, 2026-10-15).
  - Files, all new:
    - `tests/unit/ingest/conftest.py`: the autouse socket guard, `InMemoryRawEvidenceStore`, `InMemoryIngestionRepository` (PS-7 to PS-9 rules, the exclusion as a shared flag), `FakeSource`, `FixedClock`, `ScriptedExecutionIds`, `RecordingReporter`, and the fault-injection wrappers of the plan's seams table (`PublishThenFailStore`, `FlakyRepository`, interrupt wrappers);
    - `tests/unit/ingest/test_ingestion_catalogue.py`;
    - `tests/unit/ingest/test_ingest_use_case.py`;
    - `tests/unit/ingest/test_ingest_layers.py`.
  - The unit rows of plan § Validation for AC1 to AC13, AC17 and AC24, asserting on `IngestOutcome`, `run_status`, the doubles' stores and the events; the AC8 (P-2), AC3 (P-3) and AC24 (`last-page-reached`) rows at the unit tier; the AC18 layer row.
  - **Excluded from O4, written in O6b:**
    - `tests/unit/ingest/test_ingest_command.py`;
    - `tests/integration/ingest/test_ingest_cli.py`;
    - every integration end-to-end row (`tests/integration/ingest/test_ingest_end_to_end.py`, `tests/integration/ingest/test_ingest_connection_loss.py`), because they go through `run_ingest_command` or assert exit codes and stdout;
    - every assertion on exit codes, stdout or stderr.
  - Right red reasons: `NotImplementedError` from the `run_ingest` stub; functional assertions that the stub cannot meet. The catalogue and layer tests already pass, because O3 delivered those contracts; record them as green.
  - Red: recorded on 2026-10-17 (test-writer, re-run by the conductor), awaiting gate 2.
    - `uv run pytest tests/unit/ingest -q` -> `268 failed`, `119 passed`, 0 errors (387 tests). `test_ingestion_catalogue.py` -> 111 passed (green, as planned); `test_ingest_layers.py` -> 8 passed (green); `test_ingest_use_case.py` -> 268 failed.
    - Reasons: all 268 failures are `NotImplementedError` from the `run_ingest` stub; no collection or import error, no missing database, no socket attempt, nothing under the real `data/raw/` (`data/raw` still empty), no `type: ignore`, no test reads `.env`.
    - O5 focused groups (they overlap, because the plan's tokens do; their union is the 268): group 1 -> 88 failed; group 2 -> 213 failed; group 3 -> 51 failed.
    - Tests per token: success 9, repeat 4, last_page 41, failure_with_response 16, failure_without_response 6, no_retry 6, storage 7, interrupt 5, unexpected 5, connection_loss 38, connection_loss_final_finish 12, resume 12, reconcile 21, closed_run 3, identity 13, chain 115, last_page_p3 6, chain_last_page 33, catalogue 111, scope 51, execution_id 45, layer 8.
    - `uv run pytest -q` -> `268 failed`, `1280 passed`, `206 skipped` (1161 + the 119 green); `ruff check` clean; `ruff format --check` -> 113 files; `uv run mypy .` -> success on 47 source files.
    - Soundness (scratchpad only, not in the repo): a throwaway reference `run_ingest` makes all 387 tests pass; 35 of 38 mutants are caught, the 3 survivors change no reachable behavior.
    - Files: `tests/unit/ingest/conftest.py` (guard, `InMemoryRawEvidenceStore`, `InMemoryIngestionRepository` with a shared `InMemoryDatabase`, `FakeSource`, `FixedClock`, `ScriptedExecutionIds`, `RecordingReporter`, `RepositoryOpenerDouble`, `FlakyRepository`, `PublishThenFailStore`, `RefusingStore`, `Seeder`, `TransportScript`, `Journal`, one `lab` fixture), `test_ingestion_catalogue.py`, `test_ingest_use_case.py`, `test_ingest_layers.py`.
  - Done-check: gate 2 passed on 2026-10-17, with the human's words recorded in § Working state: "rojo por el motivo correcto".
- [x] **O5** 🧑 (AC1 to AC11, use-case parts; AC12 use of the id check; AC13 details; AC17; AC24; decisions P-2, P-3, P-4 and P-5, use-case parts) — the human writes `run_ingest` in `src/ec_procurement_quality/application/ingest_use_case.py` by hand. This is Day 19, "Implementa tú el caso de uso en application".
  - Contract: the state machines of the plan's § Binding constraints, which are P, C, K, T, R, H and I, and nothing beyond them. P-2 is in C, P-3 in P step 5, P-4 in H steps 4 and 5, and the `last-page-reached` validation and coverage in H step 3.
  - The executor does not write this module's body. It may run the tests and report failures.
  - Tests: `tests/unit/ingest/test_ingest_use_case.py`, from O4.
  - Green: to record, focused by token:
    - `uv run pytest tests/unit/ingest -q -k "success or repeat or last_page or failure_with_response or failure_without_response or storage or interrupt"`;
    - `uv run pytest tests/unit/ingest -q -k "connection_loss or resume or reconcile or closed_run or identity or chain or no_retry or unexpected"`;
    - `uv run pytest tests/unit/ingest -q -k "connection_loss_final_finish or last_page_p3 or chain_last_page"`;
    - broader `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing`.
  - Done-check: every O4 test passes with the in-memory doubles; no test was edited to pass; `uv run ruff check .` and `uv run mypy .` are clean.
  - Evidence, recorded on 2026-10-17 (the human wrote `run_ingest` by hand; the conductor only ran the commands): `uv run pytest tests/unit/ingest -q` -> `387 passed`; the three `-k` groups -> `88 passed`, `213 passed`, `51 passed`; `uv run pytest -q` without a database -> `1548 passed`, `206 skipped`; `uv run --env-file .env pytest --cov=ec_procurement_quality --cov-report=term-missing -q` -> `1754 passed`, total coverage 95 % (`ingest_use_case.py` 91 %); `uv run mypy .` -> success on 47 source files; `ruff check` clean; `ruff format --check` -> 113 files; 0 `ecpq_test_` databases left; `git diff --stat -- tests` shows only the one PS-4 edit (+3 lines).
  - F-3, the author's reading (pending the architect): an `OSError` from the read-back after a failed `store` is treated like `EvidenceNotFoundError` (`storage-failed`, `raw-evidence`, run `failed`), as the cross-platform expectation of the AC6 (a) test needs. The branch that handles `store.read_observation` catches `EvidenceNotFoundError` and `OSError` only; what happens when the read-back raises `EvidenceIntegrityError` is not specified by the plan and is not covered by a test. The human takes it to the architect.
- [x] **O6a** (M5 skeleton; no AC turns green yet) — executor: only the importable skeleton of the CLI composition.
  - Files:
    - `src/ec_procurement_quality/interfaces/ingest_command.py` with `ClosableSource`, `IngestWiring`, `default_wiring` and `run_ingest_command`, with the signatures the plan fixes, each raising `NotImplementedError` (no behavior);
    - `src/ec_procurement_quality/interfaces/cli.py`: the optional `ingest` subparser is registered and `main(["ingest", ...])` reaches `run_ingest_command`. The subparser is not `required`, so CLI-2 keeps `unrecognized arguments: --bogus`.
  - Check: `uv run pytest tests/unit/test_cli.py -q` passes unchanged; `uv run pytest tests/unit -q -k layer` (`interfaces` imports neither `httpx` nor `psycopg`); `uv run mypy .`.
  - Done-check: the skeleton imports, and the test-writer takes O6b.
  - Evidence, recorded on 2026-10-17 (executor, re-run by the conductor): two files only (`interfaces/ingest_command.py` new, `interfaces/cli.py` modified); `default_wiring` and `run_ingest_command` only raise `NotImplementedError`; the optional `ingest` subparser is registered, a bare command prints usage on stderr and exits 2. `uv run pytest tests/unit/test_cli.py -q` -> `2 passed`, unchanged; `uv run pytest tests/unit -q -k layer` -> `16 passed`; `uv run mypy .` -> success on 48 source files; `ruff check` clean; `ruff format --check` -> 114 files; `uv run pytest -q` -> `1551 passed`, `206 skipped`. `main(["ingest", ...])` raises `NotImplementedError` from `default_wiring()`, which `main` evaluates before `run_ingest_command`; the O6b tests inject the wiring by replacing `default_wiring` with `monkeypatch`.
- [x] **O6b** (CLI and end-to-end parts of AC1 to AC4, AC6 stderr, AC7 exit 130, AC8, AC9, AC10, AC14, AC15, AC16 exit codes, AC19, AC24 and AC25; the exit and stdout parts of P-1, P-2, P-3 and P-5) — test-writer: the second red phase, then the **stop M5-red** (decision T-2 of the human, 2026-10-15).
  - Files:
    - `tests/unit/ingest/test_ingest_command.py`: usage, environment, exit codes, output, logger, paths;
    - `tests/integration/ingest/test_ingest_cli.py`: `cli_`, `root`, `migrations`;
    - `tests/integration/ingest/test_ingest_end_to_end.py`: `e2e_success`, `e2e_repeat`, `e2e_failure`, `e2e_resume`, `e2e_reconcile`, `e2e_last_page`, `e2e_chain_last_page`;
    - `tests/integration/ingest/test_ingest_connection_loss.py`: `connection_loss`, `final_finish`;
    - the rest of `tests/integration/ingest/conftest.py`: the `KillBeforeFinishRepository` and `KillAfterFinishRepository` seams and the composition helpers.
  - The rows of plan § Validation for AC14, AC15, AC16, AC19 and AC25, the integration halves of AC1, AC2, AC4, AC8, AC9 and AC10, and the integration halves of the AC8 (P-2), AC3 (P-3) and AC24 (`last-page-reached`) rows.
  - Right red reasons (reviewed at the stop M5-red): `NotImplementedError` from the skeleton of `run_ingest_command` or `default_wiring`, or a failing assertion on exit code, stdout, stderr or stored state. These are wrong reasons:
    - "module does not exist";
    - a collection or import error;
    - a missing database;
    - a socket attempt;
    - a touch of the real `data/raw/`.
  - Red: to record (test-writer):
    - `uv run pytest tests/unit/ingest/test_ingest_command.py -q`;
    - `uv run --env-file .env pytest tests/integration/ingest -q -k "e2e_ or connection_loss or final_finish or cli_ or root or migrations"`;
    - with counts and reasons.

  - Red: recorded on 2026-10-17 (test-writer, re-run by the conductor), awaiting the stop M5-red:
    - `uv run pytest tests/unit/ingest/test_ingest_command.py -q` -> `183 failed`, `7 passed`; `uv run --env-file .env pytest tests/integration/ingest -q -k "e2e_ or connection_loss or final_finish or cli_ or root or migrations"` -> `57 failed`, `4 passed`, 22 deselected; `uv run --env-file .env pytest -q` -> `240 failed`, `1766 passed`; `uv run pytest tests/unit/test_cli.py -q` -> `2 passed`, unchanged.
    - Reasons: all 240 failures are `NotImplementedError` from the O6a skeleton (183 unit, 57 integration); no assertion failure, collection or import error, missing database or socket attempt; the real `data/raw/` stays empty; 0 `ecpq_test_` databases left; no test reads `.env`; `mypy` (52 files), `ruff` and `ruff format` (118 files) clean.
    - The 11 tests that pass at the skeleton (7 unit, 4 integration) are the failures that `argparse` in `cli.py` already produces: `--year abc`, `--raw-root`, `--base-url` and the bare command.
    - Soundness (scratchpad only, not in the repo): a throwaway reference `run_ingest_command` and `default_wiring` makes all 240 tests pass; 20 mutants of it are each killed by at least one test.
    - Files: `tests/unit/ingest/test_ingest_command.py` (55 functions, 190 cases, each through `run_ingest_command` and `main`), the extended `tests/integration/ingest/conftest.py` (`IngestLab`, `PageScript`, `Kill*Repository` wrappers), `test_ingest_cli.py` (14), `test_ingest_end_to_end.py` (18) and `test_ingest_connection_loss.py` (7).
  - Done-check: the stop M5-red passed on 2026-10-17, with the human's words recorded in § Working state: "rojo por el motivo correcto".
- [x] **O6c** (AC7, AC8, AC10, AC14, AC15, AC16, AC19 and AC25 CLI parts; AC1 to AC4, AC9 and AC24 end-to-end parts; the exit and stdout parts of P-1, P-2, P-3 and P-5) — executor, M5, without editing the tests: the CLI composition to green.
  - Files: `src/ec_procurement_quality/interfaces/ingest_command.py`. It covers:
    - the environment;
    - absolute paths, resolved once at start;
    - the `httpcore` level guard;
    - `apply_migrations` before the repository, with `MigrationLockError` mapped to 1 and any other `MigrationError` to 2;
    - the exit-code table 0, 1, 2 and 130;
    - stdout and stderr;
    - the source closed in a `finally`.

    `cli.py` is final as well.
  - Shipped capability touched, `cli`: `tests/unit/test_cli.py` must pass unchanged (CLI-1, CLI-2, CLI-3).
  - Green: to record:
    - `uv run pytest tests/unit/ingest/test_ingest_command.py -q`;
    - `uv run --env-file .env pytest tests/integration/ingest -q`;
    - broader `uv run --env-file .env pytest --cov=ec_procurement_quality --cov-report=term-missing`.
  - Done-check: every F4 test passes; the guards record no socket attempt; the real `data/raw/` is unchanged; no `ecpq_test_` database is left; `uv run ec-procurement-quality --version` prints `ec-procurement-quality 0.1.0`.
  - Evidence, recorded on 2026-10-17 (executor, re-run by the conductor): two files only (`interfaces/ingest_command.py` implemented, `interfaces/cli.py` with the `parser.error` rules in an `_IngestParser` and `--first-page` without a default, mapped to 1). `uv run pytest tests/unit/ingest/test_ingest_command.py -q` -> `190 passed`; `uv run --env-file .env pytest tests/integration/ingest -q` -> `83 passed`; `uv run pytest tests/unit/test_cli.py -q` -> `2 passed`, unchanged; `uv run --env-file .env pytest --cov=ec_procurement_quality --cov-report=term-missing -q` -> `2006 passed`, 0 skipped, total coverage 95 % (`cli.py` 100 %, `ingest_command.py` 99 %, lines 98 and 202 missed); `uv run pytest -q` without a database -> `1741 passed`, `265 skipped`; `mypy` (52 files), `ruff`, `ruff format` (118 files) clean; 0 `ecpq_test_` databases; the real `data/raw/` is empty; `interfaces` imports neither `httpx` nor `psycopg`. Notes: the executor added one public helper, `request_from_arguments`, used by `cli.py` and `run_ingest_command`; an exception that escapes `run_ingest` after `run_started` gives exit 1 with its class name and no `<id> running` line (the plan prints that line only for `KeyboardInterrupt`).
- [x] **O7** Migration (AC20): existing consumers keep working.
  - The 1307 earlier tests pass.
  - The only edited pre-F4 test is the PS-4 assertion of O2, checked with `git diff main --numstat -- tests/integration/test_postgres_migrations.py`: additions only, 0 deletions.
  - The other pre-F4 test files, `migrations`, F2 modules and `uv.lock` show no diff: the AC20 row's `git diff main --stat -- ...` command is empty.
  - `git diff main -- pyproject.toml` shows only the two `[tool.mypy]` keys of decision F-1 (`explicit_package_bases = true`, `mypy_path = "src"`) and their comment, additions only, and no dependency line.
  - `git ls-files .env` prints nothing.
  - Evidence, recorded on 2026-10-17 (conductor): the long `git diff main --stat -- ...` list is empty (0 lines); `git diff main --numstat -- tests/integration/test_postgres_migrations.py` -> `3 0`; `git diff main -- pyproject.toml` shows only the two `[tool.mypy]` keys and their comment, additions only, no dependency line (decision F-1); `uv.lock` unchanged; `git ls-files .env` prints nothing; `git diff main --check` clean; `migrations/` holds `0001_initial_schema.sql` only; `compose.yaml`, `.env.example`, `docs/glossary.md` and the ADRs show no diff. The earlier tests pass: the full suite is 2006 passed. Source files changed versus `main`: the 12 listed for F4 (O1 to O3, O5, O6).
- [ ] **O8** Docs (AC21) — executor, M6, plus 🧑 the journal.
  - Files and contents:
    - `README.md`:
      - the `ingest` command, supported only from the repository root with `uv run --env-file .env ec-procurement-quality ingest ...`;
      - `--resume`;
      - the fixed `data/raw/`;
      - the optional `POSTGRES_HOST` and `POSTGRES_PORT`;
      - the exit codes 0, 1, 2 and 130;
      - how to end a stale session that holds the ingest exclusion, without the key's value;
      - the "nothing calls ... yet" sentences replaced.
    - `AGENTS.md` § Current commands: the ingest command.
    - `docs/architecture.md` § Open questions: the audit events and the scope answered for ingestion; § Infrastructure boundary updated.
    - `CHANGELOG.md` § Unreleased: the command (Added); the two port extensions and `MigrationLockError` (Changed); the known limitations of plan § Consumers.
  - `docs/glossary.md` stays unchanged unless the human decides otherwise.
  - 🧑 `docs/learning/journal.md`: the human writes the Day 19 and later entries in his own words. The Day 17 correction and the Day 18 entry belong to gate 1.
  - Check: `git grep -n -e "ingest" -- README.md AGENTS.md docs/architecture.md CHANGELOG.md`, then inspection against the AC21 list.
  - Evidence, recorded on 2026-10-17 (executor wrote the four files, the conductor reviewed the diff): `README.md` (new `## Ingesting` section, commands table row, the false "nothing calls ... yet" sentences replaced), `AGENTS.md` § Current commands, `docs/architecture.md` (§ Infrastructure boundary, § Open questions) and `CHANGELOG.md` § Unreleased (Added, Changed, known limitations; older entries amended with an explicit note). Checked: `uv run ec-procurement-quality --help` and `ingest --help` match the documented options; `ingest --resume Bad_Id` prints usage and exits 2; the stale-session SQL ran read-only without a syntax error; `ruff format --check` -> 118 files; `git diff --check` clean; no stale "nothing calls" / "library only" sentence left in `README.md`, `AGENTS.md` or `docs/architecture.md`. The box stays unchecked because the journal part is the human's (`docs/learning/journal.md`: the Day 19 entry is written; later days as they happen). Not verified: a live run against SERCOP (the docs say none was made); `pg_terminate_backend` against a real stale session; `docs/architecture.md` § Processing model still says the exact command syntax belongs to the first vertical flow (not false, outside the listed sections).
- [ ] **O9** Broader suite vs baseline (AC19, AC20). To record:
  - `uv run --env-file .env pytest --cov=ec_procurement_quality --cov-report=term-missing`: every test passes, 0 skipped, a `TOTAL` row; compare with the 1307 baseline;
  - `uv run pytest -q` without a database: integration tests skipped with the reason;
  - `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy .`, `uv run node .sdd/doctor/run-doctor.mjs` (`0 warned, 0 failed`), `uv run ec-procurement-quality --version`;
  - the `ecpq_test_` leftover count is `0`;
  - on the pull request, `tests` and `feedback` are green.
  - Evidence, recorded on 2026-10-17 (conductor), all but the pull request: `uv run --env-file .env pytest --cov=ec_procurement_quality --cov-report=term-missing -q` -> `2006 passed`, 0 skipped, `TOTAL` 95 % (1307 baseline + 699 F4 tests); `uv run pytest -q` without a database -> `1741 passed`, `265 skipped` (integration tests skipped with the reason); `ruff check` clean; `ruff format --check` -> 118 files; `mypy` -> 52 source files; doctor -> `31 ok`, 0 warned, 0 failed; `uv run ec-procurement-quality --version` -> `ec-procurement-quality 0.1.0`; 0 `ecpq_test_` databases; the real `data/raw/` is empty. The box stays unchecked until the pull request exists and its `tests` and `feedback` checks are green (that includes the Linux run of the AC6 (a) test).
- [ ] **O10** Independent audit: the verdict from `specs/ingest-command/audit.md`, written by the auditor. Then gate 3.
- [ ] **O11** Documentation and archive (after gate 3). `harny-document` stamps `Shipped:` in `intent.md`, then `harny-sync` archives `specs/ingest-command/` and updates the capability docs of plan § Ownership:
  - `cli`: new requirements for `ingest`; the CLI-2 usage line; Invariant 3 answered.
  - `persistence`: PS-4, PS-7 and PS-13 modified, six errors; a new requirement for listing runs and the exclusion; Invariant 8 retired; N5 noted.
  - `raw-evidence`: RE-12 and Invariant 7 modified; a new requirement for the listing.
  - `source-access`: no requirement change; R-7 and R-11 may be marked handled.
  - `project-toolchain`: the PT-6 and PT-10 counts.
  - A new `ingestion` capability (suggested prefix `IG-`).
  - Then it regenerates `specs/current/_index.md`.

### After merge (human, not an outcome)
- The Day 20 bounded live run, as decided in intent Q10: `uv run --env-file .env ec-procurement-quality ingest --year 2025 --buyer "EMPRESA ELÉCTRICA QUITO S.A. E.E.Q." --first-page 1 --last-page 3`, from the repository root, after gate 3 and the merge.
- It is a manual step outside the suite, and no test depends on it.
- It gives the first comparison of the live source with the observations (source-access U1).

## Carried reservations (from the plan's § Risks; for the executor and the auditor)
- **Persistence U1:** after a commit-in-flight loss the outcome is unknown. Covered by state machine C and the `FlakyRepository`, `KillBeforeFinishRepository` and `KillAfterFinishRepository` seams; the real wire-level case is still untested.
- **Persistence N5:** the reconciliation reads run in separate snapshots. This is safe under the ingest exclusion.
- **Raw-evidence N2:** an `OSError` from `store` may arrive after the file was published (P step 3, AC6 b).
- **Source-access R-6 and raw-evidence N3:** no exception chain or `__context__` is ever printed (AC15).
- **Source-access R-7:** `httpcore` is kept above `DEBUG` (AC15).
- **Source-access R-11:** one `SercopSource` per invocation, one thread.
- **Source-access U1:** the first live comparison happens at the Day 20 run.

## Working state
- Updated: 2026-10-17
- Outcome: O1 to O7 done; O8 documentation written (the journal part is the human's) and O9 evidence recorded except the pull request checks; the audit O10 waits for the human
- Phase: branch `feat/ingest-command`; O5 done: the human wrote `run_ingest` by hand; the day 19 closing (journal, commit, push) is made; no pull request is open
- In progress: nothing
- Last command: `uv run --env-file .env pytest --cov=ec_procurement_quality --cov-report=term-missing -q` -> 2006 passed, 95 % (2026-10-17)
- **Finding F-1 (decided by the human on 2026-10-16, option a; see § Finding responses; the specs are not changed):** `uv run mypy .` aborts with `Duplicate module named "conftest" (also at tests/integration/ingest/conftest.py)` and checks nothing. Cause: the plan requires `tests/integration/ingest/conftest.py` and `tests/unit/ingest/conftest.py` next to `tests/integration/conftest.py`, and no test directory has an `__init__.py`. This contradicts AC20 and the O3 check ("`uv run mypy .` clean") once the conftests exist. An `__init__.py` is no fix: two packages named `ingest` would break pytest's import. Candidate remedies, the human decides: (a) `explicit_package_bases = true` and `mypy_path = "src"` under `[tool.mypy]` in `pyproject.toml` (the test-writer checked it with `MYPYPATH=src uv run mypy --explicit-package-bases .`: 39 files checked, only the expected `attr-defined` red noise); (b) rename or relocate the conftests, which departs from plan § Tests. Either changes the spec set or `pyproject.toml`, so it goes through the architect and the human.
- **F-1 in the specs (Revision 2):** the consequence of the decision is now written into intent AC18 and AC20, the plan (§ Ownership, § Other constraints, § Consumers, the AC18 and AC20 rows), § Constraints and O7 of this file: `uv.lock` unchanged, and `pyproject.toml` changed only by the two `[tool.mypy]` keys and their comment.
- **Findings taken to the architect (original text kept; the responses are in § Finding responses, approved by the human on 2026-10-17):**
  - **F-2 (the human takes it to the architect):** plan § Public names and intent Q7 say the ingest execution id has 33 characters, but the pinned pattern `ingest-[0-9]{8}t[0-9]{6}z-[0-9a-f]{8}` gives 32. The code and the tests follow the pattern. The architect should fix the "33" (documentation only).
  - **F-3 (the human takes it to the architect):** plan P step 3 does not say what the use case does when `store.read_observation` itself raises `OSError` after a failed `store`. On Windows, a regular file at `observations` makes the read-back raise `EvidenceNotFoundError`; on Linux (CI) it is expected to raise `NotADirectoryError`, an `OSError` (reasoned from the code, not run on Linux). The AC6 (a) test asserts `storage-failed` (page 2, sequence 2, `raw-evidence`) unconditionally, so on CI the use case would have to treat that `OSError` like "not found". The architect decides; the human writes O5 knowing it.
  - **Assumptions of the test-writer where the plan is silent (check them at gate 2):** `outcome.message` contains the target id for `INVALID_TARGET` and for every chain refusal that ends `NOT_STARTED`; when `start_run` is lost and then repeated, the path continues with `storage-failed` (the scope's first page, sequence `None`) and no `run-started` is appended; a `KeyboardInterrupt` inside `start_run` gives `INTERRUPTED` with `execution_id` and `run_status` both `None`; a local-only observation 0 gives `sequence-gap` with sequence 0; the repositories are closed even when `KeyboardInterrupt` or `SystemExit` propagates; the write order has `reporter.run_started` between `start_run` and the `run-started` event, and the exclusion is the first write.
- Next step: the human decides O10: open the pull request (Auto-fix on, no auto-merge) so `tests` and `feedback` close O9, then the auditor writes `specs/ingest-command/audit.md` and the human closes gate 3; then O11 (document and archive) and, after the merge, the Day 20 live run

## Finding responses
| Finding | Response | Evidence |
|---|---|---|
| T-1 (architect, 2026-10-15): the plan's § Rollout says M1 and M2 land "with" their tests but not who writes them | Decided by the human on 2026-10-15: in O1 and O2 the test-writer writes the tests first, red, and the executor implements until green without modifying them | § Outcomes O1 and O2; § Constraints "The executor never edits tests" |
| T-2 (architect, 2026-10-15): after M3 the CLI tests could fail only because `interfaces/ingest_command.py` did not exist | Decided by the human on 2026-10-15, option 3: the CLI tests are a second red phase inside M5. O6a is the executor's importable skeleton (no behavior) and the `ingest` subparser. O6b is the test-writer's CLI and end-to-end tests with functional red evidence, then the stop M5-red. O6c is the executor's green, without editing the tests. M3 gets no `ingest_command` stub | § Outcomes O3, O4, O6a, O6b and O6c; § Gates and review stops |
| F-1 (test-writer, 2026-10-16): with `tests/integration/ingest/conftest.py` next to `tests/integration/conftest.py` and no `__init__.py` in the test folders, `uv run mypy .` aborts with `Duplicate module named "conftest"`; the same would happen with `tests/unit/ingest/conftest.py` | Decided by the human on 2026-10-16, option (a): `explicit_package_bases = true` and `mypy_path = "src"` under `[tool.mypy]` in `pyproject.toml`. The specs are not changed. Consequence to carry: the AC20 / O7 check that `pyproject.toml` shows no diff (`git diff main --stat -- ... pyproject.toml uv.lock`) now sees this one `[tool.mypy]` change (no dependency, `uv.lock` unchanged); the auditor and O7 must expect exactly these two keys, and only the mypy settings | `pyproject.toml` `[tool.mypy]`; `uv run mypy .` -> 58 `attr-defined` errors in 4 files over 39 checked files, all the expected red-phase noise (the missing `list_runs`, `try_acquire_ingest_exclusion`, `INGEST_EXCLUSION_KEY` and `MigrationLockError`), no other error |
| F-2 (raised during O5, 2026-10-17): plan § Public names and intent Q7 say the ingest execution id has 33 characters, but the pinned pattern `ingest-[0-9]{8}t[0-9]{6}z-[0-9a-f]{8}` gives 32 | Architect proposal (2026-10-17), approved by the human on 2026-10-17: a documentation correction to 32 characters in intent Q7 and plan § Public names and signatures. The pattern, the F1 pattern `[a-z0-9][a-z0-9-]{0,63}` (which a 32-character id satisfies) and the reserved-name rule are unchanged; code and tests need no change | intent Revision 7 Q7; plan Revision 5 § Public names and signatures; `7 + 8 + 1 + 6 + 1 + 1 + 8 = 32` |
| F-3 (raised during O5, 2026-10-17): plan P step 3 does not say what happens when the read-back `store.read_observation` itself raises `OSError` (Linux: `NotADirectoryError` for a file at `observations`) or `EvidenceIntegrityError` (a corrupt record) after a failed `store` | Architect proposal (2026-10-17), approved by the human on 2026-10-17, written from the human's reasoning of 2026-10-17: a read-back that raises `EvidenceNotFoundError`, `OSError` or `EvidenceIntegrityError` counts as not recorded: `storage-failed` (page, sequence, `raw-evidence`), run `failed`, exit 1. The use case cannot tell whether a file was published and cannot record what it cannot read; nothing is lost, because a resumption requests the page again and an unreadable or orphan file counts for nothing (RE-9, AC9). `KeyboardInterrupt`, `SystemExit` and `MemoryError` keep the State machine K handling (SA-11, Q11). The `OSError` half matches the current `run_ingest`; the `EvidenceIntegrityError` half needs the human's change to the catch and the new AC6 (d) tests | intent Revision 7 AC6 (d); plan Revision 5 § State machine P step 3, the seams table and the AC6 row; O5 note on F-3 |

## Checkpoint
O1 to O5 are done and pushed on `feat/ingest-command` (2026-10-17). Revision 7 of the intent, Revision 5 of the plan and Revision 2 of this file (F-2, F-3, F-1 in the specs) were approved by the human on 2026-10-17. Next: the test-writer adds the AC6 (d) tests, the human widens the read-back catch in `run_ingest`, and the executor starts O6a.
