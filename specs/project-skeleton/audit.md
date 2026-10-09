# Audit: Project skeleton (F0)

Round 1, 2026-10-08. Branch `feat/project-skeleton`, local head `f374dfd`
(PR #11 head on GitHub is `f13ac5d`; `f374dfd` changes only `tasks.md`).
Merge base and diff base: `main` at `f07c304`. Working tree clean before and
after the audit. Local toolchain: uv 0.12.23, Python 3.13.9, Node v22.23.1.
Specs read: `intent.md` Revision 2 (approved 2026-10-07), `execution-plan.md`
Revision 1 (approved 2026-10-07), `tasks.md` (Working state updated
2026-10-08). Every changed file in `git diff main...HEAD` was read in full.

Evidence labels: `rerun` = run by the auditor in this round; `reused` = taken
from `tasks.md` or CI with its command, result and state still current;
`unavailable` = not checked.

## AC results
| AC | Status | Evidence |
|---|---|---|
| AC1 | PASS | Fresh clone of `f374dfd` in a scratch folder (`git -c core.longpaths=true clone`), `uv sync --locked` -> exit 0, created `.venv`, installed 16 packages including `ec-procurement-quality==0.1.0`; `git status --short` in the clone empty (rerun). In the repo, `uv sync --locked` -> exit 0, "Checked 16 packages", `git status --short -- uv.lock pyproject.toml` empty (rerun). CI: `uv sync --locked` step in run 37884423074 resolved 16, installed 15, green (reused, read with `gh run view --log`). |
| AC2 | PASS | Same throwaway clone, dev bound `"pytest>=9.1.1"` changed to `"pytest>=9.0.0"` without `uv lock`; `uv sync --locked` -> exit 1, `error: The lockfile at \`uv.lock\` needs to be updated, but \`--locked\` was provided.` plus `hint: To update the lockfile, run \`uv lock\`.` (rerun). |
| AC3 | PASS | Second throwaway clone, run from PowerShell: `uv sync --python 3.12` -> exit 2, `error: The requested interpreter resolved to Python 3.12.15, which is incompatible with the project's Python requirement: \`>=3.13\` (from \`project.requires-python\`)`; no `.venv` created (rerun). The Git Bash quirk recorded in O7 was not re-tested. |
| AC4 | PASS | `uv run ec-procurement-quality --version` -> stdout exactly one line `ec-procurement-quality 0.1.0` (CRLF from Windows text-mode stdout), stderr 0 bytes, exit 0 (rerun). `cli.py` reads the version with `importlib.metadata.version("ec-procurement-quality")`, `prog` set explicitly, no version literal (inspection, rerun). Unit test passes (rerun). |
| AC5 | PASS | `uv run ec-procurement-quality --bogus` -> exit 2, stdout 0 bytes, stderr `usage: ec-procurement-quality [-h] [--version]` and `ec-procurement-quality: error: unrecognized arguments: --bogus` (rerun). Unit test passes (rerun). |
| AC6 | PASS | `uv run python -c "import ec_procurement_quality.domain, ...application, ...infrastructure, ...interfaces"` -> exit 0, no output (rerun). The four `__init__.py` files are empty; `domain`, `application`, `infrastructure` contain only `__init__.py`; `interfaces` holds `__init__.py` and `cli.py` (inspection, rerun). Unit tests pass in the repo and in the clean clone, where the untracked empty folders do not exist (rerun). |
| AC7 | PASS | `uv run ruff check .` -> exit 0, "All checks passed!"; `uv run ruff format --check .` -> exit 0, "46 files already formatted" (rerun). |
| AC8 | PASS | `uv run mypy .` -> exit 0, "no issues found in 8 source files" (rerun). Untracked probe `domain/probe.py` with `def f(x): return x` -> exit 1, `src\ec_procurement_quality\domain\probe.py:1: error: Function is missing a type annotation  [no-untyped-def]`; same file in `application/` -> exit 0 "no issues found in 9 source files"; probe deleted, `uv run mypy .` -> exit 0, `git status --short` empty (rerun). |
| AC9 | PASS | `uv run pytest` -> exit 0, 7 collected, `7 passed`, version test in `tests/unit/test_cli.py` (rerun). CI `Tests` run 37884423088 -> `7 passed` (reused). |
| AC10 | PASS | CI run 37884423074 (`harny feedback`, PR #11 at `f13ac5d`): `harny feedback (Python)` step log line `harny-feedback: 2 of 2 command(s) ran, 0 skipped.`, `feedback` check SUCCESS (reused; confirmed read-only with `gh run view 37884423074 --log` and `gh pr view 11`). Locally, `uv run node .sdd/feedback/run-feedback.mjs run --whole-project --commands "$(cat .sdd/git-hooks/commands.json)"` -> `2 of 2 command(s) ran, 0 skipped.`, exit 0; the same runner without `uv run` -> `0 of 2 command(s) ran, 2 skipped.`, which confirms the CI PATH step is what makes the difference (rerun). |
| AC11 | PASS | Local runner path, which the AC11 Example allows: an untracked file `src/ec_procurement_quality/interfaces/audit_probe.py` containing `import os` -> runner printed ``finding from `ruff` (exit 1):`` with `F401 [*] \`os\` imported but unused`, then `harny-feedback: 2 of 2 command(s) ran, 0 skipped.`, exit 2; file deleted, `git status --short` empty (rerun; an untracked file was used so no tracked file was touched). CI-side probe on a throwaway PR: not run (unavailable; optional in § Validation and O8, see F3). |
| AC12 | PASS | `node .sdd/doctor/run-doctor.mjs` -> `29 ok, 2 skipped, 0 warned, 0 failed`, no `component-doc` warning (rerun). `uv run node .sdd/doctor/run-doctor.mjs` -> `OK pytest`, `30 ok, 1 skipped, 0 warned, 0 failed` (rerun). `.venv/Scripts/python.exe --version` -> `Python 3.13.9` (rerun). `git diff --check` and `git diff --check main...HEAD` -> exit 0 (rerun). Per-file hook form on `git diff --name-only main -- '*.py'` (8 files): `uv run ruff check` exit 0, `uv run mypy` exit 0 "no issues found in 8 source files" (rerun). `Secret scan (gitleaks)` step in run 37884423074 ran gitleaks 8.30.1, `4 commits scanned`, `no leaks found` (reused, log confirmed). `git diff --name-only main -- .sdd .claude .github/dependabot.yml` empty (rerun). |
| AC13 | PASS | `.github/workflows/harny-feedback.yml`: a 5-line "HAND-MAINTAINED" comment directly above the three new steps, each step name ending "(hand-maintained, restore after harny init or update)"; the `astral-sh/setup-uv` step is the first of them. `docs/repository-settings.md`: new subsection "Hand-maintained steps in `harny-feedback.yml`" naming the three steps and giving a 3-step restore procedure. `README.md` § Development commands: the Stop and pre-commit hooks run `ruff` and `mypy` only when `.venv` is on `PATH` and skip otherwise; `AGENTS.md` repeats it (inspection of `git diff main...HEAD`, rerun). |

## Binding-constraint compliance
| Constraint | Status | Evidence |
|---|---|---|
| Python version | PASS | `requires-python = ">=3.13"`; CI used CPython 3.13.16 with `UV_PYTHON=3.13` (log of run 37884423074); AC3 refusal rerun. |
| Reproducible installs | PASS | `uv.lock` committed; both CI workflows install with `uv sync --locked`; AC1 and AC2 rerun. |
| Allowed dependencies | PASS, with a recording gap | `[project] dependencies = []`; build backend `uv_build>=0.12.23,<0.13`. Dev group: `mypy`, `pytest`, `ruff` and also `pytest-cov>=7.1.0` (lock adds `pytest-cov` 7.1.0 and `coverage` 7.16.2). The constraint allows "anything else" with explicit prior approval; the human's approval of `pytest-cov` (2026-10-08) is recorded only in `tasks.md` Working state ("approved dependency"), not in intent § Constraints next to `uv_build` and `setup-uv`. Lockfile transitives otherwise match the three tools. See F1. |
| Approved versions | PASS | Versions resolved at implementation time and recorded in `uv.lock` (mypy 2.4.0, pytest 9.1.1, ruff 0.16.10). |
| Console script contract | PASS | `[project.scripts] ec-procurement-quality = "ec_procurement_quality.interfaces.cli:main"`; `main(argv: list[str] \| None = None)`; exits through `SystemExit` 0 and 2 (unit tests and CLI rerun). |
| Version output | PASS | `prog="ec-procurement-quality"`, `version=f"%(prog)s {version(DISTRIBUTION_NAME)}"`; no version literal in code. |
| Standard library only | PASS | `cli.py` imports only `argparse` and `importlib.metadata`. |
| Layer boundaries | PASS | `domain`, `application`, `infrastructure` hold only empty `__init__.py`; no import in `domain`; no SERCOP, PostgreSQL or storage reference in `src/`. |
| Strict mypy in `domain` only | PASS | Override for `ec_procurement_quality.domain.*` sets all 9 required flags, no `strict = true`; global `[tool.mypy]` holds only comments; AC8 probe rerun. |
| mypy from the repo root | PASS | `uv run mypy .` and the per-file form on the 8 changed `.py` files both exit 0; no `mypy_path` needed. |
| Doctor component discovery | PASS | `src/ec_procurement_quality/` holds one file of its own (`__init__.py`); doctor `0 warned`. |
| CI workflow file | PASS | `git diff main -- .github/workflows/harny-feedback.yml` is one 13-line hunk after `Checkout` and before `harny:begin`; nothing between the markers changed; job id `feedback` unchanged; gitleaks step unchanged and green. |
| setup-uv pinning | PASS | `astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7 # v10.2.0`. `gh api repos/astral-sh/setup-uv/git/ref/tags/v10.2.0` -> type `commit`, same SHA; `releases/latest` -> `v10.2.0` (rerun). The plan named `v10.1.0` as "the latest release" on 2026-10-07; the constraint itself only requires an explicit release, and O4 told the executor to re-check. Compliant alternative, recorded in `tasks.md`; no finding. `.github/dependabot.yml` unchanged. |
| Restore instructions | PASS | See AC13. Hook files unchanged (`git diff --name-only main -- .sdd .claude` empty). |
| No sensitive data | PASS | No `authors`, no email and no local path in `pyproject.toml`, `uv.lock`, `src/` or `tests/`; gitleaks `no leaks found`. |
| Scope ("no `tests.yml`, no coverage, no new test tier, no sub-packages inside the layers"; intent § Out) | FAIL as written | Commit `f13ac5d` adds `.github/workflows/tests.yml`, which runs `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing` in CI, and adds `pytest-cov` to the dev group. Both are explicitly listed in intent § Out ("`.github/workflows/tests.yml` and running `pytest` or coverage in CI") and in this constraint. The human decided on 2026-10-08 to do the Day 6 step now, but the approved intent and plan were not revised. No sub-packages and no new test tier were added (the CI job runs the same unit tests); the `tests` check was not made required (`required_status_checks.contexts = ["feedback"]`, read-only `gh api`), so that § Out item holds. See F1. |

Consumers and migration: the `feedback` job, the doctor, the Stop, SubagentStop
and pre-commit hooks, the local `.venv` (reused, still 3.13.9) and branch
protection were checked; none of their files changed and all keep working.
No tests needed migrating (no suite existed).

## Test coverage
| AC | Test | Status |
|---|---|---|
| AC1 | none (command and CI check) | PASS (rerun command; CI reused) |
| AC2 | none (manual) | PASS (rerun) |
| AC3 | none (manual) | PASS (rerun) |
| AC4 | `tests/unit/test_cli.py::test_version_prints_program_name_and_pyproject_version` | PASS (rerun). Red recorded in O3: collection `ImportError: cannot import name 'main'` (plausible, the module did not exist). Would fail if `--version` were removed or its output changed. |
| AC5 | `tests/unit/test_cli.py::test_bogus_option_is_a_usage_error` | PASS (rerun). Red recorded in O3 (same collection error). |
| AC6 | `tests/unit/test_layers.py::test_layer_package_is_importable[domain\|application\|infrastructure\|interfaces]`, `::test_layer_domain_imports_only_stdlib_and_itself` | PASS (rerun). Red recorded in O2: `5 failed`, `assert None is not None` for namespace packages; the `__file__` check makes the tests red in both a dirty and a clean tree. |
| AC7 | none (command check) | PASS (rerun) |
| AC8 | none (manual probe) | PASS (rerun) |
| AC9 | the AC4, AC5 and AC6 tests above | PASS (rerun; 7 passed) |
| AC10 | none (CI log) | PASS (reused, log confirmed) |
| AC11 | none (manual, optional CI) | PASS locally (rerun); CI probe unavailable |
| AC12 | none (command and CI check) | PASS (rerun; gitleaks reused) |
| AC13 | none (inspection) | PASS (rerun) |

No dead test seam: `main(argv)` is the console-script target and is called by
both CLI tests. The default `uv run pytest` run is offline. There is no
baseline suite, so no failure comparison applies.

### Tier Results
| Tier | Tests found | ACs verified | Setup matches § Validation | Ran | Status | Finding |
|---|---|---|---|---|---|---|
| unit (pytest, `tests/unit/`) | 7 tests in `tests/unit/test_cli.py` and `tests/unit/test_layers.py` | AC4, AC5, AC6, AC9 | No. § Validation names only `uv sync --locked` with pytest. Present in addition: `pytest-cov` in the dev group, and `.github/workflows/tests.yml` running the unit tier in CI with `--cov` | rerun: `uv run pytest` exit 0, `7 passed`; `-k version`, `-k bogus`, `-k layer` selections exist by name. CI `Tests` run 37884423088: `7 passed`, `TOTAL 10 0 100%` (reused) | PARTIAL | F2 |
| command | n/a (commands, no test files) | AC1, AC7, AC8, AC12 | Yes | rerun | PASS | none |
| manual | n/a | AC2, AC3, AC8, AC11, AC13 | Yes (throwaway clones, untracked probe files) | rerun | PASS | none |
| CI (`feedback` job) | n/a | AC1, AC10, AC12 | Yes | reused (run 37884423074, log read) | PASS | none |
| CI (AC11 optional throwaway PR) | n/a | AC11 | Yes | not run: optional, skipped by the human (O8) | N/A | F3 |

No test exists at a tier § Validation does not name; `tests.yml` runs the
named unit tier in CI and is covered by F2 as unapproved-at-spec setup.

## Conventions and feedback checks
- `harny-standards`: this project's conventions document is `AGENTS.md`
  (no `CLAUDE.md`). It has no separate coding-standards section; its
  declared rules were checked: layer boundaries (PASS), modular-monolith
  boundary (PASS), raw responses and SERCOP contracts (N/A, nothing
  introduced), approval before dependencies or infrastructure (approval for
  `pytest-cov` and `tests.yml` given by the human but not recorded in the
  spec, F1), no secrets or raw datasets (PASS), run verification after every
  change (PASS, recorded in `tasks.md` and rerun here).
- `harny-feedback`: `src/feedback.ts` is part of the harny package, not this
  repo; the mapped commands are read from `.sdd/git-hooks/commands.json` and
  the generated CI step (ruff check, mypy). The generated workflow is present
  and its run on PR #11 is green with `2 of 2 command(s) ran, 0 skipped.`
  (N = 2). The local Stop and pre-commit hooks probe-skipped both commands
  during implementation because `.venv` was not on `PATH` (N = 0), so the
  per-turn hook gave no feedback; see F4. Lint and type-check were run here
  only as the AC7, AC8 and AC12 commands that O9 assigns to the auditor.

## O9 results (broader suite vs baseline)
All rerun on 2026-10-08 at `f374dfd`: `uv run pytest` exit 0, `7 passed`
(baseline: no suite); `uv run ruff check .` exit 0; `uv run ruff format
--check .` exit 0; `uv run mypy .` exit 0; `node .sdd/doctor/run-doctor.mjs`
`29 ok, 2 skipped, 0 warned, 0 failed` (baseline `1 failed`, the
`spec-state` failure, now gone; no new failure); `uv run node
.sdd/doctor/run-doctor.mjs` `30 ok, 1 skipped, 0 warned, 0 failed`; `git diff
--check` exit 0. O9 is satisfied. This file does not tick O9 or O10 in
`tasks.md`; the auditor writes only `audit.md`.

## Findings
| Id | Severity | Finding | Closure condition | Status |
|---|---|---|---|---|
| F1 | CRITICAL | Binding constraint "Scope" (execution-plan) and intent § Out are not met as written: commit `f13ac5d` adds `.github/workflows/tests.yml` (pytest with coverage in CI) and the `pytest-cov` dev dependency. The human approved this on 2026-10-08, but the approval exists only as a note in `tasks.md` Working state; intent Revision 2 and execution-plan Revision 1 still exclude both. This is a spec-of-record gap, not a product defect: the workflow is green and the addition is harmless. It blocks approval because an unmet binding constraint blocks at any severity. Cites: execution-plan § Binding constraints "Scope" and "Allowed dependencies"; intent § Out and § Constraints. | Either (a) the architect issues intent Revision 3 (move `tests.yml` and CI pytest with coverage from § Out to § In; add `pytest-cov` to § Constraints as an approved dev dependency with the 2026-10-08 date) and execution-plan Revision 2 (update "Allowed dependencies" and "Scope", add the `tests.yml` setup to § Validation), both re-approved by the human; or (b) `f13ac5d` is moved out of this branch into its own Day 6 change. Then a round-2 audit confirms. | Open |
| F2 | HIGH | Tier setup present that § Validation does not name: `pytest-cov` in `[dependency-groups] dev` and `.github/workflows/tests.yml` running the unit tier with `--cov`. Cites: AC9 row of § Validation (Setup: `uv sync --locked` only). | Closed by the same spec revision as F1(a) (§ Validation names the setup), or by F1(b). | Open |
| F3 | LOW | AC11 CI-side probe (unused import on a throwaway PR) was not run by the human or the auditor; red status of the `feedback` check on GitHub is inferred from the local runner (same runner, same command list) and from AC10's `2 of 2` CI line, not observed. Cites: AC11, § Validation AC11 row (marked optional). | Accept as is (the AC11 Example allows the local runner), or run the probe on a throwaway draft PR and record the red check in `tasks.md`. | Open (acceptable) |
| F4 | LOW | Feedback-loop gap: the Stop, SubagentStop and pre-commit hooks probe-skipped `ruff` and `mypy` (N = 0) throughout implementation because `.venv` was not on `PATH`. Compensated by the executor's manual per-file `uv run` runs (O1, O5, O7), the rerun here, and CI `2 of 2`. Changing the hooks is in intent § Out and the limitation is documented (AC13). Cites: AC12, AC13. | Accept as the documented limitation; optionally activate `.venv` in the agent shell for later features. | Open (accepted limitation) |
| F5 | LOW | `tasks.md` evidence is partly stale or inaccurate: O8 says "The `setup-uv` v10.2.0 pin worked with uv 0.12.23", but the CI log shows setup-uv fell back to the latest uv and downloaded 0.12.24 (`--locked` still passed, so the drift risk did not materialise); Status is still "Implementing" and the Checkpoint says "O1 to O7 are done" while Working state says O1 to O8; the local head `f374dfd` is not yet pushed (PR #11 head is `f13ac5d`). Cites: AC1, AC10 evidence. | The executor or conductor corrects the uv version in O8, aligns Status and Checkpoint, ticks O9 and O10 after the gate, and pushes so PR #11 runs on the final head. | Open |

Notes (not findings):
- Base commit `f07c304` instead of `699cae5`: `git diff --stat 699cae5 f07c304`
  touches only `specs/project-skeleton/*` and `docs/learning/journal.md`
  (merge of PR #10). The deviation is recorded in `tasks.md` and does not
  affect the product diff.
- The human deleted untracked, empty local folders under
  `src/ec_procurement_quality/` during the red phase. They were never in git;
  the tracked tree is unaffected, the clean clone passes all 7 tests, and the
  O2/O3 red evidence stays valid (the tests check `__file__`, so they are red
  with or without the folders). Empty untracked folders remain under
  `tests/` (`contract`, `end_to_end`, `fixtures`, `integration`), outside git.
- The `feedback` job does not run `ruff format --check`, as the plan's Risks
  table accepts.
- `tests.yml` pins `setup-uv` by SHA but `actions/checkout@v7` by major tag,
  the same as the generated workflow.

## Audit log
| Round | Date | Verdict | Notes |
|---|---|---|---|
| 1 | 2026-10-08 | REJECTED | All 13 ACs PASS and every binding constraint except "Scope" passes. Blocking only on F1 (CRITICAL, spec-of-record gap for the human-approved `tests.yml` and `pytest-cov`), with F2 (HIGH) closing with it. F3 to F5 are LOW. No product code change is required to close F1 under option (a). |

## Final verdict

REJECTED

**Summary**: The F0 skeleton meets all 13 acceptance criteria. Every check
was rerun or confirmed in the CI log, and the product code, tests, CI steps
and docs follow the plan. The approved spec still excludes the
`tests.yml`/`pytest-cov` addition from commit `f13ac5d`, and an unmet binding
constraint blocks approval. A spec revision that records the human's
2026-10-08 decision closes it without any code change.

**Critical Issues** (must fix before merge):
- F1: record the 2026-10-08 scope change in intent Revision 3 and
  execution-plan Revision 2 (or move `f13ac5d` to its own Day 6 change), then
  re-audit.

**Warnings** (should fix, not blocking):
- F2: name the `pytest-cov` and `tests.yml` setup in § Validation (closes
  with F1).

**Recommendations** (nice to have):
- F3: optionally run the AC11 throwaway-PR probe once to see the `feedback`
  check go red.
- F4: activate `.venv` in the agent shell so the per-turn hook gives real
  feedback in later features.
- F5: correct the uv version in O8, align Status and Checkpoint in
  `tasks.md`, and push `f374dfd` so PR #11 runs on the final head.
