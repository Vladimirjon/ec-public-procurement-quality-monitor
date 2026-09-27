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

There is no application command, test suite, or dependency configuration yet.
Available checks include:

```powershell
.venv\Scripts\python.exe --version
.venv\Scripts\python.exe -c "import sys; print(sys.prefix != sys.base_prefix)"
git status --short
git diff --check
```

Run relevant verification after every change and report the results.

## Change restrictions

Ask for approval before adding dependencies or infrastructure, changing
architectural decisions, introducing frameworks, or adding services. Do not
include secrets, credentials, or complete raw datasets in source, prompts,
logs, tests, or documentation. Prefer minimal fixtures and synthetic or
sanitized examples.
