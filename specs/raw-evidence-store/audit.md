# Audit: Raw evidence store (F1)

Round 2, 2026-10-09, re-checks the round 1 findings: see § Round 2 below. The § Tier
Results table, the § Findings status column, the § Residual items, the § Audit log and
the § Final verdict are updated to round 2; every other section is the round 1 record,
kept as history.

Round 1, 2026-10-09. Auditor: `sdd-auditor` (harny-audit). Reviewed state: branch
`feat/raw-evidence-store` at `509ca36` (local HEAD, clean working tree), base `main`
(`62afd18`). PR #15 head is `392145f`; `509ca36` differs from it only in
`specs/raw-evidence-store/{intent,execution-plan,tasks}.md` (`git diff --stat 392145f 509ca36`),
so CI results at `392145f` are current for every code, test, doc and config file.
Specs read: `intent.md` Revision 2 (approved), `execution-plan.md` Revision 2, `tasks.md`.
ADRs read: 0002, 0005 (Accepted). Every changed file was read in full:
`domain/content_hash.py`, `domain/raw_evidence.py`, `application/raw_evidence_store.py`,
`infrastructure/local_disk_raw_evidence_store.py`, the four test files, and the
`README.md`, `docs/architecture.md` and `CHANGELOG.md` diffs. `docs/learning/journal.md`
also changed (the human's Day 10 entry); it is outside the plan's ownership, holds no
data or secrets, and is not audited as F1 output.

Human instructions applied (gate 1, Revision 2): the exact record bytes are as built,
not a contract (formatting is not judged); behaviors no AC requires need no test unless
there is a concrete risk; the `0600` mode and atomic write-once publication are judged
separately below; the human-written `ContentHash` and port are audited like the rest.

Evidence labels: `rerun` = run by the auditor in this round; `reused` = taken from a
recorded result whose command, result and tested state are still current;
`unavailable` = could not be produced.

## AC results

| AC | Status | Evidence |
|---|---|---|
| AC1 | PASS | `ContentHash` is a frozen dataclass; `__post_init__` rejects non-`str` and anything not matching `[0-9a-f]{64}` with `fullmatch` (so a trailing newline is rejected); `of()` uses `hashlib.sha256`. `uv run pytest tests/unit/test_content_hash.py -q` -> `17 passed` (rerun): vectors for `b"abc"` and `b""`, equality, `hash()`, set and dict key, uppercase, mixed case, 63, 65, non-hex, empty, newline, leading space, `0x` prefix, reassignment raises. |
| AC2 | PASS | Paths `objects/<xx>/<hex>` and `observations/<id>/<seq>.json` (`_object_path`, `_observation_path`); record keys exactly as pinned (`_serialize`). `-k round_trip` -> `9 passed` (rerun): exact object bytes, `json.loads` of `1.json` equals the pinned record with `-05:00` and the query string, only those two files under the root, `read_content` returns `b"abc"`, `read_observation` equals the returned record, decimal sequence names `0/1/12/100`, text kept as given, deterministic bytes, nothing written outside the root. |
| AC3 | PASS | `_ensure_object` reads an existing object and returns without writing when its hash matches. `-k duplicate` -> `1 passed` (rerun): one object, two observations naming the same `sha256`, object bytes and `st_mtime_ns` unchanged (mtime aged first so a rewrite would show). |
| AC4 | PASS | No status-based branch exists in `store`. `-k error_response` -> `4 passed` (rerun): `429` HTML, `503` empty (`size 0`, `e3b0c442...b855`), truncated `200` JSON; status kept in the return value and the file; exact bytes read back. |
| AC5 | PASS | `store` drops every header whose name lowercases to `set-cookie` (step 1); `Observation._validate_headers` rejects one in any case. `-k set_cookie` (adapter + domain files) -> `7 passed` (rerun): the AC5 header list leaves exactly the three non-cookie pairs in order with the repeat; file bytes contain neither `synthetic-session` nor `synthetic-other`; `SET-COOKIE` and other cases rejected by `Observation`. No request-header parameter exists on the port or the adapter. Mutation check (rerun): disabling the filter fails 2 tests. |
| AC6 | PASS | `read_content`: missing -> `EvidenceNotFoundError`; hash mismatch -> `EvidenceIntegrityError` naming the hexdigest and path only. `-k "corrupt or missing"` -> `16 passed` (rerun), including messages that contain neither body, and corrupt observation files (malformed JSON, empty, non-object, other sequence or execution, missing or extra key, `schema_version 2`, invalid status, naive time). Mutation check (rerun): removing the hash comparison in `read_content` fails 2 tests. |
| AC7 | PASS | Existing object with other bytes -> `EvidenceIntegrityError` before any observation; existing observation compared by bytes, conflict -> `EvidenceIntegrityError`, identical -> no-op. `-k conflict` -> `6 passed` (rerun): planted `b"tampered"` kept and no observation written; other content, status, headers and capture time each rejected with `1.json` bytes and mtime unchanged; identical re-store returns an equal record with bytes and mtimes unchanged. The race branch (name taken between check and link) was checked by a behavioral script (rerun, see A1): integrity error, existing bytes kept. See finding A1 for the test gap. |
| AC8 | PASS | `store` calls `_ensure_object` before `_ensure_observation` (lines 110-112); no cleanup of a published object exists. `-k orphan` -> `2 passed` (rerun) on Windows; `133 passed` on Ubuntu in the `Tests` workflow at `392145f` (reused, CI log). Mutation check (rerun): swapping the two calls fails both orphan tests and the object-conflict test. |
| AC9 | PASS | `_publish_if_absent` writes, flushes and calls `os.fsync` through the `os` module before `os.link`; the temporary file is removed in `finally`. `-k interrupted` -> `1 passed` (rerun): no final object, no observation, no file at all under the root, then a successful retry with exact bytes. |
| AC10 | PASS | All validation happens while building the `Observation` in step 1, before `_publish_if_absent` creates any directory. `-k invalid` (domain + adapter files) -> `38 passed` (rerun): every AC10 value (plus bool sequence, empty method and URL, negative size, leading hyphen, underscore, slash, backslash, newline, non-ASCII digit, float and text sequence) raises `ValueError` and leaves no file; `read_observation("../escape", 1)` raises `ValueError`. Extra check (rerun): malformed header elements (`[1]`, a 3-tuple, a non-`str` name) are also rejected before any file exists. |
| AC11 | PASS | `domain` modules import only stdlib and `domain`; the port imports only stdlib and `domain`; the adapter imports `domain` only (it does not import the port; it satisfies it structurally); nothing imports `interfaces` (Grep of imports, rerun). `uv run pytest tests/unit -q -k "layer or satisfies_port"` -> `7 passed, 126 deselected` and `-k layer` -> `6 passed` (rerun). `mypy` over the whole project: success in the `feedback` job at `392145f`, `2 of 2 command(s) ran, 0 skipped` (reused, CI log; not re-run per harny-feedback). Red check (rerun, scratch copy): changing the adapter's `read_content` return type to `str` makes `mypy` report the protocol conflict at `test_local_disk_raw_evidence_store.py:632`, so the `satisfies_port` seam is live. Strict flags apply through `[[tool.mypy.overrides]] module = "ec_procurement_quality.domain.*"` (pyproject read). |
| AC12 | PASS | `uv run pytest -q` -> `133 passed`; the 7 F0 tests run alone -> `7 passed`; `test_cli.py` and the old `test_layers.py` lines are unchanged (`git diff main...HEAD`: 0 lines for `test_cli.py`, 0 removed lines for `test_layers.py`) (rerun). `ruff format --check .` -> `63 files already formatted` (rerun). `ruff check` and `mypy`: green in the `feedback` job (reused, CI). Doctor -> `31 ok, 0 skipped, 0 warned, 0 failed`; `--version` -> `ec-procurement-quality 0.1.0`; `git diff main -- pyproject.toml uv.lock` -> empty; `git check-ignore` prints both paths; `git diff --check` and `git diff --check main...HEAD` clean; `git grep -i -e datosabiertos -e compraspublicas -- tests` -> exit 1 (all rerun). No network use in tests (Grep for `socket`, `urllib`, `http.client`, `requests`, `httpx`: no match, rerun). |
| AC13 | PASS | `git grep -n -i "raw evidence"` matches in all three files; `docs/architecture.md` § Raw evidence boundary links `adr/0005-raw-evidence-store-layout.md`; `git grep -n "four empty layer" -- README.md` -> exit 1 (rerun). By inspection: README no longer calls the layers empty, names the store as a library with no CLI command and no wired root path, and "Planned" no longer lists storage adapters; CHANGELOG § Unreleased § Added lists the store. Every claim matches the code. No Claude or AI attribution in the changed docs, source, tests or the branch's commit messages (rerun). |

## Binding-constraint compliance

| Constraint | Status | Evidence |
|---|---|---|
| Public names and signatures | PASS | `ContentHash(hexdigest)`, `ContentHash.of(content: bytes) -> Self` (the pinned `-> ContentHash` for the class itself; compliant), `hexdigest: str`, frozen. Error hierarchy exact. `Observation` has exactly the nine pinned attributes and every pinned validation rule (regex `[a-z0-9][a-z0-9-]{0,63}` with `fullmatch`, `bool` rejected for sequence and status, status 100-599, `utcoffset()` required, size >= 0, `set-cookie` any case). The protocol has exactly the three pinned methods with the pinned types. `LocalDiskRawEvidenceStore(root: Path)`. All new functions are annotated. Extra public helpers `validate_execution_id`/`validate_sequence` are recorded additions. |
| On-disk layout | PASS | `_object_path`, `_observation_path` (`f"{sequence}.json"` on a validated non-negative `int`); temporary files in `<root>/tmp/`. |
| Observation record format | PASS | `_serialize` writes exactly the pinned keys with `schema_version 1`, `captured_at.isoformat()`, method and URL as given, headers as `[name, value]` lists in order; ASCII bytes with `\n`, written in binary. Formatting is as built, not judged (human instruction 1). |
| Order of `store` | PASS | Step 1 validates and serializes before any I/O; step 2 `_ensure_object`; step 3 `_ensure_observation`; returns the filtered `Observation`. Verified by tests and the order mutation check. |
| Atomic, write-once publication | PASS (code) | Temporary file in the store, `write`, `flush`, `os.fsync` via the `os` module, `os.link` (fails if the name exists), temporary removed in `finally`, exceptions propagate. The only deletion in `src/` is `_remove_quietly(temporary)` on the `tmp/` file (Grep for `unlink`, `replace`, `rename`, `rmtree`, `truncate`, `write_bytes`, `open(`: no other match). Test coverage of the "fails when the final name exists" part is missing: finding A1. |
| Errors | PASS | `read_content` and `read_observation` raise as pinned; `_read_if_present` catches only `FileNotFoundError`, so other `OSError`s propagate unwrapped; messages hold hashes, ids, sequences, paths and fixed reasons only. |
| No logging and no secrets | PASS | No `logging` or `print` in `src/` (Grep, rerun). Tests use `.invalid` URLs and synthetic bodies and cookies; gitleaks in the `feedback` job: `no leaks found` (reused, CI log). |
| Layer imports | PASS | See AC11. |
| No new dependency | PASS | `git diff main -- pyproject.toml uv.lock` empty; `[project] dependencies = []`; only stdlib (`hashlib`, `json`, `os`, `tempfile`, `re`, `dataclasses`, `datetime`, `pathlib`, `typing`, `collections.abc`). |
| Package root | PASS | `src/ec_procurement_quality/` holds `__init__.py` and the four layer packages only; the four new files are inside layer packages (`git diff --name-status main...HEAD -- src`). |
| No compression, no retention, no deletion | PASS | No such code. |
| Tests stay in the unit tier | PASS | All new tests in `tests/unit/`, `tmp_path` only; `tests/contract`, `integration`, `end_to_end` hold no tracked file (`git ls-files tests`). |

Consumers and migration: `test_cli.py` unchanged and passing; `test_layers.py` gained
only the `application` test and its helpers; no other caller exists. `.gitignore`
unchanged and effective. PASS.

## Outcome completion

O1 to O7 are `[x]` with Tests, Red and Green evidence; O8 is this audit. The recorded
red reasons (`ModuleNotFoundError` for the pinned modules, and the `application`
layer assertion) are plausible and match the plan. The recorded green results match the
reruns above. Two records are inaccurate: findings A3 and A4.

## Test coverage

| AC | Test and file | Status |
|---|---|---|
| AC1 | `tests/unit/test_content_hash.py` (17 tests) | PASS |
| AC2 | `test_store_round_trip_*` (6 functions, 9 cases), `tests/unit/test_local_disk_raw_evidence_store.py` | PASS |
| AC3 | `test_store_duplicate_content_keeps_one_object_and_adds_an_observation`, same file | PASS |
| AC4 | `test_store_error_response_is_preserved_as_received` (3 cases), `test_store_error_response_with_empty_body_uses_the_empty_hash`, same file | PASS |
| AC5 | `test_store_set_cookie_*` (2), same file; `test_observation_with_set_cookie_header_is_rejected` (4 cases), `tests/unit/test_raw_evidence.py` | PASS |
| AC6 | `test_read_content_corrupt_*` (2 cases), `test_read_content_missing_*` (2), `test_read_observation_missing_*` (2), `test_read_observation_corrupt_*` (10 cases), adapter file | PASS |
| AC7 | `test_store_conflict_*` (5 cases), `test_store_same_response_again_is_not_a_conflict_and_changes_nothing`, adapter file | PASS (gap on the publication step: A1) |
| AC8 | `test_store_orphan_*` (2), adapter file | PASS |
| AC9 | `test_store_interrupted_write_leaves_no_file_and_a_retry_stores_the_content`, adapter file | PASS |
| AC10 | `test_observation_with_invalid_*` (`test_raw_evidence.py`), `test_store_invalid_input_is_rejected_before_anything_is_written` (11 cases), `test_read_observation_invalid_identity_raises_value_error` (3 cases), adapter file | PASS |
| AC11 | `test_layer_domain_imports_only_stdlib_and_itself`, `test_layer_application_imports_only_stdlib_domain_and_itself` (`tests/unit/test_layers.py`); `test_local_disk_store_satisfies_port_and_works_through_it` + `mypy` | PASS |
| AC12 | the 7 F0 tests (`test_cli.py`, original `test_layers.py`) plus command checks | PASS |
| AC13 | none (manual inspection, as planned) | PASS |

Suite runs:
- `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing` -> `133 passed`, total 93% (rerun, Windows, Python 3.13.9). Uncovered: `raw_evidence.py` 99, 107; adapter 89, 171, 184, 211-212, 231-232, 239-243, 279, 288, 308, 324.
- `Tests` workflow at `392145f` (Ubuntu, Python 3.13.16) -> `133 passed`, total 94%; adapter uncovered 89, 171, 184, 211-212, 231-232, 238, 279, 288, 308, 324, so the POSIX directory sync (239-243) runs in CI (reused, CI log).
- Baseline: 7 passed, no pre-existing failures; none now.

Mutation and behavioral checks (rerun, on throwaway copies in the auditor's scratch
folder, never in the repository):

| Change to a copy of the adapter | Result |
|---|---|
| `os.link(temporary, final)` -> `os.replace(temporary, final)` | `133 passed` (no test fails); finding A1 |
| Observation written before the object | 3 failed (both `orphan` tests, object `conflict`) |
| Hash comparison in `read_content` removed | 2 failed (`corrupt` object) |
| `Set-Cookie` filter removed | 2 failed (`set_cookie`) |
| `read_content` typed `-> str` | `mypy`: protocol conflict at the `satisfies_port` test |
| Race script on the code as built: final name taken between the absence check and `os.link` (object with other bytes, object with same bytes, observation with other record) | integrity error with existing bytes kept; reuse; integrity error with `1.json` unchanged |
| Same race script on the `os.replace` copy | the tampered object and the existing `1.json` are silently overwritten, no error |

### Tier Results

Updated in round 2 (round 1 values in the audit log):

| Tier | Tests found | ACs verified | Setup matches § Validation | Ran | Status | Finding |
|---|---|---|---|---|---|---|
| unit (pytest) | 130 new (17 + 52 + 60 + 1 layer test; the 60 include the 4 `race` tests of § Validation AC7, Revision 3) and the 7 F0 tests (2 CLI, 5 layer), all in `tests/unit/` (137 total) | AC1 to AC12 | Yes: `uv sync --locked` only; no dev dependency, config file or script added (`git diff main -- pyproject.toml uv.lock` and the working-tree diff of `src`, `.github`, `.sdd`, `.claude`, `.gitignore` empty) | rerun (Windows). Ubuntu: the new tests are not yet in CI (working tree not pushed), `unavailable`; a POSIX replay of the four `race` scenarios was rerun under WSL (see § Round 2) | PASS | none open (A1 closed in round 2) |
| unit (mypy, AC11) | the `satisfies_port` annotated assignment | AC11 | Yes | rerun locally at the caller's request (`Success: no issues found in 15 source files`); CI `feedback` run reused from `392145f` | PASS | none |
| command (AC12) | ruff, mypy, doctor, `--version`, git checks | AC12 | Yes | rerun | PASS | none |
| manual (AC13) | inspection plus the two `git grep` commands | AC13 | Yes (none) | rerun in round 1; docs unchanged since (empty working-tree diff) | PASS | none |

No test exists at a tier § Validation does not name.

## Separate assessment: POSIX file mode `0600` of published files

- Behavior (code reading and stdlib source, rerun): `tempfile.NamedTemporaryFile` calls
  `_mkstemp_inner`, which opens with `os.open(file, flags, 0o600)`; the umask can only
  remove bits. `os.link` gives the final name to the same inode, so a published object or
  observation on POSIX has mode `0600`. Running it on a POSIX file system was
  `unavailable` to the auditor (the WSL mount of `C:` is 9p DrvFs without `metadata`, so
  it does not report real modes), and the CI suite does not assert it.
- Requirement: no AC or binding constraint requires a mode; ADR 0005 and intent § Out put
  read-only permissions out of scope. The mode is a side effect of `tempfile`, recorded
  as built in `execution-plan.md` and `tasks.md` § Notes.
- Test viability: yes in the Ubuntu `Tests` workflow, e.g. a test marked
  `pytest.mark.skipif(os.name != "posix", ...)` that stores a response and asserts
  `stat.S_IMODE(path.stat().st_mode) == 0o600` for the object and the observation.
- Verdict on the missing coverage: finding A2 (LOW). Concrete reason: the specs state the
  mode as a fact about the store and `harny-sync` is about to carry the as-built notes
  into a new `raw-evidence` capability, while evidence "may be sensitive"
  (intent § Constraints). Without a test, any change to how the temporary file is created
  (for example `open(path, "xb")`) would silently publish files as `0644` under the usual
  umask `022`, and nothing would fail. It is not blocking because no AC requires the mode.
  Either closure in A2 is acceptable.

## Separate assessment: atomic write-once publication

| Property | Code | Test that would fail if it broke | Assessment |
|---|---|---|---|
| Complete write to a temporary file in the store, outside `objects/` and `observations/` | `NamedTemporaryFile(dir=<root>/tmp)` | `round_trip` (only the two final files remain), `interrupted` | covered, no finding |
| `fsync` before the final name exists | `os.fsync(handle.fileno())` before `os.link` | `interrupted` (a failing `fsync` must leave no final name; it would fail if publication came first) | covered, no finding |
| Temporary file removed on any exception | `finally: _remove_quietly(temporary)` | `interrupted` (no file at all under the root), object `conflict` (only the planted file remains) | covered, no finding |
| Retry after an interrupted write | stateless | `interrupted` (retry succeeds with exact bytes) | covered, no finding |
| Existing object never rewritten | absence check, then reuse | `duplicate`, idempotent `conflict` (bytes and mtime) | covered, no finding |
| Different content under an existing name never overwrites | absence check plus `EvidenceIntegrityError` | object and observation `conflict` tests | covered for a name that exists before `store` starts, no finding |
| Publication "fails when the final name exists" (no replace) | `os.link`, `FileExistsError` -> re-read and verify | none: the `os.replace` copy passes all 133 tests and, in the race script, overwrites existing evidence | finding A1 (MEDIUM) |
| Orphan semantics | object first, never deleted | `orphan` (object kept, no `.json`); the object-blocked case leaves `observations/` empty | covered, no finding. With other content (AC7), the new object stays as an orphan; no AC asks for that to be asserted |
| Failed cleanup must not hide the original error | `_remove_quietly` swallows only `OSError` from `unlink` | none (lines 231-232) | acceptable: no AC, no concrete risk found; the original exception still propagates |
| Directory `fsync` on POSIX (durability after power loss) | `_sync_directory` | runs in CI (lines 239-243 covered on Ubuntu), effect not checked | acceptable: power-loss durability cannot be shown by a unit test |

Test viability for A1: viable on both Windows and the Ubuntu CI with no skip. Without
binding the test to `os.link` (only the plan proposed it), it can use the binding
`os.fsync` seam: a wrapper that, on its first call, plants a file at the final name
(other bytes, then identical bytes) and calls the real `os.fsync`. That runs after the
absence check and before publication, so it exercises exactly the "fails when the final
name exists" branch.

## Spec and code consistency

- Every item in `execution-plan.md` § Proposed approach "Implementation notes (as built,
  Revision 2)" matches the code: the two helpers, headers not coerced, the two
  `TypeError` cases, the record bytes, the strict structural check on read (including
  `type(version) is not int` and the `isoformat()` round trip), the publication details,
  the POSIX directory sync and `0600`, and the byte-comparison consequence with the four
  tested variants.
- In the code but not recorded: a header element that cannot be unpacked (for example
  an `int`) raises `TypeError` from `store`'s filter, and a 3-item header raises
  `ValueError` from unpacking, both before any write (rerun). Harmless; part of A3.
- Recorded but incomplete: the "Not asserted by any test" list and the O7 coverage note
  (A3). Stale state in `tasks.md` (A4).

## Findings

| Id | Severity | Finding and evidence | Closure condition | Status |
|---|---|---|---|---|
| A1 | MEDIUM | Binding constraint "Atomic, write-once publication" (made visible "with an operation that fails when the final name exists"; "No code path replaces..."), AC7, ADR 0002. The code complies, but no test fails if that guarantee is removed: a copy with `os.link` replaced by `os.replace` (the alternative the plan rejected because it overwrites) passes all 133 tests, and the race script shows that copy silently overwriting a tampered object and an existing `1.json` (rerun). The current tests only reach the absence-check path, so the `FileExistsError` branch (adapter lines 171, 184, 211-212) is dead to the suite. Not blocking: no AC example is unmet and concurrent writers are out of F1's scope, but the core no-overwrite guarantee has one unguarded layer. | A unit test (viable on Windows and Ubuntu, no skip) makes the final name appear after the absence check and before publication (for example through the binding `os.fsync` seam) and asserts: other bytes -> `EvidenceIntegrityError` with the existing object, or `1.json`, unchanged and no new observation; identical bytes -> success with no rewrite. Red evidence recorded in `tasks.md` against the `os.replace` copy. The architect names the test in the § Validation AC7 (or AC9) row first, since it is not in the approved list. | Closed in round 2 (see § Round 2) |
| A2 | LOW | Separate assessment above. Published files are `0600` on POSIX (stdlib `0o600` plus a hard link), stated as a fact in `execution-plan.md` as-built notes and `tasks.md` § Notes, but not asserted by any test (the as-built notes say so). No AC requires it; the risk is an unverified security-related property entering `specs/current`. | Either (a) a POSIX-only unit test (`skipif(os.name != "posix")`, runs in the Ubuntu `Tests` workflow) asserts mode `0o600` for a published object and observation, with red evidence against a copy that publishes `0644`; or (b) the architect, or `harny-sync` at archive, records `0600` as an incidental, untested consequence of `tempfile`, not a guarantee of the store. | Closed in round 2 (see § Round 2) |
| A3 | LOW | Record accuracy (intent § Outcome as built; `execution-plan.md` Revision 2 states the notes are taken from the code). The "Not asserted by any test" list omits read-side cases not covered by tests: `headers` not a list and a header not a `[name, value]` pair of text (adapter 279, 288) and a non-text `captured_at` (308). The `tasks.md` O7 note lists the uncovered lines as only the race branches, cleanup failure, POSIX sync and non-bytes `TypeError`, but `raw_evidence.py` 99 and 107 and adapter 279, 288, 308 and 324 are also uncovered (coverage run, rerun). The `TypeError` from an un-unpackable header element is not recorded. | The architect completes the "Not asserted by any test" list (and the `TypeError` note) in `execution-plan.md`; the executor corrects the O7 coverage note in `tasks.md`. | Closed in round 2 (see § Round 2) |
| A4 | LOW | `tasks.md` contradicts itself: § Status and Next step say Revision 2 was approved, but § Working state "Phase" says "spec Revision 2 awaiting the human's approval", "Notes for the next roles" says the Revision 2 edits "are not committed yet" (they are commit `509ca36`), § Notes says "`intent.md` is Revision 2, pending approval", and § Checkpoint says Revision 2 "is in the working tree, awaiting the human's approval". | The owner of `tasks.md` updates § Working state, § Notes and § Checkpoint to the approved and committed state. | Closed in round 2 (see § Round 2) |
| A5 | LOW | Raised in round 2. Record accuracy (`tasks.md` must reflect the completion state, harny-audit step 4). O9's Tests, Red and Green lines are filled (4 tests, 137 in the suite, 94% coverage), but the rest of `tasks.md` still describes O9 as not done: § Status "O9 open" and "133 tests pass"; § Working state "O9 open (not started)", "Last command" (the `133 passed` reruns at `509ca36`) and Next step 2 "The test-writer does O9"; § Finding responses A1 Evidence "Planned ... Not yet produced"; § Checkpoint "133 tests pass" and "Resume at O9 (the `race` test)". O9's own checkbox is `[ ]` (defensible, its text says "then the auditor re-checks", and this round has now re-checked it). | The owner of `tasks.md` updates § Status, § Working state, § Finding responses (A1 Evidence pointing to O9 Red and Green) and § Checkpoint to the state after O9 (137 tests, 94% coverage), marks O9 `[x]`, and fills O8 with this round's verdict. Checked by reading; no code re-check needed. | Open |

No CRITICAL or HIGH finding. No `harny-standards` violation: every rule in `AGENTS.md`
(layer boundaries, evidence never overwritten, no invented SERCOP contract, no
dependency, infrastructure or ADR change without approval, no secrets or raw datasets,
verification reported) is met. `harny-feedback`: the CI workflow
`.github/workflows/harny-feedback.yml` is present and its run at `392145f` is green with
`harny-feedback: 2 of 2 command(s) ran, 0 skipped.` and `no leaks found`; the `Tests`
workflow is green (`gh pr checks 15`: `feedback pass`, `tests pass`).

## Notes (informational, not findings)

- N1 (human instruction 1): the record bytes are as built. Because `store` compares an
  existing observation by bytes and `read_observation` accepts only `schema_version 1`,
  any future change of the bytes must bump `schema_version`, keep version 1 readable,
  and make the idempotent re-store compare against the bytes of the existing file's
  version; otherwise re-storing an identical response against an old file becomes a
  false conflict.
- N2: a failure of the POSIX directory `fsync` after `os.link` raises `OSError` although
  the file is already published. A retry is idempotent, so no evidence is lost, but F4
  must not read an `OSError` from `store` as "nothing was written" (AC8 already implies
  this for the object).
- N3: the integrity errors use `from None`, so tracebacks and messages are clean, but
  `__context__` still links to the `JSONDecodeError`, whose `doc` attribute holds the
  record text, header values included. It only matters if a future caller serializes
  exception contexts; worth remembering when F4 adds logging.
- N4: reading an observation or object through a path whose parent is a regular file
  gives `EvidenceNotFoundError` on Windows (`FileNotFoundError`) and an `OSError` on
  POSIX (`NotADirectoryError`). Both are reasonable; no AC covers it.
- N5: whether the per-turn Stop hook fired during implementation is `unavailable`: the
  hook is configured in `.claude/settings.json`, but it leaves no persistent log, and it
  runs `ruff` and `mypy` only when `.venv` is on `PATH`. Not raised as a finding because
  the whole-project CI run on the code head ran both commands (2 of 2) with no finding to
  heed, and the executor recorded clean runs.
- N6: commit `509ca36` (spec Revision 2) is local only; PR #15 still shows `392145f`.
  Push it, with this `audit.md`, before merging so the PR carries the approved specs.
- N7: `tasks.md` O8 is left for its owner to fill with this verdict; the auditor writes
  only `audit.md`.

## Residual items for `harny-sync` at archive

1. `project-toolchain` PT-3: retire "`domain`, `application` and `infrastructure` hold
   only what makes them packages"; keep "`domain` imports nothing outside the standard
   library and itself"; consider adding the new rule enforced by
   `test_layer_application_imports_only_stdlib_domain_and_itself` (`application` imports
   only the standard library, `domain` and itself).
2. `project-toolchain` PT-6: the "7 tests passed at F0" scenario is now 137 at F1
   (133 at round 1, plus the 4 `race` tests); restate it without a count or with the F1
   count.
3. `project-toolchain` invariant 3 still holds (one file directly in
   `src/ec_procurement_quality/`); invariant 4 still holds (`[project] dependencies`
   empty). No change.
4. New capability `raw-evidence` (prefix `RE-`): AC1 to AC10 as requirements, plus the
   binding layout, record fields and `schema_version 1`, `store` order, write-once
   publication, `Set-Cookie` rule, integrity on read, error types and message rule, and
   no logging. Record the exact bytes as as-built, not contract (N1). Round 2: record
   the POSIX mode as incidental, not a requirement (A2 closure (b), `execution-plan.md`
   Revision 3 "POSIX file mode is incidental, not a guarantee"); record that the
   "name taken between the check and publication" branch is guarded by the `race` tests
   (simulated deterministically through the `os.fsync` seam), while real concurrent
   writers remain untested and out of F1's scope; drop the concurrent-publish branches
   from the "Not asserted by any test" list, as `execution-plan.md` Revision 3 says.
5. `cli`: no change. Update `specs/current/_index.md` for the new capability.
6. Optional, human: add "object" and "observation" (store terms) to `docs/glossary.md`.
7. Round 2: the `Tests` workflow on Ubuntu has not run the 4 `race` tests yet (working
   tree not pushed); confirm it is green on the pushed head before archiving.

## Round 2 (2026-10-09)

Reviewed state: branch `feat/raw-evidence-store` at `509ca36` plus the uncommitted
working tree: `intent.md` Revision 3 (Approval `Pending`, which the caller says the
human gives at the final gate together with this verdict; not treated as a defect),
`execution-plan.md` Revision 3, `tasks.md` (O9 filled), and
`tests/unit/test_local_disk_raw_evidence_store.py` (+112 lines: `import stat`, the
helpers `_plant_when_publishing` and `_reference_observation`, and 4 `race` tests).
Every changed line was read. All results below are `rerun` unless labelled otherwise.

### Nothing else changed

- `git diff --stat -- src pyproject.toml uv.lock .github .sdd .claude .gitignore README.md docs CHANGELOG.md`
  -> empty; `git status --short --untracked-files=all` lists only the three specs, the
  test file and this `audit.md`. No product code changed.
- `intent.md`: only the Revision and Approval lines and a Revision 3 history entry; no AC,
  example, scope item or constraint text changed (diff read).
- `execution-plan.md`: changes are exactly those Revision 3 lists: a § Guidance consulted
  line; the `race` token in the test-name list; the A1 design decision and red procedure
  in § Proposed approach; the as-built notes for A2 and A3 (the `TypeError` note, the
  POSIX sync note split from the new "POSIX file mode is incidental" note, the completed
  "Not asserted by any test" list); the `os.fsync` risk row; the § Validation AC7 row
  (the `race` test and the `-k "conflict or race"` command); the revision log. No
  binding constraint, signature, layout, record field or other § Validation row changed.
- No Claude or AI attribution: `git grep -i -E "claude|co-authored|generated with|anthropic" -- docs README.md CHANGELOG.md tests src`
  matches only `.claude/...` path references in `docs/learning/journal.md:49` and
  `docs/learning/plan.md` (pre-existing, not attribution); the working-tree diff adds no
  such line; no new commit on the branch. `docs/learning/journal.md` is unchanged.
- The test file's working copy is CRLF throughout (758 of 758 lines), like the other
  test files on this checkout (`core.autocrlf=true`, `.gitattributes` `* text=auto eol=lf`),
  so Git stores it with LF; `git diff --check` is clean. Not a finding.

### Commands

| Command | Result |
|---|---|
| `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing` | `137 passed`; total 94% (236 statements, 13 missed); `raw_evidence.py` 96% (99, 107); adapter 93% (151 statements; missed 89, 231-232, 239-243, 279, 288, 308, 324). Lines 171, 184 and 211-212 (the concurrent-publish branches) are now covered |
| `uv run pytest tests/unit/test_local_disk_raw_evidence_store.py -q -k race` | `4 passed, 56 deselected` |
| same file, `-k "conflict or race"` | `10 passed, 50 deselected` |
| same file, all | `60 passed` |
| `uv run ruff check .` | `All checks passed!` |
| `uv run ruff format --check .` | `64 files already formatted` |
| `uv run mypy .` | `Success: no issues found in 15 source files` (run at the caller's request; CI has not run on this working tree) |
| `uv run node .sdd/doctor/run-doctor.mjs` | `31 ok, 0 skipped, 0 warned, 0 failed` |
| `git diff --check` | clean |
| `uv run ec-procurement-quality --version` | `ec-procurement-quality 0.1.0` |
| `git check-ignore data/raw/objects/ab/x data/raw/observations/e/1.json` | both printed |
| `git grep -n -i -e datosabiertos -e compraspublicas -- tests` | exit 1 (no match) |
| `Tests` and `feedback` workflows on the new tests | `unavailable` (working tree not pushed) |

### A1: closed

Red evidence reproduced independently, on the auditor's own copies of
`src/ec_procurement_quality` in new scratch folders `audit2-*` (outside the repository,
left in place), each confirmed as the imported module with
`PYTHONPATH=<copy> uv run python -c "import ...local_disk_raw_evidence_store as m; print(m.__file__)"`
(prints the scratch path), and run with `PYTHONPATH=<copy> uv run pytest -p no:cacheprovider ...`:

| Mutant of the publication step (one change each, `diff` checked) | `-k race` | Full suite |
|---|---|---|
| M1 `os.link(temporary, final)` -> `os.replace(temporary, final)` | 4 failed: (a), (b) `DID NOT RAISE EvidenceIntegrityError`; (c) object and (c) observation `st_mtime_ns` is now, not `946684800000000000` | 4 failed, 133 passed (round 1: 133 passed, 0 failed) |
| M2 `except FileExistsError: return True` (taken name treated as published, no verification) | 2 failed: (a), (b) `DID NOT RAISE` | 2 failed, 135 passed |
| M3 object race branch does not re-read the existing file | 1 failed: (c) object raises `EvidenceIntegrityError` (false conflict) | 1 failed, 136 passed |
| M4 observation race branch does not re-read the existing file | 1 failed: (c) observation raises `EvidenceIntegrityError` | 1 failed, 136 passed |
| M5 on `FileExistsError`, `os.unlink(final)` then `os.link` again (delete-and-relink overwrite) | 4 failed, as M1 | 4 failed, 133 passed |
| M6 object race branch returns after the re-read without the hash check | 1 failed: (a) `DID NOT RAISE` | 1 failed, 136 passed |

All six are caught, each by the case it should break and for the right reason; the real
code passes all four. The tests cannot pass vacuously: every test asserts
`acted == [path]` (the wrapper acted, at the targeted name), the wrapper raises if the
name existed before it planted (so the absence check really saw it absent), the planted
file is aged to `LONG_AGO_NS` and each test asserts both its bytes and its
`st_mtime_ns` afterwards (M1 and M5 in the benign cases are caught only by the mtime
check, as the O9 Red line says), (a) asserts no file under `observations/`, and the
benign cases compare the result against a reference store under another root, so the
record bytes are not pinned. The wrapper acts at the first `os.fsync` on a regular file,
an alternative the plan allows; for the observation cases the object is put in place
first, so that call is the observation's temporary file.

POSIX check: the four scenarios replayed by a plain script mirroring the test logic
(`audit2_posix_race.py`, Python 3.12.3, WSL, store root on ext4 `/tmp`, because pytest
is not installed there): real code 4 PASS, with directory `fsync` calls seen only after a
successful link and never acted on; M1 copy 4 FAIL (`did not raise` twice, object and
observation rewritten). This is supporting evidence, not the test file itself; the
Ubuntu `Tests` run of the real tests is `unavailable` until push. Closure condition met:
test viable on both platforms with no skip, other bytes and identical bytes for object
and observation, red evidence recorded in `tasks.md` O9 against the `os.replace` copy
(reproduced here), and the test named in § Validation AC7 by the architect first.

### A2: closed

Closure (b). `execution-plan.md` Revision 3 "POSIX file mode is incidental, not a
guarantee" states the mode is whatever `tempfile` gives (currently `0600`), not a
property of the store, not required by any AC or binding constraint, not asserted by any
test, may change without a test failing, and that `harny-sync` must record it the same
way; the "Not asserted by any test" list repeats it; `tasks.md` § Notes says the same.
The earlier "a published file on POSIX has mode `0600`" sentence was removed from the
POSIX sync note. No test was added, as the human decided.

### A3: closed

`execution-plan.md` "Not asserted by any test" now lists the read-side checks (`headers`
not a list, a header not a `[name, value]` pair of text, non-text `captured_at`,
non-`isoformat()` `captured_at`, `schema_version` `true` or `1.0`), the `Observation`
`headers` rejections, the `TypeError` cases and the header `ValueError`s; the `TypeError`
note now describes the header-unpacking errors. Each claim checked: a behavioral script
shows `store` with header `[1]` -> `TypeError`, `[[1]]` and a 3-tuple -> `ValueError`,
`(1, "v")` -> `ValueError`, each with no root created; `raw_evidence.py` 99 and 107 are
the `content_hash` `TypeError` and the `headers` `ValueError`; the test file's only
read-side record mutations are `schema_version 2` and a naive `captured_at`, so the
listed checks are indeed untested. The O7 uncovered-behavior note matches this round's
coverage run, minus the race lines it says O9 targets (now covered).

### A4: closed, A5 raised

The items A4 named are fixed: § Working state "Phase" and "Notes for the next roles",
§ Notes and § Checkpoint now say Revision 2 was approved and committed as `509ca36`.
But `tasks.md` was written before O9 ran and was not updated after it, so it now says O9
is not started while O9's own lines record it done: new finding A5 (LOW), see
§ Findings. The pending Approval line is expected (caller's instruction) and is not part
of A5.

### Other observations

- No new CRITICAL, HIGH or MEDIUM finding. AC1 to AC13 and every binding constraint
  stay PASS: no product code changed, and the full suite, the focused commands and the
  checks above were rerun.
- N8: O9 was carried out before Revision 3 was approved (`tasks.md` order item 5 says
  "once the human approves it"). The caller states the human approves Revision 3 and
  this verdict together at the final gate, so it is recorded here, not raised.
- N9: after pushing, check that the `Tests` workflow on Ubuntu passes the 4 `race`
  tests (residual item 7).

## Audit log

| Round | Date | Verdict | Notes |
|---|---|---|---|
| 1 | 2026-10-09 | APPROVED WITH RESERVATIONS | AC1 to AC13 PASS; all binding constraints PASS; findings A1 (MEDIUM), A2, A3, A4 (LOW) open, none blocking. Reviewed `509ca36`; CI reused from `392145f`. Tier Results at round 1: unit 133 tests (126 new + 7 F0), rerun on Windows and reused from Ubuntu CI, PASS with A1 and A2; mypy, command and manual tiers PASS. |
| 2 | 2026-10-09 | APPROVED WITH RESERVATIONS | `509ca36` plus the uncommitted Revision 3 specs and the 4 `race` tests. A1 to A4 closed with rerun evidence (6 publication mutants all caught; POSIX replay under WSL). New A5 (LOW, `tasks.md` stale after O9) open, not blocking. 137 passed, 94% coverage on Windows; Ubuntu CI on the new tests `unavailable` until push. |

## Final verdict

APPROVED WITH RESERVATIONS

**Summary**: All four round 1 findings are closed: the new `race` tests catch replacing
`os.link` with an overwriting call, and five other mutants of the publication step,
and the records for the POSIX mode and the untested behaviors are complete and accurate.
The only reservation is that `tasks.md` was not brought up to date after O9.

**Critical Issues** (must fix before merge):
- None.

**Warnings** (should fix, not blocking):
- None.

**Recommendations** (nice to have):
- A5 (LOW): update `tasks.md` § Status, § Working state, § Finding responses and
  § Checkpoint to the state after O9 (137 tests, 94%), mark O9 `[x]` and fill O8 with
  this verdict.
- Confirm the Ubuntu `Tests` workflow is green on the pushed head (N9).
