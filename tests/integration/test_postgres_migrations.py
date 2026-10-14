"""Feature postgres-persistence (F3), outcome O6 (AC1, AC2, AC3, AC4): the
migration runner against a real PostgreSQL.

Every test runs in its own empty throwaway database (`empty_database`, copied
from `template0`). The real `migrations/` is used only by the first test; the
other cases write synthetic migrations (`synthetic_a`, `synthetic_b`, ...) into
`tmp_path`. Names to focus on, by `-k`: `runner_applies`, `runner_failure`,
`runner_integrity`, `runner_lock`. Data is synthetic.
"""

import hashlib
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from ec_procurement_quality.domain.persistence_errors import MigrationError
from ec_procurement_quality.infrastructure.postgres_migrations import (
    MIGRATION_LOCK_KEY,
    apply_migrations,
)
from ec_procurement_quality.infrastructure.postgres_settings import PostgresSettings

pytestmark = pytest.mark.integration

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
FIRST_MIGRATION = "0001_initial_schema.sql"
TABLES = ("ingestion_run", "raw_evidence", "observation", "audit_event")

OpenConnection = Callable[..., Any]

SYNTHETIC_A = b"CREATE TABLE synthetic_a (id integer, note text DEFAULT '100% a');\n"
SYNTHETIC_B = b"CREATE TABLE synthetic_b (id integer);\n"
SYNTHETIC_C = b"CREATE TABLE synthetic_c (id integer);\n"


def _write(directory: Path, files: dict[str, bytes]) -> Path:
    directory.mkdir(exist_ok=True)
    for name, content in files.items():
        (directory / name).write_bytes(content)
    return directory


def _exists(connection: Any, table: str) -> bool:
    row = connection.execute("SELECT to_regclass(%s)", (table,)).fetchone()
    return bool(row[0] is not None)


def _recorded(connection: Any) -> list[tuple[Any, ...]]:
    return connection.execute(
        "SELECT version, filename, sha256 FROM schema_migration ORDER BY version"
    ).fetchall()


# --- AC1 --------------------------------------------------------------------


def test_runner_applies_the_repository_migrations_once(
    empty_database: PostgresSettings, open_connection: OpenConnection
) -> None:
    expected_sha = hashlib.sha256((MIGRATIONS_DIR / FIRST_MIGRATION).read_bytes())

    first = apply_migrations(empty_database, MIGRATIONS_DIR)

    assert first == (FIRST_MIGRATION,)
    connection = open_connection(empty_database)
    assert all(_exists(connection, table) for table in TABLES)
    rows = connection.execute(
        "SELECT version, filename, sha256, applied_at FROM schema_migration"
    ).fetchall()
    assert [row[:3] for row in rows] == [(1, FIRST_MIGRATION, expected_sha.hexdigest())]
    assert rows[0][3] is not None

    second = apply_migrations(empty_database, MIGRATIONS_DIR)

    assert second == ()
    again = connection.execute(
        "SELECT version, filename, sha256, applied_at FROM schema_migration"
    ).fetchall()
    assert again == rows


def test_runner_applies_synthetic_files_in_the_order_of_their_names(
    tmp_path: Path, empty_database: PostgresSettings, open_connection: OpenConnection
) -> None:
    # 0002 depends on the table 0001 creates, so a wrong order fails.
    directory = _write(
        tmp_path / "migrations",
        {
            "0002_b.sql": b"INSERT INTO synthetic_a (id) VALUES (1);\n"
            b"CREATE TABLE synthetic_b (id integer);\n",
            "0001_a.sql": SYNTHETIC_A,
        },
    )

    applied = apply_migrations(empty_database, directory)

    assert applied == ("0001_a.sql", "0002_b.sql")
    connection = open_connection(empty_database)
    assert [row[:2] for row in _recorded(connection)] == [
        (1, "0001_a.sql"),
        (2, "0002_b.sql"),
    ]
    assert connection.execute("SELECT id, note FROM synthetic_a").fetchall() == [
        (1, "100% a")
    ]


def test_runner_applies_only_the_pending_files_of_a_later_call(
    tmp_path: Path, empty_database: PostgresSettings, open_connection: OpenConnection
) -> None:
    directory = _write(tmp_path / "migrations", {"0001_a.sql": SYNTHETIC_A})
    assert apply_migrations(empty_database, directory) == ("0001_a.sql",)
    _write(directory, {"0002_b.sql": SYNTHETIC_B, "0003_c.sql": SYNTHETIC_C})

    later = apply_migrations(empty_database, directory)

    assert later == ("0002_b.sql", "0003_c.sql")
    connection = open_connection(empty_database)
    assert [row[0] for row in _recorded(connection)] == [1, 2, 3]


def test_runner_applies_ignoring_files_that_are_not_migrations(
    tmp_path: Path, empty_database: PostgresSettings
) -> None:
    directory = _write(
        tmp_path / "migrations",
        {"0001_a.sql": SYNTHETIC_A, "README.md": b"# notes\n", "notes.txt": b"x"},
    )
    (directory / "archive").mkdir()
    (directory / "archive" / "0009_old.sql").write_bytes(SYNTHETIC_B)
    (directory / "0002_dir.sql").mkdir()

    assert apply_migrations(empty_database, directory) == ("0001_a.sql",)


# --- AC2 --------------------------------------------------------------------


def test_runner_failure_rolls_back_the_file_and_keeps_earlier_ones(
    tmp_path: Path, empty_database: PostgresSettings, open_connection: OpenConnection
) -> None:
    directory = _write(
        tmp_path / "migrations",
        {
            "0001_a.sql": SYNTHETIC_A,
            "0002_b.sql": b"CREATE TABLE synthetic_b (id integer);\nSELECT 1/0;\n",
            "0003_c.sql": SYNTHETIC_C,
        },
    )

    with pytest.raises(MigrationError) as caught:
        apply_migrations(empty_database, directory)

    message = str(caught.value)
    assert "0002_b.sql" in message
    assert "division" not in message.lower()
    connection = open_connection(empty_database)
    assert _exists(connection, "synthetic_a")
    assert not _exists(connection, "synthetic_b")
    assert not _exists(connection, "synthetic_c")
    assert [row[:2] for row in _recorded(connection)] == [(1, "0001_a.sql")]


def test_runner_failure_can_be_corrected_and_run_again(
    tmp_path: Path, empty_database: PostgresSettings, open_connection: OpenConnection
) -> None:
    directory = _write(
        tmp_path / "migrations",
        {
            "0001_a.sql": SYNTHETIC_A,
            "0002_b.sql": b"CREATE TABLE synthetic_b (id integer);\nSELECT 1/0;\n",
            "0003_c.sql": SYNTHETIC_C,
        },
    )
    with pytest.raises(MigrationError):
        apply_migrations(empty_database, directory)
    _write(directory, {"0002_b.sql": SYNTHETIC_B})

    applied = apply_migrations(empty_database, directory)

    assert applied == ("0002_b.sql", "0003_c.sql")
    connection = open_connection(empty_database)
    assert [row[0] for row in _recorded(connection)] == [1, 2, 3]


# --- AC3 --------------------------------------------------------------------


def test_runner_integrity_changed_byte_of_an_applied_file_stops_everything(
    tmp_path: Path, empty_database: PostgresSettings, open_connection: OpenConnection
) -> None:
    directory = _write(tmp_path / "migrations", {"0001_a.sql": SYNTHETIC_A})
    apply_migrations(empty_database, directory)
    connection = open_connection(empty_database)
    before = _recorded(connection)
    _write(directory, {"0001_a.sql": SYNTHETIC_A + b" ", "0002_b.sql": SYNTHETIC_B})

    with pytest.raises(MigrationError) as caught:
        apply_migrations(empty_database, directory)

    assert "0001_a.sql" in str(caught.value)
    assert not _exists(connection, "synthetic_b")
    assert _recorded(connection) == before


def test_runner_integrity_renamed_applied_file_stops_everything(
    tmp_path: Path, empty_database: PostgresSettings, open_connection: OpenConnection
) -> None:
    directory = _write(tmp_path / "migrations", {"0001_a.sql": SYNTHETIC_A})
    apply_migrations(empty_database, directory)
    connection = open_connection(empty_database)
    before = _recorded(connection)
    (directory / "0001_a.sql").rename(directory / "0001_x.sql")
    _write(directory, {"0002_b.sql": SYNTHETIC_B})

    with pytest.raises(MigrationError) as caught:
        apply_migrations(empty_database, directory)

    message = str(caught.value)
    assert "0001_a.sql" in message or "0001_x.sql" in message
    assert not _exists(connection, "synthetic_b")
    assert _recorded(connection) == before


def test_runner_integrity_deleted_last_applied_file_is_named(
    tmp_path: Path, empty_database: PostgresSettings, open_connection: OpenConnection
) -> None:
    directory = _write(
        tmp_path / "migrations", {"0001_a.sql": SYNTHETIC_A, "0002_b.sql": SYNTHETIC_B}
    )
    apply_migrations(empty_database, directory)
    connection = open_connection(empty_database)
    before = _recorded(connection)
    (directory / "0002_b.sql").unlink()

    with pytest.raises(MigrationError) as caught:
        apply_migrations(empty_database, directory)

    assert "0002_b.sql" in str(caught.value)
    assert _recorded(connection) == before


def test_runner_integrity_deleted_first_applied_file_stops_a_pending_one(
    tmp_path: Path, empty_database: PostgresSettings, open_connection: OpenConnection
) -> None:
    directory = _write(
        tmp_path / "migrations", {"0001_a.sql": SYNTHETIC_A, "0002_b.sql": SYNTHETIC_B}
    )
    apply_migrations(empty_database, directory)
    connection = open_connection(empty_database)
    before = _recorded(connection)
    (directory / "0001_a.sql").unlink()
    _write(directory, {"0003_c.sql": SYNTHETIC_C})

    with pytest.raises(MigrationError) as caught:
        apply_migrations(empty_database, directory)

    message = str(caught.value)
    assert any(name in message for name in ("0001_a.sql", "0002_b.sql", "0003_c.sql"))
    assert not _exists(connection, "synthetic_c")
    assert _recorded(connection) == before


def test_runner_integrity_unrecorded_file_below_a_recorded_version_is_named(
    tmp_path: Path, empty_database: PostgresSettings, open_connection: OpenConnection
) -> None:
    directory = _write(tmp_path / "migrations", {"0001_a.sql": SYNTHETIC_A})
    apply_migrations(empty_database, directory)
    _write(directory, {"0002_b.sql": SYNTHETIC_B, "0003_c.sql": SYNTHETIC_C})
    connection = open_connection(empty_database)
    # Direct SQL stands for a hand-edited bookkeeping table: version 3 is
    # recorded although version 2 never was.
    connection.execute(
        "INSERT INTO schema_migration (version, filename, sha256) VALUES (%s, %s, %s)",
        (3, "0003_c.sql", hashlib.sha256(SYNTHETIC_C).hexdigest()),
    )
    before = _recorded(connection)

    with pytest.raises(MigrationError) as caught:
        apply_migrations(empty_database, directory)

    assert "0002_b.sql" in str(caught.value)
    assert not _exists(connection, "synthetic_b")
    assert _recorded(connection) == before


# --- AC4 --------------------------------------------------------------------


def test_runner_lock_held_elsewhere_fails_at_once_and_creates_nothing(
    tmp_path: Path, empty_database: PostgresSettings, open_connection: OpenConnection
) -> None:
    directory = _write(tmp_path / "migrations", {"0001_a.sql": SYNTHETIC_A})
    holder = open_connection(empty_database)
    holder.execute("SELECT pg_advisory_lock(%s::bigint)", (MIGRATION_LOCK_KEY,))

    started = time.monotonic()
    with pytest.raises(MigrationError) as caught:
        apply_migrations(empty_database, directory)
    elapsed = time.monotonic() - started

    assert "lock" in str(caught.value).lower()
    assert elapsed < empty_database.connect_timeout
    checker = open_connection(empty_database)
    assert not _exists(checker, "schema_migration")
    assert not _exists(checker, "synthetic_a")


def test_runner_lock_released_elsewhere_lets_the_runner_succeed(
    tmp_path: Path, empty_database: PostgresSettings, open_connection: OpenConnection
) -> None:
    directory = _write(tmp_path / "migrations", {"0001_a.sql": SYNTHETIC_A})
    holder = open_connection(empty_database)
    holder.execute("SELECT pg_advisory_lock(%s::bigint)", (MIGRATION_LOCK_KEY,))
    with pytest.raises(MigrationError):
        apply_migrations(empty_database, directory)
    holder.execute("SELECT pg_advisory_unlock(%s::bigint)", (MIGRATION_LOCK_KEY,))

    assert apply_migrations(empty_database, directory) == ("0001_a.sql",)


def test_runner_lock_is_released_when_the_runner_returns(
    tmp_path: Path, empty_database: PostgresSettings, open_connection: OpenConnection
) -> None:
    directory = _write(tmp_path / "migrations", {"0001_a.sql": SYNTHETIC_A})
    apply_migrations(empty_database, directory)
    other = open_connection(empty_database)

    row = other.execute(
        "SELECT pg_try_advisory_lock(%s::bigint)", (MIGRATION_LOCK_KEY,)
    ).fetchone()

    assert row == (True,)


def test_runner_lock_is_released_when_a_migration_fails(
    tmp_path: Path, empty_database: PostgresSettings, open_connection: OpenConnection
) -> None:
    directory = _write(tmp_path / "migrations", {"0001_a.sql": b"SELECT 1/0;\n"})
    with pytest.raises(MigrationError):
        apply_migrations(empty_database, directory)
    other = open_connection(empty_database)

    row = other.execute(
        "SELECT pg_try_advisory_lock(%s::bigint)", (MIGRATION_LOCK_KEY,)
    ).fetchone()

    assert row == (True,)
