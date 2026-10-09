# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
The project has not been released yet, so every entry is under `Unreleased`.

## [Unreleased]

### Added

- Project skeleton (F0): an installable Python 3.13 package,
  `ec-procurement-quality` 0.1.0, built with `uv_build` and managed with `uv`
  and a committed `uv.lock`. No runtime dependencies.
- `src/ec_procurement_quality/` with the empty `domain`, `application`,
  `infrastructure` and `interfaces` layer packages.
- CLI `ec-procurement-quality`, standard library only. `--version` prints
  `ec-procurement-quality 0.1.0` and exits 0; an unknown option exits 2 with a
  usage error on stderr. Any other behavior is not implemented yet.
- Configuration for `ruff` (lint and format), `mypy` (strict in `domain` only)
  and `pytest`, all in `pyproject.toml`, and 7 unit tests under `tests/unit/`.
- `Tests` GitHub Actions workflow (`.github/workflows/tests.yml`): runs the unit
  tests with a `pytest-cov` coverage report on pull requests and on pushes to
  `main`, installing with `uv sync --locked`. There is no coverage threshold.
- `pytest-cov` as a development-only dependency.

### Changed

- The `feedback` CI job now installs the locked dependencies and puts `.venv`
  on `PATH` through three hand-maintained steps, so `ruff` and `mypy` actually
  run (`2 of 2 command(s) ran`) instead of being skipped. These steps must be
  restored after any `harny init` or `update`; see
  `docs/repository-settings.md`.
- `README.md` and `AGENTS.md` list the real install, CLI, lint, type and test
  commands, and document that the Stop and pre-commit hooks run `ruff` and
  `mypy` only when `.venv` is on `PATH`.
- `docs/architecture.md` no longer lists the Python compatibility range as an
  open question; it is answered by ADR 0004.

### Known limitations

- Accepted at audit (APPROVED WITH RESERVATIONS): the CI-side checks that a lint
  error fails `feedback` and that a failing test fails `tests` were verified
  locally only, not on a throwaway pull request. The local Stop and pre-commit
  hooks skip `ruff` and `mypy` when `.venv` is not on `PATH`.
- No coverage threshold is enforced yet; it is decided once real domain code
  exists.
