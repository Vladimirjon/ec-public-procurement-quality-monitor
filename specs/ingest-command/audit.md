# Audit: Ingest command (F4)

Auditor: `sdd-auditor` (outcome O10), round 3, 2026-10-18.
Reviewed: branch `feat/ingest-command` at `287946f` (clean working tree), PR #25
against `main` (base `6b34374`). Specs: `intent.md` Revision 9, `execution-plan.md`
Revision 7 and `tasks.md` Revision 4, all approved by the human on 2026-10-18.

The whole feature was audited again. Nothing was assumed to still hold from
rounds 1 and 2. `application/ingest_use_case.py` (393 lines changed since round
2) and `interfaces/ingest_command.py` were read in full against the state
machines P, C, K, T, R, H and I, the "Refused writes" table, the required
progress lines and the invocation order. `interfaces/cli.py` was also read in
full. The test changes since round 2 (`git diff 91bd69d -- tests`) were read
for weakened assertions, and the README change was read against plan
§ Consumers and migration "Docs".

Evidence labels:

- `rerun`: the auditor ran it in this round.
- `reused`: a recorded result that is still current (the CI runs of PR #25 at
  `287946f`).
- `experiment`: a throwaway auditor test or mutant in the session scratchpad
  (never in the repository). It runs against a scratch copy of `src/` and
  `tests/` with the repository's own doubles from `tests/unit/ingest/conftest.py`.
- `unavailable`: it could not be checked.

## Final verdict

REJECTED

**Summary**: The round-2 rework is real and well tested. F-13 to F-17 are
resolved, and so are F-01 to F-11 again. Each fix is pinned by tests that fail
on the round-2 code: 104 of the 131 new unit tests fail there. The suite kills
28 of 28 auditor mutants. 2296 tests pass locally and in CI, and every focused
row of § Validation passes.

One new defect breaks a guarantee of AC8 and of plan § State machine C step 3
(F-18). The second repository of State machine C becomes the current one before
it holds the ingest exclusion. Only a `PersistenceError` from
`try_acquire_ingest_exclusion` is handled there. If a Ctrl+C or a `MemoryError`
lands during that call, the K cleanup writes `run-interrupted` (or
`unexpected-error`) and `finish_run(failed)` through a connection that does not
hold the exclusion. An auditor experiment did this while another session held
the exclusion. AC8 (c) says that in that situation "the run is not touched (no
event, no `finish_run`)". The window is narrow: a double fault during one
statement. The fix is small. But an unmet guarantee of an AC or a binding
constraint blocks approval at any severity. K's text ("any other exception
after `start_run` returned: the same steps 1 to 4") and C step 3 ("an error ->
the run is not touched") collide here. So the architect states the
conservative reading, and a Validation row is added for it.

**Critical Issues** (must fix before merge):
- F-18 (HIGH, blocking: AC8 (c) and plan § State machine C step 3, Q4): a Ctrl+C or a `MemoryError` during the second `try_acquire_ingest_exclusion` makes the K cleanup write to the run without the exclusion, even while another session holds it.

**Warnings** (should fix, not blocking):
- F-12 (LOW, carried, partially resolved): `tasks.md` § Status still says the Revision 9/7/4 specs are "pending the human's approval". § Checkpoint still says "Next: the O10 round 2 rework". O8's to-do still says the README content is "Not yet written". O10 round 2 step 3 asked that the human's choice of who corrects the use case be recorded before the work started, and it is not recorded.
- F-19 (LOW): when the second `open_repository()` raises a non-database exception (`MemoryError`, Ctrl+C), the K cleanup runs on the already-closed first repository. Its only line is `read_run failed: run <A> (RuntimeError)`, which names an operation that never reached the database. The outcome (`running`, nothing written) is correct.

**Recommendations** (nice to have):
- F-20 (LOW): five code paths have no test: an unconfirmed `start_run` (line 1239), an unconfirmed normal-path append (475), the read-back path whose `record_observation` is refused or unconfirmed (1325-1336), a lost append after the re-check (285-286), and the generic `NOT_STARTED` fallback (1468). Auditor experiments show that each behaves as the plan says.

Next role: the architect. One sentence in § State machine C step 3 (or K) is
needed: C step 3 governs every exception raised while the second repository is
opened or its exclusion is taken, and the K cleanup never writes through a
repository that does not hold the exclusion. A Validation row with a `-k` token
is also needed. Then the test-writer writes the red test (the auditor's
experiment X1 is a ready template), the use case is corrected, and `tasks.md`
is brought up to date (F-12). Then audit round 4. F-19 can be settled by the
same sentence. F-20 is optional.

## Rounds 1 and 2 summary

- **Round 1** (2026-10-18, `7603379`, REJECTED). 12 findings; F-01 and F-02
  (CRITICAL, AC7 and AC15, State machine K) and F-03 (HIGH, AC14 and the ADR
  0006 constraint) blocked. The specs were revised (intent Revision 8, plan
  Revision 6, tasks Revision 3) and the rework landed in `5610e02`, `eb3a317`
  and `91bd69d`. The full report is in git history (`7069f4c`).
- **Round 2** (2026-10-18, `91bd69d`, REJECTED). F-01 to F-11 were resolved,
  and F-12 was partially resolved. New: F-13 (MEDIUM, blocking: the K cleanup
  wrote no line for a refused or lost operation, AC15), F-14 (MEDIUM, blocking
  until the architect decided: AC15 against plan required progress 3), and F-15
  to F-17 (LOW). The specs were revised (intent Revision 9, plan Revision 7,
  tasks Revision 4, approved on 2026-10-18), and the rework landed in `53fa44c`
  (red tests), `85c4bd8` (use case, command, README) and `287946f` (evidence).
  The full report is in git history (`2f77b5e`).

## Resolution of the earlier findings

Each closure condition was checked against the code, and against at least one
test that fails without the fix. For the round-2 findings, the auditor ran the
current tests against the round-2 code (`git show 91bd69d:` of the use case and
the command, in a scratch copy): `tests/unit/ingest` gives `104 failed, 765
passed`, the same as `tasks.md` § Working state records. Every failure is an
assertion on behavior, with no import, collection, database or socket error. The
28 new tests that pass on the round-2 code are expected to:

- the negative controls ("an answer gets no line");
- the reconciliation refusal cases, whose lines already existed in round 2;
- the CLI-tier F-16 (a) guards, which the plan declares as passing before the
  fix;
- the `single_result_line` cases with an escaping exception or no run.

Every fix was also reverted by an auditor mutant (`experiment`).

| Id | Earlier severity | Status | Evidence (code; tests; mutant) |
|---|---|---|---|
| F-01 | CRITICAL | Resolved (still) | `ingest_use_case.py:1302` marks the sequence pending before `store`. It is cleared only when `record_observation` returns (1390), or when the path has concluded (1335, 1348, 1381). K reads it back and records it (642-655). `interrupt_during_record`: 4 passed. Mutant M1 (clear after `store`) -> 3 failed |
| F-02 | CRITICAL | Resolved (still) | K absorbs `EvidenceNotFoundError`, `EvidenceIntegrityError` and `OSError` from its read-back (643-646) and still appends and closes the run. `cleanup_read_back or exit_code_cleanup_read_back`: 14 passed. Mutant M2 -> 10 failed |
| F-03 | HIGH | Resolved (still) | `ingest_command.py:281-287` builds the source before `_migrate` (289). Any `Exception` except `MemoryError` gives exit 2 with the six-variable message and the class name. `source_configuration or order_of_invocation`: 30 passed. Mutant M8 (source after the migrations) -> 28 failed |
| F-04 | MEDIUM | Resolved (still) | `_print_running` on both escaping branches (348-355). `output_escaping_exception`: 12 passed. Mutant M9 -> 2 failed |
| F-05 | MEDIUM | Resolved (still) | K reads the run first and returns the stored status for a finished run (632-641). `interrupt_after_finish`: 11 passed; `exit_code_interrupt_after_finish`: 6 passed. Mutant M3 -> 9 failed |
| F-06 | MEDIUM | Resolved (still) | The chain check maps the store's read errors to `invalid resumption chain <id>` (1196-1206). `chain_unreadable_record`: 12 passed. Mutant M4 -> 9 failed |
| F-07 | MEDIUM | Resolved, K included | Page lines (`_report_page` 323-327; `page N no response` 1287; `page N sequence S not stored` 1345-1347). The K lines are F-13 below. Progress group: 24 passed. Mutant M5 (no page line) -> 6 failed |
| F-08 | LOW | Resolved (still) | No `_finish` helper. The 11 uncovered lines are branches, not a dead helper |
| F-09 | LOW | Resolved (still) | `ingestion_catalogue.py:155` says "32 characters" |
| F-10 | LOW | Resolved (still) | 823-853: the listing `OSError` gives `local-listing-failed`; an unreadable or vanished record gives `local-observation-unreadable`; a `read_content` `OSError` gives `object-integrity`. `reconcile_os_error`: 4 passed. Mutant M6 -> 1 failed |
| F-11 | LOW | Resolved (still) | `_append_on_normal_path` (458-483), `_close_failed` (390-431), `_finish_succeeded` (486-522), and refused `start_run` (1240-1242). `database_refusal`: 57 passed, never `unexpected-error`. Mutant M7 -> 9 failed |
| F-12 | LOW | Open (partially resolved) | Red evidence for round 2 is now recorded (§ Working state: 104 failed, 765 passed; confirmed by the auditor). Still stale: see F-12 under § Findings |
| F-13 | MEDIUM | Resolved | `_cleanup_step` (593-609) wraps each of K's four database operations (`read_run` 632, `record_observation` 649, the append 657, `finish_run` 670). On any `Exception` it writes exactly one line (`_report_failure` 126-151: the operation, the event type, `failed` or the sequence, the run, at most the class name) and stops; a second `KeyboardInterrupt` propagates. The `read_run` after a refused P-2 repeat has its line (511-515). `cleanup_database_error`: 32 passed (Ctrl+C and `MemoryError` x 4 operations x refused, plain, lost and a synthetic defect). `final_finish_read_run`: 3 passed. `output_database_error`: 14 passed. The extended `test_unexpected_cleanup_that_meets_a_database_error_leaves_the_run_running` passed. Mutants: N1 (K silent) -> 47 failed; N18 (two lines) -> 32 failed; N19 (lines only for `PersistenceError`) -> 8 failed; N2 (P-2 `read_run` silent) -> 3 failed |
| F-14 | MEDIUM | Resolved (the architect chose AC15) | Lines for every refused or lost operation before the run exists: the opening (1120-1122), the exclusion (1141-1144), T (`_read_database` 732-751), R (`_guarded` 711-729, `_reconciliation_stopped` 691-708, the lost reconciliation `record_observation` 866-873), H (1015, 1024-1027, 987-993), I (579-581), and C's second opening and exclusion (201-213). `pre_run_database_error`: 59 passed; the two `connection_loss` tests of the second opening and exclusion: 4 passed. Mutants: N3 -> 24 failed; N4 -> 18 failed; N12 -> 3 failed; N13 -> 2 failed; N14 -> 2 failed; N15 -> 3 failed; N16 -> 3 failed |
| F-15 | LOW | Resolved | T: an unreadable target gives `NOT_STARTED` with `the resumption target <id> could not be read` (1160-1165), never `INVALID_TARGET`. R: `the reconciliation of run <X> could not be completed`, or `the running runs could not be listed` (704-708). H: `the resumption chain of <id> could not be read` (1191-1195), which does not call the chain invalid. I: `the execution id <id> could not be checked` (1217-1221), for the database read and for the store listing. `pre_run_database_error_exit_code`: 12 passed (exit 1, not 2; the final line names the identity). Mutants: N5 (T -> `INVALID_TARGET`) -> 9 failed; N6 (H called invalid) -> 9 failed; N7 (I without the id) -> 5 failed; N8 (R class name only) -> 21 failed; N17 (I retries instead) -> 2 failed |
| F-16 | LOW | Resolved | (a) `run_ingest` handles every exception of the first `open_repository()` (1118-1129): Ctrl+C gives `INTERRUPTED` with no run; anything else gives `NOT_STARTED` with `the repository could not be opened: <Class>`. A Ctrl+C at the first exclusion is closed by the `finally` (1481-1482). `repository_open_error`: 11 passed. Mutants N9 -> 1 failed; N10 -> 2 failed. (b) `_StderrReporter.result_written` is set by `_report` (234), and `_print_running` prints nothing once it is set (243). `single_result_line`: 8 passed (`<A> succeeded`, `<A> failed`, `<A> running` exactly once; nothing after a refused migration; exit 130). Mutant N11 -> 4 failed |
| F-17 | LOW | Resolved | README § Ingesting (`README.md:252-272`) lists the five `running` cases of plan § Consumers "Docs". The next `ingest` closes such a run. The exit-2 row names the six proxy and certificate variables (278). The exit-1 row says that an unreadable resumption target is exit 1, not 2 (277). stderr names each database operation that was refused or lost (268-272). Inspection (rerun) |

## Findings

Round-3 findings and the carried F-12. The resolved findings are in
§ Resolution of the earlier findings.

| Id | Severity | AC / constraint | Finding and evidence | Failure scenario | Closure condition | Status |
|---|---|---|---|---|---|---|
| F-18 | HIGH (blocking: an unmet AC8 guarantee and a binding state-machine step) | AC8 ("on exactly one new connection it takes the ingest exclusion again ... when it cannot, it leaves the run `running`"; example (c): "another session holds the exclusion: the run is not touched (no event, no `finish_run`)"); plan § State machine C step 3 ("`False` or an error -> close it; the run is not touched"); Q4 (one ingest active per database) | `_PersistenceSession._reconnect` (`ingest_use_case.py:194-217`) sets `self.repository = repository` (205) before the exclusion is taken. It then catches only `PersistenceError` around `try_acquire_ingest_exclusion()` (206-213). A `KeyboardInterrupt` or any other `Exception` there leaves `session.repository` pointing at a repository without the exclusion. The outer handlers of `run_ingest` (1451-1480) then run State machine K through `session.repository`. K follows its own text ("any other `Exception` ... after `start_run` returned: the same steps 1 to 4"). C step 3 says the run is not touched. The plan never settles the collision, and the code takes the reading that writes | Experiment X1: `record_observation` of sequence 2 is lost before commit. A hook gives the exclusion to another session at the loss. The second repository's `try_acquire_ingest_exclusion` raises `KeyboardInterrupt`. Result: the attempts are `(2, read_run)`, `(2, append_audit_event run-interrupted)` and `(2, finish_run failed)`. The run is `failed` with a `run-interrupted` event while the other session still holds the exclusion. Outcome `INTERRUPTED`/`failed`, so the CLI gives exit 130 and stdout `<A> failed`. Experiment X1b: the same with `MemoryError` writes `unexpected-error` and `finish_run(failed)`. The real-world case is a race with a second `ingest` that took the exclusion after the first session dropped and is reconciling `<A>`. Both processes then write to `<A>`, and an event can land after the other's `finish_run` (AC11) | The architect states that C step 3 covers every exception raised while the second repository is opened or its exclusion is taken: close it, no event, no `finish_run`, `running` (`INTERRUPTED` for Ctrl+C, `RUN_FAILED` otherwise), with the line of the operation that raised. The architect also states that K never writes through a repository that does not hold the exclusion, and adds a Validation row and a token. Then a red-first unit test pins it (X1 is a template), the use case is corrected (for example, the second repository becomes current only after the exclusion returns `True`, and a `BaseException` during the acquisition closes it), and the human approves | Open |
| F-19 | LOW | AC15 (the line names the operation that failed); plan § State machine C step 2 ("A failure -> left `running`") | `_reconnect` closes the lost repository (195-196) and then calls `open_repository()` inside `_reporting_failure`, which handles only `PersistenceError` (201-204). A `MemoryError` or a Ctrl+C there reaches K, which runs on the closed first repository. Its `read_run` raises `RuntimeError`, and `_cleanup_step` writes `read_run failed: run <A> (RuntimeError)`. This is the executor's choice noted in `tasks.md` § Working state | Experiments X2 and X3: a lost `record_observation` of sequence 2, then the second opening raises `MemoryError` (or `KeyboardInterrupt`). Outcome `RUN_FAILED` (or `INTERRUPTED`) with `running`, nothing written, all repositories closed: that is correct. stderr says `read_run failed ... (RuntimeError)` and never names the opening that failed. An operator would look for a database refusal of `read_run` that never happened | The same sentence as F-18 (an exception from C steps 2 and 3 leaves the run `running` without entering K, with a line naming the operation that raised), or the architect confirms the current line. A test pins the chosen line | Open |
| F-12 | LOW (carried, partially resolved) | harny-audit step 4 (outcome state); plan § Rollout M4 (authorship of `run_ingest`) | `tasks.md` § Status (line 8) says the specs are revised again, "**pending the human's approval**", though the `Approval` lines and the bullets below say approved. § Checkpoint (line 379) ends "Next: the O10 round 2 rework ... and the audit round 3". O8's to-do (line 289) still says "Not yet written; the evidence below predates it", though `README.md` now has the content and § Working state says so. O10 round 2 step 3 asks to "record the human's choice here before the work starts" for who corrects `run_ingest`. Nothing is recorded: § Working state names only the executor ("Green (executor, re-run)"), and the round-1 instruction ("Corrige tú run_ingest contra las pruebas rojas") is the only recorded authorization | The next role reads a stale state, and the authorship of the round-2 use-case fix has no recorded decision behind it | § Status, § Checkpoint and O8's to-do are corrected. The human's choice for the round-2 (and next) use-case correction is recorded | Open |
| F-20 | LOW | harny-audit step 5 (a test that would fail if the behavior were removed) | Five branches have no test. Line 1239: a `start_run` whose connection is lost when the second opening also fails, so stdout `<id> running` without `run started`; the README lists this case. Line 475: a normal-path append that cannot be confirmed. Lines 1325-1336: the AC6 (b) read-back path whose `record_observation` is unconfirmed or refused. Lines 285-286: the append on the new connection lost after the re-check. Line 1468: the generic `NOT_STARTED` fallback for a non-database exception before the run exists (its message is only the class name, for example `MemoryError`; AC15 allows that for a non-project error) | A regression on these paths would go unnoticed. Experiments X6, X7, X7b, X9 and X4 show the planned behavior today: `running` with the id; `storage-failed` (`postgresql`, 2, 2) with one line; `running`; two lines for two lost calls; `NOT_STARTED` | Optional: tests for at least 1239 and 1325-1336, the two paths with a documented or AC-level outcome | Open (recommendation) |

## Executor choices where the plan was silent

| Choice | Assessment |
|---|---|
| Line wording (`_report_failure` 126-151): `connection lost during <operation>[ <detail>]: run <id>[ sequence <s>]` for a loss (no class name); `<operation>[ <detail>] refused: run <id>[ sequence <s>] (<Class>)` for a refusal; `... failed: ... (<Class>)` for a non-database exception in K | Compliant with plan § Public names "Required progress": the operation, the event type or status, the identity, and at most the class name; never `str()` of an error. The forms with a status read oddly (`finish_run failed refused`, `finish_run failed failed ... (RuntimeError)`), but they are unambiguous. No finding |
| When the second `open_repository()` raises a non-database error, K runs on the already-closed first repository | Rated LOW (F-19): the outcome and the writes are right; the line misnames the failed operation. The neighboring case, an exception during the second exclusion, is not harmless: F-18 |
| A drawn id whose check cannot be made is not retried | Compliant: plan § State machine I says "A check that cannot be made -> `NOT_STARTED`". Only a taken id is redrawn (up to three). Mutant N17 (retry instead) is killed by 2 tests |
| The generic `NOT_STARTED` fallback (1466-1468), untested | Its behavior is compliant: the plan requires an outcome for every ending, and AC15 allows a bare class name for a non-project exception; nothing is written (experiment X4). The missing test is F-20 |
| Uncovered lines 285-286, 475, 1239, 1325-1336 and 1468 | Driven by experiments X9, X6, X7, X7b and X4: each behaves as the plan says. 1239 and 1325-1336 matter most (a documented `running` case, and an AC6 (b) combination). The others are second-order fault paths. F-20 |

## Defect-hunting checklist (the rewritten parts against the state machines)

| Area | Result |
|---|---|
| Opening (F-16 a) | Holds. `PersistenceError` gives one line and `NOT_STARTED`. Ctrl+C gives `INTERRUPTED` with no run. Any other exception gives `NOT_STARTED` naming the opening. The repository is closed by the `finally`. Note, not a finding: lines 1130-1137 run between the return of `open_repository()` and the `try` (pure Python, no I/O). A Ctrl+C in that window would leave the connection to process exit |
| Exclusion | Holds on the first connection. On the second connection: F-18 |
| T, R, H, I (F-14, F-15) | Hold: exactly one line per failed call, a fixed message naming the identity, exit 1, no new connection, nothing more written. A "not found" read as an answer gets no line. Tested: 59 + 12 + negative controls |
| Order: local store -> PostgreSQL -> events -> finish | Holds (journal-order tests; unchanged since round 2) |
| Write-once evidence | Holds: one `store` per (id, sequence); `next_sequence` grows only after `store` returns; a resumption uses a new id |
| No retries | Holds: one `search_page` per loop iteration (1268-1278); `no_retry` 6 passed |
| C: one new connection, safe repeats, re-check, P-2 | Holds (43 `connection_loss`, 12 `connection_loss_final_finish`, 4 integration `final_finish`). One line per failed call, including a repeat that fails again (experiments X8, X9). Gap: F-18 and F-19 at steps 2 and 3 |
| K (F-13) | Holds: the `read_run` guard, the pending read-back, one line and a stop at any failure of its four operations, a second Ctrl+C propagates, no new connection. Gap: K can run on a repository without the exclusion (F-18) |
| Refused writes | Holds for every table row; at most one `storage-failed` (`postgresql`); never `unexpected-error` (57 tests) |
| Secrets, URLs, tracebacks, exception text | Holds. Lines use fixed words, ids, numbers, hashes and class names. The command prints `str()` only of migration errors (F3 fixed texts) and the outcome message (fixed texts and ids). Every new test plants a marker in the error text and checks it is absent |
| Exit codes | Hold for every row, including 1 (never 2) for an unreadable target, and 130 for a Ctrl+C while the source closes |
| The single result line (F-16 b) | Holds: `result_written` is set as soon as `_report` has written; `_print_running` respects it |
| Leaked repositories or sources | None found. Every test checks `opener.all_closed`, and so does each experiment, X1 to X9. The source is closed in `_invoke`'s `finally` |
| Interrupt handling | Holds except F-18 |

## AC results

| AC | Status | Evidence |
|---|---|---|
| AC1 | PASS | `-k success` 9; `-k e2e_success` 2 passed (rerun) |
| AC2 | PASS | `-k repeat` 5; `-k e2e_repeat` 2 passed (rerun) |
| AC3 | PASS | `-k last_page` 41, `-k last_page_p3` 6, `-k e2e_last_page` 2 passed (rerun) |
| AC4 | PASS | `-k failure_with_response` 16; `-k e2e_failure` 5 passed (rerun) |
| AC5 | PASS | `-k failure_without_response` 6 passed (rerun) |
| AC6 | PASS | `-k storage` 16 and `-k database_refusal` 57 passed (rerun). (a) and (d) also on Linux in CI (reused, run 39170154723). The (b) and refusal combination is untested (F-20); experiment X7 shows the planned behavior |
| AC7 | PASS | `-k "interrupt or exit_code"` 140; `interrupt_during_record or cleanup_read_back` 14; `interrupt_after_finish` 11; `cleanup_database_error` 32; `output_database_error` 14 passed (rerun). Mutants M1, M2, M3, N1, N18 and N19 killed (experiment). See F-18 for K running without the exclusion |
| AC8 | PARTIAL | `-k connection_loss` 43 (unit), `test_ingest_connection_loss.py` 7 (integration), `connection_loss_final_finish` 12, integration `final_finish` 4 and `final_finish_read_run` 3 passed (rerun). Unmet: a Ctrl+C or `MemoryError` during the second exclusion makes the cleanup close the run without the exclusion, even while another session holds it (F-18, experiments X1 and X1b) |
| AC9 | PASS | `-k resume` 24; `-k e2e_resume` 5 passed. An unreadable target gives exit 1, not 2: `pre_run_database_error` (T cases) and `pre_run_database_error_exit_code` (rerun) |
| AC10 | PASS | `-k reconcile` 34; `-k e2e_reconcile` 6; `reconcile_os_error` 4 passed. Refused or lost reconciliation operations: `pre_run_database_error` (R cases, 24 parametrized plus the lost `record_observation`) (rerun) |
| AC11 | PASS | `-k closed_run` 3 and `interrupt_after_finish` 11 passed (rerun). The race in F-18 could add an event after another process's finish |
| AC12 | PASS | `-k "execution_id or identity"` 67 passed. An unmakeable id check: `pre_run_database_error` (I cases, the database read and the store listing) (rerun) |
| AC13 | PASS | `-k "scope or catalogue"` 111 passed; `assert_follows_catalogue` in the main, refusal and reconciliation paths (rerun) |
| AC14 | PASS | `-k "usage or environment"` 66; `source_configuration or order_of_invocation` 30 passed; mutants M8 and N5 killed (rerun, experiment) |
| AC15 | PASS | `-k "output or logger"` 81; `output_escaping_exception` 12; the progress group 24; `pre_run_database_error` 59; `repository_open_error or single_result_line` 19; `cleanup_database_error or final_finish_read_run or output_database_error` 49 passed (rerun). Mutants N1 to N4 and N9 to N19 killed (experiment). Note: F-19 misnames one failed operation in a non-database edge case |
| AC16 | PASS | `-k migrations` 11 (integration CLI); `test_persistence_error_hierarchy.py` 3; lock and runner 23 passed. `git diff main --numstat -- tests/integration/test_postgres_migrations.py` -> `3 0` (rerun) |
| AC17 | PASS | `-k no_retry` 6 passed (rerun) |
| AC18 | PASS | `uv run pytest tests/unit -q -k layer` 16 passed. The AC18 grep of `application/` finds nothing. `git diff main --stat -- uv.lock` is empty. `git diff main -- pyproject.toml` shows only the two F-1 keys and three comment lines. `mypy`: 52 files clean (rerun) |
| AC19 | PASS | `uv run --env-file .env pytest tests/unit/ingest tests/integration/ingest -q` -> 953 passed. The real `data/` holds 0 files before and after. 0 `ecpq_test_` databases (rerun) |
| AC20 | PASS | 2296 passed (1307 baseline + 989 F4). The AC20 `git diff main --stat` list is empty. `git ls-files .env` is empty. `git diff main --check` and `git diff --check` are clean. ruff, format, mypy and the doctor (`31 ok, 0 warned, 0 failed`) pass. `--version` -> `ec-procurement-quality 0.1.0` (rerun) |
| AC21 | PASS | Inspection of README § Ingesting (now with the F-17 content), AGENTS.md § Current commands, architecture § Infrastructure boundary and § Open questions, and CHANGELOG Added, Changed and Known limitations. Every document says that no live run happened (`README.md:45`, `305-306`; `CHANGELOG.md:215-218`) (rerun, inspection) |
| AC22 | PASS | `test_local_disk_raw_evidence_store_listing.py` 25 passed (rerun) |
| AC23 | PASS | `test_postgres_runs_and_exclusion.py` 24 passed (rerun) |
| AC24 | PASS | `-k chain` 140, `chain_last_page` 33, `e2e_chain_last_page` 3 and `chain_unreadable_record` 12 passed. An unreadable chain read is an operational failure, not a verdict: `pre_run_database_error` (H cases); mutant N6 killed (rerun, experiment) |
| AC25 | PASS | `-k "paths or environment"` 34 (unit); `-k root` 2 (integration) passed (rerun) |

Plan decisions and implementation findings:

| Item | Status | Evidence |
|---|---|---|
| P-1 | PASS | `ingest_command.py:256-264`: `MigrationLockError` -> 1, any other `MigrationError` -> 2, `PersistenceError` -> 1. Lock and runner row: 23 passed |
| P-2 | PASS | `_finish_succeeded` (486-522): the exact repeat with the same `finished_at`; no `storage-failed` after a refused repeat. The stored status is read with its own line (F-13). Unit 12, integration 4 and `final_finish_read_run` 3 passed |
| P-3 | PASS | `ingest_use_case.py:1433-1448` |
| P-4 | PASS | `_resume_plan` (1046-1104) with `pages_left_to_request` |
| P-5 | PASS | `_unconfirmed` (381-387); K's `running` (681-687); `_print_running` (`ingest_command.py:238-244`) |
| F-1 | PASS | `git diff main -- pyproject.toml`: `explicit_package_bases = true`, `mypy_path = "src"` and three comment lines, additions only |
| F-2 | PASS | `ingestion_catalogue.py:155` |
| F-3 | PASS | `ingest_use_case.py:1310-1316` catches the three read-back errors |

## Binding-constraint compliance

| Constraint | Status | Evidence |
|---|---|---|
| Layer placement (ADR 0001, AC18) | PASS | Layer tests 16 passed; AC18 grep clean; `interfaces` imports neither `httpx` nor `psycopg` |
| Public names and signatures | PASS | The pinned types and the `run_ingest` signature are unchanged. `run_ingest` now returns an outcome for every ending of the first opening (F-16 a) |
| CLI arguments and configuration | PASS | `cli.py` and `ingest_command.py:109-170`, unchanged since round 2; `test_cli.py` 2 passed |
| Order of an invocation (Revision 7) | PASS | Steps 1, 2, 3, 4, 5.1 (F-16 a), 5.2 (exclusion line), 6 and 7 (a Ctrl+C during `close()` gives 130 with no second line) |
| Exit codes | PASS | `_EXIT_CODES` (218-224), step 2 and step 3 mappings, and 1 (never 2) for an unreadable target |
| Output (AC15) | PASS | One result line at most; a line for each refused or lost operation in every phase; no secrets. Note F-19 |
| Audit details (closed catalogue) | PASS | `assert_follows_catalogue` across the paths |
| State machine P and "Refused writes" | PASS | Unchanged behavior since round 2, re-read in full; every table row tested |
| State machine C | FAIL (F-18) | Steps 1, 4, 5 and 6 and the P-2 exception hold. Step 3 is not met when the exclusion call raises something other than a `PersistenceError`: the run is touched without the exclusion. Step 2 with a non-database exception: F-19 (LOW) |
| State machine K | PASS for its own steps and lines (F-13 resolved) | It runs on whatever `session.repository` is, which F-18 lets be a repository without the exclusion |
| State machine T | PASS | `ingest_use_case.py:1149-1170` |
| State machine R | PASS | 810-920, with the refusal and loss rule of Revision 7 |
| State machine H | PASS | 1004-1104 and the operational-failure rule (1191-1195) |
| State machine I | PASS | 561-590 |
| F1 and F3 port extensions | PASS | Unchanged since round 2; listing 25 and runs and exclusion 24 passed |
| No schema change | PASS | `migrations/` holds `0001_initial_schema.sql` only, with no diff |
| No dependency (AGENTS.md, PT-11) | PASS | `uv.lock`: no diff; `pyproject.toml`: F-1 keys only |
| ADR 0006: a malformed proxy or certificate setting is configuration (exit 2, before the migrations) | PASS | F-03 resolved |
| R-6 and N3: no exception chain or `__context__` printed | PASS | Only fixed texts, migration `str()` and class names |
| R-7: `httpcore` above `DEBUG` | PASS | `_httpcore_above_debug` wraps step 2 onwards |
| SA-13 and PS-13: one source, at most two repositories, all closed | PASS | `opener.opens <= 2` and `all_closed` in every relevant test and experiment |
| Q4: one ingest active per database | FAIL (F-18, double-fault edge) | See F-18 |
| Tests: guards, no real `data/raw/`, throwaway databases | PASS | The guard proof tests pass; the real `data/` is empty; 0 leftover databases |
| `.env` never read by code or committed | PASS | `git ls-files .env` is empty; no code reads `.env`; the auditor never read it |

## Test coverage

| AC | Tests (file) | Status |
|---|---|---|
| AC1 | `success` in `tests/unit/ingest/test_ingest_use_case.py`; `e2e_success` in `tests/integration/ingest/test_ingest_end_to_end.py` | PASS |
| AC2 | `repeat` (unit); `e2e_repeat` (integration) | PASS |
| AC3 | `last_page`, `last_page_p3` (unit); `e2e_last_page` (integration) | PASS |
| AC4 | `failure_with_response` (unit); `e2e_failure` (integration) | PASS |
| AC5 | `failure_without_response` (unit) | PASS |
| AC6 | `storage`, `database_refusal` (unit); `output_progress` (command) | PASS (F-20 recommends a test for the (b) and refusal combination) |
| AC7 | `interrupt`, `interrupt_during_record`, `cleanup_read_back`, `interrupt_after_finish`, `cleanup_database_error` (unit); `exit_code_*`, `output_database_error` in `tests/unit/ingest/test_ingest_command.py` | PASS |
| AC8 | `connection_loss`, `connection_loss_final_finish`, `final_finish_read_run` (unit); `tests/integration/ingest/test_ingest_connection_loss.py` | PARTIAL: MISSING a test for an exception other than `PersistenceError` during the second exclusion (F-18) |
| AC9 | `resume`, `pre_run_database_error` T cases (unit); `pre_run_database_error_exit_code` (command); `e2e_resume` (integration) | PASS |
| AC10 | `reconcile`, `reconcile_os_error`, `pre_run_database_error` R cases (unit); `pre_run_database_error_exit_code` (command); `e2e_reconcile` (integration) | PASS |
| AC11 | `closed_run`, `interrupt_after_finish` (unit) | PASS |
| AC12 | `execution_id` (`tests/unit/ingest/test_ingestion_catalogue.py`), `identity`, `pre_run_database_error` I cases (unit) | PASS |
| AC13 | `scope`, `catalogue`, and `assert_follows_catalogue` across the use-case tests | PASS |
| AC14 | `usage`, `environment`, `source_configuration`, `order_of_invocation` (command); `cli_invalid_*` (integration) | PASS |
| AC15 | `output`, `logger`, `output_escaping_exception`, `output_progress`, `output_database_error`, `exit_code_repository_open_error`, `single_result_line` (command); `progress_line`, `cleanup_database_error`, `pre_run_database_error`, `repository_open_error`, the two `connection_loss` line tests (unit) | PASS |
| AC16 | `migrations` (`tests/integration/ingest/test_ingest_cli.py`); `tests/unit/test_persistence_error_hierarchy.py`; `tests/integration/test_postgres_migration_lock_error.py`; the edited PS-4 test | PASS |
| AC17 | `no_retry` (unit) | PASS |
| AC18 | `tests/unit/ingest/test_ingest_layers.py` (`layer`); `mypy` | PASS |
| AC19 | the guards and proof tests in both `conftest.py` files; the session check of `data/raw/` | PASS |
| AC20 | the 1307 existing tests, unedited except the PS-4 assertion | PASS |
| AC21 | none (inspection) | PASS (inspection) |
| AC22 | `tests/unit/test_local_disk_raw_evidence_store_listing.py` | PASS |
| AC23 | `tests/integration/ingest/test_postgres_runs_and_exclusion.py` | PASS |
| AC24 | `chain`, `chain_last_page`, `chain_unreadable_record`, `pre_run_database_error` H cases (unit); `chain_unreadable_record_message` (command); `e2e_chain_last_page` (integration) | PASS |
| AC25 | `root` (integration CLI); `paths`, `environment` (command) | PASS |

Coverage from the broader command: TOTAL 97 % locally (2296 passed) and in CI.
`ingest_use_case.py` is at 98 % (566 statements, 11 missed: 285-286, 475, 1239,
1325-1336, 1468; see F-20). `ingest_command.py` and `cli.py` are at 100 %.

### Tier Results

| Tier | Tests found | ACs verified | Setup matches § Validation | Ran | Status | Finding |
|---|---|---|---|---|---|---|
| unit | `tests/unit/ingest/` (869 tests), `test_local_disk_raw_evidence_store_listing.py` (25), `test_persistence_error_hierarchy.py` (3) | AC1 to AC18, AC22, AC24 and AC25, including the three Revision 7 rows | Yes: doubles, `tmp_path` and the autouse socket guard. The conftest additions (`Fault.execution_id`, `RepositoryOpenerDouble.open_errors`) are seams named in the Revision 7 seams table | rerun: every focused `-k` row and every required Revision 6 and 7 token passed | PARTIAL | F-18 (no test for an exception during the second exclusion); F-20 (recommendation) |
| integration | `tests/integration/ingest/` (84 tests), `test_postgres_migration_lock_error.py`, the PS-4 edit | AC1 to AC4, AC8 to AC10, AC16, AC19 and AC23 to AC25 | Yes: PT-13 throwaway databases, the admin connection, a guard that allows the configured host only, and the `data/raw/` session check | rerun with `--env-file .env`, all passed; CI reused | PASS | none |
| static | `uv run mypy .` | AC18 | Yes: the F-1 keys are the only configuration change | rerun: success on 52 files | PASS | none |
| command | ruff, format, mypy, doctor, `--version`, the git diff checks | AC20 | yes | rerun: all clean | PASS | none |
| manual | documentation inspection | AC21 | n/a | rerun (inspection) | PASS | none |

No test exists at a tier that § Validation does not name. No setup was added
that the plan does not name: no configuration, manifest or lockfile changed
since round 2.

## Commands run (2026-10-18, repository root, `287946f`)

| Command | Result | Label |
|---|---|---|
| `uv sync --locked` | ok, 25 packages | rerun |
| `uv run pytest -q` (no `--env-file`) | 2030 passed, 266 skipped | rerun |
| `uv run --env-file .env pytest --cov=ec_procurement_quality --cov-report=term-missing -q` | 2296 passed, 0 skipped, TOTAL 97 % | rerun |
| `uv run ruff check .` | All checks passed | rerun |
| `uv run ruff format --check .` | 119 files already formatted (before this report was written) | rerun |
| `uv run mypy .` | Success, 52 source files | rerun |
| `uv run node .sdd/doctor/run-doctor.mjs` | 31 ok, 0 skipped, 0 warned, 0 failed | rerun |
| `uv run ec-procurement-quality --version` | `ec-procurement-quality 0.1.0` | rerun |
| Every focused unit `-k` row of § Validation, including the Revision 6 tokens and the Revision 7 tokens (`cleanup_database_error` 32, `final_finish_read_run` 3, `pre_run_database_error` 59, `repository_open_error` 11, `output_database_error` 14, `pre_run_database_error_exit_code` 12, `exit_code_repository_open_error` 4, `single_result_line` 8) | all passed (counts in § AC results and § Resolution) | rerun |
| Every focused integration row (`e2e_*`, `migrations` 11, `root` 2, `test_ingest_connection_loss.py` 7, `-k final_finish` 4, `test_postgres_runs_and_exclusion.py` 24, lock and runner 23) | all passed | rerun |
| `uv run pytest tests/unit/test_local_disk_raw_evidence_store_listing.py tests/unit/test_persistence_error_hierarchy.py tests/unit/test_cli.py -q` | 30 passed | rerun |
| `uv run --env-file .env pytest tests/unit/ingest tests/integration/ingest -q` | 953 passed | rerun |
| `uv run pytest tests/unit -q -k layer` | 16 passed | rerun |
| AC18 grep of `src/ec_procurement_quality/application/` for `SELECT `, `INSERT `, `UPDATE `, `DELETE `, `objects/`, `observations/`, `.json`, `advisory`, `pg_` | no match | rerun |
| AC20 `git diff main --stat -- migrations tests/unit/test_cli.py ... uv.lock` (the full list of the row) | empty | rerun |
| `git diff main --stat -- uv.lock` | empty | rerun |
| `git diff main -- pyproject.toml` | only `explicit_package_bases = true`, `mypy_path = "src"` and three comment lines, additions only | rerun |
| `git diff main --numstat -- tests/integration/test_postgres_migrations.py` | `3 0` | rerun |
| `git diff main --stat -- compose.yaml .env.example docs/glossary.md docs/adr specs/current` | empty | rerun |
| `git ls-files .env` | empty | rerun |
| `git diff main --check`, `git diff --check` | clean | rerun |
| `git diff 91bd69d -U0 -- tests` (removed lines) | three `Fault(...)` constructor lines (rewritten with the new `execution_id` keyword) and three docstrings (the two corrections the plan requires and the extended F-13 test); no assertion removed or weakened | rerun |
| Leftover `ecpq_test_` databases (count only, scratch script through `uv run --env-file .env`) | 0 | rerun |
| Files under the real `data/` | 0 before and after the suites | rerun |
| `gh pr checks 25`; `gh run view` | `feedback` pass, `tests` pass, head `287946f` | rerun |
| CI `tests` log (run 39170154723, head `287946f`) | 2296 passed, TOTAL 97 % (Linux) | reused |
| CI `feedback` log (run 39170154649) | `harny-feedback: 2 of 2 command(s) ran, 0 skipped.` | reused |
| Current `tests/unit/ingest` against the round-2 use case and command (`git show 91bd69d:...`) | 104 failed, 765 passed; the round-3 tokens: 104 failed, 28 passed | experiment |
| Mutants N1 to N19 (round 3) and M1 to M9 (round-1 fixes) on a scratch copy, focused tokens | 28 of 28 killed | experiment |
| Experiments X1, X1b, X2, X3, X4, X6, X7, X7b, X8 and X9 (a scratch test file over the repository's doubles) | results quoted in § Findings and § Executor choices | experiment |

## Conventions and feedback

- harny-standards, checked against `AGENTS.md` (the project's conventions
  document):
  - layer boundaries hold;
  - raw responses are never overwritten;
  - no SERCOP contract is invented: synthetic `.invalid` data only;
  - no dependency, infrastructure or service was added;
  - no secrets are in source, tests or docs (gitleaks and the CI secret scan
    pass in the doctor);
  - verification was run and reported (`tasks.md` § Working state).

  No violation was found. The authorship rule of plan § Rollout M4 is tracked
  under F-12 (traceability), not as a code standard.
- harny-feedback: the workflow `.github/workflows/harny-feedback.yml` exists,
  and its latest run, at `287946f`, is green with 2 of 2 commands run. The
  per-turn hooks are configured in `.claude/settings.json`. Whether they fired
  and were heeded during the rework is `unavailable`: no hook log is kept, and
  `AGENTS.md` notes that the hooks run only when `.venv` is on `PATH`.

## Reservations carried forward

- Persistence U1: the real commit-in-flight case is still untested against
  PostgreSQL. The unit `FlakyRepository` and the integration `Kill*Repository`
  seams cover the deterministic cases. This is recorded in CHANGELOG Known
  limitations.
- Persistence N5: the reconciliation reads run in separate snapshots. This is
  safe under the ingest exclusion, with the F-18 caveat for the double-fault
  edge.
- Raw-evidence N2: handled for `store` (AC6 b, F-3) and for the interruption
  cleanup (F-02).
- Source-access R-6 and raw-evidence N3: hold.
- Source-access R-7: holds.
- Source-access R-11: holds. One source per invocation, closed once, also when
  its `close()` is interrupted.
- Source-access U1: open until the human's Day 20 live run. No document claims
  that a live run happened.

## What could not be verified

- Behavior against the real SERCOP source and the real `data/raw/`: out of
  scope, and it must not be run.
- A real Ctrl+C delivered to a live `psycopg` or disk operation. F-13, F-16 and
  F-18 were checked with the repository's doubles, which interrupt at the same
  call boundaries. F-18 against a real concurrent `ingest` was not reproduced
  against PostgreSQL. The unit double models the exclusion as a shared holder,
  and the code path is the same.
- `pg_terminate_backend` of a real stale session that holds the exclusion (the
  README procedure was not exercised).
- That the per-turn feedback hook fired during the rework.
- Who wrote the round-2 correction of `run_ingest`, and under whose
  authorization: no record (F-12).

## Audit log

| Round | Date | Verdict | Notes |
|---|---|---|---|
| 1 | 2026-10-18 | REJECTED | At `7603379`. F-01 and F-02 (CRITICAL, AC7, AC15, State machine K) and F-03 (HIGH, binding constraint and AC14) block. F-04 to F-07 MEDIUM, F-08 to F-12 LOW. Sent back to the architect |
| 2 | 2026-10-18 | REJECTED | At `91bd69d`. F-01 to F-11 resolved, F-12 partially resolved. New: F-13 (MEDIUM, blocking: the K cleanup wrote no line for a refused or lost operation, AC15), F-14 (MEDIUM, blocking until decided: AC15 against plan required progress 3), F-15 to F-17 LOW |
| 3 | 2026-10-18 | REJECTED | At `287946f`. F-13 to F-17 resolved and F-01 to F-11 still resolved: 104 red tests on the round-2 code, 28 of 28 mutants killed, 2296 tests pass locally and in CI. New: F-18 (HIGH, blocking: a Ctrl+C or `MemoryError` during the second exclusion of State machine C lets the K cleanup write without the exclusion; AC8 (c), C step 3, Q4). F-19 and F-20 LOW; F-12 LOW, still partially open. Next: the architect (one sentence and a Validation row), then the red test, the fix and round 4 |
