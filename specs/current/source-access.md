# Source Access Specification

> Last synced: 2026-10-28. Owned artifacts: `src/ec_procurement_quality/domain/source_response.py`, `src/ec_procurement_quality/application/procurement_source.py`, `src/ec_procurement_quality/infrastructure/sercop_source.py`, `tests/unit/test_source_response.py`, `tests/unit/test_sercop_source.py`, `tests/fixtures/sercop/`. Shared with `project-toolchain`: the `httpx` entry in `pyproject.toml` and `uv.lock`, and `test_layer_only_infrastructure_imports_httpx` in `tests/unit/test_layers.py`.

## Purpose

How the system asks the SERCOP open-contracting portal for one page of the
buyer-name search (`search_ocds`) or for one record by `ocid` (`api/record`)
and gets the response back exactly as received, or a typed error that still
carries whatever valid response arrived, so that F4 can store every response
through `RawEvidenceStore.store` (`raw-evidence`, ADR 0005) without changes. It
is its own capability because it is the only code that talks to the source.
Since F4 the `ingest` command calls it for the buyer-name search (no command
fetches `api/record` yet); it is verified with fixtures and a simulated
transport, never the network, and no run against the real portal has been made
yet (U1). The binding decision for the HTTP client is ADR 0006.

## Requirements

### Requirement: SA-1 — Port and result types

The system SHALL expose a `ProcurementSource` port in `application` with
`search_page(*, year, buyer, page) -> SearchPage` and `fetch_record(ocid) ->
RecordResponse`. `SearchPage` SHALL hold `response`, `total`, `page`, `pages`
and `record_count` (the number of entries in `data`), and a read-only
`is_beyond_last_page`, true exactly when `page > pages`. `RecordResponse` SHALL
hold `response`, `ocid` and `release_count`. The `SercopSource` adapter in
`infrastructure` SHALL satisfy the port structurally.

**Source:** sercop-source-adapter · intent.md § AC1, AC2, AC4, AC12; execution-plan.md § Binding constraints "Public names and signatures"

#### Scenario: Search result
- **WHEN** year `2025`, page `1` and buyer `EMPRESA ELÉCTRICA QUITO S.A. E.E.Q.` are searched and the transport answers `200` with the bytes of `search_single_page.json`
- **THEN** the result has `total` 3, `page` 1, `pages` 1, `record_count` 3 and `is_beyond_last_page` false, and its `response` has method `GET`, status `200` and content equal to the fixture bytes

#### Scenario: Record result
- **WHEN** `ocid` `ocds-5wno2w-SYNTHETIC-A` is fetched and the transport answers `200` with the bytes of `record_single_release.json`
- **THEN** the result has that `ocid` and `release_count` 1, and its content equals the fixture bytes with every `\/` unchanged

### Requirement: SA-2 — One request per call, in the observed form

The system SHALL send exactly one `GET` per call and SHALL NOT retry, follow
redirects or send any other request. A search SHALL go to
`<base>/api/search_ocds?local=1&year=<year>&page=<page>&buyer=<buyer>` with the
parameters in that order, the buyer percent-encoded in UTF-8 with spaces as
`%20`, and no keyword parameter. A record call SHALL go to
`<base>/api/record?ocid=<ocid>`. The default base URL is the observed
`https://datosabiertos.compraspublicas.gob.ec/PLATAFORMA`. `local=1` is a
constant with no assigned meaning.

**Source:** sercop-source-adapter · intent.md § AC1, AC2, AC5; execution-plan.md § Binding constraints "Request format"

#### Scenario: Observed query
- **WHEN** year `2025`, page `1` and the E.E.Q. buyer name are searched against `https://source.invalid/PLATAFORMA`
- **THEN** exactly one request is made, to `https://source.invalid/PLATAFORMA/api/search_ocds?local=1&year=2025&page=1&buyer=EMPRESA%20EL%C3%89CTRICA%20QUITO%20S.A.%20E.E.Q.`, with no other query parameter

### Requirement: SA-3 — The response is kept as received

The system SHALL return the response as a `RawResponse` (in `domain`) with
`method`, `url` (as sent), `status` (an `int` from 100 to 599), `headers` (ordered
`(name, value)` pairs, names in the case received, repeats kept, `Set-Cookie`
passed on unchanged), `captured_at` (from an injected clock, keeping its UTC
offset) and `content` (the message-body bytes after chunked transfer decoding
and before any content decoding). Its fields SHALL map one to one onto the
keyword arguments of `RawEvidenceStore.store` apart from `execution_id` and
`sequence`. Every request SHALL carry `Accept-Encoding: identity` and no
`Cookie` header, and the adapter SHALL keep no cookies: nothing parses a
`Set-Cookie` value during a call, so no value can produce an error, a log
record or a warning.

**Source:** sercop-source-adapter · intent.md § AC3, AC10; execution-plan.md § Binding constraints "Response capture"

#### Scenario: Chunked response with a cookie
- **WHEN** a `200` is delivered in three chunks with the headers `Content-Type`, `Docker-Distribution-Api-Version` (twice), `X-RateLimit-Limit`, `X-RateLimit-Remaining` and a synthetic `Set-Cookie`, at injected time `2026-10-10T06:58:00-05:00`
- **THEN** the headers are exactly those six pairs in that order, the content is the concatenated chunks, `captured_at` is that time, the raw response is accepted by `LocalDiskRawEvidenceStore.store`, and the next request carries no `Cookie` header

#### Scenario: Hostile cookie value
- **WHEN** a valid `200` adds a `Set-Cookie` whose `expires` holds 5,000 `9`
- **THEN** the result is the same as without it, no warning is issued, and the next request carries no `Cookie` header

### Requirement: SA-4 — A page beyond the last page is a valid result

The system SHALL return a search result, not an error, for a page beyond the
last page and for a search with no results, and the result SHALL say so through
`is_beyond_last_page`, so an empty `data` is never read as "no results" on its
own.

**Source:** sercop-source-adapter · intent.md § AC4

#### Scenario: Out of range (observed)
- **WHEN** page 30 is answered with `search_page_out_of_range.json`
- **THEN** `total` is 284, `page` 30, `pages` 29, `record_count` 0, `is_beyond_last_page` true, and no error is raised

#### Scenario: No results (inferred, not observed)
- **WHEN** page 1 is answered with `search_no_results.json`
- **THEN** `total` is 0, `pages` 0, `record_count` 0 and `is_beyond_last_page` true, with no error

### Requirement: SA-5 — A status other than 200 is a typed error with the response

The system SHALL raise `SourceStatusError`, carrying the complete raw response
(status, headers, exact body), for any status from 100 to 599 other than `200`.
It SHALL NOT read `Retry-After`, parse a non-`200` body or follow a redirect. The
`Location` header SHALL be kept as received and never interpreted: whatever it
holds (absent, relative, malformed, too long, or a host that cannot be decoded),
it never changes the outcome.

**Source:** sercop-source-adapter · intent.md § AC5

#### Scenario: Rate limit and server errors
- **WHEN** the transport answers `429` with a synthetic HTML body and `Retry-After: 1`, `500` with an empty body, or `404` for an `ocid`
- **THEN** `SourceStatusError` is raised whose response has that status and exactly that body

#### Scenario: Malformed redirect
- **WHEN** the transport answers `302` with `Location: https:abc`, or `308` with `Location: //xn--/`
- **THEN** `SourceStatusError` is raised with the status, the exact body and the `Location` unchanged, after exactly one request

### Requirement: SA-6 — A transport failure is a typed error, with the partial response when there is one

The system SHALL raise `SourceTransportError` for a failure of the HTTP
transport. It SHALL carry no response when the failure came before the status
and headers arrived, and SHALL carry a partial raw response (status, headers,
the bytes received so far) when the failure came after them. A message whose
status is outside 100 to 599 is not a valid HTTP response and cannot be stored
by `raw-evidence` (RE-11): it SHALL raise `SourceTransportError` with no
response, whose message names the operation and the status number and not the
body.

**Source:** sercop-source-adapter · intent.md § AC6; execution-plan.md § Binding constraints "Outcome mapping"

#### Scenario: Connection failure
- **WHEN** the transport raises a connect error or a read timeout before answering
- **THEN** `SourceTransportError` is raised with no response

#### Scenario: Cut-off body
- **WHEN** the transport sends status `200` and the first 100 bytes of `search_single_page.json`, then raises a protocol error
- **THEN** `SourceTransportError` is raised whose response has status `200` and content equal to those 100 bytes

#### Scenario: Invalid status
- **WHEN** the transport answers status `600`, `999` or `99` with a body
- **THEN** `SourceTransportError` is raised with no response, after exactly one request, and its message holds the operation and the status number and not the body

### Requirement: SA-7 — An unusable 200 is a typed error, never a partial result

The system SHALL raise `IncompleteResponseError`, carrying the complete raw
response, for a complete `200` whose body is unusable. A search body SHALL be
strict UTF-8 JSON (RFC 8259) whose top level is an object with `total`, `page`
and `pages` as non-negative integers (a boolean is rejected) and `data` as a
list, and its `page` SHALL equal the requested page. A record body SHALL be
strict UTF-8 JSON whose top level is an object with a non-empty `releases` list
in which every release is an object whose `ocid` equals the requested one.
`NaN`, `Infinity` and `-Infinity`, an integer of more than 4,300 digits, and
nesting too deep for the parser make a body unusable. For a repeated name the
last value counts. Nothing else is checked.

**Source:** sercop-source-adapter · intent.md § AC7

#### Scenario: Unusable bodies
- **WHEN** a `200` carries the first half of a valid body, bytes that are not UTF-8, a top-level list, `total` as `"3"` or `true`, `data` as `null`, `page` 2 for page 1, a gzip body, or a record whose release has another `ocid`
- **THEN** `IncompleteResponseError` is raised and its response holds exactly the bytes sent

#### Scenario: Repeated name
- **WHEN** the body is `{"total": 3, "page": 2, "page": 1, "pages": 1, "data": []}` for page 1
- **THEN** a valid result for page 1 is returned

### Requirement: SA-8 — No response content leaks, and nothing raised during a call is chained

The system SHALL keep body bytes and header values out of every message,
`str()` and `repr()` of its errors and of `RawResponse`, and SHALL write no log
record of its own. Every exception it creates and raises to its caller SHALL be
exactly one of `SourceTransportError`, `SourceStatusError`,
`IncompleteResponseError`, `ValueError` or `RuntimeError`, with its only
argument a fixed printable ASCII message that starts with the operation or the
parameter (or is exactly `the source adapter is closed`). It SHALL have no
`__cause__`, and its `__context__` SHALL be only the exception the caller was
already handling when the call started, or `None`, left visible (the adapter
writes no `from` clause). The message of a transport error SHALL name the
nearest class that the `httpx` package exports for the failure (for example
`ReadTimeout`), and the status SHALL be read as an exact `int`.

**Source:** sercop-source-adapter · intent.md § AC8 (Revisions 3 to 5); execution-plan.md § Output invariant, § Statement check

#### Scenario: Markers
- **WHEN** a success, a `429`, an invalid-JSON `200` and a cut-off body carry the synthetic markers `synthetic-body-marker` and `synthetic-header-marker`
- **THEN** neither marker appears in any message, `str()`, `repr()`, `args`, formatted traceback or captured log record

#### Scenario: Call inside the caller's handler
- **WHEN** a call is made inside `except SyntheticCallerError as caller_error` and fails
- **THEN** the error has no `__cause__`, its `__context__` is `caller_error` and is not hidden, and a retry made inside `except SourceError as first` raises an error whose context is `first`

#### Scenario: Class a test double defines
- **WHEN** the transport raises an instance of `type("Falloé", (httpx.ReadError,), {})` before the status
- **THEN** the message ends with `(ReadError)`

### Requirement: SA-9 — Pacing from the observed rate-limit header

The system SHALL, before each request after the first, wait through an injected
sleeper until a minimum interval has passed since the previous attempt ended,
and SHALL wait a longer cool-down instead when the previous response had status
`429` or an `X-RateLimit-Remaining` value below a threshold. `X-RateLimit-Limit`,
`Retry-After` and any reset header SHALL NOT be used. A valid `Remaining` value
is one or more ASCII digits once surrounding spaces and horizontal tabs are
removed, compared exactly with the threshold whatever its length, and the lowest
of repeated values counts; any other value is ignored. Every attempt handed to
the HTTP client counts for pacing, however it ends, and the decision reads the
status and headers whenever they arrived. The defaults are 5 s, 20 and 60 s,
all configurable. They are project decisions, not observations.

**Source:** sercop-source-adapter · intent.md § AC9 (Revisions 2 and 3)

#### Scenario: Interval and cool-down
- **WHEN** two `200`s with `Remaining: 47` are made 2 s apart, then `Remaining: 19` and a call 2 s later
- **THEN** the second call sleeps 3 s, and the call after `Remaining: 19` sleeps 58 s

#### Scenario: Attempt ended in an exception
- **WHEN** a `429` or a `200` with `Remaining: 5` is interrupted by `KeyboardInterrupt` while its body is read, and a call follows 2 s later
- **THEN** the second call sleeps 58 s

### Requirement: SA-10 — Explicit timeouts and input checked before any request or wait

The system SHALL set explicit timeouts on every request: connect, write and pool
10 s and read 30 s by default (project decisions, configurable), with each
timeout, `min_interval` and `cooldown` an `int` or `float` (not a `bool`), finite
and at most 86,400 s. It SHALL raise `ValueError` before any request and before
any wait, with no change to pacing, for a `year` or `page` that is not an `int`
(a `bool` is rejected) or is below 1 or has more digits than the interpreter
writes as text, a `buyer` or `ocid` that is empty, is not a `str`, cannot be
encoded as UTF-8, or makes the request URL longer than the HTTP library accepts.
It SHALL check the base URL completely at construction: no user information,
a non-empty host, a port of 1 to 65535, a host the library and name resolution
accept (labels of at most 63 characters, no empty label, at most 253
characters, a decodable IDNA form, no IPv6 zone identifier), and room for the
shortest request URL. It SHALL also reject option values of the wrong type
(`base_url` not a `str`, `transport` not `None` or an `httpx.BaseTransport`,
`now`, `monotonic` or `sleep` not callable). Every rejection SHALL be exactly
`ValueError` whose message starts with the name of the option or parameter and
holds no URL text. A call after `close()` SHALL raise `RuntimeError` before any
request or wait.

**Source:** sercop-source-adapter · intent.md § AC10 (Revisions 2 to 5)

#### Scenario: Timeouts and encoding header
- **WHEN** a search is sent with the defaults
- **THEN** the handler sees timeouts `connect` 10, `read` 30, `write` 10, `pool` 10 and `Accept-Encoding: identity`

#### Scenario: Invalid input
- **WHEN** page `0`, year `True`, an empty buyer, a lone-surrogate `ocid`, or a buyer of 70,000 `a` is given
- **THEN** `ValueError` is raised whose message starts with the parameter's name, the handler and the sleeper are not called, and the next valid call waits as if the rejected call had not happened

#### Scenario: Rejected base URL
- **WHEN** `base_url` is `https://synthetic-user:synthetic-secret@source.invalid/PLATAFORMA`, `https://source.invalid:99999/PLATAFORMA` or `https://[fe80::1%25é]/PLATAFORMA`
- **THEN** construction raises exactly `ValueError`, its reason starts with `base_url`, and none of the user name, secret or host text appears in `str()`, `repr()` or `args`

### Requirement: SA-11 — The set of outcomes is closed

The system SHALL end every call in a result, one of the three `SourceError`
subclasses (SA-5 to SA-7), `ValueError` (SA-10) or `RuntimeError` (call after
`close()`). Every other exception SHALL propagate unchanged, never wrapped, and
the attempt SHALL still count for pacing: `KeyboardInterrupt`, `SystemExit`,
`MemoryError`, and any exception from an injected transport, `now`, `monotonic`
or `sleep` that is not an `httpx.HTTPError`. When the read of a body ends in
such an exception, it SHALL decide the outcome even if the stream's close then
raises an `httpx.HTTPError`, which is dropped. No limit on body size is set, so
a body larger than the memory available ends in an unchanged `MemoryError`.
Caller code (the injected transport and what it returns or raises, the injected
callables, and the methods of a subclass of a documented type) is not part of
the adapter, and what it returns is used as it is.

**Source:** sercop-source-adapter · intent.md § AC15 (Revisions 2 to 5); execution-plan.md § Binding constraints, § Exit check

#### Scenario: Defect of a transport
- **WHEN** the transport raises a synthetic non-`httpx` exception, `SystemExit` or `MemoryError` before the status, or from the body stream after one chunk
- **THEN** that same object propagates, it is not a source error, and a call 2 s later still waits for pacing

#### Scenario: Interrupt then a failing close
- **WHEN** a `200` with `Remaining: 5` streams a complete valid body, then raises `KeyboardInterrupt`, and its `close()` raises `httpx.CloseError`
- **THEN** the `KeyboardInterrupt` propagates unchanged, and a call 2 s later waits 58 s

### Requirement: SA-12 — Layers hold, and tests never reach the network

The system SHALL keep the raw response and the source errors in `domain`
(standard library only, strict `mypy`), the port and the two result types in
`application` (standard library and `domain` only), and the `httpx` adapter in
`infrastructure`, the only layer that imports `httpx` (ADR 0006). Every adapter
test SHALL inject an `httpx.MockTransport`, and a guard active in those tests
SHALL fail any test that opens a socket or resolves a host name.

**Source:** sercop-source-adapter · intent.md § AC11, AC12

#### Scenario: Layer checks
- **WHEN** `uv run pytest tests/unit -q -k "layer or satisfies_port"` is run
- **THEN** it passes, including the check that no module outside `infrastructure` imports `httpx`

#### Scenario: Network guard
- **WHEN** the adapter is built with the default transport and called for `https://source.invalid/...`
- **THEN** the guard records at least one blocked attempt, and no other adapter test records any

### Requirement: SA-13 — One caller at a time

The system SHALL be used by one thread at a time per instance, and an instance
SHALL NOT be called from inside its own call (from its transport, `now`,
`monotonic` or `sleep`). The `SercopSource` docstring states the rule with the
words "one thread at a time". Nothing enforces it, and every other requirement
is stated for that use.

**Source:** sercop-source-adapter · intent.md § AC15 Revision 5 "One caller at a time"; execution-plan.md § Consumers (F4)

#### Scenario: Re-entered call
- **WHEN** a transport calls `fetch_record` on the same instance from inside its own request
- **THEN** no error is raised, and the outer call's response holds the inner body (documented behavior, not a guarantee)

## Invariants

1. One call is one request, and the adapter never retries. Retries, backoff
   beyond the cool-down and attempt caps belong to F4.
2. Every valid response received (status 100 to 599), whatever its status and
   whether or not it is complete, reaches the caller unchanged, in a result or in
   an error, so it can be stored without changing `raw-evidence` (ADR 0002 and
   ADR 0005). The one case that is not kept is a status outside 100 to 599.
3. No body bytes or header values appear in a message, `repr` or log record,
   and nothing raised during a call is chained (SA-8).
4. `httpx` is imported only in `infrastructure`, and no `httpx` type or
   exception crosses into `domain` or `application` (ADR 0006).
5. Every statement about SERCOP behavior cites `docs/sources/sercop-observations.md`
   or is a project decision. The meaning of `local=1`, the rate-limit window and
   key, the body of a `429`, any `5xx` body, the answer for an unknown `ocid` and
   filtering by RUC or `buyerId` are not assumed, and every requirement that
   touches one holds whatever the source does.
6. Not a guarantee: (a) the pacing defaults, the timeouts and the 86,400 s
   bound are project decisions, not observations; (b) there is no overall
   deadline for a call, because `read` is a per-read timeout; (c) there is no
   limit on body size; (d) rate-limit state is not shared across processes or
   runs; (e) concurrency, async clients, HTTP/2 and authentication are out of
   scope (ADR 0006, ADR 0003).
7. Tests and fixtures hold no secrets, cookies, real raw responses or complete
   datasets; tests use `.invalid` hosts and no test file names the real SERCOP
   host (`AGENTS.md`).

## Open reservations

| ID | Reservation | Severity | Source |
|---|---|---|---|
| N-21 | Known limitation, accepted by the human on 2026-10-12 and deferred (not for PR #16): no test pins `_send`'s drop of a later `httpx.HTTPError` once the status and headers were captured. No code inside `httpx` 0.28.1 reaches that drop, but caller code can, for example a transport that returns a test-local `httpx.Response` subclass whose `has_redirect_location` raises `httpx.RemoteProtocolError` (a `history` setter that raises reaches it too). Expected, confirmed by the auditor's probe: a `200` returns the `SearchPage` or `RecordResponse` of SA-1, and a `404` raises `SourceStatusError` with the complete response. A change that re-raised there (mutant m17) passes all 961 tests. Reproducer for a later test: `httpx.MockTransport` returning that subclass, built with `stream=`, under the network guard | LOW | sercop-source-adapter · audit.md § Round 4 addendum, second addendum (N-21, N-22); execution-plan.md § Risks |
| R-6 | `httpx` does not map `ResponseStream.close()`, so a rare `OSError` from `socket.close()` propagates unchanged (accepted risk since Revision 3). It is not raised by the adapter, pacing still counts the attempt, and its `__context__` can hold protocol text, so F4 must not log the chain of an exception that is not a `SourceError` | LOW | sercop-source-adapter · audit.md § Reservations (round 4); execution-plan.md § Risks |
| R-7 | With the real transport, `httpcore`'s `DEBUG` trace writes response header values (accepted risk since Revision 1). The adapter configures no logging, SA-8's log requirement assumes that logger is above `DEBUG` (its default), and F4 must keep it there. Handled by F4: the command keeps the `httpcore` logger above `DEBUG` for every run (audit round 8 PASS); carried as an accepted risk and restated by the human on 2026-10-28 | LOW (impact Med) | sercop-source-adapter · audit.md § Reservations (round 4); intent.md § AC8 Revision 4 |
| R-11 | One instance shared between threads, or called from inside its own call, mixes the evidence of two calls with no error. Resolved as a documented rule with no mechanism (SA-13), accepted by the human with Revision 5. Handled by F4: one `SercopSource` serves an invocation, from one thread (audit round 8 PASS); restated by the human on 2026-10-28 | LOW (impact High) | sercop-source-adapter · audit.md § Round 4, rechecked; execution-plan.md § Risks |
| U1 | Behavior against the real SERCOP portal is unverified: tests use fixtures and simulated transports only. The adapter's request headers (`User-Agent`, `Accept`, `Accept-Encoding: identity`) differ from the observed `curl` requests, and the source may answer differently. Every response is preserved and typed, so a different answer fails loudly. First compared with the observations at the first live run (human, F4); that run has not been made, and the human restated this reservation on 2026-10-28 | MED | sercop-source-adapter · execution-plan.md § Risks; intent.md § Constraints |

F4 consumer rules (`execution-plan.md` § Consumers): catch `SourceError` only
and never retry `ValueError` or `RuntimeError`; store `result.response` or
`error.response` when it is not `None` before deciding on a retry; keep the
`httpcore` logger above `DEBUG`; use one instance per thread and never call it
from inside its own call; make a retry outside the `except` block (a retry made
inside `except SourceError as first` chains `first` and its response, so a loop
keeps every earlier response alive); do not parse the class name in a transport
error's message to decide on retries; and report a malformed proxy or
certificate setting in the environment as configuration. F5 must run the
completeness checks again and must not treat every `200` observation as
complete (ADR 0005).

## Contributing features

| Feature | Shipped | What it established |
|---|---|---|
| sercop-source-adapter (F2) | 2026-10-12 | The raw response and the source errors in `domain`, the `ProcurementSource` port with `SearchPage` and `RecordResponse` in `application`, and the `httpx` adapter `SercopSource` in `infrastructure`, with one request per call, the typed outcomes, pacing, timeouts, base URL and input checks, the closed set of outcomes and the no-leak output invariant (SA-1 to SA-13) |
| ingest-command (F4) | 2026-10-28 | No requirement changed. The `ingest` command is the first caller: it stores the response of each result or error before deciding what to do, makes no retry, keeps the `httpcore` logger above `DEBUG`, uses one instance per invocation and reports a malformed proxy or certificate setting as configuration; R-7 and R-11 are handled, U1 stays open until the first live run |

## Related ADRs

None registered here. The binding decision is the project-level ADR 0006
(HTTP client for source access, Accepted on 2026-10-10) in `docs/adr/`, which
carries no `Capability:` field. ADR 0002 (immutable raw storage) and ADR 0005
(raw evidence store layout) bind what the adapter hands to `raw-evidence`.
