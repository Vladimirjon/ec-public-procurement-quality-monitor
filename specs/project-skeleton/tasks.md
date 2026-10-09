# Tasks: Project skeleton (F0)

## Status
Awaiting audit round 2

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

O11 and O12 were added on 2026-10-08 with intent Revision 3 (audit round 1, F1 and F2). They are listed after O8 because they cover work done in commit `f13ac5d`; the IDs were appended so that O9 and O10 keep the numbers the audit cites.

- [x] **O1** (AC1, AC2, AC3, AC7, AC8): Toolchain bootstrap, done by the executor before the red phase.
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
- [x] **O2** (AC6): The four layer packages `domain`, `application`, `infrastructure` and `interfaces` exist under `src/ec_procurement_quality/`, can be imported, and contain only what makes them packages. `domain` imports nothing outside the standard library and itself.
  - Tests: `tests/unit/test_layers.py` (tier: unit, pytest, setup `uv sync --locked`; selected by `-k layer`).
    - `test_layer_package_is_importable[domain|application|infrastructure|interfaces]` (AC6): `importlib.import_module("ec_procurement_quality.<layer>")` succeeds and the result is a regular package, i.e. it has an `__init__.py` (`__file__` is not `None`), not a bare directory that only imports as a namespace package.
    - `test_layer_domain_imports_only_stdlib_and_itself` (AC6): `domain` is a regular package, and every import in every `.py` file under it (found with `ast`) is either in `sys.stdlib_module_names` or inside `ec_procurement_quality.domain`; relative imports may not climb out of `domain`. It passes vacuously on the empty package and guards later domain code.
  - Red: run on 2026-10-07 from the repo root.
    - `uv run pytest tests/unit/test_layers.py -q` -> exit 1, `5 failed`. The four importability tests fail with `AssertionError: <layer> needs an __init__.py` (`assert None is not None`, module is `<module 'ec_procurement_quality.<layer>' (namespace) ...>`), and the domain test fails the same way for `domain`.
    - Reason this is the right one and not `ModuleNotFoundError`: the untracked, empty local folders `src/ec_procurement_quality/{domain,application,infrastructure,interfaces}/` already exist in this working tree, so Python imports them as namespace packages. In a clean clone they do not exist and the failure would be `ModuleNotFoundError`. The `__file__` check makes the test red in both situations and turns green only when the executor creates the `__init__.py` files.
    - `uv run pytest tests/unit -q` (whole directory) is interrupted at collection, exit 2, because of `tests/unit/test_cli.py` (see O3), so the layer tests only report when run on their own file or with `--ignore=tests/unit/test_cli.py` (`5 failed`).
  - Green: `uv run pytest tests/unit -q -k layer` passes, and `uv run python -c "import ec_procurement_quality.domain, ec_procurement_quality.application, ec_procurement_quality.infrastructure, ec_procurement_quality.interfaces"` exits 0 with no output.
  - Evidence (2026-10-08, repo root): created `__init__.py` (empty) in `domain`, `application`, `infrastructure` and `interfaces`. `uv run pytest tests/unit/test_layers.py -q -k layer` -> exit 0, `5 passed`. `uv run python -c "import ec_procurement_quality.domain, ..."` -> exit 0, no output. (The Green line `uv run pytest tests/unit -q -k layer` could only run after O3, because `test_cli.py` failed collection before; after O3 it gives exit 0, `5 passed, 2 deselected`.)
- [x] **O3** (AC4, AC5, AC9): The CLI `ec-procurement-quality` exists.
  - What it delivers:
    - The console script `ec-procurement-quality` in `[project.scripts]` targets `ec_procurement_quality.interfaces.cli:main`. `main` accepts an optional argument list.
    - `--version` prints exactly `ec-procurement-quality 0.1.0` and a newline to stdout and exits 0. The version is read from the installed distribution metadata and never hard-coded. `prog` is set explicitly.
    - An unknown option exits 2, prints nothing to stdout, and writes a usage error naming the option to stderr.
    - Only the standard library is used.
  - Tests: `tests/unit/test_cli.py` (tier: unit, pytest, setup `uv sync --locked`; in-process calls of `main` with `capsys`, no subprocess).
    - `test_version_prints_program_name_and_pyproject_version` (AC4, AC9; `-k version`): `main(["--version"])` raises `SystemExit` with code 0; stdout equals `ec-procurement-quality ` + `[project] version` read from `pyproject.toml` with `tomllib` + newline; stderr is empty.
    - `test_bogus_option_is_a_usage_error` (AC5; `-k bogus`): `main(["--bogus"])` raises `SystemExit` with code 2; stdout is empty; stderr contains `unrecognized arguments: --bogus`.
  - Red: run on 2026-10-07 from the repo root.
    - `uv run pytest tests/unit -q` -> exit 2, `1 error in 0.18s`, collection of `tests/unit/test_cli.py` fails: `ImportError: cannot import name 'main' from 'ec_procurement_quality.interfaces.cli' (unknown location)`.
    - Reason this is the right one and not `ModuleNotFoundError`: the untracked empty folder `src/ec_procurement_quality/interfaces/cli/` exists locally, so `ec_procurement_quality.interfaces.cli` resolves as an empty namespace package that has no `main`. In a clean clone the failure would be `ModuleNotFoundError: No module named 'ec_procurement_quality.interfaces'`. Either way the cause is that the CLI module does not exist yet. Note for the executor: create `interfaces/cli.py` (the target is `ec_procurement_quality.interfaces.cli:main`); a regular module file takes precedence over the empty `cli/` namespace folder.
    - `uv run mypy .` -> exit 1: `tests\unit\test_cli.py:12: error: Module "ec_procurement_quality.interfaces.cli" has no attribute "main"  [attr-defined]` (1 error, expected until O3). `uv run ruff check .` and `uv run ruff format --check .` -> exit 0. mypy resolves `ec_procurement_quality` from the tests without `mypy_path`.
  - Green: all of the following must hold.
    - `uv run pytest tests/unit -q` passes, with at least 1 test passed.
    - `uv run ec-procurement-quality --version` prints `ec-procurement-quality 0.1.0` and exits 0.
    - `uv run ec-procurement-quality --bogus` exits 2.
    - `uv sync --locked` still exits 0 after the `[project.scripts]` change.
  - Evidence (2026-10-08): added `src/ec_procurement_quality/interfaces/cli.py` (argparse, `prog="ec-procurement-quality"`, `version` action reading `importlib.metadata.version`) and `[project.scripts] ec-procurement-quality = "ec_procurement_quality.interfaces.cli:main"`. `uv run pytest tests/unit -q` -> exit 0, `7 passed`. `uv run ec-procurement-quality --version` -> `ec-procurement-quality 0.1.0`, exit 0. `uv run ec-procurement-quality --bogus` -> usage plus `error: unrecognized arguments: --bogus` on stderr, exit 2. `uv sync --locked` -> exit 0 ("Checked 14 packages"). `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy .` -> exit 0.
- [x] **O4** (AC10, AC11, AC13): The `feedback` CI job gets three new steps, each with a comment saying it is hand-maintained and must be restored after `harny init` or `update`. They go in `.github/workflows/harny-feedback.yml` after `Checkout` and before the harny-generated block.
  1. `astral-sh/setup-uv`, pinned to a commit SHA with a `# v10.1.0` comment or to a full version tag, with `python-version: "3.13"`. The executor re-checks the latest release before pinning.
  2. `uv sync --locked`.
  3. Add `$GITHUB_WORKSPACE/.venv/bin` to `$GITHUB_PATH`.
  - The generated block, the job id `feedback` and the `Secret scan (gitleaks)` step stay unchanged.
  - Tests: none (CI configuration; checked by O7 and O8).
  - Red: not applicable.
  - Green, locally: the runner command from Baseline prints `harny-feedback: 2 of 2 command(s) ran, 0 skipped.` and exits 0, and `git diff 699cae5 -- .github/workflows/harny-feedback.yml` shows no line changed between the harny markers.
  - Evidence (2026-10-08): the latest setup-uv release is `v10.2.0` (published 2026-09-21, not a prerelease; `gh api repos/astral-sh/setup-uv/releases/latest`), newer than the `v10.1.0` named in the plan. Pinned `astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7 # v10.2.0`. The SHA comes from `gh api repos/astral-sh/setup-uv/git/ref/tags/v10.2.0` (type `commit`, so not an annotated tag) and matches `gh api repos/astral-sh/setup-uv/commits/v10.2.0`. `action.yml` at that tag has the `python-version` input. Three steps added after `Checkout`, before the harny block, with a hand-maintained comment block and "(hand-maintained, restore after harny init or update)" in each step name. `uv run node .sdd/feedback/run-feedback.mjs run --whole-project --commands "$(cat .sdd/git-hooks/commands.json)"` -> `harny-feedback: 2 of 2 command(s) ran, 0 skipped.`, exit 0. `git diff main -- .github/workflows/harny-feedback.yml` shows one hunk (13 added lines) before the `harny:begin` marker and nothing between the markers. The workflow YAML was not parsed by a YAML tool (none installed); not run on GitHub yet (O8).
- [x] **O5** Migration (AC12): The existing consumers keep working with no change to their files: the doctor, the Stop, SubagentStop and pre-commit hooks, the gitleaks step, the local `.venv` and branch protection's `feedback` check.
  - `node .sdd/doctor/run-doctor.mjs` reports `0 warned, 0 failed`. In particular there is no `repo-readiness:component-doc:src/ec_procurement_quality` warning.
  - `uv run node .sdd/doctor/run-doctor.mjs` reports `OK pytest`.
  - `.venv\Scripts\python.exe --version` (PowerShell) prints Python 3.13.x. Record whether `uv sync` recreated `.venv`.
  - `uv run ruff check $(git diff --name-only 699cae5 -- '*.py')` and `uv run mypy $(git diff --name-only 699cae5 -- '*.py')` exit 0. This is the per-file form the hooks use. If mypy cannot resolve `ec_procurement_quality` from a test file, add `mypy_path = "src"` and record why.
  - `git diff --check` is clean.
  - No file under `.sdd/` and no `.claude/settings.json` change.
  - Evidence (2026-10-08): `node .sdd/doctor/run-doctor.mjs` -> `29 ok, 2 skipped, 0 warned, 0 failed`, exit 0, no `component-doc` warning. `uv run node .sdd/doctor/run-doctor.mjs` -> `OK pytest`, `30 ok, 1 skipped, 0 warned, 0 failed` (the remaining skip is `knowledge-base`). `.venv/Scripts/python.exe --version` -> `Python 3.13.9`; `.venv` was reused, not recreated. Per-file hook form: the files are still untracked, so `git diff --name-only main -- '*.py'` is empty; the same form on the 8 untracked `.py` files (from `git status --short --untracked-files=all`) -> `uv run ruff check <files>` exit 0 and `uv run mypy <files>` exit 0 ("no issues found in 8 source files"), including the test files, so `mypy_path` was not needed. To re-run with the real diff form after the commit (O7/AC12). `git diff --check` -> exit 0. `git status --short .sdd .claude` -> empty. `src/ec_procurement_quality/` holds one file of its own.
- [x] **O6** Docs (AC13):
  - `README.md` lists the real install, CLI, lint, format, type and test commands and stops calling the CLI and modules planned. It also states that the Stop and pre-commit hooks run `ruff` and `mypy` only when `.venv` is on `PATH`.
  - `AGENTS.md` § Current commands drops "There is no application command, test suite, or dependency configuration yet" and lists the same commands.
  - `docs/repository-settings.md` gets a note that names the hand-maintained CI steps (the `astral-sh/setup-uv` step and the two after it) and explains how to restore them after `harny init` or `update`. Its existing line about the Python Dependabot ecosystem is kept.
  - Green:
    - `git grep -n "setup-uv" -- .github/workflows/harny-feedback.yml docs/repository-settings.md` shows the step with its adjacent comment and the note.
    - `git grep -n -i "PATH" -- README.md` shows the hook limitation.
  - Evidence (2026-10-08): `README.md` now lists the real install, CLI, lint, format, type and test commands, drops the "planned" wording for the package and CLI, and states the Stop/pre-commit `.venv`-on-`PATH` limitation. `AGENTS.md` § Current commands drops the "no command or test suite" sentence and lists the same commands. `docs/repository-settings.md` has a new subsection "Hand-maintained steps in `harny-feedback.yml`" with the three steps and restore instructions; the `pip` Dependabot line is kept. `git grep -n "setup-uv" -- .github/workflows/harny-feedback.yml docs/repository-settings.md` -> workflow line 77 (comment block on lines 71-75) and settings lines 32 and 49. `git grep -n -i "PATH" -- README.md` -> lines 82 and 86 (hook limitation). `git diff --check` -> exit 0.
- [x] **O7** Local manual verification (AC1, AC2, AC3, AC7, AC8, AC11, AC12). The executor runs these after O1 to O6 are committed on `feat/project-skeleton`. The auditor re-runs them or records them as reused or unavailable. Probe files and throwaway clones are never committed.
  - AC1: run `tmp=$(mktemp -d) && git clone . "$tmp" && cd "$tmp" && uv sync --locked`. Expect exit 0, and `git status --short` in the clone shows no change.
  - AC2: in a throwaway clone, change a version bound in `[dependency-groups] dev` without running `uv lock`, then run `uv sync --locked; echo $?`. Expect a non-zero exit and an error saying the lockfile needs updating. Record the exact message.
  - AC3: in a throwaway clone, run `uv sync --python 3.12; echo $?`. Expect a non-zero exit and an error naming `>=3.13`. This may download Python 3.12. If there is no network, record it as unavailable, never as a pass.
  - AC7: `uv run ruff check .` and `uv run ruff format --check .` both exit 0.
  - AC8: with `src/ec_procurement_quality/domain/probe.py` containing `def f(x): return x`, `uv run mypy .` exits non-zero with "missing a type annotation". With the same file moved to `src/ec_procurement_quality/application/`, it exits 0. Delete the probe afterwards; `uv run mypy .` then exits 0 and `git status --short` shows no probe file.
  - AC11: add an unused `import os` to a file under `src/`, run the runner command from Baseline, and expect `finding from \`ruff\`` and exit 2. Then revert the file and confirm `git status --short` is clean.
  - AC12: the O5 commands give the same results on the final commit.
  - Evidence (2026-10-08, committed state `cbaefec`, uv 0.12.23, Python 3.13.9; throwaway clones `a1` and `a3` under the session scratchpad, made with `git -c core.longpaths=true clone` because the default clone failed with "Filename too long" on the long scratchpad path):
    - AC1: `git clone` + `uv sync --locked` in the clone -> exit 0 (created `.venv`, installed 14 packages including `ec-procurement-quality==0.1.0`); `git status --short` in the clone -> empty. Pass.
    - AC2: in the clone, `pyproject.toml` dev bound `"pytest>=9.1.1"` changed to `"pytest>=9.0.0"` with no `uv lock`; `uv sync --locked; echo $?` -> exit 1. Exact output: `Resolved 14 packages in 386ms`, then `error: The lockfile at `uv.lock` needs to be updated, but `--locked` was provided.`, blank line, `hint: To update the lockfile, run `uv lock`.` Pass.
    - AC3: `uv sync --python 3.12` in a clone; network was available and uv downloaded `cpython-3.12.15-windows-x86_64-none` (21.0MiB). Run from PowerShell -> exit 2. Exact output: `Using CPython 3.12.15 interpreter at: C:\Users\johan\AppData\Roaming\uv\python\cpython-3.12.15-windows-x86_64-none\python.exe`, then `error: The requested interpreter resolved to Python 3.12.15, which is incompatible with the project's Python requirement: `>=3.13` (from `project.requires-python`)`. Pass. Unexpected: the first runs from Git Bash (the Bash tool) failed after the download with `error: Missing expected target directory for Python minor version link at `C:\Users\johan\AppData\Roaming\uv\python\cpython-3.12.15-windows-x86_64-none`` (exit 2), also after `uv python install 3.12 --reinstall`. That is a Git Bash symlink quirk of uv's minor-version link, not a project problem, and the same command from PowerShell gives the expected error. Side effect outside the repo: uv's managed Python 3.12.15 is now installed under `%APPDATA%\uv\python`.
    - AC7: `uv run ruff check .` -> exit 0 ("All checks passed!"); `uv run ruff format --check .` -> exit 0 ("46 files already formatted"). Pass.
    - AC8: probe `src/ec_procurement_quality/domain/probe.py` with `def f(x): return x` -> `uv run mypy .` exit 1: `src\ec_procurement_quality\domain\probe.py:1: error: Function is missing a type annotation  [no-untyped-def]`, "Found 1 error in 1 file (checked 9 source files)". Same file moved to `application/` -> exit 0 ("Success: no issues found in 9 source files"). Probe deleted; `uv run mypy .` -> exit 0 ("no issues found in 8 source files"); `git status --short` empty. Pass.
    - AC11: appended `import os` to `src/ec_procurement_quality/interfaces/cli.py`; the Baseline runner command printed `finding from `ruff` (exit 1):` followed by ``F401 [*] `os` imported but unused`` at `src\ec_procurement_quality\interfaces\cli.py:29:8`, then `harny-feedback: 2 of 2 command(s) ran, 0 skipped.`, exit 2. Reverted with `git checkout -- <file>`; `git status --short` empty. Pass.
    - AC12: `node .sdd/doctor/run-doctor.mjs` -> `29 ok, 2 skipped, 0 warned, 0 failed`; `uv run node .sdd/doctor/run-doctor.mjs` -> `OK pytest`, `30 ok, 1 skipped, 0 warned, 0 failed`. `.venv/Scripts/python.exe --version` -> `Python 3.13.9`. With the real diff form, `git diff --name-only main -- '*.py'` lists the 8 `.py` files; `uv run ruff check <those>` -> exit 0 and `uv run mypy <those>` -> exit 0 ("no issues found in 8 source files"). `git diff --check` -> exit 0. `git diff --name-only main -- .sdd .claude` -> empty. `src/ec_procurement_quality/` holds one file of its own (`__init__.py`). Same results as O5. Pass.
- [x] **O8** CI verification (AC1, AC10, AC11, AC12). The human pushes `feat/project-skeleton` and opens the F0 pull request. The human, or the conductor reading the run log with `gh`, records the evidence below.
  - AC10: the `harny feedback (Python)` step log ends with `harny-feedback: 2 of 2 command(s) ran, 0 skipped.` and the `feedback` check is green.
  - AC1: the `uv sync --locked` step is green on the runner.
  - AC12: the `Secret scan (gitleaks)` step ran and passed.
  - AC11 (optional, human): the same unused-import change on a throwaway branch or draft pull request turns the `feedback` check red. Close it without merging. If skipped, record that only local evidence from O7 exists.
  - Evidence (2026-10-09, PR #11 at `f13ac5d`, read with `gh run view --log`): `harny feedback` run `37884423074` is green. The `uv sync --locked` step resolved 16 packages and installed 15 (AC1). The `harny feedback (Python)` step ends with `harny-feedback: 2 of 2 command(s) ran, 0 skipped.` (AC10). The `Secret scan (gitleaks)` step ran 8.30.1 and printed `4 commits scanned` and `no leaks found` (AC12). `Tests` run `37884423088` is green: `7 passed`, coverage `TOTAL 10 0 100%` (see O11). The `setup-uv` v10.2.0 pin worked; it has no uv version input, so it fell back to the latest uv and both runs installed uv 0.12.24 (log: `Successfully installed uv version 0.12.24`), not the local 0.12.23. `uv sync --locked` still passed, so the newer-uv drift risk did not occur. (Corrected on 2026-10-08 after audit F5; this line first said "worked with uv 0.12.23".) AC11 optional CI probe (unused import on a throwaway branch) was skipped: only the local evidence from O7 exists.
- [x] **O11** (AC14, AC15): `pytest-cov` dev dependency and the `Tests` workflow. Done in commit `f13ac5d` before the specs named it; recorded here by intent Revision 3.
  - What it delivers: `pytest-cov>=7.1.0` in `[dependency-groups] dev` (locked 7.1.0, with `coverage` 7.16.2), and `.github/workflows/tests.yml` written by hand by the human: workflow `Tests`, job `tests`, on `pull_request` and `push` to `main`, `permissions: contents: read`, `setup-uv` at the same SHA as `harny-feedback.yml` (`c18668ad...` v10.2.0) with Python 3.13, `uv sync --locked`, `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing`. No `--cov-fail-under`.
  - Tests: none new (CI configuration; it runs the existing unit tests).
  - Red: not applicable.
  - Evidence (PR #11 at `f13ac5d`, read with `gh run view 37884423088 --log`): `Tests` run `37884423088` green. `Install dependencies` ran `uv sync --locked` with CPython 3.13.16 (`Resolved 16 packages`, `Installed 15 packages`). `Run tests` printed the coverage table, `TOTAL 10 0 100%` and `7 passed`. Required checks on `main` are still `["feedback"]` (`gh api`).
- [ ] **O12** Local verification (AC15, AC16). The auditor runs these in round 2 (or the executor before it). Changes are reverted, never committed.
  - AC15: `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing` exits 0 with `7 passed` and a `TOTAL` row; `pytest-cov` appears only in the dev group and `uv.lock`; `[project] dependencies` is `[]`.
  - AC16: add `assert False` to one test in `tests/unit/`, run the AC15 command, expect a non-zero exit and `1 failed`; revert and confirm `git status --short` is clean. Confirm no `cov-fail-under` in `tests.yml` or `pyproject.toml`. The CI-side probe on a throwaway PR is optional; if skipped, record that only local evidence exists.
- [x] **O9** Broader suite vs baseline (AC9, AC12):
  - `uv run pytest` exits 0 with all tests passed. The baseline had no suite.
  - `uv run ruff check .`, `uv run ruff format --check .` and `uv run mypy .` exit 0.
  - `node .sdd/doctor/run-doctor.mjs` reports `0 warned, 0 failed`, an improvement on the baseline's single `spec-state` failure. No new failure appears.
  - Evidence: run by the auditor in round 1 at `f374dfd` (`audit.md` § O9 results): `uv run pytest` exit 0, `7 passed`; ruff check, ruff format check and mypy exit 0; doctor `29 ok, 2 skipped, 0 warned, 0 failed` (plain) and `30 ok, 1 skipped, 0 warned, 0 failed` (via `uv run`); `git diff --check` exit 0. The spec revision changes no code, so this still holds; round 2 re-runs it.
- [ ] **O10** Independent audit (AC1 to AC16): the auditor writes `specs/project-skeleton/audit.md` with a verdict. The human accepts or rejects it at the post-audit gate.
  - Round 1 (2026-10-08): REJECTED. All 13 ACs passed; blocked by F1 (CRITICAL) and F2 (HIGH), the scope gap for `tests.yml` and `pytest-cov`. F3 to F5 LOW.
  - Round 2: not started. The human approved intent Revision 3 and execution-plan Revision 2 on 2026-10-08.

## Working state
- Updated: 2026-10-08
- Outcome: O1 to O9 and O11 done. O12 and O10 (round 2) not started.
- Phase: audit round 1 rejected (F1, F2). The architect revised the specs to match what exists: intent Revision 3 (adds AC14 to AC16) and execution-plan Revision 2, both approved by the human on 2026-10-08. No code changed.
- In progress: nothing
- Deviation from Baseline: the branch was created from `f07c304`, not `699cae5` (see O1 notes). Use `main`/`f07c304` for the `git diff` checks.
- Deviation from plan: `astral-sh/setup-uv` is pinned to `v10.2.0` (`c18668ad3cf93ea998bef934396af7bb5c839dc7`) because the re-check found it is the latest release, not `v10.1.0`. The step names also carry "(hand-maintained, restore after harny init or update)" next to the comment block.
- Full-suite state (2026-10-08): `uv run pytest` -> exit 0, `7 passed`; `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy .` -> exit 0; doctor `29 ok, 2 skipped, 0 warned, 0 failed` (plain) and `30 ok, 1 skipped, 0 warned, 0 failed` (via `uv run`).
- Files changed in O2 to O6: `src/ec_procurement_quality/{domain,application,infrastructure,interfaces}/__init__.py` (new, empty), `src/ec_procurement_quality/interfaces/cli.py` (new), `pyproject.toml` (`[project.scripts]`), `.github/workflows/harny-feedback.yml`, `README.md`, `AGENTS.md`, `docs/repository-settings.md`. The red tests `tests/unit/test_layers.py` and `tests/unit/test_cli.py` were not edited.
- O1 evidence (all run from the repo root, 2026-10-07, uv 0.12.23, Python 3.13.9):
  - `uv add --dev ruff mypy pytest` -> exit 0. Locked: mypy 2.4.0, pytest 9.1.1, ruff 0.16.10 (plus transitive packages; 14 resolved in total). Because pytest is 9.1.1, the native `[tool.pytest]` table is used.
  - `uv sync --locked` -> exit 0. `git status --short -- uv.lock pyproject.toml` -> `?? pyproject.toml`, `?? uv.lock` (new files only). A second `uv sync --locked` -> exit 0, "Checked 14 packages", no change.
  - `uv run ruff check .` -> exit 0 ("All checks passed!"). `uv run ruff format --check .` -> exit 0 ("39 files already formatted"). `uv run mypy .` -> exit 0 ("no issues found in 1 source file").
  - `uv run pytest` -> exit 5, "collected 0 items ... no tests ran" (expected before the red phase).
  - `git diff --check` -> exit 0. `node .sdd/doctor/run-doctor.mjs` -> `29 ok, 2 skipped, 0 warned, 0 failed` (the `spec-state` failure from the baseline is gone; the `pytest` skip remains because the doctor was run without `uv run`).
  - Local runner `uv run node .sdd/feedback/run-feedback.mjs run --whole-project ...` -> `harny-feedback: 2 of 2 command(s) ran, 0 skipped.`, exit 0.
  - Per-file hook form on `src/ec_procurement_quality/__init__.py`: `uv run ruff check` and `uv run mypy` -> exit 0.
  - `src/ec_procurement_quality/` held one file of its own (`__init__.py`, empty). `pyproject.toml` has no `authors`, and `uv.lock` has no local path or email. `.venv` was reused (still Python 3.13.9, no "Creating virtual environment" message); no `.python-version` was created.
  - `[tool.ruff]` and the bare `[tool.mypy]` table contain only comments (defaults). The mypy override has no `strict = true`.
- Standards and feedback checks: `AGENTS.md` has no coding-standards section, so `harny-standards` found nothing binding beyond its boundaries, change restrictions and "run relevant verification" (done above). `src/feedback.ts` is not in this repo; the mapped commands were taken from `.sdd/git-hooks/commands.json` (ruff check, mypy), and both pass. Re-applied for O2 to O6 on 2026-10-08 with the same result.
- Last command: `gh run view 37884423088 --log` and `gh run view 37884423074 --log` (both installed uv 0.12.24; `Tests` printed `TOTAL 10 0 100%` and `7 passed`)
- Next step:
  1. Done (2026-10-08): the human approved intent Revision 3 and execution-plan Revision 2.
  2. Done (2026-10-08): spec changes and `audit.md` committed and pushed, so PR #11 runs on the final head (F5).
  3. The auditor does round 2: O12, a re-check of O9, and the verdict for O10.
- Earlier note, superseded by intent Revision 3: `pytest-cov` and `tests.yml` (commit `f13ac5d`) went beyond the F0 intent § Out on purpose; the human added them on Day 6 to avoid deferring the CI test job.

## Finding responses
| Finding | Response | Evidence |
|---|---|---|
| F1 (CRITICAL) | Option (a), chosen by the human on 2026-10-08: specs revised to record `tests.yml` and `pytest-cov`. Closes only after the human re-approves and round 2 confirms. | intent Revision 3 (§ Scope, § Constraints, AC14 to AC16); execution-plan Revision 2 (Allowed dependencies, Tests workflow file, Scope) |
| F2 (HIGH) | § Validation now names the `pytest-cov` setup (AC9 row) and has rows for the `tests.yml` CI check (AC14 to AC16). | execution-plan Revision 2 § Validation |
| F3 (LOW) | No change. The AC11 Example allows the local runner, and the auditor marked it acceptable. The human may still run the throwaway-PR probe. | O7, O8 |
| F4 (LOW) | No change. The hook limitation is documented (AC13) and changing hooks is Out. | `README.md`, intent § Out |
| F5 (LOW) | Fixed here: Status, Checkpoint, and the uv version in O8 (0.12.24). O9 ticked with the round 1 evidence. Pushing to PR #11 is the human's step (Next step 2). | this file; logs of runs `37884423074` and `37884423088` |

## Checkpoint
O1 to O9 and O11 are done on branch `feat/project-skeleton` (created from `f07c304`). Waiting for the human to re-approve intent Revision 3 and execution-plan Revision 2, then audit round 2 (O12, O10).
