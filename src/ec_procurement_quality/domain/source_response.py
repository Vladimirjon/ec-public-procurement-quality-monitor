"""A response received from a source, and the errors a source call can raise.

A `RawResponse` is one HTTP response exactly as received (ADR 0005): the method
and URL as sent, the status, the headers in order and the body bytes, plus the
capture time. Its field names are the keyword names of `RawEvidenceStore.store`,
so a caller can pass them on unchanged.

Every `SourceError` carries the response that was received, when there was one,
so that failed and partial responses can still be kept as evidence. Neither the
response `repr` nor any error message contains body bytes or header values.
"""

from dataclasses import dataclass
from datetime import datetime

_MIN_STATUS = 100
_MAX_STATUS = 599


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


@dataclass(frozen=True, repr=False)
class RawResponse:
    """One HTTP response exactly as received, whatever its status or completeness.

    `Set-Cookie` headers are allowed here; the raw evidence store drops them.
    """

    method: str
    url: str
    status: int
    headers: tuple[tuple[str, str], ...]
    captured_at: datetime
    content: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.method, str) or not self.method:
            raise ValueError("a method must be a non-empty string")
        if not isinstance(self.url, str) or not self.url:
            raise ValueError("a url must be a non-empty string")
        if (
            not _is_plain_int(self.status)
            or not _MIN_STATUS <= self.status <= _MAX_STATUS
        ):
            raise ValueError("a status must be an integer from 100 to 599")
        if not isinstance(self.headers, tuple) or not all(
            _is_header_pair(pair) for pair in self.headers
        ):
            raise ValueError("headers must be a tuple of (name, value) pairs of text")
        if (
            not isinstance(self.captured_at, datetime)
            or self.captured_at.utcoffset() is None
        ):
            raise ValueError("a capture time must carry a UTC offset")
        if not isinstance(self.content, bytes):
            raise TypeError("content must be bytes")

    def __repr__(self) -> str:
        # Sizes only: the body and the header values are never shown.
        return (
            f"RawResponse(method={self.method!r}, url={self.url!r}, "
            f"status={self.status}, headers=<{len(self.headers)} headers>, "
            f"captured_at={self.captured_at.isoformat()!r}, "
            f"content=<{len(self.content)} bytes>)"
        )


class SourceError(Exception):
    """Base class for source failures; `response` is what was received, if anything."""

    def __init__(self, message: str, *, response: RawResponse | None = None) -> None:
        super().__init__(message)
        self.response = response


class SourceTransportError(SourceError):
    """No complete response was obtained.

    `response` is `None` when the failure came before the status and headers
    arrived, or when the status is outside 100 to 599: such a message is not a
    valid HTTP response and a `RawResponse` cannot hold it, so the message names
    the status number instead. Otherwise `response` is a partial response (the
    bytes received so far).
    """


class SourceStatusError(SourceError):
    """A complete response arrived with a status other than 200."""

    response: RawResponse

    def __init__(self, message: str, *, response: RawResponse) -> None:
        super().__init__(message, response=response)


class IncompleteResponseError(SourceError):
    """A complete 200 response whose body is unusable."""

    response: RawResponse

    def __init__(self, message: str, *, response: RawResponse) -> None:
        super().__init__(message, response=response)
