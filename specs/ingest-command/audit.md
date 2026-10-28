# Audit: Ingest command (F4)

Auditor: `sdd-auditor` (outcome O10), round 7, 2026-10-27.
Reviewed: branch `fix/ingest-audit-hardening` at `871f4408a08ba63c4dd8c8dc8b0b3c578a2771ff`
(PR #26 against `main` at `eca3cc4`; open, `CLEAN`, auto-merge off). The previous
validated head was `c20827d` (round 6, REJECTED: F-27 MEDIUM; F-28, F-29, F-12 LOW).
Since then: `b7d4770` (`uv.lock` only: `certifi` 2026.7.22 to 2026.10.23), `0cebf11`
(the round 6 report), `5233511` (specs: intent Revision 14, plan Revision 12, tasks
Revision 9, whose Approval lines say approved by the human on 2026-10-23, with D-6 to
D-10 option A), `d958299` (115 tests: 89 unit in `tests/unit/ingest/`, 26 in the new
`tests/process/`) and `871f440` (the fix: the new `interfaces/output_streams.py`,
`interfaces/cli.py`, `interfaces/ingest_command.py`, and a README note).
`application/`, `domain/`, `infrastructure/`, `migrations/` and `pyproject.toml`
are byte-identical to `c20827d`.

Working tree, not part of the audited commit (noted, not edited): an uncommitted
one-entry edit of `specs/ingest-command/tasks.md` (§ Working state, "PR #26 at
`871f440` and its CI (2026-10-27, Revision 9 accounting)"); its CI facts agree with
the CI logs read in this round. Untracked: `docs/learning/day-20-handoff.md` and
`specs/ingest-command/.sdd/` (a feedback turn folder). `src/`, `tests/`,
`pyproject.toml`, `uv.lock` and `migrations/` in the working tree equal `871f440`
(`git diff --quiet 871f440`). The commit was audited from `git archive 871f440`
copies in the session scratchpad.

The whole feature was audited again; nothing from rounds 1 to 6 was assumed to still
hold. Read in full: `interfaces/output_streams.py` (99 lines), `interfaces/cli.py`
(149), `interfaces/ingest_command.py` (415), and the specs at the commit. Read
against the state machines: `run_ingest` (lines 1380-1696), State machine K
(`_cleanup_step`, `_cleanup_after_exception`), `_prevailing`, `_recovery_step`, the
F-20 lines; the rest of `application/ingest_use_case.py` is byte-identical to
`c20827d`, where round 6 read it in full; its tests and tokens were re-run here, and
the six F-28 mutants of round 6 were re-created on it. `git diff main` was read for the specs, the
README, `src/` and the tests; the new tests were read against the six Revision 12
rows of § Validation and the process-tier section.

Evidence labels:

- `rerun`: run by the auditor in this round on this machine (Windows 11, Python
  3.14.9, uv 0.13.5). The project's CI runs Python 3.13.18 on Linux; no Linux or
  Python 3.13 run was made locally.
- `reused`: a recorded result that is still current: the CI runs of PR #26 at
  `871f440` (`Tests` run 40449311453, `harny feedback` run 40449311508), whose logs
  were read in this round.
- `experiment`: a throwaway auditor script or mutant, run only in the session
  scratchpad on `git archive 871f440` copies (`pristine` and `work`; a third copy for
  one mutant). Real-process experiments put the pristine `src/` first on
  `PYTHONPATH` (each child logged that it imported the pristine copy) and used the
  plan's harness pattern (go byte, closed read ends set to `None`, one
  `communicate(input=..., timeout=60)`). No network (socket guard), no database
  connection from any child, no real `data/raw/`, no `ingest` against real
  collaborators. The real console script was run only for `--version`, `--help`,
  usage errors and an unset-environment error, which stop before anything is built.
- `unavailable`: could not be checked.

## Final verdict

REJECTED

**Summary**: F-27 is closed in a real process: with a closed stdout pipe, stderr
pipe or both, the confirmed result line, `--version`, `--help` and the usage errors
end with exit 1 (or 130, or a `SystemExit`'s own code), with one attempt, no
`Exception ignored` report and no exit 120, through the real console script and
through `cli.main` with genuine `sys.stdout` and `sys.stderr`; the stored run keeps
its status; D-6 to D-10 hold, and D-10's residual limitation is real and exactly as
stated (reproduced with a real failing `os.open` and a real failing `os.dup2`). F-28
and F-29 are closed. The suite passes completely (2890 passed, 0 skipped, with the
database; CI green on Linux at the same head), and ruff, mypy and the doctor are
clean. One new class A finding blocks: F-31. A process started without a stderr
(`sys.stderr` is `None`, which a plain `2>&-` produces) gets stderr text on stdout,
and since `871f440` every such ingest is closed `failed` before its first request,
and a usage or environment error exits 1 instead of 2. That breaks the stdout rule
of AC14 and AC15 and the README's "stdout holds a single result line", which is the
same yardstick the human applied to F-27.

**Critical Issues** (must fix before merge):
- F-31 (MEDIUM, class A): `write_line` and `write_text` handed a `None` stream (`sys.stderr is None`) let `print(text, file=None)` write the stderr text to stdout and then raise `AttributeError` from `None.flush()`. Real console script with `2>&-`: `ingest ... ` with `POSTGRES_DB` unset exits 1 (AC14: 2) with stdout `error: POSTGRES_DB is not set` and `unexpected error: AttributeError` (AC14: stdout empty). Real `run_ingest` in a child with doubles: the run is created, gets `unexpected-error` (`AttributeError`) and is closed `failed` before any request; stdout has three lines. At `c20827d` the same child ran the ingest to `succeeded` (exit 0, with progress text on stdout). Closing it needs a small architect decision on what a `None` stream means, and then a fix with tests (see § Findings).

**Warnings** (should fix, not blocking):
- F-30 (LOW, class B if the human confirms the update): `git diff main -- uv.lock` is no longer empty (`certifi` 2026.10.23, commit `b7d4770`, GHSA-6q48-6c7w-9gw2). AC18's example ("`git diff main --stat -- uv.lock` is empty") and AC20's ("`uv.lock` is unchanged") are now stale. No dependency was added, and `uv audit --locked` finds no vulnerability. No spec or `tasks.md` records an approval.
- F-33 (LOW, class B): AC15 Revision 14 ends "and nothing in PostgreSQL changes" for every output, but a failing stderr line during a run follows N-6, as the plan's outcome table says: the use case audits `unexpected-error` and closes the run `failed`. A stderr pipe closed from the start fails every run before its first request (reproduced). The README does not tell this.
- F-36 (LOW, class B): surviving mutants on output-only paths: (g), (n), O10, O13, O14 and O15 (§ Mutants). The code behaves as planned in each (experiments E10, X-n), so this is regression protection only.
- F-12 (LOW, class B, carried): "pending" status text survives in all three specs after their 2026-10-23 approval (list in answer 4).

**Recommendations** (nice to have):
- F-32 (LOW, class B): a Ctrl+C in the bytecode gaps of `main` after `_code_of` returned escapes with a traceback (injected experiment E15). The plan's sentence on an interrupt "between the command's return and `main`'s `raise SystemExit(code)`" now holds only inside the last flush's guards.
- F-34 (LOW, class B): a run closed without a `run-started` event cannot be resumed: `--resume` answers "invalid resumption chain" (AC24 by design). Nothing is lost, because such a run never requested a page.
- F-35 (LOW, class B): `CHANGELOG.md` § Known limitations does not list the D-10 residual limitation (the README does).

Next role: the architect, with the human, for F-31 (what a `None` stream means; see
the closure condition), F-30 (confirm the `certifi` update and amend AC18 and AC20)
and F-33; then the test-writer and the executor for F-31; then audit round 8. The
class B items can be accepted as reservations at gate 3 (§ Reservations carried
forward). Gate 3 is the human's, and it is not closed by this report.

## Rounds 1 to 6 summary

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
- **Round 6** (`c20827d`, REJECTED). F-23 to F-26 resolved (D-1 to D-5); 47 of 57
  mutants killed. New: F-27 (MEDIUM, blocking: a real closed stdout pipe gave
  Python's exit 120 and its `Exception ignored` report), F-28 and F-29 LOW; F-12
  carried. The full round 6 text is in git history at `0cebf11`
  (`git show 0cebf11:specs/ingest-command/audit.md`). The human chose option (b) for
  F-27 and D-6 to D-10 option A (2026-10-22), approved intent 14, plan 12 and tasks 9
  (2026-10-23), and approved the F4 closing criterion (`docs/learning/day-20-handoff.md`
  § 3, 2026-10-23), which this report applies.

## Resolution of the earlier findings

The use-case code is byte-identical to `c20827d`, where round 6 checked every closure
condition with a mutant that a test killed; the tests that pinned them still pass
here (§ AC results, rerun), and the only removed test lines since `c20827d` are the
two F-29 renames. The interface code changed, so the interface-side closures were
re-checked against the new code.

| Id | Earlier severity | Status | Evidence (this round) |
|---|---|---|---|
| F-01, F-02 | CRITICAL | Resolved (still) | `pending_sequence` set at 1508, cleared at 1536, 1556, 1582, 1598; K absorbs the three read-back errors (768-771); `interrupt or exit_code` 417 passed (rerun). Experiment U (closed stderr from the start): K ran and closed the run, nothing lost |
| F-03 | HIGH | Resolved (still) | `_invoke` builds the source before `_migrate`; the message now goes through `write_line` (`ingest_command.py:330`); `source_configuration or order_of_invocation` 30 passed (rerun); the I8 mutant (no flush there) survives, equivalent in a real process (§ Mutants) |
| F-04 | MEDIUM | Resolved (still) | `_print_running` (270-277) through `_end_after_escape`; E5 (real process, stderr closed, announced run): stdout `<A> running`, exit 1 |
| F-05 to F-11, F-13 to F-15, F-17 to F-22 | various | Resolved (still) | Use-case code unchanged; tokens `storage` 24, `database_refusal` 57, `connection_loss` 43, `reconcile` 34, `chain` 197, `execution_id or identity` 94 (rerun, `tests/unit`) |
| F-16 | LOW | Resolved (still) | `result_written` set in `_report` (262) before either write; `_print_running` checks it; process 7a/7b (rerun): one line only |
| F-20 | LOW | Accepted limitation (unchanged) | Coverage misses exactly 388-389 and 598 of `ingest_use_case.py` (rerun and CI); code unchanged |
| F-23 | LOW (spec decision) | Resolved (decided D-2, kept) | `refusal_then_interrupt` 42 passed (rerun) |
| F-24 | LOW (spec decision) | Resolved | `system_exit` 88 passed (rerun, `tests/unit`); D-1 holds in the new code (answer 2) |
| F-25 | LOW | Resolved | Unchanged code; tests pass (rerun) |
| F-26 | LOW | Resolved (still) | `main_parse_interrupt` 6, `main_wiring_interrupt` 3, `main_error_stream_fault` 27, `main_help_stream_fault` 31 (rerun); see F-32 for the narrowed tail of `main` |
| F-27 | MEDIUM | **Resolved** | Answer 1. Real console script and real-process children with genuine streams: every closed-pipe case ends 1, 130 or the `SystemExit` code; never 120; no `Exception ignored`, `flushing sys.` or `Traceback`; process tier 26 passed (rerun, Windows) and 26 passed in CI on Linux (reused). README note matches (answer 5). Mutants O1, O2, O7, C5, C7, I1, I3, I4, I5 killed; the unflushed stderr lines I2, I6 to I10 and C6 survive, equivalent in a real process (§ Mutants) |
| F-28 | LOW | **Resolved** | N10, N11 (C14), N12 (C13), N31, N38 and N39 re-created on the current code: all killed (§ Mutants). Tokens `main_handler_line_fault` 12, `system_exit_first_wins` 4, `window_system_exit_line` 2, `cleanup_system_exit` 9 (rerun). `cli.py` coverage 100 % (line 90 of round 6 now covered) |
| F-29 | LOW | **Resolved** | The two tests renamed (`..._a_parse_error_...`), bodies unchanged; `uv run pytest tests/unit/ingest -q -k "usage or environment"` gives 66 passed; `-k main_error_stream_fault` 27 (rerun). No new test name carries a forbidden token (45 new names checked) |
| F-12 | LOW | Partially resolved (carried) | The round 6 items were corrected in tasks Revision 9; new stale text since: answer 4 |

## Findings

Class is the human's closing criterion of 2026-10-23 (`docs/learning/day-20-handoff.md`
§ 3): class A blocks gate 3 at any severity; class B may stay as a reservation the
human accepts in writing.

| Id | Severity | Class | AC / constraint | Finding and evidence | Failure scenario | Closure condition | Status |
|---|---|---|---|---|---|---|---|
| F-31 | MEDIUM (blocking) | A (an explicit AC example and a README promise are unmet in a reproducible real process, the yardstick the human used for F-27) | AC14 ("`POSTGRES_DB` ... unset -> exit 2, stdout empty"; usage errors "stdout empty"); AC15 ("stdout carries only the result line"; "stdout is exactly one line `<id> <status>`"); README § Ingesting line 248 ("stdout holds a single result line"); plan § Public names, "The protected write" | When Python starts with no valid descriptor 2 it sets `sys.stderr` to `None` (on Windows Git Bash `2>&-` gives `None`, checked: `python -c "import sys; print(repr(sys.stderr))" 2>&-` prints `None`; on Linux CPython does the same for an invalid fd 2). `main` passes `sys.stderr` to the command, and `output_streams._written_and_flushed` runs `print(text, file=None)`, which writes to `sys.stdout`, then `None.flush()` raises `AttributeError`; `neutralize(None)` does nothing and the error is raised. Real console script (rerun, Windows, `.venv/Scripts/ec-procurement-quality.exe ... 2>&-`, `POSTGRES_*` unset): `ingest --year 2025 --buyer B --last-page 1` -> exit 1, stdout `error: POSTGRES_DB is not set` and `unexpected error: AttributeError`; the control with `2>/dev/null` -> exit 2, stdout empty. Experiment U (child, real `run_ingest` with the in-memory doubles of `tests/unit/ingest/conftest.py`, `sys.stderr = None`): exit 1; stdout `run <A> started`, `unexpected error: AttributeError`, `<A> failed`; stored run `failed` with one event `unexpected-error` (`AttributeError`, page 1), no `run-started`, no request. The same child at `c20827d`: exit 0, the run `succeeded` with both pages, and every progress line on stdout. So the stdout pollution predates the fix (round 6 noted it as "not a realistic console-script case"; `2>&-` shows it is reachable from a console shell), and `871f440` adds the exit-code change and the failed run. Separately, and not counted here: with `sys.stderr` `None`, `argparse` itself prints a usage error's usage on stdout (`print_usage(None)` falls back to `sys.stdout` before the writing hook is called); that is `argparse`'s own behavior on `main` before F4 too | An operator or a script runs `ingest ... 2>&-` (to discard progress) and parses stdout: it gets three lines, the run is closed `failed` before any request, and every retry fails the same way; a usage error reports exit 1 instead of 2 | The architect decides what a `None` stream means and records it (intent AC14/AC15 and plan "The protected write"); the obvious choice is a stream that writes nothing and does not fail (as `print(file=None)` intends when there is no stream), so the ingest runs, usage errors keep 2 and stdout keeps only the result line; or a stream that fails, without writing to stdout. Either way, the protected write must never write a stderr text to stdout. The `argparse` usage fallback needs either an exception to D-5's "only `_print_message`" or a stated limitation. Then a unit test (`sys.stderr` `None` through `main`, and the reporter of a run) and a process-tier case, and the README if the meaning is user-visible. Alternatively, the architect scopes "a process started without a stderr" out of AC14 and AC15 as a stated limitation with a README note; it then becomes a class B reservation the human accepts in writing | Open (blocking) |
| F-30 | LOW | B, if the human confirms in writing that `b7d4770` was authorized (otherwise an unapproved dependency change, class A) | AC18 ("no dependency is added: `git diff main --stat -- uv.lock` is empty"); AC20 ("`uv.lock` is unchanged"); plan § Ownership ("Unchanged: ... `uv.lock`"); `AGENTS.md` (approval before dependency changes) | `git diff main -- uv.lock` shows only `certifi` 2026.7.22 -> 2026.10.23 (version, sdist and wheel hashes), from `b7d4770` "Update certifi to 2026.10.23 for the emSign root removal" (GHSA-6q48-6c7w-9gw2). No package was added; `pyproject.toml` is unchanged; `uv audit --locked`: "Found no known vulnerabilities" (rerun). No spec, `tasks.md` or decision records an approval; the commit carries no assistant attribution | A later reader runs AC18's or AC20's literal check and finds it false | The human confirms in writing that the update was his or approved, and the architect amends AC18's and AC20's examples (for example, "`uv.lock` differs from `main` only by the security update of `certifi` of 2026-10-23"); or the update is reverted | Open |
| F-33 | LOW | B (stale or imprecise spec text; the behavior is the approved N-6 rule, unchanged since `c20827d`, and data stay consistent) | AC15 Revision 14 ("every output ... (the result line, every stderr line, ...) ... follows the rules above ...; the confirmed status is kept, the result line is not attempted again, and nothing in PostgreSQL changes"); plan "Protected writes", outcome table row "Other stderr lines of the command (progress, ...)": "during the run the use case's rules (an exception from the reporter; N-6) ... so 1"; README § Ingesting lines 290-300 | Read for a progress line, AC15's last clause contradicts the plan's row, which the code follows. Experiment U (child, real `run_ingest`, stderr pipe closed before the child writes): the first stderr write is `run <A> started`; it fails, the use case audits `unexpected-error` (`OSError`, page 1) and closes the run `failed`; stdout `<A> failed`, exit 1, no request. With stdout closed instead, the stored run stays `succeeded` with its events unchanged (nothing in PostgreSQL changes). The README states the result-writing case only ("If the command cannot write its result ...") and does not say that a stderr that fails during a run fails the run. `c20827d` did the same for a closed stderr (then with exit 120) | A reader of AC15 or of the README expects a closed stderr pipe (for example `2>&1 | head -1`, or a log reader that dies) to leave the run alone; the run is closed `failed` instead, and it is resumable when its `run-started` was written | The architect scopes AC15's clause to the result writes (the result line, the final message and the handlers' lines) and points to N-6 for the progress lines; optionally the README says that a stderr that fails during a run ends the run `failed` (resumable) | Open |
| F-36 | LOW | B (output-only paths, behavior verified by experiments; no data or run state) | Plan "Protected writes and the last flush" ("A `KeyboardInterrupt` ... the stream is not neutralized there"; "flushes `sys.stdout` and then `sys.stderr`"; "a `KeyboardInterrupt` there neutralizes that stream"; "the first one wins"); harny-audit step 5 | Surviving mutants that are not equivalent (§ Mutants): (g) a Ctrl+C in the protected write also neutralizes the stream; (n) `flush_for_exit` returns a `KeyboardInterrupt` ahead of a `SystemExit`; O10 the last flush does not neutralize on a Ctrl+C; O13 the last flush runs stderr before stdout; O14 the last of two `SystemExit` wins in the last flush; O15 the last flush stops at the first stream that ended. (C9 belongs to F-31; nine more survivors are equivalent in a real process.) The code is right: E10 (real process, a genuine SIGINT raised while the confirmed result line is flushed to a working stdout) delivers `<A> succeeded` and exits 130, while under mutant (g) the same experiment loses the line (stdout empty, exit 130); X-n (in process): stdout's last flush ending in a Ctrl+C and stderr's in `SystemExit(4)` give exit 4, and two Ctrl+C give 130. Under AC15 a line interrupted by a Ctrl+C "may be missing", so even (g) would stay inside the AC | A later change reintroduces one of these behaviors and no test fails | Unit tests that kill (g), (n), O10, O13, O14 and O15 (E10 and X-n are templates), if the human wants them; otherwise accepted as a reservation | Open (recommendation) |
| F-32 | LOW | B (a single Ctrl+C at an exact bytecode instant; consequence a traceback and Windows' exit 0xC000013A after the result line was written; no data or run state) | Plan § Public names, "The handler of `main`" ("One `try` around the whole body of `main` (... and the final `raise SystemExit(...)`)"; "on an interrupt that lands between the command's return and `main`'s `raise SystemExit(code)` (exit 130 then ...)"); AC15 ("nothing prints a traceback") | The executor split `main` into `_code_of` (the handlers) and `main` (the last flush and the raise). Lines 143-149 of `cli.py` are outside any `KeyboardInterrupt` handler; only the two `stream.flush()` calls inside `_flushed_for_exit` are guarded. At `c20827d` the final `raise SystemExit(code)` was inside the `try`. E15 (experiment, real process, a Ctrl+C injected right after `flush_for_exit`'s guarded calls): `<A> succeeded` on stdout, then a `Traceback` ending in `KeyboardInterrupt`, exit 3221225786. A Ctrl+C in the same place of the `except SystemExit:` block would replace a propagating `SystemExit`. Pure Python cannot close every bytecode gap (round 6's checklist lists others); the window here is a few bytecodes | A Ctrl+C at that instant prints a traceback (file paths and code lines of the install, no secret) and the exit code is the interpreter's, not 130 | A `KeyboardInterrupt` handler around `main`'s tail that raises `SystemExit(130)` (and keeps a propagating `SystemExit`), or the human accepts it with the other bytecode gaps | Open (recommendation) |
| F-34 | LOW | B (spec-consistent; no page can be lost; the message is unhelpful) | AC24 ("a run in the chain with no `run-started` event ... is malformed"); AC9; README § Ingesting ("A failed run is resumed with its execution id"; the exit-1 row "or the chain of a resumption is broken") | `run_ingest` calls `reporter.run_started(id)` (1450) before it appends `run-started` (1460-1469). A reporter failure there (a stderr closed from the start, F-33), a Ctrl+C there, or a refused `run-started` append ends the run `failed` with no `run-started`. Experiment (in process, real `run_ingest`, the conftest doubles): the first run fails with `unexpected error: OSError` at `run_started` and requests nothing; `--resume` of it -> `NOT_STARTED`, "invalid resumption chain <A>", exit 1. Pre-existing since the first implementation | The operator follows the README, resumes the failed run, and is told its chain is invalid; a fresh `ingest` of the same scope does the same work | Optionally a README sentence ("a run that failed before it recorded its start is not resumable; start the scope again") or a clearer message; no code change is required by the specs | Open (recommendation) |
| F-35 | LOW | B (documentation; the approved plan Revision 12 names only the README note and the `cli` capability at archive) | AC21 ("`CHANGELOG.md` § Unreleased lists ... the known limitations") | `CHANGELOG.md` § Known limitations, `ingest` (lines 200-218) does not mention the D-10 residual limitation, which README lines 296-300 state | A release note reader does not see the residual exit 120 case | Add one bullet at O11 (`harny-document`), or the human accepts it | Open (recommendation) |
| F-12 | LOW | B (accounting and stale spec text) | harny-audit step 4; plan § Rollout | Answer 4 lists the "pending" and conditional text left in the three specs at `871f440` after their approval on 2026-10-23, and the outdated F-20 line numbers in `tasks.md` § Carried reservations | The next role reads that the specs await approval | Each listed line says approved on 2026-10-23, or is marked historical; § Carried reservations names lines 388-389 and 598 | Open |

## Answers to the round 7 questions

**1. Is F-27 closed in a real process?** Yes, on Windows (rerun, experiment) and, for
the process tier, on Linux (CI, reused). Evidence from the auditor's own children:

- With genuine `sys.stdout` and `sys.stderr` (the process tier replaces `sys.stdout`
  with a recording stream; these experiments do not), `cli.main` with a stub wiring
  and a stub `run_ingest`, the parent closing its read ends before the go byte (3
  runs per case unless said):
  - E1, stdout closed, confirmed `<A> succeeded`: exit 1; stderr `run <A> started`
    and the outcome message only; `os.dup2` called once, onto descriptor 1. E1b
    (`<A> failed`): exit 1.
  - E2 `--version`, E3 `--help`, E3b `ingest --help`, stdout closed: exit 1; stderr
    exactly `unexpected error: OSError`; one `dup2` onto 1.
  - E4, stderr closed, an unannounced `SUCCEEDED`: exit 1, stdout exactly
    `<A> succeeded`; one `dup2` onto 2. E5, stderr closed, an announced run: the stub's
    `run_started` raises, stdout `<A> running`, exit 1. E5b usage error, E5c bare
    command, stderr closed: exit 1, stdout empty.
  - E6 `--version`, E6b a result line, E6c a usage error, both closed: exit 1; at
    most one `dup2` per stream (E6c writes nothing on stdout, so only descriptor 2).
  - E0 controls with working pipes: 0 with `<A> succeeded`; `--version` 0; usage
    error 2 with the usage and `error:` on stderr.
  - In none of them `Exception ignored`, `flushing sys.` or `Traceback`, and no 120.
- The real console script (`.venv/Scripts/ec-procurement-quality.exe`, 2 runs each):
  `--version` working 0; stdout closed: `--version`, `--help`, `ingest --help` 1 with
  `unexpected error: OSError`; stderr closed: a usage error, the bare command and an
  unset-environment error 1 with stdout empty; both closed `--version` 1.
- Real `run_ingest` (experiment U, a child with the in-memory doubles): stdout closed
  -> exit 1, the stored run `succeeded` with its two observations and three events,
  nothing added.
- Attempts to break it:
  - E7 `sys.stdout.close()` before `main` (a closed file): the result line gives 1,
    `--version` gives 1 with `unexpected error: ValueError`; no 120.
  - E9 a stdout with no `fileno` whose write raises: 1, no 120 (nothing to
    neutralize; the real descriptor holds nothing).
  - E10 a genuine SIGINT (`signal.raise_signal`) during the result line's flush:
    working stdout -> 130 and the line still arrives (the last flush pushes it);
    closed stdout -> 130, one `dup2` (from the last flush), no 120. E10c the same in
    `--version`'s flush: 130, the text arrives, stderr `interrupted`.
  - E11 `SystemExit(4)` raised in the result line's flush with stdout closed: exit 4,
    no 120 (the last flush neutralizes stdout while the `SystemExit` propagates).
    E11b `SystemExit(3)` from the use case: 3.
  - A full-disk analogue is not available on Windows (`/dev/full`); E7 and E9 cover a
    stream that cannot be written in two other ways.
  - D-10 with real failures: E12c exhausts the descriptor table (8188 descriptors)
    right before the result line, so `os.open(os.devnull)` itself fails with
    `EMFILE`; E13 gives `os.dup2` a descriptor that does not exist (`EBADF`). Both,
    stdout closed: exit 120 and `Exception ignored while flushing sys.stdout: OSError:
    [Errno 22] Invalid argument` after the outcome message; with working pipes E12c
    exits 0. This is the D-10 residual exactly as stated: `main` raised its code and
    made no second attempt, and only Python's finalization replaced the code.
  - Descriptor 1 closed at start-up (`>&-`, console script): `--version` exits 0 with
    its text on stderr (`argparse`'s own `file or sys.stderr` fallback, as before
    F4), and the unset-variable error exits 2 with its line on stderr. No F4 defect.
  - Not closed: descriptor 2 closed at start-up, `sys.stderr` `None` (F-31).

**2. Do D-6 to D-10 hold exactly as the plan says?** Yes, with the gaps of F-32 and the
regression gaps of F-36.
- One attempt per stream: `neutralize` records the stream in a module-level `WeakSet`
  before `fileno()`, so a failed attempt is never repeated; the protected write and the
  last flush share it. Every experiment logged at most one `dup2` per descriptor. O3
  (no record) and O6 (recorded only after success) are killed.
- Absorbed `Exception`s: `with suppress(Exception)` around the whole attempt; a closed
  file's `ValueError` (E7), a missing `fileno` (E9), `EMFILE` (E12c), `EBADF` (E13)
  were absorbed and the original write error was raised (or dropped by the last flush).
  O4 (absorbs `BaseException`) and O5 (absorbs `OSError` only) are killed.
- Ctrl+C 130: a Ctrl+C in a protected write is raised unchanged and does not
  neutralize (E10: the line still arrives); the callers give 130 (`_attempt`,
  `_settled_code`, the handlers, `main`'s handler, the last flush). A Ctrl+C in the
  neutralizing is not absorbed. (g) survives (F-36).
- `SystemExit` first wins: `_attempt` and the handlers do not catch it; `neutralize`
  does not absorb it; `main` drops the last flush's result while a `SystemExit`
  propagates and re-raises the same object; with its own code it raises the first
  `SystemExit` of the two streams. E11, process 7b and 7c, and the `neutralize_fault`
  (d) cases agree. C1, C2 and C4 are killed; (n) and O14 survive (F-36).
- No text written by the neutralizing: none in the code; O16 (a text written) is
  killed.
- The last flush of `main`: on `main`'s own exit and while a `SystemExit` propagates;
  stdout then stderr, each guarded; C1, C3, C5, O9, O11, O12 are killed; O10, O13 and
  O15 survive (F-36).
- No path was found where a stream gets a second neutralizing, a text is written twice
  (the last flush pushes only bytes that the one attempt already handed over, into the
  null device when the stream failed), or a `SystemExit` is lost, apart from the
  bytecode gap of F-32 (a Ctrl+C there would replace a propagating `SystemExit`).

**3. Is anything written to or read from PostgreSQL because of an output failure?**
Not because of a failure of the result writes: experiment U with stdout closed leaves
the run `succeeded` with its events unchanged, and `_report` touches no repository. A
failing stderr line during the run is the N-6 rule: the use case audits
`unexpected-error` and closes the run (F-33, by design). No change to `application`,
`domain`, `infrastructure`, the schema or `migrations/` since `c20827d`
(`git diff c20827d 871f440 --stat` of those paths is empty). The integration tests
pass with the database (answer 7).

**4. F-28, F-29, and the remaining F-12 text.** F-28 and F-29 are closed (§ Resolution).
Stale text at `871f440`, all class B:
- `intent.md`: line 423 ("Revision 14 holds the architect's responses, **pending the
  human's approval**"); line 523, Revision log 14 ("Pending the human's approval,
  including the decisions D-6 to D-9 and D-10"). The Revision log entries 7, 8, 9, 10
  and 12 also still say "Pending the human's approval"; their approvals are recorded
  in the Approval line.
- `execution-plan.md`: line 5 (intent Revision 14 "pending the human's approval");
  line 980, heading "Audit round 6 responses (2026-10-22; pending the human's
  approval)", and line 981 "Nothing is implemented before the human approves this
  revision"; line 1241, Revision log 12 ("Pending the human's ..."); the conditional
  "required once the revision is approved" at lines 293, 367, 384 and 433; the
  Revision log entries 5, 6, 7, 8 and 10 as in the intent.
- `tasks.md`: line 5 ("Intent ... Revision 14 (pending) · Plan ... Revision 12
  (pending)"); § Status line 15 ("pending the human's approval: `intent.md` Revision
  14, `execution-plan.md` Revision 12 and this file Revision 9"); O10 line 356
  ("Rework of round 6 (Revision 9, pending the human's approval ...)", and step 1
  "Nothing is implemented before the approval"); § Finding responses F-27, F-28 and
  F-29 (lines 500-502, "Architect proposal (2026-10-22), pending approval"); § Carried
  reservations, F-20, still names lines 475/535 and 285-286/317-318 of old heads
  (now 598 and 388-389). § Status's spec list also still opens with Revisions 11/9/6
  as the current set.

**5. README § Ingesting against the real-process behavior.** Lines 296-300 ("Normally a
closed or failing output stream ends with exit code 1 (or 130), never with Python's
own 120 or its `Exception ignored` report. In the one residual case ... Python's
finalization may still print that report and replace the exit code by 120; this
changes nothing in PostgreSQL, and the output is not attempted again") match E1 to
E11, the console script, E12c and E13. The exit-code table matches: 1 for a result that
cannot be written, 130 for a Ctrl+C while writing, 2 for usage errors with working
streams (E0c). Two gaps, both findings: `2>&-` breaks "stdout holds a single result
line" and the exit-2 row (F-31); a stderr that fails during a run fails the run, which
the README does not say (F-33). The README names no `SystemExit` case, per the approved
plan.

**6. The four conditions of the closing criterion.**
1. No class A finding open: **does not hold**. F-31 is open. F-30 is class B only once
   the human confirms the `certifi` update in writing.
2. Suite, CI, ruff, mypy, doctor: **holds**. 2890 passed, 0 skipped with the database
   (rerun, Windows, Python 3.14.9); `Tests` run 40449311453 on `871f440`: 2890 passed,
   98 %, Linux, Python 3.13.18 (reused); ruff, ruff format, mypy (54 files) and the
   doctor (31 ok, 0 warned, 0 failed) clean (rerun).
3. The latest audit audits that head with APPROVED or APPROVED WITH RESERVATIONS:
   **does not hold**. This audit audits `871f440` and is REJECTED.
4. Reservations written with their reason in `audit.md` and in `tasks.md` § Carried
   reservations, and accepted in writing: **does not hold yet**. They are written here
   (§ Reservations carried forward); `tasks.md` § Carried reservations has the D-10 and
   F-20 entries only, and the human has accepted none of the new ones.

   What the human must decide or accept in writing: the closure path of F-31 (fix, or
   a scoping that makes it a stated limitation); that `b7d4770` was authorized (F-30);
   and, as reservations, F-30 (if confirmed), F-32 to F-36 and F-12, the D-10 residual
   limitation (now reproduced for real), the F-20 limitations and F-23 (D-2).

**7. What was not run.** Linux and Python 3.13 locally: `unavailable`; the only Linux
evidence is CI at `871f440` (2890 passed, the 26 process tests included, reused).
PostgreSQL behavior is unchanged by this fix: no `application` or schema change, and
the integration tests passed with the Compose database (rerun). The real SERCOP
source, the real `data/raw/` and a real `ingest` were not used. A console Ctrl+C
(`CTRL_C_EVENT`) was not sent; `signal.raise_signal(SIGINT)` was used inside the
child. A real full disk was not reproduced.

## Executor and test-writer choices where the plan was silent

| Choice | Assessment |
|---|---|
| (1) The once-per-stream record is a module-level `weakref.WeakSet`; a stream that is not weak-referenceable or not hashable is never neutralized | Conformant. Checked: a `__slots__` stream is never recorded and its `fileno()` is never called, so it cannot be attempted twice. `sys.stdout` and `sys.stderr` are weak-referenceable |
| (2) `main` split into `_code_of` (the two handlers) and `main` (the last flush, the only `except SystemExit`) | A compliant alternative for every guarded call, with one narrowing: the final `raise SystemExit` is no longer inside a `KeyboardInterrupt` handler (F-32) |
| (3) In `flush_for_exit` the first `SystemExit` wins over a `KeyboardInterrupt`; stderr is flushed whatever stdout did | Conformant (X-n); untested (F-36: (n), O14, O15) |
| (4) `os.open(os.devnull, os.O_WRONLY)` with no extra flags | Conformant; Python opens it non-inheritable and `dup2` keeps the target inheritable, as standard streams are |
| (5) One `# noqa: BLE001` on `_flushed_for_exit` | Conformant with the existing style |
| (6) Docstrings rewritten; `_exit_after_writing` became `_code_after_writing` | Conformant; the docstrings describe the code |
| (7) A Ctrl+C in a protected write is raised unchanged and does not neutralize | Conformant (E10); untested ((g), F-36) |
| Test-writer: the process tier replaces `sys.stdout` with a recording `TextIOWrapper` subclass over descriptor 1, as the plan requires | Conformant; the auditor's experiments cover the genuine `sys.stdout` and the console script |
| Test-writer: `process_closed_both` adds an "announced-run" case (`<A> running`) | Within the row; harmless |

## Accepted limitations

- F-20 (accepted on 2026-10-18): lines 388-389 (an append on the new connection lost
  again after the re-check) and 598 (a normal-path append whose recovery is not
  confirmed) of `ingest_use_case.py` have no test. The code is unchanged; coverage
  misses exactly these lines locally and in CI.
- F-23 (decided in D-2, option 1): kept and pinned (`refusal_then_interrupt` 42).
- D-10 (option A, chosen by the human): a neutralizing that fails may leave Python's
  exit 120 and its report. Stated in intent AC15, the plan, README lines 296-300 and
  `tasks.md` § Carried reservations; reproduced for real in this round (E12c, E13).
  `main` still raises the agreed code and makes no second attempt.

## AC results

| AC | Status | Evidence |
|---|---|---|
| AC1 | PASS | `-k success` 25 (`tests/unit`); integration `e2e_success` 2 (rerun) |
| AC2 | PASS | `repeat` 22; `e2e_repeat` 2 (rerun) |
| AC3 | PASS | `last_page` 41; `e2e_last_page` 2 (rerun) |
| AC4 | PASS | `failure_with_response` 16; `e2e_failure` 5 (rerun) |
| AC5 | PASS | `failure_without_response` 6 (rerun) |
| AC6 | PASS | `storage` 24, `database_refusal` 57, `read_back_record_failure` 4, `refusal_not_retried` 37, `refusal_then_interrupt` 42 (rerun) |
| AC7 | PASS | `interrupt or exit_code` 417; `cleanup_system_exit` 9, `system_exit_first_wins` 4, `window_system_exit_line` 2 (rerun); E10 (experiment) |
| AC8 | PASS | `connection_loss` 43; `test_ingest_connection_loss.py` 7 (rerun) |
| AC9 | PASS (note F-34) | `resume` 24; `e2e_resume` 5 (rerun) |
| AC10 | PASS | `reconcile` 34; `e2e_reconcile` 6 (rerun) |
| AC11 | PASS | `closed_run` 3 (rerun) |
| AC12 | PASS | `execution_id or identity` 94 (rerun) |
| AC13 | PASS | `scope or catalogue` 124 (rerun) |
| AC14 | PARTIAL (F-31) | `tests/unit/ingest -k "usage or environment"` 66; `source_configuration or order_of_invocation` 30; `main_parse_interrupt` 6, `main_wiring_interrupt` 3, `main_error_stream_fault` 27, `main_help_stream_fault` 31, `flush_stream_fault` 34, `neutralize_fault` 28, `main_handler_line_fault` 12; `tests/unit/test_cli.py` 2; integration `cli_` 17 (rerun); process tier 26 (rerun; CI reused); the real console script (experiment). With `2>&-`, an unset-variable error exits 1 with stdout non-empty (F-31) |
| AC15 | PARTIAL (F-31; note F-33) | `output or logger` 93; `result_line_stream_fault` 21, `handler_stream_fault` 8, `system_exit` 88 (`tests/unit`); the Revision 12 rows above; process tier 26 (rerun); E1 to E13 and U (experiment). With `sys.stderr` `None`, stdout carries stderr lines (F-31) |
| AC16 | PASS | integration `migrations` 26; `test_postgres_migration_lock_error.py` 8; `git diff 2e6edcd --numstat -- tests/integration/test_postgres_migrations.py` `3 0` (rerun) |
| AC17 | PASS | `no_retry` 6 (rerun) |
| AC18 | PASS in substance (F-30 for the literal `uv.lock` check) | `layer` 16; the grep of `application/` for `SELECT `, `INSERT `, `UPDATE `, `DELETE `, `objects/`, `observations/`, `.json`, `advisory`, `pg_`, `psycopg`, `httpx` finds nothing; `interfaces` imports neither `httpx` nor `psycopg` (two comments mention `httpx`); `pyproject.toml` against `2e6edcd` shows only the two F-1 keys and three comment lines; `git diff main --stat -- uv.lock` is not empty: `certifi` only (rerun) |
| AC19 | PASS | The process tier's children run with a socket guard (exit 97), a repository factory that exits 98, synthetic `POSTGRES_*` and `POSTGRES_HOST=db.invalid`, `cwd=tmp_path`; files under the real `data/` 0 before and after the runs; leftover `ecpq_test_` databases 0 (rerun) |
| AC20 | PASS in substance (F-30) | 2890 passed; `tests/unit/test_cli.py` unchanged against `main`; the only pre-F4 test file changed since `2e6edcd` is `test_postgres_migrations.py` (`3 0`); `git diff main -U0 -- tests` removes 2 lines (the round 5 ones), and since `c20827d` only the two F-29 names; ruff, format (123 files), mypy (54 files), doctor (31 ok, 0 warned, 0 failed); `--version` 0.1.0; `git ls-files .env` empty; `git diff --check` and `git diff main --check` clean; `migrations/` unchanged. `uv.lock` differs from `main` by `certifi` (F-30) (rerun) |
| AC21 | PASS for the new note (notes F-31, F-33, F-35) | README lines 296-300 checked against real processes (answer 5); `AGENTS.md`, `docs/architecture.md` and `CHANGELOG.md` unchanged since `main` (inspection, rerun) |
| AC22 | PASS | listing tests pass in the full run (rerun) |
| AC23 | PASS | `test_postgres_runs_and_exclusion.py` 24 (rerun) |
| AC24 | PASS (note F-34) | `chain` 197; `e2e_chain_last_page` 3 (rerun) |
| AC25 | PASS | `paths or environment` 35; integration `root` 2 (rerun) |

## Binding-constraint compliance

| Constraint | Status | Evidence |
|---|---|---|
| Layer placement (ADR 0001, AC18) | PASS | `layer` 16; grep clean; `output_streams.py` imports `os`, `weakref`, `contextlib`, `typing` only |
| Ownership (Revision 12: `interfaces/output_streams.py`, `tests/process/`, no `conftest.py` there) | PASS | `git ls-files tests/process` lists one file |
| Public names and signatures | PASS | Pinned types and signatures unchanged |
| "Protected writes and the last flush" (D-6, D-7, D-10) and its outcome table | PASS except F-31 | Answers 1 and 2; a `None` stream is not covered by the table and writes to stdout (F-31) |
| The handler of `main` (D-3, D-4) and the one local parser class (D-5) | PASS (note F-32) | `_CliParser` overrides only `_print_message`, now through `write_text`; `argparse` not patched; C7, C8, N10, C13, C14 killed |
| "`SystemExit`" (D-1) | PASS (note F-32) | Answer 2 |
| Order of an invocation; Exit codes; Output, "Writing the result" | PASS except F-31 | Answers 1 and 5 |
| State machines P, C, K, T, R, H, I; "Refused writes" | PASS | Code unchanged since `c20827d`; tokens rerun; N31, N38, N39 killed |
| No schema change; write-once evidence | PASS | `migrations/` and `infrastructure/` unchanged against `main` |
| No dependency (AGENTS.md, PT-11) | PASS in substance; F-30 | No package added; `certifi` bumped by `b7d4770` |
| R-6, N3 (no chain, `__context__` or traceback printed) | PASS except the timing gap of F-32 | E1 to E13; E15 injected |
| R-7 (`httpcore` above `DEBUG`) | PASS | `_httpcore_above_debug` unchanged |
| SA-13, PS-13 | PASS | `opens <= 2` and `all_closed` in the tests |
| Q4 (one ingest per database) | PASS | No write without the exclusion on any path found |
| Tests (no network, no real `data/raw/`, throwaway databases; the process tier's pattern) | PASS | Process tier follows the plan: `Popen` with three pipes, `cwd=tmp_path`, no shell, no `creationflags`, `PYTHONUNBUFFERED` removed, the go byte, closed ends set to `None`, one `communicate(input=b"g", timeout=60)`, kill and collect on timeout; asserts the exact code, never 120, 97 or 98, and no `Exception ignored`, `flushing sys.` or `Traceback` |
| `.env` never read by code or committed | PASS | `git ls-files .env` empty; the auditor never read, printed or copied it (a copy attempt was refused by the permission guard and nothing was copied); `uv run --env-file .env` loaded it at the repository root |

## Test coverage

| AC | Tests (file) | Status |
|---|---|---|
| AC1 to AC13, AC16 to AC25 | as in round 6 (`tests/unit/ingest/`, `tests/integration/ingest/`, the F1 and F3 files) | PASS |
| AC14, AC15 (F-27, in process) | `flush_stream_fault` 34 (`tests/unit/ingest/test_ingest_command.py`) | PASS |
| AC14, AC15 (D-10) | `neutralize_fault` 28 (same file) | PASS |
| AC14, AC15, AC19, AC21 (F-27, real process) | `process_closed_stdout` 7, `process_closed_stderr` 3, `process_closed_both` 4, `process_working_pipes` 8, `process_exit_precedence` 4 (`tests/process/test_cli_process_streams.py`) | PASS |
| AC14, AC15 (F-28, handler line) | `main_handler_line_fault` 12 | PASS |
| AC7, AC8 (c), AC15 (F-28, `SystemExit`) | `system_exit_first_wins` 4, `window_system_exit_line` 2 (`test_ingest_use_case.py`), `cleanup_system_exit` 9 (5 unit plus `exit_code_cleanup_system_exit` 4) | PASS |
| AC14 (F-29) | the two renames; `-k "usage or environment"` 66 | PASS |
| AC14, AC15 with `sys.stderr` `None` | none | MISSING (F-31) |

Counts (rerun): `tests/unit/ingest` 1437 (1348 plus 89), `tests/process` 26, total new
115. Coverage: TOTAL 98 % locally and in CI; `ingest_use_case.py` misses 388-389 and
598 (F-20); `cli.py`, `ingest_command.py` and `output_streams.py` 100 %. The process
tier's children are not measured by coverage; the unit rows cover `output_streams.py`.

### Tier Results

| Tier | Tests found | ACs verified | Setup matches § Validation | Ran | Status | Finding |
|---|---|---|---|---|---|---|
| unit | `tests/unit/ingest/` (1437, +89), the F1 listing (25), the hierarchy (3), `tests/unit/test_cli.py` (2, unchanged) | AC1 to AC18, AC22, AC24, AC25, with the Revision 12 rows and their tokens | Yes. No dev dependency, config or script added; seams as named (raising `TextIO` with a flush fault, `dup2` and `os.open` recorders, the doubles) | rerun | PASS | F-31 (no `None`-stream case), F-36 |
| integration | `tests/integration/ingest/` and the F3 files | AC1 to AC4, AC8 to AC10, AC16, AC19, AC23 to AC25 | Yes; unchanged since round 5 | rerun with `--env-file .env` (13 focused commands, and `tests/unit/ingest tests/integration/ingest` 1521 passed); CI reused | PASS | none |
| process (new, Revision 12) | `tests/process/test_cli_process_streams.py` (26) | AC14, AC15, AC19, AC21 | Yes: no marker, no `pyproject.toml` change, no `conftest.py`, the exact harness pattern, the bootstrap as specified | rerun (Windows, 26 passed, about 37 s); CI on Linux 26 passed (reused) | PASS | F-31 (no `None`-stream case) |
| static | `uv run mypy .` | AC18 | Yes | rerun at the repository root: 54 files clean (in the scratch copy mypy could not load its compiled module because of the Windows path length; environment only) | PASS | none |
| command | ruff, format, mypy, doctor, `--version`, git checks | AC20 | Yes | rerun | PASS | F-30 (`uv.lock`) |
| manual | documentation inspection | AC21 | n/a | rerun (inspection and real-process checks) | PASS (notes) | F-31, F-33, F-35 |

No test exists at a tier that § Validation does not name.

## Mutants

Scratch copy `work` of `git archive 871f440`; each mutant replaced one exact text
(asserted to occur once), ran `tests/unit/ingest`, `tests/unit/test_cli.py` and
`tests/process` (1465 tests; baseline 1465 passed), and was restored; `src/` and
`tests/` of `work` were compared byte for byte (SHA-256 over every file) with the
pristine archive before every mutant and after every restoration: 47 of 47 identical.

| Id | Mutant | Result (failing tests) |
|---|---|---|
| (g) | a Ctrl+C in the protected write also neutralizes the stream (executor's survivor) | **survived**. Real-process consequence (E10 under the mutant, third copy): the confirmed `<A> succeeded` is lost after a Ctrl+C in its flush to a working stdout (F-36) |
| (n) | `flush_for_exit` returns the first non-`None`, so a Ctrl+C ahead of a `SystemExit` (executor's survivor) | **survived** (F-36; X-n shows the code gives the `SystemExit`) |
| O1 | no flush in the protected write | killed, 58 (`flush_stream_fault`, process tier) |
| O2 | the redirection is never made | killed, 33 |
| O3 | no once-per-stream record | killed, 4 (`neutralize_fault` through `main`) |
| O4 | `neutralize` absorbs `BaseException` | killed, 10 |
| O5 | `neutralize` absorbs only `OSError` | killed, 2 |
| O6 | the attempt is recorded only after success (a failed neutralizing is retried) | killed, 3 |
| O7 | the protected write swallows the failure | killed, 83 |
| O9 | the last flush does not neutralize on an `Exception` | killed, 5 |
| O10 | the last flush does not neutralize on a Ctrl+C | **survived** (F-36) |
| O11 | the last flush drops its Ctrl+C | killed, 2 |
| O12 | the last flush flushes stdout only | killed, 3 |
| O13 | the last flush runs stderr before stdout | **survived** (F-36; it changes which of two `SystemExit` wins) |
| O14 | the last of two `SystemExit` in the last flush wins | **survived** (F-36) |
| O15 | the last flush stops at the first stream that ended | **survived** (F-36) |
| O16 | the neutralizing writes a text | killed, 7 (process tier) |
| O17 | the null-device descriptor is not closed | survived (equivalent: one descriptor leaked per neutralized stream, nothing observable) |
| O18 | the redirection always targets descriptor 1 | killed, 24 |
| C1 | no last flush while a `SystemExit` propagates | killed, 2 |
| C2 | the last flush's `SystemExit` replaces a propagating one | killed, 2 |
| C3 | a Ctrl+C in the last flush keeps `main`'s code | killed, 2 |
| C4 | a `SystemExit` in the last flush is dropped | killed, 4 |
| C5 | no last flush on `main`'s own code | killed, 14 |
| C6 | `main`'s handler line written with `print` (no flush) | survived (equivalent in a real process: stderr is line-buffered since Python 3.9, so the line end flushes it, and the last flush neutralizes a failed stderr; it differs only at the in-process flush-fault seam) |
| C7 | the parser message is not flushed | killed, 37 |
| C8 | the parser hook swallows `OSError` again (D-5) | killed, 38 |
| C9 | the parser hook lets an `AttributeError` through | survived (reachable only with a `None` stream; no test has one: F-31) |
| C10 | the parser message gets an extra line end | killed, 15 |
| C11 | the parser hook falls back to `sys.stdout` (round 6 N15) | survived (equivalent: every caller passes a file) |
| C12 | the bare command's usage on stdout | killed, 13 |
| C13 | a Ctrl+C on the handler line keeps the code (round 6 N12) | killed, 2 (`main_handler_line_fault`) |
| C14 | the handler line swallows a `SystemExit` (round 6 N11) | killed, 4 (`main_handler_line_fault`) |
| N10 | no `KeyboardInterrupt` branch on the handler line (round 6) | killed, 4 (`main_handler_line_fault`) |
| N31 | `_prevailing`: the later of two of a kind wins (round 6) | killed, 4 (`system_exit_first_wins`) |
| N38 | `_recovery_step` writes a line for a `SystemExit` (round 6) | killed, 2 (`window_system_exit_line`) |
| N39 | K turns a `SystemExit` into an outcome (round 6) | killed, 9 (`cleanup_system_exit`, `exit_code_cleanup_system_exit`) |
| I1 | a progress line not flushed | killed, 1 (`flush_stream_fault` (g)) |
| I2 | `run <A> started` not flushed | survived (equivalent in a real process, as C6) |
| I3 | the result line not flushed | killed, 17 |
| I4 | the final message not flushed | killed, 1 |
| I5 | a handler's `<A> running` not flushed | killed, 2 |
| I6 | a handler's stderr line not flushed | survived (equivalent in a real process, as C6) |
| I7 | the command's own usage error not flushed | survived (equivalent in a real process, as C6; the console-script run with stderr closed and `POSTGRES_DB` unset gives 1) |
| I8 | the configuration message of step 2 not flushed | survived (equivalent in a real process, as C6) |
| I9 | the migration lock message not flushed | survived (equivalent in a real process, as C6) |
| I10 | an `applied migration` line not flushed | survived (equivalent in a real process, as C6) |

31 killed, 16 survived. Nine survivors are equivalent in a real process (O17, C6, C11,
I2, I6 to I10). Seven are regression gaps with correct code: (g), (n), O10, O13, O14,
O15 (F-36) and C9 (F-31). Every F-28 mutant of round 6 (N10, N11 = C14, N12 = C13,
N31, N38, N39) is now killed.

## Commands run (2026-10-26 and 2026-10-27; repository root read-only, scratch copies of `871f440`)

| Command | Result | Label |
|---|---|---|
| `git archive 871f440` into `pristine` and `work` (scratchpad); `git diff --quiet 871f440 -- src tests pyproject.toml uv.lock migrations` at the root | copies made; root code equals the commit | rerun |
| `docker compose ps` | postgres `Up (healthy)` | rerun |
| `uv sync --locked` (scratch) | ok, 25 packages | rerun |
| `uv run --env-file .env pytest --cov=ec_procurement_quality --cov-report=term-missing -q` (root; coverage data redirected to the scratchpad, cache disabled) | 2890 passed, 0 skipped, TOTAL 98 %; `ingest_use_case.py` 388-389, 598 | rerun, Windows, Python 3.14.9 |
| `uv run pytest -q` without the database variables (scratch) | 2624 passed, 266 skipped (the integration tests, with the reason) | rerun, Windows, Python 3.14.9 |
| `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy .` (root) | All checks passed; 123 files already formatted; Success, 54 source files | rerun |
| `uv run node .sdd/doctor/run-doctor.mjs` (root) | 31 ok, 0 skipped, 0 warned, 0 failed | rerun |
| `git diff --check`; `git diff main --check`; `git ls-files .env`; `git status --short` | clean; clean; empty; the three working-tree items above only | rerun |
| `uv audit --locked` | no known vulnerabilities in 24 packages | rerun |
| `uv run ec-procurement-quality --version` | `ec-procurement-quality 0.1.0` | rerun |
| AC18 grep of `application/`; `interfaces` imports | no match; no `httpx` or `psycopg` import | rerun |
| `git diff c20827d 871f440 --stat` for `application`, `domain`, `infrastructure`, `migrations`, `pyproject.toml`; `git diff main --stat` for `domain`, `infrastructure`, `migrations`, `pyproject.toml`, `tests/unit/test_cli.py`, `specs/current`, `docs/adr`, `compose.yaml`, `.env.example`, `docs/glossary.md`, `docs/architecture.md`, `AGENTS.md`, `CHANGELOG.md` | all empty | rerun |
| `git diff main -- uv.lock` | `certifi` only (F-30) | rerun |
| The token selections of § AC results (31 unit selections in the pristine copy, 13 integration selections with the database) and the Revision 12 tokens (`tests/unit/ingest`), `tests/process`, `tests/unit/test_cli.py` | all passed (counts in § AC results and § Test coverage) | rerun |
| New test names since `c20827d` (45) against the token rule | none carries a forbidden token; only the two F-29 names were removed | rerun |
| Leftover `ecpq_test_` databases (count only, inside the container); files under the real `data/` | 0; 0 | rerun |
| `gh pr view 26`; `gh pr checks 26` | open, head `871f440`, `CLEAN`, auto-merge off; `tests` and `feedback` pass | rerun |
| `gh run view 40449311453 --log` (`Tests`, `871f440`) | success; Linux, CPython 3.13.18; 2890 passed; process tier 26; TOTAL 98 %; `ingest_use_case.py` 388-389, 598 | reused |
| `gh run view 40449311508 --log` (`harny feedback`, `871f440`) | success; `harny-feedback: 2 of 2 command(s) ran, 0 skipped.` | reused |
| E0 to E15, E12c, the console script runs, experiment U (also at `c20827d`), the resume probe, X-n, the `__slots__` probe, E10 under mutant (g) | quoted in § Findings and § Answers | experiment |
| The 47 mutants of § Mutants | 31 killed, 16 survived (9 equivalent); 47 of 47 restorations identical | experiment |

## Conventions and feedback

- harny-standards, against `AGENTS.md`: layer boundaries hold; raw responses are never
  overwritten; no SERCOP contract is invented; no dependency, infrastructure,
  framework or service was added by the feature's commits (the `certifi` update is
  F-30); no secret in source, tests or docs (doctor gitleaks and the CI secret scan
  pass; the process tier's `synthetic-password-marker` is synthetic); verification is
  recorded in `tasks.md`. No other violation.
- harny-feedback: `.github/workflows/harny-feedback.yml` ran green at `871f440` with
  2 of 2 commands run (not 0). The per-turn hooks are configured and
  `.sdd/feedback/.turns/` is live (this session created a turn folder); whether they
  fired and were heeded during the executor's turns is `unavailable` (turn files are
  not kept). Lint and type-check were run only as the AC20 commands.

## Reservations carried forward

Each needs the human's written acceptance at gate 3 (closing criterion, condition 4)
and an entry in `tasks.md` § Carried reservations, which the conductor keeps.

- Persistence U1: the real commit-in-flight case is still untested against
  PostgreSQL. Reason: no safe way to cut a commit in flight; state machine C covers it
  with doubles.
- Persistence N5: the reconciliation reads run in separate snapshots. Reason: safe
  under the ingest exclusion.
- Raw-evidence N2, source-access R-6, R-7, R-11 and raw-evidence N3: hold.
- Source-access U1: open until the human's live run; no document claims one happened.
- The two F-20 limitations (388-389, 598). Reason: second-order fault paths, shown
  by experiments in round 3.
- F-23 (D-2 option 1). Reason: the current behavior was chosen; no data loss.
- D-10, the residual limitation of a failed neutralizing. Reason: Python's
  finalization runs after `main` and F4 cannot control it; reproduced for real (E12c,
  E13); no effect on PostgreSQL and no second attempt.
- F-30 (if the human confirms the update). Reason: a security update of an existing
  transitive dependency, no dependency added; the AC text is stale.
- F-32. Reason: a timing-only gap of a few bytecodes after the result was written;
  pure Python cannot close every gap.
- F-33. Reason: spec wording; the behavior is the approved N-6 rule.
- F-34. Reason: AC24 makes such a chain malformed; such a run requested nothing.
- F-35. Reason: documentation; the README states the limitation.
- F-36. Reason: output-only regression protection; the behavior was verified by
  experiments.
- F-12. Reason: accounting.

F-31 is not a reservation unless the architect scopes it out of AC14 and AC15 first.

## What could not be verified

- Linux and Python 3.13 locally (`unavailable`); CI on Linux at `871f440` is the only
  evidence there, including the `BrokenPipeError` branch of the process tier.
- `sys.stderr` `None` on Linux (`2>&-`): reasoned from CPython's start-up rule and
  reproduced on Windows only.
- A console Ctrl+C delivered at the bytecode gaps; faults were injected (E15) or raised
  with `signal.raise_signal` (E10).
- A real full disk; a real `ingest` against SERCOP, the real `data/raw/` or the
  configured database (out of scope; must not be run).
- That the per-turn feedback hook fired during the executor's rework.
- Who authorized `b7d4770` (F-30).

## Audit log

| Round | Date | Verdict | Notes |
|---|---|---|---|
| 1 | 2026-10-18 | REJECTED | At `7603379`. F-01 and F-02 (CRITICAL) and F-03 (HIGH) block; F-04 to F-07 MEDIUM, F-08 to F-12 LOW |
| 2 | 2026-10-18 | REJECTED | At `91bd69d`. F-01 to F-11 resolved. New: F-13 (MEDIUM, blocking), F-14 (MEDIUM, blocking until decided), F-15 to F-17 LOW |
| 3 | 2026-10-18 | REJECTED | At `287946f`. F-13 to F-17 resolved. New: F-18 (HIGH, blocking); F-19 and F-20 LOW; F-12 carried |
| 4 | 2026-10-18 | REJECTED | At `10e126d`. F-18 and F-19 resolved for the two named calls. New: F-21 (MEDIUM, blocking); F-22 LOW; F-12 and F-20 LOW, partly open |
| 5 | 2026-10-21 | APPROVED WITH RESERVATIONS | At `80c8aab` (PR #26). F-20 to F-22 resolved; N-1 to N-11 hold. New, all LOW: F-23 to F-26; F-12 carried |
| 6 | 2026-10-22 | REJECTED | At `c20827d` (PR #26; CI green, 2775 passed). F-23 to F-26 resolved. New: F-27 (MEDIUM, blocking: a real closed stdout pipe gave Python's exit 120), F-28, F-29 LOW; F-12 carried. Full text at `0cebf11` |
| 7 | 2026-10-27 | REJECTED | At `871f440` (PR #26; CI green: 2890 passed on Linux, feedback 2 of 2; locally 2890 passed with the database, 0 skipped). F-27, F-28, F-29 resolved; D-6 to D-10 hold (D-10's residual reproduced for real). New: F-31 (MEDIUM, class A, blocking: a `None` stderr writes stderr text to stdout and, since `871f440`, fails every run and turns exit 2 into 1); F-30, F-32 to F-36 LOW, class B; F-12 carried. Closing criterion: conditions 1, 3 and 4 do not hold; condition 2 holds |
