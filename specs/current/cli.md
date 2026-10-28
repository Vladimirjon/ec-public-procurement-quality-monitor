# CLI Specification

> Last synced: 2026-10-28. Owned artifacts: `src/ec_procurement_quality/interfaces/cli.py`, `src/ec_procurement_quality/interfaces/ingest_command.py`, `src/ec_procurement_quality/interfaces/output_streams.py`, `[project.scripts]` in `pyproject.toml`, `tests/unit/test_cli.py`, `tests/unit/ingest/test_ingest_command.py`, `tests/integration/ingest/test_ingest_cli.py`, `tests/process/test_cli_process_streams.py`.

## Purpose

The `ec-procurement-quality` command-line entry point, living in the
`interfaces` layer. It is its own capability, separate from
`project-toolchain`, because it is the first user-facing contract of the
product; every later command extends it. Today its behaviors are `--version`
and the `ingest` command (the use case itself is the `ingestion` capability).

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

**Source:** project-skeleton · intent.md § AC5; ingest-command · execution-plan.md § Ownership (`cli` capability: the usage line gains the subcommand)

#### Scenario: Unknown option
- **WHEN** `uv run ec-procurement-quality --bogus` is run
- **THEN** the exit code is 2, stdout is empty, and stderr contains `usage: ec-procurement-quality [-h] [--version] {ingest} ...` (the line read `usage: ec-procurement-quality [-h] [--version]` until the `ingest` subcommand was added) and `error: unrecognized arguments: --bogus`

### Requirement: CLI-3 — Console script and entry point

The system SHALL expose the console script `ec-procurement-quality`, whose
target is `ec_procurement_quality.interfaces.cli:main`, where `main` accepts an
optional list of argument strings and reads the process arguments when given
none; `--version` and usage errors end through `SystemExit`.

**Source:** project-skeleton · execution-plan.md § Binding constraints "Console script contract"

#### Scenario: In-process call
- **WHEN** a test calls `main(["--version"])` or `main(["--bogus"])`
- **THEN** it raises `SystemExit` with code 0 or 2 respectively

### Requirement: CLI-4 — The `ingest` subcommand

The system SHALL provide `ec-procurement-quality ingest`, an optional
subcommand of the CLI, supported only when run from the repository root. A
fresh run takes `--year`, `--buyer` and `--last-page` (required),
`--first-page` (optional, 1 by default) and `--migrations-dir` (optional,
`migrations` by default); `--resume <execution id>` replaces the scope options
and cannot be combined with them. The command SHALL read `POSTGRES_DB`,
`POSTGRES_USER` and `POSTGRES_PASSWORD` (required) and `POSTGRES_HOST` and
`POSTGRES_PORT` (optional, `127.0.0.1` and `5432`) from the process environment
only and never read `.env`, resolve `data/raw/` against the current directory
once at start, and delegate the run to `run_ingest` (`ingestion`). A bare
`ec-procurement-quality` SHALL print the usage on stderr and exit 2.

**Source:** ingest-command · intent.md § AC14, AC21, AC25; execution-plan.md § Ownership

#### Scenario: A fresh run
- **WHEN** `uv run --env-file .env ec-procurement-quality ingest --year 2025 --buyer "SYNTHETIC BUYER S.A." --first-page 1 --last-page 3` is run from the repository root against the Compose PostgreSQL
- **THEN** the command requests the pages of that scope one by one, from page 1 to page 3 or to the last page the source reports (`ingestion`), writes `<execution id> <status>` on stdout and ends with the exit code of CLI-6

#### Scenario: Bare command
- **WHEN** `ec-procurement-quality` is run with no arguments
- **THEN** the usage is printed on stderr, stdout is empty and the exit code is 2

### Requirement: CLI-5 — Usage, configuration and resumption-target errors exit 2 before anything is started

The system SHALL exit 2, with stdout empty, a message on stderr that names the
argument or variable and never its value, no request to the source, no file in
the store, no connection to the database and no run, for: an invalid or missing
option; a missing or invalid `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
or `POSTGRES_PORT`; a malformed proxy or certificate setting of the environment
that the source cannot be built from (`HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`,
`NO_PROXY`, `SSL_CERT_FILE`, `SSL_CERT_DIR`); a `MigrationError` other than a
busy lock; and an invalid resumption target (a malformed id, an id that names no
run, a run that already `succeeded`, or `--resume` with a scope option). The
pending migrations may already have been applied in the migration and
resumption-target cases. A busy migration lock exits 1, and so does a
resumption target that the database could not read.

**Source:** ingest-command · intent.md § AC14, AC16; execution-plan.md § Exit codes

#### Scenario: Missing variable
- **WHEN** `ingest --year 2025 --buyer "SYNTHETIC BUYER S.A." --last-page 1` is run with `POSTGRES_DB` unset
- **THEN** the exit code is 2, stdout is empty, stderr names `POSTGRES_DB` and not any value, and no connection is attempted

### Requirement: CLI-6 — The result line and the exit codes of `ingest`

The system SHALL write to stdout a single line `<execution id> <status>`
whenever the invocation created a run (status `succeeded`, `failed`, or
`running` when the command could not confirm that it closed the run) and
nothing otherwise, and SHALL write progress and errors to stderr as fixed
messages that never include a URL, a header, a body, a setting or a traceback.
The exit code SHALL be 0 (succeeded), 1 (failed, did not start, a broken
resumption chain, or the result could not be written), 2 (CLI-5) or 130
(Ctrl+C). The status in the result line is the last one the process confirmed.

**Source:** ingest-command · intent.md § AC14, AC15; README § Ingesting (audit round 8, AC21 PASS)

#### Scenario: Failed page
- **WHEN** a page answers `500`
- **THEN** the response is kept, the run ends `failed`, stdout is `<execution id> failed` and the exit code is 1

#### Scenario: Ctrl+C
- **WHEN** a Ctrl+C lands while a page is requested
- **THEN** the cleanup closes the run `failed` when it can, stdout is `<execution id> failed` (or `running` when the cleanup could not finish) and the exit code is 130

### Requirement: CLI-7 — `main` turns what reaches it into an exit code, without a traceback

The system SHALL make `main`, for every command and from the parsing of the
arguments to its exit, turn a Ctrl+C that reaches it into exit code 130 and any
other exception into exit code 1, without a traceback, without writing on stdout
and without running the ingest again, and SHALL let every `SystemExit` through
unchanged (the first one wins), so `--version` (0), usage errors (2) and the
command's own exit code stay as they are. The main parser and the `ingest`
subparser SHALL be one local `ArgumentParser` subclass that overrides only the
writing hook and `print_usage`, so that an `OSError` of the output stream reaches
`main`'s handler; `argparse` itself SHALL NOT be changed.

**Source:** ingest-command · intent.md § AC14, AC15 (decisions D-1, D-3 option B, D-5 option a); execution-plan.md § Ownership

#### Scenario: Ctrl+C while the arguments are parsed
- **WHEN** a `KeyboardInterrupt` is raised while `main` parses the arguments
- **THEN** the exit code is 130, stdout is empty, nothing is built or requested and no traceback is printed

### Requirement: CLI-8 — Every output is one protected, flushed attempt, and a failing stream never ends with Python's exit 120

The system SHALL write and flush every output of `main` and of the command (the
result line, every stderr line, `--version`, `--help` and the usage errors) in
one attempt, through `interfaces/output_streams.py` (standard library only), and
as the last step of `main` flush `sys.stdout` and then `sys.stderr`. A stream
that fails only when its buffered output is pushed out (a pipe whose reader has
gone, reported as `BrokenPipeError` on Linux and `OSError` on Windows, or a
closed stream) is a failure of that attempt: the exit code is 1, or 130 when a
Ctrl+C was already determined or lands, a `SystemExit` keeping its own code; the
status already confirmed stays in the one result line attempted, which is never
attempted again; and nothing in PostgreSQL changes because of it, so a run may
stay `succeeded` while the command exits 1. The failed stream SHALL be
neutralized (redirected once to the null device) so that, in the normal case,
the process never ends with Python's exit code 120 or its `Exception ignored ...
flushing` report. With working streams nothing changes.

Stated residual limitation, not a guarantee (decision D-10, option A chosen by
the human): when the neutralizing itself fails (the null device cannot be
opened, `os.dup2` raises, the stream has no usable descriptor, or the
redirected stream still fails), Python's finalization may still print that
report and replace the agreed exit code by 120. It changes nothing in PostgreSQL
and the faulted output is not attempted again.

**Source:** ingest-command · intent.md § AC14, AC15 (F-27, decisions D-6 to D-10); execution-plan.md § Public names "Protected writes and the last flush"; audit.md round 8 § Accepted limitations

#### Scenario: Closed stdout pipe
- **WHEN** the real `main` runs in a child process whose stdout pipe has lost its reader and the command ends with a result line
- **THEN** the exit code is 1 (130 if a Ctrl+C was determined), stderr shows no `Exception ignored` report, the process does not end with 120 and the run keeps the status it was closed with

### Requirement: CLI-9 — A missing stdout or stderr is disabled output, never a failure

The system SHALL treat a `sys.stdout` or `sys.stderr` that is `None` (Python
started with descriptor 1 or 2 closed, for example `>&-` or `2>&-`) as disabled
output for every command: nothing meant for it is written, neither on it nor
on the other stream, it is never neutralized or flushed, and it is never a
failure, so every exit code is the one the same invocation gives with that
stream working. In particular a usage or configuration error exits 2 with
stdout empty, `--version`, `--help` and `ingest --help` print nothing and exit
0 when stdout is missing, and a run is neither audited `unexpected-error` nor
closed `failed` because stderr is missing.

**Source:** ingest-command · intent.md § AC14, AC15 (F-31, decisions D-11 and D-12 option A); execution-plan.md § Public names "A missing stream"

#### Scenario: Missing stderr
- **WHEN** `ingest --year 2025 --buyer "SYNTHETIC BUYER S.A." --last-page 1` is run with descriptor 2 closed (`2>&-`) and `POSTGRES_DB` unset
- **THEN** the exit code is 2 and stdout is empty (no stderr text is written on stdout)

#### Scenario: Missing stdout
- **WHEN** `--version` is run with descriptor 1 closed (`>&-`)
- **THEN** the exit code is 0 and nothing is written

## Invariants

1. The version has one source of truth, `[project] version` in
   `pyproject.toml`. The CLI reads it from the installed package metadata and
   never hard-codes it; a second literal would let the two drift.
2. The CLI uses only the Python standard library until the CLI framework
   decision (D-09) is made.
3. ~~What a bare `ec-procurement-quality` (no arguments) does is not defined
   yet; it waits for the first real command.~~ Answered by `ingest-command` (F4):
   the bare command prints the usage on stderr and exits 2 (CLI-4).
4. Every output of `main` and of the command goes through the protected write
   of `interfaces/output_streams.py` (CLI-8); an unprotected write to
   `sys.stdout` or `sys.stderr` would let a closed pipe end the process with
   Python's exit code 120 again.

## Open reservations

| ID | Reservation | Severity | Source |
|---|---|---|---|
| D-10 | When the neutralizing of a failed output stream itself fails, Python's finalization may still print its `Exception ignored ... flushing` report and replace the agreed exit code by 120; nothing changes in PostgreSQL and the output is not attempted again. A stated limitation, not a guarantee (CLI-8); the README and the CHANGELOG state it. Accepted by the human on 2026-10-28 | LOW | ingest-command · audit.md round 8 § Accepted limitations; tasks.md § Carried reservations |
| F-32 | A Ctrl+C in the few unguarded bytecodes of `main` after the exit code was decided (`cli.py` after `_code_of` returns) prints a traceback and leaves with the interpreter's exit code; no data or run state, no secret. Accepted by the human on 2026-10-28 | LOW | ingest-command · audit.md round 8 § B F-32 |
| F-36, F-37, F-38 | Output-only paths with no regression test: surviving mutants of the last flush and the protected write (F-36), `cli.py` lines 51 and 58 (a hook or `print_usage` called with no file; no caller does that) (F-37), and missing-stream output paths (F-38). The behavior was verified by experiment at `108c5a0`; no data or run state depends on them. Accepted by the human on 2026-10-28 | LOW | ingest-command · audit.md round 8 § B F-36, F-37, F-38 |

## Contributing features

| Feature | Shipped | What it established |
|---|---|---|
| project-skeleton (F0) | 2026-10-08 | `--version`, usage error for unknown options, the console script and `main` contract (CLI-1 to CLI-3) |
| ingest-command (F4) | 2026-10-28 | Modified CLI-2 (the usage line gains `{ingest}`); added the `ingest` subcommand, its exit-2 errors, its result line and exit codes, the handler of `main`, the protected output with the D-10 residual limitation, and the missing-stream rule (CLI-4 to CLI-9); answered Invariant 3 and added Invariant 4 |

## Related ADRs

None yet.
