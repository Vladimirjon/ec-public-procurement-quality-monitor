"""Feature ingest-command (F4), outcome O2 (AC23, AC19): the F3 extension, against
a real PostgreSQL. The listing of runs by status and the ingest exclusion.

Every test runs in its own throwaway database copied from the session's migrated
template (`migrated_database`). Names to focus on, by `-k`: `list_runs`,
`exclusion`, `network_guard`. Data is synthetic.

`INGEST_EXCLUSION_KEY` and `MIGRATION_LOCK_KEY` are imported inside the tests
(through `_keys`), so the file collects while the constant does not exist yet and
the red reason is the missing member, never a collection error. A test connection
holds or probes a key from outside; the repository's own connection holds its
exclusion until `close()` or the end of its session.
"""

import socket
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

import httpx
import pytest

from ec_procurement_quality.domain.ingestion_audit import IngestionRun, RunStatus
from ec_procurement_quality.domain.persistence_errors import (
    PersistenceConnectionError,
)
from ec_procurement_quality.infrastructure.postgres_ingestion_repository import (
    PostgresIngestionRepository,
)
from ec_procurement_quality.infrastructure.postgres_migrations import apply_migrations
from ec_procurement_quality.infrastructure.postgres_settings import PostgresSettings

pytestmark = pytest.mark.integration


class NetworkGuard(Protocol):
    """The shape of the `network_guard` fixture of this directory's conftest."""

    allowed_host: str
    attempts: list[str]


OpenConnection = Callable[..., Any]
MakeRepository = Callable[[], PostgresIngestionRepository]

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"
SCOPE: dict[str, Any] = {"source": "synthetic", "year": 2025}
T0 = datetime(2026, 10, 9, 10, 15, tzinfo=UTC)
TABLES = ("ingestion_run", "raw_evidence", "observation", "audit_event")


def _keys() -> tuple[int, int]:
    """The ingest exclusion key and the migration lock key (imported lazily)."""
    from ec_procurement_quality.infrastructure.postgres_ingestion_repository import (
        INGEST_EXCLUSION_KEY,
    )
    from ec_procurement_quality.infrastructure.postgres_migrations import (
        MIGRATION_LOCK_KEY,
    )

    return INGEST_EXCLUSION_KEY, MIGRATION_LOCK_KEY


@pytest.fixture
def make_repository(
    migrated_database: PostgresSettings,
) -> Iterator[MakeRepository]:
    """Build repositories on the test's database; close them all at the end."""
    made: list[PostgresIngestionRepository] = []

    def make() -> PostgresIngestionRepository:
        repository = PostgresIngestionRepository(migrated_database)
        made.append(repository)
        return repository

    try:
        yield make
    finally:
        for repository in made:
            repository.close()


def _start(
    repository: PostgresIngestionRepository,
    execution_id: str,
    started_at: datetime = T0,
) -> IngestionRun:
    return repository.start_run(
        execution_id=execution_id, scope=SCOPE, started_at=started_at
    )


def _fail(
    repository: PostgresIngestionRepository, execution_id: str, finished_at: datetime
) -> IngestionRun:
    return repository.finish_run(
        execution_id=execution_id, status=RunStatus.FAILED, finished_at=finished_at
    )


def _counts(
    open_connection: OpenConnection, settings: PostgresSettings
) -> dict[str, int]:
    """Row counts per table, from a fresh connection."""
    connection = open_connection(settings)
    return {
        table: int(connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
        for table in TABLES
    }


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


def _holders_of(admin: Any, dbname: str, key: int) -> list[int]:
    """The pids of the sessions that hold the advisory lock `key` in `dbname`."""
    rows = admin.execute(
        "SELECT l.pid FROM pg_locks l JOIN pg_database d ON d.oid = l.database "
        "WHERE l.locktype = 'advisory' AND l.granted AND d.datname = %s "
        "AND l.classid = ((%s::bigint >> 32) & 4294967295)::bigint::oid "
        "AND l.objid = (%s::bigint & 4294967295)::bigint::oid AND l.objsubid = 1",
        (dbname, key, key),
    ).fetchall()
    return [int(row[0]) for row in rows]


def _wait_until_acquired(repository: PostgresIngestionRepository) -> None:
    """Poll `try_acquire_ingest_exclusion` until it is `True` (10 seconds at most)."""
    deadline = time.monotonic() + 10
    while not repository.try_acquire_ingest_exclusion():
        if time.monotonic() > deadline:
            pytest.fail("the exclusion was not released within 10 seconds")
        time.sleep(0.05)


def _texts(error: BaseException) -> list[str]:
    return [str(error), repr(error), " ".join(str(arg) for arg in error.args)]


def _assert_no_mechanism_in(
    error: BaseException, settings: PostgresSettings, key: int
) -> None:
    """No key, SQL, setting or word of the PostgreSQL mechanism in `error`."""
    forbidden = {
        "the key": str(key),
        "the key in hex": format(key, "x"),
        "advisory": "advisory",
        "pg_": "pg_",
        "SELECT": "SELECT",
        "the database name": settings.dbname,
        "the host": settings.host,
        "the user": settings.user,
    }
    if settings.password:
        forbidden["the password"] = settings.password
    leaked = [
        name
        for name, value in forbidden.items()
        if any(value.lower() in text.lower() for text in _texts(error))
    ]
    assert leaked == []
    assert error.__cause__ is None


# --- AC19: the guard of this directory ---------------------------------------


def test_network_guard_blocks_an_httpx_request_but_postgresql_still_works(
    network_guard: NetworkGuard,
    empty_database: PostgresSettings,
    open_connection: OpenConnection,
) -> None:
    with pytest.raises(httpx.HTTPError):
        httpx.get("https://source.invalid/PLATAFORMA", timeout=2)

    assert network_guard.attempts != []
    network_guard.attempts.clear()  # the attempt was on purpose; teardown stays clean

    connection = open_connection(empty_database)
    assert connection.execute("SELECT 1").fetchone() == (1,)
    assert network_guard.attempts == []


def test_network_guard_resolves_the_configured_host_and_no_other(
    network_guard: NetworkGuard,
) -> None:
    assert socket.getaddrinfo(network_guard.allowed_host, None) != []
    assert network_guard.attempts == []

    with pytest.raises(OSError, match="synthetic network guard"):
        socket.getaddrinfo("source.invalid", 443)
    with pytest.raises(OSError, match="synthetic network guard"):
        socket.create_connection(("source.invalid", 443), timeout=2)

    assert network_guard.attempts == ["getaddrinfo", "create_connection"]
    network_guard.attempts.clear()


# --- AC23: list_runs ---------------------------------------------------------


def test_list_runs_returns_the_runs_of_a_status_in_started_order(
    make_repository: MakeRepository,
) -> None:
    repository = make_repository()
    first = _start(repository, "synthetic-exec-001", T0)
    _start(repository, "synthetic-exec-002", T0 + timedelta(seconds=1))
    third = _start(repository, "synthetic-exec-003", T0 + timedelta(seconds=2))
    failed = _fail(repository, "synthetic-exec-002", T0 + timedelta(seconds=5))

    running = repository.list_runs(RunStatus.RUNNING)

    assert isinstance(running, tuple)
    assert running == (first, third)
    assert repository.list_runs(RunStatus.FAILED) == (failed,)
    assert repository.list_runs(RunStatus.SUCCEEDED) == ()


def test_list_runs_orders_by_start_time_then_execution_id_whatever_the_insertion_order(
    make_repository: MakeRepository,
) -> None:
    repository = make_repository()
    # Inserted out of order: the start time decides, then the execution id.
    late = _start(repository, "synthetic-exec-a", T0 + timedelta(seconds=9))
    tie_c = _start(repository, "synthetic-exec-c", T0 + timedelta(seconds=3))
    early = _start(repository, "synthetic-exec-z", T0)
    tie_b = _start(repository, "synthetic-exec-b", T0 + timedelta(seconds=3))

    first_call = repository.list_runs(RunStatus.RUNNING)

    assert first_call == (early, tie_b, tie_c, late)
    assert repository.list_runs(RunStatus.RUNNING) == first_call


def test_list_runs_sees_the_runs_of_another_repository_and_their_changes(
    make_repository: MakeRepository,
) -> None:
    writer = make_repository()
    reader = make_repository()
    started = _start(writer, "synthetic-exec-001")
    assert reader.list_runs(RunStatus.RUNNING) == (started,)

    failed = _fail(writer, "synthetic-exec-001", T0 + timedelta(seconds=1))

    assert reader.list_runs(RunStatus.RUNNING) == ()
    assert reader.list_runs(RunStatus.FAILED) == (failed,)


def test_list_runs_is_an_empty_tuple_when_there_is_no_run_of_that_status(
    make_repository: MakeRepository,
) -> None:
    repository = make_repository()

    for status in RunStatus:
        assert repository.list_runs(status) == ()


@pytest.mark.parametrize(
    "status",
    [
        pytest.param("running", id="plain-str-running"),
        pytest.param("failed", id="plain-str-failed"),
        pytest.param(None, id="none"),
        pytest.param(1, id="int"),
    ],
)
def test_list_runs_with_a_value_that_is_not_a_run_status_is_a_value_error(
    make_repository: MakeRepository, status: Any
) -> None:
    repository = make_repository()
    started = _start(repository, "synthetic-exec-001")

    with pytest.raises(ValueError):
        repository.list_runs(status)

    # Nothing broke: the repository still answers.
    assert repository.list_runs(RunStatus.RUNNING) == (started,)


def test_list_runs_writes_nothing(
    make_repository: MakeRepository,
    migrated_database: PostgresSettings,
    open_connection: OpenConnection,
) -> None:
    repository = make_repository()
    _start(repository, "synthetic-exec-001")
    before = _counts(open_connection, migrated_database)

    repository.list_runs(RunStatus.RUNNING)
    repository.list_runs(RunStatus.FAILED)

    assert _counts(open_connection, migrated_database) == before


def test_list_runs_after_close_is_a_runtime_error_and_after_a_loss_a_connection_error(
    make_repository: MakeRepository,
    migrated_database: PostgresSettings,
    admin_connection: Any,
) -> None:
    lost = make_repository()
    lost.list_runs(RunStatus.RUNNING)
    _terminate_backends(admin_connection, migrated_database.dbname)
    with pytest.raises(PersistenceConnectionError):
        lost.list_runs(RunStatus.RUNNING)

    closed = make_repository()
    closed.close()
    with pytest.raises(RuntimeError):
        closed.list_runs(RunStatus.RUNNING)


# --- AC23: the ingest exclusion ----------------------------------------------


def test_exclusion_is_true_and_true_again_for_the_same_repository(
    make_repository: MakeRepository,
    migrated_database: PostgresSettings,
    admin_connection: Any,
) -> None:
    key, _ = _keys()
    repository = make_repository()

    assert repository.try_acquire_ingest_exclusion() is True
    assert repository.try_acquire_ingest_exclusion() is True

    # One acquisition, not two stacked ones: a single session holds the key.
    assert len(_holders_of(admin_connection, migrated_database.dbname, key)) == 1


def test_exclusion_second_repository_is_false_at_once_and_writes_nothing(
    make_repository: MakeRepository,
    migrated_database: PostgresSettings,
    open_connection: OpenConnection,
) -> None:
    first = make_repository()
    second = make_repository()
    assert first.try_acquire_ingest_exclusion() is True
    before = _counts(open_connection, migrated_database)

    started = time.monotonic()
    answer = second.try_acquire_ingest_exclusion()
    elapsed = time.monotonic() - started

    assert answer is False
    assert elapsed < migrated_database.connect_timeout
    assert _counts(open_connection, migrated_database) == before
    # The refusal changes nothing: the second one is still refused, the first still holds.
    assert second.try_acquire_ingest_exclusion() is False
    assert first.try_acquire_ingest_exclusion() is True


def test_exclusion_is_held_by_the_repository_not_by_one_transaction(
    make_repository: MakeRepository,
) -> None:
    first = make_repository()
    second = make_repository()
    assert first.try_acquire_ingest_exclusion() is True

    # The repository's own operations commit and roll back; the hold survives them.
    _start(first, "synthetic-exec-001")
    first.list_runs(RunStatus.RUNNING)
    first.read_run("synthetic-exec-001")
    _fail(first, "synthetic-exec-001", T0 + timedelta(seconds=1))

    assert second.try_acquire_ingest_exclusion() is False


def test_exclusion_is_released_when_the_first_repository_closes(
    make_repository: MakeRepository,
) -> None:
    first = make_repository()
    second = make_repository()
    assert first.try_acquire_ingest_exclusion() is True
    assert second.try_acquire_ingest_exclusion() is False

    first.close()

    assert second.try_acquire_ingest_exclusion() is True


def test_exclusion_is_released_when_the_session_of_the_first_repository_is_terminated(
    make_repository: MakeRepository,
    migrated_database: PostgresSettings,
    admin_connection: Any,
) -> None:
    key, _ = _keys()
    first = make_repository()
    second = make_repository()
    assert first.try_acquire_ingest_exclusion() is True
    assert second.try_acquire_ingest_exclusion() is False
    (holder,) = _holders_of(admin_connection, migrated_database.dbname, key)

    admin_connection.execute("SELECT pg_terminate_backend(%s)", (holder,))

    _wait_until_acquired(second)


def test_exclusion_held_by_a_test_connection_refuses_the_repository_until_it_is_released(
    make_repository: MakeRepository,
    migrated_database: PostgresSettings,
    open_connection: OpenConnection,
) -> None:
    key, _ = _keys()
    holder = open_connection(migrated_database)
    row = holder.execute("SELECT pg_try_advisory_lock(%s::bigint)", (key,)).fetchone()
    assert row == (True,)
    repository = make_repository()
    before = _counts(open_connection, migrated_database)

    assert repository.try_acquire_ingest_exclusion() is False
    assert _counts(open_connection, migrated_database) == before

    holder.execute("SELECT pg_advisory_unlock(%s::bigint)", (key,))

    assert repository.try_acquire_ingest_exclusion() is True


def test_exclusion_is_independent_of_the_migration_lock(
    make_repository: MakeRepository,
    migrated_database: PostgresSettings,
    open_connection: OpenConnection,
) -> None:
    key, migration_key = _keys()
    assert key != migration_key
    holder = open_connection(migrated_database)
    holder.execute("SELECT pg_advisory_lock(%s::bigint)", (migration_key,))
    repository = make_repository()

    assert repository.try_acquire_ingest_exclusion() is True


def test_exclusion_held_does_not_block_apply_migrations(
    make_repository: MakeRepository, migrated_database: PostgresSettings
) -> None:
    repository = make_repository()
    assert repository.try_acquire_ingest_exclusion() is True

    applied = apply_migrations(migrated_database, MIGRATIONS_DIR)

    assert applied == ()
    assert repository.try_acquire_ingest_exclusion() is True


def test_exclusion_after_a_connection_loss_is_a_connection_error_and_is_no_longer_claimed(
    make_repository: MakeRepository,
    migrated_database: PostgresSettings,
    admin_connection: Any,
) -> None:
    first = make_repository()
    assert first.try_acquire_ingest_exclusion() is True
    _terminate_backends(admin_connection, migrated_database.dbname)

    with pytest.raises(PersistenceConnectionError):
        first.try_acquire_ingest_exclusion()
    # It never answers True again from memory.
    with pytest.raises(PersistenceConnectionError):
        first.try_acquire_ingest_exclusion()

    second = make_repository()
    assert second.try_acquire_ingest_exclusion() is True


def test_exclusion_never_acquired_and_lost_is_a_connection_error(
    make_repository: MakeRepository,
    migrated_database: PostgresSettings,
    admin_connection: Any,
) -> None:
    repository = make_repository()
    repository.list_runs(RunStatus.RUNNING)
    _terminate_backends(admin_connection, migrated_database.dbname)

    with pytest.raises(PersistenceConnectionError):
        repository.try_acquire_ingest_exclusion()


def test_exclusion_after_close_is_a_runtime_error(
    make_repository: MakeRepository,
) -> None:
    never_acquired = make_repository()
    never_acquired.close()
    with pytest.raises(RuntimeError):
        never_acquired.try_acquire_ingest_exclusion()

    holder = make_repository()
    assert holder.try_acquire_ingest_exclusion() is True
    holder.close()
    with pytest.raises(RuntimeError):
        holder.try_acquire_ingest_exclusion()


def test_exclusion_errors_hold_no_key_no_sql_and_no_setting(
    make_repository: MakeRepository,
    migrated_database: PostgresSettings,
    admin_connection: Any,
) -> None:
    key, _ = _keys()
    closed = make_repository()
    closed.close()
    with pytest.raises(RuntimeError) as closed_error:
        closed.try_acquire_ingest_exclusion()

    lost = make_repository()
    assert lost.try_acquire_ingest_exclusion() is True
    _terminate_backends(admin_connection, migrated_database.dbname)
    with pytest.raises(PersistenceConnectionError) as lost_error:
        lost.try_acquire_ingest_exclusion()
    with pytest.raises(PersistenceConnectionError) as lost_listing:
        lost.list_runs(RunStatus.RUNNING)

    for error in (closed_error.value, lost_error.value, lost_listing.value):
        _assert_no_mechanism_in(error, migrated_database, key)
