# CLI Specification

> Last synced: 2026-10-08. Owned artifacts: `src/ec_procurement_quality/interfaces/cli.py`, `[project.scripts]` in `pyproject.toml`, `tests/unit/test_cli.py`.

## Purpose

The `ec-procurement-quality` command-line entry point, living in the
`interfaces` layer. It is its own capability, separate from
`project-toolchain`, because it is the first user-facing contract of the
product; every later command extends it. Today its only behavior is
`--version`.

## Requirements

### Requirement: CLI-1 — Version output

The system SHALL print exactly one line, `ec-procurement-quality <version>`, to
standard output and exit with code 0 when invoked with `--version`, where
`<version>` is the `[project] version` declared in `pyproject.toml` (`0.1.0` at
F0).

**Source:** project-skeleton · intent.md § AC4

#### Scenario: Version is requested
- **WHEN** `uv run ec-procurement-quality --version` is run
- **THEN** stdout is `ec-procurement-quality 0.1.0`, stderr is empty and the exit code is 0

### Requirement: CLI-2 — Unknown option is a usage error

The system SHALL reject an unrecognized option with exit code 2, nothing on
standard output, and a usage message on standard error that names the
unrecognized argument.

**Source:** project-skeleton · intent.md § AC5

#### Scenario: Unknown option
- **WHEN** `uv run ec-procurement-quality --bogus` is run
- **THEN** the exit code is 2, stdout is empty, and stderr contains `usage: ec-procurement-quality [-h] [--version]` and `error: unrecognized arguments: --bogus`

### Requirement: CLI-3 — Console script and entry point

The system SHALL expose the console script `ec-procurement-quality`, whose
target is `ec_procurement_quality.interfaces.cli:main`, where `main` accepts an
optional list of argument strings and reads the process arguments when given
none; `--version` and usage errors end through `SystemExit`.

**Source:** project-skeleton · execution-plan.md § Binding constraints "Console script contract"

#### Scenario: In-process call
- **WHEN** a test calls `main(["--version"])` or `main(["--bogus"])`
- **THEN** it raises `SystemExit` with code 0 or 2 respectively

## Invariants

1. The version has one source of truth, `[project] version` in
   `pyproject.toml`. The CLI reads it from the installed package metadata and
   never hard-codes it; a second literal would let the two drift.
2. The CLI uses only the Python standard library until the CLI framework
   decision (D-09) is made.
3. What a bare `ec-procurement-quality` (no arguments) does is not defined yet;
   it waits for the first real command.

## Open reservations

None yet.

## Contributing features

| Feature | Shipped | What it established |
|---|---|---|
| project-skeleton (F0) | 2026-10-08 | `--version`, usage error for unknown options, the console script and `main` contract (CLI-1 to CLI-3) |

## Related ADRs

None yet.
