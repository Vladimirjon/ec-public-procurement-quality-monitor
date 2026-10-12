"""Feature sercop-source-adapter (F2), outcomes O4 and O5: the SERCOP adapter.

The adapter asks the SERCOP portal for one search page or one record and
returns the response as received, or raises a typed error that carries
whatever response was received. Every test here:

- injects an `httpx.MockTransport`, so nothing reaches the network, and runs
  under an autouse guard that fails the test if a socket is opened or a host
  name is resolved (AC11);
- uses fake `monotonic`, `sleep` and `now` callables, so nothing really sleeps;
- reads the fixtures in `tests/fixtures/sercop/` and never writes them;
- builds every other body (`429`, `5xx`, truncated, unusable) itself. Those
  bodies are SYNTHETIC: they say nothing about the format of the source's own
  answers. `search_no_results.json` is INFERRED, not observed.

URLs use `https://source.invalid/PLATAFORMA`; cookie and error bodies are
synthetic. Mock responses are built with `stream=` (never `content=`, which
adds `Content-Length` and cannot be streamed).

Revision 2 (outcome O2b; AC5, AC6, AC9, AC10 and AC15) adds, to the sections
below, a malformed `Location` on a redirect status, a status outside 100 to
599, pacing after an attempt that ends in an exception the adapter does not map,
the checks of the base URL authority, a request URL that is too long, a call
after `close()`, and an injected-transport defect that must propagate unchanged.
Its credentials, defects and bodies are SYNTHETIC; hosts are `.invalid` or
numeric and are never contacted.

Revision 3 (outcome O2c; AC3, AC5, AC7, AC8, AC9, AC10 and AC15) adds, to the
same sections, a `Location` host the library cannot decode, a `Set-Cookie` value
that is never parsed, JSON constants, huge integers and deep nesting in a body, a
repeated name, the no-chaining rule for the library's exceptions, long and
unusual `Remaining` values, the host, length and numeric rules of the
constructor, years and pages too long to write, lone surrogates and `SystemExit`.
Every body, header value and defect is SYNTHETIC, labelled where it is built.
Non-ASCII header values reach the response as bytes (`Reply` encodes Latin-1).

Revision 4 (outcome O2d; AC8, AC10, AC13 and AC15) adds, to the same sections,
the output invariant that every exception the adapter raises itself must
satisfy (type, nothing chained, fixed text, no input text), checked over three
finite sweeps (base URLs, call inputs, what the source sends); the exact type of
every construction rejection; the type rules for the options; the zone and
bracket cases of the base URL; and `MemoryError`. Every marker, body, header,
host and defect is SYNTHETIC; hosts are `.invalid` or numeric and never
contacted, and the IPv6 literals are never contacted either.

Revision 5 (outcome O2e; AC8, AC13 and AC15) adds, at the end of the file, four
groups: a call made inside the caller's own `except` or `finally` (the context
of the error is that exception and nothing else), a class name that a test
double defines (only a name that `httpx` exports reaches a message), a status
that is an `int` subclass (it is read by value), and a stream whose `close()`
fails after a read that ended in an interrupt or a defect (the first exception
decides). Every marker, class, status and defect is SYNTHETIC; hosts are
`.invalid`. A marker is always passed through a variable, never written in the
line that makes a call, because a formatted traceback quotes that line.
"""

import gzip
import json
import logging
import socket
import traceback
import warnings
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, NoReturn

import httpx
import pytest

from ec_procurement_quality.application.procurement_source import (
    ProcurementSource,
    RecordResponse,
    SearchPage,
)
from ec_procurement_quality.domain.source_response import (
    IncompleteResponseError,
    RawResponse,
    SourceError,
    SourceStatusError,
    SourceTransportError,
)
from ec_procurement_quality.infrastructure.local_disk_raw_evidence_store import (
    LocalDiskRawEvidenceStore,
)
from ec_procurement_quality.infrastructure.sercop_source import SercopSource

BASE_URL = "https://source.invalid/PLATAFORMA"
BUYER = "EMPRESA ELÉCTRICA QUITO S.A. E.E.Q."
BUYER_ENCODED = "EMPRESA%20EL%C3%89CTRICA%20QUITO%20S.A.%20E.E.Q."
OCID = "ocds-5wno2w-SYNTHETIC-A"
OTHER_OCID = "ocds-5wno2w-SYNTHETIC-B"
YEAR = 2025
SEARCH_URL = (
    f"{BASE_URL}/api/search_ocds?local=1&year=2025&page=1&buyer={BUYER_ENCODED}"
)
RECORD_URL = f"{BASE_URL}/api/record?ocid={OCID}"
NOW = datetime(2026, 10, 10, 6, 58, tzinfo=timezone(timedelta(hours=-5)))
EXECUTION_ID = "synthetic-exec-001"
BODY_MARKER = "synthetic-body-marker"
HEADER_MARKER = "synthetic-header-marker"

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "sercop"
SEARCH_SINGLE_PAGE = (FIXTURES / "search_single_page.json").read_bytes()
SEARCH_OUT_OF_RANGE = (FIXTURES / "search_page_out_of_range.json").read_bytes()
SEARCH_NO_RESULTS = (FIXTURES / "search_no_results.json").read_bytes()
RECORD_SINGLE_RELEASE = (FIXTURES / "record_single_release.json").read_bytes()

Headers = tuple[tuple[str, str], ...]
JSON_HEADERS: Headers = (("Content-Type", "application/json"),)


# --- Network guard (AC11) ---------------------------------------------------


@dataclass
class NetworkGuard:
    """Records every attempt to open a socket or resolve a host name."""

    attempts: list[str] = field(default_factory=list)
    attempts_expected: bool = False

    def expect_attempts(self) -> None:
        """Opt out of the teardown check (only the guard proof test does this)."""
        self.attempts_expected = True


@pytest.fixture(autouse=True)
def network_guard(monkeypatch: pytest.MonkeyPatch) -> Iterator[NetworkGuard]:
    guard = NetworkGuard()

    def blocked(name: str) -> Callable[..., NoReturn]:
        def refuse(*args: Any, **kwargs: Any) -> NoReturn:
            guard.attempts.append(name)
            raise OSError(f"synthetic network guard: {name} is blocked in tests")

        return refuse

    monkeypatch.setattr(socket.socket, "connect", blocked("socket.connect"))
    monkeypatch.setattr(socket.socket, "connect_ex", blocked("socket.connect_ex"))
    monkeypatch.setattr(socket, "create_connection", blocked("create_connection"))
    monkeypatch.setattr(socket, "getaddrinfo", blocked("getaddrinfo"))

    yield guard

    if not guard.attempts_expected:
        assert guard.attempts == [], (
            f"the test tried to reach the network: {guard.attempts}"
        )


# --- Fakes ------------------------------------------------------------------


class FakeClock:
    """A monotonic clock the test moves, and a sleeper that records and advances."""

    def __init__(self) -> None:
        self.value = 1000.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.value += seconds

    def advance(self, seconds: float) -> None:
        self.value += seconds


class FakeWallClock:
    """The injected `now`: a fixed aware time, counting its calls."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> datetime:
        self.calls += 1
        return NOW


class BodyStream(httpx.SyncByteStream):
    """A response body yielded in chunks, optionally failing after the last one."""

    def __init__(self, chunks: Sequence[bytes], error: BaseException | None) -> None:
        self._chunks = tuple(chunks)
        self._error = error

    def __iter__(self) -> Iterator[bytes]:
        yield from self._chunks
        if self._error is not None:
            raise self._error


@dataclass(frozen=True)
class Reply:
    """A scripted answer: a status, headers and a body that may be cut off."""

    status: int = 200
    headers: Headers = JSON_HEADERS
    chunks: tuple[bytes, ...] = ()
    error: BaseException | None = None

    def to_response(self) -> httpx.Response:
        # Latin-1 mirrors how the adapter decodes header bytes (project
        # decision), so test strings round trip byte for byte.
        raw_headers = [
            (name.encode("latin-1"), value.encode("latin-1"))
            for name, value in self.headers
        ]
        return httpx.Response(
            self.status,
            headers=raw_headers,
            stream=BodyStream(self.chunks, self.error),
        )


@dataclass(frozen=True)
class Failure:
    """A scripted failure raised by the transport before any status arrives."""

    build: Callable[[httpx.Request], BaseException]


class SyntheticTransportDefect(Exception):
    """SYNTHETIC: a defect of a test double or of the caller.

    It is not an `httpx` error and not a source outcome, so the adapter must let
    it propagate unchanged and never wrap it (AC15).
    """


def _reply(
    body: bytes = b"",
    *,
    status: int = 200,
    headers: Headers = JSON_HEADERS,
    chunks: Sequence[bytes] | None = None,
    error: BaseException | None = None,
) -> Reply:
    if chunks is None:
        chunks = (body,) if body else ()
    return Reply(status=status, headers=headers, chunks=tuple(chunks), error=error)


def _fails(error_type: type[httpx.RequestError]) -> Failure:
    return Failure(lambda request: error_type("synthetic failure", request=request))


def _with_remaining(*values: str, name: str = "X-RateLimit-Remaining") -> Headers:
    return (*JSON_HEADERS, *((name, value) for value in values))


class Script:
    """The MockTransport handler: records every request, answers in order."""

    def __init__(self, *outcomes: Reply | Failure) -> None:
        self._outcomes = list(outcomes)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if not self._outcomes:
            raise AssertionError("the adapter sent more requests than scripted")
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Failure):
            raise outcome.build(request)
        return outcome.to_response()


@dataclass
class Rig:
    source: SercopSource
    script: Script
    clock: FakeClock
    wall: FakeWallClock


@pytest.fixture
def make_rig() -> Iterator[Callable[..., Rig]]:
    """Build an adapter over scripted outcomes with fake clocks (closed at the end).

    Extra keyword arguments go to `SercopSource`. `clock` shares one fake
    monotonic clock between several adapters.
    """
    rigs: list[Rig] = []

    def build(
        *outcomes: Reply | Failure, clock: FakeClock | None = None, **options: Any
    ) -> Rig:
        script = Script(*outcomes)
        fake_clock = clock if clock is not None else FakeClock()
        wall = FakeWallClock()
        source = SercopSource(
            base_url=BASE_URL,
            transport=httpx.MockTransport(script),
            now=wall,
            monotonic=fake_clock.monotonic,
            sleep=fake_clock.sleep,
            **options,
        )
        rig = Rig(source=source, script=script, clock=fake_clock, wall=wall)
        rigs.append(rig)
        return rig

    yield build

    for rig in rigs:
        rig.source.close()


# --- Operations and bodies --------------------------------------------------


@dataclass(frozen=True)
class Operation:
    """One of the two adapter calls, with the valid body it accepts."""

    name: str
    call: Callable[[SercopSource], SearchPage | RecordResponse]
    valid_body: bytes
    url: str


SEARCH = Operation(
    name="search",
    call=lambda source: source.search_page(year=YEAR, buyer=BUYER, page=1),
    valid_body=SEARCH_SINGLE_PAGE,
    url=SEARCH_URL,
)
RECORD = Operation(
    name="record",
    call=lambda source: source.fetch_record(OCID),
    valid_body=RECORD_SINGLE_RELEASE,
    url=RECORD_URL,
)
OPERATIONS = (SEARCH, RECORD)

_MISSING = object()


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


def _search_body(**changes: object) -> bytes:
    """A synthetic search body (page 1), with fields replaced or removed."""
    body: dict[str, object] = {"total": 3, "page": 1, "pages": 1, "data": []}
    for key, value in changes.items():
        if value is _MISSING:
            del body[key]
        else:
            body[key] = value
    return _json_bytes(body)


def _record_body(releases: object = _MISSING) -> bytes:
    """A synthetic record body, with `releases` as given (or absent)."""
    body: dict[str, object] = {"version": "1.1"}
    if releases is not _MISSING:
        body["releases"] = releases
    return _json_bytes(body)


def _search_ignoring_source_errors(source: SercopSource) -> None:
    try:
        source.search_page(year=YEAR, buyer=BUYER, page=1)
    except SourceError:
        pass


def _raise_through(operation: Operation, rig: Rig) -> SourceError:
    """Run the call and return the typed error it must raise."""
    with pytest.raises(SourceError) as info:
        operation.call(rig.source)
    return info.value


def _response_of(error: SourceError) -> RawResponse:
    """The response an error must carry (the base attribute may be `None`)."""
    assert error.response is not None
    return error.response


# --- AC1: the search request and a valid page -------------------------------


def test_search_query_is_the_observed_url_in_one_get(
    make_rig: Callable[..., Rig],
) -> None:
    rig = make_rig(_reply(SEARCH_SINGLE_PAGE))

    rig.source.search_page(year=YEAR, buyer=BUYER, page=1)

    assert len(rig.script.requests) == 1
    request = rig.script.requests[0]
    assert request.method == "GET"
    assert str(request.url) == SEARCH_URL
    assert list(request.url.params.keys()) == ["local", "year", "page", "buyer"]
    assert request.url.params["local"] == "1"
    assert request.url.params["year"] == "2025"
    assert request.url.params["page"] == "1"
    assert request.url.params["buyer"] == BUYER


@pytest.mark.parametrize(("year", "page"), [(2024, 12), (1, 1), (2026, 300)])
def test_search_query_writes_year_and_page_as_plain_decimal_numbers(
    make_rig: Callable[..., Rig], year: int, page: int
) -> None:
    body = _search_body(page=page, pages=page)
    rig = make_rig(_reply(body))

    rig.source.search_page(year=year, buyer=BUYER, page=page)

    expected = (
        f"{BASE_URL}/api/search_ocds?local=1&year={year}&page={page}"
        f"&buyer={BUYER_ENCODED}"
    )
    assert str(rig.script.requests[0].url) == expected


def test_search_query_percent_encodes_reserved_characters_in_the_buyer(
    make_rig: Callable[..., Rig],
) -> None:
    rig = make_rig(_reply(SEARCH_SINGLE_PAGE))

    rig.source.search_page(year=YEAR, buyer="A&B=C/D?E#F+G %", page=1)

    expected = (
        f"{BASE_URL}/api/search_ocds?local=1&year=2025&page=1"
        "&buyer=A%26B%3DC%2FD%3FE%23F%2BG%20%25"
    )
    assert str(rig.script.requests[0].url) == expected
    assert len(rig.script.requests) == 1


def test_record_query_is_one_get_to_the_record_endpoint(
    make_rig: Callable[..., Rig],
) -> None:
    rig = make_rig(_reply(RECORD_SINGLE_RELEASE))

    rig.source.fetch_record(OCID)

    assert len(rig.script.requests) == 1
    request = rig.script.requests[0]
    assert request.method == "GET"
    assert str(request.url) == RECORD_URL
    assert list(request.url.params.keys()) == ["ocid"]


def test_record_query_percent_encodes_reserved_characters_in_the_ocid(
    make_rig: Callable[..., Rig],
) -> None:
    ocid = "SYNTHETIC/A B&C"
    rig = make_rig(_reply(_record_body([{"ocid": ocid}])))

    rig.source.fetch_record(ocid)

    expected = f"{BASE_URL}/api/record?ocid=SYNTHETIC%2FA%20B%26C"
    assert str(rig.script.requests[0].url) == expected


def test_search_success_returns_the_page_and_the_exact_bytes(
    make_rig: Callable[..., Rig],
) -> None:
    rig = make_rig(_reply(SEARCH_SINGLE_PAGE))

    result = rig.source.search_page(year=YEAR, buyer=BUYER, page=1)

    assert isinstance(result, SearchPage)
    assert result.total == 3
    assert result.page == 1
    assert result.pages == 1
    assert result.record_count == 3
    assert result.is_beyond_last_page is False
    assert isinstance(result.response, RawResponse)
    assert result.response.method == "GET"
    assert result.response.url == SEARCH_URL
    assert result.response.status == 200
    assert result.response.content == SEARCH_SINGLE_PAGE


def test_search_success_checks_nothing_beyond_the_ac7_rules(
    make_rig: Callable[..., Rig],
) -> None:
    # SYNTHETIC: extra keys, non-object entries and a total that disagrees with
    # pages are all outside the checks (F5 owns anything beyond them).
    body = _json_bytes(
        {"total": 0, "page": 1, "pages": 5, "data": [1, "x", None], "extra": {}}
    )
    rig = make_rig(_reply(body))

    result = rig.source.search_page(year=YEAR, buyer=BUYER, page=1)

    assert (result.total, result.page, result.pages) == (0, 1, 5)
    assert result.record_count == 3
    assert result.response.content == body


def test_search_success_result_is_immutable(make_rig: Callable[..., Rig]) -> None:
    rig = make_rig(_reply(SEARCH_SINGLE_PAGE))
    result = rig.source.search_page(year=YEAR, buyer=BUYER, page=1)

    names = ("response", "total", "page", "pages", "record_count")
    for name in (*names, "is_beyond_last_page"):
        with pytest.raises(AttributeError):
            setattr(result, name, 99)


# --- AC2: the record request and a valid record -----------------------------


def test_record_success_returns_the_ocid_and_the_exact_bytes(
    make_rig: Callable[..., Rig],
) -> None:
    rig = make_rig(_reply(RECORD_SINGLE_RELEASE))

    result = rig.source.fetch_record(OCID)

    assert isinstance(result, RecordResponse)
    assert result.ocid == OCID
    assert result.release_count == 1
    assert result.response.method == "GET"
    assert result.response.url == RECORD_URL
    assert result.response.status == 200
    assert result.response.content == RECORD_SINGLE_RELEASE
    # The escaped slash of the observed format is kept exactly as sent.
    assert b"\\/" in result.response.content


def test_record_success_counts_every_release_when_all_match(
    make_rig: Callable[..., Rig],
) -> None:
    # SYNTHETIC: only one release was observed; requiring every release to
    # match is a project decision.
    body = _record_body([{"ocid": OCID, "id": "r1"}, {"ocid": OCID, "id": "r2"}])
    rig = make_rig(_reply(body))

    result = rig.source.fetch_record(OCID)

    assert result.ocid == OCID
    assert result.release_count == 2


def test_record_success_checks_nothing_beyond_the_ac7_rules(
    make_rig: Callable[..., Rig],
) -> None:
    body = _json_bytes({"releases": [{"ocid": OCID}]})
    rig = make_rig(_reply(body))

    result = rig.source.fetch_record(OCID)

    assert result.release_count == 1
    assert result.response.content == body


def test_record_success_result_is_immutable(make_rig: Callable[..., Rig]) -> None:
    rig = make_rig(_reply(RECORD_SINGLE_RELEASE))
    result = rig.source.fetch_record(OCID)

    for name in ("response", "ocid", "release_count"):
        with pytest.raises(AttributeError):
            setattr(result, name, 99)


# --- AC3: the response as received, F1 shape, and no cookie -----------------


def test_raw_response_keeps_the_received_headers_content_and_capture_time(
    make_rig: Callable[..., Rig],
) -> None:
    headers: Headers = (
        ("Content-Type", "application/json"),
        ("Docker-Distribution-Api-Version", "registry/2.0"),
        ("Docker-Distribution-Api-Version", "registry/2.0"),
        ("X-RateLimit-Limit", "60"),
        ("X-RateLimit-Remaining", "47"),
        ("Set-Cookie", "synthetic-session=s1"),  # SYNTHETIC cookie
    )
    chunks = (b'{"total":1,"page":1,', b'"pages":1,', b'"data":[]}')
    rig = make_rig(_reply(headers=headers, chunks=chunks))

    result = rig.source.search_page(year=YEAR, buyer=BUYER, page=1)

    response = result.response
    assert response.headers == headers
    assert response.content == b"".join(chunks)
    assert response.captured_at == NOW
    assert response.captured_at.utcoffset() == timedelta(hours=-5)
    assert response.method == "GET"
    assert response.status == 200
    assert rig.wall.calls == 1


def test_raw_response_keeps_the_header_name_case_as_received(
    make_rig: Callable[..., Rig],
) -> None:
    headers: Headers = (
        ("content-type", "application/json"),
        ("X-RATELIMIT-REMAINING", "47"),
        ("set-COOKIE", "synthetic-session=s1"),
        ("x-Synthetic", "a"),
    )
    rig = make_rig(_reply(SEARCH_SINGLE_PAGE, headers=headers))

    result = rig.source.search_page(year=YEAR, buyer=BUYER, page=1)

    assert result.response.headers == headers


def test_raw_response_decodes_header_bytes_as_latin_1(
    make_rig: Callable[..., Rig],
) -> None:
    # Project decision: names and values are decoded as Latin-1, which is
    # lossless for any byte. The scripted bytes below are 0xE9 and 0xFF.
    headers: Headers = (*JSON_HEADERS, ("X-Synthetic-Latin1", "café ÿ"))
    rig = make_rig(_reply(SEARCH_SINGLE_PAGE, headers=headers))

    result = rig.source.search_page(year=YEAR, buyer=BUYER, page=1)

    assert result.response.headers == headers
    assert dict(result.response.headers)["X-Synthetic-Latin1"] == "café ÿ"


def test_raw_response_content_is_not_decoded_by_content_encoding(
    make_rig: Callable[..., Rig],
) -> None:
    # SYNTHETIC: a gzip-compressed error body must reach the caller as sent.
    compressed = gzip.compress(b"synthetic unavailable")
    headers: Headers = (("Content-Encoding", "gzip"),)
    rig = make_rig(_reply(compressed, status=503, headers=headers))

    error = _raise_through(SEARCH, rig)

    assert isinstance(error, SourceStatusError)
    assert _response_of(error).content == compressed


def test_raw_response_content_ignores_a_content_encoding_header_it_does_not_decode(
    make_rig: Callable[..., Rig],
) -> None:
    # SYNTHETIC: the header claims gzip but the bytes are plain JSON. The body
    # is read raw, so it is neither decoded nor rejected for that header.
    headers: Headers = (("Content-Encoding", "gzip"),)
    rig = make_rig(_reply(SEARCH_SINGLE_PAGE, headers=headers))

    result = rig.source.search_page(year=YEAR, buyer=BUYER, page=1)

    assert result.response.content == SEARCH_SINGLE_PAGE
    assert result.response.headers == headers


def test_raw_response_default_clock_gives_an_aware_capture_time() -> None:
    transport = httpx.MockTransport(Script(_reply(SEARCH_SINGLE_PAGE)))
    clock = FakeClock()
    with SercopSource(
        base_url=BASE_URL,
        transport=transport,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    ) as source:
        result = source.search_page(year=YEAR, buyer=BUYER, page=1)

    captured_at = result.response.captured_at
    assert captured_at.utcoffset() is not None
    assert abs(captured_at - datetime.now(UTC)) < timedelta(minutes=1)


@pytest.mark.parametrize("sequence", [1, 2, 3])
@pytest.mark.parametrize("kind", ["success", "status-429", "cut-off"])
def test_store_shape_response_fields_map_onto_the_store_keywords(
    make_rig: Callable[..., Rig], tmp_path: Path, kind: str, sequence: int
) -> None:
    # SYNTHETIC: the 429 body and the cut-off bytes are built here.
    headers = (*_with_remaining("47"), ("Set-Cookie", "synthetic-session=s1"))
    if kind == "success":
        rig = make_rig(_reply(SEARCH_SINGLE_PAGE, headers=headers))
        raw = rig.source.search_page(year=YEAR, buyer=BUYER, page=1).response
    elif kind == "status-429":
        rig = make_rig(
            _reply(b"<html>synthetic rate limit</html>", status=429, headers=headers)
        )
        error = _raise_through(SEARCH, rig)
        assert isinstance(error, SourceStatusError)
        raw = _response_of(error)
    else:
        rig = make_rig(
            _reply(
                headers=headers,
                chunks=(SEARCH_SINGLE_PAGE[:100],),
                error=httpx.RemoteProtocolError("synthetic cut-off"),
            )
        )
        error = _raise_through(SEARCH, rig)
        assert isinstance(error, SourceTransportError)
        raw = _response_of(error)
    store = LocalDiskRawEvidenceStore(tmp_path)

    observation = store.store(
        execution_id=EXECUTION_ID,
        sequence=sequence,
        method=raw.method,
        url=raw.url,
        status=raw.status,
        headers=raw.headers,
        captured_at=raw.captured_at,
        content=raw.content,
    )

    assert store.read_content(observation.content_hash) == raw.content
    assert observation.status == raw.status
    assert observation.method == raw.method
    assert observation.url == raw.url
    assert observation.captured_at == raw.captured_at
    assert all(name.lower() != "set-cookie" for name, _ in observation.headers)
    assert observation.headers == tuple(
        pair for pair in raw.headers if pair[0].lower() != "set-cookie"
    )
    assert len(observation.headers) == len(raw.headers) - 1
    assert store.read_observation(EXECUTION_ID, sequence) == observation


@pytest.mark.parametrize(
    ("status", "set_cookie"),
    [
        pytest.param(200, "synthetic-session=s1", id="after-200"),
        pytest.param(429, "synthetic-session=s1", id="after-429"),
        pytest.param(
            200,
            "synthetic-session=s1; Path=/; Domain=source.invalid",
            id="after-200-with-domain-and-path",
        ),
    ],
)
def test_cookie_is_never_sent_after_a_response_that_set_one(
    make_rig: Callable[..., Rig], status: int, set_cookie: str
) -> None:
    # SYNTHETIC cookie: the observation requests carried none (project decision).
    headers = (*JSON_HEADERS, ("Set-Cookie", set_cookie))
    first = _reply(
        SEARCH_SINGLE_PAGE if status == 200 else b"", status=status, headers=headers
    )
    rig = make_rig(first, _reply(RECORD_SINGLE_RELEASE), _reply(SEARCH_SINGLE_PAGE))

    _search_ignoring_source_errors(rig.source)
    rig.source.fetch_record(OCID)
    rig.source.search_page(year=YEAR, buyer=BUYER, page=1)

    assert len(rig.script.requests) == 3
    for request in rig.script.requests:
        assert "cookie" not in request.headers


# Revision 3 (AC3, project decision): the adapter keeps no cookies, so nothing
# parses a `Set-Cookie`. SYNTHETIC value whose `expires` year has 5,000 digits:
# the client's cookie jar issued a `UserWarning` with a traceback for it (stderr
# outside tests).
HUGE_YEAR_SET_COOKIE = "synthetic=1; expires=01-Jan-" + "9" * 5000 + " 00:00:00 GMT"


def _summary(result: SearchPage | RecordResponse) -> tuple[object, ...]:
    """What a result says, apart from the headers that came with it."""
    response = result.response
    shape: tuple[object, ...]
    if isinstance(result, SearchPage):
        shape = (result.total, result.page, result.pages, result.record_count)
    else:
        shape = (result.ocid, result.release_count)
    return (
        *shape,
        response.method,
        response.url,
        response.status,
        response.content,
        response.captured_at,
    )


@pytest.mark.parametrize("operation", OPERATIONS, ids=lambda o: o.name)
def test_cookie_set_cookie_is_never_parsed_and_raises_no_warning(
    make_rig: Callable[..., Rig], operation: Operation
) -> None:
    plain = make_rig(_reply(operation.valid_body))
    expected = _summary(operation.call(plain.source))
    headers = (*JSON_HEADERS, ("Set-Cookie", HUGE_YEAR_SET_COOKIE))
    rig = make_rig(
        _reply(operation.valid_body, headers=headers), _reply(operation.valid_body)
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = operation.call(rig.source)
    operation.call(rig.source)

    # Only the category and a prefix are shown if this fails: the warning text
    # of the cookie jar carries a traceback.
    assert [(w.category.__name__, str(w.message)[:40]) for w in caught] == []
    assert _summary(result) == expected
    assert result.response.headers == headers
    assert len(rig.script.requests) == 2
    for request in rig.script.requests:
        assert "cookie" not in request.headers


# --- AC4: out-of-range and no-results pages are valid -----------------------


def test_search_out_of_range_page_is_a_valid_result(
    make_rig: Callable[..., Rig],
) -> None:
    # OBSERVED: page 30 with pages 29 is a successful, empty response.
    rig = make_rig(_reply(SEARCH_OUT_OF_RANGE))

    result = rig.source.search_page(year=YEAR, buyer=BUYER, page=30)

    assert result.total == 284
    assert result.page == 30
    assert result.pages == 29
    assert result.record_count == 0
    assert result.is_beyond_last_page is True
    assert result.response.content == SEARCH_OUT_OF_RANGE


def test_search_no_results_is_a_valid_result(make_rig: Callable[..., Rig]) -> None:
    # INFERRED, not observed: search_no_results.json was built from the
    # out-of-range shape and an earlier 45-byte reply (fixtures README).
    rig = make_rig(_reply(SEARCH_NO_RESULTS))

    result = rig.source.search_page(year=YEAR, buyer=BUYER, page=1)

    assert result.total == 0
    assert result.page == 1
    assert result.pages == 0
    assert result.record_count == 0
    assert result.is_beyond_last_page is True
    assert result.response.content == SEARCH_NO_RESULTS


def test_search_out_of_range_property_is_true_exactly_when_page_exceeds_pages(
    make_rig: Callable[..., Rig],
) -> None:
    rig = make_rig(_reply(SEARCH_SINGLE_PAGE))
    response = rig.source.search_page(year=YEAR, buyer=BUYER, page=1).response

    def page_of(page: int, pages: int) -> SearchPage:
        return SearchPage(
            response=response, total=0, page=page, pages=pages, record_count=0
        )

    assert page_of(5, 4).is_beyond_last_page is True
    assert page_of(4, 4).is_beyond_last_page is False
    assert page_of(1, 0).is_beyond_last_page is True
    assert page_of(1, 29).is_beyond_last_page is False


def test_search_in_range_page_with_empty_data_is_valid_and_not_out_of_range(
    make_rig: Callable[..., Rig],
) -> None:
    # SYNTHETIC: no rule was observed for an in-range page with empty data, so
    # it is valid, and an empty `data` alone is never "beyond the last page".
    body = _search_body(total=284, page=1, pages=29, data=[])
    rig = make_rig(_reply(body))

    result = rig.source.search_page(year=YEAR, buyer=BUYER, page=1)

    assert result.record_count == 0
    assert result.is_beyond_last_page is False


# --- AC5: any status other than 200 is a status error -----------------------

# Every body below is SYNTHETIC (neither a 429 nor a 5xx body was ever
# observed); a body of `None` means "the valid body of the operation".
STATUS_CASES = [
    pytest.param(
        429,
        b"<html>synthetic rate limit</html>",
        (("Content-Type", "text/html"), ("Retry-After", "1")),
        id="429-html-with-retry-after",
    ),
    pytest.param(500, b"", (("Content-Type", "text/plain"),), id="500-empty"),
    pytest.param(
        503, b"synthetic unavailable", (("Content-Type", "text/plain"),), id="503"
    ),
    pytest.param(
        404, b"synthetic not found", (("Content-Type", "text/plain"),), id="404"
    ),
    pytest.param(204, b"", (), id="204"),
    pytest.param(
        302,
        b"",
        (("Location", "https://source.invalid/PLATAFORMA/elsewhere"),),
        id="302-with-location",
    ),
    pytest.param(
        500,
        b"\xff\xfe synthetic bytes that are not utf-8",
        (("Content-Type", "text/plain"),),
        id="500-not-utf-8",
    ),
    pytest.param(201, None, JSON_HEADERS, id="201-with-a-valid-body"),
    pytest.param(206, None, JSON_HEADERS, id="206-with-a-valid-body"),
    # Revision 2, all SYNTHETIC: a `Location` header that the HTTP library cannot
    # parse as a URL must never change the outcome. The status, the exact body
    # and the `Location` value are kept as received, after one request.
    pytest.param(
        302,
        b"synthetic redirect body",
        (("Location", "https:abc"),),
        id="302-location-not-starting-with-slash",
    ),
    pytest.param(
        302,
        b"synthetic redirect body",
        (("Location", "/synthetic\tpath"),),
        id="302-location-with-a-tab",
    ),
    pytest.param(
        307,
        b"synthetic redirect body",
        (("Location", "http://999.1.1.1/"),),
        id="307-location-with-an-invalid-ipv4-host",
    ),
    pytest.param(
        301,
        b"synthetic redirect body",
        (("Location", "/" + "a" * 65_530),),
        id="301-location-longer-than-the-url-limit",
    ),
    # Revision 3, SYNTHETIC: a `Location` host that the HTTP library cannot
    # decode from IDNA (`xn--` is no valid A-label) made its redirect step raise
    # an `idna.IDNAError`, which escaped the call. Like every other value, it
    # never changes the outcome: same status, body and header, one request.
    pytest.param(
        302,
        b"synthetic redirect body",
        (("Location", "http://xn--/"),),
        id="302-location-host-not-decodable",
    ),
    pytest.param(
        308,
        b"synthetic redirect body",
        (("Location", "//xn--/"),),
        id="308-location-scheme-relative-host-not-decodable",
    ),
]


@pytest.mark.parametrize("operation", OPERATIONS, ids=lambda o: o.name)
@pytest.mark.parametrize(("status", "body", "headers"), STATUS_CASES)
def test_status_error_carries_the_complete_response(
    make_rig: Callable[..., Rig],
    operation: Operation,
    status: int,
    body: bytes | None,
    headers: Headers,
) -> None:
    sent = operation.valid_body if body is None else body
    rig = make_rig(_reply(sent, status=status, headers=headers))

    error = _raise_through(operation, rig)

    assert isinstance(error, SourceStatusError)
    response = _response_of(error)
    assert response.status == status
    assert response.content == sent
    assert response.headers == headers
    assert response.method == "GET"
    assert response.url == operation.url
    assert response.captured_at == NOW
    # One call is one request: no redirect is followed and nothing is retried.
    assert len(rig.script.requests) == 1


# --- AC6: transport failures ------------------------------------------------


@pytest.mark.parametrize("operation", OPERATIONS, ids=lambda o: o.name)
@pytest.mark.parametrize(
    "error_type",
    [
        pytest.param(httpx.ConnectError, id="connect-error"),
        pytest.param(httpx.ConnectTimeout, id="connect-timeout"),
        pytest.param(httpx.ReadTimeout, id="read-timeout-before-the-status"),
        pytest.param(httpx.RemoteProtocolError, id="protocol-error-before-the-status"),
    ],
)
def test_transport_failure_before_the_status_carries_no_response(
    make_rig: Callable[..., Rig],
    operation: Operation,
    error_type: type[httpx.RequestError],
) -> None:
    rig = make_rig(_fails(error_type))

    with pytest.raises(SourceTransportError) as info:
        operation.call(rig.source)

    assert info.value.response is None
    assert len(rig.script.requests) == 1


CUT_OFF_ERRORS: list[Any] = [
    pytest.param(
        lambda: httpx.RemoteProtocolError("synthetic cut-off"), id="protocol-error"
    ),
    pytest.param(
        lambda: httpx.ReadTimeout("synthetic read timeout"), id="read-timeout"
    ),
]


@pytest.mark.parametrize("operation", OPERATIONS, ids=lambda o: o.name)
@pytest.mark.parametrize("make_error", CUT_OFF_ERRORS)
def test_transport_cut_off_body_keeps_the_partial_bytes(
    make_rig: Callable[..., Rig],
    operation: Operation,
    make_error: Callable[[], BaseException],
) -> None:
    first_100 = operation.valid_body[:100]
    headers: Headers = (*JSON_HEADERS, ("X-Synthetic", "kept"))
    rig = make_rig(
        _reply(
            headers=headers,
            chunks=(first_100[:60], first_100[60:]),
            error=make_error(),
        )
    )

    with pytest.raises(SourceTransportError) as info:
        operation.call(rig.source)

    response = info.value.response
    assert response is not None
    assert response.status == 200
    assert len(first_100) == 100
    assert response.content == first_100
    assert response.headers == headers
    assert response.captured_at == NOW
    assert response.method == "GET"
    assert response.url == operation.url
    assert len(rig.script.requests) == 1


def test_transport_cut_off_before_any_body_byte_keeps_status_and_headers(
    make_rig: Callable[..., Rig],
) -> None:
    rig = make_rig(_reply(chunks=(), error=httpx.ReadTimeout("synthetic read timeout")))

    with pytest.raises(SourceTransportError) as info:
        rig.source.search_page(year=YEAR, buyer=BUYER, page=1)

    response = info.value.response
    assert response is not None
    assert response.status == 200
    assert response.content == b""
    assert response.headers == JSON_HEADERS


def test_transport_cut_off_non_200_response_is_a_transport_error_with_its_bytes(
    make_rig: Callable[..., Rig],
) -> None:
    # SYNTHETIC: a 503 whose body is cut off is still partial evidence.
    headers: Headers = (("Content-Type", "text/plain"),)
    rig = make_rig(
        _reply(
            status=503,
            headers=headers,
            chunks=(b"synthetic una",),
            error=httpx.RemoteProtocolError("synthetic cut-off"),
        )
    )

    with pytest.raises(SourceTransportError) as info:
        rig.source.search_page(year=YEAR, buyer=BUYER, page=1)

    response = info.value.response
    assert response is not None
    assert response.status == 503
    assert response.content == b"synthetic una"
    assert response.headers == headers


def test_transport_interrupt_before_the_status_is_not_swallowed(
    make_rig: Callable[..., Rig],
) -> None:
    rig = make_rig(Failure(lambda request: KeyboardInterrupt()))

    with pytest.raises(KeyboardInterrupt):
        rig.source.search_page(year=YEAR, buyer=BUYER, page=1)


def test_transport_interrupt_while_reading_the_body_is_not_swallowed(
    make_rig: Callable[..., Rig],
) -> None:
    rig = make_rig(_reply(chunks=(b"{",), error=KeyboardInterrupt()))

    with pytest.raises(KeyboardInterrupt):
        rig.source.search_page(year=YEAR, buyer=BUYER, page=1)


@pytest.mark.parametrize(
    ("operation", "operation_name"),
    [
        pytest.param(SEARCH, "search_ocds", id="search"),
        pytest.param(RECORD, "record", id="record"),
    ],
)
@pytest.mark.parametrize("status", [99, 600, 999])
def test_transport_invalid_status_is_a_transport_error_without_response(
    make_rig: Callable[..., Rig],
    operation: Operation,
    operation_name: str,
    status: int,
) -> None:
    # SYNTHETIC: no such status was ever observed, and RFC 9110 § 15 calls it
    # invalid. F1 cannot store it, so no response is carried, but the message
    # keeps the operation and the status number for the caller to record.
    headers: Headers = (*JSON_HEADERS, ("X-Synthetic", HEADER_MARKER))
    rig = make_rig(_reply(BODY_MARKER.encode("ascii"), status=status, headers=headers))

    with pytest.raises(SourceTransportError) as info:
        operation.call(rig.source)

    error = info.value
    assert error.response is None
    assert operation_name in str(error)
    assert str(status) in str(error)
    for raised in _exception_chain(error):
        for text in (str(raised), repr(raised)):
            assert BODY_MARKER not in text
            assert HEADER_MARKER not in text
    assert len(rig.script.requests) == 1


@pytest.mark.parametrize("operation", OPERATIONS, ids=lambda o: o.name)
@pytest.mark.parametrize(
    "where",
    [
        pytest.param("before-the-status", id="before-the-status"),
        pytest.param(
            "from-the-body-after-one-chunk", id="from-the-body-after-one-chunk"
        ),
    ],
)
def test_transport_defect_from_an_injected_transport_propagates_unchanged(
    make_rig: Callable[..., Rig], operation: Operation, where: str
) -> None:
    # SYNTHETIC defect of a test double: not an `httpx` error and not a source
    # outcome, so it must reach the caller as the same object, unwrapped.
    defect = SyntheticTransportDefect("synthetic transport defect")
    outcome: Reply | Failure
    if where == "before-the-status":
        outcome = Failure(lambda request: defect)
    else:
        outcome = _reply(chunks=(operation.valid_body[:50],), error=defect)
    rig = make_rig(outcome)

    with pytest.raises(SyntheticTransportDefect) as info:
        operation.call(rig.source)

    assert info.value is defect
    assert len(rig.script.requests) == 1


@pytest.mark.parametrize("operation", OPERATIONS, ids=lambda o: o.name)
@pytest.mark.parametrize(
    "where",
    [
        pytest.param("before-the-status", id="before-the-status"),
        pytest.param(
            "from-the-body-after-one-chunk", id="from-the-body-after-one-chunk"
        ),
    ],
)
def test_transport_defect_system_exit_propagates_unchanged(
    make_rig: Callable[..., Rig], operation: Operation, where: str
) -> None:
    # Revision 3 (audit R-3), SYNTHETIC: `SystemExit` is not a source outcome,
    # so it must reach the caller as the same object, next to `KeyboardInterrupt`.
    exit_request = SystemExit("synthetic system exit")
    outcome: Reply | Failure
    if where == "before-the-status":
        outcome = Failure(lambda request: exit_request)
    else:
        outcome = _reply(chunks=(operation.valid_body[:50],), error=exit_request)
    rig = make_rig(outcome)

    with pytest.raises(SystemExit) as info:
        operation.call(rig.source)

    assert info.value is exit_request
    assert len(rig.script.requests) == 1


@pytest.mark.parametrize("operation", OPERATIONS, ids=lambda o: o.name)
@pytest.mark.parametrize(
    "where",
    [
        pytest.param("before-the-status", id="before-the-status"),
        pytest.param(
            "from-the-body-after-one-chunk", id="from-the-body-after-one-chunk"
        ),
    ],
)
def test_transport_defect_memory_error_propagates_unchanged(
    make_rig: Callable[..., Rig], operation: Operation, where: str
) -> None:
    # Revision 4 (audit R-9), SYNTHETIC: no limit on the size of a body was
    # observed or is set, so exhausting memory is not a source outcome. It
    # reaches the caller as the same object, and is not a `SourceError`.
    memory_error = MemoryError("synthetic memory error")
    outcome: Reply | Failure
    if where == "before-the-status":
        outcome = Failure(lambda request: memory_error)
    else:
        outcome = _reply(chunks=(operation.valid_body[:50],), error=memory_error)
    rig = make_rig(outcome)

    with pytest.raises(MemoryError) as info:
        operation.call(rig.source)

    assert info.value is memory_error
    assert len(rig.script.requests) == 1


# --- AC7: a complete 200 whose body is unusable -----------------------------

# Every body below is SYNTHETIC, built from the fixtures or from small JSON
# objects; none of them says anything about the source's own format.
_GZIP_HEADERS: Headers = (
    ("Content-Type", "application/json"),
    ("Content-Encoding", "gzip"),
)

# Revision 3 (AC7), SYNTHETIC bodies built as bytes: `json.dumps` cannot write an
# integer of more than 4,300 digits. RFC 8259 allows neither `NaN`, `Infinity`
# nor `-Infinity`, and the standard parser reads neither an integer of more than
# 4,300 digits nor nesting deeper than the recursion limit (default settings).
_SEARCH_BODY_START = b'{"total":3,"page":1,"pages":1,"data":'
_RECORD_BODY_START = b'{"releases":[{"ocid":"' + OCID.encode("ascii") + b'","amount":'
_HUGE_INTEGER = b"1" * 5001
_DEEP_NESTING = b"[" * 100_000 + b"]" * 100_000

INCOMPLETE_SEARCH_CASES = [
    pytest.param(
        1,
        SEARCH_SINGLE_PAGE[: len(SEARCH_SINGLE_PAGE) // 2],
        JSON_HEADERS,
        id="first-half-of-the-fixture",
    ),
    pytest.param(1, SEARCH_SINGLE_PAGE + b"x", JSON_HEADERS, id="trailing-garbage"),
    pytest.param(1, b"\xff\xfe", JSON_HEADERS, id="not-utf-8"),
    pytest.param(
        1,
        b'{"total":3,"page":1,"pages":1,"data":["caf\xe9"]}',
        JSON_HEADERS,
        id="latin-1-bytes-in-otherwise-valid-json",
    ),
    pytest.param(1, b"\xef\xbb\xbf" + SEARCH_SINGLE_PAGE, JSON_HEADERS, id="utf-8-bom"),
    pytest.param(1, b"", JSON_HEADERS, id="empty-body"),
    pytest.param(1, b"[]", JSON_HEADERS, id="top-level-list"),
    pytest.param(1, b"null", JSON_HEADERS, id="top-level-null"),
    pytest.param(1, _search_body(total=_MISSING), JSON_HEADERS, id="total-missing"),
    pytest.param(1, _search_body(total="3"), JSON_HEADERS, id="total-text"),
    pytest.param(1, _search_body(total=True), JSON_HEADERS, id="total-true"),
    pytest.param(1, _search_body(total=-1), JSON_HEADERS, id="total-negative"),
    pytest.param(1, _search_body(total=3.0), JSON_HEADERS, id="total-float"),
    pytest.param(1, _search_body(page=_MISSING), JSON_HEADERS, id="page-missing"),
    pytest.param(1, _search_body(page="1"), JSON_HEADERS, id="page-text"),
    pytest.param(1, _search_body(page=True), JSON_HEADERS, id="page-true"),
    pytest.param(1, _search_body(pages=_MISSING), JSON_HEADERS, id="pages-missing"),
    pytest.param(1, _search_body(pages=-1), JSON_HEADERS, id="pages-negative"),
    pytest.param(1, _search_body(pages=False), JSON_HEADERS, id="pages-false"),
    pytest.param(1, _search_body(data=None), JSON_HEADERS, id="data-null"),
    pytest.param(1, _search_body(data={}), JSON_HEADERS, id="data-object"),
    pytest.param(1, _search_body(data=_MISSING), JSON_HEADERS, id="data-missing"),
    pytest.param(1, _search_body(page=2), JSON_HEADERS, id="page-2-answers-page-1"),
    pytest.param(2, SEARCH_SINGLE_PAGE, JSON_HEADERS, id="page-1-answers-page-2"),
    pytest.param(
        1, gzip.compress(SEARCH_SINGLE_PAGE), _GZIP_HEADERS, id="gzip-kept-raw"
    ),
    # Revision 3 (AC7): each body is valid except for the one thing named.
    pytest.param(1, _SEARCH_BODY_START + b"[NaN]}", JSON_HEADERS, id="nan-in-data"),
    pytest.param(
        1, _SEARCH_BODY_START + b"[Infinity]}", JSON_HEADERS, id="infinity-in-data"
    ),
    pytest.param(
        1,
        _SEARCH_BODY_START + b"[-Infinity]}",
        JSON_HEADERS,
        id="negative-infinity-in-data",
    ),
    pytest.param(
        1,
        _SEARCH_BODY_START + b"[" + _HUGE_INTEGER + b"]}",
        JSON_HEADERS,
        id="integer-of-5001-digits-in-data",
    ),
    pytest.param(
        1,
        b'{"total":1' + b"0" * 4300 + b',"page":1,"pages":1,"data":[]}',
        JSON_HEADERS,
        id="total-of-4301-digits",
    ),
    pytest.param(
        1,
        _SEARCH_BODY_START + _DEEP_NESTING + b"}",
        JSON_HEADERS,
        id="nested-too-deep",
    ),
]


@pytest.mark.parametrize(("requested_page", "body", "headers"), INCOMPLETE_SEARCH_CASES)
def test_incomplete_search_200_raises_with_the_exact_bytes(
    make_rig: Callable[..., Rig], requested_page: int, body: bytes, headers: Headers
) -> None:
    rig = make_rig(_reply(body, headers=headers))

    with pytest.raises(IncompleteResponseError) as info:
        rig.source.search_page(year=YEAR, buyer=BUYER, page=requested_page)

    response = info.value.response
    assert response is not None
    assert response.status == 200
    assert response.content == body
    assert response.headers == headers
    assert response.captured_at == NOW
    assert len(rig.script.requests) == 1


def _release(**changes: object) -> dict[str, object]:
    release: dict[str, object] = {"id": "synthetic-release", "ocid": OCID}
    release.update(changes)
    return release


INCOMPLETE_RECORD_CASES = [
    pytest.param(
        RECORD_SINGLE_RELEASE[: len(RECORD_SINGLE_RELEASE) // 2],
        JSON_HEADERS,
        id="first-half-of-the-fixture",
    ),
    pytest.param(b"\xff\xfe", JSON_HEADERS, id="not-utf-8"),
    pytest.param(b"\xef\xbb\xbf" + RECORD_SINGLE_RELEASE, JSON_HEADERS, id="utf-8-bom"),
    pytest.param(b"", JSON_HEADERS, id="empty-body"),
    pytest.param(b"[]", JSON_HEADERS, id="top-level-list"),
    pytest.param(_record_body(), JSON_HEADERS, id="releases-missing"),
    pytest.param(_record_body([]), JSON_HEADERS, id="releases-empty"),
    pytest.param(_record_body({}), JSON_HEADERS, id="releases-object"),
    pytest.param(_record_body(None), JSON_HEADERS, id="releases-null"),
    pytest.param(_record_body(["x"]), JSON_HEADERS, id="release-text"),
    pytest.param(_record_body([None]), JSON_HEADERS, id="release-null"),
    pytest.param(_record_body([{"id": "x"}]), JSON_HEADERS, id="release-without-ocid"),
    pytest.param(
        _record_body([_release(ocid=OTHER_OCID)]), JSON_HEADERS, id="other-ocid"
    ),
    pytest.param(
        _record_body([_release(ocid=OCID.lower())]),
        JSON_HEADERS,
        id="ocid-case-differs",
    ),
    pytest.param(_record_body([_release(ocid=None)]), JSON_HEADERS, id="ocid-null"),
    pytest.param(_record_body([_release(ocid=5)]), JSON_HEADERS, id="ocid-number"),
    pytest.param(
        _record_body([_release(), _release(ocid=OTHER_OCID)]),
        JSON_HEADERS,
        id="one-release-of-two-differs",
    ),
    pytest.param(
        gzip.compress(RECORD_SINGLE_RELEASE), _GZIP_HEADERS, id="gzip-kept-raw"
    ),
    # Revision 3 (AC7): the single release matches the `ocid`; only the value of
    # `amount` (or the nesting) makes the body unusable.
    pytest.param(
        _RECORD_BODY_START + b"Infinity}]}",
        JSON_HEADERS,
        id="infinity-in-a-release",
    ),
    pytest.param(_RECORD_BODY_START + b"NaN}]}", JSON_HEADERS, id="nan-in-a-release"),
    pytest.param(
        _RECORD_BODY_START + _HUGE_INTEGER + b"}]}",
        JSON_HEADERS,
        id="integer-of-5001-digits-in-a-release",
    ),
    pytest.param(
        _RECORD_BODY_START + _DEEP_NESTING + b"}]}",
        JSON_HEADERS,
        id="nested-too-deep",
    ),
]


@pytest.mark.parametrize(("body", "headers"), INCOMPLETE_RECORD_CASES)
def test_incomplete_record_200_raises_with_the_exact_bytes(
    make_rig: Callable[..., Rig], body: bytes, headers: Headers
) -> None:
    rig = make_rig(_reply(body, headers=headers))

    with pytest.raises(IncompleteResponseError) as info:
        rig.source.fetch_record(OCID)

    response = info.value.response
    assert response is not None
    assert response.status == 200
    assert response.content == body
    assert response.headers == headers
    assert response.captured_at == NOW
    assert len(rig.script.requests) == 1


def test_search_success_takes_the_last_value_of_a_repeated_name(
    make_rig: Callable[..., Rig],
) -> None:
    # Revision 3 (AC7, project decision), SYNTHETIC: RFC 8259 § 4 leaves a repeated
    # name open; the value the parser keeps, the last, is the one that counts.
    body = b'{"total": 3, "page": 2, "page": 1, "pages": 1, "data": []}'
    rig = make_rig(_reply(body))

    result = rig.source.search_page(year=YEAR, buyer=BUYER, page=1)

    assert (result.total, result.page, result.pages) == (3, 1, 1)
    assert result.record_count == 0
    assert result.response.content == body


# --- AC8: nothing leaks response content ------------------------------------

NO_LEAK_SCENARIOS = [
    "success",
    "status-429",
    "invalid-json",
    "not-utf-8",
    "wrong-value",
    "cut-off",
]


def _leaky_reply(scenario: str, operation: Operation) -> Reply:
    """A SYNTHETIC answer whose body and header values hold the markers."""
    marker = BODY_MARKER.encode("ascii")
    headers: Headers = (*JSON_HEADERS, ("X-Synthetic", HEADER_MARKER))
    if scenario == "success":
        if operation is SEARCH:
            body = _search_body(data=[{"note": BODY_MARKER}])
        else:
            body = _record_body([{"ocid": OCID, "note": BODY_MARKER}])
        return _reply(body, headers=headers)
    if scenario == "status-429":
        return _reply(
            b"<html>" + marker + b"</html>",
            status=429,
            headers=(*headers, ("Retry-After", "1")),
        )
    if scenario == "invalid-json":
        return _reply(marker + b" is not json", headers=headers)
    if scenario == "not-utf-8":
        return _reply(marker + b"\xff", headers=headers)
    if scenario == "wrong-value":
        if operation is SEARCH:
            return _reply(_search_body(total=BODY_MARKER), headers=headers)
        return _reply(_record_body([{"ocid": BODY_MARKER}]), headers=headers)
    assert scenario == "cut-off"
    return _reply(
        headers=headers,
        chunks=(b'{"note":"' + marker,),
        error=httpx.RemoteProtocolError("synthetic cut-off"),
    )


def _exception_chain(error: BaseException) -> list[BaseException]:
    """`error` and everything reachable through `__cause__` and `__context__`."""
    chain: list[BaseException] = []
    pending: list[BaseException | None] = [error]
    while pending:
        current = pending.pop()
        if current is None or any(current is seen for seen in chain):
            continue
        chain.append(current)
        pending.extend([current.__cause__, current.__context__])
    return chain


@pytest.mark.parametrize("operation", OPERATIONS, ids=lambda o: o.name)
@pytest.mark.parametrize("scenario", NO_LEAK_SCENARIOS)
def test_no_leak_in_messages_representations_logs_chains_and_output(
    make_rig: Callable[..., Rig],
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
    scenario: str,
    operation: Operation,
) -> None:
    caplog.set_level(logging.DEBUG)
    rig = make_rig(_leaky_reply(scenario, operation))
    texts: list[str] = []

    try:
        result = operation.call(rig.source)
    except SourceError as error:
        assert scenario != "success"
        for raised in _exception_chain(error):
            assert not isinstance(raised, json.JSONDecodeError | UnicodeDecodeError)
            texts.extend([str(raised), repr(raised)])
            texts.extend(repr(argument) for argument in raised.args)
        if error.response is not None:
            texts.extend([repr(error.response), str(error.response)])
    else:
        assert scenario == "success"
        texts.extend([repr(result), str(result)])
        texts.extend([repr(result.response), str(result.response)])

    for record in caplog.records:
        assert not record.name.startswith("ec_procurement_quality"), record.name
        texts.extend([record.getMessage(), str(record.args), record.exc_text or ""])
    texts.append(caplog.text)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    for text in texts:
        assert BODY_MARKER not in text
        assert HEADER_MARKER not in text


# --- AC9: pacing ------------------------------------------------------------


@dataclass(frozen=True)
class Step:
    """One call: what the transport answers, and the waits it must cause."""

    outcome: Reply | Failure
    waits: tuple[float, ...] = ()
    after: float = 2.0  # seconds between the previous attempt's end and this call


def _ok(
    *remaining: str, name: str = "X-RateLimit-Remaining", extra: Headers = ()
) -> Reply:
    headers = (*_with_remaining(*remaining, name=name), *extra)
    return _reply(SEARCH_SINGLE_PAGE, headers=headers)


# SYNTHETIC: no 429 or 5xx was observed; these bodies and headers are built here.
RATE_LIMITED = _reply(
    b"<html>synthetic rate limit</html>",
    status=429,
    headers=(("Content-Type", "text/html"), ("Retry-After", "1")),
)
UNAVAILABLE = _reply(b"", status=500, headers=())


def _partial(*remaining: str) -> Reply:
    return _reply(
        headers=_with_remaining(*remaining),
        chunks=(SEARCH_SINGLE_PAGE[:50],),
        error=httpx.RemoteProtocolError("synthetic cut-off"),
    )


PACING_CASES = [
    pytest.param({}, (Step(_ok("47")),), id="the-first-call-never-waits"),
    pytest.param(
        {},
        (Step(_ok("47")), Step(_ok("47"), (3.0,))),
        id="remaining-47-waits-the-minimum-interval-less-the-elapsed-time",
    ),
    pytest.param(
        {},
        (Step(_ok("47")), Step(_ok("47"), (), after=10.0)),
        id="no-wait-when-10-s-have-passed",
    ),
    pytest.param(
        {},
        (Step(_ok("47")), Step(_ok("47"), (), after=5.0)),
        id="no-wait-when-exactly-the-interval-has-passed",
    ),
    pytest.param(
        {},
        (Step(_ok("19")), Step(_ok("47"), (58.0,))),
        id="remaining-19-waits-the-cool-down",
    ),
    pytest.param(
        {},
        (Step(_ok("20")), Step(_ok("47"), (3.0,))),
        id="remaining-20-is-not-below-the-threshold",
    ),
    pytest.param(
        {},
        (Step(_ok("5")), Step(_ok("47"), (), after=60.0)),
        id="cool-down-over-after-60-s",
    ),
    pytest.param(
        {},
        (Step(_ok("5")), Step(_ok("47"), (1.0,), after=59.0)),
        id="cool-down-less-59-elapsed-seconds",
    ),
    pytest.param(
        {},
        (Step(RATE_LIMITED), Step(_ok("47"), (58.0,))),
        id="429-without-a-rate-limit-header-waits-the-cool-down",
    ),
    pytest.param(
        {},
        (Step(UNAVAILABLE), Step(_ok("47"), (3.0,))),
        id="500-without-a-rate-limit-header-waits-the-minimum-interval",
    ),
    pytest.param(
        {},
        (Step(_ok()), Step(_ok("47"), (3.0,))),
        id="missing-remaining-waits-the-minimum-interval",
    ),
    pytest.param(
        {},
        (Step(_ok("abc")), Step(_ok("47"), (3.0,))),
        id="non-numeric-remaining-waits-the-minimum-interval",
    ),
    pytest.param(
        {},
        (Step(_ok("")), Step(_ok("47"), (3.0,))),
        id="empty-remaining-is-ignored",
    ),
    pytest.param(
        {},
        (Step(_ok("-1")), Step(_ok("47"), (3.0,))),
        id="negative-remaining-is-ignored",
    ),
    pytest.param(
        {},
        (Step(_ok("1.5")), Step(_ok("47"), (3.0,))),
        id="decimal-remaining-is-ignored",
    ),
    pytest.param(
        {},
        (Step(_ok(" 19 ")), Step(_ok("47"), (58.0,))),
        id="remaining-with-surrounding-spaces-counts",
    ),
    pytest.param(
        {},
        (Step(_ok("30", "5")), Step(_ok("47"), (58.0,))),
        id="the-lowest-of-repeated-remaining-values-counts",
    ),
    pytest.param(
        {},
        (Step(_ok("abc", "5")), Step(_ok("47"), (58.0,))),
        id="an-ignored-value-does-not-hide-a-low-one",
    ),
    pytest.param(
        {},
        (Step(_ok("abc", "30")), Step(_ok("47"), (3.0,))),
        id="an-ignored-value-next-to-a-high-one",
    ),
    pytest.param(
        {},
        (Step(_ok("5", name="x-ratelimit-remaining")), Step(_ok("47"), (58.0,))),
        id="the-header-name-is-matched-ignoring-case",
    ),
    pytest.param(
        {},
        (
            Step(
                _ok(
                    "47",
                    extra=(
                        ("X-RateLimit-Limit", "10"),
                        ("Retry-After", "120"),
                        ("X-RateLimit-Reset", "120"),
                    ),
                )
            ),
            Step(_ok("47"), (3.0,)),
        ),
        id="limit-retry-after-and-reset-are-not-used",
    ),
    pytest.param(
        {},
        (Step(_fails(httpx.ConnectError)), Step(_ok("47"), (3.0,))),
        id="a-failure-before-any-response-waits-the-minimum-interval",
    ),
    pytest.param(
        {},
        (Step(_partial("5")), Step(_ok("47"), (58.0,))),
        id="a-partial-response-with-low-remaining-waits-the-cool-down",
    ),
    pytest.param(
        {},
        (Step(_partial("47")), Step(_ok("47"), (3.0,))),
        id="a-partial-response-with-high-remaining-waits-the-minimum-interval",
    ),
    pytest.param(
        {},
        (
            Step(_ok("47")),
            Step(_ok("5"), (3.0,)),
            Step(_ok("47"), (58.0,)),
            Step(_ok("47"), (3.0,)),
        ),
        id="the-cool-down-depends-only-on-the-previous-attempt",
    ),
    pytest.param(
        {"min_interval": 1, "cooldown": 7, "low_remaining_threshold": 50},
        (
            Step(_ok("47")),
            Step(_ok("60"), (5.0,)),
            Step(_ok("50"), ()),
            Step(_ok("49"), ()),
            Step(_ok("47"), (5.0,)),
        ),
        id="custom-gaps-and-threshold",
    ),
    pytest.param(
        {"min_interval": 1},
        (Step(_ok("47")), Step(_ok("47"), (1.0,), after=0.0)),
        id="custom-minimum-interval",
    ),
    pytest.param(
        {"min_interval": 0},
        (Step(_ok("47")), Step(_ok("47"), (), after=0.0)),
        id="a-zero-minimum-interval-never-waits",
    ),
    pytest.param(
        {"cooldown": 7},
        (Step(RATE_LIMITED), Step(_ok("47"), (5.0,))),
        id="custom-cool-down-after-a-429",
    ),
    pytest.param(
        {"low_remaining_threshold": 0},
        (Step(_ok("0")), Step(_ok("47"), (3.0,))),
        id="threshold-0-never-counts-a-remaining-value-as-low",
    ),
    # Revision 2, SYNTHETIC: a status outside 100 to 599 is a transport error
    # without a response, yet its status and headers still decide the next wait.
    pytest.param(
        {},
        (
            Step(_reply(b"", status=600, headers=_with_remaining("5"))),
            Step(_ok("47"), (58.0,)),
        ),
        id="an-invalid-status-with-low-remaining-waits-the-cool-down",
    ),
    pytest.param(
        {},
        (
            Step(_reply(b"", status=600, headers=JSON_HEADERS)),
            Step(_ok("47"), (3.0,)),
        ),
        id="an-invalid-status-without-a-rate-limit-header-waits-the-minimum-interval",
    ),
    # Revision 3 (audit F-1, family check), SYNTHETIC. A valid `Remaining` is one
    # or more ASCII digits between spaces and tabs only; its number is compared
    # exactly with the threshold, however many digits it has. Any other byte
    # makes the value invalid and ignored. Header values reach the response as
    # Latin-1 bytes (`Reply`), so "\xa0" is the byte 0xA0 and "\xb2" is 0xB2.
    pytest.param(
        {},
        (Step(_ok("0" * 4999 + "5")), Step(_ok("47"), (58.0,))),
        id="remaining-of-4999-zeros-and-a-5-waits-the-cool-down",
    ),
    pytest.param(
        {},
        (Step(_ok("0" * 4300 + "5")), Step(_ok("47"), (58.0,))),
        id="remaining-of-4301-digits-below-the-threshold-waits-the-cool-down",
    ),
    pytest.param(
        {},
        (Step(_ok("0" * 4299 + "5")), Step(_ok("47"), (58.0,))),
        id="remaining-of-4300-digits-below-the-threshold-waits-the-cool-down",
    ),
    pytest.param(
        {},
        (Step(_ok("0" * 5000 + "20")), Step(_ok("47"), (3.0,))),
        id="remaining-of-5002-digits-equal-to-the-threshold-waits-the-minimum",
    ),
    pytest.param(
        {},
        (Step(_ok("9" * 5000)), Step(_ok("47"), (3.0,))),
        id="remaining-of-5000-nines-waits-the-minimum-interval",
    ),
    pytest.param(
        {"low_remaining_threshold": 10**5000},
        (Step(_ok("9" * 4400)), Step(_ok("47"), (58.0,))),
        id="a-threshold-of-5001-digits-is-compared-exactly",
    ),
    pytest.param(
        {},
        (Step(_ok("\xa05")), Step(_ok("47"), (3.0,))),
        id="a-non-breaking-space-makes-remaining-invalid",
    ),
    pytest.param(
        {},
        (Step(_ok("\xb2")), Step(_ok("47"), (3.0,))),
        id="a-superscript-digit-makes-remaining-invalid",
    ),
    pytest.param(
        {},
        (Step(_ok("\t19\t")), Step(_ok("47"), (58.0,))),
        id="remaining-between-tabs-counts",
    ),
]


@pytest.mark.parametrize(("options", "steps"), PACING_CASES)
def test_pacing_waits_follow_remaining_and_429_through_the_injected_sleeper(
    make_rig: Callable[..., Rig], options: dict[str, Any], steps: tuple[Step, ...]
) -> None:
    rig = make_rig(*(step.outcome for step in steps), **options)

    for index, step in enumerate(steps):
        if index > 0:
            rig.clock.advance(step.after)
        sleeps_before = len(rig.clock.sleeps)

        _search_ignoring_source_errors(rig.source)

        assert rig.clock.sleeps[sleeps_before:] == list(step.waits)
        assert len(rig.script.requests) == index + 1


def _raised_by_the_transport(error: BaseException) -> Failure:
    return Failure(lambda request: error)


def _body_read_interrupted_after_a_429(error: BaseException) -> Reply:
    # SYNTHETIC 429: its status and headers arrive, then the body read is cut.
    return _reply(
        status=429,
        headers=(("Content-Type", "text/html"), ("Retry-After", "1")),
        chunks=(b"<html>synthetic",),
        error=error,
    )


def _body_read_interrupted_after_a_low_remaining(error: BaseException) -> Reply:
    return _reply(
        headers=_with_remaining("5"),
        chunks=(SEARCH_SINGLE_PAGE[:50],),
        error=error,
    )


# Revision 2. Each case: the exception the test double raises, how the transport
# raises it, and the waits of the call that follows 2 s after the attempt ended.
UNMAPPED_EXCEPTION_CASES: list[Any] = [
    pytest.param(
        KeyboardInterrupt,
        _raised_by_the_transport,
        (3.0,),
        id="keyboard-interrupt-before-the-status",
    ),
    pytest.param(
        SyntheticTransportDefect,
        _raised_by_the_transport,
        (3.0,),
        id="non-httpx-exception-before-the-status",
    ),
    pytest.param(
        KeyboardInterrupt,
        _body_read_interrupted_after_a_429,
        (58.0,),
        id="keyboard-interrupt-while-reading-a-429",
    ),
    pytest.param(
        KeyboardInterrupt,
        _body_read_interrupted_after_a_low_remaining,
        (58.0,),
        id="keyboard-interrupt-while-reading-a-200-with-low-remaining",
    ),
    # Revision 3 (audit R-3): `SystemExit` is not a source outcome either.
    pytest.param(
        SystemExit,
        _raised_by_the_transport,
        (3.0,),
        id="system-exit-before-the-status",
    ),
    pytest.param(
        SystemExit,
        _body_read_interrupted_after_a_429,
        (58.0,),
        id="system-exit-while-reading-a-429",
    ),
    # Revision 4 (audit R-9): `MemoryError` is not a source outcome either, and it
    # propagates unchanged next to `KeyboardInterrupt` and `SystemExit`.
    pytest.param(
        MemoryError,
        _raised_by_the_transport,
        (3.0,),
        id="memory-error-before-the-status",
    ),
    pytest.param(
        MemoryError,
        _body_read_interrupted_after_a_429,
        (58.0,),
        id="memory-error-while-reading-a-429",
    ),
]


@pytest.mark.parametrize(("error_type", "outcome", "waits"), UNMAPPED_EXCEPTION_CASES)
def test_pacing_counts_an_attempt_that_ends_in_an_unmapped_exception(
    make_rig: Callable[..., Rig],
    error_type: type[BaseException],
    outcome: Callable[[BaseException], Reply | Failure],
    waits: tuple[float, ...],
) -> None:
    error = error_type("synthetic unmapped exception")
    rig = make_rig(outcome(error), _ok("47"))

    with pytest.raises(error_type) as info:
        rig.source.search_page(year=YEAR, buyer=BUYER, page=1)

    assert info.value is error
    assert rig.clock.sleeps == []
    rig.clock.advance(2.0)
    rig.source.search_page(year=YEAR, buyer=BUYER, page=1)

    assert rig.clock.sleeps == list(waits)
    assert len(rig.script.requests) == 2


def test_pacing_is_shared_by_search_and_record_calls(
    make_rig: Callable[..., Rig],
) -> None:
    rig = make_rig(_ok("47"), _reply(RECORD_SINGLE_RELEASE), _ok("19"))

    rig.source.search_page(year=YEAR, buyer=BUYER, page=1)
    rig.clock.advance(2.0)
    rig.source.fetch_record(OCID)
    rig.clock.advance(2.0)
    rig.source.search_page(year=YEAR, buyer=BUYER, page=1)

    assert rig.clock.sleeps == [3.0, 3.0]


def test_pacing_state_belongs_to_each_adapter_instance(
    make_rig: Callable[..., Rig],
) -> None:
    clock = FakeClock()
    first = make_rig(_ok("5"), clock=clock)
    second = make_rig(_ok("47"), clock=clock)

    first.source.search_page(year=YEAR, buyer=BUYER, page=1)
    second.source.search_page(year=YEAR, buyer=BUYER, page=1)

    assert clock.sleeps == []


def test_pacing_ignores_a_call_rejected_as_invalid(
    make_rig: Callable[..., Rig],
) -> None:
    rig = make_rig(_ok("47"), _ok("47"))
    rig.source.search_page(year=YEAR, buyer=BUYER, page=1)
    rig.clock.advance(2.0)

    with pytest.raises(ValueError):
        rig.source.search_page(year=YEAR, buyer=BUYER, page=0)
    assert rig.clock.sleeps == []
    rig.clock.advance(1.0)
    rig.source.search_page(year=YEAR, buyer=BUYER, page=1)

    # 3 s have passed since the first attempt ended: the rejected call changed
    # no pacing state, so the wait is 5 - 3 and not 5 - 1.
    assert rig.clock.sleeps == [2.0]
    assert len(rig.script.requests) == 2


# --- AC10: timeouts, identity encoding and input validation -----------------


@pytest.mark.parametrize("operation", OPERATIONS, ids=lambda o: o.name)
def test_timeout_defaults_are_explicit_on_every_request(
    make_rig: Callable[..., Rig], operation: Operation
) -> None:
    rig = make_rig(_reply(operation.valid_body))

    operation.call(rig.source)

    assert rig.script.requests[0].extensions["timeout"] == {
        "connect": 10.0,
        "read": 30.0,
        "write": 10.0,
        "pool": 10.0,
    }


@pytest.mark.parametrize("operation", OPERATIONS, ids=lambda o: o.name)
def test_timeout_values_follow_the_configuration(
    make_rig: Callable[..., Rig], operation: Operation
) -> None:
    rig = make_rig(_reply(operation.valid_body), connect_timeout=3, read_timeout=40)

    operation.call(rig.source)

    assert rig.script.requests[0].extensions["timeout"] == {
        "connect": 3.0,
        "read": 40.0,
        "write": 3.0,
        "pool": 3.0,
    }


@pytest.mark.parametrize("operation", OPERATIONS, ids=lambda o: o.name)
def test_accept_encoding_asks_for_an_uncompressed_body(
    make_rig: Callable[..., Rig], operation: Operation
) -> None:
    rig = make_rig(_reply(operation.valid_body), _reply(operation.valid_body))

    operation.call(rig.source)
    operation.call(rig.source)

    assert len(rig.script.requests) == 2
    for request in rig.script.requests:
        assert request.headers.get_list("accept-encoding") == ["identity"]


INVALID_SEARCH_ARGUMENTS = [
    pytest.param({"year": YEAR, "buyer": BUYER, "page": 0}, id="page-zero"),
    pytest.param({"year": YEAR, "buyer": BUYER, "page": -1}, id="page-negative"),
    pytest.param({"year": YEAR, "buyer": BUYER, "page": True}, id="page-true"),
    pytest.param({"year": YEAR, "buyer": BUYER, "page": "1"}, id="page-text"),
    pytest.param({"year": YEAR, "buyer": BUYER, "page": 1.0}, id="page-float"),
    pytest.param({"year": 0, "buyer": BUYER, "page": 1}, id="year-zero"),
    pytest.param({"year": -2025, "buyer": BUYER, "page": 1}, id="year-negative"),
    pytest.param({"year": True, "buyer": BUYER, "page": 1}, id="year-true"),
    pytest.param({"year": "2025", "buyer": BUYER, "page": 1}, id="year-text"),
    pytest.param({"year": 2025.0, "buyer": BUYER, "page": 1}, id="year-float"),
    pytest.param({"year": YEAR, "buyer": "", "page": 1}, id="buyer-empty"),
    pytest.param({"year": YEAR, "buyer": 123, "page": 1}, id="buyer-number"),
    pytest.param({"year": YEAR, "buyer": None, "page": 1}, id="buyer-none"),
    # Revision 3 (pinned, AC10): a year or page whose decimal text the interpreter
    # will not write (more than 4,300 digits), and a buyer that cannot be encoded
    # as UTF-8 (a lone surrogate). Explicit ids: writing 10**5000 raises.
    pytest.param(
        {"year": 10**5000, "buyer": BUYER, "page": 1}, id="year-of-5001-digits"
    ),
    pytest.param(
        {"year": YEAR, "buyer": BUYER, "page": 10**5000}, id="page-of-5001-digits"
    ),
    pytest.param(
        {"year": YEAR, "buyer": "\ud800", "page": 1}, id="buyer-lone-surrogate"
    ),
]


@pytest.mark.parametrize("arguments", INVALID_SEARCH_ARGUMENTS)
def test_invalid_search_input_raises_value_error_before_any_request_or_wait(
    make_rig: Callable[..., Rig], arguments: dict[str, Any]
) -> None:
    fresh = make_rig()
    after_a_call = make_rig(_ok("47"))
    after_a_call.source.search_page(year=YEAR, buyer=BUYER, page=1)
    after_a_call.clock.advance(1.0)  # a wait would now be due

    with pytest.raises(ValueError):
        fresh.source.search_page(**arguments)
    with pytest.raises(ValueError):
        after_a_call.source.search_page(**arguments)

    assert fresh.script.requests == []
    assert fresh.clock.sleeps == []
    assert len(after_a_call.script.requests) == 1
    assert after_a_call.clock.sleeps == []


@pytest.mark.parametrize(
    "ocid",
    [
        pytest.param("", id="ocid-empty"),
        pytest.param(None, id="ocid-none"),
        pytest.param(5, id="ocid-number"),
        # Revision 3 (pinned, AC10): a lone surrogate cannot be encoded as UTF-8.
        pytest.param("\ud800", id="ocid-lone-surrogate"),
    ],
)
def test_invalid_record_input_raises_value_error_before_any_request_or_wait(
    make_rig: Callable[..., Rig], ocid: Any
) -> None:
    rig = make_rig(_ok("47"))
    rig.source.search_page(year=YEAR, buyer=BUYER, page=1)
    rig.clock.advance(1.0)

    with pytest.raises(ValueError):
        rig.source.fetch_record(ocid)

    assert len(rig.script.requests) == 1
    assert rig.clock.sleeps == []


# Revision 3 (AC10), SYNTHETIC hosts of exactly 254 and 253 characters, with
# labels of 63 characters at most (RFC 1035 § 2.3.4 allows 253 without the
# trailing dot). They are never resolved: construction decides first.
_HOST_OF_254 = ".".join(("a" * 63, "a" * 63, "a" * 63, "a" * 62))
_HOST_OF_253 = ".".join(("a" * 63, "a" * 63, "a" * 63, "a" * 61))

# Revision 2: base URLs that construction must reject, as (id suffix, URL). The
# user names and secrets are SYNTHETIC. Numeric hosts are never contacted:
# construction fails before any client could use them.
REJECTED_BASE_URLS: tuple[tuple[str, str], ...] = (
    (
        "with-user-and-password",
        "https://synthetic-user:synthetic-secret@source.invalid/PLATAFORMA",
    ),
    ("with-user-only", "https://synthetic-user@source.invalid/PLATAFORMA"),
    ("with-empty-userinfo", "https://@source.invalid/PLATAFORMA"),
    ("port-without-host", "https://:8443/PLATAFORMA"),
    ("port-not-numeric", "https://source.invalid:abc/PLATAFORMA"),
    ("port-empty", "https://source.invalid:/PLATAFORMA"),
    ("port-zero", "https://source.invalid:0/PLATAFORMA"),
    ("port-65536", "https://source.invalid:65536/PLATAFORMA"),
    ("port-99999", "https://source.invalid:99999/PLATAFORMA"),
    ("port-with-sign", "https://source.invalid:+8443/PLATAFORMA"),
    ("port-non-ascii-digit", "https://source.invalid:٣/PLATAFORMA"),
    ("invalid-ipv4-host", "https://999.1.1.1/PLATAFORMA"),
    ("control-character", "https://source.invalid/PLAT\nAFORMA"),
    # Revision 3 (audit F-2, family check): the host as name resolution and TLS
    # receive it, and the room left for the shortest request URL. None of them
    # may reach a call, where each would fail with an unmapped library error.
    ("label-of-64", "https://" + "a" * 64 + ".invalid/PLATAFORMA"),
    ("empty-label", "https://a..invalid/PLATAFORMA"),
    ("leading-dot", "https://.source.invalid/PLATAFORMA"),
    ("two-trailing-dots", "https://source.invalid../PLATAFORMA"),
    ("host-of-254", f"https://{_HOST_OF_254}/PLATAFORMA"),
    ("a-label-malformed", "https://xn--.invalid/PLATAFORMA"),
    ("a-label-disallowed", "https://xn--ls8h.invalid/PLATAFORMA"),
    ("ipv6-zone", "https://[fe80::1%25eth0]/PLATAFORMA"),
    ("ipv6-zone-not-encoded", "https://[fe80::1%eth0]/PLATAFORMA"),
    ("no-room-for-the-request", "https://source.invalid/" + "p" * 65_500),
    # Revision 4 (audit F-5 and R-2): the zone rule holds whatever characters the
    # zone holds (the library raised a `UnicodeEncodeError` with the host text for
    # a non-ASCII zone), and two bracketed hosts that `urlsplit` itself rejects.
    ("ipv6-zone-non-ascii", "https://[fe80::1%25é]/PLATAFORMA"),
    ("ipv6-zone-non-ascii-not-encoded", "https://[fe80::1%éth0]/PLATAFORMA"),
    ("ipv6-zone-non-ascii-with-a-port", "https://[::1%25é]:8443/PLATAFORMA"),
    ("ipv6-zone-zero-width-joiner", "https://[fe80::1%25‍]/PLATAFORMA"),
    ("ipv6-unclosed-bracket", "https://[::1/PLATAFORMA"),
    ("ipv6-invalid-literal", "https://[zz]/PLATAFORMA"),
)


@pytest.mark.parametrize(
    "options",
    [
        pytest.param({"min_interval": -1}, id="min-interval-negative"),
        pytest.param({"cooldown": -1}, id="cooldown-negative"),
        pytest.param({"connect_timeout": 0}, id="connect-timeout-zero"),
        pytest.param({"connect_timeout": -1}, id="connect-timeout-negative"),
        pytest.param({"read_timeout": 0}, id="read-timeout-zero"),
        pytest.param({"read_timeout": -5}, id="read-timeout-negative"),
        pytest.param({"low_remaining_threshold": True}, id="threshold-true"),
        pytest.param({"low_remaining_threshold": -1}, id="threshold-negative"),
        pytest.param({"low_remaining_threshold": 1.5}, id="threshold-float"),
        pytest.param({"base_url": f"{BASE_URL}/"}, id="base-url-ends-with-slash"),
        pytest.param(
            {"base_url": "source.invalid/PLATAFORMA"}, id="base-url-no-scheme"
        ),
        pytest.param(
            {"base_url": "ftp://source.invalid/PLATAFORMA"}, id="base-url-ftp"
        ),
        pytest.param({"base_url": "/PLATAFORMA"}, id="base-url-relative"),
        pytest.param({"base_url": ""}, id="base-url-empty"),
        pytest.param({"base_url": f"{BASE_URL}?x=1"}, id="base-url-with-query"),
        pytest.param({"base_url": f"{BASE_URL}#part"}, id="base-url-with-fragment"),
        # Revision 2: the base URLs of `REJECTED_BASE_URLS`.
        *(
            pytest.param({"base_url": url}, id=f"base-url-{name}")
            for name, url in REJECTED_BASE_URLS
        ),
        # Revision 3 (AC10, project decision): a number that is finite and at
        # most one day (86,400 s). `nan` switched pacing off, `inf` and very
        # large values made every call fail in the socket layer or `time.sleep`.
        pytest.param({"connect_timeout": float("nan")}, id="connect-timeout-nan"),
        pytest.param({"connect_timeout": float("inf")}, id="connect-timeout-inf"),
        pytest.param({"connect_timeout": 86_401}, id="connect-timeout-86401"),
        pytest.param({"connect_timeout": True}, id="connect-timeout-true"),
        pytest.param({"read_timeout": float("nan")}, id="read-timeout-nan"),
        pytest.param({"read_timeout": 1e10}, id="read-timeout-1e10"),
        pytest.param({"min_interval": float("nan")}, id="min-interval-nan"),
        pytest.param({"min_interval": float("inf")}, id="min-interval-inf"),
        pytest.param({"min_interval": 86_401}, id="min-interval-86401"),
        pytest.param({"cooldown": float("nan")}, id="cooldown-nan"),
        pytest.param({"cooldown": float("inf")}, id="cooldown-inf"),
        pytest.param({"cooldown": "60"}, id="cooldown-text"),
    ],
)
def test_invalid_construction_options_raise_value_error(
    options: dict[str, Any],
) -> None:
    with pytest.raises(ValueError):
        SercopSource(transport=httpx.MockTransport(Script()), **options)


def _assert_base_url_not_echoed(error: BaseException, base_url: str) -> None:
    """No `str()` or `repr()` in the chain of `error` shows the URL or a credential.

    The URL is looked for as given and as `repr()` writes it (a control
    character shows as its escape), in the message and in the representation.
    """
    forms = (base_url, repr(base_url)[1:-1])
    for raised in _exception_chain(error):
        for text in (str(raised), repr(raised)):
            assert "synthetic-user" not in text
            assert "synthetic-secret" not in text
            for form in forms:
                assert form not in text


@pytest.mark.parametrize(
    "base_url",
    [pytest.param(url, id=name) for name, url in REJECTED_BASE_URLS],
)
def test_invalid_base_url_is_rejected_without_echoing_it(base_url: str) -> None:
    # Every rejected base URL raises a `ValueError` that neither it nor its
    # `__cause__` / `__context__` chain shows (the library's own `InvalidURL`
    # text repeats parts of the URL, so it must not be chained).
    with pytest.raises(ValueError) as info:
        SercopSource(base_url=base_url, transport=httpx.MockTransport(Script()))

    _assert_base_url_not_echoed(info.value, base_url)


@pytest.mark.parametrize(
    "base_url",
    [
        pytest.param(
            "https://synthetic-user:synthetic-secret@source.invalid/PLATAFORMA",
            id="user-and-password",
        ),
        pytest.param(
            "https://synthetic-user@source.invalid/PLATAFORMA", id="user-only"
        ),
        pytest.param("https://@source.invalid/PLATAFORMA", id="empty-userinfo"),
    ],
)
def test_invalid_base_url_with_userinfo_is_rejected_without_echoing_it(
    base_url: str,
) -> None:
    # SYNTHETIC credentials. The library would turn user information into an
    # `Authorization` header and keep it in the URL as sent (ADR 0003).
    with pytest.raises(ValueError) as info:
        SercopSource(base_url=base_url, transport=httpx.MockTransport(Script()))

    _assert_base_url_not_echoed(info.value, base_url)


@pytest.mark.parametrize(
    "options",
    [
        pytest.param({"min_interval": 0}, id="min-interval-zero"),
        pytest.param({"cooldown": 0}, id="cooldown-zero"),
        pytest.param({"low_remaining_threshold": 0}, id="threshold-zero"),
        pytest.param({"base_url": "http://source.invalid"}, id="http-without-path"),
        pytest.param({"base_url": f"{BASE_URL}/v1"}, id="longer-path"),
        # Revision 2: the lowest, a usual and the highest valid port.
        pytest.param({"base_url": "https://source.invalid:1/PLATAFORMA"}, id="port-1"),
        pytest.param(
            {"base_url": "https://source.invalid:8443/PLATAFORMA"}, id="port-8443"
        ),
        pytest.param(
            {"base_url": "https://source.invalid:65535/PLATAFORMA"}, id="port-65535"
        ),
        # Revision 3 (AC10): the edges of the new rules, and pinned behavior.
        pytest.param(
            {"base_url": "https://" + "a" * 63 + ".invalid/PLATAFORMA"},
            id="label-of-63",
        ),
        pytest.param(
            {"base_url": f"https://{_HOST_OF_253}/PLATAFORMA"}, id="host-of-253"
        ),
        pytest.param(
            {"base_url": f"https://{_HOST_OF_253}./PLATAFORMA"},
            id="host-of-253-with-a-trailing-dot",
        ),
        pytest.param(
            {"base_url": "https://source.invalid./PLATAFORMA"}, id="trailing-dot"
        ),
        pytest.param(
            {"base_url": "https://[::1]:8443/PLATAFORMA"}, id="ipv6-with-a-port"
        ),
        pytest.param(
            {"base_url": "https://source.invalid/PLATAFORMÁ"},
            id="non-ascii-in-the-path",
        ),
        pytest.param(
            {"base_url": "https://source.invalid/P%zz"}, id="percent-in-the-path"
        ),
        pytest.param(
            {
                "connect_timeout": 86_400,
                "read_timeout": 86_400,
                "min_interval": 86_400,
                "cooldown": 86_400,
            },
            id="all-four-numbers-at-one-day",
        ),
        pytest.param(
            {"connect_timeout": 0.5, "read_timeout": 0.5},
            id="timeouts-of-half-a-second",
        ),
    ],
)
def test_construction_accepts_the_documented_boundaries(
    options: dict[str, Any],
) -> None:
    source = SercopSource(transport=httpx.MockTransport(Script()), **options)

    with source as entered:
        assert entered is source


def test_construction_close_may_be_called_directly() -> None:
    source = SercopSource(base_url=BASE_URL, transport=httpx.MockTransport(Script()))

    source.close()


def test_record_query_sends_a_non_ascii_base_path_percent_encoded() -> None:
    # Revision 3 (pinned, AC1 and AC10): the library percent-encodes the path, and
    # the raw response holds the URL as sent. No adapter test double is involved.
    script = Script(_reply(RECORD_SINGLE_RELEASE))
    clock = FakeClock()
    with SercopSource(
        base_url="https://source.invalid/PLATAFORMÁ",
        transport=httpx.MockTransport(script),
        now=FakeWallClock(),
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    ) as source:
        result = source.fetch_record(OCID)

    expected = f"https://source.invalid/PLATAFORM%C3%81/api/record?ocid={OCID}"
    assert len(script.requests) == 1
    assert str(script.requests[0].url) == expected
    assert result.response.url == expected


# Revision 2: an input that makes the request URL longer than the HTTP library
# accepts (65,536 characters in `httpx` 0.28.1) is invalid input. 70,000 does not
# depend on the exact limit.
TOO_LONG_FOR_A_URL = "a" * 70_000


@pytest.mark.parametrize(
    ("operation", "call_too_long"),
    [
        pytest.param(
            SEARCH,
            lambda source: source.search_page(
                year=YEAR, buyer=TOO_LONG_FOR_A_URL, page=1
            ),
            id="search-buyer",
        ),
        pytest.param(
            RECORD,
            lambda source: source.fetch_record(TOO_LONG_FOR_A_URL),
            id="record-ocid",
        ),
    ],
)
def test_invalid_input_too_long_for_a_url_raises_value_error_before_any_request_or_wait(
    make_rig: Callable[..., Rig],
    operation: Operation,
    call_too_long: Callable[[SercopSource], object],
) -> None:
    rig = make_rig(_reply(operation.valid_body), _reply(operation.valid_body))
    operation.call(rig.source)
    rig.clock.advance(1.0)  # a wait of 4 s would now be due

    with pytest.raises(ValueError):
        call_too_long(rig.source)

    assert len(rig.script.requests) == 1
    assert rig.clock.sleeps == []
    rig.clock.advance(1.0)
    operation.call(rig.source)

    # 2 s have passed since the first attempt ended: the rejected call changed
    # no pacing state, so the wait is 5 - 2 and not 5 - 1.
    assert rig.clock.sleeps == [3.0]
    assert len(rig.script.requests) == 2


def test_invalid_input_too_long_year_on_a_long_base_url_raises_value_error() -> None:
    # Revision 3 (AC10): construction accepts this base URL (65,023 characters)
    # and leaves room for the shortest request. A year of 4,000 digits, which the
    # interpreter writes, makes the URL too long: that is invalid input, raised
    # before any request or wait and with no change to pacing. It cannot go
    # through `make_rig`, which fixes the base URL, so the adapter is built here.
    long_base_url = "https://source.invalid/" + "p" * 65_000
    script = Script(_ok("47"), _ok("47"))
    clock = FakeClock()
    with SercopSource(
        base_url=long_base_url,
        transport=httpx.MockTransport(script),
        now=FakeWallClock(),
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    ) as source:
        source.search_page(year=YEAR, buyer=BUYER, page=1)
        clock.advance(1.0)  # a wait of 4 s would now be due

        with pytest.raises(ValueError):
            source.search_page(year=10**3999, buyer=BUYER, page=1)

        assert len(script.requests) == 1
        assert clock.sleeps == []
        clock.advance(1.0)
        source.search_page(year=YEAR, buyer=BUYER, page=1)

    # 2 s have passed since the first attempt ended: the rejected call changed
    # no pacing state, so the wait is 5 - 2 and not 5 - 1.
    assert clock.sleeps == [3.0]
    assert len(script.requests) == 2


def _close_directly(source: SercopSource) -> None:
    source.close()


def _leave_the_with_block(source: SercopSource) -> None:
    with source:
        pass


@pytest.mark.parametrize("operation", OPERATIONS, ids=lambda o: o.name)
@pytest.mark.parametrize(
    "close_it",
    [
        pytest.param(_close_directly, id="close"),
        pytest.param(_leave_the_with_block, id="leaving-the-with-block"),
    ],
)
def test_invalid_use_after_close_raises_runtime_error_before_any_wait(
    make_rig: Callable[..., Rig],
    operation: Operation,
    close_it: Callable[[SercopSource], None],
) -> None:
    rig = make_rig(_reply(operation.valid_body), _reply(operation.valid_body))
    operation.call(rig.source)
    close_it(rig.source)
    rig.clock.advance(1.0)  # a wait of 4 s would now be due

    with pytest.raises(RuntimeError):
        operation.call(rig.source)

    assert len(rig.script.requests) == 1
    assert rig.clock.sleeps == []


@pytest.mark.parametrize(
    "call_invalid",
    [
        pytest.param(
            lambda source: source.search_page(year=YEAR, buyer=BUYER, page=0),
            id="search-page-zero",
        ),
        pytest.param(
            lambda source: source.search_page(year=YEAR, buyer="", page=1),
            id="search-buyer-empty",
        ),
        pytest.param(lambda source: source.fetch_record(""), id="record-ocid-empty"),
    ],
)
def test_invalid_input_after_close_raises_runtime_error_not_value_error(
    make_rig: Callable[..., Rig], call_invalid: Callable[[SercopSource], object]
) -> None:
    # The closed check comes first (execution-plan.md § Binding constraints):
    # an invalid argument on a closed adapter is a usage error, not bad input.
    rig = make_rig(_ok("47"))
    rig.source.search_page(year=YEAR, buyer=BUYER, page=1)
    rig.source.close()
    rig.clock.advance(1.0)  # a wait of 4 s would now be due

    with pytest.raises(RuntimeError):
        call_invalid(rig.source)

    assert len(rig.script.requests) == 1
    assert rig.clock.sleeps == []


# --- AC8, Revision 3: no exception of the HTTP library is chained -----------

# The six malformed-`Location` cases of `STATUS_CASES` (four of Revision 2 and
# two of Revision 3), all SYNTHETIC. They are selected by id, so the cases that
# `test_status_error_carries_the_complete_response` runs are the ones used here.
MALFORMED_LOCATION_IDS = (
    "302-location-not-starting-with-slash",
    "302-location-with-a-tab",
    "307-location-with-an-invalid-ipv4-host",
    "301-location-longer-than-the-url-limit",
    "302-location-host-not-decodable",
    "308-location-scheme-relative-host-not-decodable",
)
MALFORMED_LOCATION_CASES = [
    case for case in STATUS_CASES if case.id in MALFORMED_LOCATION_IDS
]
assert len(MALFORMED_LOCATION_CASES) == len(MALFORMED_LOCATION_IDS)

NO_LIBRARY_EXCEPTION_CASES = [
    # Group 1: every rejected base URL, at construction.
    *(
        pytest.param("base-url", url, id=f"base-url-{name}")
        for name, url in REJECTED_BASE_URLS
    ),
    # Group 2: an input too long for a request URL.
    pytest.param("too-long-input", SEARCH, id="too-long-search-buyer"),
    pytest.param("too-long-input", RECORD, id="too-long-record-ocid"),
    # Group 3: a redirect status whose `Location` the library cannot use.
    *(
        pytest.param(
            "malformed-location",
            (operation, *case.values),
            id=f"location-{case.id}-{operation.name}",
        )
        for case in MALFORMED_LOCATION_CASES
        for operation in OPERATIONS
    ),
]


@pytest.mark.parametrize(("kind", "subject"), NO_LIBRARY_EXCEPTION_CASES)
def test_no_leak_rejections_chain_no_library_exception(
    make_rig: Callable[..., Rig], kind: str, subject: Any
) -> None:
    # The library's own exceptions repeat parts of the URL they rejected or of the
    # `Location` value (a header value). None may be reachable through
    # `__cause__` or `__context__`, and the first two groups have neither.
    error: BaseException
    if kind == "base-url":
        with pytest.raises(ValueError) as value_error:
            SercopSource(base_url=subject, transport=httpx.MockTransport(Script()))
        error = value_error.value
    elif kind == "too-long-input":
        rig = make_rig(_reply(subject.valid_body))
        with pytest.raises(ValueError) as value_error:
            if subject is SEARCH:
                rig.source.search_page(year=YEAR, buyer=TOO_LONG_FOR_A_URL, page=1)
            else:
                rig.source.fetch_record(TOO_LONG_FOR_A_URL)
        error = value_error.value
        assert rig.script.requests == []
    else:
        assert kind == "malformed-location"
        operation, status, body, headers = subject
        rig = make_rig(_reply(body, status=status, headers=headers))
        error = _raise_through(operation, rig)
        assert isinstance(error, SourceStatusError)
        assert len(rig.script.requests) == 1

    if kind != "malformed-location":
        assert error.__cause__ is None
        assert error.__context__ is None
    for raised in _exception_chain(error):
        assert not isinstance(raised, httpx.InvalidURL | httpx.HTTPError), repr(
            type(raised)
        )


# --- AC8, AC10 and AC15, Revision 4: the output invariant -------------------

# SYNTHETIC marker. The sweeps put it in every slot through which text could
# reach an exception: each part of a base URL, each argument of a call, and the
# message of the HTTP library's own errors.
LEAK_MARKER = "synthetic-leak-marker"

# The output invariant (execution-plan.md § Output invariant, I1 to I4) binds
# every exception the adapter raises itself: a source error, and a `ValueError`
# or `RuntimeError` of the constructor or of a call.
OUTPUT_ERROR_TYPES: tuple[type[BaseException], ...] = (
    SourceTransportError,
    SourceStatusError,
    IncompleteResponseError,
    ValueError,
    RuntimeError,
)
# Source errors name the operation; option and input errors name the parameter.
FIXED_MESSAGE_PREFIXES = (
    "search_ocds: ",
    "record: ",
    "base_url ",
    "connect_timeout ",
    "read_timeout ",
    "min_interval ",
    "cooldown ",
    "low_remaining_threshold ",
    "transport ",
    "now ",
    "monotonic ",
    "sleep ",
    "year ",
    "page ",
    "buyer ",
    "ocid ",
)
CLOSED_ADAPTER_MESSAGE = "the source adapter is closed"


def _assert_output_invariant(
    error: BaseException,
    *markers: str,
    check_response: bool = True,
    prefix: str | None = None,
) -> None:
    """Assert I1 to I4 on an exception the adapter raised itself.

    `markers` are the texts that must appear nowhere in the error. With
    `check_response` the carried response is checked too; that is right for a
    marker in what the source sends, and wrong for one in what the caller gave
    (the response's `url` holds the caller's input as sent). `prefix` is the
    start of the message that this case must have.
    """
    # I1: exactly one of five types, so a subclass the interpreter or a library
    # raises (`UnicodeEncodeError`, `idna.IDNAError`) fails here.
    assert type(error) in OUTPUT_ERROR_TYPES, f"I1: type {type(error).__name__}"
    # I2: nothing chained.
    assert error.__cause__ is None, f"I2: cause {type(error.__cause__).__name__}"
    assert error.__context__ is None, f"I2: context {type(error.__context__).__name__}"
    # I3: fixed text. The only argument is the message, printable ASCII, and it
    # starts with the operation or the parameter it concerns.
    message = str(error)
    assert error.args == (message,), "I3: the message is the only argument"
    assert message.isascii(), "I3: the message is ASCII"
    assert message.isprintable(), "I3: the message is printable"
    assert message == CLOSED_ADAPTER_MESSAGE or message.startswith(
        FIXED_MESSAGE_PREFIXES
    ), f"I3: the message starts with an unknown prefix ({message[:20]!r})"
    if prefix is not None:
        assert message.startswith(prefix), f"I3: the message does not start {prefix!r}"
    # I4: no marker in the formatted traceback (which includes any chain), the
    # representation or the arguments, nor in the response when it is checked.
    texts = {
        "traceback": "".join(traceback.format_exception(error)),
        "repr": repr(error),
        "args": repr(error.args),
    }
    response = error.response if isinstance(error, SourceError) else None
    if check_response and response is not None:
        texts["response repr"] = repr(response)
        texts["response str"] = str(response)
    for marker in markers:
        for place, text in texts.items():
            assert marker not in text, f"I4: marker {marker!r} is in the {place}"


class ClosingStream(BodyStream):
    """A `BodyStream` whose `close()` may fail (only a test double can do this).

    The library does not map `ResponseStream.close()`, so no real transport
    raises an `httpx` error from it. SYNTHETIC failures are injected here.
    """

    def __init__(
        self,
        chunks: Sequence[bytes],
        error: BaseException | None,
        close_error: BaseException | None,
    ) -> None:
        super().__init__(chunks, error)
        self._close_error = close_error

    def close(self) -> None:
        if self._close_error is not None:
            raise self._close_error


@dataclass(frozen=True)
class ClosingReply(Reply):
    """A scripted answer whose stream fails when it is closed."""

    close_error: BaseException | None = None

    def to_response(self) -> httpx.Response:
        raw_headers = [
            (name.encode("latin-1"), value.encode("latin-1"))
            for name, value in self.headers
        ]
        return httpx.Response(
            self.status,
            headers=raw_headers,
            stream=ClosingStream(self.chunks, self.error, self.close_error),
        )


# Revision 4, base URLs (T2): nine places a marked payload can go, by sixteen
# payloads that are each a character or a form found to be pathological. Each URL
# either fails construction with a `ValueError` that satisfies I1 to I4, or is
# accepted and then ends a call in a `SourceStatusError` that satisfies I1 to I3.
BASE_URL_TEMPLATES = (
    ("userinfo", "https://{p}@source.invalid/PLATAFORMA"),
    ("first-label", "https://{p}.source.invalid/PLATAFORMA"),
    ("last-labels", "https://source.{p}/PLATAFORMA"),
    ("zone-encoded", "https://[fe80::1%25{p}]/PLATAFORMA"),
    ("zone-not-encoded", "https://[fe80::1%{p}]/PLATAFORMA"),
    ("ipv6-tail", "https://[::1{p}]/PLATAFORMA"),
    ("port", "https://source.invalid:{p}/PLATAFORMA"),
    ("path", "https://source.invalid/{p}"),
    ("scheme", "{p}://source.invalid/PLATAFORMA"),
)
BASE_URL_PAYLOADS = (
    ("marker", LEAK_MARKER),
    ("e-acute", LEAK_MARKER + "é"),
    ("arabic-indic-digit", LEAK_MARKER + "٣"),
    ("zero-width-joiner", LEAK_MARKER + "‍"),
    ("nul", LEAK_MARKER + "\x00"),
    ("tab", LEAK_MARKER + "\t"),
    ("newline", LEAK_MARKER + "\n"),
    ("space", LEAK_MARKER + " "),
    ("percent", LEAK_MARKER + "%"),
    ("percent-zz", LEAK_MARKER + "%zz"),
    ("percent-encoded-e-acute", LEAK_MARKER + "%C3%A9"),
    ("open-bracket", LEAK_MARKER + "["),
    ("close-bracket", LEAK_MARKER + "]"),
    ("at-sign", LEAK_MARKER + "@"),
    ("colon", LEAK_MARKER + ":"),
    ("a-label-prefix", "xn--" + LEAK_MARKER),
)
BASE_URL_SWEEP = [
    pytest.param(template.replace("{p}", payload), id=f"{place}-{kind}")
    for place, template in BASE_URL_TEMPLATES
    for kind, payload in BASE_URL_PAYLOADS
]
assert len(BASE_URL_SWEEP) == 9 * 16


@pytest.mark.parametrize("base_url", BASE_URL_SWEEP)
def test_no_leak_invariant_holds_for_every_base_url_in_the_sweep(
    base_url: str,
) -> None:
    script = Script(_reply(b"synthetic not found", status=404))
    clock = FakeClock()
    try:
        source = SercopSource(
            base_url=base_url,
            transport=httpx.MockTransport(script),
            now=FakeWallClock(),
            monotonic=clock.monotonic,
            sleep=clock.sleep,
        )
    except ValueError as rejected:
        _assert_output_invariant(rejected, LEAK_MARKER, prefix="base_url ")
        assert script.requests == []
        return

    # Accepted: the call reaches the transport and ends as the status error. The
    # marker is in the request URL, so the response is not checked for it.
    with source, pytest.raises(SourceStatusError) as info:
        source.search_page(year=YEAR, buyer=BUYER, page=1)

    _assert_output_invariant(
        info.value, LEAK_MARKER, check_response=False, prefix="search_ocds: "
    )
    assert len(script.requests) == 1
    assert clock.sleeps == []


# Revision 4, call inputs (T3): a marked buyer or `ocid`, a year or page of each
# pathological kind, and a call on a closed adapter. All SYNTHETIC. The explicit
# ids matter: writing 10**5000 as text raises.
CALL_INPUT_TEXTS = (
    ("lone-surrogate-after-the-marker", LEAK_MARKER + "\ud800"),
    ("lone-surrogate-before-the-marker", "\udfff" + LEAK_MARKER),
    ("nul", LEAK_MARKER + "\x00"),
    ("carriage-return-and-line-feed", LEAK_MARKER + "\r\n"),
    ("e-acute", LEAK_MARKER + "é"),
    ("repeated-4000-times", LEAK_MARKER * 4_000),
    ("percent-first", "%" + LEAK_MARKER),
    ("reserved-characters", LEAK_MARKER + "/../?#&="),
)
CALL_INPUT_NUMBERS: tuple[tuple[str, Any], ...] = (
    ("zero", 0),
    ("minus-one", -1),
    ("true", True),
    ("float", 2025.0),
    ("text", "2025"),
    ("none", None),
    ("10-to-the-5000", 10**5000),
    ("10-to-the-4300", 10**4300),
)


def _search_with(**changes: Any) -> Callable[[SercopSource], object]:
    arguments: dict[str, Any] = {"year": YEAR, "buyer": BUYER, "page": 1} | changes

    def call(source: SercopSource) -> object:
        return source.search_page(**arguments)

    return call


def _record_with(ocid: Any) -> Callable[[SercopSource], object]:
    def call(source: SercopSource) -> object:
        return source.fetch_record(ocid)

    return call


def _after_close(call: Callable[[SercopSource], object]) -> Callable[..., object]:
    def closed_call(source: SercopSource) -> object:
        source.close()
        return call(source)

    return closed_call


CALL_INPUT_SWEEP = [
    *(
        pytest.param(_search_with(buyer=value), id=f"buyer-{name}")
        for name, value in CALL_INPUT_TEXTS
    ),
    *(
        pytest.param(_record_with(value), id=f"ocid-{name}")
        for name, value in CALL_INPUT_TEXTS
    ),
    *(
        pytest.param(_search_with(year=value), id=f"year-{name}")
        for name, value in CALL_INPUT_NUMBERS
    ),
    *(
        pytest.param(_search_with(page=value), id=f"page-{name}")
        for name, value in CALL_INPUT_NUMBERS
    ),
    pytest.param(_after_close(_search_with()), id="search-on-a-closed-adapter"),
    pytest.param(_after_close(_record_with(OCID)), id="record-on-a-closed-adapter"),
]
assert len(CALL_INPUT_SWEEP) == 34


@pytest.mark.parametrize("call", CALL_INPUT_SWEEP)
def test_no_leak_invariant_holds_for_every_call_input_in_the_sweep(
    make_rig: Callable[..., Rig], call: Callable[[SercopSource], object]
) -> None:
    rig = make_rig(_reply(b"synthetic not found", status=404))

    with pytest.raises((SourceError, ValueError, RuntimeError)) as info:
        call(rig.source)

    # The marker is in what the caller gave, so the response is not checked.
    error = info.value
    _assert_output_invariant(error, LEAK_MARKER, check_response=False)
    if type(error) in (ValueError, RuntimeError):
        # Rejected input and a closed adapter leave no request and no wait.
        assert rig.script.requests == []
        assert rig.clock.sleeps == []


# Revision 4, what the source sends (T4): the message of every concrete
# `httpx.TransportError`, a status line, a header line and a chunk header, with
# the shape the real protocol parser gives them, quoting rejected bytes. All
# SYNTHETIC. The library's text must never reach the error, whole or in part.
HEADER_LINE_TEXT = (
    "illegal header line: bytearray(b'X-Synthetic: synthetic-header-marker\\x00')"
)
STATUS_LINE_TEXT = (
    "illegal status line: bytearray(b'HTTP/1.1 2000 synthetic-header-marker')"
)
CHUNK_HEADER_TEXT = (
    'illegal chunk header: bytearray(b\'{"total":3,"note":"synthetic-body-marker\')'
)
TRANSPORT_ERROR_TYPES: tuple[type[httpx.TransportError], ...] = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    httpx.ReadError,
    httpx.WriteError,
    httpx.CloseError,
    httpx.RemoteProtocolError,
    httpx.LocalProtocolError,
    httpx.ProxyError,
    httpx.UnsupportedProtocol,
)
TRANSPORT_ERROR_NAMES = tuple(
    error_type.__name__ for error_type in TRANSPORT_ERROR_TYPES
)

# What a case gives the test: the scripted outcome, the class name that the
# message of the transport error must hold (`None` for a status case), and the
# bytes of the partial response (`None`: no response).
SweepOutcome = tuple[Reply | Failure, str | None, bytes | None]


@dataclass(frozen=True)
class SourceSweepCase:
    build: Callable[[Operation], SweepOutcome]


def _raised_before_the_status(
    error_type: type[httpx.TransportError], message: str
) -> SourceSweepCase:
    def build(operation: Operation) -> SweepOutcome:
        failure = Failure(lambda request: error_type(message, request=request))
        return failure, error_type.__name__, None

    return SourceSweepCase(build)


def _raised_while_reading_the_body(
    error_type: type[httpx.TransportError], message: str
) -> SourceSweepCase:
    def build(operation: Operation) -> SweepOutcome:
        outcome = _reply(chunks=(b'{"note":"',), error=error_type(message))
        return outcome, error_type.__name__, b'{"note":"'

    return SourceSweepCase(build)


def _close_fails_after_a_complete_body(operation: Operation) -> SweepOutcome:
    # Rule 3: the failure of the close that `iter_raw` performs after the last
    # chunk is a body failure, and every byte is kept.
    outcome = ClosingReply(
        chunks=(operation.valid_body,),
        close_error=httpx.ReadError(CHUNK_HEADER_TEXT),
    )
    return outcome, "ReadError", operation.valid_body


def _close_fails_after_a_cut(operation: Operation) -> SweepOutcome:
    # The first failure decides (`ReadError`). The `CloseError` of the close that
    # follows is dropped, neither raised nor named, and nothing is chained.
    outcome = ClosingReply(
        chunks=(b"{",),
        error=httpx.ReadError(CHUNK_HEADER_TEXT),
        close_error=httpx.CloseError(CHUNK_HEADER_TEXT),
    )
    return outcome, "ReadError", b"{"


def _a_status_with_markers(status: int) -> SourceSweepCase:
    def build(operation: Operation) -> SweepOutcome:
        headers: Headers = (
            ("X-Synthetic", HEADER_MARKER),
            ("Location", f"http://xn--/{HEADER_MARKER}"),
            ("Set-Cookie", f"synthetic-session={HEADER_MARKER}"),
        )
        outcome = _reply(BODY_MARKER.encode("ascii"), status=status, headers=headers)
        return outcome, None, None

    return SourceSweepCase(build)


SOURCE_SWEEP_CASES = [
    *(
        pytest.param(
            _raised_before_the_status(error_type, HEADER_LINE_TEXT),
            id=f"before-the-status-{error_type.__name__}",
        )
        for error_type in TRANSPORT_ERROR_TYPES
    ),
    pytest.param(
        _raised_before_the_status(httpx.RemoteProtocolError, STATUS_LINE_TEXT),
        id="before-the-status-illegal-status-line",
    ),
    *(
        pytest.param(
            _raised_while_reading_the_body(error_type, CHUNK_HEADER_TEXT),
            id=f"during-the-body-{error_type.__name__}",
        )
        for error_type in (
            httpx.ReadTimeout,
            httpx.ReadError,
            httpx.RemoteProtocolError,
            httpx.CloseError,
        )
    ),
    pytest.param(
        SourceSweepCase(_close_fails_after_a_complete_body),
        id="close-after-a-complete-body",
    ),
    pytest.param(SourceSweepCase(_close_fails_after_a_cut), id="close-after-cut"),
    *(
        pytest.param(_a_status_with_markers(status), id=f"status-{status}")
        for status in (200, 301, 302, 303, 307, 308, 404, 429, 500, 600)
    ),
]
assert len(SOURCE_SWEEP_CASES) == 29


@pytest.mark.parametrize("operation", OPERATIONS, ids=lambda o: o.name)
@pytest.mark.parametrize("case", SOURCE_SWEEP_CASES)
def test_no_leak_invariant_holds_for_what_the_source_sends(
    make_rig: Callable[..., Rig], operation: Operation, case: SourceSweepCase
) -> None:
    outcome, failure_class, partial = case.build(operation)
    rig = make_rig(outcome)

    error = _raise_through(operation, rig)

    # The markers are in what the source sent, so the response is checked too.
    _assert_output_invariant(error, BODY_MARKER, HEADER_MARKER)
    assert len(rig.script.requests) == 1
    if failure_class is not None:
        assert isinstance(error, SourceTransportError)
        # The message names the class of the failure that decided, and no other.
        named = [name for name in TRANSPORT_ERROR_NAMES if name in str(error)]
        assert named == [failure_class]
        if partial is None:
            assert error.response is None
        else:
            response = _response_of(error)
            assert response.status == 200
            assert response.content == partial


@pytest.mark.parametrize(
    "base_url",
    [pytest.param(url, id=name) for name, url in REJECTED_BASE_URLS],
)
def test_invalid_base_url_raises_exactly_value_error_with_a_fixed_reason(
    base_url: str,
) -> None:
    # Audit F-5: a `UnicodeEncodeError` is a `ValueError`, so `pytest.raises` alone
    # would accept it. The type is exact, the reason starts with the option's
    # name, nothing is chained, and the URL is nowhere in the error.
    with pytest.raises(ValueError) as info:
        SercopSource(base_url=base_url, transport=httpx.MockTransport(Script()))

    error = info.value
    assert type(error) is ValueError
    _assert_output_invariant(error, prefix="base_url ")
    _assert_base_url_not_echoed(error, base_url)


# Revision 4 (audit R-8): the options of `test_invalid_construction_options_raise_
# value_error` that do not set `base_url` (Revisions 1 and 3), with their
# prefix, and one case for each type that was accepted or failed later. All
# SYNTHETIC values.
INVALID_OPTION_CASES = [
    pytest.param({"min_interval": -1}, "min_interval ", id="min-interval-negative"),
    pytest.param({"cooldown": -1}, "cooldown ", id="cooldown-negative"),
    pytest.param({"connect_timeout": 0}, "connect_timeout ", id="connect-timeout-zero"),
    pytest.param(
        {"connect_timeout": -1}, "connect_timeout ", id="connect-timeout-negative"
    ),
    pytest.param({"read_timeout": 0}, "read_timeout ", id="read-timeout-zero"),
    pytest.param({"read_timeout": -5}, "read_timeout ", id="read-timeout-negative"),
    pytest.param(
        {"low_remaining_threshold": True},
        "low_remaining_threshold ",
        id="threshold-true",
    ),
    pytest.param(
        {"low_remaining_threshold": -1},
        "low_remaining_threshold ",
        id="threshold-negative",
    ),
    pytest.param(
        {"low_remaining_threshold": 1.5},
        "low_remaining_threshold ",
        id="threshold-float",
    ),
    pytest.param(
        {"connect_timeout": float("nan")}, "connect_timeout ", id="connect-timeout-nan"
    ),
    pytest.param(
        {"connect_timeout": float("inf")}, "connect_timeout ", id="connect-timeout-inf"
    ),
    pytest.param(
        {"connect_timeout": 86_401}, "connect_timeout ", id="connect-timeout-86401"
    ),
    pytest.param(
        {"connect_timeout": True}, "connect_timeout ", id="connect-timeout-true"
    ),
    pytest.param(
        {"read_timeout": float("nan")}, "read_timeout ", id="read-timeout-nan"
    ),
    pytest.param({"read_timeout": 1e10}, "read_timeout ", id="read-timeout-1e10"),
    pytest.param(
        {"min_interval": float("nan")}, "min_interval ", id="min-interval-nan"
    ),
    pytest.param(
        {"min_interval": float("inf")}, "min_interval ", id="min-interval-inf"
    ),
    pytest.param({"min_interval": 86_401}, "min_interval ", id="min-interval-86401"),
    pytest.param({"cooldown": float("nan")}, "cooldown ", id="cooldown-nan"),
    pytest.param({"cooldown": float("inf")}, "cooldown ", id="cooldown-inf"),
    pytest.param({"cooldown": "60"}, "cooldown ", id="cooldown-text"),
    # The type rules: each of these was accepted, or failed with another type.
    pytest.param({"base_url": 123}, "base_url ", id="base-url-int"),
    pytest.param({"base_url": 1.5}, "base_url ", id="base-url-float"),
    pytest.param({"base_url": None}, "base_url ", id="base-url-none"),
    pytest.param(
        {"base_url": b"https://source.invalid/PLATAFORMA"},
        "base_url ",
        id="base-url-bytes",
    ),
    pytest.param({"base_url": bytearray(b"x")}, "base_url ", id="base-url-bytearray"),
    pytest.param({"base_url": ["x"]}, "base_url ", id="base-url-list"),
    pytest.param({"transport": 5}, "transport ", id="transport-int"),
    pytest.param({"transport": "mock"}, "transport ", id="transport-text"),
    pytest.param({"now": 5}, "now ", id="now-int"),
    pytest.param({"monotonic": 5}, "monotonic ", id="monotonic-int"),
    pytest.param({"sleep": 5}, "sleep ", id="sleep-int"),
]
assert len(INVALID_OPTION_CASES) == 32


@pytest.mark.parametrize(("options", "prefix"), INVALID_OPTION_CASES)
def test_invalid_construction_option_raises_exactly_value_error_with_a_fixed_reason(
    options: dict[str, Any], prefix: str
) -> None:
    with pytest.raises(ValueError) as info:
        SercopSource(**({"transport": httpx.MockTransport(Script())} | options))

    error = info.value
    assert type(error) is ValueError
    _assert_output_invariant(error, prefix=prefix)


# --- AC11: no test reaches the network --------------------------------------


def test_no_network_default_transport_is_stopped_by_the_guard(
    network_guard: NetworkGuard,
) -> None:
    network_guard.expect_attempts()
    clock = FakeClock()
    # No `transport`: the library's real transport. `.invalid` never resolves,
    # and the guard raises on any socket or name-resolution attempt first.
    source = SercopSource(
        base_url=BASE_URL,
        now=FakeWallClock(),
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )
    try:
        with pytest.raises(SourceTransportError) as info:
            source.search_page(year=YEAR, buyer=BUYER, page=1)
    finally:
        source.close()

    assert info.value.response is None
    assert len(network_guard.attempts) >= 1
    assert clock.sleeps == []


def test_no_network_guard_blocks_every_patched_socket_path(
    network_guard: NetworkGuard,
) -> None:
    network_guard.expect_attempts()

    with pytest.raises(OSError):
        socket.getaddrinfo("source.invalid", 443)
    with pytest.raises(OSError):
        socket.create_connection(("source.invalid", 443), timeout=0.1)
    with socket.socket() as candidate:
        with pytest.raises(OSError):
            candidate.connect(("source.invalid", 443))
        with pytest.raises(OSError):
            candidate.connect_ex(("source.invalid", 443))

    assert sorted(network_guard.attempts) == [
        "create_connection",
        "getaddrinfo",
        "socket.connect",
        "socket.connect_ex",
    ]


# --- AC12: the adapter satisfies the port -----------------------------------


def test_satisfies_port_the_adapter_is_usable_as_a_procurement_source() -> None:
    script = Script(_reply(SEARCH_SINGLE_PAGE), _reply(RECORD_SINGLE_RELEASE))
    clock = FakeClock()
    source: ProcurementSource = SercopSource(
        transport=httpx.MockTransport(script),
        now=FakeWallClock(),
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )

    page = source.search_page(year=YEAR, buyer=BUYER, page=1)
    record = source.fetch_record(OCID)

    assert isinstance(page, SearchPage)
    assert page.total == 3
    assert isinstance(record, RecordResponse)
    assert record.ocid == OCID
    assert len(script.requests) == 2


# --- Revision 5 (outcome O2e): the caller's handler, class names, the status --
# and a failing stream close (AC8, AC13 and AC15; plan § Output invariant and
# § Statement check). Everything below is SYNTHETIC. The marker is always held
# in a variable: a formatted traceback quotes the line that made the call, so a
# literal there would put the marker in the text that I4 checks.

# Where the marker sits in what the transport delivers (the cases that check the
# carried response): the body and one header value.
MARKER_BYTES = LEAK_MARKER.encode("ascii")
MARKED_HEADERS: Headers = (*JSON_HEADERS, ("X-Synthetic", LEAK_MARKER))
OPERATION_PREFIXES = {SEARCH.name: "search_ocds: ", RECORD.name: "record: "}


def _assert_invariant_with_context(
    error: BaseException,
    context: BaseException | None,
    *markers: str,
    check_response: bool = True,
    prefix: str | None = None,
) -> None:
    """Assert I1 to I4 in their Revision 5 form (plan § Output invariant).

    `context` is `sys.exception()` when the call began: the exception the caller
    was handling in an `except`, a `finally` or an `__exit__`, or `None`. The
    Revision 4 helper `_assert_output_invariant` says `__context__ is None`,
    which is the same answer for a call made outside any handler, and it is
    left as it was. I4 reads the traceback with `chain=False`, so the caller's
    own exception (which may hold anything) is left out.
    """
    # I1: exactly one of five types.
    assert type(error) in OUTPUT_ERROR_TYPES, f"I1: type {type(error).__name__}"
    # I2: no cause, the context is the caller's exception and it is not hidden.
    assert error.__cause__ is None, f"I2: cause {type(error.__cause__).__name__}"
    assert error.__suppress_context__ is False, "I2: the context is hidden"
    assert error.__context__ is context, (
        f"I2: context {type(error.__context__).__name__}, "
        f"expected {type(context).__name__}"
    )
    # I3: fixed text, printable ASCII, starting with the operation or parameter.
    message = str(error)
    assert error.args == (message,), "I3: the message is the only argument"
    assert message.isascii(), "I3: the message is ASCII"
    assert message.isprintable(), "I3: the message is printable"
    assert message == CLOSED_ADAPTER_MESSAGE or message.startswith(
        FIXED_MESSAGE_PREFIXES
    ), f"I3: the message starts with an unknown prefix ({message[:20]!r})"
    if prefix is not None:
        assert message.startswith(prefix), f"I3: the message does not start {prefix!r}"
    # I4: no marker in this error's own text (not in its chain).
    texts = {
        "traceback": "".join(traceback.format_exception(error, chain=False)),
        "repr": repr(error),
        "args": repr(error.args),
    }
    response = error.response if isinstance(error, SourceError) else None
    if check_response and response is not None:
        texts["response repr"] = repr(response)
        texts["response str"] = str(response)
    for marker in markers:
        for place, text in texts.items():
            assert marker not in text, f"I4: marker {marker!r} is in the {place}"


# T5: a call made while the caller handles an exception. The audit's F-8: Python
# links that exception as the `__context__` of whatever the call raises, and no
# code can clear it (`from None` only hides it). The adapter must chain nothing
# of its own and must not hide that link.


class SyntheticCallerError(Exception):
    """SYNTHETIC: the caller's own exception, handled while it calls the adapter.

    Its message holds the marker, as anything the caller handles may.
    """


def _in_an_except_block(
    action: Callable[[], object],
) -> tuple[BaseException, BaseException]:
    """Run `action` inside `except SyntheticCallerError`; return both exceptions."""
    caller_text = LEAK_MARKER
    try:
        raise SyntheticCallerError(caller_text)
    except SyntheticCallerError as caller_error:
        try:
            action()
        except (SourceError, ValueError, RuntimeError) as error:
            return error, caller_error
    pytest.fail("the call did not raise")


def _in_a_finally_block(
    action: Callable[[], object],
) -> tuple[BaseException, BaseException]:
    """Run `action` inside a `finally` while `SyntheticCallerError` propagates."""
    caller_text = LEAK_MARKER
    raised: list[BaseException] = []
    try:
        try:
            raise SyntheticCallerError(caller_text)
        finally:
            try:
                action()
            except (SourceError, ValueError, RuntimeError) as error:
                raised.append(error)
    except SyntheticCallerError as caller_error:
        assert len(raised) == 1, "the call did not raise"
        return raised[0], caller_error
    pytest.fail("the caller's exception did not propagate")


@dataclass(frozen=True)
class HandlerRun:
    """What one case saw: the adapter's error and the exception it must chain."""

    error: BaseException
    context: BaseException
    expected_type: type[BaseException]
    prefix: str
    check_response: bool


HandlerCase = Callable[[Callable[..., Rig]], HandlerRun]


def _construction_in_a_handler(prefix: str, **options: Any) -> HandlerCase:
    def run(make_rig: Callable[..., Rig]) -> HandlerRun:
        arguments: dict[str, Any] = {
            "base_url": BASE_URL,
            "transport": httpx.MockTransport(Script()),
        } | options

        def construct() -> object:
            return SercopSource(**arguments)

        error, caller_error = _in_an_except_block(construct)
        return HandlerRun(error, caller_error, ValueError, prefix, False)

    return run


def _call_in_a_handler(
    call: Callable[[SercopSource], object],
    outcome: Callable[[], Reply | Failure],
    expected_type: type[BaseException],
    prefix: str,
    *,
    delivered: bool,
) -> HandlerCase:
    """`delivered`: the marker is in what the transport sent, so the response is checked."""

    def run(make_rig: Callable[..., Rig]) -> HandlerRun:
        rig = make_rig(outcome())
        error, caller_error = _in_an_except_block(lambda: call(rig.source))
        return HandlerRun(error, caller_error, expected_type, prefix, delivered)

    return run


def _retry_in_a_handler(operation: Operation) -> HandlerCase:
    """A second call inside `except SourceError as first`: its context is `first`."""

    def run(make_rig: Callable[..., Rig]) -> HandlerRun:
        rig = make_rig(
            _reply(MARKER_BYTES, status=404, headers=MARKED_HEADERS),
            _reply(MARKER_BYTES, status=429, headers=MARKED_HEADERS),
        )
        try:
            operation.call(rig.source)
        except SourceError as first:
            # The first call was made outside any handler.
            assert first.__context__ is None, "the first error has a context"
            try:
                operation.call(rig.source)
            except SourceError as second:
                prefix = OPERATION_PREFIXES[operation.name]
                return HandlerRun(second, first, SourceStatusError, prefix, True)
            pytest.fail("the retry did not raise")
        pytest.fail("the first call did not raise")

    return run


def _call_in_a_finally(operation: Operation) -> HandlerCase:
    def run(make_rig: Callable[..., Rig]) -> HandlerRun:
        rig = make_rig(_reply(MARKER_BYTES, status=404, headers=MARKED_HEADERS))
        error, caller_error = _in_a_finally_block(lambda: operation.call(rig.source))
        prefix = OPERATION_PREFIXES[operation.name]
        return HandlerRun(error, caller_error, SourceStatusError, prefix, True)

    return run


# SYNTHETIC call inputs. Each is built in a variable first.
_SURROGATE_TEXT = LEAK_MARKER + "\ud800"
_TOO_LONG_TEXT = LEAK_MARKER + "a" * 70_000


def _marked_failure() -> Failure:
    # Rule 1: the library error's own text holds the marker.
    return Failure(lambda request: httpx.ConnectError(LEAK_MARKER, request=request))


def _marked_status(status: int) -> Callable[[], Reply | Failure]:
    return lambda: _reply(MARKER_BYTES, status=status, headers=MARKED_HEADERS)


def _marked_cut_off() -> Reply:
    # Rule 3: a first chunk, then a library error whose text holds the marker.
    return _reply(
        chunks=(b"{" + MARKER_BYTES,),
        headers=MARKED_HEADERS,
        error=httpx.ReadError(LEAK_MARKER),
    )


def _handler_cases_of(
    operation: Operation,
    invalid_argument: Callable[[SercopSource], object],
    invalid_prefix: str,
    surrogate: Callable[[SercopSource], object],
    surrogate_prefix: str,
    too_long: Callable[[SercopSource], object],
) -> list[Any]:
    name = operation.name
    prefix = OPERATION_PREFIXES[name]
    filler = _marked_status(404)
    return [
        pytest.param(
            _call_in_a_handler(
                invalid_argument, filler, ValueError, invalid_prefix, delivered=False
            ),
            id=f"{name}-invalid-argument",
        ),
        pytest.param(
            _call_in_a_handler(
                surrogate, filler, ValueError, surrogate_prefix, delivered=False
            ),
            id=f"{name}-lone-surrogate",
        ),
        pytest.param(
            _call_in_a_handler(too_long, filler, ValueError, prefix, delivered=False),
            id=f"{name}-too-long-for-a-url",
        ),
        pytest.param(
            _call_in_a_handler(
                _after_close(operation.call),
                filler,
                RuntimeError,
                CLOSED_ADAPTER_MESSAGE,
                delivered=False,
            ),
            id=f"{name}-closed-adapter",
        ),
        pytest.param(
            _call_in_a_handler(
                operation.call,
                _marked_failure,
                SourceTransportError,
                prefix,
                delivered=True,
            ),
            id=f"{name}-rule-1-failure-before-the-status",
        ),
        pytest.param(
            _call_in_a_handler(
                operation.call,
                _marked_status(600),
                SourceTransportError,
                prefix,
                delivered=True,
            ),
            id=f"{name}-rule-2-invalid-status",
        ),
        pytest.param(
            _call_in_a_handler(
                operation.call,
                _marked_cut_off,
                SourceTransportError,
                prefix,
                delivered=True,
            ),
            id=f"{name}-rule-3-cut-off-body",
        ),
        pytest.param(
            _call_in_a_handler(
                operation.call, filler, SourceStatusError, prefix, delivered=True
            ),
            id=f"{name}-rule-4-status-error",
        ),
        pytest.param(
            _call_in_a_handler(
                operation.call,
                _marked_status(200),
                IncompleteResponseError,
                prefix,
                delivered=True,
            ),
            id=f"{name}-rule-5-unusable-200",
        ),
    ]


HANDLER_CASES: list[Any] = [
    pytest.param(
        _construction_in_a_handler("base_url ", base_url="https://[::1/PLATAFORMA"),
        id="construction-unclosed-bracket-in-the-base-url",
    ),
    pytest.param(
        _construction_in_a_handler("min_interval ", min_interval=-1),
        id="construction-negative-min-interval",
    ),
    pytest.param(
        _construction_in_a_handler("transport ", transport=5),
        id="construction-transport-of-the-wrong-type",
    ),
    *_handler_cases_of(
        SEARCH,
        _search_with(page=0),
        "page ",
        _search_with(buyer=_SURROGATE_TEXT),
        "buyer ",
        _search_with(buyer=_TOO_LONG_TEXT),
    ),
    *_handler_cases_of(
        RECORD,
        _record_with(""),
        "ocid ",
        _record_with(_SURROGATE_TEXT),
        "ocid ",
        _record_with(_TOO_LONG_TEXT),
    ),
    *(
        pytest.param(_retry_in_a_handler(operation), id=f"{operation.name}-retry")
        for operation in OPERATIONS
    ),
    *(
        pytest.param(_call_in_a_finally(operation), id=f"{operation.name}-finally")
        for operation in OPERATIONS
    ),
]
assert len(HANDLER_CASES) == 25


@pytest.mark.parametrize("case", HANDLER_CASES)
def test_no_leak_invariant_context_is_the_callers_own_exception(
    make_rig: Callable[..., Rig], case: HandlerCase
) -> None:
    observed = case(make_rig)

    assert type(observed.error) is observed.expected_type
    _assert_invariant_with_context(
        observed.error,
        observed.context,
        LEAK_MARKER,
        check_response=observed.check_response,
        prefix=observed.prefix,
    )


# T6: the class a message names. A test double can define any class that derives
# from `httpx.HTTPError`, with any name; the message may name only a class that
# `httpx` itself exports (the nearest one in the failure's class hierarchy).


def _renamed_write_error() -> type[Any]:
    # SYNTHETIC: the name is set after the class exists, as a double might.
    renamed = type("Placeholder", (httpx.WriteError,), {})
    renamed.__name__ = LEAK_MARKER
    return renamed


# Each entry: the case id, a SYNTHETIC test-local class, and the name the message
# must end with.
DOUBLE_ERROR_CLASSES: tuple[tuple[str, type[Any], str], ...] = (
    ("non-ascii-name", type("Falloé", (httpx.ReadError,), {}), "ReadError"),
    (
        "name-is-the-marker",
        type(LEAK_MARKER, (httpx.ConnectError,), {}),
        "ConnectError",
    ),
    (
        "name-with-a-newline",
        type("Bad\nName", (httpx.RemoteProtocolError,), {}),
        "RemoteProtocolError",
    ),
    (
        "name-of-200-characters",
        type("X" * 200, (httpx.ReadTimeout,), {}),
        "ReadTimeout",
    ),
    ("name-set-to-the-marker-later", _renamed_write_error(), "WriteError"),
    (
        "direct-subclass-of-http-error",
        type(LEAK_MARKER, (httpx.HTTPError,), {}),
        "HTTPError",
    ),
    (
        "two-httpx-bases",
        type(LEAK_MARKER, (httpx.ReadError, httpx.WriteError), {}),
        "ReadError",
    ),
)


def _double_error(
    error_class: type[Any], message: str, request: httpx.Request | None = None
) -> BaseException:
    error: BaseException
    if issubclass(error_class, httpx.RequestError):
        error = error_class(message, request=request)
    else:
        error = error_class(message)
    return error


@pytest.mark.parametrize("operation", OPERATIONS, ids=lambda o: o.name)
@pytest.mark.parametrize("place", ["before-the-status", "after-one-chunk"])
@pytest.mark.parametrize(
    ("error_class", "expected"),
    [
        pytest.param(cls, name, id=case_id)
        for case_id, cls, name in DOUBLE_ERROR_CLASSES
    ],
)
def test_no_leak_invariant_names_only_a_class_that_httpx_exports(
    make_rig: Callable[..., Rig],
    operation: Operation,
    place: str,
    error_class: type[Any],
    expected: str,
) -> None:
    message = LEAK_MARKER
    outcome: Reply | Failure
    partial: bytes | None
    if place == "before-the-status":
        outcome = Failure(lambda request: _double_error(error_class, message, request))
        partial = None
    else:
        partial = b"{"
        outcome = _reply(chunks=(partial,), error=_double_error(error_class, message))
    rig = make_rig(outcome)

    error = _raise_through(operation, rig)

    assert isinstance(error, SourceTransportError)
    _assert_invariant_with_context(
        error, None, LEAK_MARKER, prefix=OPERATION_PREFIXES[operation.name]
    )
    assert str(error).endswith(f" ({expected})"), (
        f"the message does not end with ({expected}), the class httpx exports"
    )
    if partial is None:
        assert error.response is None
    else:
        assert _response_of(error).content == partial
    assert len(rig.script.requests) == 1


# T7: the status is read by value. A test double can answer with an `int`
# subclass whose own methods write any text; none of it may reach a message or
# the response.


class SyntheticStatus(int):
    """SYNTHETIC: an `int` subclass that a test double answers as a status.

    Formatting it writes the marker followed by a non-ASCII letter, and `str()`
    and `repr()` write the marker.
    """

    def __format__(self, format_spec: str) -> str:
        return LEAK_MARKER + "é"

    def __str__(self) -> str:
        return LEAK_MARKER

    def __repr__(self) -> str:
        return LEAK_MARKER


# Each entry: the case id, the scripted answer, the exact error type, the status
# of the carried response (`None`: no response) and a part of the message.
STATUS_SUBCLASS_CASES: tuple[
    tuple[str, Callable[[], Reply], type[BaseException], int | None, str | None], ...
] = (
    (
        "rule-2-invalid-status",
        lambda: _reply(b"synthetic body", status=SyntheticStatus(600)),
        SourceTransportError,
        None,
        "status 600",
    ),
    (
        "rule-3-cut-off-body",
        lambda: _reply(
            status=SyntheticStatus(200),
            chunks=(b"{",),
            error=httpx.ReadError("synthetic cut-off"),
        ),
        SourceTransportError,
        200,
        "(status 200)",
    ),
    (
        "rule-4-status-error",
        lambda: _reply(b"synthetic not found", status=SyntheticStatus(404)),
        SourceStatusError,
        404,
        "status 404",
    ),
    (
        "rule-5-unusable-200",
        lambda: _reply(b"nope", status=SyntheticStatus(200)),
        IncompleteResponseError,
        200,
        None,
    ),
)


@pytest.mark.parametrize("operation", OPERATIONS, ids=lambda o: o.name)
@pytest.mark.parametrize(
    ("build", "expected_type", "status", "message_part"),
    [
        pytest.param(build, error_type, status, part, id=case_id)
        for case_id, build, error_type, status, part in STATUS_SUBCLASS_CASES
    ],
)
def test_no_leak_invariant_reads_the_status_as_an_exact_int(
    make_rig: Callable[..., Rig],
    operation: Operation,
    build: Callable[[], Reply],
    expected_type: type[BaseException],
    status: int | None,
    message_part: str | None,
) -> None:
    rig = make_rig(build())

    error = _raise_through(operation, rig)
    carried = error.response

    assert type(error) is expected_type
    # The marker is in what the transport delivered (its status), so the
    # response is checked too.
    _assert_invariant_with_context(
        error, None, LEAK_MARKER, prefix=OPERATION_PREFIXES[operation.name]
    )
    if message_part is not None:
        assert message_part in str(error)
    if status is None:
        assert carried is None
    else:
        assert carried is not None
        response = carried
        assert type(response.status) is int
        assert response.status == status
    assert len(rig.script.requests) == 1


# AC15, Revision 5 (plan § Statement check S21 to S23): the stream's `close()`
# fails after a read that ended in an interrupt or a defect. The first exception
# decides; before Revision 5 the close's `httpx` error replaced it and was
# dropped, and the call went on to build a result from the bytes already read.

# Each entry: the case id, the first exception (not an `httpx` error) and the
# `httpx` error that the stream's `close()` then raises.
FAILING_CLOSE_CASES: tuple[
    tuple[str, type[BaseException], type[httpx.TransportError]], ...
] = (
    ("keyboard-interrupt-then-close-error", KeyboardInterrupt, httpx.CloseError),
    ("system-exit-then-read-error", SystemExit, httpx.ReadError),
    ("memory-error-then-close-error", MemoryError, httpx.CloseError),
    ("transport-defect-then-close-error", SyntheticTransportDefect, httpx.CloseError),
)


@pytest.mark.parametrize("operation", OPERATIONS, ids=lambda o: o.name)
@pytest.mark.parametrize(
    ("first_type", "close_type"),
    [
        pytest.param(first, close, id=case_id)
        for case_id, first, close in FAILING_CLOSE_CASES
    ],
)
def test_transport_defect_survives_a_failing_stream_close(
    make_rig: Callable[..., Rig],
    operation: Operation,
    first_type: type[BaseException],
    close_type: type[httpx.TransportError],
) -> None:
    # SYNTHETIC: a `200` with a low `Remaining` streams the complete valid body,
    # raises the first exception, and then its `close()` raises the second one.
    first = first_type("synthetic first exception")
    outcome = ClosingReply(
        headers=_with_remaining("5"),
        chunks=(operation.valid_body,),
        error=first,
        close_error=close_type("synthetic failing close"),
    )
    rig = make_rig(outcome, _reply(b"synthetic not found", status=404))

    with pytest.raises(first_type) as info:
        operation.call(rig.source)

    assert info.value is first
    assert len(rig.script.requests) == 1
    assert rig.clock.sleeps == []
    # The attempt counted: `Remaining: 5` asks for the cool-down (60 s, 2 s gone).
    rig.clock.advance(2.0)
    later = _raise_through(operation, rig)
    assert isinstance(later, SourceStatusError)
    assert rig.clock.sleeps == [58.0]
    assert len(rig.script.requests) == 2


@pytest.mark.parametrize("operation", OPERATIONS, ids=lambda o: o.name)
def test_transport_defect_from_the_stream_close_follows_python_chaining(
    make_rig: Callable[..., Rig], operation: Operation
) -> None:
    # SYNTHETIC: this case pins Python's own rule, not an adapter rule. A second
    # exception that is not an `httpx` error is not caught, so it propagates as
    # the same object with the first as its `__context__`.
    first = SyntheticTransportDefect("synthetic first defect")
    second = SyntheticTransportDefect("synthetic second defect")
    outcome = ClosingReply(chunks=(b"{",), error=first, close_error=second)
    rig = make_rig(outcome)

    with pytest.raises(SyntheticTransportDefect) as info:
        operation.call(rig.source)

    assert info.value is second
    assert second.__context__ is first
    assert len(rig.script.requests) == 1
