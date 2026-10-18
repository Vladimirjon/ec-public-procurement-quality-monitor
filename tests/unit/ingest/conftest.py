"""Feature ingest-command (F4), outcome O4 (AC18, AC19): the doubles of
`tests/unit/ingest`.

What this file provides, as `execution-plan.md` § Tests and its seams table pin it:

- `network_guard` (autouse): fails the test if it opens a socket or resolves a
  host name (it patches `socket.socket.connect`, `connect_ex`,
  `socket.create_connection` and `socket.getaddrinfo`);
- `InMemoryRawEvidenceStore`, which keeps objects and observations in dicts and
  applies F1's `Observation` validation, and `InMemoryIngestionRepository`,
  which applies the identity and idempotency rules of PS-7 to PS-9 and models
  the ingest exclusion as a flag shared by every repository of one
  `InMemoryDatabase`. Both implement the extended ports;
- `FakeSource`, `FixedClock`, `ScriptedExecutionIds`, `RecordingReporter` and
  `RepositoryOpenerDouble`;
- the fault-injection seams: `PublishThenFailStore`, `RefusingStore` and
  `FlakyRepository` (commit-then-raise or raise-before-commit on the n-th call
  of an operation, a refusal, a `KeyboardInterrupt`);
- `Seeder`, which writes runs, observations and events straight into the doubles
  for the resume, reconcile and chain cases, and `TransportScript`, the
  `httpx.MockTransport` handler for the cases that go through `SercopSource`.

The test files cannot import from this file (the test folders have no package
marker), so everything reaches them through the `lab` fixture, a `Lab`. Their
type annotations import `Lab` under `TYPE_CHECKING` only.

Data is synthetic: the source is `https://source.invalid/PLATAFORMA`, the buyer
`SYNTHETIC BUYER S.A.`, the year 2025, and page bodies carry the marker
`synthetic-body-marker`. Nothing here touches the network, a database, the disk
or `.env`.
"""

from __future__ import annotations

import json
import socket
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, ClassVar, Literal, NoReturn
from urllib.parse import quote

import httpx
import pytest

from ec_procurement_quality.application.ingest_ports import (
    Clock,
    ClosableIngestionRepository,
    ExecutionIdSource,
    IngestReporter,
    RepositoryOpener,
)
from ec_procurement_quality.application.ingestion_repository import IngestionRepository
from ec_procurement_quality.application.procurement_source import (
    ProcurementSource,
    RecordResponse,
    SearchPage,
)
from ec_procurement_quality.application.raw_evidence_store import RawEvidenceStore
from ec_procurement_quality.domain.content_hash import ContentHash
from ec_procurement_quality.domain.ingestion_audit import (
    AuditEvent,
    IngestionRun,
    JsonValue,
    RunStatus,
    same_json,
)
from ec_procurement_quality.domain.ingestion_catalogue import IngestScope
from ec_procurement_quality.domain.persistence_errors import (
    PersistenceConnectionError,
    PersistenceError,
    PersistenceIntegrityError,
    PersistenceNotFoundError,
)
from ec_procurement_quality.domain.raw_evidence import (
    EvidenceIntegrityError,
    EvidenceNotFoundError,
    Observation,
    validate_execution_id,
    validate_sequence,
)
from ec_procurement_quality.domain.source_response import (
    IncompleteResponseError,
    RawResponse,
    SourceStatusError,
    SourceTransportError,
)
from ec_procurement_quality.infrastructure.sercop_source import SercopSource

BASE_URL = "https://source.invalid/PLATAFORMA"
BUYER = "SYNTHETIC BUYER S.A."
YEAR = 2025
BODY_MARKER = "synthetic-body-marker"
JSON_HEADERS: tuple[tuple[str, str], ...] = (("Content-Type", "application/json"),)
GUAYAQUIL = timezone(timedelta(hours=-5))
CLOCK_START = datetime(2026, 10, 17, 10, 0, 0, tzinfo=GUAYAQUIL)
SEED_START = datetime(2026, 10, 16, 9, 0, 0, tzinfo=GUAYAQUIL)

# --- The network guard (AC19) -----------------------------------------------


@dataclass
class NetworkGuard:
    """Records every attempt to open a socket or resolve a host name."""

    attempts: list[str] = field(default_factory=list)


@pytest.fixture(autouse=True)
def network_guard(monkeypatch: pytest.MonkeyPatch) -> Iterator[NetworkGuard]:
    """Fail the test if it opens a socket or resolves a host name."""
    guard = NetworkGuard()

    def blocked(name: str) -> Callable[..., NoReturn]:
        def refuse(*args: Any, **kwargs: Any) -> NoReturn:
            guard.attempts.append(name)
            raise OSError(f"synthetic network guard: {name} is blocked in tests")

        return refuse

    monkeypatch.setattr(socket.socket, "connect", blocked("socket.connect"))
    monkeypatch.setattr(socket.socket, "connect_ex", blocked("socket.connect_ex"))
    monkeypatch.setattr(socket, "create_connection", blocked("create_connection"))
    monkeypatch.setattr(socket, "getaddrinfo", blocked("getaddrinfo"))

    yield guard

    assert guard.attempts == [], (
        f"the test tried to reach the network: {guard.attempts}"
    )


# --- Page bodies and responses ----------------------------------------------


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
    `data`, as the source answers beyond the last page. `variant` changes the
    bytes of an otherwise equal page.
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


def raw_response(
    page: int,
    *,
    status: int = 200,
    body: bytes,
    captured_at: datetime,
    headers: tuple[tuple[str, str], ...] = JSON_HEADERS,
) -> RawResponse:
    return RawResponse(
        method="GET",
        url=page_url(page),
        status=status,
        headers=headers,
        captured_at=captured_at,
        content=body,
    )


# --- Journal ----------------------------------------------------------------


class Journal:
    """The order of the writes the doubles saw: store, repository, reporter.

    An entry is `(operation, execution_id, detail)`. Reads are not recorded.
    """

    def __init__(self) -> None:
        self.entries: list[tuple[str, str, str]] = []

    def record(self, operation: str, execution_id: str = "", detail: str = "") -> None:
        self.entries.append((operation, execution_id, detail))

    def labels(self, execution_id: str | None = None) -> list[str]:
        """`operation:detail` of each entry, for one run when `execution_id` is given.

        The entries with no run (the exclusion) are left out of a run's labels.
        """
        return [
            f"{operation}:{detail}" if detail else operation
            for operation, entry_id, detail in self.entries
            if execution_id is None or entry_id == execution_id
        ]


# --- The raw evidence store double ------------------------------------------


class InMemoryRawEvidenceStore:
    """`RawEvidenceStore` over dicts, with F1's validation and no disk."""

    def __init__(self, journal: Journal) -> None:
        self._journal = journal
        self.objects: dict[ContentHash, bytes] = {}
        self.observations: dict[tuple[str, int], Observation] = {}
        self._unreadable: set[tuple[str, int]] = set()
        self._listing_errors: dict[str, BaseException] = {}

    # --- Port ---

    def store(
        self,
        *,
        execution_id: str,
        sequence: int,
        method: str,
        url: str,
        status: int,
        headers: Sequence[tuple[str, str]],
        captured_at: datetime,
        content: bytes,
    ) -> Observation:
        if not isinstance(content, bytes):
            raise TypeError("content must be bytes")
        kept = tuple(
            (name, value) for name, value in headers if name.lower() != "set-cookie"
        )
        content_hash = ContentHash.of(content)
        observation = Observation(
            execution_id=execution_id,
            sequence=sequence,
            method=method,
            url=url,
            status=status,
            headers=kept,
            captured_at=captured_at,
            content_hash=content_hash,
            size=len(content),
        )
        existing_object = self.objects.get(content_hash)
        if existing_object is not None and ContentHash.of(existing_object) != (
            content_hash
        ):
            raise EvidenceIntegrityError("an object exists with bytes that differ")
        key = (execution_id, sequence)
        existing = self.observations.get(key)
        if existing is not None and existing != observation:
            raise EvidenceIntegrityError(
                f"observation {execution_id}/{sequence} exists with different data"
            )
        self.objects.setdefault(content_hash, content)
        self.observations[key] = observation
        self._journal.record("store", execution_id, str(sequence))
        return observation

    def read_content(self, content_hash: ContentHash) -> bytes:
        content = self.objects.get(content_hash)
        if content is None:
            raise EvidenceNotFoundError(f"no object for {content_hash.hexdigest}")
        if ContentHash.of(content) != content_hash:
            raise EvidenceIntegrityError(
                f"object {content_hash.hexdigest} does not match its name"
            )
        return content

    def read_observation(self, execution_id: str, sequence: int) -> Observation:
        validate_execution_id(execution_id)
        validate_sequence(sequence)
        key = (execution_id, sequence)
        if key in self._unreadable:
            raise EvidenceIntegrityError(
                f"observation {execution_id}/{sequence} is not a valid record"
            )
        observation = self.observations.get(key)
        if observation is None:
            raise EvidenceNotFoundError(f"no observation {execution_id}/{sequence}")
        return observation

    def list_observation_sequences(self, execution_id: str) -> tuple[int, ...]:
        validate_execution_id(execution_id)
        failure = self._listing_errors.get(execution_id)
        if failure is not None:
            raise failure
        return tuple(
            sorted(
                sequence
                for stored_id, sequence in self.observations
                if stored_id == execution_id
            )
        )

    # --- Test hooks (not part of the port, no journal entry) ---

    def put(self, observation: Observation, content: bytes) -> None:
        """Place an object and its observation, as a finished `store` would."""
        self.objects.setdefault(observation.content_hash, content)
        self.observations[(observation.execution_id, observation.sequence)] = (
            observation
        )

    def put_object(self, content: bytes) -> ContentHash:
        """Place an orphan object: bytes with no observation."""
        content_hash = ContentHash.of(content)
        self.objects.setdefault(content_hash, content)
        return content_hash

    def replace_observation(self, observation: Observation) -> None:
        self.observations[(observation.execution_id, observation.sequence)] = (
            observation
        )

    def remove_object(self, content_hash: ContentHash) -> None:
        del self.objects[content_hash]

    def tamper_object(self, content_hash: ContentHash, content: bytes) -> None:
        self.objects[content_hash] = content

    def make_unreadable(self, execution_id: str, sequence: int) -> None:
        """The record is still listed, and reading it raises `EvidenceIntegrityError`."""
        self._unreadable.add((execution_id, sequence))

    def fail_listing(self, execution_id: str, error: BaseException) -> None:
        self._listing_errors[execution_id] = error


class PublishThenFailStore:
    """Publishes through `inner` and then raises on the n-th `store` (N2, AC6 b).

    With `KeyboardInterrupt` as the error it is the interrupt after the local
    store and before PostgreSQL (AC7).
    """

    def __init__(
        self,
        inner: RawEvidenceStore,
        *,
        on_call: int,
        error: Callable[[], BaseException] = lambda: OSError(
            "synthetic: the disk failed after publication"
        ),
    ) -> None:
        self._inner = inner
        self._on_call = on_call
        self._error = error
        self._calls = 0

    def store(
        self,
        *,
        execution_id: str,
        sequence: int,
        method: str,
        url: str,
        status: int,
        headers: Sequence[tuple[str, str]],
        captured_at: datetime,
        content: bytes,
    ) -> Observation:
        self._calls += 1
        observation = self._inner.store(
            execution_id=execution_id,
            sequence=sequence,
            method=method,
            url=url,
            status=status,
            headers=headers,
            captured_at=captured_at,
            content=content,
        )
        if self._calls == self._on_call:
            raise self._error()
        return observation

    def read_content(self, content_hash: ContentHash) -> bytes:
        return self._inner.read_content(content_hash)

    def read_observation(self, execution_id: str, sequence: int) -> Observation:
        return self._inner.read_observation(execution_id, sequence)

    def list_observation_sequences(self, execution_id: str) -> tuple[int, ...]:
        return self._inner.list_observation_sequences(execution_id)


class RefusingStore:
    """Raises on the n-th `store` before anything is published."""

    def __init__(
        self,
        inner: RawEvidenceStore,
        *,
        on_call: int,
        error: Callable[[], BaseException] = lambda: OSError(
            "synthetic: the disk refused the write"
        ),
    ) -> None:
        self._inner = inner
        self._on_call = on_call
        self._error = error
        self._calls = 0

    def store(
        self,
        *,
        execution_id: str,
        sequence: int,
        method: str,
        url: str,
        status: int,
        headers: Sequence[tuple[str, str]],
        captured_at: datetime,
        content: bytes,
    ) -> Observation:
        self._calls += 1
        if self._calls == self._on_call:
            raise self._error()
        return self._inner.store(
            execution_id=execution_id,
            sequence=sequence,
            method=method,
            url=url,
            status=status,
            headers=headers,
            captured_at=captured_at,
            content=content,
        )

    def read_content(self, content_hash: ContentHash) -> bytes:
        return self._inner.read_content(content_hash)

    def read_observation(self, execution_id: str, sequence: int) -> Observation:
        return self._inner.read_observation(execution_id, sequence)

    def list_observation_sequences(self, execution_id: str) -> tuple[int, ...]:
        return self._inner.list_observation_sequences(execution_id)


# --- The repository double --------------------------------------------------

_OTHER_SESSION = object()


@dataclass(frozen=True)
class RunState:
    """What one run holds, in a form that two moments can be compared by `==`."""

    status: RunStatus
    finished_at: datetime | None
    observations: tuple[tuple[int, str], ...]
    events: tuple[tuple[int, str, str], ...]


@dataclass(frozen=True)
class LabState:
    """Everything the doubles hold, comparable by `==`."""

    runs: dict[str, RunState]
    evidence: frozenset[ContentHash]
    objects: frozenset[ContentHash]
    local_observations: frozenset[tuple[str, int]]


class InMemoryDatabase:
    """The state that every `InMemoryIngestionRepository` of one test shares.

    It stands for the PostgreSQL database: runs, observations, `raw_evidence`
    rows, events, and the holder of the ingest exclusion.
    """

    def __init__(self) -> None:
        self.runs: dict[str, IngestionRun] = {}
        self.observations: dict[tuple[str, int], Observation] = {}
        self.evidence: dict[ContentHash, int] = {}
        self.events: dict[str, list[AuditEvent]] = {}
        self.exclusion_holder: object | None = None
        self.next_event_id = 1

    def hold_exclusion_elsewhere(self) -> None:
        """Another session takes the exclusion (it must be free)."""
        assert self.exclusion_holder is None
        self.exclusion_holder = _OTHER_SESSION

    def release_exclusion_elsewhere(self) -> None:
        if self.exclusion_holder is _OTHER_SESSION:
            self.exclusion_holder = None

    def run_state(self, execution_id: str) -> RunState:
        run = self.runs[execution_id]
        return RunState(
            status=run.status,
            finished_at=run.finished_at,
            observations=tuple(
                sorted(
                    (sequence, observation.content_hash.hexdigest)
                    for (stored_id, sequence), observation in self.observations.items()
                    if stored_id == execution_id
                )
            ),
            events=tuple(
                (
                    event.event_id,
                    event.event_type,
                    json.dumps(dict(event.detail), sort_keys=True),
                )
                for event in self.events.get(execution_id, [])
            ),
        )


class InMemoryIngestionRepository:
    """`IngestionRepository` over an `InMemoryDatabase`, with PS-7 to PS-9 rules.

    One repository is one connection: `lose_connection()` ends it the way a
    killed session does (every operation raises `PersistenceConnectionError` and
    the exclusion it held is gone), and `close()` releases the exclusion.
    """

    def __init__(
        self, database: InMemoryDatabase, journal: Journal | None = None
    ) -> None:
        self._database = database
        self._journal = journal if journal is not None else Journal()
        self._closed = False
        self._lost = False

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def lost(self) -> bool:
        return self._lost

    def lose_connection(self) -> None:
        self._lost = True
        self._release()

    def _release(self) -> None:
        if self._database.exclusion_holder is self:
            self._database.exclusion_holder = None

    def _require_usable(self, operation: str) -> None:
        if self._closed:
            raise RuntimeError("the ingestion repository is closed")
        if self._lost:
            raise PersistenceConnectionError(
                f"{operation}: the database connection was lost"
            )

    # --- Runs ---

    def start_run(
        self, *, execution_id: str, scope: Mapping[str, JsonValue], started_at: datetime
    ) -> IngestionRun:
        self._require_usable("start_run")
        validate_execution_id(execution_id)
        run = IngestionRun(
            execution_id=execution_id,
            scope=scope,
            started_at=started_at,
            status=RunStatus.RUNNING,
            finished_at=None,
        )
        self._journal.record("start_run", execution_id)
        stored = self._database.runs.get(execution_id)
        if stored is None:
            self._database.runs[execution_id] = run
            self._database.events[execution_id] = []
            return run
        if stored.started_at != run.started_at or not same_json(
            dict(stored.scope), dict(run.scope)
        ):
            raise PersistenceIntegrityError(
                f"start_run: run {execution_id} already exists with another "
                "scope or start time"
            )
        return stored

    def finish_run(
        self, *, execution_id: str, status: RunStatus, finished_at: datetime
    ) -> IngestionRun:
        self._require_usable("finish_run")
        validate_execution_id(execution_id)
        if not isinstance(status, RunStatus) or status is RunStatus.RUNNING:
            raise ValueError("a status that finishes a run must be SUCCEEDED or FAILED")
        if finished_at.utcoffset() is None:
            raise ValueError("finished_at must be a datetime with a UTC offset")
        self._journal.record("finish_run", execution_id, status.value)
        stored = self._database.runs.get(execution_id)
        if stored is None:
            raise PersistenceNotFoundError(f"finish_run: no run {execution_id}")
        if stored.status is not RunStatus.RUNNING:
            if stored.status is status and stored.finished_at == finished_at:
                return stored
            raise PersistenceIntegrityError(
                f"finish_run: run {execution_id} is already finished with "
                "another status or finish time"
            )
        finished = IngestionRun(
            execution_id=execution_id,
            scope=stored.scope,
            started_at=stored.started_at,
            status=status,
            finished_at=finished_at,
        )
        self._database.runs[execution_id] = finished
        return finished

    def read_run(self, execution_id: str) -> IngestionRun:
        self._require_usable("read_run")
        validate_execution_id(execution_id)
        stored = self._database.runs.get(execution_id)
        if stored is None:
            raise PersistenceNotFoundError(f"read_run: no run {execution_id}")
        return stored

    def list_runs(self, status: RunStatus) -> tuple[IngestionRun, ...]:
        self._require_usable("list_runs")
        if not isinstance(status, RunStatus):
            raise ValueError(  # noqa: TRY004 (ValueError is the pinned error)
                "status must be a RunStatus"
            )
        return tuple(
            sorted(
                (run for run in self._database.runs.values() if run.status is status),
                key=lambda run: (run.started_at, run.execution_id),
            )
        )

    def try_acquire_ingest_exclusion(self) -> bool:
        self._require_usable("try_acquire_ingest_exclusion")
        holder = self._database.exclusion_holder
        if holder is self:
            return True
        if holder is None:
            self._database.exclusion_holder = self
            self._journal.record("exclusion", detail="taken")
            return True
        self._journal.record("exclusion", detail="refused")
        return False

    # --- Observations ---

    def record_observation(self, observation: Observation) -> Observation:
        self._require_usable("record_observation")
        if not isinstance(observation, Observation):
            raise ValueError(  # noqa: TRY004 (ValueError is the pinned error)
                "observation must be an Observation"
            )
        identity = f"{observation.execution_id}/{observation.sequence}"
        self._journal.record(
            "record_observation", observation.execution_id, str(observation.sequence)
        )
        if observation.execution_id not in self._database.runs:
            raise PersistenceIntegrityError(
                f"record_observation {identity}: the database refused the data"
            )
        known_size = self._database.evidence.get(observation.content_hash)
        if known_size is not None and known_size != observation.size:
            raise PersistenceIntegrityError(
                f"record_observation {identity}: content is already stored with "
                "another size"
            )
        key = (observation.execution_id, observation.sequence)
        stored = self._database.observations.get(key)
        if stored is not None:
            if stored != observation:
                raise PersistenceIntegrityError(
                    f"record_observation: observation {identity} already exists "
                    "with different data"
                )
            return stored
        self._database.evidence.setdefault(observation.content_hash, observation.size)
        self._database.observations[key] = observation
        return observation

    def read_observation(self, execution_id: str, sequence: int) -> Observation:
        self._require_usable("read_observation")
        validate_execution_id(execution_id)
        stored = self._database.observations.get((execution_id, sequence))
        if stored is None:
            raise PersistenceNotFoundError(
                f"read_observation: no observation {execution_id}/{sequence}"
            )
        return stored

    def list_observations(self, execution_id: str) -> tuple[Observation, ...]:
        self._require_usable("list_observations")
        validate_execution_id(execution_id)
        if execution_id not in self._database.runs:
            raise PersistenceNotFoundError(
                f"list_observations: no run {execution_id} was started"
            )
        return tuple(
            observation
            for (stored_id, _), observation in sorted(
                self._database.observations.items(), key=lambda item: item[0][1]
            )
            if stored_id == execution_id
        )

    # --- Audit events ---

    def append_audit_event(
        self,
        *,
        execution_id: str,
        occurred_at: datetime,
        event_type: str,
        detail: Mapping[str, JsonValue],
    ) -> AuditEvent:
        self._require_usable("append_audit_event")
        validate_execution_id(execution_id)
        event = AuditEvent(
            event_id=self._database.next_event_id,
            execution_id=execution_id,
            occurred_at=occurred_at,
            event_type=event_type,
            detail=detail,
        )
        self._journal.record("append", execution_id, event_type)
        if execution_id not in self._database.runs:
            raise PersistenceIntegrityError(
                f"append_audit_event: the database refused the data for {execution_id}"
            )
        self._database.next_event_id += 1
        self._database.events[execution_id].append(event)
        return event

    def list_audit_events(self, execution_id: str) -> tuple[AuditEvent, ...]:
        self._require_usable("list_audit_events")
        validate_execution_id(execution_id)
        if execution_id not in self._database.runs:
            raise PersistenceNotFoundError(
                f"list_audit_events: no run {execution_id} was started"
            )
        return tuple(self._database.events[execution_id])

    def close(self) -> None:
        self._closed = True
        self._release()


# --- Fault injection for the repository -------------------------------------


@dataclass
class Fault:
    """A fault of one repository operation.

    The fault fires on the `nth` call of `operation` whose `detail` matches
    (`detail` is the event type of `append_audit_event`, the status value of
    `finish_run`, the sequence of `record_observation`, `None` for any). With
    `when="after"` the call is delegated first, so it commits, and then the
    error is raised (commit-then-raise); with `when="before"` nothing is
    delegated. A `PersistenceConnectionError` also ends the connection, as the
    real adapter does. `hook` runs just before the error is raised.
    """

    operation: str
    when: Literal["before", "after"] = "after"
    nth: int = 1
    detail: str | None = None
    error: Callable[[], BaseException] = lambda: PersistenceConnectionError(
        "synthetic: the database connection was lost"
    )
    hook: Callable[[], None] | None = None
    matched: int = 0
    fired: bool = False


@dataclass(frozen=True)
class Attempt:
    """One call a repository received, delegated or not."""

    open_index: int
    operation: str
    detail: str
    args: tuple[object, ...]


class FaultKit:
    """Builders of the faults the seams table names."""

    @staticmethod
    def lost_after_commit(
        operation: str,
        *,
        detail: str | None = None,
        nth: int = 1,
        hook: Callable[[], None] | None = None,
    ) -> Fault:
        return Fault(operation, "after", nth, detail, hook=hook)

    @staticmethod
    def lost_before_commit(
        operation: str,
        *,
        detail: str | None = None,
        nth: int = 1,
        hook: Callable[[], None] | None = None,
    ) -> Fault:
        return Fault(operation, "before", nth, detail, hook=hook)

    @staticmethod
    def refuses(
        operation: str,
        error: Callable[[], PersistenceError],
        *,
        detail: str | None = None,
        nth: int = 1,
    ) -> Fault:
        return Fault(operation, "before", nth, detail, error=error)

    @staticmethod
    def interrupts(
        operation: str,
        *,
        detail: str | None = None,
        nth: int = 1,
        when: Literal["before", "after"] = "before",
    ) -> Fault:
        return Fault(operation, when, nth, detail, error=lambda: KeyboardInterrupt())


class FlakyRepository:
    """Wraps an `InMemoryIngestionRepository` and applies its faults.

    It records every call it receives in `log` (shared by all repositories of one
    opener) so a test can compare the values of a call and of its repeat.
    """

    def __init__(
        self,
        inner: InMemoryIngestionRepository,
        *,
        open_index: int,
        faults: Sequence[Fault],
        log: list[Attempt],
    ) -> None:
        self.inner = inner
        self._open_index = open_index
        self._faults = list(faults)
        self._log = log

    def _call[T](
        self,
        operation: str,
        detail: str,
        args: tuple[object, ...],
        call: Callable[[], T],
    ) -> T:
        self._log.append(Attempt(self._open_index, operation, detail, args))
        for fault in self._faults:
            if fault.fired or fault.operation != operation:
                continue
            if fault.detail is not None and fault.detail != detail:
                continue
            fault.matched += 1
            if fault.matched != fault.nth:
                continue
            fault.fired = True
            if fault.when == "after":
                call()
            self._raise(fault)
        return call()

    def _raise(self, fault: Fault) -> NoReturn:
        error = fault.error()
        if isinstance(error, PersistenceConnectionError):
            self.inner.lose_connection()
        if fault.hook is not None:
            fault.hook()
        raise error

    def start_run(
        self, *, execution_id: str, scope: Mapping[str, JsonValue], started_at: datetime
    ) -> IngestionRun:
        return self._call(
            "start_run",
            "",
            (execution_id, dict(scope), started_at),
            lambda: self.inner.start_run(
                execution_id=execution_id, scope=scope, started_at=started_at
            ),
        )

    def finish_run(
        self, *, execution_id: str, status: RunStatus, finished_at: datetime
    ) -> IngestionRun:
        return self._call(
            "finish_run",
            status.value,
            (execution_id, status, finished_at),
            lambda: self.inner.finish_run(
                execution_id=execution_id, status=status, finished_at=finished_at
            ),
        )

    def read_run(self, execution_id: str) -> IngestionRun:
        return self._call(
            "read_run",
            "",
            (execution_id,),
            lambda: self.inner.read_run(execution_id),
        )

    def list_runs(self, status: RunStatus) -> tuple[IngestionRun, ...]:
        return self._call(
            "list_runs", str(status), (status,), lambda: self.inner.list_runs(status)
        )

    def try_acquire_ingest_exclusion(self) -> bool:
        return self._call(
            "try_acquire_ingest_exclusion",
            "",
            (),
            lambda: self.inner.try_acquire_ingest_exclusion(),
        )

    def record_observation(self, observation: Observation) -> Observation:
        return self._call(
            "record_observation",
            str(observation.sequence),
            (observation,),
            lambda: self.inner.record_observation(observation),
        )

    def read_observation(self, execution_id: str, sequence: int) -> Observation:
        return self._call(
            "read_observation",
            str(sequence),
            (execution_id, sequence),
            lambda: self.inner.read_observation(execution_id, sequence),
        )

    def list_observations(self, execution_id: str) -> tuple[Observation, ...]:
        return self._call(
            "list_observations",
            "",
            (execution_id,),
            lambda: self.inner.list_observations(execution_id),
        )

    def append_audit_event(
        self,
        *,
        execution_id: str,
        occurred_at: datetime,
        event_type: str,
        detail: Mapping[str, JsonValue],
    ) -> AuditEvent:
        return self._call(
            "append_audit_event",
            event_type,
            (execution_id, occurred_at, event_type, dict(detail)),
            lambda: self.inner.append_audit_event(
                execution_id=execution_id,
                occurred_at=occurred_at,
                event_type=event_type,
                detail=detail,
            ),
        )

    def list_audit_events(self, execution_id: str) -> tuple[AuditEvent, ...]:
        return self._call(
            "list_audit_events",
            "",
            (execution_id,),
            lambda: self.inner.list_audit_events(execution_id),
        )

    def close(self) -> None:
        self.inner.close()


class RepositoryOpenerDouble:
    """The `RepositoryOpener` of the use case: counts opens and can fail one.

    Every repository it opens is a `FlakyRepository` over a new
    `InMemoryIngestionRepository` of the shared database, with the faults
    registered for that open number (the first open is number 1).
    """

    def __init__(self, database: InMemoryDatabase, journal: Journal) -> None:
        self._database = database
        self._journal = journal
        self.opens = 0
        self.fail_opens: set[int] = set()
        self.faults: dict[int, list[Fault]] = {}
        self.attempts: list[Attempt] = []
        self.repositories: list[FlakyRepository] = []

    def __call__(self) -> ClosableIngestionRepository:
        self.opens += 1
        if self.opens in self.fail_opens:
            raise PersistenceConnectionError(
                "synthetic: the database cannot be reached"
            )
        repository = FlakyRepository(
            InMemoryIngestionRepository(self._database, self._journal),
            open_index=self.opens,
            faults=self.faults.get(self.opens, []),
            log=self.attempts,
        )
        self.repositories.append(repository)
        return repository

    @property
    def all_closed(self) -> bool:
        return all(repository.inner.closed for repository in self.repositories)

    def attempts_of(self, operation: str, detail: str | None = None) -> list[Attempt]:
        return [
            attempt
            for attempt in self.attempts
            if attempt.operation == operation
            and (detail is None or attempt.detail == detail)
        ]


# --- The source, the clock, the ids and the reporter ------------------------

type Step = SearchPage | BaseException | Callable[[], SearchPage]


class FakeSource:
    """A `ProcurementSource` scripted per page.

    A page with no scripted step left answers with the default page (`pages` 9).
    A step is a `SearchPage`, an exception to raise (a `SourceError` with or
    without a response, `KeyboardInterrupt`, `MemoryError`, any other), or a
    callable that returns the page (and may do something first). `requests`
    counts the requests, in order.
    """

    def __init__(self, default: Callable[[int], SearchPage]) -> None:
        self._default = default
        self._scripts: dict[int, list[Step]] = {}
        self.calls: list[tuple[int, str, int]] = []
        self.record_fetches: list[str] = []
        self.closed = False

    def script(self, page: int, *steps: Step) -> None:
        self._scripts.setdefault(page, []).extend(steps)

    @property
    def requests(self) -> list[int]:
        return [page for _, _, page in self.calls]

    def requests_for(self, page: int) -> int:
        return self.requests.count(page)

    def search_page(self, *, year: int, buyer: str, page: int) -> SearchPage:
        self.calls.append((year, buyer, page))
        queue = self._scripts.get(page)
        if not queue:
            return self._default(page)
        step = queue.pop(0)
        if isinstance(step, BaseException):
            raise step
        if isinstance(step, SearchPage):
            return step
        return step()

    def fetch_record(self, ocid: str) -> RecordResponse:
        self.record_fetches.append(ocid)
        raise AssertionError("F4 does not fetch records")


class FixedClock:
    """A `Clock` that starts at a fixed instant and steps one second per call."""

    def __init__(
        self, start: datetime = CLOCK_START, step: timedelta = timedelta(seconds=1)
    ) -> None:
        self._start = start
        self._step = step
        self.issued: list[datetime] = []

    def now(self) -> datetime:
        value = self._start + self._step * len(self.issued)
        self.issued.append(value)
        return value


class ScriptedExecutionIds:
    """An `ExecutionIdSource` that returns a fixed list, or counts up."""

    def __init__(self, ids: Sequence[str] | None = None) -> None:
        self._ids = list(ids) if ids is not None else None
        self.drawn_at: list[datetime] = []
        self.drawn: list[str] = []

    def new_execution_id(self, started_at: datetime) -> str:
        self.drawn_at.append(started_at)
        if self._ids is None:
            new_id = f"ingest-20261017t150000z-{len(self.drawn) + 1:08x}"
        else:
            assert self._ids, "more ids were drawn than the test scripted"
            new_id = self._ids.pop(0)
        self.drawn.append(new_id)
        return new_id


class RecordingReporter:
    """An `IngestReporter` that keeps what it was told."""

    def __init__(self, journal: Journal) -> None:
        self._journal = journal
        self.started: list[str] = []
        self.messages: list[str] = []

    def run_started(self, execution_id: str) -> None:
        self.started.append(execution_id)
        self._journal.record("run_started", execution_id)

    def progress(self, message: str) -> None:
        self.messages.append(message)


# --- The simulated transport (cases that go through SercopSource) -----------


class BodyStream(httpx.SyncByteStream):
    """A response body yielded in chunks, optionally failing after the last one."""

    def __init__(self, chunks: Sequence[bytes], error: BaseException | None) -> None:
        self._chunks = tuple(chunks)
        self._error = error

    def __iter__(self) -> Iterator[bytes]:
        yield from self._chunks
        if self._error is not None:
            raise self._error


@dataclass(frozen=True)
class WireReply:
    """A scripted answer: a status and a body that may be cut off by an error."""

    status: int = 200
    body: bytes = b""
    cut_after: int | None = None

    def to_response(self) -> httpx.Response:
        if self.cut_after is None:
            chunks: tuple[bytes, ...] = (self.body,) if self.body else ()
            error: BaseException | None = None
        else:
            chunks = (self.body[: self.cut_after],)
            error = httpx.RemoteProtocolError("synthetic cut-off")
        return httpx.Response(
            self.status,
            headers=[(b"content-type", b"application/json")],
            stream=BodyStream(chunks, error),
        )


@dataclass(frozen=True)
class WireFailure:
    """A scripted failure raised by the transport before any status arrives."""

    build: Callable[[httpx.Request], BaseException]


class TransportScript:
    """The `MockTransport` handler: answers per page, counts requests per page.

    A page with no scripted answer left gets a valid `200` page body with
    `pages` 9.
    """

    def __init__(self) -> None:
        self._scripts: dict[int, list[WireReply | WireFailure]] = {}
        self.requests: list[int] = []

    def script(self, page: int, *outcomes: WireReply | WireFailure) -> None:
        self._scripts.setdefault(page, []).extend(outcomes)

    def requests_for(self, page: int) -> int:
        return self.requests.count(page)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        self.requests.append(page)
        queue = self._scripts.get(page)
        if not queue:
            return WireReply(body=page_body(page)).to_response()
        outcome = queue.pop(0)
        if isinstance(outcome, WireFailure):
            raise outcome.build(request)
        return outcome.to_response()


# --- Seeding the doubles ----------------------------------------------------


class Seeder:
    """Writes runs, observations and events straight into the doubles.

    It uses its own repository (no journal), so what it writes is not part of
    what a test asserts about a call of `run_ingest`. Times are fixed and earlier
    than the `FixedClock` of the call.
    """

    def __init__(
        self, database: InMemoryDatabase, store: InMemoryRawEvidenceStore
    ) -> None:
        self._repository = InMemoryIngestionRepository(database)
        self._store = store
        self._runs = 0
        self._started: dict[str, datetime] = {}
        self._events: dict[str, int] = {}

    def run(
        self,
        execution_id: str,
        *,
        scope: IngestScope | Mapping[str, JsonValue],
        status: RunStatus = RunStatus.FAILED,
    ) -> IngestionRun:
        """Start a run (and finish it, unless `status` is `RUNNING`)."""
        started_at = SEED_START + timedelta(minutes=10 * self._runs)
        self._runs += 1
        self._started[execution_id] = started_at
        scope_json = scope.to_json() if isinstance(scope, IngestScope) else dict(scope)
        run = self._repository.start_run(
            execution_id=execution_id, scope=scope_json, started_at=started_at
        )
        if status is not RunStatus.RUNNING:
            run = self._repository.finish_run(
                execution_id=execution_id,
                status=status,
                finished_at=started_at + timedelta(minutes=5),
            )
        return run

    def _time(self, execution_id: str) -> datetime:
        self._events[execution_id] = self._events.get(execution_id, 0) + 1
        return self._started.get(execution_id, SEED_START) + timedelta(
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
        """The `run-started` event, with raw values so a test can break them."""
        self.event(
            execution_id, "run-started", {"resumes": resumes, "first_page": first_page}
        )

    def page(
        self,
        execution_id: str,
        page: int,
        sequence: int,
        *,
        status: int = 200,
        body: bytes | None = None,
        local: bool = True,
        postgres: bool = True,
        event: bool = True,
        event_hash: str | None = None,
    ) -> Observation:
        """A response for `page` in the chosen stores, and its `page-completed`."""
        content = body if body is not None else page_body(page)
        observation = Observation(
            execution_id=execution_id,
            sequence=sequence,
            method="GET",
            url=page_url(page),
            status=status,
            headers=JSON_HEADERS,
            captured_at=self._time(execution_id),
            content_hash=ContentHash.of(content),
            size=len(content),
        )
        if local:
            self._store.put(observation, content)
        if postgres:
            self._repository.record_observation(observation)
        if event:
            self.event(
                execution_id,
                "page-completed",
                {
                    "page": page,
                    "sequence": sequence,
                    "content_hash": event_hash or observation.content_hash.hexdigest,
                },
            )
        return observation

    def completed(
        self, execution_id: str, *pages: int, first_sequence: int = 1
    ) -> None:
        """`page-completed` for each page, with the sequences in order."""
        for offset, page in enumerate(pages):
            self.page(execution_id, page, first_sequence + offset)

    def failed_page(
        self, execution_id: str, page: int, sequence: int, *, status: int = 429
    ) -> None:
        """A response that failed (kept in both stores) and its `page-failed`."""
        self.page(
            execution_id,
            page,
            sequence,
            status=status,
            body=b"<html>synthetic</html>",
            event=False,
        )
        self.event(
            execution_id,
            "page-failed",
            {
                "page": page,
                "sequence": sequence,
                "failure": "status",
                "status": status,
            },
        )

    def last_page(self, execution_id: str, page: JsonValue, pages: JsonValue) -> None:
        self.event(execution_id, "last-page-reached", {"page": page, "pages": pages})


# --- The lab ----------------------------------------------------------------


class Lab:
    """Everything one test needs: the doubles, wired to each other.

    The ports are `store`, `source`, `opener`, `clock`, `execution_ids` and
    `reporter`; `database` is the state behind the repositories.
    """

    A: ClassVar[str] = "ingest-20261016t100000z-aaaaaaaa"
    B: ClassVar[str] = "ingest-20261016t100000z-bbbbbbbb"
    C: ClassVar[str] = "ingest-20261016t100000z-cccccccc"
    D: ClassVar[str] = "ingest-20261016t100000z-dddddddd"
    # A well-formed ingest id that names no run and no observation.
    ABSENT: ClassVar[str] = "ingest-20261014t150000z-ffffffff"

    def __init__(self) -> None:
        self.journal = Journal()
        self.database = InMemoryDatabase()
        self.store = InMemoryRawEvidenceStore(self.journal)
        self.clock = FixedClock()
        self.execution_ids = ScriptedExecutionIds()
        self.reporter = RecordingReporter(self.journal)
        self.source = FakeSource(lambda page: self.ok(page)())
        self.opener = RepositoryOpenerDouble(self.database, self.journal)
        self.faults = FaultKit()
        self.seed = Seeder(self.database, self.store)
        self._sources: list[SercopSource] = []

    # --- Scope and pages ---

    def scope(self, first_page: int = 1, last_page: int = 2) -> IngestScope:
        return IngestScope(
            base_url=BASE_URL,
            buyer=BUYER,
            year=YEAR,
            first_page=first_page,
            last_page=last_page,
        )

    def body(
        self,
        page: int,
        *,
        pages: int = 9,
        total: int | None = None,
        variant: str = "",
    ) -> bytes:
        return page_body(page, pages=pages, total=total, variant=variant)

    def ok(
        self,
        page: int,
        *,
        pages: int = 9,
        total: int | None = None,
        variant: str = "",
    ) -> Callable[[], SearchPage]:
        """A step: a complete `200` page, captured when the request is made."""

        def build() -> SearchPage:
            body = page_body(page, pages=pages, total=total, variant=variant)
            decoded = json.loads(body)
            return SearchPage(
                response=raw_response(page, body=body, captured_at=self.clock.now()),
                total=decoded["total"],
                page=page,
                pages=pages,
                record_count=len(decoded["data"]),
            )

        return build

    def status_failure(
        self, page: int, status: int, body: bytes = b""
    ) -> SourceStatusError:
        response = raw_response(
            page, status=status, body=body, captured_at=self.clock.now()
        )
        return SourceStatusError("synthetic status failure", response=response)

    def incomplete_failure(self, page: int, body: bytes) -> IncompleteResponseError:
        response = raw_response(page, body=body, captured_at=self.clock.now())
        return IncompleteResponseError(
            "synthetic incomplete response", response=response
        )

    def cutoff_failure(self, page: int, body: bytes) -> SourceTransportError:
        response = raw_response(page, body=body, captured_at=self.clock.now())
        return SourceTransportError("synthetic cut-off", response=response)

    def failure_without_response(self) -> SourceTransportError:
        return SourceTransportError("synthetic connect failure")

    # --- Reading the doubles ---

    def events(self, execution_id: str) -> list[AuditEvent]:
        return list(self.database.events.get(execution_id, []))

    def event_types(self, execution_id: str) -> list[str]:
        return [event.event_type for event in self.events(execution_id)]

    def details(self, execution_id: str, event_type: str) -> list[dict[str, JsonValue]]:
        return [
            dict(event.detail)
            for event in self.events(execution_id)
            if event.event_type == event_type
        ]

    def sequences(self, execution_id: str) -> tuple[int, ...]:
        """The sequences of the PostgreSQL observations of a run."""
        return tuple(
            sorted(
                sequence
                for stored_id, sequence in self.database.observations
                if stored_id == execution_id
            )
        )

    def local_sequences(self, execution_id: str) -> tuple[int, ...]:
        return self.store.list_observation_sequences(execution_id)

    def snapshot(self) -> LabState:
        return LabState(
            runs={
                execution_id: self.database.run_state(execution_id)
                for execution_id in self.database.runs
            },
            evidence=frozenset(self.database.evidence),
            objects=frozenset(self.store.objects),
            local_observations=frozenset(self.store.observations),
        )

    def new_run_ids(self, before: LabState) -> list[str]:
        return [
            execution_id
            for execution_id in self.database.runs
            if execution_id not in before.runs
        ]

    # --- The simulated source through SercopSource ---

    def sercop(self, script: TransportScript) -> SercopSource:
        """A real `SercopSource` over `script`, paced by nothing, on this clock."""
        source = SercopSource(
            base_url=BASE_URL,
            transport=httpx.MockTransport(script),
            now=self.clock.now,
            sleep=lambda seconds: None,
            min_interval=0,
            cooldown=0,
        )
        self._sources.append(source)
        return source

    def transport(self) -> TransportScript:
        return TransportScript()

    def reply(
        self, *, status: int = 200, body: bytes = b"", cut_after: int | None = None
    ) -> WireReply:
        """A scripted answer; `cut_after` ends the body with a protocol error."""
        return WireReply(status=status, body=body, cut_after=cut_after)

    def connect_error(self) -> WireFailure:
        """A connect error that arrives before any status."""
        return WireFailure(
            lambda request: httpx.ConnectError(
                "synthetic connect failure", request=request
            )
        )

    def script_ids(self, *ids: str) -> None:
        """The ids the use case will draw, in order."""
        self.execution_ids = ScriptedExecutionIds(ids)

    def publishes_then_fails(
        self,
        *,
        on_call: int,
        error: Callable[[], BaseException] | None = None,
    ) -> PublishThenFailStore:
        """The store of this lab, failing after the n-th publication (N2)."""
        if error is None:
            return PublishThenFailStore(self.store, on_call=on_call)
        return PublishThenFailStore(self.store, on_call=on_call, error=error)

    def refuses_to_store(
        self,
        *,
        on_call: int,
        error: Callable[[], BaseException] | None = None,
    ) -> RefusingStore:
        """The store of this lab, refusing the n-th write before publishing."""
        if error is None:
            return RefusingStore(self.store, on_call=on_call)
        return RefusingStore(self.store, on_call=on_call, error=error)

    def other_session_finishes(
        self, execution_id: str, status: RunStatus, finished_at: datetime
    ) -> None:
        """Another connection closes the run (a hand-made conflict)."""
        InMemoryIngestionRepository(self.database).finish_run(
            execution_id=execution_id, status=status, finished_at=finished_at
        )

    def close(self) -> None:
        for source in self._sources:
            source.close()


@pytest.fixture
def lab() -> Iterator[Lab]:
    laboratory = Lab()
    yield laboratory
    laboratory.close()


# The doubles are the extended ports: `mypy` checks these assignments.


def _the_doubles_implement_the_ports(lab: Lab) -> None:
    store: RawEvidenceStore = lab.store
    wrapped: RawEvidenceStore = PublishThenFailStore(store, on_call=1)
    refusing: RawEvidenceStore = RefusingStore(store, on_call=1)
    repository: IngestionRepository = InMemoryIngestionRepository(lab.database)
    closable: ClosableIngestionRepository = InMemoryIngestionRepository(lab.database)
    flaky: ClosableIngestionRepository = FlakyRepository(
        InMemoryIngestionRepository(lab.database), open_index=1, faults=[], log=[]
    )
    opener: RepositoryOpener = lab.opener
    source: ProcurementSource = lab.source
    clock: Clock = lab.clock
    ids: ExecutionIdSource = lab.execution_ids
    reporter: IngestReporter = lab.reporter
    del wrapped, refusing, repository, closable, flaky, opener, source, clock, ids
    del reporter
