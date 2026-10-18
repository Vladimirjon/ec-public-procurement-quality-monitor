"""Application use case: ingest the search pages of one buyer and year.

`run_ingest` opens its own repository, requests the pages of a scope one by one,
keeps every response in the raw evidence store and in PostgreSQL, and records
the run and its audit events. It reaches the source, the stores and the clock
only through ports.
"""

import enum
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from typing import TypeGuard, TypeVar

from ec_procurement_quality.application.ingest_ports import (
    Clock,
    ClosableIngestionRepository,
    ExecutionIdSource,
    IngestReporter,
    RepositoryOpener,
)
from ec_procurement_quality.application.procurement_source import ProcurementSource
from ec_procurement_quality.application.raw_evidence_store import RawEvidenceStore
from ec_procurement_quality.domain.content_hash import ContentHash
from ec_procurement_quality.domain.ingestion_audit import (
    AuditEvent,
    IngestionRun,
    JsonValue,
    RunStatus,
    same_json,
)
from ec_procurement_quality.domain.ingestion_catalogue import (
    AuditEventType,
    EvidenceStoreName,
    IngestScope,
    PageFailure,
    ReconciliationProblem,
    pages_left_to_request,
    validate_ingest_execution_id,
)
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
)
from ec_procurement_quality.domain.source_response import (
    IncompleteResponseError,
    RawResponse,
    SourceError,
    SourceStatusError,
)


@dataclass(frozen=True, kw_only=True)
class IngestRequest:
    """A request for a new run over `scope`."""

    scope: IngestScope


@dataclass(frozen=True, kw_only=True)
class ResumeRequest:
    """A request for a new run that resumes the run `execution_id`."""

    execution_id: str


class IngestEnd(enum.Enum):
    """How a call of `run_ingest` ended."""

    SUCCEEDED = enum.auto()
    RUN_FAILED = enum.auto()
    NOT_STARTED = enum.auto()
    INVALID_TARGET = enum.auto()
    INTERRUPTED = enum.auto()


@dataclass(frozen=True, kw_only=True)
class IngestOutcome:
    """The result of a call of `run_ingest`.

    `execution_id` and `run_status` describe the run the call created, and are
    `None` when it created none.
    """

    end: IngestEnd
    execution_id: str | None
    run_status: RunStatus | None
    message: str


_T = TypeVar("_T")


class _ConnectionUnconfirmed(Exception):
    """The one allowed recovery could not confirm the pending operation."""


class _PersistenceSession:
    def __init__(
        self,
        repository: ClosableIngestionRepository,
        open_repository: RepositoryOpener,
    ) -> None:
        self.repository = repository
        self._open_repository = open_repository
        self._reconnected = False

    def _reconnect(self) -> ClosableIngestionRepository:
        with suppress(Exception):
            self.repository.close()
        if self._reconnected:
            raise _ConnectionUnconfirmed
        self._reconnected = True
        try:
            repository = self._open_repository()
        except PersistenceError as error:
            raise _ConnectionUnconfirmed from error
        self.repository = repository
        try:
            acquired = repository.try_acquire_ingest_exclusion()
        except PersistenceError as error:
            repository.close()
            raise _ConnectionUnconfirmed from error
        if not acquired:
            repository.close()
            raise _ConnectionUnconfirmed
        return repository

    def safe_repeat(
        self, operation: Callable[[ClosableIngestionRepository], _T]
    ) -> tuple[_T, bool]:
        try:
            return operation(self.repository), False
        except PersistenceConnectionError:
            repository = self._reconnect()
            try:
                return operation(repository), True
            except PersistenceConnectionError as error:
                raise _ConnectionUnconfirmed from error

    def append_event(
        self,
        *,
        execution_id: str,
        occurred_at: datetime,
        event_type: AuditEventType,
        detail: dict[str, JsonValue],
    ) -> bool:
        def append(repository: ClosableIngestionRepository) -> None:
            repository.append_audit_event(
                execution_id=execution_id,
                occurred_at=occurred_at,
                event_type=event_type.value,
                detail=detail,
            )

        try:
            append(self.repository)
            return False
        except PersistenceConnectionError:
            repository = self._reconnect()
            try:
                already_stored = any(
                    event.event_type == event_type.value
                    and event.occurred_at == occurred_at
                    and same_json(dict(event.detail), detail)
                    for event in repository.list_audit_events(execution_id)
                )
                if not already_stored:
                    append(repository)
            except PersistenceConnectionError as error:
                raise _ConnectionUnconfirmed from error
            return True

    def close(self) -> None:
        self.repository.close()


def _outcome(
    end: IngestEnd,
    message: str,
    *,
    execution_id: str | None = None,
    run_status: RunStatus | None = None,
) -> IngestOutcome:
    return IngestOutcome(
        end=end,
        execution_id=execution_id,
        run_status=run_status,
        message=message,
    )


def _append_event(
    repository: ClosableIngestionRepository,
    clock: Clock,
    execution_id: str,
    event_type: AuditEventType,
    detail: dict[str, JsonValue],
) -> None:
    repository.append_audit_event(
        execution_id=execution_id,
        occurred_at=clock.now(),
        event_type=event_type.value,
        detail=detail,
    )


def _finish(
    repository: ClosableIngestionRepository,
    clock: Clock,
    execution_id: str,
    status: RunStatus,
) -> IngestOutcome:
    run = repository.finish_run(
        execution_id=execution_id,
        status=status,
        finished_at=clock.now(),
    )
    end = IngestEnd.SUCCEEDED if status is RunStatus.SUCCEEDED else IngestEnd.RUN_FAILED
    return _outcome(
        end,
        status.value,
        execution_id=execution_id,
        run_status=run.status,
    )


def _append_session_event(
    session: _PersistenceSession,
    clock: Clock,
    execution_id: str,
    event_type: AuditEventType,
    detail: dict[str, JsonValue],
) -> bool:
    return session.append_event(
        execution_id=execution_id,
        occurred_at=clock.now(),
        event_type=event_type,
        detail=detail,
    )


def _finish_session(
    session: _PersistenceSession,
    clock: Clock,
    execution_id: str,
    status: RunStatus,
) -> tuple[IngestOutcome, bool]:
    finished_at = clock.now()
    run, recovered = session.safe_repeat(
        lambda repository: repository.finish_run(
            execution_id=execution_id,
            status=status,
            finished_at=finished_at,
        )
    )
    end = IngestEnd.SUCCEEDED if status is RunStatus.SUCCEEDED else IngestEnd.RUN_FAILED
    return (
        _outcome(
            end,
            status.value,
            execution_id=execution_id,
            run_status=run.status,
        ),
        recovered,
    )


def _unconfirmed(execution_id: str) -> IngestOutcome:
    return _outcome(
        IngestEnd.RUN_FAILED,
        "the database write could not be confirmed",
        execution_id=execution_id,
        run_status=RunStatus.RUNNING,
    )


def _fail_after_connection_loss(
    session: _PersistenceSession,
    clock: Clock,
    execution_id: str,
    *,
    page: int,
    sequence: int | None,
) -> IngestOutcome:
    try:
        _append_session_event(
            session,
            clock,
            execution_id,
            AuditEventType.STORAGE_FAILED,
            {
                "page": page,
                "sequence": sequence,
                "store": EvidenceStoreName.POSTGRESQL.value,
            },
        )
        outcome, _ = _finish_session(session, clock, execution_id, RunStatus.FAILED)
    except _ConnectionUnconfirmed:
        return _unconfirmed(execution_id)
    return outcome


def _failure_kind(error: SourceError) -> PageFailure:
    if isinstance(error, SourceStatusError):
        return PageFailure.STATUS
    if isinstance(error, IncompleteResponseError):
        return PageFailure.INCOMPLETE
    return PageFailure.TRANSPORT


def _store_response(
    store: RawEvidenceStore,
    *,
    execution_id: str,
    sequence: int,
    response: RawResponse,
) -> Observation:
    return store.store(
        execution_id=execution_id,
        sequence=sequence,
        method=response.method,
        url=response.url,
        status=response.status,
        headers=response.headers,
        captured_at=response.captured_at,
        content=response.content,
    )


def _record_observation_operation(
    observation: Observation,
) -> Callable[[ClosableIngestionRepository], Observation]:
    def record(repository: ClosableIngestionRepository) -> Observation:
        return repository.record_observation(observation)

    return record


def _draw_execution_id(
    repository: ClosableIngestionRepository,
    store: RawEvidenceStore,
    execution_ids: ExecutionIdSource,
    started_at: datetime,
) -> str | None:
    for _ in range(3):
        execution_id = execution_ids.new_execution_id(started_at)
        try:
            validate_ingest_execution_id(execution_id)
        except ValueError:
            return None
        try:
            repository.read_run(execution_id)
        except PersistenceNotFoundError:
            pass
        else:
            continue
        if not store.list_observation_sequences(execution_id):
            return execution_id
    return None


def _cleanup_after_exception(
    *,
    repository: ClosableIngestionRepository,
    clock: Clock,
    store: RawEvidenceStore,
    execution_id: str,
    page: int,
    sequence: int | None,
    locally_stored: bool,
    event_type: AuditEventType,
    event_detail: dict[str, JsonValue],
    end: IngestEnd,
) -> IngestOutcome:
    try:
        if locally_stored and sequence is not None:
            observation = store.read_observation(execution_id, sequence)
            repository.record_observation(observation)
        _append_event(repository, clock, execution_id, event_type, event_detail)
        run = repository.finish_run(
            execution_id=execution_id,
            status=RunStatus.FAILED,
            finished_at=clock.now(),
        )
    except PersistenceError:
        return _outcome(
            end,
            event_type.value,
            execution_id=execution_id,
            run_status=RunStatus.RUNNING,
        )
    return _outcome(
        end,
        event_type.value,
        execution_id=execution_id,
        run_status=run.status,
    )


def _reconciliation_failed(
    repository: ClosableIngestionRepository,
    clock: Clock,
    run: IngestionRun,
    sequence: int | None,
    problem: ReconciliationProblem,
) -> bool:
    _append_event(
        repository,
        clock,
        run.execution_id,
        AuditEventType.RECONCILIATION_FAILED,
        {"sequence": sequence, "problem": problem.value},
    )
    repository.finish_run(
        execution_id=run.execution_id,
        status=RunStatus.FAILED,
        finished_at=clock.now(),
    )
    return False


def _reconcile_run(
    repository: ClosableIngestionRepository,
    store: RawEvidenceStore,
    clock: Clock,
    run: IngestionRun,
) -> bool:
    try:
        local_sequences = store.list_observation_sequences(run.execution_id)
    except (EvidenceIntegrityError, OSError):
        return _reconciliation_failed(
            repository,
            clock,
            run,
            None,
            ReconciliationProblem.LOCAL_LISTING_FAILED,
        )

    postgres = {
        observation.sequence: observation
        for observation in repository.list_observations(run.execution_id)
    }
    local: dict[int, Observation] = {}
    all_sequences = sorted(set(local_sequences) | set(postgres))
    for sequence in all_sequences:
        if sequence in postgres and sequence not in local_sequences:
            return _reconciliation_failed(
                repository,
                clock,
                run,
                sequence,
                ReconciliationProblem.LOCAL_OBSERVATION_MISSING,
            )
        try:
            observation = store.read_observation(run.execution_id, sequence)
        except EvidenceIntegrityError:
            return _reconciliation_failed(
                repository,
                clock,
                run,
                sequence,
                ReconciliationProblem.LOCAL_OBSERVATION_UNREADABLE,
            )
        local[sequence] = observation
        if sequence in postgres and postgres[sequence] != observation:
            return _reconciliation_failed(
                repository,
                clock,
                run,
                sequence,
                ReconciliationProblem.LOCAL_OBSERVATION_DIFFERENT,
            )
        try:
            store.read_content(observation.content_hash)
        except EvidenceNotFoundError:
            return _reconciliation_failed(
                repository,
                clock,
                run,
                sequence,
                ReconciliationProblem.OBJECT_MISSING,
            )
        except EvidenceIntegrityError:
            return _reconciliation_failed(
                repository,
                clock,
                run,
                sequence,
                ReconciliationProblem.OBJECT_INTEGRITY,
            )

    if all_sequences:
        expected = set(range(1, max(all_sequences) + 1))
        actual = set(all_sequences)
        if actual != expected:
            missing = min(expected - actual) if expected - actual else 0
            return _reconciliation_failed(
                repository,
                clock,
                run,
                missing,
                ReconciliationProblem.SEQUENCE_GAP,
            )

    local_only = sorted(set(local) - set(postgres))
    for sequence in local_only:
        try:
            repository.record_observation(local[sequence])
        except PersistenceIntegrityError:
            return _reconciliation_failed(
                repository,
                clock,
                run,
                sequence,
                ReconciliationProblem.POSTGRESQL_OBSERVATION_CONFLICT,
            )
        _append_event(
            repository,
            clock,
            run.execution_id,
            AuditEventType.OBSERVATION_RECONCILED,
            {"sequence": sequence},
        )

    _append_event(
        repository,
        clock,
        run.execution_id,
        AuditEventType.RUN_CLOSED_BY_RECONCILIATION,
        {"reconciled_observations": len(local_only)},
    )
    repository.finish_run(
        execution_id=run.execution_id,
        status=RunStatus.FAILED,
        finished_at=clock.now(),
    )
    return True


def _reconcile_running_runs(
    repository: ClosableIngestionRepository,
    store: RawEvidenceStore,
    clock: Clock,
) -> bool:
    for run in repository.list_runs(RunStatus.RUNNING):
        if not _reconcile_run(repository, store, clock, run):
            return False
    return True


@dataclass(frozen=True)
class _ChainEntry:
    run: IngestionRun
    events: tuple[AuditEvent, ...]
    resumes: str | None
    first_page: int


@dataclass(frozen=True)
class _ResumePlan:
    scope: IngestScope
    pages: tuple[int, ...]
    first_page: int


def _plain_int(value: object) -> TypeGuard[int]:
    return type(value) is int


def _run_started_values(events: tuple[AuditEvent, ...]) -> tuple[str | None, int]:
    started = [
        event
        for event in events
        if event.event_type == AuditEventType.RUN_STARTED.value
    ]
    if len(started) != 1:
        raise ValueError("the chain must have exactly one run-started event")
    detail = started[0].detail
    if set(detail) != {"resumes", "first_page"}:
        raise ValueError("run-started has another detail shape")
    resumes = detail["resumes"]
    first_page = detail["first_page"]
    if resumes is not None:
        if not isinstance(resumes, str):
            raise ValueError("resumes is not an execution id")
        validate_execution_id(resumes)
    if not _plain_int(first_page) or first_page < 1:
        raise ValueError("first_page is invalid")
    return resumes, first_page


def _validated_completed_page(
    repository: ClosableIngestionRepository,
    store: RawEvidenceStore,
    scope: IngestScope,
    run_id: str,
    event: AuditEvent,
) -> int:
    detail = event.detail
    if set(detail) != {"page", "sequence", "content_hash"}:
        raise ValueError("page-completed has another detail shape")
    page = detail["page"]
    sequence = detail["sequence"]
    content_hash_text = detail["content_hash"]
    if (
        not _plain_int(page)
        or not scope.first_page <= page <= scope.last_page
        or not _plain_int(sequence)
        or sequence < 0
        or not isinstance(content_hash_text, str)
    ):
        raise ValueError("page-completed has invalid values")
    content_hash = ContentHash(content_hash_text)
    postgres = repository.read_observation(run_id, sequence)
    local = store.read_observation(run_id, sequence)
    if (
        postgres != local
        or postgres.status != 200
        or postgres.content_hash != content_hash
    ):
        raise ValueError("page-completed contradicts its observation")
    return page


def _resume_plan(
    repository: ClosableIngestionRepository,
    store: RawEvidenceStore,
    target_id: str,
) -> _ResumePlan:
    target = repository.read_run(target_id)
    scope = IngestScope.from_json(target.scope)
    chain_from_target: list[_ChainEntry] = []
    visited: set[str] = set()
    current_id: str | None = target_id
    while current_id is not None:
        if current_id in visited:
            raise ValueError("the resumption chain is cyclic")
        visited.add(current_id)
        run = repository.read_run(current_id)
        events = repository.list_audit_events(current_id)
        resumes, first_page = _run_started_values(events)
        if not same_json(dict(run.scope), dict(target.scope)):
            raise ValueError("the resumption chain has another scope")
        if current_id != target_id and run.status in {
            RunStatus.SUCCEEDED,
            RunStatus.RUNNING,
        }:
            raise ValueError("the resumption chain has an invalid middle run")
        chain_from_target.append(
            _ChainEntry(
                run=run,
                events=events,
                resumes=resumes,
                first_page=first_page,
            )
        )
        current_id = resumes

    completed: set[int] = set()
    last_reached: int | None = None
    reached_count = 0
    for index, entry in enumerate(reversed(chain_from_target)):
        pages_before = pages_left_to_request(scope, frozenset(completed), last_reached)
        expected_first = (
            scope.first_page
            if index == 0
            else (pages_before[0] if pages_before else scope.last_page + 1)
        )
        if entry.first_page != expected_first:
            raise ValueError("a run has an unjustified first_page")
        page_events = {
            AuditEventType.PAGE_COMPLETED.value,
            AuditEventType.PAGE_FAILED.value,
        }
        if entry.first_page == scope.last_page + 1 and any(
            event.event_type in page_events for event in entry.events
        ):
            raise ValueError("a sentinel run has a page event")

        valid_completed_in_run: set[int] = set()
        for event_index, event in enumerate(entry.events):
            if event.event_type == AuditEventType.PAGE_COMPLETED.value:
                completed_page = _validated_completed_page(
                    repository, store, scope, entry.run.execution_id, event
                )
                valid_completed_in_run.add(completed_page)
                completed.add(completed_page)
            elif event.event_type == AuditEventType.LAST_PAGE_REACHED.value:
                reached_count += 1
                detail = event.detail
                if reached_count != 1 or set(detail) != {"page", "pages"}:
                    raise ValueError("last-page-reached is not unique or exact")
                reached_page = detail["page"]
                reported_pages = detail["pages"]
                if (
                    not _plain_int(reached_page)
                    or not _plain_int(reported_pages)
                    or not scope.first_page <= reached_page <= scope.last_page
                    or reported_pages < 0
                    or reached_page < reported_pages
                    or reached_page not in valid_completed_in_run
                ):
                    raise ValueError("last-page-reached has invalid values")
                if any(
                    later.event_type in page_events
                    for later in entry.events[event_index + 1 :]
                ):
                    raise ValueError("a page event follows last-page-reached")
                if not set(range(scope.first_page, reached_page + 1)).issubset(
                    completed
                ):
                    raise ValueError("last-page-reached has incomplete coverage")
                last_reached = reached_page

    pages_left = pages_left_to_request(scope, frozenset(completed), last_reached)
    first_page = pages_left[0] if pages_left else scope.last_page + 1
    return _ResumePlan(scope=scope, pages=pages_left, first_page=first_page)


def run_ingest(
    request: IngestRequest | ResumeRequest,
    *,
    source: ProcurementSource,
    store: RawEvidenceStore,
    open_repository: RepositoryOpener,
    clock: Clock,
    execution_ids: ExecutionIdSource,
    reporter: IngestReporter,
) -> IngestOutcome:
    """Run one ingest, or resume one, and return how it ended."""
    try:
        repository = open_repository()
    except PersistenceError:
        return _outcome(IngestEnd.NOT_STARTED, "the repository is unavailable")
    session = _PersistenceSession(repository, open_repository)

    execution_id: str | None = None
    run_created = False
    page = request.scope.first_page if isinstance(request, IngestRequest) else 1
    attempted_sequence: int | None = None
    store_was_called = False

    try:
        try:
            if not session.repository.try_acquire_ingest_exclusion():
                return _outcome(IngestEnd.NOT_STARTED, "another ingest is running")
        except PersistenceError:
            return _outcome(IngestEnd.NOT_STARTED, "the ingest exclusion failed")

        target_id: str | None = None
        if isinstance(request, ResumeRequest):
            target_id = request.execution_id
            try:
                target = session.repository.read_run(target_id)
            except PersistenceNotFoundError:
                return _outcome(
                    IngestEnd.INVALID_TARGET,
                    f"invalid resumption target {target_id}",
                )
            if target.status is RunStatus.SUCCEEDED:
                return _outcome(
                    IngestEnd.INVALID_TARGET,
                    f"invalid resumption target {target_id}",
                )

        if not _reconcile_running_runs(session.repository, store, clock):
            return _outcome(IngestEnd.NOT_STARTED, "reconciliation failed")

        if target_id is None:
            assert isinstance(request, IngestRequest)
            scope = request.scope
            pages_to_request = tuple(range(scope.first_page, scope.last_page + 1))
            first_page = scope.first_page
        else:
            try:
                resume_plan = _resume_plan(session.repository, store, target_id)
            except (ValueError, PersistenceNotFoundError, EvidenceNotFoundError):
                return _outcome(
                    IngestEnd.NOT_STARTED,
                    f"invalid resumption chain {target_id}",
                )
            scope = resume_plan.scope
            pages_to_request = resume_plan.pages
            first_page = resume_plan.first_page
            page = first_page

        started_at = clock.now()
        try:
            execution_id = _draw_execution_id(
                session.repository, store, execution_ids, started_at
            )
        except (PersistenceError, OSError, EvidenceIntegrityError):
            return _outcome(
                IngestEnd.NOT_STARTED, "an execution id could not be checked"
            )
        if execution_id is None:
            return _outcome(IngestEnd.NOT_STARTED, "no execution id is available")

        scope_json = scope.to_json()
        try:
            _, recovered = session.safe_repeat(
                lambda active: active.start_run(
                    execution_id=execution_id,
                    scope=scope_json,
                    started_at=started_at,
                )
            )
        except KeyboardInterrupt:
            return _outcome(IngestEnd.INTERRUPTED, "the ingest was interrupted")
        except _ConnectionUnconfirmed:
            return _unconfirmed(execution_id)
        run_created = True
        reporter.run_started(execution_id)
        if recovered:
            return _fail_after_connection_loss(
                session,
                clock,
                execution_id,
                page=first_page,
                sequence=None,
            )
        try:
            recovered = _append_session_event(
                session,
                clock,
                execution_id,
                AuditEventType.RUN_STARTED,
                {"resumes": target_id, "first_page": first_page},
            )
        except _ConnectionUnconfirmed:
            return _unconfirmed(execution_id)
        if recovered:
            return _fail_after_connection_loss(
                session,
                clock,
                execution_id,
                page=first_page,
                sequence=None,
            )

        next_sequence = 1
        for page in pages_to_request:
            result = None
            source_error: SourceError | None = None
            try:
                result = source.search_page(
                    year=scope.year,
                    buyer=scope.buyer,
                    page=page,
                )
            except SourceError as error:
                source_error = error

            response: RawResponse | None
            if result is not None:
                response = result.response
            else:
                assert source_error is not None
                response = source_error.response
            if response is None:
                try:
                    _append_session_event(
                        session,
                        clock,
                        execution_id,
                        AuditEventType.PAGE_FAILED,
                        {
                            "page": page,
                            "sequence": None,
                            "failure": PageFailure.TRANSPORT.value,
                            "status": None,
                        },
                    )
                    outcome, _ = _finish_session(
                        session, clock, execution_id, RunStatus.FAILED
                    )
                except _ConnectionUnconfirmed:
                    return _unconfirmed(execution_id)
                return outcome

            attempted_sequence = next_sequence
            store_was_called = True
            try:
                stored_observation = _store_response(
                    store,
                    execution_id=execution_id,
                    sequence=next_sequence,
                    response=response,
                )
            except (OSError, EvidenceIntegrityError):
                try:
                    published_observation = store.read_observation(
                        execution_id, next_sequence
                    )
                except (EvidenceNotFoundError, EvidenceIntegrityError, OSError):
                    published_observation = None
                if published_observation is not None:
                    try:
                        session.safe_repeat(
                            _record_observation_operation(published_observation)
                        )
                    except PersistenceError:
                        try:
                            _append_session_event(
                                session,
                                clock,
                                execution_id,
                                AuditEventType.STORAGE_FAILED,
                                {
                                    "page": page,
                                    "sequence": next_sequence,
                                    "store": EvidenceStoreName.POSTGRESQL.value,
                                },
                            )
                            outcome, _ = _finish_session(
                                session, clock, execution_id, RunStatus.FAILED
                            )
                        except _ConnectionUnconfirmed:
                            return _unconfirmed(execution_id)
                        return outcome
                    except _ConnectionUnconfirmed:
                        return _unconfirmed(execution_id)
                try:
                    _append_session_event(
                        session,
                        clock,
                        execution_id,
                        AuditEventType.STORAGE_FAILED,
                        {
                            "page": page,
                            "sequence": next_sequence,
                            "store": EvidenceStoreName.RAW_EVIDENCE.value,
                        },
                    )
                    outcome, _ = _finish_session(
                        session, clock, execution_id, RunStatus.FAILED
                    )
                except _ConnectionUnconfirmed:
                    return _unconfirmed(execution_id)
                return outcome
            observation = stored_observation
            next_sequence += 1
            store_was_called = False

            try:
                _, recovered = session.safe_repeat(
                    _record_observation_operation(observation)
                )
            except _ConnectionUnconfirmed:
                return _unconfirmed(execution_id)
            except PersistenceError:
                try:
                    _append_session_event(
                        session,
                        clock,
                        execution_id,
                        AuditEventType.STORAGE_FAILED,
                        {
                            "page": page,
                            "sequence": observation.sequence,
                            "store": EvidenceStoreName.POSTGRESQL.value,
                        },
                    )
                    outcome, _ = _finish_session(
                        session, clock, execution_id, RunStatus.FAILED
                    )
                except _ConnectionUnconfirmed:
                    return _unconfirmed(execution_id)
                return outcome
            if recovered:
                return _fail_after_connection_loss(
                    session,
                    clock,
                    execution_id,
                    page=page,
                    sequence=observation.sequence,
                )

            if source_error is not None:
                try:
                    _append_session_event(
                        session,
                        clock,
                        execution_id,
                        AuditEventType.PAGE_FAILED,
                        {
                            "page": page,
                            "sequence": observation.sequence,
                            "failure": _failure_kind(source_error).value,
                            "status": response.status,
                        },
                    )
                    outcome, _ = _finish_session(
                        session, clock, execution_id, RunStatus.FAILED
                    )
                except _ConnectionUnconfirmed:
                    return _unconfirmed(execution_id)
                return outcome

            assert result is not None
            try:
                recovered = _append_session_event(
                    session,
                    clock,
                    execution_id,
                    AuditEventType.PAGE_COMPLETED,
                    {
                        "page": page,
                        "sequence": observation.sequence,
                        "content_hash": observation.content_hash.hexdigest,
                    },
                )
            except _ConnectionUnconfirmed:
                return _unconfirmed(execution_id)
            if recovered:
                return _fail_after_connection_loss(
                    session,
                    clock,
                    execution_id,
                    page=page,
                    sequence=observation.sequence,
                )
            if page >= result.pages:
                try:
                    recovered = _append_session_event(
                        session,
                        clock,
                        execution_id,
                        AuditEventType.LAST_PAGE_REACHED,
                        {"page": page, "pages": result.pages},
                    )
                except _ConnectionUnconfirmed:
                    return _unconfirmed(execution_id)
                if recovered:
                    return _fail_after_connection_loss(
                        session,
                        clock,
                        execution_id,
                        page=page,
                        sequence=observation.sequence,
                    )
                try:
                    outcome, _ = _finish_session(
                        session, clock, execution_id, RunStatus.SUCCEEDED
                    )
                except _ConnectionUnconfirmed:
                    return _unconfirmed(execution_id)
                except PersistenceIntegrityError:
                    stored = session.repository.read_run(execution_id)
                    return _outcome(
                        IngestEnd.RUN_FAILED,
                        "the final status conflicts with stored state",
                        execution_id=execution_id,
                        run_status=stored.status,
                    )
                return outcome

        try:
            outcome, _ = _finish_session(
                session, clock, execution_id, RunStatus.SUCCEEDED
            )
        except _ConnectionUnconfirmed:
            return _unconfirmed(execution_id)
        except PersistenceIntegrityError:
            stored = session.repository.read_run(execution_id)
            return _outcome(
                IngestEnd.RUN_FAILED,
                "the final status conflicts with stored state",
                execution_id=execution_id,
                run_status=stored.status,
            )
        return outcome
    except KeyboardInterrupt:
        if not run_created or execution_id is None:
            return _outcome(IngestEnd.INTERRUPTED, "the ingest was interrupted")
        return _cleanup_after_exception(
            repository=session.repository,
            clock=clock,
            store=store,
            execution_id=execution_id,
            page=page,
            sequence=attempted_sequence,
            locally_stored=store_was_called,
            event_type=AuditEventType.RUN_INTERRUPTED,
            event_detail={"page": page},
            end=IngestEnd.INTERRUPTED,
        )
    except Exception as error:  # noqa: BLE001 -- State machine K audits defects.
        if not run_created or execution_id is None:
            return _outcome(IngestEnd.NOT_STARTED, type(error).__name__)
        return _cleanup_after_exception(
            repository=session.repository,
            clock=clock,
            store=store,
            execution_id=execution_id,
            page=page,
            sequence=attempted_sequence,
            locally_stored=store_was_called,
            event_type=AuditEventType.UNEXPECTED_ERROR,
            event_detail={"page": page, "error_type": type(error).__name__},
            end=IngestEnd.RUN_FAILED,
        )
    finally:
        session.close()
