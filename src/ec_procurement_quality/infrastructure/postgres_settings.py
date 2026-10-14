"""Connection settings for the PostgreSQL adapter and the migration runner (ADR 0007).

`PostgresSettings` is built by the caller (this layer reads no environment and no
file) and is passed to `psycopg` as separate keyword arguments, never as a
connection string, so no password can travel in one. A rejected field is named in
the message and its value never is, and `repr()` and `str()` hide the password.

The module also holds the two helpers that the runner and the adapter share to
open a connection and to tell a lost connection from a refused statement. Their
failures are reported without any text from the driver or the server: the
server's own messages quote the rows they reject.
"""

from dataclasses import dataclass, field
from typing import Any

import psycopg

from ec_procurement_quality.domain.persistence_errors import PersistenceConnectionError

_MIN_PORT = 1
_MAX_PORT = 65535
# `libpq` treats a connect timeout of 1 as 2, so 1 is not accepted.
_MIN_CONNECT_TIMEOUT = 2
_MAX_CONNECT_TIMEOUT = 60
# SQLSTATE class 08 (connection exception) and the shutdown states 57P01 to 57P03.
_CONNECTION_CLASS = "08"
_SHUTDOWN_STATES = frozenset({"57P01", "57P02", "57P03"})

type PostgresConnection = psycopg.Connection[tuple[Any, ...]]


def _require_text(value: object, name: str, *, allow_empty: bool = False) -> None:
    if not isinstance(value, str) or (not value and not allow_empty):
        raise ValueError(
            f"{name} must be a {'string' if allow_empty else 'non-empty string'}"
        )
    if "\x00" in value:
        raise ValueError(f"{name} must not contain U+0000")
    # A lone surrogate cannot be encoded, and the encoding error would hold the
    # text, so try the encoding here and raise ours after the `try`.
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        pass
    else:
        return
    raise ValueError(f"{name} must be text that UTF-8 can encode")


def _require_int(value: object, name: str, minimum: int, maximum: int) -> None:
    # `bool` is a subclass of `int`; a flag is never a port or a timeout.
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not minimum <= value <= maximum
    ):
        raise ValueError(f"{name} must be an integer from {minimum} to {maximum}")


@dataclass(frozen=True, kw_only=True)
class PostgresSettings:
    """Immutable connection settings, built with keyword arguments only."""

    host: str
    port: int
    dbname: str
    user: str
    password: str = field(repr=False)
    connect_timeout: int = 5

    def __post_init__(self) -> None:
        _require_text(self.host, "host")
        _require_int(self.port, "port", _MIN_PORT, _MAX_PORT)
        _require_text(self.dbname, "dbname")
        _require_text(self.user, "user")
        _require_text(self.password, "password", allow_empty=True)
        _require_int(
            self.connect_timeout,
            "connect_timeout",
            _MIN_CONNECT_TIMEOUT,
            _MAX_CONNECT_TIMEOUT,
        )


def open_connection(settings: PostgresSettings) -> PostgresConnection:
    """Open a connection with a UTC session time zone, outside any transaction.

    Raises `PersistenceConnectionError` with fixed text when the database cannot
    be reached, refuses the credentials, or fails while the session is prepared.
    """
    connection: PostgresConnection | None = None
    try:
        connection = psycopg.connect(
            host=settings.host,
            port=settings.port,
            dbname=settings.dbname,
            user=settings.user,
            password=settings.password,
            connect_timeout=settings.connect_timeout,
        )
        connection.execute("SET TIME ZONE 'UTC'")
        connection.commit()
    except psycopg.Error:
        if connection is not None:
            connection.close()
        connection = None
    # Raised outside the `except` block: the driver's text is not chained.
    if connection is None:
        raise PersistenceConnectionError("could not open a connection to the database")
    return connection


def connection_was_lost(connection: PostgresConnection, error: psycopg.Error) -> bool:
    """Return whether `error` means the connection itself is gone.

    A statement refused by the server (an integrity violation, a failed
    statement) leaves the connection usable and is not a loss.
    """
    if connection.closed:
        return True
    state = error.sqlstate
    if state is None:
        # Not a server error report: the client library failed to talk to it.
        return isinstance(error, psycopg.OperationalError)
    return state.startswith(_CONNECTION_CLASS) or state in _SHUTDOWN_STATES
