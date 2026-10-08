# Tasks: Project skeleton (F0)

## Status
Implementing

## Baseline
- Base commit: `699cae5` (`main`, "Merge pull request #9 from Vladimirjon/chore/day-4-harny-full-install")
- Branch: `main` when these specs were written. The executor creates `feat/project-skeleton` from `699cae5` before O1, because `AGENTS.md` and the repository rules forbid working on `main`.
- Interpreter: Python 3.13.9 in `.venv` (created by `python -m venv`), uv 0.12.23, Node v22.23.1
- Cwd: the repository root, `ec-public-procurement-quality-monitor`
- Commands:
  - Install: `uv sync --locked`
  - Test: `uv run pytest`
  - Lint and format: `uv run ruff check .` and `uv run ruff format --check .`
  - Type check: `uv run mypy .`
  - CI runner locally: `uv run node .sdd/feedback/run-feedback.mjs run --whole-project --commands "$(cat .sdd/git-hooks/commands.json)"`
  - Readiness: `node .sdd/doctor/run-doctor.mjs`
- Pre-existing failures:
  - No test suite, lint configuration or type configuration exists yet, so there are no test, lint or type failures to compare against.
  - Doctor on 2026-10-07: `29 ok, 2 skipped, 0 warned, 1 failed`. The only failure was `spec-state:project-skeleton` reporting that `tasks.md` was missing, which this file resolves. The two skips are `knowledge-base` (no `specs/current/`) and `pytest` (not installed).
  - Local feedback runner on 2026-10-07: `harny-feedback: 0 of 2 command(s) ran, 2 skipped.`, exit 0.

## Outcomes
Order: O1 is done by the executor before the red phase. pytest cannot run, and `uv_build` cannot install the package, until `pyproject.toml`, `uv.lock` and `src/ec_procurement_quality/__init__.py` exist. O1 contains no behavior that a unit test covers.

Then the test-writer writes the red tests for O2 and O3 and fills their Tests and Red lines. The human reviews them at the post-red-tests gate. After that, the executor does O2 to O8 in order, then the auditor does O9. Manual and CI checks are explicit outcomes (O7, O8), each naming who runs it.

- [ ] **O1** (AC1, AC2, AC3, AC7, AC8): Toolchain bootstrap, done by the executor before the red phase.
  - What it delivers:
    - `pyproject.toml`, written by hand and with no `authors` email, containing: project name `ec-procurement-quality`, version `0.1.0`, `requires-python = ">=3.13"`, empty runtime dependencies, and build system `uv_build>=0.12.23,<0.13`.
    - `ruff`, `mypy` and `pytest` in the `[dependency-groups] dev` group, added with `uv add --dev`. This command triggers the permission prompt, which the human approves.
    - ruff configuration with default rules and formatting.
    - mypy configuration: global defaults, plus an override for `ec_procurement_quality.domain.*` with the explicit strict flags from execution-plan § Binding constraints, and no `strict = true` inside the override.
    - pytest configuration with `testpaths = ["tests"]`.
    - The committed `uv.lock`.
    - `src/ec_procurement_quality/__init__.py` as the only file in the package root. The root may never hold more than 2 files of its own.
  - Tests: none. This outcome is checked by commands, per execution-plan § Validation for AC1, AC2, AC3, AC7 and AC8.
  - Red: not applicable, because no behavior is under test.
  - Green: all of the following must hold.
    - `uv sync --locked` exits 0.
    - `git status --short -- uv.lock` shows `uv.lock` only as a new file, and a second `uv sync --locked` changes nothing.
    - `uv run ruff check .`, `uv run ruff format --check .` and `uv run mypy .` exit 0.
    - `uv run pytest` exits 5 with "no tests ran". That is the expected state before the red phase.
- [ ] **O2** (AC6): The four layer packages `domain`, `application`, `infrastructure` and `interfaces` exist under `src/ec_procurement_quality/`, can be imported, and contain only what makes them packages. `domain` imports nothing outside the standard library and itself.
  - Tests: to be filled in by the test-writer. The unit test in `tests/unit/` imports the four layer packages.
  - Red: to be filled in by the test-writer. The expected right reason is `ModuleNotFoundError` for the `ec_procurement_quality` layer packages, from `uv run pytest tests/unit -q`.
  - Green: `uv run pytest tests/unit -q -k layer` passes, and `uv run python -c "import ec_procurement_quality.domain, ec_procurement_quality.application, ec_procurement_quality.infrastructure, ec_procurement_quality.interfaces"` exits 0 with no output.
- [ ] **O3** (AC4, AC5, AC9): The CLI `ec-procurement-quality` exists.
  - What it delivers:
    - The console script `ec-procurement-quality` in `[project.scripts]` targets `ec_procurement_quality.interfaces.cli:main`. `main` accepts an optional argument list.
    - `--version` prints exactly `ec-procurement-quality 0.1.0` and a newline to stdout and exits 0. The version is read from the installed distribution metadata and never hard-coded. `prog` is set explicitly.
    - An unknown option exits 2, prints nothing to stdout, and writes a usage error naming the option to stderr.
    - Only the standard library is used.
  - Tests: to be filled in by the test-writer. The unit tests in `tests/unit/` check the `--version` output against `[project] version` read with `tomllib`, and the unknown-option exit code and streams.
  - Red: to be filled in by the test-writer. The expected right reason is `ModuleNotFoundError` for `ec_procurement_quality.interfaces.cli`, from `uv run pytest tests/unit -q`.
  - Green: all of the following must hold.
    - `uv run pytest tests/unit -q` passes, with at least 1 test passed.
    - `uv run ec-procurement-quality --version` prints `ec-procurement-quality 0.1.0` and exits 0.
    - `uv run ec-procurement-quality --bogus` exits 2.
    - `uv sync --locked` still exits 0 after the `[project.scripts]` change.
- [ ] **O4** (AC10, AC11, AC13): The `feedback` CI job gets three new steps, each with a comment saying it is hand-maintained and must be restored after `harny init` or `update`. They go in `.github/workflows/harny-feedback.yml` after `Checkout` and before the harny-generated block.
  1. `astral-sh/setup-uv`, pinned to a commit SHA with a `# v10.1.0` comment or to a full version tag, with `python-version: "3.13"`. The executor re-checks the latest release before pinning.
  2. `uv sync --locked`.
  3. Add `$GITHUB_WORKSPACE/.venv/bin` to `$GITHUB_PATH`.
  - The generated block, the job id `feedback` and the `Secret scan (gitleaks)` step stay unchanged.
  - Tests: none (CI configuration; checked by O7 and O8).
  - Red: not applicable.
  - Green, locally: the runner command from Baseline prints `harny-feedback: 2 of 2 command(s) ran, 0 skipped.` and exits 0, and `git diff 699cae5 -- .github/workflows/harny-feedback.yml` shows no line changed between the harny markers.
- [ ] **O5** Migration (AC12): The existing consumers keep working with no change to their files: the doctor, the Stop, SubagentStop and pre-commit hooks, the gitleaks step, the local `.venv` and branch protection's `feedback` check.
  - `node .sdd/doctor/run-doctor.mjs` reports `0 warned, 0 failed`. In particular there is no `repo-readiness:component-doc:src/ec_procurement_quality` warning.
  - `uv run node .sdd/doctor/run-doctor.mjs` reports `OK pytest`.
  - `.venv\Scripts\python.exe --version` (PowerShell) prints Python 3.13.x. Record whether `uv sync` recreated `.venv`.
  - `uv run ruff check $(git diff --name-only 699cae5 -- '*.py')` and `uv run mypy $(git diff --name-only 699cae5 -- '*.py')` exit 0. This is the per-file form the hooks use. If mypy cannot resolve `ec_procurement_quality` from a test file, add `mypy_path = "src"` and record why.
  - `git diff --check` is clean.
  - No file under `.sdd/` and no `.claude/settings.json` change.
- [ ] **O6** Docs (AC13):
  - `README.md` lists the real install, CLI, lint, format, type and test commands and stops calling the CLI and modules planned. It also states that the Stop and pre-commit hooks run `ruff` and `mypy` only when `.venv` is on `PATH`.
  - `AGENTS.md` § Current commands drops "There is no application command, test suite, or dependency configuration yet" and lists the same commands.
  - `docs/repository-settings.md` gets a note that names the hand-maintained CI steps (the `astral-sh/setup-uv` step and the two after it) and explains how to restore them after `harny init` or `update`. Its existing line about the Python Dependabot ecosystem is kept.
  - Green:
    - `git grep -n "setup-uv" -- .github/workflows/harny-feedback.yml docs/repository-settings.md` shows the step with its adjacent comment and the note.
    - `git grep -n -i "PATH" -- README.md` shows the hook limitation.
- [ ] **O7** Local manual verification (AC1, AC2, AC3, AC7, AC8, AC11, AC12). The executor runs these after O1 to O6 are committed on `feat/project-skeleton`. The auditor re-runs them or records them as reused or unavailable. Probe files and throwaway clones are never committed.
  - AC1: run `tmp=$(mktemp -d) && git clone . "$tmp" && cd "$tmp" && uv sync --locked`. Expect exit 0, and `git status --short` in the clone shows no change.
  - AC2: in a throwaway clone, change a version bound in `[dependency-groups] dev` without running `uv lock`, then run `uv sync --locked; echo $?`. Expect a non-zero exit and an error saying the lockfile needs updating. Record the exact message.
  - AC3: in a throwaway clone, run `uv sync --python 3.12; echo $?`. Expect a non-zero exit and an error naming `>=3.13`. This may download Python 3.12. If there is no network, record it as unavailable, never as a pass.
  - AC7: `uv run ruff check .` and `uv run ruff format --check .` both exit 0.
  - AC8: with `src/ec_procurement_quality/domain/probe.py` containing `def f(x): return x`, `uv run mypy .` exits non-zero with "missing a type annotation". With the same file moved to `src/ec_procurement_quality/application/`, it exits 0. Delete the probe afterwards; `uv run mypy .` then exits 0 and `git status --short` shows no probe file.
  - AC11: add an unused `import os` to a file under `src/`, run the runner command from Baseline, and expect `finding from \`ruff\`` and exit 2. Then revert the file and confirm `git status --short` is clean.
  - AC12: the O5 commands give the same results on the final commit.
- [ ] **O8** CI verification (AC1, AC10, AC11, AC12). The human pushes `feat/project-skeleton` and opens the F0 pull request. The human, or the conductor reading the run log with `gh`, records the evidence below.
  - AC10: the `harny feedback (Python)` step log ends with `harny-feedback: 2 of 2 command(s) ran, 0 skipped.` and the `feedback` check is green.
  - AC1: the `uv sync --locked` step is green on the runner.
  - AC12: the `Secret scan (gitleaks)` step ran and passed.
  - AC11 (optional, human): the same unused-import change on a throwaway branch or draft pull request turns the `feedback` check red. Close it without merging. If skipped, record that only local evidence from O7 exists.
- [ ] **O9** Broader suite vs baseline (AC9, AC12):
  - `uv run pytest` exits 0 with all tests passed. The baseline had no suite.
  - `uv run ruff check .`, `uv run ruff format --check .` and `uv run mypy .` exit 0.
  - `node .sdd/doctor/run-doctor.mjs` reports `0 warned, 0 failed`, an improvement on the baseline's single `spec-state` failure. No new failure appears.
- [ ] **O10** Independent audit (AC1 to AC13): the auditor writes `specs/project-skeleton/audit.md` with a verdict. The human accepts or rejects it at the post-audit gate.

## Working state
- Updated: 2026-10-07
- Outcome: O1
- Phase: not started. The specs are approved (intent Revision 2, execution-plan Revision 1 and this file, by Vladimirjon on 2026-10-07); the next step is the toolchain bootstrap.
- In progress: nothing
- Last command: `node .sdd/doctor/run-doctor.mjs` -> `29 ok, 2 skipped, 0 warned, 1 failed` (the missing `tasks.md`, now written)
- Next step: the executor creates `feat/project-skeleton` from `699cae5` and does O1. Then the test-writer writes the red tests for O2 and O3, and the human reviews them at the post-red-tests gate.

## Finding responses
| Finding | Response | Evidence |
|---|---|---|

## Checkpoint
Nothing implemented yet. Resume at O1 on branch `feat/project-skeleton`, created from `699cae5`.
