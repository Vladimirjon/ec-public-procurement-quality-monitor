"""Feature raw-evidence-store (F1), AC5 (domain part), AC10, outcome O2.

`Observation` is the immutable metadata record of one obtained response. It
validates its own invariants at construction (execution id pattern, sequence,
method, URL, status range, UTC offset, size, no `Set-Cookie` header). The
evidence errors share a common base. All data is synthetic; URLs use the
reserved `.invalid` domain.
"""

from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest

from ec_procurement_quality.domain.content_hash import ContentHash
from ec_procurement_quality.domain.raw_evidence import (
    EvidenceIntegrityError,
    EvidenceNotFoundError,
    Observation,
    RawEvidenceError,
)

ABC_HEXDIGEST = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
URL = "https://source.invalid/api/search?year=2025&page=1"
CAPTURED_AT = datetime(2026, 10, 9, 10, 15, tzinfo=timezone(timedelta(hours=-5)))


def _fields(**overrides: Any) -> dict[str, Any]:
    """Valid keyword arguments for `Observation`, with `overrides` applied."""
    fields: dict[str, Any] = {
        "execution_id": "synthetic-exec-001",
        "sequence": 1,
        "method": "GET",
        "url": URL,
        "status": 200,
        "headers": (("Content-Type", "application/json"),),
        "captured_at": CAPTURED_AT,
        "content_hash": ContentHash(ABC_HEXDIGEST),
        "size": 3,
    }
    fields.update(overrides)
    return fields


def test_observation_keeps_the_given_attributes() -> None:
    observation = Observation(**_fields())

    assert observation.execution_id == "synthetic-exec-001"
    assert observation.sequence == 1
    assert observation.method == "GET"
    assert observation.url == URL
    assert observation.status == 200
    assert observation.headers == (("Content-Type", "application/json"),)
    assert observation.captured_at == CAPTURED_AT
    assert observation.captured_at.utcoffset() == timedelta(hours=-5)
    assert observation.content_hash == ContentHash(ABC_HEXDIGEST)
    assert observation.size == 3


def test_observations_with_the_same_fields_are_equal() -> None:
    assert Observation(**_fields()) == Observation(**_fields())


def test_observations_with_different_fields_are_different() -> None:
    assert Observation(**_fields()) != Observation(**_fields(status=503))


def test_observation_cannot_be_modified() -> None:
    observation = Observation(**_fields())

    # "Immutable": the plan does not fix which exception type signals it.
    with pytest.raises(Exception):  # noqa: B017
        setattr(observation, "status", 500)  # noqa: B010

    assert observation.status == 200


def test_evidence_errors_share_a_common_base() -> None:
    assert issubclass(RawEvidenceError, Exception)
    assert issubclass(EvidenceIntegrityError, RawEvidenceError)
    assert issubclass(EvidenceNotFoundError, RawEvidenceError)
    with pytest.raises(RawEvidenceError):
        raise EvidenceIntegrityError("synthetic integrity failure")
    with pytest.raises(RawEvidenceError):
        raise EvidenceNotFoundError("synthetic missing evidence")


# --- Set-Cookie (AC5, domain part) -----------------------------------------


@pytest.mark.parametrize(
    "name", ["Set-Cookie", "set-cookie", "SET-COOKIE", "sEt-CoOkIe"]
)
def test_observation_with_set_cookie_header_is_rejected(name: str) -> None:
    headers = (("Content-Type", "application/json"), (name, "synthetic-session=s1"))

    with pytest.raises(ValueError):
        Observation(**_fields(headers=headers))


def test_observation_accepts_headers_that_are_not_exactly_set_cookie() -> None:
    headers = (("X-Set-Cookie-Count", "0"), ("Cookie-Policy", "none"))

    observation = Observation(**_fields(headers=headers))

    assert observation.headers == headers


def test_observation_keeps_repeated_header_names_in_order() -> None:
    headers = (
        ("X-RateLimit-Remaining", "7"),
        ("Content-Type", "application/json"),
        ("X-RateLimit-Remaining", "6"),
    )

    assert Observation(**_fields(headers=headers)).headers == headers


# --- Valid boundaries -------------------------------------------------------


@pytest.mark.parametrize(
    "execution_id",
    ["a", "0", "synthetic-exec-001", "1-2", "a" * 64],
)
def test_observation_accepts_execution_ids_matching_the_pattern(
    execution_id: str,
) -> None:
    assert (
        Observation(**_fields(execution_id=execution_id)).execution_id == execution_id
    )


@pytest.mark.parametrize("sequence", [0, 1, 12])
def test_observation_accepts_non_negative_integer_sequences(sequence: int) -> None:
    assert Observation(**_fields(sequence=sequence)).sequence == sequence


@pytest.mark.parametrize("status", [100, 200, 429, 503, 599])
def test_observation_accepts_any_status_from_100_to_599(status: int) -> None:
    assert Observation(**_fields(status=status)).status == status


@pytest.mark.parametrize(
    "captured_at",
    [
        datetime(2026, 10, 9, 15, 15, tzinfo=UTC),
        datetime(2026, 10, 9, 10, 15, tzinfo=timezone(timedelta(hours=-5))),
        datetime(2026, 10, 9, 20, 45, tzinfo=timezone(timedelta(hours=5, minutes=30))),
    ],
)
def test_observation_accepts_capture_times_with_a_utc_offset(
    captured_at: datetime,
) -> None:
    assert Observation(**_fields(captured_at=captured_at)).captured_at == captured_at


def test_observation_accepts_an_empty_body_size() -> None:
    assert Observation(**_fields(size=0)).size == 0


# --- Invalid input (AC10) ---------------------------------------------------


@pytest.mark.parametrize(
    "execution_id",
    [
        pytest.param("../escape", id="path-traversal"),
        pytest.param("Synthetic-Exec", id="uppercase"),
        pytest.param("", id="empty"),
        pytest.param("a" * 65, id="65-characters"),
        pytest.param("-synthetic-exec", id="leading-hyphen"),
        pytest.param("synthetic_exec", id="underscore"),
        pytest.param("synthetic exec", id="space"),
        pytest.param("synthetic/exec", id="slash"),
        pytest.param("synthetic\\exec", id="backslash"),
        pytest.param("synthetic-exec-001\n", id="trailing-newline"),
        pytest.param("synthetic-exec-٣", id="non-ascii-digit"),
    ],
)
def test_observation_with_invalid_execution_id_is_rejected(execution_id: str) -> None:
    with pytest.raises(ValueError):
        Observation(**_fields(execution_id=execution_id))


@pytest.mark.parametrize(
    "sequence",
    [
        pytest.param(-1, id="negative"),
        pytest.param(True, id="bool"),
        pytest.param(1.0, id="float"),
        pytest.param("1", id="text"),
    ],
)
def test_observation_with_invalid_sequence_is_rejected(sequence: Any) -> None:
    with pytest.raises(ValueError):
        Observation(**_fields(sequence=sequence))


def test_observation_with_invalid_empty_method_is_rejected() -> None:
    with pytest.raises(ValueError):
        Observation(**_fields(method=""))


def test_observation_with_invalid_empty_url_is_rejected() -> None:
    with pytest.raises(ValueError):
        Observation(**_fields(url=""))


@pytest.mark.parametrize("status", [99, 0, -1, 600, 1000])
def test_observation_with_invalid_status_is_rejected(status: int) -> None:
    with pytest.raises(ValueError):
        Observation(**_fields(status=status))


def test_observation_with_invalid_naive_capture_time_is_rejected() -> None:
    with pytest.raises(ValueError):
        Observation(**_fields(captured_at=datetime(2026, 10, 9, 10, 15)))  # noqa: DTZ001


def test_observation_with_invalid_negative_size_is_rejected() -> None:
    with pytest.raises(ValueError):
        Observation(**_fields(size=-1))
