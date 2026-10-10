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
- Local raw evidence store (F1), following
  [ADR 0005](docs/adr/0005-raw-evidence-store-layout.md): the `ContentHash`
  value object, the `Observation` record and the evidence errors in `domain`;
  the `RawEvidenceStore` port in `application`; and `LocalDiskRawEvidenceStore`
  in `infrastructure`, which keeps response bytes once under their SHA-256 and
  one JSON observation per response obtained, publishes files write-once and
  atomically, never persists `Set-Cookie` headers, and verifies integrity on
  read. No CLI command or use case calls it yet, and no dependency was added.
- SERCOP source adapter (F2), following
  [ADR 0006](docs/adr/0006-http-client-for-source-access.md): `RawResponse` and
  the source errors (`SourceError`, `SourceTransportError`,
  `SourceStatusError`, `IncompleteResponseError`) in `domain`; the
  `ProcurementSource` port with `SearchPage` and `RecordResponse` in
  `application`; and `SercopSource` in `infrastructure`, on a synchronous
  `httpx.Client`. One call makes one request, to the buyer-name search
  (`search_ocds`) or to `api/record`, and returns the response exactly as
  received or raises a typed error that carries the valid response that arrived
  (a status outside 100 to 599 is reported without a response), so that failed
  and partial responses can be stored through the raw evidence store. It never
  retries, spaces requests from the `X-RateLimit-Remaining`
  header, sets explicit timeouts, and rejects a base URL with user
  information. Its tests use `httpx.MockTransport` and a network guard, and
  never reach the network. It is a library only: no CLI command or use case
  calls it yet.
- `httpx` as the first runtime dependency (`httpx>=0.28.1` in
  `[project] dependencies`, resolved to 0.28.1 in `uv.lock`), imported only in
  `infrastructure`. The development dependencies do not change.

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
- `README.md` and `docs/architecture.md` describe the raw evidence store and
  link ADR 0005; the raw-storage paths and metadata question is answered there
  for local storage, while compression and retention stay open.

### Known limitations

- Accepted at audit (APPROVED WITH RESERVATIONS): the CI-side checks that a lint
  error fails `feedback` and that a failing test fails `tests` were verified
  locally only, not on a throwaway pull request. The local Stop and pre-commit
  hooks skip `ruff` and `mypy` when `.venv` is not on `PATH`.
- No coverage threshold is enforced yet; it is decided once real domain code
  exists.
