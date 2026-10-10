# ADR 0006: HTTP client for source access

- Status: Accepted
- Date: 2026-10-10

## Context

F2 (`sercop-source-adapter`) must call two SERCOP endpoints recorded in
[sercop-observations.md](../sources/sercop-observations.md): the search
(`search_ocds`) and the record (`api/record`). The project has no runtime
dependencies so far: `dependencies = []` in `pyproject.toml`, and
[ADR 0004](0004-python-toolchain.md) and [ADR 0005](0005-raw-evidence-store-layout.md)
added none. This is therefore the first one.

Three facts from the observations shape the choice. Requests took 4.0 to 5.3 s
on 2026-10-03 and 5.9 to 12.0 s on 2026-10-10 end to end. The source advertises
`X-RateLimit-Limit: 60` with an unknown window and key, and answered one
request with `429` whose headers and body were not kept. And tests must never
reach the network: the adapter is verified with approved fixtures, not with
live SERCOP calls.

## Decision

Use `httpx`, through its synchronous `httpx.Client`, as the HTTP client of the
SERCOP adapter.

- **Placement.** Only `infrastructure` imports it. No `httpx` type or exception
  crosses into `domain` or `application`: transport failures leave the adapter
  as the project's own typed errors.
- **Tests.** The adapter receives its transport from the outside. Tests use
  `httpx.MockTransport` with approved fixtures, so no test opens a socket and no
  extra mocking package is needed.
- **Timeouts.** Every request sets explicit connect, read, write and pool
  timeouts that are recorded in the F2 spec. They are a project decision, not
  the library default: `httpx` 0.28.1 defaults to 5 s, below the 12.0 s
  observed for a whole request.
- **Retries, backoff and pacing.** Not delegated to the library: its retry
  option would hide failed responses from the raw store. The adapter makes one
  attempt per call and never retries. The caller (F4) owns retries and backoff
  and stores every response received, including those that trigger a retry
  (ADR 0005). Pacing and its defaults are decided in the F2 spec.
- **Version.** Resolved and pinned by `uv.lock`. The dependency is added by the
  first task of F2, not by this ADR.

## Alternatives considered

The standard library `urllib` was rejected because it has no injectable
transport: tests would have to patch functions inside the module, and headers,
redirects and response handling become manual. What is lost is having no new
dependency. `requests` was rejected because it has no built-in test transport,
so mocking needs a second package (`responses` or `requests-mock`) or
monkeypatching. What is lost is familiarity. An asynchronous client (`aiohttp`
or the async API of `httpx`) was rejected because the system is a bounded batch
CLI against a source limited to 60 requests, so concurrency adds complexity
to idempotency and resumption without a benefit. What is lost is parallel
downloading.

## Consequences

The project gains its first third-party runtime dependency, plus the packages
it pulls in, all recorded in `uv.lock` and watched by Dependabot. Adapter tests
stay offline and fast, and the choice of client is isolated in one layer, so
replacing it later touches only the adapter.

This decision should be revisited if the source requires concurrency or
HTTP/2, if the client stops being maintained, or if a second source with
different transport needs appears.
