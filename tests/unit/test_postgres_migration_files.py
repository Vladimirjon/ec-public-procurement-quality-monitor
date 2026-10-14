"""Feature postgres-persistence (F3), outcome O6 (AC3): the migration runner
checks the migrations directory before it opens any connection.

Every case builds a synthetic migrations directory in `tmp_path` and points the
settings at `127.0.0.1` on a port nobody listens on. A bad directory must raise
`MigrationError` naming the offending file: if the runner opened a connection
first, the closed port would make it raise `PersistenceConnectionError`
instead. The autouse guard also fails a test that opens a Python socket.
Contents are synthetic SQL; the password is a marker.
"""

import socket
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, NoReturn

import pytest

from ec_procurement_quality.domain.persistence_errors import MigrationError
from ec_procurement_quality.infrastructure.postgres_migrations import (
    MIGRATION_LOCK_KEY,
    apply_migrations,
)
from ec_procurement_quality.infrastructure.postgres_settings import PostgresSettings

CLOSED_PORT_SETTINGS = PostgresSettings(
    host="127.0.0.1",
    port=1,
    dbname="synthetic_db",
    user="synthetic_user",
    password="synthetic-password-marker",
    connect_timeout=2,
)
VALID_SQL = b"CREATE TABLE synthetic_a (id integer);\n"


@pytest.fixture(autouse=True)
def socket_guard(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """Fail the test if it opens a socket or resolves a host name."""
    attempts: list[str] = []

    def blocked(name: str) -> Callable[..., NoReturn]:
        def refuse(*args: Any, **kwargs: Any) -> NoReturn:
            attempts.append(name)
            raise OSError(f"synthetic network guard: {name} is blocked in tests")

        return refuse

    monkeypatch.setattr(socket.socket, "connect", blocked("socket.connect"))
    monkeypatch.setattr(socket.socket, "connect_ex", blocked("socket.connect_ex"))
    monkeypatch.setattr(socket, "create_connection", blocked("create_connection"))
    monkeypatch.setattr(socket, "getaddrinfo", blocked("getaddrinfo"))

    yield attempts

    assert attempts == [], f"the test tried to reach the network: {attempts}"


def _directory(tmp_path: Path, files: dict[str, bytes]) -> Path:
    directory = tmp_path / "migrations"
    directory.mkdir()
    for name, content in files.items():
        (directory / name).write_bytes(content)
    return directory


def _message_naming_a_file(directory: Path) -> str:
    with pytest.raises(MigrationError) as caught:
        apply_migrations(CLOSED_PORT_SETTINGS, directory)
    return str(caught.value)


def test_migration_files_bad_name_is_named_before_any_connection(
    tmp_path: Path,
) -> None:
    directory = _directory(tmp_path, {"0001_a.sql": VALID_SQL, "1_a.sql": VALID_SQL})

    assert "1_a.sql" in _message_naming_a_file(directory)


@pytest.mark.parametrize(
    "bad_name",
    [
        pytest.param("0002_B.sql", id="uppercase-description"),
        pytest.param("0002_x.SQL", id="uppercase-extension"),
        pytest.param("0002-x.sql", id="dash-instead-of-underscore"),
        pytest.param("0002_.sql", id="empty-description"),
        pytest.param("00002_x.sql", id="five-digits"),
        pytest.param("002_x.sql", id="three-digits"),
        pytest.param("0002_x y.sql", id="space"),
    ],
)
def test_migration_files_name_outside_the_pattern_is_named(
    tmp_path: Path, bad_name: str
) -> None:
    directory = _directory(tmp_path, {"0001_a.sql": VALID_SQL, bad_name: VALID_SQL})

    assert bad_name in _message_naming_a_file(directory)


def test_migration_files_gap_in_the_numbering_names_the_file_after_it(
    tmp_path: Path,
) -> None:
    directory = _directory(tmp_path, {"0001_a.sql": VALID_SQL, "0003_c.sql": VALID_SQL})

    assert "0003_c.sql" in _message_naming_a_file(directory)


def test_migration_files_numbering_must_start_at_one(tmp_path: Path) -> None:
    directory = _directory(tmp_path, {"0002_b.sql": VALID_SQL})

    assert "0002_b.sql" in _message_naming_a_file(directory)


def test_migration_files_repeated_number_names_one_of_the_two(tmp_path: Path) -> None:
    directory = _directory(tmp_path, {"0001_a.sql": VALID_SQL, "0001_b.sql": VALID_SQL})

    message = _message_naming_a_file(directory)

    assert "0001_a.sql" in message or "0001_b.sql" in message


def test_migration_files_empty_file_is_named(tmp_path: Path) -> None:
    directory = _directory(tmp_path, {"0001_a.sql": b""})

    assert "0001_a.sql" in _message_naming_a_file(directory)


def test_migration_files_file_that_is_not_utf8_is_named(tmp_path: Path) -> None:
    directory = _directory(tmp_path, {"0001_a.sql": b"SELECT '\xff';\n"})

    assert "0001_a.sql" in _message_naming_a_file(directory)


def test_migration_files_file_holding_a_nul_is_named(tmp_path: Path) -> None:
    directory = _directory(
        tmp_path,
        {
            "0001_a.sql": VALID_SQL,
            "0002_b.sql": b"CREATE TABLE synthetic_b (id integer);\x00\n",
        },
    )

    assert "0002_b.sql" in _message_naming_a_file(directory)


def test_migration_files_whitespace_only_file_is_named(tmp_path: Path) -> None:
    directory = _directory(tmp_path, {"0001_a.sql": b" \n\t\r\n"})

    assert "0001_a.sql" in _message_naming_a_file(directory)


def test_migration_files_missing_directory_is_a_migration_error(
    tmp_path: Path,
) -> None:
    with pytest.raises(MigrationError):
        apply_migrations(CLOSED_PORT_SETTINGS, tmp_path / "does-not-exist")


def test_migration_files_other_files_beside_them_are_not_reported(
    tmp_path: Path,
) -> None:
    directory = _directory(
        tmp_path,
        {"README.md": b"# notes\n", "notes.txt": b"x", "1_a.sql": VALID_SQL},
    )
    (directory / "subdirectory.sql").mkdir()

    message = _message_naming_a_file(directory)

    assert "1_a.sql" in message
    assert "README.md" not in message
    assert "notes.txt" not in message
    assert "subdirectory.sql" not in message


def test_migration_files_message_holds_no_password(tmp_path: Path) -> None:
    directory = _directory(tmp_path, {"1_a.sql": VALID_SQL})

    message = _message_naming_a_file(directory)

    assert CLOSED_PORT_SETTINGS.password not in message


def test_migration_files_lock_key_is_a_signed_64_bit_integer() -> None:
    assert isinstance(MIGRATION_LOCK_KEY, int)
    assert not isinstance(MIGRATION_LOCK_KEY, bool)
    assert -(2**63) <= MIGRATION_LOCK_KEY <= 2**63 - 1
