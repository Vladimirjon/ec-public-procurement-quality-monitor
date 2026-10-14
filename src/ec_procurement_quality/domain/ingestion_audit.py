"""Ingestion audit concepts: the ingestion run, the audit event and JSON values.

An *ingestion run* is the recorded identity, scope and outcome of one ingestion
execution; an *audit event* is one fact appended to a run's history. Scopes and
event details are JSON objects whose values are limited to `None`, `bool`,
`int`, `str`, `list` and `dict`: no `float`, so a value read back from storage
is exactly the value written.

Python's `==` treats `True` as `1` and `False` as `0`, so two JSON values are
compared with `same_json`, which also tells their types apart at every depth.
"""

import copy
import enum
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from ec_procurement_quality.domain.raw_evidence import validate_execution_id

type JsonValue = None | bool | int | str | list[JsonValue] | dict[str, JsonValue]


def _check_json(value: object) -> None:
    """Raise `ValueError` unless `value` is a JSON value under the rule above."""
    if value is None or isinstance(value, bool | int | str):
        return
    if isinstance(value, list):
        for item in value:
            _check_json(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(  # noqa: TRY004 (ValueError is the pinned error)
                    "a JSON object must have text keys"
                )
            _check_json(item)
        return
    raise ValueError("a JSON value must be None, bool, int, str, list or dict of those")


def _same(left: object, right: object) -> bool:
    # Both arguments already satisfy the JSON rule.
    if left is None or right is None:
        return left is None and right is None
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if isinstance(left, int):
        return isinstance(right, int) and left == right
    if isinstance(left, str):
        return isinstance(right, str) and left == right
    if isinstance(left, list):
        return (
            isinstance(right, list)
            and len(left) == len(right)
            and all(_same(a, b) for a, b in zip(left, right, strict=True))
        )
    if isinstance(left, dict):
        return (
            isinstance(right, dict)
            and left.keys() == right.keys()
            and all(_same(item, right[key]) for key, item in left.items())
        )
    return False


def same_json(left: object, right: object) -> bool:
    """Return whether two JSON values are the same, types included.

    `True` is not `1` and `False` is not `0` at any depth; key order does not
    matter and list order does. A value outside the JSON rule (a `float`, a
    `tuple`, a non-text key) raises `ValueError`.
    """
    _check_json(left)
    _check_json(right)
    return _same(left, right)


def _json_object(value: object, field: str) -> dict[str, JsonValue]:
    """Return a copy of `value` if it is a JSON object, else raise `ValueError`."""
    if not isinstance(value, dict):
        raise ValueError(  # noqa: TRY004 (ValueError is the pinned error)
            f"{field} must be a JSON object"
        )
    try:
        _check_json(value)
    except ValueError:
        raise ValueError(
            f"{field} must be a JSON object of None, bool, int, str, list and dict"
        ) from None
    copied: dict[str, JsonValue] = copy.deepcopy(value)
    return copied


def _has_utc_offset(value: object) -> bool:
    return isinstance(value, datetime) and value.utcoffset() is not None


class RunStatus(enum.StrEnum):
    """The state of an ingestion run."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, eq=False)
class IngestionRun:
    """Immutable record of one ingestion run.

    Two runs are equal when their identity, status and times are equal (times
    by instant) and their scopes are the same JSON value (`same_json`).
    """

    execution_id: str
    scope: Mapping[str, JsonValue]
    started_at: datetime
    status: RunStatus
    finished_at: datetime | None

    def __post_init__(self) -> None:
        validate_execution_id(self.execution_id)
        object.__setattr__(self, "scope", _json_object(self.scope, "a scope"))
        if not _has_utc_offset(self.started_at):
            raise ValueError("a start time must carry a UTC offset")
        if self.finished_at is not None and not _has_utc_offset(self.finished_at):
            raise ValueError("a finish time must carry a UTC offset")
        if not isinstance(self.status, RunStatus):
            raise ValueError(  # noqa: TRY004 (ValueError is the pinned error)
                "a status must be a RunStatus"
            )
        if (self.finished_at is None) != (self.status is RunStatus.RUNNING):
            raise ValueError(
                "a finish time is required exactly when the run is not running"
            )
        if self.finished_at is not None and self.finished_at < self.started_at:
            raise ValueError("a finish time must not be before the start time")

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, IngestionRun):
            return NotImplemented
        return (
            self.execution_id == other.execution_id
            and self.status == other.status
            and self.started_at == other.started_at
            and self.finished_at == other.finished_at
            and same_json(dict(self.scope), dict(other.scope))
        )

    # Defining `__eq__` makes the class unhashable, as the plan allows.
    __hash__ = None  # type: ignore[assignment]


@dataclass(frozen=True, eq=False)
class AuditEvent:
    """Immutable record of one audit event appended to a run.

    Two events are equal when their other fields are equal and their details
    are the same JSON value (`same_json`).
    """

    event_id: int
    execution_id: str
    occurred_at: datetime
    event_type: str
    detail: Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.event_id, int)
            or isinstance(self.event_id, bool)
            or self.event_id < 1
        ):
            raise ValueError("an event id must be an integer of at least 1")
        validate_execution_id(self.execution_id)
        if not _has_utc_offset(self.occurred_at):
            raise ValueError("an occurrence time must carry a UTC offset")
        if not isinstance(self.event_type, str) or not self.event_type:
            raise ValueError("an event type must be a non-empty string")
        object.__setattr__(self, "detail", _json_object(self.detail, "a detail"))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AuditEvent):
            return NotImplemented
        return (
            self.event_id == other.event_id
            and self.execution_id == other.execution_id
            and self.occurred_at == other.occurred_at
            and self.event_type == other.event_type
            and same_json(dict(self.detail), dict(other.detail))
        )

    # Defining `__eq__` makes the class unhashable, as the plan allows.
    __hash__ = None  # type: ignore[assignment]
