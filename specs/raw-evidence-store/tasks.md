# Tasks: Raw evidence store (F1)

## Status
Awaiting intent approval

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

- [ ] **O1** (AC1, AC11) — human: the content hash value object `ContentHash` in `src/ec_procurement_quality/domain/content_hash.py`, with `ContentHash(hexdigest)`, `ContentHash.of(content)`, the `hexdigest` attribute, value equality and hashing, immutability, and `ValueError` for anything that is not 64 lowercase hex characters. Standard library only (`hashlib`); passes strict `mypy`.
  - Tests: `tests/unit/test_content_hash.py`
  - Red: [command and failing result]
  - Green: `uv run pytest tests/unit/test_content_hash.py -q` passes and `uv run mypy .` exits 0
- [ ] **O2** (AC5, AC10, AC11) — executor: `src/ec_procurement_quality/domain/raw_evidence.py` with `RawEvidenceError`, `EvidenceIntegrityError`, `EvidenceNotFoundError`, and the immutable `Observation` record with exactly the pinned attributes and validation rules (execution id pattern, sequence, method, URL, status range, UTC offset required, size, no `Set-Cookie` header). Standard library and `domain` only; passes strict `mypy`.
  - Tests: `tests/unit/test_raw_evidence.py` (names containing `set_cookie` and `invalid`)
  - Red: [command and failing result]
  - Green: `uv run pytest tests/unit/test_raw_evidence.py -q` passes and `uv run mypy .` exits 0
- [ ] **O3** (AC11) — human: the port `RawEvidenceStore` in `src/ec_procurement_quality/application/raw_evidence_store.py`, a `typing.Protocol` with exactly `store(*, execution_id, sequence, method, url, status, headers, captured_at, content) -> Observation`, `read_content(content_hash) -> bytes` and `read_observation(execution_id, sequence) -> Observation`, typed as pinned. It imports only the standard library and `domain`.
  - Tests: `tests/unit/test_layers.py` (`test_layer_application_imports_only_stdlib_domain_and_itself`); the `satisfies_port` test in `tests/unit/test_local_disk_raw_evidence_store.py`, checked by `mypy`
  - Red: [command and failing result]
  - Green: `uv run pytest tests/unit -q -k layer` passes; `uv run mypy .` exits 0 once O4 exists
- [ ] **O4** (AC2, AC3, AC4, AC5, AC6, AC7, AC8, AC9, AC10, AC11) — executor: `LocalDiskRawEvidenceStore(root)` in `src/ec_procurement_quality/infrastructure/local_disk_raw_evidence_store.py`, implementing the port with the pinned layout, record format, `store` order, write-once atomic publication through a temporary file synced with `os.fsync`, `Set-Cookie` filtering, integrity checks on read and on existing identities, typed errors, and no logging.
  - Tests: `tests/unit/test_local_disk_raw_evidence_store.py` (names containing `round_trip`, `duplicate`, `error_response`, `set_cookie`, `corrupt`, `missing`, `conflict`, `orphan`, `interrupted`, `invalid`, `satisfies_port`)
  - Red: [command and failing result]
  - Green: `uv run pytest tests/unit/test_local_disk_raw_evidence_store.py -q` passes, each `-k` command of `execution-plan.md` § Validation AC2 to AC10 passes, and `uv run mypy .` exits 0
- [ ] **O5** Migration (AC11, AC12): existing consumers keep working.
  - `tests/unit/test_cli.py` and the existing tests in `tests/unit/test_layers.py` are not edited and still pass; `test_layers.py` only gains the `application` import test.
  - `pyproject.toml` and `uv.lock` are unchanged (`git diff main -- pyproject.toml uv.lock` is empty); no new file directly in `src/ec_procurement_quality/`.
  - `git check-ignore data/raw/objects/ab/x data/raw/observations/e/1.json` prints both paths; no test writes to the real `data/raw/`.
  - `uv run ec-procurement-quality --version` still prints `ec-procurement-quality 0.1.0`.
- [ ] **O6** Docs (AC13): `README.md` (§ Architecture no longer says the layer packages are empty; § Technologies names the local raw evidence store and drops it from "Planned"; no CLI command is claimed), `docs/architecture.md` (§ Raw evidence boundary links ADR 0005; § Open questions marks the local raw-storage question as answered by ADR 0005), and `CHANGELOG.md` § Unreleased (an `Added` entry for the store). Checked with the AC13 commands of `execution-plan.md` § Validation.
- [ ] **O7** Broader suite vs baseline (AC12): `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing` passes with the 7 baseline tests plus the new ones; `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy .` exit 0; `uv run node .sdd/doctor/run-doctor.mjs` reports `0 warned, 0 failed`; `git diff --check` is clean; `git grep -n -i -e datosabiertos -e compraspublicas -- tests` finds nothing. On the F1 pull request, the `feedback` and `Tests` checks are green.
- [ ] **O8** Independent audit: [verdict from `specs/raw-evidence-store/audit.md`]

## Working state
- Updated: 2026-10-09
- Outcome: none started
- Phase: specs drafted (intent Revision 1, execution-plan Revision 1), awaiting the human's review at the first gate
- In progress: nothing
- Last command: `node .sdd/doctor/run-doctor.mjs --only spec-state` -> `0 ok, 0 skipped, 0 warned, 0 failed` after the three spec files were written (it failed with `spec-state:raw-evidence-store` while only `intent.md` existed)
- Next step:
  1. The human reviews `intent.md` and `execution-plan.md` and records the approval in `intent.md`'s `Approval` line, and decides whether to mark ADR 0005 as `Accepted`.
  2. The test-writer writes the red tests (O1 to O5) and fills the Red lines; the human reviews them at the post-red-tests gate.
  3. Day 10: the human writes O1 and O3; the executor writes O2 and O4, then O5 to O7.

## Finding responses
| Finding | Response | Evidence |
|---|---|---|

## Checkpoint
Specs written on 2026-10-09 from base `3f8f779`; nothing implemented. Resume at the first gate: the human reviews and approves `intent.md` and `execution-plan.md`, then the test-writer starts the red phase.
