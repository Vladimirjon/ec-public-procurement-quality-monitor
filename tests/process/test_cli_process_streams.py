"""Feature ingest-command (F4), outcome O10, rework of round 6: the process tier.

Plan Revision 12, § Validation, "Process tier" (audit finding F-27, option (b), and
decisions D-6 to D-9, option A, chosen by the human on 2026-10-22; acceptance
criteria AC14, AC15, AC19 and AC21). Each test starts the real `cli.main` in a child
Python process and breaks the pipe of its stdout, of its stderr, or of both, to show
what a unit test cannot: in a real process stdout to a pipe is block-buffered, so a
`print` only fills a buffer and a closed pipe shows only when Python flushes at exit
(`Exception ignored ... flushing sys.stdout`, exit code 120). The command and `main`
must end with the planned code (1, 130, or the `SystemExit` code), never with 120, and
never with Python's report or a traceback.

The child runs a bootstrap script that the test writes into `tmp_path`. It stubs
`ingest_command.run_ingest` and `cli.default_wiring`, so it opens no socket, touches no
database and no real `data/raw/` (a socket guard ends it with 97 and the repository
factory with 98: neither code may ever be seen). Its stdout is a recording stream over
descriptor 1 that appends each text it is handed to `stdout-record.txt`, so the parent
can check the single attempt and the status of a line that the closed pipe never
delivered.

The synchronization is the pattern of the plan, and nothing sleeps: the child blocks
reading one go byte from stdin; right after `Popen` the parent closes its read end of
each pipe the case breaks and sets that attribute to `None`; one
`communicate(input=b"g", timeout=60)` then sends the byte and collects the child. On a
timeout the child is killed and collected before the test fails.

These are the normal cases, where the null device can be opened and copied onto the
failed descriptor. The failure of that neutralizing is the unit row `neutralize_fault`
and the residual limitation of decision D-10, not covered here. The same tests run on
Windows and on Linux; a pipe whose reader has gone raises `OSError` (Windows) or
`BrokenPipeError` (Linux), the only platform-dependent assertion.

Tokens (`-k`): `process_closed_stdout`, `process_closed_stderr`, `process_closed_both`,
`process_working_pipes` and `process_exit_precedence`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from importlib.metadata import version as installed_version
from pathlib import Path

import pytest

A = "ingest-20261014t150000z-0a1b2c3d"
MESSAGE = "synthetic outcome message"
INGEST = [
    "ingest",
    "--year",
    "2025",
    "--buyer",
    "SYNTHETIC BUYER S.A.",
    "--last-page",
    "2",
]
PARSE_ERROR = ["ingest", "--last-page", "2"]
# A pipe whose reader has gone: `OSError` (EINVAL) on Windows, `BrokenPipeError` on Linux.
FAILURE_CLASS = "OSError" if sys.platform.startswith("win") else "BrokenPipeError"
UNEXPECTED = f"unexpected error: {FAILURE_CLASS}"
FORBIDDEN_TEXT = ("Exception ignored", "flushing sys.", "Traceback")

# The bootstrap of the child. It writes nothing before the go byte, installs the
# socket guard, records what is handed to stdout, stubs the use case and the wiring of
# the case named in `sys.argv[1]`, and then calls `cli.main` and lets the process end
# through Python's normal exit, so that the exit-time flush is exercised.
BOOTSTRAP = r'''
import sys

sys.stdin.buffer.read(1)

import io
import os
import socket
from pathlib import Path


def end_at_once(*args, **kwargs):
    os._exit(97)


socket.socket.connect = end_at_once
socket.socket.connect_ex = end_at_once
socket.create_connection = end_at_once
socket.getaddrinfo = end_at_once

from ec_procurement_quality.application.ingest_use_case import IngestEnd, IngestOutcome
from ec_procurement_quality.domain.ingestion_audit import RunStatus
from ec_procurement_quality.infrastructure.system_clock import (
    RandomExecutionIdSource,
    SystemClock,
)
from ec_procurement_quality.interfaces import cli, ingest_command

RECORD = Path.cwd() / "stdout-record.txt"


class RecordingStdout(io.TextIOWrapper):
    """Stdout as Python builds it for a pipe, recording every text it is handed."""

    def write(self, text):
        with open(RECORD, "a", encoding="utf-8", newline="") as record:
            record.write(text)
        return super().write(text)


original = sys.stdout
sys.stdout = RecordingStdout(
    io.BufferedWriter(io.FileIO(1, "w", closefd=False)),
    encoding=original.encoding,
    errors=original.errors,
    line_buffering=False,
    write_through=False,
)

A = "ingest-20261014t150000z-0a1b2c3d"
MESSAGE = "synthetic outcome message"
CASE = sys.argv[1]
ARGV = sys.argv[2:]
OUTCOMES = {
    "succeeded": (IngestEnd.SUCCEEDED, RunStatus.SUCCEEDED),
    "succeeded-unannounced": (IngestEnd.SUCCEEDED, RunStatus.SUCCEEDED),
    "failed": (IngestEnd.RUN_FAILED, RunStatus.FAILED),
    "failed-running": (IngestEnd.RUN_FAILED, RunStatus.RUNNING),
    "ended-130": (IngestEnd.INTERRUPTED, RunStatus.FAILED),
    "source-close-system-exit": (IngestEnd.SUCCEEDED, RunStatus.SUCCEEDED),
}


class DummySource:
    def search_page(self, *, year, buyer, page):
        os._exit(97)

    def fetch_record(self, ocid):
        os._exit(97)

    def close(self):
        if CASE == "source-close-system-exit":
            raise SystemExit(3)


def stub_run_ingest(
    request, *, source, store, open_repository, clock, execution_ids, reporter
):
    if CASE != "succeeded-unannounced":
        reporter.run_started(A)
    if CASE == "ctrl-c-after-start":
        raise KeyboardInterrupt
    if CASE == "system-exit-after-start":
        raise SystemExit(3)
    end, status = OUTCOMES[CASE]
    return IngestOutcome(end=end, execution_id=A, run_status=status, message=MESSAGE)


def stub_wiring():
    if CASE == "wiring-ctrl-c":
        raise KeyboardInterrupt
    return ingest_command.IngestWiring(
        base_url="https://source.invalid/PLATAFORMA",
        make_source=lambda now: DummySource(),
        make_store=lambda root: object(),
        make_repository=lambda settings: os._exit(98),
        migrate=lambda settings, directory: (),
        clock=SystemClock(),
        execution_ids=RandomExecutionIdSource(),
    )


ingest_command.run_ingest = stub_run_ingest
cli.default_wiring = stub_wiring
cli.main(ARGV)
'''


@dataclass
class Child:
    """What one child run produced.

    `out` and `err` are the text the parent read, or `None` for a pipe it closed.
    `record` is what the child handed to its stdout, in order (`stdout-record.txt`).
    """

    code: int
    out: str | None
    err: str | None
    record: str


def _text(data: bytes | None) -> str | None:
    return None if data is None else data.decode("utf-8").replace("\r\n", "\n")


def run_child(
    tmp_path: Path, case: str, argv: list[str], *, closed: tuple[str, ...] = ()
) -> Child:
    """Run the bootstrap in a child process; the parent closes the pipes in `closed`.

    The pattern of the plan: the child blocks on its first stdin byte; the parent closes
    its read end of each broken pipe and sets that attribute to `None`; one
    `communicate(input=b"g", timeout=60)`; a child that does not end is killed and
    collected before the test fails.
    """
    bootstrap = tmp_path / "bootstrap.py"
    bootstrap.write_text(BOOTSTRAP, encoding="utf-8")
    environment = {
        name: value for name, value in os.environ.items() if name != "PYTHONUNBUFFERED"
    }
    environment.update(
        POSTGRES_HOST="db.invalid",
        POSTGRES_DB="synthetic_db",
        POSTGRES_USER="synthetic_user",
        POSTGRES_PASSWORD="synthetic-password-marker",
    )
    process = subprocess.Popen(
        [sys.executable, str(bootstrap), case, *argv],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=tmp_path,
        env=environment,
    )
    if "stdout" in closed:
        assert process.stdout is not None
        process.stdout.close()
        process.stdout = None
    if "stderr" in closed:
        assert process.stderr is not None
        process.stderr.close()
        process.stderr = None
    try:
        out, err = process.communicate(input=b"g", timeout=60)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        pytest.fail(f"the child ({case}) did not end within 60 seconds")
    record_file = tmp_path / "stdout-record.txt"
    record = record_file.read_bytes().decode("utf-8") if record_file.exists() else ""
    return Child(process.returncode, _text(out), _text(err), record)


def assert_ended(child: Child, code: int) -> None:
    """The exact code (never 120, 97 or 98), and none of Python's own reports."""
    assert child.code == code, child
    assert child.code not in (120, 97, 98)
    for stream in (child.out, child.err):
        if stream is not None:
            for text in FORBIDDEN_TEXT:
                assert text not in stream, child


def version_text() -> str:
    return f"ec-procurement-quality {installed_version('ec-procurement-quality')}\n"


# === process_closed_stdout (AC14, AC15, AC19, AC21; F-27, real process) ========


@pytest.mark.parametrize(
    ("case", "code", "status"),
    [
        pytest.param("succeeded", 1, "succeeded", id="succeeded"),
        pytest.param("failed", 1, "failed", id="failed"),
        pytest.param("failed-running", 1, "running", id="failed-running"),
        pytest.param("ended-130", 130, "failed", id="ended-by-ctrl-c"),
    ],
)
def test_process_closed_stdout_the_result_line_fails_with_the_planned_code_and_one_attempt(
    tmp_path: Path, case: str, code: int, status: str
) -> None:
    """(1) The reader of stdout has gone before the child writes.

    The result line `<A> <status>` was attempted once, with the status the stub
    returned. The code is 1 (130 for the run ended by Ctrl+C), never 120. Stderr holds
    `run <A> started` and the outcome message, and at most one `unexpected error`
    line with the platform's class.
    """
    child = run_child(tmp_path, case, INGEST, closed=("stdout",))

    assert_ended(child, code)
    assert child.err is not None
    lines = child.err.splitlines()
    others = [line for line in lines if not line.startswith("unexpected error")]
    assert others == [f"run {A} started", MESSAGE], child
    assert [line for line in lines if line not in others] in ([], [UNEXPECTED]), child
    assert child.record == f"{A} {status}\n"


def test_process_closed_stdout_version_fails_with_code_1_and_one_attempt(
    tmp_path: Path,
) -> None:
    """(2) `--version`: 1, stderr exactly one `unexpected error: <cls>`, text recorded once."""
    child = run_child(tmp_path, "plain", ["--version"], closed=("stdout",))

    assert_ended(child, 1)
    assert child.err == f"{UNEXPECTED}\n", child
    assert child.record == version_text()


@pytest.mark.parametrize(
    "argv",
    [
        pytest.param(["--help"], id="help"),
        pytest.param(["ingest", "--help"], id="ingest-help"),
    ],
)
def test_process_closed_stdout_help_fails_with_code_1_and_one_attempt(
    tmp_path: Path, argv: list[str]
) -> None:
    """(3) `--help` and `ingest --help`: 1, the same stderr, the help text recorded once."""
    child = run_child(tmp_path, "plain", argv, closed=("stdout",))

    assert_ended(child, 1)
    assert child.err == f"{UNEXPECTED}\n", child
    assert child.record.startswith("usage:")
    assert child.record.count("usage:") == 1


# === process_closed_stderr (AC14, AC15, AC19, AC21; F-27, real process) ========


@pytest.mark.parametrize(
    "argv",
    [
        pytest.param(PARSE_ERROR, id="parse-error"),
        pytest.param([], id="bare-command"),
    ],
)
def test_process_closed_stderr_a_parser_message_fails_with_code_1_and_empty_stdout(
    tmp_path: Path, argv: list[str]
) -> None:
    """(4) The reader of stderr has gone: a parse error and the bare command give 1.

    The child writes nothing on stdout; the code is 1, never 120.
    """
    child = run_child(tmp_path, "plain", argv, closed=("stderr",))

    assert_ended(child, 1)
    assert child.out == "", child
    assert child.record == ""


def test_process_closed_stderr_the_final_message_fails_and_the_result_line_goes_out(
    tmp_path: Path,
) -> None:
    """(4) The stub returns `SUCCEEDED` without announcing the run.

    The final message cannot be written (stderr is closed), the result line still is:
    stdout is exactly `<A> succeeded` and the code is 1.
    """
    child = run_child(tmp_path, "succeeded-unannounced", INGEST, closed=("stderr",))

    assert_ended(child, 1)
    assert child.out == f"{A} succeeded\n", child
    assert child.record == f"{A} succeeded\n"


# === process_closed_both (AC14, AC15, AC19, AC21; F-27, real process) ==========


@pytest.mark.parametrize(
    ("case", "argv", "record"),
    [
        pytest.param("plain", ["--version"], version_text(), id="version"),
        pytest.param("plain", PARSE_ERROR, "", id="parse-error"),
        pytest.param(
            "succeeded-unannounced", INGEST, f"{A} succeeded\n", id="unannounced-run"
        ),
        pytest.param("succeeded", INGEST, f"{A} running\n", id="announced-run"),
    ],
)
def test_process_closed_both_pipes_end_with_code_1_and_record_what_was_attempted_once(
    tmp_path: Path, case: str, argv: list[str], record: str
) -> None:
    """(5) Both readers have gone: each case gives 1, never 120.

    The record holds what was attempted on stdout, once. An announced run cannot write
    its `run <A> started` line (stderr is closed): the write's exception escapes the
    stub, so the command writes `<A> running`, as it does for any escaping exception.
    """
    child = run_child(tmp_path, case, argv, closed=("stdout", "stderr"))

    assert_ended(child, 1)
    assert child.record == record


# === process_working_pipes (AC14, AC15, AC19, AC21; F-27, real process) ========


@pytest.mark.parametrize(
    ("case", "code", "line"),
    [
        pytest.param("succeeded", 0, f"{A} succeeded\n", id="succeeded"),
        pytest.param("failed", 1, f"{A} failed\n", id="failed"),
        pytest.param("ended-130", 130, f"{A} failed\n", id="ended-by-ctrl-c"),
    ],
)
def test_process_working_pipes_the_stub_outcomes_keep_their_codes_and_lines(
    tmp_path: Path, case: str, code: int, line: str
) -> None:
    """(6) Nothing is closed: the codes 0, 1 and 130, the result line and the stderr lines."""
    child = run_child(tmp_path, case, INGEST)

    assert_ended(child, code)
    assert child.out == line, child
    assert child.err is not None
    assert child.err.splitlines() == [f"run {A} started", MESSAGE], child
    assert child.record == line


def test_process_working_pipes_version_is_exit_0_with_its_text_on_stdout(
    tmp_path: Path,
) -> None:
    """(6) `--version` -> 0, stdout exactly `ec-procurement-quality <version>`."""
    child = run_child(tmp_path, "plain", ["--version"])

    assert_ended(child, 0)
    assert child.out == version_text(), child
    assert child.err == "", child


@pytest.mark.parametrize(
    "argv",
    [
        pytest.param(["--help"], id="help"),
        pytest.param(["ingest", "--help"], id="ingest-help"),
    ],
)
def test_process_working_pipes_help_is_exit_0_with_the_help_text_on_stdout(
    tmp_path: Path, argv: list[str]
) -> None:
    """(6) `--help` and `ingest --help` -> 0, stdout starts with `usage:`."""
    child = run_child(tmp_path, "plain", argv)

    assert_ended(child, 0)
    assert child.out is not None
    assert child.out.startswith("usage:"), child
    assert child.err == "", child


@pytest.mark.parametrize(
    ("argv", "words"),
    [
        pytest.param(PARSE_ERROR, ("usage:", "error:"), id="parse-error"),
        pytest.param([], ("usage:",), id="bare-command"),
    ],
)
def test_process_working_pipes_a_parse_error_and_the_bare_command_exit_2(
    tmp_path: Path, argv: list[str], words: tuple[str, ...]
) -> None:
    """(6) `ingest --last-page 2` -> 2 with `usage:` and `error:` on stderr; bare -> 2."""
    child = run_child(tmp_path, "plain", argv)

    assert_ended(child, 2)
    assert child.out == "", child
    assert child.err is not None
    for word in words:
        assert word in child.err, child


# === process_exit_precedence (AC7, AC14, AC15; F-27, D-1, real process) ========


def test_process_exit_precedence_a_ctrl_c_after_the_run_started_exits_130(
    tmp_path: Path,
) -> None:
    """(7a) Stdout closed; the stub raises Ctrl+C after `run_started`.

    130, stderr says `interrupted`, and the record holds `<A> running` once.
    """
    child = run_child(tmp_path, "ctrl-c-after-start", INGEST, closed=("stdout",))

    assert_ended(child, 130)
    assert child.err is not None
    assert "interrupted" in child.err.splitlines(), child
    assert child.record == f"{A} running\n"


def test_process_exit_precedence_a_system_exit_from_the_source_close_keeps_its_code(
    tmp_path: Path,
) -> None:
    """(7b) Stdout closed; the stub returns `SUCCEEDED` and the source's `close` exits 3.

    The `SystemExit` code 3 wins over the failed result line, which was attempted once.
    """
    child = run_child(tmp_path, "source-close-system-exit", INGEST, closed=("stdout",))

    assert_ended(child, 3)
    assert child.record == f"{A} succeeded\n"


def test_process_exit_precedence_a_system_exit_from_the_use_case_keeps_its_code(
    tmp_path: Path,
) -> None:
    """(7c) Stdout closed; the stub raises `SystemExit(3)` after `run_started` -> 3.

    No `<A> running` is written for it: the record is empty.
    """
    child = run_child(tmp_path, "system-exit-after-start", INGEST, closed=("stdout",))

    assert_ended(child, 3)
    assert child.record == ""


def test_process_exit_precedence_a_ctrl_c_while_the_wiring_is_built_exits_130(
    tmp_path: Path,
) -> None:
    """(7d) Both readers have gone; the wiring stub raises Ctrl+C -> 130, not 120."""
    child = run_child(tmp_path, "wiring-ctrl-c", INGEST, closed=("stdout", "stderr"))

    assert_ended(child, 130)
