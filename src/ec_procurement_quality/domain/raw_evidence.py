"""Raw evidence concepts: the observation record and the evidence errors.

An *observation* is the metadata record of one response obtained by an
ingestion execution (ADR 0005). The response bytes themselves are identified by
their `ContentHash`; the observation never holds them.
"""

import re
from dataclasses import dataclass
from datetime import datetime

from ec_procurement_quality.domain.content_hash import ContentHash

_EXECUTION_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
_MIN_STATUS = 100
_MAX_STATUS = 599
_SET_COOKIE = "set-cookie"


class RawEvidenceError(Exception):
    """Base class for raw evidence failures."""


class EvidenceIntegrityError(RawEvidenceError):
    """Stored evidence does not match its identity, or conflicts with new data."""


class EvidenceNotFoundError(RawEvidenceError):
    """The requested evidence is not in the store."""


def _is_plain_int(value: object) -> bool:
    # `bool` is a subclass of `int`; a flag is never a valid number here.
    return isinstance(value, int) and not isinstance(value, bool)


def _is_header_pair(pair: object) -> bool:
    return (
        isinstance(pair, tuple)
        and len(pair) == 2
        and isinstance(pair[0], str)
        and isinstance(pair[1], str)
    )


def validate_execution_id(execution_id: str) -> str:
    """Return `execution_id` if it is 1 to 64 of `a-z`, `0-9`, `-`, not leading `-`."""
    if (
        not isinstance(execution_id, str)
        or _EXECUTION_ID.fullmatch(execution_id) is None
    ):
        raise ValueError(
            "an execution id must be 1 to 64 characters from a-z, 0-9 and '-', "
            "and must not start with '-'"
        )
    return execution_id


def validate_sequence(sequence: int) -> int:
    """Return `sequence` if it is a non-negative integer (a `bool` is rejected)."""
    if not _is_plain_int(sequence) or sequence < 0:
        raise ValueError("a sequence must be a non-negative integer")
    return sequence


@dataclass(frozen=True)
class Observation:
    """Immutable record of one response obtained by an ingestion execution."""

    execution_id: str
    sequence: int
    method: str
    url: str
    status: int
    headers: tuple[tuple[str, str], ...]
    captured_at: datetime
    content_hash: ContentHash
    size: int

    def __post_init__(self) -> None:
        validate_execution_id(self.execution_id)
        validate_sequence(self.sequence)
        if not isinstance(self.method, str) or not self.method:
            raise ValueError("a method must be a non-empty string")
        if not isinstance(self.url, str) or not self.url:
            raise ValueError("a url must be a non-empty string")
        if (
            not _is_plain_int(self.status)
            or not _MIN_STATUS <= self.status <= _MAX_STATUS
        ):
            raise ValueError("a status must be an integer from 100 to 599")
        self._validate_headers()
        if (
            not isinstance(self.captured_at, datetime)
            or self.captured_at.utcoffset() is None
        ):
            raise ValueError("a capture time must carry a UTC offset")
        if not isinstance(self.content_hash, ContentHash):
            raise TypeError("a content hash must be a ContentHash")
        if not _is_plain_int(self.size) or self.size < 0:
            raise ValueError("a size must be a non-negative integer")

    def _validate_headers(self) -> None:
        if not isinstance(self.headers, tuple) or not all(
            _is_header_pair(pair) for pair in self.headers
        ):
            raise ValueError("headers must be a tuple of (name, value) pairs of text")
        if any(name.lower() == _SET_COOKIE for name, _ in self.headers):
            raise ValueError("Set-Cookie headers are never kept as evidence")
