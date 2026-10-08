# Execution Plan: Project skeleton (F0)

## Guidance consulted
- `specs/project-skeleton/intent.md` Revision 2, approved by Vladimirjon on 2026-10-07. It is the only source of acceptance criteria (AC1 to AC13).
- `AGENTS.md` (layer boundaries, approval rule for dependencies, current commands), `README.md`, `docs/architecture.md`, `docs/ai-assisted-development.md`, `docs/repository-settings.md`, and ADR 0001 to ADR 0004, especially `docs/adr/0004-python-toolchain.md`.
- `docs/learning/plan.md` section 4 (F0 row), section 6 (CI evolution) and the Day 5 and Day 6 entries.
- `.github/workflows/harny-feedback.yml`: its header comment, the `# <!-- harny:begin ... -->` and `# <!-- harny:end ... -->` markers, and the generated step `harny feedback (Python)`.
- `.sdd/feedback/run-feedback.mjs` (`run --whole-project` passes `.` to each command, skips any command whose binary is not on `PATH`, and prints `harny-feedback: N of M command(s) ran, K skipped.`), `.sdd/shared/probes.mjs`, `.sdd/git-hooks/commands.json`, `.sdd/git-hooks/run-git-hook.mjs` and the Stop and SubagentStop hooks in `.claude/settings.json`.
- `.sdd/doctor/checks.json`, `.sdd/doctor/run-doctor.mjs` and `.sdd/shared/components.mjs`. These contain the component-doc discovery rule that leads to a binding constraint below.
- harny source at commit `466c636`, `src/feedback.ts`: the python profile has no `ciInstall` on purpose (harny reservation R6).
- `harny-sync` lookup: `specs/current/` does not exist, so the brief was empty.
- External facts checked on 2026-10-07:
  - **uv build backend docs:** the recommended requirement is `uv_build>=0.12.23,<0.13`. The default module root is `src/`. The module name is derived from the project name, so `ec-procurement-quality` becomes `ec_procurement_quality`. When its bundled backend version is compatible, uv uses it.
  - **uv sync docs:** with `--locked`, an out-of-date lockfile is an error. The `dev` group is synced by default. `uv run` locks and syncs before running.
  - **setup-uv README:** the latest release is `v10.1.0`. Examples pin a commit SHA with a `# v10.1.0` comment. The `python-version` input sets `UV_PYTHON`. The action does not install project dependencies.
  - **mypy docs (stable, 2.4.0):** recursive discovery never enters `site-packages`, `node_modules`, `__pycache__` or directories whose name starts with a period. `foo.bar.*` matches `foo.bar` and its submodules. The flags enabled by `--strict` are documented. mypy issues #11401, #16387 and #18836 report that `strict` does not take effect reliably inside per-module sections.
  - **ruff docs:** `.venv` is excluded by default and `.gitignore` is respected. The target version is inferred from `requires-python`. `ruff format --check` exits non-zero when a file would be reformatted.
  - **pytest docs (stable, 9.x):** a native `[tool.pytest]` table is supported since 9.0. `[tool.pytest.ini_options]` works since 6.0.
  - **argparse on the local Python 3.13.9:** with `prog="ec-procurement-quality"`, the `version` action prints `ec-procurement-quality 0.1.0` plus a newline to stdout, nothing to stderr, and exits with code 0. `--bogus` prints nothing to stdout, prints a usage line and `ec-procurement-quality: error: unrecognized arguments: --bogus` to stderr, and exits with code 2.
  - **uv 0.12.23 locally:** `uv init --package --name ec-procurement-quality`, run only in a scratch folder outside the repo, generated `requires = ["uv_build>=0.12.23,<0.13.0"]` and `src/ec_procurement_quality/__init__.py`. It also filled `[project] authors` with the email from the local git config.

## Ownership
- `pyproject.toml` and `uv.lock` (new, repo root): project metadata, the build backend, the development dependency group and the tool configuration.
- `src/ec_procurement_quality/` (new): the package root and the four layer packages `domain`, `application`, `infrastructure` and `interfaces`. The CLI lives in `interfaces`.
- `tests/unit/` (new): unit tests for AC4, AC5 and AC6.
- `.github/workflows/harny-feedback.yml`: new steps only, outside the generated block.
- Documentation: `README.md`, the `AGENTS.md` § Current commands section, and `docs/repository-settings.md`.
- Affected `specs/current` capabilities: none exist yet. This feature introduces two new capabilities that `harny-sync` archive creates: `cli` (the `ec-procurement-quality` command and its `--version` contract) and `project-toolchain` (install, lint, type check, test and the `feedback` CI gate).

## Binding constraints
- **Python version.** `requires-python = ">=3.13"`, and CI runs on Python 3.13 (source: ADR 0004; intent AC3, AC10).
- **Reproducible installs.** `uv` manages the environment and `uv.lock` is committed. Every install in CI uses `uv sync --locked`, which errors when the lockfile is out of date instead of re-resolving (source: ADR 0004; intent AC1, AC2; uv sync docs).
- **Allowed dependencies.**
  - There are no runtime dependencies (`[project] dependencies` stays empty).
  - The only development dependencies are `ruff`, `mypy` and `pytest`.
  - The build backend is `uv_build`, with an upper bound below the next minor version of uv.
  - Anything else needs explicit approval first (source: `AGENTS.md`; intent § Constraints; ADR 0004).
- **Approved versions.** Versions of `ruff`, `mypy` and `pytest` are not fixed in this plan. The executor resolves them at implementation time, and `uv.lock` records them (source: ADR 0004). No version is invented here.
- **Console script contract.** The command is `ec-procurement-quality` and the distribution version is `0.1.0`. The console script target is `ec_procurement_quality.interfaces.cli:main` (source: intent AC4 and § Scope; `AGENTS.md` puts entry points in `interfaces`).
  - `main` accepts an optional list of argument strings. When it gets none, it reads the process arguments.
  - `--version` and usage errors end through `SystemExit`, with code 0 and code 2 respectively.
  - This contract is pinned because `pyproject.toml` and the unit tests both call it.
- **Version output.** `--version` prints exactly `ec-procurement-quality`, a space, the version and a newline to stdout. The version comes from the installed distribution metadata and is never a literal in code. The program name is set explicitly so the output does not depend on how the process was started (source: intent AC4 and § Constraints; local argparse check).
- **Standard library only.** The CLI uses only the standard library, so no CLI framework is added before D-09 (source: intent § Constraints; `docs/learning/plan.md` D-09).
- **Layer boundaries.**
  - `domain`, `application` and `infrastructure` contain only what makes them importable packages.
  - `domain` imports nothing outside the standard library and itself.
  - Nothing references SERCOP, PostgreSQL or storage (source: `AGENTS.md`; `docs/architecture.md`; intent AC6).
- **Strict mypy in `domain` only.**
  - Strictness for `ec_procurement_quality.domain.*` is set with explicit per-module flags in a mypy override. It covers at least `disallow_untyped_defs`, `disallow_incomplete_defs`, `disallow_untyped_calls`, `disallow_untyped_decorators`, `disallow_any_generics`, `disallow_subclassing_any`, `check_untyped_defs`, `warn_return_any` and `strict_equality`.
  - Global flags that `--strict` enables, such as `warn_unused_ignores` and `warn_redundant_casts`, may be set globally if every layer passes.
  - Do not use `strict = true` inside an override, because mypy does not apply it reliably there.
  - The other layers keep mypy's default, non-strict settings (source: ADR 0004; intent AC8; mypy docs and issues listed above).
- **mypy from the repo root.** `mypy .` run from the repo root must pass. This is what the harny runner executes in CI. The per-file form must also work, with the CLI module and a test file under `tests/unit/` passed as explicit paths. The Stop hook and the pre-commit hook use that form (source: `.sdd/feedback/run-feedback.mjs`; `.sdd/git-hooks/commands.json`; intent AC8, AC12).
- **Doctor component discovery.** `src/ec_procurement_quality/` must hold at most 2 files of its own, directly in that folder (for example `__init__.py` and optionally `py.typed`). Rule (c) in `.sdd/shared/components.mjs` treats a direct child of `src/` with 3 or more files as a component. The doctor would then warn about a missing `src/ec_procurement_quality/AGENTS.md`, which breaks the `0 warned` part of AC12 (source: `.sdd/shared/components.mjs`; intent AC12).
- **CI workflow file.**
  - The harny-generated block and everything between its markers stay byte-identical.
  - The job id `feedback` does not change, because branch protection requires it (`docs/repository-settings.md`).
  - The new steps go after `Checkout` and before the generated block, so `ruff` and `mypy` are on `PATH` when the runner starts.
  - The `Secret scan (gitleaks)` step stays as it is (source: workflow header; intent AC10, AC12, § Out).
- **setup-uv pinning.** `astral-sh/setup-uv` is pinned to an explicit release: a commit SHA with a version comment, or a full version tag. A major-only tag or `@main` is not allowed. This keeps the action visible to the existing Dependabot `github-actions` updates. `.github/dependabot.yml` does not change (source: intent § Constraints and § Out).
- **Restore instructions.**
  - The new CI steps carry a comment saying they are hand-maintained and must be restored after `harny init` or `update`.
  - `docs/repository-settings.md` names those steps and explains how to restore them.
  - `README.md` documents that the Stop and pre-commit hooks run `ruff` and `mypy` only when `.venv` is on `PATH`.
  - The hooks themselves are not changed (source: intent AC13 and § Out).
- **No sensitive data.** No secrets, credentials, personal contact data or raw procurement data go into any file. This includes the `authors` email that `uv init` fills in automatically (source: `AGENTS.md`).
- **Scope.** There is no `tests.yml`, no coverage, no new test tier, and no sub-packages inside the layers (source: intent § Out).

## Proposed approach
Revisable by the executor if it records why.
- **Decision: write `pyproject.toml` by hand instead of running `uv init` in the repo.**
  - Rationale: `uv init` fills `authors` from the git config, including an email address, puts `main` in the package `__init__.py` instead of `interfaces`, and adds a `.python-version` file that the intent does not list.
  - Rejected: running `uv init --package` in place and then cleaning up, because it is easy to leave the email behind.
- **Decision: put `ruff`, `mypy` and `pytest` in the PEP 735 `[dependency-groups] dev` group, added with `uv add --dev`, which also writes `uv.lock`.**
  - Rationale: uv syncs the `dev` group by default, so `uv sync --locked` and `uv run` find all three tools with no extra flags.
  - Rejected: `[project.optional-dependencies]`, because it would publish development tools as an installable extra of the package.
- **Decision: use the build system `requires = ["uv_build>=0.12.23,<0.13"]` with `build-backend = "uv_build"`.**
  - Rationale: these are the bounds uv 0.12.23 generates and the uv docs recommend. The default module root `src/` and the name mapping produce `src/ec_procurement_quality/` with no extra settings.
  - Rejected: no build system, because uv would then not install the package or its console script.
- **Decision: the CLI uses `argparse` with `prog="ec-procurement-quality"`, a `--version` option with the `version` action, and the version read through `importlib.metadata`.**
  - Rationale: the local check showed this gives the exact AC4 and AC5 output, streams and exit codes. It needs only the standard library.
  - Rejected: reading `pyproject.toml` at runtime, because the file is not shipped in an installed wheel.
  - Rejected: a `__version__` literal, because it would be a second source of truth.
- **Decision: keep the configuration of the three tools in `pyproject.toml`.**
  - ruff: default rules (they include the Pyflakes `F` rules, so an unused import is a finding) and default formatting. The target version is inferred from `requires-python`.
  - mypy: global defaults, plus one override for `ec_procurement_quality.domain.*` with the strict flags listed in Binding constraints.
  - pytest: `testpaths = ["tests"]`, in the native `[tool.pytest]` table if the locked pytest is 9.0 or newer, and in `[tool.pytest.ini_options]` otherwise.
  - Rationale: one file, one place to review.
  - Rejected: separate `ruff.toml`, `mypy.ini` and `pytest.ini` files, because they mean more files and nothing gains from them here.
  - Suggestion: extending ruff's rule set (for example import sorting) is allowed if AC7 stays green.
- **Decision: let `mypy .` discover the package by its `__init__.py` files. Add `mypy_path = "src"` only if the per-file run on test files cannot resolve `ec_procurement_quality` from the installed editable package.**
  - Rationale: mypy maps `src/ec_procurement_quality/...` to `ec_procurement_quality...` by crawling `__init__.py` files, and skips `.venv` because its name starts with a period.
  - Rejected: `explicit_package_bases`, because the package already has `__init__.py` files.
- **Decision: add three steps to the CI job, after `Checkout`, each with the restore comment.**
  1. `astral-sh/setup-uv` pinned to a commit SHA with a `# v10.1.0` comment, as its README shows, with `python-version: "3.13"`.
  2. `uv sync --locked`.
  3. `echo "$GITHUB_WORKSPACE/.venv/bin" >> "$GITHUB_PATH"`.
  - Rationale: the harny runner only checks for `ruff` and `mypy` on `PATH`. `$GITHUB_PATH` is the documented GitHub Actions way to add to `PATH` for later steps.
  - Rejected: setup-uv's `activate-environment` input, because its README does not say it adds the environment to `PATH`.
  - Rejected: `uv run` around the generated step, because that would mean editing the generated block.
  - Rejected: `pip install uv`, which the human ruled out.
- **Decision: leave the uv version used in CI at the action default (latest release).**
  - Rationale: Dependabot does not update a hard-coded uv version, and `--locked` fails loudly if a newer uv disagrees with `uv.lock`.
  - Rejected: pinning setup-uv's `version` input, because it would then need manual updates. The executor may switch to a pin if the first CI run shows drift.
- **Decision: the unit tests call `ec_procurement_quality.interfaces.cli.main` in-process with an argument list. They capture stdout and stderr with pytest's `capsys` and assert the `SystemExit` code.**
  - The AC4 test compares the output with the version read from `pyproject.toml` through the standard library `tomllib`. This proves the CLI follows the single source of truth.
  - Rationale: this stays in the unit tier with no subprocesses.
  - Rejected: running the console script in a subprocess, because that is end-to-end and the intent keeps `tests/unit` as the only tier. The console script itself is covered by the AC4 command check.

## Consumers and migration
- **`.github/workflows/harny-feedback.yml`.** The required check `feedback` keeps its job id. Its generated step starts finding `ruff` and `mypy` on `PATH`, so the summary line changes from `0 of 2` to `2 of 2`. The gitleaks step is unchanged.
- **Local hooks.** These are the Stop and SubagentStop hooks in `.claude/settings.json` and the pre-commit hook through `.sdd/git-hooks/commands.json`. They start running `ruff` and `mypy` on touched or staged `.py` files whenever `.venv` is on `PATH`. The configuration must therefore make the per-file form pass on clean files. Without `.venv` on `PATH` they keep skipping, which AC13 documents. No hook file changes.
- **`.sdd/doctor`.** The `pytest` readiness command goes from `SKIP` to `OK` when run through `uv run`. Component discovery now sees `src/ec_procurement_quality/`, so the file-count constraint above applies. No doctor file changes.
- **Local `.venv`.** It was created by `python -m venv` with Python 3.13.9 at an earlier folder path. `uv sync` reuses it or recreates it. `.venv\Scripts\python.exe` must still exist afterwards (AC12). The executor reports whether it was recreated.
- **Documentation.**
  - `AGENTS.md` § Current commands drops "There is no application command, test suite, or dependency configuration yet" and lists the real install, CLI, lint, format, type and test commands.
  - `README.md` stops saying the CLI and modules are only planned, lists the same commands, and adds the local-hook limitation.
  - `docs/repository-settings.md` adds the restore note. Its existing line about adding the `pip` Dependabot ecosystem stays, because Python Dependabot updates are out of scope.
  - `docs/architecture.md` still lists "Which Python compatibility range should be declared in project metadata?" as open. ADR 0004 already answers it, but the intent does not scope that file, so it is left for the documentation role to raise.
- **Untracked empty folders** under `src/ec_procurement_quality/` (for example `domain/models` and `infrastructure/sercop`) and under `tests/`. They hold no files, so `ruff`, `mypy`, `pytest` and git ignore them. Do not add files to them.
- **Tests to migrate:** none, because no test suite exists yet. No `specs/current` capability exists to migrate.

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| A future `harny init` or `update` rewrites the parts of `harny-feedback.yml` outside the markers and drops the new CI steps, so `ruff` and `mypy` silently skip again | Med | High | Restore comment on the steps and a note in `docs/repository-settings.md` (AC13). After any harny update, check that the `feedback` log still reports `2 of 2 command(s) ran` (AC10). |
| mypy strictness for `domain` is configured but does not take effect | Med | High | Explicit per-module flags instead of `strict = true`, and the probe check in AC8 run in both `domain` and `application` |
| `src/ec_procurement_quality/` gets a third file of its own (for example `__main__.py`) and the doctor starts warning | Med | Low | Binding file-count constraint, and the doctor run in AC12 checks for `0 warned` |
| `uv init` or a copied snippet leaks the git email into `pyproject.toml` | Med | Med | Write `pyproject.toml` by hand, and check the diff for an `authors` entry before committing |
| The latest uv in CI is newer than local uv 0.12.23 and treats `uv.lock` as outdated, or needs to download `uv_build` | Low | Med | `--locked` makes it fail loudly. Relock with the newer uv, or pin setup-uv's `version` input and record why. |
| mypy run per-file on a test file cannot resolve `ec_procurement_quality` from the editable install | Low | Med | Check the per-file command in AC12. If it fails, add `mypy_path = "src"`. |
| Formatting drift reaches `main`, because the `feedback` check runs `ruff check` but not `ruff format --check` | Low | Low | AC7 command before every PR. Adding the format check to CI is left to a later CI change. |
| The AC3 check downloads Python 3.12 or touches the working `.venv` | Med | Low | Run AC3 only in a throwaway clone outside the repo folder |

## Validation
One row per AC. "pytest" means a test in `tests/unit/`, the only test tier in this feature. ACs that pytest cannot check are marked command, manual or CI. AC1, AC2, AC3, AC7, AC8, AC10, AC11, AC12 and AC13 are checked by commands, CI logs or inspection, not by pytest. Commands are written for Git Bash; on PowerShell, use `.venv\Scripts\...` paths where noted. Cwd is the repository root unless stated.

| AC | Demonstrated by | Tests to write | Tier | Framework | Setup | Focused command | Broader command | Cwd |
|---|---|---|---|---|---|---|---|---|
| AC1 | `uv sync --locked` succeeds and leaves `uv.lock` and `pyproject.toml` unchanged, locally, in a fresh clone and in CI | none (command check) | command, CI | uv | none | `uv sync --locked && git status --short -- uv.lock pyproject.toml` (expect exit 0 and no output) | after committing on the feature branch: `tmp=$(mktemp -d) && git clone . "$tmp" && cd "$tmp" && uv sync --locked`; in CI, the `uv sync --locked` step of the `feedback` job is green | repo root; the clone folder for the broader command |
| AC2 (failure) | `uv sync --locked` refuses a lockfile that no longer matches `pyproject.toml` | none (manual) | manual | uv | a throwaway clone: change a version bound in `[dependency-groups] dev` without running `uv lock` | `uv sync --locked; echo $?` (expect non-zero and an error saying the lockfile needs updating; the exact wording is not verified) | delete the clone; in the real repo, `git status --short` shows nothing | the throwaway clone |
| AC3 (failure) | uv refuses Python 3.12 because of `requires-python = ">=3.13"` | none (manual) | manual | uv | a throwaway clone; network access, because uv may download Python 3.12 | `uv sync --python 3.12; echo $?` (expect non-zero and an error naming `>=3.13`; the exact wording is not verified) | in the real repo, `.venv/Scripts/python.exe --version` still prints 3.13 | the throwaway clone |
| AC4 | `--version` prints `ec-procurement-quality 0.1.0` to stdout and exits 0 | `tests/unit/`: calling `main(["--version"])` raises `SystemExit` with code 0; stdout equals `ec-procurement-quality`, a space, `[project] version` read from `pyproject.toml` with `tomllib`, and a newline; stderr is empty | unit | pytest | `uv sync --locked` | `uv run pytest tests/unit -q -k version` | `uv run ec-procurement-quality --version` (expect `ec-procurement-quality 0.1.0`, exit 0) | repo root |
| AC5 (failure) | an unknown option exits 2 with a usage error on stderr and nothing on stdout | `tests/unit/`: calling `main(["--bogus"])` raises `SystemExit` with code 2; stdout is empty; stderr contains `unrecognized arguments: --bogus` | unit | pytest | `uv sync --locked` | `uv run pytest tests/unit -q -k bogus` | `uv run ec-procurement-quality --bogus; echo $?` (expect 2) | repo root |
| AC6 | the four layer packages import cleanly and are empty | `tests/unit/`: importing `ec_procurement_quality.domain`, `.application`, `.infrastructure` and `.interfaces` succeeds; emptiness and the `domain` import rule are checked by inspection at audit | unit | pytest | `uv sync --locked` | `uv run pytest tests/unit -q -k layer` | `uv run python -c "import ec_procurement_quality.domain, ec_procurement_quality.application, ec_procurement_quality.infrastructure, ec_procurement_quality.interfaces"` (expect exit 0, no output) | repo root |
| AC7 | lint and format checks pass on the whole repository | none (command check) | command | ruff | `uv sync --locked` | `uv run ruff check .` | `uv run ruff format --check .` | repo root |
| AC8 | `mypy .` passes, and a probe file proves strict mode in `domain` only | none (manual probe; the probe file is never committed) | command, manual | mypy | `uv sync --locked`; create `src/ec_procurement_quality/domain/probe.py` with `def f(x): return x` | `uv run mypy .` with the probe in `domain` (expect non-zero and "missing a type annotation"), then with the probe moved to `application/` (expect 0), then delete it | `uv run mypy .` with no probe (expect 0) and `git status --short` (no probe file) | repo root |
| AC9 | the suite passes, with the version test collected from `tests/unit/` | the tests listed for AC4, AC5 and AC6 | unit | pytest | `uv sync --locked` | `uv run pytest tests/unit -q` | `uv run pytest` (expect exit 0 and at least 1 passed) | repo root |
| AC10 | the `feedback` job really runs both tools | none (CI log check) | CI | GitHub Actions, harny runner | the F0 pull request | locally, the same runner: `uv run node .sdd/feedback/run-feedback.mjs run --whole-project --commands "$(cat .sdd/git-hooks/commands.json)"` (expect `harny-feedback: 2 of 2 command(s) ran, 0 skipped.` and exit 0) | the `harny feedback (Python)` step log on the F0 pull request ends with `harny-feedback: 2 of 2 command(s) ran, 0 skipped.`, and the `feedback` check is green | repo root |
| AC11 (failure) | a lint error makes the runner, and therefore the `feedback` check, fail | none (manual; the change is reverted, never committed to `main`) | manual, CI | harny runner, ruff | temporarily add `import os` (unused) to a file under `src/` | the local runner command from AC10 (expect `finding from \`ruff\`` and exit 2), then revert the file | optional: push the same change on a throwaway branch or draft pull request and see the `feedback` check fail; close it without merging | repo root |
| AC12 (compatibility) | the doctor, the gitleaks step, the AGENTS.md interpreter check and whitespace checks keep passing; per-file hook-style runs pass | none (command check) | command, CI | harny doctor, git, ruff, mypy | `uv sync --locked` | `node .sdd/doctor/run-doctor.mjs` (expect `0 warned, 0 failed`) and `uv run node .sdd/doctor/run-doctor.mjs` (expect `OK pytest`) | `.venv/Scripts/python.exe --version` (PowerShell: `.venv\Scripts\python.exe --version`, expect 3.13.x); `git diff --check`; after committing, `uv run ruff check $(git diff --name-only main -- '*.py')` and `uv run mypy $(git diff --name-only main -- '*.py')` (the per-file form the hooks use, expect exit 0); the F0 pull request log shows the `Secret scan (gitleaks)` step ran | repo root |
| AC13 | the restore comment, the restore note and the hook limitation are documented where the intent says | none (inspection at audit) | manual | git | none | `git grep -n "setup-uv" -- .github/workflows/harny-feedback.yml docs/repository-settings.md` (expect the step with an adjacent restore comment, and a note naming it) | `git grep -n -i "PATH" -- README.md` (expect the statement that the Stop and pre-commit hooks run `ruff` and `mypy` only when `.venv` is on `PATH`); `git diff` shows no change between the harny markers | repo root |

## Revision log
- Revision 1 (2026-10-07): First draft, based on intent Revision 2 as approved. Approved revision 1 by Vladimirjon on 2026-10-07.
