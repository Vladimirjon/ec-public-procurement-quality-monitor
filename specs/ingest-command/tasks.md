# Tasks: Ingest command (F4)

Revision: 1
Approval: Approved revision 1 by Vladimirjon on 2026-10-15 (gate 1: design, criteria and execution order; no claim that F4 is implemented or tested)
Intent: [intent.md](intent.md) Revision 6 · Plan: [execution-plan.md](execution-plan.md) Revision 4

## Status
Awaiting intent approval.
- **The spec set:**
  - `intent.md` Revision 6 (AC1 to AC25; Q1 to Q15, findings 1 to 22 and P-1 to P-5 decided by the human on 2026-10-14 and 2026-10-15);
  - `execution-plan.md` Revision 4;
  - this file.
- **Approval:** the human reviewed and accepted intent Revision 6 and plan Revision 4 on 2026-10-15, and confirmed Q14 (reconciliation never restores `page-completed`). The `Approval` lines of all three files stay `Pending` until the human closes gate 1.
- **Nothing implemented yet:** no code, test or configuration has changed. The work is split into outcomes O1 to O11, with O6 split into O6a, O6b and O6c (decision T-2 of the human, 2026-10-15).

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
- **Re-record the baseline.** At the start of implementation the executor re-runs every command above on the commit it branches from and records the results here, because `main` may have moved since Day 18.

## Constraints (from `AGENTS.md`, intent § Constraints)
- **No new dependency, infrastructure, framework or service** without the human's approval. None is expected: `argparse` is in the standard library, and `httpx` and `psycopg[binary]` are already approved. `pyproject.toml` and `uv.lock` stay unchanged (intent AC18).
- **No secrets or real data:** no secrets, credentials, connection strings or real SERCOP data in code, tests, fixtures, logs or docs. Data is synthetic, URLs use `.invalid`, and passwords are markers such as `synthetic-password-marker`.
- **No real network:** tests never reach the network (guards in `tests/unit/ingest/conftest.py` and `tests/integration/ingest/conftest.py`), never touch the real `data/raw/`, and never touch the database named by `POSTGRES_DB` (intent AC19).
- **Integration tests need the Compose PostgreSQL** (`docker compose up -d --wait`) and run as `uv run --env-file .env pytest tests/integration`. Without it they skip locally and fail when `CI` is `true` (PT-13).
- **`.env` belongs to the human:** no agent reads, prints, copies or commits it. Commands load it only through `uv run --env-file .env`.
- **No edits outside F4's files:** no role edits `compose.yaml`, `.env.example`, `migrations/0001_initial_schema.sql`, the ADRs, `docs/glossary.md` or the F2 modules. No migration file is added (plan § No schema change).
- **One existing test edit only:** the one assertion added to `tests/integration/test_postgres_migrations.py` (decision P-1, O2). No other pre-F4 test file is edited.
- **The executor never edits tests** (`docs/learning/plan.md` § 3: the executor reaches green without touching the tests). Every F4 test is written by the test-writer, red first (decision T-1 of the human, 2026-10-15).

## Gates and review stops (harny pipeline, `docs/learning/plan.md` § 3)
- **Gate 1, the specs** (human).
  - The human reviews and approves this spec set and records the approval in the `Approval` line of `intent.md` (and of the plan and this file).
  - Required: every AC maps to an outcome and to a Validation row; no open question is left.
  - 🧑 At gate 1 close, the human's session writes in `docs/learning/journal.md`, in the human's words: the correction of the Day 17 "Siguiente paso" and the Day 18 entry. This is a deliverable of the spec work (intent § Scope In), not of the code.
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
Order and ownership. This follows `execution-plan.md` Revision 4 § Rollout order and the human's decisions T-1 and T-2 of 2026-10-15.

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

- [ ] **O1** (AC22; AC20 for F1) — M1, the F1 listing, with its tests.
  - Tests, test-writer first: `tests/unit/test_local_disk_raw_evidence_store_listing.py`, the AC22 row of plan § Validation. Right red reason: `AttributeError` for `list_observation_sequences` on `LocalDiskRawEvidenceStore`.
  - Code, executor, without editing the tests: `src/ec_procurement_quality/application/raw_evidence_store.py` (`list_observation_sequences` in the port) and `src/ec_procurement_quality/infrastructure/local_disk_raw_evidence_store.py` (its implementation, read-only), exactly as plan § F1 port extension.
  - Shipped capability touched, `raw-evidence`: write-once publication, no deletions and integrity on read stay unchanged. These existing tests must keep passing unchanged:
    - `tests/unit/test_local_disk_raw_evidence_store.py`, including the typed assignment to `RawEvidenceStore`;
    - `tests/unit/test_raw_evidence.py`;
    - `tests/unit/test_content_hash.py`;
    - the store-shape test in `tests/unit/test_sercop_source.py`;
    - `tests/unit/test_layers.py`.
  - Red: to record (test-writer). `uv run pytest tests/unit/test_local_disk_raw_evidence_store_listing.py -q`.
  - Green: to record (executor). The same command; broader `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing`; `uv run mypy .` for the typed assignment.
  - Done-check: the listing tests pass; the F1 tests above are unchanged and pass; the executor's `git diff --stat` touches only the two modules. Review stop.
- [ ] **O2** (AC23; AC16 runner part and decision P-1; AC20 for F3) — M2, the F3 extension and `MigrationLockError`, with their tests.
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
  - Red: to record (test-writer), with the commands below.
  - Green: to record (executor):
    - `uv run --env-file .env pytest tests/integration/ingest/test_postgres_runs_and_exclusion.py -q`;
    - `uv run pytest tests/unit/test_persistence_error_hierarchy.py -q`;
    - `uv run --env-file .env pytest tests/integration/test_postgres_migration_lock_error.py tests/integration/test_postgres_migrations.py -q -k "lock or runner"`;
    - broader `uv run --env-file .env pytest --cov=ec_procurement_quality --cov-report=term-missing`.
  - Done-check: the tests pass, with no `ecpq_test_` database left; the hierarchy test pins the AC16 (P-1) points; every non-lock case is not a `MigrationLockError`. Review stop.
- [ ] **O3** (AC12 id rule; AC13 catalogue and scope; AC18; decision P-4 helper) — executor, M3, the production contracts of `domain`, `application` and `infrastructure`.
  - Files:
    - `src/ec_procurement_quality/domain/ingestion_catalogue.py`: the enums, `IngestScope`, `WINDOWS_RESERVED_NAMES`, `validate_ingest_execution_id`, `pages_left_to_request`;
    - `src/ec_procurement_quality/application/ingest_ports.py`: `Clock`, `ExecutionIdSource`, `ClosableIngestionRepository`, `RepositoryOpener`, `IngestReporter`;
    - `src/ec_procurement_quality/application/ingest_use_case.py`: the pinned types `IngestRequest`, `ResumeRequest`, `IngestEnd` and `IngestOutcome`, and a `run_ingest` stub with the pinned signature that raises `NotImplementedError`;
    - `src/ec_procurement_quality/infrastructure/system_clock.py`: `SystemClock` and `RandomExecutionIdSource`.
  - Nothing in `interfaces` changes in M3 (decision T-2).
  - No test files: these contracts are tested in O4.
  - Check: `uv run mypy .` (strict flags on the new `domain` module); `uv run ruff check .`; `uv run pytest -q` stays at the O2 count.
  - Done-check: every name of plan § Public names and signatures for these four modules exists with the pinned signature. The executor stops; the test-writer takes O4.
- [ ] **O4** (use-case parts of AC1 to AC13, AC17 and AC24; AC18; the unit guard of AC19; the use-case parts of P-2, P-3, P-4 and P-5) — test-writer, after M3: the F4 red tests that M3 makes expressible, and the doubles; then gate 2.
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
  - Red: to record (test-writer). `uv run pytest tests/unit/ingest -q` and the focused tokens of O5, with counts and reasons.
  - Done-check: gate 2 passed, with the human's words recorded in § Working state.
- [ ] **O5** 🧑 (AC1 to AC11, use-case parts; AC12 use of the id check; AC13 details; AC17; AC24; decisions P-2, P-3, P-4 and P-5, use-case parts) — the human writes `run_ingest` in `src/ec_procurement_quality/application/ingest_use_case.py` by hand. This is Day 19, "Implementa tú el caso de uso en application".
  - Contract: the state machines of the plan's § Binding constraints, which are P, C, K, T, R, H and I, and nothing beyond them. P-2 is in C, P-3 in P step 5, P-4 in H steps 4 and 5, and the `last-page-reached` validation and coverage in H step 3.
  - The executor does not write this module's body. It may run the tests and report failures.
  - Tests: `tests/unit/ingest/test_ingest_use_case.py`, from O4.
  - Green: to record, focused by token:
    - `uv run pytest tests/unit/ingest -q -k "success or repeat or last_page or failure_with_response or failure_without_response or storage or interrupt"`;
    - `uv run pytest tests/unit/ingest -q -k "connection_loss or resume or reconcile or closed_run or identity or chain or no_retry or unexpected"`;
    - `uv run pytest tests/unit/ingest -q -k "connection_loss_final_finish or last_page_p3 or chain_last_page"`;
    - broader `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing`.
  - Done-check: every O4 test passes with the in-memory doubles; no test was edited to pass; `uv run ruff check .` and `uv run mypy .` are clean.
- [ ] **O6a** (M5 skeleton; no AC turns green yet) — executor: only the importable skeleton of the CLI composition.
  - Files:
    - `src/ec_procurement_quality/interfaces/ingest_command.py` with `ClosableSource`, `IngestWiring`, `default_wiring` and `run_ingest_command`, with the signatures the plan fixes, each raising `NotImplementedError` (no behavior);
    - `src/ec_procurement_quality/interfaces/cli.py`: the optional `ingest` subparser is registered and `main(["ingest", ...])` reaches `run_ingest_command`. The subparser is not `required`, so CLI-2 keeps `unrecognized arguments: --bogus`.
  - Check: `uv run pytest tests/unit/test_cli.py -q` passes unchanged; `uv run pytest tests/unit -q -k layer` (`interfaces` imports neither `httpx` nor `psycopg`); `uv run mypy .`.
  - Done-check: the skeleton imports, and the test-writer takes O6b.
- [ ] **O6b** (CLI and end-to-end parts of AC1 to AC4, AC6 stderr, AC7 exit 130, AC8, AC9, AC10, AC14, AC15, AC16 exit codes, AC19, AC24 and AC25; the exit and stdout parts of P-1, P-2, P-3 and P-5) — test-writer: the second red phase, then the **stop M5-red** (decision T-2 of the human, 2026-10-15).
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
  - Done-check: the stop M5-red passed, with the human's words recorded in § Working state.
- [ ] **O6c** (AC7, AC8, AC10, AC14, AC15, AC16, AC19 and AC25 CLI parts; AC1 to AC4, AC9 and AC24 end-to-end parts; the exit and stdout parts of P-1, P-2, P-3 and P-5) — executor, M5, without editing the tests: the CLI composition to green.
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
- [ ] **O7** Migration (AC20): existing consumers keep working.
  - The 1307 earlier tests pass.
  - The only edited pre-F4 test is the PS-4 assertion of O2, checked with `git diff main --numstat -- tests/integration/test_postgres_migrations.py`: additions only, 0 deletions.
  - The other pre-F4 test files, `migrations`, F2 modules, `pyproject.toml` and `uv.lock` show no diff: the AC20 row's `git diff main --stat -- ...` command is empty.
  - `git ls-files .env` prints nothing.
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
- [ ] **O9** Broader suite vs baseline (AC19, AC20). To record:
  - `uv run --env-file .env pytest --cov=ec_procurement_quality --cov-report=term-missing`: every test passes, 0 skipped, a `TOTAL` row; compare with the 1307 baseline;
  - `uv run pytest -q` without a database: integration tests skipped with the reason;
  - `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy .`, `uv run node .sdd/doctor/run-doctor.mjs` (`0 warned, 0 failed`), `uv run ec-procurement-quality --version`;
  - the `ecpq_test_` leftover count is `0`;
  - on the pull request, `tests` and `feedback` are green.
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
- Updated: 2026-10-15
- Outcome: none started
- Phase: gate 1 (the human reviews `intent.md` Revision 6, `execution-plan.md` Revision 4 and this file)
- In progress: nothing
- Last command: `uv run ruff format --check .` -> clean (architect, 2026-10-15)
- Next step: the human closes gate 1 and writes the journal entries (Day 17 correction, Day 18); then O1 (M1: the test-writer first, then the executor)

## Finding responses
| Finding | Response | Evidence |
|---|---|---|
| T-1 (architect, 2026-10-15): the plan's § Rollout says M1 and M2 land "with" their tests but not who writes them | Decided by the human on 2026-10-15: in O1 and O2 the test-writer writes the tests first, red, and the executor implements until green without modifying them | § Outcomes O1 and O2; § Constraints "The executor never edits tests" |
| T-2 (architect, 2026-10-15): after M3 the CLI tests could fail only because `interfaces/ingest_command.py` did not exist | Decided by the human on 2026-10-15, option 3: the CLI tests are a second red phase inside M5. O6a is the executor's importable skeleton (no behavior) and the `ingest` subparser. O6b is the test-writer's CLI and end-to-end tests with functional red evidence, then the stop M5-red. O6c is the executor's green, without editing the tests. M3 gets no `ingest_command` stub | § Outcomes O3, O4, O6a, O6b and O6c; § Gates and review stops |

## Checkpoint
Gate 1 is open. After the human's approval, resume at O1 (M1): the test-writer writes and records the listing tests red, then the executor makes them green.
