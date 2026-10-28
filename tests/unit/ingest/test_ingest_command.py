"""Feature ingest-command (F4), outcome O6b: the unit tests of `run_ingest_command`.

The command runs with an injected `IngestWiring` made of the doubles of
`conftest.py` (`lab`): no database, network or disk. Two entries are used. The
command itself is called with a parsed `Namespace` and in-memory streams, and `main`
is called with `default_wiring` replaced through `monkeypatch`; the cases of
AC14 run through both. Nothing here reads `.env`: the environment is a mapping
the test builds, and `main` sees only the variables the test sets.

Acceptance criteria covered (intent AC14, AC15, AC16, AC18, AC25 and the exit and
stdout parts of AC7 and decisions P-1, P-2 and P-5), by `-k` token:

- `usage` (AC14): invalid arguments exit 2 before anything is built;
- `environment` (AC14, AC25): missing or invalid variables exit 2, the defaults of
  `POSTGRES_HOST` and `POSTGRES_PORT`, a `.env` is never read, the migrations
  directory;
- `paths` (AC25): the store root and the migrations directory are absolute and
  resolved once at the start;
- `exit_code` (AC7, AC8, AC9, AC16, AC18, decision P-1, P-2): the table 0, 1, 2 and
  130, the order of an invocation, the source closed once;
- `output` (AC15, decisions P-2, P-5): one result line on stdout, a safe stderr, no
  traceback, no chain, no marker;
- `logger` (AC15, R-7): `httpcore` stays above `DEBUG` and no handler is added.

The audit round 1 of 2026-10-18 added, at the end of the file (plan Revision 6):

- `source_configuration` and `order_of_invocation` (AC14, AC16, F-03): the source
  is built before the migrations, and a malformed proxy or certificate setting
  exits 2;
- `exit_code_cleanup_read_back` (AC7, F-02), `exit_code_interrupt_after_finish`
  (AC7, AC11, F-05), `output_escaping_exception` (AC15, F-04), `output_progress`
  (AC6 c, AC15, F-07) and `chain_unreadable_record_message` (AC24, F-06).

Six older tests (`migrations` error, real runner, interrupt in the migrations, the
migration failures, and the two `order_of_invocation` ones) were migrated to the
new order: `make_source` once before `migrate`, the source closed once.

The audit round 2 of 2026-10-18 added, at the end of the file (plan Revision 7):

- `output_database_error` (AC7, AC15, F-13): the lines of the K cleanup reach stderr;
- `pre_run_database_error_exit_code` (AC9, AC10, AC15, AC24, F-14, F-15): a database
  operation refused or lost before the run exists is exit 1 (never 2), with a line
  and a final message that name the identity;
- `exit_code_repository_open_error` (AC15, F-16 a): guards, they pass at `91bd69d`;
- `single_result_line` (AC15, F-16 b): a Ctrl+C while the source closes adds no
  second result line.

The audit round 3 of 2026-10-18 added, at the end of the file (plan Revision 8):

- `exit_code_reconnect_exclusion_interrupt` and `exit_code_reconnect_open_interrupt`
  (AC7, AC8 c, AC15, F-18, F-19): an interrupt or an exception while a lost
  connection is recovered prints `<A> running` (nothing while `start_run` is the lost
  operation), exits 130 or 1, and names the operation that raised on one stderr line;
- `exit_code_start_run_unconfirmed` (AC8, AC15, F-20): a lost `start_run` whose
  recovery fails prints `<id> running`, exit 1, and no `run <id> started` line.

The audit round 5 rework of 2026-10-20 added, at the end of the file (plan
Revisions 9 and 10): `exit_code_reconnect_close_interrupt` (F-21),
`exit_code_final_close_error` and `exit_code_final_close_interrupt` (F-22),
`exit_code_start_run_second_loss`, `exit_code_unexpected_cleanup_interrupt`,
`exit_code_recovery_double_fault` and `exit_code_refusal_not_retried` (sweep A2), and
`result_line_stream_fault` and `handler_stream_fault` (sweep N-7: a stream that fails
while the command writes its result, through the `RaisingStream` double).

The audit round 6 rework of 2026-10-23 added, at the end of the file (outcome O10,
plan Revision 12; the section comment there lists the tokens): `flush_stream_fault`
(AC14, AC15, F-27: every output is flushed in its one attempt), `neutralize_fault`
(AC14, AC15, F-27, decision D-10: the neutralizing of a failed stream fails),
`main_handler_line_fault` and `exit_code_cleanup_system_exit` (AC7, AC14, AC15, F-28),
and the rename of two tests without `usage` (AC14, F-29).

The audit round 7 rework of 2026-10-27 added, at the end of the file (outcome O10,
plan Revision 13; the section comment there lists the tokens): `absent_stderr_command`,
`absent_stderr_main`, `absent_stdout_command`, `absent_stdout_main`,
`absent_streams_main` and `absent_stream_helpers` (AC14, AC15, F-31, decisions D-11
and D-12: a missing stream, that is `None`, is disabled output).

Data is synthetic: the source is `https://source.invalid/PLATAFORMA`, the buyer
`SYNTHETIC BUYER S.A.`, the year 2025, and the markers `synthetic-password-marker`,
`synthetic-body-marker` and `synthetic-header-marker`.
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import re
import sys
import typing
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from importlib.metadata import version as installed_version
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import httpx
import pytest

from ec_procurement_quality.application.ingest_ports import (
    ClosableIngestionRepository,
    IngestReporter,
)
from ec_procurement_quality.application.ingest_use_case import IngestOutcome
from ec_procurement_quality.application.procurement_source import (
    ProcurementSource,
    RecordResponse,
    SearchPage,
)
from ec_procurement_quality.application.raw_evidence_store import RawEvidenceStore
from ec_procurement_quality.domain.ingestion_audit import RunStatus, same_json
from ec_procurement_quality.domain.persistence_errors import (
    MigrationError,
    MigrationLockError,
    PersistenceConnectionError,
    PersistenceError,
    PersistenceIntegrityError,
    PersistenceNotFoundError,
)
from ec_procurement_quality.domain.raw_evidence import (
    EvidenceIntegrityError,
    EvidenceNotFoundError,
)
from ec_procurement_quality.infrastructure.postgres_migrations import apply_migrations
from ec_procurement_quality.infrastructure.postgres_settings import PostgresSettings
from ec_procurement_quality.infrastructure.sercop_source import SercopSource
from ec_procurement_quality.interfaces import cli, ingest_command, output_streams
from ec_procurement_quality.interfaces.ingest_command import (
    IngestWiring,
    default_wiring,
    run_ingest_command,
)

if TYPE_CHECKING:
    from tests.unit.ingest.conftest import Lab

BASE_URL = "https://source.invalid/PLATAFORMA"
BUYER = "SYNTHETIC BUYER S.A."
YEAR = 2025
BODY_MARKER = "synthetic-body-marker"
HEADER_MARKER = "synthetic-header-marker"
PASSWORD_MARKER = "synthetic-password-marker"
COOKIE_NAME = "synthetic-session"
JSON_HEADERS = [("Content-Type", "application/json")]
HTML_429 = b"<html><body>synthetic rate limit synthetic-body-marker</body></html>"
RESUME_ID = "ingest-20261016t100000z-aaaaaaaa"
FIRST_MIGRATION = "0001_initial_schema.sql"
POSTGRES_VARIABLES = (
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
)
GOOD_ENVIRON: dict[str, str] = {
    "POSTGRES_DB": "synthetic_db",
    "POSTGRES_USER": "synthetic_user",
    "POSTGRES_PASSWORD": PASSWORD_MARKER,
}
SCOPE_ARGS = [
    "--year",
    str(YEAR),
    "--buyer",
    BUYER,
    "--first-page",
    "1",
    "--last-page",
    "2",
]

# --- The wiring double --------------------------------------------------------

SourceBuild = tuple[ProcurementSource, Callable[[], None]]


@dataclass
class Result:
    """What one invocation produced: the exit code and the two streams."""

    code: int
    out: str
    err: str
    sys_out: str = ""
    sys_err: str = ""


class CountingSource:
    """A `ClosableSource` that forwards to `inner` and counts its closes."""

    def __init__(
        self, inner: ProcurementSource, close_inner: Callable[[], None]
    ) -> None:
        self._inner = inner
        self._close_inner = close_inner
        self.closes = 0

    def search_page(self, *, year: int, buyer: str, page: int) -> SearchPage:
        return self._inner.search_page(year=year, buyer=buyer, page=page)

    def fetch_record(self, ocid: str) -> RecordResponse:
        return self._inner.fetch_record(ocid)

    def close(self) -> None:
        self.closes += 1
        self._close_inner()


class ChunkStream(httpx.SyncByteStream):
    """A response body as one chunk, so the source reads it from the stream."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def __iter__(self) -> Iterator[bytes]:
        yield self._body


def answer(
    status: int, body: bytes, headers: Sequence[tuple[str, str]]
) -> httpx.Response:
    """A response whose body the source reads from a stream (as on the wire)."""
    return httpx.Response(status, headers=list(headers), stream=ChunkStream(body))


def exit_status(code: object) -> int:
    assert isinstance(code, int), f"the exit status is not an integer: {code!r}"
    return code


class Rig:
    """The `IngestWiring` of one test, over the doubles of a `Lab`.

    Every collaborator the command builds is recorded in `calls`, in order. A name
    in `forbidden` makes its double fail the test when the command reaches it
    (`calls` still shows the attempt, so a command that swallows the failure is
    caught as well).
    """

    def __init__(
        self,
        lab: Lab,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
        entry: str,
    ) -> None:
        self.lab = lab
        self.entry = entry
        self._capsys = capsys
        self._monkeypatch = monkeypatch
        self.calls: list[str] = []
        self.forbidden: set[str] = set()
        self.store_roots: list[Path] = []
        self.source_clocks: list[Callable[[], datetime]] = []
        self.sources: list[CountingSource] = []
        self.repository_settings: list[PostgresSettings] = []
        self.migrate_calls: list[tuple[PostgresSettings, Path]] = []
        self.migrate_names: tuple[str, ...] = ()
        self.migrate_impl: Callable[[PostgresSettings, Path], tuple[str, ...]] = (
            lambda settings, directory: self.migrate_names
        )
        self.repository_error: BaseException | None = None
        self.store_error: BaseException | None = None
        # The store `make_store` hands out; a test may put a faulty one here.
        self.store: RawEvidenceStore = lab.store
        self.source_builder: Callable[[Callable[[], datetime]], SourceBuild] = (
            lambda now: (lab.source, lambda: None)
        )

    # --- The collaborators the command builds ---

    def _enter(self, name: str) -> None:
        self.calls.append(name)
        if name in self.forbidden:
            raise AssertionError(f"the command must not reach {name}")

    def make_source(self, now: Callable[[], datetime]) -> CountingSource:
        self._enter("make_source")
        self.source_clocks.append(now)
        inner, close_inner = self.source_builder(now)
        source = CountingSource(inner, close_inner)
        self.sources.append(source)
        return source

    def make_store(self, root: Path) -> RawEvidenceStore:
        self._enter("make_store")
        self.store_roots.append(root)
        if self.store_error is not None:
            raise self.store_error
        return self.store

    def make_repository(
        self, settings: PostgresSettings
    ) -> ClosableIngestionRepository:
        self._enter("make_repository")
        self.repository_settings.append(settings)
        if self.repository_error is not None:
            raise self.repository_error
        return self.lab.opener()

    def migrate(self, settings: PostgresSettings, directory: Path) -> tuple[str, ...]:
        self._enter("migrate")
        self.migrate_calls.append((settings, directory))
        names = self.migrate_impl(settings, directory)
        self.calls.append("migrate:done")
        return names

    def forbid(self, *names: str) -> None:
        self.forbidden.update(names)

    def use_transport(self, handler: Callable[[httpx.Request], httpx.Response]) -> None:
        """Build the real `SercopSource` over `handler`, as the real wiring does."""

        def build(now: Callable[[], datetime]) -> SourceBuild:
            source = SercopSource(
                base_url=BASE_URL,
                transport=httpx.MockTransport(handler),
                now=now,
                sleep=lambda seconds: None,
                min_interval=0,
                cooldown=0,
            )
            return source, source.close

        self.source_builder = build

    def wiring(self) -> IngestWiring:
        return IngestWiring(
            base_url=BASE_URL,
            make_source=self.make_source,
            make_store=self.make_store,
            make_repository=self.make_repository,
            migrate=self.migrate,
            clock=self.lab.clock,
            execution_ids=self.lab.execution_ids,
        )

    # --- The two entries ---

    def invoke(
        self, argv: Sequence[str], *, environ: Mapping[str, str] | None = None
    ) -> Result:
        """Run `ingest <argv>` through the entry of this rig."""
        environment = dict(GOOD_ENVIRON) if environ is None else dict(environ)
        try:
            if self.entry == "main":
                return self._through_main(argv, environment)
            return self._through_command(argv, environment)
        except KeyboardInterrupt as error:
            raise AssertionError(
                "the command let a KeyboardInterrupt escape"
            ) from error

    def _through_main(self, argv: Sequence[str], environment: dict[str, str]) -> Result:
        for name in POSTGRES_VARIABLES:
            self._monkeypatch.delenv(name, raising=False)
        for name, value in environment.items():
            self._monkeypatch.setenv(name, value)
        wiring = self.wiring()
        self._monkeypatch.setattr(cli, "default_wiring", lambda: wiring)
        with pytest.raises(SystemExit) as stop:
            cli.main(["ingest", *argv])
        captured = self._capsys.readouterr()
        return Result(exit_status(stop.value.code), captured.out, captured.err)

    def _through_command(
        self, argv: Sequence[str], environment: dict[str, str]
    ) -> Result:
        out = io.StringIO()
        err = io.StringIO()
        try:
            arguments = cli.build_parser().parse_args(["ingest", *argv])
            code = run_ingest_command(
                arguments,
                environ=environment,
                wiring=self.wiring(),
                stdout=out,
                stderr=err,
            )
        except SystemExit as stop:
            code = exit_status(stop.code)
        captured = self._capsys.readouterr()
        return Result(
            code,
            out.getvalue(),
            err.getvalue() + captured.err,
            sys_out=captured.out,
            sys_err=captured.err,
        )


@pytest.fixture(params=["command", "main"])
def entry(request: pytest.FixtureRequest) -> str:
    """The entry a test runs through: `run_ingest_command` or `main`."""
    return str(request.param)


@pytest.fixture
def rig(
    lab: Lab,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    entry: str,
) -> Rig:
    return Rig(lab, capsys, monkeypatch, entry)


@pytest.fixture
def command_rig(
    lab: Lab, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> Rig:
    """A rig that always calls `run_ingest_command` itself."""
    return Rig(lab, capsys, monkeypatch, "command")


# --- Helpers ------------------------------------------------------------------


def the_run(lab: Lab) -> str:
    """The id of the one run the call created."""
    assert len(lab.database.runs) == 1, list(lab.database.runs)
    return next(iter(lab.database.runs))


def assert_nothing_started(rig: Rig) -> None:
    """No collaborator was built, nothing was requested, stored or recorded."""
    lab = rig.lab
    assert rig.calls == []
    assert lab.source.calls == []
    assert lab.opener.opens == 0
    assert lab.store.observations == {}
    assert lab.store.objects == {}
    assert lab.database.runs == {}
    assert lab.database.observations == {}


def names(error_text: str, pattern: str) -> bool:
    return re.search(pattern, error_text, re.IGNORECASE) is not None


def all_details(lab: Lab) -> str:
    """Every stored audit detail, as one text."""
    return json.dumps(
        [
            {"type": event.event_type, "detail": dict(event.detail)}
            for events in lab.database.events.values()
            for event in events
        ],
        sort_keys=True,
    )


class SyntheticDefect(Exception):
    """SYNTHETIC: an exception that is not a project error."""


# === usage (AC14) ==============================================================

USAGE_CASES = [
    pytest.param([], r"--(year|buyer|last-page)", id="no-arguments"),
    pytest.param(
        ["--year", "2025", "--buyer", BUYER], r"--last-page", id="no-last-page"
    ),
    pytest.param(["--buyer", BUYER, "--last-page", "1"], r"--year", id="no-year"),
    pytest.param(["--year", "2025", "--last-page", "1"], r"--buyer", id="no-buyer"),
    pytest.param(
        ["--year", "2025", "--buyer", BUYER, "--first-page", "0", "--last-page", "1"],
        r"first[-_]page",
        id="first-page-0",
    ),
    pytest.param(
        ["--year", "2025", "--buyer", BUYER, "--last-page", "1", "--first-page", "2"],
        r"(first|last)[-_]page",
        id="first-page-after-last-page",
    ),
    pytest.param(
        ["--year", "2025", "--buyer", BUYER, "--last-page", "0"],
        r"last[-_]page",
        id="last-page-0",
    ),
    pytest.param(
        ["--year", "0", "--buyer", BUYER, "--last-page", "1"], r"year", id="year-0"
    ),
    pytest.param(
        ["--year", "abc", "--buyer", BUYER, "--last-page", "1"],
        r"--year",
        id="year-abc",
    ),
    pytest.param(
        ["--year", "-5", "--buyer", BUYER, "--last-page", "1"],
        r"year",
        id="year-negative",
    ),
    pytest.param(
        ["--year", "2025", "--buyer", "", "--last-page", "1"],
        r"buyer",
        id="empty-buyer",
    ),
    pytest.param(
        [*SCOPE_ARGS, "--raw-root", "somewhere"],
        r"unrecognized arguments",
        id="raw-root",
    ),
    pytest.param(
        [*SCOPE_ARGS, "--base-url", "https://source.invalid/other"],
        r"unrecognized arguments",
        id="base-url",
    ),
    pytest.param(["--resume", "Synthetic_Id"], r"resume", id="resume-bad-id"),
    pytest.param(
        ["--resume", RESUME_ID, "--year", "2025"],
        r"--(resume|year)",
        id="resume-with-year",
    ),
    pytest.param(
        ["--resume", RESUME_ID, "--buyer", BUYER],
        r"--(resume|buyer)",
        id="resume-with-buyer",
    ),
    pytest.param(
        ["--resume", RESUME_ID, "--first-page", "2"],
        r"--(resume|first-page)",
        id="resume-with-first-page",
    ),
    pytest.param(
        ["--resume", RESUME_ID, "--last-page", "3"],
        r"--(resume|last-page)",
        id="resume-with-last-page",
    ),
]


@pytest.mark.parametrize(("argv", "pattern"), USAGE_CASES)
def test_usage_invalid_arguments_exit_2_before_anything_is_built(
    rig: Rig, argv: list[str], pattern: str
) -> None:
    """AC14: exit 2, stdout empty, stderr names the argument, nothing started."""
    rig.forbid("make_source", "make_store", "make_repository", "migrate")

    result = rig.invoke(argv)

    assert result.code == 2
    assert result.out == ""
    assert "usage" in result.err.lower()
    assert names(result.err, pattern), result.err
    assert PASSWORD_MARKER not in result.err
    assert_nothing_started(rig)


def test_usage_bare_command_prints_usage_and_exits_2(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC14: a bare `ec-procurement-quality` prints the usage on stderr, exit 2."""
    with pytest.raises(SystemExit) as stop:
        cli.main([])

    captured = capsys.readouterr()
    assert stop.value.code == 2
    assert captured.out == ""
    assert "usage" in captured.err.lower()


def test_usage_resume_with_only_the_migrations_directory_is_a_valid_command(
    rig: Rig,
) -> None:
    """AC9, AC14: `--resume <id> --migrations-dir <path>` is parsed, then checked.

    The id names no run, so the command ends as an invalid target (exit 2); what
    matters here is that it got past the arguments and built the repository.
    """
    result = rig.invoke(["--resume", RESUME_ID, "--migrations-dir", "migrations"])

    assert result.code == 2
    assert RESUME_ID in result.err
    assert "make_repository" in rig.calls


# === environment (AC14, AC25) ==================================================


@pytest.mark.parametrize(
    "missing", ["POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"]
)
def test_environment_a_missing_required_variable_exits_2(
    rig: Rig, missing: str
) -> None:
    """AC14: the message names the variable and never the value of another one."""
    rig.forbid("make_source", "make_store", "make_repository", "migrate")
    environ = {name: value for name, value in GOOD_ENVIRON.items() if name != missing}

    result = rig.invoke(SCOPE_ARGS, environ=environ)

    assert result.code == 2
    assert result.out == ""
    assert missing in result.err
    assert not any(value in result.err for value in environ.values())
    assert_nothing_started(rig)


@pytest.mark.parametrize("port", ["abc", "70000"])
def test_environment_an_invalid_port_exits_2_and_never_prints_it(
    rig: Rig, port: str
) -> None:
    """AC14: `POSTGRES_PORT` `abc` or `70000` -> exit 2, naming the variable."""
    rig.forbid("make_source", "make_store", "make_repository", "migrate")

    result = rig.invoke(SCOPE_ARGS, environ={**GOOD_ENVIRON, "POSTGRES_PORT": port})

    assert result.code == 2
    assert result.out == ""
    assert names(result.err, r"POSTGRES_PORT|port")
    assert port not in result.err
    assert PASSWORD_MARKER not in result.err
    assert_nothing_started(rig)


def test_environment_a_dotenv_file_in_the_current_directory_is_never_read(
    rig: Rig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC14: with the variables unset and a `.env` present, the result is exit 2."""
    (tmp_path / ".env").write_text(
        "POSTGRES_DB=synthetic_dotenv_db\n"
        "POSTGRES_USER=synthetic_dotenv_user\n"
        f"POSTGRES_PASSWORD={PASSWORD_MARKER}\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    rig.forbid("make_source", "make_store", "make_repository", "migrate")

    result = rig.invoke(SCOPE_ARGS, environ={})

    assert result.code == 2
    assert result.out == ""
    assert "POSTGRES_DB" in result.err
    assert "synthetic_dotenv" not in result.err
    assert PASSWORD_MARKER not in result.err
    assert_nothing_started(rig)


def test_environment_the_command_reads_only_the_mapping_it_is_given(
    command_rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC14: nothing but `environ` is read, whatever the process environment holds."""
    monkeypatch.setenv("POSTGRES_DB", "process_db")
    monkeypatch.setenv("POSTGRES_USER", "process_user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "process-password")
    monkeypatch.setenv("POSTGRES_HOST", "process.invalid")
    monkeypatch.setenv("POSTGRES_PORT", "6543")

    result = command_rig.invoke(SCOPE_ARGS)

    assert result.code == 0
    settings = command_rig.repository_settings[0]
    assert settings.dbname == "synthetic_db"
    assert settings.user == "synthetic_user"
    assert settings.password == PASSWORD_MARKER
    assert settings.host == "127.0.0.1"
    assert settings.port == 5432


def test_environment_host_and_port_default_to_127_0_0_1_and_5432(rig: Rig) -> None:
    """AC25: `POSTGRES_HOST` and `POSTGRES_PORT` unset -> the defaults, no error."""
    result = rig.invoke(SCOPE_ARGS, environ=GOOD_ENVIRON)

    assert result.code == 0
    assert rig.repository_settings, "make_repository was not called"
    for settings in [*rig.repository_settings, rig.migrate_calls[0][0]]:
        assert settings.host == "127.0.0.1"
        assert settings.port == 5432
        assert settings.dbname == "synthetic_db"
        assert settings.user == "synthetic_user"
        assert settings.password == PASSWORD_MARKER


def test_environment_the_settings_carry_the_values_given(rig: Rig) -> None:
    """AC25: the optional variables, when set, reach the migrations and the repository."""
    environ = {
        **GOOD_ENVIRON,
        "POSTGRES_HOST": "db.synthetic.invalid",
        "POSTGRES_PORT": "6543",
    }

    result = rig.invoke(SCOPE_ARGS, environ=environ)

    assert result.code == 0
    assert rig.migrate_calls[0][0] == rig.repository_settings[0]
    settings = rig.repository_settings[0]
    assert (settings.host, settings.port) == ("db.synthetic.invalid", 6543)
    assert PASSWORD_MARKER not in repr(settings)


def test_environment_a_migrations_error_exits_2_and_builds_nothing_else(
    rig: Rig,
) -> None:
    """AC14, AC16: an invalid migrations history stops the command at exit 2.

    The source is built first (plan Revision 6, invocation step 2) and closed once;
    no store and no repository is built.
    """

    def refuse(settings: PostgresSettings, directory: Path) -> tuple[str, ...]:
        raise MigrationError("migration file 'bad.sql' is not named NNNN_description")

    rig.migrate_impl = refuse
    rig.forbid("make_store", "make_repository")

    result = rig.invoke([*SCOPE_ARGS, "--migrations-dir", "bad-migrations"])

    assert result.code == 2
    assert result.out == ""
    assert result.err.strip() != ""
    assert PASSWORD_MARKER not in result.err
    assert rig.calls == ["make_source", "migrate"]
    assert [source.closes for source in rig.sources] == [1]
    assert rig.lab.source.calls == []
    assert rig.lab.opener.opens == 0


def _write(directory: Path, name: str, text: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(text, encoding="utf-8")


def _missing_directory(tmp_path: Path) -> Path:
    return tmp_path / "missing-migrations"


def _misnamed_file(tmp_path: Path) -> Path:
    _write(tmp_path / "misnamed", "bad.sql", "SELECT 1;\n")
    return tmp_path / "misnamed"


def _empty_file(tmp_path: Path) -> Path:
    _write(tmp_path / "empty", FIRST_MIGRATION, "\n")
    return tmp_path / "empty"


@pytest.mark.parametrize(
    "make_directory",
    [_missing_directory, _misnamed_file, _empty_file],
    ids=["missing-directory", "misnamed-file", "empty-file"],
)
def test_environment_the_real_runner_refuses_a_bad_directory_before_a_connection(
    rig: Rig, tmp_path: Path, make_directory: Callable[[Path], Path]
) -> None:
    """AC14: a missing or invalid migrations directory -> exit 2, no connection.

    The real `apply_migrations` checks the directory before it opens a connection
    (PS-3), and the port in the environment is one nothing listens on.
    """
    rig.migrate_impl = apply_migrations
    rig.forbid("make_store", "make_repository")
    directory = make_directory(tmp_path)

    result = rig.invoke(
        [*SCOPE_ARGS, "--migrations-dir", str(directory)],
        environ={**GOOD_ENVIRON, "POSTGRES_PORT": "1"},
    )

    assert result.code == 2
    assert result.out == ""
    assert result.err.strip() != ""
    assert PASSWORD_MARKER not in result.err
    assert rig.calls == ["make_source", "migrate"]
    assert [source.closes for source in rig.sources] == [1]
    assert rig.lab.source.calls == []
    assert rig.lab.store.observations == {}
    assert rig.lab.database.runs == {}


# === paths (AC25) ==============================================================


def test_paths_the_store_root_is_absolute_and_under_the_current_directory(
    rig: Rig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC25: the root given to `make_store` is `Path.cwd() / "data" / "raw"`."""
    monkeypatch.chdir(tmp_path)

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == 0
    assert rig.store_roots == [Path.cwd() / "data" / "raw"]
    assert rig.store_roots[0].is_absolute()


@pytest.mark.parametrize(
    ("option", "expected"),
    [
        pytest.param([], "migrations", id="default"),
        pytest.param(["--migrations-dir", "sql/forward"], "sql/forward", id="relative"),
    ],
)
def test_paths_a_relative_migrations_directory_is_resolved_against_the_current_directory(
    rig: Rig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    option: list[str],
    expected: str,
) -> None:
    """AC25, plan § Configuration: `Path.cwd() / <--migrations-dir>`, absolute."""
    monkeypatch.chdir(tmp_path)

    result = rig.invoke([*SCOPE_ARGS, *option])

    assert result.code == 0
    directory = rig.migrate_calls[0][1]
    assert directory.is_absolute()
    assert directory == Path.cwd() / expected


def test_paths_an_absolute_migrations_directory_is_used_as_given(
    rig: Rig, tmp_path: Path
) -> None:
    """AC25: an absolute `--migrations-dir` is not rebased."""
    given = tmp_path / "elsewhere" / "sql"

    result = rig.invoke([*SCOPE_ARGS, "--migrations-dir", str(given)])

    assert result.code == 0
    assert rig.migrate_calls[0][1] == given


def test_paths_are_resolved_once_before_anything_changes_the_current_directory(
    command_rig: Rig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC25: a change of the current directory during the run changes no path.

    The migration step moves the process to another directory; the store root the
    command hands out afterwards is still the one resolved at the start.
    """
    root = tmp_path / "repository-root"
    elsewhere = tmp_path / "elsewhere"
    root.mkdir()
    elsewhere.mkdir()
    monkeypatch.chdir(root)
    expected_store = Path.cwd() / "data" / "raw"
    expected_migrations = Path.cwd() / "migrations"

    def migrate_and_move(
        settings: PostgresSettings, directory: Path
    ) -> tuple[str, ...]:
        monkeypatch.chdir(elsewhere)
        return ()

    command_rig.migrate_impl = migrate_and_move

    result = command_rig.invoke(SCOPE_ARGS)

    assert result.code == 0
    assert command_rig.migrate_calls[0][1] == expected_migrations
    assert command_rig.store_roots == [expected_store]


# === exit_code (AC7, AC8, AC9, AC14, AC16, AC18, decisions P-1, P-2, P-5) =====


def test_exit_code_0_a_succeeded_run_prints_one_result_line(rig: Rig) -> None:
    """AC1, AC15: exit 0 and stdout exactly `<A> succeeded`."""
    lab = rig.lab

    result = rig.invoke(SCOPE_ARGS)

    run_id = the_run(lab)
    assert result.code == 0
    assert result.out == f"{run_id} succeeded\n"
    assert lab.database.runs[run_id].status is RunStatus.SUCCEEDED
    assert lab.source.calls == [(YEAR, BUYER, 1), (YEAR, BUYER, 2)]
    assert same_json(dict(lab.database.runs[run_id].scope), lab.scope(1, 2).to_json())
    assert lab.event_types(run_id) == [
        "run-started",
        "page-completed",
        "page-completed",
    ]


def test_exit_code_0_first_page_defaults_to_1(rig: Rig) -> None:
    """Q9: `--first-page` is optional and starts at page 1."""
    lab = rig.lab

    result = rig.invoke(["--year", "2025", "--buyer", BUYER, "--last-page", "2"])

    assert result.code == 0
    assert lab.source.requests == [1, 2]
    assert same_json(
        dict(lab.database.runs[the_run(lab)].scope), lab.scope(1, 2).to_json()
    )


def test_exit_code_0_the_source_is_built_with_the_wiring_clock(rig: Rig) -> None:
    """AC12: `make_source` receives the clock the whole invocation uses."""
    lab = rig.lab

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == 0
    assert len(rig.source_clocks) == 1
    before = len(lab.clock.issued)
    rig.source_clocks[0]()
    assert len(lab.clock.issued) == before + 1


def test_exit_code_1_a_failed_run_prints_its_id_and_failed(rig: Rig) -> None:
    """AC4, AC15: a page that fails after a response -> exit 1, `<A> failed`."""
    lab = rig.lab
    lab.source.script(2, lab.status_failure(2, 429, HTML_429))

    result = rig.invoke(SCOPE_ARGS)

    run_id = the_run(lab)
    assert result.code == 1
    assert result.out == f"{run_id} failed\n"
    assert lab.database.runs[run_id].status is RunStatus.FAILED
    assert lab.source.requests == [1, 2]


def test_exit_code_1_a_run_without_a_response_prints_failed(rig: Rig) -> None:
    """AC5: a failure before any response -> exit 1, `<A> failed`."""
    lab = rig.lab
    lab.source.script(2, lab.failure_without_response())

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == 1
    assert result.out == f"{the_run(lab)} failed\n"


def test_exit_code_1_the_exclusion_held_elsewhere_starts_nothing(rig: Rig) -> None:
    """AC8 c, AC10: another ingest is active -> exit 1, stdout empty, no run."""
    lab = rig.lab
    lab.database.hold_exclusion_elsewhere()

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == 1
    assert result.out == ""
    assert result.err.strip() != ""
    assert lab.database.runs == {}
    assert lab.source.calls == []
    assert lab.store.observations == {}


def test_exit_code_1_an_unreachable_database_starts_nothing(rig: Rig) -> None:
    """Exit table: the repository cannot be opened -> `NOT_STARTED`, exit 1."""
    lab = rig.lab
    rig.repository_error = PersistenceConnectionError("synthetic: unreachable")

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == 1
    assert result.out == ""
    assert lab.source.calls == []
    assert lab.database.runs == {}


def test_exit_code_1_a_reconciliation_problem_starts_no_run(rig: Rig) -> None:
    """AC10: a problem closes the old run `failed` and creates no run: exit 1."""
    lab = rig.lab
    lab.seed.run(lab.A, scope=lab.scope(1, 4), status=RunStatus.RUNNING)
    lab.seed.started(lab.A)
    lab.seed.page(lab.A, 1, 1, local=False)

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == 1
    assert result.out == ""
    assert set(lab.database.runs) == {lab.A}
    assert lab.database.runs[lab.A].status is RunStatus.FAILED
    assert lab.source.calls == []


def test_exit_code_2_an_unknown_resumption_target_writes_nothing(rig: Rig) -> None:
    """AC9, AC14: a well-formed id that names no run -> exit 2, a fixed message."""
    lab = rig.lab
    before = lab.snapshot()

    result = rig.invoke(["--resume", lab.ABSENT])

    assert result.code == 2
    assert result.out == ""
    assert lab.ABSENT in result.err
    assert lab.snapshot() == before
    assert lab.source.calls == []


def test_exit_code_2_a_succeeded_resumption_target_writes_nothing(rig: Rig) -> None:
    """AC9, AC14: a `succeeded` run needs no resumption -> exit 2."""
    lab = rig.lab
    lab.seed.run(lab.A, scope=lab.scope(1, 2), status=RunStatus.SUCCEEDED)
    lab.seed.started(lab.A)
    lab.seed.completed(lab.A, 1, 2)
    before = lab.snapshot()

    result = rig.invoke(["--resume", lab.A])

    assert result.code == 2
    assert result.out == ""
    assert lab.A in result.err
    assert lab.snapshot() == before
    assert lab.source.calls == []


def test_exit_code_1_a_broken_chain_is_not_a_usage_error(rig: Rig) -> None:
    """AC24: a resumable target with a chain that does not hold -> exit 1."""
    lab = rig.lab
    lab.seed.run(lab.A, scope=lab.scope(1, 4))
    lab.seed.started(lab.A, resumes=lab.B)
    before = lab.snapshot()

    result = rig.invoke(["--resume", lab.A])

    assert result.code == 1
    assert result.out == ""
    assert lab.A in result.err
    assert lab.snapshot() == before
    assert lab.source.calls == []


def test_exit_code_130_an_interrupt_during_a_page_prints_failed(rig: Rig) -> None:
    """AC7: Ctrl+C while page 2 is requested -> exit 130, stdout `<A> failed`."""
    lab = rig.lab
    lab.source.script(2, KeyboardInterrupt())

    result = rig.invoke(SCOPE_ARGS)

    run_id = the_run(lab)
    assert result.code == 130
    assert result.out == f"{run_id} failed\n"
    assert lab.event_types(run_id) == [
        "run-started",
        "page-completed",
        "run-interrupted",
    ]
    assert lab.database.runs[run_id].status is RunStatus.FAILED


def test_exit_code_130_a_second_interrupt_leaves_the_run_running(rig: Rig) -> None:
    """AC7, P-5: the cleanup is interrupted -> exit 130 and `<A> running`."""
    lab = rig.lab
    lab.source.script(2, KeyboardInterrupt())
    lab.opener.faults[1] = [
        lab.faults.interrupts("append_audit_event", detail="run-interrupted")
    ]

    result = rig.invoke(SCOPE_ARGS)

    run_id = the_run(lab)
    assert result.code == 130
    assert result.out == f"{run_id} running\n"
    assert lab.database.runs[run_id].status is RunStatus.RUNNING


def test_exit_code_130_an_interrupt_before_the_run_exists_prints_nothing(
    rig: Rig,
) -> None:
    """AC7: Ctrl+C before `start_run` returned -> exit 130, stdout empty."""
    lab = rig.lab
    lab.opener.faults[1] = [lab.faults.interrupts("start_run")]

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == 130
    assert result.out == ""
    assert lab.database.runs == {}


def test_exit_code_130_an_interrupt_while_the_migrations_run(rig: Rig) -> None:
    """Exit table: a `KeyboardInterrupt` in steps 1 to 4 -> 130, no store or repository.

    The source built at step 2 is still closed, once.
    """

    def interrupted(settings: PostgresSettings, directory: Path) -> tuple[str, ...]:
        raise KeyboardInterrupt

    rig.migrate_impl = interrupted

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == 130
    assert result.out == ""
    assert rig.calls == ["make_source", "migrate"]
    assert [source.closes for source in rig.sources] == [1]
    assert rig.lab.opener.opens == 0


def test_exit_code_130_an_interrupt_while_the_source_is_built(rig: Rig) -> None:
    """Exit table: a `KeyboardInterrupt` in step 4 -> 130, no repository, no line."""

    def interrupted(now: Callable[[], datetime]) -> SourceBuild:
        raise KeyboardInterrupt

    rig.source_builder = interrupted

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == 130
    assert result.out == ""
    assert rig.lab.opener.opens == 0
    assert rig.lab.database.runs == {}


def test_exit_code_130_an_interrupt_while_the_repository_opens(rig: Rig) -> None:
    """Exit table: Ctrl+C while the repository opens -> 130, stdout empty.

    After F-16 (a), `run_ingest` handles it itself (INTERRUPTED, no run), so nothing
    escapes it; the exit code and the empty stdout are the same either way.
    """
    rig.repository_error = KeyboardInterrupt()

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == 130
    assert result.out == ""
    assert rig.lab.database.runs == {}
    assert all(source.closes == 1 for source in rig.sources)


MIGRATE_FAILURES = [
    pytest.param(
        lambda: MigrationLockError("another migration run holds the lock"),
        1,
        id="migration-lock-held",
    ),
    pytest.param(
        lambda: MigrationError("applied migration '0001' was changed"),
        2,
        id="migration-history",
    ),
    pytest.param(
        lambda: PersistenceConnectionError("could not open a connection"),
        1,
        id="connection",
    ),
    pytest.param(
        lambda: PersistenceIntegrityError("the database refused the data"),
        1,
        id="integrity",
    ),
    pytest.param(
        lambda: PersistenceError("the database reported an error"), 1, id="persistence"
    ),
]


@pytest.mark.parametrize(("make_error", "code"), MIGRATE_FAILURES)
def test_exit_code_migration_failures_map_to_1_or_2_before_anything_is_built(
    rig: Rig, make_error: Callable[[], BaseException], code: int
) -> None:
    """AC16, P-1: `MigrationLockError` 1, other `MigrationError` 2, database 1."""

    def fail(settings: PostgresSettings, directory: Path) -> tuple[str, ...]:
        raise make_error()

    rig.migrate_impl = fail
    rig.forbid("make_store", "make_repository")

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == code
    assert result.out == ""
    assert result.err.strip() != ""
    assert PASSWORD_MARKER not in result.err
    assert rig.calls == ["make_source", "migrate"]
    assert [source.closes for source in rig.sources] == [1]
    assert rig.lab.opener.opens == 0


def test_exit_code_order_of_invocation_migrate_returns_before_the_repository(
    rig: Rig,
) -> None:
    """AC16: `apply_migrations` returns before `make_repository` is called.

    The source is built before the migrations (plan Revision 6, step 2).
    """
    result = rig.invoke(SCOPE_ARGS)

    assert result.code == 0
    assert rig.calls[:2] == ["make_source", "migrate"]
    assert "migrate:done" in rig.calls
    assert rig.calls.index("migrate:done") < rig.calls.index("make_repository")
    assert rig.calls.count("migrate") == 1
    assert rig.calls.count("make_source") == 1
    assert rig.calls.count("make_store") == 1
    assert rig.calls.count("make_repository") == 1


def test_exit_code_order_of_invocation_a_refused_migration_builds_no_repository(
    rig: Rig,
) -> None:
    """AC16: a failing runner means no repository or store was built.

    The source was built at step 2, once, before the runner, and is closed once.
    """

    def fail(settings: PostgresSettings, directory: Path) -> tuple[str, ...]:
        raise MigrationLockError("another migration run holds the lock")

    rig.migrate_impl = fail

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == 1
    assert "make_repository" not in rig.calls
    assert "make_store" not in rig.calls
    assert rig.calls.count("make_source") == 1
    assert [source.closes for source in rig.sources] == [1]


def test_exit_code_1_an_exception_that_escapes_the_use_case_names_its_class_only(
    rig: Rig,
) -> None:
    """Exit table: an exception while the repository opens -> 1, the class name alone.

    After F-16 (a), `run_ingest` handles it itself (NOT_STARTED, a fixed message
    with at most the class name), so it no longer escapes; the exit code and the
    class-name-only stderr are the same either way. The escaping path stays pinned
    by the `output_escaping_exception` tests, which replace `run_ingest`.
    """
    error = SyntheticDefect(f"{BODY_MARKER} {PASSWORD_MARKER}")
    error.__cause__ = ValueError(HEADER_MARKER)
    rig.repository_error = error

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == 1
    assert result.out == ""
    assert "SyntheticDefect" in result.err
    for text in (BODY_MARKER, PASSWORD_MARKER, HEADER_MARKER):
        assert text not in result.err
    assert "Traceback" not in result.err
    assert "ValueError" not in result.err


def _end_succeeded(rig: Rig) -> Result:
    return rig.invoke(SCOPE_ARGS)


def _end_failed(rig: Rig) -> Result:
    rig.lab.source.script(2, rig.lab.status_failure(2, 500))
    return rig.invoke(SCOPE_ARGS)


def _end_interrupted(rig: Rig) -> Result:
    rig.lab.source.script(1, KeyboardInterrupt())
    return rig.invoke(SCOPE_ARGS)


def _end_second_interrupt(rig: Rig) -> Result:
    rig.lab.source.script(1, KeyboardInterrupt())
    rig.lab.opener.faults[1] = [
        rig.lab.faults.interrupts("append_audit_event", detail="run-interrupted")
    ]
    return rig.invoke(SCOPE_ARGS)


def _end_exclusion_held(rig: Rig) -> Result:
    rig.lab.database.hold_exclusion_elsewhere()
    return rig.invoke(SCOPE_ARGS)


def _end_invalid_target(rig: Rig) -> Result:
    return rig.invoke(["--resume", rig.lab.ABSENT])


def _end_escaped_exception(rig: Rig) -> Result:
    rig.repository_error = SyntheticDefect("synthetic")
    return rig.invoke(SCOPE_ARGS)


def _end_unreachable(rig: Rig) -> Result:
    rig.repository_error = PersistenceConnectionError("synthetic")
    return rig.invoke(SCOPE_ARGS)


@pytest.mark.parametrize(
    "ending",
    [
        _end_succeeded,
        _end_failed,
        _end_interrupted,
        _end_second_interrupt,
        _end_exclusion_held,
        _end_invalid_target,
        _end_escaped_exception,
        _end_unreachable,
    ],
    ids=lambda ending: ending.__name__.removeprefix("_end_"),
)
def test_exit_code_one_source_is_built_and_closed_once_whatever_the_ending(
    rig: Rig, ending: Callable[[Rig], Result]
) -> None:
    """AC18: one `SercopSource` per invocation, closed in a `finally`."""
    ending(rig)

    assert rig.calls.count("make_source") == 1
    assert len(rig.sources) == 1
    assert rig.sources[0].closes == 1


def test_exit_code_p2_a_final_finish_lost_before_commit_is_confirmed_exit_0(
    rig: Rig,
) -> None:
    """AC8 (P-2): the exact repeat finishes the run -> exit 0, `<A> succeeded`."""
    lab = rig.lab
    lab.opener.faults[1] = [
        lab.faults.lost_before_commit("finish_run", detail="succeeded")
    ]

    result = rig.invoke(SCOPE_ARGS)

    run_id = the_run(lab)
    assert result.code == 0
    assert result.out == f"{run_id} succeeded\n"
    assert lab.database.runs[run_id].status is RunStatus.SUCCEEDED
    assert "storage-failed" not in lab.event_types(run_id)
    assert lab.opener.opens == 2


def test_exit_code_p2_a_final_finish_lost_after_commit_is_confirmed_exit_0(
    rig: Rig,
) -> None:
    """AC8 (P-2): the repeat returns the stored `succeeded` run -> exit 0."""
    lab = rig.lab
    lab.opener.faults[1] = [
        lab.faults.lost_after_commit("finish_run", detail="succeeded")
    ]

    result = rig.invoke(SCOPE_ARGS)

    run_id = the_run(lab)
    assert result.code == 0
    assert result.out == f"{run_id} succeeded\n"
    assert lab.database.runs[run_id].status is RunStatus.SUCCEEDED


def test_exit_code_p2_recovery_refused_leaves_the_run_running_exit_1(rig: Rig) -> None:
    """AC8 (P-2): the new connection cannot be opened -> exit 1, `<A> running`."""
    lab = rig.lab
    lab.opener.faults[1] = [
        lab.faults.lost_before_commit("finish_run", detail="succeeded")
    ]
    lab.opener.fail_opens.add(2)

    result = rig.invoke(SCOPE_ARGS)

    run_id = the_run(lab)
    assert result.code == 1
    assert result.out == f"{run_id} running\n"
    assert lab.database.runs[run_id].status is RunStatus.RUNNING


def test_exit_code_1_a_connection_lost_in_the_middle_closes_the_run_failed(
    rig: Rig,
) -> None:
    """AC8: a loss that is not the final finish -> `failed`, exit 1."""
    lab = rig.lab
    lab.opener.faults[1] = [
        lab.faults.lost_before_commit("record_observation", detail="2")
    ]

    result = rig.invoke(SCOPE_ARGS)

    run_id = the_run(lab)
    assert result.code == 1
    assert result.out == f"{run_id} failed\n"
    assert lab.details(run_id, "storage-failed")[0]["store"] == "postgresql"


# === output (AC15, decisions P-2, P-5) =========================================


def test_output_the_applied_migration_names_go_to_stderr_only(rig: Rig) -> None:
    """AC16: the applied files are named on stderr; stdout holds the result line."""
    rig.migrate_names = (FIRST_MIGRATION,)

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == 0
    assert FIRST_MIGRATION in result.err
    assert FIRST_MIGRATION not in result.out
    assert PASSWORD_MARKER not in result.err
    assert result.out == f"{the_run(rig.lab)} succeeded\n"


def test_output_nothing_applied_names_no_file(rig: Rig) -> None:
    """AC16: a migrated database -> no migration file on stderr."""
    rig.migrate_names = ()

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == 0
    assert ".sql" not in result.err


def test_output_the_command_writes_only_to_the_streams_it_is_given(
    command_rig: Rig,
) -> None:
    """AC15: stdout and stderr are the streams passed in, not `sys.stdout`."""
    command_rig.lab.source.script(2, command_rig.lab.status_failure(2, 500))

    result = command_rig.invoke(SCOPE_ARGS)

    assert result.code == 1
    assert result.out == f"{the_run(command_rig.lab)} failed\n"
    assert result.sys_out == ""
    assert result.sys_err == ""


def _marker_handler(
    lab: Lab, *, status_of_page_2: int
) -> Callable[[httpx.Request], httpx.Response]:
    """Every response carries a header marker and a cookie; page 2 may fail."""
    headers = [
        ("Content-Type", "application/json"),
        ("X-Synthetic-Header", HEADER_MARKER),
        ("Set-Cookie", f"{COOKIE_NAME}=s1"),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        if page == 2 and status_of_page_2 != 200:
            return answer(status_of_page_2, HTML_429, headers)
        return answer(200, lab.body(page), headers)

    return handler


@pytest.mark.parametrize(
    ("status_of_page_2", "code"),
    [(200, 0), (429, 1), (500, 1)],
    ids=["succeeded", "status-429", "status-500"],
)
def test_output_no_marker_reaches_stdout_stderr_or_a_stored_audit_detail(
    rig: Rig, status_of_page_2: int, code: int
) -> None:
    """AC15: password, body, header value and cookie never leave the process."""
    lab = rig.lab
    rig.use_transport(_marker_handler(lab, status_of_page_2=status_of_page_2))

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == code
    for marker in (PASSWORD_MARKER, BODY_MARKER, HEADER_MARKER, COOKIE_NAME):
        assert marker not in result.out
        assert marker not in result.err
        assert marker not in all_details(lab)
    assert "://" not in result.err
    assert "source.invalid" not in result.err
    assert "source.invalid" not in result.out
    assert "Traceback" not in result.err
    assert len(result.out.splitlines()) == 1


def _defect_handler(
    lab: Lab, error: Callable[[], BaseException]
) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        if page == 2:
            raise error()
        return answer(200, lab.body(page), JSON_HEADERS)

    return handler


def _synthetic_defect() -> BaseException:
    defect = SyntheticDefect(f"{BODY_MARKER} {HEADER_MARKER}")
    defect.__cause__ = ValueError(f"{BODY_MARKER} cause")
    return defect


def test_output_a_synthetic_exception_from_the_transport_names_no_message(
    rig: Rig,
) -> None:
    """AC15, Q11: `unexpected-error` (page, class name), `failed`, exit 1."""
    lab = rig.lab
    rig.use_transport(_defect_handler(lab, _synthetic_defect))

    result = rig.invoke(SCOPE_ARGS, environ=GOOD_ENVIRON)

    run_id = the_run(lab)
    assert result.code == 1
    assert result.out == f"{run_id} failed\n"
    assert BODY_MARKER not in result.err
    assert HEADER_MARKER not in result.err
    assert "cause" not in result.err
    assert "Traceback" not in result.err
    assert "://" not in result.err
    assert lab.event_types(run_id) == [
        "run-started",
        "page-completed",
        "unexpected-error",
    ]
    assert same_json(
        lab.details(run_id, "unexpected-error")[0],
        {"page": 2, "error_type": "SyntheticDefect"},
    )
    assert BODY_MARKER not in all_details(lab)


def test_output_a_memory_error_from_the_transport_exits_1_best_effort(
    rig: Rig,
) -> None:
    """AC15, Q11: `MemoryError` -> the same: exit 1, one result line, no message."""
    lab = rig.lab
    rig.use_transport(_defect_handler(lab, lambda: MemoryError(BODY_MARKER)))

    result = rig.invoke(SCOPE_ARGS)

    run_id = the_run(lab)
    assert result.code == 1
    assert result.out in {f"{run_id} failed\n", f"{run_id} running\n"}
    assert BODY_MARKER not in result.err
    assert "Traceback" not in result.err
    assert BODY_MARKER not in all_details(lab)
    if result.out == f"{run_id} failed\n":
        assert same_json(
            lab.details(run_id, "unexpected-error")[0],
            {"page": 2, "error_type": "MemoryError"},
        )


def test_output_the_p2_case_prints_succeeded_and_keeps_stderr_free_of_secrets(
    rig: Rig,
) -> None:
    """AC15, P-2: `<A> succeeded`, exit 0, and no secret on stderr."""
    lab = rig.lab
    lab.opener.faults[1] = [
        lab.faults.lost_before_commit("finish_run", detail="succeeded")
    ]

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == 0
    assert result.out == f"{the_run(lab)} succeeded\n"
    assert PASSWORD_MARKER not in result.err
    assert "Traceback" not in result.err


def test_output_a_second_interrupt_prints_running_and_no_traceback(rig: Rig) -> None:
    """AC15, P-5: after the second Ctrl+C the line is `<A> running`."""
    lab = rig.lab
    lab.source.script(2, KeyboardInterrupt())
    lab.opener.faults[1] = [
        lab.faults.interrupts("append_audit_event", detail="run-interrupted")
    ]

    result = rig.invoke(SCOPE_ARGS)

    assert result.out == f"{the_run(lab)} running\n"
    assert "Traceback" not in result.err
    assert "KeyboardInterrupt" not in result.out


def test_output_stdout_is_empty_when_no_run_was_created(rig: Rig) -> None:
    """AC15: no run, no result line, whatever the exit code."""
    rig.lab.database.hold_exclusion_elsewhere()

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == 1
    assert result.out == ""
    assert PASSWORD_MARKER not in result.err
    assert "://" not in result.err


# === logger (AC15, R-7) ========================================================


@pytest.fixture
def restore_logging() -> Iterator[None]:
    """Put the levels of the root and the `httpcore` logger back afterwards."""
    root = logging.getLogger()
    httpcore = logging.getLogger("httpcore")
    saved = (root.level, httpcore.level)
    yield
    root.setLevel(saved[0])
    httpcore.setLevel(saved[1])


def _logging_handlers() -> dict[str, list[logging.Handler]]:
    return {
        name: list(logging.getLogger(name).handlers)
        for name in ("", "httpcore", "httpx", "ec_procurement_quality")
    }


LOGGER_STATES = [
    pytest.param(logging.DEBUG, logging.NOTSET, id="root-debug"),
    pytest.param(logging.WARNING, logging.DEBUG, id="httpcore-debug"),
    pytest.param(logging.WARNING, logging.INFO, id="httpcore-info"),
    pytest.param(logging.DEBUG, logging.WARNING, id="httpcore-warning"),
]


@pytest.mark.usefixtures("restore_logging")
@pytest.mark.parametrize(("root_level", "httpcore_level"), LOGGER_STATES)
def test_logger_httpcore_stays_above_debug_during_the_whole_invocation(
    rig: Rig, root_level: int, httpcore_level: int
) -> None:
    """AC15, R-7: the effective level is above `DEBUG` when a page is requested."""
    lab = rig.lab
    levels: list[int] = []
    httpcore = logging.getLogger("httpcore")

    def handler(request: httpx.Request) -> httpx.Response:
        levels.append(httpcore.getEffectiveLevel())
        page = int(request.url.params["page"])
        return answer(200, lab.body(page), JSON_HEADERS)

    def migrate(settings: PostgresSettings, directory: Path) -> tuple[str, ...]:
        levels.append(httpcore.getEffectiveLevel())
        return ()

    rig.use_transport(handler)
    rig.migrate_impl = migrate
    logging.getLogger().setLevel(root_level)
    httpcore.setLevel(httpcore_level)

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == 0
    assert len(levels) == 3  # the migrations and the two pages
    assert all(level > logging.DEBUG for level in levels), levels
    if httpcore_level > logging.DEBUG:
        assert levels[1:] == [httpcore_level, httpcore_level]


@pytest.mark.usefixtures("restore_logging")
@pytest.mark.parametrize(("root_level", "httpcore_level"), LOGGER_STATES)
def test_logger_the_levels_are_restored_when_the_invocation_ends(
    rig: Rig, root_level: int, httpcore_level: int
) -> None:
    """AC15: the guard is limited to the invocation; nothing else is configured."""
    root = logging.getLogger()
    httpcore = logging.getLogger("httpcore")
    root.setLevel(root_level)
    httpcore.setLevel(httpcore_level)

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == 0
    assert httpcore.level == httpcore_level
    assert root.level == root_level


@pytest.mark.usefixtures("restore_logging")
def test_logger_the_level_is_restored_when_the_invocation_is_interrupted(
    rig: Rig,
) -> None:
    """AC15: a `KeyboardInterrupt` in the migrations still restores the level."""
    httpcore = logging.getLogger("httpcore")
    logging.getLogger().setLevel(logging.DEBUG)
    httpcore.setLevel(logging.NOTSET)

    def interrupted(settings: PostgresSettings, directory: Path) -> tuple[str, ...]:
        assert httpcore.getEffectiveLevel() > logging.DEBUG
        raise KeyboardInterrupt

    rig.migrate_impl = interrupted

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == 130
    assert httpcore.level == logging.NOTSET


@pytest.mark.usefixtures("restore_logging")
def test_logger_no_handler_is_added(rig: Rig) -> None:
    """AC15, R-7: `ingest` adds no logging handler to any logger."""
    logging.getLogger().setLevel(logging.DEBUG)
    before = _logging_handlers()

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == 0
    assert _logging_handlers() == before


@pytest.mark.usefixtures("restore_logging")
def test_logger_a_failed_invocation_adds_no_handler_either(rig: Rig) -> None:
    """AC15: the same holds for a usage error and for a failed run."""
    before = _logging_handlers()
    rig.lab.source.script(1, rig.lab.status_failure(1, 500))

    failed = rig.invoke(SCOPE_ARGS)
    refused = rig.invoke(["--year", "abc"])

    assert (failed.code, refused.code) == (1, 2)
    assert _logging_handlers() == before


# === Audit round 1 (2026-10-18), findings F-02 to F-07 =========================
#
# Written red against the Revision 6 specs. Tokens: `source_configuration` and
# `order_of_invocation` (F-03), `exit_code_cleanup_read_back` (F-02),
# `exit_code_interrupt_after_finish` (F-05), `output_escaping_exception` (F-04),
# `output_progress` (F-07) and `chain_unreadable_record_message` (F-06).

PROXY_AND_CERTIFICATE_VARIABLES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
)


def number_in(text: str, number: int) -> bool:
    """`number` stands on its own in `text`: not inside a word or a content hash."""
    return re.search(rf"(?<![0-9A-Za-z]){number}(?![0-9A-Za-z])", text) is not None


def stderr_lines(
    result: Result, *words: str, numbers: tuple[int, ...] = ()
) -> list[str]:
    """The lines of stderr that hold every word and every stand-alone number."""
    return [
        line
        for line in result.err.splitlines()
        if all(word in line for word in words)
        and all(number_in(line, number) for number in numbers)
    ]


@pytest.fixture
def clean_source_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """No proxy or certificate variable is set, in either case."""
    for name in PROXY_AND_CERTIFICATE_VARIABLES:
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.lower(), raising=False)


def real_source(now: Callable[[], datetime]) -> SourceBuild:
    """The `make_source` of `default_wiring()`: construction only, no request."""
    source = default_wiring().make_source(now)
    return source, source.close


def unbuildable_source(
    make_error: Callable[[], BaseException],
) -> Callable[[Callable[[], datetime]], SourceBuild]:
    def build(now: Callable[[], datetime]) -> SourceBuild:
        raise make_error()

    return build


def assert_configuration_message(error_text: str) -> None:
    """The fixed message: the setting kind and the six variable names."""
    for name in PROXY_AND_CERTIFICATE_VARIABLES:
        assert name in error_text, (name, error_text)
    assert names(error_text, r"proxy")
    assert names(error_text, r"certificate")


def assert_nothing_written(rig: Rig) -> None:
    lab = rig.lab
    assert lab.opener.opens == 0
    assert lab.source.calls == []
    assert lab.store.observations == {}
    assert lab.store.objects == {}
    assert lab.database.runs == {}
    assert rig.sources == []


# === source_configuration (AC14, F-03) =========================================

MALFORMED_SETTINGS = [
    pytest.param(
        "HTTPS_PROXY", lambda tmp: "http://[zz]:1", ("[zz]",), id="proxy-bad-url"
    ),
    pytest.param(
        "HTTPS_PROXY",
        lambda tmp: "ftp://proxy.invalid:21",
        ("proxy.invalid", "ftp://"),
        id="proxy-ftp",
    ),
    pytest.param(
        "ALL_PROXY",
        lambda tmp: "socks5://proxy.invalid:1080",
        ("proxy.invalid", "socks5://"),
        id="proxy-socks",
    ),
    pytest.param(
        "SSL_CERT_FILE",
        lambda tmp: str(tmp / "missing.pem"),
        ("missing.pem",),
        id="certificate-missing-file",
    ),
]


@pytest.mark.usefixtures("clean_source_environment")
@pytest.mark.parametrize(("variable", "make_value", "leaks"), MALFORMED_SETTINGS)
def test_source_configuration_a_malformed_setting_exits_2_before_anything_is_written(
    rig: Rig,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    variable: str,
    make_value: Callable[[Path], str],
    leaks: tuple[str, ...],
) -> None:
    """AC14, F-03: the real `make_source` fails on the environment -> exit 2.

    Nothing is migrated, built, requested or written, and the message names the
    six variables and holds no value, path or URL.
    """
    monkeypatch.setenv(variable, make_value(tmp_path))
    rig.source_builder = real_source
    rig.forbid("migrate", "make_store", "make_repository")

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == 2
    assert result.out == ""
    assert_configuration_message(result.err)
    for text in (*leaks, str(tmp_path), PASSWORD_MARKER):
        assert text not in result.err
    assert "Traceback" not in result.err
    assert rig.calls == ["make_source"]
    assert_nothing_written(rig)


@pytest.mark.parametrize(
    "make_error",
    [
        pytest.param(ValueError, id="value-error"),
        pytest.param(OSError, id="os-error"),
        pytest.param(ImportError, id="import-error"),
        pytest.param(SyntheticDefect, id="any-other-exception"),
    ],
)
def test_source_configuration_an_exception_from_make_source_exits_2_naming_no_value(
    rig: Rig, make_error: Callable[[str], BaseException]
) -> None:
    """AC14, F-03: every `Exception` but `MemoryError` is a configuration error."""
    secret = "http://secret-proxy.invalid:8080 synthetic-body-marker"

    def build(now: Callable[[], datetime]) -> SourceBuild:
        error = make_error(secret)
        error.__cause__ = ValueError(f"{HEADER_MARKER} cause")
        raise error

    rig.source_builder = build
    rig.forbid("migrate", "make_store", "make_repository")

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == 2
    assert result.out == ""
    assert_configuration_message(result.err)
    for text in ("secret-proxy", "8080", BODY_MARKER, HEADER_MARKER, PASSWORD_MARKER):
        assert text not in result.err
    assert "Traceback" not in result.err
    assert rig.calls == ["make_source"]
    assert_nothing_written(rig)


def test_source_configuration_a_memory_error_exits_1_naming_only_the_class(
    rig: Rig,
) -> None:
    """Exit table, step 2: `MemoryError` is not a configuration error."""
    rig.source_builder = unbuildable_source(lambda: MemoryError(BODY_MARKER))
    rig.forbid("migrate", "make_store", "make_repository")

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == 1
    assert result.out == ""
    assert "MemoryError" in result.err
    assert BODY_MARKER not in result.err
    assert "Traceback" not in result.err
    assert rig.calls == ["make_source"]
    assert_nothing_written(rig)


def test_source_configuration_a_keyboard_interrupt_exits_130_with_empty_stdout(
    rig: Rig,
) -> None:
    """Exit table, step 2: Ctrl+C while the source is built -> 130."""
    rig.source_builder = unbuildable_source(lambda: KeyboardInterrupt())
    rig.forbid("migrate", "make_store", "make_repository")

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == 130
    assert result.out == ""
    assert rig.calls == ["make_source"]
    assert_nothing_written(rig)


def test_source_configuration_a_system_exit_is_not_caught(rig: Rig) -> None:
    """Step 2: `SystemExit` from the construction propagates to the caller."""
    rig.source_builder = unbuildable_source(lambda: SystemExit(3))
    rig.forbid("migrate", "make_store", "make_repository")

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == 3
    assert result.out == ""
    assert rig.calls == ["make_source"]
    assert_nothing_written(rig)


# === order_of_invocation (AC14, AC16, F-03) ====================================


def test_exit_code_order_of_invocation_the_source_comes_first_then_the_migrations(
    rig: Rig,
) -> None:
    """Step 2 before 3 and 4: `make_source`, `migrate`, then store and repository."""
    result = rig.invoke(SCOPE_ARGS)

    assert result.code == 0
    assert rig.calls == [
        "make_source",
        "migrate",
        "migrate:done",
        "make_store",
        "make_repository",
    ]
    assert [source.closes for source in rig.sources] == [1]


@pytest.mark.usefixtures("restore_logging")
def test_exit_code_order_of_invocation_httpcore_is_guarded_while_the_source_is_built(
    rig: Rig,
) -> None:
    """Step 2.1 before 2.2: `httpcore` is above `DEBUG` when `make_source` runs."""
    levels: list[int] = []

    def build(now: Callable[[], datetime]) -> SourceBuild:
        levels.append(logging.getLogger("httpcore").getEffectiveLevel())
        return rig.lab.source, lambda: None

    rig.source_builder = build
    logging.getLogger().setLevel(logging.DEBUG)
    logging.getLogger("httpcore").setLevel(logging.NOTSET)

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == 0
    assert len(levels) == 1
    assert levels[0] > logging.DEBUG


# === exit_code_cleanup_read_back (AC7, F-02) ===================================


def test_exit_code_cleanup_read_back_an_interrupt_inside_store_exits_130(
    rig: Rig,
) -> None:
    """AC7: Ctrl+C inside `store` before publication -> 130 and `<A> failed`."""
    lab = rig.lab
    rig.store = lab.refuses_to_store(on_call=2, error=lambda: KeyboardInterrupt())

    result = rig.invoke(SCOPE_ARGS)

    run_id = the_run(lab)
    assert result.code == 130
    assert result.out == f"{run_id} failed\n"
    assert lab.database.runs[run_id].status is RunStatus.FAILED
    assert lab.event_types(run_id) == [
        "run-started",
        "page-completed",
        "run-interrupted",
    ]
    assert "Traceback" not in result.err


def test_exit_code_cleanup_read_back_a_memory_error_inside_store_exits_1(
    rig: Rig,
) -> None:
    """AC7, AC15: `MemoryError` there -> 1, `<A> failed`, the class name only."""
    lab = rig.lab
    rig.store = lab.refuses_to_store(on_call=2, error=lambda: MemoryError(BODY_MARKER))

    result = rig.invoke(SCOPE_ARGS)

    run_id = the_run(lab)
    assert result.code == 1
    assert result.out == f"{run_id} failed\n"
    assert "MemoryError" in result.err
    assert BODY_MARKER not in result.err
    assert "Traceback" not in result.err
    assert lab.event_types(run_id) == [
        "run-started",
        "page-completed",
        "unexpected-error",
    ]
    assert same_json(
        lab.details(run_id, "unexpected-error")[0],
        {"page": 2, "error_type": "MemoryError"},
    )


# === exit_code_interrupt_after_finish (AC7, AC11, AC15, F-05) ==================


def test_exit_code_interrupt_after_finish_a_succeeded_run_exits_130_and_prints_succeeded(
    rig: Rig,
) -> None:
    """AC7, AC11: Ctrl+C after the final `finish_run` committed -> `<A> succeeded`."""
    lab = rig.lab
    lab.opener.faults[1] = [
        lab.faults.interrupts("finish_run", detail="succeeded", when="after")
    ]

    result = rig.invoke(SCOPE_ARGS)

    run_id = the_run(lab)
    assert result.code == 130
    assert result.out == f"{run_id} succeeded\n"
    assert lab.database.runs[run_id].status is RunStatus.SUCCEEDED
    assert lab.event_types(run_id) == [
        "run-started",
        "page-completed",
        "page-completed",
    ]


def test_exit_code_interrupt_after_finish_a_failed_run_exits_130_and_prints_failed(
    rig: Rig,
) -> None:
    """AC7, AC11: the same after the failure path's `finish_run(FAILED)`."""
    lab = rig.lab
    lab.source.script(2, lab.status_failure(2, 500))
    lab.opener.faults[1] = [
        lab.faults.interrupts("finish_run", detail="failed", when="after")
    ]

    result = rig.invoke(SCOPE_ARGS)

    run_id = the_run(lab)
    assert result.code == 130
    assert result.out == f"{run_id} failed\n"
    assert lab.event_types(run_id) == ["run-started", "page-completed", "page-failed"]


def test_exit_code_interrupt_after_finish_an_unexpected_exception_exits_1(
    rig: Rig,
) -> None:
    """AC15, K step 1: a `MemoryError` after the commit -> 1 and `<A> succeeded`."""
    lab = rig.lab
    lab.opener.faults[1] = [
        lab.faults.raises(
            "finish_run", lambda: MemoryError(), detail="succeeded", when="after"
        )
    ]

    result = rig.invoke(SCOPE_ARGS)

    run_id = the_run(lab)
    assert result.code == 1
    assert result.out == f"{run_id} succeeded\n"
    assert lab.database.runs[run_id].status is RunStatus.SUCCEEDED
    assert lab.event_types(run_id) == [
        "run-started",
        "page-completed",
        "page-completed",
    ]


# === output_escaping_exception (AC15, F-04) ====================================


def escaping(
    execution_id: str | None, make_error: Callable[[], BaseException]
) -> Callable[..., IngestOutcome]:
    """A `run_ingest` that announces the run (or not) and then raises."""

    def run_ingest_that_raises(
        request: object, *, reporter: IngestReporter, **ports: object
    ) -> IngestOutcome:
        if execution_id is not None:
            reporter.run_started(execution_id)
        raise make_error()

    return run_ingest_that_raises


def _escaping_defect() -> BaseException:
    defect = SyntheticDefect(f"{BODY_MARKER} {PASSWORD_MARKER}")
    defect.__cause__ = ValueError(HEADER_MARKER)
    return defect


ESCAPING = [
    pytest.param(_escaping_defect, 1, "SyntheticDefect", id="synthetic-defect"),
    pytest.param(
        lambda: EvidenceNotFoundError(f"no observation {BODY_MARKER}"),
        1,
        "EvidenceNotFoundError",
        id="project-error",
    ),
    pytest.param(lambda: KeyboardInterrupt(), 130, None, id="keyboard-interrupt"),
]


@pytest.mark.parametrize(("make_error", "code", "class_name"), ESCAPING)
def test_output_escaping_exception_after_the_run_was_announced_prints_it_running(
    rig: Rig,
    monkeypatch: pytest.MonkeyPatch,
    make_error: Callable[[], BaseException],
    code: int,
    class_name: str | None,
) -> None:
    """AC15, P-5: whatever escapes after `run_started`, stdout is `<A> running`."""
    monkeypatch.setattr(ingest_command, "run_ingest", escaping(rig.lab.A, make_error))

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == code
    assert result.out == f"{rig.lab.A} running\n"
    if class_name is not None:
        assert class_name in result.err
    for text in (BODY_MARKER, PASSWORD_MARKER, HEADER_MARKER, "Traceback"):
        assert text not in result.err
    assert "ValueError" not in result.err


@pytest.mark.parametrize(("make_error", "code", "class_name"), ESCAPING)
def test_output_escaping_exception_before_the_run_was_announced_prints_nothing(
    rig: Rig,
    monkeypatch: pytest.MonkeyPatch,
    make_error: Callable[[], BaseException],
    code: int,
    class_name: str | None,
) -> None:
    """AC15: no `run_started`, no run to name: stdout stays empty."""
    monkeypatch.setattr(ingest_command, "run_ingest", escaping(None, make_error))

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == code
    assert result.out == ""
    if class_name is not None:
        assert class_name in result.err
    for text in (BODY_MARKER, PASSWORD_MARKER, HEADER_MARKER, "Traceback"):
        assert text not in result.err


# === output_progress (AC6 c, AC15, F-07) =======================================


def test_output_progress_the_page_lines_reach_stderr(rig: Rig) -> None:
    """Required progress 1: each page, with its sequence, status and content hash."""
    lab = rig.lab

    result = rig.invoke(SCOPE_ARGS)

    run_id = the_run(lab)
    assert result.code == 0
    for sequence in (1, 2):
        digest = lab.database.observations[(run_id, sequence)].content_hash.hexdigest
        assert stderr_lines(result, digest, numbers=(sequence, 200)), result.err
    assert "://" not in result.err


def test_output_progress_a_failed_page_is_named_and_no_marker_appears(rig: Rig) -> None:
    """AC15: with every marker in play, the page line shows and no marker does."""
    lab = rig.lab
    rig.use_transport(_marker_handler(lab, status_of_page_2=429))

    result = rig.invoke(SCOPE_ARGS)

    run_id = the_run(lab)
    digest = lab.database.observations[(run_id, 2)].content_hash.hexdigest
    assert result.code == 1
    assert stderr_lines(result, digest, numbers=(2, 429)), result.err
    for marker in (PASSWORD_MARKER, BODY_MARKER, HEADER_MARKER, COOKIE_NAME):
        assert marker not in result.out
        assert marker not in result.err
    assert "://" not in result.err
    assert "source.invalid" not in result.err


@pytest.mark.parametrize(
    "error", [PersistenceIntegrityError, PersistenceNotFoundError, PersistenceError]
)
def test_output_progress_a_refused_write_names_the_operation_and_the_identity(
    rig: Rig, error: Callable[[str], PersistenceError]
) -> None:
    """AC6 (c): stderr names the refused operation and the run, nothing of the error."""
    lab = rig.lab
    lab.opener.faults[1] = [
        lab.faults.refuses(
            "record_observation",
            lambda: error(f"refused {BODY_MARKER} {HEADER_MARKER}"),
            detail="1",
        )
    ]

    result = rig.invoke(SCOPE_ARGS)

    run_id = the_run(lab)
    assert result.code == 1
    assert result.out == f"{run_id} failed\n"
    assert stderr_lines(result, "record_observation", run_id), result.err
    for text in (BODY_MARKER, HEADER_MARKER, PASSWORD_MARKER, "Traceback"):
        assert text not in result.err


def test_output_progress_a_lost_connection_is_named_on_stderr(rig: Rig) -> None:
    """Required progress 3: the lost operation and the run, no driver text."""
    lab = rig.lab
    lab.opener.faults[1] = [
        lab.faults.lost_before_commit("record_observation", detail="2")
    ]

    result = rig.invoke(SCOPE_ARGS)

    run_id = the_run(lab)
    assert result.code == 1
    assert stderr_lines(result, "record_observation", run_id), result.err
    assert "synthetic:" not in result.err
    assert PASSWORD_MARKER not in result.err


# === chain_unreadable_record_message (AC24, F-06) ==============================


@pytest.mark.parametrize(
    "error", [EvidenceIntegrityError, EvidenceNotFoundError, OSError]
)
def test_chain_unreadable_record_message_names_the_target_on_stderr(
    rig: Rig, error: Callable[[str], BaseException]
) -> None:
    """AC24: an unreadable local record -> exit 1, nothing on stdout, `<A>` on stderr."""
    lab = rig.lab
    lab.seed.run(lab.A, scope=lab.scope(1, 4))
    lab.seed.started(lab.A)
    lab.seed.completed(lab.A, 1, 2)
    store = lab.faulty_reads()
    store.fail_observation(lab.A, 2, lambda: error(f"unreadable {BODY_MARKER}"))
    rig.store = store
    before = lab.snapshot()

    result = rig.invoke(["--resume", lab.A])

    assert result.code == 1
    assert result.out == ""
    assert lab.A in result.err
    assert BODY_MARKER not in result.err
    assert "Traceback" not in result.err
    assert lab.snapshot() == before
    assert lab.source.calls == []


# === Audit round 2 (2026-10-18), findings F-13 to F-16 =========================
#
# Written against the Revision 7 specs. Tokens: `output_database_error` (F-13),
# `pre_run_database_error_exit_code` (F-14, F-15), `exit_code_repository_open_error`
# and `single_result_line` (F-16). The CLI-tier halves of F-16 (a) already hold at
# `91bd69d` (the command's own handlers give the same exit code and stdout): they
# are guards, and their red evidence is at the use-case tier. The tests that are red
# here are the lines of the K cleanup and of `open_repository`, and F-16 (b).

DB_ERRORS = [PersistenceIntegrityError, PersistenceError, PersistenceConnectionError]
# The id `ScriptedExecutionIds` draws first when a test scripts none.
FIRST_DRAWN_ID = "ingest-20261017t150000z-00000001"
INVALID_WORDS = ("invalid", "malformed", "cyclic", "contradictory")


def failing(
    lab: Lab,
    operation: str,
    error: Callable[[str], BaseException],
    *,
    detail: str | None = None,
    nth: int = 1,
    execution_id: str | None = None,
) -> None:
    """The first repository raises `error` on a call; the error text holds a marker."""
    lab.opener.faults.setdefault(1, []).append(
        lab.faults.raises(
            operation,
            lambda: error(f"database text {BODY_MARKER} {HEADER_MARKER}"),
            detail=detail,
            nth=nth,
            execution_id=execution_id,
        )
    )


def assert_safe_stderr(result: Result) -> None:
    for text in (BODY_MARKER, HEADER_MARKER, PASSWORD_MARKER, "Traceback", "://"):
        assert text not in result.err, text


def final_line(result: Result) -> str:
    return result.err.splitlines()[-1]


# === output_database_error (AC7, AC15, F-13) ===================================


@pytest.mark.parametrize("error", DB_ERRORS)
def test_output_database_error_a_refused_interrupt_append_is_named_on_stderr(
    rig: Rig, error: Callable[[str], BaseException]
) -> None:
    """AC15, K: Ctrl+C, then the `run-interrupted` append fails -> 130, `<A> running`.

    Exactly one stderr line names the operation, the event type and the run.
    """
    lab = rig.lab
    lab.source.script(2, KeyboardInterrupt())
    failing(lab, "append_audit_event", error, detail="run-interrupted")

    result = rig.invoke(SCOPE_ARGS)

    run_id = the_run(lab)
    assert result.code == 130
    assert result.out == f"{run_id} running\n"
    assert lab.database.runs[run_id].status is RunStatus.RUNNING
    assert (
        len(stderr_lines(result, "append_audit_event", "run-interrupted", run_id)) == 1
    )
    assert_safe_stderr(result)


@pytest.mark.parametrize("error", DB_ERRORS)
def test_output_database_error_a_failed_closing_after_a_defect_is_named_on_stderr(
    rig: Rig, error: Callable[[str], BaseException]
) -> None:
    """AC15, K: a `MemoryError`, then `finish_run(FAILED)` fails -> 1, `<A> running`."""
    lab = rig.lab
    lab.source.script(2, MemoryError())
    failing(lab, "finish_run", error, detail="failed")

    result = rig.invoke(SCOPE_ARGS)

    run_id = the_run(lab)
    assert result.code == 1
    assert result.out == f"{run_id} running\n"
    assert lab.database.runs[run_id].status is RunStatus.RUNNING
    assert len(stderr_lines(result, "finish_run", "failed", run_id)) == 1
    assert_safe_stderr(result)


def test_output_database_error_a_cleanup_that_cannot_read_the_run_is_named_on_stderr(
    rig: Rig,
) -> None:
    """AC11, AC15, K step 1: the cleanup's `read_run` fails -> nothing is written."""
    lab = rig.lab
    lab.source.script(2, KeyboardInterrupt())
    # The first `read_run` of the new run is the identity check; the second is the
    # cleanup's.
    failing(lab, "read_run", PersistenceError, nth=2, execution_id=FIRST_DRAWN_ID)

    result = rig.invoke(SCOPE_ARGS)

    run_id = the_run(lab)
    assert result.code == 130
    assert result.out == f"{run_id} running\n"
    assert lab.event_types(run_id) == ["run-started", "page-completed"]
    assert len(stderr_lines(result, "read_run", run_id)) == 1
    assert_safe_stderr(result)


# === pre_run_database_error_exit_code (AC9, AC10, AC15, AC24; F-14, F-15) ======


@pytest.mark.parametrize("error", DB_ERRORS)
def test_pre_run_database_error_exit_code_an_unreadable_target_exits_1_not_2(
    rig: Rig, error: Callable[[str], BaseException]
) -> None:
    """State machine T: the target's `read_run` fails -> exit 1, never exit 2.

    stdout stays empty, a stderr line names `read_run` and the target, and the final
    line names the target without calling it invalid.
    """
    lab = rig.lab
    lab.seed.run(lab.A, scope=lab.scope(1, 4))
    lab.seed.started(lab.A)
    lab.seed.completed(lab.A, 1, 2)
    before = lab.snapshot()
    failing(lab, "read_run", error, execution_id=lab.A)

    result = rig.invoke(["--resume", lab.A])

    assert result.code == 1
    assert result.out == ""
    assert stderr_lines(result, "read_run", lab.A), result.err
    assert lab.A in final_line(result)
    assert not any(word in final_line(result).lower() for word in INVALID_WORDS)
    assert_safe_stderr(result)
    assert lab.snapshot() == before
    assert lab.source.calls == []


def test_pre_run_database_error_exit_code_a_lost_reconciliation_write_names_the_run(
    rig: Rig,
) -> None:
    """State machine R: `X` holds a local-only observation 3; recording it is lost.

    exit 1, stdout empty, a line names `record_observation`, `X` and sequence 3, and
    the final line names `X`.
    """
    lab = rig.lab
    lab.seed.run(lab.A, scope=lab.scope(1, 4), status=RunStatus.RUNNING)
    lab.seed.page(lab.A, 1, 1, event=False)
    lab.seed.page(lab.A, 2, 2, event=False)
    lab.seed.page(lab.A, 3, 3, postgres=False, event=False)
    failing(lab, "record_observation", PersistenceConnectionError, detail="3")

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == 1
    assert result.out == ""
    assert stderr_lines(result, "record_observation", lab.A, numbers=(3,)), result.err
    assert lab.A in final_line(result)
    assert final_line(result) != "PersistenceConnectionError"
    assert_safe_stderr(result)
    assert list(lab.database.runs) == [lab.A]
    assert lab.database.runs[lab.A].status is RunStatus.RUNNING
    assert lab.source.calls == []


@pytest.mark.parametrize("error", [PersistenceConnectionError, PersistenceError])
def test_pre_run_database_error_exit_code_a_repository_that_cannot_be_opened_is_named(
    rig: Rig, error: Callable[[str], BaseException]
) -> None:
    """Required progress 2 and 3: `open_repository` fails -> exit 1 and a named line."""
    lab = rig.lab
    rig.repository_error = error(f"database text {BODY_MARKER}")

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == 1
    assert result.out == ""
    assert stderr_lines(result, "open_repository"), result.err
    assert_safe_stderr(result)
    assert lab.database.runs == {}
    assert lab.source.calls == []


# === exit_code_repository_open_error (AC15, F-16 a) ============================
#
# Guards: they hold at `91bd69d` and after the fix, through different code.


def test_exit_code_repository_open_error_a_memory_error_exits_1_naming_the_class(
    rig: Rig,
) -> None:
    """F-16 (a): `MemoryError` while the repository opens -> 1, stdout empty."""
    rig.repository_error = MemoryError(BODY_MARKER)

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == 1
    assert result.out == ""
    assert "MemoryError" in result.err
    assert_safe_stderr(result)
    assert rig.lab.database.runs == {}
    assert rig.lab.source.calls == []
    assert [source.closes for source in rig.sources] == [1]


def test_exit_code_repository_open_error_a_keyboard_interrupt_exits_130_silently(
    rig: Rig,
) -> None:
    """F-16 (a): Ctrl+C while the repository opens -> 130, stdout empty."""
    rig.repository_error = KeyboardInterrupt()

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == 130
    assert result.out == ""
    assert_safe_stderr(result)
    assert rig.lab.database.runs == {}
    assert rig.lab.source.calls == []
    assert [source.closes for source in rig.sources] == [1]


# === single_result_line (AC15, F-16 b) =========================================


def interrupt_when_the_source_closes(rig: Rig) -> None:
    """The source is the lab's, and closing it raises `KeyboardInterrupt`."""

    def interrupted() -> None:
        raise KeyboardInterrupt

    rig.source_builder = lambda now: (rig.lab.source, interrupted)


def test_single_result_line_a_succeeded_run_prints_its_line_once(rig: Rig) -> None:
    """Step 7: Ctrl+C while the source closes -> 130, stdout exactly `<A> succeeded`."""
    interrupt_when_the_source_closes(rig)

    result = rig.invoke(SCOPE_ARGS)

    run_id = the_run(rig.lab)
    assert result.code == 130
    assert result.out == f"{run_id} succeeded\n"
    assert "interrupted" in result.err
    assert [source.closes for source in rig.sources] == [1]


def test_single_result_line_a_failed_run_prints_its_line_once(rig: Rig) -> None:
    """Step 7: the same after a failed run -> stdout exactly `<A> failed`."""
    rig.lab.source.script(2, rig.lab.status_failure(2, 500))
    interrupt_when_the_source_closes(rig)

    result = rig.invoke(SCOPE_ARGS)

    run_id = the_run(rig.lab)
    assert result.code == 130
    assert result.out == f"{run_id} failed\n"
    assert "interrupted" in result.err


def test_single_result_line_an_escaped_exception_prints_running_once(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Step 7: nothing was printed by step 6 -> the one line is `<A> running`."""
    monkeypatch.setattr(
        ingest_command,
        "run_ingest",
        escaping(rig.lab.A, lambda: SyntheticDefect(BODY_MARKER)),
    )
    interrupt_when_the_source_closes(rig)

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == 130
    assert result.out == f"{rig.lab.A} running\n"
    assert BODY_MARKER not in result.err
    assert "Traceback" not in result.err


def test_single_result_line_a_command_that_announced_no_run_prints_nothing(
    rig: Rig,
) -> None:
    """Step 7: no run was announced (a refused migration) -> stdout stays empty."""

    def refused(settings: PostgresSettings, directory: Path) -> tuple[str, ...]:
        raise MigrationLockError("another migration run holds the lock")

    rig.migrate_impl = refused
    interrupt_when_the_source_closes(rig)

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == 130
    assert result.out == ""
    assert "interrupted" in result.err
    assert rig.calls == ["make_source", "migrate"]


# === exit_code_reconnect_* and exit_code_start_run_unconfirmed (F-18, F-19, F-20) ==
#
# Plan Revision 8: a Ctrl+C, a `MemoryError` or another exception that arrives while a
# lost connection is being recovered (the second connection being opened, or the
# exclusion being taken on it) leaves the run `running` and writes nothing to it. The
# result line is `<A> running`, exit 130 for Ctrl+C and 1 otherwise, and exactly one
# stderr line names the operation that raised. While `start_run` itself is the lost
# operation no run was confirmed, so stdout stays empty.

RECOVERY_ERRORS = [
    pytest.param(lambda: KeyboardInterrupt(), 130, id="ctrl-c"),
    pytest.param(lambda: MemoryError(), 1, id="memory-error"),
    pytest.param(
        lambda: SyntheticDefect(f"database text {BODY_MARKER} {HEADER_MARKER}"),
        1,
        id="synthetic-defect",
    ),
]
EXCLUSION_STATES = pytest.mark.parametrize(
    "other_session", [False, True], ids=["exclusion-free", "exclusion-held"]
)
CLEANUP_WORDS = ("run-interrupted", "read_run", "append_audit_event", "finish_run")


def lose_the_second_observation(lab: Lab, *, other_session: bool) -> None:
    """The first connection is lost at observation 2, before the commit.

    With `other_session`, another session takes the exclusion at that moment (the
    auditor's experiment X1).
    """
    lab.opener.faults[1] = [
        lab.faults.lost_before_commit(
            "record_observation",
            detail="2",
            hook=lab.database.hold_exclusion_elsewhere if other_session else None,
        )
    ]


def lose_start_run(lab: Lab, *, other_session: bool) -> None:
    """The first connection is lost at `start_run`, before the commit."""
    lab.opener.faults[1] = [
        lab.faults.lost_before_commit(
            "start_run",
            hook=lab.database.hold_exclusion_elsewhere if other_session else None,
        )
    ]


def assert_the_run_stays_running(result: Result, lab: Lab, code: int) -> str:
    """`<A> running` on stdout, nothing written after the loss, nothing left open."""
    run_id = the_run(lab)
    assert result.code == code
    assert result.out == f"{run_id} running\n"
    assert lab.database.runs[run_id].status is RunStatus.RUNNING
    assert lab.event_types(run_id) == ["run-started", "page-completed"]
    assert lab.sequences(run_id) == (1,)
    assert lab.opener.all_closed
    assert_safe_stderr(result)
    return run_id


@EXCLUSION_STATES
@pytest.mark.parametrize(("make_error", "code"), RECOVERY_ERRORS)
def test_exit_code_reconnect_exclusion_interrupt_prints_running_and_names_the_call(
    rig: Rig,
    make_error: Callable[[], BaseException],
    code: int,
    other_session: bool,
) -> None:
    """F-18: the second exclusion raises -> `<A> running`, 130 for Ctrl+C else 1.

    One stderr line holds `try_acquire_ingest_exclusion`; none holds a cleanup step.
    """
    lab = rig.lab
    lose_the_second_observation(lab, other_session=other_session)
    lab.opener.faults[2] = [
        lab.faults.raises("try_acquire_ingest_exclusion", make_error)
    ]

    result = rig.invoke(SCOPE_ARGS)

    assert_the_run_stays_running(result, lab, code)
    assert len(stderr_lines(result, "try_acquire_ingest_exclusion")) == 1, result.err
    for word in CLEANUP_WORDS:
        assert stderr_lines(result, word) == [], result.err
    assert lab.opener.opens == 2


@EXCLUSION_STATES
@pytest.mark.parametrize(("make_error", "code"), RECOVERY_ERRORS)
def test_exit_code_reconnect_open_interrupt_prints_running_and_names_the_opening(
    rig: Rig,
    make_error: Callable[[], BaseException],
    code: int,
    other_session: bool,
) -> None:
    """F-19: the second `open_repository()` raises -> `<A> running`, 130 or 1.

    One stderr line holds `open_repository`; none names a read of the run.
    """
    lab = rig.lab
    lose_the_second_observation(lab, other_session=other_session)
    lab.opener.open_errors[2] = make_error

    result = rig.invoke(SCOPE_ARGS)

    assert_the_run_stays_running(result, lab, code)
    assert len(stderr_lines(result, "open_repository")) == 1, result.err
    for word in CLEANUP_WORDS:
        assert stderr_lines(result, word) == [], result.err
    assert "RuntimeError" not in result.err
    assert lab.opener.opens == 2


@EXCLUSION_STATES
@pytest.mark.parametrize(("make_error", "code"), RECOVERY_ERRORS)
def test_exit_code_reconnect_exclusion_interrupt_while_start_run_is_lost_prints_nothing(
    rig: Rig,
    make_error: Callable[[], BaseException],
    code: int,
    other_session: bool,
) -> None:
    """`start_run` lost, then the second exclusion raises: no run was confirmed.

    stdout is empty; Ctrl+C gives 130 and anything else 1; one stderr line names the
    call; the run was never announced; nothing is written.
    """
    lab = rig.lab
    lose_start_run(lab, other_session=other_session)
    lab.opener.faults[2] = [
        lab.faults.raises("try_acquire_ingest_exclusion", make_error)
    ]

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == code
    assert result.out == ""
    assert len(stderr_lines(result, "try_acquire_ingest_exclusion")) == 1, result.err
    assert stderr_lines(result, "started") == []
    assert_safe_stderr(result)
    assert lab.database.runs == {}
    assert lab.source.calls == []
    assert lab.opener.opens == 2
    assert lab.opener.all_closed


@EXCLUSION_STATES
@pytest.mark.parametrize(("make_error", "code"), RECOVERY_ERRORS)
def test_exit_code_reconnect_open_interrupt_while_start_run_is_lost_prints_nothing(
    rig: Rig,
    make_error: Callable[[], BaseException],
    code: int,
    other_session: bool,
) -> None:
    """`start_run` lost, then the second `open_repository()` raises: stdout is empty."""
    lab = rig.lab
    lose_start_run(lab, other_session=other_session)
    lab.opener.open_errors[2] = make_error

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == code
    assert result.out == ""
    assert len(stderr_lines(result, "open_repository")) == 1, result.err
    assert stderr_lines(result, "started") == []
    assert_safe_stderr(result)
    assert lab.database.runs == {}
    assert lab.source.calls == []
    assert lab.opener.opens == 2
    assert lab.opener.all_closed


@pytest.mark.parametrize("recovery", ["open-refused", "exclusion-held"])
@pytest.mark.parametrize("when", ["before", "after"])
def test_exit_code_start_run_unconfirmed_prints_running_without_a_started_line(
    rig: Rig, when: str, recovery: str
) -> None:
    """AC8, AC15: `start_run` is lost and the recovery fails -> exit 1, `<id> running`.

    The run was never announced, so stderr has no `run <id> started` line; one line
    names the lost `start_run` and the id.
    """
    lab = rig.lab
    hook = (
        lab.database.hold_exclusion_elsewhere if recovery == "exclusion-held" else None
    )
    lab.opener.faults[1] = [
        lab.faults.lost_before_commit("start_run", hook=hook)
        if when == "before"
        else lab.faults.lost_after_commit("start_run", hook=hook)
    ]
    if recovery == "open-refused":
        lab.opener.fail_opens.add(2)

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == 1
    assert result.out == f"{FIRST_DRAWN_ID} running\n"
    assert f"run {FIRST_DRAWN_ID} started" not in result.err
    assert stderr_lines(result, "started") == []
    assert len(stderr_lines(result, "start_run", FIRST_DRAWN_ID)) == 1, result.err
    assert_safe_stderr(result)
    assert lab.source.calls == []
    assert lab.opener.opens == 2
    assert lab.opener.all_closed


# === Audit round 5 rework (2026-10-20), plan Revisions 9 and 10 ================
#
# Written red against the Revision 12/10/7 specs (approved on 2026-10-20), before the
# round 5 fix. Command-tier tokens: `exit_code_reconnect_close_interrupt` (F-21, E12),
# `exit_code_final_close_error` and `exit_code_final_close_interrupt` (F-22),
# `exit_code_start_run_second_loss` (N-1), `exit_code_unexpected_cleanup_interrupt`
# (N-2), `exit_code_recovery_double_fault` (N-3), `exit_code_refusal_not_retried`
# (N-4), and, for N-7, `result_line_stream_fault` and `handler_stream_fault`.
#
# The close fault of a repository is `lab.opener.close_faults` (conftest). The raising
# stream is `RaisingStream` below, passed to `run_ingest_command` as `stdout` or
# `stderr` through `invoke_through` (the existing injectable `TextIO` parameters: no
# new product seam). Progress lines also go to the injected stderr, so a fault is
# aimed by the text of the write.


class RaisingStream(io.StringIO):
    """A text stream that raises once, on a chosen write (plan Revision 10, seams).

    `trigger` is asked about the text of every write. The `nth` write it accepts
    raises `error()`, after the text was stored (`keep`) or before. It raises once:
    the writes that follow succeed, so the lines written after the failure can be
    seen. `writes` keeps every text it was asked to write, and `fired` tells whether
    it raised. `print` writes the text and the line end in two calls.
    """

    def __init__(
        self,
        error: Callable[[], BaseException],
        trigger: Callable[[str], bool],
        *,
        nth: int = 1,
        keep: bool = True,
    ) -> None:
        super().__init__()
        self._error = error
        self._trigger = trigger
        self._nth = nth
        self._keep = keep
        self._matched = 0
        self.writes: list[str] = []
        self.fired = False

    def write(self, text: str) -> int:
        self.writes.append(text)
        if not self.fired and self._trigger(text):
            self._matched += 1
            if self._matched == self._nth:
                self.fired = True
                if self._keep:
                    super().write(text)
                raise self._error()
        return super().write(text)


class Phase:
    """Tells a trigger whether `run_ingest` has already returned or raised."""

    def __init__(self) -> None:
        self.over = False


def watched(
    phase: Phase, inner: Callable[..., IngestOutcome]
) -> Callable[..., IngestOutcome]:
    """`inner`, which sets `phase.over` when it returns or raises."""

    def run_ingest_watched(*args: object, **kwargs: object) -> IngestOutcome:
        try:
            return inner(*args, **kwargs)
        finally:
            phase.over = True

    return run_ingest_watched


def watch_run_ingest(monkeypatch: pytest.MonkeyPatch) -> Phase:
    """Replace `run_ingest` of the command by itself, watched."""
    phase = Phase()
    original: Callable[..., IngestOutcome] = ingest_command.run_ingest
    monkeypatch.setattr(ingest_command, "run_ingest", watched(phase, original))
    return phase


def after_run_ingest(phase: Phase) -> Callable[[str], bool]:
    """The first text write once `run_ingest` is over: the command's own final text."""
    return lambda text: phase.over and text != "\n"


def invoke_through(rig: Rig, out: io.StringIO, err: io.StringIO) -> int:
    """`run_ingest_command` with the streams given; whatever escapes fails the test."""
    arguments = cli.build_parser().parse_args(["ingest", *SCOPE_ARGS])
    try:
        return run_ingest_command(
            arguments,
            environ=dict(GOOD_ENVIRON),
            wiring=rig.wiring(),
            stdout=out,
            stderr=err,
        )
    except (Exception, KeyboardInterrupt) as error:
        raise AssertionError(
            f"the command let {type(error).__name__} escape"
        ) from error


CLOSE_MOMENTS = pytest.mark.parametrize("when", ["before", "after"])


# === exit_code_reconnect_close_interrupt (F-21, E12) ===========================


@CLOSE_MOMENTS
@pytest.mark.parametrize(
    ("make_error", "code"),
    [
        pytest.param(lambda: KeyboardInterrupt(), 130, id="ctrl-c"),
        pytest.param(lambda: MemoryError(), 1, id="memory-error"),
    ],
)
def test_exit_code_reconnect_close_interrupt_prints_running_and_runs_no_cleanup(
    rig: Rig,
    make_error: Callable[[], BaseException],
    code: int,
    when: Literal["before", "after"],
) -> None:
    """E12: the lost repository's `close()` raises after a loss at page 2.

    `<A> running`, 130 for Ctrl+C and 1 for `MemoryError`; no stderr line names a
    read of the run, `RuntimeError` or `run-interrupted`; no traceback.
    """
    lab = rig.lab
    lose_the_second_observation(lab, other_session=False)
    lab.opener.close_faults[1] = [lab.faults.close_raises(make_error, when=when)]

    result = rig.invoke(SCOPE_ARGS)

    assert_the_run_stays_running(result, lab, code)
    for word in (*CLEANUP_WORDS, "RuntimeError"):
        assert stderr_lines(result, word) == [], result.err
    assert lab.opener.opens == 1


# === exit_code_final_close_error, exit_code_final_close_interrupt (F-22) =======


def test_exit_code_final_close_interrupt_a_succeeded_run_exits_130_and_prints_succeeded(
    rig: Rig,
) -> None:
    """F-22: Ctrl+C while the final repository closes, after the AC1 run.

    Exit 130, stdout exactly one line `<A> succeeded`, stderr says interrupted.
    """
    lab = rig.lab
    lab.opener.close_faults[1] = [
        lab.faults.close_raises(lambda: KeyboardInterrupt(), when="after")
    ]

    result = rig.invoke(SCOPE_ARGS)

    run_id = the_run(lab)
    assert result.code == 130
    assert result.out == f"{run_id} succeeded\n"
    assert "interrupted" in result.err
    assert "Traceback" not in result.err
    assert lab.database.runs[run_id].status is RunStatus.SUCCEEDED
    assert lab.event_types(run_id) == [
        "run-started",
        "page-completed",
        "page-completed",
    ]


def test_exit_code_final_close_interrupt_a_failed_run_exits_130_and_prints_failed(
    rig: Rig,
) -> None:
    """F-22: the same after the AC4 run (page 2 answers 500) -> exactly `<A> failed`."""
    lab = rig.lab
    lab.source.script(2, lab.status_failure(2, 500))
    lab.opener.close_faults[1] = [
        lab.faults.close_raises(lambda: KeyboardInterrupt(), when="after")
    ]

    result = rig.invoke(SCOPE_ARGS)

    run_id = the_run(lab)
    assert result.code == 130
    assert result.out == f"{run_id} failed\n"
    assert "interrupted" in result.err
    assert "Traceback" not in result.err
    assert lab.event_types(run_id) == ["run-started", "page-completed", "page-failed"]


@pytest.mark.parametrize(
    "make_error",
    [
        pytest.param(lambda: OSError("synthetic close failure"), id="os-error"),
        pytest.param(lambda: MemoryError(), id="memory-error"),
    ],
)
def test_exit_code_final_close_error_changes_nothing_exit_0_and_succeeded(
    rig: Rig, make_error: Callable[[], BaseException]
) -> None:
    """F-22: an error from the final close is suppressed: exit 0, `<A> succeeded`.

    No stderr line names the error or says `unexpected error`.
    """
    lab = rig.lab
    lab.opener.close_faults[1] = [lab.faults.close_raises(make_error, when="after")]

    result = rig.invoke(SCOPE_ARGS)

    run_id = the_run(lab)
    assert result.code == 0
    assert result.out == f"{run_id} succeeded\n"
    for text in ("OSError", "MemoryError", "unexpected error", "Traceback"):
        assert text not in result.err, result.err
    assert lab.database.runs[run_id].status is RunStatus.SUCCEEDED


# === exit_code_start_run_second_loss (N-1) =====================================


def lose_start_run_on_both(
    lab: Lab, first: Literal["before", "after"], second: Literal["before", "after"]
) -> None:
    """`start_run` is lost on the first repository and again on the second."""
    for open_index, when in ((1, first), (2, second)):
        lab.opener.faults[open_index] = [
            lab.faults.lost_before_commit("start_run")
            if when == "before"
            else lab.faults.lost_after_commit("start_run")
        ]


@pytest.mark.parametrize(
    ("first", "second"), [("before", "before"), ("before", "after"), ("after", "after")]
)
def test_exit_code_start_run_second_loss_prints_running_without_a_started_line(
    rig: Rig, first: Literal["before", "after"], second: Literal["before", "after"]
) -> None:
    """N-1: the repeat of `start_run` is lost too -> exit 1, stdout `<id> running`.

    The run was never announced, so there is no `run <id> started` line; two lines
    name the lost `start_run`; nothing reads the run.
    """
    lab = rig.lab
    lose_start_run_on_both(lab, first, second)

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == 1
    assert result.out == f"{FIRST_DRAWN_ID} running\n"
    assert f"run {FIRST_DRAWN_ID} started" not in result.err
    assert stderr_lines(result, "started") == []
    assert stderr_lines(result, "read_run") == []
    assert len(stderr_lines(result, "start_run", FIRST_DRAWN_ID)) == 2, result.err
    assert_safe_stderr(result)
    assert lab.source.calls == []
    assert lab.opener.opens == 2
    assert lab.opener.all_closed


@CLOSE_MOMENTS
@pytest.mark.parametrize(
    ("make_error", "code"),
    [
        pytest.param(lambda: KeyboardInterrupt(), 130, id="ctrl-c"),
        pytest.param(lambda: MemoryError(), 1, id="memory-error"),
    ],
)
@pytest.mark.parametrize(
    ("first", "second"), [("before", "before"), ("after", "after")]
)
def test_exit_code_start_run_second_loss_an_error_on_the_second_line_prints_nothing(
    command_rig: Rig,
    first: Literal["before", "after"],
    second: Literal["before", "after"],
    make_error: Callable[[], BaseException],
    code: int,
    when: Literal["before", "after"],
) -> None:
    """N-1: the stderr stream raises on the second write that names `start_run`.

    Ctrl+C gives 130 and `MemoryError` 1; no run was confirmed, so stdout is empty;
    no stderr line names `read_run`; nothing escapes, so no traceback.
    """
    lab = command_rig.lab
    lose_start_run_on_both(lab, first, second)
    out = io.StringIO()
    err = RaisingStream(
        make_error, lambda text: "start_run" in text, nth=2, keep=when == "after"
    )

    result = invoke_through(command_rig, out, err)

    assert err.fired
    assert result == code
    assert out.getvalue() == ""
    assert "read_run" not in err.getvalue()
    assert "started" not in err.getvalue()
    assert "Traceback" not in err.getvalue()
    assert lab.source.calls == []
    assert lab.opener.opens == 2
    assert lab.opener.all_closed


# === exit_code_unexpected_cleanup_interrupt (N-2) ==============================


@pytest.mark.parametrize(
    "make_error",
    [
        pytest.param(lambda: MemoryError(BODY_MARKER), id="memory-error"),
        pytest.param(lambda: SyntheticDefect(BODY_MARKER), id="synthetic-defect"),
    ],
)
def test_exit_code_unexpected_cleanup_interrupt_exits_130_and_prints_running(
    rig: Rig, make_error: Callable[[], BaseException]
) -> None:
    """N-2: an unexpected exception at page 2, then Ctrl+C on the `unexpected-error` append.

    Exit 130, stdout exactly one line `<A> running`, stderr says interrupted and holds
    no marker and no traceback.
    """
    lab = rig.lab
    lab.source.script(2, make_error())
    lab.opener.faults[1] = [
        lab.faults.interrupts("append_audit_event", detail="unexpected-error")
    ]

    result = rig.invoke(SCOPE_ARGS)

    run_id = the_run(lab)
    assert result.code == 130
    assert result.out == f"{run_id} running\n"
    assert "interrupted" in result.err
    assert BODY_MARKER not in result.err
    assert "Traceback" not in result.err
    assert lab.database.runs[run_id].status is RunStatus.RUNNING
    assert lab.event_types(run_id) == ["run-started", "page-completed"]
    assert lab.opener.all_closed


# === exit_code_recovery_double_fault (N-3) =====================================


def test_exit_code_recovery_double_fault_a_ctrl_c_among_two_exceptions_exits_130(
    rig: Rig,
) -> None:
    """N-3, case (a): the second exclusion raises `MemoryError`, its close Ctrl+C.

    Exit 130, stdout exactly `<A> running`, one stderr line holds
    `try_acquire_ingest_exclusion`, none holds `read_run`, `RuntimeError` or
    `run-interrupted`, no traceback.
    """
    lab = rig.lab
    lose_the_second_observation(lab, other_session=False)
    lab.opener.faults[2] = [
        lab.faults.raises("try_acquire_ingest_exclusion", lambda: MemoryError())
    ]
    lab.opener.close_faults[2] = [
        lab.faults.close_raises(lambda: KeyboardInterrupt(), when="after")
    ]

    result = rig.invoke(SCOPE_ARGS)

    assert_the_run_stays_running(result, lab, 130)
    assert len(stderr_lines(result, "try_acquire_ingest_exclusion")) == 1, result.err
    for word in (*CLEANUP_WORDS, "RuntimeError"):
        assert stderr_lines(result, word) == [], result.err
    assert lab.opener.opens == 2


# === exit_code_refusal_not_retried (N-4) =======================================


def refuse_every_call(lab: Lab, operation: str, *, detail: str | None = None) -> None:
    """The first repository refuses each of the next calls of `operation`."""
    lab.opener.faults.setdefault(1, []).extend(
        lab.faults.refuses(
            operation,
            lambda: PersistenceIntegrityError("synthetic refusal"),
            detail=detail,
        )
        for _ in range(3)
    )


def test_exit_code_refusal_not_retried_a_refused_observation_exits_130_and_prints_failed(
    command_rig: Rig,
) -> None:
    """N-4 case (i): Ctrl+C on the line of a refused `record_observation` of sequence 2.

    The cleanup does not record it again, so it closes the run `failed`: exit 130,
    stdout exactly `<A> failed`, no traceback.
    """
    lab = command_rig.lab
    refuse_every_call(lab, "record_observation", detail="2")
    out = io.StringIO()
    err = RaisingStream(
        lambda: KeyboardInterrupt(), lambda text: "record_observation" in text
    )

    result = invoke_through(command_rig, out, err)

    run_id = the_run(lab)
    assert err.fired
    assert result == 130
    assert out.getvalue() == f"{run_id} failed\n"
    assert "Traceback" not in err.getvalue()
    assert lab.database.runs[run_id].status is RunStatus.FAILED
    assert lab.event_types(run_id) == [
        "run-started",
        "page-completed",
        "run-interrupted",
    ]


def test_exit_code_refusal_not_retried_a_refused_failing_finish_exits_130_and_prints_running(
    command_rig: Rig,
) -> None:
    """N-4 case (iv): Ctrl+C on the line of a refused `finish_run(FAILED)` (AC4 path).

    Nothing more is written to the run: exit 130, stdout exactly `<A> running`.
    """
    lab = command_rig.lab
    lab.source.script(2, lab.status_failure(2, 500))
    refuse_every_call(lab, "finish_run", detail="failed")
    out = io.StringIO()
    err = RaisingStream(lambda: KeyboardInterrupt(), lambda text: "finish_run" in text)

    result = invoke_through(command_rig, out, err)

    run_id = the_run(lab)
    assert err.fired
    assert result == 130
    assert out.getvalue() == f"{run_id} running\n"
    assert "Traceback" not in err.getvalue()
    assert lab.database.runs[run_id].status is RunStatus.RUNNING


# === result_line_stream_fault (AC15; sweep N-7) ================================
#
# Plan Revision 10, § Output, "Writing the result", with the human's amendment: an
# exception while the command writes its result keeps the confirmed status, never
# writes a second result line, never touches PostgreSQL and never escapes. A Ctrl+C
# gives 130, any other exception 1 (130 kept when already determined).

STREAM_ERRORS = [
    pytest.param(lambda: KeyboardInterrupt(), 130, id="ctrl-c"),
    pytest.param(lambda: OSError("synthetic stream failure"), 1, id="os-error"),
    pytest.param(lambda: MemoryError(), 1, id="memory-error"),
]
STORING = pytest.mark.parametrize(
    "keep", [True, False], ids=["after-storing", "before-storing"]
)


def assert_the_stored_run_is_as_confirmed(lab: Lab, status: str) -> None:
    """The run keeps its status and nothing was written after the outcome."""
    run_id = the_run(lab)
    assert run_id == FIRST_DRAWN_ID
    assert lab.database.runs[run_id].status is RunStatus(status)
    labels = lab.journal.labels(run_id)
    assert labels[-1] == f"finish_run:{status}"
    assert [label for label in labels if label.startswith("finish_run")] == [labels[-1]]


@STORING
@pytest.mark.parametrize(("make_error", "code"), STREAM_ERRORS)
@pytest.mark.parametrize("status", ["succeeded", "failed"])
def test_result_line_stream_fault_a_failing_final_message_keeps_the_confirmed_status(
    command_rig: Rig,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    make_error: Callable[[], BaseException],
    code: int,
    keep: bool,
) -> None:
    """N-7 (a): stderr raises on the final outcome message, after the run returned.

    The result line is still written once, with the confirmed status: never
    `<A> running`. 130 for Ctrl+C, 1 for any other error; the stored run is as
    confirmed and nothing was written to it after the outcome.
    """
    lab = command_rig.lab
    if status == "failed":
        lab.source.script(2, lab.status_failure(2, 500))
    phase = watch_run_ingest(monkeypatch)
    out = io.StringIO()
    err = RaisingStream(make_error, after_run_ingest(phase), keep=keep)

    result = invoke_through(command_rig, out, err)

    assert err.fired
    assert result == code
    assert out.getvalue() == f"{FIRST_DRAWN_ID} {status}\n"
    assert_the_stored_run_is_as_confirmed(lab, status)
    assert lab.opener.all_closed


STDOUT_MODES = [
    pytest.param("text-after", id="text-after-storing"),
    pytest.param("text-before", id="text-before-storing"),
    pytest.param("line-end", id="line-end"),
]


@pytest.mark.parametrize("mode", STDOUT_MODES)
@pytest.mark.parametrize(("make_error", "code"), STREAM_ERRORS)
def test_result_line_stream_fault_a_failing_result_line_is_attempted_once(
    command_rig: Rig,
    make_error: Callable[[], BaseException],
    code: int,
    mode: str,
) -> None:
    """N-7 (b): stdout raises while the result line `<A> succeeded` is written.

    On the text (after storing it, and before) or on the line end that follows it.
    130 for Ctrl+C, 1 for any other error. stdout holds that one attempt only: the
    line with or without its line end, or nothing; never a second line or `running`.
    The stored run is still `succeeded`.
    """
    lab = command_rig.lab
    line = f"{FIRST_DRAWN_ID} succeeded"
    out = RaisingStream(
        make_error,
        (lambda text: text.endswith("\n"))
        if mode == "line-end"
        else (lambda text: line in text),
        keep=mode != "text-before",
    )
    err = io.StringIO()

    result = invoke_through(command_rig, out, err)

    assert out.fired
    assert result == code
    assert out.getvalue() in {"", line, f"{line}\n"}, out.getvalue()
    assert [text for text in out.writes if "running" in text] == []
    assert_the_stored_run_is_as_confirmed(lab, "succeeded")
    assert lab.opener.all_closed


# === handler_stream_fault (AC15; sweep N-7) ====================================
#
# The command's own handlers for an exception that escaped `run_ingest` after the run
# was announced. `run_ingest` is replaced by a function that announces `<A>` and then
# raises, as in `output_escaping_exception`. A stream that fails inside a handler
# never lets an exception escape, never writes `<A> running` twice, and the exit code
# is 130 for a Ctrl+C, or when it was already determined, and 1 otherwise.

HANDLER_FAULTS = [
    pytest.param(
        lambda: KeyboardInterrupt(),
        "stderr",
        lambda: KeyboardInterrupt(),
        130,
        id="ctrl-c-then-stderr-ctrl-c",
    ),
    pytest.param(
        lambda: KeyboardInterrupt(),
        "stderr",
        lambda: OSError("synthetic stream failure"),
        130,
        id="ctrl-c-then-stderr-os-error",
    ),
    pytest.param(
        lambda: SyntheticDefect(BODY_MARKER),
        "stderr",
        lambda: KeyboardInterrupt(),
        130,
        id="defect-then-stderr-ctrl-c",
    ),
    pytest.param(
        lambda: SyntheticDefect(BODY_MARKER),
        "stderr",
        lambda: OSError("synthetic stream failure"),
        1,
        id="defect-then-stderr-os-error",
    ),
    pytest.param(
        lambda: KeyboardInterrupt(),
        "stdout",
        lambda: KeyboardInterrupt(),
        130,
        id="ctrl-c-then-stdout-ctrl-c",
    ),
    pytest.param(
        lambda: SyntheticDefect(BODY_MARKER),
        "stdout",
        lambda: KeyboardInterrupt(),
        130,
        id="defect-then-stdout-ctrl-c",
    ),
    pytest.param(
        lambda: KeyboardInterrupt(),
        "stdout",
        lambda: OSError("synthetic stream failure"),
        130,
        id="ctrl-c-then-stdout-os-error",
    ),
    pytest.param(
        lambda: SyntheticDefect(BODY_MARKER),
        "stdout",
        lambda: OSError("synthetic stream failure"),
        1,
        id="defect-then-stdout-os-error",
    ),
]


@pytest.mark.parametrize(
    ("make_escape", "broken", "make_error", "code"), HANDLER_FAULTS
)
def test_handler_stream_fault_a_failing_stream_in_a_handler_never_escapes(
    command_rig: Rig,
    monkeypatch: pytest.MonkeyPatch,
    make_escape: Callable[[], BaseException],
    broken: str,
    make_error: Callable[[], BaseException],
    code: int,
) -> None:
    """N-7 (c): `run_ingest` announces `<A>` and raises; a stream fails in the handler.

    `run_ingest_command` returns the code (130 for a Ctrl+C or when already determined,
    1 otherwise), so nothing escapes and no traceback can be printed. A failing stderr
    leaves stdout exactly `<A> running`; a failing stdout holds that one attempt at
    most. `<A> running` is never written twice.
    """
    lab = command_rig.lab
    phase = Phase()
    monkeypatch.setattr(
        ingest_command, "run_ingest", watched(phase, escaping(lab.A, make_escape))
    )
    running = f"{lab.A} running"
    out = io.StringIO()
    err = io.StringIO()
    if broken == "stderr":
        failing_err = RaisingStream(make_error, after_run_ingest(phase))
        err = failing_err
        fired = failing_err
    else:
        failing_out = RaisingStream(make_error, lambda text: running in text)
        out = failing_out
        fired = failing_out

    result = invoke_through(command_rig, out, err)

    assert fired.fired
    assert result == code
    if broken == "stderr":
        assert out.getvalue() == f"{running}\n"
    else:
        assert out.getvalue() in {"", running, f"{running}\n"}, out.getvalue()
        assert len([text for text in fired.writes if "running" in text]) == 1
    assert "Traceback" not in err.getvalue()
    assert BODY_MARKER not in err.getvalue()


# === Audit round 5 rework, step 2 (2026-10-21), plan Revision 11 ================
#
# Written against the Revision 13/11/8 specs (approved on 2026-10-21), before the
# rework of the command and of `main`. Command-tier tokens, by finding:
#
# - F-24 (decision D-1, option A: a `SystemExit` always wins and is preserved):
#   `exit_code_system_exit_final_close` and `system_exit_command_end`;
# - F-23 (decision D-2, option 1: the current behavior): `exit_code_refusal_then_interrupt`;
# - F-26 (decisions D-3 option B, D-4 option 1, D-5 option a: the handler of `main` and
#   the one local parser class): `main_parse_interrupt`, `main_wiring_interrupt`,
#   `main_error_stream_fault` and `main_help_stream_fault`. They go through
#   `main([...])`, with `cli.default_wiring`, `cli.run_ingest_command`,
#   `cli.request_from_arguments` and `cli.version` replaced through `monkeypatch`,
#   and `sys.stdout` and `sys.stderr` replaced by an `io.StringIO` or by the
#   `RaisingStream` of the sweep (no `capsys` there: the test reads the stored text).
#
# No new double and no product seam: the use-case tokens of F-24, F-25 and F-23 are
# in `test_ingest_use_case.py`.


class Raised:
    """A maker of exceptions that remembers each one it made (see the use-case tests)."""

    def __init__(self, make: Callable[[], BaseException]) -> None:
        self._make = make
        self.made: list[BaseException] = []

    def __call__(self) -> BaseException:
        error = self._make()
        self.made.append(error)
        return error

    @property
    def first(self) -> BaseException:
        assert self.made, "the fault never raised"
        return self.made[0]


def interrupt_error() -> BaseException:
    return KeyboardInterrupt()


def memory_error() -> BaseException:
    return MemoryError()


def os_error() -> BaseException:
    return OSError("synthetic stream failure")


def invoke_exiting(rig: Rig, out: io.StringIO, err: io.StringIO) -> SystemExit:
    """`run_ingest_command` with the streams given, which must end through `SystemExit`.

    Return that very object. Any other exception that escapes (a `KeyboardInterrupt`
    included, which would end the whole pytest session) fails the test by name.
    """
    arguments = cli.build_parser().parse_args(["ingest", *SCOPE_ARGS])
    try:
        with pytest.raises(SystemExit) as stop:
            run_ingest_command(
                arguments,
                environ=dict(GOOD_ENVIRON),
                wiring=rig.wiring(),
                stdout=out,
                stderr=err,
            )
    except (Exception, KeyboardInterrupt) as error:
        raise AssertionError(
            f"the command let {type(error).__name__} escape in place of the SystemExit"
        ) from error
    return stop.value


def close_the_source_with(rig: Rig, make_error: Callable[[], BaseException]) -> None:
    """The source is the lab's, and its `close()` raises `make_error()`."""

    def failing_close() -> None:
        raise make_error()

    rig.source_builder = lambda now: (rig.lab.source, failing_close)


# === exit_code_system_exit_final_close (AC7, AC15; F-24, decision D-1) ==========


def assert_a_system_exit_left_quietly(result: Result) -> None:
    """Code 3, stdout empty, and no line of the command on stderr, no traceback."""
    assert result.code == 3
    assert result.out == ""
    for text in ("interrupted", "unexpected error", "Traceback"):
        assert text not in result.err, text


def test_exit_code_system_exit_final_close_after_the_ac1_run_leaves_with_its_code(
    rig: Rig,
) -> None:
    """D-1: the AC1 invocation, the repository's final close raises `SystemExit(3)`.

    The command lets it escape (`Rig` reads code 3): stdout is empty, there is no
    outcome message, no `interrupted` and no `unexpected error`, no traceback; the
    source was closed once and `<A>` is stored `succeeded`.
    """
    lab = rig.lab
    lab.opener.close_faults[1] = [
        lab.faults.close_raises(lambda: SystemExit(3), when="after")
    ]

    result = rig.invoke(SCOPE_ARGS)

    run_id = the_run(lab)
    assert_a_system_exit_left_quietly(result)
    assert "succeeded" not in result.err.splitlines()
    assert [source.closes for source in rig.sources] == [1]
    assert lab.database.runs[run_id].status is RunStatus.SUCCEEDED


def test_exit_code_system_exit_final_close_wins_over_a_ctrl_c_from_the_close(
    rig: Rig,
) -> None:
    """D-1: `SystemExit(3)` at page 2, then Ctrl+C from the final close -> code 3.

    Stdout is empty (no `<A> running`) and stderr does not say `interrupted`.
    """
    lab = rig.lab
    lab.source.script(2, SystemExit(3))
    lab.opener.close_faults[1] = [
        lab.faults.close_raises(interrupt_error, when="after")
    ]

    result = rig.invoke(SCOPE_ARGS)

    run_id = the_run(lab)
    assert_a_system_exit_left_quietly(result)
    assert [source.closes for source in rig.sources] == [1]
    assert lab.database.runs[run_id].status is RunStatus.RUNNING
    assert lab.event_types(run_id) == ["run-started", "page-completed"]


# === system_exit_command_end (AC15; F-24, decision D-1, M5, M14, M15) ===========
#
# Plan § Output, "Writing the result" and "`SystemExit`": a `SystemExit` raised while
# the command writes its result, or at step 7, is preserved and propagated: no further
# write, stdout holds at most the one line already attempted and never `running` for a
# confirmed run, and the exit code is its own.


def assert_the_one_line_attempted(out: io.StringIO, line: str) -> None:
    """Stdout holds at most `line`, once, with or without its line end; never `running`."""
    assert out.getvalue() in {"", line, f"{line}\n"}, out.getvalue()
    assert "running" not in out.getvalue()


@pytest.mark.parametrize("where", ["final-message", "result-line"])
def test_system_exit_command_end_a_system_exit_while_the_result_is_written(
    command_rig: Rig, monkeypatch: pytest.MonkeyPatch, where: str
) -> None:
    """(i): after the AC1 run, `SystemExit(3)` on the final message, then on the line.

    Code 3; stdout holds that one line at most (the order of the two writes is free)
    and never `running`; `<A>` stays `succeeded`; the source is closed once.
    """
    lab = command_rig.lab
    line = f"{FIRST_DRAWN_ID} succeeded"
    exits = Raised(lambda: SystemExit(3))
    out = io.StringIO()
    err = io.StringIO()
    raising: RaisingStream
    if where == "final-message":
        phase = watch_run_ingest(monkeypatch)
        raising = err = RaisingStream(exits, after_run_ingest(phase))
    else:
        raising = out = RaisingStream(exits, lambda text: line in text)

    stop = invoke_exiting(command_rig, out, err)

    assert raising.fired
    assert stop is exits.first
    assert stop.code == 3
    assert_the_one_line_attempted(out, line)
    assert_the_stored_run_is_as_confirmed(lab, "succeeded")
    assert [source.closes for source in command_rig.sources] == [1]


def test_system_exit_command_end_a_system_exit_on_the_line_after_an_error_on_stderr(
    command_rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(j): stderr raises `OSError` on the final message, stdout `SystemExit(3)` on the line."""
    lab = command_rig.lab
    line = f"{FIRST_DRAWN_ID} succeeded"
    exits = Raised(lambda: SystemExit(3))
    phase = watch_run_ingest(monkeypatch)
    err = RaisingStream(os_error, after_run_ingest(phase))
    out = RaisingStream(exits, lambda text: line in text)

    stop = invoke_exiting(command_rig, out, err)

    assert err.fired
    assert out.fired
    assert stop is exits.first
    assert stop.code == 3
    assert_the_one_line_attempted(out, line)
    assert_the_stored_run_is_as_confirmed(lab, "succeeded")
    assert [source.closes for source in command_rig.sources] == [1]


def test_system_exit_command_end_a_system_exit_on_the_interrupted_line(
    command_rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(k): `run_ingest` announces `<A>` and raises Ctrl+C; stderr raises `SystemExit(3)`.

    The write that fails is the `interrupted` line of the handler: code 3, and stdout
    holds `<A> running` at most once.
    """
    lab = command_rig.lab
    monkeypatch.setattr(ingest_command, "run_ingest", escaping(lab.A, interrupt_error))
    exits = Raised(lambda: SystemExit(3))
    out = io.StringIO()
    err = RaisingStream(exits, lambda text: "interrupted" in text)

    stop = invoke_exiting(command_rig, out, err)

    assert err.fired
    assert stop is exits.first
    assert stop.code == 3
    assert out.getvalue() in {"", f"{lab.A} running", f"{lab.A} running\n"}
    assert [source.closes for source in command_rig.sources] == [1]


def test_system_exit_command_end_a_system_exit_wins_over_a_ctrl_c_from_the_source_close(
    command_rig: Rig,
) -> None:
    """(l): `SystemExit(3)` at page 2, then the source's `close()` raises Ctrl+C.

    Code 3, stdout empty (no `<A> running`), no `interrupted` on stderr.
    """
    lab = command_rig.lab
    first = SystemExit(3)
    lab.source.script(2, first)
    close_the_source_with(command_rig, interrupt_error)
    out = io.StringIO()
    err = io.StringIO()

    stop = invoke_exiting(command_rig, out, err)

    assert stop is first
    assert stop.code == 3
    assert out.getvalue() == ""
    assert "interrupted" not in err.getvalue()
    assert [source.closes for source in command_rig.sources] == [1]
    assert lab.database.runs[the_run(lab)].status is RunStatus.RUNNING


def test_system_exit_command_end_a_system_exit_from_the_source_close_keeps_the_line(
    command_rig: Rig,
) -> None:
    """(m): after the AC1 run the source's `close()` raises `SystemExit(3)` -> code 3.

    The result line was written before step 7: stdout is exactly `<A> succeeded`.
    """
    lab = command_rig.lab
    exits = Raised(lambda: SystemExit(3))
    close_the_source_with(command_rig, exits)
    out = io.StringIO()
    err = io.StringIO()

    stop = invoke_exiting(command_rig, out, err)

    assert stop is exits.first
    assert stop.code == 3
    assert out.getvalue() == f"{FIRST_DRAWN_ID} succeeded\n"
    assert_the_stored_run_is_as_confirmed(lab, "succeeded")
    assert [source.closes for source in command_rig.sources] == [1]


# === exit_code_refusal_then_interrupt (AC6 e, AC7, AC15; F-23, decision D-2) ====


def test_exit_code_refusal_then_interrupt_a_refused_failure_event_exits_130_and_prints_failed(
    command_rig: Rig,
) -> None:
    """Case (i): the `page-failed` append is refused and Ctrl+C lands on its line.

    The cleanup audits the interruption and closes the run `failed`: exit 130, stdout
    exactly `<A> failed`, no traceback.
    """
    lab = command_rig.lab
    lab.source.script(2, lab.status_failure(2, 500))
    refuse_every_call(lab, "append_audit_event", detail="page-failed")
    out = io.StringIO()
    err = RaisingStream(
        interrupt_error,
        lambda text: "append_audit_event" in text and "page-failed" in text,
    )

    result = invoke_through(command_rig, out, err)

    run_id = the_run(lab)
    assert err.fired
    assert result == 130
    assert out.getvalue() == f"{run_id} failed\n"
    assert "Traceback" not in err.getvalue()
    assert lab.database.runs[run_id].status is RunStatus.FAILED
    assert lab.event_types(run_id) == [
        "run-started",
        "page-completed",
        "run-interrupted",
    ]


def test_exit_code_refusal_then_interrupt_a_refused_cleanup_append_exits_130_and_prints_running(
    command_rig: Rig,
) -> None:
    """Case (v): the cleanup's own `run-interrupted` append is refused too.

    K stops there and the run stays `running`: exit 130, stdout exactly `<A> running`.
    """
    lab = command_rig.lab
    lab.source.script(2, lab.status_failure(2, 500))
    refuse_every_call(lab, "append_audit_event", detail="page-failed")
    refuse_every_call(lab, "append_audit_event", detail="run-interrupted")
    out = io.StringIO()
    err = RaisingStream(
        interrupt_error,
        lambda text: "append_audit_event" in text and "page-failed" in text,
    )

    result = invoke_through(command_rig, out, err)

    run_id = the_run(lab)
    assert err.fired
    assert result == 130
    assert out.getvalue() == f"{run_id} running\n"
    assert "Traceback" not in err.getvalue()
    assert lab.database.runs[run_id].status is RunStatus.RUNNING
    assert lab.event_types(run_id) == ["run-started", "page-completed"]


# === The handler of `main` (AC14, AC15; F-26, D-3 option B, D-4 option 1, D-5 a) =
#
# Plan § Public names, `interfaces.cli`, "The handler of `main`": one `try` around the
# whole body of `main` with two handlers. A Ctrl+C -> one attempt to write
# `interrupted` on stderr, then `SystemExit(130)`; any other exception (a `MemoryError`,
# or an `OSError` from the write of a usage error) -> one attempt to write
# `unexpected error: <class>`, then `SystemExit(1)`; what that attempt raises: Ctrl+C
# makes it 130, `SystemExit` replaces it, anything else is suppressed. A `SystemExit`
# is never caught. D-5 option a: one local parser class lets the `OSError` that
# `argparse` suppresses reach the handler.


@dataclass
class MainCalls:
    """How many times `main` called what the test replaced."""

    default_wiring: int = 0
    run_ingest_command: int = 0


def watch_main(
    monkeypatch: pytest.MonkeyPatch,
    *,
    wiring: Callable[[], IngestWiring] | None = None,
    run_command: bool = False,
) -> MainCalls:
    """Replace `cli.default_wiring` and `cli.run_ingest_command` by recorders.

    `default_wiring` fails the test when no `wiring` is given. `run_ingest_command` is
    a recorder that returns 0, or, with `run_command`, the real command, called once.
    """
    calls = MainCalls()
    real_command = cli.run_ingest_command

    def watched_wiring() -> IngestWiring:
        calls.default_wiring += 1
        if wiring is None:
            raise AssertionError("main must not build the wiring here")
        return wiring()

    def watched_command(*args: typing.Any, **kwargs: typing.Any) -> int:
        calls.run_ingest_command += 1
        if run_command:
            return real_command(*args, **kwargs)
        return 0

    monkeypatch.setattr(cli, "default_wiring", watched_wiring)
    monkeypatch.setattr(cli, "run_ingest_command", watched_command)
    return calls


def capture_streams(
    monkeypatch: pytest.MonkeyPatch,
    *,
    out: io.StringIO | None = None,
    err: io.StringIO | None = None,
) -> tuple[io.StringIO, io.StringIO]:
    """`sys.stdout` and `sys.stderr` are the streams given (or new `io.StringIO`)."""
    out = io.StringIO() if out is None else out
    err = io.StringIO() if err is None else err
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    return out, err


def run_main(argv: Sequence[str]) -> SystemExit:
    """`main(argv)`, which must end through `SystemExit`: return that very object.

    Any other exception that escapes (a `KeyboardInterrupt` included, which would end
    the whole pytest session) fails the test by name.
    """
    try:
        with pytest.raises(SystemExit) as stop:
            cli.main(list(argv))
    except (Exception, KeyboardInterrupt) as error:
        raise AssertionError(
            f"main let {type(error).__name__} escape in place of the SystemExit"
        ) from error
    return stop.value


def raising(make_error: Callable[[], BaseException]) -> Callable[..., typing.NoReturn]:
    """A function that raises `make_error()` whatever it is called with."""

    def raise_it(*args: object, **kwargs: object) -> typing.NoReturn:
        raise make_error()

    return raise_it


# === main_parse_interrupt (AC14, AC15; F-26, D-3 option B) ======================

PARSE_TRIGGERS = ["request-from-arguments", "version"]


def arm_parse_trigger(
    monkeypatch: pytest.MonkeyPatch,
    trigger: str,
    make_error: Callable[[], BaseException],
) -> list[str]:
    """Make `main` raise `make_error()` while it parses; return the arguments.

    `request-from-arguments`: the ingest arguments of AC1, with the function that
    `_IngestParser` calls inside `parse_args` replaced. `version`: `--version`, with
    the `version` that `build_parser` calls replaced.
    """
    if trigger == "version":
        monkeypatch.setattr(cli, "version", raising(make_error))
        return ["--version"]
    assert trigger == "request-from-arguments"
    monkeypatch.setattr(cli, "request_from_arguments", raising(make_error))
    return ["ingest", *SCOPE_ARGS]


@pytest.mark.parametrize("trigger", PARSE_TRIGGERS)
def test_main_parse_interrupt_a_ctrl_c_exits_130_and_says_interrupted(
    monkeypatch: pytest.MonkeyPatch, trigger: str
) -> None:
    """D-3: Ctrl+C while `main` parses -> code 130, stdout empty, `interrupted` once.

    No traceback; the wiring is not built and the command is not run.
    """
    calls = watch_main(monkeypatch)
    out, err = capture_streams(monkeypatch)
    argv = arm_parse_trigger(monkeypatch, trigger, interrupt_error)

    stop = run_main(argv)

    assert stop.code == 130
    assert out.getvalue() == ""
    assert err.getvalue().count("interrupted") == 1, err.getvalue()
    for text in ("Traceback", "KeyboardInterrupt"):
        assert text not in err.getvalue()
    assert calls == MainCalls()


@pytest.mark.parametrize("trigger", PARSE_TRIGGERS)
def test_main_parse_interrupt_a_memory_error_exits_1_naming_only_the_class(
    monkeypatch: pytest.MonkeyPatch, trigger: str
) -> None:
    """D-3, D-4: a `MemoryError` while `main` parses -> code 1, `unexpected error: MemoryError`.

    Once on stderr, nothing else of the error; stdout empty; nothing is built or run.
    """
    calls = watch_main(monkeypatch)
    out, err = capture_streams(monkeypatch)
    argv = arm_parse_trigger(monkeypatch, trigger, memory_error)

    stop = run_main(argv)

    assert stop.code == 1
    assert out.getvalue() == ""
    assert err.getvalue().count("unexpected error: MemoryError") == 1, err.getvalue()
    assert err.getvalue().count("MemoryError") == 1
    assert "Traceback" not in err.getvalue()
    assert calls == MainCalls()


@pytest.mark.parametrize("trigger", PARSE_TRIGGERS)
def test_main_parse_interrupt_a_system_exit_is_preserved(
    monkeypatch: pytest.MonkeyPatch, trigger: str
) -> None:
    """D-1: `SystemExit(3)` while `main` parses leaves `main` as that same object."""
    calls = watch_main(monkeypatch)
    out, err = capture_streams(monkeypatch)
    exits = Raised(lambda: SystemExit(3))
    argv = arm_parse_trigger(monkeypatch, trigger, exits)

    stop = run_main(argv)

    assert stop is exits.first
    assert stop.code == 3
    assert out.getvalue() == ""
    for text in ("interrupted", "unexpected error", "Traceback"):
        assert text not in err.getvalue(), text
    assert calls == MainCalls()


# === main_wiring_interrupt (AC14, AC15; F-26, D-3 option B) =====================


@pytest.mark.parametrize(
    ("make_error", "code", "handler_line"),
    [
        pytest.param(interrupt_error, 130, "interrupted", id="ctrl-c"),
        pytest.param(
            memory_error, 1, "unexpected error: MemoryError", id="memory-error"
        ),
    ],
)
def test_main_wiring_interrupt_an_exception_while_the_wiring_is_built_ends_through_the_handler(
    monkeypatch: pytest.MonkeyPatch,
    make_error: Callable[[], BaseException],
    code: int,
    handler_line: str,
) -> None:
    """D-3: `default_wiring()` raises Ctrl+C or `MemoryError` -> code 130 or 1.

    Stdout is empty and the handler's line is on stderr once; the command is not run;
    nothing is built; no traceback.
    """
    calls = watch_main(monkeypatch, wiring=raising(make_error))
    out, err = capture_streams(monkeypatch)

    stop = run_main(["ingest", *SCOPE_ARGS])

    assert stop.code == code
    assert out.getvalue() == ""
    assert err.getvalue().count(handler_line) == 1, err.getvalue()
    assert "Traceback" not in err.getvalue()
    assert calls == MainCalls(default_wiring=1, run_ingest_command=0)


def test_main_wiring_interrupt_a_system_exit_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-1: `SystemExit(3)` from `default_wiring()` leaves `main` as that same object."""
    exits = Raised(lambda: SystemExit(3))
    calls = watch_main(monkeypatch, wiring=raising(exits))
    out, err = capture_streams(monkeypatch)

    stop = run_main(["ingest", *SCOPE_ARGS])

    assert stop is exits.first
    assert stop.code == 3
    assert out.getvalue() == ""
    for text in ("interrupted", "unexpected error", "Traceback"):
        assert text not in err.getvalue(), text
    assert calls == MainCalls(default_wiring=1, run_ingest_command=0)


# === main_error_stream_fault (AC14, AC15; F-26, D-3, D-4, D-5 option a) =========
#
# `sys.stderr` is the `RaisingStream` of the sweep. (a) `main(["ingest", "--last-page",
# "2"])`: `_IngestParser` calls `parser.error`, whose `print_usage` writes the usage.
# (b) `main([])`: the bare command's `print_usage`. (c) The ingest arguments of AC1
# with `POSTGRES_DB` unset: `run_ingest_command` writes `error: POSTGRES_DB is not set`.

ERROR_STREAM_CASES = ["a", "b", "c"]
ERROR_STREAM_MARKERS = {
    "a": "usage:",
    "b": "usage:",
    "c": "POSTGRES_DB is not set",
}


def arm_error_stream_case(
    rig: Rig, monkeypatch: pytest.MonkeyPatch, case: str
) -> tuple[MainCalls, list[str]]:
    """Set what `main` sees in one case of F-26; return the recorders and the arguments."""
    if case == "c":
        for name in POSTGRES_VARIABLES:
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setenv("POSTGRES_USER", GOOD_ENVIRON["POSTGRES_USER"])
        monkeypatch.setenv("POSTGRES_PASSWORD", GOOD_ENVIRON["POSTGRES_PASSWORD"])
        rig.forbid("make_source", "migrate", "make_store", "make_repository")
        calls = watch_main(monkeypatch, wiring=rig.wiring, run_command=True)
        return calls, ["ingest", *SCOPE_ARGS]
    calls = watch_main(monkeypatch)
    if case == "a":
        return calls, ["ingest", "--last-page", "2"]
    assert case == "b"
    return calls, []


def assert_nothing_was_built_by_main(rig: Rig, calls: MainCalls, case: str) -> None:
    """Nothing was built; the command ran only in (c), once, and built nothing."""
    assert rig.calls == []
    assert calls.run_ingest_command == (1 if case == "c" else 0)
    assert calls.default_wiring == (1 if case == "c" else 0)


@pytest.mark.parametrize("case", ERROR_STREAM_CASES)
def test_main_error_stream_fault_with_working_streams_a_parse_error_still_exits_2(
    command_rig: Rig, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    """Control: with working streams the same three calls give 2, as today."""
    calls, argv = arm_error_stream_case(command_rig, monkeypatch, case)
    out, err = capture_streams(monkeypatch)

    stop = run_main(argv)

    assert stop.code == 2
    assert out.getvalue() == ""
    assert ERROR_STREAM_MARKERS[case] in err.getvalue()
    assert_nothing_was_built_by_main(command_rig, calls, case)


@pytest.mark.parametrize("keep", [True, False], ids=["after-storing", "before-storing"])
@pytest.mark.parametrize(
    ("make_error", "code", "handler_line"),
    [
        pytest.param(interrupt_error, 130, "interrupted", id="ctrl-c"),
        pytest.param(
            memory_error, 1, "unexpected error: MemoryError", id="memory-error"
        ),
        pytest.param(os_error, 1, "unexpected error: OSError", id="os-error"),
    ],
)
@pytest.mark.parametrize("case", ERROR_STREAM_CASES)
def test_main_error_stream_fault_a_failing_write_of_a_parse_error_ends_through_the_handler(
    command_rig: Rig,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    make_error: Callable[[], BaseException],
    code: int,
    handler_line: str,
    keep: bool,
) -> None:
    """D-3, D-4, D-5: the write of a usage error fails -> 130 for Ctrl+C, else 1.

    The faulted message is attempted once and never written again; the handler's line
    is on the same stream once; stdout is empty; no traceback; nothing is built, and
    the command ran only in (c). An `OSError` in (a) and (b) is one `argparse` would
    suppress, so it reaches the handler only through the one local parser class.
    """
    marker = ERROR_STREAM_MARKERS[case]
    calls, argv = arm_error_stream_case(command_rig, monkeypatch, case)
    err = RaisingStream(make_error, lambda text: marker in text, keep=keep)
    out, _ = capture_streams(monkeypatch, err=err)

    stop = run_main(argv)

    assert err.fired
    assert stop.code == code
    assert out.getvalue() == ""
    assert len([text for text in err.writes if marker in text]) == 1, err.writes
    assert err.getvalue().count(marker) <= 1
    assert err.getvalue().count(handler_line) == 1, err.getvalue()
    assert "Traceback" not in err.getvalue()
    assert_nothing_was_built_by_main(command_rig, calls, case)


@pytest.mark.parametrize("keep", [True, False], ids=["after-storing", "before-storing"])
@pytest.mark.parametrize("case", ERROR_STREAM_CASES)
def test_main_error_stream_fault_a_system_exit_from_the_write_is_preserved(
    command_rig: Rig, monkeypatch: pytest.MonkeyPatch, case: str, keep: bool
) -> None:
    """D-1: `SystemExit(3)` from the write of a usage error leaves `main` as that object.

    No handler line (`interrupted`, `unexpected error`) is written for it.
    """
    marker = ERROR_STREAM_MARKERS[case]
    calls, argv = arm_error_stream_case(command_rig, monkeypatch, case)
    exits = Raised(lambda: SystemExit(3))
    err = RaisingStream(exits, lambda text: marker in text, keep=keep)
    out, _ = capture_streams(monkeypatch, err=err)

    stop = run_main(argv)

    assert err.fired
    assert stop is exits.first
    assert stop.code == 3
    assert out.getvalue() == ""
    assert len([text for text in err.writes if marker in text]) == 1, err.writes
    for text in ("interrupted", "unexpected error", "Traceback"):
        assert text not in err.getvalue(), text
    assert_nothing_was_built_by_main(command_rig, calls, case)


# === main_help_stream_fault (AC14, AC15; F-26, D-3, D-5 option a) ===============
#
# `--version`, `--help` and `ingest --help` write on stdout through `argparse`'s own
# `_print_message`, which suppresses an `OSError`. The main parser and the `ingest`
# subparser are both of the one local parser class, so the `OSError` reaches the
# handler of `main`. `argparse` itself is not patched.

HELP_CASES = [
    pytest.param(
        ["--version"], lambda text: "ec-procurement-quality" in text, id="version"
    ),
    pytest.param(["--help"], lambda text: "usage:" in text, id="help"),
    pytest.param(["ingest", "--help"], lambda text: "usage:" in text, id="ingest-help"),
]
STANDARD_PRINT_MESSAGE = argparse.ArgumentParser._print_message


@pytest.mark.parametrize(("argv", "trigger"), HELP_CASES)
def test_main_help_stream_fault_with_working_streams_the_text_goes_to_stdout(
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    trigger: Callable[[str], bool],
) -> None:
    """Control (CLI-1): exit 0 and the text as today on stdout; stderr is empty."""
    calls = watch_main(monkeypatch)
    out, err = capture_streams(monkeypatch)

    stop = run_main(argv)

    assert stop.code == 0
    assert trigger(out.getvalue())
    if argv == ["--version"]:
        assert (
            out.getvalue()
            == f"ec-procurement-quality {installed_version('ec-procurement-quality')}\n"
        )
    else:
        assert out.getvalue().startswith("usage:")
    assert err.getvalue() == ""
    assert calls == MainCalls()


@pytest.mark.parametrize("keep", [True, False], ids=["after-storing", "before-storing"])
@pytest.mark.parametrize(
    ("make_error", "code", "handler_line"),
    [
        pytest.param(os_error, 1, "unexpected error: OSError", id="os-error"),
        pytest.param(interrupt_error, 130, "interrupted", id="ctrl-c"),
        pytest.param(
            memory_error, 1, "unexpected error: MemoryError", id="memory-error"
        ),
    ],
)
@pytest.mark.parametrize(("argv", "trigger"), HELP_CASES)
def test_main_help_stream_fault_a_failing_stdout_ends_through_the_handler(
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    trigger: Callable[[str], bool],
    make_error: Callable[[], BaseException],
    code: int,
    handler_line: str,
    keep: bool,
) -> None:
    """D-3, D-5: the write of the help or version text fails -> 1 (130 for Ctrl+C).

    The text is attempted once on stdout and never again; stderr holds exactly the
    handler's line, once; no traceback; nothing is built and the command is not run.
    """
    calls = watch_main(monkeypatch)
    out = RaisingStream(make_error, trigger, keep=keep)
    _, err = capture_streams(monkeypatch, out=out)

    stop = run_main(argv)

    assert out.fired
    assert stop.code == code
    assert len([text for text in out.writes if trigger(text)]) == 1, out.writes
    assert err.getvalue().splitlines() == [handler_line]
    assert calls == MainCalls()


@pytest.mark.parametrize("keep", [True, False], ids=["after-storing", "before-storing"])
@pytest.mark.parametrize(("argv", "trigger"), HELP_CASES)
def test_main_help_stream_fault_a_system_exit_from_stdout_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    trigger: Callable[[str], bool],
    keep: bool,
) -> None:
    """D-1: `SystemExit(3)` from the write of the text leaves `main` as that object.

    No handler line is written for it.
    """
    calls = watch_main(monkeypatch)
    exits = Raised(lambda: SystemExit(3))
    out = RaisingStream(exits, trigger, keep=keep)
    _, err = capture_streams(monkeypatch, out=out)

    stop = run_main(argv)

    assert out.fired
    assert stop is exits.first
    assert stop.code == 3
    assert len([text for text in out.writes if trigger(text)]) == 1, out.writes
    assert err.getvalue() == ""
    assert calls == MainCalls()


@pytest.mark.parametrize(("argv", "trigger"), HELP_CASES)
def test_main_help_stream_fault_a_failing_stderr_in_the_handler_attempts_nothing_more(
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    trigger: Callable[[str], bool],
) -> None:
    """Stdout and the handler's own line both fail with `OSError` -> code 1, no traceback.

    Each is attempted once: the handler's line is not written again anywhere.
    """
    calls = watch_main(monkeypatch)
    out = RaisingStream(os_error, trigger)
    err = RaisingStream(os_error, lambda text: "unexpected error" in text)
    capture_streams(monkeypatch, out=out, err=err)

    stop = run_main(argv)

    assert out.fired
    assert err.fired
    assert stop.code == 1
    assert len([text for text in out.writes if trigger(text)]) == 1, out.writes
    assert len([text for text in err.writes if "unexpected error" in text]) == 1
    assert "Traceback" not in out.getvalue() + err.getvalue()
    assert calls == MainCalls()


def test_main_help_stream_fault_argparse_itself_is_not_patched() -> None:
    """`argparse.ArgumentParser._print_message` is the standard library's own function.

    The product adapts one local parser class; it never patches `argparse`.
    """
    cli.build_parser()

    method = argparse.ArgumentParser._print_message
    assert method is STANDARD_PRINT_MESSAGE
    assert method.__module__ == "argparse"
    assert (
        Path(method.__code__.co_filename).resolve() == Path(argparse.__file__).resolve()
    )


# === Audit round 6 rework (2026-10-23), plan Revision 12 ========================
#
# Feature ingest-command (F4), outcome O10, rework of round 6. Written red against the
# Revision 14/12/9 specs (approved on 2026-10-23), before the protected write, the
# neutralizing of a failed stream and the last flush of `main` exist. Tokens, by
# finding:
#
# - F-27, in process (option (b)): `flush_stream_fault`. Every output is written and
#   flushed in its one attempt, so a failure that a buffered stream shows only at the
#   flush gives the planned exit code. The stream is the `RaisingStream` of the sweep
#   extended with a fault on the n-th `flush()` after a matching write
#   (`FlushFaultStream`: its write faults are unchanged). The real closed pipe is the
#   process tier (`tests/process/`), not this file.
# - F-27, decision D-10: `neutralize_fault`. The neutralizing of a failed stream
#   (`os.open` of the null device, `os.dup2`) fails, succeeds, or has no descriptor to
#   act on. The descriptor is one the test opened on a file in `tmp_path` (never 0, 1
#   or 2) and `os.open` and `os.dup2` are replaced by recorders that never touch a
#   standard descriptor.
# - F-28 (D-1, D-3, D-4): `main_handler_line_fault` (a Ctrl+C or a `SystemExit` while
#   `main`'s handler writes its own line) and `exit_code_cleanup_system_exit` (State
#   machine K never turns a `SystemExit` into an outcome); the use-case tokens
#   `system_exit_first_wins`, `window_system_exit_line` and `cleanup_system_exit` are in
#   `test_ingest_use_case.py`. They protect behavior that already holds.
# - F-29: the two renamed tests of `main_error_stream_fault` (no `usage` in a name).


_KEPT_ALIVE: list[object] = []


class FlushFaultStream(RaisingStream):
    """A `RaisingStream` whose `flush()` raises after a matching write (Revision 12).

    `after` is asked about the text of every write; once a write whose text it accepts
    was stored the stream is armed, and its `flush()` calls are counted from 1. The
    armed call number `flush_nth + i` raises `flush_errors[i]()`; every other call
    succeeds. Its write faults are the base class's and none is set: it never raises
    from `write`. `fileno()` returns `descriptor` when one is given, else the
    `io.UnsupportedOperation` of an `io.StringIO`. `flush_faults` keeps the exceptions
    it raised, `flushes` counts every `flush()` call.
    """

    def __init__(
        self,
        flush_errors: Sequence[Callable[[], BaseException]],
        after: Callable[[str], bool],
        *,
        flush_nth: int = 1,
        descriptor: int | None = None,
    ) -> None:
        super().__init__(
            lambda: AssertionError("a FlushFaultStream has no write fault"),
            lambda text: False,
        )
        self._flush_errors = list(flush_errors)
        self._after = after
        self._flush_nth = flush_nth
        self._descriptor = descriptor
        self._armed = False
        self._armed_flushes = 0
        self.flushes = 0
        self.flush_faults: list[BaseException] = []
        if descriptor is not None:
            # A stream with a descriptor must not share an identity with a later test's.
            _KEPT_ALIVE.append(self)

    def write(self, text: str) -> int:
        count = super().write(text)
        if self._after(text):
            self._armed = True
        return count

    def flush(self) -> None:
        self.flushes += 1
        super().flush()
        if not self._armed:
            return
        self._armed_flushes += 1
        index = self._armed_flushes - self._flush_nth
        if 0 <= index < len(self._flush_errors):
            error = self._flush_errors[index]()
            self.flush_faults.append(error)
            raise error

    def fileno(self) -> int:
        if self._descriptor is None:
            return super().fileno()
        return self._descriptor

    @property
    def flush_fired(self) -> bool:
        return bool(self.flush_faults)


class Redirections:
    """What the product asked of `os.open` (the null device) and of `os.dup2`."""

    def __init__(self) -> None:
        self.null_device_opens: list[str] = []
        self.copies: list[tuple[int, int]] = []


def record_redirections(
    monkeypatch: pytest.MonkeyPatch,
    *,
    open_error: Callable[[], BaseException] | None = None,
    copy_error: Callable[[], BaseException] | None = None,
) -> Redirections:
    """Replace `os.open` and `os.dup2` by recorders that touch no standard descriptor.

    `os.dup2` records the call and does nothing (it raises `copy_error()` when given),
    so no descriptor, standard or not, is ever redirected by the product. Pytest's own
    capture also uses `os.dup2` to restore the standard descriptors between the phases
    of a test, so a call made from a `_pytest` module is passed on to the real one and
    is not recorded. `os.open` delegates to the real one for every path, and for the
    null device it records the call first and raises `open_error()` when given. A test
    checks the targets afterwards: an assertion raised inside the recorder could be
    absorbed by the product.
    """
    redirections = Redirections()
    real_open = os.open
    real_dup2 = os.dup2

    def recording_open(
        path: typing.Any, flags: int, *args: typing.Any, **kwargs: typing.Any
    ) -> int:
        if os.fspath(path) == os.devnull:
            redirections.null_device_opens.append(os.devnull)
            if open_error is not None:
                raise open_error()
        return real_open(path, flags, *args, **kwargs)

    def recording_dup2(
        source: int, target: int, *args: typing.Any, **kwargs: typing.Any
    ) -> int:
        if sys._getframe(1).f_globals.get("__name__", "").startswith("_pytest"):
            return real_dup2(source, target, *args, **kwargs)
        redirections.copies.append((source, target))
        if copy_error is not None:
            raise copy_error()
        return target

    monkeypatch.setattr(os, "open", recording_open)
    monkeypatch.setattr(os, "dup2", recording_dup2)
    return redirections


@pytest.fixture
def owned_descriptor(tmp_path: Path, request: pytest.FixtureRequest) -> int:
    """A descriptor this test opened on a file in `tmp_path`: never 0, 1 or 2.

    It stays open until the end of the session, so that no later test is given the
    same number (a record kept by the product per stream cannot then meet it twice).
    """
    descriptor = os.open(
        tmp_path / "owned-stream.bin",
        os.O_WRONLY | os.O_CREAT | getattr(os, "O_BINARY", 0),
    )
    assert descriptor > 2
    request.config.add_cleanup(lambda: _close_quietly(descriptor))
    return descriptor


def _close_quietly(descriptor: int) -> None:
    try:
        os.close(descriptor)
    except OSError:
        pass


def version_text() -> str:
    return f"ec-procurement-quality {installed_version('ec-procurement-quality')}\n"


def is_version_text(text: str) -> bool:
    return text == version_text()


SYNTHETIC_RESULT_LINE = "synthetic result line\n"
SYNTHETIC_MESSAGE_LINE = "synthetic message line\n"


def arm_command_that_writes_without_flushing(
    monkeypatch: pytest.MonkeyPatch, rig: Rig, *, code: int = 0
) -> None:
    """`main(["ingest", ...])` runs a command that writes one line on each stream.

    The command does not flush: the only flush that follows its writes is the last
    flush of `main`. It returns `code`, so `main` ends with its own `SystemExit`.
    """

    def command(
        arguments: argparse.Namespace,
        *,
        environ: Mapping[str, str],
        wiring: IngestWiring,
        stdout: typing.TextIO,
        stderr: typing.TextIO,
    ) -> int:
        stdout.write(SYNTHETIC_RESULT_LINE)
        stderr.write(SYNTHETIC_MESSAGE_LINE)
        return code

    monkeypatch.setattr(cli, "default_wiring", rig.wiring)
    monkeypatch.setattr(cli, "run_ingest_command", command)


# === flush_stream_fault (AC14, AC15; F-27, in process) =========================
#
# Plan Revision 12, § Public names, "Protected writes and the last flush": every output
# is written and flushed inside its one attempt, so a flush that fails is handled where
# a write that fails is today. In a real process a `print` only fills a buffer, so
# these tests aim the fault at `flush()`, after the text was stored. In process no
# stream has a descriptor, so nothing is redirected: the `os.dup2` recorder stays empty.

FLUSH_ERRORS = [
    pytest.param(lambda: OSError("synthetic stream failure"), 1, id="os-error"),
    pytest.param(lambda: BrokenPipeError("synthetic broken pipe"), 1, id="broken-pipe"),
    pytest.param(
        lambda: ValueError("I/O operation on closed file."), 1, id="closed-file"
    ),
    pytest.param(lambda: KeyboardInterrupt(), 130, id="ctrl-c"),
]


@pytest.mark.parametrize(("make_error", "code"), FLUSH_ERRORS)
def test_flush_stream_fault_a_failing_flush_after_a_succeeded_result_line(
    command_rig: Rig,
    monkeypatch: pytest.MonkeyPatch,
    make_error: Callable[[], BaseException],
    code: int,
) -> None:
    """(a) AC14, AC15: stdout's flush raises after `<A> succeeded` was stored.

    1 (130 for Ctrl+C); stdout holds `<A> succeeded` once, never `running` or a second
    line; stderr holds the outcome message; `<A>` stays `succeeded` with nothing
    written after the outcome; nothing is redirected.
    """
    lab = command_rig.lab
    redirections = record_redirections(monkeypatch)
    line = f"{FIRST_DRAWN_ID} succeeded"
    out = FlushFaultStream([make_error], lambda text: line in text)
    err = io.StringIO()

    result = invoke_through(command_rig, out, err)

    assert result == code
    assert out.flush_fired
    assert out.getvalue() == f"{line}\n"
    assert [text for text in out.writes if "running" in text] == []
    assert "succeeded" in err.getvalue().splitlines()
    assert_the_stored_run_is_as_confirmed(lab, "succeeded")
    assert lab.opener.all_closed
    assert redirections.copies == []


def test_flush_stream_fault_a_system_exit_in_the_flush_after_a_result_line(
    command_rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(a) D-1: `SystemExit(3)` from stdout's flush leaves the command as that object.

    The result line was stored once; the stored run is as confirmed.
    """
    lab = command_rig.lab
    redirections = record_redirections(monkeypatch)
    line = f"{FIRST_DRAWN_ID} succeeded"
    exits = Raised(lambda: SystemExit(3))
    out = FlushFaultStream([exits], lambda text: line in text)
    err = io.StringIO()

    stop = invoke_exiting(command_rig, out, err)

    assert out.flush_fired
    assert stop is exits.first
    assert stop.code == 3
    assert out.getvalue() == f"{line}\n"
    assert_the_stored_run_is_as_confirmed(lab, "succeeded")
    assert redirections.copies == []


@pytest.mark.parametrize(
    ("ending", "code"),
    [
        pytest.param("failed-page", 1, id="failed-run"),
        pytest.param("ctrl-c", 130, id="ended-by-ctrl-c"),
    ],
)
def test_flush_stream_fault_a_failing_flush_after_a_failed_result_line(
    command_rig: Rig, monkeypatch: pytest.MonkeyPatch, ending: str, code: int
) -> None:
    """(b) AC14, AC15: stdout's flush raises after `<A> failed` was stored.

    A failed run (page 2 answers 500) gives 1; a run ended by Ctrl+C at page 2 gives
    130, already determined. Stdout holds `<A> failed` once; the stored run is
    `failed` with nothing written after the outcome.
    """
    lab = command_rig.lab
    redirections = record_redirections(monkeypatch)
    if ending == "failed-page":
        lab.source.script(2, lab.status_failure(2, 500))
    else:
        lab.source.script(2, KeyboardInterrupt())
    line = f"{FIRST_DRAWN_ID} failed"
    out = FlushFaultStream([os_error], lambda text: line in text)
    err = io.StringIO()

    result = invoke_through(command_rig, out, err)

    assert result == code
    assert out.flush_fired
    assert out.getvalue() == f"{line}\n"
    assert_the_stored_run_is_as_confirmed(lab, "failed")
    assert lab.opener.all_closed
    assert redirections.copies == []


def test_flush_stream_fault_a_failing_flush_of_the_final_message_keeps_the_result_line(
    command_rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(c) AC14, AC15: stderr's flush raises after the final message was stored.

    1; stdout is exactly `<A> succeeded`; the stored run is as confirmed.
    """
    lab = command_rig.lab
    redirections = record_redirections(monkeypatch)
    phase = watch_run_ingest(monkeypatch)
    out = io.StringIO()
    err = FlushFaultStream([os_error], after_run_ingest(phase))

    result = invoke_through(command_rig, out, err)

    assert result == 1
    assert err.flush_fired
    assert out.getvalue() == f"{FIRST_DRAWN_ID} succeeded\n"
    assert_the_stored_run_is_as_confirmed(lab, "succeeded")
    assert lab.opener.all_closed
    assert redirections.copies == []


@pytest.mark.parametrize(
    ("make_escape", "code"),
    [
        pytest.param(lambda: KeyboardInterrupt(), 130, id="ctrl-c-escape"),
        pytest.param(lambda: SyntheticDefect(BODY_MARKER), 1, id="defect-escape"),
    ],
)
def test_flush_stream_fault_a_failing_flush_of_the_running_line(
    command_rig: Rig,
    monkeypatch: pytest.MonkeyPatch,
    make_escape: Callable[[], BaseException],
    code: int,
) -> None:
    """(d) AC15: `run_ingest` announces `<A>` and raises; stdout's flush raises.

    130 for the Ctrl+C and 1 for the defect; `<A> running` is stored once and never
    written again; no traceback.
    """
    lab = command_rig.lab
    redirections = record_redirections(monkeypatch)
    monkeypatch.setattr(ingest_command, "run_ingest", escaping(lab.A, make_escape))
    running = f"{lab.A} running"
    out = FlushFaultStream([os_error], lambda text: running in text)
    err = io.StringIO()

    result = invoke_through(command_rig, out, err)

    assert result == code
    assert out.flush_fired
    assert out.getvalue() == f"{running}\n"
    assert len([text for text in out.writes if "running" in text]) == 1
    assert "Traceback" not in err.getvalue()
    assert redirections.copies == []


@pytest.mark.parametrize(
    ("make_error", "handler_line"),
    [
        pytest.param(os_error, "unexpected error: OSError", id="os-error"),
        pytest.param(
            lambda: BrokenPipeError("synthetic broken pipe"),
            "unexpected error: BrokenPipeError",
            id="broken-pipe",
        ),
        pytest.param(
            lambda: ValueError("I/O operation on closed file."),
            "unexpected error: ValueError",
            id="closed-file",
        ),
    ],
)
@pytest.mark.parametrize(("argv", "trigger"), HELP_CASES)
def test_flush_stream_fault_a_failing_flush_of_the_help_or_version_text(
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    trigger: Callable[[str], bool],
    make_error: Callable[[], BaseException],
    handler_line: str,
) -> None:
    """(e) AC14: `--version`, `--help` and `ingest --help`; stdout's flush raises.

    `SystemExit` with code 1; stderr is exactly the handler's one line; the text was
    stored once; nothing is built; nothing is redirected.
    """
    calls = watch_main(monkeypatch)
    redirections = record_redirections(monkeypatch)
    out = FlushFaultStream([make_error], trigger)
    _, err = capture_streams(monkeypatch, out=out)

    stop = run_main(argv)

    assert stop.code == 1
    assert out.flush_fired
    assert err.getvalue().splitlines() == [handler_line]
    assert len([text for text in out.writes if trigger(text)]) == 1, out.writes
    assert calls == MainCalls()
    assert redirections.copies == []


@pytest.mark.parametrize(("argv", "trigger"), HELP_CASES)
def test_flush_stream_fault_a_ctrl_c_in_the_flush_of_the_help_or_version_text(
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    trigger: Callable[[str], bool],
) -> None:
    """(e) AC14, AC15: Ctrl+C from stdout's flush gives 130, `interrupted` at most once."""
    calls = watch_main(monkeypatch)
    redirections = record_redirections(monkeypatch)
    out = FlushFaultStream([interrupt_error], trigger)
    _, err = capture_streams(monkeypatch, out=out)

    stop = run_main(argv)

    assert stop.code == 130
    assert out.flush_fired
    assert err.getvalue().splitlines() in ([], ["interrupted"])
    assert len([text for text in out.writes if trigger(text)]) == 1, out.writes
    assert calls == MainCalls()
    assert redirections.copies == []


@pytest.mark.parametrize(("argv", "trigger"), HELP_CASES)
def test_flush_stream_fault_a_system_exit_in_the_flush_of_the_help_or_version_text(
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    trigger: Callable[[str], bool],
) -> None:
    """(e) D-1: `SystemExit(3)` from stdout's flush leaves `main` as that object.

    No handler line is written for it.
    """
    calls = watch_main(monkeypatch)
    redirections = record_redirections(monkeypatch)
    exits = Raised(lambda: SystemExit(3))
    out = FlushFaultStream([exits], trigger)
    _, err = capture_streams(monkeypatch, out=out)

    stop = run_main(argv)

    assert out.flush_fired
    assert stop is exits.first
    assert stop.code == 3
    assert err.getvalue() == ""
    assert len([text for text in out.writes if trigger(text)]) == 1, out.writes
    assert calls == MainCalls()
    assert redirections.copies == []


@pytest.mark.parametrize(
    "argv",
    [
        pytest.param(["ingest", "--last-page", "2"], id="parse-error"),
        pytest.param([], id="bare-command"),
    ],
)
def test_flush_stream_fault_a_failing_flush_of_the_parser_message(
    monkeypatch: pytest.MonkeyPatch, argv: list[str]
) -> None:
    """(f) AC14: stderr's flush raises after the usage message of the parser.

    Code 1; the message was stored once; stdout is empty; the command was not called.
    """
    calls = watch_main(monkeypatch)
    redirections = record_redirections(monkeypatch)
    err = FlushFaultStream([os_error], lambda text: "usage:" in text)
    out, _ = capture_streams(monkeypatch, err=err)

    stop = run_main(argv)

    assert stop.code == 1
    assert err.flush_fired
    assert out.getvalue() == ""
    assert len([text for text in err.writes if "usage:" in text]) == 1, err.writes
    assert calls == MainCalls()
    assert redirections.copies == []


def test_flush_stream_fault_a_failing_flush_of_a_progress_line_follows_the_progress_rules(
    command_rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(g) AC15: stderr's flush raises after the progress line of page 1.

    The same outcome as a progress write that raises: `unexpected-error` for page 1
    with `OSError`, `<A> failed`, exit 1.
    """
    lab = command_rig.lab
    redirections = record_redirections(monkeypatch)
    out = io.StringIO()
    err = FlushFaultStream([os_error], lambda text: text.startswith("page 1 sequence"))

    result = invoke_through(command_rig, out, err)

    run_id = the_run(lab)
    assert result == 1
    assert err.flush_fired
    assert out.getvalue() == f"{run_id} failed\n"
    assert lab.database.runs[run_id].status is RunStatus.FAILED
    assert lab.details(run_id, "unexpected-error") == [
        {"page": 1, "error_type": "OSError"}
    ]
    assert "Traceback" not in err.getvalue()
    assert redirections.copies == []


LAST_FLUSH_STREAMS = ["stdout", "stderr"]


@pytest.mark.parametrize("stream", LAST_FLUSH_STREAMS)
@pytest.mark.parametrize(
    ("make_error", "code"),
    [
        pytest.param(os_error, 0, id="os-error-dropped"),
        pytest.param(interrupt_error, 130, id="ctrl-c-sets-130"),
    ],
)
def test_flush_stream_fault_the_last_flush_of_main_keeps_or_sets_the_code(
    command_rig: Rig,
    monkeypatch: pytest.MonkeyPatch,
    stream: str,
    make_error: Callable[[], BaseException],
    code: int,
) -> None:
    """The last step of `main`: it flushes stdout, then stderr, each in its own guard.

    A command that writes a line on each stream without flushing returns 0. An
    exception other than Ctrl+C and `SystemExit` from that flush is dropped (0); a
    Ctrl+C makes the code 130. The step writes no text; nothing is redirected.
    """
    redirections = record_redirections(monkeypatch)
    arm_command_that_writes_without_flushing(monkeypatch, command_rig)
    faulty = FlushFaultStream([make_error], lambda text: "synthetic" in text)
    plain = io.StringIO()
    out, err = (faulty, plain) if stream == "stdout" else (plain, faulty)
    capture_streams(monkeypatch, out=out, err=err)

    stop = run_main(["ingest", *SCOPE_ARGS])

    assert faulty.flush_fired
    assert stop.code == code
    assert out.getvalue() == SYNTHETIC_RESULT_LINE
    assert err.getvalue() == SYNTHETIC_MESSAGE_LINE
    assert redirections.copies == []


@pytest.mark.parametrize("stream", LAST_FLUSH_STREAMS)
def test_flush_stream_fault_a_system_exit_in_the_last_flush_of_main_replaces_its_code(
    command_rig: Rig, monkeypatch: pytest.MonkeyPatch, stream: str
) -> None:
    """D-1: `SystemExit(3)` from the last flush leaves `main` in place of its own code."""
    redirections = record_redirections(monkeypatch)
    arm_command_that_writes_without_flushing(monkeypatch, command_rig)
    exits = Raised(lambda: SystemExit(3))
    faulty = FlushFaultStream([exits], lambda text: "synthetic" in text)
    plain = io.StringIO()
    out, err = (faulty, plain) if stream == "stdout" else (plain, faulty)
    capture_streams(monkeypatch, out=out, err=err)

    stop = run_main(["ingest", *SCOPE_ARGS])

    assert faulty.flush_fired
    assert stop is exits.first
    assert stop.code == 3
    assert out.getvalue() == SYNTHETIC_RESULT_LINE
    assert err.getvalue() == SYNTHETIC_MESSAGE_LINE
    assert redirections.copies == []


# === neutralize_fault (AC14, AC15; F-27, decision D-10) =========================
#
# Plan Revision 12, "When the neutralizing fails". A failed stream with a working
# descriptor is redirected to the null device (`os.open` of `os.devnull`, `os.dup2`,
# `os.close`). When that fails, the agreed code still leaves the command and `main`
# through the same exit: the helper absorbs every `Exception` (a `KeyboardInterrupt`
# and a `SystemExit` are not absorbed), writes nothing about it, never retries the
# faulted write, and attempts the neutralizing at most once per stream. The stream's
# descriptor is one the test opened (`owned_descriptor`); `os.open` and `os.dup2` are
# recorders (`record_redirections`) that never touch a standard descriptor. The
# product is expected to call `os.open` and `os.dup2` through the `os` module.

NEUTRALIZING_FAILURES = [
    pytest.param("copy", lambda: OSError("synthetic copy failure"), id="copy-os-error"),
    pytest.param(
        "copy", lambda: ValueError("synthetic bad descriptor"), id="copy-value-error"
    ),
    pytest.param("open", lambda: OSError("synthetic open failure"), id="open-os-error"),
    pytest.param(
        "no-descriptor", lambda: OSError("synthetic unused"), id="no-descriptor"
    ),
]
NEUTRALIZING_SPOKEN_WORDS = (
    "synthetic copy",
    "synthetic bad",
    "synthetic open",
    "dup2",
    "Traceback",
    "unexpected error",
)


def arm_neutralizing(
    monkeypatch: pytest.MonkeyPatch,
    descriptor: int,
    mode: str,
    make_error: Callable[[], BaseException] | None,
) -> tuple[Redirections, int | None]:
    """Make the neutralizing of a stream fail as `mode` says.

    `copy`: `os.dup2` raises `make_error()`. `open`: `os.open` of the null device
    raises it. `no-descriptor`: the stream has none (`fileno()` raises
    `io.UnsupportedOperation`). `success`: both calls succeed. Return the recorders
    and the descriptor the stream must report (`None` for none).
    """
    redirections = record_redirections(
        monkeypatch,
        open_error=make_error if mode == "open" else None,
        copy_error=make_error if mode == "copy" else None,
    )
    return redirections, (None if mode == "no-descriptor" else descriptor)


def assert_neutralizing_attempted_once(
    redirections: Redirections, mode: str, descriptor: int
) -> None:
    """The neutralizing was attempted once, on the test's descriptor, or not at all."""
    if mode == "no-descriptor":
        assert redirections.null_device_opens == []
        assert redirections.copies == []
    elif mode == "open":
        assert len(redirections.null_device_opens) == 1
        assert redirections.copies == []
    else:
        assert len(redirections.null_device_opens) == 1
        assert [target for _, target in redirections.copies] == [descriptor]


def result_line_of(run_id: str) -> str:
    return f"{run_id} succeeded"


@pytest.mark.parametrize(("mode", "make_error"), NEUTRALIZING_FAILURES)
def test_neutralize_fault_a_neutralizing_that_fails_still_gives_the_planned_code(
    command_rig: Rig,
    monkeypatch: pytest.MonkeyPatch,
    owned_descriptor: int,
    mode: str,
    make_error: Callable[[], BaseException],
) -> None:
    """(a) D-10: the AC1 invocation; stdout's flush raises, and its neutralizing fails.

    The command returns 1; `<A> succeeded` is stored once; stderr holds the outcome
    message and says nothing about the neutralizing; the neutralizing was attempted
    once (not at all when the stream has no descriptor).
    """
    lab = command_rig.lab
    redirections, descriptor = arm_neutralizing(
        monkeypatch, owned_descriptor, mode, make_error
    )
    line = result_line_of(FIRST_DRAWN_ID)
    out = FlushFaultStream([os_error], lambda text: line in text, descriptor=descriptor)
    err = io.StringIO()

    result = invoke_through(command_rig, out, err)

    assert result == 1
    assert out.flush_fired
    assert out.getvalue() == f"{line}\n"
    assert err.getvalue().splitlines()[-1] == "succeeded"
    for word in NEUTRALIZING_SPOKEN_WORDS:
        assert word not in err.getvalue(), word
    assert_neutralizing_attempted_once(redirections, mode, owned_descriptor)
    assert_the_stored_run_is_as_confirmed(lab, "succeeded")
    assert lab.opener.all_closed


@pytest.mark.parametrize("fires", [1, 2], ids=["write-flush", "write-and-last-flush"])
@pytest.mark.parametrize(("mode", "make_error"), NEUTRALIZING_FAILURES)
def test_neutralize_fault_a_neutralizing_that_fails_still_gives_code_1_through_main(
    monkeypatch: pytest.MonkeyPatch,
    owned_descriptor: int,
    mode: str,
    make_error: Callable[[], BaseException],
    fires: int,
) -> None:
    """(b) D-10: `--version`; stdout's flush raises, and its neutralizing fails.

    `main` ends with `SystemExit(1)`; stderr is exactly one `unexpected error: OSError`;
    the version text is stored once. With `fires` 2 the flush fails again at the last
    flush of `main`: the code stays 1 and the neutralizing was still attempted once.
    """
    calls = watch_main(monkeypatch)
    redirections, descriptor = arm_neutralizing(
        monkeypatch, owned_descriptor, mode, make_error
    )
    out = FlushFaultStream([os_error] * fires, is_version_text, descriptor=descriptor)
    _, err = capture_streams(monkeypatch, out=out)

    stop = run_main(["--version"])

    assert stop.code == 1
    assert len(out.flush_faults) == fires
    assert err.getvalue().splitlines() == ["unexpected error: OSError"]
    assert out.getvalue() == version_text()
    assert_neutralizing_attempted_once(redirections, mode, owned_descriptor)
    assert calls == MainCalls()


@pytest.mark.parametrize("mode", ["copy", "open"])
def test_neutralize_fault_a_ctrl_c_in_the_neutralizing_exits_130_through_the_command(
    command_rig: Rig,
    monkeypatch: pytest.MonkeyPatch,
    owned_descriptor: int,
    mode: str,
) -> None:
    """(c) D-10: Ctrl+C from `os.dup2` (or `os.open`) in the AC1 invocation -> 130.

    It propagates in place of the flush's exception and the command's rule gives 130;
    the line was stored once and the neutralizing attempted once.
    """
    lab = command_rig.lab
    redirections, descriptor = arm_neutralizing(
        monkeypatch, owned_descriptor, mode, interrupt_error
    )
    line = result_line_of(FIRST_DRAWN_ID)
    out = FlushFaultStream([os_error], lambda text: line in text, descriptor=descriptor)
    err = io.StringIO()

    result = invoke_through(command_rig, out, err)

    assert result == 130
    assert out.flush_fired
    assert out.getvalue() == f"{line}\n"
    assert_neutralizing_attempted_once(redirections, mode, owned_descriptor)
    assert_the_stored_run_is_as_confirmed(lab, "succeeded")


@pytest.mark.parametrize("mode", ["copy", "open"])
def test_neutralize_fault_a_ctrl_c_in_the_neutralizing_exits_130_through_main(
    monkeypatch: pytest.MonkeyPatch, owned_descriptor: int, mode: str
) -> None:
    """(c) D-10: Ctrl+C from `os.dup2` (or `os.open`) while `--version` is written -> 130.

    `interrupted` at most once; the neutralizing was attempted once.
    """
    calls = watch_main(monkeypatch)
    redirections, descriptor = arm_neutralizing(
        monkeypatch, owned_descriptor, mode, interrupt_error
    )
    out = FlushFaultStream([os_error], is_version_text, descriptor=descriptor)
    _, err = capture_streams(monkeypatch, out=out)

    stop = run_main(["--version"])

    assert stop.code == 130
    assert out.flush_fired
    assert err.getvalue().splitlines() in ([], ["interrupted"])
    assert out.getvalue() == version_text()
    assert_neutralizing_attempted_once(redirections, mode, owned_descriptor)
    assert calls == MainCalls()


@pytest.mark.parametrize("mode", ["copy", "open"])
def test_neutralize_fault_a_system_exit_in_the_neutralizing_leaves_the_command(
    command_rig: Rig,
    monkeypatch: pytest.MonkeyPatch,
    owned_descriptor: int,
    mode: str,
) -> None:
    """(d) D-1, D-10: `SystemExit(4)` from the neutralizing leaves the command as is.

    The line was stored once and the neutralizing attempted once.
    """
    lab = command_rig.lab
    exits = Raised(lambda: SystemExit(4))
    redirections, descriptor = arm_neutralizing(
        monkeypatch, owned_descriptor, mode, exits
    )
    line = result_line_of(FIRST_DRAWN_ID)
    out = FlushFaultStream([os_error], lambda text: line in text, descriptor=descriptor)
    err = io.StringIO()

    stop = invoke_exiting(command_rig, out, err)

    assert out.flush_fired
    assert stop is exits.first
    assert stop.code == 4
    assert out.getvalue() == f"{line}\n"
    assert_neutralizing_attempted_once(redirections, mode, owned_descriptor)
    assert_the_stored_run_is_as_confirmed(lab, "succeeded")


@pytest.mark.parametrize("mode", ["copy", "open"])
def test_neutralize_fault_a_system_exit_in_the_neutralizing_leaves_main(
    monkeypatch: pytest.MonkeyPatch, owned_descriptor: int, mode: str
) -> None:
    """(d) D-1, D-10: `SystemExit(4)` from the neutralizing while `--version` is written.

    The `SystemExit(4)` object leaves `main`; no handler line is written for it.
    """
    calls = watch_main(monkeypatch)
    exits = Raised(lambda: SystemExit(4))
    redirections, descriptor = arm_neutralizing(
        monkeypatch, owned_descriptor, mode, exits
    )
    out = FlushFaultStream([os_error], is_version_text, descriptor=descriptor)
    _, err = capture_streams(monkeypatch, out=out)

    stop = run_main(["--version"])

    assert out.flush_fired
    assert stop is exits.first
    assert stop.code == 4
    assert err.getvalue() == ""
    assert_neutralizing_attempted_once(redirections, mode, owned_descriptor)
    assert calls == MainCalls()


@pytest.mark.parametrize("mode", ["copy", "open"])
def test_neutralize_fault_a_system_exit_in_the_last_flush_replaces_the_code_of_main(
    command_rig: Rig,
    monkeypatch: pytest.MonkeyPatch,
    owned_descriptor: int,
    mode: str,
) -> None:
    """(d) D-1, D-10: the only flush is the last flush of `main`, which ends with 0.

    Its neutralizing raises `SystemExit(4)`: that object leaves `main` in place of
    `SystemExit(0)`; the neutralizing was attempted once.
    """
    arm_command_that_writes_without_flushing(monkeypatch, command_rig)
    exits = Raised(lambda: SystemExit(4))
    redirections, descriptor = arm_neutralizing(
        monkeypatch, owned_descriptor, mode, exits
    )
    out = FlushFaultStream(
        [os_error], lambda text: "synthetic" in text, descriptor=descriptor
    )
    capture_streams(monkeypatch, out=out)

    stop = run_main(["ingest", *SCOPE_ARGS])

    assert out.flush_fired
    assert stop is exits.first
    assert stop.code == 4
    assert out.getvalue() == SYNTHETIC_RESULT_LINE
    assert_neutralizing_attempted_once(redirections, mode, owned_descriptor)


@pytest.mark.parametrize("mode", ["copy", "open"])
def test_neutralize_fault_the_first_system_exit_wins_over_one_in_the_last_flush(
    monkeypatch: pytest.MonkeyPatch, owned_descriptor: int, mode: str
) -> None:
    """(d) D-1, D-10: `SystemExit(3)` from the flush of `--version` propagates.

    The last flush of `main` then fails with `OSError` and its neutralizing raises
    `SystemExit(4)`, which is dropped: the `SystemExit(3)` object leaves `main`. The
    neutralizing is attempted once, in the last flush (a `SystemExit` does not start it).
    """
    calls = watch_main(monkeypatch)
    first = Raised(lambda: SystemExit(3))
    second = Raised(lambda: SystemExit(4))
    redirections, descriptor = arm_neutralizing(
        monkeypatch, owned_descriptor, mode, second
    )
    out = FlushFaultStream([first, os_error], is_version_text, descriptor=descriptor)
    _, err = capture_streams(monkeypatch, out=out)

    stop = run_main(["--version"])

    assert len(out.flush_faults) == 2
    assert stop is first.first
    assert stop.code == 3
    assert err.getvalue() == ""
    assert_neutralizing_attempted_once(redirections, mode, owned_descriptor)
    assert calls == MainCalls()


def test_neutralize_fault_a_successful_neutralizing_gives_the_same_code_through_the_command(
    command_rig: Rig, monkeypatch: pytest.MonkeyPatch, owned_descriptor: int
) -> None:
    """(e) D-6: the null device is opened and copied onto the test's descriptor once.

    The same code and the same lines as `flush_stream_fault`: 1, `<A> succeeded` stored
    once. No standard descriptor is the target.
    """
    lab = command_rig.lab
    redirections, descriptor = arm_neutralizing(
        monkeypatch, owned_descriptor, "success", None
    )
    line = result_line_of(FIRST_DRAWN_ID)
    out = FlushFaultStream([os_error], lambda text: line in text, descriptor=descriptor)
    err = io.StringIO()

    result = invoke_through(command_rig, out, err)

    assert result == 1
    assert out.flush_fired
    assert out.getvalue() == f"{line}\n"
    assert_neutralizing_attempted_once(redirections, "success", owned_descriptor)
    assert_the_stored_run_is_as_confirmed(lab, "succeeded")


@pytest.mark.parametrize("fires", [1, 2], ids=["write-flush", "write-and-last-flush"])
def test_neutralize_fault_a_successful_neutralizing_is_not_attempted_again_by_main(
    monkeypatch: pytest.MonkeyPatch, owned_descriptor: int, fires: int
) -> None:
    """(e) D-6, D-10: `--version`; with `fires` 2 the flush fails at the last flush too.

    Code 1 and one `unexpected error: OSError`; the stream was neutralized once, and
    the last flush did not attempt it a second time.
    """
    calls = watch_main(monkeypatch)
    redirections, descriptor = arm_neutralizing(
        monkeypatch, owned_descriptor, "success", None
    )
    out = FlushFaultStream([os_error] * fires, is_version_text, descriptor=descriptor)
    _, err = capture_streams(monkeypatch, out=out)

    stop = run_main(["--version"])

    assert stop.code == 1
    assert len(out.flush_faults) == fires
    assert err.getvalue().splitlines() == ["unexpected error: OSError"]
    assert_neutralizing_attempted_once(redirections, "success", owned_descriptor)
    assert calls == MainCalls()


def test_neutralize_fault_a_failed_last_flush_neutralizes_its_stream_and_keeps_the_code(
    command_rig: Rig, monkeypatch: pytest.MonkeyPatch, owned_descriptor: int
) -> None:
    """(e) D-6: the only flush is the last flush of `main`, which ends with 0.

    The `OSError` is dropped and the code stays 0; the stream was neutralized once; no
    text is written about it.
    """
    arm_command_that_writes_without_flushing(monkeypatch, command_rig)
    redirections, descriptor = arm_neutralizing(
        monkeypatch, owned_descriptor, "success", None
    )
    out = FlushFaultStream(
        [os_error], lambda text: "synthetic" in text, descriptor=descriptor
    )
    _, err = capture_streams(monkeypatch, out=out)

    stop = run_main(["ingest", *SCOPE_ARGS])

    assert out.flush_fired
    assert stop.code == 0
    assert out.getvalue() == SYNTHETIC_RESULT_LINE
    assert err.getvalue() == SYNTHETIC_MESSAGE_LINE
    assert_neutralizing_attempted_once(redirections, "success", owned_descriptor)


# === main_handler_line_fault (AC14, AC15; F-28, D-1, D-3, D-4) ==================
#
# Plan Revision 12, § Public names, "The handler of `main`": one attempt to write the
# handler's own line; a Ctrl+C there makes the code 130, a `SystemExit` propagates in its
# place, and any other failure keeps the code. `cli.default_wiring` raises, `sys.stderr`
# is the `RaisingStream` aimed at the handler's line. They protect behavior that already
# holds (audit experiment X26) and kill the mutants N10, N11 and N12.

HANDLER_LINE_CASES = [
    pytest.param(
        memory_error,
        "unexpected error: MemoryError",
        interrupt_error,
        130,
        id="memory-error-then-line-ctrl-c",
    ),
    pytest.param(
        interrupt_error,
        "interrupted",
        interrupt_error,
        130,
        id="ctrl-c-then-line-ctrl-c",
    ),
    pytest.param(
        interrupt_error, "interrupted", os_error, 130, id="ctrl-c-then-line-os-error"
    ),
    pytest.param(
        memory_error,
        "unexpected error: MemoryError",
        os_error,
        1,
        id="memory-error-then-line-os-error",
    ),
]


@pytest.mark.parametrize("keep", [True, False], ids=["after-storing", "before-storing"])
@pytest.mark.parametrize(
    ("make_escape", "line", "make_fault", "code"), HANDLER_LINE_CASES
)
def test_main_handler_line_fault_a_failing_handler_line_keeps_or_sets_the_code(
    monkeypatch: pytest.MonkeyPatch,
    make_escape: Callable[[], BaseException],
    line: str,
    make_fault: Callable[[], BaseException],
    code: int,
    keep: bool,
) -> None:
    """Cases (i) to (iv): `default_wiring` raises, and the handler's line fails.

    A Ctrl+C on the line gives 130, an `OSError` keeps the code the handler had (130
    after a Ctrl+C, 1 after a `MemoryError`). The line is attempted once, stdout is
    empty, no traceback is written and the command is not called.
    """
    calls = watch_main(monkeypatch, wiring=raising(make_escape))
    err = RaisingStream(make_fault, lambda text: line in text, keep=keep)
    out, _ = capture_streams(monkeypatch, err=err)

    stop = run_main(["ingest", *SCOPE_ARGS])

    assert err.fired
    assert stop.code == code
    assert out.getvalue() == ""
    assert len([text for text in err.writes if line in text]) == 1, err.writes
    assert "Traceback" not in err.getvalue()
    assert calls == MainCalls(default_wiring=1, run_ingest_command=0)


@pytest.mark.parametrize("keep", [True, False], ids=["after-storing", "before-storing"])
@pytest.mark.parametrize(
    ("make_escape", "line"),
    [
        pytest.param(
            memory_error, "unexpected error: MemoryError", id="after-a-memory-error"
        ),
        pytest.param(interrupt_error, "interrupted", id="after-a-ctrl-c"),
    ],
)
def test_main_handler_line_fault_a_system_exit_on_the_handler_line_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
    make_escape: Callable[[], BaseException],
    line: str,
    keep: bool,
) -> None:
    """Case (v): `SystemExit(3)` on the handler's line leaves `main` as that object.

    Code 3 whatever the handler was handling; the line is attempted once; stdout is
    empty; no traceback; the command is not called.
    """
    calls = watch_main(monkeypatch, wiring=raising(make_escape))
    exits = Raised(lambda: SystemExit(3))
    err = RaisingStream(exits, lambda text: line in text, keep=keep)
    out, _ = capture_streams(monkeypatch, err=err)

    stop = run_main(["ingest", *SCOPE_ARGS])

    assert err.fired
    assert stop is exits.first
    assert stop.code == 3
    assert out.getvalue() == ""
    assert len([text for text in err.writes if line in text]) == 1, err.writes
    assert "Traceback" not in err.getvalue()
    assert calls == MainCalls(default_wiring=1, run_ingest_command=0)


# === exit_code_cleanup_system_exit (AC7, AC15; F-28, D-1, N39) ==================
#
# State machine K never turns a `SystemExit` into an outcome: a `SystemExit` raised by
# the cleanup's `run-interrupted` append leaves the command with its own code (`Rig`
# reads it), writes no `<A> running`, no `interrupted` and no `unexpected error` line.
# The use-case twin is `cleanup_system_exit` in `test_ingest_use_case.py`.


@pytest.mark.parametrize("when", ["before", "after"])
def test_exit_code_cleanup_system_exit_the_run_closing_append_leaves_with_its_code(
    rig: Rig, when: Literal["before", "after"]
) -> None:
    """Ctrl+C at page 2; K's `run-interrupted` append raises `SystemExit(3)` -> code 3.

    Stdout is empty (no `<A> running`), stderr has no `interrupted` and no
    `unexpected error`; `<A>` stays `running`; every repository is closed.
    """
    lab = rig.lab
    lab.source.script(2, KeyboardInterrupt())
    lab.opener.faults[1] = [
        lab.faults.raises(
            "append_audit_event",
            lambda: SystemExit(3),
            detail="run-interrupted",
            when=when,
        )
    ]

    result = rig.invoke(SCOPE_ARGS)

    run_id = the_run(lab)
    assert_a_system_exit_left_quietly(result)
    assert lab.database.runs[run_id].status is RunStatus.RUNNING
    assert lab.opener.attempts[-1].operation == "append_audit_event"
    assert lab.opener.all_closed


# === Audit round 7 rework (2026-10-27), plan Revision 13 ========================
#
# Feature ingest-command (F4), outcome O10, rework of round 7 (audit finding F-31;
# decisions D-11 and D-12, option A, chosen by the human on 2026-10-27; D-5 as adjusted
# for a missing stream; acceptance criteria AC14 and AC15). Written red against the
# Revision 15/13/10 specs, before the protected write, the neutralizing, the last
# flush and the one local parser class know a missing stream.
#
# A stream is *missing* when it is `None`: `sys.stdout` or `sys.stderr` when Python
# started without a descriptor 1 or 2 (CPython then sets the attribute to `None`), or
# a `None` handed to `run_ingest_command`. A missing stream is disabled output, never
# a failing stream (and never a faked closed stream): nothing is written for it,
# neither there nor on the other stream, nothing is flushed, redirected or raised, and
# no exit code, outcome or run status changes because of it. Tokens:
#
# - `absent_stderr_command`: a `None` stderr handed to the command;
# - `absent_stderr_main`: `main` with `sys.stderr` `None` (and the parser class);
# - `absent_stdout_command` and `absent_stdout_main`: a missing stdout (D-12): the
#   result line, `--version` and `--help` are not written and not sent to stderr;
# - `absent_streams_main`: both missing, the descriptors read with `capfd`;
# - `absent_stream_helpers`: `output_streams` called with `None`.
#
# No test name here contains `usage`, `output`, `environment`, `interrupt`, `exit_code`,
# `system_exit`, `stream_fault` or another forbidden word of the plan's token rule: a
# usage error is a `parse error` or a `rule error`, an unset variable an `unset
# variable`, a Ctrl+C `ctrl-c`. The `os.open` and `os.dup2` recorders of Revision 12
# show that a missing stream starts no neutralizing. The real process is the process
# tier (`tests/process/`).

ABSENT: typing.TextIO = typing.cast(typing.TextIO, None)
STANDARD_PRINT_USAGE = argparse.ArgumentParser.print_usage
UNREACHED = ("make_source", "migrate", "make_store", "make_repository")
ENDINGS = [
    pytest.param(
        "succeeded",
        0,
        "succeeded",
        ["run-started", "page-completed", "page-completed"],
        id="succeeded-run",
    ),
    pytest.param(
        "failed-page",
        1,
        "failed",
        ["run-started", "page-completed", "page-failed"],
        id="failed-run",
    ),
    pytest.param(
        "ctrl-c",
        130,
        "failed",
        ["run-started", "page-completed", "run-interrupted"],
        id="ended-by-ctrl-c",
    ),
]


def arm_ending(lab: Lab, ending: str) -> None:
    """The AC1 run (`succeeded`), the AC4 run (`failed-page`) or the AC7 run (`ctrl-c`)."""
    if ending == "failed-page":
        lab.source.script(2, lab.status_failure(2, 500))
    elif ending == "ctrl-c":
        lab.source.script(2, KeyboardInterrupt())
    else:
        assert ending == "succeeded"


def call_command(
    rig: Rig,
    arguments: argparse.Namespace,
    *,
    environ: Mapping[str, str],
    stdout: typing.TextIO,
    stderr: typing.TextIO,
) -> int:
    """`run_ingest_command`; whatever escapes it fails the test by name."""
    try:
        return run_ingest_command(
            arguments,
            environ=environ,
            wiring=rig.wiring(),
            stdout=stdout,
            stderr=stderr,
        )
    except (Exception, KeyboardInterrupt) as error:
        raise AssertionError(
            f"the command let {type(error).__name__} escape"
        ) from error


def invoke_without_stream(
    rig: Rig,
    *,
    stdout: typing.TextIO,
    stderr: typing.TextIO,
    argv: Sequence[str] = SCOPE_ARGS,
    environ: Mapping[str, str] | None = None,
) -> int:
    """`ingest <argv>` through the command, with the streams given (one may be `None`)."""
    arguments = cli.build_parser().parse_args(["ingest", *argv])
    return call_command(
        rig,
        arguments,
        environ=dict(GOOD_ENVIRON) if environ is None else environ,
        stdout=stdout,
        stderr=stderr,
    )


def assert_process_streams_empty(capsys: pytest.CaptureFixture[str]) -> None:
    """Nothing reached the process's stdout or stderr (no text sent to the other one)."""
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def assert_no_redirection(redirections: Redirections) -> None:
    """A missing stream starts no neutralizing: no null device opened, no `os.dup2`."""
    assert redirections.null_device_opens == []
    assert redirections.copies == []


def assert_argparse_is_standard() -> None:
    """`argparse` is not patched: its two methods are the standard library's own."""
    cli.build_parser()
    for method, standard in (
        (argparse.ArgumentParser._print_message, STANDARD_PRINT_MESSAGE),
        (argparse.ArgumentParser.print_usage, STANDARD_PRINT_USAGE),
    ):
        assert method is standard
        assert method.__module__ == "argparse"
        assert (
            Path(method.__code__.co_filename).resolve()
            == Path(argparse.__file__).resolve()
        )


def use_environment(
    monkeypatch: pytest.MonkeyPatch, *, unset: Sequence[str] = ()
) -> None:
    """The process variables `main` reads: the good ones, without those in `unset`."""
    for name in POSTGRES_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    for name, value in GOOD_ENVIRON.items():
        if name not in unset:
            monkeypatch.setenv(name, value)


def arm_ingest_through_main(
    rig: Rig, monkeypatch: pytest.MonkeyPatch, *, unset: Sequence[str] = ()
) -> MainCalls:
    """`main(["ingest", ...])` runs the real command over the rig's doubles.

    With a variable in `unset`, the rig's doubles fail the test if the command reaches
    them: a rejected invocation builds nothing.
    """
    use_environment(monkeypatch, unset=unset)
    if unset:
        rig.forbid(*UNREACHED)
    return watch_main(monkeypatch, wiring=rig.wiring, run_command=True)


def remove_streams(monkeypatch: pytest.MonkeyPatch, *names: str) -> None:
    """Python started without these streams: `sys.stdout` or `sys.stderr` is `None`."""
    for name in names:
        monkeypatch.setattr(sys, name, None)


def assert_the_ingest_ended(rig: Rig, status: str, events: list[str]) -> None:
    """The run is as with working streams: its events, its status, nothing after."""
    lab = rig.lab
    run_id = the_run(lab)
    assert lab.event_types(run_id) == events
    assert "unexpected-error" not in lab.event_types(run_id)
    assert_the_stored_run_is_as_confirmed(lab, status)
    assert lab.opener.all_closed


@pytest.fixture
def descriptor_rig(
    lab: Lab, capfd: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> Rig:
    """A rig whose process streams are read on the descriptors (`capfd`), not `capsys`."""
    return Rig(lab, capfd, monkeypatch, "main")


# === absent_stderr_command (AC14, AC15; F-31, D-11 option A) ====================


@pytest.mark.parametrize(("ending", "code", "status", "events"), ENDINGS)
def test_absent_stderr_command_an_ingest_ends_as_with_a_working_stderr(
    command_rig: Rig,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    ending: str,
    code: int,
    status: str,
    events: list[str],
) -> None:
    """(a) to (c) A `None` stderr is disabled output: the outcome is the same.

    The AC1, AC4 and AC7 runs end 0, 1 and 130; the injected stdout is exactly the one
    result line; nothing reaches the process's stdout or stderr (`print(file=None)`
    would fall back to `sys.stdout`); the reporter's `run_started` and progress lines
    raise nothing, so the run is not closed `failed` by an `unexpected-error`; and no
    null device is opened and no descriptor redirected.
    """
    lab = command_rig.lab
    redirections = record_redirections(monkeypatch)
    arm_ending(lab, ending)
    out = io.StringIO()

    result = invoke_without_stream(command_rig, stdout=out, stderr=ABSENT)

    assert result == code
    assert out.getvalue() == f"{the_run(lab)} {status}\n"
    assert_process_streams_empty(capsys)
    assert_the_ingest_ended(command_rig, status, events)
    assert_no_redirection(redirections)


@pytest.mark.parametrize("case", ["unset-variable", "rule-error"])
def test_absent_stderr_command_a_rejected_invocation_returns_2_and_builds_nothing(
    command_rig: Rig,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    """(d) The `error: <message>` line has nowhere to go and is not a failure.

    A variable that is not set, and a namespace that breaks a rule of
    `request_from_arguments` (built directly, as a caller other than `main` would),
    return 2 (nothing escapes), with stdout empty and nothing built.
    """
    redirections = record_redirections(monkeypatch)
    command_rig.forbid(*UNREACHED)
    out = io.StringIO()
    if case == "unset-variable":
        environ = {k: v for k, v in GOOD_ENVIRON.items() if k != "POSTGRES_DB"}
        arguments = cli.build_parser().parse_args(["ingest", *SCOPE_ARGS])
    else:
        environ = dict(GOOD_ENVIRON)
        arguments = argparse.Namespace(
            command="ingest",
            year=YEAR,
            buyer=BUYER,
            first_page=3,
            last_page=2,
            resume=None,
            migrations_dir="migrations",
        )

    result = call_command(
        command_rig, arguments, environ=environ, stdout=out, stderr=ABSENT
    )

    assert result == 2
    assert out.getvalue() == ""
    assert_process_streams_empty(capsys)
    assert command_rig.calls == []
    assert_no_redirection(redirections)


# === absent_stderr_main (AC14, AC15; F-31, D-11, D-5 as adjusted) ===============


@pytest.mark.parametrize(
    "argv",
    [
        pytest.param([], id="bare-command"),
        pytest.param(["ingest", "--last-page", "2"], id="parse-error"),
    ],
)
def test_absent_stderr_main_the_bare_command_and_a_parse_error_exit_2_silently(
    command_rig: Rig,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
) -> None:
    """(a), (b) Code 2 and stdout empty: the usage is not sent to stdout.

    `argparse` replaces a `None` file by `sys.stdout` in `print_usage`; the parser
    class overrides `print_usage` so that a missing stderr stays missing. The command
    is not run and nothing is built.
    """
    redirections = record_redirections(monkeypatch)
    calls = watch_main(monkeypatch)
    remove_streams(monkeypatch, "stderr")

    stop = run_main(argv)

    assert stop.code == 2
    assert capsys.readouterr().out == ""
    assert calls == MainCalls()
    assert_no_redirection(redirections)
    assert_argparse_is_standard()


@pytest.mark.parametrize(("argv", "trigger"), HELP_CASES)
def test_absent_stderr_main_version_and_help_keep_their_text_on_stdout(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    trigger: Callable[[str], bool],
) -> None:
    """(c) `--version`, `--help` and `ingest --help` -> 0, the text on stdout as today."""
    redirections = record_redirections(monkeypatch)
    calls = watch_main(monkeypatch)
    remove_streams(monkeypatch, "stderr")

    stop = run_main(argv)

    text = capsys.readouterr().out
    assert stop.code == 0
    assert trigger(text)
    if argv == ["--version"]:
        assert text == version_text()
    else:
        assert text.startswith("usage:")
    assert calls == MainCalls()
    assert_no_redirection(redirections)
    assert_argparse_is_standard()


def test_absent_stderr_main_an_ingest_ends_as_with_a_working_stderr(
    command_rig: Rig,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(d) The AC1 arguments -> 0, stdout exactly `<A> succeeded`, `<A>` `succeeded`.

    The progress lines and the final message are not written anywhere: no stderr text
    on stdout, no `unexpected-error`, no run closed `failed` before its first request.
    """
    lab = command_rig.lab
    redirections = record_redirections(monkeypatch)
    calls = arm_ingest_through_main(command_rig, monkeypatch)
    remove_streams(monkeypatch, "stderr")

    stop = run_main(["ingest", *SCOPE_ARGS])

    assert stop.code == 0
    assert capsys.readouterr().out == f"{the_run(lab)} succeeded\n"
    assert calls == MainCalls(default_wiring=1, run_ingest_command=1)
    assert_the_ingest_ended(
        command_rig, "succeeded", ["run-started", "page-completed", "page-completed"]
    )
    assert_no_redirection(redirections)
    assert_argparse_is_standard()


def test_absent_stderr_main_an_unset_variable_exits_2_with_stdout_empty(
    command_rig: Rig,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(e) The AC1 arguments with `POSTGRES_DB` unset -> 2, stdout empty, nothing built.

    The message `error: POSTGRES_DB is not set` has nowhere to go and is not a failure.
    """
    redirections = record_redirections(monkeypatch)
    calls = arm_ingest_through_main(command_rig, monkeypatch, unset=["POSTGRES_DB"])
    remove_streams(monkeypatch, "stderr")

    stop = run_main(["ingest", *SCOPE_ARGS])

    assert stop.code == 2
    assert capsys.readouterr().out == ""
    assert calls == MainCalls(default_wiring=1, run_ingest_command=1)
    assert command_rig.calls == []
    assert_no_redirection(redirections)
    assert_argparse_is_standard()


@pytest.mark.parametrize(
    ("make_escape", "code"),
    [
        pytest.param(interrupt_error, 130, id="ctrl-c"),
        pytest.param(memory_error, 1, id="memory-error"),
    ],
)
def test_absent_stderr_main_the_handler_keeps_its_code_and_writes_its_line_nowhere(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    make_escape: Callable[[], BaseException],
    code: int,
) -> None:
    """(f) `default_wiring` raises: 130 for Ctrl+C, 1 for `MemoryError`, stdout empty.

    The handler's line (`interrupted`, `unexpected error: <class>`) is not written on
    stdout in place of the missing stderr.
    """
    redirections = record_redirections(monkeypatch)
    calls = watch_main(monkeypatch, wiring=raising(make_escape))
    remove_streams(monkeypatch, "stderr")

    stop = run_main(["ingest", *SCOPE_ARGS])

    assert stop.code == code
    assert capsys.readouterr().out == ""
    assert calls == MainCalls(default_wiring=1, run_ingest_command=0)
    assert_no_redirection(redirections)


def test_absent_stderr_main_an_own_exit_from_the_wiring_is_preserved(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """(f) D-1: `SystemExit(3)` from `default_wiring` leaves `main` as that object."""
    redirections = record_redirections(monkeypatch)
    exits = Raised(lambda: SystemExit(3))
    calls = watch_main(monkeypatch, wiring=raising(exits))
    remove_streams(monkeypatch, "stderr")

    stop = run_main(["ingest", *SCOPE_ARGS])

    assert stop is exits.first
    assert stop.code == 3
    assert capsys.readouterr().out == ""
    assert calls == MainCalls(default_wiring=1, run_ingest_command=0)
    assert_no_redirection(redirections)


# === absent_stdout_command (AC14, AC15; F-31, D-12 option A) ====================


@pytest.mark.parametrize(("ending", "code", "status", "events"), ENDINGS)
def test_absent_stdout_command_an_ingest_ends_as_with_a_working_stdout(
    command_rig: Rig,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    ending: str,
    code: int,
    status: str,
    events: list[str],
) -> None:
    """A `None` stdout drops the result line: the code is the one the run determined.

    The injected stderr holds `run <A> started`, the progress lines and the outcome
    message, and no `<A> <status>` line; nothing reaches the process's streams (the
    result line goes nowhere); the run is as with a working stdout.
    """
    lab = command_rig.lab
    redirections = record_redirections(monkeypatch)
    arm_ending(lab, ending)
    err = io.StringIO()

    result = invoke_without_stream(command_rig, stdout=ABSENT, stderr=err)

    run_id = the_run(lab)
    lines = err.getvalue().splitlines()
    assert result == code
    assert f"run {run_id} started" in lines
    assert len(lines) >= 3
    assert f"{run_id} {status}" not in lines
    assert "Traceback" not in err.getvalue()
    assert_process_streams_empty(capsys)
    assert_the_ingest_ended(command_rig, status, events)
    assert_no_redirection(redirections)


# === absent_stdout_main (AC14, AC15; F-31, D-12 option A) =======================


def test_absent_stdout_main_an_ingest_drops_only_the_result_line(
    command_rig: Rig,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The AC1 arguments -> 0; stderr as with a working stdout, without the result line."""
    lab = command_rig.lab
    redirections = record_redirections(monkeypatch)
    arm_ingest_through_main(command_rig, monkeypatch)
    remove_streams(monkeypatch, "stdout")

    stop = run_main(["ingest", *SCOPE_ARGS])

    run_id = the_run(lab)
    lines = capsys.readouterr().err.splitlines()
    assert stop.code == 0
    assert f"run {run_id} started" in lines
    assert f"{run_id} succeeded" not in lines
    assert len(lines) >= 3
    assert_the_ingest_ended(
        command_rig, "succeeded", ["run-started", "page-completed", "page-completed"]
    )
    assert_no_redirection(redirections)
    assert_argparse_is_standard()


def test_absent_stdout_main_a_ctrl_c_ingest_exits_130_without_a_result_line(
    command_rig: Rig,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The AC7 arguments -> 130; the closed run is stored, no `<A> failed` anywhere."""
    lab = command_rig.lab
    redirections = record_redirections(monkeypatch)
    arm_ending(lab, "ctrl-c")
    arm_ingest_through_main(command_rig, monkeypatch)
    remove_streams(monkeypatch, "stdout")

    stop = run_main(["ingest", *SCOPE_ARGS])

    run_id = the_run(lab)
    lines = capsys.readouterr().err.splitlines()
    assert stop.code == 130
    assert f"{run_id} failed" not in lines
    assert_the_stored_run_is_as_confirmed(lab, "failed")
    assert_no_redirection(redirections)


@pytest.mark.parametrize(("argv", "trigger"), HELP_CASES)
def test_absent_stdout_main_version_and_help_write_nothing_and_exit_0(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    trigger: Callable[[str], bool],
) -> None:
    """`--version`, `--help` and `ingest --help` -> 0, stderr empty (no substitute).

    `argparse` alone would send their text to stderr when stdout is missing; the parser
    class drops it.
    """
    redirections = record_redirections(monkeypatch)
    calls = watch_main(monkeypatch)
    remove_streams(monkeypatch, "stdout")

    stop = run_main(argv)

    assert stop.code == 0
    assert_process_streams_empty(capsys)
    assert calls == MainCalls()
    assert_no_redirection(redirections)
    assert_argparse_is_standard()


@pytest.mark.parametrize(
    ("argv", "words"),
    [
        pytest.param(
            ["ingest", "--last-page", "2"], ("usage:", "error:"), id="parse-error"
        ),
        pytest.param([], ("usage:",), id="bare-command"),
    ],
)
def test_absent_stdout_main_a_parse_error_and_the_bare_command_keep_their_stderr_text(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    words: tuple[str, ...],
) -> None:
    """Code 2 with `usage:` (and `error:`) on stderr, as with a working stdout."""
    redirections = record_redirections(monkeypatch)
    calls = watch_main(monkeypatch)
    remove_streams(monkeypatch, "stdout")

    stop = run_main(argv)

    text = capsys.readouterr().err
    assert stop.code == 2
    for word in words:
        assert word in text
    assert "Traceback" not in text
    assert calls == MainCalls()
    assert_no_redirection(redirections)


def test_absent_stdout_main_an_unset_variable_exits_2_with_its_message_on_stderr(
    command_rig: Rig,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The AC1 arguments with `POSTGRES_DB` unset -> 2, `error: POSTGRES_DB is not set`."""
    redirections = record_redirections(monkeypatch)
    arm_ingest_through_main(command_rig, monkeypatch, unset=["POSTGRES_DB"])
    remove_streams(monkeypatch, "stdout")

    stop = run_main(["ingest", *SCOPE_ARGS])

    assert stop.code == 2
    assert "error: POSTGRES_DB is not set" in capsys.readouterr().err.splitlines()
    assert command_rig.calls == []
    assert_no_redirection(redirections)


# === absent_streams_main (AC14, AC15; F-31, D-11 and D-12) ======================


@pytest.mark.parametrize(
    ("ending", "code", "status", "events"),
    [ENDINGS[0], ENDINGS[2]],
)
def test_absent_streams_main_an_ingest_ends_as_with_working_streams(
    descriptor_rig: Rig,
    capfd: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    ending: str,
    code: int,
    status: str,
    events: list[str],
) -> None:
    """Both streams `None`: the AC1 run ends 0 and the AC7 run 130, nothing is written.

    The descriptors (read with `capfd`) stay empty; the stored run is as confirmed and
    no `unexpected-error` closes it.
    """
    redirections = record_redirections(monkeypatch)
    arm_ending(descriptor_rig.lab, ending)
    arm_ingest_through_main(descriptor_rig, monkeypatch)
    remove_streams(monkeypatch, "stdout", "stderr")

    stop = run_main(["ingest", *SCOPE_ARGS])

    captured = capfd.readouterr()
    assert stop.code == code
    assert (captured.out, captured.err) == ("", "")
    assert_the_ingest_ended(descriptor_rig, status, events)
    assert_no_redirection(redirections)
    assert_argparse_is_standard()


@pytest.mark.parametrize(
    ("argv", "code"),
    [
        pytest.param(["ingest", "--last-page", "2"], 2, id="parse-error"),
        pytest.param([], 2, id="bare-command"),
        pytest.param(["--version"], 0, id="version"),
        pytest.param(["--help"], 0, id="help"),
        pytest.param(["ingest", "--help"], 0, id="ingest-help"),
    ],
)
def test_absent_streams_main_the_parser_writes_nothing_and_keeps_its_code(
    capfd: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    code: int,
) -> None:
    """A parse error and the bare command -> 2; `--version` and `--help` -> 0."""
    redirections = record_redirections(monkeypatch)
    calls = watch_main(monkeypatch)
    remove_streams(monkeypatch, "stdout", "stderr")

    stop = run_main(argv)

    captured = capfd.readouterr()
    assert stop.code == code
    assert (captured.out, captured.err) == ("", "")
    assert calls == MainCalls()
    assert_no_redirection(redirections)
    assert_argparse_is_standard()


def test_absent_streams_main_an_unset_variable_exits_2_and_builds_nothing(
    descriptor_rig: Rig,
    capfd: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The AC1 arguments with `POSTGRES_DB` unset -> 2, nothing is built or written."""
    redirections = record_redirections(monkeypatch)
    arm_ingest_through_main(descriptor_rig, monkeypatch, unset=["POSTGRES_DB"])
    remove_streams(monkeypatch, "stdout", "stderr")

    stop = run_main(["ingest", *SCOPE_ARGS])

    captured = capfd.readouterr()
    assert stop.code == 2
    assert (captured.out, captured.err) == ("", "")
    assert descriptor_rig.calls == []
    assert_no_redirection(redirections)


@pytest.mark.parametrize(
    ("make_escape", "code"),
    [
        pytest.param(interrupt_error, 130, id="ctrl-c"),
        pytest.param(memory_error, 1, id="memory-error"),
    ],
)
def test_absent_streams_main_the_handler_keeps_its_code_and_writes_nothing(
    capfd: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    make_escape: Callable[[], BaseException],
    code: int,
) -> None:
    """`default_wiring` raises: 130 for Ctrl+C and 1 for `MemoryError`, nothing written.

    The handler's attempt to write its line neither fails nor redirects anything.
    """
    redirections = record_redirections(monkeypatch)
    calls = watch_main(monkeypatch, wiring=raising(make_escape))
    remove_streams(monkeypatch, "stdout", "stderr")

    stop = run_main(["ingest", *SCOPE_ARGS])

    captured = capfd.readouterr()
    assert stop.code == code
    assert (captured.out, captured.err) == ("", "")
    assert calls == MainCalls(default_wiring=1, run_ingest_command=0)
    assert_no_redirection(redirections)


# === absent_stream_helpers (AC14, AC15; F-31, D-11, D-10's record) ==============


@pytest.mark.parametrize(
    "write",
    [
        pytest.param(output_streams.write_line, id="write-line"),
        pytest.param(output_streams.write_text, id="write-text"),
    ],
)
def test_absent_stream_helpers_a_protected_write_to_a_missing_stream_does_nothing(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    write: Callable[[typing.TextIO, str], None],
) -> None:
    """`write_line(None, "x")` and `write_text(None, "x")` return, raise and write nothing.

    `print(text, file=None)` would write on `sys.stdout`, and `None.flush()` would
    raise `AttributeError`; neither may happen.
    """
    redirections = record_redirections(monkeypatch)

    write(ABSENT, "x")

    assert_process_streams_empty(capsys)
    assert_no_redirection(redirections)


def test_absent_stream_helpers_the_neutralizing_of_a_missing_stream_does_nothing(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The neutralizing called with `None` returns: no `os.open`, no `os.dup2`."""
    redirections = record_redirections(monkeypatch)

    output_streams.neutralize(ABSENT)

    assert_process_streams_empty(capsys)
    assert_no_redirection(redirections)


def test_absent_stream_helpers_the_last_flush_of_two_missing_streams_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`flush_for_exit(None, None)` returns `None` and redirects nothing."""
    redirections = record_redirections(monkeypatch)

    returned = output_streams.flush_for_exit(ABSENT, ABSENT)

    assert returned is None
    assert_no_redirection(redirections)


@pytest.mark.parametrize(
    "missing_first", [True, False], ids=["missing-first", "missing-last"]
)
@pytest.mark.parametrize(
    "make_error",
    [
        pytest.param(interrupt_error, id="ctrl-c"),
        pytest.param(lambda: SystemExit(4), id="own-exit"),
    ],
)
def test_absent_stream_helpers_a_missing_stream_masks_what_the_other_one_ended_in(
    monkeypatch: pytest.MonkeyPatch,
    make_error: Callable[[], BaseException],
    missing_first: bool,
) -> None:
    """The other stream's flush ends in Ctrl+C or `SystemExit(4)`: it is returned.

    The same object comes back whichever order the two streams are given in.
    """
    redirections = record_redirections(monkeypatch)
    ended = Raised(make_error)
    stream = FlushFaultStream([ended], lambda text: True)
    stream.write("pending text\n")
    streams = (ABSENT, stream) if missing_first else (stream, ABSENT)

    returned = output_streams.flush_for_exit(*streams)

    assert stream.flush_fired
    assert returned is ended.first
    assert_no_redirection(redirections)
