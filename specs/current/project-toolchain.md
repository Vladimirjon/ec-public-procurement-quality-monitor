# Project Toolchain Specification

> Last synced: 2026-10-28. Owned artifacts: `pyproject.toml`, `uv.lock`, `src/ec_procurement_quality/`, `tests/unit/`, `tests/process/`, `tests/integration/conftest.py`, `.github/workflows/harny-feedback.yml` (hand-maintained steps), `.github/workflows/tests.yml`.

## Purpose

How the project installs, lints, type-checks and tests, locally and in CI,
including the four-layer package layout. It is separate from `cli` because it
describes the engineering gate around the code, not any product behavior.

## Requirements

### Requirement: PT-1 — Reproducible install from the lockfile

The system SHALL install from the committed `uv.lock` with `uv sync --locked`
without changing `uv.lock` or `pyproject.toml`, and SHALL reject a lockfile
that no longer matches `pyproject.toml` instead of re-resolving it.

**Source:** project-skeleton · intent.md § AC1, AC2

#### Scenario: Fresh clone
- **WHEN** `uv sync --locked` is run in a clean clone
- **THEN** it exits 0 and `git status --short` shows no change to `uv.lock` or `pyproject.toml`

#### Scenario: Stale lockfile
- **WHEN** a dependency bound in `pyproject.toml` is edited without `uv lock`, then `uv sync --locked` is run
- **THEN** it exits non-zero with an error saying the lockfile needs to be updated

### Requirement: PT-2 — Python 3.13 floor

The system SHALL declare `requires-python = ">=3.13"` and refuse older Python
versions.

**Source:** project-skeleton · intent.md § AC3

#### Scenario: Python 3.12
- **WHEN** `uv sync --python 3.12` is run
- **THEN** it exits non-zero with an error naming the project's `>=3.13` requirement and installs nothing

### Requirement: PT-3 — Four importable layer packages

The system SHALL provide `domain`, `application`, `infrastructure` and
`interfaces` as importable packages under `src/ec_procurement_quality/`,
where `domain` imports nothing outside the standard library and itself, and
`application` imports nothing outside the standard library, `domain` and
itself, and only `infrastructure` imports `httpx` (ADR 0006) and `psycopg`
(ADR 0007). The four rules are enforced by tests in
`tests/unit/test_layers.py`. (The clause that
`domain`, `application` and `infrastructure` hold only what makes them
packages was retired at F1; modules live inside the layer packages, never
directly in `src/ec_procurement_quality/`, see invariant 3.)

**Source:** project-skeleton · intent.md § AC6; execution-plan.md § Binding constraints "Layer boundaries"; raw-evidence-store · intent.md § AC11, § Constraints "Current-truth note"; execution-plan.md § Binding constraints "Layer imports"; sercop-source-adapter · intent.md § AC12, § Constraints "Current-truth notes"; postgres-persistence · intent.md § AC13, § Constraints "Current-truth notes"; execution-plan.md § Binding constraints "Other constraints"

#### Scenario: Import the layers
- **WHEN** the four layer packages are imported in one `python -c` command
- **THEN** it exits 0 with no output

#### Scenario: Layer import rules
- **WHEN** `uv run pytest tests/unit -q -k layer` is run
- **THEN** it passes, including the check that every module in `domain` imports only the standard library and `domain`, the check that every module in `application` imports only the standard library, `domain` and `application`, and `test_layer_only_infrastructure_imports_httpx`, which fails if a module outside `infrastructure` imports `httpx`, and `test_layer_only_infrastructure_imports_psycopg`, which fails if a module outside `infrastructure` imports `psycopg` in any form (it also requires one `infrastructure` module to import it, so it cannot pass vacuously)

### Requirement: PT-4 — Lint and format pass on the whole repository

The system SHALL pass `ruff check .` and `ruff format --check .` on the whole
repository.

**Source:** project-skeleton · intent.md § AC7

#### Scenario: Clean repository
- **WHEN** `uv run ruff check .` and `uv run ruff format --check .` are run
- **THEN** both exit 0

### Requirement: PT-5 — Strict type checking in `domain` only

The system SHALL pass `mypy .` on the whole repository, with strict checking
applied to `ec_procurement_quality.domain.*` through explicit per-module flags
and not to the other layers. The `[tool.mypy]` table also sets
`explicit_package_bases = true` and `mypy_path = "src"` (decision F-1 of the
human, F4), so that `mypy .` accepts the several `conftest.py` files of the test
folders; no strictness changes outside `domain`.

**Source:** project-skeleton · intent.md § AC8; ingest-command · intent.md § AC18, AC20 (decision F-1); execution-plan.md § Ownership

#### Scenario: Untyped function in domain
- **WHEN** `def f(x): return x` is placed in `src/ec_procurement_quality/domain/probe.py` and `uv run mypy .` is run
- **THEN** it exits non-zero with a "missing a type annotation" error for that file

#### Scenario: Untyped function in application
- **WHEN** the same file is placed in `src/ec_procurement_quality/application/`
- **THEN** `uv run mypy .` exits 0

### Requirement: PT-6 — Unit test suite

The system SHALL run a pytest suite from `tests/unit/`, `tests/integration/`
and, since F4, `tests/process/` (child-process tests of the CLI's output
streams) with `uv run pytest`, including a unit test that proves the version command
output (CLI-1). The integration tests are skipped when no database is
configured (PT-13).

**Source:** project-skeleton · intent.md § AC9; postgres-persistence · intent.md § AC14, § Constraints "Current-truth notes"; ingest-command · audit.md round 8 § Commands run

#### Scenario: Run the suite
- **WHEN** `uv run pytest` is run
- **THEN** it exits 0 with every test passed (7 at F0; 137 at F1, the 7 F0 tests plus 130 raw evidence tests; 961 at F2, the 137 earlier tests plus 824 source adapter tests; at F3, 1307 tests, of which 1132 passed and 175 integration tests were skipped without a database, and all 1307 passed with `uv run --env-file .env pytest`; at F4, 2976 tests, of which 2710 passed and 266 integration tests were skipped without a database, and all 2976 passed with `uv run --env-file .env pytest`, 0 skipped), including the version test in `tests/unit/test_cli.py`

### Requirement: PT-7 — The `feedback` CI check really runs ruff and mypy

The system SHALL run `ruff` and `mypy` in the required `feedback` CI job
through three hand-maintained steps (`astral-sh/setup-uv` pinned to a commit
SHA with Python 3.13, `uv sync --locked`, and `.venv/bin` appended to
`GITHUB_PATH`), so the `harny feedback (Python)` step is not skipped, and a
lint or type error SHALL fail the check.

**Source:** project-skeleton · intent.md § AC10, AC11

#### Scenario: Pull request
- **WHEN** a pull request is checked
- **THEN** the `harny feedback (Python)` log ends with `harny-feedback: 2 of 2 command(s) ran, 0 skipped.` and the `feedback` check is green

#### Scenario: Unused import
- **WHEN** an unused import is added to a file under `src/` and the runner is invoked through `uv run`
- **THEN** the runner prints a finding from `ruff` and exits 2 (verified locally; see reservation F3)

### Requirement: PT-8 — Existing checks keep passing

The system SHALL keep `node .sdd/doctor/run-doctor.mjs` at 0 warned and 0
failed, keep the `Secret scan (gitleaks)` step in the `feedback` job, keep
`.venv\Scripts\python.exe --version` printing a Python 3.13 version, and keep
`git diff --check` clean.

**Source:** project-skeleton · intent.md § AC12

#### Scenario: Doctor
- **WHEN** `node .sdd/doctor/run-doctor.mjs` is run
- **THEN** the summary shows `0 warned, 0 failed` (once archived, `31 ok, 0 skipped, 0 warned, 0 failed` when run through `uv run`, where the `pytest` readiness line is `OK`; `30 ok, 1 skipped, 0 warned, 0 failed` without `uv run`, where that line is skipped)

### Requirement: PT-9 — Hand-maintained CI steps and hook limitation are documented

The system SHALL document, next to the `setup-uv` step in
`harny-feedback.yml` and in `docs/repository-settings.md`, that the three CI
setup steps are hand-maintained and how to restore them after `harny init` or
`update`, and SHALL document in `README.md` that the Stop and pre-commit hooks
run `ruff` and `mypy` only when `.venv` is on `PATH`.

**Source:** project-skeleton · intent.md § AC13

#### Scenario: After a harny update
- **WHEN** `harny init` or `update` has rewritten the workflow
- **THEN** the restore note in `docs/repository-settings.md` lists the three steps and the check that `feedback` still reports `2 of 2 command(s) ran`

### Requirement: PT-10 — The `Tests` workflow reports coverage in CI

The system SHALL run the unit and integration tests with a coverage report in
a separate `Tests` workflow (job `tests`, which starts a `postgres:18` service
container with a health check and the five `POSTGRES_*` variables) on every
pull request and on every push to `main`, installing with
`uv sync --locked` and running
`uv run pytest --cov=ec_procurement_quality --cov-report=term-missing`.

**Source:** project-skeleton · intent.md § AC14; postgres-persistence · intent.md § AC15; execution-plan.md § Binding constraints "CI"; ingest-command · audit.md round 8 § Commands run; tasks.md § Working state

#### Scenario: Pull request
- **WHEN** a pull request is opened
- **THEN** the `Tests` job is green, its `Install dependencies` step ran `uv sync --locked`, and its `Run tests` log shows a `TOTAL` coverage row and every test passed (`7 passed` at F0, `133 passed` on the F1 head `392145f`; 137 locally at F1 with the `race` tests; at F2, `890 passed` on the PR #16 head `dc78500`, the run the audit read, and `961 passed` on the PR #16 head `b939248`, confirmed by a read of the PR checks after the audit, outside `audit.md`; 961 locally; at F3, `1298 passed` with no skipped count on the PR #23 head `ee9ac87`, run `38604796727`, whose log shows `docker pull postgres:18` and `PostgreSQL 18.6`, the run the audit read; 1307 locally after the tests added for audit findings F3 and F4; at F4, `2976 passed` on the PR #26 head `108c5a0`, run `40617404828`, Linux, Python 3.13.18, total coverage 98 %, the run the audit read, and again `2976 passed` on `61fb1c1`, run `40718224389`; 2976 locally with the database). The push-to-`main` trigger is verified by inspection only

### Requirement: PT-11 — `pytest-cov` is development-only, and `httpx` and `psycopg` are the only runtime dependencies

The system SHALL record `pytest-cov` only in `[dependency-groups] dev` and
`uv.lock` (locked at 7.1.0, with `coverage` 7.16.2), keep `[project]
dependencies` to the two approved runtime dependencies, `httpx`
(`httpx>=0.28.1`, locked at 0.28.1; ADR 0006) and `psycopg[binary]`
(`psycopg[binary]>=3.3.6`, locked at 3.3.6 with `psycopg-binary` 3.3.6 and the
Windows-only `tzdata` 2026.5; ADR 0007), and make the CI test command work
locally. (Until F2 this clause read "keep `[project] dependencies` empty"; F2
added `httpx` and F3 added `psycopg`, each with the human's approval.)

**Source:** project-skeleton · intent.md § AC15; sercop-source-adapter · intent.md § AC13, § Constraints "Current-truth notes"; postgres-persistence · intent.md § AC16, § Open questions 2

#### Scenario: Local coverage run
- **WHEN** `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing` is run
- **THEN** it exits 0 with every test passed (`7 passed` at F0, 137 at F1, 961 at F2, 1307 at F3 with the integration tests run, 1132 passed and 175 skipped without a database) and a coverage table with a `TOTAL` row

#### Scenario: Runtime dependencies
- **WHEN** `git diff main -- pyproject.toml` is read for F2
- **THEN** it adds only an `httpx` entry to `[project] dependencies`, and `uv sync --locked` and `uv lock --check` exit 0

#### Scenario: Second runtime dependency
- **WHEN** `git diff main -- pyproject.toml` is read for F3
- **THEN** it adds only the `psycopg[binary]>=3.3.6` entry to `[project] dependencies` and the `integration` marker to the pytest configuration, `uv.lock` gains only `psycopg`, `psycopg-binary` and `tzdata` (22 to 25 packages), and `uv sync --locked` and `uv lock --check` exit 0

### Requirement: PT-12 — A failing test fails `tests`; coverage alone never does

The system SHALL fail the CI test command when a test fails, and SHALL NOT
set a coverage threshold (`--cov-fail-under` or any coverage configuration).

**Source:** project-skeleton · intent.md § AC16

#### Scenario: Failing assertion
- **WHEN** a test with `assert False` is added under `tests/unit/` and the CI test command is run
- **THEN** it exits non-zero (`1 failed`), and the coverage percentage does not change the exit code (verified locally; see reservation F7)

### Requirement: PT-13 — Integration tests run in one throwaway database each, and skip or fail by policy

The system SHALL keep the integration tests under `tests/integration/`, marked
`integration`, each running in its own throwaway database named
`ecpq_test_<hex>`, created for that test through an admin connection and dropped
with `DROP DATABASE ... WITH (FORCE)` when it ends, never in the database named
by `POSTGRES_DB`. Runner tests SHALL start from an empty database copied from
`template0`; every other test SHALL start from a copy of a migrated template
that the session creates once, closes to connections and drops at session end.
At session end it SHALL check that no database it created remains and that the
configured database's user objects are unchanged. When a `POSTGRES_*` variable
is missing or the server cannot be reached, every integration test SHALL be
skipped with a reason naming `uv run --env-file .env pytest tests/integration`,
except that when the `CI` variable is `true` it SHALL fail instead.

**Source:** postgres-persistence · intent.md § AC14; execution-plan.md § Binding constraints "Tests"

#### Scenario: No database locally
- **WHEN** the `POSTGRES_*` variables are unset and `uv run pytest tests/integration -q -rs` is run
- **THEN** every integration test is skipped with that reason and the exit code is 0

#### Scenario: No database in CI
- **WHEN** the same command is run with `CI=true`
- **THEN** every integration test fails, none is skipped, and the exit code is non-zero

#### Scenario: Database available
- **WHEN** `uv run --env-file .env pytest tests/integration -q` is run against the Compose PostgreSQL
- **THEN** every test passes, and afterwards no database whose name starts with `ecpq_test_` remains

## Invariants

1. Every CI install uses `uv sync --locked`; a drifted lockfile must fail,
   never re-resolve (ADR 0004 drift risk).
2. The harny-generated block of `harny-feedback.yml` is never hand-edited, and
   the job id `feedback` does not change, because branch protection requires it.
3. `src/ec_procurement_quality/` holds at most 2 files of its own: the doctor
   treats a direct child of `src/` with 3 or more files as a component and
   would warn about a missing `AGENTS.md`.
4. `[project] dependencies` holds only runtime dependencies the human
   explicitly approved (today `httpx`, added by F2, and `psycopg[binary]`,
   added by F3, which fulfil this invariant); development tools live in the
   `dev` group.
5. The `setup-uv` SHA is the same in `harny-feedback.yml` and `tests.yml` so
   Dependabot keeps both in step.
6. No integration test creates, changes or drops an object in the database
   named by `POSTGRES_DB`; only `ecpq_test_`-prefixed databases are created and
   dropped.

## Open reservations

| ID | Reservation | Severity | Source |
|---|---|---|---|
| F3 | The CI-side probe that an unused import turns `feedback` red was not run; only the local runner evidence exists | LOW | project-skeleton · audit.md |
| F4 | The Stop, SubagentStop and pre-commit hooks skip `ruff` and `mypy` when `.venv` is not on `PATH`; accepted and documented (PT-9) | LOW | project-skeleton · audit.md |
| F6 | `tasks.md` bookkeeping was stale at audit time; `tasks.md` says it was corrected afterwards, which the auditor did not re-check | LOW | project-skeleton · audit.md |
| F7 | The CI-side probe that a failing test turns `tests` red was not run; only the local exit code exists | LOW | project-skeleton · audit.md |
| F-30 | `uv.lock` differs from `main` before F4 only by the already-locked transitive dependency `certifi` 2026.7.22 -> 2026.10.23 (a security update, GHSA-6q48-6c7w-9gw2; no package added, `pyproject.toml` unchanged for it, `uv audit --locked` clean). The literal "`uv.lock` is unchanged" checks of the F4 specs (AC18, AC20) are stale by exactly that one package. The human kept the update on 2026-10-28; no earlier authorization is recorded | LOW | ingest-command · audit.md round 8 § B F-30; tasks.md § Carried reservations |

`tests` became a required status check of `main` on 2026-10-09, after the F0
audit, as a human GitHub settings action outside F0 scope (see
`docs/repository-settings.md`).

## Contributing features

| Feature | Shipped | What it established |
|---|---|---|
| project-skeleton (F0) | 2026-10-08 | The `uv` package and lockfile, Python floor, four layer packages, ruff, mypy and pytest configuration, the `feedback` CI setup steps and the `Tests` workflow with `pytest-cov` (PT-1 to PT-12) |
| raw-evidence-store (F1) | 2026-10-09 | Modified PT-3 (the layers may hold modules; `application` imports only the standard library, `domain` and itself, enforced by a layer test) and PT-6, PT-10 and PT-11 (test counts restated: 137 at F1). Invariants 3 and 4 kept |
| sercop-source-adapter (F2) | 2026-10-12 | Modified PT-3 (only `infrastructure` may import `httpx`, enforced by a layer test), PT-11 (`[project] dependencies` holds `httpx`, the first approved runtime dependency, and Invariant 4 is fulfilled) and the counts of PT-6, PT-10 and PT-11 (961 at F2) |
| postgres-persistence (F3) | 2026-10-14 | Modified PT-3 (only `infrastructure` may import `psycopg`, enforced by a layer test), PT-6 (the suite includes `tests/integration/`), PT-10 (the `tests` job runs a `postgres:18` service and the integration tests) and PT-11 (`psycopg[binary]`, the second approved runtime dependency; Invariant 4 kept), restated the counts (1307 at F3), and added PT-13 (integration tier, one throwaway database per test, skip or fail policy) and Invariant 6 |
| ingest-command (F4) | 2026-10-28 | Restated the counts of PT-6 and PT-10 (2976 at F4; the suite now includes `tests/process/`), noted in PT-5 the two `[tool.mypy]` keys of decision F-1 (PT-3 unchanged: the layer tests also cover the new modules); registered reservation F-30 (the `certifi` lockfile update) |

## Related ADRs

None registered here. The project-level ADRs live in `docs/adr/` and carry no
`Capability:` field; ADR 0004 (Python toolchain) is the binding decision for
this capability, with ADR 0006 and ADR 0007 for its two runtime dependencies.
