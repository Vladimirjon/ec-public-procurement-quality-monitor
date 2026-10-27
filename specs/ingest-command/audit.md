# Audit: Ingest command (F4)

Auditor: `sdd-auditor` (outcome O10), round 6, 2026-10-22.
Reviewed: branch `fix/ingest-audit-hardening` at `c20827d05e4de53cbd73bfe97b93fdfef2d73c10`
(PR #26 against `main` at `eca3cc4`). The previous validated head was `80c8aab`
(round 5 report committed at `5574cd6`). Since then: `c70a6bd` (specs, intent
Revision 13, plan Revision 11, tasks Revision 8), `22cd04c` (159 new tests, +1585/-0)
and `c20827d` (the fix: `ingest_use_case.py` +9/-6, `ingest_command.py` +13/-2,
`cli.py` +54/-18). Specs: `intent.md` Revision 13, `execution-plan.md` Revision 11
and `tasks.md` Revision 8, all approved by the human on 2026-10-21 (D-1 option A,
D-2 option 1, D-3 option B, D-4 option 1, D-5 option a). The working tree was clean
for the whole round; the source under `src/` is byte-identical to `HEAD` once line
ends are normalized (two empty, untracked folders `tests/contract` and
`tests/end_to_end` exist and hold nothing).

The whole feature was audited again; nothing from rounds 1 to 5 was assumed to
still hold. `application/ingest_use_case.py` (1697 lines), `interfaces/ingest_command.py`
(415 lines) and `interfaces/cli.py` (120 lines) were read in full against the state
machines P, C (with "The current repository", "The explicit record" and "Two or more
exceptions"), K (with "After any other refusal"), T, R, H and I, the "Refused writes"
table and "A refusal is answered, never retried", the required progress lines, the
invocation order (with "Where step 1 runs"), § Output (with "Writing the result"),
§ Exit codes, the "`SystemExit`" rule and its combination table, "The handler of
`main`", the D-5 parser constraint and AC1 to AC25. `git diff main` was read for the
specs, the README, `src/` and the tests; the new tests were read against the four new
§ Validation rows.

Evidence labels:

- `rerun`: the auditor ran it in this round.
- `reused`: a recorded result that is still current (the CI runs of PR #26 at
  `c20827d`, finished before this report).
- `experiment`: a throwaway auditor script, test or mutant, run only in the session
  scratchpad on copies of `src/` and `tests/` extracted with `git archive HEAD`. The
  mutant copy was checked byte for byte against a second pristine archive before the
  run and after every mutant (57 mutants, 57 restorations identical). Experiments that
  needed the repository's doubles ran in a third archive copy with one added scratch
  test file. Real-process experiments ran with the pristine copy's `src/` on
  `PYTHONPATH`, outside the repository, with no network, no database connection and
  no `ingest` run against real collaborators.
- `unavailable`: it could not be checked.

## Final verdict

REJECTED

**Summary**: The round 5 reservations are closed in the code and pinned by tests: the
`SystemExit` rule (D-1) holds at every place it names, F-23 is settled as the current
behavior and pinned, F-26 is closed by the handler of `main` and the one local parser
class, F-25's paths have tests (M5, M14, M15, M16 and M28 are now killed), F-01 to F-22
are still resolved, 2775 tests pass locally and in CI, and 47 of 57 mutants are
killed. One MEDIUM finding blocks: F-27, a closed stdout pipe (or a stdout file that
cannot be written) does not give exit 1 in a real process, as AC15, AC14 (D-5) and
the README say; the line is buffered, so the failure shows only when Python flushes
stdout at exit, which prints `Exception ignored on flushing sys.stdout: OSError: ...`
and exits 120.

F-27 was present at `80c8aab` and round 5 did not raise it: its AC21 row checked the
README sentence against the in-process behavior only. Its classification needs the
human's eye. The plan's "Writing the result" scopes the exit-1 rule to an exception
"raised while it writes", and under that reading the code conforms and only the
README's example ("for example, a closed output stream") is wrong, which is still a
documentation deviation (AC21, MEDIUM). Read literally for a real process, AC15's
"any other error that prevents writing the result ... gives exit 1" is unmet, which
blocks at any severity. Either reading blocks.

**Critical Issues** (must fix before merge):
- F-27 (MEDIUM, blocking): in a real process, a closed stdout pipe makes the command exit 120 with Python's `Exception ignored on flushing sys.stdout` report, not exit 1. This holds for a confirmed result line, and for `--version` and `--help`. AC15 (N-7), AC14 (D-5) and README § Ingesting (lines 290-295) promise exit 1.

**Warnings** (should fix, not blocking):
- F-28 (LOW): some required behavior of D-1 and D-3 has no test that would fail if it were removed. That covers the handler line of `main` (`cli.py:89-90`, a Ctrl+C or a `SystemExit` while `main`'s handler writes its own line), the first of two `SystemExit` in the recovery window, no progress line for a `SystemExit` in the window, and a `SystemExit` raised during State machine K. The surviving mutants are N10, N11, N12, N31, N38 and N39. The code behaves as planned in every one of these cases (experiments X26, X29, X30 and X31).
- F-12 (LOW, carried): `tasks.md` and one heading of the plan still describe the state before the round 5 rework. Examples: "pending approval" for the approved Revision 13/11/8, "uncommitted, awaiting the human's review" for the committed fix, "Next: the round 5 rework", PR #26 head `5574cd6`, and "the F-21 README to-do of Revision 6 is open".

**Recommendations** (nice to have):
- F-29 (LOW): two new test names (`..._a_failing_write_of_a_usage_error_...`, `..._a_usage_error_still_exits_2`, 21 items) contain `usage`, which plan Revision 11's token rule forbids. As a result, AC14's `-k "usage or environment"` row now selects 87 tests instead of 66. The selection is harmless (they are AC14 tests).

Next role: the architect, then the executor or the human, under the gate 3
rejection rule. For F-27, the architect decides with the human between two closures:
- (a) Scope the exit-1 rule of AC15, AC14 and § Output to a write that raises while the command writes. The README then states what a real closed pipe gives (Python's own exit 120 and its one-line report, the run unchanged). This closure changes the documentation and the spec only.
- (b) Make the failure surface inside the guarded write: flush stdout inside the one attempt, and keep Python's exit-time flush from failing again. A real-process check then needs a tier that § Validation does not name today, so it needs the human's approval.

Then F-28, F-29 and F-12 go to the test-writer and to whoever keeps `tasks.md`, if the
human wants them closed. After that comes audit round 7.

## Rounds 1 to 5 summary

- **Round 1** (`7603379`, REJECTED). 12 findings; F-01, F-02 (CRITICAL) and F-03
  (HIGH) blocked. Full report in git history at `7069f4c`.
- **Round 2** (`91bd69d`, REJECTED). F-01 to F-11 resolved; F-13, F-14 (MEDIUM)
  blocked; F-15 to F-17 LOW. Full report at `2f77b5e`.
- **Round 3** (`287946f`, REJECTED). F-13 to F-17 resolved; F-18 (HIGH) blocked;
  F-19, F-20 LOW. Full report at `fe0fb28`.
- **Round 4** (`10e126d`, REJECTED). F-18, F-19 resolved for the named calls; F-21
  (MEDIUM) blocked; F-22 LOW. Full report at `25d1253`.
- **Round 5** (`80c8aab`, APPROVED WITH RESERVATIONS). F-20 to F-22 resolved; N-1
  to N-11 held; new, all LOW: F-23 (a refused write followed by an interrupt), F-24
  (`SystemExit` against `KeyboardInterrupt`), F-25 (untested required paths), F-26
  (step 1 interrupt or stream error escapes the command); F-12 carried. Full report at
  `5574cd6`. The human chose to correct the reservations before gate 3: D-1 to D-5
  (2026-10-21) gave intent Revision 13, plan Revision 11 and tasks Revision 8; the
  rework landed in `22cd04c` (tests) and `c20827d` (fix).

## Resolution of the earlier findings

Each closure condition was checked against the current code and against at least one
mutant of this round that a test kills (scratch copy, `tests/unit/ingest` and
`tests/unit/test_cli.py`, 1350 tests). The `E-` mutants re-create the round 1 to 4
fixes on the current code; the `N` mutants are this round's. The code of
`ingest_use_case.py` changed since round 5 only in `run_ingest`'s propagating handler
and `_close_while_propagating`; `ingest_command.py` only in `_invoke`'s step 7.

| Id | Earlier severity | Status | Evidence (current code; mutant: failing tests) |
|---|---|---|---|
| F-01 | CRITICAL | Resolved (still) | Pending set before `store` (1508), cleared only when the record returned or the path concluded (1536, 1556, 1582, 1598). E-F01 (clear right after `store`): 4 failed |
| F-02 | CRITICAL | Resolved (still) | K absorbs the three read-back errors (768-771). E-F02: 4 failed |
| F-03 | HIGH | Resolved (still) | `ingest_command.py:324-330`, source built before `_migrate`. E-F03 (exit 1): 16 failed |
| F-04 | MEDIUM | Resolved (still) | `_print_running` (269-276) through `_end_after_escape`. E-F04: 24 failed |
| F-05 | MEDIUM | Resolved (still) | K reads the run first (757-766). E-F05: 9 failed |
| F-06 | MEDIUM | Resolved (still) | 1402-1412. E-F06 (chain `OSError` escapes): 3 failed |
| F-07 | MEDIUM | Resolved (still) | `_report_page` (423-427; 1524, 1571). E-F07: 8 failed |
| F-08, F-09 | LOW | Resolved (still) | No `_finish` helper; catalogue text says 32 characters |
| F-10 | LOW | Resolved (still) | 947-950. E-F10: 2 failed |
| F-11 | LOW | Resolved (still) | `_close_failed`, `_append_on_normal_path`, `_finish_succeeded`; `database_refusal` 57 (rerun). The compound case is now decided (F-23) |
| F-12 | LOW | Partially resolved (carried) | The five round 5 items are corrected in Revision 8 except § Checkpoint's "the F-21 README to-do of Revision 6 is open" (it was written in `80c8aab`). New stale text since: see F-12 below |
| F-13 | MEDIUM | Resolved (still) | `_cleanup_step` (718-734). E-F13: 57 failed |
| F-14 | MEDIUM | Resolved (still) | One line per refused or lost call in every phase; `pre_run_database_error` 59 (rerun) |
| F-15 | LOW | Resolved (still) | Fixed messages naming the identity (1362-1412, 1423-1427) |
| F-16 | LOW | Resolved (still) | (a) first opening (1243-1254): E-F16a 1 failed. (b) `result_written`: N26 4 failed |
| F-17 | LOW | Resolved (still) | README § Ingesting lists every `running` case |
| F-18 | HIGH | Resolved (still) | Second repository current only after `True` (303-305). E-F18 (M19): 48 failed |
| F-19 | LOW | Resolved (still) | `_recovery_step` names only the call of the window (193-214) |
| F-20 | LOW | Resolved (still) | `generic_fallback` 2 (rerun). E-F20: 23 failed. The two accepted limitations stay accepted (388-389, 598; code unchanged) |
| F-21 | MEDIUM | Resolved (still) | The explicit record (`drop_current` 252-261, used at 326, 332, 358, 377, 540, 636). N41 (M1): 124 failed; N44 (M3): 8 failed |
| F-22 | LOW | Resolved (still) | `_close_after_outcome` (1304-1324). E-F22: 10 failed |
| F-23 | LOW (spec decision) | Resolved (decided and pinned) | D-2 option 1 kept the current behavior: AC6 (e) now says "'No further event' says how a refusal is answered, not what a later interruption does", plan § State machine K "After any other refusal" and the failure-path row of "Refused writes" agree. `refusal_then_interrupt` 42 (rerun). E-D2 (an interrupt in the refused line swallowed, K skipped): 28 failed |
| F-24 | LOW (spec decision) | Resolved | D-1 option A implemented at every place it names (answer 1). N30 (M5): 8 failed; N34 (M14): 6; N32 (close's Ctrl+C replaces a propagating `SystemExit`): 6; N20/N21 (step 7 flag): 1 each; N22: 9; N23 (`_attempt` catches `SystemExit`): 4; N40: 22; N45: 6; N5: 139; N6 (identity lost in `main`): 15. Residual test gaps: F-28 |
| F-25 | LOW (recommendation) | Resolved | `window_line_fault` 12, `close_while_propagating` 6, `p2_read_run_loss_line` 4, `interrupted_outcome_close` 1 (rerun). N36 (M16): 8 failed; N33 (M15): 5; N37 (M28): 4. Line 1315 covered (M13 stays equivalent) |
| F-26 | LOW | Resolved | The handler of `main` (`cli.py:102-119`) and `_CliParser` (28-39). `main_parse_interrupt` 6, `main_wiring_interrupt` 3, `main_error_stream_fault` 27, `main_help_stream_fault` 31 (rerun). Killed: N1 13, N2 13, N3 8, N4 5, N7 42, N8 15, N9 30, N13 45, N14 12, N16 2, N17 169. Real process (X27): a Ctrl+C from `default_wiring()` exits 130 with stderr exactly `interrupted`, no traceback |

The sweep A2 rules (plan Revision 10) still hold: N-1 (`start_run_second_loss` 34), N-2
(`unexpected_cleanup_interrupt` 18; E-N2 25 failed), N-3 (`recovery_double_fault` 15,
`window_line_fault` 12; N36 killed), N-4 (`refusal_not_retried` 37; N42 8, N43 19, N44
8 failed), N-5 (`close` 266-277), N-6 (`when="before"`/`"after"` everywhere), N-7
(`result_line_stream_fault`/`handler_stream_fault` 29; N25 10, N26 4, N27 9 failed; but
see F-27 for a real process), N-8, N-9 (`close_while_propagating`; N33 killed), N-10
(`CloseFault` one-shot), N-11 (accounting).

## Findings

| Id | Severity | AC / constraint | Finding and evidence | Failure scenario | Closure condition | Status |
|---|---|---|---|---|---|---|
| F-27 | MEDIUM (blocking; see the verdict for the two readings) | AC15 ("any other error that prevents writing the result (for example `OSError` or `MemoryError`) gives exit 1"; N-7, the human's decision of 2026-10-20); AC14 Revision 13 (D-5: "an `OSError` while their text is written exits 1"); AC21 (README § Ingesting, lines 290-295: "If the command cannot write its result (for example, a closed output stream) ... 1 for any other write failure"); plan § Output "Writing the result" (scoped to an exception "raised while it writes") | In a real process, stdout to a pipe or a file is block-buffered. `print(line, file=stdout)` in `_report` (`ingest_command.py:265`) and `argparse`'s write in `_CliParser._print_message` (`cli.py:39`) only fill the buffer and do not raise. The command returns its code and `main` raises `SystemExit(code)`. CPython then flushes stdout at finalization, the flush fails, and Python prints `Exception ignored on flushing sys.stdout:` and `OSError: [Errno 22] Invalid argument` on stderr. That report includes the error's text, not only its class name. Python then exits 120. The N-7 and D-5 machinery (`_attempt`, `_settled_code`, the handler of `main`) is never reached. stderr is line-buffered, so stderr failures do raise at write time and are handled as planned. The tests model a stream whose write raises (the approved seam), so they cannot see this. The behavior is the same at `80c8aab`. For `--version`, it is the same on `main` before F4, but AC14 now promises 1. Not raised in round 5 | X28 (experiment, real process, Windows): `cli.main` with `run_ingest` returning a confirmed `succeeded` outcome and a wiring that builds nothing. Control: exit 0, stdout `<A> succeeded`. With the parent closing the stdout pipe at once (3 runs): exit 120 every time, stderr `run <A> started`, `succeeded`, `Exception ignored on flushing sys.stdout:`, `OSError: [Errno 22] Invalid argument`. X27 (experiment): `ec-procurement-quality --version` and `--help` with stdout a closed pipe: exit 120 and the same `Exception ignored` report, 3 of 3 runs each, no `Traceback`. On Linux the same CPython path is expected to report `BrokenPipeError: [Errno 32] Broken pipe` and exit 120 (`unavailable`: not run on Linux) | Either (a) the architect scopes the exit-1 rule of AC15, AC14 and § Output to a write that raises, and README § Ingesting stops promising exit 1 for "a closed output stream" (it states what a real closed pipe gives, the run unchanged); or (b) the code makes the failure surface inside the one guarded attempt (for example, flush after the write) and prevents the exit-time flush from failing again, with a real-process check approved as a § Validation row. The human decides between them | Open (blocking) |
| F-28 | LOW (recommendation) | Plan § Public names "The handler of `main`" ("what that one attempt raises: a `KeyboardInterrupt` makes the code 130; a `SystemExit` propagates in its place"); "`SystemExit`" ("of two `SystemExit`, the first one propagates"; "never writes a line because of it"; the table row "including from the write of an `interrupted` or `unexpected error` line by `main()`'s handler"; "During § State machine K"); harny-audit step 5 | Required behavior with no test that would fail if it were removed (surviving mutants): N10 (no `KeyboardInterrupt` branch on the handler line, `cli.py:89-90`), N11 (the handler line swallows a `SystemExit`), N12 (a Ctrl+C on the handler line keeps code 1); N31 (`_prevailing`: the later of two `SystemExit` wins in the window); N38 (`_recovery_step` writes a line for a `SystemExit`); N39 (K turns a `SystemExit` into an outcome). `cli.py:90` is the only uncovered line of `cli.py`. The § Validation F-26 row lists only `OSError` on the handler line, and the F-24 row has no two-`SystemExit` window case and no `SystemExit` during K, so this is a regression gap, not a missing row. Also, `main`'s docstring says the handler names "only its class" for a `KeyboardInterrupt`, but it writes `interrupted` | X26 (experiment, through `main`): `MemoryError` from `default_wiring`, then a Ctrl+C on `unexpected error: MemoryError` gives `SystemExit(130)`. Ctrl+C then a Ctrl+C on `interrupted` gives 130. `SystemExit(3)` on either handler line comes out as the same object, code 3. `OSError` on the line gives 1. stdout is empty in all of them. X29: in the window, the exclusion raises `SystemExit(3)` and the second close raises `SystemExit(4)`: `SystemExit(3)`, the same object, comes out. X30: an exclusion raising `SystemExit(3)` writes no line that names it. X31: a Ctrl+C at page 2, then K's `run-interrupted` append raises `SystemExit(3)`: that object propagates, and `<A>` stays `running` with no new event. The code is right in every case; only regression protection is missing | Unit tests that fail on N10, N11, N12, N31, N38 and N39 (X26 and X29 to X31 are templates; the existing `RaisingStream`, `Fault`, close fault and `Raised` suffice) | Open (recommendation) |
| F-29 | LOW | Plan Revision 11 § Validation, required tokens ("No name that carries them contains ... `usage`, ... `output`") | `test_main_error_stream_fault_a_failing_write_of_a_usage_error_ends_through_the_handler` (18 items) and `test_main_error_stream_fault_with_working_streams_a_usage_error_still_exits_2` (3 items) contain `usage`. AC14's row `-k "usage or environment"` selects 87 tests (66 in round 5). Harmless, because they are AC14 tests, but it deviates from the approved naming rule | `uv run pytest tests/unit/ingest -q -k "usage or environment"` gives 87 passed (rerun) | Rename the two tests without `usage`, or the architect relaxes the rule | Open |
| F-12 | LOW (carried, partially resolved) | harny-audit step 4 (outcome state); plan § Rollout | At `c20827d` these are stale. `tasks.md` § Status (line 8) ends "then the test-writer writes the red tests, the executor fixes without editing tests, and the audit round 6 follows" and names PR #26's head as `5574cd6`. O10 round 5 rework step 1 says "this file Revision 8 (pending)". § Working state Phase says "the audit round 5 responses Revision 13/11/8 are pending the human's approval", and "Updated: 2026-10-21" while it holds a 2026-10-22 entry. The "Round 5 green evidence, audit reservations" entry says "uncommitted, awaiting the human's review before commit", but it is `c20827d`; it was also committed in `c70a6bd`, before the tests and the fix it describes. § Finding responses F-23, F-24, F-26 say "the revision stays pending approval" and F-25 "pending approval". § Checkpoint says "the F-21 README to-do of Revision 6 is open" and "Next: the round 5 rework of O10 ... and the audit round 6". The plan's heading "Audit round 5 responses (2026-10-21; pending the human's approval)" and its sentence "Nothing is implemented before the human approves this revision" contradict its Approval line. The Approval lines and revision logs of the three files agree with each other | The next role reads that the specs await approval and that the fix is not committed | § Status, § Working state, § Checkpoint, O10 and § Finding responses describe `c20827d`, the CI of `c20827d` and this round; the plan heading drops "pending" | Open |

## Answers to the round 6 questions

**1. `SystemExit` identity and precedence (D-1).** It is never converted, lost,
replaced or turned into a result line at any place the rule names. Code reading,
tests and experiments agree:
- Recovery window. `_recovery_step` (207-208) passes a `SystemExit` with no line. When a window operation's line raises, `_prevailing` (179-190) returns the `SystemExit`, the first of two. `_reconnect` keeps it across the close of the second repository (307-314). `raise ... from None` sets only `__cause__` and `__suppress_context__` on the same object. Tests: `system_exit_window` (a) to (e) with identity (`stop is exits.first`). X29 and X30 pin the first-of-two and no-line parts (F-28).
- K. `_cleanup_step` and K catch `Exception` only (730, 806), and `_ingest_through` catches `KeyboardInterrupt` and `Exception` only, so a `SystemExit` raised in K propagates and K never returns an outcome for it. X31 (F-28: no permanent test; N39 survives).
- Final close while propagating. `run_ingest` binds the propagating exception (1266-1268). `_close_while_propagating` (1290-1301) attempts each unclosed repository once (a snapshot tuple), drops what the close raises while a `SystemExit` propagates, and the bare `raise` re-raises the same object. While a `KeyboardInterrupt` propagates, a `SystemExit` or a `KeyboardInterrupt` from the close is raised in its place (the close's own object). Tests: `system_exit_final_close` (g), (h) and `close_while_propagating`. N32 6 and N33 5 failed.
- Final close after an outcome. `_close_after_outcome` (1312-1316) raises the close's `SystemExit` and returns no outcome. Test (f). N34 6 failed.
- Step 7, the source close. `_invoke` (347-358) sets `exiting` for a `SystemExit` from step 4, 5 or 6. In the `finally`, the close's `KeyboardInterrupt`, `Exception` or second `SystemExit` is dropped while exiting. When not exiting, an `Exception` is suppressed, and a `KeyboardInterrupt` or a `SystemExit` from the close propagates in place of the return or of a propagating `KeyboardInterrupt`, as the plan's step 7 says. Tests: `system_exit_command_end` (l) and (m). N20, N21 and N22 killed.
- Writing the result. `_attempt` (227-237) catches `Exception` and `KeyboardInterrupt` only, so a `SystemExit` stops the remaining writes and escapes. Tests (i) to (k). N23 4 failed.
- Step 1. The command's step 1 catches `ValueError` only (381-386). `main` catches `KeyboardInterrupt` and `Exception` only. Tests: `main_parse_interrupt`, `main_wiring_interrupt`, `main_error_stream_fault` and `main_help_stream_fault`, each with a `SystemExit` case checked by identity. N5 139 failed and N6 15 failed.
- Command level, in every case: the exit code is the `SystemExit`'s own, and stdout is empty unless the result line was written before it (exactly `<A> succeeded` in (m)). No `interrupted` or `unexpected error` line is written after it, and no traceback. The stored run keeps its state (`succeeded` in `exit_code_system_exit_final_close`, `running` in (l)). The object is the same one, checked by identity in every new test.
- Real process (X27): `SystemExit("synthetic text")` from `default_wiring` exits 1 with Python's own `synthetic text` line, as the plan's note on a non-integer code says.

**2. The handler of `main` (D-3 B, D-4, D-5).**
- Conforms to plan § Public names: one `try` around the whole body, exactly two handlers, one attempt of the handler's line (`_exit_after_writing`), `SystemExit` never caught, nothing on stdout, no second call of the command.
- CLI-1 to CLI-3 with working streams:
  - `tests/unit/test_cli.py`: 2 passed. Unchanged against `main` and against `2e6edcd` (empty diff).
  - X27, real process: usage error 2 with the usage and the message, bare command 2 with the usage, `POSTGRES_DB is not set` 2, `--version` 0.
  - The integration `cli_` tests: 17 passed.
- Ctrl+C at every point gives 130 without a traceback:
  - during parsing, through `request_from_arguments` and through `version` in `build_parser`;
  - during wiring, through `default_wiring`;
  - in the command's step 1 and during the usage write, by `argparse` and by the command;
  - in the handler's own line, X26 only (F-28);
  - between the command's return and `raise SystemExit(code)`, by construction (no injection point).
- Other exceptions give 1. No second attempt: each test counts the faulted message as attempted once, and N7 (the handler's line written twice) is killed by 42 tests.
- `argparse` is not patched: `test_main_help_stream_fault_argparse_itself_is_not_patched` checks identity, `__module__` and the code file.
- The class structure is conformant. The plan allows "the existing `_IngestParser`, or a CLI parser class that `_IngestParser` extends". With the second option the subparser's class must be `_IngestParser`, which carries the `request_from_arguments` check, so "used for the `ingest` subparser" can only mean that the subparser is an instance of the one class that holds the adaptation. The override exists once, in `_CliParser`; `_IngestParser` adds no writing logic, and both parsers are `_CliParser` instances. Reading it as one class object would make the plan's second option impossible without running the ingest check on the main parser. No spec decision is needed. N3 (main parser plain) and N4 (subparser not extending `_CliParser`) are killed.
- `AttributeError` suppression in `_print_message` is conformant. It reproduces `argparse`'s own rule (Python 3.13 `argparse.py:2630-2636` suppresses `AttributeError` and `OSError`), so a `None` stream still behaves as `argparse` does, and only `OSError` changes, as D-5 requires.
- `file or sys.stderr` matches `argparse`'s `file = file or _sys.stderr`. N15 (`sys.stdout` there) survives and is equivalent: every caller in 3.13 passes a file (`print_usage` and `print_help` default to `sys.stdout` before the call, `exit` passes `sys.stderr`, the version action passes `sys.stdout`).
- No 3.13 path writes without `_print_message`: the only `.write(` in `argparse.py` is at 2634. The writers are `print_usage`, `print_help`, `exit(message=...)`, `error`, `_VersionAction`, `_HelpAction` through `print_help`, and `_warning`. `format_help` and `format_usage` do not write.
- `__context__`: the `SystemExit(130)` or `SystemExit(1)` that `main` raises inside its handlers carries the original exception as `__context__` (X26). A `SystemExit` from the handler's line keeps its identity, but Python sets its `__context__` to the handled exception. The interpreter prints nothing for an integer `SystemExit`, so neither shows: X27's stderr is exactly `interrupted`.
- Real-process caveat: F-27. With a real closed stdout pipe, `--version` and `--help` exit 120, not 1.

**3. Paths with no permanent test.** The coverage run gives 2775 passed and TOTAL 98 %
(rerun, Windows; CI on Linux the same three files).
- `ingest_use_case.py` misses 388-389 and 598 only. They are still the two F-20 limitations accepted on 2026-10-18: 388-389 is the re-check path of `append_event` lost again on the second repository (`raise _ConnectionUnconfirmed`), and 598 is a normal-path append whose recovery is not confirmed (`return _unconfirmed(...)`). The code is unchanged since round 5 and the lines did not shift.
- `ingest_command.py` is at 100 %.
- `cli.py` misses line 90 (`code = EXIT_INTERRUPTED`): a Ctrl+C that lands while `main`'s handler writes its own line.
  - Required: plan § Public names, "The handler of `main`": "what that one attempt raises: a `KeyboardInterrupt` makes the code 130".
  - Scenario X26: a `MemoryError` from `default_wiring` makes the handler write `unexpected error: MemoryError`, and a Ctrl+C lands in that write. The code gives `SystemExit(130)`, stdout empty, no traceback. Without lines 89-90 the Ctrl+C would escape `main` with a traceback (N10). With line 90 replaced by `pass` the code would be 1 (N12).
  - Verdict: compliant, untested. Severity LOW (F-28). A permanent test should exist, cheaply, with the existing `RaisingStream` on `sys.stderr` aimed at `unexpected error` or `interrupted`. The same test can also pin the `SystemExit` row of the D-1 table for the handler's line (N11).
- Other uncovered lines of the feature, all pre-existing and outside the changed code: `ingestion_catalogue.py:168` and `system_clock.py:11`, as in round 5. The rest are F1 to F3 lines.

**4. A refused failure-path append, then a Ctrl+C in its line (F-23, D-2 option 1).**
- Code: `_close_failed` (523-534) suppresses the refusal only after `append_event` wrote its line inside `_reporting_failure`. A `KeyboardInterrupt` or a `MemoryError` from that line leaves `_close_failed`, which catches only `_ConnectionUnconfirmed` and `PersistenceError`. `_ingest_through` then hands it to K on the current repository. K reads the run, appends `run-interrupted` (or `unexpected-error`) for the page and calls `finish_run(FAILED)`. The refused event is never appended again.
- Tests (rerun): `refusal_then_interrupt` 40 (page-failed, storage-failed, page-completed and the final `finish_run(succeeded)`, each with two refusal flavors, two interruptions and two moments, plus case (v) with K's own append refused, which leaves the run `running`) and `exit_code_refusal_then_interrupt` 2 (exit 130 with `<A> failed`, and with `<A> running`).
- E-D2 kills the opposite behavior (28 failed).
- The spec text is consistent:
  - AC6 (e) keeps "no further event" for how a refusal is answered and adds that a later interruption is AC7's cleanup.
  - The "Refused writes" table's failure-path row points to K's "After any other refusal".
  - K's bullet lists the same four refusals.
  - N-4 keeps a refused `finish_run(FAILED)` outside K.
  - The intro sentence "never enters § State machine K" is about the refusal itself, not a later exception, so it does not contradict the row.
  - No residual contradiction was found.

**7. The environment-dependent `FileNotFoundError`.**
- `test_storage_a_regular_file_at_observations_stops_the_run` passed in every run of this round: the full suite with the database (2775), the suite without it (2509), `tests/unit/ingest` (1348), the scratch baseline (1350), 57 mutant runs where it was not the target, and the test alone 5 times.
- No other environment-dependent or intermittent failure was seen.
- Recorded separately: the round 5 explanation (a second session sharing `--basetemp` deletes the first one's folder) still stands. No session of this round shared a `--basetemp`, and the reported failure did not recur.

## Executor and test-writer choices where the plan was silent

| Choice | Assessment |
|---|---|
| `_CliParser` for the main parser and `_IngestParser(_CliParser)` for the subparser | Conformant with D-5 option a (answer 2) |
| `_print_message` keeps `suppress(AttributeError)` | Conformant: `argparse`'s own rule except `OSError` |
| `_exit_after_writing` wraps one `print` in `suppress(Exception)` around an inner `except KeyboardInterrupt` | Conformant with "what that one attempt raises"; untested branch (F-28) |
| `_print_running` sets `result_written` before printing | Harmless and defensive: only one handler runs per invocation (N24 equivalent) |
| Step 7 uses an `exiting` flag set by `except SystemExit` around steps 3 to 6 | Conformant; a Ctrl+C between `except SystemExit:` and `exiting = True` is a bytecode gap (checklist) |
| The `main` tests set `sys.stdout` and `sys.stderr` with `monkeypatch` to `io.StringIO` or `RaisingStream` instead of `capsys` | A compliant alternative to the plan's "stdout read with `capsys`": no new setup, and the seams table already says "no `capsys` in these cases" for stderr |
| A local `Raised` helper in each test file records the exception objects | Test-only, no new double; it gives the identity checks D-1 needs |

## Accepted limitations

Lines 388-389 and 598 of `ingest_use_case.py` remain the two limitations the human
accepted on 2026-10-18. Their code is unchanged since round 5. They stay accepted.

## Defect-hunting checklist (both modules and `cli.py` against the state machines)

| Area | Result |
|---|---|
| Opening and first exclusion | Hold (E-F16a killed) |
| C, the window | Hold; `SystemExit` precedence holds (X29); no line for a `SystemExit` (X30) |
| C, repeats, re-check, P-2, second loss | Hold (`connection_loss` 43, `p2_read_run_loss_line` 4; N37 killed) |
| K on the current repository; "After any other refusal" | Hold (E-N2, E-D2 killed; X31) |
| T, R, H, I | Hold (`pre_run_database_error` 59, `reconcile` 34, `chain` 197) |
| Refused writes, never retried | Hold (N42, N43, N44 killed) |
| Write-once evidence; no retries | Hold (`no_retry` 6; F1 store unchanged against `main`) |
| Secrets, URLs, tracebacks, exception text | Hold in-process; a real closed stdout pipe makes Python print `OSError: [Errno 22] Invalid argument` at exit (F-27) |
| Exactly one stdout line; writing the result | Hold in-process (N25, N26, N27 killed); real buffered stdout: F-27 |
| Final close; step 7 | Hold (answer 1) |
| `main` and the parsers | Hold (answer 2); the handler line is untested (F-28) |
| `sys.stderr` is `None` (a GUI-subsystem launch) | `print(..., file=None)` writes to stdout, so the handler's line or a command line would go to stdout. Pre-existing for the command, not a realistic console-script case. Noted, not a finding |
| Asynchronous exceptions between bytecodes | A Ctrl+C can land between `except SystemExit:` and `exiting = True` (`ingest_command.py:347-348`), between `main`'s `except` and the call of `_exit_after_writing`, and between that call's `print` and its `raise SystemExit(code)`. As in round 5, pure Python cannot close such gaps without masking signals. Noted, not a finding |

## AC results

| AC | Status | Evidence |
|---|---|---|
| AC1 | PASS | `-k success` 9; integration `-k e2e_success` 2 (rerun) |
| AC2 | PASS | `-k repeat` 22; `-k e2e_repeat` 2 (rerun) |
| AC3 | PASS | `-k last_page` 41, `last_page_p3` 6, `e2e_last_page` 2 (rerun) |
| AC4 | PASS | `-k failure_with_response` 16; `-k e2e_failure` 5 (rerun) |
| AC5 | PASS | `-k failure_without_response` 6 (rerun) |
| AC6 | PASS | `-k storage` 24, `database_refusal` 57, `read_back_record_failure` 4, `refusal_not_retried` 37, `refusal_then_interrupt` 42 (rerun); (e) is consistent after D-2 (answer 4) |
| AC7 | PASS (note F-28) | `-k "interrupt or exit_code"` 413; `interrupt_during_record or cleanup_read_back` 14; `interrupt_after_finish` 11; `cleanup_database_error or final_finish_read_run or output_database_error` 49; `reconnect_exclusion_interrupt or reconnect_open_interrupt` 93; the F-21 row 56; `final_close_error or final_close_interrupt` 20; `unexpected_cleanup_interrupt` 18; `recovery_double_fault` 15; the F-24 row 27; the F-25 row 23 (rerun) |
| AC8 | PASS | `-k connection_loss` 43, `connection_loss_final_finish` 12, `start_run_unconfirmed` 12, `start_run_second_loss` 34; integration `test_ingest_connection_loss.py` 7, `final_finish` 4 (rerun) |
| AC9 | PASS | `-k resume` 24; `-k e2e_resume` 5 (rerun) |
| AC10 | PASS | `-k reconcile` 34; `-k e2e_reconcile` 6; `reconcile_os_error` 4 (rerun) |
| AC11 | PASS | `-k closed_run` 3; `interrupt_after_finish` 11; `interrupted_outcome_close` 1 (rerun) |
| AC12 | PASS | `-k "execution_id or identity"` 94 (rerun) |
| AC13 | PASS | `-k "scope or catalogue"` 124 (rerun) |
| AC14 | PASS in-process (notes F-27, F-29) | `-k "usage or environment"` 87; `source_configuration or order_of_invocation` 30; the F-26 row 67; `tests/unit/test_cli.py` 2; integration `cli_` 17 (rerun). X27: a real process gives 2, 2, 2 and 0 with working streams, and 130 and 1 for a Ctrl+C and a `MemoryError` during wiring. A real closed stdout pipe on `--version` or `--help` gives 120, not 1 (F-27) |
| AC15 | FAIL for a real buffered stdout (F-27); PASS in-process (note F-28) | `-k "output or logger"` 93; `output_escaping_exception` 12; progress group 24; `pre_run_database_error` 59; `repository_open_error or single_result_line` 19; `result_line_stream_fault or handler_stream_fault` 29; `generic_fallback` 2; the F-24 row 27; the F-26 row 67 (rerun). X28: a confirmed run with a closed stdout pipe exits 120 with Python's `Exception ignored ... OSError: [Errno 22] Invalid argument`, not 1 |
| AC16 | PASS | integration `-k migrations` 11; `test_persistence_error_hierarchy.py` 3; lock and runner 23; `git diff 2e6edcd --numstat -- tests/integration/test_postgres_migrations.py` is `3 0` (rerun) |
| AC17 | PASS | `-k no_retry` 6 (rerun) |
| AC18 | PASS | `-k layer` 16. The grep of `application/` for `SELECT `, `INSERT `, `UPDATE `, `DELETE `, `objects/`, `observations/`, `.json`, `advisory`, `pg_`, `psycopg` and `httpx` finds nothing. `interfaces` imports neither `httpx` nor `psycopg`. `git diff main --stat -- pyproject.toml uv.lock` is empty. Against `2e6edcd`, `pyproject.toml` shows only the two F-1 keys and three comment lines, and `uv.lock` has no diff. mypy: 52 files clean (rerun) |
| AC19 | PASS | `uv run --env-file .env pytest tests/unit/ingest tests/integration/ingest -q` gives 1432 passed. No file under the real `data/` before or after. No `ecpq_test_` database left (count 0). The new tests use doubles and in-memory streams only (rerun) |
| AC20 | PASS | 2775 passed. `tests/unit/test_cli.py` is unchanged against `main` and `2e6edcd`. The only pre-F4 test file changed since `2e6edcd` is `test_postgres_migrations.py` (`3 0`). `git diff main -U0 -- tests` removes 2 lines, the same as round 5 (an import widened, one docstring line); `22cd04c` is +1585/-0 and `c20827d` touches no test. `git ls-files .env` is empty; `git diff main --check` and `git diff --check` are clean. ruff, format (120 files), mypy and the doctor (`31 ok, 0 skipped, 0 warned, 0 failed`) pass; `--version` gives `ec-procurement-quality 0.1.0`. No migration added; `migrations/` holds `0001_initial_schema.sql` only (rerun) |
| AC21 | FAIL (F-27) | README § Ingesting was read sentence by sentence against the code. Lines 246-289, 296-307 and the stale-session procedure match. Lines 290-295 ("for example, a closed output stream ... 1 for any other write failure") are false for a real closed stdout pipe (exit 120, X28). Plan Revision 11 required no README change for D-1 to D-5, and the README names no `SystemExit` case or usage-write failure; that omission is per the approved plan and not a finding. AGENTS.md, `docs/architecture.md` and CHANGELOG are unchanged since `main` (rerun, inspection) |
| AC22 | PASS | listing 25 (rerun) |
| AC23 | PASS | `test_postgres_runs_and_exclusion.py` 24 (rerun) |
| AC24 | PASS | `-k chain` 197, `chain_last_page` 33, `e2e_chain_last_page` 3, `chain_unreadable_record` 12 (rerun) |
| AC25 | PASS | `-k "paths or environment"` 34; integration `-k root` 2 (rerun) |

Plan decisions P-1 to P-5, F-1 to F-3 and D-1 to D-5 were checked. P-1 to P-5 and F-1 to
F-3 are unchanged since round 5 and still hold (as above). D-1 is implemented (answer 1).
D-2 is kept and pinned (answer 4). D-3 is implemented (answer 2). For D-4, a usage
error that cannot be written gives 1 (`main_error_stream_fault`, `OSError` and
`MemoryError` cases). D-5 is implemented in-process (`main_help_stream_fault`). A real
closed pipe gives 120 (F-27).

## Binding-constraint compliance

| Constraint | Status | Evidence |
|---|---|---|
| Layer placement (ADR 0001, AC18) | PASS | Layer tests 16; grep clean; `interfaces` imports |
| Public names and signatures | PASS | Pinned types and signatures unchanged; propagation list (Revision 11) holds |
| "`SystemExit`" (D-1) and its combination table | PASS (note F-28) | Answer 1 |
| The handler of `main` (D-3, D-4) and the one local parser class (D-5) | PASS (notes F-27, F-28) | Answer 2 |
| CLI arguments, configuration, CLI-1 to CLI-3 | PASS | `test_cli.py` unchanged, 2 passed; X27 |
| Order of an invocation (with "Where step 1 runs") | PASS | Answer 2; the command's step 1 is unchanged |
| Exit codes | PASS in-process; real buffered stdout gives 120 (F-27) | `_EXIT_CODES`, `_settled_code`, `main` |
| Output, "Writing the result" | PASS as scoped by the plan ("raised while it writes"); F-27 for the wider AC15 sentence | N25, N26, N27 killed |
| Audit details (closed catalogue) | PASS | `assert_follows_catalogue` in the new tests too |
| State machine P, "Refused writes", "never retried" | PASS | N42, N43, N44, E-D2 killed |
| State machine C, "The explicit record", "Two or more exceptions" | PASS (note F-28) | N36, N41, E-F18 killed; X29 |
| State machine K (with "After any other refusal") | PASS (note F-28) | E-N2, E-D2 killed; X31 |
| State machines T, R, H, I | PASS | Unchanged since round 5; E-F06, E-F10 killed |
| F1 and F3 port extensions | PASS | Listing 25; runs and exclusion 24 |
| No schema change; write-once evidence | PASS | `migrations/` unchanged; `infrastructure/` and `domain/` have no diff against `main` |
| No dependency (AGENTS.md, PT-11) | PASS | `uv.lock` has no diff; `pyproject.toml` only the F-1 keys (against `2e6edcd`) |
| ADR 0006 (configuration before migrations) | PASS | E-F03 killed |
| R-6, N3 (no chain or `__context__` printed) | PASS in-process (X27: stderr `interrupted` only); F-27 for Python's exit-time report | |
| R-7 (`httpcore` above `DEBUG`) | PASS | `_httpcore_above_debug` unchanged |
| SA-13, PS-13 (one source, at most two repositories, all closed) | PASS | `opens <= 2` and `all_closed` in the new tests |
| Q4 (one ingest per database) | PASS | No write without the exclusion on any path found |
| Tests (no network, no real `data/raw/`, throwaway databases) | PASS | Guards pass; `data/` empty; 0 leftover databases; the no-database run skips 266 integration tests as designed |
| `.env` never read by code or committed | PASS | `git ls-files .env` is empty. The auditor never read, printed or copied it: the database-count script reads only the variables `uv run --env-file` loaded and prints only a count |

## Test coverage

| AC | Tests (file) | Status |
|---|---|---|
| AC1 to AC5 | as in round 5 (`tests/unit/ingest/test_ingest_use_case.py`, `tests/integration/ingest/test_ingest_end_to_end.py`) | PASS |
| AC6 | `storage`, `database_refusal`, `read_back_record_failure`, `refusal_not_retried`, `refusal_then_interrupt` (unit); `exit_code_refusal_not_retried`, `exit_code_refusal_then_interrupt` (`tests/unit/ingest/test_ingest_command.py`) | PASS |
| AC7 | as in round 5, plus `system_exit_window`, `system_exit_final_close`, `window_line_fault`, `close_while_propagating`, `interrupted_outcome_close`, `refusal_then_interrupt` (unit) and `exit_code_system_exit_final_close`, `system_exit_command_end` (command) | PASS (F-28 regression gaps) |
| AC8 | as in round 5, plus `system_exit_window`, `p2_read_run_loss_line` | PASS |
| AC9 to AC13 | as in round 5 | PASS |
| AC14 | `usage`, `environment`, `source_configuration`, `order_of_invocation`, `main_parse_interrupt`, `main_wiring_interrupt`, `main_error_stream_fault`, `main_help_stream_fault` (`tests/unit/ingest/test_ingest_command.py`); `tests/unit/test_cli.py`; integration `cli_` | PASS in-process; no real-process test (F-27) |
| AC15 | as in round 5, plus the F-24 and F-26 rows | PASS in-process; F-27 untestable at the approved seam; F-28 |
| AC16 to AC25 | as in round 5 | PASS (AC21 is inspection: FAIL, F-27) |

Coverage: TOTAL 98 % locally (2775 passed, Windows) and in CI (2775 passed, Linux).
`ingest_use_case.py` misses 388-389 and 598 (accepted); `ingest_command.py` is at 100 %;
`cli.py` misses 90 (F-28).

### Tier Results

| Tier | Tests found | ACs verified | Setup matches § Validation | Ran | Status | Finding |
|---|---|---|---|---|---|---|
| unit | `tests/unit/ingest/` (1348 tests, +159 this round), `test_local_disk_raw_evidence_store_listing.py` (25), `test_persistence_error_hierarchy.py` (3), `tests/unit/test_cli.py` (2, unchanged) | AC1 to AC18, AC22, AC24, AC25, including the four Revision 11 rows and their fourteen tokens | Yes. No dev dependency, config or script was added. The new tests use the seams the plan names (`Fault`, close fault, raising reporter, `RaisingStream`, the source double, `monkeypatch` on `cli.request_from_arguments`, `cli.version`, `cli.default_wiring`, `cli.run_ingest_command`, `sys.stdout` and `sys.stderr`), plus a local `Raised` recorder. `io.StringIO` through `monkeypatch` stands in for `capsys` (a compliant alternative). Two names break the token rule (F-29) | rerun: every focused row passed (36 unit commands, plus the 13 AC tokens of the AC table) | PASS | F-28, F-29 |
| integration | `tests/integration/ingest/` (84), `test_postgres_migration_lock_error.py`, the PS-4 edit | AC1 to AC4, AC8 to AC10, AC16, AC19, AC23 to AC25 | Yes; unchanged since round 5 | rerun with `--env-file .env` (10 focused commands, all passed); CI reused | PASS | none |
| static | `uv run mypy .` | AC18 | Yes | rerun: 52 files clean | PASS | none |
| command | ruff, format, mypy, doctor, `--version`, git checks | AC20 | Yes | rerun: all clean | PASS | none |
| manual | documentation inspection | AC21 | n/a | rerun (inspection) | FAIL | F-27 |

No test exists at a tier that § Validation does not name. No real-process test of the
CLI exists, and § Validation names none; closing F-27 with option (b) needs one, with
the human's approval.

## Mutants (scratch copy, `tests/unit/ingest` and `tests/unit/test_cli.py`, 1350 tests)

Each mutant replaced exact text in the scratch copy. After every mutant the copy was
restored and compared byte for byte with the pristine archive: 57 of 57 identical.

| Id | Mutant | Result |
|---|---|---|
| N1 | `_print_message` swallows `OSError` again | killed, 13 |
| N2 | `_CliParser` without the override | killed, 13 |
| N3 | main parser plain `argparse.ArgumentParser` | killed, 8 |
| N4 | `_IngestParser` does not extend `_CliParser` | killed, 5 |
| N5 | `main` catches `BaseException` (a `SystemExit` caught) | killed, 139 |
| N6 | `main` re-creates the `SystemExit` (identity lost) | killed, 15 |
| N7 | handler line written twice | killed, 42 |
| N8 | Ctrl+C handler exits 0 | killed, 15 |
| N9 | `Exception` handler exits 2 | killed, 30 |
| N10 | no `KeyboardInterrupt` branch on the handler line (`cli.py:89-90`) | **survived** (F-28) |
| N11 | the handler line swallows a `SystemExit` | **survived** (F-28) |
| N12 | Ctrl+C on the handler line keeps code 1 (`cli.py:90`) | **survived** (F-28) |
| N13 | handler line on stdout | killed, 45 |
| N14 | handler line names more than the class | killed, 12 |
| N15 | `_print_message` falls back to `sys.stdout` | survived (equivalent: no caller passes a falsy file) |
| N16 | `build_parser()` outside the handler | killed, 2 |
| N17 | `main` returns instead of raising the command's code | killed, 169 |
| N20 | step 7 ignores the `exiting` flag | killed, 1 |
| N21 | step 7 never sets `exiting` | killed, 1 |
| N22 | step 7 swallows every close exception | killed, 9 |
| N23 | `_attempt` catches `SystemExit` | killed, 4 |
| N24 | `_print_running` does not set `result_written` | survived (equivalent: one handler per invocation) |
| N25 | `_settled_code` keeps the code on a write error (M11) | killed, 10 |
| N26 | `_report` does not set `result_written` (M9) | killed, 4 |
| N27 | a Ctrl+C on a write does not give 130 | killed, 9 |
| N30 | `_prevailing` ranks Ctrl+C above `SystemExit` (M5) | killed, 8 |
| N31 | `_prevailing`: the later of two of a kind wins | **survived** (F-28; X29 shows the code is right) |
| N32 | the close's Ctrl+C replaces a propagating `SystemExit` | killed, 6 |
| N33 | the final close swallows its Ctrl+C while another propagates (M15) | killed, 5 |
| N34 | the final close after an outcome swallows a `SystemExit` (M14) | killed, 6 |
| N35 | `_close_remaining`: the last raised wins | survived (equivalent: at most one repository is left for the final close) |
| N36 | a window line error replaces `_prevailing` (M16) | killed, 8 |
| N37 | the P-2 `read_run` without `on_loss` (M28) | killed, 4 |
| N38 | `_recovery_step` writes a line for a `SystemExit` | **survived** (F-28; X30) |
| N39 | K turns a `SystemExit` into an outcome | **survived** (F-28; X31) |
| N40 | `_ingest_through` handles `SystemExit` like a Ctrl+C | killed, 22 |
| N41 | `drop_current` keeps the repository current (M1) | killed, 124 |
| N42 | no pending clear on a refused read-back record | killed, 8 |
| N43 | no pending clear on a refused record (M7) | killed, 19 |
| N44 | `_close_failed` without `drop_current` (M3) | killed, 8 |
| N45 | `run_ingest` passes a wrong propagating exception | killed, 6 |
| N46 | `drop_current` without its `None` guard | survived (equivalent: never called with no current repository on a reachable path) |
| E-F01 to E-F22, E-N2, E-D2 | the round 1 to 4 fixes reverted, and D-2 reversed (F-01, F-02, F-03, F-04, F-05, F-06, F-07, F-10, F-13, F-16 a, F-18, F-20, F-22, N-2, D-2) | killed, 4, 4, 16, 24, 9, 3, 8, 2, 57, 1, 48, 23, 10, 25, 28 |

47 killed, 10 survived. Four survivors are equivalent (N15, N24, N35, N46). Six are
regression gaps with correct code (N10, N11, N12, N31, N38, N39: F-28).

## Commands run (2026-10-22, repository root, `c20827d`)

| Command | Result | Label |
|---|---|---|
| `docker compose ps` | postgres `Up (healthy)` | rerun |
| `uv sync --locked` | ok, 25 packages | rerun |
| `uv run pytest -q` (no `--env-file`) | 2509 passed, 266 skipped | rerun |
| `uv run --env-file .env pytest --cov=ec_procurement_quality --cov-report=term-missing -q` | 2775 passed, 0 skipped, TOTAL 98 %; `ingest_use_case.py` missing 388-389, 598; `cli.py` missing 90 | rerun |
| `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy .` | All checks passed; 120 files already formatted; Success, 52 source files | rerun |
| `uv run node .sdd/doctor/run-doctor.mjs` | 31 ok, 0 skipped, 0 warned, 0 failed | rerun |
| `uv run ec-procurement-quality --version` | `ec-procurement-quality 0.1.0` | rerun |
| Every `pytest` command of plan § Validation (49 focused commands; the coverage and full-suite ones above) | all passed (counts in § AC results) | rerun |
| The 13 unit and 5 integration AC tokens of § AC results | all passed | rerun |
| `test_storage_a_regular_file_at_observations_stops_the_run` alone, 5 times | 5 passed | rerun |
| AC18 grep of `application/`; `interfaces` imports | no match; no `httpx` or `psycopg` | rerun |
| `git diff main --stat -- pyproject.toml uv.lock`; `git diff 2e6edcd -- pyproject.toml`; `git diff 2e6edcd --stat -- uv.lock` | empty; the two F-1 keys and three comment lines; empty | rerun |
| `git diff main --stat` for `tests/unit/test_cli.py`, `specs/current`, `docs/adr`, `compose.yaml`, `.env.example`, `migrations`, `docs/glossary.md`, `docs/architecture.md`, `AGENTS.md`, `CHANGELOG.md`, `domain`, `infrastructure` | empty | rerun |
| `git diff 2e6edcd --name-status -- tests` (modified pre-F4 files) | `M tests/integration/test_postgres_migrations.py` only, `3 0` | rerun |
| `git diff main -U0 -- tests` removed lines; per-commit file lists of `main..HEAD` | 2 (as in round 5); `22cd04c` tests only (+1585/-0), `c20827d` src only | rerun |
| `git ls-files .env`; `git diff main --check`; `git diff --check`; `git status --short` | empty; clean; clean; clean | rerun |
| Leftover `ecpq_test_` databases (count only) | 0 | rerun |
| Files under the real `data/` | 0 | rerun |
| `gh pr checks 26`; `gh pr view 26` | `feedback` pass, `tests` pass; open, head `c20827d`, `CLEAN`, auto-merge off | rerun |
| `gh run view 39782097174` (`Tests`, head `c20827d`) | success; 2775 passed, TOTAL 98 %, `ingest_use_case.py` 388-389, 598, `cli.py` 90 (Linux) | reused |
| `gh run view 39782097285` (`harny feedback`, head `c20827d`) | success; `harny-feedback: 2 of 2 command(s) ran, 0 skipped.` | reused |
| X26 (handler line, through `main`), X27 (real process: `main` paths and closed pipes), X28 (real process: confirmed result, closed stdout pipe), X29 to X31 (repository doubles) | quoted in § Findings and § Answers | experiment |
| 57 mutants (N1 to N46, E-F01 to E-D2) | 47 killed, 10 survived | experiment |

## Conventions and feedback

- harny-standards, checked against `AGENTS.md` (the project's conventions document):
  - layer boundaries hold;
  - raw responses are never overwritten;
  - no SERCOP contract is invented, and only synthetic `.invalid` data is used;
  - no dependency, infrastructure, framework or service was added; the `argparse` subclass is the standard library;
  - no secret is in source, tests or docs (doctor gitleaks and the CI secret scan pass);
  - verification was run and reported (`tasks.md`, round 5 red and green evidence).

  No violation was found. The stale record of `tasks.md` is F-12.
- harny-feedback:
  - `.github/workflows/harny-feedback.yml` exists, and its run at `c20827d` is green with 2 of 2 commands run (not 0).
  - The per-turn hooks are configured in `.claude/settings.json` (PostToolUse, Stop, SubagentStop), and `.sdd/feedback/.turns/` is live.
  - Whether they fired and were heeded during the executor's turns is `unavailable`: turn files are not kept.
  - Lint and type-check were run only as the AC20 commands, not as feedback evidence.

## Reservations carried forward

- Persistence U1: the real commit-in-flight case is still untested against PostgreSQL.
- Persistence N5: the reconciliation reads run in separate snapshots; safe under the
  exclusion.
- Raw-evidence N2, source-access R-6, R-7, R-11 and raw-evidence N3: hold (F-27 adds a
  Python exit-time report outside F4's code).
- The two F-20 limitations accepted on 2026-10-18 (388-389, 598).
- Source-access U1: open until the human's live run. No document claims that a live run
  happened.

## What could not be verified

- Behavior against the real SERCOP source, the real `data/raw/` and a real `ingest`
  run: out of scope, and it must not be run. F-27 was shown with `run_ingest` replaced
  in a real process.
- F-27 on Linux: the CPython exit-time flush path is platform-independent, but no Linux
  process was run (`unavailable`). On Linux the report is expected to be
  `BrokenPipeError: [Errno 32] Broken pipe`.
- A real Ctrl+C (a console signal) delivered at the bytecode gaps listed in the
  checklist; faults were injected at the call boundaries.
- `pg_terminate_backend` of a real stale session that holds the exclusion.
- That the per-turn feedback hook fired during the executor's rework.

## Audit log

| Round | Date | Verdict | Notes |
|---|---|---|---|
| 1 | 2026-10-18 | REJECTED | At `7603379`. F-01 and F-02 (CRITICAL) and F-03 (HIGH) block; F-04 to F-07 MEDIUM, F-08 to F-12 LOW |
| 2 | 2026-10-18 | REJECTED | At `91bd69d`. F-01 to F-11 resolved. New: F-13 (MEDIUM, blocking), F-14 (MEDIUM, blocking until decided), F-15 to F-17 LOW |
| 3 | 2026-10-18 | REJECTED | At `287946f`. F-13 to F-17 resolved. New: F-18 (HIGH, blocking); F-19 and F-20 LOW; F-12 carried |
| 4 | 2026-10-18 | REJECTED | At `10e126d`. F-18 and F-19 resolved for the two named calls. New: F-21 (MEDIUM, blocking); F-22 LOW; F-12 and F-20 LOW, partly open |
| 5 | 2026-10-21 | APPROVED WITH RESERVATIONS | At `80c8aab` (PR #26). F-20 to F-22 resolved; N-1 to N-11 hold; 2616 tests pass; 40 of 47 mutants killed. New, all LOW: F-23, F-24, F-25, F-26; F-12 carried |
| 6 | 2026-10-22 | REJECTED | At `c20827d` (PR #26; CI green: 2775 passed, feedback 2 of 2). F-23 to F-26 resolved (D-1 to D-5 implemented and pinned); F-01 to F-22 still resolved; 47 of 57 mutants killed. New: F-27 (MEDIUM, blocking: a real closed stdout pipe gives Python's exit 120 and its exit-time `OSError` report, not exit 1 as AC15, AC14 and the README say; present since `80c8aab`), F-28 (LOW, untested D-1 and D-3 paths), F-29 (LOW, test names against the token rule); F-12 LOW carried. The `FileNotFoundError` did not recur. Next: the architect and the human decide F-27's closure |
