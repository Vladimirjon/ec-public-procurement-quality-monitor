"""Feature postgres-persistence (F3), outcome O6 (AC12): the connection
settings value.

`PostgresSettings` is built by the caller with keyword arguments, validates
every field and never shows its password. A rejection names the field and
never its value. Building the value opens no socket (autouse guard). The
password is the marker `synthetic-password-marker`, never a real one.
"""

import socket
from collections.abc import Callable, Iterator
from typing import Any, NoReturn

import pytest

from ec_procurement_quality.infrastructure.postgres_settings import PostgresSettings

PASSWORD = "synthetic-password-marker"
VALUE_MARKER = "synthetic-value-marker"


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


def _fields(**overrides: Any) -> dict[str, Any]:
    """Valid keyword arguments for `PostgresSettings`, with `overrides` applied."""
    fields: dict[str, Any] = {
        "host": "127.0.0.1",
        "port": 5432,
        "dbname": "synthetic_db",
        "user": "synthetic_user",
        "password": PASSWORD,
    }
    fields.update(overrides)
    return fields


def test_settings_keep_the_given_values_and_default_the_connect_timeout() -> None:
    settings = PostgresSettings(**_fields())

    assert settings.host == "127.0.0.1"
    assert settings.port == 5432
    assert settings.dbname == "synthetic_db"
    assert settings.user == "synthetic_user"
    assert settings.password == PASSWORD
    assert settings.connect_timeout == 5


def test_settings_keep_a_given_connect_timeout() -> None:
    assert PostgresSettings(**_fields(connect_timeout=30)).connect_timeout == 30


def test_settings_accept_the_boundaries_of_port_and_connect_timeout() -> None:
    for port in (1, 65535):
        assert PostgresSettings(**_fields(port=port)).port == port
    for timeout in (2, 60):
        assert (
            PostgresSettings(**_fields(connect_timeout=timeout)).connect_timeout
            == timeout
        )


def test_settings_accept_an_empty_password() -> None:
    assert PostgresSettings(**_fields(password="")).password == ""


def test_settings_attributes_cannot_be_assigned() -> None:
    settings: Any = PostgresSettings(**_fields())

    with pytest.raises((AttributeError, TypeError)):
        settings.port = 5433


def test_settings_are_built_with_keyword_arguments_only() -> None:
    constructor: Any = PostgresSettings

    with pytest.raises(TypeError):
        constructor("127.0.0.1", 5432, "synthetic_db", "synthetic_user", PASSWORD)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        pytest.param("host", "", id="empty-host"),
        pytest.param("host", 5, id="non-str-host"),
        pytest.param("host", f"{VALUE_MARKER}\x00", id="nul-host"),
        pytest.param("dbname", "", id="empty-dbname"),
        pytest.param("dbname", None, id="none-dbname"),
        pytest.param("dbname", f"a\x00{VALUE_MARKER}", id="nul-dbname"),
        pytest.param("user", "", id="empty-user"),
        pytest.param("user", b"synthetic", id="bytes-user"),
        pytest.param("user", f"\x00{VALUE_MARKER}", id="nul-user"),
        pytest.param("password", 5, id="non-str-password"),
        pytest.param("password", None, id="none-password"),
        pytest.param("password", f"{VALUE_MARKER}\x00", id="nul-password"),
        pytest.param("port", 0, id="port-zero"),
        pytest.param("port", 65536, id="port-too-large"),
        pytest.param("port", -7, id="port-negative"),
        pytest.param("port", True, id="bool-port"),
        pytest.param("port", "5432", id="text-port"),
        pytest.param("port", 5432.0, id="float-port"),
        pytest.param("connect_timeout", 1, id="timeout-one"),
        pytest.param("connect_timeout", 0, id="timeout-zero"),
        pytest.param("connect_timeout", 61, id="timeout-too-large"),
        pytest.param("connect_timeout", True, id="bool-timeout"),
        pytest.param("connect_timeout", "5", id="text-timeout"),
        pytest.param("connect_timeout", 2.5, id="float-timeout"),
    ],
)
def test_settings_reject_an_invalid_field_naming_it(field: str, value: Any) -> None:
    with pytest.raises(ValueError) as caught:
        PostgresSettings(**_fields(**{field: value}))

    message = str(caught.value)
    assert field in message
    assert VALUE_MARKER not in message
    assert PASSWORD not in message


@pytest.mark.parametrize(
    ("field", "value"),
    [
        pytest.param("port", 70000, id="port"),
        pytest.param("connect_timeout", 99, id="connect-timeout"),
    ],
)
def test_settings_rejection_does_not_repeat_a_number(field: str, value: int) -> None:
    with pytest.raises(ValueError) as caught:
        PostgresSettings(**_fields(**{field: value}))

    assert str(value) not in str(caught.value)


def test_password_is_not_in_repr_or_str() -> None:
    settings = PostgresSettings(**_fields())

    assert PASSWORD not in repr(settings)
    assert PASSWORD not in str(settings)
    assert PASSWORD not in f"{settings}"
    assert PASSWORD not in repr([settings])


def test_password_is_not_in_the_repr_of_a_rejection() -> None:
    with pytest.raises(ValueError) as caught:
        PostgresSettings(**_fields(port=70000))

    assert PASSWORD not in repr(caught.value)
    assert PASSWORD not in str(caught.value)
    assert all(PASSWORD not in str(argument) for argument in caught.value.args)
