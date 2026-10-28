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

The audit round 7 rework of 2026-10-27 (plan Revision 13, finding F-31, decisions D-11
and D-12) adds, at the end of the file, the missing-stream cases: `process_no_stderr`,
`process_no_stdout`, `process_no_streams` and `process_hung_cleanup`. The section
comment there describes the launcher, the start-state record and the cleanup rule.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
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

import time

if sys.argv[1] == "hang":
    # Round 7: used only by `process_hung_cleanup`. Block forever, importing nothing.
    while True:
        time.sleep(60)

import io
import os
import socket
from pathlib import Path

# Round 7: the emulation switch. The parent names the streams to remove; before the
# project is imported they become `None`, as CPython sets them for a missing descriptor.
for name in os.environ.get("ECPQ_TEST_MISSING_STREAMS", "").split(","):
    if name in ("stdout", "stderr"):
        setattr(sys, name, None)

# The start state, for the parent to compare with the case's missing streams.
with open(
    Path.cwd() / "stream-state.txt", "w", encoding="utf-8", newline=""
) as state:
    for name in ("stdout", "stderr"):
        state.write(f"{name}={'None' if getattr(sys, name) is None else 'stream'}\n")


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
if original is not None:
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
try:
    cli.main(ARGV)
except SystemExit:
    raise
except BaseException as error:
    # With a missing stderr a traceback would be invisible: leave a record of it.
    with open(Path.cwd() / "escaped.txt", "w", encoding="utf-8") as escaped:
        escaped.write(type(error).__name__)
    raise
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


def child_environment(unset: tuple[str, ...] = ()) -> dict[str, str]:
    """The parent's environment without `PYTHONUNBUFFERED`, plus synthetic settings.

    A name in `unset` is removed last (round 7: `POSTGRES_DB` absent from the child).
    """
    environment = {
        name: value for name, value in os.environ.items() if name != "PYTHONUNBUFFERED"
    }
    environment.update(
        POSTGRES_HOST="db.invalid",
        POSTGRES_DB="synthetic_db",
        POSTGRES_USER="synthetic_user",
        POSTGRES_PASSWORD="synthetic-password-marker",
    )
    for name in unset:
        environment.pop(name, None)
    return environment


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
    process = subprocess.Popen(
        [sys.executable, str(bootstrap), case, *argv],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=tmp_path,
        env=child_environment(),
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


# === Audit round 7 rework (2026-10-27), plan Revision 13: missing streams ========
#
# Feature ingest-command (F4), outcome O10, rework of round 7 (audit finding F-31;
# decisions D-11 and D-12, option A, chosen by the human on 2026-10-27; acceptance
# criteria AC14, AC15 and AC19). A stream is *missing* when it is `None`: CPython sets
# `sys.stdout` or `sys.stderr` to `None` when Python starts without a descriptor 1 or
# 2. A missing stream is disabled output, never a failing stream: nothing is written
# for it, neither there nor on the other stream, and no code, outcome or run status
# changes because of it.
#
# Every `process_no_*` case runs in two modes that must agree:
#
# - `closed`: a launcher child closes descriptor 1, 2 or both and then starts the
#   bootstrap, so that CPython itself sets the stream to `None`;
# - `emulated`: the bootstrap is started directly and sets the stream to `None` itself.
#
# The start-state record (`stream-state.txt`) shows which streams were `None` when the
# bootstrap began, and the parent compares it with the case's missing streams, so a
# platform where CPython does not set `None` makes the test fail instead of passing
# vacuously. The bootstrap also records any exception other than `SystemExit` that
# leaves `cli.main` (`escaped.txt`): with a missing stderr a traceback is invisible.
#
# Exceptions to the harness pattern of round 6, accepted by the human on 2026-10-27
# with the requirement that both processes are cleaned up on a timeout: (1) a `closed`
# case runs two processes, bounded by the launcher's shorter timeout and, if the
# launcher itself does not end, by the cleanup on the parent's timeout; (2) the parent
# keeps all three pipes, and the pipe of a descriptor the launcher closed reads as
# empty ("nothing written in place of the missing stream"); (3) 96 joins 97 and 98 as
# a code that must never be a result (and so do the launcher's own failure codes 94 and
# 95; `process_hung_cleanup`, case (1), asserts 96 itself).
#
# Tokens (`-k`): `process_no_stderr`, `process_no_stdout`, `process_no_streams` and
# `process_hung_cleanup` (the cleanup of both processes on a timeout; it tests the
# harness, not the product, so it is green as soon as the harness exists). The
# launcher's argument `<descriptors>` is a comma-separated list: `1` and `2` name the
# descriptors it closes, `stall` (test-only, used by `process_hung_cleanup`) makes it
# block after writing the pid file instead of waiting for its child.

# The bounds of the cleanup rule. Module-level so that `process_hung_cleanup` can
# shorten them through `monkeypatch`; the relation required is that the launcher's
# timeout is strictly shorter than the parent's.
PARENT_TIMEOUT = 60
LAUNCHER_TIMEOUT = 50
REAP_TIMEOUT = 10
GONE_DEADLINE = 5

MISSING_SWITCH = "ECPQ_TEST_MISSING_STREAMS"
PID_FILE = "child.pid"
DESCRIPTOR_OF = {"stdout": "1", "stderr": "2"}
# 94 and 95 are the launcher's own failures (a code it could not relay, an exception);
# 96 is its timeout; 97 and 98 are the bootstrap's guards; 120 is Python's flush report.
NEVER_A_RESULT = (94, 95, 96, 97, 98, 120)
FORBIDDEN_WHEN_MISSING = (*FORBIDDEN_TEXT, "AttributeError")

# The launcher of the `closed` mode (written by the test into `tmp_path`). It writes
# nothing on any stream: it closes the named descriptors, starts the bootstrap without
# a shell, `creationflags` or redirection (so the bootstrap inherits the parent's
# stdin and every descriptor still open, and CPython starts it with the closed ones
# missing), writes the bootstrap's pid atomically BEFORE it waits, and then waits for
# `<timeout>` seconds. On its own timeout it kills and reaps its child and ends with 96.
LAUNCHER = r"""
import os
import subprocess
import sys
import time
import traceback

pid_file, timeout, tokens = sys.argv[1:4]
command = sys.argv[4:]
tokens = tokens.split(",")
try:
    for token in tokens:
        if token in ("1", "2"):
            os.close(int(token))
    child = subprocess.Popen(command)
    temporary = pid_file + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        handle.write(str(child.pid))
    os.replace(temporary, pid_file)
    if "stall" in tokens:
        while True:
            time.sleep(60)
    try:
        code = child.wait(timeout=float(timeout))
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait()
        os._exit(96)
    os._exit(code if 0 <= code < 256 else 94)
except BaseException:
    with open(pid_file + ".error", "w", encoding="utf-8") as handle:
        traceback.print_exc(file=handle)
    os._exit(95)
"""


@dataclass
class MissingChild(Child):
    """What one child run produced, with the records of the round 7 additions.

    `state` is the start-state record (`stream-state.txt`), `escaped` the class name of
    an exception other than `SystemExit` that left `cli.main` (`None` when none did),
    and `launcher_error` the traceback of a failure of the launcher (`None` when none).
    """

    state: str = ""
    escaped: str | None = None
    launcher_error: str | None = None


@dataclass
class Started:
    """A child (or its launcher) that was started and not yet collected."""

    process: subprocess.Popen[bytes]
    tmp_path: Path
    case: str


def start_child(
    tmp_path: Path,
    case: str,
    argv: list[str],
    *,
    missing: tuple[str, ...],
    mode: str,
    unset: tuple[str, ...] = (),
    stall: bool = False,
) -> Started:
    """Start the bootstrap for `case` with the streams in `missing` missing.

    `closed`: behind the launcher, which closes the descriptors. `emulated`: directly,
    with the switch naming the streams the bootstrap sets to `None`. In both modes the
    parent keeps its three pipes (the exception (2) to the harness pattern).
    """
    assert mode in ("closed", "emulated")
    bootstrap = tmp_path / "bootstrap.py"
    bootstrap.write_text(BOOTSTRAP, encoding="utf-8")
    environment = child_environment(unset)
    if mode == "emulated":
        environment[MISSING_SWITCH] = ",".join(missing)
        command = [sys.executable, str(bootstrap), case, *argv]
    else:
        assert LAUNCHER_TIMEOUT < PARENT_TIMEOUT
        launcher = tmp_path / "launcher.py"
        launcher.write_text(LAUNCHER, encoding="utf-8")
        tokens = [DESCRIPTOR_OF[name] for name in missing]
        if stall:
            tokens.append("stall")
        command = [
            sys.executable,
            str(launcher),
            str(tmp_path / PID_FILE),
            str(LAUNCHER_TIMEOUT),
            ",".join(tokens) or "-",
            sys.executable,
            str(bootstrap),
            case,
            *argv,
        ]
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=tmp_path,
        env=environment,
    )
    return Started(process, tmp_path, case)


def read_pid(pid_file: Path) -> int | None:
    """The pid the launcher wrote, or `None` when it never got that far."""
    try:
        return int(pid_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def kill_by_pid(pid: int) -> None:
    """End the process `pid`; one that is already gone is not an error.

    `SIGKILL` on Linux; on Windows `SIGTERM`, which `os.kill` turns into
    `TerminateProcess` (any signal other than the two console events does).
    """
    try:
        os.kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))
    except OSError:
        pass


if sys.platform == "win32":

    def process_is_alive(pid: int) -> bool:
        """Alive: `OpenProcess` succeeds and `GetExitCodeProcess` says `STILL_ACTIVE`.

        An open that fails means gone. Never `os.kill(pid, 0)` here: on Windows any
        signal other than the two console events ends the process.
        """
        import ctypes
        from ctypes import wintypes

        query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel32.OpenProcess(query_limited_information, False, pid)
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == still_active
        finally:
            kernel32.CloseHandle(handle)

else:

    def process_is_alive(pid: int) -> bool:
        """Alive: `os.kill(pid, 0)` finds it and `/proc/<pid>/stat` is not state `Z`.

        A zombie that waits for a reaper counts as gone.
        """
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        try:
            stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        except OSError:
            return False
        return stat.rsplit(")", 1)[1].split()[0] != "Z"


def wait_until_gone(pid: int) -> bool:
    """Poll until `pid` is not alive or `GONE_DEADLINE` passes (never a single check)."""
    deadline = time.monotonic() + GONE_DEADLINE
    while process_is_alive(pid):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)
    return True


def clean_up_after_timeout(started: Started) -> str:
    """The cleanup rule on the parent's own timeout; return the problems it found.

    In this order: read the pid file (absent: only the launcher is cleaned up); kill
    the child by that pid while the launcher is alive and has not reaped it, so the
    pid cannot have been reused; kill the launcher; reap it and drain its pipes with a
    bounded `communicate` (on a timeout kill the child pid again, wait for the
    launcher, and record the leak); then check, polling until `GONE_DEADLINE`, that
    the launcher is reaped and neither pid is alive (a survivor is killed once more
    and named). No other wait or sleep.
    """
    process = started.process
    problems: list[str] = []
    child_pid = read_pid(started.tmp_path / PID_FILE)
    if child_pid is not None:
        kill_by_pid(child_pid)
    process.kill()
    try:
        process.communicate(timeout=REAP_TIMEOUT)
    except subprocess.TimeoutExpired:
        problems.append("the launcher's pipes were still held after the kill")
        if child_pid is not None:
            kill_by_pid(child_pid)
        try:
            process.wait(timeout=REAP_TIMEOUT)
        except subprocess.TimeoutExpired:
            problems.append("the launcher was not reaped")
    if process.returncode is None:
        problems.append("the launcher has no return code")
    if not wait_until_gone(process.pid):
        kill_by_pid(process.pid)
        problems.append(f"the launcher (pid {process.pid}) is still alive")
    if child_pid is not None and not wait_until_gone(child_pid):
        kill_by_pid(child_pid)
        problems.append(f"the child (pid {child_pid}) is still alive")
    return "; ".join(problems)


def collect_child(started: Started) -> MissingChild:
    """The one `communicate`; on the parent's timeout the cleanup runs, then the test fails."""
    process = started.process
    tmp_path = started.tmp_path
    try:
        out, err = process.communicate(input=b"g", timeout=PARENT_TIMEOUT)
    except subprocess.TimeoutExpired:
        problems = clean_up_after_timeout(started)
        outcome = (
            f"cleanup problems: {problems}"
            if problems
            else "both processes were cleaned up"
        )
        pytest.fail(
            f"the child ({started.case}) did not end within {PARENT_TIMEOUT} seconds; "
            + outcome
        )

    def record(name: str) -> str | None:
        path = tmp_path / name
        return path.read_bytes().decode("utf-8") if path.exists() else None

    return MissingChild(
        process.returncode,
        _text(out),
        _text(err),
        record("stdout-record.txt") or "",
        state=record("stream-state.txt") or "",
        escaped=record("escaped.txt"),
        launcher_error=record(PID_FILE + ".error"),
    )


def run_missing_child(
    tmp_path: Path,
    case: str,
    argv: list[str],
    *,
    missing: tuple[str, ...],
    mode: str,
    unset: tuple[str, ...] = (),
) -> MissingChild:
    """Run the bootstrap with the streams in `missing` missing, in the mode given."""
    started = start_child(tmp_path, case, argv, missing=missing, mode=mode, unset=unset)
    return collect_child(started)


def assert_ended_without(
    child: MissingChild, code: int, missing: tuple[str, ...]
) -> None:
    """The exact code and the records: the start state, no escaped exception, no reports.

    The code is never one of `NEVER_A_RESULT`; no stream the parent reads holds
    Python's own reports or `AttributeError`; the pipe of a missing stream is empty
    (nothing was written in place of it).
    """
    expected_state = "".join(
        f"{name}={'None' if name in missing else 'stream'}\n"
        for name in ("stdout", "stderr")
    )
    assert child.launcher_error is None, child
    assert child.state == expected_state, child
    assert child.escaped is None, child
    assert child.code == code, child
    assert child.code not in NEVER_A_RESULT
    for stream in (child.out, child.err):
        assert stream is not None, child
        for text in FORBIDDEN_WHEN_MISSING:
            assert text not in stream, child
    if "stdout" in missing:
        assert child.out == "", child
    if "stderr" in missing:
        assert child.err == "", child


MODES = [
    pytest.param("closed", id="closed-descriptor"),
    pytest.param("emulated", id="emulated-none"),
]


# === process_no_stderr (AC14, AC15, AC19; F-31, D-11, real process) =============


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize(
    ("case", "code", "line"),
    [
        pytest.param("succeeded", 0, f"{A} succeeded\n", id="succeeded"),
        pytest.param("failed", 1, f"{A} failed\n", id="failed"),
        pytest.param("ended-130", 130, f"{A} failed\n", id="ended-by-ctrl-c"),
        pytest.param("ctrl-c-after-start", 130, f"{A} running\n", id="ctrl-c-escapes"),
    ],
)
def test_process_no_stderr_an_ingest_keeps_its_code_and_one_result_line(
    tmp_path: Path, mode: str, case: str, code: int, line: str
) -> None:
    """Stderr is missing: the codes 0, 1, 130 and 130, and the result line once.

    Stdout (read by the parent) is exactly the one line; no stderr text reaches it and
    nothing fails because the progress lines have nowhere to go.
    """
    child = run_missing_child(tmp_path, case, INGEST, missing=("stderr",), mode=mode)

    assert_ended_without(child, code, ("stderr",))
    assert child.out == line, child
    assert child.record == line


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize(
    "argv",
    [
        pytest.param(PARSE_ERROR, id="parse-error"),
        pytest.param([], id="bare-command"),
    ],
)
def test_process_no_stderr_a_parse_error_and_the_bare_command_exit_2_with_stdout_empty(
    tmp_path: Path, mode: str, argv: list[str]
) -> None:
    """Stderr is missing: the usage is not sent to stdout; the code is 2."""
    child = run_missing_child(tmp_path, "plain", argv, missing=("stderr",), mode=mode)

    assert_ended_without(child, 2, ("stderr",))
    assert child.out == "", child
    assert child.record == ""


@pytest.mark.parametrize("mode", MODES)
def test_process_no_stderr_an_unset_variable_exits_2_with_stdout_empty(
    tmp_path: Path, mode: str
) -> None:
    """Stderr is missing and `POSTGRES_DB` is absent from the child: 2, stdout empty."""
    child = run_missing_child(
        tmp_path,
        "plain",
        INGEST,
        missing=("stderr",),
        mode=mode,
        unset=("POSTGRES_DB",),
    )

    assert_ended_without(child, 2, ("stderr",))
    assert child.out == "", child
    assert child.record == ""


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize(
    "argv",
    [
        pytest.param(["--version"], id="version"),
        pytest.param(["--help"], id="help"),
    ],
)
def test_process_no_stderr_version_and_help_keep_their_text_on_stdout(
    tmp_path: Path, mode: str, argv: list[str]
) -> None:
    """Stderr is missing: `--version` -> 0 with its text, `--help` -> 0 with `usage:`."""
    child = run_missing_child(tmp_path, "plain", argv, missing=("stderr",), mode=mode)

    assert_ended_without(child, 0, ("stderr",))
    assert child.out is not None
    if argv == ["--version"]:
        assert child.out == version_text(), child
    else:
        assert child.out.startswith("usage:"), child


# === process_no_stdout (AC14, AC15, AC19; F-31, D-12, real process) =============


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize(
    ("case", "code"),
    [
        pytest.param("succeeded", 0, id="succeeded"),
        pytest.param("ended-130", 130, id="ended-by-ctrl-c"),
    ],
)
def test_process_no_stdout_an_ingest_keeps_its_code_and_drops_the_result_line(
    tmp_path: Path, mode: str, case: str, code: int
) -> None:
    """Stdout is missing: the result line is not written, anywhere.

    Stderr holds `run <A> started` and the outcome message, and no `<A> ` line; the
    code is the one the run determined.
    """
    child = run_missing_child(tmp_path, case, INGEST, missing=("stdout",), mode=mode)

    assert_ended_without(child, code, ("stdout",))
    assert child.err is not None
    assert child.err.splitlines() == [f"run {A} started", MESSAGE], child
    assert child.record == ""


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize(
    "argv",
    [
        pytest.param(["--version"], id="version"),
        pytest.param(["--help"], id="help"),
    ],
)
def test_process_no_stdout_version_and_help_write_nothing_and_exit_0(
    tmp_path: Path, mode: str, argv: list[str]
) -> None:
    """Stdout is missing: `--version` and `--help` -> 0, stderr empty (no substitute)."""
    child = run_missing_child(tmp_path, "plain", argv, missing=("stdout",), mode=mode)

    assert_ended_without(child, 0, ("stdout",))
    assert child.err == "", child
    assert child.record == ""


@pytest.mark.parametrize("mode", MODES)
def test_process_no_stdout_a_parse_error_exits_2_with_its_text_on_stderr(
    tmp_path: Path, mode: str
) -> None:
    """Stdout is missing: `ingest --last-page 2` -> 2 with `usage:` and `error:` on stderr."""
    child = run_missing_child(
        tmp_path, "plain", PARSE_ERROR, missing=("stdout",), mode=mode
    )

    assert_ended_without(child, 2, ("stdout",))
    assert child.err is not None
    assert "usage:" in child.err, child
    assert "error:" in child.err, child
    assert child.record == ""


@pytest.mark.parametrize("mode", MODES)
def test_process_no_stdout_an_unset_variable_exits_2_with_its_message_on_stderr(
    tmp_path: Path, mode: str
) -> None:
    """Stdout is missing and `POSTGRES_DB` is absent: 2, `error: POSTGRES_DB is not set`."""
    child = run_missing_child(
        tmp_path,
        "plain",
        INGEST,
        missing=("stdout",),
        mode=mode,
        unset=("POSTGRES_DB",),
    )

    assert_ended_without(child, 2, ("stdout",))
    assert child.err is not None
    assert "error: POSTGRES_DB is not set" in child.err.splitlines(), child
    assert child.record == ""


# === process_no_streams (AC14, AC15, AC19; F-31, D-11 and D-12, real process) ===


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize(
    ("case", "argv", "code"),
    [
        pytest.param("succeeded", INGEST, 0, id="succeeded"),
        pytest.param("ended-130", INGEST, 130, id="ended-by-ctrl-c"),
        pytest.param("plain", PARSE_ERROR, 2, id="parse-error"),
        pytest.param("plain", ["--version"], 0, id="version"),
    ],
)
def test_process_no_streams_the_codes_hold_and_nothing_is_written(
    tmp_path: Path, mode: str, case: str, argv: list[str], code: int
) -> None:
    """Both streams are missing: the run's code, 2 for a parse error, 0 for `--version`.

    Both parent pipes are empty and nothing is recorded as attempted on stdout.
    """
    child = run_missing_child(
        tmp_path, case, argv, missing=("stdout", "stderr"), mode=mode
    )

    assert_ended_without(child, code, ("stdout", "stderr"))
    assert child.record == ""


@pytest.mark.parametrize("mode", MODES)
def test_process_no_streams_an_unset_variable_exits_2_and_writes_nothing(
    tmp_path: Path, mode: str
) -> None:
    """Both streams are missing and `POSTGRES_DB` is absent: 2, nothing written."""
    child = run_missing_child(
        tmp_path,
        "plain",
        INGEST,
        missing=("stdout", "stderr"),
        mode=mode,
        unset=("POSTGRES_DB",),
    )

    assert_ended_without(child, 2, ("stdout", "stderr"))
    assert child.record == ""


# === process_hung_cleanup (AC19; F-31, the cleanup of both processes) ============
#
# The requirement the human added on 2026-10-27 when accepting the launcher: a child
# that never ends leaves no live or unreaped process. These tests exercise the harness
# and the bootstrap's `hang` case, not the product, so they are green as soon as the
# harness exists; their value is shown on scratch mutants of the harness (without the
# parent's kill of the child pid, with the launcher's timeout not shorter than the
# parent's, without the launcher's own kill and wait). The timeouts are shortened
# through `monkeypatch`; nothing sleeps to synchronize (liveness is polled).


def shorten_timeouts(
    monkeypatch: pytest.MonkeyPatch, *, parent: int, launcher: int
) -> None:
    module = sys.modules[__name__]
    monkeypatch.setattr(module, "PARENT_TIMEOUT", parent)
    monkeypatch.setattr(module, "LAUNCHER_TIMEOUT", launcher)


def test_process_hung_cleanup_the_launcher_kills_and_reaps_a_child_that_never_ends(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(1) The launcher's 2 s against the parent's 10 s: the launcher ends with 96.

    The parent's `communicate` returns (no timeout of the parent) with the code 96,
    asserted here and not through `assert_ended_without`; the child's pid, in the pid
    file, is not alive within the liveness deadline.
    """
    shorten_timeouts(monkeypatch, parent=10, launcher=2)
    # Positive control: the liveness helper sees a process that is alive (this one).
    assert process_is_alive(os.getpid())

    child = run_missing_child(tmp_path, "hang", [], missing=("stderr",), mode="closed")

    assert child.launcher_error is None, child
    assert child.code == 96, child
    child_pid = read_pid(tmp_path / PID_FILE)
    assert child_pid is not None
    assert wait_until_gone(child_pid), f"the child (pid {child_pid}) is still alive"


def test_process_hung_cleanup_the_parent_kills_both_processes_when_the_launcher_stalls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(2) A stalled launcher, the parent's 4 s: the harness's timeout path runs.

    It fails the test with a message that names the case and says both processes were
    cleaned up. Afterwards the launcher's return code is set, and the launcher and the
    child of the pid file are not alive (checked again here with the same helper).
    """
    shorten_timeouts(monkeypatch, parent=4, launcher=2)
    started = start_child(
        tmp_path, "hang", [], missing=("stderr",), mode="closed", stall=True
    )

    with pytest.raises(pytest.fail.Exception) as failure:
        collect_child(started)

    message = str(failure.value)
    child_pid = read_pid(tmp_path / PID_FILE)
    assert "hang" in message
    assert "both processes were cleaned up" in message
    assert started.process.returncode is not None
    assert not process_is_alive(started.process.pid)
    assert child_pid is not None
    assert not process_is_alive(child_pid)
