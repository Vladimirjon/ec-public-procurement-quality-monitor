# Intent: Project skeleton (F0)

Revision: 2
Approval: Approved revision 2 by Vladimirjon on 2026-10-07

## Outcome
The repository becomes an installable Python 3.13 package managed by `uv`, with
a committed `uv.lock`, a `src/` layout holding the four architectural layers
(`domain`, `application`, `infrastructure`, `interfaces`), and a CLI whose only
behavior is `--version`. `ruff`, `mypy` (strict in `domain`) and `pytest` are
configured and pass locally, and the required `feedback` check in CI stops
skipping Python checks and actually runs `ruff` and `mypy` on every pull
request. No domain behavior, data source, database or storage is introduced.

## Acceptance criteria
- **AC1** A fresh clone installs reproducibly from the committed lockfile: `uv sync --locked` succeeds on Python 3.13 and creates or reuses `.venv` without changing `uv.lock`.
  Example: `uv sync --locked` in a clean clone -> exit code 0, and `git status --short` shows no change to `uv.lock` or `pyproject.toml`.
- **AC2** (failure) A lockfile that no longer matches `pyproject.toml` is rejected instead of silently re-resolved.
  Example: edit the dependency list in `pyproject.toml` without running `uv lock`, then `uv sync --locked` -> non-zero exit and an error saying the lockfile needs to be updated.
- **AC3** (failure) The project refuses Python versions older than 3.13, as declared by `requires-python = ">=3.13"`.
  Example: `uv sync --python 3.12` -> non-zero exit and an error naming the project's `>=3.13` Python requirement; nothing is installed.
- **AC4** The CLI command `ec-procurement-quality --version` prints exactly one line to standard output with the program name and the package version, and exits 0. The version shown is the one declared in `pyproject.toml` (`0.1.0` for this feature).
  Example: `uv run ec-procurement-quality --version` -> stdout `ec-procurement-quality 0.1.0`, exit code 0.
- **AC5** (failure) An unknown option is a usage error, not a silent success.
  Example: `uv run ec-procurement-quality --bogus` -> exit code 2, nothing on stdout, and a usage message on stderr that names the unrecognized argument `--bogus`.
- **AC6** The four layers exist as importable, empty packages under `src/ec_procurement_quality/`.
  Example: `uv run python -c "import ec_procurement_quality.domain, ec_procurement_quality.application, ec_procurement_quality.infrastructure, ec_procurement_quality.interfaces"` -> exit code 0, no output.
- **AC7** Lint and formatting pass on the whole repository.
  Example: `uv run ruff check .` -> exit code 0; `uv run ruff format --check .` -> exit code 0.
- **AC8** Type checking passes on the whole repository, and `domain` is checked in strict mode while the other layers are not.
  Example: `uv run mypy .` -> exit code 0. With a temporary file `src/ec_procurement_quality/domain/probe.py` containing `def f(x): return x`, `uv run mypy .` -> non-zero exit with a "missing a type annotation" error for that file; the same file placed in `src/ec_procurement_quality/application/` -> exit code 0.
- **AC9** The test suite runs and includes at least one unit test that proves the version command's output from AC4.
  Example: `uv run pytest` -> exit code 0, at least 1 test collected and passed, with the version test under `tests/unit/`.
- **AC10** The required `feedback` check in CI really runs `ruff` and `mypy` on the Python code instead of skipping them.
  Example: on a pull request with this feature, the `harny feedback (Python)` step log ends with `harny-feedback: 2 of 2 command(s) ran, 0 skipped.` and the `feedback` check is green. Today the same line reports `0 of 2 command(s) ran, 2 skipped.`
- **AC11** (failure) A lint or type error in Python code fails the `feedback` check.
  Example: a pull request (or the same runner invoked locally through `uv run`) that adds an unused import to a file under `src/` -> the step prints a finding from `ruff` and the `feedback` check fails.
- **AC12** (compatibility) Existing checks keep passing: `node .sdd/doctor/run-doctor.mjs` reports 0 failed and 0 warned; the `Secret scan (gitleaks)` step still runs in the `feedback` job; the `AGENTS.md` check `.venv\Scripts\python.exe --version` still prints a Python 3.13 version; and `git diff --check` is clean.
  Example: `uv run node .sdd/doctor/run-doctor.mjs` -> summary with `0 warned, 0 failed`, and the `pytest` readiness line changes from `SKIP` to `OK`.
- **AC13** (documentation) Two things are documented where a maintainer will find them. First, the hand-added CI setup step and how to restore it after a harny update. Second, the known limitation of the local hooks.
  Example: in `.github/workflows/harny-feedback.yml`, the step that uses `astral-sh/setup-uv` has a comment next to it saying it is hand-maintained and must be restored after `harny init` or `update`. `docs/repository-settings.md` has a note that names that step and explains how to restore it. `README.md` says that the per-turn Stop hook and the pre-commit hook run `ruff` and `mypy` only when `.venv` is on `PATH`, and skip them otherwise.

## Scope
**In**
- `pyproject.toml` with project metadata, `requires-python = ">=3.13"`, version `0.1.0`, a console script `ec-procurement-quality`, the `uv_build` build backend, no runtime dependencies, and `ruff`, `mypy` and `pytest` as development-only dependencies.
- Committed `uv.lock`.
- `src/ec_procurement_quality/` with the four layer packages, each empty apart from what a package needs to be importable, and the CLI entry point inside `interfaces`.
- Configuration for `ruff` (lint and format), `mypy` (strict for `domain` only) and `pytest`.
- At least one unit test in `tests/unit/` covering AC4.
- A setup step in the `feedback` job of `.github/workflows/harny-feedback.yml`, outside the harny-generated block. It uses the official `astral-sh/setup-uv` action pinned to an explicit version, uses Python 3.13, installs the locked development dependencies, and makes `ruff` and `mypy` visible to the harny runner.
- A short comment next to that setup step saying it is hand-maintained and must be restored after any `harny init` or `update`.
- A note in `docs/repository-settings.md` that names the setup step and explains how to restore it after any `harny init` or `update`.
- Documenting in `README.md` the known limitation that the per-turn Stop hook and the pre-commit hook run `ruff` and `mypy` only when `.venv` is on `PATH`.
- Updating `README.md` and the `AGENTS.md` § Current commands so they list the real install, CLI, lint, type and test commands and stop saying no command or test suite exists.

**Out**
- `.github/workflows/tests.yml` and running `pytest` or coverage in CI. Day 6 adds that workflow by hand as a separate learning step, and keeping it out leaves F0's CI change limited to making the existing `feedback` check honest.
- Adding `tests` to the required checks of `main` (Day 6).
- What a bare `ec-procurement-quality` (no arguments) does. That waits for the first real command.
- Changing the Stop hook, the pre-commit hook or their configuration so that `ruff` and `mypy` run without `.venv` on `PATH`.
- Installing `uv` in CI with `pip`.
- Sub-packages inside the layers (for example the local, untracked, empty folders `infrastructure/sercop`, `infrastructure/cache`, `interfaces/api`, `interfaces/workers`), and the empty `tests/contract`, `tests/integration`, `tests/end_to_end`, `tests/fixtures`, `data/`, `migrations/` and `powerbi/` folders.
- Any domain concept, use case, port or adapter; SERCOP access; PostgreSQL; raw or local storage; Docker Compose.
- Choosing a CLI framework (decision D-09, planned for Day 18).
- Dependabot updates for the Python ecosystem. The existing `github-actions` entry already tracks the new action, so `.github/dependabot.yml` does not change.
- Editing the harny-generated block of `harny-feedback.yml`, or changing harny itself.

## Constraints
- ADR 0004 is binding: Python `>=3.13` and CI on 3.13, `uv` with a committed `uv.lock`, `ruff` for lint and format, `mypy` strict only in `domain`, `pytest` for tests. Apart from those three development tools and the two items approved below, nothing new is added without explicit approval (`AGENTS.md`).
- Approved build-time dependency: the human approved `uv_build`, uv's own build backend, as the `pyproject.toml` build backend on 2026-10-07. It is used only at build time, and this approval covers it.
- Approved CI action: the human approved the official `astral-sh/setup-uv` action on 2026-10-07. It must be pinned to an explicit version so the existing Dependabot `github-actions` updates track it.
- Layer boundaries from `AGENTS.md` and `docs/architecture.md`: `domain` imports nothing from the other layers or from any third-party package; the CLI lives in `interfaces`; nothing in this feature depends on SERCOP, PostgreSQL or storage.
- The package version has a single source of truth, `[project] version` in `pyproject.toml`; the CLI reads it from the installed package metadata and never hard-codes it.
- The CLI uses only the Python standard library, so no CLI framework is introduced before D-09.
- CI installs dependencies from the lockfile and fails if it is out of date (the ADR 0004 drift risk), never re-resolving them.
- The harny-generated block of `harny-feedback.yml` is not hand-edited. The python profile in harny has no CI install step on purpose (harny reservation R6). The header of that file says everything outside the markers is rewritten by `harny init`, so the new setup step can be lost on a future `harny init` or `update`, the same way the `actions/checkout@v7` line was on Day 4. The comment and the note from AC13 are how it gets restored.
- No secrets, credentials or raw procurement data in code, tests, fixtures or logs.
- This is the first feature, so there is no `specs/current/` knowledge base yet and the `harny-sync` lookup returned an empty brief. Nothing here contradicts a recorded current-truth statement.

## Open questions
- None

## Revision history
- Revision 1 (2026-10-05): First draft.
- Revision 2 (2026-10-07): Recorded the human's answers to the six open questions. Approved `uv_build` as the build backend and `astral-sh/setup-uv`, pinned to a version, for CI, both added to Constraints. Confirmed the command name `ec-procurement-quality` and version `0.1.0`. Moved the no-argument CLI behavior to Out. Added the comment next to the CI setup step, the restore note in `docs/repository-settings.md` and the `README.md` note on the local-hook limitation to In. Moved changing the hooks and installing uv with `pip` to Out. Added AC13 for the documentation. Open questions are now None.
