"""Feature ingest-command (F4), outcome O2 (AC16, decision P-1): only a busy
migration lock produces `MigrationLockError`.

Every test runs in its own empty throwaway database (`empty_database`). The lock
is held by a test connection through `pg_advisory_lock(MIGRATION_LOCK_KEY)`; every
other refusal of the runner must stay a plain `MigrationError`, checked by exact
type. `MigrationLockError` is imported inside each test, so the file collects
while the class does not exist yet and the red reason is the `ImportError` inside
the test. Names to focus on, by `-k`: `lock_error`. Data is synthetic.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import psycopg
import pytest

from ec_procurement_quality.domain.persistence_errors import MigrationError
from ec_procurement_quality.infrastructure.postgres_migrations import (
    MIGRATION_LOCK_KEY,
    apply_migrations,
)
from ec_procurement_quality.infrastructure.postgres_settings import PostgresSettings

pytestmark = pytest.mark.integration

OpenConnection = Callable[..., Any]

LOCK_MESSAGE = "another migration run holds the lock"
PASSWORD_MARKER = "synthetic-password-marker"

SYNTHETIC_A = b"CREATE TABLE synthetic_a (id integer);\n"
SYNTHETIC_B = b"CREATE TABLE synthetic_b (id integer);\n"
SYNTHETIC_C = b"CREATE TABLE synthetic_c (id integer);\n"


def _write(directory: Path, files: dict[str, bytes]) -> Path:
    directory.mkdir(exist_ok=True)
    for name, content in files.items():
        (directory / name).write_bytes(content)
    return directory


def _texts(error: BaseException) -> list[str]:
    return [str(error), repr(error), " ".join(str(arg) for arg in error.args)]


# --- The busy lock ----------------------------------------------------------


def test_lock_error_busy_lock_raises_migration_lock_error_with_the_fixed_message(
    tmp_path: Path, empty_database: PostgresSettings, open_connection: OpenConnection
) -> None:
    from ec_procurement_quality.domain.persistence_errors import MigrationLockError

    directory = _write(tmp_path / "migrations", {"0001_a.sql": SYNTHETIC_A})
    holder = open_connection(empty_database)
    holder.execute("SELECT pg_advisory_lock(%s::bigint)", (MIGRATION_LOCK_KEY,))

    with pytest.raises(MigrationError) as caught:
        apply_migrations(empty_database, directory)

    error = caught.value
    assert type(error) is MigrationLockError
    assert str(error) == LOCK_MESSAGE
    assert error.args == (LOCK_MESSAGE,)
    assert error.__cause__ is None


def test_lock_error_busy_lock_is_caught_by_except_migration_error(
    tmp_path: Path, empty_database: PostgresSettings, open_connection: OpenConnection
) -> None:
    from ec_procurement_quality.domain.persistence_errors import MigrationLockError

    directory = _write(tmp_path / "migrations", {"0001_a.sql": SYNTHETIC_A})
    holder = open_connection(empty_database)
    holder.execute("SELECT pg_advisory_lock(%s::bigint)", (MIGRATION_LOCK_KEY,))

    caught: MigrationError | None = None
    try:
        apply_migrations(empty_database, directory)
    except MigrationError as error:
        caught = error

    assert type(caught) is MigrationLockError


def test_lock_error_busy_lock_holds_no_setting_password_key_or_server_text(
    tmp_path: Path, empty_database: PostgresSettings, open_connection: OpenConnection
) -> None:
    from ec_procurement_quality.domain.persistence_errors import MigrationLockError

    directory = _write(tmp_path / "migrations", {"0001_a.sql": SYNTHETIC_A})
    holder = open_connection(empty_database)
    holder.execute("SELECT pg_advisory_lock(%s::bigint)", (MIGRATION_LOCK_KEY,))

    with pytest.raises(MigrationError) as caught:
        apply_migrations(empty_database, directory)

    error = caught.value
    assert type(error) is MigrationLockError
    forbidden = {
        "the password marker": PASSWORD_MARKER,
        "the database name": empty_database.dbname,
        "the host": empty_database.host,
        "the user": empty_database.user,
        "the key": str(MIGRATION_LOCK_KEY),
        "the key in hex": format(MIGRATION_LOCK_KEY, "x"),
        "SQL": "SELECT",
        "the lock function": "pg_",
    }
    if empty_database.password:
        forbidden["the password"] = empty_database.password
    leaked = [
        name
        for name, value in forbidden.items()
        if any(value.lower() in text.lower() for text in _texts(error))
    ]
    assert leaked == []
    seen: BaseException | None = error.__context__
    while seen is not None:
        assert not isinstance(seen, psycopg.Error)
        seen = seen.__context__


# --- Every other refusal stays a plain MigrationError ------------------------


def _changed_applied_file(tmp_path: Path, settings: PostgresSettings) -> Path:
    directory = _write(tmp_path / "migrations", {"0001_a.sql": SYNTHETIC_A})
    apply_migrations(settings, directory)
    _write(directory, {"0001_a.sql": SYNTHETIC_A + b" "})
    return directory


def _missing_applied_file(tmp_path: Path, settings: PostgresSettings) -> Path:
    directory = _write(
        tmp_path / "migrations", {"0001_a.sql": SYNTHETIC_A, "0002_b.sql": SYNTHETIC_B}
    )
    apply_migrations(settings, directory)
    (directory / "0002_b.sql").unlink()
    return directory


def _failed_file(tmp_path: Path, settings: PostgresSettings) -> Path:
    return _write(tmp_path / "migrations", {"0001_a.sql": b"SELECT 1/0;\n"})


def _gap_in_the_numbering(tmp_path: Path, settings: PostgresSettings) -> Path:
    return _write(
        tmp_path / "migrations", {"0001_a.sql": SYNTHETIC_A, "0003_c.sql": SYNTHETIC_C}
    )


def _missing_directory(tmp_path: Path, settings: PostgresSettings) -> Path:
    return tmp_path / "absent"


@pytest.mark.parametrize(
    "prepare",
    [
        pytest.param(_changed_applied_file, id="changed-applied-file"),
        pytest.param(_missing_applied_file, id="missing-applied-file"),
        pytest.param(_failed_file, id="failed-file"),
        pytest.param(_gap_in_the_numbering, id="gap-in-the-numbering"),
        pytest.param(_missing_directory, id="missing-directory"),
    ],
)
def test_lock_error_is_not_raised_for_a_refusal_that_is_not_the_busy_lock(
    tmp_path: Path,
    empty_database: PostgresSettings,
    prepare: Callable[[Path, PostgresSettings], Path],
) -> None:
    from ec_procurement_quality.domain.persistence_errors import MigrationLockError

    directory = prepare(tmp_path, empty_database)

    with pytest.raises(MigrationError) as caught:
        apply_migrations(empty_database, directory)

    assert type(caught.value) is MigrationError
    assert not isinstance(caught.value, MigrationLockError)
