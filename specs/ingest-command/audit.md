# Audit: Ingest command (F4)

Auditor: `sdd-auditor` (outcome O10), round 2, 2026-10-18.
Reviewed: branch `feat/ingest-command` at `91bd69d` (clean working tree), PR #25
against `main` (base `6b34374`). Specs: `intent.md` Revision 8, `execution-plan.md`
Revision 6 and `tasks.md` Revision 3, all approved by the human on 2026-10-18.

The whole feature was audited again, not only the fixes. Every changed line of
`application/ingest_use_case.py` (rewritten in the rework: 776 lines changed
since round 1), `interfaces/ingest_command.py` and `interfaces/cli.py` was read
against the state machines P, C, K, T, R, H and I, the "Refused writes" table and
the required progress lines. The test changes since round 1
(`git diff 7603379 -- tests`) were read for weakened assertions, and so were the
four documentation files.

Evidence labels:

- `rerun`: the auditor ran it in this round.
- `reused`: a recorded result that is still current (the CI runs of PR #25 at
  `91bd69d`).
- `experiment`: a throwaway auditor test or mutant in the session scratchpad
  (never in the repository), run against a scratch copy of `src/` and `tests/`
  with the repository's own doubles from `tests/unit/ingest/conftest.py`.
- `unavailable`: it could not be checked.

## Final verdict

REJECTED

**Summary**: The rework closes the three blocking findings of round 1 and every
other round-1 finding except the stale `tasks.md` lines. The fixes are real:
each one is pinned by tests that fail on the round-1 code (161 of the 738 unit
ingest tests fail there) and by an auditor mutant that the suite kills (12 of
12). 2165 tests pass locally and in CI, and every focused row of § Validation
passes.

One clause of an acceptance criterion is still unmet. AC15 requires "one line
for each database write refused or lost, naming the operation and the
identity". The plan's required progress lists State machine K among the paths
that must report it. The interruption cleanup (`_cleanup_after_exception`)
swallows a refused or lost `record_observation`, `append_audit_event` or
`finish_run` without any progress line (F-13). The fix is small, but an unmet
AC blocks approval at any severity. A second gap comes from the specs: AC15 and
the plan's required progress 3 disagree on a write lost during reconciliation.
The architect must decide that one (F-14).

**Critical Issues** (must fix before merge):
- F-13 (MEDIUM, blocking: an AC15 clause and plan § Public names "Required progress" 2 and 3): the K cleanup writes no progress line when one of its writes is refused or lost. The run is left `running` and stderr says only `the ingest was interrupted` or `unexpected error: <class>`.
- F-14 (MEDIUM, blocking until the architect decides; spec conflict): AC15 asks for a line for every lost write, but the plan's required progress 3 asks only "from `start_run` on". A write lost during reconciliation prints only `PersistenceConnectionError`, with no operation and no run.

**Warnings** (should fix, not blocking alone):
- F-12 (LOW, carried from round 1, partially resolved): `tasks.md` § Status and § Checkpoint still say the specs are "pending the human's approval". O8 is still `[ ]`. O10 rework step 3 says the human corrects `run_ingest`, while § Working state says the executor did it. No red evidence is recorded for the round-2 tests.
- F-15 (LOW, spec gap): a refused or lost read during the target check, the chain check, the reconciliation or the id draw ends `NOT_STARTED`, and its stderr message is only an exception's class name.

**Recommendations** (nice to have):
- F-16 (LOW): edge cases of the "returns an outcome" and "exactly one stdout line" contracts. A `KeyboardInterrupt` or another non-persistence exception from `open_repository()` escapes `run_ingest`. A `KeyboardInterrupt` during `source.close()` adds a second stdout line.
- F-17 (LOW): README § Ingesting gives an incomplete list of the cases that print `running`, and its exit-2 row does not name the proxy and certificate settings.
- Untested branches, listed under § Test coverage. Auditor experiments show that they behave as the plan says.

Next role: the architect, to decide F-14 (align AC15 with the plan's required
progress 3, or the reverse) and F-15 (the message of a refused read in T, H, R
and I). F-13 needs no spec change. Then the test-writer writes red tests for
F-13 (and F-14 or F-15 if the architect changes them), the use case is
corrected, and `tasks.md` is brought up to date (F-12). Then audit round 3.

## Round 1 summary (2026-10-18, `7603379`, REJECTED)

Round 1 found 12 findings. Three of them blocked approval:

- F-01 and F-02 (CRITICAL, AC7 and AC15, State machine K): a Ctrl+C during
  `record_observation` lost the observation, and a Ctrl+C or `MemoryError`
  inside `store` let `EvidenceNotFoundError` escape.
- F-03 (HIGH, binding constraint and AC14): a malformed proxy or certificate
  setting gave exit 1 after the migrations.

The others were F-04 to F-07 (MEDIUM) and F-08 to F-12 (LOW). The human
accepted the rejection. The architect wrote intent Revision 8, plan Revision 6
and tasks Revision 3, and the human approved them on 2026-10-18. The
test-writer added red tests (`5610e02`). The use case was then fixed
(`eb3a317`), and the CLI composition and a docstring were fixed (`91bd69d`).
The full round-1 report is in git history (`7069f4c`).

## Resolution of the round-1 findings

Each closure condition was checked against the code and against at least one
test that fails without the fix. For each finding, a mutant reverts the fix in
a scratch copy and the focused tests must fail.

| Id | Round-1 severity | Status | Evidence (code; tests; mutant) |
|---|---|---|---|
| F-01 | CRITICAL | Resolved | `ingest_use_case.py:1099` marks the sequence pending before `store`. It is cleared only once `record_observation` returns (1187) or the path has concluded (1132, 1145, 1178). The K cleanup reads the observation back and records it (548-554). `interrupt_during_record`: 4 passed. They cover before and after delegating and the repeat under C; the journal shows `record_observation:2` before `finish_run:failed`. Mutant M1 (clear pending after `store`) -> 3 failed (experiment) |
| F-02 | CRITICAL | Resolved | `_cleanup_after_exception` (525-568) absorbs `EvidenceNotFoundError`, `EvidenceIntegrityError` and `OSError` from its read-back (551-552) and still appends and closes. Any other exception stops the cleanup with `running` (561-567), and nothing escapes. `cleanup_read_back`: 10 passed (`KeyboardInterrupt` and `MemoryError`; nothing published, or published but unreadable). `exit_code_cleanup_read_back`: 4 passed (exit 130 with `<A> failed`; exit 1 with `<A> failed` and `MemoryError` only). Mutant M2 (do not absorb) -> 10 failed. Mutant M10 (no cleanup for a non-interrupt) -> 5 failed (experiment) |
| F-03 | HIGH | Resolved | `ingest_command.py:271-277` builds the source at invocation step 2, inside the `httpcore` guard, before `_migrate` (279). Any `Exception` except `MemoryError` gives exit 2, with the fixed message naming the six variables plus the class name (208-212, 276). The source is closed in a `finally` (293-296). `source_configuration or order_of_invocation`: 30 passed. They use the real `default_wiring().make_source` with `HTTPS_PROXY=http://[zz]:1`, an `ftp://` proxy, a `socks5://` `ALL_PROXY` and a missing `SSL_CERT_FILE`: exit 2, `rig.calls == ["make_source"]`, nothing written, and no value or path in stderr. The ten order tests were migrated to `["make_source", "migrate"]` with the source closed once, and no assertion was weakened (`git diff 7603379 -- tests` read). Mutant M8 (source after migrations) -> 28 failed. Mutant M12 (message without the variable names) -> 16 failed (experiment) |
| F-04 | MEDIUM | Resolved | `ingest_command.py:338-345`: `_print_running` runs on both escaping branches, so stdout is `<id> running` once `run_started` was called. `output_escaping_exception`: 12 passed (a synthetic defect, a project error and `KeyboardInterrupt`, after and before the announcement). Mutant M9 -> 4 failed (experiment) |
| F-05 | MEDIUM | Resolved | `ingest_use_case.py:543-547`: the cleanup calls `read_run` first. A finished run gets nothing more and keeps its status. A failing `read_run` writes nothing and gives `running` (561-567). `interrupt_after_finish`: 11 passed. `exit_code_interrupt_after_finish`: 6 passed (exit 130 with `<A> succeeded`; 130 with `<A> failed`; 1 with `<A> succeeded` for `MemoryError`). Mutant M3 (no guard) -> 9 failed (experiment) |
| F-06 | MEDIUM | Resolved | `ingest_use_case.py:992-1004`: the chain check catches `EvidenceIntegrityError` and `OSError` as well, and the message is `invalid resumption chain <target>`. `chain_unreadable_record`: 12 passed (corrupt, missing and `OSError`; the message names `<A>` and is not a class name; stderr names `<A>`). Mutant M4 -> 6 failed, all on the two errors it removes (experiment). See F-15 for refusals that are not `PersistenceNotFoundError` |
| F-07 | MEDIUM | Resolved for P, C and R; K still silent (F-13) | Page lines `_report_page` (241-245, called at 1115 and 1160). `page N no response` (1084). `page N sequence S not stored` (1142-1144). Refusals `_report_refusal` (248-264) in P, the "Refused writes" table and R. Losses `_report_loss` (126-129). The two once-vacuous tests now assert non-empty messages first (`test_ingest_use_case.py:1006-1012`, `1165`). `progress_line or output_progress or progress_text or text_never_reaches_the_reporter`: 24 passed. Mutant M5 (no page line) -> 6 failed (experiment). The K cleanup writes none of the required lines: F-13 |
| F-08 | LOW | Resolved | `_finish` removed. Coverage shows no uncalled helper in the module |
| F-09 | LOW | Resolved | `ingestion_catalogue.py:155` says "The id is 32 characters" |
| F-10 | LOW | Resolved | `ingest_use_case.py:666-697`: the listing `OSError` -> `local-listing-failed`. `read_observation` raising `EvidenceNotFoundError` or `OSError` -> `local-observation-unreadable`. `read_content` raising `OSError` -> `object-integrity`. `reconcile_os_error`: 4 passed. Mutant M6 -> 1 failed (experiment) |
| F-11 | LOW | Resolved | Start refused -> `NOT_STARTED` without `run_started` (1037-1039). A normal-path append refused -> one `storage-failed` (`postgresql`) (`_append_on_normal_path` 393-425). A final finish refused -> `storage-failed`, then `finish_run(FAILED)` with a new reading (448-451). A failure-path append refused -> no further event (`_close_failed` 337-349). `finish_run(FAILED)` refused -> `running` (352-365). In R: refusal -> `NOT_STARTED` naming `X` (`_guarded` 583-595), and a refused record -> `postgresql-observation-conflict` (712-722). `database_refusal`: 57 passed, never `unexpected-error`, at most one `storage-failed` (`postgresql`). Mutant M7 -> 9 failed (experiment) |
| F-12 | LOW | Open (partially resolved) | § Working state was updated, but other lines are stale; see F-12 under § Findings |

Red evidence for the rework tests: `tasks.md` records none (F-12). The auditor
ran it retroactively. The current tests, run against the round-1 versions of
`ingest_use_case.py` and `ingest_command.py` (`git show 7603379:...` in a
scratch copy), give `161 failed, 577 passed` for `tests/unit/ingest`. The
round-2 tokens alone give `141 failed, 23 passed`. Every failure is an
assertion on behavior: no import, collection, database or socket error
(experiment).

## AC results

| AC | Status | Evidence |
|---|---|---|
| AC1 | PASS | `-k success` 9; `-k e2e_success` 2 passed (rerun) |
| AC2 | PASS | `-k repeat` 5; `-k e2e_repeat` 2 passed (rerun) |
| AC3 | PASS | `-k last_page` 41, `-k last_page_p3` 6, `-k e2e_last_page` 2 passed. `ingest_use_case.py:1230` appends the event when `p >= pages`, with no scope condition (rerun) |
| AC4 | PASS | `-k failure_with_response` 16; `-k e2e_failure` 5 passed (rerun) |
| AC5 | PASS | `-k failure_without_response` 6 passed (rerun) |
| AC6 | PASS | `-k storage` 16 passed: (a) to (d). (a) and (d) on Linux in CI (reused, run 39147642720). (c): stderr names `record_observation`, the run and the sequence, with at most the class name (`output_progress` and `progress_line` refusal tests). (e): `-k database_refusal` 57 passed (rerun) |
| AC7 | PASS | `-k "interrupt or exit_code"` 116; `-k "interrupt_during_record or cleanup_read_back"` 14; `-k interrupt_after_finish` 11; `-k exit_code_cleanup_read_back` 4; `-k exit_code_interrupt_after_finish` 6 passed (rerun). Mutants M1, M2, M3 and M10 killed (experiment) |
| AC8 | PASS | `-k connection_loss` 39 (unit); `test_ingest_connection_loss.py` 7 (integration). `-k connection_loss_final_finish` 12 (unit); `-k final_finish` 4 (integration) passed (rerun) |
| AC9 | PASS | `-k resume` 24; `-k e2e_resume` 5 passed (rerun) |
| AC10 | PASS | `-k reconcile` 31; `-k e2e_reconcile` 6; `-k reconcile_os_error` 4 passed (rerun) |
| AC11 | PASS | `-k closed_run` 3 and `-k interrupt_after_finish` 11 passed (rerun) |
| AC12 | PASS | `-k "execution_id or identity"` 67 passed (rerun) |
| AC13 | PASS | `-k "scope or catalogue"` 111 passed. `assert_follows_catalogue` also runs in the `database_refusal` and `reconcile_os_error` tests (rerun) |
| AC14 | PASS | `-k "usage or environment"` 66; `-k "source_configuration or order_of_invocation"` 30 passed (rerun). Mutants M8 and M12 killed (experiment) |
| AC15 | PARTIAL | `-k "output or logger"` 67; `-k output_escaping_exception` 12; the progress group 24 passed (rerun). Unmet: no line for a write refused or lost in the K cleanup (F-13, experiments E1 to E4b), and none for a write lost during reconciliation (F-14, experiment E8) |
| AC16 | PASS | `-k migrations` 11 (integration CLI, `["make_source", "migrate"]`); `test_persistence_error_hierarchy.py` 3; lock and runner 23 passed. `git diff main --numstat -- tests/integration/test_postgres_migrations.py` -> `3 0` (rerun) |
| AC17 | PASS | `-k no_retry` 6 passed. One `search_page` per loop iteration (`ingest_use_case.py:1065-1075`) (rerun) |
| AC18 | PASS | `-k layer` 16 passed. The AC18 grep of `application/` finds nothing. `uv.lock`: no diff. `pyproject.toml`: only the two F-1 keys and their comment. `mypy`: 52 files clean (rerun) |
| AC19 | PASS | `uv run --env-file .env pytest tests/unit/ingest tests/integration/ingest -q` -> 822 passed. The real `data/` holds 0 files before and after. 0 `ecpq_test_` databases (rerun) |
| AC20 | PASS | 2165 passed (1307 baseline + 858 F4). The AC20 `git diff main --stat` list is empty. `git ls-files .env` is empty. `git diff main --check` and `git diff --check` are clean. ruff, format, mypy and doctor (`31 ok, 0 warned, 0 failed`) pass. `--version` -> `ec-procurement-quality 0.1.0` (rerun) |
| AC21 | PASS | Inspection: README § Ingesting, AGENTS.md § Current commands, architecture § Infrastructure boundary and § Open questions, and CHANGELOG Added, Changed and Known limitations. No document claims that a live run happened. Nicety F-17 (rerun, inspection) |
| AC22 | PASS | `test_local_disk_raw_evidence_store_listing.py` 25 passed (rerun) |
| AC23 | PASS | `test_postgres_runs_and_exclusion.py` 24 passed (rerun) |
| AC24 | PASS | `-k chain` 129, `-k chain_last_page` 33, `-k e2e_chain_last_page` 3 and `-k chain_unreadable_record` 12 passed (rerun). Spec gap F-15 for refused reads |
| AC25 | PASS | `-k "paths or environment"` 34 (unit); `-k root` 2 (integration) passed (rerun) |

Plan decisions and implementation findings:

| Item | Status | Evidence |
|---|---|---|
| P-1 | PASS | `ingest_command.py:246-251`: `MigrationLockError` -> 1, any other `MigrationError` -> 2. `postgres_migrations.py` unchanged since round 1 (rerun tests) |
| P-2 | PASS | `ingest_use_case.py:287-312, 428-463`: the exact repeat of `finish_run(SUCCEEDED)` with the same `finished_at`, and no `storage-failed`. A refused repeat gives `RUN_FAILED` with the stored status. Unit 12 and integration 4 passed. Mutant M11 killed (experiment) |
| P-3 | PASS | `ingest_use_case.py:1230-1245` |
| P-4 | PASS | `ingest_use_case.py:872-927` with `pages_left_to_request` |
| P-5 | PASS | `_unconfirmed` (315-321), K's `running` (561-567), `_print_running` (`ingest_command.py:231-234`) |
| F-1 | PASS | `git diff main -- pyproject.toml`: `explicit_package_bases = true`, `mypy_path = "src"` and three comment lines, additions only |
| F-2 | PASS | Docstring corrected (F-09) |
| F-3 | PASS | `ingest_use_case.py:1107-1113` catches the three read-back errors. AC6 (d) tests pass |

## Binding-constraint compliance

| Constraint | Status | Evidence |
|---|---|---|
| Layer placement (ADR 0001, AC18) | PASS | Layer tests 16 passed. `application` imports only the standard library, `domain` and `application`. `interfaces` imports no `httpx` or `psycopg` |
| Public names and signatures | PASS | The pinned names and signatures are unchanged since round 1. `run_ingest` keeps the pinned keyword signature |
| CLI arguments and configuration | PASS | `cli.py:25-60`, `ingest_command.py:109-170`. The subparser is not required (CLI-2 kept, `test_cli.py` 2 passed) |
| Order of an invocation (Revision 6) | PASS | Arguments and environment (316-321), absolute paths (324-326), `httpcore` guard (327, step 2.1), `make_source` (272, step 2.2), migrations (279), store and `run_ingest` (282-291), source closed in a `finally` (293-296). `order_of_invocation` tests pass |
| Exit codes | PASS | `_EXIT_CODES` (214-220) and the step 2 and step 3 mappings. Every row has a test |
| Output (AC15) | PARTIAL | stdout rule including F-04: PASS. Required progress 1: PASS. Required progress 2 and 3: PASS in P, C and R, FAIL in K (F-13); reconciliation losses: F-14 |
| Audit details (closed catalogue) | PASS | `assert_follows_catalogue` in the main, refusal and reconciliation paths |
| State machine P and "Refused writes" | PASS | Write order, pending observation, read-back rule, decide step, P-3, and every row of the table (F-11 above) |
| State machine C | PASS | `_PersistenceSession` (110-208): one new connection, the exclusion taken again, safe repeats only, the append re-checked with `list_audit_events` (same type, `same_json` detail and instant), no third connection (134-135), and no reconnect before `start_run` |
| State machine K | PASS for behavior; FAIL for its progress lines (F-13) | `read_run` guard, pending read-back, the three absorbed errors, stop with `running` on any other exception, no new connection, a second `KeyboardInterrupt` propagates |
| State machine T | PASS | `ingest_use_case.py:961-975`, before reconciliation, writes nothing |
| State machine R | PASS | `ingest_use_case.py:654-758`: problem order, gap after verification, local-only records, stop at the first problem, F-10 mapping, F-11 refusals |
| State machine H | PASS | `_resume_plan` (835-927): link, cycle, `run-started` shape, scope, middle-run status, step 2 reads including F-06, `last-page-reached` validity and coverage, P-4 sentinel. Message gap F-15 (spec gap, not a breach of the listed failures) |
| State machine I | PASS | `_draw_execution_id` (502-522): three draws, both ports checked, under the exclusion |
| F1 and F3 port extensions | PASS | Unchanged since round 1; listing 25 and runs and exclusion 24 passed |
| No schema change | PASS | `migrations/` holds `0001_initial_schema.sql` only, with no diff |
| No dependency (AGENTS.md, PT-11) | PASS | `uv.lock`: no diff. `pyproject.toml`: F-1 keys only |
| ADR 0006: "report a malformed proxy or certificate setting in the environment as configuration (exit 2, before the migrations)" | PASS | F-03 resolved |
| R-6 and N3: no exception chain or `__context__` printed | PASS | Only fixed texts, `str()` of migration errors and class names are printed |
| R-7: `httpcore` above `DEBUG` | PASS | Guarded before the source is built (`order_of_invocation` httpcore test) |
| SA-13 and PS-13: one source, at most two repositories, all closed | PASS | Source closed once in a `finally`. `run_ingest` closes the current repository in its `finally` (1276-1277), and `_reconnect` closes the lost one. `PostgresIngestionRepository.close` is idempotent (`postgres_ingestion_repository.py:657-661`) |
| Tests: guards, no real `data/raw/`, throwaway databases | PASS | Guard proof tests pass. The real `data/` is empty. 0 leftover databases |
| `.env` never read by code or committed | PASS | `git ls-files .env` is empty. No code reads `.env` |

## Test coverage

| AC | Tests (file) | Status |
|---|---|---|
| AC1 | `success` in `tests/unit/ingest/test_ingest_use_case.py`; `e2e_success` in `tests/integration/ingest/test_ingest_end_to_end.py` | PASS |
| AC2 | `repeat` (unit); `e2e_repeat` (integration) | PASS |
| AC3 | `last_page`, `last_page_p3` (unit); `e2e_last_page` (integration) | PASS |
| AC4 | `failure_with_response` (unit); `e2e_failure` (integration) | PASS |
| AC5 | `failure_without_response` (unit) | PASS |
| AC6 | `storage` (unit, 16); `database_refusal` (unit, 57) for (e); `output_progress` refusal (unit command) for the (c) stderr | PASS |
| AC7 | `interrupt`, `interrupt_during_record`, `cleanup_read_back`, `interrupt_after_finish` (unit); `exit_code_130`, `exit_code_cleanup_read_back`, `exit_code_interrupt_after_finish` in `tests/unit/ingest/test_ingest_command.py` | PASS |
| AC8 | `connection_loss`, `connection_loss_final_finish` (unit); `tests/integration/ingest/test_ingest_connection_loss.py` | PASS |
| AC9 | `resume` (unit); `e2e_resume` (integration) | PASS |
| AC10 | `reconcile`, `reconcile_os_error` (unit); `e2e_reconcile` (integration) | PASS |
| AC11 | `closed_run`, `interrupt_after_finish` (unit) | PASS |
| AC12 | `execution_id` (`tests/unit/ingest/test_ingestion_catalogue.py`), `identity` (unit) | PASS |
| AC13 | `scope`, `catalogue`, and `assert_follows_catalogue` across the use-case tests | PASS |
| AC14 | `usage`, `environment`, `source_configuration`, `order_of_invocation` (unit command); `cli_invalid_*` (integration) | PASS |
| AC15 | `output`, `logger`, `output_escaping_exception`, `output_progress` (unit command); `progress_line` (unit) | PARTIAL: MISSING a test for the K cleanup's refused or lost writes (F-13). `test_unexpected_cleanup_that_meets_a_database_error_leaves_the_run_running` (`test_ingest_use_case.py:1169`) drives that path but checks no progress line |
| AC16 | `migrations` (`tests/integration/ingest/test_ingest_cli.py`); `tests/unit/test_persistence_error_hierarchy.py`; `tests/integration/test_postgres_migration_lock_error.py`; the edited PS-4 test | PASS |
| AC17 | `no_retry` (unit) | PASS |
| AC18 | `tests/unit/ingest/test_ingest_layers.py` (`layer`); `mypy`; the source built and closed once (command tests) | PASS |
| AC19 | guards and proof tests in both `conftest.py` files; the session check of `data/raw/` | PASS |
| AC20 | the 1307 existing tests, unedited except the PS-4 assertion | PASS |
| AC21 | none (inspection) | PASS (inspection) |
| AC22 | `tests/unit/test_local_disk_raw_evidence_store_listing.py` | PASS |
| AC23 | `tests/integration/ingest/test_postgres_runs_and_exclusion.py` | PASS |
| AC24 | `chain`, `chain_last_page`, `chain_unreadable_record` (unit); `chain_unreadable_record_message` (unit command); `e2e_chain_last_page` (integration) | PASS |
| AC25 | `root` (integration CLI); `paths`, `environment` (unit command) | PASS |

Coverage from the broader command: TOTAL 97 % locally and in CI.
`ingest_use_case.py` is at 96 %, and `ingest_command.py` and `cli.py` are at 100 %.
These lines of `ingest_use_case.py` are missed:

- 144-146: the exclusion check raising on the new connection;
- 202-204: a second loss during the append re-check;
- 410: an unconfirmed normal-path append;
- 455-456: `read_run` failing after a refused P-2 repeat;
- 711: a connection loss on a reconciliation record;
- 1036: an unconfirmed `start_run`;
- 1122-1133: the read-back observation of P step 3 whose `record_observation` is unconfirmed or refused;
- 1250: a `KeyboardInterrupt` before the run exists, in the outer handler.

They are not counted as findings. Experiments E9, E11 and E12 drove 1122-1133
and 410-style paths: they behave as the plan says (`storage-failed`
(`postgresql`, 2, 2) for a refusal; `running` with no third connection for a
double loss).

### Tier Results

| Tier | Tests found | ACs verified | Setup matches § Validation | Ran | Status | Finding |
|---|---|---|---|---|---|---|
| unit | `tests/unit/ingest/` (738 tests), `test_local_disk_raw_evidence_store_listing.py` (25), `test_persistence_error_hierarchy.py` (3) | AC1 to AC18, AC22, AC24, AC25, including the Revision 6 rows | yes: doubles, `tmp_path`, autouse socket guard; the conftest additions are fault seams named in the plan's seams table | rerun: every focused `-k` row and the required Revision 6 tokens, all passed | PARTIAL | F-13 (AC15: no test or behavior for the K cleanup's progress lines) |
| integration | `tests/integration/ingest/` (84 tests), `test_postgres_migration_lock_error.py`, the PS-4 edit | AC1 to AC4, AC8 to AC10, AC16, AC19, AC23 to AC25 | yes: PT-13 throwaway databases, admin connection, guard allowing the configured host only, `data/raw/` session check | rerun with `--env-file .env`, all passed; CI reused | PASS | none |
| static | `uv run mypy .` | AC18 | yes: the F-1 keys are the only config change | rerun: success on 52 files | PASS | none |
| command | ruff, format, mypy, doctor, `--version`, git diff checks | AC20 | yes | rerun: all clean | PASS | none |
| manual | documentation inspection | AC21 | n/a | rerun (inspection) | PASS | F-17 (nicety) |

No test exists at a tier that § Validation does not name. No setup was added
that the plan does not name: since round 1, no configuration, manifest or
lockfile changed.

## Findings

Round-2 findings (new) and the open round-1 finding. The resolved round-1
findings are in § Resolution of the round-1 findings.

| Id | Severity | AC / constraint | Finding and evidence | Failure scenario | Closure condition | Status |
|---|---|---|---|---|---|---|
| F-13 | MEDIUM (blocking: an unmet AC clause) | AC15 ("one line for each database write refused or lost, naming the operation and the identity"); plan § Public names "Required progress" 2 (which lists K) and 3 ("each `PersistenceConnectionError` from `start_run` on") | `_cleanup_after_exception` (`ingest_use_case.py:542-567`) catches every `Exception` from `read_run`, `record_observation`, the `run-interrupted` or `unexpected-error` append and `finish_run(FAILED)`, and returns with `running` without calling `reporter.progress`. In the same way, a lost `read_run` after a refused P-2 repeat (453-456) reports nothing | Ctrl+C at page 2, then PostgreSQL refuses the `run-interrupted` append (experiment E1): stderr holds only the page-1 line and `the ingest was interrupted`; stdout `<A> running`, exit 130. The same for a refused `finish_run(FAILED)` after a `MemoryError` (E2), a lost `finish_run(FAILED)` (E3), and a refused `record_observation` of the pending observation (E4b). The operator never learns which write failed or that the database refused it | Every refused or lost write (and every lost operation) in the K cleanup writes the required line naming the operation and the identity, with at most the class name, and a red-first unit test pins it (for example, by extending `test_unexpected_cleanup_that_meets_a_database_error_leaves_the_run_running` and adding a refused `run-interrupted` case). Or the architect changes AC15 and the plan to exempt the cleanup, and the human approves | Open |
| F-14 | MEDIUM (blocking until the architect decides: spec conflict) | AC15 (same clause, unconditional) versus plan "Required progress" 3 ("from `start_run` on") and § State machine R ("A `PersistenceConnectionError` here -> `NOT_STARTED`, with no new connection") | `_guarded` (583-586) and the reconciliation's `record_observation` (708-711) let `PersistenceConnectionError` pass to the generic handler (1262-1264), whose message is `type(error).__name__` | `<A>` is `running` with a local-only observation 3, and the connection is lost while `record_observation(3)` runs (experiment E8): stderr says only `PersistenceConnectionError`, with no operation and no run named; exit 1; `<A>` stays `running`. The behavior follows the plan; the AC text asks for more | The architect aligns AC15 with the plan (narrowing the "lost" clause to `start_run` on), or the plan with AC15 (a line for a lost reconciliation write, naming the operation and `X`). Then the code and a test follow, and the human approves | Open |
| F-12 | LOW (carried, partially resolved) | harny-audit step 4 (outcome state) and step 5 (recorded red evidence) | `tasks.md` § Status (line 8) still ends "pending the human's approval", and so does § Checkpoint ("pending the human's approval ... Next: after approval, the O10 rework"), though the `Approval` lines say approved. O8 is still `[ ]` rather than `[!]`. O10 rework step 3 says "The human corrects `run_ingest`", but § Working state says "use case fixed by the executor with the human's authorization", which contradicts plan § Rollout M4 ("The executor does not write this module's body") unless that authorization is recorded. No red evidence (command, counts, reasons) is recorded for the round-2 tests | The next role reads a stale state. The authorship deviation is not traceable to a recorded decision | § Status and § Checkpoint are corrected. O8 is checked or marked `[!]` with its reason. The human's authorization for the executor to edit `run_ingest` is recorded (or step 3 is corrected). The round-2 red evidence is recorded (the auditor's retroactive run: 161 failed against `7603379` code) | Open |
| F-15 | LOW (spec gap) | Plan § State machine H message rule ("Any failure -> NOT_STARTED, with a fixed message naming the execution id ... never only an exception's class name"); § State machine C ("Before the new run exists ... NOT_STARTED, exit 1"); AC24 | Only `PersistenceNotFoundError` is a listed H read failure. A refused read (`PersistenceIntegrityError`, plain `PersistenceError`) or a lost connection in T (965), H (993) or I reaches the generic handler (1262-1264) with message `type(error).__name__`. This is the executor's choice noted in `tasks.md` § Working state | A refused `read_observation` during the chain check (E5) -> `NOT_STARTED`, exit 1, stderr `PersistenceIntegrityError`, without naming `<A>`. A lost `list_audit_events` (E6) or target `read_run` (E7) -> `PersistenceConnectionError`. The exit code and "nothing written" are right; only the message is bare. Reading H's "Any failure" broadly would make this a breach, but the plan lists the failures and C governs losses, so the auditor rates it a gap, not a violation | The architect states the message for a refused or lost read before the run exists (R already requires "a message naming X" for its refusals), and a test pins it, or the architect confirms the class-name message | Open |
| F-16 | LOW | Plan § `run_ingest` ("returns an outcome for every ending except a `KeyboardInterrupt` raised during its own interruption cleanup and `SystemExit`"); AC15 ("exactly one line") | (a) `ingest_use_case.py:941-944` catches only `PersistenceError` around `open_repository()`, so a `KeyboardInterrupt` or `MemoryError` there escapes `run_ingest` (experiment E13). This was present in round 1 and missed then. (b) `ingest_command.py:293-296` suppresses only `Exception` around `source.close()`. A `KeyboardInterrupt` during it, after `_report` printed `<id> <status>`, reaches `_print_running` (338-340) and prints a second line `<id> running`, with exit 130 | (a) The CLI still gives 130 or 1 with empty stdout, so nothing visible changes. (b) Needs a Ctrl+C in the instant the HTTP client closes; stdout then holds two lines | (a) Caught inside `run_ingest` (`INTERRUPTED` or `NOT_STARTED`), or the plan's sentence amended. (b) The result line is printed once whatever happens in the `finally`. Tests pin both | Open |
| F-17 | LOW | AC21 (docs say what exists; not a listed item) | README § Ingesting gives `running` only "(after Ctrl+C, or after a lost database connection it could not recover)". Since Revision 8 it also follows a refused `finish_run(FAILED)`, a cleanup that cannot read the run, and any exception that escapes after the run was announced. The exit-2 row does not name a malformed proxy or certificate setting (it says "a missing or invalid environment variable") | An operator who reads `running` after a database refusal finds no matching case in the README | README lists the cases or says "whenever closing was not confirmed", and the exit-2 row names the proxy and certificate settings | Open |

## Defect-hunting checklist (the rewritten module read against the state machines)

| Area | Result |
|---|---|
| Order: local store -> PostgreSQL -> events -> finish | Holds (journal-order tests; `interrupt_during_record` journal) |
| Write-once evidence never overwritten | Holds: one `store` per (id, sequence); `next_sequence` grows only after `store` returns; a resumption uses a new id; the F1 listing is read-only |
| No retries | Holds (`no_retry`; one request per loop iteration; no page requested after an ending) |
| Pending local observation (F-01, F-02) | Holds: pending from before `store` until `record_observation` returns, including the C repeat and the P step 3 read-back path; cleared only on the concluded paths |
| Secrets, URLs and tracebacks never printed | Holds: progress uses fixed words, numbers, hashes, ids and class names; the CLI prints `str()` only of migration errors (fixed texts) and the outcome message (fixed texts and ids) |
| Exit codes | Holds for every row, including step 2 (F-03) and K step 1 (F-05) |
| Connection loss (C) | Holds: one new connection, exclusion again, safe repeats, append re-check, no third connection, P-2. Losses are reported (`_report_loss`) except in K (F-13) |
| Refused writes | Holds for every table row; at most one `storage-failed` (`postgresql`) per run; never `unexpected-error` (57 tests) |
| Interruption cleanup (K) | Holds for behavior (`read_run` guard, read-back, stop with `running`, second `KeyboardInterrupt` propagates). Silent on refusals and losses (F-13) |
| Reconciliation (R) | Holds, including F-10 and F-11. A loss is reported by class name only (F-14) |
| Chain validation (H), `last-page-reached` validity, coverage, P-4 | Holds (129 + 33 + 12 unit, 3 integration). Bare message for refused or lost reads (F-15) |
| Execution-id checks (I) | Holds |
| `KeyboardInterrupt`, `SystemExit`, `MemoryError` propagation | `SystemExit` is never caught (tests). A second `KeyboardInterrupt` propagates. `MemoryError` gets `unexpected-error` inside the run and exit 1 while the source is built. Edge F-16 (a) at `open_repository()` |
| Leaked repositories or sources | None: `run_ingest`'s `finally` closes the current repository; `_reconnect` closes the lost one and a failed second one; double closes are safe (idempotent `close`); the source is closed in `_invoke`'s `finally` |
| Unconfirmed `start_run` | The outcome names the id with `running` (line 1036); this is what plan § State machine C prescribes (note) |

## Executor choices where the plan was silent

| Choice | Assessment |
|---|---|
| Cleanup message texts: `the ingest was interrupted`, `unexpected error: <ClassName>` (`ingest_use_case.py:1250-1275`), CLI `interrupted` (`ingest_command.py:340`) | Compliant: fixed words, plus a class name for non-project errors, as § Output allows. The K progress gap is F-13 |
| Any non-connection `PersistenceError` on the repeat of the final `finish_run(SUCCEEDED)` handled like the P-2 `PersistenceIntegrityError` case: `RUN_FAILED` with the stored status read by `read_run`, no `storage-failed`, `running` if that read fails (`ingest_use_case.py:448-462`) | Compliant and conservative: C step 5 says no `storage-failed` or `finish_run(FAILED)` after the P-2 repeat, and "Refused writes" says C's rules come first. Pinned by one `connection_loss_final_finish` case (mutant M11 killed). Lines 455-456 are untested. A lost `read_run` there prints nothing (F-13) |
| Refusals or losses during the target, chain or id reads, other than `PersistenceNotFoundError`, reach the generic `NOT_STARTED` handler with a class-name message (`ingest_use_case.py:1262-1264`) | Exit code and "nothing written" are correct. Whether it breaks the plan's "never only a class name" depends on whether H's "Any failure" covers an operational read failure. The plan lists the H failures and C governs losses, so the auditor rates it a spec gap, LOW (F-15). AC15 covers writes only, so AC15 is not broken by it. AC24's message rule covers the cyclic, malformed or contradictory verdicts, and those all name the id |

## Commands run (2026-10-18, repository root, `91bd69d`)

| Command | Result | Label |
|---|---|---|
| `uv sync --locked` | ok, 25 packages | rerun |
| `uv run pytest -q` (no `--env-file`) | 1899 passed, 266 skipped | rerun |
| `uv run --env-file .env pytest --cov=ec_procurement_quality --cov-report=term-missing -q` | 2165 passed, 0 skipped, TOTAL 97 % | rerun |
| `uv run ruff check .` | All checks passed | rerun |
| `uv run ruff format --check .` | 119 files already formatted (before this report was written) | rerun |
| `uv run mypy .` | Success, 52 source files | rerun |
| `uv run node .sdd/doctor/run-doctor.mjs` | 31 ok, 0 skipped, 0 warned, 0 failed | rerun |
| `uv run ec-procurement-quality --version` | `ec-procurement-quality 0.1.0` | rerun |
| Every focused unit `-k` row of § Validation, including the required Revision 6 tokens (`interrupt_during_record`, `cleanup_read_back`, `interrupt_after_finish`, `chain_unreadable_record`, `progress_line`, `reconcile_os_error`, `database_refusal`, `source_configuration`, `order_of_invocation`, `exit_code_cleanup_read_back`, `exit_code_interrupt_after_finish`, `output_escaping_exception`, `output_progress`, `chain_unreadable_record_message`) | all passed (counts in § AC results and § Resolution) | rerun |
| Every focused integration row of § Validation (`e2e_*`, `migrations`, `root`, `test_ingest_connection_loss.py`, `-k final_finish`, `test_postgres_runs_and_exclusion.py`, the lock-error and runner row) | all passed | rerun |
| `uv run pytest tests/unit/test_local_disk_raw_evidence_store_listing.py -q`; `uv run pytest tests/unit/test_persistence_error_hierarchy.py -q`; `uv run pytest tests/unit/test_cli.py -q` | 25, 3, 2 passed | rerun |
| `uv run --env-file .env pytest tests/unit/ingest tests/integration/ingest -q` | 822 passed | rerun |
| `uv run pytest tests/unit -q -k layer` | 16 passed | rerun |
| AC18 grep of `src/ec_procurement_quality/application/` for `SELECT `, `INSERT `, `UPDATE `, `DELETE `, `objects/`, `observations/`, `.json`, `advisory`, `pg_` | no match | rerun |
| AC20 `git diff main --stat -- migrations tests/unit/test_cli.py ... uv.lock` (the full list of the row) | empty | rerun |
| `git diff main --stat -- uv.lock` | empty | rerun |
| `git diff main -- pyproject.toml` | only `explicit_package_bases = true`, `mypy_path = "src"` and three comment lines, additions only | rerun |
| `git diff main --numstat -- tests/integration/test_postgres_migrations.py` | `3 0` | rerun |
| `git diff main --stat -- compose.yaml .env.example docs/glossary.md docs/adr specs/current` | empty | rerun |
| `git ls-files .env` | empty | rerun |
| `git diff main --check`, `git diff --check` | clean | rerun |
| `git diff 7603379 -U0 -- tests` (removed lines) | only the migrated order assertions (`["migrate"]` -> `["make_source", "migrate"]`, with the source closed once added), doubles refactoring and imports; no weakened assertion | rerun |
| Leftover `ecpq_test_` databases (count only, scratch script through `uv run --env-file .env`) | 0 | rerun |
| Files under the real `data/` | 0 before and after the suites | rerun |
| `gh pr checks 25`; `gh run list --branch feat/ingest-command` | `feedback` pass, `tests` pass, head `91bd69d` | rerun |
| CI `tests` log (run 39147642720, merge of `91bd69d` into `6b34374`) | 2165 passed, TOTAL 97 % (Linux) | reused |
| CI `feedback` log (run 39147642707) | `harny-feedback: 2 of 2 command(s) ran, 0 skipped.` | reused |
| Mutants M1 to M12 (scratch copy, focused tokens) | 12 of 12 killed | experiment |
| Current unit tests against the round-1 use case and command (`git show 7603379:...`) | 161 failed, 577 passed (round-2 tokens: 141 failed, 23 passed) | experiment |
| Experiments E1 to E13 (scratch test file over the repository's doubles) | results quoted in § Findings and § Test coverage | experiment |

## Conventions and feedback

- harny-standards, checked against `AGENTS.md` (the project's conventions
  document):
  - layer boundaries hold;
  - raw responses are never overwritten;
  - no SERCOP contract is invented: synthetic `.invalid` data only;
  - no dependency, infrastructure or service was added (the F-1 config change
    was approved);
  - no secrets are in source, tests or docs (gitleaks and the CI secret scan
    pass in the doctor);
  - verification was run and reported (`tasks.md` § Working state, last
    command).

  No violation was found. The round-1 dead code (F-08) and stale docstring
  (F-09) are gone.
- harny-feedback: the workflow `.github/workflows/harny-feedback.yml` exists, and
  its latest run, at `91bd69d`, is green with 2 of 2 commands run. The per-turn
  PostToolUse and Stop hooks are configured in `.claude/settings.json`. Whether
  they fired and were heeded during the rework is `unavailable`: no hook log is
  kept, and `AGENTS.md` notes that the hooks run only when `.venv` is on `PATH`.

## Reservations carried forward

- Persistence U1: the real commit-in-flight case is still untested against
  PostgreSQL. The unit `FlakyRepository` and the integration `Kill*Repository`
  seams cover the deterministic cases. This is recorded in CHANGELOG Known
  limitations.
- Persistence N5: the reconciliation reads run in separate snapshots. This is
  safe under the ingest exclusion: R runs only after the exclusion is held.
- Raw-evidence N2: now handled both for `store` (AC6 b, F-3) and for the
  interruption cleanup (F-02 resolved).
- Source-access R-6 and raw-evidence N3: hold. Only class names or fixed project
  texts are printed, and the F-03 message carries the class name only.
- Source-access R-7: holds. The guard now covers the construction of the source
  too.
- Source-access R-11: holds. One source per invocation, built once and closed
  once, on every path including a refused migration.
- Source-access U1: open until the human's Day 20 live run. No document claims
  that a live run happened: README, CHANGELOG, AGENTS.md and the journal all say
  none was made.

## What could not be verified

- Behavior against the real SERCOP source and the real `data/raw/`: out of scope,
  and it must not be run.
- A real Ctrl+C delivered to a live `psycopg` or disk operation. F-01, F-02,
  F-05 and F-13 were checked with the repository's doubles, which interrupt at
  the same call boundaries.
- A real malformed proxy against a live network. The unit tests build the real
  `SercopSource` from the environment; construction opens no socket, and the
  guard stays silent.
- `pg_terminate_backend` of a real stale session that holds the exclusion (the
  README procedure was not exercised).
- That the per-turn feedback hook fired during the rework (see § Conventions
  and feedback).
- The human's authorization for the executor to edit the body of `run_ingest`
  during the rework: `tasks.md` § Working state states it, and no other record
  was found (F-12).

## Audit log

| Round | Date | Verdict | Notes |
|---|---|---|---|
| 1 | 2026-10-18 | REJECTED | At `7603379`. F-01 and F-02 (CRITICAL, AC7, AC15, State machine K) and F-03 (HIGH, binding constraint and AC14) block. F-04 to F-07 MEDIUM, F-08 to F-12 LOW. Sent back to the architect |
| 2 | 2026-10-18 | REJECTED | At `91bd69d`. F-01 to F-11 resolved, each with tests that fail on the round-1 code and a killed mutant; F-12 partially resolved. New: F-13 (MEDIUM, blocking: the K cleanup prints no line for a refused or lost write, AC15) and F-14 (MEDIUM, blocking until the architect decides: AC15 versus plan required progress 3 for reconciliation losses); F-15 to F-17 LOW. 2165 tests pass locally and in CI. Next: the architect (F-14, F-15), then red tests and the fix of the cleanup |
