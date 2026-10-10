# Tasks: Raw evidence store (F1)

## Status
Implemented (O1 to O7 done; O8 independent audit pending). Completed 2026-10-09: 133 tests pass, `ruff`, `mypy` and the doctor are clean

## Baseline
- Base commit: `3f8f779` (`main`, "Merge pull request #13 from Vladimirjon/docs/day-8-glossary")
- Branch: `docs/day-9-raw-evidence-store-adr-specs` when these specs were written (it also holds the untracked ADR 0005). Implementation happens on a new branch, `feat/raw-evidence-store`, created from `main` after the specs and ADR 0005 are merged or from this branch, as the human decides.
- Interpreter: Python 3.13.9 (`uv run python --version`), uv 0.12.23
- Cwd: the repository root, `ec-public-procurement-quality-monitor`
- Commands:
  - Install: `uv sync --locked`
  - Test: `uv run pytest` (CI form: `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing`)
  - Lint and format: `uv run ruff check .` and `uv run ruff format --check .`
  - Type check: `uv run mypy .`
  - Readiness: `uv run node .sdd/doctor/run-doctor.mjs`
- Pre-existing failures: none. On 2026-10-09 at `3f8f779`: `uv run pytest -q` -> `7 passed`; `ruff check` -> "All checks passed!"; `ruff format --check` -> "53 files already formatted"; `mypy .` -> "no issues found in 8 source files"; doctor -> `31 ok, 0 skipped, 0 warned, 0 failed`. While only `intent.md` existed, `--only spec-state` failed because `execution-plan.md` and `tasks.md` were missing; this file resolves it.

## Outcomes
Order and ownership:
1. The test-writer writes the red tests for O1 to O5 (files and names from `execution-plan.md` § Proposed approach) and fills their Tests and Red lines. The correct red reason is that the pinned module or name does not exist yet (`ModuleNotFoundError` or `ImportError` for the module named in `execution-plan.md` § Binding constraints), never a typo in a test. The human reviews them at the post-red-tests gate.
2. O1 and O3 are written **by the human by hand** (`docs/learning/plan.md` Day 10). The executor never writes `domain/content_hash.py` or `application/raw_evidence_store.py`; if they are missing when the executor needs them, the executor stops, sets Status to Blocked and says which one is missing. The executor may review them and report problems.
3. O2 and O4 are written by the executor. O2 needs O1 to exist; O4 needs O1, O2 and O3. Each one relies only on the names and signatures fixed in `execution-plan.md` § Binding constraints, not on how the human wrote the inside of O1 or O3.
4. Then O5 to O7 (executor), and O8 (auditor).

- [x] **O1** (AC1, AC11) — human: the content hash value object `ContentHash` in `src/ec_procurement_quality/domain/content_hash.py`, with `ContentHash(hexdigest)`, `ContentHash.of(content)`, the `hexdigest` attribute, value equality and hashing, immutability, and `ValueError` for anything that is not 64 lowercase hex characters. Standard library only (`hashlib`); passes strict `mypy`.
  - Tests: `tests/unit/test_content_hash.py` (17 tests: SHA-256 vectors for `b"abc"` and `b""`, value equality and hashing, set and dict key, 9 invalid values including a trailing newline, immutability)
  - Red: `uv run pytest tests/unit/test_content_hash.py -q` -> 1 error in collection, 0 tests run: `E   ModuleNotFoundError: No module named 'ec_procurement_quality.domain.content_hash'` (correct reason: the module O1 creates does not exist)
  - Green: `uv run pytest tests/unit/test_content_hash.py -q` -> `17 passed`; `uv run mypy .` -> `Success: no issues found in 15 source files`. Written by the human; reviewed by the executor, no problem found (it stays read-only for the executor).
- [x] **O2** (AC5, AC10, AC11) — executor: `src/ec_procurement_quality/domain/raw_evidence.py` with `RawEvidenceError`, `EvidenceIntegrityError`, `EvidenceNotFoundError`, and the immutable `Observation` record with exactly the pinned attributes and validation rules (execution id pattern, sequence, method, URL, status range, UTC offset required, size, no `Set-Cookie` header). Standard library and `domain` only; passes strict `mypy`.
  - Tests: `tests/unit/test_raw_evidence.py` (52 tests: valid attributes and boundaries, value equality, immutability, common error base, `Set-Cookie` rejected in any case, and invalid execution id, sequence, method, URL, status, naive capture time and size; names containing `set_cookie` and `invalid`)
  - Red: `uv run pytest tests/unit/test_raw_evidence.py -q` -> 1 error in collection, 0 tests run: `E   ModuleNotFoundError: No module named 'ec_procurement_quality.domain.content_hash'` (the file imports `ContentHash` first, so the first missing module is O1's; once O1 exists the next failure is `ModuleNotFoundError: No module named 'ec_procurement_quality.domain.raw_evidence'`, checked against a partial scratch copy outside the repo)
  - Green: `uv run pytest tests/unit/test_raw_evidence.py -q` -> `52 passed`; `uv run mypy .` -> `Success: no issues found in 15 source files` (strict flags apply to `domain.raw_evidence`); `uv run pytest tests/unit -q -k layer` includes the `domain` import check over the new module and passes
- [x] **O3** (AC11) — human: the port `RawEvidenceStore` in `src/ec_procurement_quality/application/raw_evidence_store.py`, a `typing.Protocol` with exactly `store(*, execution_id, sequence, method, url, status, headers, captured_at, content) -> Observation`, `read_content(content_hash) -> bytes` and `read_observation(execution_id, sequence) -> Observation`, typed as pinned. It imports only the standard library and `domain`.
  - Tests: `tests/unit/test_layers.py` (`test_layer_application_imports_only_stdlib_domain_and_itself`, 1 new test; it requires `application/raw_evidence_store.py` to exist, so it cannot pass on the empty package); the `satisfies_port` test in `tests/unit/test_local_disk_raw_evidence_store.py`, checked by `mypy`
  - Red: `uv run pytest tests/unit/test_layers.py -q` -> `1 failed, 5 passed`: `FAILED tests/unit/test_layers.py::test_layer_application_imports_only_stdlib_domain_and_itself` with `AssertionError: application needs raw_evidence_store.py` (correct reason: the port module does not exist). The `satisfies_port` test is red with the O4 file (`ModuleNotFoundError: No module named 'ec_procurement_quality.application.raw_evidence_store'`)
  - Green: `uv run pytest tests/unit -q -k "layer or satisfies_port"` -> `7 passed, 126 deselected`; `uv run mypy .` -> `Success: no issues found in 15 source files` (the `satisfies_port` test assigns the adapter to a variable typed as the port). Written by the human; reviewed by the executor, signatures match the pinned ones exactly.
- [x] **O4** (AC2, AC3, AC4, AC5, AC6, AC7, AC8, AC9, AC10, AC11) — executor: `LocalDiskRawEvidenceStore(root)` in `src/ec_procurement_quality/infrastructure/local_disk_raw_evidence_store.py`, implementing the port with the pinned layout, record format, `store` order, write-once atomic publication through a temporary file synced with `os.fsync`, `Set-Cookie` filtering, integrity checks on read and on existing identities, typed errors, and no logging.
  - Tests: `tests/unit/test_local_disk_raw_evidence_store.py` (56 tests; names containing `round_trip`, `duplicate`, `error_response`, `set_cookie`, `corrupt`, `missing`, `conflict`, `orphan`, `interrupted`, `invalid`, `satisfies_port`)
  - Red: `uv run pytest tests/unit/test_local_disk_raw_evidence_store.py -q` -> 1 error in collection, 0 tests run: `E   ModuleNotFoundError: No module named 'ec_procurement_quality.application.raw_evidence_store'` (the file imports the port first; with O1 to O3 present the next failure is `ModuleNotFoundError: No module named 'ec_procurement_quality.infrastructure.local_disk_raw_evidence_store'`, checked against a partial scratch copy outside the repo)
  - Green: `uv run pytest tests/unit/test_local_disk_raw_evidence_store.py -q` -> `56 passed`; focused `-k` commands of § Validation: `round_trip` 9 passed, `duplicate` 1, `error_response` 4, `set_cookie` (adapter + domain files) 7, `"corrupt or missing"` 16, `conflict` 6, `orphan` 2, `interrupted` 1, `invalid` (domain + adapter files) 38, all passed; `uv run mypy .` -> `Success: no issues found in 15 source files`
- [x] **O5** Migration (AC11, AC12): existing consumers keep working.
  - `tests/unit/test_cli.py` and the existing tests in `tests/unit/test_layers.py` are not edited and still pass; `test_layers.py` only gains the `application` import test.
  - `pyproject.toml` and `uv.lock` are unchanged (`git diff main -- pyproject.toml uv.lock` is empty); no new file directly in `src/ec_procurement_quality/`.
  - `git check-ignore data/raw/objects/ab/x data/raw/observations/e/1.json` prints both paths; no test writes to the real `data/raw/`.
  - `uv run ec-procurement-quality --version` still prints `ec-procurement-quality 0.1.0`.
  - Evidence: `git diff main --stat -- pyproject.toml uv.lock` -> empty; `git check-ignore data/raw/objects/ab/x data/raw/observations/e/1.json` -> both printed; `ls src/ec_procurement_quality` -> `__init__.py` plus the four layer packages only (no new root file); `git diff -- tests/unit/test_layers.py` -> additions only (the `application` test and its helpers); `tests/unit/test_cli.py` unmodified; `uv run ec-procurement-quality --version` -> `ec-procurement-quality 0.1.0`; the 2 CLI tests and the 5 original layer tests are inside the 133 passed; no test uses the network or the real `data/raw/` (all use `tmp_path`).
- [x] **O6** Docs (AC13): `README.md` (§ Architecture no longer says the layer packages are empty; § Technologies names the local raw evidence store and drops it from "Planned"; no CLI command is claimed), `docs/architecture.md` (§ Raw evidence boundary links ADR 0005; § Open questions marks the local raw-storage question as answered by ADR 0005), and `CHANGELOG.md` § Unreleased (an `Added` entry for the store). Checked with the AC13 commands of `execution-plan.md` § Validation.
  - Green: `git grep -n -i "raw evidence" -- README.md docs/architecture.md CHANGELOG.md` -> matches in all three (architecture links `adr/0005-raw-evidence-store-layout.md`); `git grep -n "four empty layer" -- README.md` -> no match (exit 1); the README "Planned" list no longer lists storage adapters as missing and says no CLI command calls the store; `git diff --check` clean.
- [x] **O7** Broader suite vs baseline (AC12): `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing` passes with the 7 baseline tests plus the new ones; `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy .` exit 0; `uv run node .sdd/doctor/run-doctor.mjs` reports `0 warned, 0 failed`; `git diff --check` is clean; `git grep -n -i -e datosabiertos -e compraspublicas -- tests` finds nothing. On the F1 pull request, the `feedback` and `Tests` checks are green.
  - Green (local, 2026-10-09): `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing` -> `133 passed` (7 baseline + 126 new), total coverage 93% (`raw_evidence.py` 96%, `local_disk_raw_evidence_store.py` 90%; uncovered lines are the concurrent-publish race branches, the best-effort cleanup failure, the POSIX-only directory sync, and the non-bytes `TypeError`); `uv run ruff check .` -> `All checks passed!`; `uv run ruff format --check .` -> `63 files already formatted`; `uv run mypy .` -> `Success: no issues found in 15 source files`; `uv run node .sdd/doctor/run-doctor.mjs` -> `31 ok, 0 skipped, 0 warned, 0 failed`; `git diff --check` clean; `git grep -n -i -e datosabiertos -e compraspublicas -- tests` -> no match (exit 1). The `feedback` and `Tests` checks on the pull request are not available yet (no PR); to confirm after the PR is opened.
- [ ] **O8** Independent audit: [verdict from `specs/raw-evidence-store/audit.md`]

## Working state
- Updated: 2026-10-09
- Outcome: O1 to O7 done; O8 (independent audit) pending
- Phase: implemented, awaiting the independent audit
- In progress: nothing
- Last command: `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing` -> `133 passed`, 93% coverage; `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy .` clean; `uv run node .sdd/doctor/run-doctor.mjs` -> `31 ok, 0 skipped, 0 warned, 0 failed`.
- Notes for the next roles: see § Notes. Nothing is committed; the whole change is in the working tree of `feat/raw-evidence-store`.
- Next step:
  1. The auditor writes `audit.md` against the intent ACs and the binding constraints.
  2. The human reviews, commits, opens the pull request, and refreshes the stale "Proposed" text in the specs (see § Notes).

## Finding responses
| Finding | Response | Evidence |
|---|---|---|

## Notes
Deviations from `execution-plan.md` § Proposed approach and additions (none changes a binding constraint):
- `domain/raw_evidence.py` also exposes two public helpers, `validate_execution_id` and `validate_sequence`, so `read_observation` applies exactly the `Observation` rules without duplicating the pattern in the adapter. They are additions to the pinned names, not changes.
- `Observation` requires `headers` to be a `tuple` of `(str, str)` tuples (anything else is `ValueError`) and does not convert lists. A `content_hash` of the wrong type and non-`bytes` `content` raise `TypeError`, which no pinned rule covers (the lint configuration prefers `TypeError` for wrong types).
- The record is written as ASCII-only JSON (`ensure_ascii`), indent 2, a trailing newline, keys in the pinned order, so text that is not valid Unicode can still be preserved. A `captured_at` read back must equal `isoformat()` of the parsed value, otherwise `EvidenceIntegrityError`.
- Temporary files use `tempfile.NamedTemporaryFile(dir=<root>/tmp, delete=False)` inside a context manager, then `os.link` and best-effort removal, as proposed. On POSIX the containing directory is also `fsync`ed after publication, as suggested. Because the published file shares the temporary file's inode, its mode on POSIX is `0600`; read-only permissions stay out of scope.
- POSIX behavior was checked only by a throwaway smoke script on a copy of `src/` run under WSL Ubuntu with Python 3.12 (store, duplicate, interrupted `os.fsync`, tampered object): all behaved as expected. The suite itself ran on Windows only; the POSIX-only directory sync is not covered by it.

Stale text found in the spec files (the executor does not edit specs other than `tasks.md`; the architect or the human should refresh it): `intent.md` § Constraints says "ADR 0005 is `Proposed`"; `execution-plan.md` § Guidance consulted says the intent is "pending approval" and ADR 0005 "Proposed"; `execution-plan.md` § Consumers says the ADR moves to `Accepted` only by the human (now done); this file's § Baseline still describes the branch situation before the implementation branch existed.

## Checkpoint
Implementation complete on branch `feat/raw-evidence-store` (base `62afd18`), uncommitted: O1 and O3 by the human, O2 and O4 to O7 by the executor; 133 tests pass, `ruff`, `mypy` and the doctor are clean. Created: `src/ec_procurement_quality/domain/raw_evidence.py`, `src/ec_procurement_quality/infrastructure/local_disk_raw_evidence_store.py`; edited: `README.md`, `docs/architecture.md`, `CHANGELOG.md`, this file. Resume at O8: the independent audit.
