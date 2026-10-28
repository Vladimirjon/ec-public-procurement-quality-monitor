# Audit: Ingest command (F4)

Auditor: `sdd-auditor` (outcome O10), round 8, 2026-10-27.
Reviewed: branch `fix/ingest-audit-hardening` at `108c5a09cda897da1541606a60725b6b9db6bc39`
(PR #26 against `main` at `eca3cc4`; open, `CLEAN`, auto-merge off; checks `tests` and
`feedback` pass on this head). The previous audited head was `871f440` (round 7,
REJECTED: F-31 MEDIUM, class A; F-30 and F-32 to F-36 LOW, class B; F-12 carried).
Since then: `f9a0566` (the round 7 report), `131b740` (specs: intent Revision 15, plan
Revision 13, tasks Revision 10, whose Approval lines say approved by the human on
2026-10-27, with D-11 and D-12 option A, the D-5 adjustments (a) to (d) and the
process-tier exceptions with the cleanup requirement; the tests for the mutants (g) and
(n) left out), `45137d9` (86 tests: 44 unit `absent_*` in
`tests/unit/ingest/test_ingest_command.py`, 42 process tests in
`tests/process/test_cli_process_streams.py`: 40 `process_no_*` and 2
`process_hung_cleanup`) and `108c5a0` (the fix: `interfaces/output_streams.py`,
`interfaces/cli.py`, the `TextIO | None` annotations of `interfaces/ingest_command.py`,
one README sentence). `application/`, `domain/`, `infrastructure/`, `migrations/`,
`pyproject.toml` and `uv.lock` are byte-identical to `871f440`; `application/`,
`domain/`, `infrastructure/` and `migrations/` are byte-identical to `c20827d`. No test
line was changed by the fix commit (`git diff 45137d9 108c5a0 -- tests` is empty).

Working tree, not part of the audited commit (noted, not edited): an uncommitted edit
of `specs/ingest-command/tasks.md` (§ Working state: the "Updated" line and a new entry
"PR #26 at `108c5a0` and its CI (2026-10-28, Revision 10 accounting)"). Its CI facts
agree with the CI logs read in this round (run ids, 2976 passed in 51.56 s, 98 %,
Linux, Python 3.13.18, uv 0.13.6, `certifi==2026.10.23`, `feedback` success; the
process tier's 68 dots are visible in the log as 30 plus 38). Its date, 2026-10-28, is
the UTC date of the CI run. Untracked: `docs/learning/day-20-handoff.md` and
`specs/ingest-command/.sdd/` (a feedback turn folder). `src/`, `tests/`,
`pyproject.toml`, `uv.lock`, `migrations/`, `README.md`, `docs/` and `CHANGELOG.md` in
the working tree equal `108c5a0` (`git diff --quiet 108c5a0 -- ...`). The commit was
audited from `git archive 108c5a0` copies in the session scratchpad (`p108`, pristine;
`w108`, the mutant copy), with `git archive 871f440` (`p871`) and `git archive c20827d`
(`p208`) copies for the regression matrix; each copy has its own `.venv`
(`uv sync --locked`).

The whole feature was audited again; nothing from rounds 1 to 7 was assumed to still
hold. Read in full at the commit: `interfaces/output_streams.py` (115 lines),
`interfaces/cli.py` (162), `interfaces/ingest_command.py` (422), the three specs (intent
Revision 15, plan Revision 13, tasks Revision 10), the round 1 to 7 history of
`audit.md`, README § Ingesting, `CHANGELOG.md` § Known limitations, the 34 new test
functions (86 items) and the harness of `tests/process/` (1215 lines). Read against the
state machines: `run_ingest`, `_close_remaining`, `_close_while_propagating`,
`_close_after_outcome` and `_ingest_through` (`application/ingest_use_case.py` lines
1232-1696) and the reporter call sites; the rest of that file is byte-identical to
`c20827d`, where round 6 read it in full, and its tests and tokens were re-run here.
`argparse` 3.14.9 (`C:\Program Files\Python314\Lib\argparse.py`) was read for every
caller of `_print_message` and `print_usage`.

Evidence labels:

- `rerun`: run by the auditor in this round on this machine (Windows 11, Python 3.14.9,
  uv 0.13.5). No Linux or Python 3.13 run was made locally.
- `reused`: a recorded result that is still current: the CI runs of PR #26 at
  `108c5a0` (`Tests` run 40617404828, `harny feedback` run 40617404826), whose logs
  were read in this round.
- `experiment`: a throwaway auditor script or mutant, run only in the session
  scratchpad on the `git archive` copies. Every child put the copy under test first on
  `PYTHONPATH` and logged the `ec_procurement_quality` it imported; a socket guard ends
  a child with 97, and any repository factory with 98 (never seen). No network, no
  database connection from any child, no real `data/raw/`, no `ingest` against real
  collaborators. The real console script was run only for `--version`, `--help`,
  `ingest --help`, usage errors and an unset `POSTGRES_DB`, which stop before anything
  is built.
- `unavailable`: could not be checked.

## Final verdict

APPROVED WITH RESERVATIONS

**Summary**: F-31 is closed. With `sys.stderr`, `sys.stdout` or both `None` (Python
started with descriptor 2, 1 or both closed: real `2>&-`, `>&-` and both, through the
real console script, through `cli.main` in a child, and with the real `run_ingest` over
the in-memory doubles), every invocation ends with the code of a working stream, nothing
meant for the missing stream is written anywhere, stdout carries only the one result line
(or nothing), no run is audited `unexpected-error` or closed `failed` because of it, and
no descriptor is redirected; D-11, D-12 and the D-5 adjustments are implemented as
written. No regression was found against `871f440` or `c20827d`: with working streams
all 26 cases are identical at the three heads, and with closed pipes `108c5a0` is
identical to `871f440` in all 78 cases (F-27 stays closed; F-28 and F-29 stay closed).
The suite passes completely (2976 passed, 0 skipped, with the database; CI green on Linux
at this head), and ruff, format, mypy and the doctor are clean. No class A finding is
open, on one condition stated in F-30 (the human's written confirmation of the `certifi`
update). What remains is class B and needs the human's written acceptance (closing
criterion, condition 4).

**Critical Issues** (must fix before merge):
- None (class A: none open). F-30 turns into class A only if the human does not confirm
  in writing that `b7d4770` was authorized.

**Warnings** (should fix, not blocking; class B reservations, each with its reason in
§ B):
- F-30 (LOW): `uv.lock` differs from `main` by the `certifi` 2026.10.23 security update;
  AC18's and AC20's literal "`uv.lock` unchanged" checks are stale; needs the human's
  written confirmation.
- F-33 (LOW): AC15's "nothing in PostgreSQL changes" read for a failing progress line
  contradicts the approved N-6 rule the code follows (a stderr that fails during a run
  closes the run `failed`); README silent.
- F-37 (LOW, new): `cli.py` lines 51 and 58 (a hook or `print_usage` call with no file)
  have no test; mutants (h), (h2) and H3 survive; no caller passes no file.
- F-38 (LOW, new): output-only missing-stream paths with no regression test (mutants
  listed in § Mutants), the code right in each by experiment.
- F-36 (LOW, carried): the surviving mutants (g), (n), O10, O13 (and C-k, its twin in the `except SystemExit` branch), O14, O15.
- F-12 (LOW, carried): stale "pending" and conditional text in the three specs (exact
  lines in answer 6).

**Recommendations** (nice to have; class B, accepted or fixed at the human's choice):
- F-32 (LOW): a Ctrl+C in the unguarded tail of `main` prints a traceback.
- F-34 (LOW): a run closed before its `run-started` cannot be resumed (AC24 by design).
- F-35 (LOW): `CHANGELOG.md` § Known limitations lacks the D-10 residual limitation.
- The optional improvements of § C.

Next role: the human, for the decisions of answer 6 (gate 3 is the human's; this report
does not close it); then the conductor records the accounting in `tasks.md` (§ Carried
reservations, § Working state) and, if the human chooses, the architect, the test-writer
or the documentation step for the optional items.

## A. Blocking defects (class A under the closing criterion)

None. Every item that round 7 or this round classified class A is closed or was never
class A:

- F-31 (MEDIUM, class A in round 7): **closed** (answer 1, § Resolution, the regression
  matrix).
- No new class A finding. In particular: no path writes to or reads from PostgreSQL
  because of a missing stream; a failing stream follows the approved rules unchanged;
  no observation or raw copy can be lost, duplicated, overwritten or corrupted by the
  change (`application`, `infrastructure` and the schema are byte-identical to
  `c20827d`); the stored run status and the printed status agree in every case of the
  matrix; no secret, URL, header or body reaches stdout or stderr; the ingest exclusion
  is untouched; every AC (AC1 to AC25) passes (F-30's literal `uv.lock` example aside,
  see F-30); every README promise of § Ingesting holds in a real process; and every
  plan-required path that touches data or run state has a test that fails when it is
  removed (the missing-stream paths that touch the run, N-6 for a missing reporter
  stream, are killed by the A1, A2 and R-4 mutants).
- Condition attached to this verdict: F-30 is class B only once the human confirms in
  writing that the `certifi` update of `b7d4770` was authorized (answer 6, decision
  D-G1). Without that confirmation it is an unapproved dependency change under
  `AGENTS.md` and an unmet AC18/AC20 example, class A, and the verdict for gate 3 would
  have to be read as REJECTED until the update is approved or reverted.

## B. Reservations (class B, each with the reason it stays acceptable)

Each needs the human's written acceptance at gate 3 (closing criterion, condition 4) and
an entry in `tasks.md` § Carried reservations, which the conductor keeps.

- **F-30** (LOW) `uv.lock` differs from `main` only by `certifi` 2026.7.22 -> 2026.10.23
  (`b7d4770`, GHSA-6q48-6c7w-9gw2). Reason: a security update of an existing transitive
  dependency, no package added, `pyproject.toml` unchanged against `main`,
  `uv audit --locked` clean, CI installs exactly that version; only the literal examples
  of AC18 ("`git diff main --stat -- uv.lock` is empty") and AC20 ("`uv.lock` is
  unchanged") are stale. Condition: the human's written confirmation (decision D-G1).
- **F-33** (LOW) AC15's last clause of the F-27 sentence ("... and nothing in
  PostgreSQL changes") read for a progress line contradicts the plan's outcome table row
  "Other stderr lines of the command ... during the run the use case's rules (an
  exception from the reporter; N-6)" and AC15's own N-6 sentence. Re-verified (mixed
  experiment M1-P2 and matrix P2, real `run_ingest` over the doubles): a stderr pipe
  closed from the start fails the run with `unexpected-error` (`OSError`, page 1) and
  closes it `failed` before its first request, at all three heads. Reason: the behavior
  is the approved N-6 rule, unchanged since `c20827d`; data stay consistent (nothing is
  lost: no page was requested, and a later run starts again); the conflict is spec
  wording. A strict reading of "an explicit AC unmet" could make it class A, which is
  why answer 6 recommends the one-sentence AC15 scoping (decision D-G3).
- **F-37** (LOW, new) `cli.py` line 51 (`_print_message` called with no file means
  `sys.stderr`) and line 58 (`print_usage` called with no file means `sys.stdout`) are
  not covered (locally and in CI); mutants (h), (h2) and H3 survive. Reason: no caller
  of the process passes no file. `argparse` 3.14.9 calls `_print_message` only with an
  explicit stream (`_VersionAction`, `print_usage`, `print_help`, `exit`, `_warning`)
  and `print_usage` only as `print_usage(_sys.stderr)` from `error`; the CLI calls
  `parser.print_usage(sys.stderr)`; CI on Python 3.13.18 shows the same two lines
  uncovered, so 3.13 does not call them without a file either. The code keeps
  `argparse`'s meaning (experiment: `parser._print_message("...")` writes on stderr and
  `parser.print_usage()` on stdout). Output only; no data or run state depends on it.
- **F-38** (LOW, new) Missing-stream output paths that the plan requires but no test
  pins: the surviving mutants R-2, R-5, R-6, R-8 and C9 of § Mutants. Reason: output only; each was
  verified by experiment at `108c5a0` (the matrix, `config_probe`): the handler's
  `<A> running` with a missing stdout is not written anywhere (matrix E1
  `ctrl-c-after-start`, `error-after-start`); the configuration message, the migration
  messages and the applied-migration names with a missing stderr are not written
  anywhere and keep 2, 2, 1 and the outcome (`config_probe`); the `AttributeError`
  suppression for a stream object without `write` keeps `argparse`'s 0 and 2
  (`inproc`). None of them touches the run.
- **F-36** (LOW, carried) Surviving mutants (g), (n), O10, O13 (and C-k, the same order
  swap in `main`'s `except SystemExit` branch), O14, O15 on output-only paths of the last
  flush and the protected write. Reason: the human left their tests
  out on 2026-10-27; the code behaves as planned (round 7 experiments E10, X-n; this
  round, the mutants survive again and the code is unchanged); no data or run state.
- **F-32** (LOW, carried) A Ctrl+C in the few unguarded bytecodes of `main` after
  `_code_of` returns (cli.py 154-162) escapes with a traceback. Reason: a single Ctrl+C
  at an exact instant after the result line was written; consequence a traceback (paths
  of the install, no secret) and the interpreter's exit code; no data or run state; pure
  Python cannot close every bytecode gap. `main` is unchanged since `871f440`.
- **F-34** (LOW, carried) A run closed before its `run-started` event (a reporter that
  fails at `run_started`, a Ctrl+C there, a refused append) cannot be resumed: `--resume`
  answers `invalid resumption chain <A>`, exit 1. Re-verified in process at `108c5a0`.
  Reason: AC24 makes such a chain malformed by design; such a run requested nothing, so
  nothing is lost; a fresh `ingest` of the scope does the same work (intent § Risks).
- **F-35** (LOW, carried) `CHANGELOG.md` § Known limitations, `ingest`, does not list
  the D-10 residual limitation (the README does, lines 296-300). Reason: documentation;
  the user-facing promise (README) states it; the CHANGELOG is the documentation step's
  (O11, `harny-document`) deliverable; no data or run state.
- **F-12** (LOW, carried) Stale accounting text (answer 6, D-G6, lists every line).
  Reason: accounting only; the Approval lines record the approvals.
- **Accepted earlier, still true** (to be listed again in § Carried reservations): the
  two F-20 limitations (`ingest_use_case.py` 388-389 and 598, uncovered locally and in
  CI), F-23 (D-2 option 1), the D-10 residual limitation (reproduced again this round
  with a real failing `os.dup2`), persistence U1 and N5, source-access U1.

## C. Optional improvements (no reservation needed)

- C-1: tests that kill the F-37, F-38 and F-36 survivors (one test-writer pass; the
  experiments of this report are templates).
- C-2: README: the bullet "If the command cannot write its result (for example, a
  closed output stream)" could say "a pipe whose reader has gone", so it does not read
  against the new bullet on a stream closed at start-up.
- C-3: README, Windows only: with `>&-` the uv console-script launcher itself writes
  `warning: Making stdout inheritable failed` on stderr before Python starts (seen at
  all three heads; not F4's output, not on stdout). A half-sentence could say so.
- C-4: `CHANGELOG.md`: one line for the D-12 behavior change (`--version` and `--help`
  with stdout closed at start-up now print nothing, where `argparse` alone printed them
  on stderr), with the F-35 line.
- C-5: the process harness's second kills by pid (cleanup step 4 after the launcher was
  killed, and step 5's survivor kill) run only after the cleanup already failed; on
  those paths a pid reused within the 5 to 10 s window could in theory be signalled. The
  normal timeout path kills the child while the launcher still holds it unreaped (no
  reuse possible) and the liveness checks only query. Probability negligible; a
  `pidfd` on Linux or a process handle on Windows would remove it.
- C-6: AC15 and README: say that a stderr that fails during a run ends the run `failed`
  (resumable when its `run-started` was written), the F-33 closure.

## Rounds 1 to 7 summary

- **Round 1** (`7603379`, REJECTED). 12 findings; F-01, F-02 (CRITICAL) and F-03
  (HIGH) blocked. Full report in git history at `7069f4c`.
- **Round 2** (`91bd69d`, REJECTED). F-01 to F-11 resolved; F-13, F-14 (MEDIUM)
  blocked; F-15 to F-17 LOW. Full report at `2f77b5e`.
- **Round 3** (`287946f`, REJECTED). F-13 to F-17 resolved; F-18 (HIGH) blocked;
  F-19, F-20 LOW. Full report at `fe0fb28`.
- **Round 4** (`10e126d`, REJECTED). F-18, F-19 resolved for the named calls; F-21
  (MEDIUM) blocked; F-22 LOW. Full report at `25d1253`.
- **Round 5** (`80c8aab`, APPROVED WITH RESERVATIONS). F-20 to F-22 resolved; N-1 to
  N-11 held; new, all LOW: F-23 to F-26; F-12 carried. Full report at `5574cd6`.
- **Round 6** (`c20827d`, REJECTED). F-23 to F-26 resolved (D-1 to D-5). New: F-27
  (MEDIUM, blocking: a real closed stdout pipe gave Python's exit 120), F-28, F-29 LOW;
  F-12 carried. Full report at `0cebf11`
  (`git show 0cebf11:specs/ingest-command/audit.md`).
- **Round 7** (`871f440`, REJECTED). F-27, F-28, F-29 resolved; D-6 to D-10 held
  (D-10's residual reproduced for real). New: F-31 (MEDIUM, class A, blocking: a `None`
  stderr wrote stderr text on stdout and failed every run), F-30 and F-32 to F-36 LOW,
  class B; F-12 carried. The full round 7 text is in git history at `f9a0566`
  (`git show f9a0566:specs/ingest-command/audit.md`). The human chose D-11 and D-12
  option A, accepted the D-5 adjustments and the process-tier exceptions with the
  cleanup requirement, and approved intent 15, plan 13 and tasks 10 (2026-10-27).

## Resolution of the earlier findings

| Id | Earlier severity | Status | Evidence (this round) |
|---|---|---|---|
| F-01, F-02 | CRITICAL | Resolved (still) | `application` byte-identical to `c20827d`; `pending_sequence` set at 1508 and cleared at 1536, 1556, 1582, 1598 (read); `interrupt or exit_code` 417 passed (rerun); in the matrix a stderr that fails at the first page's line (P2, real `run_ingest`) still records the pending observation through K before `unexpected-error` (no observation lost) |
| F-03 | HIGH | Resolved (still) | `_invoke` builds the source before `_migrate`; `source_configuration or order_of_invocation` 30 passed (rerun); with a missing stderr the configuration error still returns 2 (`config_probe`, experiment) |
| F-04 | MEDIUM | Resolved (still) | `_print_running` through `_end_after_escape`; matrix W, E2 `ctrl-c-after-start` -> 130, stdout `<A> running` (experiment) |
| F-05 to F-11, F-13 to F-15, F-17 to F-22 | various | Resolved (still) | Use-case code unchanged; tokens `storage` 24, `database_refusal` 57, `connection_loss` 43, `reconcile` 34, `chain` 197, `execution_id or identity` 94, `refusal_not_retried` 37 (rerun, `tests/unit`) |
| F-16 | LOW | Resolved (still) | `result_written` set in `_report` (265) before either write and in `_print_running` (279); one result line in every matrix cell |
| F-20 | LOW | Accepted limitation (unchanged) | Coverage misses exactly 388-389 and 598 of `ingest_use_case.py` (rerun and CI) |
| F-23 | LOW (spec decision) | Resolved (decided D-2, kept) | `refusal_then_interrupt` 42 passed (rerun) |
| F-24 | LOW (spec decision) | Resolved | `system_exit` 88 passed (rerun); D-1 holds with missing streams (matrix `system-exit-after-start`, `source-close-system-exit`, `wiring-system-exit`: 3, 3 and 4 in every mode) |
| F-25 | LOW | Resolved | Unchanged code; tests pass (rerun) |
| F-26 | LOW | Resolved (still) | `main_parse_interrupt` 6, `main_wiring_interrupt` 3, `main_error_stream_fault` 27, `main_help_stream_fault` 31 (rerun); see F-32 for the tail of `main` |
| F-27 | MEDIUM | **Resolved (still)** | Answer 2. Closed pipes: `108c5a0` identical to `871f440` in all 78 matrix cells and in all 24 console-script cells; never 120, no `Exception ignored`, at most one `dup2` per descriptor; process tier 68 passed (rerun, Windows; CI on Linux reused) |
| F-28 | LOW | **Resolved (still)** | `main_handler_line_fault` 12, `system_exit_first_wins` 4, `window_system_exit_line` 2, `cleanup_system_exit` 9 (rerun); the code they pin is unchanged |
| F-29 | LOW | **Resolved (still)** | `-k "usage or environment"` 66, `-k main_error_stream_fault` 27 (rerun, `tests/unit/ingest`); no new test name carries a forbidden token (34 new functions checked) |
| F-31 | MEDIUM, class A | **Resolved** | Answer 1: closure condition met (the architect decided D-11 and D-12, recorded in intent AC14/AC15 and plan "A missing stream"; the protected write never writes a stderr text on stdout; the `argparse` fallbacks adjusted under D-5; unit tests and a process-tier case exist; the README sentence is there). `absent_` 44 and `process_no_` 40 passed (rerun; CI reused); the console script and `cli.main` children with real `2>&-`, `>&-` and both; the real `run_ingest` with `2>&-` ends `succeeded`, 0, one stdout line |
| F-30, F-32 to F-36, F-12 | LOW | Open (class B; § B) | Re-verified at `108c5a0` (§ Findings) |

## Findings

Class is the human's closing criterion of 2026-10-23 (`docs/learning/day-20-handoff.md`
§ 3): class A blocks gate 3 at any severity; class B may stay as a reservation the human
accepts in writing.

| Id | Severity | Class | AC / constraint | Finding and evidence | Failure scenario | Closure condition | Status |
|---|---|---|---|---|---|---|---|
| F-31 | MEDIUM | A (round 7) | AC14, AC15; README § Ingesting ("stdout holds a single result line"); plan "A missing stream", "D-5 as adjusted" | `output_streams`: `neutralize`, `_written_and_flushed` (so `write_line` and `write_text`) and `_flushed_for_exit` return at once for `None`; `_CliParser._print_message` writes only when its stream is not `None` (no file means `sys.stderr`); `_CliParser.print_usage` keeps an explicit `None` missing (no file means `sys.stdout`). Real processes (answer 1): every case ends with the working-stream code, nothing on the other stream, no `dup2`; the real `run_ingest` with `2>&-` ends `succeeded` with exit 0 and stdout exactly `<A> succeeded` | (none left) | Met (answer 1) | **Resolved** |
| F-30 | LOW | B if the human confirms in writing that `b7d4770` was authorized; otherwise A | AC18 ("`git diff main --stat -- uv.lock` is empty"); AC20 ("`uv.lock` is unchanged"); plan § Ownership and § Other constraints ("`uv.lock` is unchanged"); `AGENTS.md` (approval before dependency changes) | `git diff main 108c5a0 -- uv.lock`: `certifi` 2026.7.22 -> 2026.10.23 only (version, sdist and wheel hashes), from `b7d4770` (author Vladimirjon; message: emSign roots, GHSA-6q48-6c7w-9gw2). `pyproject.toml` equals `main`. `uv audit --locked`: "Found no known vulnerabilities and no adverse project statuses in 24 packages" (rerun). CI installs `certifi==2026.10.23` (reused). No spec, `tasks.md` line or decision records the approval; Revision 15 left F-30 unanswered | A reader runs AC18's or AC20's literal check and finds it false | The human writes the confirmation (answer 6, D-G1), and the architect amends AC18's and AC20's examples (and plan § Ownership, § Other constraints) to "differs from `main` only by the `certifi` security update of `b7d4770`"; or the update is reverted | Open |
| F-33 | LOW | B (spec wording; behavior is the approved N-6 rule) | AC15 (Revision 14 F-27 sentence, "... and nothing in PostgreSQL changes"); plan outcome table, row "Other stderr lines of the command"; README § Ingesting | Unchanged since round 7. Matrix P2 and mixed M1-P2 (real `run_ingest`, stderr a closed pipe, or stdout missing and stderr a closed pipe): exit 1, run `failed`, one `unexpected-error` (`OSError`, page 1), no request; identical at `871f440` and `c20827d` (exit 120 there). With a missing stderr this no longer happens (F-31 closed) | A reader of AC15 or of the README expects a stderr pipe that dies to leave the run alone | The architect scopes AC15's clause to the result writes and points to N-6 for progress lines; optionally a README sentence (C-6) | Open |
| F-37 | LOW | B (output only; no caller passes no file) | Plan "D-5 as adjusted" (a), (b): "a call without a file still means `sys.stderr`" / "`sys.stdout`, as in `argparse`"; plan § Risks row (Revision 13) | Coverage misses `cli.py` 51 and 58 (rerun; CI reused). Mutants (h) (no file writes nothing), (h2) (`print_usage()` writes nothing) and H3 (no file means stdout) survive (§ Mutants). `argparse` never calls either method without a stream (read, 3.14.9; CI 3.13.18 coverage agrees). Experiment `inproc`: `parser._print_message("no-file-hook\n")` writes on stderr, `parser.print_usage()` on stdout | A later change breaks `argparse`'s default meaning and no test fails; only a third-party direct call would notice | Two unit tests (one per line), or the human accepts the reservation | Open |
| F-38 | LOW | B (output only; verified by experiment; no data or run state) | Plan "A missing stream" and its table (the handler's `<A> running`; the configuration message; migration names; the command's other stderr lines), "D-5 as adjusted" (c) | Surviving mutants listed in § Mutants under F-38: each sends a text meant for a missing stream to the other one, or lets the `AttributeError` of a stream object without `write` through, and no test fails. The code is right in each (matrix E1 rows for `<A> running`; `config_probe` for the configuration message, migration error, lock, connection and applied names with a missing stderr; `inproc` for a stream without `write`) | A later change reintroduces a stdout contamination on one of these rarer paths with a missing stream, and no test fails | Unit tests for the surviving cases (C-1), or the human accepts the reservation | Open |
| F-36 | LOW | B (output-only paths, behavior verified by experiments) | Plan "Protected writes and the last flush" | (g), (n), O10, O13 (on `main`'s own exit, and C-k in its `except SystemExit`), O14, O15 survive again (§ Mutants). The code is unchanged since `871f440`, where round 7's E10 and X-n showed the planned behavior | A later change reintroduces one of these behaviors and no test fails | Unit tests that kill them (the human left them out on 2026-10-27), or the human accepts the reservation | Open |
| F-32 | LOW | B (a single Ctrl+C at an exact bytecode instant; a traceback, no data or run state) | Plan "The handler of `main`" ("on an interrupt that lands between the command's return and `main`'s `raise SystemExit(code)`"); AC15 ("nothing prints a traceback") | `main` (cli.py 154-162) is unchanged since `871f440`: only the two `stream.flush()` calls inside `_flushed_for_exit` are guarded; the assignment of `code`, the call of `flush_for_exit`, the `isinstance` check and the final `raise` are outside any `KeyboardInterrupt` handler. Round 7's E15 applies unchanged | A Ctrl+C at that instant prints a traceback and Windows' 0xC000013A instead of 130 | A handler around `main`'s tail, or the human accepts it with the other bytecode gaps | Open (recommendation) |
| F-34 | LOW | B (AC24 by design; such a run requested nothing) | AC24, AC9; README ("A failed run is resumed with its execution id") | `run_ingest` calls `reporter.run_started(id)` (1450) before the `run-started` append (1460-1469). Re-run in process at `108c5a0` (`resume_probe`): a reporter whose `run_started` raises `OSError` -> `RUN_FAILED`, events `['unexpected-error']`, 0 requests; `--resume` of it -> `NOT_STARTED`, `invalid resumption chain <A>` | The operator follows the README and is told the chain is invalid | A README sentence or a clearer message, or the human accepts it | Open (recommendation) |
| F-35 | LOW | B (documentation; the README states the limitation) | AC21 ("`CHANGELOG.md` § Unreleased lists ... the known limitations") | `CHANGELOG.md` lines 200-222 (`ingest` limitations) do not mention the D-10 residual limitation (README lines 296-300 do), nor the F-34 case of intent § Risks | A release-note reader does not see them | One bullet each at the documentation step (O11), or the human accepts it | Open (recommendation) |
| F-12 | LOW | B (accounting and stale spec text) | harny-audit step 4; plan § Rollout | Answer 6 (D-G6) lists the exact lines at `108c5a0` | The next role reads that approved specs are pending | Each listed line says approved on its date, or is marked historical; § Carried reservations names 388-389 and 598 | Open |

## Regression matrix

Inputs, the same at the three heads (`108c5a0`, `871f440`, `c20827d`), each run in a
child with the copy under test on `PYTHONPATH` and genuine `sys.stdout` and `sys.stderr`
(no recording stream), Windows, Python 3.14.9 (experiment): 26 cases (`--version`,
`--help`, `ingest --help`, the bare command, a parse error, `--bogus`,
`--resume Synthetic_Id`, `POSTGRES_DB` unset, a stub `run_ingest` returning
`SUCCEEDED` announced and unannounced, `RUN_FAILED` with `failed` and with `running`,
`INTERRUPTED`, `INVALID_TARGET`, `NOT_STARTED`, raising `KeyboardInterrupt`,
`LookupError` or `SystemExit(3)` after `run_started`, a source close raising
`SystemExit(3)`, `default_wiring` raising `KeyboardInterrupt`, `MemoryError` or
`SystemExit(4)`, the real `run_ingest` over the in-memory doubles of
`tests/unit/ingest/conftest.py` for the AC1, AC4 (page 2 `500`) and AC7 (Ctrl+C at page
2) runs, and a D-10 case whose `os.dup2` really fails with `EBADF`) in 7 stream modes:
working (W); real `2>&-` (E2), `>&-` (E1), both (E12) through Git Bash; and a pipe whose
reader closed before the child wrote, for stdout (P1), stderr (P2) or both (P12), with
the plan's go-byte pattern. 546 child runs. Plus the real console script of each copy
(8 cases that build nothing x 7 modes x 3 heads = 168 runs) and a mixed set (one stream
missing at start-up, the other a closed pipe; 5 cases x 2 x 3 = 30 runs).

| Mode | `108c5a0` against `871f440` | `108c5a0` against `c20827d` | `108c5a0` against the plan |
|---|---|---|---|
| W (working streams) | identical in 26 of 26 (code, stdout, stderr, stored run, no `dup2`) | identical in 26 of 26 | matches § Exit codes and § Output |
| P1, P2, P12 (closed pipes, F-27) | identical in 78 of 78 | `c20827d` ends 120 in 62 cells (`Exception ignored ... flushing sys.stdout` for stdout); identical in the other 16 | matches the outcome table: 1, 130 or the `SystemExit` code; at most one `dup2` per descriptor; never 120 except the D-10 case (below) |
| E2, E1, E12 (missing streams, F-31) | differs in 40 of 78, every difference an F-31 or D-12 defect of `871f440` (stderr text and `AttributeError` on stdout; 1 instead of 0, 2, 130 or 3; the real run closed `failed` with `unexpected-error`; `--version` and `--help` text on stderr) | differs in 25 of 78 (`c20827d` wrote stderr text and usages on stdout with `2>&-`, and `--version`/`--help` on stderr with `>&-`) | matches the plan's "A missing stream" table in all 78 cells |
| Console script E1, E2, E12 | `108c5a0`: usage errors 2 with stdout empty (`871f440` and `c20827d`: the usage on stdout); unset `POSTGRES_DB` 2 with stdout empty (`871f440`: 1 with two stdout lines; `c20827d`: 2 with the error on stdout); `--version`, `--help`, `ingest --help` with `>&-` print nothing (both older heads: the text on stderr) | as left | matches; the uv launcher's own `warning: Making stdout inheritable failed` on stderr with `>&-` is identical at the three heads (C-3) |
| Console script P1, P2, P12 | identical in 24 of 24 | `c20827d` 120 in 16 | matches (1 with `unexpected error: OSError`, 2, or 1) |
| Mixed (M2-P1: `2>&-` and stdout a closed pipe; M1-P2: `>&-` and stderr a closed pipe) | differs only where `871f440` hit F-31 or D-12 (`ctrl-c-after-start` 130 against 1; parse error 2 against 1; the real run `succeeded` against `failed`; `--version` with `>&-` 0 against 1) | `c20827d` 120 in every cell | matches: the existing failing stream follows the outcome table, the missing one adds nothing |

Selected cells (`108c5a0`; stored run in brackets):

| Case | W | E2 (`2>&-`) | E1 (`>&-`) | E12 | P1 | P2 |
|---|---|---|---|---|---|---|
| real `run_ingest`, AC1 | 0, `<A> succeeded` (succeeded) | 0, `<A> succeeded` (succeeded, no `unexpected-error`) | 0, nothing on stdout, progress on stderr (succeeded) | 0 (succeeded) | 1, progress on stderr (succeeded) | 1, `<A> failed` (failed, `unexpected-error` OSError: F-33) |
| real `run_ingest`, AC4 | 1, `<A> failed` | 1, `<A> failed` | 1 | 1 | 1 | 1 |
| real `run_ingest`, AC7 | 130, `<A> failed` | 130, `<A> failed` | 130 | 130 | 130 | 1 (F-33 path) |
| unset `POSTGRES_DB` | 2, stderr `error: POSTGRES_DB is not set` | 2, stdout empty | 2, the line on stderr | 2 | 2 | 1 (D-4) |
| `--version` | 0 | 0, the text on stdout | 0, nothing anywhere | 0 | 1, `unexpected error: OSError` | 0 |
| `ctrl-c-after-start` | 130, `<A> running` | 130, `<A> running` | 130, stderr `interrupted` | 130 | 130 | 1 |
| `system-exit-after-start` | 3, stdout empty | 3 | 3 | 3 | 3 | 1 |
| D-10 (real `EBADF` from `os.dup2`) | 0 | 0, no `dup2` | 0, no `dup2` | 0 | **120** and `Exception ignored while flushing sys.stdout: OSError: [Errno 22]`, one `dup2` (D-10 residual) | **120**, stdout `<A> running`, one `dup2` |

The D-10 rows reproduce the stated residual limitation for real at `108c5a0` and
`c20827d` alike (with no neutralizing at `c20827d`); `main` raised its agreed code (1 in
the child's log) and made no second attempt; only Python's finalization replaced it.

## Answers to the round 8 questions

**1. Is F-31 closed, and are D-11, D-12 and the D-5 adjustments implemented exactly as
the plan says?** Yes, on Windows (rerun, experiment) and, for the process tier, on Linux
(CI, reused).

- Every place a stream is used, with `None` (experiment `inproc`, matrix, unit tests):
  - `write_line(None, ...)` and `write_text(None, ...)` return before `print`, write
    nothing anywhere and raise nothing (`output_streams.py` 60-61; `print(file=None)`
    is never reached); `neutralize(None)` returns before the once-per-stream record and
    before `fileno()`, `os.open` or `os.dup2` (37-38); `_flushed_for_exit(None)` returns
    `None`, so `flush_for_exit` skips a missing stream and it masks nothing (91-92;
    `absent_stream_helpers`, both orders, a `KeyboardInterrupt` and a `SystemExit(4)`
    from the other stream come back as the same object).
  - `_CliParser._print_message` writes only when `message` and the stream exist; a call
    with no file means `sys.stderr` (line 51; F-37). `_CliParser.print_usage` keeps an
    explicit `None` missing and means `sys.stdout` with no file (line 58), and writes
    `format_usage()` through the hook. `argparse`'s own paths: `error()` ->
    `print_usage(_sys.stderr)` -> the override -> nothing; `exit(2, msg)` ->
    `_print_message(msg, _sys.stderr)` -> nothing; `_VersionAction` ->
    `_print_message(text, _sys.stdout)`; `_HelpAction` -> `print_help()` ->
    `_print_message(text, None)` when stdout is missing -> nothing. The bare command
    calls `parser.print_usage(sys.stderr)`. Console script and children: usage errors,
    `--bogus`, `--resume Synthetic_Id` and the bare command exit 2 with stdout empty
    under `2>&-`; `--version`, `--help` and `ingest --help` exit 0 with their text on
    stdout under `2>&-` and with nothing anywhere under `>&-`; both closed: 0 or 2,
    nothing written.
  - `_StderrReporter.run_started` and `progress` with a missing stderr raise nothing, so
    the use case's N-6 rules never fire: the real `run_ingest` with `2>&-` ends
    `succeeded` (AC1), `failed` (AC4) and `failed` after Ctrl+C (AC7) exactly as with a
    working stderr, events `run-started`, `page-completed`, ... and no
    `unexpected-error`, stdout exactly one line. N-6 still fires on a real failure (a
    stderr pipe closed: F-33), so it depends only on real failures.
  - The result line with a missing stdout: `_report` sets `result_written` first, the
    write returns, `_settled_code` sees no failure, so the exit code is the outcome's
    (0, 1, 130, 2 for `INVALID_TARGET`), D-12 option A; nothing on stderr in its place.
    The handler's `<A> running` with a missing stdout: 130 or 1, nothing anywhere (matrix
    E1 `ctrl-c-after-start`, `error-after-start`).
  - The handler line of `main` and `_code_after_writing` with a missing stderr:
    `default_wiring` raising `KeyboardInterrupt` -> 130, `MemoryError` -> 1,
    `SystemExit(4)` -> 4, nothing on stdout (matrix `wiring-*`; `absent_stderr_main`).
  - A falsy but existing stream (a `StringIO` whose `__bool__` is false) is written to,
    as an existing stream must be (`argparse`'s `file or sys.stderr` is not used any
    more). A stream object without `write` (plain and weak-referenceable): `--version`
    0, a parse error 2, the bare command 2, nothing elsewhere (the `AttributeError` is
    suppressed by the hook, D-5 (c)). `sys.stdout` replaced by `None` while the run is
    in progress: the result line still goes to the stream the command was given, the last
    flush skips `None`, exit 0.
  - With working streams nothing changed (the W column of the matrix, `tests/unit/test_cli.py`
    unedited and passing, CLI-1 to CLI-3).
- D-11: implemented as written (protected write, neutralizing, record, last flush,
  parser, handler). D-12: implemented as written (result line, `--version`, `--help`,
  `ingest --help` not written, no substitute stream, the command's own code). D-5
  adjustments: (a) lines 49-54; (b) lines 56-59; (c) `suppress(AttributeError)` only
  around a stream that is not `None`; (d) the class overrides exactly `_print_message`
  and `print_usage` (`_IngestParser` keeps its earlier `parse_known_args` for the
  `request_from_arguments` rules, a subclass the plan allows), `argparse` is not patched
  (`assert_argparse_is_standard` checks both methods after `build_parser()`), and the
  D-5 tests (`main_error_stream_fault` 27, `main_help_stream_fault` 31) still pass.
- stdout rule of AC14 and AC15 and README "stdout holds a single result line": holds in
  every matrix cell with a missing stream (one line or nothing).
- One observation outside F4 (C-3): on Windows, with `>&-`, the uv console-script
  launcher prints `warning: Making stdout inheritable failed` on stderr before Python
  starts; identical at the three heads; not stdout, not an F4 text.

**2. Regressions against `871f440` and `c20827d`?** None (the regression matrix). With
working streams all 26 cases are identical at the three heads (codes, stdout, stderr,
stored run). With closed pipes `108c5a0` equals `871f440` in all 78 matrix cells, all 24
console-script cells and the mixed cells that do not involve F-31: exit 1, 130 or the
`SystemExit`'s code, at most one `dup2` per descriptor, no `Exception ignored`, no 120
(except the D-10 case with a real failing `os.dup2`, the stated residual). F-27 stays
closed in real processes; F-28 and F-29 stay closed (their tests pass, their code is
unchanged). The D-6 to D-10 machinery is unchanged except for the `None` guards; the
handler of `main` and the last flush are unchanged except for the `None` skip; AC1 to
AC25 pass; the README changed by one sentence, which matches the behavior.

**3. Anything written to or read from PostgreSQL because of an output failure beyond the
plan (N-6)?** No. A missing stream causes nothing in PostgreSQL (the stored runs of the
E columns equal the W column). A failing result write touches nothing (P1: the AC1 run
stays `succeeded` with its events). A failing stderr during the run follows N-6
(`unexpected-error`, `failed`), as the plan's outcome table says (F-33 is the wording
conflict). No change to `application`, `domain`, `infrastructure`, `migrations/` or the
schema since `c20827d`; the 266 integration tests pass with the database (rerun).

**4. Is the test suite itself sound?**
- No flakiness seen: the process tier passed in both full suites, in its own run (68
  passed, about 58 s), in the five token selections and in the mutant baseline, and in
  CI on Linux (reused); under the 41 mutants it failed only on the tests each mutant
  targets. Its synchronization uses
  no sleep; the launcher's timeout (50 s) is strictly shorter than the parent's (60 s),
  asserted before each launch; liveness is polled until a deadline.
- No process left behind: no `python.exe` before or after the runs (`tasklist`); no
  `ecpq_test_` database left (count 0 inside the container); the real `data/raw/`
  holds 0 files before and after.
- The cleanup rule of the plan is met line by line (`clean_up_after_timeout`: pid file,
  kill the child by pid while the launcher still holds it, kill the launcher, a bounded
  reaping `communicate`, kill again and record on its timeout, poll liveness, kill and
  name a survivor, then `pytest.fail`), and the harness mutants HX-1, HX-2 and HX-3 are
  killed (§ Mutants). `ctypes` is used only to query (`OpenProcess` with
  `PROCESS_QUERY_LIMITED_INFORMATION`, `GetExitCodeProcess`, `CloseHandle`); `os.kill`
  targets only the launcher's child pid and the launcher. On the normal paths neither
  can reach an unrelated process; the residual pid-reuse window on two failure-only
  paths is C-5.
- Token rule: none of the 34 new test functions carries `usage`, `output`,
  `environment`, `interrupt`, `connection_loss`, `storage`, `final_close_`,
  `reconnect_`, `stream_fault`, `exit_code`, `system_exit`, `process_closed_`,
  `process_working_` or another AC token; `-k "usage or environment"` 66,
  `-k main_error_stream_fault` 27, and the broad selections did not grow
  (`interrupt or exit_code` 417, `output or logger` 93, `system_exit` 88) (rerun).
- No test was edited to pass: `git diff 45137d9 108c5a0 -- tests` is empty; the
  test-writer's commit removed no assertion (the 18 removed lines of the process file
  are the bootstrap's unconditional stdout replacement and bare `cli.main(ARGV)`, both
  now guarded, and `run_child`'s inline environment, moved into `child_environment()`;
  the one removed line of the unit file is the import widened to `output_streams`);
  against `main` the only removed test lines are a docstring line and two import lines.
  The new tests are red for the planned reasons at `871f440` (§ Mutants, last
  paragraph).
- No network (socket guards, `.invalid` hosts), temporary paths only (`tmp_path`), both
  platform branches present (CI exercised the POSIX branch of the liveness helper and the
  launcher on Linux).

**5. The four conditions of the closing criterion.**
1. No class A finding open: **holds, with one condition**. F-31 is closed and no new
   class A was found. F-30 is class B only once the human confirms the `certifi` update
   in writing (D-G1). F-33 is class B on this report's reading; a strict reading of
   AC15 could call it class A, which D-G3 removes.
2. Suite, CI, ruff, mypy, doctor: **holds**. 2976 passed, 0 skipped with the database
   (rerun, Windows, Python 3.14.9); `Tests` run 40617404828 on `108c5a0`: 2976 passed,
   98 %, Linux, Python 3.13.18 (reused); ruff, ruff format (123 files), mypy (54
   files) and the doctor (31 ok, 0 skipped, 0 warned, 0 failed) clean (rerun).
3. The latest audit audits that head with APPROVED or APPROVED WITH RESERVATIONS:
   **holds for `108c5a0`** with this report. It stops holding when the PR head moves
   (the uncommitted `tasks.md` edit, or any F-12, F-30, F-33 or F-35 edit, makes a new
   head): see D-G7.
4. Reservations written with their reason in `audit.md` and `tasks.md` § Carried
   reservations, and accepted in writing: **does not hold yet**. They are written here
   (§ B, § Reservations carried forward); `tasks.md` § Carried reservations holds only
   the earlier N2, R-6, R-7, R-11, U1, F-20 and D-10 entries; the human has accepted
   none of F-30 and F-32 to F-38 in writing.

**6. Consolidated list of the decisions the human still must take to close gate 3.**

| Id | Decision | Options | Recommendation | Settles |
|---|---|---|---|---|
| D-G1 | Confirm in writing that the `certifi` update `b7d4770` was authorized | (a) write, for example: "Confirmo que la actualización de `certifi` 2026.7.22 -> 2026.10.23 del commit `b7d4770` fue mía y autorizada (seguridad, GHSA-6q48-6c7w-9gw2); acepto F-30 como reserva de clase B y pido que AC18 y AC20 se ajusten a esa diferencia"; (b) revert `b7d4770` (the lock returns to the vulnerable bundle) | (a); then the architect amends the AC18 and AC20 examples and plan § Ownership and § Other constraints (spec-only) | F-30; condition 1 |
| D-G2 | Accept in writing each class B reservation that is not fixed | per item: accept, or order the fix: F-32, F-33, F-34, F-35, F-36, F-37, F-38, F-12; and restate the earlier accepted F-20 (388-389, 598), F-23 (D-2), D-10 residual, persistence U1 and N5, source-access U1 | accept F-32, F-34, F-36, F-37, F-38 (output-only or by design; no data); fix F-33, F-35 and F-12, which are one-line spec or documentation edits (D-G3, D-G5, D-G6) or accept them too | condition 4 |
| D-G3 | F-33: AC15's "nothing in PostgreSQL changes" against N-6 | (a) the architect scopes the clause to the result writes and points to N-6 for progress lines (spec-only), optionally a README sentence (C-6); (b) accept as reservation | (a) | F-33; removes the strict-reading risk to condition 1 |
| D-G4 | Commission the optional test-writer pass | (a) tests for F-37 (two), F-38 (the surviving mutants of § Mutants) and F-36 ((g), (n), O10, O13, O14, O15), regression only, no product change; it needs plan rows, red or green evidence and a new head; (b) accept them as reservations | (b) for gate 3 (no data or run state; behavior verified); (a) later if the human wants no output-path gaps | F-36, F-37, F-38 |
| D-G5 | F-35: the `CHANGELOG.md` lines | (a) add the D-10 residual limitation (and optionally the F-34 case and the D-12 behavior change, C-4) at the documentation step O11 (block B); (b) add them now; (c) accept | (a), recorded as a reservation until O11 | F-35 |
| D-G6 | F-12 accounting pass | (a) the architect or the conductor marks as approved or historical: intent lines 423, 442, 552, 558 (and the historical "Pending" in 512, 517, 525, 531, 540); plan line 5, headings 1009 and 1017 with their "Nothing is implemented before the human approves this revision" (1010, 1018), the conditionals "required once the revision is approved" at 294, 368, 375, 381, 390, 401, 454 and 1231, and the Revision log "Pending" entries (1269, 1274, 1284, 1291, 1300, 1314, 1321); `tasks.md` line 5 ("Revision 15 (pending)", "Revision 13 (pending)"), § Status lines 15-16 (both "pending the human's approval") and its spec list that opens with Revisions 11/9/6, O10 lines 358 and 364-365 ("pending", "Nothing is implemented before the approval"), § Finding responses rows F-27, F-28, F-29 (521-523) and F-31 (525) ("Architect proposal ..., pending approval"), § Carried reservations F-20 (391: lines 475/535 and 285-286/317-318 of old heads; now 598 and 388-389), § Working state round 7 green (464 (e), "The code is uncommitted") superseded by the uncommitted entry; and record whether the human authorized the commit and push of `45137d9` and `108c5a0` (no committed line says so); (b) accept as reservation | (a), together with the uncommitted `tasks.md` entry | F-12 |
| D-G7 | Which head gate 3 closes on | (a) the human states in writing that a follow-up commit limited to `specs/` (and `docs/learning/`) keeps this audit valid, with a recorded check that `git diff 108c5a0 <head> -- src tests pyproject.toml uv.lock migrations README.md CHANGELOG.md` is empty and CI is green on that head; (b) a short audit round 9 on the final head | (a) if only specs and the journal change; (b) if the README or the CHANGELOG change (C-2, C-3, C-4, F-35) | condition 3 |
| D-G8 | The optional README and CHANGELOG improvements C-2, C-3, C-4, C-6 | adopt any, or none | C-2 and C-6 with D-G3; C-3 optional; C-4 with D-G5 | (none required) |
| D-G9 | Gate 3 itself, then the merge of PR #26, the archive (O11, `harny-sync`) and the Day 20 live ingest | the human's | after D-G1, D-G2 and D-G7 | gate 3 |

What the documentation step (block B, O11) still needs: the `CHANGELOG.md` lines of
D-G5; the `harny-sync` updates at archive (the `cli` capability with the handler of
`main`, the protected writes, the missing-stream rule of D-11 and D-12, and the D-10
residual limitation stated as a limitation; `persistence` PS-4, PS-7, PS-13 and
Invariant 8; `raw-evidence` RE-12 and Invariant 7; `project-toolchain` PT-6 and PT-10
counts and the F-1 note; the new `ingestion` capability); `tasks.md` § Carried
reservations with every reservation the human accepts; the human's journal entry.

**7. What could not be verified.** Linux and Python 3.13 locally (`unavailable`; the
only evidence there is CI at `108c5a0`, which ran the 68 process tests, the POSIX
liveness branch and the launcher); `sys.stdout`/`sys.stderr` `None` on Linux through a
real shell `2>&-` (only through the launcher in CI, with the start-state record); a
console Ctrl+C (`CTRL_C_EVENT`) at the bytecode gaps of F-32 (not sent); a real full
disk; anything live against SERCOP, the real `data/raw/` or the configured database
(out of scope; never run); the 3.13 `argparse` source (only CI's behavior and coverage);
that the per-turn feedback hook fired during the executor's and the test-writer's turns
(turn files are not kept); who authorized `b7d4770` and the commit and push of the round
7 rework (F-30, F-12). Outside F4 and not a finding: on POSIX a descriptor closed at
start-up can be reused by the next `open` (Windows returned descriptor 3 in a probe, no
reuse); the command writes nothing to a missing stream's descriptor, and a stray write by
a C library into a reused descriptor would be caught by RE-7's hash check on read.

## Executor and test-writer choices where the plan was silent

| Choice | Assessment |
|---|---|
| (1) The "no file given" sentinel is a module-level `_NO_FILE: Any = object()` | Conformant |
| (2) `_print_message` and `print_usage` keep `file: Any` | Conformant; mypy clean |
| (3) A falsy but non-`None` file is written to (only `None` is missing) | Conformant with "a stream is missing when it is `None`"; experiment `inproc` |
| (4) `print_usage` goes through the hook (and its `AttributeError` suppression) | Conformant with D-5 (b) |
| (5) Explicit `None` guards in `neutralize`, `_written_and_flushed`, `_flushed_for_exit`, and `file is not None` in the hook, redundant in effect | Conformant; the mutants that remove them (A3, A4, C-a) survive as equivalents (§ Mutants) |
| (6) All 11 `stdout`/`stderr` annotations of `ingest_command.py` widened to `TextIO \| None` | Conformant (the plan's suggestion, slightly wider) |
| (7) The README sentence is its own bullet after the D-10 bullet | Conformant; C-2 for the wording next to it |
| Test-writer: `ABSENT = typing.cast(typing.TextIO, None)`; a `capfd` rig for both missing streams | Conformant with the seams row |
| Test-writer: the launcher's own failures end 94 (a code it cannot relay) or 95 (an exception, traceback into `child.pid.error`), added to `NEVER_A_RESULT` | Stricter than the plan's "96 joins 97 and 98"; harmless |
| Test-writer: `-` as the launcher's descriptor list when nothing is closed; `stall` as the test-only switch | Within the plan |
| Test-writer: a positive control of the liveness helper (`process_is_alive(os.getpid())`) | Good practice; it kills HX-3 |

## Accepted limitations

- F-20 (accepted on 2026-10-18): lines 388-389 and 598 of `ingest_use_case.py` have no
  test; coverage misses exactly these lines locally and in CI.
- F-23 (decided in D-2, option 1): kept and pinned (`refusal_then_interrupt` 42).
- D-10 (option A, chosen by the human): a neutralizing that fails may leave Python's
  exit 120 and its report. Reproduced again this round with a real `EBADF` from
  `os.dup2` (matrix `d10`: P1, P2, P12 end 120; `main` raised 1; one attempt per stream).
  Stated in intent AC15, the plan, README lines 296-300 and `tasks.md` § Carried
  reservations (not in the CHANGELOG: F-35).

## AC results

| AC | Status | Evidence |
|---|---|---|
| AC1 | PASS | `success` 25 (`tests/unit`); integration `e2e_success` 2 (rerun, with the database); matrix W and E2 real `run_ingest` (experiment) |
| AC2 | PASS | `repeat` 22; `e2e_repeat` 2 (rerun) |
| AC3 | PASS | `last_page` 41; `e2e_last_page` 2 (rerun) |
| AC4 | PASS | `failure_with_response` 16; `e2e_failure` 5 (rerun); matrix `uc-failed500` (experiment) |
| AC5 | PASS | `failure_without_response` 6 (rerun) |
| AC6 | PASS | `storage` 24, `database_refusal` 57, `read_back_record_failure` 4, `refusal_not_retried` 37, `refusal_then_interrupt` 42 (rerun) |
| AC7 | PASS | `interrupt or exit_code` 417, `cleanup_system_exit` 9, `system_exit_first_wins` 4, `window_system_exit_line` 2 (rerun); matrix `uc-ctrlc` (experiment) |
| AC8 | PASS | `connection_loss` 43; `test_ingest_connection_loss.py` 7 (rerun) |
| AC9 | PASS (note F-34) | `resume` 24; `e2e_resume` 5 (rerun); `resume_probe` (experiment) |
| AC10 | PASS | `reconcile` 34; `e2e_reconcile` 6 (rerun) |
| AC11 | PASS | `closed_run` 3 (rerun) |
| AC12 | PASS | `execution_id or identity` 94 (rerun) |
| AC13 | PASS | `scope or catalogue` 124 (rerun) |
| AC14 | **PASS** (F-31 closed) | `tests/unit/ingest -k "usage or environment"` 66; `source_configuration or order_of_invocation` 30; `main_parse_interrupt` 6, `main_wiring_interrupt` 3, `main_error_stream_fault` 27, `main_help_stream_fault` 31, `flush_stream_fault` 34, `neutralize_fault` 28, `main_handler_line_fault` 12, `absent_` 44 (rerun); `tests/unit/test_cli.py` 2; integration `cli_` 17 (rerun); process tier 68 (rerun; CI reused); the console script and the children with `2>&-`, `>&-` and both (experiment) |
| AC15 | **PASS** (F-31 closed; notes F-33, F-32) | `output or logger` 93, `result_line_stream_fault` 21, `handler_stream_fault` 8, `system_exit` 88 (rerun); the rows above; the regression matrix (experiment) |
| AC16 | PASS | integration `migrations` 26; `test_postgres_migration_lock_error.py` 8 (rerun); with a missing stream, a migration error 2 and a lock 1 (`config_probe`, experiment) |
| AC17 | PASS | `no_retry` 6 (rerun) |
| AC18 | PASS in substance (F-30 for the literal `uv.lock` check) | `layer` 16 (rerun); the grep of `application/` for `SELECT `, `INSERT `, `UPDATE `, `DELETE `, `objects/`, `observations/`, `.json`, `advisory`, `pg_`, `psycopg`, `httpx` finds nothing; `interfaces` imports neither `httpx` nor `psycopg` (two comments mention `httpx`); `pyproject.toml` equals `main`; `git diff main --stat -- uv.lock` is `certifi` only (rerun) |
| AC19 | PASS | socket guards (97), the repository factory (98), `POSTGRES_HOST=db.invalid`, `cwd=tmp_path`; real `data/raw/` 0 files before and after; leftover `ecpq_test_` databases 0 (rerun) |
| AC20 | PASS in substance (F-30) | 2976 passed; `tests/unit/test_cli.py` unchanged against `main`; the only pre-F4 test file changed since `2e6edcd` is `test_postgres_migrations.py` (`3 0`); `migrations/` unchanged; ruff, format, mypy, doctor clean; `--version` 0.1.0; `git ls-files .env` empty; `git diff --check` and `git diff main..108c5a0 --check` clean (rerun) |
| AC21 | PASS for the README (notes F-35, C-2, C-3) | README lines 296-304 checked against real processes (answers 1 and 2); `AGENTS.md`, `docs/architecture.md` and `CHANGELOG.md` unchanged against `main` (only `docs/learning/` changed there) |
| AC22 | PASS | listing tests in the full run (rerun) |
| AC23 | PASS | `test_postgres_runs_and_exclusion.py` 24 (rerun) |
| AC24 | PASS (note F-34) | `chain` 197; `e2e_chain_last_page` 3 (rerun) |
| AC25 | PASS | `paths or environment` 35; integration `root` 2 (rerun) |

## Binding-constraint compliance

| Constraint | Status | Evidence |
|---|---|---|
| Layer placement (ADR 0001, AC18) | PASS | `layer` 16; the grep is clean; `output_streams.py` imports `os`, `weakref`, `contextlib`, `typing` only |
| Ownership (Revision 13: `output_streams.py`, `cli.py` with two overridden methods, `ingest_command.py` annotations; tests in the two named files; no `conftest.py` in `tests/process`) | PASS | `git show --stat` of `45137d9` and `108c5a0`; `git ls-files tests/process` lists one file |
| Public names and signatures | PASS | Pinned names unchanged; `run_ingest_command` and the helpers accept `TextIO \| None` (the plan's suggestion) |
| "A missing stream" and its table (D-11, D-12) | PASS | Answer 1; the matrix E columns |
| "D-5 as adjusted for a missing stream" (a) to (d) | PASS | Answer 1 |
| "Protected writes and the last flush" (D-6, D-7, D-10) and its outcome table | PASS | The P columns identical to `871f440`; D-10 reproduced (`d10`) |
| The handler of `main` (D-3, D-4) | PASS (note F-32) | `main_*` tokens; matrix `wiring-*` |
| "`SystemExit`" (D-1) | PASS (note F-32) | `system_exit` 88; matrix codes 3 and 4 in every mode |
| Order of an invocation; Exit codes; Output, "Writing the result" | PASS | Answers 1 and 2 |
| State machines P, C, K, T, R, H, I; "Refused writes" | PASS | Code unchanged since `c20827d`; tokens rerun |
| No schema change; write-once evidence | PASS | `migrations/` and `infrastructure/` unchanged against `main` |
| No dependency (AGENTS.md, PT-11) | PASS in substance; F-30 | No package added; `certifi` bumped by `b7d4770` |
| R-6, N3 (no chain or traceback) | PASS except the timing gap of F-32 | No `Traceback` in any matrix cell; the bootstrap's `escaped.txt` never written |
| R-7 (`httpcore` above `DEBUG`) | PASS | `_httpcore_above_debug` unchanged; `logger` tokens |
| SA-13, PS-13 | PASS | Unchanged; `opens <= 2` and `all_closed` in the tests |
| Q4 (one ingest per database) | PASS | No write without the exclusion on any path found |
| Tests (no network, no real `data/raw/`, throwaway databases; the process tier's pattern and the Revision 13 exceptions with the cleanup rule) | PASS | Answer 4 |
| `.env` never read by code or committed | PASS | `git ls-files .env` empty; the auditor never read, printed or copied it; `uv run --env-file` loaded it from the repository root by path |

## Test coverage

| AC | Tests (file) | Status |
|---|---|---|
| AC1 to AC13, AC16 to AC25 | as in rounds 6 and 7 (`tests/unit/ingest/`, `tests/integration/ingest/`, the F1 and F3 files) | PASS |
| AC14, AC15 (F-27, in process and real process) | `flush_stream_fault` 34, `neutralize_fault` 28 (unit); `process_closed_stdout` 7, `process_closed_stderr` 3, `process_closed_both` 4, `process_working_pipes` 8, `process_exit_precedence` 4 | PASS |
| AC14, AC15 (F-28, F-29) | `main_handler_line_fault` 12, `system_exit_first_wins` 4, `window_system_exit_line` 2, `cleanup_system_exit` 9; `-k "usage or environment"` 66 | PASS |
| AC14, AC15 (F-31, in process) | `absent_stderr_command` 5, `absent_stderr_main` 10, `absent_stdout_command` 3, `absent_stdout_main` 8, `absent_streams_main` 10, `absent_stream_helpers` 8 (`tests/unit/ingest/test_ingest_command.py`) | PASS |
| AC14, AC15, AC19 (F-31, real process) | `process_no_stderr` 18, `process_no_stdout` 12, `process_no_streams` 10 (`tests/process/test_cli_process_streams.py`) | PASS |
| AC19 (the cleanup of both processes) | `process_hung_cleanup` 2 (same file) | PASS |

Counts (rerun): `tests/unit/ingest` 1481 (1437 plus 44), `tests/process` 68 (26 plus 42),
total 2976 (2890 plus 86). Coverage: TOTAL 98 % locally and in CI;
`ingest_use_case.py` misses 388-389 and 598 (F-20); `cli.py` misses 51 and 58 (F-37);
`ingest_command.py` and `output_streams.py` 100 %. The process tier's children are not
measured by coverage.

### Tier Results

| Tier | Tests found | ACs verified | Setup matches § Validation | Ran | Status | Finding |
|---|---|---|---|---|---|---|
| unit | `tests/unit/ingest/` (1481, +44), the F1 listing, the hierarchy, `tests/unit/test_cli.py` (2, unchanged) | AC1 to AC18, AC22, AC24, AC25, with the Revision 12 and 13 rows and their tokens | Yes. No dev dependency, config or script added; the seams as named (`monkeypatch` of `sys.stdout`/`sys.stderr` to `None`, `capsys`, `capfd`, `record_redirections`, `FlushFaultStream`) | rerun | PASS | F-37, F-38, F-36 (regression gaps only) |
| integration | `tests/integration/ingest/` and the F3 files (266) | AC1 to AC4, AC8 to AC10, AC16, AC19, AC23 to AC25 | Yes; unchanged since round 5 | rerun in the full run with the database (2976 passed, 0 skipped); CI reused | PASS | none |
| process (Revisions 12 and 13) | `tests/process/test_cli_process_streams.py` (68) | AC14, AC15, AC19, AC21 | Yes: no marker, no `pyproject.toml` change, no `conftest.py`, the harness pattern, the Revision 13 bootstrap additions, the launcher, the cleanup rule and the accepted exceptions (two processes, three pipes kept, 96) | rerun (Windows, 68 passed, about 58 s); CI on Linux 68 passed (reused) | PASS | none (C-5 note) |
| static | `uv run mypy .` | AC18 | Yes | rerun at the repository root: 54 files clean | PASS | none |
| command | ruff, format, mypy, doctor, `--version`, git checks, `uv audit` | AC20 | Yes | rerun | PASS | F-30 (`uv.lock`) |
| manual | documentation against real processes | AC21 | n/a | rerun (inspection and experiments) | PASS (notes) | F-35, C-2, C-3, C-4 |

No test exists at a tier that § Validation does not name.

## Mutants

Scratch copy `w108` of `git archive 108c5a0`; each mutant replaced one exact text
(asserted to occur once), ran `tests/unit/ingest`, `tests/unit/test_cli.py` and
`tests/process` (1551 tests; baseline 1551 passed; the four harness mutants ran
`tests/process` only), and was restored; `src/` and `tests/` of `w108` were compared by
SHA-256 with the pristine `p108` before every mutant and after every restoration (41 of
41 identical, and identical again at the end). No `python.exe` was left after the runs.

| Id | Mutant | Result (failing tests) | Finding |
|---|---|---|---|
| A1 | the protected write without its `None` guard (executor's (a)) | killed, 36 (`absent_stderr_command`, `absent_stderr_main`, `process_no_stderr`, ...) | |
| A2 | the protected write falls back to `sys.stdout` for `None` | killed, 36 | |
| A3 | `neutralize` without its `None` guard (executor's (c1)) | survived (equivalent: `None in WeakSet` is false, `add(None)` raises `TypeError`, absorbed; nothing recorded, no `fileno`) | |
| A4 | the last flush does not skip `None` (executor's (d1)) | survived (equivalent: `None.flush()` raises `AttributeError`, absorbed, `neutralize(None)` does nothing) | |
| A5 | a `None` stream contributes a Ctrl+C to the last flush (executor's (d2)) | killed, 29 | |
| A6 | `neutralize(None)` neutralizes the real stderr | killed, 1 (`absent_stream_helpers` neutralizing) | |
| A7 | a `None` stream contributes a `SystemExit(5)` to the last flush | killed, 43 | |
| C-a | the hook without its own `file is not None` check | survived (equivalent: `write_text(None, ...)` returns) | |
| C-d | `print_usage` not overridden (executor's (f)) | killed, 6 | |
| C-e | `print_usage` falls back to stdout for `None` (executor's (e2)) | killed, 6 | |
| C-f | the hook in its `871f440` form, `file or sys.stderr` (executor's (g)) | killed, 7 | |
| C-n | `main` hands stdout to the command when stderr is missing | killed, 12 | |
| C-q | `main` hands stderr to the command when stdout is missing | killed, 6 | |
| C-o | the handler line of `main` falls back to stdout | killed, 2 | |
| C-p | the bare command's usage falls back to stdout | killed, 3 | |
| R-1 | the result line falls back to stderr when stdout is missing | killed, 9 | |
| R-4 | progress falls back to stdout when stderr is missing | killed, 4 | |
| R-7 | the command's `error: <message>` falls back to stdout | killed, 5 | |
| R-9 | the final message falls back to stdout | killed, 10 | |
| R-10 | the command handler's stderr line falls back to stdout | killed, 2 | |
| R-2 | the handler's `<A> running` falls back to stderr when stdout is missing | **survived** | F-38 |
| R-5 | the applied-migration names fall back to stdout | **survived** | F-38 |
| R-6 | the source-configuration message falls back to stdout | **survived** | F-38 |
| R-8 | the migration-lock message falls back to stdout | **survived** | F-38 |
| C9 | the hook lets an `AttributeError` through (a stream object without `write`) | **survived** (reachable only with such an object; `inproc` shows the code keeps 0 and 2) | F-38 |
| H | (h) the hook called with no file writes nothing | **survived** | F-37 |
| H2 | (h2) `print_usage()` with no file writes nothing | **survived** | F-37 |
| H3 | the hook called with no file writes on stdout | **survived** | F-37 |
| G | (g) a Ctrl+C in the protected write also neutralizes the stream | **survived** | F-36 |
| N | (n) the first non-`None` wins in `flush_for_exit` (a Ctrl+C ahead of a `SystemExit`) | **survived** | F-36 |
| O10 | the last flush does not neutralize on a Ctrl+C | **survived** | F-36 |
| O13 | the last flush on `main`'s own exit runs stderr first | **survived** | F-36 |
| C-k | the same order swap while a `SystemExit` propagates | **survived** | F-36 |
| O14 | the last of two `SystemExit` wins in the last flush | **survived** | F-36 |
| O15 | the last flush stops at the first stream that ended | **survived** | F-36 |
| C-l | (C3) a Ctrl+C in the last flush keeps `main`'s code | killed, 2 | |
| C-m | (C5) no last flush on `main`'s own code | killed, 14 | |
| HX-1 | harness: no kill of the child by pid on the parent's timeout | killed, 1 (`process_hung_cleanup` case (2); nothing leaked) | |
| HX-2 | the launcher does not kill and wait for its child on its own timeout | killed, 1 (case (1)) | |
| HX-3 | the Windows liveness helper always says gone | killed, 1 (case (1), the positive control) | |
| HX-4 | the start-state record is not checked | survived (equivalent on a platform where CPython sets `None`, as Windows does and CI shows for Linux; it guards against a vacuous pass elsewhere) | |

22 killed, 19 survived. Four survivors are equivalent (A3, A4, C-a) or platform guards
(HX-4). Fifteen are regression gaps with correct code: F-36 (G, N, O10, O13, C-k, O14,
O15), F-37 (H, H2, H3) and F-38 (R-2, R-5, R-6, R-8, C9). Every one of the fifteen is on
an output-only path; none touches data or run state. The new tests also give the red
evidence the plan records: run against the `871f440` code (the `p871` source first on
`PYTHONPATH`, the `p108` tests), `-k absent_` gives 23 failed and 21 passed and
`tests/process -k "process_no_ or process_hung_cleanup"` 26 failed and 16 passed, the
counts of `tasks.md`'s round 7 red evidence (rerun).

## Commands run (2026-10-27; repository root read-only, scratch copies of `108c5a0`, `871f440` and `c20827d`)

| Command | Result | Label |
|---|---|---|
| `git archive 108c5a0` into `p108` and `w108`, `871f440` into `p871`, `c20827d` into `p208` (scratchpad); `git diff --quiet 108c5a0 -- src tests pyproject.toml uv.lock migrations README.md docs CHANGELOG.md` at the root | copies made; the root equals the commit there | rerun |
| `docker ps` (no container running; engine 29.8.0 up); `docker compose up -d --wait` once | postgres `Up (healthy)` | rerun |
| `uv sync --locked` in each copy | ok | rerun |
| `uv run --env-file <root>/.env pytest -p no:cacheprovider --cov=ec_procurement_quality --cov-report=term-missing -q` (in `p108`; coverage data in the scratchpad) | 2976 passed, 0 skipped, 132 s, TOTAL 98 %; `ingest_use_case.py` 388-389, 598; `cli.py` 51, 58 | rerun, Windows, Python 3.14.9 |
| `uv run pytest -p no:cacheprovider -q` without the database variables (in `p108`) | 2710 passed, 266 skipped (the integration tests, with the reason) | rerun |
| `uv run ruff check --no-cache .`; `uv run ruff format --no-cache --check .`; `uv run mypy --cache-dir <scratch> .` (root) | All checks passed; 123 files already formatted; Success, 54 source files | rerun |
| `uv run node .sdd/doctor/run-doctor.mjs` (root) | 31 ok, 0 skipped, 0 warned, 0 failed | rerun |
| `git diff --check`; `git diff main 108c5a0 --check`; `git ls-files .env`; `git status --short` | clean; clean; empty; the three working-tree items only | rerun |
| `uv audit --locked` | no known vulnerabilities and no adverse project statuses in 24 packages | rerun |
| `uv run ec-procurement-quality --version` | `ec-procurement-quality 0.1.0` | rerun |
| AC18 grep of `application/`; `interfaces` imports | no match; no `httpx` or `psycopg` import | rerun |
| `git diff --stat` of `application`, `domain`, `infrastructure`, `migrations` against `c20827d` and `871f440`; of `pyproject.toml`, `uv.lock`, `tests` against `871f440`; `git diff main 108c5a0 -- uv.lock`, `-- pyproject.toml`, `-U0 -- tests`; `git diff 45137d9 108c5a0 -- tests` | empty except `uv.lock` (`certifi`, F-30) and the 86 new tests; no assertion removed; the fix commit edits no test | rerun |
| Token selections (`tests/unit` and `tests/unit/ingest`, 47 selections) and `tests/process` (6 selections) | counts in § AC results and § Test coverage; all passed | rerun |
| New test names since `871f440` (34 functions) against the token rule | none carries a forbidden or AC token | rerun |
| `tasklist` for `python.exe` before and after; `docker exec ... psql ... count of ecpq_test_%`; files under the real `data/` | none; 0; 0 before and after | rerun |
| `gh pr view 26`; `gh pr checks 26` | open, head `108c5a0`, `CLEAN`, auto-merge off; `tests` and `feedback` pass | rerun |
| `gh run view 40617404828 --log` (`Tests`, `108c5a0`) | success; Linux, CPython 3.13.18, uv 0.13.6, `certifi==2026.10.23`; 2976 passed in 51.56 s; `tests/process` 68 dots; TOTAL 98 %; `ingest_use_case.py` 388-389, 598; `cli.py` 51, 58 | reused |
| `gh run view 40617404826 --log` (`harny feedback`, `108c5a0`) | success; `harny-feedback: 2 of 2 command(s) ran, 0 skipped.` | reused |
| `r8x/driver.py` (546 child runs), `r8x/console.py` (168), `r8x/mixed.py` (30), `r8x/inproc.py`, `r8x/config_probe.py`, `r8x/resume_probe.py`, the descriptor-reuse probe | § Regression matrix and the answers | experiment |
| `r8x/mutate.py` (the mutants of § Mutants; baseline 1551 passed) | § Mutants; every restoration byte-identical | experiment |

## Conventions and feedback

- harny-standards, against `AGENTS.md`: layer boundaries hold; raw responses are never
  overwritten; no SERCOP contract is invented; no dependency, infrastructure, framework
  or service was added by the feature's commits (the `certifi` update is F-30); no secret
  in source, tests or docs (doctor gitleaks and the CI secret scan pass; the
  `synthetic-password-marker` is synthetic); verification is recorded in `tasks.md`. No
  other violation.
- harny-feedback: `.github/workflows/harny-feedback.yml` ran green at `108c5a0` with 2 of
  2 commands run (not 0). The per-turn hooks are configured and `.sdd/feedback/.turns/`
  is live (this session's turn folder exists); whether they fired and were heeded during
  the executor's and the test-writer's turns is `unavailable`. Lint and type-check were
  run only as the AC20 commands.

## Reservations carried forward

Each needs the human's written acceptance at gate 3 (closing criterion, condition 4) and
an entry in `tasks.md` § Carried reservations, which the conductor keeps. The reason of
each is in § B.

- Persistence U1 (the commit-in-flight case untested against PostgreSQL) and N5 (the
  reconciliation reads in separate snapshots, safe under the exclusion).
- Raw-evidence N2, source-access R-6, R-7, R-11 and raw-evidence N3: hold.
- Source-access U1: open until the human's live run; no document claims one happened.
- The two F-20 limitations (388-389, 598).
- F-23 (D-2 option 1).
- D-10, the residual limitation of a failed neutralizing (reproduced again).
- F-30 (only once the human confirms the update in writing; D-G1).
- F-32, F-33, F-34, F-35, F-36, F-37, F-38 and F-12, unless the human orders their fix
  (answer 6).

## What could not be verified

See answer 7. In short: Linux and Python 3.13 locally; a shell `2>&-` on Linux; a console
Ctrl+C at the bytecode gaps; a real full disk; anything live (SERCOP, the real
`data/raw/`, the configured database); the 3.13 `argparse` source; the per-turn hook
during the earlier roles' turns; who authorized `b7d4770` and the commit and push of the
round 7 rework.

## Audit log

| Round | Date | Verdict | Notes |
|---|---|---|---|
| 1 | 2026-10-18 | REJECTED | At `7603379`. F-01 and F-02 (CRITICAL) and F-03 (HIGH) block; F-04 to F-07 MEDIUM, F-08 to F-12 LOW |
| 2 | 2026-10-18 | REJECTED | At `91bd69d`. F-01 to F-11 resolved. New: F-13 (MEDIUM, blocking), F-14 (MEDIUM, blocking until decided), F-15 to F-17 LOW |
| 3 | 2026-10-18 | REJECTED | At `287946f`. F-13 to F-17 resolved. New: F-18 (HIGH, blocking); F-19 and F-20 LOW; F-12 carried |
| 4 | 2026-10-18 | REJECTED | At `10e126d`. F-18 and F-19 resolved for the two named calls. New: F-21 (MEDIUM, blocking); F-22 LOW; F-12 and F-20 LOW, partly open |
| 5 | 2026-10-21 | APPROVED WITH RESERVATIONS | At `80c8aab` (PR #26). F-20 to F-22 resolved; N-1 to N-11 hold. New, all LOW: F-23 to F-26; F-12 carried |
| 6 | 2026-10-22 | REJECTED | At `c20827d` (PR #26; CI green, 2775 passed). F-23 to F-26 resolved. New: F-27 (MEDIUM, blocking: a real closed stdout pipe gave Python's exit 120), F-28, F-29 LOW; F-12 carried. Full text at `0cebf11` |
| 7 | 2026-10-27 | REJECTED | At `871f440` (PR #26; CI green: 2890 passed). F-27, F-28, F-29 resolved; D-6 to D-10 hold. New: F-31 (MEDIUM, class A, blocking); F-30, F-32 to F-36 LOW, class B; F-12 carried. Full text at `f9a0566` |
| 8 | 2026-10-27 | APPROVED WITH RESERVATIONS | At `108c5a0` (PR #26; CI green: 2976 passed on Linux, feedback 2 of 2; locally 2976 passed with the database, 0 skipped). F-31 resolved (D-11, D-12 and the D-5 adjustments as written); no regression against `871f440` or `c20827d` (546 child runs, 168 console-script runs, 30 mixed); F-27 to F-29 still closed. New, LOW, class B: F-37 (`cli.py` 51 and 58), F-38 (missing-stream output paths without a regression test). Carried, LOW, class B: F-30 (conditional on the human's written confirmation), F-32 to F-36, F-12. Closing criterion: condition 2 holds; conditions 1 and 3 hold for this head (1 subject to D-G1); condition 4 does not hold yet. Gate 3 is the human's |
