# Audit: Ingest command (F4)

Auditor: `sdd-auditor` (outcome O10), round 4, 2026-10-18.
Reviewed: branch `feat/ingest-command` at `10e126d` (clean working tree), PR #25
against `main` (base `6b34374`). Specs: `intent.md` Revision 10,
`execution-plan.md` Revision 8 and `tasks.md` Revision 5, all approved by the
human on 2026-10-18.

The whole feature was audited again, and nothing from rounds 1 to 3 was
assumed to still hold. `application/ingest_use_case.py` and
`interfaces/ingest_command.py` were read in full against the state machines P,
C (with "The current repository"), K, T, R, H and I. They were also read
against the "Refused writes" table, the required progress lines, the
invocation order and AC15. `interfaces/cli.py` was read in full as well. The
round-3 diff (`git diff 287946f 10e126d`) was read line by line: the use case
(+98/-22), 767 added test lines and the README (+10). No test line was removed
or weakened (0 removed lines under `tests/`), and `tests/unit/ingest/conftest.py`
is unchanged since round 3.

Evidence labels:

- `rerun`: the auditor ran it in this round.
- `reused`: a recorded result that is still current (the CI runs of PR #25 at
  `10e126d`).
- `experiment`: a throwaway auditor test or mutant, run in the session
  scratchpad (never in the repository). It runs on a scratch copy of `src/` and
  `tests/` that is byte-identical to `10e126d` (checked with `diff -rq` after
  every mutant), with the repository's own doubles from
  `tests/unit/ingest/conftest.py`.
- `unavailable`: it could not be checked.

## Final verdict

REJECTED

**Summary**: F-18 and F-19 are resolved for the two calls that the round-3
report named. A Ctrl+C, a `MemoryError`, a synthetic defect, an exclusion held
elsewhere, a `False`, a `PersistenceError` or a `SystemExit` raised by the
second `open_repository()` or by the second `try_acquire_ingest_exclusion()`
gives the planned outcome. Nothing is read or written, the second repository is
closed, and one line names the call alone. 87 of the 109 new tests fail on the
round-3 code, and 10 of 12 new mutants are killed (the two survivors are
explained below). Every earlier fix, F-01 to F-17, is still pinned: 14 of 14
re-run mutants are killed. 2405 tests pass locally and in CI, and every focused
row of § Validation passes.

One defect remains, and it blocks (F-21). The fix routes away from State
machine K only the exceptions raised inside the two wrapped calls. The window
with no current repository is wider than those two calls. The plan's binding
text names "while the lost repository is closed" as part of the window, and so
does AC7 Revision 10: "after a lost connection and before the exclusion was
taken again ... the cleanup does not run". `session.repository` keeps pointing
at the lost repository through the whole window. So a Ctrl+C that lands
anywhere else in the window still enters K, for example:

- while the lost repository is closed (C step 1);
- while the line of the lost operation is written;
- while the second repository is closed after a `False`.

K then attempts `read_run` on the lost, closed repository and writes
`read_run failed: run <A> (RuntimeError)`. This is the F-19 line that the
architect rejected in Revision 8. Experiments E1, E2 and E3 show it. The
consequence in production is small: nothing is written, the outcome is
`INTERRUPTED` with `running`, stdout is `<A> running` and the exit code is 130.
But an unmet acceptance criterion or binding constraint blocks approval at any
severity. The defect is a narrow double fault, and the fix is local.

**Critical Issues** (must fix before merge):
- F-21 (MEDIUM, blocking: AC7 Revision 10; plan § State machine C "The current repository" and the first bullet of § State machine K): a Ctrl+C in the window, outside the two wrapped calls, still enters K. K attempts `read_run` on the lost repository and names it on stderr. When the Ctrl+C lands before the second repository's `close()` takes effect, that repository is also left open.

**Warnings** (should fix, not blocking):
- F-12 (LOW, carried, partially resolved): several `tasks.md` texts are stale or wrong. § Status still says "the next step is the human's decision on the Revision 10/8/5 specs, then the round 3 rework" and cites the CI of `287946f`. The human's choice of who corrects `run_ingest` in round 3 is not recorded, although O10 round 3 step 3 asks for it. § Working state calls line 1530 an "accepted F-20 limitation", and it is not one.
- F-20 (LOW, carried, partially resolved): the generic `NOT_STARTED` fallback for a non-database exception before the run exists (`ingest_use_case.py:1529-1530`) still has no test. Mutant R11 (re-raise there) survives all 978 unit tests. Plan Revision 8 expected the F-18 and F-19 `start_run` cases to pin it, but the fix routes those cases through `_recovery_ended` instead.

**Recommendations** (nice to have):
- F-22 (LOW, present since round 1): the closing `session.close()` in `run_ingest`'s `finally` (`ingest_use_case.py:1543-1544`) is not guarded. A Ctrl+C or an `Exception` from the final repository `close()` escapes `run_ingest`, which then returns no outcome. At the command tier, a run confirmed `succeeded` then prints `<A> running` (exit 130 or 1).

Next role: the human at gate 3. The rest follows the gate 3 rule (a rejection
goes back to the architect, never to a weaker criterion). F-21 needs no new
rule, because the approved text already names the case. Two things are needed
from the architect:

- one sentence that settles C step 1 for a non-interrupt exception: "close it
  quietly" against "any exception in the window ends C";
- a Validation row with a token, for example `reconnect_close_interrupt`.

Then the test-writer writes the red tests (experiments E1, E2 and E3 below are
ready templates), and the use case is corrected by whoever the human names. Then
audit round 5. F-12, F-20 and F-22 can be closed in the same pass.

## Rounds 1 to 3 summary

- **Round 1** (`7603379`, REJECTED). 12 findings. F-01 and F-02 (CRITICAL, AC7,
  AC15, State machine K) and F-03 (HIGH, AC14 and ADR 0006) blocked. The full
  report is in git history at `7069f4c`.
- **Round 2** (`91bd69d`, REJECTED). F-01 to F-11 were resolved. New: F-13
  (MEDIUM, blocking: the K cleanup wrote no line for a refused or lost
  operation), F-14 (MEDIUM, blocking until decided: AC15 against the plan) and
  F-15 to F-17 (LOW). The full report is at `2f77b5e`.
- **Round 3** (`287946f`, REJECTED). F-13 to F-17 were resolved. New: F-18
  (HIGH, blocking): the second repository became current before it held the
  ingest exclusion, so a Ctrl+C or a `MemoryError` during the second
  `try_acquire_ingest_exclusion` let K write without the exclusion. Also F-19
  and F-20 (LOW), and F-12 carried. The full report is at `fe0fb28`. Intent
  Revision 10, plan Revision 8 and tasks Revision 5 answered it, with the
  human's approval on 2026-10-18. The rework landed in `6468790` (109 tests)
  and `10e126d` (use case and README).

## Resolution of the earlier findings

Each closure condition was checked against the current code. Each was also
checked against at least one test that fails without the fix, either by mutant
(M and N, rerun this round) or by the red evidence. For the round-3 rework, the
current tests were run against the round-3 use case (`git show
287946f:...ingest_use_case.py` in the scratch copy):

- `tests/unit/ingest` gives 87 failed and 891 passed;
- the four round-3 tokens give 87 failed and 22 passed.

This is the same as `tasks.md` § Working state records. Every failure is an
`AssertionError` on state, events, outcome or lines; there is no import,
collection, database or socket error. The 22 tests that pass on the round-3
code are the F-20 regression tests and the 6 `SystemExit` guards, as the plan
declares.

| Id | Earlier severity | Status | Evidence (current code; tests; mutant) |
|---|---|---|---|
| F-01 | CRITICAL | Resolved (still) | Pending set before `store` (`ingest_use_case.py:1362`); cleared only when `record_observation` returned or the path concluded (1395, 1408, 1441, 1450); K reads it back and records it (702-715). M1 (clear right after `store`) -> 3 failed |
| F-02 | CRITICAL | Resolved (still) | K absorbs the three read-back errors (705-706) and still appends and finishes. M2 (absorb only `EvidenceNotFoundError`) -> 4 failed |
| F-03 | HIGH | Resolved (still) | `ingest_command.py:281-287`: source built before `_migrate` (289); any `Exception` except `MemoryError` -> exit 2 with the six variables and the class name. M8 (source after the migrations) -> 58 failed |
| F-04 | MEDIUM | Resolved (still) | `_print_running` on both escaping branches (348-355). M9 -> 4 failed |
| F-05 | MEDIUM | Resolved (still) | K reads the run first and keeps a finished run's status (698-701). M3 -> 9 failed |
| F-06 | MEDIUM | Resolved (still) | Store read errors of the chain map to `invalid resumption chain <id>` (1256-1266). M4 -> 6 failed |
| F-07 | MEDIUM | Resolved (still) | Page lines (`_report_page` 355-359; 1347; 1405-1407). M5 -> 7 failed |
| F-08 | LOW | Resolved (still) | No `_finish` helper exists |
| F-09 | LOW | Resolved (still) | `ingestion_catalogue.py:155` says 32 characters |
| F-10 | LOW | Resolved (still) | 882-885, 901-913. M6 -> 2 failed |
| F-11 | LOW | Resolved (still) | `_append_on_normal_path` (518-543), `_close_failed` (450-491), `_finish_succeeded` (546-582), refused `start_run` (1300-1302); 57 `database_refusal` tests. M7 -> 9 failed |
| F-12 | LOW | Partially resolved (carried) | The round-3 items were fixed in `f77fd4e`. New stale text: see F-12 under § Findings |
| F-13 | MEDIUM | Resolved (still) | `_cleanup_step` (653-669) writes one line for any failure of K's four operations; P-2 `read_run` (571-575). N1 (K silent) -> 47 failed |
| F-14 | MEDIUM | Resolved (still) | One line per refused or lost call in every phase: opening (1180-1182), exclusion (1201-1204), T and H (`_read_database` 792-811), R (`_guarded` 771-789, 926-933), I (639-641), C's second opening and exclusion (`_recovery_step` 185-202). N3 -> 18 failed |
| F-15 | LOW | Resolved (still) | Fixed messages naming the identity (1220-1225, 764-768, 1251-1255, 1277-1281). N5 (unreadable target -> `INVALID_TARGET`) -> 10 failed |
| F-16 | LOW | Resolved (still) | (a) first opening (1178-1189), `finally` close (1543-1544); N9 -> 1 failed. (b) `result_written` (`ingest_command.py:234`, 243); N11 -> 4 failed |
| F-17 | LOW | Resolved (still) | README § Ingesting lists every `running` case, the exit-2 proxy and certificate variables and the exit-1 unreadable target (`README.md:246-289`). Inspection (rerun) |
| F-18 | HIGH | Resolved for its closure condition; residue is F-21 | `_reconnect` (226-249) assigns `self.repository = second` only after `try_acquire_ingest_exclusion()` returned `True` (248). `_recovery_step` (185-202) turns any non-`SystemExit` exception of the second opening or exclusion into `_RecoveryEnded` (one line, named alone), and `run_ingest` maps it to `_recovery_ended` without K (1511-1512, 422-447). The second repository is closed on any failure (243-247). Tests: `reconnect_exclusion_interrupt` (use case 12 + 6 + 2 + 3; command 12 + 12), the X1 hook with another session holding the exclusion, `opener.attempts` after the loss, `all_closed` and the stored snapshot. Mutants: R9 (route `_RecoveryEnded` into K) -> 51 failed; R2 (catch `Exception` only) -> 30; R4 (second not closed) -> 56; R6 -> 30; R8 -> 32; R10 (line names the run) -> 38. Not resolved: interrupts elsewhere in the window (F-21) |
| F-19 | LOW | Resolved for its closure condition; residue is F-21 | A non-database exception from the second `open_repository()` no longer reaches K. The one line names `open_repository`, and nothing is attempted on the closed first repository. `test_reconnect_open_interrupt_never_asks_the_closed_first_repository` asserts no `RuntimeError` and no `read_run` line. R3 (no line in the window) -> 87 failed. The same misleading line still appears for a Ctrl+C during C step 1 (F-21) |
| F-20 | LOW | Partially resolved (carried) | Required tests exist and pass: `start_run_unconfirmed` (8 use-case, 4 command) and `read_back_record_failure` (4). The accepted limitations (now lines 317-318 and 535) are recorded in `tasks.md` § Carried reservations. Still untested: the generic fallback at 1529-1530 (R11 survives; experiment E6 shows `NOT_STARTED` `MemoryError`, nothing written) |

## Findings

| Id | Severity | AC / constraint | Finding and evidence | Failure scenario | Closure condition | Status |
|---|---|---|---|---|---|---|
| F-21 | MEDIUM (blocking: an unmet AC7 guarantee and binding plan text) | AC7 Revision 10 ("when the Ctrl+C or the `MemoryError` lands after a lost connection and before the exclusion was taken again on the new connection ... the cleanup does not run: nothing is read from or written to `<A>`"); plan § State machine C "The current repository" (required: "a `KeyboardInterrupt` ... that arrives in the window (while the lost repository is closed, while `open_repository()` runs, or while `try_acquire_ingest_exclusion()` runs) ... ends § State machine C ... § State machine K is not entered"; "no operation is attempted on the lost repository"; "No line names an operation that was not attempted (for example `read_run`), so no cleanup line is written"); § State machine K first bullet; AC15 and AC8 (the line names only the operation in progress) | The "no current repository" state is not represented. `_reconnect` leaves `self.repository` on the lost repository (`ingest_use_case.py:232-234`), and only exceptions raised inside the two `_recovery_step` blocks become `_RecoveryEnded` (237-240). Elsewhere in the window, a raw `KeyboardInterrupt` or `Exception` reaches the outer handlers (1513-1542), and they run K on `session.repository`, the lost repository. Unguarded points: the close of the lost repository (227-228; `suppress(Exception)` lets `KeyboardInterrupt` through); the loss line in `safe_repeat` (261) and in `append_event`'s `_reporting_failure` (285-291); the close of the second repository after a `False`, a refusal or an exception (244-246); the bytecodes between the `True` and line 248; and a line being written inside `_recovery_step`'s handlers. Mutant R1 (make the second repository current before the exclusion, the round-3 code) survives all 978 unit tests. This confirms that the invariant rests only on how the exceptions are routed | E1 (experiment): `record_observation` of sequence 2 lost before commit, and the lost repository's `close()` raises `KeyboardInterrupt`, after closing (as psycopg would after `PQfinish`) or before it. The exclusion is free, or another session takes it at the loss. Result: attempts after the loss are `['1 read_run']`, and the last stderr line is `read_run failed: run <A> (RuntimeError)` (or `connection lost during read_run: run <A>`). The outcome is `INTERRUPTED`, `running`; the CLI tier gives stdout `<A> running`, exit 130 (E12). Nothing is written. E2: another session holds the exclusion at the loss, the second exclusion returns `False`, and its `close()` raises `KeyboardInterrupt`. The result is the same: `['2 try_acquire_ingest_exclusion', '1 read_run']` and the same line. E2b: the same `KeyboardInterrupt` before that `close()` takes effect leaves the second repository open (`opener.all_closed` is `False`; SA-13 and PS-13). E3: a `KeyboardInterrupt` while the line `connection lost during record_observation ...` is written also runs K on the lost repository. An operator would look for a `read_run` refusal that never reached the database (the F-19 symptom) | The window is represented explicitly, for example as a current repository that is `None` from the loss until the second exclusion returns `True`. K and every write are skipped while there is none, whatever the exception and wherever it lands. Every repository obtained in the window is closed even when its `close()` is interrupted, at least by the `finally`. The architect settles C step 1 for a non-interrupt exception: "close it quietly" (today a `MemoryError` there is suppressed and the recovery goes on, then writes safely under the second exclusion, experiment E13) against "any exception in the window ends C". The architect also adds a Validation row with a token. Red-first unit tests pin E1, E2 and E3 (no attempt after the loss, no `read_run` line, `running`, `all_closed`). README § Ingesting ("stderr names only `open_repository` or `try_acquire_ingest_exclusion`") then holds | Open |
| F-12 | LOW (carried, partially resolved) | harny-audit step 4 (outcome state); plan § Rollout M4 (authorship of `run_ingest`); O10 round 3 step 3 | `tasks.md` § Status (line 8) still ends: "Gate 3 is open: the next step is the human's decision on the Revision 10/8/5 specs, then the round 3 rework under O10 (red tests, the fix, the audit round 4)". The specs are approved and the rework is done (§ Working state, § Checkpoint). The same line cites "checks passed on `287946f`"; the current head is `10e126d`. O10 round 3 step 3 asks to "record the human's choice here before the work starts" for who corrects `run_ingest`. Nothing is recorded; § Working state says only "Green (executor, re-run)". § Working state (line 361) calls "lines 317-318, 535 and 1530" "the accepted F-20 limitations". § Carried reservations accepts only the first two, and 1530 was meant to be pinned by tests (see F-20) | The next role reads a stale state and a wrong coverage claim. The authorship of the round-3 use-case fix has no recorded decision | § Status is brought up to date. The human's choice for the round-3 (and next) correction is recorded. The 1530 claim is corrected | Open |
| F-20 | LOW (carried, partially resolved) | harny-audit step 5; plan Revision 8 § Audit round 3 responses ("the non-database exception before the run exists is pinned by the `start_run` cases of the F-18 and F-19 row") | The `start_run` window cases are now handled by `_recovery_ended` (430-434), not by the generic fallback. So `ingest_use_case.py:1529-1530` is still uncovered (the coverage reports it locally and in CI). Mutant R11 (`raise` instead of returning `NOT_STARTED`) survives the 978 unit tests | A regression that lets a `MemoryError` before the run exists (from the first `start_run`, the reconciliation's store, the id source or a defect in the chain check) escape `run_ingest` would go unnoticed. E6 shows the planned behavior today: `NOT_STARTED`, message `MemoryError`, nothing written | One unit test drives a non-database exception before the run exists outside the recovery window, for example `start_run` on the first repository raising `MemoryError` | Open (recommendation) |
| F-22 | LOW | Plan § Public names (`run_ingest` "returns an outcome for every ending except a `KeyboardInterrupt` raised during its own interruption cleanup and `SystemExit`"); AC15 (`<status>` is the last status the process confirmed) | `run_ingest`'s `finally: session.close()` (1543-1544) is not guarded, unlike the source's close (`ingest_command.py:303-306`). Present since round 1 and not raised before | E7: after an AC1 run that `succeeded`, a `KeyboardInterrupt` from the repository's final `close()` escapes `run_ingest`. E8 does the same with an `OSError`. The command then prints `<A> running` with exit 130, or `unexpected error: OSError` with exit 1, although the process confirmed `succeeded`. This is conservative under P-5, but it departs from the pinned sentence. The real adapter's `close()` is idempotent and rarely raises | The final close suppresses an `Exception` (and the architect decides whether a Ctrl+C there keeps the outcome or gives 130), or the plan accepts the escape | Open (recommendation) |

## Executor choices where the plan was silent

| Choice | Assessment |
|---|---|
| `SystemExit` raised in the window writes no line (`_recovery_step` 198-199) | Compliant: plan required progress says "`SystemExit` propagates without a required line", and § Public names lets it propagate. The second repository is still closed (243-247). Tests: the two `system_exit` tests (3 + 3); mutant R5 (swallow it) -> 6 failed |
| The `RUN_FAILED` message in the window is `unexpected error: <ClassName>`; in the `start_run` window it is the bare class name | Compliant with AC15 (at most the class name, never `str()`), and consistent with K's message. Mutant R12 (append `str(error)`) -> 16 failed |
| An exception from `close()` of the second repository is suppressed (`suppress(Exception)`, 245) | Acceptable for an `Exception`: closing must not change the ending, as for the source. Not acceptable for a `KeyboardInterrupt`, which passes through and enters K on the lost repository (F-21, E2), and which can leave the second repository open (E2b) |
| A `MemoryError` from `close()` of the lost repository at C step 1 is suppressed, and the recovery continues | It matches "Close the lost repository quietly" (C step 1), and it is safe: E13 writes only after the second exclusion returned `True`. It collides with the window bullet ("a `MemoryError` ... while the lost repository is closed ... ends § State machine C"). The architect settles it under F-21 |
| The window's protection is exception routing (`_RecoveryEnded`), not a "no current repository" state | Works for the two named calls, but not for the rest of the window (F-21). Mutant R1 survives because of this design |

Accepted limitations: lines 317-318 (an append on the new connection lost
after the re-check) and 535 (an unconfirmed normal-path append) stay
uncovered. The human accepted them on 2026-10-18, and the round-3 experiments
X9 and X6 still describe their behavior. The code there is unchanged since
round 3 except for the line numbers. Line 1530 is not an accepted limitation
(F-20, F-12).

## Defect-hunting checklist (both modules against the state machines)

| Area | Result |
|---|---|
| Opening and first exclusion | Hold: `PersistenceError` -> one line, `NOT_STARTED`; Ctrl+C -> `INTERRUPTED` with no run; anything else -> `NOT_STARTED` naming the opening; closed by the `finally`. Note, unchanged: lines 1190-1197 run between the return of `open_repository()` and the `try` (pure Python) |
| C, the two named calls (steps 2 and 3) | Hold for every exception kind, with the exclusion free or held elsewhere (93 tests; X1 included) |
| C, the rest of the window (step 1, the loss line, the close after `False`) | F-21 |
| C, repeats, re-check, P-2, second loss | Hold: `connection_loss` 43, `connection_loss_final_finish` 12, integration 7 + 4. E9: a second loss gives `running`, two lines, no third connection, all closed |
| K on the current repository | Holds after a successful reconnect (E5: K runs on the second repository, which holds the exclusion) and on the first repository. F-21: K can also run on the lost one |
| T, R, H, I | Hold (59 `pre_run_database_error`, 12 exit-code tests, negative controls) |
| Refused writes | Hold: at most one `storage-failed` (`postgresql`), never `unexpected-error` (57 tests) |
| Order: local store -> PostgreSQL -> event -> finish | Holds (journal-order tests) |
| Write-once evidence; no retries | Hold: one `store` per (id, sequence); one `search_page` per page (`no_retry` 6) |
| Secrets, URLs, tracebacks, exception text (AC15) | Hold: lines and messages use fixed words, ids, numbers, hashes and class names. The command prints `str()` only of F3 migration errors and of the outcome message. Every new test plants markers in the error text and checks that they are absent |
| Exactly one stdout line; exit codes | Hold: `result_written` guards a second line. The window gives 130 for Ctrl+C and 1 otherwise. The `start_run` window gives an empty stdout |
| Leaked repositories or sources | None on the tested paths (`all_closed` everywhere). E2b leaves one open (F-21). The source is closed in `_invoke`'s `finally` |
| Final repository close | F-22 |

## AC results

| AC | Status | Evidence |
|---|---|---|
| AC1 | PASS | `-k success` 9; `-k e2e_success` 2 passed (rerun) |
| AC2 | PASS | `-k repeat` 5; `-k e2e_repeat` 2 passed (rerun) |
| AC3 | PASS | `-k last_page` 41, `-k last_page_p3` 6, `-k e2e_last_page` 2 passed (rerun) |
| AC4 | PASS | `-k failure_with_response` 16; `-k e2e_failure` 5 passed (rerun) |
| AC5 | PASS | `-k failure_without_response` 6 passed (rerun) |
| AC6 | PASS | `-k storage` 16, `-k database_refusal` 57 and `-k read_back_record_failure` 4 passed (rerun). The (a) and (d) cases also pass on Linux in CI (reused) |
| AC7 | PARTIAL | `-k "interrupt or exit_code"` 241, `interrupt_during_record or cleanup_read_back` 14, `interrupt_after_finish` 11, `cleanup_database_error or final_finish_read_run or output_database_error` 49 and `reconnect_exclusion_interrupt or reconnect_open_interrupt` 93 passed (rerun). Unmet: a Ctrl+C after a lost connection and before the exclusion is taken again, outside the two wrapped calls, still runs the cleanup (F-21, experiments E1 to E3) |
| AC8 | PASS | `-k connection_loss` 43 (unit), `test_ingest_connection_loss.py` 7 (integration), `connection_loss_final_finish` 12, integration `final_finish` 4, `start_run_unconfirmed` 12 and the 93 `reconnect_*` tests passed (rerun). (c) holds: with another session holding the exclusion, nothing is written by any path, including E1 and E2, where K's read fails on the closed repository. The misnamed line in those cases is F-21 |
| AC9 | PASS | `-k resume` 24; `-k e2e_resume` 5; an unreadable target gives exit 1 (`pre_run_database_error`) (rerun) |
| AC10 | PASS | `-k reconcile` 34; `-k e2e_reconcile` 6; `reconcile_os_error` 4; R cases of `pre_run_database_error` (rerun) |
| AC11 | PASS | `-k closed_run` 3; `interrupt_after_finish` 11 (rerun). No path adds to a finished run (E1 and E2 write nothing) |
| AC12 | PASS | `-k "execution_id or identity"` 67; I cases of `pre_run_database_error` (rerun) |
| AC13 | PASS | `-k "scope or catalogue"` 111; `assert_follows_catalogue` across the paths, including the new F-20 tests (rerun) |
| AC14 | PASS | `-k "usage or environment"` 66; `source_configuration or order_of_invocation` 30 (rerun); M8 killed (experiment) |
| AC15 | PASS | `-k "output or logger"` 81; `output_escaping_exception` 12; progress group 24; `pre_run_database_error` 59; `repository_open_error or single_result_line` 19; the 93 `reconnect_*` tests (rerun). Note: F-21 adds a line naming an operation that never reached the database, and F-22 can print `<A> running` after a confirmed finish |
| AC16 | PASS | `-k migrations` 11; `test_persistence_error_hierarchy.py` 3 (inside the 30 below); lock and runner 23; `git diff main --numstat -- tests/integration/test_postgres_migrations.py` -> `3 0` (rerun) |
| AC17 | PASS | `-k no_retry` 6 (rerun) |
| AC18 | PASS | `uv run pytest tests/unit -q -k layer` 16 passed; the AC18 grep of `application/` finds nothing; `interfaces` imports neither `httpx` nor `psycopg`; `git diff main --stat -- uv.lock` is empty; `git diff main -- pyproject.toml` shows only the two F-1 keys and three comment lines; `mypy` reports 52 files clean (rerun) |
| AC19 | PASS | `uv run --env-file .env pytest tests/unit/ingest tests/integration/ingest -q` -> 1062 passed; 0 files under the real `data/` before and after; 0 `ecpq_test_` databases (rerun) |
| AC20 | PASS | 2405 passed (1307 baseline + 1098 F4); the AC20 `git diff main --stat` list is empty; `git ls-files .env` is empty; `git diff main --check` and `git diff --check` are clean; ruff, format, mypy and the doctor (`31 ok, 0 skipped, 0 warned, 0 failed`) pass; `--version` -> `ec-procurement-quality 0.1.0` (rerun) |
| AC21 | PASS | Inspection of README § Ingesting, including the Revision 8 recovery cases (`README.md:261-265`, `274-277`, which match the code except for the F-21 edge), AGENTS.md § Current commands, architecture § Infrastructure boundary and § Open questions, and CHANGELOG. Every document says that no live run happened (`README.md:44-46`, `315-316`; `CHANGELOG.md:215`) (rerun, inspection) |
| AC22 | PASS | `test_local_disk_raw_evidence_store_listing.py` 25 (inside the 30) (rerun) |
| AC23 | PASS | `test_postgres_runs_and_exclusion.py` 24 (rerun) |
| AC24 | PASS | `-k chain` 140, `chain_last_page` 33, `e2e_chain_last_page` 3, `chain_unreadable_record` 12; H cases of `pre_run_database_error`; M4 and N5 killed (rerun, experiment) |
| AC25 | PASS | `-k "paths or environment"` 34 (unit); `-k root` 2 (integration) (rerun) |

Plan decisions and implementation findings:

| Item | Status | Evidence |
|---|---|---|
| P-1 | PASS | `ingest_command.py:254-264`: `MigrationLockError` -> 1, any other `MigrationError` -> 2, `PersistenceError` -> 1; lock and runner row 23 passed |
| P-2 | PASS | `_finish_succeeded` (546-582): the exact repeat with the same `finished_at`; no `storage-failed` after a refused repeat; the window cases with `final-finish` give `running` with no repeat (12 + 12 tests) |
| P-3 | PASS | `ingest_use_case.py:1493-1508` |
| P-4 | PASS | `_resume_plan` (1064-1164) with `pages_left_to_request` |
| P-5 | PASS | `_unconfirmed` (413-419), `_recovery_ended` (422-447), K (741-747), `_print_running` (`ingest_command.py:238-244`) |
| F-1 | PASS | `git diff main -- pyproject.toml`: the two keys and three comment lines, additions only |
| F-2 | PASS | `ingestion_catalogue.py:155` |
| F-3 | PASS | `ingest_use_case.py:1370-1376` catches the three read-back errors |

## Binding-constraint compliance

| Constraint | Status | Evidence |
|---|---|---|
| Layer placement (ADR 0001, AC18) | PASS | Layer tests 16; AC18 grep clean; `interfaces` imports no `httpx` or `psycopg` |
| Public names and signatures | PASS, with note F-22 | Pinned types and `run_ingest` signature unchanged; F-22 is an unguarded escape from the final close |
| CLI arguments and configuration | PASS | `cli.py` and `ingest_command.py:109-170` unchanged since round 2; `test_cli.py` 2 passed |
| Order of an invocation | PASS | Steps 1 to 7 (unchanged since round 3) |
| Exit codes | PASS | `_EXIT_CODES` (218-224); the window gives 130 or 1 |
| Output (AC15) | PASS, with notes F-21 and F-22 | One result line at most; no secrets |
| Audit details (closed catalogue) | PASS | `assert_follows_catalogue` across the paths |
| State machine P and "Refused writes" | PASS | Re-read in full; every table row tested |
| State machine C | FAIL (F-21) | Steps 2 and 3 and their outcomes hold (F-18 and F-19 resolved). "The current repository" is not met for an interrupt during step 1's close, the loss line, or the close after a `False`: K runs on the lost repository |
| State machine K | FAIL (F-21) | Its own steps and lines hold (F-13). Its first bullet ("only through the current repository") is not met in the F-21 cases |
| State machines T, R, H, I | PASS | 1208-1230, 870-980, 1064-1164, 621-650 |
| F1 and F3 port extensions | PASS | Listing 25; runs and exclusion 24 |
| No schema change | PASS | `migrations/` holds `0001_initial_schema.sql` only, with no diff |
| No dependency (AGENTS.md, PT-11) | PASS | `uv.lock` has no diff; `pyproject.toml` has only the F-1 keys |
| ADR 0006 (configuration error before the migrations) | PASS | F-03 (M8 killed) |
| R-6 and N3 (no chain or `__context__` printed) | PASS | `_RecoveryEnded` chains its error but is never printed; only class names reach the reporter |
| R-7 (`httpcore` above `DEBUG`) | PASS | `_httpcore_above_debug` |
| SA-13 and PS-13 (one source, at most two repositories, all closed) | PASS on tested paths, with note F-21 | `opens <= 2` and `all_closed` everywhere; E2b leaves the second repository open |
| Q4 (one ingest active per database) | PASS | No write without the exclusion on any path the auditor found, including E1, E2, E2b, E3 and E13 |
| Tests (guards, no real `data/raw/`, throwaway databases) | PASS | Guard proof tests pass; `data/` empty; 0 leftover databases |
| `.env` never read by code or committed | PASS | `git ls-files .env` is empty; no code reads `.env`; the auditor never read it |

## Test coverage

| AC | Tests (file) | Status |
|---|---|---|
| AC1 | `success` in `tests/unit/ingest/test_ingest_use_case.py`; `e2e_success` in `tests/integration/ingest/test_ingest_end_to_end.py` | PASS |
| AC2 | `repeat` (unit); `e2e_repeat` (integration) | PASS |
| AC3 | `last_page`, `last_page_p3` (unit); `e2e_last_page` (integration) | PASS |
| AC4 | `failure_with_response` (unit); `e2e_failure` (integration) | PASS |
| AC5 | `failure_without_response` (unit) | PASS |
| AC6 | `storage`, `database_refusal`, `read_back_record_failure` (unit); `output_progress` (command) | PASS |
| AC7 | `interrupt`, `interrupt_during_record`, `cleanup_read_back`, `interrupt_after_finish`, `cleanup_database_error`, `reconnect_*` (unit); `exit_code_*`, `output_database_error` in `tests/unit/ingest/test_ingest_command.py` | PARTIAL: MISSING a test for an interrupt during C step 1's close, the loss line, or the close after a `False` (F-21) |
| AC8 | `connection_loss`, `connection_loss_final_finish`, `final_finish_read_run`, `reconnect_*`, `start_run_unconfirmed` (unit and command); `tests/integration/ingest/test_ingest_connection_loss.py` | PASS |
| AC9 | `resume`, `pre_run_database_error` T cases (unit); `pre_run_database_error_exit_code` (command); `e2e_resume` (integration) | PASS |
| AC10 | `reconcile`, `reconcile_os_error`, `pre_run_database_error` R cases (unit); `e2e_reconcile` (integration) | PASS |
| AC11 | `closed_run`, `interrupt_after_finish` (unit) | PASS |
| AC12 | `execution_id` (`test_ingestion_catalogue.py`), `identity`, `pre_run_database_error` I cases (unit) | PASS |
| AC13 | `scope`, `catalogue`, `assert_follows_catalogue` across the use-case tests | PASS |
| AC14 | `usage`, `environment`, `source_configuration`, `order_of_invocation` (command); `cli_invalid_*` (integration) | PASS |
| AC15 | `output`, `logger`, `output_escaping_exception`, `output_progress`, `output_database_error`, `single_result_line`, `exit_code_reconnect_*`, `exit_code_start_run_unconfirmed` (command); `progress_line`, `cleanup_database_error`, `pre_run_database_error`, `repository_open_error`, `reconnect_*` (unit) | PASS (F-20: the generic fallback at 1530 untested) |
| AC16 | `migrations` (`tests/integration/ingest/test_ingest_cli.py`); `tests/unit/test_persistence_error_hierarchy.py`; `tests/integration/test_postgres_migration_lock_error.py`; the PS-4 edit | PASS |
| AC17 | `no_retry` (unit) | PASS |
| AC18 | `tests/unit/ingest/test_ingest_layers.py`; `mypy` | PASS |
| AC19 | the guards and proof tests of both `conftest.py` files; the session check of `data/raw/` | PASS |
| AC20 | the 1307 existing tests, unedited except the PS-4 assertion | PASS |
| AC21 | none (inspection) | PASS (inspection) |
| AC22 | `tests/unit/test_local_disk_raw_evidence_store_listing.py` | PASS |
| AC23 | `tests/integration/ingest/test_postgres_runs_and_exclusion.py` | PASS |
| AC24 | `chain`, `chain_last_page`, `chain_unreadable_record`, H cases (unit); `chain_unreadable_record_message` (command); `e2e_chain_last_page` (integration) | PASS |
| AC25 | `root` (integration CLI); `paths`, `environment` (command) | PASS |

Coverage from the broader command: TOTAL 98 % locally (2405 passed) and in CI.
`ingest_use_case.py` is at 99 % (592 statements, 4 missed: 317-318 and 535,
which are accepted, and 1530, which is F-20). `ingest_command.py` and `cli.py`
are at 100 %.

### Tier Results

| Tier | Tests found | ACs verified | Setup matches § Validation | Ran | Status | Finding |
|---|---|---|---|---|---|---|
| unit | `tests/unit/ingest/` (978 tests), `test_local_disk_raw_evidence_store_listing.py` (25), `test_persistence_error_hierarchy.py` (3) | AC1 to AC18, AC22, AC24 and AC25, including the three Revision 8 rows and their seven tokens | Yes: doubles, `tmp_path`, autouse socket guard. No conftest change since round 3; the Revision 8 seams (`open_errors`, `Fault.hook`, the shared exclusion holder) already existed | rerun: every focused `-k` row passed | PARTIAL | F-21 (no test for the rest of the window); F-20 (recommendation) |
| integration | `tests/integration/ingest/` (84 tests), `test_postgres_migration_lock_error.py`, the PS-4 edit | AC1 to AC4, AC8 to AC10, AC16, AC19 and AC23 to AC25 | Yes: PT-13 throwaway databases, admin connection, host-only `getaddrinfo` guard, `data/raw/` session check | rerun with `--env-file .env`, all passed; CI reused | PASS | none |
| static | `uv run mypy .` | AC18 | Yes: the F-1 keys are the only configuration change | rerun: 52 files clean | PASS | none |
| command | ruff, format, mypy, doctor, `--version`, git diff checks | AC20 | yes | rerun: all clean | PASS | none |
| manual | documentation inspection | AC21 | n/a | rerun (inspection) | PASS | none |

No test exists at a tier that § Validation does not name. No setup was added
that the plan does not name: since round 3, no configuration, manifest,
lockfile or conftest changed.

## Commands run (2026-10-18, repository root, `10e126d`)

| Command | Result | Label |
|---|---|---|
| `uv sync --locked` | ok, 25 packages | rerun |
| `uv run pytest -q` (no `--env-file`) | 2139 passed, 266 skipped | rerun |
| `uv run --env-file .env pytest --cov=ec_procurement_quality --cov-report=term-missing -q` | 2405 passed, 0 skipped, TOTAL 98 % | rerun |
| `uv run ruff check .` | All checks passed | rerun |
| `uv run ruff format --check .` | 119 files already formatted (before and after this report) | rerun |
| `uv run mypy .` | Success, 52 source files | rerun |
| `uv run node .sdd/doctor/run-doctor.mjs` | 31 ok, 0 skipped, 0 warned, 0 failed | rerun |
| `uv run ec-procurement-quality --version` | `ec-procurement-quality 0.1.0` | rerun |
| Every focused unit `-k` row of § Validation (38 commands, counts in § AC results), including the Revision 8 tokens: `reconnect_exclusion_interrupt or reconnect_open_interrupt` 93, `start_run_unconfirmed` 12, `read_back_record_failure` 4, `exit_code_reconnect_exclusion_interrupt` 24, `exit_code_reconnect_open_interrupt` 24, `exit_code_start_run_unconfirmed` 8 | all passed | rerun |
| Every focused integration row (`e2e_*`, `migrations` 11, `root` 2, `final_finish` 4, `test_ingest_connection_loss.py` 7, `test_postgres_runs_and_exclusion.py` 24, lock and runner 23) | all passed | rerun |
| `uv run pytest tests/unit/test_local_disk_raw_evidence_store_listing.py tests/unit/test_persistence_error_hierarchy.py tests/unit/test_cli.py -q` | 30 passed | rerun |
| `uv run --env-file .env pytest tests/unit/ingest tests/integration/ingest -q` | 1062 passed | rerun |
| `uv run pytest tests/unit -q -k layer` | 16 passed | rerun |
| AC18 grep of `src/ec_procurement_quality/application/` (`SELECT `, `INSERT `, `UPDATE `, `DELETE `, `objects/`, `observations/`, `.json`, `advisory`, `pg_`) | no match | rerun |
| AC20 `git diff main --stat -- <the full list of the row>` | empty | rerun |
| `git diff main --stat -- uv.lock`; `git diff main -- pyproject.toml` | empty; only the two F-1 keys and three comment lines, additions only | rerun |
| `git diff main --numstat -- tests/integration/test_postgres_migrations.py` | `3 0` | rerun |
| `git diff main --stat -- compose.yaml .env.example docs/glossary.md docs/adr specs/current` | empty | rerun |
| `git ls-files .env`; `git diff main --check`; `git diff --check` | empty; clean; clean | rerun |
| `git diff 287946f -U0 -- tests` (removed lines) | 0 | rerun |
| Leftover `ecpq_test_` databases (count only, scratch script through `uv run --env-file .env`) | 0 | rerun |
| Files under the real `data/` | 0 before and after the suites | rerun |
| `gh pr checks 25`; `gh run list` | `feedback` pass, `tests` pass, head `10e126d`, PR open and mergeable | rerun |
| CI `tests` log (run 39176690398, head `10e126d`) | 2405 passed, TOTAL 98 %, `ingest_use_case.py` missing 317-318, 535, 1530 (Linux) | reused |
| CI `feedback` log (run 39176690413, head `10e126d`) | `harny-feedback: 2 of 2 command(s) ran, 0 skipped.` | reused |
| Current `tests/unit/ingest` against the round-3 use case (`git show 287946f:...`) | 87 failed, 891 passed; the round-3 tokens 87 failed, 22 passed; all `AssertionError` | experiment |
| Round-4 mutants R1 to R12 on the scratch copy, focused tokens | 10 killed; R1 survives (equivalent under the current routing, which is the root of F-21); R11 survives (F-20) | experiment |
| Earlier-fix mutants M1 to M9 and N1, N3, N5, N9, N11, full `tests/unit/ingest` | 14 of 14 killed | experiment |
| Experiments E1 to E13 (scratch test file over the repository's doubles) | quoted in § Findings and § Executor choices | experiment |

## Conventions and feedback

- harny-standards, checked against `AGENTS.md` (the project's conventions
  document):
  - layer boundaries hold;
  - raw responses are never overwritten;
  - no SERCOP contract is invented, and only synthetic `.invalid` data is used;
  - no dependency, infrastructure or service was added;
  - no secrets are in source, tests or docs (the doctor's gitleaks and CI
    secret-scan checks pass);
  - verification was run and reported (`tasks.md` § Working state).

  No violation was found. The authorship record of plan § Rollout M4 is
  tracked under F-12.
- harny-feedback: `.github/workflows/harny-feedback.yml` exists, and its latest
  run at `10e126d` is green with 2 of 2 commands run. The per-turn hooks are
  configured in `.claude/settings.json`. Whether they fired and were heeded
  during the rework is `unavailable`: no hook log is kept.

## Reservations carried forward

- Persistence U1: the real commit-in-flight case is still untested against
  PostgreSQL (CHANGELOG Known limitations).
- Persistence N5: the reconciliation reads run in separate snapshots. This is
  safe under the ingest exclusion. Round 4 found no path that writes without
  the exclusion.
- Raw-evidence N2: handled for `store` (AC6 b, F-3, and the F-20 read-back
  tests) and for the cleanup (F-02).
- Source-access R-6, R-7 and R-11 and raw-evidence N3: hold.
- The two F-20 limitations accepted on 2026-10-18 (lines 317-318 and 535).
- Source-access U1: open until the human's Day 20 live run. No document claims
  that a live run happened.

## What could not be verified

- Behavior against the real SERCOP source and the real `data/raw/`: out of
  scope, and it must not be run.
- A real Ctrl+C delivered to a live `psycopg` call. F-18, F-19 and F-21 were
  checked with the repository's doubles at the same call boundaries. F-21's
  production line (`RuntimeError`) follows from the real adapter's `close()`,
  which sets `_closed` before closing the connection
  (`postgres_ingestion_repository.py:657-661`) and raises `RuntimeError` on any
  later call. This was read, not run.
- `pg_terminate_backend` of a real stale session that holds the exclusion (the
  README procedure was not exercised).
- That the per-turn feedback hook fired during the rework.
- Who wrote the round-3 correction of `run_ingest`, and under whose
  authorization (F-12).

## Audit log

| Round | Date | Verdict | Notes |
|---|---|---|---|
| 1 | 2026-10-18 | REJECTED | At `7603379`. F-01 and F-02 (CRITICAL) and F-03 (HIGH) block; F-04 to F-07 MEDIUM, F-08 to F-12 LOW |
| 2 | 2026-10-18 | REJECTED | At `91bd69d`. F-01 to F-11 resolved. New: F-13 (MEDIUM, blocking), F-14 (MEDIUM, blocking until decided), F-15 to F-17 LOW |
| 3 | 2026-10-18 | REJECTED | At `287946f`. F-13 to F-17 resolved. New: F-18 (HIGH, blocking: K could write without the exclusion after a lost connection); F-19 and F-20 LOW; F-12 carried |
| 4 | 2026-10-18 | REJECTED | At `10e126d`. F-18 and F-19 resolved for the two named calls; F-01 to F-17 still resolved (14 of 14 mutants killed); 87 red tests on the round-3 code; 2405 tests pass locally and in CI. New: F-21 (MEDIUM, blocking: an interrupt elsewhere in the recovery window, for example while the lost repository is closed, still enters K on the lost repository; AC7, plan C "The current repository", K). F-22 LOW. F-12 and F-20 LOW, still partially open. Next: the human at gate 3, then the architect (C step 1 sentence and a Validation row), the red tests, the fix and round 5 |
