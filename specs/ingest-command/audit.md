# Audit: Ingest command (F4)

Auditor: `sdd-auditor` (outcome O10), round 1, 2026-10-18.
Reviewed: branch `feat/ingest-command` at `7603379` (clean working tree), PR #25
against `main`. The base is `main` at `6b34374`. Specs: `intent.md` Revision 7,
`execution-plan.md` Revision 5 and `tasks.md` Revision 2, all approved by the
human on 2026-10-17. Every changed file under `src/` and `tests/`, plus the four
documentation files, was read against the state machines P, C, K, T, R, H and I.
`application/ingest_use_case.py` (written by hand by the human, O5) was audited
like any other code.

Evidence labels: `rerun` means the auditor ran it in this round. `reused` means a
recorded result that is still current (the CI run of PR #25 at `7603379`).
`experiment` means a throwaway auditor test in the session scratchpad (not in the
repository), run against the repository's own doubles from
`tests/unit/ingest/conftest.py`. `unavailable` means it could not be checked.

## Final verdict

REJECTED

**Summary**: The feature is broad and mostly correct: 2006 tests pass, CI is
green, and the write order, idempotency, reconciliation, chain validation, P-2,
the exit-code table and the AC20 compatibility checks hold. But two reachable
interruption paths break AC7 and AC15, the guarantees of State machine K:

- a Ctrl+C while `record_observation` runs closes the run `failed` with the
  observation only in the local store (F-01);
- a Ctrl+C or `MemoryError` raised inside `store` before publication lets
  `EvidenceNotFoundError` escape `run_ingest`. The run stays `running` with no
  audit event, the exit code is 1 instead of 130, and stdout is empty although a
  run was created (F-02).

A malformed proxy or certificate setting in the environment is also reported as
an unexpected error with exit 1, after the migrations ran. This breaks the
binding constraint "report as configuration" and AC14 (F-03). As `tasks.md`
§ Gates says, this goes back to the architect: F-03 also needs a decision on
the plan's invocation order.

**Critical Issues** (must fix before merge):
- F-01 (CRITICAL, AC7, State machine K): `store_was_called` is cleared before `record_observation` returns, so the cleanup skips recording an observation that only the local store holds.
- F-02 (CRITICAL, AC7, AC15, State machine K, plan § `run_ingest`): the cleanup's read-back catches only `PersistenceError`, so a missing or unreadable observation makes an exception escape `run_ingest`.
- F-03 (HIGH, binding constraint intent § Constraints "ADR 0006 and source-access", AC14): a malformed `HTTPS_PROXY` or `SSL_CERT_FILE` gives exit 1, `unexpected error: <class>`, after `apply_migrations`.

**Warnings** (should fix, not blocking alone):
- F-04 (MEDIUM, AC15): an exception that escapes `run_ingest` after a run was created prints no `<id> <status>` line.
- F-05 (MEDIUM, AC11): a Ctrl+C that lands after `finish_run` committed makes the cleanup append `run-interrupted` to a finished run.
- F-06 (MEDIUM, AC24, State machine H step 2): an unreadable local record, or an `OSError` during the chain check, refuses the resumption with the class name, not a fixed message that names the execution id.
- F-07 (MEDIUM, AC6 (c), AC15, Q9): no progress line is ever written, stderr never names the refused operation, and two tests are vacuous.

**Recommendations** (nice to have):
- F-08 to F-12 (LOW): dead helper `_finish`; a stale "33 characters" docstring; spec gaps in reconciliation and the non-connection repository errors; untested branches; stale `tasks.md` state lines.

Next role: the architect, who decides whether any spec change is needed (F-03
order of invocation; F-05 and F-10 spec gaps). Then the test-writer writes red
tests for F-01 to F-07, the human corrects `run_ingest` (O5 module), and the
executor corrects `ingest_command.py`. Then a new audit round.

## AC results

| AC | Status | Evidence |
|---|---|---|
| AC1 | PASS | `-k success` 9 passed; `-k e2e_success` 2 passed; journal order store, record, event, finish asserted (`test_ingest_use_case.py:357`) (rerun) |
| AC2 | PASS | `-k repeat` 4 passed; `-k e2e_repeat` 2 passed (rerun) |
| AC3 | PASS | `-k last_page` 41, `-k last_page_p3` 6, `-k e2e_last_page` 2 passed; `ingest_use_case.py:1034` appends the event when `p >= pages` with no scope condition (P-3) (rerun) |
| AC4 | PASS | `-k failure_with_response` 16, `-k e2e_failure` 5 passed (rerun) |
| AC5 | PASS | `-k failure_without_response` 6 passed (rerun) |
| AC6 | PARTIAL | (a), (b) and (d) pass: `-k storage` 10 passed (rerun); (a) on Linux passed in CI (reused, run 39098935636). (c) records `storage-failed` (`postgresql`), but stderr never names the operation (F-07) |
| AC7 | FAIL | The listed seams pass (`-k "interrupt or exit_code"` 84 passed, rerun). Experiments E1/E3b: Ctrl+C inside `record_observation(2)` -> run `failed`, PostgreSQL sequences `(1,)`, local `(1, 2)` (F-01). E2/E3: Ctrl+C inside `store(2)` before publication -> `EvidenceNotFoundError` escapes, run `running`, no `run-interrupted`, exit 1, stdout empty (F-02) (experiment) |
| AC8 | PASS | `-k connection_loss` 38, `-k connection_loss_final_finish` 12 (unit); `test_ingest_connection_loss.py` 7, `-k final_finish` 4 (integration) passed (rerun) |
| AC9 | PASS | `-k resume` 24, `-k e2e_resume` 5 passed (rerun) |
| AC10 | PASS | `-k reconcile` 21, `-k e2e_reconcile` 6 passed. Spec gap noted in F-10 (rerun; experiment E7) |
| AC11 | PARTIAL | `-k closed_run` 3 passed (rerun). Experiment E5: `KeyboardInterrupt` after `finish_run(succeeded)` committed -> `run-interrupted` appended to the `succeeded` run (F-05) |
| AC12 | PASS | `-k "execution_id or identity"` 58 passed (rerun) |
| AC13 | PASS | `-k "scope or catalogue"` 111 passed; `assert_follows_catalogue` checks every detail (rerun) |
| AC14 | PARTIAL | `-k "usage or environment"` 66 passed (rerun). Experiment E10: `HTTPS_PROXY=http://[zz]:1`, an `ftp://` proxy, or a missing `SSL_CERT_FILE` -> exit 1, `unexpected error: InvalidURL` / `ValueError` / `FileNotFoundError`, after `migrate` was called (F-03) |
| AC15 | PARTIAL | `-k "output or logger"` 43 passed (rerun). A created run with an escaping exception prints no stdout line (E3, F-02, F-04); no progress lines (F-07) |
| AC16 | PASS | `-k migrations` 10 (integration CLI), `test_persistence_error_hierarchy.py` 3, lock and runner tests 23 passed; the PS-4 edit is additions only (`3 0`) (rerun) |
| AC17 | PASS | `-k no_retry` 6 passed; one request per page in the loop at `ingest_use_case.py:853-863` (rerun) |
| AC18 | PASS | `-k layer` 16 passed; grep of `application/` for SQL keywords, `advisory`, `pg_`, `objects/`, `observations/`, `.json` -> no match; `uv.lock` no diff; `pyproject.toml` only the two F-1 keys and comment; `mypy` 52 files clean (rerun) |
| AC19 | PASS | `uv run --env-file .env pytest tests/unit/ingest tests/integration/ingest -q` 663 passed; real `data/raw/` has 0 files before and after; 0 `ecpq_test_` databases left (rerun) |
| AC20 | PASS | 2006 passed (1307 baseline + 699); the AC20 `git diff main --stat` list is empty; `git ls-files .env` empty; `git diff main --check` clean; ruff, format, mypy, doctor `31 ok, 0 warned, 0 failed`; `--version` -> `ec-procurement-quality 0.1.0` (rerun) |
| AC21 | PASS | README `## Ingesting`, AGENTS.md § Current commands, architecture § Open questions and § Infrastructure boundary, CHANGELOG Added, Changed and Known limitations; no document claims a live run. The "stderr carries the progress" wording is folded into F-07 (rerun, inspection) |
| AC22 | PASS | `test_local_disk_raw_evidence_store_listing.py` 25 passed (rerun) |
| AC23 | PASS | `test_postgres_runs_and_exclusion.py` 24 passed (rerun) |
| AC24 | PARTIAL | `-k chain` 117, `-k chain_last_page` 33, `-k e2e_chain_last_page` 3 passed (rerun). Experiment E6: corrupt local record of a `page-completed` -> `NOT_STARTED` with message `EvidenceIntegrityError`, not naming the execution id (F-06) |
| AC25 | PASS | `-k root` 2 (integration), `-k "paths or environment"` 34 (unit) passed (rerun) |

Plan decisions and implementation findings:

| Item | Status | Evidence |
|---|---|---|
| P-1 | PASS | `postgres_migrations.py:310` raises `MigrationLockError` at the busy-lock branch only; `ingest_command.py:231-236` maps it to 1, any other `MigrationError` to 2 (rerun tests) |
| P-2 | PASS | `ingest_use_case.py:253-276` repeats `finish_run(SUCCEEDED)` with the same `finished_at` and appends no `storage-failed`; unit and integration `final_finish` rows pass |
| P-3 | PASS | `ingest_use_case.py:1034-1067` |
| P-4 | PASS | `ingest_use_case.py:673-689, 726-728`; `pages_left_to_request` in `ingestion_catalogue.py:172-185` |
| P-5 | PASS | `ingest_command.py:316-320` prints `<id> running` for an escaping `KeyboardInterrupt` |
| F-1 | PASS | `git diff main -- pyproject.toml`: only `explicit_package_bases = true`, `mypy_path = "src"` and three comment lines; no dependency line; `uv.lock` unchanged |
| F-2 | PARTIAL | Specs corrected; the code docstring at `ingestion_catalogue.py:155` still says "33 characters" (F-09) |
| F-3 | PASS | `ingest_use_case.py:901-907` catches `EvidenceNotFoundError`, `EvidenceIntegrityError` and `OSError` from the read-back; AC6 (d) tests pass for both errors; `KeyboardInterrupt` keeps K (`test_ingest_use_case.py:924`) |

## Binding-constraint compliance

| Constraint | Status | Evidence |
|---|---|---|
| Layer placement (plan § Layer placement, ADR 0001, AC18) | PASS | `application` modules import only the standard library, `domain` and `application`; `interfaces` imports no `httpx` or `psycopg` (layer tests 16 passed); no new file directly under `src/ec_procurement_quality/` |
| Public names and signatures | PASS | Every pinned name exists with the pinned signature (`ingestion_catalogue.py`, `ingest_ports.py`, `ingest_use_case.py:62-98, 731-740`, `ingest_command.py:77-106, 278-285`, the two port extensions, `INGEST_EXCLUSION_KEY`, `SystemClock`, `RandomExecutionIdSource`). Extra public helper `request_from_arguments` (recorded by O6c, compliant) |
| CLI arguments and configuration | PASS with F-03 | `cli.py:23-60`, `ingest_command.py:109-170`; the subparser is not required (CLI-2 kept) |
| Order of an invocation | PARTIAL | Steps 1 to 7 hold. A source construction failure (environment configuration) happens at step 4, after migrations, and is not reported as configuration (F-03) |
| Exit codes | PARTIAL | Table holds for every outcome. An escaping read-back error after Ctrl+C gives 1, not 130 (F-02) |
| Output (AC15) | PARTIAL | F-04 (no line for a created run when an exception escapes), F-07 (no progress) |
| Audit details (closed catalogue) | PASS | `assert_follows_catalogue` in every main path; experiment E8 shows `unexpected-error` with a project error's class name for a refused append (spec silent, F-11) |
| State machine P | PASS | Write order, no-response path, read-back rule (F-3), decide step, P-3 |
| State machine C | PASS | `_PersistenceSession` (`ingest_use_case.py:107-185`): one new connection, the exclusion taken again, safe repeats only, the append re-checked with `list_audit_events` (type, `same_json` detail, instant), no third connection; no reconnect before `start_run` |
| State machine K | FAIL | F-01, F-02; F-05 is a race K does not address |
| State machine T | PASS | `ingest_use_case.py:762-775`, before reconciliation, writes nothing |
| State machine R | PASS with F-10 | `ingest_use_case.py:433-559`: the problem order, the gap checked after verification, local-only records, stop at the first problem |
| State machine H | PARTIAL | Steps 1 to 5 are implemented, including the coverage and sentinel rules (`ingest_use_case.py:636-728`). Refusals from `EvidenceIntegrityError` or `OSError` lose the fixed message (F-06) |
| State machine I | PASS | `ingest_use_case.py:350-370`: three draws, both ports checked, under the exclusion |
| F1 port extension | PASS | `local_disk_raw_evidence_store.py:156-184` is read-only, validates the id first, raises `EvidenceIntegrityError` for a bad entry, returns `()` when the directory is absent |
| F3 port extension | PASS | `postgres_ingestion_repository.py:353-393`: try-only session lock, the flag stops a stacked acquisition, cleared on loss; no key or SQL in messages |
| No schema change | PASS | `migrations/` holds `0001_initial_schema.sql` only, no diff |
| No dependency (AGENTS.md, PT-11) | PASS | `uv.lock` no diff; `pyproject.toml` F-1 keys only |
| Intent § Constraints, ADR 0006 and source-access: "report a malformed proxy or certificate setting in the environment as configuration" | FAIL | F-03 |
| Intent § Constraints, R-6 and N3: no chain or `__context__` printed | PASS | Only `str()` of project errors and class names are printed (`ingest_command.py:232-239, 316-323`) |
| Intent § Constraints, R-7: `httpcore` above `DEBUG` | PASS | `ingest_command.py:173-187`; `-k logger` passed |
| Intent § Constraints, SA-13 and PS-13: one source, at most two repositories, all closed | PASS | `ingest_command.py:259-275` closes the source in a `finally`; `ingest_use_case.py:1114-1115` closes the current repository; `_reconnect` closes the lost one |
| Tests: guards, no real `data/raw/`, throwaway databases | PASS | Guard proof tests pass; `data/raw/` stays empty; 0 leftover databases |
| `.env` never read by code or committed | PASS | `git ls-files .env` empty; no `.env` read under `src/` (`_settings_from` reads the mapping only) |

## Test coverage

| AC | Tests (file) | Status |
|---|---|---|
| AC1 | `success` in `tests/unit/ingest/test_ingest_use_case.py`; `e2e_success` in `tests/integration/ingest/test_ingest_end_to_end.py`; `exit_code_0` in `tests/unit/ingest/test_ingest_command.py` | PASS |
| AC2 | `repeat` (unit); `e2e_repeat` (integration) | PASS |
| AC3 | `last_page`, `last_page_p3` (unit); `e2e_last_page` (integration) | PASS |
| AC4 | `failure_with_response` (unit); `e2e_failure` (integration) | PASS |
| AC5 | `failure_without_response` (unit); `e2e_failure_without_a_response...` (integration) | PASS |
| AC6 | `storage` (unit, 10 cases) | PASS for (a), (b), (d); the (c) stderr part has only a vacuous test (F-07) |
| AC7 | `interrupt` (unit), `exit_code_130` (unit command) | PASS as written; MISSING: a `KeyboardInterrupt` inside `record_observation`, and one inside `store` before publication (F-01, F-02) |
| AC8 | `connection_loss`, `connection_loss_final_finish` (unit); `test_ingest_connection_loss.py` (integration) | PASS |
| AC9 | `resume` (unit); `e2e_resume` (integration) | PASS |
| AC10 | `reconcile` (unit); `e2e_reconcile` (integration) | PASS |
| AC11 | `closed_run` (unit) | PASS as written; MISSING: the finished-before-interrupt race (F-05) |
| AC12 | `execution_id` (`test_ingestion_catalogue.py`), `identity` (unit) | PASS |
| AC13 | `scope`, `catalogue`, plus `assert_follows_catalogue` in the use-case tests | PASS |
| AC14 | `usage`, `environment` (unit command); `cli_invalid_*` (integration) | PASS as written; MISSING: a malformed proxy or certificate setting (F-03) |
| AC15 | `output`, `logger` (unit command) | PASS as written; MISSING: a created run plus an escaping exception (F-04) |
| AC16 | `migrations` (`test_ingest_cli.py`); `test_persistence_error_hierarchy.py`; `test_postgres_migration_lock_error.py`; edited PS-4 test | PASS |
| AC17 | `no_retry` (unit) | PASS |
| AC18 | `tests/unit/ingest/test_ingest_layers.py` (`layer`); `mypy`; source closed once (`test_exit_code_one_source_is_built_and_closed_once...`) | PASS |
| AC19 | guards and proof tests in both `conftest.py` files; the session check of `data/raw/` | PASS |
| AC20 | the existing 1307 tests, unedited except the PS-4 assertion | PASS |
| AC21 | none (inspection) | PASS (inspection) |
| AC22 | `tests/unit/test_local_disk_raw_evidence_store_listing.py` | PASS |
| AC23 | `tests/integration/ingest/test_postgres_runs_and_exclusion.py` | PASS |
| AC24 | `chain`, `chain_last_page` (unit); `e2e_chain_last_page` (integration) | PASS as written; MISSING: a refusal from an unreadable local record, with its message (F-06) |
| AC25 | `root` (integration CLI); `paths`, `environment` (unit command) | PASS |

Coverage from the broader command: total 95 % locally and 96 % in CI.
`ingest_use_case.py` is at 91 %, with these lines missed: 130-132, 180-181,
224-230 (dead `_finish`), 821-822, 841-842, 888-889, 913-933 (a published
read-back that PostgreSQL then refuses), 949-950, 978-979, 1007-1008,
1024-1025, 1043-1046, 1057-1061 and 1086. `ingest_command.py` is at 99 %; line
202, `progress`, is never called (F-07).

Red evidence (reused from `tasks.md`): O1, O2, O4 and O6b each record red for a
functional reason, and the human accepted gate 2 and the stop M5-red. The O4
and O6b soundness notes (reference implementations and mutants) are the
test-writer's, not re-run here.

### Tier Results

| Tier | Tests found | ACs verified | Setup matches § Validation | Ran | Status | Finding |
|---|---|---|---|---|---|---|
| unit | `tests/unit/ingest/` (580 tests), `test_local_disk_raw_evidence_store_listing.py` (25), `test_persistence_error_hierarchy.py` (3) | AC1 to AC18, AC22, AC24, AC25 | yes: doubles, `tmp_path`, autouse guard; no setup beyond plan | rerun: every focused `-k` row, all passed | PASS | Coverage gaps F-01, F-02, F-03, F-04, F-05, F-06, F-07 (MISSING cases above) |
| integration | `tests/integration/ingest/` (83 tests), `test_postgres_migration_lock_error.py`, the PS-4 edit | AC1 to AC4, AC8 to AC10, AC16, AC19, AC23 to AC25 | yes: PT-13 throwaway databases, admin connection, guard that allows the configured host only, `data/raw/` session check | rerun with `--env-file .env`, all passed; CI reused | PASS | none |
| static | `uv run mypy .` | AC18 | yes: the F-1 keys are the only config change | rerun: success on 52 files | PASS | none |
| command | ruff, format, mypy, doctor, `--version`, git diff checks | AC20 | yes | rerun: all clean | PASS | none |
| manual | documentation inspection | AC21 | n/a | rerun (inspection) | PASS | F-07 wording |

No test exists at a tier that § Validation does not name. No unnamed setup was
added: the only configuration change is the two `[tool.mypy]` keys approved by
F-1.

## Findings

| Id | Severity | AC / constraint | Finding and evidence | Failure scenario | Closure condition | Status |
|---|---|---|---|---|---|---|
| F-01 | CRITICAL | AC7 (second example), State machine K bullet 1 | `ingest_use_case.py:952-954` sets `store_was_called = False` right after `store` returns, before `record_observation` is called at 956-959. The cleanup at 386-389 records the local observation only when `locally_stored` is true | Ctrl+C arrives while the `record_observation` round trip for page 2 is in flight (the most likely moment, because it waits on the database). The cleanup appends `run-interrupted`, closes the run `failed`, and never records observation 2. Experiment E1/E3b: exit 130, stdout `<id> failed`, PostgreSQL sequences `(1,)`, local `(1, 2)`. The run is finished, so reconciliation (only `running` runs) never repairs it: the stores disagree for good | The observation is read back and recorded whenever the interrupt comes after `store` was called and before `record_observation` returned; a red-first unit test with `faults.interrupts("record_observation", detail="2")` shows PostgreSQL holding sequence 2 before `finish_run(FAILED)` | Open |
| F-02 | CRITICAL | AC7 (exit 130, `run-interrupted`), AC15 (stdout line), plan § `run_ingest` ("returns an outcome for every ending except ..."), K ("record a found observation") | `_cleanup_after_exception` (`ingest_use_case.py:386-402`) catches only `PersistenceError`. Its `store.read_observation` raises `EvidenceNotFoundError` (or `EvidenceIntegrityError`, `OSError`) when nothing was published. `store_was_called` is already true (893) when `store` is interrupted | Ctrl+C or `MemoryError` inside `store` for page 2, before the file is published. `EvidenceNotFoundError` escapes `run_ingest`; the run stays `running` with no `run-interrupted` or `unexpected-error`; `ingest_command.py:321-323` prints `unexpected error: EvidenceNotFoundError` and returns 1 (not 130), and stdout is empty although a run was created (experiments E2, E3, E4) | A read-back that finds nothing, or cannot read, is treated as "not found" in the cleanup, which then appends its event and closes the run; tests for `KeyboardInterrupt` and `MemoryError` from a store that has not published show `INTERRUPTED` (exit 130, `<id> failed`) and `RUN_FAILED` (exit 1, `<id> failed`) | Open |
| F-03 | HIGH (blocking: unmet binding constraint) | Intent § Constraints "ADR 0006 and source-access" (report a malformed proxy or certificate setting as configuration), AC14 | `ingest_command.py:256-259` runs `_migrate` and only then `wiring.make_source`. A construction error from the environment (`httpx.InvalidURL`, `ValueError`, `FileNotFoundError`, as recorded by the F2 plan) falls into `except Exception` at 321-323 | `HTTPS_PROXY=http://[zz]:1` (or an `ftp://` proxy, or a missing `SSL_CERT_FILE`) in the operator's environment: migrations are applied to the real database, then exit 1 with `unexpected error: InvalidURL`, which does not say it is configuration (experiment E10). AC14 expects exit 2 before anything else happens | The architect decides where the check goes, because plan § Order of an invocation builds the source at step 4, after migrations. Closed when such a setting gives exit 2 with a configuration message that names the variable and never its value, before any connection, and a test pins it | Open |
| F-04 | MEDIUM | AC15 ("one line whenever this invocation created a run, whatever the exit code") | `ingest_command.py:316-323` prints `<id> running` only for `KeyboardInterrupt`; any other exception that escapes `run_ingest` after `run_started` prints nothing on stdout (recorded as a deliberate reading in O6c) | With F-02, a created run ends with empty stdout and exit 1, so the operator never sees the id needed for `--resume` | After `run_started`, an escaping exception prints `<id> running` (closing not confirmed, P-5), or the plan states the exception explicitly; a test pins it | Open |
| F-05 | MEDIUM | AC11, State machine K (spec gap) | K appends `run-interrupted` and calls `finish_run(FAILED)` without knowing whether the interrupted `finish_run` had already committed (`ingest_use_case.py:386-395`, 1084-1098). The schema allows appends to finished runs (`migrations/0001_initial_schema.sql`: no append guard), so only the use case enforces AC11 | Ctrl+C lands just after `finish_run(succeeded)` committed and before it returned. Experiment E5: `run-interrupted` appended to the `succeeded` run, `finish_run(FAILED)` refused, outcome `INTERRUPTED` with `running`, exit 130, stdout `<id> running` | The architect decides how K behaves when the run may already be finished (for example a `read_run` before the cleanup writes), and a test pins it | Open |
| F-06 | MEDIUM | AC24 ("stderr a fixed message naming the execution id"), State machine H step 2 ("otherwise -> contradictory") | `ingest_use_case.py:786-792` catches only `ValueError`, `PersistenceNotFoundError` and `EvidenceNotFoundError`; an `EvidenceIntegrityError` or `OSError` from `store.read_observation` in `_validated_completed_page` (626) reaches 1099-1101 | A resumption whose chain holds a `page-completed` with a corrupt local record ends `NOT_STARTED`, exit 1, nothing written (correct), but stderr says only `EvidenceIntegrityError` with no execution id (experiment E6) | Every H refusal ends with the fixed message that names the target; a test with an unreadable local record pins it | Open |
| F-07 | MEDIUM | AC6 (c) ("stderr names the operation and the identity"), AC15 / Q9 (progress lines), harny-audit "no dead test seam" | `IngestReporter.progress` is never called by `run_ingest` (no call in `ingest_use_case.py`; `ingest_command.py:202` uncovered). On a refused `record_observation` stderr holds `run <id> started` and `failed` only. `test_storage_progress_text_holds_no_url_body_or_header_value` (`test_ingest_use_case.py:978`) and `test_unexpected_exception_text_never_reaches_the_reporter` (1136) iterate over an always-empty `reporter.messages`, so they are vacuous. README § Ingesting and the CHANGELOG say stderr carries the progress | An operator watching a long run sees no page, sequence, status or hash progress; a PostgreSQL refusal is not named on stderr | The use case reports progress (page, sequence, status, hash) and project-error text through `progress`, the AC6 (c) stderr names the operation and identity, and the two tests assert on non-empty messages; or the architect states that progress is optional and the docs are aligned | Open |
| F-08 | LOW | harny-standards (no dead code) | `_finish` at `ingest_use_case.py:218-235` is never called (lines 224-230 uncovered) | None at run time | Removed or used | Open |
| F-09 | LOW | F-2 (Q7, 32 characters) | `ingestion_catalogue.py:155` docstring still says "The id is 33 characters" | Misleads a reader | Docstring says 32 | Open |
| F-10 | LOW | AC10, State machine R step 3 (spec gap) | R maps only `EvidenceIntegrityError` from `read_observation`, and `EvidenceNotFoundError` or `EvidenceIntegrityError` from `read_content`. An `OSError` (for example `PermissionError`), or `EvidenceNotFoundError` from a listed record that vanished, escapes `_reconcile_run` (`ingest_use_case.py:465-501`) | Experiment E7: `NOT_STARTED`, exit 1, message `PermissionError`, the run stays `running` with no `reconciliation-failed`, and every later `ingest` stops at the same place until a human fixes the file | The architect assigns these errors a problem value (or confirms the current behavior), and a test pins it | Open |
| F-11 | LOW | State machine P / K (spec gap) | A non-connection `PersistenceError` from `append_audit_event` or `finish_run` goes to the `except Exception` branch and is audited as `unexpected-error` with a project error's class name (experiment E8). K reserves `unexpected-error` for exceptions that are not project errors, and P specifies only `record_observation` | The audit trail calls a database refusal an unexpected defect | The architect specifies the reaction, and a test pins it | Open |
| F-12 | LOW | harny-audit step 4 (outcome state) | `tasks.md` O8 is `[ ]` (explained: the journal is the human's) rather than `[x]` or `[!]`; § Working state line "Phase" still says "no pull request is open" while PR #25 is open | Stale state for the next role | O8 is checked or marked `[!]`, and the stale line is corrected | Open |

Untested branches, not counted as separate findings: `ingest_use_case.py:913-933`
(AC6 (b) when PostgreSQL then refuses or loses the observation that was read
back), 130-132 and 180-181 (an error while taking the exclusion again, and a
second loss during the append re-check).

## Defect-hunting checklist (state machines read against the code)

| Area | Result |
|---|---|
| Order local store -> PostgreSQL -> events -> finish | Holds (`test_ingest_use_case.py:357`, AC4 order tests) |
| Write-once evidence never overwritten | Holds: one `store` per (id, sequence); a resumption uses a new id; the F1 listing is read-only (AC22 bytes and mtimes test) |
| No retries | Holds (`no_retry`; one `search_page` per loop iteration) |
| Secrets, URLs and tracebacks never printed | Holds for every path seen; class names only for foreign exceptions |
| Exit-code table | Holds except F-02 (1 instead of 130) and F-03 (1 instead of 2) |
| Connection loss | Holds: one new connection, the exclusion taken again, safe repeats only, append re-checked, no third connection, P-2 |
| Interruption cleanup | Fails: F-01, F-02; race F-05 |
| Reconciliation problems list | Holds for the listed cases; gap F-10 |
| Chain validation, `last-page-reached` validity and coverage | Holds (117 + 33 unit, 3 integration); message gap F-06 |
| Execution-id checks | Holds |
| `KeyboardInterrupt`, `SystemExit`, `MemoryError` propagation | `SystemExit` never caught (test); a second `KeyboardInterrupt` propagates (test); `MemoryError` is audited as `unexpected-error` (test). F-02 when either arrives inside `store` |
| Leaked repositories or sources | None found: `finally` closes the current repository, `_reconnect` closes the lost one, the source is closed in `_invoke`'s `finally` |
| Unconfirmed `start_run` | Outcome names the id with `running` although the run may not exist (experiment E9); this is what plan § State machine C prescribes (note, no finding) |

## Commands run (2026-10-18, repository root, `7603379`)

| Command | Result | Label |
|---|---|---|
| `uv sync --locked` | ok, 25 packages | rerun |
| `uv run pytest -q` (no `--env-file`) | 1741 passed, 265 skipped | rerun |
| `uv run --env-file .env pytest --cov=ec_procurement_quality --cov-report=term-missing -q` | 2006 passed, 0 skipped, TOTAL 95 % | rerun |
| `uv run ruff check .` | All checks passed | rerun |
| `uv run ruff format --check .` | 118 files already formatted (before this file was added) | rerun |
| `uv run mypy .` | Success, 52 source files | rerun |
| `uv run node .sdd/doctor/run-doctor.mjs` | 31 ok, 0 skipped, 0 warned, 0 failed | rerun |
| `uv run ec-procurement-quality --version` | `ec-procurement-quality 0.1.0` | rerun |
| Every focused unit `-k` row of § Validation and the O5 groups | all passed (counts in § AC results) | rerun |
| Every focused integration row of § Validation | all passed (counts in § AC results) | rerun |
| `uv run --env-file .env pytest tests/unit/ingest tests/integration/ingest -q` | 663 passed | rerun |
| `uv run pytest tests/unit -q -k layer` | 16 passed | rerun |
| AC18 grep of `src/ec_procurement_quality/application/` for `SELECT `, `INSERT `, `UPDATE `, `DELETE `, `objects/`, `observations/`, `.json`, `advisory`, `pg_` | no match | rerun |
| AC20 `git diff main --stat -- migrations tests/unit/test_cli.py ... uv.lock` (the full list of the row) | empty | rerun |
| `git diff main --stat -- uv.lock` | empty | rerun |
| `git diff main -- pyproject.toml` | only the two F-1 keys and three comment lines, additions only | rerun |
| `git diff main --numstat -- tests/integration/test_postgres_migrations.py` | `3 0` | rerun |
| `git diff main --stat -- compose.yaml .env.example docs/glossary.md docs/adr specs/current` | empty | rerun |
| `git ls-files .env` | empty | rerun |
| `git diff main --check`, `git diff --check` | clean | rerun |
| Leftover `ecpq_test_` databases (count only, through `uv run --env-file .env`) | 0 | rerun |
| Files under the real `data/` | 0 before and after | rerun |
| `gh pr checks 25` | `feedback` pass, `tests` pass; head `7603379` | rerun |
| CI `tests` log (run 39098935636) | 2006 passed, TOTAL 96 % (Linux; includes AC6 (a) and (d)) | reused |
| CI `feedback` log (run 39098935620) | `harny-feedback: 2 of 2 command(s) ran, 0 skipped.` | reused |
| Auditor experiments E1 to E10 (scratchpad, the repository's unit doubles; nothing written to the repository) | results quoted in § Findings | experiment |

## Conventions and feedback

- harny-standards, checked against `AGENTS.md` (the project's conventions document):
  - layer boundaries hold;
  - raw responses are never overwritten;
  - no invented SERCOP contract: synthetic `.invalid` data only;
  - no dependency, infrastructure or service added (the F-1 config change was approved);
  - no secrets in source, tests or docs (gitleaks and the CI secret scan pass in doctor);
  - verification was run and reported.

  Violations: dead code F-08, a stale docstring F-09.
- harny-feedback: the CI workflow `.github/workflows/harny-feedback.yml` exists and its latest run is green with 2 of 2 commands run. The per-turn PostToolUse and Stop hooks are configured in `.claude/settings.json`. That they fired and were heeded during implementation is `unavailable`: no persisted hook log exists, and `AGENTS.md` notes the hooks run only when `.venv` is on `PATH`.

## Reservations carried forward

- Persistence U1: the real commit-in-flight case is still untested against PostgreSQL. The unit `FlakyRepository` and the integration `Kill*Repository` seams cover the deterministic cases (recorded in CHANGELOG Known limitations).
- Persistence N5: the reconciliation reads run in separate snapshots; this is safe under the ingest exclusion (checked: R runs only after the exclusion is held).
- Raw-evidence N2: handled for `store` (AC6 b, F-3), not for the interruption cleanup (F-02).
- Source-access R-6 and raw-evidence N3: hold; only class names or fixed project texts are printed.
- Source-access R-7: holds (`-k logger`).
- Source-access R-11: holds; one source per invocation, closed once.
- Source-access U1: open until the human's Day 20 live run. No document claims that a live run happened: README, CHANGELOG, AGENTS.md and the journal all say none was made.

## What could not be verified

- Behavior against the real SERCOP source and the real `data/raw/` (out of scope; must not be run).
- A real Ctrl+C delivered to a live `psycopg` or disk operation. F-01 and F-02 were shown with the repository's doubles, which interrupt at the same call boundaries; the real `LocalDiskRawEvidenceStore.read_observation` also raises `EvidenceNotFoundError` for a missing file.
- `pg_terminate_backend` of a real stale session that holds the exclusion (the README procedure was not exercised).
- That the per-turn feedback hook fired during implementation (see § Conventions and feedback).
- The test-writer's mutation and reference-implementation soundness claims for O4 and O6b (scratchpad artifacts, not re-run).

## Audit log

| Round | Date | Verdict | Notes |
|---|---|---|---|
| 1 | 2026-10-18 | REJECTED | F-01 and F-02 (CRITICAL, AC7, AC15, State machine K) and F-03 (HIGH, binding constraint and AC14) block. F-04 to F-07 MEDIUM, F-08 to F-12 LOW. Sent back to the architect |
