"""PostgreSQL adapter for the `IngestionRepository` port, on `psycopg` 3 (ADR 0007).

It keeps ingestion runs, raw evidence rows (content hash and size, never bytes),
observations and audit events in the schema of `migrations/`. Every operation
is one transaction, so it is applied completely or not at all:

- the input is validated before any SQL is sent (`ValueError`, naming the field
  and never its value), including the limits PostgreSQL has and the domain does
  not: U+0000 or a lone surrogate in a text, a sequence above 2,147,483,647 and
  a size above 9,223,372,036,854,775,807;
- a write whose identity already exists is a no-op when every value is the same
  and a `PersistenceIntegrityError` otherwise, never an overwrite. JSON values
  (a scope) are compared with `same_json`, so `True` is not `1`;
- times are stored as instants and read back in UTC (the offset is not stored);
- an observation's size is read from `raw_evidence` by join.

A connection lost before the statements are sent, or while the transaction is
open, leaves nothing written. A connection lost while the commit is in flight
leaves the outcome unknown: `PersistenceConnectionError` is raised although the
transaction may have committed in full. The adapter cannot tell which and does
not try. It never reconnects: once the connection is lost every later call
raises `PersistenceConnectionError`. After `close()` a call raises
`RuntimeError`.

The adapter writes no log output. Its errors carry fixed text that names the
operation and an identity (an execution id, a sequence, a content hash), never
a stored value, a setting or any text from the driver or the server (the
server's own messages quote the rows they reject). Every error is raised
outside the `except` block that caught the driver's exception, with no `from`
clause, so no `psycopg` exception is reachable through `__cause__` or
`__context__`.
"""

import json
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any, Self

import psycopg

from ec_procurement_quality.domain.content_hash import ContentHash
from ec_procurement_quality.domain.ingestion_audit import (
    AuditEvent,
    IngestionRun,
    JsonValue,
    RunStatus,
    same_json,
)
from ec_procurement_quality.domain.persistence_errors import (
    PersistenceConnectionError,
    PersistenceError,
    PersistenceIntegrityError,
    PersistenceNotFoundError,
)
from ec_procurement_quality.domain.raw_evidence import (
    Observation,
    validate_execution_id,
    validate_sequence,
)
from ec_procurement_quality.infrastructure.postgres_settings import (
    PostgresConnection,
    PostgresSettings,
    connection_was_lost,
    open_connection,
)

_MAX_SEQUENCE = 2_147_483_647  # PostgreSQL `integer`
_MAX_SIZE = 9_223_372_036_854_775_807  # PostgreSQL `bigint`

_RUN_COLUMNS = "execution_id, scope, started_at, finished_at, status"
_OBSERVATION_COLUMNS = (
    "o.execution_id, o.sequence, o.method, o.url, o.status, o.headers, "
    "o.captured_at, o.content_hash, r.size"
)
_OBSERVATION_FROM = (
    "FROM observation o JOIN raw_evidence r ON r.content_hash = o.content_hash"
)
_EVENT_COLUMNS = "event_id, execution_id, occurred_at, event_type, detail"


# --- Input validation (before any SQL) --------------------------------------


def _is_storable_text(text: str) -> bool:
    """Whether PostgreSQL can store `text`: no U+0000 and no lone surrogate."""
    if "\x00" in text:
        return False
    if text.isascii():
        return True
    # The encoding error would hold the text, so only the answer leaves here.
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        pass
    else:
        return True
    return False


def _json_is_storable(value: object) -> bool:
    """Whether every text (string value or key) nested in `value` is storable."""
    if isinstance(value, str):
        return _is_storable_text(value)
    if isinstance(value, list):
        return all(_json_is_storable(item) for item in value)
    if isinstance(value, dict):
        return all(
            _is_storable_text(key) and _json_is_storable(item)
            for key, item in value.items()
        )
    return True


def _json_text(value: Mapping[str, JsonValue], field: str) -> str:
    """The JSON text of a scope or detail, already known to follow the JSON rule."""
    if not _json_is_storable(value):
        raise ValueError(f"{field} must not contain U+0000 or a lone surrogate")
    try:
        return json.dumps(dict(value), ensure_ascii=True, allow_nan=False)
    except ValueError:
        pass  # an integer with too many digits: the interpreter's text is dropped
    raise ValueError(f"{field} cannot be written as JSON text")


def _require_storable(text: str, field: str) -> None:
    if not _is_storable_text(text):
        raise ValueError(f"{field} must not contain U+0000 or a lone surrogate")


def _require_aware(value: object, field: str) -> None:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{field} must be a datetime with a UTC offset")


def _require_limits(sequence: int) -> None:
    validate_sequence(sequence)
    if sequence > _MAX_SEQUENCE:
        raise ValueError("a sequence must be at most 2147483647")


# --- Rows to domain records -------------------------------------------------


def _run_from_row(row: tuple[Any, ...], operation: str) -> IngestionRun:
    execution_id, scope, started_at, finished_at, status = row
    run: IngestionRun | None = None
    try:
        run = IngestionRun(
            execution_id=execution_id,
            scope=scope,
            started_at=started_at,
            status=RunStatus(status),
            finished_at=finished_at,
        )
    except (ValueError, TypeError):
        pass
    if run is None:
        raise PersistenceIntegrityError(
            f"{operation}: the stored run {execution_id} is not valid"
        )
    return run


def _headers_from_json(value: object) -> tuple[tuple[str, str], ...] | None:
    if not isinstance(value, list):
        return None
    headers: list[tuple[str, str]] = []
    for pair in value:
        if (
            not isinstance(pair, list)
            or len(pair) != 2
            or not isinstance(pair[0], str)
            or not isinstance(pair[1], str)
        ):
            return None
        headers.append((pair[0], pair[1]))
    return tuple(headers)


def _observation_from_row(row: tuple[Any, ...], operation: str) -> Observation:
    execution_id, sequence, method, url, status, headers, captured_at, digest, size = (
        row
    )
    observation: Observation | None = None
    pairs = _headers_from_json(headers)
    if pairs is not None:
        try:
            observation = Observation(
                execution_id=execution_id,
                sequence=sequence,
                method=method,
                url=url,
                status=status,
                headers=pairs,
                captured_at=captured_at,
                content_hash=ContentHash(digest),
                size=size,
            )
        except (ValueError, TypeError):
            pass
    if observation is None:
        raise PersistenceIntegrityError(
            f"{operation}: the stored observation {execution_id}/{sequence} "
            "is not valid"
        )
    return observation


def _event_from_row(row: tuple[Any, ...], operation: str) -> AuditEvent:
    event_id, execution_id, occurred_at, event_type, detail = row
    event: AuditEvent | None = None
    try:
        event = AuditEvent(
            event_id=event_id,
            execution_id=execution_id,
            occurred_at=occurred_at,
            event_type=event_type,
            detail=detail,
        )
    except (ValueError, TypeError):
        pass
    if event is None:
        raise PersistenceIntegrityError(
            f"{operation}: a stored audit event of {execution_id} is not valid"
        )
    return event


# --- The adapter ------------------------------------------------------------


class PostgresIngestionRepository:
    """Ingestion repository that keeps its records in PostgreSQL.

    The adapter connects when built, and `close()` (or leaving a `with` block)
    ends the connection. An instance must be used by one thread at a time:
    nothing enforces it, and two threads on one instance share one connection
    and one transaction. Use one instance per thread, or serialize the calls.
    """

    def __init__(self, settings: PostgresSettings) -> None:
        if not isinstance(settings, PostgresSettings):
            raise ValueError(  # noqa: TRY004 (ValueError is the pinned error)
                "settings must be a PostgresSettings"
            )
        self._connection: PostgresConnection = open_connection(settings)
        self._closed = False
        self._lost = False

    # --- Runs ---------------------------------------------------------------

    def start_run(
        self, *, execution_id: str, scope: Mapping[str, JsonValue], started_at: datetime
    ) -> IngestionRun:
        """Insert a `running` run, or return the stored one if it is the same."""
        self._require_usable("start_run")
        validate_execution_id(execution_id)
        run = IngestionRun(
            execution_id=execution_id,
            scope=scope,
            started_at=started_at,
            status=RunStatus.RUNNING,
            finished_at=None,
        )
        scope_text = _json_text(run.scope, "scope")

        def work(connection: PostgresConnection) -> IngestionRun:
            row = connection.execute(
                "INSERT INTO ingestion_run (execution_id, scope, started_at, status) "
                "VALUES (%s, %s::jsonb, %s, 'running') "
                f"ON CONFLICT (execution_id) DO NOTHING RETURNING {_RUN_COLUMNS}",
                (execution_id, scope_text, run.started_at),
            ).fetchone()
            if row is not None:
                return _run_from_row(row, "start_run")
            stored = self._select_run(connection, execution_id, "start_run", lock=False)
            # The stored scope was read back from `jsonb`, which keeps `true` as
            # `True` and integers as `int`, so `same_json` tells the types apart.
            if stored.started_at != run.started_at or not same_json(
                stored.scope, run.scope
            ):
                raise PersistenceIntegrityError(
                    f"start_run: run {execution_id} already exists with another "
                    "scope or start time"
                )
            return stored

        return self._transaction("start_run", execution_id, work)

    def finish_run(
        self, *, execution_id: str, status: RunStatus, finished_at: datetime
    ) -> IngestionRun:
        """Move a `running` run to `succeeded` or `failed`; repeats are no-ops."""
        self._require_usable("finish_run")
        validate_execution_id(execution_id)
        if not isinstance(status, RunStatus) or status is RunStatus.RUNNING:
            raise ValueError(
                "a status that finishes a run must be RunStatus.SUCCEEDED or "
                "RunStatus.FAILED"
            )
        _require_aware(finished_at, "finished_at")

        def work(connection: PostgresConnection) -> IngestionRun:
            stored = self._select_run(connection, execution_id, "finish_run", lock=True)
            if stored.status is not RunStatus.RUNNING:
                if stored.status is status and stored.finished_at == finished_at:
                    return stored
                raise PersistenceIntegrityError(
                    f"finish_run: run {execution_id} is already finished with "
                    "another status or finish time"
                )
            # Raises `ValueError` when `finished_at` is before `started_at`;
            # nothing has been written yet, and the transaction is rolled back.
            IngestionRun(
                execution_id=execution_id,
                scope=stored.scope,
                started_at=stored.started_at,
                status=status,
                finished_at=finished_at,
            )
            row = connection.execute(
                "UPDATE ingestion_run SET status = %s, finished_at = %s "
                f"WHERE execution_id = %s RETURNING {_RUN_COLUMNS}",
                (status.value, finished_at, execution_id),
            ).fetchone()
            if row is None:
                raise PersistenceIntegrityError(
                    f"finish_run: run {execution_id} could not be updated"
                )
            return _run_from_row(row, "finish_run")

        return self._transaction("finish_run", execution_id, work)

    def read_run(self, execution_id: str) -> IngestionRun:
        """Return the run stored for `execution_id`."""
        self._require_usable("read_run")
        validate_execution_id(execution_id)
        return self._transaction(
            "read_run",
            execution_id,
            lambda connection: self._select_run(
                connection, execution_id, "read_run", lock=False
            ),
        )

    # --- Observations -------------------------------------------------------

    def record_observation(self, observation: Observation) -> Observation:
        """Record an observation and its content row; return the stored one."""
        self._require_usable("record_observation")
        if not isinstance(observation, Observation):
            raise ValueError(  # noqa: TRY004 (ValueError is the pinned error)
                "observation must be an Observation"
            )
        _require_limits(observation.sequence)
        _require_storable(observation.method, "method")
        _require_storable(observation.url, "url")
        for name, value in observation.headers:
            _require_storable(name, "headers")
            _require_storable(value, "headers")
        if observation.size > _MAX_SIZE:
            raise ValueError("a size must be at most 9223372036854775807")
        headers_text = json.dumps(
            [[name, value] for name, value in observation.headers], ensure_ascii=True
        )
        digest = observation.content_hash.hexdigest
        execution_id = observation.execution_id
        sequence = observation.sequence
        identity = f"{execution_id}/{sequence}"

        def work(connection: PostgresConnection) -> Observation:
            evidence = connection.execute(
                "INSERT INTO raw_evidence (content_hash, size) VALUES (%s, %s) "
                "ON CONFLICT (content_hash) DO NOTHING RETURNING content_hash",
                (digest, observation.size),
            ).fetchone()
            if evidence is None:
                row = connection.execute(
                    "SELECT size FROM raw_evidence WHERE content_hash = %s", (digest,)
                ).fetchone()
                if row is None or row[0] != observation.size:
                    raise PersistenceIntegrityError(
                        f"record_observation {identity}: content {digest} is "
                        "already stored with another size"
                    )
            connection.execute(
                "INSERT INTO observation (execution_id, sequence, method, url, "
                "status, headers, captured_at, content_hash) "
                "VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s) "
                "ON CONFLICT (execution_id, sequence) DO NOTHING",
                (
                    execution_id,
                    sequence,
                    observation.method,
                    observation.url,
                    observation.status,
                    headers_text,
                    observation.captured_at,
                    digest,
                ),
            )
            stored = self._select_observation(
                connection, execution_id, sequence, "record_observation"
            )
            # Equal field by field: times by instant, headers as an ordered
            # list of exact (name, value) pairs, numbers as plain `int`.
            if stored != observation:
                raise PersistenceIntegrityError(
                    f"record_observation: observation {identity} already exists "
                    "with different data"
                )
            return stored

        return self._transaction("record_observation", identity, work)

    def read_observation(self, execution_id: str, sequence: int) -> Observation:
        """Return the observation stored for `execution_id` and `sequence`."""
        self._require_usable("read_observation")
        validate_execution_id(execution_id)
        _require_limits(sequence)
        return self._transaction(
            "read_observation",
            f"{execution_id}/{sequence}",
            lambda connection: self._select_observation(
                connection, execution_id, sequence, "read_observation"
            ),
        )

    def list_observations(self, execution_id: str) -> tuple[Observation, ...]:
        """Return the run's observations in sequence order."""
        self._require_usable("list_observations")
        validate_execution_id(execution_id)

        def work(connection: PostgresConnection) -> tuple[Observation, ...]:
            self._require_run(connection, execution_id, "list_observations")
            rows = connection.execute(
                f"SELECT {_OBSERVATION_COLUMNS} {_OBSERVATION_FROM} "
                "WHERE o.execution_id = %s ORDER BY o.sequence",
                (execution_id,),
            ).fetchall()
            return tuple(
                _observation_from_row(row, "list_observations") for row in rows
            )

        return self._transaction("list_observations", execution_id, work)

    # --- Audit events -------------------------------------------------------

    def append_audit_event(
        self,
        *,
        execution_id: str,
        occurred_at: datetime,
        event_type: str,
        detail: Mapping[str, JsonValue],
    ) -> AuditEvent:
        """Append an event; the database assigns its `event_id`."""
        self._require_usable("append_audit_event")
        validate_execution_id(execution_id)
        # The event id is assigned by the database; 1 stands in for it here.
        candidate = AuditEvent(
            event_id=1,
            execution_id=execution_id,
            occurred_at=occurred_at,
            event_type=event_type,
            detail=detail,
        )
        _require_storable(event_type, "event_type")
        detail_text = _json_text(candidate.detail, "detail")

        def work(connection: PostgresConnection) -> AuditEvent:
            row = connection.execute(
                "INSERT INTO audit_event (execution_id, occurred_at, event_type, "
                f"detail) VALUES (%s, %s, %s, %s::jsonb) RETURNING {_EVENT_COLUMNS}",
                (execution_id, occurred_at, event_type, detail_text),
            ).fetchone()
            if row is None:
                raise PersistenceIntegrityError(
                    f"append_audit_event: no event was stored for {execution_id}"
                )
            return _event_from_row(row, "append_audit_event")

        return self._transaction("append_audit_event", execution_id, work)

    def list_audit_events(self, execution_id: str) -> tuple[AuditEvent, ...]:
        """Return the run's events in the order they were appended."""
        self._require_usable("list_audit_events")
        validate_execution_id(execution_id)

        def work(connection: PostgresConnection) -> tuple[AuditEvent, ...]:
            self._require_run(connection, execution_id, "list_audit_events")
            rows = connection.execute(
                f"SELECT {_EVENT_COLUMNS} FROM audit_event "
                "WHERE execution_id = %s ORDER BY event_id",
                (execution_id,),
            ).fetchall()
            return tuple(_event_from_row(row, "list_audit_events") for row in rows)

        return self._transaction("list_audit_events", execution_id, work)

    # --- Statements shared by several operations ----------------------------

    @staticmethod
    def _select_run(
        connection: PostgresConnection, execution_id: str, operation: str, *, lock: bool
    ) -> IngestionRun:
        row = connection.execute(
            f"SELECT {_RUN_COLUMNS} FROM ingestion_run WHERE execution_id = %s"
            + (" FOR UPDATE" if lock else ""),
            (execution_id,),
        ).fetchone()
        if row is None:
            raise PersistenceNotFoundError(
                f"{operation}: no run {execution_id} was started"
            )
        return _run_from_row(row, operation)

    @staticmethod
    def _require_run(
        connection: PostgresConnection, execution_id: str, operation: str
    ) -> None:
        row = connection.execute(
            "SELECT 1 FROM ingestion_run WHERE execution_id = %s", (execution_id,)
        ).fetchone()
        if row is None:
            raise PersistenceNotFoundError(
                f"{operation}: no run {execution_id} was started"
            )

    @staticmethod
    def _select_observation(
        connection: PostgresConnection,
        execution_id: str,
        sequence: int,
        operation: str,
    ) -> Observation:
        row = connection.execute(
            f"SELECT {_OBSERVATION_COLUMNS} {_OBSERVATION_FROM} "
            "WHERE o.execution_id = %s AND o.sequence = %s",
            (execution_id, sequence),
        ).fetchone()
        if row is None:
            raise PersistenceNotFoundError(
                f"{operation}: no observation {execution_id}/{sequence} was recorded"
            )
        return _observation_from_row(row, operation)

    # --- Transactions and failures ------------------------------------------

    def _require_usable(self, operation: str) -> None:
        if self._closed:
            raise RuntimeError("the ingestion repository is closed")
        if self._lost or self._connection.closed:
            self._lost = True
            raise PersistenceConnectionError(
                f"{operation}: the database connection was lost"
            )

    def _transaction[T](
        self, operation: str, subject: str, work: Callable[[PostgresConnection], T]
    ) -> T:
        """Run `work` and commit, or roll back; map the driver's errors.

        Errors that `work` raises itself (not found, integrity, `ValueError`)
        pass through after the rollback. A driver error is turned into one of
        the persistence errors after the `except` block, with nothing chained.
        """
        try:
            try:
                result = work(self._connection)
                self._connection.commit()
            except BaseException:
                self._rollback_quietly()
                raise
        except psycopg.Error as error:
            problem = self._problem_of(operation, subject, error)
        else:
            return result
        raise problem

    def _problem_of(
        self, operation: str, subject: str, error: psycopg.Error
    ) -> PersistenceError:
        """Choose the error for a driver failure; nothing of `error` is kept."""
        if connection_was_lost(self._connection, error):
            self._lost = True
            return PersistenceConnectionError(
                f"{operation} {subject}: the database connection was lost"
            )
        if isinstance(error, psycopg.IntegrityError):
            return PersistenceIntegrityError(
                f"{operation} {subject}: the database refused the data"
            )
        return PersistenceError(
            f"{operation} {subject}: the database reported an error"
        )

    def _rollback_quietly(self) -> None:
        try:
            self._connection.rollback()
        except psycopg.Error:
            pass

    # --- Close and context manager ------------------------------------------

    def close(self) -> None:
        """Close the connection. Later calls raise `RuntimeError`."""
        if not self._closed:
            self._closed = True
            self._connection.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
