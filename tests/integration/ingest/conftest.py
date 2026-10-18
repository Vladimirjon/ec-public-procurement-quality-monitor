"""Feature ingest-command (F4), outcome O2 (AC19, AC23): the guards of
`tests/integration/ingest`.

What this file provides, as `execution-plan.md` § Tests pins it:

- `network_guard` (autouse): the same guard as F2's, except that name resolution
  is allowed for the configured `POSTGRES_HOST` only. It patches
  `socket.socket.connect`, `connect_ex`, `socket.create_connection` and
  `socket.getaddrinfo`. `libpq` opens its own sockets outside Python, so
  PostgreSQL keeps working while any `httpx` attempt fails. A test that attempts
  the network on purpose (the proof tests) empties `attempts` itself; for every
  other test an attempt fails it at teardown;
- `real_raw_directory_is_untouched` (session, autouse): the names, sizes and
  modification times under the repository's real `data/raw/` at session start
  must be the same at session end. File contents are never read.

The host is read from `POSTGRES_HOST` in the process environment (unset or empty
means `127.0.0.1`, as in `tests/integration/conftest.py`); this file never reads
`.env` and never prints a setting.

Outcome O6b (AC8, AC9, AC10, AC14, AC16, AC19, AC24, AC25) adds the composition
helpers and the fault-injection seams of the CLI tests, after the guards:

- `IngestLab`, reached through the fixtures `migrated_lab` and `empty_lab`: one
  throwaway database (never the one named by `POSTGRES_DB`), a real
  `LocalDiskRawEvidenceStore` on `tmp_path`, the simulated source (`SercopSource`
  over `httpx.MockTransport`, no pause), a stepping clock and counting ids. It builds
  the `IngestWiring`, runs `run_ingest_command` or `main`, reads the stored state
  by direct SQL, and seeds runs through the real ports;
- the seams of the plan's table: `pg_terminate_backend` and `ALLOW_CONNECTIONS
  false` through the admin connection, a test session holding the exclusion or the
  migration lock, `KillBeforeFinishRepository` and `KillAfterFinishRepository`.

The environment of a command is built from the throwaway database's settings
object; no `.env` is read and no setting is printed. Test files cannot import this
file (the folders have no package marker), so everything reaches them through the
lab; their annotations import the names under `TYPE_CHECKING` only.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import socket
import time
from collections.abc import Callable, Collection, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, NoReturn
from urllib.parse import quote

import httpx
import psycopg
import pytest
from psycopg import sql

from ec_procurement_quality.application.ingest_ports import ClosableIngestionRepository
from ec_procurement_quality.application.raw_evidence_store import RawEvidenceStore
from ec_procurement_quality.domain.content_hash import ContentHash
from ec_procurement_quality.domain.ingestion_audit import (
    AuditEvent,
    IngestionRun,
    JsonValue,
    RunStatus,
)
from ec_procurement_quality.domain.ingestion_catalogue import IngestScope
from ec_procurement_quality.domain.persistence_errors import PersistenceConnectionError
from ec_procurement_quality.domain.raw_evidence import Observation
from ec_procurement_quality.infrastructure.local_disk_raw_evidence_store import (
    LocalDiskRawEvidenceStore,
)
from ec_procurement_quality.infrastructure.postgres_ingestion_repository import (
    PostgresIngestionRepository,
)
from ec_procurement_quality.infrastructure.postgres_migrations import apply_migrations
from ec_procurement_quality.infrastructure.postgres_settings import PostgresSettings
from ec_procurement_quality.infrastructure.sercop_source import SercopSource
from ec_procurement_quality.interfaces import cli
from ec_procurement_quality.interfaces.ingest_command import (
    ClosableSource,
    IngestWiring,
    run_ingest_command,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
REAL_RAW_ROOT = REPOSITORY_ROOT / "data" / "raw"
DEFAULT_POSTGRES_HOST = "127.0.0.1"

# --- The network guard ------------------------------------------------------


@dataclass
class NetworkGuard:
    """What the guard allows and what it refused during one test."""

    allowed_host: str
    attempts: list[str] = field(default_factory=list)


@pytest.fixture(autouse=True)
def network_guard(monkeypatch: pytest.MonkeyPatch) -> Iterator[NetworkGuard]:
    """Fail the test if it opens a socket or resolves any host but PostgreSQL's."""
    guard = NetworkGuard(
        allowed_host=os.environ.get("POSTGRES_HOST") or DEFAULT_POSTGRES_HOST
    )
    resolve = socket.getaddrinfo

    def blocked(name: str) -> Callable[..., NoReturn]:
        def refuse(*args: Any, **kwargs: Any) -> NoReturn:
            guard.attempts.append(name)
            raise OSError(f"synthetic network guard: {name} is blocked in tests")

        return refuse

    def resolve_configured_host_only(host: Any, *args: Any, **kwargs: Any) -> Any:
        if isinstance(host, str) and host == guard.allowed_host:
            return resolve(host, *args, **kwargs)
        guard.attempts.append("getaddrinfo")
        raise OSError("synthetic network guard: getaddrinfo is blocked in tests")

    monkeypatch.setattr(socket.socket, "connect", blocked("connect"))
    monkeypatch.setattr(socket.socket, "connect_ex", blocked("connect_ex"))
    monkeypatch.setattr(socket, "create_connection", blocked("create_connection"))
    monkeypatch.setattr(socket, "getaddrinfo", resolve_configured_host_only)

    yield guard

    assert guard.attempts == [], (
        f"the test tried to reach the network: {guard.attempts}"
    )


# --- The real data/raw/ stays untouched -------------------------------------

RawSnapshot = dict[str, tuple[str, int, int]]


def snapshot_of(root: Path) -> RawSnapshot:
    """Relative path -> (kind, size, modification time in ns) for everything
    under `root`. A missing `root` gives an empty snapshot. No file is opened."""
    if not root.exists():
        return {}
    entries: RawSnapshot = {}
    for path in sorted(root.rglob("*")):
        status = path.lstat()
        kind = "dir" if path.is_dir() and not path.is_symlink() else "file"
        entries[path.relative_to(root).as_posix()] = (
            kind,
            status.st_size,
            status.st_mtime_ns,
        )
    return entries


@pytest.fixture(scope="session", autouse=True)
def real_raw_directory_is_untouched() -> Iterator[None]:
    """The names, sizes and times under the real `data/raw/` do not change."""
    before = snapshot_of(REAL_RAW_ROOT)
    yield
    after = snapshot_of(REAL_RAW_ROOT)
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(
        name for name in set(before) & set(after) if before[name] != after[name]
    )
    assert (added, removed, changed) == ([], [], []), (
        "the integration session touched the real data/raw/: "
        f"added {added}, removed {removed}, changed {changed}"
    )


# --- Data and the simulated source (O6b) ------------------------------------

BASE_URL = "https://source.invalid/PLATAFORMA"
BUYER = "SYNTHETIC BUYER S.A."
YEAR = 2025
BODY_MARKER = "synthetic-body-marker"
JSON_HEADERS: tuple[tuple[str, str], ...] = (("Content-Type", "application/json"),)
GUAYAQUIL = timezone(timedelta(hours=-5))
CLOCK_START = datetime(2026, 10, 17, 10, 0, 0, tzinfo=GUAYAQUIL)
SEED_START = datetime(2026, 10, 16, 9, 0, 0, tzinfo=GUAYAQUIL)
TABLES = ("ingestion_run", "raw_evidence", "observation", "audit_event")
WAIT_SECONDS = 10

type Connection = psycopg.Connection[tuple[Any, ...]]
type OpenConnection = Callable[..., Connection]


def page_url(page: int) -> str:
    return (
        f"{BASE_URL}/api/search_ocds?local=1&year={YEAR}&page={page}"
        f"&buyer={quote(BUYER)}"
    )


def page_body(
    page: int, *, pages: int = 9, total: int | None = None, variant: str = ""
) -> bytes:
    """A synthetic search page body in the observed shape.

    A page above `pages` (or any page of a search with no results) has an empty
    `data`. `variant` changes the bytes of an otherwise equal page.
    """
    has_records = pages > 0 and page <= pages
    data = (
        [
            {
                "id": 9_000_000 + page,
                "ocid": f"ocds-5wno2w-SYNTHETIC-{page}{variant}",
                "year": YEAR,
                "buyer": BUYER,
                "title": f"Synthetic process {page}{variant} {BODY_MARKER}",
            }
        ]
        if has_records
        else []
    )
    body = {
        "total": len(data) if total is None else total,
        "page": page,
        "pages": pages,
        "data": data,
    }
    return json.dumps(body, separators=(",", ":")).encode("utf-8")


class BodyStream(httpx.SyncByteStream):
    """A response body yielded in one chunk, optionally failing after it."""

    def __init__(self, chunks: Sequence[bytes], error: BaseException | None) -> None:
        self._chunks = tuple(chunks)
        self._error = error

    def __iter__(self) -> Iterator[bytes]:
        yield from self._chunks
        if self._error is not None:
            raise self._error


@dataclass(frozen=True)
class Reply:
    """A scripted answer: a status and a body, which may be cut off by an error.

    `body` `None` means the page's own synthetic body. `cut_after` ends the body
    with a protocol error after that many bytes (the status is already sent).
    """

    status: int = 200
    body: bytes | None = None
    cut_after: int | None = None


class PageScript:
    """The `MockTransport` handler: one answer per request, counted per page.

    A page with no scripted reply left gets a valid `200` page body that reports
    `pages_reported` pages. A `before` hook runs when the page is first requested,
    before the answer; a `fail` step raises instead of answering.
    """

    def __init__(self) -> None:
        self.pages_reported = 9
        self.requests: list[int] = []
        self._replies: dict[int, list[Reply]] = {}
        self._hooks: dict[int, list[Callable[[], None]]] = {}
        self._failures: dict[int, list[Callable[[httpx.Request], BaseException]]] = {}

    def body(self, page: int, *, variant: str = "") -> bytes:
        return page_body(page, pages=self.pages_reported, variant=variant)

    def reply(self, page: int, *replies: Reply) -> None:
        self._replies.setdefault(page, []).extend(replies)

    def before(self, page: int, hook: Callable[[], None]) -> None:
        self._hooks.setdefault(page, []).append(hook)

    def fail(
        self, page: int, make_error: Callable[[httpx.Request], BaseException]
    ) -> None:
        self._failures.setdefault(page, []).append(make_error)

    def requests_for(self, page: int) -> int:
        return self.requests.count(page)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        self.requests.append(page)
        for hook in self._hooks.pop(page, []):
            hook()
        failures = self._failures.get(page)
        if failures:
            raise failures.pop(0)(request)
        replies = self._replies.get(page)
        reply = replies.pop(0) if replies else Reply()
        body = reply.body if reply.body is not None else self.body(page)
        if reply.cut_after is None:
            chunks: tuple[bytes, ...] = (body,) if body else ()
            error: BaseException | None = None
        else:
            chunks = (body[: reply.cut_after],)
            error = httpx.RemoteProtocolError("synthetic cut-off")
        return httpx.Response(
            reply.status,
            headers=[(b"content-type", b"application/json")],
            stream=BodyStream(chunks, error),
        )


class SteppingClock:
    """A `Clock` that starts at a fixed instant and steps one second per call."""

    def __init__(self, start: datetime = CLOCK_START) -> None:
        self._start = start
        self.calls = 0

    def now(self) -> datetime:
        value = self._start + timedelta(seconds=self.calls)
        self.calls += 1
        return value


class CountingIds:
    """An `ExecutionIdSource` that counts up (`...-00000001`, `...-00000002`, ...)."""

    def __init__(self) -> None:
        self.drawn: list[str] = []

    def new_execution_id(self, started_at: datetime) -> str:
        new_id = f"ingest-20261017t150000z-{len(self.drawn) + 1:08x}"
        self.drawn.append(new_id)
        return new_id


@dataclass
class CliResult:
    """What one invocation produced: the exit code and the two streams."""

    code: int
    out: str
    err: str

    @property
    def run_id(self) -> str:
        """The id on the one result line of stdout."""
        return self.result_line()[0]

    @property
    def status(self) -> str:
        return self.result_line()[1]

    def result_line(self) -> tuple[str, str]:
        lines = self.out.splitlines()
        assert len(lines) == 1, f"stdout is not one line: {self.out!r}"
        parts = lines[0].split(" ")
        assert len(parts) == 2, f"stdout is not '<id> <status>': {self.out!r}"
        return parts[0], parts[1]


# --- Repositories that kill their own backend (P-2 seams) -------------------


class DelegatingRepository:
    """Forwards every operation of the port to `inner`; a subclass overrides some.

    `finish_calls` records every `finish_run` it received, as `(status, finished_at)`.
    """

    def __init__(self, inner: PostgresIngestionRepository) -> None:
        self.inner = inner
        self.finish_calls: list[tuple[RunStatus, datetime]] = []
        self.committed: list[IngestionRun] = []

    def start_run(
        self, *, execution_id: str, scope: Mapping[str, JsonValue], started_at: datetime
    ) -> IngestionRun:
        return self.inner.start_run(
            execution_id=execution_id, scope=scope, started_at=started_at
        )

    def finish_run(
        self, *, execution_id: str, status: RunStatus, finished_at: datetime
    ) -> IngestionRun:
        self.finish_calls.append((status, finished_at))
        return self.inner.finish_run(
            execution_id=execution_id, status=status, finished_at=finished_at
        )

    def read_run(self, execution_id: str) -> IngestionRun:
        return self.inner.read_run(execution_id)

    def list_runs(self, status: RunStatus) -> tuple[IngestionRun, ...]:
        return self.inner.list_runs(status)

    def try_acquire_ingest_exclusion(self) -> bool:
        return self.inner.try_acquire_ingest_exclusion()

    def record_observation(self, observation: Observation) -> Observation:
        return self.inner.record_observation(observation)

    def read_observation(self, execution_id: str, sequence: int) -> Observation:
        return self.inner.read_observation(execution_id, sequence)

    def list_observations(self, execution_id: str) -> tuple[Observation, ...]:
        return self.inner.list_observations(execution_id)

    def append_audit_event(
        self,
        *,
        execution_id: str,
        occurred_at: datetime,
        event_type: str,
        detail: Mapping[str, JsonValue],
    ) -> AuditEvent:
        return self.inner.append_audit_event(
            execution_id=execution_id,
            occurred_at=occurred_at,
            event_type=event_type,
            detail=detail,
        )

    def list_audit_events(self, execution_id: str) -> tuple[AuditEvent, ...]:
        return self.inner.list_audit_events(execution_id)

    def close(self) -> None:
        self.inner.close()


class KillBeforeFinishRepository(DelegatingRepository):
    """On `finish_run(SUCCEEDED)` it first ends its own server session.

    It calls `pg_terminate_backend` for its own backend through the admin
    connection and waits until the backend is gone, runs `on_killed` (a refusal of
    the recovery, if the test wants one), and then delegates: the delegate raises
    `PersistenceConnectionError` and nothing is written (execution-plan seams
    table, AC8 P-2 "before commit").
    """

    def __init__(
        self,
        inner: PostgresIngestionRepository,
        *,
        lab: IngestLab,
        backend: int,
        on_killed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(inner)
        self._lab = lab
        self._backend = backend
        self._on_killed = on_killed

    def finish_run(
        self, *, execution_id: str, status: RunStatus, finished_at: datetime
    ) -> IngestionRun:
        if status is RunStatus.SUCCEEDED:
            self.finish_calls.append((status, finished_at))
            self._lab.terminate_backends({self._backend})
            if self._on_killed is not None:
                self._on_killed()
            return self.inner.finish_run(
                execution_id=execution_id, status=status, finished_at=finished_at
            )
        return super().finish_run(
            execution_id=execution_id, status=status, finished_at=finished_at
        )


class KillAfterFinishRepository(DelegatingRepository):
    """On `finish_run(SUCCEEDED)` it delegates (the commit happens), then lets go.

    It ends its own server session and raises `PersistenceConnectionError` itself,
    standing in for the reply lost on the wire (persistence U1: the real
    commit-in-flight loss is not deterministic). The run it committed is kept in
    `committed`.
    """

    def __init__(
        self,
        inner: PostgresIngestionRepository,
        *,
        lab: IngestLab,
        backend: int,
        on_killed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(inner)
        self._lab = lab
        self._backend = backend
        self._on_killed = on_killed

    def finish_run(
        self, *, execution_id: str, status: RunStatus, finished_at: datetime
    ) -> IngestionRun:
        run = super().finish_run(
            execution_id=execution_id, status=status, finished_at=finished_at
        )
        if status is not RunStatus.SUCCEEDED:
            return run
        self.committed.append(run)
        self._lab.terminate_backends({self._backend})
        if self._on_killed is not None:
            self._on_killed()
        raise PersistenceConnectionError("synthetic: the reply was lost")


type WrapRepository = Callable[[PostgresIngestionRepository, int], DelegatingRepository]


# --- Seeding the real ports -------------------------------------------------


class IngestSeeder:
    """Writes runs, observations and events through the real ports.

    A run is started, given its events and pages, and then finished (or left
    `running`). Times are fixed and earlier than the stepping clock of a command.
    """

    def __init__(
        self, repository: PostgresIngestionRepository, store: LocalDiskRawEvidenceStore
    ) -> None:
        self._repository = repository
        self._store = store
        self._runs = 0
        self._started: dict[str, datetime] = {}
        self._events: dict[str, int] = {}

    def run(
        self, execution_id: str, *, first_page: int = 1, last_page: int = 4
    ) -> None:
        """Start a run (leave it `running` until `finish`)."""
        started_at = SEED_START + timedelta(minutes=10 * self._runs)
        self._runs += 1
        self._started[execution_id] = started_at
        scope = IngestScope(
            base_url=BASE_URL,
            buyer=BUYER,
            year=YEAR,
            first_page=first_page,
            last_page=last_page,
        )
        self._repository.start_run(
            execution_id=execution_id, scope=scope.to_json(), started_at=started_at
        )

    def finish(self, execution_id: str, status: RunStatus = RunStatus.FAILED) -> None:
        self._repository.finish_run(
            execution_id=execution_id,
            status=status,
            finished_at=self._started[execution_id] + timedelta(minutes=5),
        )

    def _time(self, execution_id: str) -> datetime:
        self._events[execution_id] = self._events.get(execution_id, 0) + 1
        return self._started[execution_id] + timedelta(
            seconds=self._events[execution_id]
        )

    def event(
        self, execution_id: str, event_type: str, detail: Mapping[str, JsonValue]
    ) -> None:
        self._repository.append_audit_event(
            execution_id=execution_id,
            occurred_at=self._time(execution_id),
            event_type=event_type,
            detail=detail,
        )

    def started(
        self,
        execution_id: str,
        *,
        resumes: JsonValue = None,
        first_page: JsonValue = 1,
    ) -> None:
        self.event(
            execution_id, "run-started", {"resumes": resumes, "first_page": first_page}
        )

    def page(
        self,
        execution_id: str,
        page: int,
        sequence: int,
        *,
        local: bool = True,
        postgres: bool = True,
        event: bool = True,
    ) -> Observation:
        """A `200` response for `page` in the chosen stores, and its `page-completed`."""
        content = page_body(page)
        captured_at = self._time(execution_id)
        if local:
            observation = self._store.store(
                execution_id=execution_id,
                sequence=sequence,
                method="GET",
                url=page_url(page),
                status=200,
                headers=JSON_HEADERS,
                captured_at=captured_at,
                content=content,
            )
        else:
            observation = Observation(
                execution_id=execution_id,
                sequence=sequence,
                method="GET",
                url=page_url(page),
                status=200,
                headers=JSON_HEADERS,
                captured_at=captured_at,
                content_hash=ContentHash.of(content),
                size=len(content),
            )
        if postgres:
            self._repository.record_observation(observation)
        if event:
            self.event(
                execution_id,
                "page-completed",
                {
                    "page": page,
                    "sequence": sequence,
                    "content_hash": observation.content_hash.hexdigest,
                },
            )
        return observation

    def completed(
        self, execution_id: str, *pages: int, first_sequence: int = 1
    ) -> None:
        for offset, page in enumerate(pages):
            self.page(execution_id, page, first_sequence + offset)

    def last_page(self, execution_id: str, page: JsonValue, pages: JsonValue) -> None:
        self.event(execution_id, "last-page-reached", {"page": page, "pages": pages})


# --- The lab ----------------------------------------------------------------


class IngestLab:
    """Everything one CLI integration test needs, over one throwaway database.

    The command runs with an injected wiring: the real `LocalDiskRawEvidenceStore`
    on `root` (a `tmp_path` folder; `make_store` ignores the path it is given), the
    real `PostgresIngestionRepository` and `apply_migrations` on the throwaway
    database, and the simulated source. `calls` records the order in which the
    wiring was used; `opens` counts the repositories requested.
    """

    A = "ingest-20261016t100000z-aaaaaaaa"
    B = "ingest-20261016t100000z-bbbbbbbb"
    C = "ingest-20261016t100000z-cccccccc"
    ABSENT = "ingest-20261014t150000z-ffffffff"

    def __init__(
        self,
        *,
        settings: PostgresSettings,
        root: Path,
        admin: Connection,
        open_connection: OpenConnection,
    ) -> None:
        self.settings = settings
        self.root = root
        self.store = LocalDiskRawEvidenceStore(root)
        self.pages = PageScript()
        self.clock = SteppingClock()
        self.ids = CountingIds()
        self.calls: list[str] = []
        self.store_roots: list[Path] = []
        self.sources: list[SercopSource] = []
        self.opens = 0
        self.wrapped: list[DelegatingRepository] = []
        self._wrappers: dict[int, WrapRepository] = {}
        self._repositories: list[PostgresIngestionRepository] = []
        self._admin = admin
        self._open_connection = open_connection

    # --- The command ---

    def environ(self) -> dict[str, str]:
        """The variables of the throwaway database, as the command reads them."""
        settings = self.settings
        return {
            "POSTGRES_HOST": settings.host,
            "POSTGRES_PORT": str(settings.port),
            "POSTGRES_DB": settings.dbname,
            "POSTGRES_USER": settings.user,
            "POSTGRES_PASSWORD": settings.password,
        }

    def make_source(self, now: Callable[[], datetime]) -> ClosableSource:
        self.calls.append("make_source")
        source = SercopSource(
            base_url=BASE_URL,
            transport=httpx.MockTransport(self.pages),
            now=now,
            sleep=lambda seconds: None,
            min_interval=0,
            cooldown=0,
        )
        self.sources.append(source)
        return source

    def make_store(self, root: Path) -> RawEvidenceStore:
        self.calls.append("make_store")
        self.store_roots.append(root)
        return self.store

    def make_repository(
        self, settings: PostgresSettings
    ) -> ClosableIngestionRepository:
        self.calls.append("make_repository")
        self.opens += 1
        wrap = self._wrappers.get(self.opens)
        before = self.backends() if wrap is not None else frozenset[int]()
        repository = PostgresIngestionRepository(settings)
        self._repositories.append(repository)
        if wrap is None:
            return repository
        own = self.backends() - before
        assert len(own) == 1, "could not tell which backend is the repository's own"
        wrapped = wrap(repository, next(iter(own)))
        self.wrapped.append(wrapped)
        return wrapped

    def migrate(self, settings: PostgresSettings, directory: Path) -> tuple[str, ...]:
        self.calls.append("migrate")
        applied = apply_migrations(settings, directory)
        self.calls.append("migrate:done")
        return applied

    def wiring(
        self,
        *,
        make_store: Callable[[Path], RawEvidenceStore] | None = None,
        migrate: Callable[[PostgresSettings, Path], tuple[str, ...]] | None = None,
    ) -> IngestWiring:
        return IngestWiring(
            base_url=BASE_URL,
            make_source=self.make_source,
            make_store=self.make_store if make_store is None else make_store,
            make_repository=self.make_repository,
            migrate=self.migrate if migrate is None else migrate,
            clock=self.clock,
            execution_ids=self.ids,
        )

    def run(
        self,
        argv: Sequence[str],
        *,
        environ: Mapping[str, str] | None = None,
        wiring: IngestWiring | None = None,
    ) -> CliResult:
        """Run `ingest <argv>` through `run_ingest_command`."""
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            try:
                arguments = cli.build_parser().parse_args(["ingest", *argv])
                code = run_ingest_command(
                    arguments,
                    environ=self.environ() if environ is None else environ,
                    wiring=self.wiring() if wiring is None else wiring,
                    stdout=out,
                    stderr=err,
                )
            except SystemExit as stop:
                assert isinstance(stop.code, int)
                code = stop.code
        return CliResult(code, out.getvalue(), err.getvalue())

    def run_main(
        self,
        argv: Sequence[str],
        *,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        wiring: IngestWiring | None = None,
    ) -> CliResult:
        """Run `main(["ingest", ...])` with this lab's environment and wiring."""
        for name, value in self.environ().items():
            monkeypatch.setenv(name, value)
        chosen = self.wiring() if wiring is None else wiring
        monkeypatch.setattr(cli, "default_wiring", lambda: chosen)
        with pytest.raises(SystemExit) as stop:
            cli.main(["ingest", *argv])
        assert isinstance(stop.value.code, int)
        captured = capsys.readouterr()
        return CliResult(stop.value.code, captured.out, captured.err)

    # --- The seams ---

    def kill_before_final_finish(
        self, *, on_killed: Callable[[], None] | None = None, open_index: int = 1
    ) -> None:
        """The repository opened `open_index`-th ends its session before the finish."""

        def build(
            repository: PostgresIngestionRepository, backend: int
        ) -> DelegatingRepository:
            return KillBeforeFinishRepository(
                repository, lab=self, backend=backend, on_killed=on_killed
            )

        self._wrappers[open_index] = build

    def kill_after_final_finish(
        self, *, on_killed: Callable[[], None] | None = None, open_index: int = 1
    ) -> None:
        """The repository opened `open_index`-th loses its reply after the commit."""

        def build(
            repository: PostgresIngestionRepository, backend: int
        ) -> DelegatingRepository:
            return KillAfterFinishRepository(
                repository, lab=self, backend=backend, on_killed=on_killed
            )

        self._wrappers[open_index] = build

    def backends(self) -> frozenset[int]:
        """The pids of the sessions on the throwaway database (admin excluded)."""
        rows = self._admin.execute(
            "SELECT pid FROM pg_stat_activity WHERE datname = %s",
            (self.settings.dbname,),
        ).fetchall()
        return frozenset(int(row[0]) for row in rows)

    def terminate_backends(self, pids: Collection[int] | None = None) -> None:
        """End the given sessions (all of the database's when `None`) and wait."""
        deadline = time.monotonic() + WAIT_SECONDS
        while True:
            targets = sorted(self.backends() if pids is None else pids)
            for pid in targets:
                self._admin.execute("SELECT pg_terminate_backend(%s)", (pid,))
            left = self.backends() & frozenset(targets)
            if not left:
                return
            if time.monotonic() > deadline:
                pytest.fail("the sessions of the throwaway database did not end")
            time.sleep(0.05)

    def refuse_connections(self) -> None:
        """New connections to the throwaway database are refused."""
        self._admin.execute(
            sql.SQL("ALTER DATABASE {} ALLOW_CONNECTIONS false").format(
                sql.Identifier(self.settings.dbname)
            )
        )

    def allow_connections(self) -> None:
        self._admin.execute(
            sql.SQL("ALTER DATABASE {} ALLOW_CONNECTIONS true").format(
                sql.Identifier(self.settings.dbname)
            )
        )

    def hold(self, key: int) -> Connection:
        """A test session that holds the advisory lock `key` until the test ends."""
        connection = self._open_connection(self.settings)
        row = connection.execute(
            "SELECT pg_try_advisory_lock(%s::bigint)", (key,)
        ).fetchone()
        assert row is not None
        assert row[0] is True, "the test session did not get the lock"
        return connection

    def reply(
        self,
        *,
        status: int = 200,
        body: bytes | None = None,
        cut_after: int | None = None,
    ) -> Reply:
        """A scripted answer for `pages.reply(page, ...)`; `cut_after` cuts the body."""
        return Reply(status=status, body=body, cut_after=cut_after)

    def on_request(self, page: int, hook: Callable[[], None]) -> None:
        """Run `hook` when `page` is first requested (a kill, a changed directory)."""
        self.pages.before(page, hook)

    # --- Reading the stored state ---

    def query(
        self, statement: str, params: Sequence[object] = ()
    ) -> list[tuple[Any, ...]]:
        """Run a read-only statement on a short-lived connection."""
        with psycopg.connect(
            host=self.settings.host,
            port=self.settings.port,
            dbname=self.settings.dbname,
            user=self.settings.user,
            password=self.settings.password,
            autocommit=True,
            connect_timeout=5,
        ) as connection:
            return connection.execute(statement, params).fetchall()

    def run_row(self, execution_id: str) -> tuple[str, datetime | None, dict[str, Any]]:
        """`(status, finished_at, scope)` of the run."""
        rows = self.query(
            "SELECT status, finished_at, scope FROM ingestion_run "
            "WHERE execution_id = %s",
            (execution_id,),
        )
        assert len(rows) == 1, f"no single run {execution_id}"
        return str(rows[0][0]), rows[0][1], dict(rows[0][2])

    def run_ids(self) -> list[str]:
        rows = self.query(
            "SELECT execution_id FROM ingestion_run ORDER BY started_at, execution_id"
        )
        return [str(row[0]) for row in rows]

    def events(self, execution_id: str) -> list[tuple[str, dict[str, Any]]]:
        rows = self.query(
            "SELECT event_type, detail FROM audit_event "
            "WHERE execution_id = %s ORDER BY event_id",
            (execution_id,),
        )
        return [(str(row[0]), dict(row[1])) for row in rows]

    def event_types(self, execution_id: str) -> list[str]:
        return [event_type for event_type, _ in self.events(execution_id)]

    def details(self, execution_id: str, event_type: str) -> list[dict[str, Any]]:
        return [
            detail for found, detail in self.events(execution_id) if found == event_type
        ]

    def observation_rows(self, execution_id: str) -> list[tuple[int, int, str]]:
        """`(sequence, status, content_hash)` of the run's observations."""
        rows = self.query(
            "SELECT sequence, status, content_hash FROM observation "
            "WHERE execution_id = %s ORDER BY sequence",
            (execution_id,),
        )
        return [(int(row[0]), int(row[1]), str(row[2])) for row in rows]

    def stored_observation(self, execution_id: str, sequence: int) -> Observation:
        """The observation as PostgreSQL holds it (read through the real adapter)."""
        with PostgresIngestionRepository(self.settings) as repository:
            return repository.read_observation(execution_id, sequence)

    def started_at(self, execution_id: str) -> datetime:
        rows = self.query(
            "SELECT started_at FROM ingestion_run WHERE execution_id = %s",
            (execution_id,),
        )
        assert len(rows) == 1, f"no single run {execution_id}"
        return rows[0][0]

    def evidence_rows(self) -> list[tuple[str, int]]:
        rows = self.query("SELECT content_hash, size FROM raw_evidence ORDER BY 1")
        return [(str(row[0]), int(row[1])) for row in rows]

    def counts(self) -> dict[str, int]:
        return {
            table: int(self.query(f"SELECT count(*) FROM {table}")[0][0])
            for table in TABLES
        }

    def table_exists(self, table: str) -> bool:
        rows = self.query("SELECT to_regclass(%s) IS NOT NULL", (table,))
        return bool(rows[0][0])

    def local_sequences(self, execution_id: str) -> tuple[int, ...]:
        return self.store.list_observation_sequences(execution_id)

    def files(self, root: Path | None = None) -> dict[str, tuple[int, int, str]]:
        """Relative path -> (size, modification time in ns, SHA-256) of every file."""
        base = self.root if root is None else root
        found: dict[str, tuple[int, int, str]] = {}
        if not base.exists():
            return found
        for path in sorted(base.rglob("*")):
            if path.is_file():
                status = path.stat()
                found[path.relative_to(base).as_posix()] = (
                    status.st_size,
                    status.st_mtime_ns,
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                )
        return found

    def object_files(self) -> dict[str, tuple[int, int, str]]:
        return {
            name: found
            for name, found in self.files().items()
            if name.startswith("objects/")
        }

    # --- Seeding ---

    @contextlib.contextmanager
    def seeding(self) -> Iterator[IngestSeeder]:
        """Write runs and observations through the real ports, then let go."""
        repository = PostgresIngestionRepository(self.settings)
        try:
            yield IngestSeeder(repository, self.store)
        finally:
            repository.close()

    def close(self) -> None:
        for source in self.sources:
            source.close()
        for repository in self._repositories:
            repository.close()


def _lab(
    settings: PostgresSettings,
    tmp_path: Path,
    admin: Connection,
    open_connection: OpenConnection,
) -> IngestLab:
    return IngestLab(
        settings=settings,
        root=tmp_path / "raw",
        admin=admin,
        open_connection=open_connection,
    )


@pytest.fixture
def migrated_lab(
    migrated_database: PostgresSettings,
    tmp_path: Path,
    admin_connection: Connection,
    open_connection: OpenConnection,
) -> Iterator[IngestLab]:
    """A lab over a migrated throwaway database."""
    lab = _lab(migrated_database, tmp_path, admin_connection, open_connection)
    try:
        yield lab
    finally:
        lab.close()


@pytest.fixture
def empty_lab(
    empty_database: PostgresSettings,
    tmp_path: Path,
    admin_connection: Connection,
    open_connection: OpenConnection,
) -> Iterator[IngestLab]:
    """A lab over an empty throwaway database (the command applies the schema)."""
    lab = _lab(empty_database, tmp_path, admin_connection, open_connection)
    try:
        yield lab
    finally:
        lab.close()
