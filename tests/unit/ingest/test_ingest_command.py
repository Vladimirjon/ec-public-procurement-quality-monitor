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

Data is synthetic: the source is `https://source.invalid/PLATAFORMA`, the buyer
`SYNTHETIC BUYER S.A.`, the year 2025, and the markers `synthetic-password-marker`,
`synthetic-body-marker` and `synthetic-header-marker`.
"""

from __future__ import annotations

import io
import json
import logging
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
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
from ec_procurement_quality.interfaces import cli, ingest_command
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
