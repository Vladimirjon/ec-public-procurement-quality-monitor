# Intent: SERCOP source adapter (F2)

Revision: 1
Approval: Approved revision 1 by Vladimirjon on 2026-10-10

## Outcome
The system can ask the SERCOP open-contracting portal for one page of the
confirmed buyer-name search (`search_ocds`) or for one record by `ocid`
(`api/record`) and get back the response exactly as received: method, URL as
sent, status, headers and body bytes, plus the capture time. Each call sends
exactly one HTTP request and ends in one of two ways. It returns a checked
result, or it raises a typed error that still carries whatever response was
received, so F4 can store every response, the failed ones included, through
the existing `RawEvidenceStore.store` (F1, ADR 0005) without changes. F2 delivers
the port, the result and error types and the `httpx` adapter, with pacing
driven by the observed rate-limit header. It is tested only with the fixtures
and a simulated transport, never the network, and nothing calls it yet (no CLI
command, no ingestion, no storage, no normalization).

## Acceptance criteria
Sources. Every statement about SERCOP below cites a section of
[`docs/sources/sercop-observations.md`](../../docs/sources/sercop-observations.md)
("Obs. §") or is marked **project decision**. "Series" is its section
"Observation series of 2026-10-10". Fixtures are the files in
`tests/fixtures/sercop/` (README there), approved at gate 1 on 2026-10-10. Bodies for
other statuses and for truncation are **synthetic**: the test builds them, and
they say nothing about the source's own format.

Notation. `<base>` is the base URL the adapter is given. In tests it is
`https://source.invalid/PLATAFORMA`. The default is the observed
`https://datosabiertos.compraspublicas.gob.ec/PLATAFORMA` (Obs. § Confirmed
search endpoint). `<EEQ>` is the complete buyer name
`EMPRESA ELÉCTRICA QUITO S.A. E.E.Q.`, and `<EEQ%>` is its observed encoding
`EMPRESA%20EL%C3%89CTRICA%20QUITO%20S.A.%20E.E.Q.` (same section). The exact
names of types, errors and attributes are pinned in `execution-plan.md`
§ Binding constraints.

- **AC1** A search call sends exactly one `GET` with the confirmed buyer-name query, reproduced as observed: parameters `local=1` (an opaque constant with no assigned meaning), `year`, `page` and `buyer` in that order, the buyer name percent-encoded in UTF-8 with spaces as `%20`, and no keyword parameter (Obs. § Confirmed search endpoint, § Minimum pending checks). A `200` whose body passes the AC7 checks returns a search result with `total`, `page`, `pages`, the number of entries in `data`, and the raw response.
  Example: year `2025`, page `1`, buyer `<EEQ>`, transport answering `200` with the bytes of `search_single_page.json` -> exactly one request, to `<base>/api/search_ocds?local=1&year=2025&page=1&buyer=<EEQ%>`; result `total` 3, `page` 1, `pages` 1, record count 3, not beyond the last page; its raw response has method `GET`, that URL exactly, status `200`, and content equal to the fixture bytes.
- **AC2** A record call sends exactly one `GET` to `<base>/api/record?ocid=<ocid>` (Obs. § Record endpoint and rate limiting). A `200` whose body passes the AC7 checks returns a record result with the `ocid` and the number of releases, and the raw response.
  Example: `ocid` `ocds-5wno2w-SYNTHETIC-A`, transport answering `200` with the bytes of `record_single_release.json` -> request URL `<base>/api/record?ocid=ocds-5wno2w-SYNTHETIC-A`; result `ocid` `ocds-5wno2w-SYNTHETIC-A`, release count 1; content equal to the fixture bytes, with every `\/` unchanged (Series § `api/record`).
- **AC3** The raw response is the response as received. Headers are ordered `(name, value)` pairs, with names in the case received and repeated names kept in order (Series § Other response behavior). `Set-Cookie` is passed on unchanged, and the store drops it (RE-6). The content is the exact message-body bytes after chunked transfer decoding and before any content decoding (Series § Response body: chunked, no `Content-Length`). The capture time comes from an injected clock and keeps its UTC offset. The raw response's fields map one to one onto the keyword arguments of `RawEvidenceStore.store` (RE-12) apart from `execution_id` and `sequence`, so storing it needs no change to F1. No request carries a `Cookie` header, even after a response that set one (**project decision**: the observation requests carried none).
  Example: a `200` delivered in three chunks with headers `Content-Type: application/json`, `Docker-Distribution-Api-Version: registry/2.0` (twice), `X-RateLimit-Limit: 60`, `X-RateLimit-Remaining: 47` and a synthetic `Set-Cookie: synthetic-session=s1`, at injected time `2026-10-10T06:58:00-05:00` -> the headers are exactly those six pairs in that order, the content is the concatenated chunks, and `captured_at` is that time. Passing the raw response to `LocalDiskRawEvidenceStore(tmp_path).store` with an execution id and sequence succeeds, `read_content` returns the same bytes, the observation keeps the other five pairs, and the next request sent carries no `Cookie` header.
- **AC4** A page beyond the last page, and a search with no results, are valid results, not errors. The result says whether the page is beyond the last page, so an empty `data` is never read as "no results" on its own (Series § Pagination).
  Example (observed): `search_page_out_of_range.json` for page 30 -> result `total` 284, `page` 30, `pages` 29, record count 0, beyond the last page, no error. Example (**inferred, not observed**): `search_no_results.json` for page 1 -> `total` 0, `pages` 0, record count 0, beyond the last page, no error.
- **AC5** (failure) Any status other than `200` raises a status error that carries the complete raw response (status, headers, exact body). The adapter does not read `Retry-After`, does not parse non-`200` bodies, and does not follow redirects. The requirement holds whatever a `429` or `5xx` contains, because neither was preserved (Obs. § Record endpoint and rate limiting; Series § Still unverified after this series).
  Example (all synthetic): `429` with body `b"<html>synthetic rate limit</html>"` and `Retry-After: 1`, `500` with an empty body, `503` with `b"synthetic unavailable"`, `404` for an `ocid` (the real answer for an unknown `ocid` is unobserved), `204`, and `302` with a `Location` header -> each raises the status error, whose response has that status and exactly that body. The `302` produces exactly one request.
- **AC6** (failure) A transport failure raises a transport error and never a result. If it happens before the status and headers arrive (connection failure, timeout), the error carries no response. If it happens after them (the body is cut off, or a read times out partway), the error carries a partial raw response with the status, the headers and the bytes received so far, because a truncated body is evidence (ADR 0005).
  Example: the transport raises a synthetic connect error or read timeout before answering -> transport error with no response. The transport sends status `200` and then the first 100 bytes of `search_single_page.json` before raising a synthetic protocol error -> transport error whose response has status `200` and content equal to those 100 bytes.
- **AC7** (failure) A complete `200` whose body is unusable raises an incomplete-response error that carries the complete raw response, never a partial result (ADR 0005 leaves this judgement to the adapter). Search body: it must be strict UTF-8 JSON whose top level is an object with `total`, `page` and `pages` as non-negative integers (`true` and `false` are rejected) and `data` as a list, and its `page` must equal the requested page (Series § Response body, § Pagination: "`page` echoed the requested number"). Record body: it must be strict UTF-8 JSON whose top level is an object with a non-empty `releases` list in which every release is an object whose `ocid` equals the requested one (Series § `api/record`). Nothing else is checked: not the 15 record keys, not page sizes, not other OCDS sections (F5).
  Example: the first half of `search_single_page.json` delivered as a complete body; bytes that are not UTF-8; a top-level list; `total` missing, `"3"` or `true`; `data` set to `null`; `page` 2 in answer to page 1; a gzip-compressed body with `Content-Encoding: gzip` (kept raw, so it is not JSON); and, for a record, `releases` missing, empty or not a list, a release without `ocid`, or a release whose `ocid` differs from the requested one -> each raises the incomplete-response error, and its response holds exactly the bytes sent.
- **AC8** (failure) Nothing leaks response content. Error messages, and `str()` and `repr()` of errors and of raw responses, contain no body bytes and no header values. No error's `__cause__` or `__context__` chain holds a `JSONDecodeError` or `UnicodeDecodeError` (they keep the body text, F1 reservation N3). The adapter writes no log records of its own, and no log record emitted during a call contains body or header values.
  Example: synthetic body marker `synthetic-body-marker` and header value `synthetic-header-marker`, in a success, a `429`, an invalid-JSON `200` and a cut-off body -> neither marker appears in any message, `str()`, `repr()` or captured log record, and no record comes from an `ec_procurement_quality` logger.
- **AC9** Pacing uses the observed `X-RateLimit-Remaining` header as its only source signal, as advice: the window and key are unknown (Series § Rate limiting). Before each request after the first, the adapter waits through an injected sleeper until a minimum interval has passed since the previous attempt ended. It waits a longer cool-down instead when the previous response had status `429` or a `Remaining` value below a threshold. `X-RateLimit-Limit`, `Retry-After` and any reset header are not used. Defaults (**project decision, not observed**, all configurable): minimum interval 5 s, threshold 20 (borrowed from the stop rule of the observation series, not a source fact), cool-down 60 s (the series only showed a refill within 29 minutes). Tests use an injected monotonic clock and sleeper, so they never sleep.
  Example (fake clock, defaults): two `200`s with `Remaining: 47`, the second call 2 s after the first ended -> one sleep of 3 s. `Remaining: 19`, then a call 2 s later -> one sleep of 58 s. `Remaining: 20` -> 3 s. A synthetic `429` with no rate-limit header and `Retry-After: 1` -> 58 s. A missing or non-numeric `Remaining` -> 3 s. Repeated `Remaining` values `30` and `5` -> 58 s (the lowest counts). A call 10 s after a `200` -> no sleep. The first call -> no sleep.
- **AC10** Request discipline. Every request sets explicit timeouts: connect, write and pool 10 s and read 30 s by default (**project decision, not observed**, configurable). The read default clears the 12.01 s observed for a whole request (Series table), while the `httpx` default is 5 s. Every request asks for an uncompressed body (`Accept-Encoding: identity`, **project decision**). Invalid input raises `ValueError` before any request and before any wait.
  Example: the handler sees timeouts `connect` 10, `read` 30, `write` 10, `pool` 10 and `Accept-Encoding: identity`. Page `0`, year `True`, an empty buyer, an empty `ocid`, or `min_interval=-1` at construction -> `ValueError`, the handler is never called, and the sleeper is never called.
- **AC11** No test reaches the network. Every adapter test injects an `httpx.MockTransport`. A guard active in those tests fails any test that opens a socket or resolves a host name, and one test shows that the guard catches an adapter built with the default transport.
  Example: `uv run pytest tests/unit -q` passes and the guard records no attempt in any adapter test. The guard test records at least one blocked attempt for a default-transport request to `https://source.invalid/...` and passes.
- **AC12** The layers keep their boundaries. The raw response and the source errors live in `domain` (standard library only, strict `mypy`). The port and the two result types live in `application` (standard library and `domain` only). Only `infrastructure` imports `httpx` (ADR 0006), and the adapter satisfies the port without the port knowing it.
  Example: `uv run pytest tests/unit -q -k "layer or satisfies_port"` passes, including a new check that no module outside `infrastructure` imports `httpx`; `uv run mypy .` exits 0 with a test that assigns the adapter to a variable typed as the port.
- **AC13** (compatibility) Everything that worked keeps working, and the only change to the dependencies is `httpx`.
  Example: the 137 existing tests still pass; `uv run ruff check .`, `uv run ruff format --check .` and `uv run mypy .` exit 0; `uv run node .sdd/doctor/run-doctor.mjs` reports `0 warned, 0 failed`; `uv run ec-procurement-quality --version` prints `ec-procurement-quality 0.1.0`; `uv sync --locked` succeeds; `git diff main -- pyproject.toml` adds only an `httpx` entry to `[project] dependencies`; the F1 modules, the fixture files and `interfaces/cli.py` are unchanged; `git diff --check` is clean; no test file names the real SERCOP host.
- **AC14** (documentation) The documentation says what exists.
  Example: `README.md` names the SERCOP adapter (a library, no command yet) and `httpx` as the first runtime dependency, and no longer lists the adapter as planned; `CHANGELOG.md` § Unreleased lists the adapter and the dependency; `docs/architecture.md` § Open questions records that the first flow uses `search_ocds` (buyer-name query) and `api/record`.

## Scope
**In**
- `domain`: the raw response value (one response as received) and the closed set of source errors, sharing one base, each carrying the response when one was received.
- `application`: the source port (a search page by year, buyer name and page; a record by `ocid`) and its two result types.
- `infrastructure`: the SERCOP adapter on a synchronous `httpx.Client`, with the injected transport, clock, monotonic clock and sleeper, the completeness checks, pacing and timeouts.
- The `httpx` runtime dependency, added with `uv add` by the first executor task (`pyproject.toml`, `uv.lock`). The human approved it.
- Unit tests under `tests/unit/` for AC1 to AC12, using the fixtures and bodies built in the tests, plus the network guard and a new layer check.
- Documentation updates for AC14.

**Out**
- Storing evidence, execution ids, sequence numbers, retries, backoff between attempts, attempt caps, resuming and the `ingest` command (F4). The adapter never retries: one call is one request.
- Parsing or normalizing records, checking the 15 search-record keys or OCDS sections, and money values (F5).
- Any CLI command or composition root (wiring a real adapter to a real store), and PostgreSQL (F3).
- Filtering by RUC or `buyerId`, a keyword parameter, and giving `local=1` any meaning (Obs. § Minimum pending checks; Series § Still unverified after this series).
- Reading `Retry-After`, reset headers or `X-RateLimit-Limit`; rate-limit state shared across processes or runs.
- Concurrency, async clients, HTTP/2, proxies set by the project, and authentication (ADR 0006, ADR 0003).
- Any request to the real portal from tests or from F2 work. Live checks belong to the human and to F4.
- Creating or editing the fixture files; they were approved by the human at gate 1.
- Context7 or any MCP server. The `httpx` API is checked against the installed package in `.venv`.

## Constraints
- Single source of truth for source behavior: `docs/sources/sercop-observations.md`. Every source statement in these specs cites one of its sections or is labelled a project decision. These are not assumed anywhere: the meaning of `local=1`; the rate-limit window and key; whether a `429` carries `Retry-After` and what its body is; any `5xx` body; the answer for an unknown `ocid`; whether `api/record` structure varies between records; filtering by RUC or `buyerId`. Every requirement that touches one of them (AC5, AC6, AC7, AC9) holds whatever the source does.
- ADR 0002 and ADR 0005 are binding. Every response received, whatever its status and whether or not it is complete, must be able to reach the raw store unchanged. F1's port and adapter do not change.
- ADR 0006 (`Accepted` by the human at gate 1 on 2026-10-10): `httpx` with a synchronous `httpx.Client`, imported only in `infrastructure`; transport injected; tests use `httpx.MockTransport` with no extra mocking package; explicit timeouts; retries, backoff and pacing decided here, not delegated to the library. These specs treat its decision as binding and do not change its status.
- Layer boundaries from `AGENTS.md` and `docs/architecture.md`; strict `mypy` in `domain` (ADR 0004).
- No new infrastructure, framework, service or CLI command. `httpx` is the only new dependency (approved by the human); its transitive packages come with it in `uv.lock`.
- Tests, fixtures and docs hold no secrets, cookies, real raw responses or complete datasets (`AGENTS.md`). URLs in tests use `.invalid`; cookie and error bodies are synthetic and labelled so.
- Responses may be sensitive: no body bytes or header values in messages, `repr` or logs (same discipline as F1, RE-7 and Invariant 5).
- Current-truth notes (`harny-sync` lookup):
  - `project-toolchain` PT-11 says the system keeps `[project] dependencies` empty, and its Invariant 4 says it stays empty "until a runtime dependency is explicitly approved". F2 adds `httpx` there, with the human's approval, so at archive PT-11 is modified and Invariant 4 is fulfilled, not broken. The `dev` group does not change.
  - PT-3 (layer import rules) is kept and extended by one check: only `infrastructure` may import `httpx`.
  - PT-6, PT-10 and PT-11 restate test counts, which grow.
  - `raw-evidence` RE-12 (the local-disk adapter adds no dependency) refers to that adapter and stays true.
  - The raw-evidence purpose line, "no HTTP access calls it yet", also stays true: F2 does not call the store outside tests.
  - `cli` is untouched.

## Open questions
- None. At gate 1 the human accepted the two project decisions flagged for review: the search check that the echoed `page` equals the requested page (AC7), and the pacing defaults (AC9).

## Revision history
- Revision 1 (2026-10-10): First draft, based on `docs/sources/sercop-observations.md` (including the observation series of 2026-10-10), the draft fixtures in `tests/fixtures/sercop/`, ADR 0006 (`Proposed`) and the human's decisions on scope, client and dependency.
