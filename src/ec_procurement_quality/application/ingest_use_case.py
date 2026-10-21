"""Application use case: ingest the search pages of one buyer and year.

`run_ingest` opens its own repository, requests the pages of a scope one by one,
keeps every response in the raw evidence store and in PostgreSQL, and records
the run and its audit events. It reaches the source, the stores and the clock
only through ports.
"""

import enum
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
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


class _ReconciliationRefused(Exception):
    """The database refused or lost a read or a write of the reconciliation."""


class _Unreadable(Exception):
    """A database read failed before the run exists; its line was already written."""


class _IdUnchecked(Exception):
    """The drawn execution id could not be checked; it names the id."""

    def __init__(self, execution_id: str) -> None:
        super().__init__(execution_id)
        self.execution_id = execution_id


class _CleanupStopped(Exception):
    """A database operation of the interruption cleanup failed; it was reported."""


def _report_failure(
    reporter: IngestReporter,
    operation: str,
    execution_id: str | None,
    error: BaseException,
    *,
    detail: str | None = None,
    sequence: int | None = None,
) -> None:
    """Name the failed database operation and its identity; of the error, its class.

    A lost connection is worded as a loss and adds no class name.
    """
    text = operation if detail is None else f"{operation} {detail}"
    if isinstance(error, PersistenceConnectionError):
        line = f"connection lost during {text}"
        tail = ""
    else:
        verb = "refused" if isinstance(error, PersistenceError) else "failed"
        line = f"{text} {verb}"
        tail = f" ({type(error).__name__})"
    if execution_id is not None:
        line += f": run {execution_id}"
    if sequence is not None:
        line += f" sequence {sequence}"
    reporter.progress(line + tail)


@contextmanager
def _reporting_failure(
    reporter: IngestReporter,
    operation: str,
    execution_id: str | None,
    *,
    detail: str | None = None,
    sequence: int | None = None,
    on_loss: Callable[[], None] | None = None,
) -> Iterator[None]:
    """Write the one line of a database operation that raises, then let it pass.

    `on_loss` runs first when the connection was lost, before the line is written.
    """
    try:
        yield
    except PersistenceError as error:
        if on_loss is not None and isinstance(error, PersistenceConnectionError):
            on_loss()
        _report_failure(
            reporter, operation, execution_id, error, detail=detail, sequence=sequence
        )
        raise


def _prevailing(first: BaseException, second: BaseException) -> BaseException:
    """The exception that decides when two arrive in the window of State machine C.

    A `SystemExit` propagates, a `KeyboardInterrupt` comes next, and any other
    exception decides over `_ConnectionUnconfirmed`, which only says that the
    recovery was not confirmed (plan Revision 10, sweep finding N-3).
    """
    for kind in (SystemExit, KeyboardInterrupt):
        for error in (first, second):
            if isinstance(error, kind):
                return error
    return second if isinstance(first, _ConnectionUnconfirmed) else first


@contextmanager
def _recovery_step(reporter: IngestReporter, operation: str) -> Iterator[None]:
    """One database operation of State machine C steps 2 and 3, before any is current.

    Whatever it raises is reported once, under its own name, and ends the step:
    a `PersistenceError` as an unconfirmed recovery, anything else as itself.
    `SystemExit` passes without a line. When the line raises too, `_prevailing`
    decides.
    """
    try:
        yield
    except PersistenceError as error:
        _report_failure(reporter, operation, None, error)
        raise _ConnectionUnconfirmed from error
    except SystemExit:
        raise
    except BaseException as error:
        try:
            _report_failure(reporter, operation, None, error)
        except BaseException as line_error:  # noqa: BLE001 -- see `_prevailing`.
            raise _prevailing(error, line_error) from None
        raise


class _PersistenceSession:
    """The repositories of one call, and the record of which one is current.

    The current repository is the one that holds the ingest exclusion (State
    machine C, "The explicit record"): the first one until a connection is lost,
    none until the second one holds the exclusion, then the second one. A lost
    repository, and a second one that does not hold it, are kept only to be closed.
    """

    def __init__(
        self,
        repository: ClosableIngestionRepository,
        open_repository: RepositoryOpener,
        reporter: IngestReporter,
    ) -> None:
        self._current: ClosableIngestionRepository | None = repository
        self._dropped: ClosableIngestionRepository | None = None
        self._unclosed = [repository]
        self._open_repository = open_repository
        self._reporter = reporter
        self._reconnected = False

    @property
    def reconnected(self) -> bool:
        return self._reconnected

    @property
    def current(self) -> ClosableIngestionRepository | None:
        return self._current

    @property
    def repository(self) -> ClosableIngestionRepository:
        assert self._current is not None
        return self._current

    def drop_current(self) -> None:
        """No repository is current from here on.

        It is the first action of the handler of a lost connection, before its
        line is written, and also what a refused `finish_run(FAILED)` does: nothing
        more is written to the run.
        """
        if self._current is not None:
            self._dropped = self._current
            self._current = None

    def unclosed(self) -> tuple[ClosableIngestionRepository, ...]:
        return tuple(self._unclosed)

    def close(self, repository: ClosableIngestionRepository) -> None:
        """Close `repository`; an `Exception` other than `MemoryError` counts as closed.

        A `MemoryError`, a `KeyboardInterrupt` or a `SystemExit` propagates and
        leaves the repository to be attempted once more by the final close.
        """
        try:
            repository.close()
        except Exception as error:
            if isinstance(error, MemoryError):
                raise
        self._unclosed.remove(repository)

    def _report_loss(self, operation: str, execution_id: str) -> None:
        self._reporter.progress(
            f"connection lost during {operation}: run {execution_id}"
        )

    def _reconnect(self) -> ClosableIngestionRepository:
        dropped = self._dropped
        assert dropped is not None
        self.close(dropped)
        if self._reconnected:
            raise _ConnectionUnconfirmed
        self._reconnected = True
        # No repository is current until the second one holds the exclusion
        # (State machine C, "The current repository"): whatever ends the window
        # propagates after the second repository, if one was obtained, was closed.
        second: ClosableIngestionRepository | None = None
        failure: BaseException
        try:
            with _recovery_step(self._reporter, "open_repository"):
                second = self._open_repository()
                self._unclosed.append(second)
            assert second is not None
            with _recovery_step(self._reporter, "try_acquire_ingest_exclusion"):
                acquired = second.try_acquire_ingest_exclusion()
            if acquired:
                self._current = second
                return second
            failure = _ConnectionUnconfirmed()
        except BaseException as error:  # noqa: BLE001 -- see `_prevailing`.
            failure = error
        if second is not None:
            try:
                self.close(second)
            except BaseException as error:  # noqa: BLE001 -- see `_prevailing`.
                failure = _prevailing(failure, error)
        raise failure

    def safe_repeat(
        self,
        operation: Callable[[ClosableIngestionRepository], _T],
        *,
        name: str,
        execution_id: str,
    ) -> tuple[_T, bool]:
        try:
            return operation(self.repository), False
        except PersistenceConnectionError:
            self.drop_current()
            self._report_loss(name, execution_id)
            repository = self._reconnect()
            try:
                return operation(repository), True
            except PersistenceConnectionError as error:
                self.drop_current()
                self._report_loss(name, execution_id)
                raise _ConnectionUnconfirmed from error

    def append_event(
        self,
        *,
        execution_id: str,
        occurred_at: datetime,
        event_type: AuditEventType,
        detail: dict[str, JsonValue],
        sequence: int | None = None,
    ) -> bool:
        """Append once, re-checking after a lost connection.

        Every `PersistenceError` that leaves this method was already reported,
        under the name of the operation that failed.
        """

        def append(repository: ClosableIngestionRepository) -> None:
            with _reporting_failure(
                self._reporter,
                "append_audit_event",
                execution_id,
                detail=event_type.value,
                sequence=sequence,
                on_loss=self.drop_current,
            ):
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
                with _reporting_failure(
                    self._reporter,
                    "list_audit_events",
                    execution_id,
                    on_loss=self.drop_current,
                ):
                    events = repository.list_audit_events(execution_id)
                already_stored = any(
                    event.event_type == event_type.value
                    and event.occurred_at == occurred_at
                    and same_json(dict(event.detail), detail)
                    for event in events
                )
                if not already_stored:
                    append(repository)
            except PersistenceConnectionError as error:
                raise _ConnectionUnconfirmed from error
            return True


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


def _report_page(reporter: IngestReporter, page: int, observation: Observation) -> None:
    reporter.progress(
        f"page {page} sequence {observation.sequence} status {observation.status} "
        f"sha256 {observation.content_hash.hexdigest}"
    )


def _sequence_of(detail: dict[str, JsonValue]) -> int | None:
    sequence = detail.get("sequence")
    return sequence if isinstance(sequence, int) else None


def _append_session_event(
    session: _PersistenceSession,
    clock: Clock,
    execution_id: str,
    event_type: AuditEventType,
    detail: dict[str, JsonValue],
    *,
    sequence: int | None,
) -> bool:
    return session.append_event(
        execution_id=execution_id,
        occurred_at=clock.now(),
        event_type=event_type,
        detail=detail,
        sequence=sequence,
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
        ),
        name=f"finish_run {status.value}",
        execution_id=execution_id,
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


def _recovery_ended(error: BaseException, execution_id: str) -> IngestOutcome:
    """The outcome when an exception lands while no repository is current.

    State machine K is not entered: the run is left `running`, untouched.
    """
    if isinstance(error, KeyboardInterrupt):
        return _outcome(
            IngestEnd.INTERRUPTED,
            "the ingest was interrupted",
            execution_id=execution_id,
            run_status=RunStatus.RUNNING,
        )
    return _outcome(
        IngestEnd.RUN_FAILED,
        f"unexpected error: {type(error).__name__}",
        execution_id=execution_id,
        run_status=RunStatus.RUNNING,
    )


def _close_failed(
    session: _PersistenceSession,
    clock: Clock,
    reporter: IngestReporter,
    execution_id: str,
    event_type: AuditEventType,
    detail: dict[str, JsonValue],
) -> IngestOutcome:
    """The failure path: append `event_type`, then `finish_run(FAILED)`.

    A refused append adds no further event, and a refused `finish_run` leaves
    the run `running` for the next ingest to close.
    """
    try:
        # A refused append was reported by `append_event`; no further event follows.
        with suppress(PersistenceError):
            _append_session_event(
                session,
                clock,
                execution_id,
                event_type,
                detail,
                sequence=_sequence_of(detail),
            )
        outcome, _ = _finish_session(session, clock, execution_id, RunStatus.FAILED)
    except _ConnectionUnconfirmed:
        return _unconfirmed(execution_id)
    except PersistenceError as error:
        # A refusal is answered, never retried: nothing more is written to the run,
        # so an exception that lands in the line below does not enter State machine K.
        session.drop_current()
        _report_failure(
            reporter,
            "finish_run",
            execution_id,
            error,
            detail=RunStatus.FAILED.value,
        )
        return _outcome(
            IngestEnd.RUN_FAILED,
            "the database refused to close the run",
            execution_id=execution_id,
            run_status=RunStatus.RUNNING,
        )
    return outcome


def _fail_postgresql(
    session: _PersistenceSession,
    clock: Clock,
    reporter: IngestReporter,
    execution_id: str,
    *,
    page: int,
    sequence: int | None,
) -> IngestOutcome:
    """Answer a lost or refused PostgreSQL write with one `storage-failed`."""
    return _close_failed(
        session,
        clock,
        reporter,
        execution_id,
        AuditEventType.STORAGE_FAILED,
        {
            "page": page,
            "sequence": sequence,
            "store": EvidenceStoreName.POSTGRESQL.value,
        },
    )


def _append_on_normal_path(
    session: _PersistenceSession,
    clock: Clock,
    reporter: IngestReporter,
    execution_id: str,
    event_type: AuditEventType,
    detail: dict[str, JsonValue],
    *,
    page: int,
    sequence: int | None,
) -> IngestOutcome | None:
    """Append a normal-path event; return the outcome if the run ended instead."""
    try:
        recovered = _append_session_event(
            session, clock, execution_id, event_type, detail, sequence=sequence
        )
    except _ConnectionUnconfirmed:
        return _unconfirmed(execution_id)
    except PersistenceError:
        # Reported by `append_event`; the refusal is answered like a recovery.
        recovered = True
    if recovered:
        return _fail_postgresql(
            session, clock, reporter, execution_id, page=page, sequence=sequence
        )
    return None


def _finish_succeeded(
    session: _PersistenceSession,
    clock: Clock,
    reporter: IngestReporter,
    execution_id: str,
    *,
    page: int,
) -> IngestOutcome:
    try:
        outcome, _ = _finish_session(session, clock, execution_id, RunStatus.SUCCEEDED)
    except _ConnectionUnconfirmed:
        return _unconfirmed(execution_id)
    except PersistenceError as error:
        _report_failure(
            reporter,
            "finish_run",
            execution_id,
            error,
            detail=RunStatus.SUCCEEDED.value,
        )
        if not session.reconnected:
            return _fail_postgresql(
                session, clock, reporter, execution_id, page=page, sequence=None
            )
        # State machine C, P-2: the stored run decides what the refused repeat means.
        try:
            with _reporting_failure(
                reporter, "read_run", execution_id, on_loss=session.drop_current
            ):
                stored = session.repository.read_run(execution_id)
        except PersistenceError:
            return _unconfirmed(execution_id)
        return _outcome(
            IngestEnd.RUN_FAILED,
            "the final status conflicts with stored state",
            execution_id=execution_id,
            run_status=stored.status,
        )
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
    reporter: IngestReporter,
) -> str | None:
    """Draw a free id; raise `_IdUnchecked` when a check cannot be made."""
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
        except PersistenceError as error:
            _report_failure(reporter, "read_run", execution_id, error)
            raise _IdUnchecked(execution_id) from error
        else:
            continue
        try:
            taken = store.list_observation_sequences(execution_id)
        except (OSError, EvidenceIntegrityError) as error:
            raise _IdUnchecked(execution_id) from error
        if not taken:
            return execution_id
    return None


def _cleanup_step[T](
    reporter: IngestReporter,
    execution_id: str,
    operation: str,
    call: Callable[[], T],
    *,
    detail: str | None = None,
    sequence: int | None = None,
) -> T:
    """One database operation of State machine K: if it raises, say so and stop."""
    try:
        return call()
    except Exception as error:  # Any failure stops State machine K.
        _report_failure(
            reporter, operation, execution_id, error, detail=detail, sequence=sequence
        )
        raise _CleanupStopped from error


def _cleanup_after_exception(
    *,
    repository: ClosableIngestionRepository,
    clock: Clock,
    store: RawEvidenceStore,
    reporter: IngestReporter,
    execution_id: str,
    pending_sequence: int | None,
    event_type: AuditEventType,
    event_detail: dict[str, JsonValue],
    end: IngestEnd,
    message: str,
) -> IngestOutcome:
    """State machine K: best effort, on the current connection, no new one.

    Only a second `KeyboardInterrupt` and `SystemExit` leave it; any other
    exception stops it where it is and leaves the run `running`. A database
    operation that raises writes one progress line before it stops.
    """
    try:
        run = _cleanup_step(
            reporter,
            execution_id,
            "read_run",
            lambda: repository.read_run(execution_id),
        )
        if run.status is not RunStatus.RUNNING:
            return _outcome(
                end, message, execution_id=execution_id, run_status=run.status
            )
        if pending_sequence is not None:
            try:
                pending = store.read_observation(execution_id, pending_sequence)
            except (EvidenceNotFoundError, EvidenceIntegrityError, OSError):
                pending = None
            if pending is not None:
                recorded = pending
                _cleanup_step(
                    reporter,
                    execution_id,
                    "record_observation",
                    lambda: repository.record_observation(recorded),
                    sequence=pending_sequence,
                )
        occurred_at = clock.now()
        _cleanup_step(
            reporter,
            execution_id,
            "append_audit_event",
            lambda: repository.append_audit_event(
                execution_id=execution_id,
                occurred_at=occurred_at,
                event_type=event_type.value,
                detail=event_detail,
            ),
            detail=event_type.value,
        )
        finished_at = clock.now()
        run = _cleanup_step(
            reporter,
            execution_id,
            "finish_run",
            lambda: repository.finish_run(
                execution_id=execution_id,
                status=RunStatus.FAILED,
                finished_at=finished_at,
            ),
            detail=RunStatus.FAILED.value,
        )
    except Exception:  # noqa: BLE001 -- State machine K stops at any other failure.
        return _outcome(
            end,
            message,
            execution_id=execution_id,
            run_status=RunStatus.RUNNING,
        )
    return _outcome(end, message, execution_id=execution_id, run_status=run.status)


def _reconciliation_stopped(
    reporter: IngestReporter,
    operation: str,
    execution_id: str | None,
    error: PersistenceError,
    *,
    detail: str | None = None,
    sequence: int | None = None,
) -> _ReconciliationRefused:
    """Write the line of a refused or lost operation; return what ends the step."""
    _report_failure(
        reporter, operation, execution_id, error, detail=detail, sequence=sequence
    )
    if execution_id is None:
        return _ReconciliationRefused("the running runs could not be listed")
    return _ReconciliationRefused(
        f"the reconciliation of run {execution_id} could not be completed"
    )


def _guarded[T](
    reporter: IngestReporter,
    operation: str,
    execution_id: str | None,
    call: Callable[[], T],
    *,
    detail: str | None = None,
) -> T:
    """Run a read or write of the reconciliation; a failure ends the reconciliation.

    A refusal and a lost connection both stop it, with one line and a message that
    names the run; the reconciliation opens no new connection.
    """
    try:
        return call()
    except PersistenceError as error:
        raise _reconciliation_stopped(
            reporter, operation, execution_id, error, detail=detail
        ) from error


def _read_database[T](
    reporter: IngestReporter,
    operation: str,
    execution_id: str,
    call: Callable[[str], T],
    *,
    sequence: int | None = None,
) -> T:
    """Read run `execution_id` before the run of this call exists.

    A failed read is reported and raises `_Unreadable`. `PersistenceNotFoundError`
    is an answer the caller reads, so it passes through.
    """
    try:
        return call(execution_id)
    except PersistenceNotFoundError:
        raise
    except PersistenceError as error:
        _report_failure(reporter, operation, execution_id, error, sequence=sequence)
        raise _Unreadable from error


def _reconciliation_event(
    repository: ClosableIngestionRepository,
    clock: Clock,
    reporter: IngestReporter,
    execution_id: str,
    event_type: AuditEventType,
    detail: dict[str, JsonValue],
) -> None:
    _guarded(
        reporter,
        "append_audit_event",
        execution_id,
        lambda: _append_event(repository, clock, execution_id, event_type, detail),
        detail=event_type.value,
    )


def _reconciliation_finish(
    repository: ClosableIngestionRepository,
    clock: Clock,
    reporter: IngestReporter,
    execution_id: str,
) -> None:
    _guarded(
        reporter,
        "finish_run",
        execution_id,
        lambda: repository.finish_run(
            execution_id=execution_id,
            status=RunStatus.FAILED,
            finished_at=clock.now(),
        ),
        detail=RunStatus.FAILED.value,
    )


def _reconciliation_failed(
    repository: ClosableIngestionRepository,
    clock: Clock,
    reporter: IngestReporter,
    run: IngestionRun,
    sequence: int | None,
    problem: ReconciliationProblem,
) -> bool:
    _reconciliation_event(
        repository,
        clock,
        reporter,
        run.execution_id,
        AuditEventType.RECONCILIATION_FAILED,
        {"sequence": sequence, "problem": problem.value},
    )
    _reconciliation_finish(repository, clock, reporter, run.execution_id)
    return False


def _reconcile_run(
    repository: ClosableIngestionRepository,
    store: RawEvidenceStore,
    clock: Clock,
    reporter: IngestReporter,
    run: IngestionRun,
) -> bool:
    def failed(sequence: int | None, problem: ReconciliationProblem) -> bool:
        return _reconciliation_failed(
            repository, clock, reporter, run, sequence, problem
        )

    try:
        local_sequences = store.list_observation_sequences(run.execution_id)
    except (EvidenceIntegrityError, OSError):
        return failed(None, ReconciliationProblem.LOCAL_LISTING_FAILED)

    postgres = {
        observation.sequence: observation
        for observation in _guarded(
            reporter,
            "list_observations",
            run.execution_id,
            lambda: repository.list_observations(run.execution_id),
        )
    }
    local: dict[int, Observation] = {}
    all_sequences = sorted(set(local_sequences) | set(postgres))
    for sequence in all_sequences:
        if sequence in postgres and sequence not in local_sequences:
            return failed(sequence, ReconciliationProblem.LOCAL_OBSERVATION_MISSING)
        try:
            observation = store.read_observation(run.execution_id, sequence)
        except (EvidenceIntegrityError, EvidenceNotFoundError, OSError):
            return failed(sequence, ReconciliationProblem.LOCAL_OBSERVATION_UNREADABLE)
        local[sequence] = observation
        if sequence in postgres and postgres[sequence] != observation:
            return failed(sequence, ReconciliationProblem.LOCAL_OBSERVATION_DIFFERENT)
        try:
            store.read_content(observation.content_hash)
        except EvidenceNotFoundError:
            return failed(sequence, ReconciliationProblem.OBJECT_MISSING)
        except (EvidenceIntegrityError, OSError):
            return failed(sequence, ReconciliationProblem.OBJECT_INTEGRITY)

    if all_sequences:
        expected = set(range(1, max(all_sequences) + 1))
        actual = set(all_sequences)
        if actual != expected:
            missing = min(expected - actual) if expected - actual else 0
            return failed(missing, ReconciliationProblem.SEQUENCE_GAP)

    local_only = sorted(set(local) - set(postgres))
    for sequence in local_only:
        try:
            repository.record_observation(local[sequence])
        except PersistenceConnectionError as error:
            raise _reconciliation_stopped(
                reporter,
                "record_observation",
                run.execution_id,
                error,
                sequence=sequence,
            ) from error
        except PersistenceError as error:
            _report_failure(
                reporter,
                "record_observation",
                run.execution_id,
                error,
                sequence=sequence,
            )
            return failed(
                sequence, ReconciliationProblem.POSTGRESQL_OBSERVATION_CONFLICT
            )
        _reconciliation_event(
            repository,
            clock,
            reporter,
            run.execution_id,
            AuditEventType.OBSERVATION_RECONCILED,
            {"sequence": sequence},
        )

    _reconciliation_event(
        repository,
        clock,
        reporter,
        run.execution_id,
        AuditEventType.RUN_CLOSED_BY_RECONCILIATION,
        {"reconciled_observations": len(local_only)},
    )
    _reconciliation_finish(repository, clock, reporter, run.execution_id)
    return True


def _reconcile_running_runs(
    repository: ClosableIngestionRepository,
    store: RawEvidenceStore,
    clock: Clock,
    reporter: IngestReporter,
) -> bool:
    for run in _guarded(
        reporter,
        "list_runs",
        None,
        lambda: repository.list_runs(RunStatus.RUNNING),
    ):
        if not _reconcile_run(repository, store, clock, reporter, run):
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
    reporter: IngestReporter,
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
    postgres = _read_database(
        reporter,
        "read_observation",
        run_id,
        lambda run: repository.read_observation(run, sequence),
        sequence=sequence,
    )
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
    reporter: IngestReporter,
    target_id: str,
) -> _ResumePlan:
    """Check the chain of `target_id` (State machine H).

    A verdict on the chain raises `ValueError` (or the not-found errors that
    count as one); a database read that fails raises `_Unreadable`.
    """
    target = _read_database(reporter, "read_run", target_id, repository.read_run)
    scope = IngestScope.from_json(target.scope)
    chain_from_target: list[_ChainEntry] = []
    visited: set[str] = set()
    current_id: str | None = target_id
    while current_id is not None:
        if current_id in visited:
            raise ValueError("the resumption chain is cyclic")
        visited.add(current_id)
        run = _read_database(reporter, "read_run", current_id, repository.read_run)
        events = _read_database(
            reporter, "list_audit_events", current_id, repository.list_audit_events
        )
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
                    repository, store, reporter, scope, entry.run.execution_id, event
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
    except PersistenceError as error:
        _report_failure(reporter, "open_repository", None, error)
        return _outcome(IngestEnd.NOT_STARTED, "the repository is unavailable")
    except KeyboardInterrupt:
        return _outcome(IngestEnd.INTERRUPTED, "the ingest was interrupted")
    except Exception as error:  # noqa: BLE001 -- only the class name is reported.
        return _outcome(
            IngestEnd.NOT_STARTED,
            f"the repository could not be opened: {type(error).__name__}",
        )
    session = _PersistenceSession(repository, open_repository, reporter)
    try:
        outcome = _ingest_through(
            request,
            source=source,
            store=store,
            session=session,
            clock=clock,
            execution_ids=execution_ids,
            reporter=reporter,
        )
    except BaseException:
        _close_while_propagating(session)
        raise
    return _close_after_outcome(outcome, session)


def _close_remaining(session: _PersistenceSession) -> BaseException | None:
    """The final close: every repository not closed yet is attempted, each once.

    An `Exception` from a `close()`, `MemoryError` included, is suppressed. What
    else a `close()` raises is returned once the other repositories were attempted:
    a `KeyboardInterrupt`, or a `SystemExit`, which prevails.
    """
    raised: BaseException | None = None
    for repository in session.unclosed():
        try:
            # Closing never changes how the run ended.
            with suppress(Exception):
                session.close(repository)
        except BaseException as error:  # noqa: BLE001 -- returned, not raised here.
            raised = error if raised is None else _prevailing(raised, error)
    return raised


def _close_while_propagating(session: _PersistenceSession) -> None:
    """The final close while an exception leaves `run_ingest`.

    An `Exception` from it is suppressed and the propagating exception goes on; a
    `KeyboardInterrupt` or a `SystemExit` from it propagates in its place.
    """
    raised = _close_remaining(session)
    if raised is not None:
        raise raised


def _close_after_outcome(
    outcome: IngestOutcome, session: _PersistenceSession
) -> IngestOutcome:
    """The final close once the outcome is determined: it never changes how the run ended.

    A `KeyboardInterrupt` during it keeps the run and its confirmed status and
    records the interrupt; nothing is read from or written to the run.
    """
    raised = _close_remaining(session)
    if raised is None:
        return outcome
    if not isinstance(raised, KeyboardInterrupt):
        raise raised
    if outcome.end is IngestEnd.INTERRUPTED:
        return outcome
    return _outcome(
        IngestEnd.INTERRUPTED,
        f"the ingest was interrupted while the repository was closed: {outcome.message}",
        execution_id=outcome.execution_id,
        run_status=outcome.run_status,
    )


def _ingest_through(
    request: IngestRequest | ResumeRequest,
    *,
    source: ProcurementSource,
    store: RawEvidenceStore,
    session: _PersistenceSession,
    clock: Clock,
    execution_ids: ExecutionIdSource,
    reporter: IngestReporter,
) -> IngestOutcome:
    """The run itself, on the repositories of `session`; it closes none of them."""
    execution_id: str | None = None
    run_created = False
    page = request.scope.first_page if isinstance(request, IngestRequest) else 1
    # The sequence of a local observation that PostgreSQL may not hold yet: from
    # the call of `store` until `record_observation` returns (State machine K).
    pending_sequence: int | None = None

    try:
        try:
            with _reporting_failure(reporter, "try_acquire_ingest_exclusion", None):
                acquired = session.repository.try_acquire_ingest_exclusion()
        except PersistenceError:
            return _outcome(IngestEnd.NOT_STARTED, "the ingest exclusion failed")
        if not acquired:
            return _outcome(IngestEnd.NOT_STARTED, "another ingest is running")

        target_id: str | None = None
        if isinstance(request, ResumeRequest):
            target_id = request.execution_id
            try:
                target = _read_database(
                    reporter, "read_run", target_id, session.repository.read_run
                )
            except PersistenceNotFoundError:
                return _outcome(
                    IngestEnd.INVALID_TARGET,
                    f"invalid resumption target {target_id}",
                )
            except _Unreadable:
                # Its existence is unknown: not an invalid target.
                return _outcome(
                    IngestEnd.NOT_STARTED,
                    f"the resumption target {target_id} could not be read",
                )
            if target.status is RunStatus.SUCCEEDED:
                return _outcome(
                    IngestEnd.INVALID_TARGET,
                    f"invalid resumption target {target_id}",
                )

        try:
            reconciled = _reconcile_running_runs(
                session.repository, store, clock, reporter
            )
        except _ReconciliationRefused as refused:
            return _outcome(IngestEnd.NOT_STARTED, str(refused))
        if not reconciled:
            return _outcome(IngestEnd.NOT_STARTED, "reconciliation failed")

        if target_id is None:
            assert isinstance(request, IngestRequest)
            scope = request.scope
            pages_to_request = tuple(range(scope.first_page, scope.last_page + 1))
            first_page = scope.first_page
        else:
            try:
                resume_plan = _resume_plan(
                    session.repository, store, reporter, target_id
                )
            except _Unreadable:
                return _outcome(
                    IngestEnd.NOT_STARTED,
                    f"the resumption chain of {target_id} could not be read",
                )
            except (
                ValueError,
                PersistenceNotFoundError,
                EvidenceNotFoundError,
                EvidenceIntegrityError,
                OSError,
            ):
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
                session.repository, store, execution_ids, started_at, reporter
            )
        except _IdUnchecked as unchecked:
            return _outcome(
                IngestEnd.NOT_STARTED,
                f"the execution id {unchecked.execution_id} could not be checked",
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
                ),
                name="start_run",
                execution_id=execution_id,
            )
        except KeyboardInterrupt:
            return _outcome(IngestEnd.INTERRUPTED, "the ingest was interrupted")
        except _ConnectionUnconfirmed:
            return _unconfirmed(execution_id)
        except PersistenceError as error:
            _report_failure(reporter, "start_run", execution_id, error)
            return _outcome(IngestEnd.NOT_STARTED, "the database refused the run")
        run_created = True
        reporter.run_started(execution_id)
        if recovered:
            return _fail_postgresql(
                session,
                clock,
                reporter,
                execution_id,
                page=first_page,
                sequence=None,
            )
        ended = _append_on_normal_path(
            session,
            clock,
            reporter,
            execution_id,
            AuditEventType.RUN_STARTED,
            {"resumes": target_id, "first_page": first_page},
            page=first_page,
            sequence=None,
        )
        if ended is not None:
            return ended

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
                reporter.progress(f"page {page} no response")
                return _close_failed(
                    session,
                    clock,
                    reporter,
                    execution_id,
                    AuditEventType.PAGE_FAILED,
                    {
                        "page": page,
                        "sequence": None,
                        "failure": PageFailure.TRANSPORT.value,
                        "status": None,
                    },
                )

            pending_sequence = next_sequence
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
                    _report_page(reporter, page, published_observation)
                    try:
                        session.safe_repeat(
                            _record_observation_operation(published_observation),
                            name=f"record_observation sequence {next_sequence}",
                            execution_id=execution_id,
                        )
                    except _ConnectionUnconfirmed:
                        return _unconfirmed(execution_id)
                    except PersistenceError as error:
                        # The refusal ends the pending period before its line is
                        # written: nothing records this observation again.
                        pending_sequence = None
                        _report_failure(
                            reporter,
                            "record_observation",
                            execution_id,
                            error,
                            sequence=next_sequence,
                        )
                        return _fail_postgresql(
                            session,
                            clock,
                            reporter,
                            execution_id,
                            page=page,
                            sequence=next_sequence,
                        )
                else:
                    reporter.progress(
                        f"page {page} sequence {next_sequence} not stored"
                    )
                pending_sequence = None
                return _close_failed(
                    session,
                    clock,
                    reporter,
                    execution_id,
                    AuditEventType.STORAGE_FAILED,
                    {
                        "page": page,
                        "sequence": next_sequence,
                        "store": EvidenceStoreName.RAW_EVIDENCE.value,
                    },
                )
            observation = stored_observation
            next_sequence += 1
            _report_page(reporter, page, observation)

            try:
                _, recovered = session.safe_repeat(
                    _record_observation_operation(observation),
                    name=f"record_observation sequence {observation.sequence}",
                    execution_id=execution_id,
                )
            except _ConnectionUnconfirmed:
                return _unconfirmed(execution_id)
            except PersistenceError as error:
                pending_sequence = None
                _report_failure(
                    reporter,
                    "record_observation",
                    execution_id,
                    error,
                    sequence=observation.sequence,
                )
                return _fail_postgresql(
                    session,
                    clock,
                    reporter,
                    execution_id,
                    page=page,
                    sequence=observation.sequence,
                )
            pending_sequence = None
            if recovered:
                return _fail_postgresql(
                    session,
                    clock,
                    reporter,
                    execution_id,
                    page=page,
                    sequence=observation.sequence,
                )

            if source_error is not None:
                return _close_failed(
                    session,
                    clock,
                    reporter,
                    execution_id,
                    AuditEventType.PAGE_FAILED,
                    {
                        "page": page,
                        "sequence": observation.sequence,
                        "failure": _failure_kind(source_error).value,
                        "status": response.status,
                    },
                )

            assert result is not None
            ended = _append_on_normal_path(
                session,
                clock,
                reporter,
                execution_id,
                AuditEventType.PAGE_COMPLETED,
                {
                    "page": page,
                    "sequence": observation.sequence,
                    "content_hash": observation.content_hash.hexdigest,
                },
                page=page,
                sequence=observation.sequence,
            )
            if ended is not None:
                return ended
            if page >= result.pages:
                ended = _append_on_normal_path(
                    session,
                    clock,
                    reporter,
                    execution_id,
                    AuditEventType.LAST_PAGE_REACHED,
                    {"page": page, "pages": result.pages},
                    page=page,
                    sequence=observation.sequence,
                )
                if ended is not None:
                    return ended
                return _finish_succeeded(
                    session, clock, reporter, execution_id, page=page
                )

        return _finish_succeeded(session, clock, reporter, execution_id, page=page)
    except KeyboardInterrupt as interrupt:
        if not run_created or execution_id is None:
            return _outcome(IngestEnd.INTERRUPTED, "the ingest was interrupted")
        # With no current repository State machine K is not entered (State machine
        # C, "The explicit record"), whatever raised and wherever it landed.
        current = session.current
        if current is None:
            return _recovery_ended(interrupt, execution_id)
        return _cleanup_after_exception(
            repository=current,
            clock=clock,
            store=store,
            reporter=reporter,
            execution_id=execution_id,
            pending_sequence=pending_sequence,
            event_type=AuditEventType.RUN_INTERRUPTED,
            event_detail={"page": page},
            end=IngestEnd.INTERRUPTED,
            message="the ingest was interrupted",
        )
    except Exception as error:  # noqa: BLE001 -- State machine K audits defects.
        if not run_created or execution_id is None:
            return _outcome(IngestEnd.NOT_STARTED, type(error).__name__)
        current = session.current
        if current is None:
            return _recovery_ended(error, execution_id)
        return _cleanup_after_exception(
            repository=current,
            clock=clock,
            store=store,
            reporter=reporter,
            execution_id=execution_id,
            pending_sequence=pending_sequence,
            event_type=AuditEventType.UNEXPECTED_ERROR,
            event_detail={"page": page, "error_type": type(error).__name__},
            end=IngestEnd.RUN_FAILED,
            message=f"unexpected error: {type(error).__name__}",
        )
