# Audit: PostgreSQL persistence (F3)

- Round: 1, 2026-10-14 (outcome O12).
- Reviewed: branch `feat/postgres-persistence` at `ee9ac87` (PR #23), base `main` at `e74a41a`. The working tree was clean before and after the audit. The only files changed are this one and the O12 line of `tasks.md`.
- Specs: `intent.md` Revision 2 with its AC6 clarification (approved at gate 2), `execution-plan.md` with its two clarifications of 2026-10-14 (AC6 `TRUNCATE` SQLSTATE: approved; `same_json(object, object)`: pending the human's review), and `tasks.md`.
- Read in full: the six new modules under `src/`, `migrations/0001_initial_schema.sql`, `tests/integration/conftest.py`, the four integration test files, the three new unit test files, the `tests/unit/test_layers.py` diff, the diffs of `pyproject.toml`, `uv.lock`, `.github/workflows/tests.yml`, `README.md`, `AGENTS.md`, `docs/architecture.md` and `CHANGELOG.md`.
- Evidence labels: `rerun` means the auditor ran it in this round. `reused` means it was taken from `tasks.md` and is still current. `unavailable` means it could not be checked. `.env` and the values of the `POSTGRES_*` variables were never read or printed.

## AC results

| AC | Status | Evidence |
|---|---|---|
| AC1 | PASS | `apply_migrations` (`postgres_migrations.py:292-314`) applies the pending files in lexical order. It records version, name, SHA-256 and `applied_at`, and returns the applied names. `test_runner_applies_*` (4 tests) pass: `("0001_initial_schema.sql",)`, then `()` with the rows unchanged. (rerun) |
| AC2 | PASS | Each file runs in one transaction with its bookkeeping row (`_apply_one`, `postgres_migrations.py:213-219`). On failure the runner rolls back and raises `MigrationError` naming the file, with fixed text (`:282-287`). `test_runner_failure_*` (2) pass, including the corrected rerun returning `("0002_b.sql", "0003_c.sql")`. (rerun) |
| AC3 | PASS | Name, numbering, empty, UTF-8 and missing-directory checks run before `open_connection` (`postgres_migrations.py:115-150, 301-302`). The recorded-row integrity check (`:233-258`) runs before any apply. Unit test `test_postgres_migration_files.py` (17) and `runner_integrity` (5) pass. (rerun) |
| AC4 | PASS | `pg_try_advisory_lock(MIGRATION_LOCK_KEY)` runs before the bookkeeping table is created (`:304-308`). The lock is released in `finally` (`:311-312`). `runner_lock` (4) pass: an immediate failure, no `schema_migration`, success after unlock, lock released after a success and after a failure. (rerun) |
| AC5 | PASS | Every column and check of § Schema is in `0001_initial_schema.sql:16-158`. `test_schema_rejects_invalid_row` (36 cases) covers every AC5 example plus the duplicate keys, and `test_schema_defaults_*` shows `{}`. All pass. (rerun) |
| AC6 | PASS | The triggers (`0001_initial_schema.sql:173-239`) raise `23000`. `append_only` (11 cases) requires `23000`. A plain `TRUNCATE` of `raw_evidence` or `ingestion_run` accepts `23000` or `0A000` with no row changed, as the approved clarification allows (`test_postgres_schema.py:477-494`). The `run_transition` tests pass. (rerun) |
| AC7 | PASS | `start_run`/`finish_run`/`read_run` (`postgres_ingestion_repository.py:252-344`) compare scopes with `same_json` after the `jsonb` read-back. `same_json` (`ingestion_audit.py:68-77`) keeps types apart at every depth. Unit `same_json`/`ingestion_run` and integration `run_` cases (incl. the Revision 2 JSON-type examples) pass. (rerun) |
| AC8 | PASS | `record_observation` (`:348-414`) does insert-if-absent of the evidence row, then insert-if-absent of the observation, then reads it back by join and compares the whole record. A difference raises an integrity error and rolls back. The `observation_` tests (19) pass, including the "no `<empty>` row" check and the `../escape` -> `ValueError` case. (rerun) |
| AC9 | PASS | `append_audit_event`/`list_audit_events` (`:449-499`). The database assigns the id, and events are listed by `event_id`. The `audit_event_` tests pass: two identical calls give two events, and `{"page": True}` is not `same_json` to `{"page": 1}`. (rerun) |
| AC10 | PASS | The domain rules run in `IngestionRun`/`AuditEvent`/`Observation`, and the PostgreSQL limits are checked before SQL (`:84-138, 355-362, 468-469`). `test_invalid_input_is_a_value_error_and_writes_nothing` (26 cases) and unit `invalid` pass. The auditor's probe also showed that an integer too long to write as JSON text gives `ValueError`. (rerun) |
| AC11 | PASS | Construction failures map to `PersistenceConnectionError` (`postgres_settings.py:86-111`). A lost connection sets `_lost` and every later call raises the same error (`:550-557, 581-589`). After `close()` a call raises `RuntimeError`. Both deterministic loss cases are tested and pass (`test_postgres_ingestion_repository.py:888-938`). The commit-in-flight case is documented in the module docstring and `CHANGELOG.md`, as agreed. (rerun) |
| AC12 | PASS | Every error is raised after its `except` block with fixed text. The `leak` tests (5) check message, `repr`, `args` and the formatted traceback, and walk `__cause__`/`__context__`. The `password` and `settings` unit tests pass. No logger is created in any F3 module. The CI server log shows no password marker. (rerun) |
| AC13 | PASS | `domain` imports only stdlib and `domain`, and `application` only stdlib and `domain`. `psycopg` is imported only in the three `infrastructure` modules. `uv run pytest tests/unit -q -k layer` -> `8 passed`. `uv run mypy .` -> `Success: no issues found in 34 source files`, `satisfies_port` included. (rerun) |
| AC14 | PASS | Unit-only run: `1126 passed, 172 skipped`, with the reason naming `uv run --env-file .env pytest tests/integration`, exit 0. With `CI=true`: `172 errors`, exit 1, no `skipped`. The `isolation` tests (5) pass. After all runs the `ecpq_test_%` count is `0`. (rerun) |
| AC15 | PASS | PR #23 at the final head `ee9ac87`: `gh pr checks 23` -> `feedback pass`, `tests pass`. Run `38604796727` log: `docker pull postgres:18`, `PostgreSQL 18.6` started, `postgres service is healthy`, then `Run tests`. All four integration files show dots and the run ends `1298 passed in 17.09s`, no skipped count. Coverage rows exist for the three new `infrastructure` modules (93%, 93%, 92%). (rerun) |
| AC16 | PASS | `uv sync --locked` and `uv lock --check` give `Resolved 25 packages`. The only lock additions are `psycopg` 3.3.6, `psycopg-binary` 3.3.6 and `tzdata` 2026.5. The `pyproject.toml` diff holds only the dependency line and the `integration` marker. The AC16-row unchanged files (plus `harny-feedback.yml`) have an empty diff, and the only test change outside the new files is `test_layers.py`. `--version` prints `ec-procurement-quality 0.1.0`. `git ls-files .env` is empty, the `datosabiertos`/`compraspublicas` grep finds nothing, and `git diff --check` is clean. The ruff, format, mypy and doctor results are under § Checks re-run. (rerun) |
| AC17 | PASS | `README.md` § Technologies and § Version 1 scope describe the schema, runner and adapter as a library that nothing calls. § Development commands has the integration command, the skip/fail policy and the leftover query. `AGENTS.md` § Current commands has the command. `docs/architecture.md` § Infrastructure boundary is updated, and § Open questions keeps the audit-event catalogue open. `CHANGELOG.md` § Unreleased lists the feature, the dependency and all three limitations. The README leftover query was **executed by the auditor** (see note N6). (rerun) |

## Binding-constraint compliance

| Constraint (`execution-plan.md` § Binding constraints) | Status | Evidence |
|---|---|---|
| Public names: `JsonValue`, `RunStatus`, `IngestionRun`, `AuditEvent`, JSON object rule | PASS | `ingestion_audit.py:21-195`. Frozen dataclasses with `eq=False`, an explicit `__eq__` through `same_json`, and `__hash__ = None`. A plain `str` status raises `ValueError` (`:129-132`). |
| `same_json(left: object, right: object) -> bool` | PASS against the current text; approval pending | `ingestion_audit.py:68`. The behavior matches every pinned case. The signature follows the 2026-10-14 clarification, which is still **pending the human's review** (`execution-plan.md:54, 355`; `tasks.md:177`). See F1. |
| Persistence errors (five, direct subclasses) | PASS | `persistence_errors.py:9-29`. Unit test `test_persistence_errors_are_direct_subclasses_of_persistence_error`. |
| `IngestionRepository` Protocol, exact signatures | PASS | `ingestion_repository.py:16-44` matches the pinned block, keyword-only markers included. |
| `PostgresSettings` | PASS (with an extra rule) | `postgres_settings.py:61-83`: keyword-only, frozen, `password` has `repr=False`, the bounds are as pinned, and a `bool` is rejected. It also rejects a lone surrogate, which the plan does not list (F3). |
| `apply_migrations`, `MIGRATION_LOCK_KEY` | PASS | `MIGRATION_LOCK_KEY = 0x6563_7071_6D69_6772` = 7305806652994316146, which is in the signed 64-bit range (unit test asserts the range). |
| `PostgresIngestionRepository(settings)`: connects when built, `close()`, context manager, "one thread at a time" | PASS | `postgres_ingestion_repository.py:232-248, 606-616`. |
| Schema (§ Schema table, indexes, triggers, comments) | PASS | `0001_initial_schema.sql`: every column and check in the table, both indexes, the append-only and transition triggers raising `23000`, and a comment per group and trigger. It was reviewed line by line by the human (`tasks.md:93-94`). |
| Runner contract: directory, checksum, lock, bookkeeping, integrity, applying, connection failures | PASS (with extra rules) | `postgres_migrations.py`. The file pattern `[0-9]{4}` is stricter than `\d{4}` and compliant. A file with NUL or only whitespace is also refused (F3). A lost connection maps to `PersistenceConnectionError` (`_raise_for`, `:222-227`), tested at construction. |
| Runner authoring rules (no transaction control, nothing that cannot run in a transaction, no lasting `SET`, no `schema_migration`) | PASS | Grep of `0001_initial_schema.sql`: the only `BEGIN` keywords (`:176`, `:189`) open PL/pgSQL bodies inside `$function$`, which the file's comment states. There is no `COMMIT`, `ROLLBACK`, `SAVEPOINT`, `SET`, `CONCURRENTLY`, `VACUUM`, `CREATE DATABASE` or `schema_migration`. Names are unqualified, and the file is stored with LF (`git ls-files --eol`: `i/lf w/lf`). |
| Adapter behavior: transactions, session UTC, validation first, `start_run`, `finish_run`, `record_observation`, `append_audit_event`, reads, connection, closed set of outcomes | PASS | See AC7 to AC11, and notes N3 and N4 on `SET TIME ZONE` and the list snapshot. `_transaction` rolls back on `BaseException` and re-raises non-driver exceptions unchanged (`:559-579`). |
| Errors and output (AC12) | PASS | No `from` clause anywhere in F3. Every driver exception is caught and dropped before the raise. No `logging` import in the F3 modules. |
| Tests: tiers, settings for tests, one database per test, template, leftover check, skip/fail, data | PASS | `conftest.py` follows each point: `ecpq_test_<hex>` names, `template0` for empty databases, template with `ALLOW_CONNECTIONS false`, copies only from the admin connection, `DROP ... WITH (FORCE)`, and the session-end check of `pg_database` and of the configured database's `pg_class`. Each new unit file has an autouse socket guard. |
| CI | PASS | `tests.yml` diff: a `postgres:18` service with a health check, the five-variable job env with a placeholder password, and the same job id and command. Gitleaks: `no leaks found`. |
| Layer imports, dependency, package root, unchanged files | PASS | See AC13 and AC16. No new file directly in `src/ec_procurement_quality/`, and no development dependency added. |

## Test coverage

| AC | Tests (file) | Status |
|---|---|---|
| AC1 | `test_runner_applies_*` (`tests/integration/test_postgres_migrations.py`) | PASS |
| AC2 | `test_runner_failure_*` (same file); `test_leak_migration_failure_*` (`test_postgres_ingestion_repository.py`) | PASS |
| AC3 | `test_migration_files_*` (`tests/unit/test_postgres_migration_files.py`); `test_runner_integrity_*` (integration) | PASS (the extra NUL and whitespace-only rules have no test, F3) |
| AC4 | `test_runner_lock_*` (integration) | PASS |
| AC5 | `test_schema_rejects_invalid_row`, `test_schema_defaults_*`, `test_schema_accepts_*`, `test_schema_assigns_*` (`tests/integration/test_postgres_schema.py`) | PASS |
| AC6 | `test_append_only_*`, `test_run_transition_*` (same file) | PASS |
| AC7 | `test_same_json_*`, `test_ingestion_run*` (`tests/unit/test_ingestion_audit.py`); `test_run_*` (integration repository file) | PASS |
| AC8 | `test_observation_*` (integration repository file) | PASS (no non-ASCII case, F4) |
| AC9 | `test_audit_event*` (unit and integration) | PASS |
| AC10 | `test_invalid_*` (unit and integration) | PASS |
| AC11 | `test_connection_*` (integration repository file) | PASS |
| AC12 | `test_leak_*` (integration); `test_password_*`, `test_settings_*` (`tests/unit/test_postgres_settings.py`) | PASS (the extra lone-surrogate rule has no test, F3) |
| AC13 | `test_layer_only_infrastructure_imports_psycopg` (`tests/unit/test_layers.py`); `test_satisfies_port_*` under `mypy` | PASS |
| AC14 | `test_isolation_*` (`tests/integration/test_postgres_isolation.py`); the `conftest.py` leftover check; policy by command | PASS |
| AC15 | none (workflow); CI run `38604796727` | PASS |
| AC16 | none (command checks) | PASS |
| AC17 | none (inspection) | PASS |

Red evidence: `tasks.md` O2 records a plausible red for every new file. The F3 modules or `migrations/0001_initial_schema.sql` did not exist yet, and the psycopg layer test failed with `an infrastructure module must import psycopg`. No test seam is dead: every conftest fixture is used. (reused)

### Tier Results

| Tier | Tests found | ACs verified | Setup matches § Validation | Ran | Status | Finding |
|---|---|---|---|---|---|---|
| unit | `test_ingestion_audit.py`, `test_postgres_settings.py`, `test_postgres_migration_files.py`, `test_layers.py` (164 new + 1 layer test) | AC3, AC7, AC9, AC10, AC12, AC13, AC14 (socket guards) | Yes: none needed beyond `uv sync --locked`, no dev dependency added | rerun: `164 passed`; `-k layer` `8 passed` | PASS | none (F3 notes two untested extra rules) |
| integration | `conftest.py` + 4 files (172 tests, all `integration`-marked) | AC1 to AC12, AC14 | Yes: Compose database, `--env-file .env`, the `integration` marker in `[tool.pytest]` as named, `psycopg` runtime dependency only | rerun: `172 passed` (full), focused `-k` selection `96 passed` | PASS | none |
| static (`mypy`) | `satisfies_port` annotation; strict `domain` | AC13 | Yes | rerun: `Success: no issues found in 34 source files` | PASS | none |
| command | AC14 policy commands, AC16 checks | AC14, AC16 | Yes | rerun (see § Checks re-run) | PASS | none |
| CI | `tests` job with `postgres:18` | AC15 | Yes: service, env, unchanged command and job id | rerun via `gh` at `ee9ac87` | PASS | none |
| manual | docs inspection | AC17 | Yes | rerun (inspection and the README query executed) | PASS | none |

No test sits at a tier that § Validation does not name, and no setup was added that the plan does not name.

## Notes on executor deviations and specific questions

- **N1. Lone surrogate in `PostgresSettings`** (`postgres_settings.py:40-48`). This rule is stricter than the pinned list, and it is justified. `open_connection` catches only `psycopg.Error`, so a `UnicodeEncodeError` raised while encoding a surrogate password would propagate with the password in its text. Rejecting it in the settings closes a real AC12 path. The rule has no test and has not been ratified (F3). The auditor's probe confirmed the `ValueError` names `password`. (rerun)
- **N2. NUL or whitespace-only migration files** (`postgres_migrations.py:110-111, 145-146`). These rules are stricter than the pinned list, and reasonable: the checksum covers the whole file, while a NUL would cut the statement. Neither rule has a dedicated test, and line 111 is uncovered (F3). The auditor's probe confirmed both give a `MigrationError` that names the file, with no connection. (rerun)
- **N3. Shared helpers in `postgres_settings.py`** (`open_connection`, `connection_was_lost`). This is compliant: § Ownership names three `infrastructure` modules and no fourth one was added. The module docstring states the extra role. A rename or split could be considered when F4 adds consumers (recommendation only).
- **N4. `SET TIME ZONE 'UTC'` after connect** (`postgres_settings.py:102-103`). This is a compliant alternative. § Adapter behavior pins the outcome (a UTC session, times read back in UTC) and not the mechanism, and `test_run_times_read_back_are_the_same_instants_in_utc` shows it. The `SET` is a session setting of the runner's or adapter's own connection, not of a migration file, so the authoring rule does not apply.
- **N5. Existence check then list under READ COMMITTED** (`postgres_ingestion_repository.py:434-443, 490-497`). Each list is one `SELECT` with its join, so "a list and its joins see one snapshot" holds. The earlier `SELECT 1` existence check runs in a separate statement snapshot. It cannot be invalidated, because `ingestion_run` refuses `DELETE` and `TRUNCATE` (AC6). Compliant. If F4 ever needs the existence check and the list in one snapshot, it can use `REPEATABLE READ` for reads (recommendation).
- **N6. README leftover-database query** (`README.md:164-170`). `tasks.md` O10 records it as not verified. The auditor verified it in the Compose server inside a throwaway database `ecpq_test_manual_b3316edf3ec8`: created from `template0`, set to `ALLOW_CONNECTIONS false` (the template's state), listed by the README `SELECT ... LIKE 'ecpq\_test\_%'`, and dropped by the README `DROP DATABASE "<name>" WITH (FORCE)`. The final count was `0`. This closes the O10 "Not verified" item. (rerun)
- **N7. AC6 clarification** (plain `TRUNCATE` -> `23000` or `0A000`). It was approved by the human at gate 2 (`intent.md:4, 132`). The schema comment, the test, the plan and the intent agree. The `CASCADE` and the `observation`/`audit_event` cases still require `23000` and pass.
- **N8. `docs/learning/journal.md`** changed on the branch in commit `e18d53d` (the human's session, before O1). It is outside F3's ownership, is not in the AC16 unchanged list, and is not part of the feature. No finding.
- **N9. Lint and type-check** were re-run at the caller's explicit request. The `harny-feedback` procedure (verify, do not re-run) was also followed: `.github/workflows/harny-feedback.yml` is present, its run `38604796606` at `ee9ac87` is green with `harny-feedback: 2 of 2 command(s) ran, 0 skipped.`, and gitleaks reports `no leaks found`.

## Findings

| Id | Severity | AC / constraint | Statement | Evidence | Closure condition | Status |
|---|---|---|---|---|---|---|
| F1 | MEDIUM | AC7, AC13; § Binding constraints "Public names" (`same_json`) | The implementation follows the `same_json(left: object, right: object)` clarification, which the spec records as pending the human's review and not yet approved. | `execution-plan.md:54, 355`; `tasks.md:177`; `ingestion_audit.py:68` | The human approves the clarification and the approval is recorded (execution-plan revision log and the `tasks.md` finding-response row). If the human rejects it, the architect revises the spec before merge. | Open |
| F2 | MEDIUM | Outcome completion (AC14, AC16; O2, O8, O11) | `tasks.md` has outcomes left unchecked or stale. O2 and O11 are still `[ ]` although their evidence is recorded. O11's last item, PR checks green on the final head, now holds (verified by the auditor at `ee9ac87`). § Working state and § Checkpoint still say the O8 CI evidence is pending. | `tasks.md:40, 141, 156, 161-165, 180` | The executor ticks O2 and O11 with their evidence, citing the final-head CI run `38604796727`/`38604796606`, and refreshes § Working state and § Checkpoint. | Open |
| F3 | LOW | AC3, AC12; § Binding constraints `PostgresSettings` and § Runner contract "Directory" | Three executor additions to the pinned rejection lists are not ratified in the plan and have no test: lone surrogate in settings, NUL in a migration file, whitespace-only migration file. | `postgres_settings.py:40-48` (coverage misses 44-45, 48); `postgres_migrations.py:110-111` (misses 111), `:145`; `tasks.md:103` | The architect records the three rules in `execution-plan.md` (or rejects them), and a unit test covers each one. | Open |
| F4 | LOW | AC8, AC10 | No test stores non-ASCII text (a realistic case for Spanish-language headers, URLs and scopes) or a JSON integer too long to write, so those adapter branches are uncovered. The auditor's probe shows both behave correctly. | `postgres_ingestion_repository.py:96, 120-122` (uncovered in the rerun coverage) | An integration case round-trips a non-ASCII URL, header value, scope and detail. Optionally, an AC10 case covers the over-long integer. | Open |
| F5 | LOW | `harny-feedback` (hook heeded) | The record does not show that the per-turn Stop/SubagentStop hook fired during implementation (it runs only with `.venv` on `PATH`). Only the CI gate and the reruns are shown. | `tasks.md` (no hook output recorded); `.claude/settings.json:132-147` | The human accepts the CI gate (`2 of 2 command(s) ran, 0 skipped`) and the clean reruns as sufficient, or hook output is recorded in later features. | Open |

There is no CRITICAL or HIGH finding.

## Checks re-run (round 1, 2026-10-14, at `ee9ac87`, Compose PostgreSQL 18 healthy)

| Command | Result |
|---|---|
| `uv run --env-file .env pytest --cov=ec_procurement_quality --cov-report=term-missing` | `1298 passed in 64.72s`, 0 skipped, exit 0. New modules: `ingestion_repository` 100%, `persistence_errors` 100%, `ingestion_audit` 97%, `postgres_ingestion_repository` 93%, `postgres_migrations` 93%, `postgres_settings` 92%. TOTAL 96%. |
| `uv run pytest -q -rs` (variables unset) | `1126 passed, 172 skipped`, each skip with the reason naming `uv run --env-file .env pytest tests/integration`, exit 0 |
| `CI=true uv run pytest tests/integration -q` (variables unset) | `172 errors` (`Failed: ... not set ...`), exit 1, no `skipped` |
| `uv run --env-file .env pytest tests/integration -q` | `172 passed` |
| Focused: `uv run pytest tests/unit -q -k layer`; the three new unit files; integration `-k "isolation or leak or connection or runner_ or schema_rejects or append_only or run_transition or satisfies_port"` | `8 passed`; `164 passed`; `96 passed` |
| `uv run ruff check .` | `All checks passed!` |
| `uv run ruff format --check .` | `95 files already formatted` |
| `uv run mypy .` | `Success: no issues found in 34 source files` |
| `uv run node .sdd/doctor/run-doctor.mjs` | `summary: 31 ok, 0 skipped, 0 warned, 0 failed` |
| `git diff --check` | clean (exit 0) |
| `uv lock --check`; `uv sync --locked` | `Resolved 25 packages`; `Checked 25 packages` |
| `uv run ec-procurement-quality --version` | `ec-procurement-quality 0.1.0` |
| `git ls-files .env`; `git grep -n -i -e datosabiertos -e compraspublicas -- tests` | empty; no match (exit 1) |
| `git diff main --stat` on the AC16 unchanged list (plus `harny-feedback.yml`) | empty |
| Leftover count (`docker compose exec -T postgres ... count(*) ... 'ecpq\_test\_%'`) after all runs and the probes | `0` |
| `gh pr checks 23`; `gh run view 38604796727 --log`; `gh run view 38604796606 --log` | `feedback pass`, `tests pass`; `postgres:18` and `1298 passed`, no skipped; `2 of 2 command(s) ran, 0 skipped`, `no leaks found` |
| Auditor probe (scratch script outside the repository, throwaway `ecpq_test_manual_<hex>` database, dropped) | Lone surrogate in settings -> `ValueError`; NUL and whitespace-only migration files -> `MigrationError` naming the file; non-ASCII scope, URL, header and detail round-trip and repeat as no-ops; an over-long JSON integer -> `ValueError`; probe database dropped |

## Audit log

| Round | Date | Verdict | Notes |
|---|---|---|---|
| 1 | 2026-10-14 | APPROVED WITH RESERVATIONS | All 17 ACs pass on rerun. No CRITICAL or HIGH finding. F1 (the `same_json` clarification awaits the human's approval) and F2 (`tasks.md` bookkeeping) should close before merge. F3 to F5 are LOW. The README leftover query was verified by the auditor (N6). |

## Final verdict

APPROVED WITH RESERVATIONS

**Summary**: The implementation meets AC1 to AC17 and every binding constraint, verified independently: 1298 tests passed locally with no skips, CI is green on `ee9ac87` with `postgres:18`, and nothing leaked or was left behind. The reservations are about governance and bookkeeping, not behavior.

**Critical Issues** (must fix before merge):
- None. Before merge, however, the human must approve (or reject) the `same_json(object, object)` clarification (F1), because the delivered signature rests on it.

**Warnings** (should fix, not blocking):
- F2: tick O2 and O11 in `tasks.md` with their evidence and refresh § Working state and § Checkpoint.
- F3: ratify the three extra rejection rules in `execution-plan.md` and give each a unit test.

**Recommendations** (nice to have):
- F4: add a non-ASCII round-trip integration case (and an over-long integer case).
- F5: record hook output in future features, or accept the CI gate as the evidence.
- N3: consider moving `open_connection` and `connection_was_lost` to a dedicated connection module when F4 adds consumers.
- N5: if F4 needs an existence check and a list in one snapshot, use `REPEATABLE READ` for reads.
