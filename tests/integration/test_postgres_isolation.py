"""Feature postgres-persistence (F3), outcome O2 and O9 (AC14): the integration
harness keeps its promises.

One throwaway database per test; the migrated template is a source of copies
that nothing can connect to; the databases of earlier tests are gone; the
configured database holds no object created by the tests. The session-end
leftover check itself lives in `conftest.py` (it fails the session at teardown
if a database or an object remains). Names to focus on, by `-k`: `isolation`.

The skip and fail policy (no database -> skipped locally, failed when `CI` is
`true`) is shown by command evidence in `tasks.md`, not by a test: a test of a
skip would itself be skipped without a database. Data is synthetic.
"""

from collections.abc import Callable
from typing import Any, Literal

import psycopg
import pytest

from ec_procurement_quality.infrastructure.postgres_settings import PostgresSettings

pytestmark = pytest.mark.integration

OpenConnection = Callable[..., Any]
DatabaseFactory = Callable[[Literal["empty", "migrated"]], PostgresSettings]

RUN_SQL = (
    "INSERT INTO ingestion_run (execution_id, scope, started_at, finished_at, status) "
    "VALUES ('synthetic-exec-001', '{}'::jsonb, now(), NULL, 'running')"
)


def test_isolation_each_database_is_its_own_and_rows_do_not_cross(
    database_factory: DatabaseFactory,
    open_connection: OpenConnection,
    postgres_environment: Any,
    migrated_template: str,
) -> None:
    first = database_factory("migrated")
    second = database_factory("migrated")

    assert first.dbname != second.dbname
    assert {first.dbname, second.dbname}.isdisjoint(
        {postgres_environment.dbname, migrated_template}
    )
    open_connection(first).execute(RUN_SQL)
    in_first = open_connection(first).execute("SELECT count(*) FROM ingestion_run")
    in_second = open_connection(second).execute("SELECT count(*) FROM ingestion_run")
    assert in_first.fetchone() == (1,)
    assert in_second.fetchone() == (0,)


def test_isolation_empty_database_has_no_tables_and_a_migrated_one_has_them(
    database_factory: DatabaseFactory, open_connection: OpenConnection
) -> None:
    empty = database_factory("empty")
    migrated = database_factory("migrated")

    exists = "SELECT to_regclass('ingestion_run') IS NOT NULL"

    assert open_connection(empty).execute(exists).fetchone() == (False,)
    assert open_connection(migrated).execute(exists).fetchone() == (True,)


def test_isolation_the_migrated_template_refuses_every_connection(
    migrated_template: str, migrated_database: PostgresSettings
) -> None:
    with pytest.raises(psycopg.OperationalError):
        psycopg.connect(
            host=migrated_database.host,
            port=migrated_database.port,
            dbname=migrated_template,
            user=migrated_database.user,
            password=migrated_database.password,
            connect_timeout=5,
        )


def test_isolation_databases_of_earlier_tests_are_already_dropped(
    migrated_database: PostgresSettings,
    migrated_template: str,
    created_databases: list[str],
    admin_connection: Any,
) -> None:
    kept = {migrated_template, migrated_database.dbname}
    earlier = [name for name in created_databases if name not in kept]

    rows = admin_connection.execute(
        "SELECT datname FROM pg_database WHERE datname = ANY(%s)", (earlier,)
    ).fetchall()

    assert rows == []
    assert all(name.startswith("ecpq_test_") for name in created_databases)


def test_isolation_the_configured_database_gets_no_object_from_the_tests(
    migrated_database: PostgresSettings,
    configured_objects_at_start: list[tuple[Any, ...]],
    configured_objects_now: Callable[[], list[tuple[Any, ...]]],
    open_connection: OpenConnection,
) -> None:
    open_connection(migrated_database).execute(RUN_SQL)

    assert configured_objects_now() == configured_objects_at_start
