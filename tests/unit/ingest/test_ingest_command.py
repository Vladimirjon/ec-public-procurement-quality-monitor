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
from typing import TYPE_CHECKING

import httpx
import pytest

from ec_procurement_quality.application.ingest_ports import ClosableIngestionRepository
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
)
from ec_procurement_quality.infrastructure.postgres_migrations import apply_migrations
from ec_procurement_quality.infrastructure.postgres_settings import PostgresSettings
from ec_procurement_quality.infrastructure.sercop_source import SercopSource
from ec_procurement_quality.interfaces import cli
from ec_procurement_quality.interfaces.ingest_command import (
    IngestWiring,
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
        return self.lab.store

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
    """AC14, AC16: an invalid migrations history stops the command at exit 2."""

    def refuse(settings: PostgresSettings, directory: Path) -> tuple[str, ...]:
        raise MigrationError("migration file 'bad.sql' is not named NNNN_description")

    rig.migrate_impl = refuse
    rig.forbid("make_source", "make_store", "make_repository")

    result = rig.invoke([*SCOPE_ARGS, "--migrations-dir", "bad-migrations"])

    assert result.code == 2
    assert result.out == ""
    assert result.err.strip() != ""
    assert PASSWORD_MARKER not in result.err
    assert rig.calls == ["migrate"]
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
    rig.forbid("make_source", "make_store", "make_repository")
    directory = make_directory(tmp_path)

    result = rig.invoke(
        [*SCOPE_ARGS, "--migrations-dir", str(directory)],
        environ={**GOOD_ENVIRON, "POSTGRES_PORT": "1"},
    )

    assert result.code == 2
    assert result.out == ""
    assert result.err.strip() != ""
    assert PASSWORD_MARKER not in result.err
    assert rig.calls == ["migrate"]
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
    """Exit table: a `KeyboardInterrupt` in steps 1 to 4 -> 130, nothing built."""

    def interrupted(settings: PostgresSettings, directory: Path) -> tuple[str, ...]:
        raise KeyboardInterrupt

    rig.migrate_impl = interrupted

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == 130
    assert result.out == ""
    assert rig.calls == ["migrate"]
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
    """Exit table: a `KeyboardInterrupt` that escapes `run_ingest` -> 130."""
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
    rig.forbid("make_source", "make_store", "make_repository")

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == code
    assert result.out == ""
    assert result.err.strip() != ""
    assert PASSWORD_MARKER not in result.err
    assert rig.calls == ["migrate"]
    assert rig.sources == []
    assert rig.lab.opener.opens == 0


def test_exit_code_order_of_invocation_migrate_returns_before_the_repository(
    rig: Rig,
) -> None:
    """AC16: `apply_migrations` returns before `make_repository` is called."""
    result = rig.invoke(SCOPE_ARGS)

    assert result.code == 0
    assert rig.calls[0] == "migrate"
    assert "migrate:done" in rig.calls
    assert rig.calls.index("migrate:done") < rig.calls.index("make_repository")
    assert rig.calls.count("migrate") == 1
    assert rig.calls.count("make_source") == 1
    assert rig.calls.count("make_store") == 1
    assert rig.calls.count("make_repository") == 1


def test_exit_code_order_of_invocation_a_refused_migration_builds_no_repository(
    rig: Rig,
) -> None:
    """AC16: a failing runner means no repository, source or store was built."""

    def fail(settings: PostgresSettings, directory: Path) -> tuple[str, ...]:
        raise MigrationLockError("another migration run holds the lock")

    rig.migrate_impl = fail

    result = rig.invoke(SCOPE_ARGS)

    assert result.code == 1
    assert "make_repository" not in rig.calls
    assert "make_source" not in rig.calls


def test_exit_code_1_an_exception_that_escapes_the_use_case_names_its_class_only(
    rig: Rig,
) -> None:
    """Exit table: any exception escaping `run_ingest` -> 1, the class name alone."""
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
