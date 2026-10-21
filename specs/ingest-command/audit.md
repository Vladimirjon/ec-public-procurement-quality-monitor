# Audit: Ingest command (F4)

Auditor: `sdd-auditor` (outcome O10), round 5, 2026-10-21.
Reviewed: branch `fix/ingest-audit-hardening` at `80c8aab064704a92de289c0502c48025f03eae1e`
(PR #26 against `main` at `eca3cc4`, which holds PR #25 and the round 4 code).
Specs: `intent.md` Revision 12, `execution-plan.md` Revision 10 and `tasks.md`
Revision 7, all approved by the human on 2026-10-20. The working tree held one
uncommitted change to `specs/ingest-command/tasks.md` (the PR #26 and CI
accounting entry); it is not part of the audited head and was not used as
evidence. Three working-tree files (`ingest_use_case.py`, `ingest_command.py`,
`test_local_disk_raw_evidence_store_listing.py`) carry CRLF line ends while the
index holds LF (`.gitattributes` says `eol=lf`); the content is identical
(`diff -rq --strip-trailing-cr` against `git archive HEAD` is empty), so this is
a checkout artifact, not a change.

The whole feature was audited again, and nothing from rounds 1 to 4 was assumed
to still hold. `application/ingest_use_case.py` (1693 lines),
`interfaces/ingest_command.py` (405 lines) and `interfaces/cli.py` were read in
full against the state machines P, C (with "The current repository", "The
explicit record" and "Two or more exceptions"), K, T, R, H and I, the "Refused
writes" table and "A refusal is answered, never retried", the required progress
lines, the invocation order, § Output (including "Writing the result"),
§ Exit codes and AC1 to AC25. `git diff main` was read line by line: the use
case (+206/-57), the command (+65/-15), the README (+25/-7), the specs and
2018 added test lines. The only two removed test lines are an import widened to
`TYPE_CHECKING, Literal` in `test_ingest_command.py` and one docstring line of
`FlakyRepository` in `tests/unit/ingest/conftest.py`; no assertion was removed or
weakened. The executor's commit `80c8aab` touches only `README.md`,
`ingest_use_case.py` and `ingest_command.py`; the tests came in the test-writer's
commit `3844101`.

Evidence labels:

- `rerun`: the auditor ran it in this round.
- `reused`: a recorded result that is still current (the CI runs of PR #26 at
  `80c8aab`).
- `experiment`: a throwaway auditor test or mutant, run in the session
  scratchpad, never in the repository. It runs on a scratch copy of `src/` and
  `tests/` extracted with `git archive HEAD`, checked byte for byte against a
  second pristine archive before the run and after every mutant (47 mutants, all
  restored), with the repository's own doubles from `tests/unit/ingest/conftest.py`.
- `unavailable`: it could not be checked.

## Final verdict

APPROVED WITH RESERVATIONS

**Summary**: F-20, F-21 and F-22 are resolved, F-01 to F-19 are still resolved,
and every N-1 to N-11 rule of the sweep holds in the code and in the tests:
2616 tests pass locally and in CI, every focused row of § Validation passes, and
40 of 47 mutants are killed (2 of the 7 survivors are equivalent). Only LOW
findings remain: two spec questions the approved text leaves open (F-23, the
refused write followed by a Ctrl+C in its line; F-24, `SystemExit` against
`KeyboardInterrupt`), plan-required paths with no test that would fail (F-25),
a Ctrl+C or a stream error during invocation step 1 that escapes the command
(F-26), and stale text in `tasks.md` (F-12). The human decides at gate 3 whether
to accept them as reservations.

One classification needs the human's eye: F-26 is rated LOW because the plan's
own CLI design leaves the argument parsing of step 1 in `main()` without any
handler, so the § Exit codes sentence "a `KeyboardInterrupt` that ... interrupts
steps 1 to 4" cannot be read literally for all of step 1. If the human reads
that sentence as binding for the part of step 1 inside `run_ingest_command`,
F-26 is an unmet binding constraint, it blocks, and the verdict is REJECTED.

**Critical Issues** (must fix before merge):
- none

**Warnings** (should fix, not blocking):
- F-23 (LOW, needs a spec decision): after a refused `page-failed`, `storage-failed` or normal-path append, or a refused final `finish_run(succeeded)`, a Ctrl+C or a `MemoryError` that lands in the refusal's progress line makes State machine K append `run-interrupted` (or `unexpected-error`) and call `finish_run(failed)`. It is another write, not a retry, and it matches the plan's K, but AC6 (e) "no further event is added" can be read to forbid it.
- F-24 (LOW, needs a spec decision): the spec does not decide `SystemExit` against `KeyboardInterrupt`. The code lets `SystemExit` win in the recovery window, while at the final close a `KeyboardInterrupt` replaces a propagating `SystemExit`; a `SystemExit` from the final close also drops the result line of a confirmed run. No test pins any of it (mutants M5, M14 and M15 survive).
- F-26 (LOW): a Ctrl+C, or an error of the stream, during invocation step 1 inside `run_ingest_command` (the argument and environment checks and the write of the usage error) escapes the command, so `main()` ends with a traceback instead of returning 130 or 2. Nothing is built or written. Present since round 1.

**Recommendations** (nice to have):
- F-25 (LOW): permanent tests for the plan-required paths that no test pins: a window operation whose own line raises (`ingest_use_case.py:212-213`, N-3; mutant M16 survives), a `KeyboardInterrupt` from the final close while another exception propagates (1298, N-9; M15 survives), and the `on_loss` hook of the P-2 `read_run` (636, C step 6; M28 survives). 1313 and 1315 follow F-24 and free wording.
- F-12 (LOW, carried): `tasks.md` at `80c8aab` is stale in five places (§ Status, § Checkpoint, the O8 Revision 6 to-do, O10 round 4 step 1 and the "uncommitted" round 5 green evidence).

Next role: the human at gate 3. If the human accepts the reservations, the
spec questions F-23, F-24 and F-26 go to the architect when the human wants them
closed (none needs a new acceptance criterion), the F-25 tests to the
test-writer, and F-12 to whoever keeps `tasks.md`. If the human reads F-26 as
blocking, the route is the gate 3 rejection rule: the architect, then the
red test (the `environ` and `stderr` seams already allow it), the fix and
round 6.

## Rounds 1 to 4 summary

- **Round 1** (`7603379`, REJECTED). 12 findings. F-01 and F-02 (CRITICAL, AC7,
  AC15, State machine K) and F-03 (HIGH, AC14 and ADR 0006) blocked. The full
  report is in git history at `7069f4c`.
- **Round 2** (`91bd69d`, REJECTED). F-01 to F-11 were resolved. New: F-13 and
  F-14 (MEDIUM, blocking), F-15 to F-17 (LOW). The full report is at `2f77b5e`.
- **Round 3** (`287946f`, REJECTED). F-13 to F-17 were resolved. New: F-18
  (HIGH, blocking: the cleanup could write without the ingest exclusion after a
  lost connection), F-19 and F-20 (LOW), F-12 carried. The full report is at
  `fe0fb28`.
- **Round 4** (`10e126d`, REJECTED). F-18 and F-19 were resolved for the two
  named calls. New: F-21 (MEDIUM, blocking: an interrupt elsewhere in the
  recovery window still entered K on the lost repository), F-22 (LOW, the
  unguarded final close), F-20 and F-12 still partly open. The full report is
  at `25d1253`. Intent Revision 11, plan Revision 9 and tasks Revision 6
  answered it, then the architect's sweep A2 (N-1 to N-11) gave intent
  Revision 12, plan Revision 10 and tasks Revision 7, all approved by the human
  on 2026-10-20. The rework landed in `3844101` (211 red tests) and `80c8aab`
  (the fix and the README).

## Resolution of the earlier findings

Each closure condition was checked against the current code and against at
least one mutant of this round that a test kills (scratch copy, full
`tests/unit/ingest`, 1189 tests). The "E-" mutants re-create the round 1 to 4
fixes on the current code.

| Id | Earlier severity | Status | Evidence (current code; mutant: failing tests) |
|---|---|---|---|
| F-01 | CRITICAL | Resolved (still) | Pending set before `store` (1505), cleared only when the record returned or the path concluded (1533, 1553, 1579, 1595). E-F01 (clear right after `store`): 4 failed |
| F-02 | CRITICAL | Resolved (still) | K absorbs the three read-back errors (768-771). E-F02 (absorb `EvidenceNotFoundError` only): 4 failed |
| F-03 | HIGH | Resolved (still) | `ingest_command.py:324-330`, source built before `_migrate` (332). E-F03 (exit 1 instead of 2): 16 failed |
| F-04 | MEDIUM | Resolved (still) | `_print_running` (269-276) through `_end_after_escape` (279-287). E-F04 (no `<id> running`): 24 failed |
| F-05 | MEDIUM | Resolved (still) | K reads the run first (757-766). E-F05: 9 failed |
| F-06 | MEDIUM | Resolved (still) | Chain store read errors -> `invalid resumption chain <id>` (1399-1409). E-F06: 10 failed |
| F-07 | MEDIUM | Resolved (still) | Page lines (`_report_page` 423-427; 1490, 1521, 1551, 1568). E-F07: 8 failed |
| F-08, F-09 | LOW | Resolved (still) | No `_finish` helper; `ingestion_catalogue.py` says 32 characters |
| F-10 | LOW | Resolved (still) | 947-978. E-F10 (listing `OSError` escapes): 2 failed |
| F-11 | LOW | Resolved (still) | `_append_on_normal_path` (581-606), `_close_failed` (510-554), `_finish_succeeded` (609-647), refused `start_run` (1443-1445). E-F11: 9 failed. See F-23 for the compound case with an interrupt |
| F-12 | LOW | Partially resolved (carried) | The round 4 items are closed: the human's choice for the round 4 and round 5 correction is recorded (O10 round 4 step 3; § Working state A3), and the line 1530 label is corrected. New stale text at `80c8aab`: see F-12 below |
| F-13 | MEDIUM | Resolved (still) | `_cleanup_step` (718-734). E-F13 (K writes no line): 49 failed |
| F-14 | MEDIUM | Resolved (still) | One line per refused or lost call in every phase (`_reporting_failure`, `_read_database`, `_guarded`, `_recovery_step`). E-F14: 18 failed; E-F19 (no line in the window): 10 failed |
| F-15 | LOW | Resolved (still) | Fixed messages naming the identity (1363-1368, 1394-1398, 1420-1424, 829-833). E-F15 (unreadable target -> `INVALID_TARGET`): 10 failed |
| F-16 | LOW | Resolved (still) | (a) first opening handled (1243-1254); E-F16a: 2 failed. (b) `result_written` (261, 274); M9: 4 failed, M10: 4 failed |
| F-17 | LOW | Resolved (still) | README § Ingesting lists every `running` case (inspection, rerun) |
| F-18 | HIGH | Resolved (still) | The second repository becomes current only after `True` (303-305). M19 (current before the exclusion): 40 failed |
| F-19 | LOW | Resolved (still) | `_recovery_step` names only the call of the window (193-214). E-F19: 10 failed |
| F-20 | LOW | Resolved | `generic_fallback` (2 tests) pins the `NOT_STARTED` fallback (1677-1678). E-F20 (R11, re-raise there): 23 failed. The two accepted limitations stay accepted (§ Accepted limitations) |
| F-21 | MEDIUM | Resolved | The explicit record: `_PersistenceSession._current` (232), `drop_current` as the first action of every loss handler (`safe_repeat` 326 and 332, `on_loss` 171-172 in `append_event` 358 and 377 and in the P-2 `read_run` 636); the outer handlers read `session.current` and never enter K with none (1661-1663, 1679-1681). Closes of C steps 1 and 3 follow the rule (`close` 266-277, `_reconnect` 284-314); the final close attempts what is left (1272-1321). Tests: `reconnect_close_interrupt` 40, `reconnect_loss_line_interrupt` 10, `reconnect_false_close_interrupt` 6. Mutants: M1 107, M20 107, M17 21, M18 8, M2 4, M4 4, M30 4 failed. README § Ingesting holds (lines 261-269). Every closure item of round 4 is met |
| F-22 | LOW | Resolved | `_close_after_outcome` and `_close_while_propagating` (1290-1321). Tests: `final_close_error`, `final_close_interrupt`, `exit_code_final_close` (28 together). E-F22 (the interrupt escapes): 9 failed; M23 (`MemoryError` not suppressed): 7 failed |

The sweep A2 rules (plan Revision 10):

| Rule | Status | Evidence |
|---|---|---|
| N-1 (second loss of `start_run`) | Holds | 1439-1442 and `safe_repeat` 331-334; `start_run_second_loss` 34 and `exit_code_start_run_second_loss` 14 (rerun); E-N1 (Ctrl+C keeps the run): 35 failed; experiment X17 |
| N-2 (Ctrl+C during K after a `MemoryError` propagates) | Holds | `_cleanup_step` and K catch `Exception` only (730, 806); `unexpected_cleanup_interrupt` 18 + 4; E-N2 (K swallows it): 17 failed |
| N-3 (two exceptions in the window) | Holds, with F-24 and F-25 | `_prevailing` (179-190) in `_recovery_step` and `_reconnect`; `recovery_double_fault` 15 + 2; M6: 6 failed; M5 and M16 survive |
| N-4 (a refusal is never retried) | Holds | Pending cleared before the refusal's line (1533, 1579); `drop_current` after a refused `finish_run(failed)` (540); `refusal_not_retried` 37 + 2; M7 19, M8 8, M3 8 failed. The compound case with another write is F-23 |
| N-5 (close errors scoped to the window) | Holds | `close` re-raises `MemoryError` only in the window (274-276); the final close suppresses every `Exception` (1283) |
| N-6 (an interrupted line may be missing) | Holds | Tests use both `when="before"` and `"after"` |
| N-7 (writing the result) | Holds | `_report`, `_attempt`, `_settled_code`, `_end_after_escape` (227-287); `result_line_stream_fault` 21, `handler_stream_fault` 8; M9, M10, M11, M12, M22, M24, M31 killed; M32 (stdout first) survives and is equivalent (the order is free) |
| N-8 (130 for a Ctrl+C at C step 1 or on the loss line, P-2 case) | Holds | `reconnect_close_interrupt` includes the lost final `finish_run(succeeded)` |
| N-9 (what propagates out of `run_ingest`) | Holds, with F-25 | 1266-1268, 1290-1298; experiments X8 to X10 |
| N-10 (one-shot close fault) | Holds | `FlakyRepository.close` pops one `CloseFault` per call (`conftest.py:1226-1233`) |
| N-11 (accounting) | Holds | O10 round 4 step 3 and § Working state A3 record the delegation of 2026-10-20 |

## Findings

| Id | Severity | AC / constraint | Finding and evidence | Failure scenario | Closure condition | Status |
|---|---|---|---|---|---|---|
| F-23 | LOW (needs a spec decision; not blocking) | AC6 (e) ("when the refused write is itself a failure-path write ... no further event is added"); AC7 (a best-effort audit and close after Ctrl+C); plan § State machine P "Refused writes" and "A refusal is answered, never retried"; § State machine K; plan Revision 10 § Sweep A2 responses, last bullet ("identified for the audit") | A refused write followed by an interrupt in its progress line enters State machine K, which appends `run-interrupted` (or `unexpected-error`) and calls `finish_run(failed)`. This holds for a refused failure-path append (`page-failed` X1, `storage-failed` X3), a refused normal-path append (`page-completed` X4; the table answers it with `storage-failed`) and a refused final `finish_run(succeeded)` (X5). The cause is that only a refused `record_observation` (pending cleared, 1533, 1579) and a refused `finish_run(failed)` (`drop_current`, 540) change what K does. Verdict: consistent with the plan, not a defect against it. K's step 3 is another write, not a retry; the plan says of a refused record that K "still runs its steps 1, 3 and 4 ... (they are other writes)"; and AC7 asks for a best-effort audit and close after a Ctrl+C. But AC6 (e) and F-11 ("no event answers the refusal of a failure-path event") can be read as "nothing after the refusal except `finish_run(failed)`", and no rule decides between the readings | X1 (experiment): page 2 answers `500`, the `page-failed` append is refused, and the reporter raises `KeyboardInterrupt` on its line. Result: K reads the run, appends `run-interrupted` (page 2) and finishes `failed`; `INTERRUPTED`, `failed`; at the command tier exit 130, stdout `<A> failed`. The control without the Ctrl+C (X2) ends `RUN_FAILED`, `failed`, with no further event. With `MemoryError` instead: `unexpected-error` (page 2, `MemoryError`), `RUN_FAILED`, `failed`. X6: when the database refuses the run's appends persistently, K's append is refused too, K writes its line and stops, and the run stays `running` (exit 130, `<A> running`), where the same refusal without the Ctrl+C ends `failed` (exit 1) | The architect decides, with the human, between keeping the current behavior (K audits the interrupt after any refusal except `finish_run(failed)`, and AC6 (e) says so) and suppressing K's step 3 after a refused write (K then only closes the run, or does not run). If the rule changes, a Validation row and red tests (X1 to X6 are templates) precede the fix | Open (spec decision) |
| F-24 | LOW (needs a spec decision; not blocking) | Plan § Public names (`run_ingest`: "`SystemExit`" propagates; "The final close", last bullet: "a `KeyboardInterrupt` from it propagates in its place"; "`SystemExit` raised by a `close()` propagates"); § State machine C ("`SystemExit` propagates, and the second repository is still closed" against "Two or more exceptions": "a `KeyboardInterrupt` among them gives the `KeyboardInterrupt` outcome"); AC15 ("Closing the database connection at the end of the invocation never changes how the run ended") | The spec does not decide `SystemExit` against `KeyboardInterrupt`. The executor's `_prevailing` (179-190) ranks `SystemExit` first, and it is used in `_recovery_step`, `_reconnect` and `_close_remaining`. `_close_while_propagating` (1290-1298) does not consult the propagating exception, so a `KeyboardInterrupt` from the final close replaces a propagating `SystemExit`; this follows the plan's literal sentence and is the opposite ranking. `_close_remaining` can hold at most one repository (C step 1 closes the lost repository before a second one is opened), so "a `SystemExit` from a final close is raised after the other repositories were attempted" is unreachable. No test raises `SystemExit` at any of these points: M5 (swap the ranking), M14 (swallow a `SystemExit` from the final close) and M15 (swallow the final close's interrupt while another exception propagates) survive all 1189 unit tests | X16 (experiment): in the window, the second exclusion raises `KeyboardInterrupt` and the second repository's `close()` raises `SystemExit(4)`. `SystemExit` escapes `run_ingest`; under the N-3 reading the outcome would be `INTERRUPTED`, exit 130, `<A> running`. X10: a `SystemExit` from the transport propagates, the final close raises `KeyboardInterrupt`, and `KeyboardInterrupt` escapes. X11 and X15: after an AC1 run confirmed `succeeded`, the final `close()` raises `SystemExit(3)`; the command's result line is never written (stdout empty, exit 3, the run `succeeded` in the store). X15 at the command tier for six raise points: `SystemExit(3)` always escapes `run_ingest_command`, stdout is empty even after `run <A> started`, every repository and the source are closed, nothing more is written, and the run stays as it was (`running` or `succeeded`). No adapter of the project raises `SystemExit`, so each case needs a defect elsewhere | The architect states the precedence of `SystemExit` against `KeyboardInterrupt` once, for the window, the final close while an exception propagates, and the final close after an outcome, and says whether AC15's final-close sentence covers `SystemExit`. Tests pin the chosen ranking (X10, X11 and X16 are templates) | Open (spec decision) |
| F-25 | LOW (recommendation) | Plan § State machine C "Two or more exceptions" (N-3), § Public names "The final close", last bullet (N-9), § State machine C step 6 ("The record becomes *none* again"); harny-audit step 5 (a test that would fail if the behavior were removed) | Plan-required behavior that no test pins (coverage report and surviving mutants): (a) 212-213, the line of a window operation that raises in turn (N-3 decides; M16, raise the line's error instead of `_prevailing`, survives); (b) 1298, a `KeyboardInterrupt` from the final close while another exception propagates (N-9; M15 survives); (c) 636, the `on_loss` hook of the P-2 `read_run` (C step 6: the record is *none* after a further loss; M28, remove the hook, survives: after a refused P-2 repeat and a lost `read_run`, a Ctrl+C in that loss line would enter K on the lost second repository and K would write a `read_run` line, by reading); (d) 1313 and 1315, which depend on F-24 and on free wording (M13, rewrap an `INTERRUPTED` outcome, is equivalent under the plan) | X7 (experiment): the second exclusion raises `MemoryError` and its line raises `KeyboardInterrupt` -> `INTERRUPTED`, `running`, nothing written, all closed; `KeyboardInterrupt` then `MemoryError` -> `INTERRUPTED`; `RuntimeError` then `MemoryError` -> `RUN_FAILED`, `running`. X8: a `KeyboardInterrupt` during K after a `MemoryError` propagates, the final close raises `KeyboardInterrupt` before closing -> `KeyboardInterrupt` escapes (context chained, never printed), the repository stays open after its one attempt. X12: an `INTERRUPTED` outcome whose final close is interrupted is returned unchanged. Every experiment shows the planned behavior; the gap is regression protection | Unit tests that fail on M15, M16 and M28 (X7, X8 and a P-2 variant of `reconnect_loss_line_interrupt` are templates), and the 1313 and 1315 cases once F-24 is decided | Open (recommendation) |
| F-26 | LOW (not blocking; see the verdict for the alternative reading) | Plan § Exit codes, 130 ("a `KeyboardInterrupt` that escapes `run_ingest` or interrupts steps 1 to 4"); § Order of an invocation step 1; AC15 ("nothing prints a traceback"); plan § Public names (`interfaces.cli`: `main` calls `run_ingest_command` and raises `SystemExit(code)`, with no handler) | In `run_ingest_command` (`ingest_command.py:371-377`), `request_from_arguments`, `_settings_from` and the write of the usage error sit outside the `except KeyboardInterrupt` and `except Exception` handlers, which start at line 378. A Ctrl+C there, or a stream error while the usage error is written, escapes the command. Through `main()` Python then prints a traceback; the process exits by the interpreter's own rule (130 through SIGINT on POSIX, 0xC000013A on Windows), not through `SystemExit(130)`. Nothing is built, requested or written. These lines are unchanged since round 1 and no earlier round raised them. The plan's own CLI design leaves the argument parsing of step 1 in `main()` unguarded, so the "steps 1 to 4" sentence cannot be literal for all of step 1 | X22 (experiment): an `environ` mapping whose read raises `KeyboardInterrupt` -> `KeyboardInterrupt` escapes `run_ingest_command`, with no collaborator built. With `environ={}` and a `stderr` that raises on the `POSTGRES_DB is not set` message: `KeyboardInterrupt` escapes, and an `OSError` escapes too | Either the command's two handlers also cover step 1 (a usage error whose message cannot be written still exits 2; a Ctrl+C exits 130 with stdout empty), with a test through the existing `environ` and `stderr` seams, or the architect scopes the 130 row and AC15 to the steps after argument parsing | Open |
| F-12 | LOW (carried, partially resolved) | harny-audit step 4 (outcome state); plan § Rollout M4 (authorship) | `tasks.md` at `80c8aab` is stale: § Status (line 8) ends "the test-writer then writes the red tests of plan Revisions 9 and 10 together (the human stops after the red evidence, before A3)"; § Checkpoint (line 460) says "Next: the human reviews the round 5 diff and green evidence (nothing committed)"; the O8 Revision 6 to-do (line 302) says "Not yet written", but the README text was written in `80c8aab`; O10 round 4 step 1 (line 340) says the Revision 12/10/7 approval is "pending"; § Working state (line 403) calls the committed round 5 fix "uncommitted, awaiting the human's review before commit". The uncommitted PR #26 entry (not audited) does not change these lines | The next role reads that the fix is not committed and that the README is not written | § Status, § Checkpoint, O8, O10 and § Working state describe `80c8aab`, PR #26 and the round 5 audit | Open |

## Answers to the round 5 questions

**1. `SystemExit` precedence.** The spec does not decide it; it is an executor
choice where the spec leaves two sentences in collision (F-24). Plan § State
machine C says "`SystemExit` propagates", and its "Two or more exceptions" bullet
says "a `KeyboardInterrupt` among them gives the `KeyboardInterrupt` outcome";
neither names the pair. For the final close while an exception propagates, the
plan does decide, and the opposite way: "a `KeyboardInterrupt` from it
propagates in its place", even when the propagating exception is `SystemExit`
(plan § Public names, "The final close"). The code follows that sentence (X10),
so the executor's "`SystemExit` ranks above `KeyboardInterrupt`" holds in the
window (X16) and inside `_close_remaining`, but not across the final close. "A
`SystemExit` from a final close is raised only after the other repositories were
attempted" is true but moot: at most one repository is ever left for the final
close. Behavior of the command with `SystemExit` at every step (X15, command
tier, `SystemExit(3)`): the first opening, page 2, the second exclusion, the
close of the lost repository at C step 1, a pre-run `read_run`, and the final
close after a confirmed `succeeded`. In every case `SystemExit(3)` escapes
`run_ingest_command` (`main()` exits 3, Python prints nothing). stdout is empty,
also after `run <A> started` and after a confirmed `succeeded`. stderr holds the
lines written before. Every repository and the source are closed, nothing more is
written, and the run keeps its stored state (`running`, or `succeeded` for the
final-close case). This matches "`SystemExit` is not caught" (invocation step 6;
§ Output, "Nothing escapes ... except `SystemExit`"); the final-close case is in
tension with AC15's final-close sentence (F-24).

**2. Paths with no permanent test.** The coverage run gives
`ingest_use_case.py` 655 statements, 8 missed: 212-213, 388-389, 598, 1298, 1313
and 1315 (the same in CI on Linux). `ingest_command.py` and `cli.py` are at
100 %.

| Lines | What it does | Required by the spec | Experiment | Permanent test? |
|---|---|---|---|---|
| 212-213 | A window operation (second open or exclusion) raised something other than a `PersistenceError`, and its own progress line raised too; `_prevailing` decides | Yes: N-3 ("whatever the order of arrival") and the line rule of the window | X7: planned (`INTERRUPTED` when a Ctrl+C is among them, else the first exception's outcome; `running`; nothing written; all closed) | Yes, LOW (F-25; M16 survives) |
| 388-389 | The re-check path of `append_event` lost again on the second repository | Accepted limitation (F-20, 2026-10-18) | X13: two loss lines, `RUN_FAILED`, `running`, all closed | No; still accepted. The code differs from round 4 only by the `on_loss` hook that C step 6 requires |
| 598 | A normal-path append lost and the recovery not confirmed | Accepted limitation (F-20, 2026-10-18) | X14: `RUN_FAILED`, `running`, lines `append_audit_event page-completed` and `open_repository` | No; still accepted, code unchanged |
| 1298 | A `KeyboardInterrupt` or `SystemExit` from the final close while another exception propagates | Yes: N-9 and "The final close", last bullet | X8, X10: the close's exception propagates in place of the other one | Yes, LOW (F-25; M15 survives) |
| 1313 | A `SystemExit` from the final close after the outcome was determined | "`SystemExit` propagates" (§ Public names) | X11: `SystemExit` escapes, the confirmed outcome is lost | After F-24 is decided |
| 1315 | An outcome already `INTERRUPTED` whose final close is interrupted is returned unchanged | Compliant: "a message that says the ingest was interrupted" (wording free) | X12: unchanged, `failed` kept | Optional (M13 is equivalent) |

Other uncovered lines of the feature, all pre-existing and outside the recovery
zone: `ingestion_catalogue.py:168` (a defensive branch an id matching the
pattern cannot reach) and `system_clock.py:11` (`SystemClock.now`, checked by
inspection against plan § Public names). The other missed lines are F1 to F3
code that F4 did not change.

**3. A refused failure-path append, then a Ctrl+C in its line.** Identified
and reproduced (X1 to X6). Verdict: not a defect against the approved plan. The
cleanup's `run-interrupted` is another write, not a retry, and plan § State
machine P says of a refused record that K "still runs its steps 1, 3 and 4 ...
(they are other writes)". It is still a question the spec should settle,
because AC6 (e) and F-11 can be read to forbid any further event after a refused
failure-path append. The same holds for a refused normal-path append and for a
refused final `finish_run(succeeded)`. Severity LOW; it needs a spec decision
(F-23). It was not fixed, as asked.

**5. The `FileNotFoundError` in
`test_storage_a_regular_file_at_observations_stops_the_run`.** It is
environment-dependent, not a defect, and it was reproduced.

- The signature (X25, experiment): when the test's store folder vanishes before
  the page 2 step, the step's `shutil.rmtree(blocker)` raises
  `FileNotFoundError`. The run ends through K as `RUN_FAILED` with
  `run_status` `failed`, which passes the first two assertions. Then
  `blocker.read_bytes()` at `test_ingest_use_case.py:880` raises
  `FileNotFoundError`, which is the reported failure.
- The executor's exact hypothesis is refuted (X23, experiment). With the
  default `pytest-of-<user>` base, pytest 9.1.1 never deletes the numbered
  folder of a live session: each session holds a `.lock` that
  `ensure_deletable` honors for three days. A 25-second loop of the test body
  (1047 runs) passed while 12 other sessions that use `tmp_path` started and
  ended.
- A variant reproduces it (X24, experiment). With two sessions given the same
  `--basetemp`, the second session removes that folder when it starts (pytest's
  rule for a given base). The loop then failed with `FileNotFoundError` at line
  880 on its 102nd run.
- So the reported failure needs a second pytest session (or any other process)
  deleting the first one's temporary folder. A shared `--basetemp`, which an
  agent restricted to a scratch folder may use, fits. The test is not edited, it
  passes alone, in the full suite and in CI, and it is not a finding.

## Executor choices where the plan was silent

| Choice | Assessment |
|---|---|
| `_prevailing` ranks `SystemExit` above `KeyboardInterrupt` | A defensible reading of "`SystemExit` propagates", but the spec leaves the pair open and the final close ranks them the other way, as the plan's sentence says (F-24) |
| When a window operation's own line raises, `_prevailing` decides (212-213) | Compliant with N-3; untested (F-25) |
| A refused `finish_run(failed)` reuses the explicit record (`drop_current`, 540); a later exception ends through `_recovery_ended` (`INTERRUPTED`, or `RUN_FAILED` with `unexpected error: <Class>`, `running`) | Compliant with N-4 (iv) and "the outcome is `INTERRUPTED` for a `KeyboardInterrupt` and `RUN_FAILED` otherwise, with `run_status=RUNNING`". M3: 8 failed |
| The final-close interrupt message is `the ingest was interrupted while the repository was closed: <earlier message>`; an outcome already `INTERRUPTED` is returned unchanged | Compliant (wording free) |
| `_settled_code` gives 1 for any non-interrupt write failure unless 130 was determined, including the exit 2 of `INVALID_TARGET` (X18: exit 1, stdout empty) | Compliant with the human's N-7 amendment ("any other exception ... that prevents writing the final result gives exit 1"; the final message is part of the result, § Output). Note: AC14's exit 2 then yields to the later, more specific decision |
| `result_written` is set before the first write, also when the outcome names no run | Compliant: it only guards `_print_running`, which needs an announced run |
| The handlers still attempt their stderr line after a stdout failure | Compliant ("The command may write a further stderr line about it"); M31 (skip it) is caught: 24 failed |
| The explicit record is not set to *none* for a loss before the run exists | A compliant alternative: before `start_run` no new connection is opened and K is gated on `run_created`, so the outcome is the same |
| `_PersistenceSession.close` removes the repository from `_unclosed` after closing it | When a Ctrl+C lands after the second opening returned and before it was registered (X21), `close` closes it and then raises `ValueError` from `remove`; `_prevailing` keeps the `KeyboardInterrupt`, so the outcome is right and the repository is closed. Benign, noted |

## Accepted limitations

Lines 388-389 (an append lost again after the re-check) and 598 (a normal-path
append whose recovery is not confirmed) remain the two limitations the human
accepted on 2026-10-18. The code at 598 is unchanged since round 4. The re-check
path gained the `on_loss` hook that C step 6 requires, and its outcome is
unchanged. Experiments X13 and X14 show the planned behavior. They stay
accepted.

## Defect-hunting checklist (both modules against the state machines)

| Area | Result |
|---|---|
| Opening and first exclusion | Hold (`repository_open_error` 19 with `single_result_line`; E-F16a killed) |
| C, the window (step 1 close, loss line, open, exclusion, line of a window error, close after `False`) | Hold: K never runs without a current repository (M1, M20 107 failed each). X20: a Ctrl+C raised inside `open_repository()` after the connection was made leaks that connection; no caller can close an object it never received (inherent, noted) |
| C, repeats, re-check, P-2, second loss, third connection | Hold (`connection_loss` 43, `connection_loss_final_finish` 12, integration 7; M26: 1 failed; E-P2: 4 failed). M28 survives (F-25) |
| K on the current repository | Holds; N-2 propagation holds (E-N2) |
| T, R, H, I | Hold (`pre_run_database_error` 59, `reconcile` 34, `chain` 140, `identity`) |
| Refused writes | Hold, with F-23 for a refusal followed by an interrupt |
| Order: local store -> PostgreSQL -> event -> finish | Holds |
| Write-once evidence; no retries | Hold (`no_retry` 6; F1 store unchanged since `main`) |
| Secrets, URLs, tracebacks, exception text (AC15) | Hold for run output; F-26 for step 1 |
| Exactly one stdout line; writing the result | Hold (N-7 rows; M24: 141 failed) |
| Final close | Holds (F-22 resolved); F-24 for `SystemExit` |
| Asynchronous exceptions between bytecodes | A Ctrl+C can land between a `PersistenceConnectionError` and the first action of its handler, or between `run_ingest` returning and `_report` setting `result_written`; the plan's guarantees start at those first actions, and pure Python cannot close such gaps without masking signals. Noted, not a finding |

## AC results

| AC | Status | Evidence |
|---|---|---|
| AC1 | PASS | `-k success` 9; `-k e2e_success` 2 (rerun) |
| AC2 | PASS | `-k repeat` 13; `-k e2e_repeat` 2 (rerun) |
| AC3 | PASS | `-k last_page` 41, `last_page_p3` 6, `e2e_last_page` 2 (rerun) |
| AC4 | PASS | `-k failure_with_response` 16; `-k e2e_failure` 5 (rerun) |
| AC5 | PASS | `-k failure_without_response` 6 (rerun) |
| AC6 | PASS (note F-23) | `-k storage` 16, `database_refusal` 57, `read_back_record_failure` 4, `refusal_not_retried` 37 (rerun); (a) and (d) also on Linux in CI (reused) |
| AC7 | PASS (notes F-23, F-24, F-26) | `-k "interrupt or exit_code"` 348; `interrupt_during_record or cleanup_read_back` 14; `interrupt_after_finish` 11; `cleanup_database_error or final_finish_read_run or output_database_error` 49; `reconnect_exclusion_interrupt or reconnect_open_interrupt` 93; the F-21 row 56; `final_close_error or final_close_interrupt` 20; `unexpected_cleanup_interrupt` 18; `recovery_double_fault` 15; `refusal_not_retried` 37 (rerun). F-21 is resolved |
| AC8 | PASS | `-k connection_loss` 43 (unit), `test_ingest_connection_loss.py` 7 (integration), `connection_loss_final_finish` 12, integration `final_finish` 4, `start_run_unconfirmed` 12, `start_run_second_loss` 34, the F-21 row (rerun) |
| AC9 | PASS | `-k resume` 24; `-k e2e_resume` 5 (rerun) |
| AC10 | PASS | `-k reconcile` 34; `-k e2e_reconcile` 6; `reconcile_os_error` 4 (rerun) |
| AC11 | PASS | `-k closed_run` 3; `interrupt_after_finish` 11 (rerun) |
| AC12 | PASS | `-k "execution_id or identity"` 67 (rerun) |
| AC13 | PASS | `-k "scope or catalogue"` 111; `assert_follows_catalogue` across the new tests (rerun) |
| AC14 | PASS (note F-26) | `-k "usage or environment"` 66; `source_configuration or order_of_invocation` 30 (rerun) |
| AC15 | PASS (notes F-24, F-26) | `-k "output or logger"` 81; `output_escaping_exception` 12; progress group 24; `pre_run_database_error` 59; `repository_open_error or single_result_line` 19; `result_line_stream_fault` 21; `handler_stream_fault` 8; `generic_fallback` 2 (rerun) |
| AC16 | PASS | integration `-k migrations` 11; hierarchy 3; lock and runner 23; `git diff 2e6edcd --numstat -- tests/integration/test_postgres_migrations.py` -> `3 0` (rerun) |
| AC17 | PASS | `-k no_retry` 6 (rerun) |
| AC18 | PASS | `uv run pytest tests/unit -q -k layer` 16; the AC18 grep of `application/` (`SELECT `, `INSERT `, `UPDATE `, `DELETE `, `objects/`, `observations/`, `.json`, `advisory`, `pg_`, `psycopg`, `httpx`) finds nothing; `interfaces` imports neither `httpx` nor `psycopg`; `git diff main --stat -- pyproject.toml uv.lock` is empty, and against the baseline `2e6edcd` `pyproject.toml` shows only the two F-1 keys and three comment lines and `uv.lock` no diff; `mypy` 52 files clean (rerun) |
| AC19 | PASS | `uv run --env-file .env pytest tests/unit/ingest tests/integration/ingest -q` -> 1273 passed; 0 files under the real `data/` before and after; 0 `ecpq_test_` databases (rerun) |
| AC20 | PASS | 2616 passed (1307 baseline + 1309 F4); the AC20 `git diff --stat` list is empty against `main` and against `2e6edcd`; the only pre-F4 test file changed since `2e6edcd` is `test_postgres_migrations.py` (`3 0`); `git ls-files .env` is empty; `git diff main --check` and `git diff --check` are clean; ruff, format (120 files), mypy and the doctor (`31 ok, 0 skipped, 0 warned, 0 failed`) pass; `--version` -> `ec-procurement-quality 0.1.0` (rerun) |
| AC21 | PASS | README § Ingesting read sentence by sentence against the code (lines 246-307). The recovery window (261-269), the refused `finish_run` (270-271), "answered once and not repeated" (284-285: true; the writes of F-23 are other writes), the final close (287-289; the parenthesis gives examples, and `running` is also kept), the output-failure paragraph (290-295) and the exit table (305, 307) match the code. AGENTS.md, `docs/architecture.md` and CHANGELOG are unchanged since round 4 and still match. No document claims a live run (rerun, inspection) |
| AC22 | PASS | listing 25 (rerun) |
| AC23 | PASS | `test_postgres_runs_and_exclusion.py` 24 (rerun) |
| AC24 | PASS | `-k chain` 140, `chain_last_page` 33, `e2e_chain_last_page` 3, `chain_unreadable_record` 12 (rerun) |
| AC25 | PASS | `-k "paths or environment"` 34; integration `-k root` 2 (rerun) |

Plan decisions:

| Item | Status | Evidence |
|---|---|---|
| P-1 | PASS | `ingest_command.py:290-310`; lock and runner 23 |
| P-2 | PASS | `_finish_succeeded` (609-647); E-P2 killed |
| P-3 | PASS | 1638-1653 |
| P-4 | PASS | `_resume_plan` (1129-1229) |
| P-5 | PASS | `_unconfirmed`, `_recovery_ended`, K, `_print_running` |
| F-1 | PASS | `pyproject.toml` against `2e6edcd`: the two keys and three comment lines, additions only |
| F-2, F-3 | PASS | `ingestion_catalogue.py`; 1513-1519 |

## Binding-constraint compliance

| Constraint | Status | Evidence |
|---|---|---|
| Layer placement (ADR 0001, AC18) | PASS | Layer tests 16; grep clean; `interfaces` imports |
| Public names and signatures | PASS (note F-24) | Pinned types and signatures unchanged; the propagation list (N-9) holds |
| CLI arguments and configuration | PASS | `cli.py` unchanged; `ingest_command.py:109-170` unchanged; `test_cli.py` 2 |
| Order of an invocation | PASS (note F-26) | Steps 1 to 7; step 1 inside the command is outside its handlers |
| Exit codes | PASS (note F-26) | `_EXIT_CODES` (218-224), `_settled_code` (240-250) |
| Output (AC15), "Writing the result" | PASS | N-7 rows; M9 to M12, M22, M24, M31 killed |
| Audit details (closed catalogue) | PASS | `assert_follows_catalogue` across the paths |
| State machine P, "Refused writes", "never retried" | PASS (note F-23) | N-4 row; M3, M7, M8 killed |
| State machine C, "The explicit record", "Two or more exceptions" | PASS (notes F-24, F-25) | F-21 resolved; M1, M2, M4, M6, M17 to M20, M30 killed |
| State machine K | PASS | Only on the current repository; N-2 holds |
| State machines T, R, H, I | PASS | Unchanged since round 4; earlier-fix mutants killed |
| F1 and F3 port extensions | PASS | Listing 25; runs and exclusion 24 |
| No schema change | PASS | `migrations/` holds `0001_initial_schema.sql` only, no diff |
| No dependency (AGENTS.md, PT-11) | PASS | `uv.lock` no diff; `pyproject.toml` only the F-1 keys |
| ADR 0006 (configuration before the migrations) | PASS | E-F03 killed |
| R-6 and N3 (no chain or `__context__` printed) | PASS | Only class names reach the reporter; the exceptions `_prevailing` raises are never printed |
| R-7 (`httpcore` above `DEBUG`) | PASS | `_httpcore_above_debug` |
| SA-13 and PS-13 (one source, at most two repositories, all closed) | PASS | `opens <= 2` and `all_closed` everywhere; X20 is an inherent leak inside the opener |
| Q4 (one ingest active per database) | PASS | No write without the exclusion on any path found, including X1 to X21 |
| Tests (guards, no real `data/raw/`, throwaway databases) | PASS | Guards pass; `data/` empty; 0 leftover databases |
| `.env` never read by code or committed | PASS | `git ls-files .env` empty; no code reads `.env`; the auditor never read it (the database count script reads only the variables `uv run --env-file` loaded and prints only a count) |

## Test coverage

| AC | Tests (file) | Status |
|---|---|---|
| AC1 | `success` in `tests/unit/ingest/test_ingest_use_case.py`; `e2e_success` in `tests/integration/ingest/test_ingest_end_to_end.py` | PASS |
| AC2 | `repeat` (unit); `e2e_repeat` (integration) | PASS |
| AC3 | `last_page`, `last_page_p3` (unit); `e2e_last_page` (integration) | PASS |
| AC4 | `failure_with_response` (unit); `e2e_failure` (integration) | PASS |
| AC5 | `failure_without_response` (unit) | PASS |
| AC6 | `storage`, `database_refusal`, `read_back_record_failure`, `refusal_not_retried` (unit); `exit_code_refusal_not_retried` in `tests/unit/ingest/test_ingest_command.py` | PASS (F-23 compound case untested by design: no rule) |
| AC7 | `interrupt`, `interrupt_during_record`, `cleanup_read_back`, `interrupt_after_finish`, `cleanup_database_error`, `reconnect_*`, `final_close_*`, `unexpected_cleanup_interrupt`, `recovery_double_fault`, `refusal_not_retried` (unit); `exit_code_*` (command) | PASS (F-25 regression gaps) |
| AC8 | `connection_loss`, `connection_loss_final_finish`, `final_finish_read_run`, `reconnect_*`, `start_run_unconfirmed`, `start_run_second_loss` (unit and command); `tests/integration/ingest/test_ingest_connection_loss.py` | PASS |
| AC9 | `resume`, `pre_run_database_error` (unit); `e2e_resume` (integration) | PASS |
| AC10 | `reconcile`, `reconcile_os_error` (unit); `e2e_reconcile` (integration) | PASS |
| AC11 | `closed_run`, `interrupt_after_finish` (unit) | PASS |
| AC12 | `execution_id` (`test_ingestion_catalogue.py`), `identity` (unit) | PASS |
| AC13 | `scope`, `catalogue`, `assert_follows_catalogue` | PASS |
| AC14 | `usage`, `environment`, `source_configuration`, `order_of_invocation` (command); `cli_invalid_*` (integration) | PASS (F-26: no step 1 interrupt test) |
| AC15 | `output`, `logger`, `output_escaping_exception`, `output_progress`, `output_database_error`, `single_result_line`, `result_line_stream_fault`, `handler_stream_fault`, `exit_code_final_close_*` (command); `progress_line`, `generic_fallback`, `final_close_*` (unit) | PASS (F-24, F-25) |
| AC16 | `migrations` (integration); `tests/unit/test_persistence_error_hierarchy.py`; `tests/integration/test_postgres_migration_lock_error.py`; the PS-4 edit | PASS |
| AC17 | `no_retry` (unit) | PASS |
| AC18 | `tests/unit/ingest/test_ingest_layers.py`; `mypy` | PASS |
| AC19 | the guards and proof tests of both `conftest.py` files; the session check of `data/raw/` | PASS |
| AC20 | the 1307 existing tests, unedited except the PS-4 assertion | PASS |
| AC21 | none (inspection) | PASS (inspection) |
| AC22 | `tests/unit/test_local_disk_raw_evidence_store_listing.py` | PASS |
| AC23 | `tests/integration/ingest/test_postgres_runs_and_exclusion.py` | PASS |
| AC24 | `chain`, `chain_last_page`, `chain_unreadable_record` (unit); `chain_unreadable_record_message` (command); `e2e_chain_last_page` (integration) | PASS |
| AC25 | `root` (integration); `paths`, `environment` (command) | PASS |

Coverage from the broader command: TOTAL 98 % locally (2616 passed) and in CI.
`ingest_use_case.py` is at 99 % (655 statements, 8 missed, all discussed in
answer 2); `ingest_command.py` and `cli.py` are at 100 %.

### Tier Results

| Tier | Tests found | ACs verified | Setup matches § Validation | Ran | Status | Finding |
|---|---|---|---|---|---|---|
| unit | `tests/unit/ingest/` (1189 tests, +211 this round), `test_local_disk_raw_evidence_store_listing.py` (25), `test_persistence_error_hierarchy.py` (3) | AC1 to AC18, AC22, AC24, AC25, including the eight Revision 9 and Revision 10 rows and their 19 tokens | Yes: the new seams (`CloseFault` and `close_faults`, `RaisingReporter` with a count, `RaisingStream` in `test_ingest_command.py`, the refusal wrapper on every call) are the ones the seams table names; no dev dependency, config or script was added | rerun: every focused row passed (58 unit commands) | PASS | F-25 (recommendation) |
| integration | `tests/integration/ingest/` (84), `test_postgres_migration_lock_error.py`, the PS-4 edit | AC1 to AC4, AC8 to AC10, AC16, AC19, AC23 to AC25 | Yes (PT-13 throwaway databases, host-only `getaddrinfo` guard, `data/raw/` session check); unchanged since round 4 | rerun with `--env-file .env`, all passed; CI reused | PASS | none |
| static | `uv run mypy .` | AC18 | Yes | rerun: 52 files clean | PASS | none |
| command | ruff, format, mypy, doctor, `--version`, git checks | AC20 | Yes | rerun: all clean | PASS | none |
| manual | documentation inspection | AC21 | n/a | rerun (inspection) | PASS | none |

No test exists at a tier that § Validation does not name, and no setup was
added that the plan does not name.

## Mutants (scratch copy, full `tests/unit/ingest`, 1189 tests)

Each mutant replaced exact text in the scratch copy. The copy was restored and
compared byte for byte with the pristine archive after each one (47 of 47
identical).

| Id | Mutant | Result |
|---|---|---|
| M1 | `drop_current` keeps the lost repository current | killed, 107 failed |
| M2 | `safe_repeat` drops the record after the loss line | killed, 4 |
| M3 | `_close_failed` without `drop_current` | killed, 8 |
| M4 | `append_event` drops after the loss line | killed, 4 |
| M5 | `_prevailing` ranks `KeyboardInterrupt` above `SystemExit` | **survived** (F-24) |
| M6 | `_prevailing` ignores `KeyboardInterrupt` | killed, 6 |
| M7 | no pending clear on a refused record (P step 4) | killed, 19 |
| M8 | no pending clear on a refused record (read-back) | killed, 8 |
| M9 | `_report` never sets `result_written` | killed, 4 |
| M10 | `_print_running` ignores `result_written` | killed, 4 |
| M11 | `_settled_code` keeps the code on a write error | killed, 10 |
| M12 | `_settled_code` does not keep 130 | killed, 2 |
| M13 | the final close rewraps an `INTERRUPTED` outcome | survived (equivalent: wording free) |
| M14 | the final close swallows a `SystemExit` after the outcome | **survived** (F-24) |
| M15 | the final close swallows its interrupt while another exception propagates | **survived** (F-25) |
| M16 | a window line failure raises the line's error instead of `_prevailing` | **survived** (F-25) |
| M17 | `close` suppresses `MemoryError` in the window | killed, 21 |
| M18 | `_reconnect` does not close the second repository | killed, 8 |
| M19 | the second repository is current before its exclusion | killed, 40 |
| M20 | the handlers fall back to the dropped repository | killed, 107 |
| M22 | `_attempt` lets `KeyboardInterrupt` escape | killed, 8 |
| M23 | the final close does not suppress `MemoryError` | killed, 7 |
| M24 | the result line is attempted twice | killed, 141 |
| M26 | a third connection is allowed | killed, 1 |
| M28 | the P-2 `read_run` without `on_loss` | **survived** (F-25) |
| M30 | `_reporting_failure` runs `on_loss` after the line | killed, 4 |
| M31 | the handlers skip their stderr line | killed, 24 |
| M32 | `_report` writes stdout first | survived (equivalent: order free) |
| E-F01 to E-F22 | the round 1 to 4 fixes reverted one at a time (F-01, F-02, F-03, F-04, F-05, F-06, F-07, F-10, F-11, F-13, F-14, F-15, F-16 a, F-19, F-20, F-22) | killed, 4, 4, 16, 24, 9, 10, 8, 2, 9, 49, 18, 10, 2, 10, 23, 9 |
| E-N1, E-N2, E-P2 | the `start_run` window keeps the run; K swallows a Ctrl+C; a refused P-2 repeat answered with `storage-failed` | killed, 35, 17, 4 |

40 killed, 7 survived (M13 and M32 equivalent; M5, M14, M15, M16 and M28 are
F-24 and F-25).

## Commands run (2026-10-20 and 2026-10-21, repository root, `80c8aab`)

| Command | Result | Label |
|---|---|---|
| `uv sync --locked` | ok, 25 packages | rerun |
| `uv run pytest -q` (no `--env-file`) | 2350 passed, 266 skipped | rerun |
| `uv run --env-file .env pytest --cov=ec_procurement_quality --cov-report=term-missing -q` | 2616 passed, 0 skipped, TOTAL 98 %; `ingest_use_case.py` missing 212-213, 388-389, 598, 1298, 1313, 1315 | rerun |
| `uv run ruff check .` | All checks passed | rerun |
| `uv run ruff format --check .` | 120 files already formatted | rerun |
| `uv run mypy .` | Success, 52 source files | rerun |
| `uv run node .sdd/doctor/run-doctor.mjs` | 31 ok, 0 skipped, 0 warned, 0 failed | rerun |
| `uv run ec-procurement-quality --version` | `ec-procurement-quality 0.1.0` | rerun |
| Every focused row of § Validation (72 commands: 58 unit, 13 integration and the mixed AC19 row; counts in § AC results and § Resolution) | all passed | rerun |
| `uv run --env-file .env pytest tests/unit/ingest tests/integration/ingest -q` | 1273 passed | rerun |
| AC18 grep of `application/`; `interfaces` imports | no match; no `httpx` or `psycopg` | rerun |
| `git diff main --stat -- pyproject.toml uv.lock`; `git diff 2e6edcd -- pyproject.toml`; `git diff 2e6edcd --stat -- uv.lock` | empty; the two F-1 keys and three comment lines; empty | rerun |
| AC20 `git diff --stat` list, against `main` and against `2e6edcd` | empty, empty | rerun |
| `git diff 2e6edcd --name-status -- tests` (modified pre-F4 files) | `M tests/integration/test_postgres_migrations.py` only, `3 0` | rerun |
| `git diff main -U0 -- tests` (removed lines) | 2: an import line widened, one docstring line | rerun |
| `git diff main --stat -- compose.yaml .env.example docs/glossary.md docs/adr specs/current src/ec_procurement_quality/infrastructure src/ec_procurement_quality/domain` | empty | rerun |
| `git ls-files .env`; `git diff main --check`; `git diff --check` | empty; clean; clean | rerun |
| Leftover `ecpq_test_` databases (count only, scratch script through `uv run --env-file .env`) | 0 | rerun |
| Files under the real `data/` | 0 before and after the suites | rerun |
| `gh run view 39544303927` (`Tests`, head `80c8aab`) | success; 2616 passed, TOTAL 98 %, the same 8 missed lines (Linux) | reused |
| `gh run view 39544303846` (`harny feedback`, head `80c8aab`) | success; `harny-feedback: 2 of 2 command(s) ran, 0 skipped.` | reused |
| `gh pr view 26` | open, head `80c8aab`, `mergeStateStatus` CLEAN, auto-merge off | rerun |
| Experiments X1 to X25 (scratch tests over the repository's doubles and `Rig`) | quoted in § Findings and § Answers | experiment |
| 47 mutants (M1 to M32, E-F01 to E-P2) | 40 killed, 7 survived | experiment |

## Conventions and feedback

- harny-standards, checked against `AGENTS.md` (the project's conventions
  document):
  - the layer boundaries hold;
  - raw responses are never overwritten;
  - no SERCOP contract is invented, and only synthetic `.invalid` data is used;
  - no dependency, infrastructure, framework or service was added;
  - no secrets are in source, tests or docs (the doctor's gitleaks and CI
    secret-scan checks pass; `docs/learning/day-20-prompt.md`, new on this
    branch, holds no secret or data);
  - verification was run and reported (`tasks.md` § Working state, round 5
    green evidence).

  No violation was found. The stale record of `tasks.md` is F-12.
- harny-feedback: `.github/workflows/harny-feedback.yml` exists and its run at
  `80c8aab` is green with 2 of 2 commands run (not 0). The per-turn hooks are
  configured in `.claude/settings.json` (PostToolUse accumulate, Stop,
  SubagentStop), and `.sdd/feedback/.turns/` is live for this session. Whether
  they fired and were heeded during the executor's turns is `unavailable`: turn
  files are not kept after a turn. Lint and type-check were not re-run as
  feedback evidence; they were run only as the AC20 commands.

## Reservations carried forward

- Persistence U1: the real commit-in-flight case is still untested against
  PostgreSQL (CHANGELOG Known limitations).
- Persistence N5: the reconciliation reads run in separate snapshots; safe under
  the exclusion; no path writes without it.
- Raw-evidence N2: handled for `store`, the read-back and the cleanup.
- Source-access R-6, R-7 and R-11 and raw-evidence N3: hold.
- The two F-20 limitations accepted on 2026-10-18 (lines 388-389 and 598).
- Source-access U1: open until the human's live run. No document claims that a
  live run happened.
- Proposed for the human at gate 3: F-23, F-24, F-25, F-26 and F-12, all LOW.

## What could not be verified

- Behavior against the real SERCOP source and the real `data/raw/`: out of
  scope, and it must not be run.
- A real Ctrl+C delivered to a live `psycopg` call, and a Ctrl+C landing between
  two bytecodes (for example between a `PersistenceConnectionError` and the first
  action of its handler, or between `run_ingest` returning and `_report`).
  Faults were injected at the same call boundaries with the repository's
  doubles; the bytecode gaps are noted in the checklist.
- `pg_terminate_backend` of a real stale session that holds the exclusion (the
  README procedure was not exercised).
- That the per-turn feedback hook fired during the executor's rework.
- The environment of the review that first saw the `FileNotFoundError`; the
  shared `--basetemp` reproduction fits it, but the original command was not
  available.

## Audit log

| Round | Date | Verdict | Notes |
|---|---|---|---|
| 1 | 2026-10-18 | REJECTED | At `7603379`. F-01 and F-02 (CRITICAL) and F-03 (HIGH) block; F-04 to F-07 MEDIUM, F-08 to F-12 LOW |
| 2 | 2026-10-18 | REJECTED | At `91bd69d`. F-01 to F-11 resolved. New: F-13 (MEDIUM, blocking), F-14 (MEDIUM, blocking until decided), F-15 to F-17 LOW |
| 3 | 2026-10-18 | REJECTED | At `287946f`. F-13 to F-17 resolved. New: F-18 (HIGH, blocking: K could write without the exclusion after a lost connection); F-19 and F-20 LOW; F-12 carried |
| 4 | 2026-10-18 | REJECTED | At `10e126d`. F-18 and F-19 resolved for the two named calls; F-01 to F-17 still resolved. New: F-21 (MEDIUM, blocking: an interrupt elsewhere in the recovery window still entered K on the lost repository); F-22 LOW; F-12 and F-20 LOW, partly open |
| 5 | 2026-10-21 | APPROVED WITH RESERVATIONS | At `80c8aab` (PR #26). F-20, F-21 and F-22 resolved; F-01 to F-19 still resolved; N-1 to N-11 hold; 2616 tests pass locally and in CI; 40 of 47 mutants killed. New, all LOW: F-23 (a refused write followed by an interrupt in its line; spec decision), F-24 (`SystemExit` against `KeyboardInterrupt`; spec decision), F-25 (untested required paths; recommendation), F-26 (step 1 interrupt or stream error escapes the command). F-12 LOW carried. The `FileNotFoundError` of the AC6 (a) test is environment-dependent (a second session sharing `--basetemp`), not a defect. Next: the human at gate 3 |
