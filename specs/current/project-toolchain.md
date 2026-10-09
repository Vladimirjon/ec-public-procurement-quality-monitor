# Project Toolchain Specification

> Last synced: 2026-10-08. Owned artifacts: `pyproject.toml`, `uv.lock`, `src/ec_procurement_quality/`, `tests/unit/`, `.github/workflows/harny-feedback.yml` (hand-maintained steps), `.github/workflows/tests.yml`.

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
`interfaces` as importable packages under `src/ec_procurement_quality/`, where
`domain`, `application` and `infrastructure` hold only what makes them
packages, and `domain` imports nothing outside the standard library and itself.

**Source:** project-skeleton · intent.md § AC6; execution-plan.md § Binding constraints "Layer boundaries"

#### Scenario: Import the layers
- **WHEN** the four layer packages are imported in one `python -c` command
- **THEN** it exits 0 with no output

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
and not to the other layers.

**Source:** project-skeleton · intent.md § AC8

#### Scenario: Untyped function in domain
- **WHEN** `def f(x): return x` is placed in `src/ec_procurement_quality/domain/probe.py` and `uv run mypy .` is run
- **THEN** it exits non-zero with a "missing a type annotation" error for that file

#### Scenario: Untyped function in application
- **WHEN** the same file is placed in `src/ec_procurement_quality/application/`
- **THEN** `uv run mypy .` exits 0

### Requirement: PT-6 — Unit test suite

The system SHALL run a pytest suite from `tests/unit/` with `uv run pytest`,
including a unit test that proves the version command output (CLI-1).

**Source:** project-skeleton · intent.md § AC9

#### Scenario: Run the suite
- **WHEN** `uv run pytest` is run
- **THEN** it exits 0 with 7 tests passed at F0, including the version test in `tests/unit/test_cli.py`

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
- **THEN** the summary shows `0 warned, 0 failed` (`30 ok, 1 skipped, 0 warned, 0 failed` once archived; the `pytest` readiness line is `OK` when run through `uv run`)

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

The system SHALL run the unit tests with a coverage report in a separate
`Tests` workflow (job `tests`) on every pull request and on every push to
`main`, installing with `uv sync --locked` and running
`uv run pytest --cov=ec_procurement_quality --cov-report=term-missing`.

**Source:** project-skeleton · intent.md § AC14

#### Scenario: Pull request
- **WHEN** a pull request is opened
- **THEN** the `Tests` job is green, its `Install dependencies` step ran `uv sync --locked`, and its `Run tests` log shows a `TOTAL` coverage row and `7 passed` (at F0). The push-to-`main` trigger is verified by inspection only

### Requirement: PT-11 — `pytest-cov` is a development-only dependency

The system SHALL record `pytest-cov` only in `[dependency-groups] dev` and
`uv.lock` (locked at 7.1.0, with `coverage` 7.16.2), keep `[project]
dependencies` empty, and make the CI test command work locally.

**Source:** project-skeleton · intent.md § AC15

#### Scenario: Local coverage run
- **WHEN** `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing` is run
- **THEN** it exits 0 with `7 passed` and a coverage table with a `TOTAL` row

### Requirement: PT-12 — A failing test fails `tests`; coverage alone never does

The system SHALL fail the CI test command when a test fails, and SHALL NOT
set a coverage threshold (`--cov-fail-under` or any coverage configuration).

**Source:** project-skeleton · intent.md § AC16

#### Scenario: Failing assertion
- **WHEN** a test with `assert False` is added under `tests/unit/` and the CI test command is run
- **THEN** it exits non-zero (`1 failed`), and the coverage percentage does not change the exit code (verified locally; see reservation F7)

## Invariants

1. Every CI install uses `uv sync --locked`; a drifted lockfile must fail,
   never re-resolve (ADR 0004 drift risk).
2. The harny-generated block of `harny-feedback.yml` is never hand-edited, and
   the job id `feedback` does not change, because branch protection requires it.
3. `src/ec_procurement_quality/` holds at most 2 files of its own: the doctor
   treats a direct child of `src/` with 3 or more files as a component and
   would warn about a missing `AGENTS.md`.
4. `[project] dependencies` stays empty until a runtime dependency is
   explicitly approved; development tools live in the `dev` group.
5. The `setup-uv` SHA is the same in `harny-feedback.yml` and `tests.yml` so
   Dependabot keeps both in step.

## Open reservations

| ID | Reservation | Severity | Source |
|---|---|---|---|
| F3 | The CI-side probe that an unused import turns `feedback` red was not run; only the local runner evidence exists | LOW | project-skeleton · audit.md |
| F4 | The Stop, SubagentStop and pre-commit hooks skip `ruff` and `mypy` when `.venv` is not on `PATH`; accepted and documented (PT-9) | LOW | project-skeleton · audit.md |
| F6 | `tasks.md` bookkeeping was stale at audit time; `tasks.md` says it was corrected afterwards, which the auditor did not re-check | LOW | project-skeleton · audit.md |
| F7 | The CI-side probe that a failing test turns `tests` red was not run; only the local exit code exists | LOW | project-skeleton · audit.md |

`tests` became a required status check of `main` on 2026-10-09, after the F0
audit, as a human GitHub settings action outside F0 scope (see
`docs/repository-settings.md`).

## Contributing features

| Feature | Shipped | What it established |
|---|---|---|
| project-skeleton (F0) | 2026-10-08 | The `uv` package and lockfile, Python floor, four layer packages, ruff, mypy and pytest configuration, the `feedback` CI setup steps and the `Tests` workflow with `pytest-cov` (PT-1 to PT-12) |

## Related ADRs

None yet. The project-level ADRs live in `docs/adr/` and carry no
`Capability:` field; ADR 0004 (Python toolchain) is the binding decision for
this capability.
