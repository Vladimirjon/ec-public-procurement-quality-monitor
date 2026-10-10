# Tasks: SERCOP source adapter (F2)

## Status
Intent Revision 1 approved by the human at gate 1 on 2026-10-10. Gate 1 also accepted ADR 0006, the fixtures in `tests/fixtures/sercop/`, and the series of 2026-10-10 in `docs/sources/sercop-observations.md`. Next: O1.

## Baseline
- Base commit: `fff0f2d` (`main`, "Merge pull request #15 from Vladimirjon/feat/raw-evidence-store").
- Branch: `feat/sercop-source-adapter`. The working tree at drafting time held, uncommitted: `docs/sources/sercop-observations.md` (modified), `docs/adr/0006-http-client-for-source-access.md` (new), `tests/fixtures/sercop/` (new), and these three spec files.
- Interpreter: Python 3.13.9 (`.venv\Scripts\python.exe --version`), uv 0.12.23.
- Cwd: the repository root, `ec-public-procurement-quality-monitor`.
- Commands:
  - Install: `uv sync --locked`
  - Test: `uv run pytest` (CI form: `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing`)
  - Lint and format: `uv run ruff check .` and `uv run ruff format --check .`
  - Type check: `uv run mypy .`
  - Readiness: `uv run node .sdd/doctor/run-doctor.mjs`
- Pre-existing failures: none. On 2026-10-10 at `fff0f2d`, measured by the architect:
  - `uv run pytest -q` -> `137 passed`.
  - `uv run ruff check .` -> `All checks passed!`.
  - `uv run ruff format --check .` -> `67 files already formatted`.
  - `uv run mypy .` -> `Success: no issues found in 15 source files`.
  - `git grep -n -i -e datosabiertos -e compraspublicas -- tests` -> no match.
  - `uv run node .sdd/doctor/run-doctor.mjs` -> `31 ok, 0 skipped, 0 warned, 0 failed` (run with these three spec files in place).

## Outcomes
Order and ownership:
1. **O1 (executor) first**, before any red test: add the dependency, so the red tests fail because the F2 modules are missing, not because `httpx` is.
2. **O2 (test-writer)** writes the red tests for O3 to O5 (files and `-k` names from `execution-plan.md` § Proposed approach) and fills their Tests and Red lines.
   - The correct red reason is that a pinned F2 module does not exist yet: `ModuleNotFoundError` for `ec_procurement_quality.domain.source_response`, `ec_procurement_quality.application.procurement_source` or `ec_procurement_quality.infrastructure.sercop_source`.
   - For the new layer check, the reason is `AssertionError` saying `infrastructure/sercop_source.py` is missing.
   - A typo in a test, or a missing `httpx`, is never a correct red reason.
   - The human reviews the red tests at gate 2.
3. **O3 to O5 (executor)**, in that order. Each relies only on the names, signatures and rules in `execution-plan.md` § Binding constraints. Every `httpx` signature is confirmed against `.venv/Lib/site-packages/httpx/`; no MCP is used.
4. Then **O6 to O8 (executor)** and **O9 (auditor)**.
5. No role creates or edits the fixture files, ADR 0006 or the F1 modules. If a fixture seems wrong, stop and report it.

- [ ] **O1** (AC13) — executor: add `httpx` as the first runtime dependency with `uv add httpx`.
  - Done when:
    - `[project] dependencies` holds only the `httpx` entry that `uv` wrote, and `uv.lock` is updated.
    - `uv lock --check` and `uv sync --locked` exit 0.
    - `git diff main -- pyproject.toml` shows only that line.
    - The 137 baseline tests still pass, and `uv run ruff check .`, `uv run ruff format --check .` and `uv run mypy .` exit 0.
    - The resolved `httpx` version and its transitive packages are recorded here.
  - Evidence: [command and result]
- [ ] **O2** (AC1 to AC12) — test-writer: the red tests.
  - Files: `tests/unit/test_source_response.py` and `tests/unit/test_sercop_source.py` (new), with the network guard, and `tests/unit/test_layers.py` (new check `test_layer_only_infrastructure_imports_httpx`).
  - Synthetic bodies are labelled as synthetic. `search_no_results.json` is labelled inferred. Fixtures are read only.
  - Tests: [files and counts]
  - Red: [command and failing result, with the reason]
- [ ] **O3** (AC3, AC8, AC10, AC12) — executor: `src/ec_procurement_quality/domain/source_response.py`.
  - It holds `RawResponse` (the pinned attributes and validation; `repr` and `str` without content or header values) and `SourceError`, `SourceTransportError`, `SourceStatusError` and `IncompleteResponseError`, each with `response`.
  - Standard library only; passes strict `mypy`.
  - Tests: `tests/unit/test_source_response.py`
  - Green: [command and passing result]
- [ ] **O4** (AC1, AC2, AC4, AC12) — executor: `src/ec_procurement_quality/application/procurement_source.py`.
  - It holds `SearchPage` (with `is_beyond_last_page`), `RecordResponse` and the `ProcurementSource` protocol, exactly as pinned.
  - It imports only the standard library and `domain`.
  - Tests: covered by `tests/unit/test_sercop_source.py` and `tests/unit/test_layers.py`
  - Green: [command and passing result]
- [ ] **O5** (AC1 to AC11, AC12) — executor: `src/ec_procurement_quality/infrastructure/sercop_source.py`, with `DEFAULT_BASE_URL` and `SercopSource`.
  - Request format: URL built with `quote(..., safe="")`; `Accept-Encoding: identity`; no cookies; no redirects; one request per call; the pinned timeouts.
  - Response capture: streamed raw bytes, Latin-1 headers in order, `now()` once per response.
  - The closed outcome mapping and the completeness checks.
  - Pacing through the injected `monotonic` and `sleep`.
  - No logging, and no `JSONDecodeError` or `UnicodeDecodeError` in error chains.
  - `close()` and context manager.
  - Tests: `tests/unit/test_sercop_source.py`
  - Green: [each focused command of `execution-plan.md` § Validation AC1 to AC12, and its result]
- [ ] **O6** Migration (AC12, AC13): existing consumers keep working.
  - `tests/unit/test_cli.py`, the three F1 test files and the existing tests in `tests/unit/test_layers.py` are not edited (a docstring mention of F2 is allowed) and still pass.
  - The F1 modules and `interfaces/cli.py` are unchanged, and the fixtures are unchanged since gate 1.
  - No new file directly in `src/ec_procurement_quality/`, and no CLI command.
  - Evidence: [the AC13 `git diff` and `git log` commands and their results]
- [ ] **O7** Docs (AC14):
  - `README.md`: § Architecture no longer says no source access exists; § Technologies names the SERCOP adapter as a library with no command and `httpx` as the first runtime dependency, and removes it from "Planned".
  - `CHANGELOG.md` § Unreleased: an `Added` entry.
  - `docs/architecture.md` § Open questions: the first flow uses `search_ocds` with the buyer-name query and `api/record`.
  - Checked with the AC14 commands.
  - Green: [command and result]
- [ ] **O8** Broader suite vs baseline (AC13):
  - `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing` passes, with the 137 baseline tests plus the new ones.
  - `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy .`, `uv lock --check` and `uv sync --locked` exit 0.
  - The doctor reports `0 warned, 0 failed`.
  - `uv run ec-procurement-quality --version` prints `ec-procurement-quality 0.1.0`.
  - `git diff --check` is clean.
  - `git grep -n -i --untracked -e datosabiertos -e compraspublicas -- tests` finds nothing.
  - On the F2 pull request, the `feedback` and `Tests` checks are green. Record a check that has not run yet as unavailable, never as a pass.
  - Green: [commands and results]
- [ ] **O9** Independent audit (`specs/sercop-source-adapter/audit.md`, written by the auditor): [verdict]

## Working state
- Updated: 2026-10-10
- Outcome: none started
- Phase: specs approved (Revision 1), gate 1 passed on 2026-10-10
- In progress: nothing
- Last command (architect, plan evidence): `uv run pytest -q` -> `137 passed` at `fff0f2d`
- Next step:
  1. Gate 1 passed: the human approved the specs, the fixtures and the observations, accepted ADR 0006, and the decision is in the `intent.md` `Approval` line.
  2. Commit the observations, the ADR, the fixtures and the specs.
  3. Then O1 (executor).

## Finding responses
| Finding | Response | Evidence |
|---|---|---|

## Checkpoint
Specs Revision 1 approved on `feat/sercop-source-adapter` (base `fff0f2d`) at gate 1 on 2026-10-10, with ADR 0006 accepted. Resume at O1.
