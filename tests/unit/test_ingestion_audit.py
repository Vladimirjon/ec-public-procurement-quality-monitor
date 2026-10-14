"""Feature postgres-persistence (F3), outcome O3 (AC7, AC9, AC10): the run, the
audit event, the run status, the JSON comparison and the persistence errors.

All of these live in `domain`, need no database and open no socket. The module
names are the ones pinned in `execution-plan.md` § Binding constraints:
`ec_procurement_quality.domain.ingestion_audit` and
`ec_procurement_quality.domain.persistence_errors`. Data is synthetic.

The central rule is `same_json`: two JSON values are the same only when their
types are the same at every depth, so `True` is not `1` and `False` is not `0`
(Python's own `==` says otherwise). Key order never matters; list order does.
Records compare their scope and detail with it.
"""

import socket
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, NoReturn

import pytest

from ec_procurement_quality.domain.ingestion_audit import (
    AuditEvent,
    IngestionRun,
    RunStatus,
    same_json,
)
from ec_procurement_quality.domain.persistence_errors import (
    MigrationError,
    PersistenceConnectionError,
    PersistenceError,
    PersistenceIntegrityError,
    PersistenceNotFoundError,
)

EXECUTION_ID = "synthetic-exec-001"
STARTED_AT = datetime(2026, 10, 9, 10, 15, tzinfo=timezone(timedelta(hours=-5)))
FINISHED_AT = datetime(2026, 10, 9, 10, 15, 42, tzinfo=timezone(timedelta(hours=-5)))
SCOPE = {"source": "synthetic", "year": 2025}


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


def _run_fields(**overrides: Any) -> dict[str, Any]:
    """Valid keyword arguments for a `running` `IngestionRun`."""
    fields: dict[str, Any] = {
        "execution_id": EXECUTION_ID,
        "scope": {"source": "synthetic", "year": 2025},
        "started_at": STARTED_AT,
        "status": RunStatus.RUNNING,
        "finished_at": None,
    }
    fields.update(overrides)
    return fields


def _finished_fields(**overrides: Any) -> dict[str, Any]:
    """Valid keyword arguments for a `succeeded` `IngestionRun`."""
    return _run_fields(
        **{"status": RunStatus.SUCCEEDED, "finished_at": FINISHED_AT, **overrides}
    )


def _event_fields(**overrides: Any) -> dict[str, Any]:
    """Valid keyword arguments for an `AuditEvent`."""
    fields: dict[str, Any] = {
        "event_id": 1,
        "execution_id": EXECUTION_ID,
        "occurred_at": STARTED_AT,
        "event_type": "synthetic-run-started",
        "detail": {"page": 1},
    }
    fields.update(overrides)
    return fields


# --- same_json (AC7, AC9) ---------------------------------------------------


@pytest.mark.parametrize(
    ("left", "right"),
    [
        pytest.param(None, None, id="none"),
        pytest.param(True, True, id="true"),
        pytest.param(False, False, id="false"),
        pytest.param(0, 0, id="zero"),
        pytest.param(10**30, 10**30, id="big-int"),
        pytest.param("a", "a", id="str"),
        pytest.param("", "", id="empty-str"),
        pytest.param([], [], id="empty-list"),
        pytest.param({}, {}, id="empty-dict"),
        pytest.param([1, "a", None, True], [1, "a", None, True], id="list"),
        pytest.param({"b": 1, "a": 2}, {"a": 2, "b": 1}, id="key-order-ignored"),
        pytest.param(
            {"x": [1, {"y": True}]}, {"x": [1, {"y": True}]}, id="nested-equal"
        ),
    ],
)
def test_same_json_is_true_for_the_same_json_value(left: Any, right: Any) -> None:
    assert same_json(left, right) is True
    assert same_json(right, left) is True


def test_same_json_is_true_for_a_value_and_itself() -> None:
    value = {"x": [1, {"y": True}], "z": None}

    assert same_json(value, value) is True


@pytest.mark.parametrize(
    ("left", "right"),
    [
        pytest.param(1, True, id="one-is-not-true"),
        pytest.param(0, False, id="zero-is-not-false"),
        pytest.param({"x": 1}, {"x": True}, id="nested-one-is-not-true"),
        pytest.param({"x": [1]}, {"x": [True]}, id="list-item-one-is-not-true"),
        pytest.param({"x": {"y": 0}}, {"x": {"y": False}}, id="deep-zero-is-not-false"),
        pytest.param([1, 2], [2, 1], id="list-order-matters"),
        pytest.param(1, "1", id="number-is-not-text"),
        pytest.param([], {}, id="list-is-not-dict"),
        pytest.param(None, False, id="none-is-not-false"),
        pytest.param([1], [1, 2], id="list-length"),
        pytest.param({"a": 1}, {"a": 1, "b": 2}, id="extra-key"),
        pytest.param({"a": 1}, {"b": 1}, id="other-key"),
        pytest.param("a", "b", id="other-text"),
        pytest.param(1, 2, id="other-number"),
    ],
)
def test_same_json_is_false_when_the_types_or_values_differ(
    left: Any, right: Any
) -> None:
    assert same_json(left, right) is False
    assert same_json(right, left) is False


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(1.5, id="float"),
        pytest.param(2025.0, id="whole-float"),
        pytest.param(float("nan"), id="nan"),
        pytest.param(float("inf"), id="infinity"),
        pytest.param((1, 2), id="tuple"),
        pytest.param({1, 2}, id="set"),
        pytest.param({1: "x"}, id="non-str-key"),
        pytest.param({"a": [1.0]}, id="nested-float"),
        pytest.param({"a": (1,)}, id="nested-tuple"),
    ],
)
def test_same_json_raises_value_error_for_a_value_outside_the_json_rule(
    value: Any,
) -> None:
    with pytest.raises(ValueError):
        same_json(value, value)
    with pytest.raises(ValueError):
        same_json([value], [value])


# --- RunStatus (AC7) --------------------------------------------------------


def test_run_status_has_exactly_the_three_states() -> None:
    assert {member.name: member.value for member in RunStatus} == {
        "RUNNING": "running",
        "SUCCEEDED": "succeeded",
        "FAILED": "failed",
    }


def test_run_status_is_a_string_value() -> None:
    assert RunStatus("succeeded") is RunStatus.SUCCEEDED
    assert RunStatus.RUNNING == "running"
    assert isinstance(RunStatus.FAILED, str)


# --- IngestionRun (AC7, AC10) -----------------------------------------------


def test_ingestion_run_keeps_the_given_attributes() -> None:
    run = IngestionRun(**_run_fields())

    assert run.execution_id == EXECUTION_ID
    assert same_json(run.scope, SCOPE)
    assert run.started_at == STARTED_AT
    assert run.started_at.utcoffset() == timedelta(hours=-5)
    assert run.status is RunStatus.RUNNING
    assert run.finished_at is None


def test_ingestion_run_accepts_a_finished_run() -> None:
    run = IngestionRun(**_finished_fields())

    assert run.status is RunStatus.SUCCEEDED
    assert run.finished_at == FINISHED_AT


def test_ingestion_run_accepts_a_failed_run_finished_at_its_start() -> None:
    run = IngestionRun(
        **_finished_fields(status=RunStatus.FAILED, finished_at=STARTED_AT)
    )

    assert run.status is RunStatus.FAILED
    assert run.finished_at == STARTED_AT


@pytest.mark.parametrize(
    "attribute", ["execution_id", "scope", "started_at", "status", "finished_at"]
)
def test_ingestion_run_attributes_cannot_be_assigned(attribute: str) -> None:
    run = IngestionRun(**_run_fields())

    with pytest.raises((AttributeError, TypeError)):
        setattr(run, attribute, getattr(run, attribute))


def test_ingestion_run_with_the_same_fields_are_equal() -> None:
    assert IngestionRun(**_run_fields()) == IngestionRun(**_run_fields())


def test_ingestion_run_equality_ignores_scope_key_order() -> None:
    first = IngestionRun(**_run_fields(scope={"b": 1, "a": 2}))
    second = IngestionRun(**_run_fields(scope={"a": 2, "b": 1}))

    assert first == second


def test_ingestion_run_equality_compares_the_instant_not_the_offset() -> None:
    same_instant = STARTED_AT.astimezone(UTC)

    assert IngestionRun(**_run_fields()) == IngestionRun(
        **_run_fields(started_at=same_instant)
    )


@pytest.mark.parametrize(
    ("scope", "other"),
    [
        pytest.param({"x": 1}, {"x": True}, id="one-is-not-true"),
        pytest.param({"x": [1]}, {"x": [True]}, id="nested-list"),
        pytest.param({"x": {"y": 0}}, {"x": {"y": False}}, id="nested-dict"),
        pytest.param({"x": [1, 2]}, {"x": [2, 1]}, id="list-order"),
    ],
)
def test_ingestion_runs_with_different_json_scopes_are_not_equal(
    scope: Any, other: Any
) -> None:
    assert IngestionRun(**_run_fields(scope=scope)) != IngestionRun(
        **_run_fields(scope=other)
    )


@pytest.mark.parametrize(
    "change",
    [
        pytest.param({"execution_id": "synthetic-exec-002"}, id="execution-id"),
        pytest.param({"started_at": STARTED_AT + timedelta(seconds=1)}, id="started"),
        pytest.param(
            {"status": RunStatus.FAILED, "finished_at": FINISHED_AT}, id="status"
        ),
    ],
)
def test_ingestion_runs_differing_in_a_field_are_not_equal(
    change: dict[str, Any],
) -> None:
    assert IngestionRun(**_run_fields()) != IngestionRun(**_run_fields(**change))


def test_ingestion_runs_finished_at_different_instants_are_not_equal() -> None:
    first = IngestionRun(**_finished_fields())
    second = IngestionRun(
        **_finished_fields(finished_at=FINISHED_AT + timedelta(seconds=1))
    )

    assert first != second


@pytest.mark.parametrize(
    "fields",
    [
        pytest.param(_run_fields(execution_id="Synthetic-Exec"), id="uppercase-id"),
        pytest.param(_run_fields(execution_id="-x"), id="leading-dash-id"),
        pytest.param(_run_fields(execution_id=""), id="empty-id"),
        pytest.param(_run_fields(execution_id="a" * 65), id="long-id"),
        pytest.param(_run_fields(execution_id=5), id="non-str-id"),
        pytest.param(_run_fields(scope=[]), id="list-scope"),
        pytest.param(_run_fields(scope=None), id="none-scope"),
        pytest.param(_run_fields(scope={"year": 2025.0}), id="float-scope"),
        pytest.param(_run_fields(scope={"year": float("nan")}), id="nan-scope"),
        pytest.param(_run_fields(scope={1: "x"}), id="non-str-key-scope"),
        pytest.param(_run_fields(scope={"pages": (1, 2)}), id="tuple-scope"),
        pytest.param(_run_fields(scope={"pages": {1, 2}}), id="set-scope"),
        pytest.param(
            _run_fields(started_at=datetime(2026, 10, 9, 10, 15)), id="naive-start"
        ),
        pytest.param(_run_fields(started_at="2026-10-09T10:15:00-05:00"), id="text"),
        pytest.param(
            _finished_fields(finished_at=datetime(2026, 10, 9, 10, 16)),
            id="naive-finish",
        ),
        pytest.param(_finished_fields(status="succeeded"), id="plain-str-status"),
        pytest.param(_run_fields(status="running"), id="plain-str-running"),
        pytest.param(_run_fields(finished_at=FINISHED_AT), id="running-finished"),
        pytest.param(_finished_fields(finished_at=None), id="succeeded-unfinished"),
        pytest.param(
            _finished_fields(status=RunStatus.FAILED, finished_at=None),
            id="failed-unfinished",
        ),
        pytest.param(
            _finished_fields(finished_at=STARTED_AT - timedelta(seconds=1)),
            id="finished-before-started",
        ),
    ],
)
def test_invalid_ingestion_run_raises_value_error(fields: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        IngestionRun(**fields)


# --- AuditEvent (AC9, AC10) -------------------------------------------------


def test_audit_event_keeps_the_given_attributes() -> None:
    event = AuditEvent(**_event_fields())

    assert event.event_id == 1
    assert event.execution_id == EXECUTION_ID
    assert event.occurred_at == STARTED_AT
    assert event.event_type == "synthetic-run-started"
    assert same_json(event.detail, {"page": 1})


def test_audit_event_accepts_an_empty_detail() -> None:
    assert same_json(AuditEvent(**_event_fields(detail={})).detail, {})


@pytest.mark.parametrize(
    "attribute", ["event_id", "execution_id", "occurred_at", "event_type", "detail"]
)
def test_audit_event_attributes_cannot_be_assigned(attribute: str) -> None:
    event = AuditEvent(**_event_fields())

    with pytest.raises((AttributeError, TypeError)):
        setattr(event, attribute, getattr(event, attribute))


def test_audit_events_with_the_same_fields_are_equal() -> None:
    assert AuditEvent(**_event_fields()) == AuditEvent(**_event_fields())


def test_audit_event_equality_ignores_detail_key_order() -> None:
    first = AuditEvent(**_event_fields(detail={"a": 1, "b": 2}))
    second = AuditEvent(**_event_fields(detail={"b": 2, "a": 1}))

    assert first == second


@pytest.mark.parametrize(
    ("detail", "other"),
    [
        pytest.param({"page": True}, {"page": 1}, id="true-is-not-one"),
        pytest.param({"page": [0]}, {"page": [False]}, id="nested-zero"),
        pytest.param({"page": [1, 2]}, {"page": [2, 1]}, id="list-order"),
    ],
)
def test_audit_events_with_different_json_details_are_not_equal(
    detail: Any, other: Any
) -> None:
    assert AuditEvent(**_event_fields(detail=detail)) != AuditEvent(
        **_event_fields(detail=other)
    )


@pytest.mark.parametrize(
    "change",
    [
        pytest.param({"event_id": 2}, id="event-id"),
        pytest.param({"execution_id": "synthetic-exec-002"}, id="execution-id"),
        pytest.param({"occurred_at": STARTED_AT + timedelta(seconds=1)}, id="time"),
        pytest.param({"event_type": "synthetic-page-stored"}, id="type"),
    ],
)
def test_audit_events_differing_in_a_field_are_not_equal(
    change: dict[str, Any],
) -> None:
    assert AuditEvent(**_event_fields()) != AuditEvent(**_event_fields(**change))


@pytest.mark.parametrize(
    "fields",
    [
        pytest.param(_event_fields(event_id=0), id="zero-id"),
        pytest.param(_event_fields(event_id=-1), id="negative-id"),
        pytest.param(_event_fields(event_id=True), id="bool-id"),
        pytest.param(_event_fields(event_id="1"), id="text-id"),
        pytest.param(_event_fields(event_id=1.0), id="float-id"),
        pytest.param(_event_fields(execution_id="Synthetic-Exec"), id="bad-run-id"),
        pytest.param(_event_fields(execution_id="-x"), id="leading-dash-run-id"),
        pytest.param(
            _event_fields(occurred_at=datetime(2026, 10, 9, 10, 15)), id="naive-time"
        ),
        pytest.param(_event_fields(event_type=""), id="empty-type"),
        pytest.param(_event_fields(event_type=5), id="non-str-type"),
        pytest.param(_event_fields(detail=[]), id="list-detail"),
        pytest.param(_event_fields(detail=None), id="none-detail"),
        pytest.param(_event_fields(detail={"page": 1.0}), id="float-detail"),
        pytest.param(_event_fields(detail={"page": float("nan")}), id="nan-detail"),
        pytest.param(_event_fields(detail={1: "x"}), id="non-str-key-detail"),
        pytest.param(_event_fields(detail={"pages": (1, 2)}), id="tuple-detail"),
        pytest.param(_event_fields(detail={"pages": {1, 2}}), id="set-detail"),
    ],
)
def test_invalid_audit_event_raises_value_error(fields: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        AuditEvent(**fields)


# --- the JSON object rule (AC10) --------------------------------------------


def test_json_object_rule_accepts_nested_values_of_the_allowed_types() -> None:
    value: dict[str, Any] = {
        "none": None,
        "flag": True,
        "number": -3,
        "big": 10**30,
        "text": "synthetic",
        "list": [None, False, 0, "a", [1], {"k": "v"}],
        "dict": {"inner": {"deeper": []}},
        "": "empty key",
    }

    run = IngestionRun(**_run_fields(scope=value))
    event = AuditEvent(**_event_fields(detail=value))

    assert same_json(run.scope, value)
    assert same_json(event.detail, value)


# --- persistence errors (AC11) ----------------------------------------------


def test_persistence_errors_are_direct_subclasses_of_persistence_error() -> None:
    assert issubclass(PersistenceError, Exception)
    for error in (
        PersistenceConnectionError,
        PersistenceIntegrityError,
        PersistenceNotFoundError,
        MigrationError,
    ):
        assert error.__bases__ == (PersistenceError,)
