"""SERCOP adapter for the `ProcurementSource` port, on a synchronous `httpx.Client`.

One call sends exactly one GET request and ends in one of six ways (see
`_outcome`): no response, a status outside 100 to 599, a cut-off body, a status
other than 200, an unusable 200, or a checked result. Every error carries the
response that was received (none for the first two), so the caller can store
failed and partial responses as evidence (ADR 0005).

The adapter never retries; it only spaces requests (see "Pacing"). It creates no
logger and prints nothing, and no message holds body bytes or header values.
Anything that is not a source outcome (an interrupt, a defect of an injected
transport or clock) propagates unchanged and is never wrapped.

The HTTP client is kept from processing anything the source sends beyond the
status, the headers and the body: no cookie is parsed or replayed and `Location`
is never read by the client (see `_NoCookieJar` and `_capture_response`).

File order: defaults, input validation, request URLs and the base URL checks,
the class (constructor, public calls, URL building, pacing, the single request,
close), then the outcome mapping and the completeness checks as plain functions.
"""

import json
import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from http.cookiejar import CookieJar
from typing import Any, Never, Self
from urllib.parse import quote, urlsplit

import httpx

from ec_procurement_quality.application.procurement_source import (
    RecordResponse,
    SearchPage,
)
from ec_procurement_quality.domain.source_response import (
    IncompleteResponseError,
    RawResponse,
    SourceStatusError,
    SourceTransportError,
)

# --- (a) Defaults and constants ---------------------------------------------

# Observed in docs/sources/sercop-observations.md, section "Confirmed search endpoint".
DEFAULT_BASE_URL = "https://datosabiertos.compraspublicas.gob.ec/PLATAFORMA"

_SEARCH_OPERATION = "search_ocds"
_RECORD_OPERATION = "record"
_STATUS_OK = 200
_STATUS_TOO_MANY_REQUESTS = 429
# The statuses `RawResponse` accepts (RE-11). No `RawResponse` is built outside.
_MIN_STATUS = 100
_MAX_STATUS = 599
_REMAINING_HEADER = "x-ratelimit-remaining"
# The largest number of seconds a timeout, interval or cool-down may be (project
# decision, one day). A socket accepts less than 2,147,483.647 s on Windows.
_MAX_SECONDS = 86_400
# RFC 1035 section 2.3.4: a label of 63 characters at most, a name of 253
# without its trailing dot.
_MAX_HOST_LABEL = 63
_MAX_HOST_NAME = 253


def _local_now() -> datetime:
    """The current local time, with its UTC offset."""
    return datetime.now().astimezone()


# --- (b) Input validation ---------------------------------------------------


def _require_positive_int(value: object, name: str) -> None:
    # `bool` is a subclass of `int`; a flag is never a valid year or page.
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{name} must be an integer of 1 or more")


def _require_text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")


def _require_seconds(value: object, name: str, *, positive: bool) -> None:
    """A number of seconds: an `int` or `float`, finite, at most one day.

    `nan` switches pacing off, and `inf` or a very large value fails every call
    in the socket layer or in `time.sleep` with an error nothing maps.
    """
    if (
        isinstance(value, bool)  # a flag is not a number of seconds
        or not isinstance(value, int | float)
        or (isinstance(value, float) and not math.isfinite(value))
    ):
        raise ValueError(f"{name} must be a finite number")
    if value > _MAX_SECONDS:
        raise ValueError(f"{name} must not be more than {_MAX_SECONDS} seconds")
    if positive and value <= 0:
        raise ValueError(f"{name} must be positive")
    if not positive and value < 0:
        raise ValueError(f"{name} must not be negative")


def _is_port(text: str) -> bool:
    # 1 to 5 ASCII digits with a value of 1 to 65535. `isdigit` alone would
    # accept "٣", which the HTTP library reads as port 3.
    return (
        text.isascii() and text.isdigit() and len(text) <= 5 and 1 <= int(text) <= 65535
    )


# --- (c) Request URLs and the checks of the base URL ------------------------
# The URL is a literal string, sent unchanged. `params=` would write spaces as
# `+`, and the observed query uses `%20`.


def _search_url(base_url: str, year: int, buyer: str, page: int) -> str:
    """The observed query: `local=1`, `year`, `page`, `buyer`, in this order."""
    encoded_buyer = quote(buyer, safe="")
    return (
        f"{base_url}/api/search_ocds"
        f"?local=1&year={year}&page={page}&buyer={encoded_buyer}"
    )


def _record_url(base_url: str, ocid: str) -> str:
    return f"{base_url}/api/record?ocid={quote(ocid, safe='')}"


def _host_problem(host: str) -> str | None:
    """Why `host`, as name resolution and TLS receive it, is not acceptable.

    `host` is the library's ASCII form (IDNA-encoded for a non-ASCII host, an
    IPv6 literal without its brackets). Python's `idna` codec, which
    `getaddrinfo` and `ssl` apply to it, raises an error that nothing maps for an
    empty label or one of 64 characters or more.
    """
    if ":" in host and "%" in host:
        # A zone names a local network interface (RFC 6874), and its text would
        # reach name resolution and TLS unchanged.
        return "must not hold an IPv6 zone identifier"
    name = host.removesuffix(".")  # one trailing dot is allowed
    if len(name) > _MAX_HOST_NAME:
        return "must have a host of at most 253 characters"
    for label in name.split("."):
        if not label or len(label) > _MAX_HOST_LABEL:
            return "must have host labels of 1 to 63 characters"
    return None


def _library_accepts(url: str) -> bool:
    try:
        httpx.URL(url)
    except (httpx.InvalidURL, ValueError):
        return False
    return True


def _base_url_problem(base_url: str) -> str | None:
    """Why `base_url` is not acceptable, or `None` when it is.

    The reasons are fixed text. What the parsers say is never passed on: their
    messages can repeat the URL, and with it any user information.
    """
    try:
        parts = urlsplit(base_url)
    except ValueError:  # for example an invalid IPv6 literal
        return "must be an absolute http or https URL"
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return "must be an absolute http or https URL"
    if base_url.endswith("/") or "?" in base_url or "#" in base_url:
        return "must not end with '/' or hold a query or fragment"
    # User information would become an `Authorization` header and stay in the
    # URL as sent (ADR 0003). Even an empty one (`https://@host`) is refused.
    if "@" in parts.netloc:
        return "must not hold user information"
    if not parts.hostname:
        return "must have a host"
    # What follows the host: nothing, or ":" and the port. `rfind("]")` steps
    # over an IPv6 literal, whose own colons are not a port separator.
    after_host = parts.netloc[parts.netloc.rfind("]") + 1 :]
    _, colon, port = after_host.partition(":")
    if colon and not _is_port(port):
        return "must have a port from 1 to 65535"
    # Last, the HTTP library's own parse, so that no call fails on the URL later.
    try:
        url = httpx.URL(base_url)
    except (httpx.InvalidURL, ValueError):
        return "is not accepted by the HTTP library"
    try:
        _ = url.host  # decodes a first label `xn--` (every request reads it)
    except ValueError:  # `idna.IDNAError`, which is not an `httpx` exception
        return "must have a host that the HTTP library can decode"
    problem = _host_problem(url.raw_host.decode("ascii"))
    if problem is not None:
        return problem
    # Room for the shortest request of each operation, checked by the library
    # so that the rule follows its own limit on the length of a URL.
    shortest = (_search_url(base_url, 1, "a", 1), _record_url(base_url, "a"))
    if not all(_library_accepts(request_url) for request_url in shortest):
        return "must leave room for the request URL"
    return None


def _require_base_url(base_url: str) -> None:
    problem = _base_url_problem(base_url)
    if problem is not None:
        raise ValueError(f"base_url {problem}")


# --- What one request produced ----------------------------------------------


@dataclass
class _Capture:
    """What the response hook saw of one response, filled in as it arrives.

    The status and headers are set before the body is read, so pacing can use
    them even when the read is interrupted. No `RawResponse` is built here: a
    status outside 100 to 599 would make that raise inside the HTTP client.
    """

    status: int | None = None  # `None`: no status arrived
    headers: tuple[tuple[str, str], ...] = ()
    body: bytearray = field(default_factory=bytearray)
    failure: httpx.HTTPError | None = None  # sending or reading the body failed


@dataclass(frozen=True)
class _Attempt:
    """The result of one request.

    `status` is `None` when the failure came before the status arrived.
    `response` is `None` then, and also when the status is outside 100 to 599.
    `failure` is set when sending or reading the body failed.
    """

    status: int | None
    response: RawResponse | None
    failure: httpx.HTTPError | None


class _NoCookieJar(CookieJar):
    """A cookie jar that takes nothing from a response and so stays empty.

    The client calls `extract_cookies` on every response, which parses each
    `Set-Cookie` value and, when `http.cookiejar` fails on one, issues a
    warning with a traceback. Here nothing is parsed and no `Cookie` header is
    ever built. `Set-Cookie` stays in the raw headers exactly as received.
    """

    def extract_cookies(self, response: object, request: object) -> None:
        return None


class SercopSource:
    """Reads search pages and records from the SERCOP portal."""

    # --- (a) Constructor and the two public calls ---------------------------

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        transport: httpx.BaseTransport | None = None,
        connect_timeout: float = 10.0,
        read_timeout: float = 30.0,
        min_interval: float = 5.0,
        low_remaining_threshold: int = 20,
        cooldown: float = 60.0,
        now: Callable[[], datetime] = _local_now,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        _require_base_url(base_url)
        _require_seconds(connect_timeout, "connect_timeout", positive=True)
        _require_seconds(read_timeout, "read_timeout", positive=True)
        _require_seconds(min_interval, "min_interval", positive=False)
        _require_seconds(cooldown, "cooldown", positive=False)
        if (
            not isinstance(low_remaining_threshold, int)
            or isinstance(low_remaining_threshold, bool)
            or low_remaining_threshold < 0
        ):
            raise ValueError("low_remaining_threshold must be a non-negative integer")
        self._base_url = base_url
        self._min_interval = min_interval
        self._low_remaining_threshold = low_remaining_threshold
        self._cooldown = cooldown
        self._now = now
        self._monotonic = monotonic
        self._sleep = sleep
        # Pacing state, in memory only: when the last attempt ended, and whether
        # the source asked for the longer wait.
        self._last_attempt_end: float | None = None
        self._cooldown_required = False
        # What the response hook captured of the response being read.
        self._capture = _Capture()
        self._client = httpx.Client(
            transport=transport,
            timeout=httpx.Timeout(
                connect=connect_timeout,
                read=read_timeout,
                write=connect_timeout,
                pool=connect_timeout,
            ),
            headers={"Accept-Encoding": "identity"},
            follow_redirects=False,
            # Never stores a cookie, so none is parsed and none is sent.
            cookies=_NoCookieJar(),
            # The client calls this hook as soon as a response arrives, before it
            # looks at `Location` (see `_capture_response`).
            event_hooks={"response": [self._capture_response]},
        )

    # Each call: the closed check, the argument checks, the request is built,
    # then the pacing wait and the send. Invalid input never waits.

    def search_page(self, *, year: int, buyer: str, page: int) -> SearchPage:
        """Ask for one page of the buyer-name search (one request)."""
        self._require_open()
        _require_positive_int(year, "year")
        _require_positive_int(page, "page")
        _require_text(buyer, "buyer")
        request = self._build_request(
            _search_url(self._base_url, year, buyer, page), _SEARCH_OPERATION
        )
        attempt = self._attempt(request)
        return _outcome(
            attempt,
            _SEARCH_OPERATION,
            lambda response: _search_page_if_complete(response, page),
        )

    def fetch_record(self, ocid: str) -> RecordResponse:
        """Ask for one record by `ocid` (one request)."""
        self._require_open()
        _require_text(ocid, "ocid")
        request = self._build_request(
            _record_url(self._base_url, ocid), _RECORD_OPERATION
        )
        attempt = self._attempt(request)
        return _outcome(
            attempt,
            _RECORD_OPERATION,
            lambda response: _record_if_complete(response, ocid),
        )

    # --- (c) Building the request --------------------------------------------

    def _build_request(self, url: str, operation: str) -> httpx.Request:
        """Build the GET, before any wait. A URL the library rejects is invalid input."""
        try:
            return self._client.build_request("GET", url)
        except httpx.InvalidURL:
            pass  # the base URL was checked, so only a too long URL is left
        # Raised outside the `except` block: the library's text is not chained.
        raise ValueError(
            f"{operation}: the request URL is too long for the HTTP client"
        )

    # --- (d) Pacing ----------------------------------------------------------
    # `X-RateLimit-Remaining` is advice only: its window and key are unknown.

    def _attempt(self, request: httpx.Request) -> _Attempt:
        """Wait if due, send one request, then note how the attempt ended."""
        self._wait_if_due()
        self._capture = _Capture()
        try:
            self._send(request)
        finally:
            # Every attempt counts, whatever ends it, `KeyboardInterrupt` included.
            self._last_attempt_end = self._monotonic()
            self._cooldown_required = self._asks_for_cooldown(self._capture)
        return self._attempt_from_capture(request)

    def _wait_if_due(self) -> None:
        """Sleep once, unless the required gap since the last attempt has passed."""
        if self._last_attempt_end is None:
            return  # the first request of an instance never waits
        gap = self._cooldown if self._cooldown_required else self._min_interval
        wait = gap - (self._monotonic() - self._last_attempt_end)
        if wait > 0:
            self._sleep(wait)

    def _asks_for_cooldown(self, capture: _Capture) -> bool:
        """True after a 429, or when any `Remaining` value is below the threshold.

        It reads whatever status and headers arrived, even for an incomplete body
        or a status outside 100 to 599.
        """
        if capture.status is None:
            return False  # nothing arrived: the minimum interval is enough
        if capture.status == _STATUS_TOO_MANY_REQUESTS:
            return True
        for name, value in capture.headers:
            if name.lower() != _REMAINING_HEADER:
                continue
            # HTTP's optional whitespace is a space or a tab. `str.strip()`
            # would also remove `0xA0` and `0x85`, which a field value may hold.
            text = value.strip(" \t")
            if not (text.isascii() and text.isdigit()):
                continue  # not a plain number: ignored
            # `Decimal` compares exactly for any number of digits and any
            # threshold, where `int()` refuses more than 4,300 digits by default.
            if Decimal(text) < self._low_remaining_threshold:
                return True
        return False

    # --- (e) The single request ----------------------------------------------

    def _send(self, request: httpx.Request) -> None:
        """Send one GET. The response hook reads the body into `self._capture`."""
        capture = self._capture
        try:
            self._client.send(request, stream=True)
        except httpx.HTTPError as error:
            if capture.status is None:
                capture.failure = error  # no status arrived
            # Otherwise the response was captured and the outcome is decided
            # from the capture: the library's error is dropped, not chained.

    def _capture_response(self, response: httpx.Response) -> None:
        """Response hook: keep the status, headers and body, and hide `Location`.

        With `follow_redirects=False` the client still parses `Location` for a
        3xx right after this hook, and fails on some values (an invalid URL, a
        host that `idna` cannot decode), closing the response and losing its
        body. The headers are kept first, then `Location` is removed from the
        client's own copy, so the client has nothing to parse: no value of it
        can run or leave the call. `RawResponse.headers` keeps it as received.
        """
        capture = self._capture
        capture.status = response.status_code
        capture.headers = tuple(  # Latin-1 is lossless for any byte
            (name.decode("latin-1"), value.decode("latin-1"))
            for name, value in response.headers.raw
        )
        if "location" in response.headers:
            del response.headers["location"]  # every `Location`, any case
        try:
            for chunk in response.iter_raw():  # raw bytes: no content decoding
                capture.body += chunk
        except httpx.HTTPError as error:
            capture.failure = error  # the bytes read so far stay in the capture
        finally:
            response.close()

    def _attempt_from_capture(self, request: httpx.Request) -> _Attempt:
        """The attempt, with a `RawResponse` when the status is in 100 to 599."""
        capture = self._capture
        status = capture.status
        if status is None or not _MIN_STATUS <= status <= _MAX_STATUS:
            return _Attempt(status=status, response=None, failure=capture.failure)
        response = RawResponse(
            method=request.method,
            url=str(request.url),
            status=status,
            headers=capture.headers,
            captured_at=self._now(),
            content=bytes(capture.body),
        )
        return _Attempt(status=status, response=response, failure=capture.failure)

    # --- (h) Close and context manager ---------------------------------------

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def _require_open(self) -> None:
        # The client's own state: `close()` and leaving the `with` block set it.
        if self._client.is_closed:
            raise RuntimeError("the source adapter is closed")

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


# --- (f) Outcome mapping ----------------------------------------------------


def _outcome[Result](
    attempt: _Attempt,
    operation: str,
    build: Callable[[RawResponse], Result | None],
) -> Result:
    """Return the result of an attempt, or raise the error it maps to.

    `build` returns the result when a 200 body passes the completeness checks,
    and `None` otherwise. The six branches below are the closed list of
    outcomes; the error messages hold no body bytes and no header values.
    """
    response = attempt.response
    # 1. failure before the response (no response)
    if attempt.status is None:
        raise SourceTransportError(
            f"{operation}: the request failed before a response arrived"
        ) from attempt.failure
    # 2. status outside 100 to 599 (invalid HTTP status, no response)
    if response is None:
        raise SourceTransportError(
            f"{operation}: the source answered an invalid HTTP status {attempt.status}"
        )
    # 3. cut off during the body (partial response)
    if attempt.failure is not None:
        raise SourceTransportError(
            f"{operation}: the body was cut off (status {response.status})",
            response=response,
        ) from attempt.failure
    # 4. status other than 200 (status error)
    if response.status != _STATUS_OK:
        raise SourceStatusError(
            f"{operation}: the source answered status {response.status}",
            response=response,
        )
    # 5. unusable 200 (incomplete-response error)
    result = build(response)
    if result is None:
        raise IncompleteResponseError(
            f"{operation}: the 200 body is incomplete or unusable", response=response
        )
    # 6. success (result)
    return result


# --- (g) Completeness checks ------------------------------------------------
# Each reads only `response.content` and the requested page or `ocid`. Nothing
# else is checked: not the record keys, page sizes or other OCDS sections.


def _reject_json_constant(name: str) -> Never:
    # `NaN`, `Infinity` and `-Infinity` are not JSON (RFC 8259 section 6), but
    # Python's parser reads them unless it is told not to.
    raise ValueError("a constant that RFC 8259 does not allow")


def _decode_json_object(content: bytes) -> dict[str, Any] | None:
    """The body as strict UTF-8 JSON with an object at the top level, else `None`.

    The failure is caught here and a verdict is returned, so the caller raises
    outside the `except` block: no `JSONDecodeError` or `UnicodeDecodeError`
    (both keep the body text) ends up in the chain of a raised error.
    """
    try:
        value = json.loads(
            content.decode("utf-8"), parse_constant=_reject_json_constant
        )
    except (ValueError, RecursionError):
        # Not UTF-8, not JSON, a non-standard constant, an integer of more than
        # 4,300 digits, or nesting that is too deep.
        return None
    return value if isinstance(value, dict) else None


def _is_count(value: object) -> bool:
    # A JSON integer: `int` but not `bool`, which is a subclass of `int`.
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _search_page_if_complete(response: RawResponse, page: int) -> SearchPage | None:
    """The page if the body has `total`, `page`, `pages`, `data` and echoes `page`."""
    body = _decode_json_object(response.content)
    if body is None:
        return None
    if not all(_is_count(body.get(key)) for key in ("total", "page", "pages")):
        return None
    data = body.get("data")
    if not isinstance(data, list) or body["page"] != page:
        return None
    return SearchPage(
        response=response,
        total=body["total"],
        page=page,
        pages=body["pages"],
        record_count=len(data),
    )


def _record_if_complete(response: RawResponse, ocid: str) -> RecordResponse | None:
    """The record if `releases` is a non-empty list of objects with this `ocid`."""
    body = _decode_json_object(response.content)
    if body is None:
        return None
    releases = body.get("releases")
    if not isinstance(releases, list) or not releases:
        return None
    for release in releases:
        if not isinstance(release, dict) or release.get("ocid") != ocid:
            return None
    return RecordResponse(response=response, ocid=ocid, release_count=len(releases))
