"""Feature postgres-persistence (F3), outcome O2 (AC14): the integration harness.

What this file provides, as `execution-plan.md` § Binding constraints "Tests"
pins it:

- the settings, read from `POSTGRES_HOST` (default `127.0.0.1`),
  `POSTGRES_PORT` (default `5432`), `POSTGRES_DB`, `POSTGRES_USER` and
  `POSTGRES_PASSWORD`. Locally `uv run --env-file .env pytest tests/integration`
  loads them; in CI the workflow sets them. Only fixtures read them;
- the skip or fail policy: a missing variable or an unreachable database skips
  every integration test with the command that runs them, unless `CI` is
  `true`, where the test fails instead;
- an *admin connection* to the configured database, in autocommit. Databases
  are created and dropped only through it. No test creates, changes or drops an
  object inside the configured database;
- one throwaway database per test (`ecpq_test_<hex>`), dropped when the test
  ends with `DROP DATABASE ... WITH (FORCE)`: from `template0` for runner and
  connection tests (`empty_database`), or copied from the session's migrated
  template for every other test (`migrated_database`);
- the migrated template: created once per session from `template0`, migrated
  with the repository's `migrations/`, closed with `ALLOW_CONNECTIONS false`,
  used only as a source of copies, and dropped at session end;
- the leftover check at session end: none of the databases the session created
  remains, and the configured database's user objects are the same as at start.

No password is ever printed: the environment record hides it from `repr`, and
messages here name variables, never values. Data is synthetic.

The F3 modules are imported lazily inside fixtures, so a missing module is
reported by the fixture that needs it and never hides the reason at collection.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import psycopg
import pytest
from psycopg import sql

if TYPE_CHECKING:
    from ec_procurement_quality.infrastructure.postgres_settings import (
        PostgresSettings,
    )

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = REPOSITORY_ROOT / "migrations"
FIRST_MIGRATION = "0001_initial_schema.sql"
DATABASE_PREFIX = "ecpq_test_"
HOW_TO_RUN = "uv run --env-file .env pytest tests/integration"
REQUIRED_VARIABLES = ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")
ADMIN_CONNECT_TIMEOUT = 5

DatabaseKind = Literal["empty", "migrated"]
Connection = psycopg.Connection[tuple[Any, ...]]

_USER_OBJECTS = """
SELECT n.nspname, c.relname, c.relkind
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND n.nspname !~ '^pg_toast' AND n.nspname !~ '^pg_temp'
ORDER BY 1, 2, 3
"""


@dataclass(frozen=True)
class Environment:
    """The configured database. The password never shows in `repr`."""

    host: str
    port: int
    dbname: str
    user: str
    password: str = field(repr=False)


@dataclass
class Harness:
    """What one session shares: the admin connection and its bookkeeping."""

    environment: Environment
    admin: Connection
    created: list[str] = field(default_factory=list)
    objects_at_start: list[tuple[Any, ...]] = field(default_factory=list)


def _refuse(reason: str) -> None:
    """Skip locally; fail when `CI` is `true` (resolved question 4)."""
    if os.environ.get("CI") == "true":
        pytest.fail(reason, pytrace=False)
    pytest.skip(reason)


def _connect(environment: Environment, dbname: str, **options: Any) -> Connection:
    return psycopg.connect(
        host=environment.host,
        port=environment.port,
        dbname=dbname,
        user=environment.user,
        password=environment.password,
        **options,
    )


def _user_objects(connection: Connection) -> list[tuple[Any, ...]]:
    return connection.execute(_USER_OBJECTS).fetchall()


def _settings_for(environment: Environment, dbname: str) -> PostgresSettings:
    from ec_procurement_quality.infrastructure.postgres_settings import (
        PostgresSettings,
    )

    return PostgresSettings(
        host=environment.host,
        port=environment.port,
        dbname=dbname,
        user=environment.user,
        password=environment.password,
    )


def _new_name(harness: Harness, middle: str = "") -> str:
    name = f"{DATABASE_PREFIX}{middle}{secrets.token_hex(8)}"
    harness.created.append(name)
    return name


def _create(harness: Harness, name: str, template: str) -> None:
    harness.admin.execute(
        sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
            sql.Identifier(name), sql.Identifier(template)
        )
    )


def _drop(harness: Harness, name: str) -> None:
    harness.admin.execute(
        sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
    )


@pytest.fixture(scope="session")
def postgres_environment() -> Environment:
    """The configured database, or a skip (locally) or a failure (CI)."""
    missing = [name for name in REQUIRED_VARIABLES if not os.environ.get(name)]
    if missing:
        _refuse(
            f"{', '.join(missing)} not set: integration tests need the Compose "
            f"database; run `{HOW_TO_RUN}`"
        )
    port_text = os.environ.get("POSTGRES_PORT") or "5432"
    try:
        port = int(port_text)
    except ValueError:
        port = 0
    if not 1 <= port <= 65535:
        _refuse(f"POSTGRES_PORT is not a port number; run `{HOW_TO_RUN}`")
    return Environment(
        host=os.environ.get("POSTGRES_HOST") or "127.0.0.1",
        port=port,
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )


@pytest.fixture(scope="session")
def harness(postgres_environment: Environment) -> Iterator[Harness]:
    """The admin connection, plus the leftover check at session end."""
    try:
        admin = _connect(
            postgres_environment,
            postgres_environment.dbname,
            autocommit=True,
            connect_timeout=ADMIN_CONNECT_TIMEOUT,
        )
    except psycopg.Error:
        _refuse(
            "the configured PostgreSQL database cannot be reached: start it with "
            f"`docker compose up -d --wait` and run `{HOW_TO_RUN}`"
        )
        raise  # not reached: _refuse always skips or fails
    shared = Harness(environment=postgres_environment, admin=admin)
    shared.objects_at_start = _user_objects(admin)
    try:
        yield shared
        # The template fixture is finalized before this point, so the template
        # is gone as well.
        remaining = [
            row[0]
            for row in admin.execute(
                "SELECT datname FROM pg_database WHERE datname = ANY(%s)",
                (shared.created,),
            ).fetchall()
        ]
        assert remaining == [], f"databases left behind by the session: {remaining}"
        assert _user_objects(admin) == shared.objects_at_start, (
            "the configured database's user objects changed during the session"
        )
    finally:
        for name in shared.created:
            _drop(shared, name)
        admin.close()


@pytest.fixture(scope="session")
def migrated_template(harness: Harness) -> Iterator[str]:
    """The name of the migrated template database (copies only, never used)."""
    if not (MIGRATIONS_DIR / FIRST_MIGRATION).is_file():
        pytest.fail(
            f"migrations/{FIRST_MIGRATION} does not exist, so the migrated "
            "template cannot be built",
            pytrace=False,
        )
    from ec_procurement_quality.infrastructure.postgres_migrations import (
        apply_migrations,
    )

    name = _new_name(harness, "template_")
    _create(harness, name, "template0")
    try:
        apply_migrations(_settings_for(harness.environment, name), MIGRATIONS_DIR)
        harness.admin.execute(
            sql.SQL("ALTER DATABASE {} ALLOW_CONNECTIONS false").format(
                sql.Identifier(name)
            )
        )
        yield name
    finally:
        _drop(harness, name)


@pytest.fixture
def database_factory(
    harness: Harness, request: pytest.FixtureRequest
) -> Iterator[Callable[[DatabaseKind], PostgresSettings]]:
    """Create throwaway databases for one test; drop them when it ends."""
    made: list[str] = []

    def make(kind: DatabaseKind) -> PostgresSettings:
        template = (
            "template0"
            if kind == "empty"
            else str(request.getfixturevalue("migrated_template"))
        )
        name = _new_name(harness)
        made.append(name)
        _create(harness, name, template)
        return _settings_for(harness.environment, name)

    try:
        yield make
    finally:
        for name in reversed(made):
            _drop(harness, name)


@pytest.fixture
def empty_database(
    database_factory: Callable[[DatabaseKind], PostgresSettings],
) -> PostgresSettings:
    """Settings of a new, empty database (copied from `template0`)."""
    return database_factory("empty")


@pytest.fixture
def migrated_database(
    database_factory: Callable[[DatabaseKind], PostgresSettings],
) -> PostgresSettings:
    """Settings of a new database copied from the migrated template."""
    return database_factory("migrated")


@pytest.fixture
def admin_connection(harness: Harness) -> Connection:
    """The autocommit admin connection to the configured database."""
    return harness.admin


@pytest.fixture
def open_connection() -> Iterator[Callable[..., Connection]]:
    """Open test connections to a throwaway database, closed at the end."""
    opened: list[Connection] = []

    def open_(settings: PostgresSettings, *, autocommit: bool = True) -> Connection:
        connection: Connection = psycopg.connect(
            host=settings.host,
            port=settings.port,
            dbname=settings.dbname,
            user=settings.user,
            password=settings.password,
            autocommit=autocommit,
        )
        opened.append(connection)
        return connection

    try:
        yield open_
    finally:
        for connection in opened:
            connection.close()


@pytest.fixture
def created_databases(harness: Harness) -> list[str]:
    """Every database name the session has created so far (template included)."""
    return harness.created


@pytest.fixture
def configured_objects_at_start(harness: Harness) -> list[tuple[Any, ...]]:
    """The configured database's user objects when the session started."""
    return harness.objects_at_start


@pytest.fixture
def configured_objects_now(harness: Harness) -> Callable[[], list[tuple[Any, ...]]]:
    """A callable listing the configured database's user objects now."""
    return lambda: _user_objects(harness.admin)


@pytest.fixture
def environment_user_and_host(harness: Harness) -> dict[str, str]:
    """User and host of the configured database, for leak checks only."""
    return {"user": harness.environment.user, "host": harness.environment.host}
