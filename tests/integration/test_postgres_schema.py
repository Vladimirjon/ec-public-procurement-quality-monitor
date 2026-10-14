"""Feature postgres-persistence (F3), outcome O5 (AC5, AC6): the schema of
`migrations/0001_initial_schema.sql`, through direct SQL.

Every test runs in its own throwaway database copied from the session's
migrated template (`migrated_database`), so the schema under test is exactly
what `migrations/0001_initial_schema.sql` creates. If that file does not exist
the template cannot be built and every test here is reported as an error that
names it.

The rules are the database's, so the tests bypass the adapter on purpose: each
bad row must be refused even when written with plain SQL. "Rejected" means the
statement fails and the table is unchanged. Names to focus on, by `-k`:
`schema_rejects`, `append_only`, `run_transition`. Data is synthetic and URLs
use `.invalid`.

This file imports no F3 module at run time: it needs only the database.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import psycopg
import pytest

if TYPE_CHECKING:
    from ec_procurement_quality.infrastructure.postgres_settings import (
        PostgresSettings,
    )

pytestmark = pytest.mark.integration

OpenConnection = Callable[..., Any]

ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
EMPTY = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
URL = "https://source.invalid/api/search?year=2025&page=1"
HEADERS = '[["Content-Type", "application/json"], ["X-A", "1"], ["X-A", "2"]]'
STARTED = datetime(2026, 10, 9, 15, 15, tzinfo=UTC)
FINISHED = STARTED + timedelta(seconds=42)
SEEDED_RUN = "synthetic-exec-001"
_TABLES = ("ingestion_run", "raw_evidence", "observation", "audit_event")

RUN_SQL = (
    "INSERT INTO ingestion_run (execution_id, scope, started_at, finished_at, status) "
    "VALUES (%s, %s::jsonb, %s, %s, %s)"
)
EVIDENCE_SQL = "INSERT INTO raw_evidence (content_hash, size) VALUES (%s, %s)"
OBSERVATION_SQL = (
    "INSERT INTO observation (execution_id, sequence, method, url, status, "
    "headers, captured_at, content_hash) "
    "VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s)"
)
EVENT_SQL = (
    "INSERT INTO audit_event (execution_id, occurred_at, event_type, detail) "
    "VALUES (%s, %s, %s, %s::jsonb)"
)
EVENT_WITHOUT_DETAIL_SQL = (
    "INSERT INTO audit_event (execution_id, occurred_at, event_type) "
    "VALUES (%s, %s, %s)"
)
EVENT_WITH_ID_SQL = (
    "INSERT INTO audit_event (event_id, execution_id, occurred_at, event_type, "
    "detail) VALUES (%s, %s, %s, %s, %s::jsonb)"
)


def _run(**changes: Any) -> tuple[Any, ...]:
    fields: dict[str, Any] = {
        "execution_id": "synthetic-exec-002",
        "scope": "{}",
        "started_at": STARTED,
        "finished_at": None,
        "status": "running",
    }
    fields.update(changes)
    return tuple(fields.values())


def _observation(**changes: Any) -> tuple[Any, ...]:
    fields: dict[str, Any] = {
        "execution_id": SEEDED_RUN,
        "sequence": 2,
        "method": "GET",
        "url": URL,
        "status": 200,
        "headers": HEADERS,
        "captured_at": STARTED,
        "content_hash": ABC,
    }
    fields.update(changes)
    return tuple(fields.values())


def _event(**changes: Any) -> tuple[Any, ...]:
    fields: dict[str, Any] = {
        "execution_id": SEEDED_RUN,
        "occurred_at": STARTED,
        "event_type": "synthetic-page-stored",
        "detail": "{}",
    }
    fields.update(changes)
    return tuple(fields.values())


def _seed(connection: Any) -> None:
    """One valid row in each table, so duplicates and references can be tried."""
    connection.execute(RUN_SQL, (SEEDED_RUN, "{}", STARTED, None, "running"))
    connection.execute(EVIDENCE_SQL, (ABC, 3))
    connection.execute(
        OBSERVATION_SQL,
        (SEEDED_RUN, 1, "GET", URL, 200, HEADERS, STARTED, ABC),
    )
    connection.execute(EVENT_SQL, (SEEDED_RUN, STARTED, "synthetic-run-started", "{}"))


def _count(connection: Any, table: str) -> int:
    return int(connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0])


def _rows(connection: Any, table: str) -> list[tuple[Any, ...]]:
    return connection.execute(f"SELECT * FROM {table} ORDER BY 1, 2").fetchall()


def _sqlstate(error: pytest.ExceptionInfo[psycopg.Error]) -> str:
    return error.value.sqlstate or ""


# --- AC5 --------------------------------------------------------------------


def test_schema_accepts_valid_base_rows(
    migrated_database: PostgresSettings, open_connection: OpenConnection
) -> None:
    connection = open_connection(migrated_database)

    _seed(connection)
    connection.execute(RUN_SQL, _run(status="succeeded", finished_at=FINISHED))
    connection.execute(
        RUN_SQL, _run(execution_id="a", status="failed", finished_at=STARTED)
    )
    connection.execute(OBSERVATION_SQL, _observation())
    connection.execute(EVENT_SQL, _event(detail='{"page": 1}'))

    assert _count(connection, "ingestion_run") == 3
    assert _count(connection, "raw_evidence") == 1
    assert _count(connection, "observation") == 2
    assert _count(connection, "audit_event") == 2


@pytest.mark.parametrize(
    ("table", "statement", "params", "expected"),
    [
        # ingestion_run
        pytest.param(
            "ingestion_run",
            RUN_SQL,
            _run(execution_id="Synthetic-Exec"),
            "23",
            id="run-uppercase-id",
        ),
        pytest.param(
            "ingestion_run",
            RUN_SQL,
            _run(execution_id="-x"),
            "23",
            id="run-leading-dash-id",
        ),
        pytest.param(
            "ingestion_run", RUN_SQL, _run(execution_id=""), "23", id="run-empty-id"
        ),
        pytest.param(
            "ingestion_run",
            RUN_SQL,
            _run(execution_id="a" * 65),
            "23",
            id="run-long-id",
        ),
        pytest.param(
            "ingestion_run",
            RUN_SQL,
            _run(execution_id="synthetic-exec-002\n"),
            "23",
            id="run-trailing-newline-id",
        ),
        pytest.param(
            "ingestion_run", RUN_SQL, _run(status="paused"), "23", id="run-bad-status"
        ),
        pytest.param(
            "ingestion_run",
            RUN_SQL,
            _run(finished_at=FINISHED),
            "23",
            id="run-running-with-finish",
        ),
        pytest.param(
            "ingestion_run",
            RUN_SQL,
            _run(status="failed"),
            "23",
            id="run-failed-without-finish",
        ),
        pytest.param(
            "ingestion_run",
            RUN_SQL,
            _run(status="succeeded", finished_at=STARTED - timedelta(seconds=1)),
            "23",
            id="run-finished-before-started",
        ),
        pytest.param(
            "ingestion_run", RUN_SQL, _run(scope="[]"), "23", id="run-array-scope"
        ),
        pytest.param(
            "ingestion_run", RUN_SQL, _run(scope="null"), "23", id="run-null-scope"
        ),
        pytest.param(
            "ingestion_run",
            RUN_SQL,
            _run(execution_id=SEEDED_RUN),
            "23505",
            id="run-duplicate-key",
        ),
        # raw_evidence
        pytest.param(
            "raw_evidence", EVIDENCE_SQL, (ABC[:63], 3), "23", id="evidence-short-hash"
        ),
        pytest.param(
            "raw_evidence",
            EVIDENCE_SQL,
            (ABC.upper(), 3),
            "23",
            id="evidence-uppercase-hash",
        ),
        pytest.param(
            "raw_evidence",
            EVIDENCE_SQL,
            (ABC[:63] + "\n", 3),
            "23",
            id="evidence-trailing-newline-hash",
        ),
        pytest.param(
            "raw_evidence", EVIDENCE_SQL, (EMPTY, -1), "23", id="evidence-negative-size"
        ),
        pytest.param(
            "raw_evidence", EVIDENCE_SQL, (ABC, 3), "23505", id="evidence-duplicate-key"
        ),
        # observation
        pytest.param(
            "observation",
            OBSERVATION_SQL,
            _observation(sequence=-1),
            "23",
            id="observation-negative-sequence",
        ),
        pytest.param(
            "observation",
            OBSERVATION_SQL,
            _observation(method=""),
            "23",
            id="observation-empty-method",
        ),
        pytest.param(
            "observation",
            OBSERVATION_SQL,
            _observation(url=""),
            "23",
            id="observation-empty-url",
        ),
        pytest.param(
            "observation",
            OBSERVATION_SQL,
            _observation(status=99),
            "23",
            id="observation-status-99",
        ),
        pytest.param(
            "observation",
            OBSERVATION_SQL,
            _observation(status=600),
            "23",
            id="observation-status-600",
        ),
        pytest.param(
            "observation",
            OBSERVATION_SQL,
            _observation(execution_id="synthetic-missing"),
            "23503",
            id="observation-unknown-run",
        ),
        pytest.param(
            "observation",
            OBSERVATION_SQL,
            _observation(content_hash=EMPTY),
            "23503",
            id="observation-unknown-content",
        ),
        pytest.param(
            "observation",
            OBSERVATION_SQL,
            _observation(headers="{}"),
            "23",
            id="observation-object-headers",
        ),
        pytest.param(
            "observation",
            OBSERVATION_SQL,
            _observation(headers="null"),
            "23",
            id="observation-null-headers",
        ),
        pytest.param(
            "observation",
            OBSERVATION_SQL,
            _observation(headers='[["SET-COOKIE", "s=1"]]'),
            "23",
            id="observation-set-cookie-upper",
        ),
        pytest.param(
            "observation",
            OBSERVATION_SQL,
            _observation(headers='[["Set-Cookie", "s=1"]]'),
            "23",
            id="observation-set-cookie-mixed",
        ),
        pytest.param(
            "observation",
            OBSERVATION_SQL,
            _observation(headers='[["X-A", "1"], ["set-cookie", "s=1"]]'),
            "23",
            id="observation-set-cookie-second",
        ),
        pytest.param(
            "observation",
            OBSERVATION_SQL,
            _observation(sequence=1),
            "23505",
            id="observation-duplicate-key",
        ),
        # audit_event
        pytest.param(
            "audit_event",
            EVENT_SQL,
            _event(event_type=""),
            "23",
            id="event-empty-type",
        ),
        pytest.param(
            "audit_event",
            EVENT_SQL,
            _event(execution_id="synthetic-missing"),
            "23503",
            id="event-unknown-run",
        ),
        pytest.param(
            "audit_event", EVENT_SQL, _event(detail="[]"), "23", id="event-array-detail"
        ),
        pytest.param(
            "audit_event",
            EVENT_SQL,
            _event(detail="null"),
            "23",
            id="event-null-detail",
        ),
        pytest.param(
            "audit_event",
            EVENT_WITH_ID_SQL,
            (7, *_event()),
            "428C9",
            id="event-explicit-id",
        ),
    ],
)
def test_schema_rejects_invalid_row(
    migrated_database: PostgresSettings,
    open_connection: OpenConnection,
    table: str,
    statement: str,
    params: tuple[Any, ...],
    expected: str,
) -> None:
    connection = open_connection(migrated_database)
    _seed(connection)
    before = _rows(connection, table)

    with pytest.raises(psycopg.Error) as caught:
        connection.execute(statement, params)

    assert _sqlstate(caught).startswith(expected)
    assert _rows(connection, table) == before


def test_schema_defaults_a_missing_detail_to_an_empty_object(
    migrated_database: PostgresSettings, open_connection: OpenConnection
) -> None:
    connection = open_connection(migrated_database)
    _seed(connection)

    connection.execute(
        EVENT_WITHOUT_DETAIL_SQL, (SEEDED_RUN, STARTED, "synthetic-page-stored")
    )

    row = connection.execute(
        "SELECT detail FROM audit_event WHERE event_type = %s",
        ("synthetic-page-stored",),
    ).fetchone()
    assert row == ({},)


def test_schema_assigns_increasing_event_ids(
    migrated_database: PostgresSettings, open_connection: OpenConnection
) -> None:
    connection = open_connection(migrated_database)
    _seed(connection)

    first = connection.execute(EVENT_SQL + " RETURNING event_id", _event()).fetchone()
    second = connection.execute(EVENT_SQL + " RETURNING event_id", _event()).fetchone()

    assert first is not None and second is not None
    assert second[0] > first[0]


# --- AC6 --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("table", "statement"),
    [
        pytest.param(
            "raw_evidence",
            "UPDATE raw_evidence SET size = size + 1",
            id="evidence-update",
        ),
        pytest.param("raw_evidence", "DELETE FROM raw_evidence", id="evidence-delete"),
        pytest.param(
            "raw_evidence", "TRUNCATE raw_evidence CASCADE", id="evidence-truncate"
        ),
        pytest.param(
            "observation",
            "UPDATE observation SET status = 201",
            id="observation-update",
        ),
        pytest.param("observation", "DELETE FROM observation", id="observation-delete"),
        pytest.param("observation", "TRUNCATE observation", id="observation-truncate"),
        pytest.param(
            "audit_event",
            "UPDATE audit_event SET event_type = 'synthetic-changed'",
            id="event-update",
        ),
        pytest.param("audit_event", "DELETE FROM audit_event", id="event-delete"),
        pytest.param("audit_event", "TRUNCATE audit_event", id="event-truncate"),
        pytest.param("ingestion_run", "DELETE FROM ingestion_run", id="run-delete"),
        pytest.param(
            "ingestion_run", "TRUNCATE ingestion_run CASCADE", id="run-truncate-cascade"
        ),
    ],
)
def test_append_only_statement_is_refused_with_integrity_violation(
    migrated_database: PostgresSettings,
    open_connection: OpenConnection,
    table: str,
    statement: str,
) -> None:
    assert table in _TABLES
    connection = open_connection(migrated_database)
    _seed(connection)
    before = {name: _rows(connection, name) for name in _TABLES}

    with pytest.raises(psycopg.Error) as caught:
        connection.execute(statement)

    assert _sqlstate(caught) == "23000"
    assert {name: _rows(connection, name) for name in _TABLES} == before


@pytest.mark.parametrize("table", ["raw_evidence", "ingestion_run"])
def test_append_only_plain_truncate_of_a_referenced_table_is_refused(
    migrated_database: PostgresSettings,
    open_connection: OpenConnection,
    table: str,
) -> None:
    # PostgreSQL itself refuses a plain TRUNCATE of a table another table
    # references (SQLSTATE 0A000) before any trigger runs; either way the
    # statement fails and no row changes.
    connection = open_connection(migrated_database)
    _seed(connection)
    before = {name: _rows(connection, name) for name in _TABLES}

    with pytest.raises(psycopg.Error) as caught:
        connection.execute(f"TRUNCATE {table}")

    assert _sqlstate(caught) in {"23000", "0A000"}
    assert {name: _rows(connection, name) for name in _TABLES} == before


@pytest.mark.parametrize("final_status", ["succeeded", "failed"])
def test_run_transition_running_to_a_final_status_is_accepted(
    migrated_database: PostgresSettings,
    open_connection: OpenConnection,
    final_status: str,
) -> None:
    connection = open_connection(migrated_database)
    _seed(connection)

    connection.execute(
        "UPDATE ingestion_run SET status = %s, finished_at = %s "
        "WHERE execution_id = %s",
        (final_status, FINISHED, SEEDED_RUN),
    )

    row = connection.execute(
        "SELECT status, finished_at FROM ingestion_run WHERE execution_id = %s",
        (SEEDED_RUN,),
    ).fetchone()
    assert row == (final_status, FINISHED)


@pytest.mark.parametrize(
    ("statement", "params"),
    [
        pytest.param(
            "UPDATE ingestion_run SET status = 'failed'", (), id="to-another-status"
        ),
        pytest.param(
            "UPDATE ingestion_run SET status = 'running', finished_at = NULL",
            (),
            id="back-to-running",
        ),
        pytest.param(
            "UPDATE ingestion_run SET finished_at = %s",
            (FINISHED + timedelta(seconds=1),),
            id="new-finished-at",
        ),
        pytest.param(
            "UPDATE ingestion_run SET scope = '{\"x\": 1}'::jsonb", (), id="new-scope"
        ),
        pytest.param(
            "UPDATE ingestion_run SET started_at = %s",
            (STARTED - timedelta(seconds=1),),
            id="new-started-at",
        ),
    ],
)
def test_run_transition_after_the_first_change_nothing_may_change(
    migrated_database: PostgresSettings,
    open_connection: OpenConnection,
    statement: str,
    params: tuple[Any, ...],
) -> None:
    connection = open_connection(migrated_database)
    _seed(connection)
    connection.execute(
        "UPDATE ingestion_run SET status = 'succeeded', finished_at = %s",
        (FINISHED,),
    )
    before = _rows(connection, "ingestion_run")

    with pytest.raises(psycopg.Error) as caught:
        connection.execute(statement, params)

    assert _sqlstate(caught) == "23000"
    assert _rows(connection, "ingestion_run") == before


@pytest.mark.parametrize(
    ("statement", "params"),
    [
        pytest.param(
            "UPDATE ingestion_run SET execution_id = 'synthetic-exec-009'",
            (),
            id="execution-id",
        ),
        pytest.param(
            "UPDATE ingestion_run SET scope = '{\"x\": 1}'::jsonb", (), id="scope"
        ),
        pytest.param(
            "UPDATE ingestion_run SET started_at = %s",
            (STARTED + timedelta(seconds=1),),
            id="started-at",
        ),
    ],
)
def test_run_transition_identity_scope_and_start_of_a_running_run_are_fixed(
    migrated_database: PostgresSettings,
    open_connection: OpenConnection,
    statement: str,
    params: tuple[Any, ...],
) -> None:
    connection = open_connection(migrated_database)
    _seed(connection)
    before = _rows(connection, "ingestion_run")

    with pytest.raises(psycopg.Error) as caught:
        connection.execute(statement, params)

    assert _sqlstate(caught) == "23000"
    assert _rows(connection, "ingestion_run") == before


def test_run_transition_to_a_final_status_needs_a_finish_time(
    migrated_database: PostgresSettings, open_connection: OpenConnection
) -> None:
    connection = open_connection(migrated_database)
    _seed(connection)
    before = _rows(connection, "ingestion_run")

    with pytest.raises(psycopg.Error) as caught:
        connection.execute("UPDATE ingestion_run SET status = 'succeeded'")

    assert _sqlstate(caught).startswith("23")
    assert _rows(connection, "ingestion_run") == before
