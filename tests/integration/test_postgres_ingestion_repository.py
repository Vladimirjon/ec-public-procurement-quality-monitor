"""Feature postgres-persistence (F3), outcomes O4 and O7 (AC7 to AC13): the
`psycopg` adapter, through the persistence port, against a real PostgreSQL.

Every test runs in its own throwaway database copied from the session's
migrated template (`migrated_database`), or an empty one for connection and
runner cases. Row counts are read with direct SQL from a fresh connection,
never through the adapter under test. Names to focus on, by `-k`: `run_`,
`observation_`, `audit_event_`, `invalid`, `connection`, `leak`,
`satisfies_port`.

All data is synthetic: URLs use `.invalid`, passwords and stored values are
markers such as `synthetic-password-marker` and `synthetic-url-marker`, and a
marker is always passed through a variable (a formatted traceback quotes the
line that made the call).

Not tested, documented in the intent (AC11): a connection lost while a commit
is in flight, whose outcome is unknown. The deterministic cases are: lost before
the statements are sent, and lost while the transaction waits on a lock.
"""

import logging
import re
import socket
import time
import traceback
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import psycopg
import pytest

from ec_procurement_quality.application.ingestion_repository import (
    IngestionRepository,
)
from ec_procurement_quality.domain.content_hash import ContentHash
from ec_procurement_quality.domain.ingestion_audit import (
    AuditEvent,
    IngestionRun,
    RunStatus,
    same_json,
)
from ec_procurement_quality.domain.persistence_errors import (
    MigrationError,
    PersistenceConnectionError,
    PersistenceIntegrityError,
    PersistenceNotFoundError,
)
from ec_procurement_quality.domain.raw_evidence import Observation
from ec_procurement_quality.infrastructure.postgres_ingestion_repository import (
    PostgresIngestionRepository,
)
from ec_procurement_quality.infrastructure.postgres_migrations import apply_migrations
from ec_procurement_quality.infrastructure.postgres_settings import PostgresSettings

pytestmark = pytest.mark.integration

OpenConnection = Callable[..., Any]

ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
EMPTY = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
EXEC_1 = "synthetic-exec-001"
EXEC_2 = "synthetic-exec-002"
NEVER_STARTED = "synthetic-exec-009"
URL = "https://source.invalid/api/search?year=2025&page=1"
SCOPE: dict[str, Any] = {"source": "synthetic", "year": 2025}
UTC_MINUS_5 = timezone(timedelta(hours=-5))
STARTED_AT = datetime(2026, 10, 9, 10, 15, tzinfo=UTC_MINUS_5)
FINISHED_AT = datetime(2026, 10, 9, 10, 15, 42, tzinfo=UTC_MINUS_5)
CAPTURED_AT = datetime(2026, 10, 9, 10, 15, tzinfo=UTC_MINUS_5)
HEADERS = (("Content-Type", "application/json"), ("X-A", "1"), ("X-A", "2"))

PASSWORD_MARKER = "synthetic-password-marker"
URL_MARKER = "synthetic-url-marker"
HEADER_MARKER = "synthetic-header-marker"
SCOPE_MARKER = "synthetic-scope-marker"
OTHER_SCOPE_MARKER = "synthetic-other-scope-marker"
SQL_MARKER = "synthetic-sql-marker"
NUL_MARKER = "synthetic-nul-marker"

TABLES = ("ingestion_run", "raw_evidence", "observation", "audit_event")


def make_observation(**changes: Any) -> Observation:
    fields: dict[str, Any] = {
        "execution_id": EXEC_1,
        "sequence": 1,
        "method": "GET",
        "url": URL,
        "status": 200,
        "headers": HEADERS,
        "captured_at": CAPTURED_AT,
        "content_hash": ContentHash(ABC),
        "size": 3,
    }
    fields.update(changes)
    return Observation(**fields)


OBSERVATION = make_observation()


@pytest.fixture
def repository(
    migrated_database: PostgresSettings,
) -> Iterator[PostgresIngestionRepository]:
    adapter = PostgresIngestionRepository(migrated_database)
    try:
        yield adapter
    finally:
        adapter.close()


def _start(
    repository: PostgresIngestionRepository,
    execution_id: str = EXEC_1,
    scope: Any = None,
    started_at: datetime = STARTED_AT,
) -> IngestionRun:
    return repository.start_run(
        execution_id=execution_id,
        scope=SCOPE if scope is None else scope,
        started_at=started_at,
    )


def _counts(
    open_connection: OpenConnection, settings: PostgresSettings
) -> dict[str, int]:
    """Row counts per table, from a fresh connection."""
    connection = open_connection(settings)
    counts = {
        table: int(connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
        for table in TABLES
    }
    connection.close()
    return counts


def _count_where(
    open_connection: OpenConnection,
    settings: PostgresSettings,
    table: str,
    column: str,
    value: str,
) -> int:
    connection = open_connection(settings)
    row = connection.execute(
        f"SELECT count(*) FROM {table} WHERE {column} = %s", (value,)
    ).fetchone()
    connection.close()
    return int(row[0])


def _with(settings: PostgresSettings, **changes: Any) -> PostgresSettings:
    fields: dict[str, Any] = {
        "host": settings.host,
        "port": settings.port,
        "dbname": settings.dbname,
        "user": settings.user,
        "password": settings.password,
    }
    fields.update(changes)
    return PostgresSettings(**fields)


def _closed_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


# --- AC7: runs ---------------------------------------------------------------


def test_run_start_returns_a_running_run_and_read_returns_an_equal_one(
    repository: PostgresIngestionRepository,
) -> None:
    started = _start(repository)

    assert started.execution_id == EXEC_1
    assert started.status is RunStatus.RUNNING
    assert started.finished_at is None
    assert same_json(started.scope, SCOPE)
    assert started.started_at == STARTED_AT
    assert repository.read_run(EXEC_1) == started


def test_run_times_read_back_are_the_same_instants_in_utc(
    repository: PostgresIngestionRepository,
) -> None:
    _start(repository)
    repository.finish_run(
        execution_id=EXEC_1, status=RunStatus.SUCCEEDED, finished_at=FINISHED_AT
    )

    run = repository.read_run(EXEC_1)

    assert run.started_at == STARTED_AT
    assert run.finished_at == FINISHED_AT
    assert run.started_at.utcoffset() == timedelta(0)
    assert run.finished_at is not None
    assert run.finished_at.utcoffset() == timedelta(0)


def test_run_start_repeated_with_the_same_values_changes_nothing(
    repository: PostgresIngestionRepository,
    migrated_database: PostgresSettings,
    open_connection: OpenConnection,
) -> None:
    first = _start(repository)
    before = _counts(open_connection, migrated_database)

    again = _start(repository)

    assert again == first
    assert _counts(open_connection, migrated_database) == before


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"scope": {"source": "synthetic", "year": 2024}}, id="scope"),
        pytest.param({"started_at": STARTED_AT + timedelta(seconds=1)}, id="start"),
    ],
)
def test_run_start_with_another_scope_or_start_time_is_an_integrity_error(
    repository: PostgresIngestionRepository, changes: dict[str, Any]
) -> None:
    first = _start(repository)

    with pytest.raises(PersistenceIntegrityError):
        _start(repository, **changes)

    assert repository.read_run(EXEC_1) == first


def test_run_start_of_a_finished_run_returns_it_whatever_its_status(
    repository: PostgresIngestionRepository,
) -> None:
    _start(repository)
    finished = repository.finish_run(
        execution_id=EXEC_1, status=RunStatus.FAILED, finished_at=FINISHED_AT
    )

    again = _start(repository)

    assert again == finished
    assert again.status is RunStatus.FAILED


def test_run_start_with_the_same_instant_at_another_offset_is_a_repeat(
    repository: PostgresIngestionRepository,
) -> None:
    first = _start(repository)

    again = _start(repository, started_at=STARTED_AT.astimezone(UTC))

    assert again == first


def test_run_finish_returns_the_finished_run_and_repeats_are_no_ops(
    repository: PostgresIngestionRepository,
    migrated_database: PostgresSettings,
    open_connection: OpenConnection,
) -> None:
    _start(repository)

    finished = repository.finish_run(
        execution_id=EXEC_1, status=RunStatus.SUCCEEDED, finished_at=FINISHED_AT
    )
    before = _counts(open_connection, migrated_database)
    again = repository.finish_run(
        execution_id=EXEC_1, status=RunStatus.SUCCEEDED, finished_at=FINISHED_AT
    )

    assert finished.status is RunStatus.SUCCEEDED
    assert finished.finished_at == FINISHED_AT
    assert repository.read_run(EXEC_1) == finished
    assert again == finished
    assert _counts(open_connection, migrated_database) == before


@pytest.mark.parametrize(
    ("status", "finished_at"),
    [
        pytest.param(RunStatus.FAILED, FINISHED_AT, id="other-status"),
        pytest.param(
            RunStatus.SUCCEEDED, FINISHED_AT + timedelta(seconds=1), id="other-time"
        ),
    ],
)
def test_run_finish_again_with_other_values_is_an_integrity_error(
    repository: PostgresIngestionRepository,
    status: RunStatus,
    finished_at: datetime,
) -> None:
    _start(repository)
    finished = repository.finish_run(
        execution_id=EXEC_1, status=RunStatus.SUCCEEDED, finished_at=FINISHED_AT
    )

    with pytest.raises(PersistenceIntegrityError):
        repository.finish_run(
            execution_id=EXEC_1, status=status, finished_at=finished_at
        )

    assert repository.read_run(EXEC_1) == finished


@pytest.mark.parametrize(
    "status",
    [
        pytest.param(RunStatus.RUNNING, id="running"),
        pytest.param("succeeded", id="plain-string"),
    ],
)
def test_run_finish_with_a_status_that_cannot_finish_a_run_is_a_value_error(
    repository: PostgresIngestionRepository, status: Any
) -> None:
    started = _start(repository)

    with pytest.raises(ValueError):
        repository.finish_run(
            execution_id=EXEC_1, status=status, finished_at=FINISHED_AT
        )

    assert repository.read_run(EXEC_1) == started


def test_run_read_or_finish_of_a_run_never_started_is_not_found(
    repository: PostgresIngestionRepository,
) -> None:
    with pytest.raises(PersistenceNotFoundError):
        repository.read_run(NEVER_STARTED)
    with pytest.raises(PersistenceNotFoundError):
        repository.finish_run(
            execution_id=NEVER_STARTED,
            status=RunStatus.SUCCEEDED,
            finished_at=FINISHED_AT,
        )


@pytest.mark.parametrize(
    ("stored", "given"),
    [
        pytest.param({"x": 1}, {"x": True}, id="one-then-true"),
        pytest.param({"x": True}, {"x": 1}, id="true-then-one"),
        pytest.param({"x": [1]}, {"x": [True]}, id="nested-list"),
        pytest.param({"x": {"y": 0}}, {"x": {"y": False}}, id="nested-dict"),
        pytest.param({"x": [1, 2]}, {"x": [2, 1]}, id="list-order"),
    ],
)
def test_run_start_with_a_scope_of_other_json_types_is_an_integrity_error(
    repository: PostgresIngestionRepository, stored: Any, given: Any
) -> None:
    first = _start(repository, scope=stored)

    with pytest.raises(PersistenceIntegrityError):
        _start(repository, scope=given)

    read = repository.read_run(EXEC_1)
    assert read == first
    assert same_json(read.scope, stored)


@pytest.mark.parametrize(
    ("stored", "given"),
    [
        pytest.param(
            {"x": [1, {"y": True}]}, {"x": [1, {"y": True}]}, id="nested-repeat"
        ),
        pytest.param({"b": 1, "a": 2}, {"a": 2, "b": 1}, id="key-order"),
        pytest.param({}, {}, id="empty"),
    ],
)
def test_run_start_with_the_same_json_scope_returns_the_stored_run(
    repository: PostgresIngestionRepository, stored: Any, given: Any
) -> None:
    first = _start(repository, scope=stored)

    again = _start(repository, scope=given)

    assert again == first
    assert same_json(again.scope, stored)


# --- AC8: observations -------------------------------------------------------


def test_observation_record_stores_one_evidence_row_for_both_runs(
    repository: PostgresIngestionRepository,
    migrated_database: PostgresSettings,
    open_connection: OpenConnection,
) -> None:
    _start(repository, EXEC_1)
    _start(repository, EXEC_2)

    first = repository.record_observation(make_observation(execution_id=EXEC_1))
    second = repository.record_observation(make_observation(execution_id=EXEC_2))

    assert first == make_observation(execution_id=EXEC_1)
    assert second == make_observation(execution_id=EXEC_2)
    counts = _counts(open_connection, migrated_database)
    assert counts["raw_evidence"] == 1
    assert counts["observation"] == 2
    connection = open_connection(migrated_database)
    assert connection.execute(
        "SELECT content_hash, size FROM raw_evidence"
    ).fetchall() == [(ABC, 3)]


def test_observation_read_equals_the_one_given_with_headers_in_order(
    repository: PostgresIngestionRepository,
) -> None:
    _start(repository, EXEC_1)
    repository.record_observation(OBSERVATION)

    read = repository.read_observation(EXEC_1, 1)

    assert read == OBSERVATION
    assert read.headers == HEADERS
    assert read.size == 3
    assert read.captured_at.utcoffset() == timedelta(0)
    assert repository.list_observations(EXEC_1) == (OBSERVATION,)


def test_observation_list_is_in_sequence_order_and_only_of_the_run(
    repository: PostgresIngestionRepository,
) -> None:
    _start(repository, EXEC_1)
    _start(repository, EXEC_2)
    for sequence in (3, 1, 2):
        repository.record_observation(make_observation(sequence=sequence))
    repository.record_observation(make_observation(execution_id=EXEC_2, sequence=1))

    listed = repository.list_observations(EXEC_1)

    assert [observation.sequence for observation in listed] == [1, 2, 3]
    assert {observation.execution_id for observation in listed} == {EXEC_1}
    assert isinstance(listed, tuple)


def test_observation_record_repeated_is_a_no_op(
    repository: PostgresIngestionRepository,
    migrated_database: PostgresSettings,
    open_connection: OpenConnection,
) -> None:
    _start(repository)
    repository.record_observation(OBSERVATION)
    before = _counts(open_connection, migrated_database)

    again = repository.record_observation(OBSERVATION)

    assert again == OBSERVATION
    assert _counts(open_connection, migrated_database) == before


def test_observation_record_with_the_same_instant_at_another_offset_is_a_repeat(
    repository: PostgresIngestionRepository,
) -> None:
    _start(repository)
    repository.record_observation(OBSERVATION)

    again = repository.record_observation(
        make_observation(captured_at=CAPTURED_AT.astimezone(UTC))
    )

    assert again == OBSERVATION


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"status": 500}, id="status"),
        pytest.param({"headers": tuple(reversed(HEADERS))}, id="header-order"),
        pytest.param({"headers": HEADERS[:2]}, id="dropped-repeated-header"),
        pytest.param({"method": "POST"}, id="method"),
        pytest.param({"url": URL + "&extra=1"}, id="url"),
        pytest.param(
            {"captured_at": CAPTURED_AT + timedelta(seconds=1)}, id="captured-at"
        ),
        pytest.param(
            {"content_hash": ContentHash(EMPTY), "size": 0}, id="other-content"
        ),
    ],
)
def test_observation_record_of_a_different_one_under_the_same_identity_is_refused(
    repository: PostgresIngestionRepository,
    migrated_database: PostgresSettings,
    open_connection: OpenConnection,
    changes: dict[str, Any],
) -> None:
    _start(repository)
    repository.record_observation(OBSERVATION)
    before = _counts(open_connection, migrated_database)

    with pytest.raises(PersistenceIntegrityError) as caught:
        repository.record_observation(make_observation(**changes))

    assert EXEC_1 in str(caught.value)
    assert repository.read_observation(EXEC_1, 1) == OBSERVATION
    assert _counts(open_connection, migrated_database) == before
    assert (
        _count_where(
            open_connection, migrated_database, "raw_evidence", "content_hash", EMPTY
        )
        == 0
    )


def test_observation_record_of_known_content_with_another_size_is_refused(
    repository: PostgresIngestionRepository,
    migrated_database: PostgresSettings,
    open_connection: OpenConnection,
) -> None:
    _start(repository)
    repository.record_observation(OBSERVATION)
    before = _counts(open_connection, migrated_database)

    with pytest.raises(PersistenceIntegrityError):
        repository.record_observation(make_observation(sequence=2, size=4))

    assert _counts(open_connection, migrated_database) == before
    with pytest.raises(PersistenceNotFoundError):
        repository.read_observation(EXEC_1, 2)


def test_observation_record_for_a_run_never_started_writes_no_evidence(
    repository: PostgresIngestionRepository,
    migrated_database: PostgresSettings,
    open_connection: OpenConnection,
) -> None:
    with pytest.raises(PersistenceIntegrityError):
        repository.record_observation(make_observation(execution_id=NEVER_STARTED))

    assert _counts(open_connection, migrated_database) == dict.fromkeys(TABLES, 0)


def test_observation_read_of_an_identity_never_recorded_is_not_found(
    repository: PostgresIngestionRepository,
) -> None:
    _start(repository)

    with pytest.raises(PersistenceNotFoundError):
        repository.read_observation(EXEC_1, 9)
    with pytest.raises(PersistenceNotFoundError):
        repository.read_observation(NEVER_STARTED, 1)


def test_observation_list_of_a_run_never_started_is_not_found_and_of_an_empty_run_empty(
    repository: PostgresIngestionRepository,
) -> None:
    _start(repository)

    assert repository.list_observations(EXEC_1) == ()
    with pytest.raises(PersistenceNotFoundError):
        repository.list_observations(NEVER_STARTED)


@pytest.mark.parametrize("execution_id", ["../escape", "Synthetic-Exec", ""])
def test_observation_read_with_an_invalid_execution_id_is_a_value_error(
    repository: PostgresIngestionRepository, execution_id: str
) -> None:
    with pytest.raises(ValueError):
        repository.read_observation(execution_id, 1)
    with pytest.raises(ValueError):
        repository.list_observations(execution_id)


def test_observation_read_of_a_stored_row_that_fails_domain_validation_is_refused(
    repository: PostgresIngestionRepository,
    migrated_database: PostgresSettings,
    open_connection: OpenConnection,
) -> None:
    # Direct SQL stands for a row the adapter never wrote: the database accepts
    # headers that are an array, the domain wants pairs of text.
    _start(repository)
    connection = open_connection(migrated_database)
    connection.execute("INSERT INTO raw_evidence VALUES (%s, %s)", (ABC, 3))
    connection.execute(
        "INSERT INTO observation (execution_id, sequence, method, url, status, "
        "headers, captured_at, content_hash) VALUES (%s, 1, 'GET', %s, 200, "
        "%s::jsonb, %s, %s)",
        (EXEC_1, URL, f'[["{HEADER_MARKER}"]]', CAPTURED_AT, ABC),
    )

    with pytest.raises(PersistenceIntegrityError) as caught:
        repository.read_observation(EXEC_1, 1)

    assert HEADER_MARKER not in str(caught.value)


def test_observation_non_ascii_text_round_trips_in_url_headers_scope_and_detail(
    repository: PostgresIngestionRepository,
    migrated_database: PostgresSettings,
    open_connection: OpenConnection,
) -> None:
    scope = {
        "entidad": "Ministerio de Educación",
        "año": 2025,
        "nota": "contratación pública \U0001f4c4",
    }
    url = "https://source.invalid/búsqueda?año=2025&categoría=obras"
    headers = (
        ("Content-Type", "application/json"),
        ("X-Descripción", "Adquisición de equipos — ñandú"),
    )
    detail = {"descripción": "Página 1 — adquisición"}
    observation = make_observation(url=url, headers=headers)
    started = _start(repository, scope=scope)
    recorded = repository.record_observation(observation)
    event = repository.append_audit_event(
        execution_id=EXEC_1,
        occurred_at=STARTED_AT,
        event_type="synthetic-page-stored",
        detail=detail,
    )

    run = repository.read_run(EXEC_1)
    read = repository.read_observation(EXEC_1, 1)
    (listed,) = repository.list_audit_events(EXEC_1)

    assert run == started
    assert same_json(run.scope, scope)
    assert read == recorded
    assert read.url == url
    assert read.headers == headers
    assert listed == event
    assert same_json(listed.detail, detail)
    before = _counts(open_connection, migrated_database)
    assert _start(repository, scope=scope) == started
    assert repository.record_observation(observation) == recorded
    assert _counts(open_connection, migrated_database) == before


# --- AC9: audit events -------------------------------------------------------


def test_audit_event_append_assigns_increasing_ids_and_lists_in_order(
    repository: PostgresIngestionRepository,
) -> None:
    _start(repository)

    first = repository.append_audit_event(
        execution_id=EXEC_1,
        occurred_at=STARTED_AT,
        event_type="synthetic-run-started",
        detail={},
    )
    second = repository.append_audit_event(
        execution_id=EXEC_1,
        occurred_at=FINISHED_AT,
        event_type="synthetic-page-stored",
        detail={"page": 1},
    )

    assert second.event_id > first.event_id
    assert first.event_type == "synthetic-run-started"
    assert first.execution_id == EXEC_1
    assert first.occurred_at == STARTED_AT
    assert same_json(second.detail, {"page": 1})
    assert repository.list_audit_events(EXEC_1) == (first, second)


def test_audit_event_the_same_call_twice_appends_two_events(
    repository: PostgresIngestionRepository,
    migrated_database: PostgresSettings,
    open_connection: OpenConnection,
) -> None:
    _start(repository)

    first = repository.append_audit_event(
        execution_id=EXEC_1,
        occurred_at=STARTED_AT,
        event_type="synthetic-page-stored",
        detail={"page": 1},
    )
    second = repository.append_audit_event(
        execution_id=EXEC_1,
        occurred_at=STARTED_AT,
        event_type="synthetic-page-stored",
        detail={"page": 1},
    )

    assert second.event_id != first.event_id
    assert len(repository.list_audit_events(EXEC_1)) == 2
    assert _counts(open_connection, migrated_database)["audit_event"] == 2


def test_audit_event_detail_is_read_back_as_the_same_json_value(
    repository: PostgresIngestionRepository,
) -> None:
    _start(repository)
    repository.append_audit_event(
        execution_id=EXEC_1,
        occurred_at=STARTED_AT,
        event_type="synthetic-page-stored",
        detail={"page": True},
    )

    (event,) = repository.list_audit_events(EXEC_1)

    assert same_json(event.detail, {"page": True}) is True
    assert same_json(event.detail, {"page": 1}) is False
    assert isinstance(event, AuditEvent)


def test_audit_event_append_for_a_run_never_started_is_an_integrity_error(
    repository: PostgresIngestionRepository,
    migrated_database: PostgresSettings,
    open_connection: OpenConnection,
) -> None:
    with pytest.raises(PersistenceIntegrityError):
        repository.append_audit_event(
            execution_id=NEVER_STARTED,
            occurred_at=STARTED_AT,
            event_type="synthetic-run-started",
            detail={},
        )

    assert _counts(open_connection, migrated_database)["audit_event"] == 0


def test_audit_event_append_with_an_empty_type_is_a_value_error(
    repository: PostgresIngestionRepository,
    migrated_database: PostgresSettings,
    open_connection: OpenConnection,
) -> None:
    _start(repository)

    with pytest.raises(ValueError):
        repository.append_audit_event(
            execution_id=EXEC_1, occurred_at=STARTED_AT, event_type="", detail={}
        )

    assert _counts(open_connection, migrated_database)["audit_event"] == 0


def test_audit_event_list_of_an_unknown_run_is_not_found_and_of_a_quiet_run_empty(
    repository: PostgresIngestionRepository,
) -> None:
    _start(repository)

    assert repository.list_audit_events(EXEC_1) == ()
    with pytest.raises(PersistenceNotFoundError):
        repository.list_audit_events(NEVER_STARTED)


# --- AC10: invalid input -----------------------------------------------------


def _start_with(**changes: Any) -> Callable[[PostgresIngestionRepository], object]:
    fields: dict[str, Any] = {
        "execution_id": EXEC_2,
        "scope": SCOPE,
        "started_at": STARTED_AT,
    }
    fields.update(changes)
    return lambda repository: repository.start_run(**fields)


def _finish_with(**changes: Any) -> Callable[[PostgresIngestionRepository], object]:
    fields: dict[str, Any] = {
        "execution_id": EXEC_1,
        "status": RunStatus.SUCCEEDED,
        "finished_at": FINISHED_AT,
    }
    fields.update(changes)
    return lambda repository: repository.finish_run(**fields)


def _record(
    observation: Observation,
) -> Callable[[PostgresIngestionRepository], object]:
    return lambda repository: repository.record_observation(observation)


def _append_with(**changes: Any) -> Callable[[PostgresIngestionRepository], object]:
    fields: dict[str, Any] = {
        "execution_id": EXEC_1,
        "occurred_at": STARTED_AT,
        "event_type": "synthetic-page-stored",
        "detail": {},
    }
    fields.update(changes)
    return lambda repository: repository.append_audit_event(**fields)


INVALID_CASES = [
    pytest.param(_start_with(scope={"year": 2025.0}), id="start-float"),
    pytest.param(_start_with(scope={"year": float("nan")}), id="start-nan"),
    pytest.param(_start_with(scope={1: "x"}), id="start-int-key"),
    pytest.param(_start_with(scope={"pages": (1, 2)}), id="start-tuple"),
    pytest.param(_start_with(scope={"pages": {1, 2}}), id="start-set"),
    pytest.param(_start_with(scope={"k": f"{NUL_MARKER}\x00"}), id="start-nul-value"),
    pytest.param(_start_with(scope={f"{NUL_MARKER}\x00": "v"}), id="start-nul-key"),
    pytest.param(_start_with(scope={"k": f"{NUL_MARKER}\ud800"}), id="start-surrogate"),
    pytest.param(
        _start_with(scope={"a": [{"b": f"{NUL_MARKER}\x00"}]}), id="start-nested-nul"
    ),
    pytest.param(
        _start_with(started_at=datetime(2026, 10, 9, 10, 15)), id="start-naive"
    ),
    pytest.param(_start_with(execution_id="Synthetic-Exec"), id="start-bad-id"),
    pytest.param(
        _finish_with(finished_at=STARTED_AT - timedelta(seconds=1)),
        id="finish-before-start",
    ),
    pytest.param(
        _finish_with(finished_at=datetime(2026, 10, 9, 10, 16)), id="finish-naive"
    ),
    pytest.param(
        _record(make_observation(url=f"https://source.invalid/{NUL_MARKER}\x00")),
        id="record-nul-url",
    ),
    pytest.param(
        _record(make_observation(headers=(("X-A", f"{NUL_MARKER}\ud800"),))),
        id="record-surrogate-header-value",
    ),
    pytest.param(
        _record(make_observation(headers=((f"X-{NUL_MARKER}\x00", "1"),))),
        id="record-nul-header-name",
    ),
    pytest.param(
        _record(make_observation(method=f"{NUL_MARKER}\x00")), id="record-nul-method"
    ),
    pytest.param(_record(make_observation(sequence=2**31)), id="record-sequence"),
    pytest.param(_record(make_observation(size=2**63)), id="record-size-above-bigint"),
    pytest.param(
        _append_with(detail={"note": f"a{NUL_MARKER}\x00b"}), id="append-nul-detail"
    ),
    pytest.param(_append_with(event_type=f"{NUL_MARKER}\x00"), id="append-nul-type"),
    pytest.param(_append_with(detail={"page": 1.0}), id="append-float"),
    pytest.param(_append_with(detail={"pages": {1, 2}}), id="append-set"),
    pytest.param(_append_with(event_type=""), id="append-empty-type"),
    pytest.param(
        _append_with(occurred_at=datetime(2026, 10, 9, 10, 15)), id="append-naive"
    ),
    pytest.param(_append_with(execution_id="-x"), id="append-bad-id"),
]


@pytest.mark.parametrize("call", INVALID_CASES)
def test_invalid_input_is_a_value_error_and_writes_nothing(
    repository: PostgresIngestionRepository,
    migrated_database: PostgresSettings,
    open_connection: OpenConnection,
    call: Callable[[PostgresIngestionRepository], object],
) -> None:
    _start(repository, EXEC_1)
    before = _counts(open_connection, migrated_database)

    with pytest.raises(ValueError) as caught:
        call(repository)

    assert NUL_MARKER not in str(caught.value)
    assert _counts(open_connection, migrated_database) == before


@pytest.mark.parametrize(
    ("field", "call"),
    [
        pytest.param("scope", _start_with(scope={"n": 10**5000}), id="scope"),
        pytest.param("detail", _append_with(detail={"n": 10**5000}), id="detail"),
    ],
)
def test_invalid_json_integer_too_long_to_write_is_a_value_error_naming_the_field(
    repository: PostgresIngestionRepository,
    migrated_database: PostgresSettings,
    open_connection: OpenConnection,
    field: str,
    call: Callable[[PostgresIngestionRepository], object],
) -> None:
    _start(repository, EXEC_1)
    before = _counts(open_connection, migrated_database)

    with pytest.raises(ValueError) as caught:
        call(repository)

    error = caught.value
    assert field in str(error)
    assert re.search(r"10{20}", str(error)) is None
    assert error.__cause__ is None
    assert error.__context__ is None
    assert _counts(open_connection, migrated_database) == before


# --- AC11: connections -------------------------------------------------------


def _terminate_backends(admin: Any, dbname: str) -> None:
    """Terminate every session on `dbname` and wait until none is left."""
    deadline = time.monotonic() + 10
    while True:
        admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
            (dbname,),
        )
        row = admin.execute(
            "SELECT count(*) FROM pg_stat_activity WHERE datname = %s", (dbname,)
        ).fetchone()
        if row[0] == 0:
            return
        if time.monotonic() > deadline:
            pytest.fail("the sessions of the throwaway database did not end")
        time.sleep(0.05)


def _wait_for_lock_waiter(admin: Any, dbname: str, locker_pid: int) -> int:
    """The pid of a backend on `dbname`, other than the locker, waiting on a lock."""
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        row = admin.execute(
            "SELECT pid FROM pg_stat_activity WHERE datname = %s AND pid <> %s "
            "AND wait_event_type = 'Lock'",
            (dbname, locker_pid),
        ).fetchone()
        if row is not None:
            return int(row[0])
        time.sleep(0.05)
    pytest.fail("no backend waited on the lock within 10 seconds")


def test_connection_to_a_closed_port_is_a_connection_error(
    empty_database: PostgresSettings,
) -> None:
    settings = _with(empty_database, host="127.0.0.1", port=_closed_port())

    with pytest.raises(PersistenceConnectionError):
        PostgresIngestionRepository(settings)


def test_connection_with_a_wrong_password_is_a_connection_error(
    migrated_database: PostgresSettings,
) -> None:
    settings = _with(migrated_database, password="synthetic-wrong-password")

    with pytest.raises(PersistenceConnectionError):
        PostgresIngestionRepository(settings)


def test_connection_failures_of_the_runner_are_connection_errors_not_migration_errors(
    tmp_path: Path, empty_database: PostgresSettings
) -> None:
    (tmp_path / "0001_a.sql").write_bytes(b"CREATE TABLE synthetic_a (id integer);\n")

    with pytest.raises(PersistenceConnectionError):
        apply_migrations(
            _with(empty_database, host="127.0.0.1", port=_closed_port()), tmp_path
        )
    with pytest.raises(PersistenceConnectionError):
        apply_migrations(
            _with(empty_database, password="synthetic-wrong-password"), tmp_path
        )


def test_connection_terminated_before_a_call_is_a_connection_error_and_writes_nothing(
    repository: PostgresIngestionRepository,
    migrated_database: PostgresSettings,
    admin_connection: Any,
    open_connection: OpenConnection,
) -> None:
    _start(repository)
    _terminate_backends(admin_connection, migrated_database.dbname)

    with pytest.raises(PersistenceConnectionError):
        repository.record_observation(OBSERVATION)
    with pytest.raises(PersistenceConnectionError):
        repository.read_run(EXEC_1)
    with pytest.raises(PersistenceConnectionError):
        repository.read_run(EXEC_1)

    counts = _counts(open_connection, migrated_database)
    assert counts["raw_evidence"] == 0
    assert counts["observation"] == 0


def test_connection_lost_while_the_transaction_waits_on_a_lock_leaves_nothing(
    repository: PostgresIngestionRepository,
    migrated_database: PostgresSettings,
    admin_connection: Any,
    open_connection: OpenConnection,
) -> None:
    _start(repository)
    locker = open_connection(migrated_database, autocommit=False)
    locker_pid = int(locker.execute("SELECT pg_backend_pid()").fetchone()[0])
    locker.execute("LOCK TABLE observation IN ACCESS EXCLUSIVE MODE")
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        # The adapter is still used by one thread at a time: only the worker
        # touches it until its future is done.
        future = pool.submit(repository.record_observation, OBSERVATION)
        waiter = _wait_for_lock_waiter(
            admin_connection, migrated_database.dbname, locker_pid
        )
        admin_connection.execute("SELECT pg_terminate_backend(%s)", (waiter,))
        locker.rollback()

        with pytest.raises(PersistenceConnectionError):
            future.result(timeout=10)
    finally:
        locker.rollback()
        pool.shutdown(wait=True, cancel_futures=True)

    counts = _counts(open_connection, migrated_database)
    assert counts["raw_evidence"] == 0
    assert counts["observation"] == 0


@pytest.mark.parametrize(
    "operation",
    [
        pytest.param(lambda r: r.read_run(EXEC_1), id="read-run"),
        pytest.param(lambda r: _start(r), id="start-run"),
        pytest.param(lambda r: r.record_observation(OBSERVATION), id="record"),
        pytest.param(lambda r: r.list_observations(EXEC_1), id="list-observations"),
        pytest.param(lambda r: r.list_audit_events(EXEC_1), id="list-events"),
    ],
)
def test_connection_closed_adapter_raises_runtime_error(
    migrated_database: PostgresSettings,
    operation: Callable[[PostgresIngestionRepository], object],
) -> None:
    adapter = PostgresIngestionRepository(migrated_database)
    adapter.close()

    with pytest.raises(RuntimeError):
        operation(adapter)


def test_connection_context_manager_closes_the_adapter(
    migrated_database: PostgresSettings,
) -> None:
    adapter = PostgresIngestionRepository(migrated_database)

    with adapter:
        _start(adapter)

    with pytest.raises(RuntimeError):
        adapter.read_run(EXEC_1)


# --- AC12: nothing leaks -----------------------------------------------------


def _texts(error: BaseException, *, with_traceback: bool = True) -> list[str]:
    texts = [str(error), repr(error), " ".join(str(arg) for arg in error.args)]
    if with_traceback:
        texts.append("".join(traceback.format_exception(error)))
    return texts


def _assert_no_driver_exception_is_reachable(error: BaseException) -> None:
    assert error.__cause__ is None
    seen: BaseException | None = error.__context__
    while seen is not None:
        assert not isinstance(seen, psycopg.Error)
        seen = seen.__context__


def test_leak_connection_error_holds_no_secret_and_no_setting(
    empty_database: PostgresSettings,
) -> None:
    port = _closed_port()
    settings = _with(
        empty_database, host="127.0.0.1", port=port, password=PASSWORD_MARKER
    )

    with pytest.raises(PersistenceConnectionError) as caught:
        PostgresIngestionRepository(settings)

    error = caught.value
    assert [t for t in _texts(error) if PASSWORD_MARKER in t] == []
    # Settings that name the database and the host (the user name is checked in
    # the message only: a short user name could occur in module paths).
    leaked = [
        name
        for name, value in (
            ("dbname", settings.dbname),
            ("host", settings.host),
            ("port", str(port)),
        )
        if any(value in text for text in _texts(error))
    ]
    assert leaked == []
    user_leaked = any(settings.user in t for t in _texts(error, with_traceback=False))
    assert user_leaked is False
    _assert_no_driver_exception_is_reachable(error)


def test_leak_wrong_password_error_holds_neither_password(
    migrated_database: PostgresSettings,
) -> None:
    settings = _with(migrated_database, password=PASSWORD_MARKER)

    with pytest.raises(PersistenceConnectionError) as caught:
        PostgresIngestionRepository(settings)

    assert [t for t in _texts(caught.value) if PASSWORD_MARKER in t] == []
    _assert_no_driver_exception_is_reachable(caught.value)


def test_leak_integrity_conflict_names_the_identity_and_no_stored_value(
    repository: PostgresIngestionRepository,
) -> None:
    stored_url = f"https://source.invalid/{URL_MARKER}"
    stored_headers = (("X-Marker", HEADER_MARKER),)
    other_scope = {"note": OTHER_SCOPE_MARKER}
    _start(repository, scope={"note": SCOPE_MARKER})
    repository.record_observation(
        make_observation(sequence=7, url=stored_url, headers=stored_headers)
    )

    with pytest.raises(PersistenceIntegrityError) as caught:
        repository.record_observation(
            make_observation(
                sequence=7, url=stored_url, headers=stored_headers, status=500
            )
        )
    with pytest.raises(PersistenceIntegrityError) as caught_run:
        _start(repository, scope=other_scope)

    message = str(caught.value)
    assert EXEC_1 in message
    assert "7" in message
    for error in (caught.value, caught_run.value):
        for marker in (URL_MARKER, HEADER_MARKER, SCOPE_MARKER, OTHER_SCOPE_MARKER):
            assert [t for t in _texts(error) if marker in t] == []
        _assert_no_driver_exception_is_reachable(error)


def test_leak_migration_failure_names_the_file_and_no_server_text(
    tmp_path: Path, empty_database: PostgresSettings
) -> None:
    failing_sql = f"SELECT '{SQL_MARKER}'::integer;\n"
    (tmp_path / "0001_a.sql").write_text(failing_sql, encoding="utf-8")

    with pytest.raises(MigrationError) as caught:
        apply_migrations(empty_database, tmp_path)

    assert "0001_a.sql" in str(caught.value)
    assert [t for t in _texts(caught.value) if SQL_MARKER in t] == []
    password_leaked = any(empty_database.password in t for t in _texts(caught.value))
    assert password_leaked is False
    _assert_no_driver_exception_is_reachable(caught.value)


def test_leak_adapter_and_runner_write_no_log_records(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    repository: PostgresIngestionRepository,
    empty_database: PostgresSettings,
) -> None:
    caplog.set_level(logging.DEBUG)
    (tmp_path / "0001_a.sql").write_text("SELECT 1/0;\n", encoding="utf-8")

    _start(repository)
    repository.record_observation(OBSERVATION)
    with pytest.raises(PersistenceIntegrityError):
        repository.record_observation(make_observation(status=500))
    with pytest.raises(PersistenceNotFoundError):
        repository.read_run(NEVER_STARTED)
    with pytest.raises(MigrationError):
        apply_migrations(empty_database, tmp_path)

    own = [
        record
        for record in caplog.records
        if record.name.startswith("ec_procurement_quality")
    ]
    assert own == []


# --- AC13: the port ----------------------------------------------------------


def test_satisfies_port_the_adapter_is_usable_as_the_port(
    migrated_database: PostgresSettings,
) -> None:
    adapter = PostgresIngestionRepository(migrated_database)
    repository: IngestionRepository = adapter
    try:
        started = repository.start_run(
            execution_id=EXEC_1, scope=SCOPE, started_at=STARTED_AT
        )
        recorded = repository.record_observation(make_observation(execution_id=EXEC_1))
        event = repository.append_audit_event(
            execution_id=EXEC_1,
            occurred_at=STARTED_AT,
            event_type="synthetic-run-started",
            detail={},
        )

        assert repository.read_run(EXEC_1) == started
        assert repository.read_observation(EXEC_1, 1) == recorded
        assert repository.list_observations(EXEC_1) == (recorded,)
        assert repository.list_audit_events(EXEC_1) == (event,)
    finally:
        adapter.close()
