"""Migration runner for PostgreSQL (ADR 0007), a library function with no CLI.

`apply_migrations` applies the numbered SQL files of a directory that a database
has not recorded yet, each once and in order, and returns the names it applied.

- Files: `NNNN_description.sql` (`NNNN` four digits, the description of `a-z`,
  `0-9` and `_`), numbered contiguously from `0001`. Every check on the
  directory and on the files happens before a connection is opened.
- Checksum: the SHA-256 of the file's exact bytes. Before anything is applied,
  every recorded row must match a file (same number, name and checksum) and
  every file up to the highest recorded number must be recorded.
- Lock: a session advisory lock taken with `pg_try_advisory_lock`. When another
  session holds it the runner fails at once and never waits.
- Atomicity: each pending file runs in its own transaction together with the
  insert of its bookkeeping row, so a file's effects and its row commit together
  or not at all. A file that fails is rolled back, is not recorded, and stops the
  run. A connection lost while a commit is in flight leaves that one file's
  outcome unknown (applied and recorded, or neither); running the runner again
  resolves it, because it reads the bookkeeping table.
- Authoring rules (not parsed here, checked at review): a migration holds no
  transaction control, no statement that cannot run in a transaction and no
  `SET` that outlives it, and never edits `schema_migration`.

The runner writes no log output. Errors carry fixed text that names a migration
file and nothing from the driver or the server, and are raised outside the
`except` block that caught the driver's exception, with no `from` clause.
"""

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import NoReturn

import psycopg

from ec_procurement_quality.domain.persistence_errors import (
    MigrationError,
    MigrationLockError,
    PersistenceConnectionError,
)
from ec_procurement_quality.infrastructure.postgres_settings import (
    PostgresConnection,
    PostgresSettings,
    connection_was_lost,
    open_connection,
)

# The key of the runner's advisory lock: the ASCII bytes of "ecpqmigr".
MIGRATION_LOCK_KEY = 0x6563_7071_6D69_6772

_FILE_NAME = re.compile(r"([0-9]{4})_[a-z0-9_]+\.sql")
_CREATE_BOOKKEEPING = (
    "CREATE TABLE IF NOT EXISTS schema_migration ("
    "version integer PRIMARY KEY CHECK (version >= 1), "
    "filename text NOT NULL UNIQUE, "
    "sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'), "
    "applied_at timestamptz NOT NULL DEFAULT now())"
)
_SELECT_RECORDED = (
    "SELECT version, filename, sha256 FROM schema_migration ORDER BY version"
)
_INSERT_RECORD = (
    "INSERT INTO schema_migration (version, filename, sha256) VALUES (%s, %s, %s)"
)
_LOCK = "SELECT pg_try_advisory_lock(%s::bigint)"
_UNLOCK = "SELECT pg_advisory_unlock(%s::bigint)"


@dataclass(frozen=True)
class _Migration:
    version: int
    name: str
    sql: str
    sha256: str


class _Failure(Enum):
    LOST = auto()  # the connection is gone
    REFUSED = auto()  # the server refused a statement; the connection is usable


# --- Files ------------------------------------------------------------------


def _list_names(directory: Path) -> list[str] | None:
    """The names of the regular `.sql` files directly in `directory`, sorted."""
    try:
        return sorted(
            entry.name
            for entry in directory.iterdir()
            if entry.name.lower().endswith(".sql") and entry.is_file()
        )
    except OSError:
        return None


def _read_file(path: Path) -> tuple[str, str] | None:
    """The file's text and the SHA-256 of its bytes, or `None` if unusable.

    A file is unusable when it cannot be read, is not strict UTF-8, or holds a
    NUL (the driver would cut the statement there).
    """
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if "\0" in text:
        return None
    return text, hashlib.sha256(raw).hexdigest()


def _read_migrations(directory: Path) -> tuple[_Migration, ...]:
    """Check the directory and every file, and return them in order.

    Raises `MigrationError` naming the offending file. Opens no connection.
    """
    if not directory.is_dir():
        raise MigrationError("the migrations directory does not exist")
    names = _list_names(directory)
    if names is None:
        raise MigrationError("the migrations directory cannot be read")
    for name in names:
        if _FILE_NAME.fullmatch(name) is None:
            raise MigrationError(
                f"migration file {name!a} is not named NNNN_description.sql"
            )
    for index, name in enumerate(names):
        expected = index + 1
        if int(name[:4]) != expected:
            raise MigrationError(
                f"migration file {name!a} breaks the numbering: "
                f"expected number {expected:04d}"
            )
    migrations: list[_Migration] = []
    for name in names:
        read = _read_file(directory / name)
        if read is None:
            raise MigrationError(
                f"migration file {name!a} cannot be read as UTF-8 text without NUL"
            )
        text, checksum = read
        if not text.strip():
            raise MigrationError(f"migration file {name!a} is empty")
        migrations.append(
            _Migration(version=int(name[:4]), name=name, sql=text, sha256=checksum)
        )
    return tuple(migrations)


# --- Database steps ---------------------------------------------------------


def _rollback_quietly(connection: PostgresConnection) -> None:
    try:
        connection.rollback()
    except psycopg.Error:
        pass


def _attempt[T](
    connection: PostgresConnection, work: Callable[[], T]
) -> tuple[T | None, _Failure | None]:
    """Run `work`; return its value, or the kind of failure, never the driver's text.

    The caller raises its own error after this returns, so nothing the driver
    raised is chained.
    """
    value: T | None = None
    failure: _Failure | None = None
    try:
        value = work()
    except psycopg.Error as error:
        failure = (
            _Failure.LOST
            if connection_was_lost(connection, error)
            else _Failure.REFUSED
        )
    if failure is not None:
        _rollback_quietly(connection)
    return value, failure


def _try_lock(connection: PostgresConnection) -> bool:
    row = connection.execute(_LOCK, (MIGRATION_LOCK_KEY,)).fetchone()
    connection.commit()
    return row is not None and row[0] is True


def _unlock_quietly(connection: PostgresConnection) -> None:
    _rollback_quietly(connection)

    def unlock() -> None:
        connection.execute(_UNLOCK, (MIGRATION_LOCK_KEY,))
        connection.commit()

    _attempt(connection, unlock)


def _prepare_bookkeeping(connection: PostgresConnection) -> None:
    connection.execute(_CREATE_BOOKKEEPING)
    connection.commit()


def _recorded(connection: PostgresConnection) -> list[tuple[int, str, str]]:
    rows = connection.execute(_SELECT_RECORDED).fetchall()
    connection.commit()
    return [(int(row[0]), str(row[1]), str(row[2])) for row in rows]


def _apply_one(connection: PostgresConnection, migration: _Migration) -> None:
    # No parameters: several statements may run, and `%` is not interpreted.
    connection.execute(migration.sql)
    connection.execute(
        _INSERT_RECORD, (migration.version, migration.name, migration.sha256)
    )
    connection.commit()


def _raise_for(failure: _Failure, refused: str) -> NoReturn:
    if failure is _Failure.LOST:
        raise PersistenceConnectionError(
            "the database connection was lost while applying migrations"
        )
    raise MigrationError(refused)


# --- Checks against the bookkeeping table -----------------------------------


def _check_recorded(
    recorded: list[tuple[int, str, str]], migrations: tuple[_Migration, ...]
) -> int:
    """Raise `MigrationError` on any mismatch; return the highest recorded number."""
    by_version = {migration.version: migration for migration in migrations}
    highest = 0
    for version, filename, checksum in recorded:
        highest = max(highest, version)
        migration = by_version.get(version)
        if migration is None or migration.name != filename:
            raise MigrationError(
                f"applied migration {filename!a} is missing from the "
                "migrations directory or was renamed"
            )
        if migration.sha256 != checksum:
            raise MigrationError(
                f"applied migration {filename!a} was changed after it was applied"
            )
    recorded_versions = {version for version, _, _ in recorded}
    for migration in migrations:
        if migration.version <= highest and migration.version not in recorded_versions:
            raise MigrationError(
                f"migration {migration.name!a} is not recorded although a "
                "later migration is"
            )
    return highest


def _apply_pending(
    connection: PostgresConnection, migrations: tuple[_Migration, ...]
) -> tuple[str, ...]:
    _, failure = _attempt(connection, lambda: _prepare_bookkeeping(connection))
    if failure is not None:
        _raise_for(failure, "the migration bookkeeping table cannot be created")
    recorded, failure = _attempt(connection, lambda: _recorded(connection))
    if failure is not None or recorded is None:
        _raise_for(
            failure or _Failure.REFUSED,
            "the migration bookkeeping table cannot be read",
        )
    highest = _check_recorded(recorded, migrations)
    applied: list[str] = []
    for migration in migrations:
        if migration.version <= highest:
            continue

        def run(pending: _Migration = migration) -> None:
            _apply_one(connection, pending)

        _, failure = _attempt(connection, run)
        if failure is not None:
            _raise_for(
                failure,
                f"migration {migration.name!a} failed and was rolled back",
            )
        applied.append(migration.name)
    return tuple(applied)


def apply_migrations(settings: PostgresSettings, directory: Path) -> tuple[str, ...]:
    """Apply the pending migrations of `directory` and return their file names.

    Raises `MigrationError` for a bad directory, file or applied-file mismatch
    (before any connection is opened for the first two), for a lock held by
    another run (`MigrationLockError`, a `MigrationError`), and for a file the
    database refused. Raises
    `PersistenceConnectionError` when the database cannot be reached or the
    connection is lost.
    """
    migrations = _read_migrations(directory)
    connection = open_connection(settings)
    try:
        locked, failure = _attempt(connection, lambda: _try_lock(connection))
        if failure is not None:
            _raise_for(failure, "the migration lock cannot be taken")
        if not locked:
            raise MigrationLockError("another migration run holds the lock")
        try:
            return _apply_pending(connection, migrations)
        finally:
            _unlock_quietly(connection)
    finally:
        connection.close()
