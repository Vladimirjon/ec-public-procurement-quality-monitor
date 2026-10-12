"""Feature sercop-source-adapter (F2), outcome O3: the raw response and source errors.

`RawResponse` is one HTTP response exactly as received, and the four source
errors carry whatever response was received. These tests cover AC8 (nothing
leaks through `repr` and `str`) and the domain part of AC10 (invalid values).
All data is synthetic, URLs use the reserved `.invalid` domain, and nothing
here touches the network.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from ec_procurement_quality.domain.source_response import (
    IncompleteResponseError,
    RawResponse,
    SourceError,
    SourceStatusError,
    SourceTransportError,
)

CAPTURED_AT = datetime(2026, 10, 10, 6, 58, tzinfo=timezone(timedelta(hours=-5)))
NAIVE_TIME = datetime.fromisoformat("2026-10-10T06:58:00")  # no UTC offset
URL = "https://source.invalid/PLATAFORMA/api/record?ocid=ocds-5wno2w-SYNTHETIC-A"
HEADERS = (("Content-Type", "application/json"),)
BODY_MARKER = "synthetic-body-marker"
HEADER_MARKER = "synthetic-header-marker"

ERROR_TYPES = (
    SourceError,
    SourceTransportError,
    SourceStatusError,
    IncompleteResponseError,
)


# --- Helpers ----------------------------------------------------------------


def _fields(**overrides: Any) -> dict[str, Any]:
    """Valid keyword arguments for `RawResponse`, with `overrides` applied.

    Typed as `Any` so that tests can pass deliberately wrong values.
    """
    fields: dict[str, Any] = {
        "method": "GET",
        "url": URL,
        "status": 200,
        "headers": HEADERS,
        "captured_at": CAPTURED_AT,
        "content": b'{"releases":[]}',
    }
    fields.update(overrides)
    return fields


def _response(**overrides: Any) -> RawResponse:
    return RawResponse(**_fields(**overrides))


def _leaky_response() -> RawResponse:
    """A response whose body and header values hold the synthetic markers."""
    return _response(
        content=BODY_MARKER.encode("ascii"),
        headers=(
            ("Content-Type", "application/json"),
            ("X-Synthetic", HEADER_MARKER),
            ("Set-Cookie", f"synthetic-session={HEADER_MARKER}"),
        ),
    )


# --- RawResponse: valid values ----------------------------------------------


def test_raw_response_keeps_every_field_as_given() -> None:
    headers = (("Content-Type", "application/json"), ("X-Synthetic", "a"))

    response = _response(headers=headers, content=b"abc", status=404)

    assert response.method == "GET"
    assert response.url == URL
    assert response.status == 404
    assert response.headers == headers
    assert response.captured_at == CAPTURED_AT
    assert response.captured_at.utcoffset() == timedelta(hours=-5)
    assert response.content == b"abc"


def test_raw_response_is_equal_by_value() -> None:
    assert _response() == _response()
    assert _response() != _response(content=b"other")
    assert _response() != _response(status=500)


@pytest.mark.parametrize(
    "field", ["method", "url", "status", "headers", "captured_at", "content"]
)
def test_raw_response_is_immutable(field: str) -> None:
    response = _response()

    with pytest.raises(AttributeError):
        setattr(response, field, getattr(response, field))


def test_raw_response_accepts_set_cookie_and_repeated_names_in_order() -> None:
    headers = (
        ("Docker-Distribution-Api-Version", "registry/2.0"),
        ("Set-Cookie", "synthetic-session=s1"),
        ("Docker-Distribution-Api-Version", "registry/2.0"),
    )

    response = _response(headers=headers)

    assert response.headers == headers


@pytest.mark.parametrize("status", [100, 200, 599])
def test_raw_response_accepts_statuses_from_100_to_599(status: int) -> None:
    assert _response(status=status).status == status


def test_raw_response_accepts_empty_headers_and_empty_content() -> None:
    response = _response(headers=(), content=b"")

    assert response.headers == ()
    assert response.content == b""


# --- RawResponse: invalid values (AC10, domain part) ------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"method": ""}, id="empty-method"),
        pytest.param({"url": ""}, id="empty-url"),
        pytest.param({"status": 99}, id="status-99"),
        pytest.param({"status": 600}, id="status-600"),
        pytest.param({"status": True}, id="status-bool"),
        pytest.param({"status": 200.0}, id="status-float"),
        pytest.param({"status": "200"}, id="status-text"),
        pytest.param({"captured_at": NAIVE_TIME}, id="naive-time"),
        pytest.param({"headers": [("Content-Type", "application/json")]}, id="list"),
        pytest.param({"headers": (("Content-Type",),)}, id="pair-of-one"),
        pytest.param({"headers": (("a", "b", "c"),)}, id="pair-of-three"),
        pytest.param({"headers": (("a", 1),)}, id="value-not-text"),
        pytest.param({"headers": ((b"a", "b"),)}, id="name-not-text"),
    ],
)
def test_raw_response_invalid_values_raise_value_error(
    overrides: dict[str, Any],
) -> None:
    with pytest.raises(ValueError):
        _response(**overrides)


@pytest.mark.parametrize(
    "content",
    [
        pytest.param("synthetic text", id="text"),
        pytest.param(bytearray(b"abc"), id="bytearray"),
    ],
)
def test_raw_response_invalid_content_raises_type_error(content: Any) -> None:
    with pytest.raises(TypeError):
        _response(content=content)


# --- Source errors ----------------------------------------------------------


def test_source_errors_share_one_base_and_are_distinct() -> None:
    assert issubclass(SourceError, Exception)
    concrete = (SourceTransportError, SourceStatusError, IncompleteResponseError)
    for error_type in concrete:
        assert issubclass(error_type, SourceError)
    for error_type in concrete:
        for other in concrete:
            if error_type is not other:
                assert not issubclass(error_type, other)


def test_source_error_response_defaults_to_none() -> None:
    assert SourceError("synthetic reason").response is None
    assert SourceTransportError("synthetic reason").response is None


@pytest.mark.parametrize("error_type", ERROR_TYPES)
def test_source_error_carries_the_response_and_the_message(
    error_type: type[SourceError],
) -> None:
    response = _response()

    error = error_type("synthetic reason", response=response)

    assert error.response == response
    assert "synthetic reason" in str(error)


@pytest.mark.parametrize("error_type", ERROR_TYPES)
def test_source_error_is_caught_by_its_base(error_type: type[SourceError]) -> None:
    with pytest.raises(SourceError):
        raise error_type("synthetic reason", response=_response())


@pytest.mark.parametrize("error_type", [SourceStatusError, IncompleteResponseError])
def test_source_error_invalid_without_response_raises_type_error(
    error_type: type[SourceError],
) -> None:
    with pytest.raises(TypeError):
        error_type("synthetic reason")


# --- No content in representations (AC8) ------------------------------------


def test_raw_response_no_leak_in_repr_and_str() -> None:
    response = _leaky_response()

    for text in (repr(response), str(response), f"{response!r}", f"{response}"):
        assert BODY_MARKER not in text
        assert HEADER_MARKER not in text


@pytest.mark.parametrize("error_type", ERROR_TYPES)
def test_source_error_no_leak_in_repr_and_str(error_type: type[SourceError]) -> None:
    response = _leaky_response()
    error = error_type("fixed reason", response=response)

    texts = [repr(error), str(error), repr(error.response), str(error.response)]
    texts.extend(repr(argument) for argument in error.args)

    for text in texts:
        assert BODY_MARKER not in text
        assert HEADER_MARKER not in text
