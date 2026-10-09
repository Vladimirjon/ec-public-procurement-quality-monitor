# Repository instructions

## Reading order

Read this file first, then [README.md](README.md),
[docs/architecture.md](docs/architecture.md), and the relevant ADR. Read
[docs/ai-assisted-development.md](docs/ai-assisted-development.md) when a
task involves an AI assistant.

## Boundaries

- `domain` contains business concepts and rules and must not depend on
  SERCOP, PostgreSQL, local storage, or interface frameworks.
- `application` coordinates use cases through ports.
- `infrastructure` implements external-system and persistence adapters.
- `interfaces` exposes CLI or other entry points and translates external
  input into application requests.

Keep the modular-monolith boundary explicit. Raw responses are evidence and
must not be overwritten. Do not invent SERCOP contracts; use observed,
documented source behavior and approved fixtures.

## Current commands

Install and run from the repository root with `uv` (Python 3.13, committed
`uv.lock`):

```powershell
uv sync --locked
uv run ec-procurement-quality --version
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest
uv run pytest --cov=ec_procurement_quality --cov-report=term-missing
```

The last command is what the `Tests` workflow runs in CI. It reports coverage
and sets no minimum percentage.

Other available checks:

```powershell
.venv\Scripts\python.exe --version
.venv\Scripts\python.exe -c "import sys; print(sys.prefix != sys.base_prefix)"
git status --short
git diff --check
```

The Stop and pre-commit hooks run `ruff` and `mypy` only when `.venv` is on
`PATH`.

Run relevant verification after every change and report the results.

## Change restrictions

Ask for approval before adding dependencies or infrastructure, changing
architectural decisions, introducing frameworks, or adding services. Do not
include secrets, credentials, or complete raw datasets in source, prompts,
logs, tests, or documentation. Prefer minimal fixtures and synthetic or
sanitized examples.
