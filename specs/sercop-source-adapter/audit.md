# Audit: SERCOP source adapter (F2)

Current round: **round 2** (2026-10-10, intent Revision 3, commit `19ab9c3`). Its
full report is § Round 2, after the round 1 sections. Round 1 is kept below exactly as
written, as history; only its Tier Results table gained round 2 columns, because the
procedure keeps a single Tier Results table.

## Final verdict

REJECTED (round 2, current)

**Summary**: Revision 3 closes every round 1 item: F-1, F-2, F-3, F-4, R-1 and R-3 are
resolved on the exact inputs that reproduced them, all 569 tests pass locally and in
CI on `19ab9c3`, the 453 tests of `015a72b` lost no line, and 42 of the 43 rows of the
plan's § Family check hold against the installed packages. Two new defects with
concrete reproducers block approval. A non-ASCII IPv6 zone in the base URL makes
construction raise a raw `UnicodeEncodeError` instead of the fixed `base_url ...`
reason, and the host text sits in its `repr` and `args` (F-5). When the source sends
malformed HTTP framing, the `httpx` exception chained under the `SourceTransportError`
quotes the bytes `h11` rejected, which include body bytes or a whole header line,
value included (F-6, AC8). The plan explicitly allows that chaining because "it holds
no body", and that premise is false. F-6 needs a decision by the architect. F-5
needs § Validation to name the case before any code changes.

**Critical Issues** (must fix before merge):
- F-5 (MEDIUM, blocking: binding constraint "the `ValueError` message names
  `base_url` and a fixed reason", AC10 Revision 3 "no URL text in its message or
  chain"). `SercopSource(base_url="https://[fe80::1%25é]/PLATAFORMA")` raises
  `UnicodeEncodeError('ascii', 'fe80::1%25é', ...)` from
  `url.raw_host`, which `_base_url_problem` reads outside any `try`. The current tests
  would not catch it. Route: the architect names the case and the message assertion in
  § Validation and corrects § Family check row 2.9. Then red, then green. No code
  workaround is proposed here.
- F-6 (MEDIUM, blocking, spec gap: AC8 "Nothing leaks response content ... str() and
  repr() of errors ... contain no body bytes and no header values"; plan § No content
  "An `httpx` exception may be chained ... It holds no body"). Two inputs that go
  through the real `httpx`, `httpcore` and `h11` stack offline: a chunked `200` whose first chunk line is
  `{"total":3,...,"note":"synthetic-body-marker..."}` raises `SourceTransportError`
  whose `__cause__` message holds about 30 KB of that body, and a header line
  `Authorization-Synthetic: synthetic-header-marker\x00` puts the whole header line,
  value included, in the cause of a `SourceTransportError` with no response. The architect decides
  between withdrawing the chaining permission and narrowing AC8 (§ Round 2 Findings).

**Warnings** (should fix, not blocking):
- F-7 (LOW): stale or inaccurate text in the specs: intent § Constraints still says
  the Revision 2 reading "needs the human's approval"; plan § Risks says "the human
  decides at approval" twice; plan § Family check row 1.10 gives the header block as
  16 KiB, where `httpcore` sets 100 KiB; `tasks.md` § Status, O8b, § Working state and
  § Checkpoint still describe the Revision 3 work as uncommitted at `83c0b11`, with the
  PR checks unavailable.

**Recommendations** (nice to have):
- R-2: lines 171 and 172 (the `urlsplit` `ValueError` branch) still have no test. A
  third mutant, m2c, which chains that branch's exception, passes the whole no-chain
  test. Add `https://[::1/PLATAFORMA` to `REJECTED_BASE_URLS`.
- R-8: a non-`str` `base_url` such as `123` raises `AttributeError` at construction,
  not `ValueError`. No rule covers the type of `base_url`, unlike the numeric options.
- R-9 and R-10: `MemoryError` and the `except httpx.HTTPError` drop in `_send` behave as
  specified (probe), but no test covers them.

### Round 1 final verdict (superseded by round 2)

REJECTED

**Summary**: The adapter, the domain types, the port and the tests match intent
Revision 2 almost everywhere. All 453 tests pass, every § Validation row has tests at
least as strong as the plan asks, the outcome set is closed as the plan argues, and no
path chains the library's `InvalidURL`. Two inputs, each with a concrete reproducer,
break a binding rule. In pacing, a zero-padded `X-RateLimit-Remaining` longer than
4,300 digits is ignored when the spec says it counts (F-1, AC9). At construction, the
base URL check lets through URLs on which every later call fails (F-2, AC10). Both
inputs are pathological and both fixes are small, but an unmet binding rule blocks
approval at any severity. Each one needs a decision by the architect before any code
changes.

**Critical Issues** (must fix before merge):
- F-1 (MEDIUM, blocking): AC9 and the plan's pacing rule are not met for a valid
  `X-RateLimit-Remaining` value of more than 4,300 ASCII digits with a low value, such as
  `"0" * 4300 + "5"`. The next call waits 3 s where the spec requires 58 s. The architect
  decides: keep the rule and plan a test case plus a code change, or revise AC9 and the
  plan to say that such a value is ignored.
- F-2 (MEDIUM, blocking, spec gap): AC10 says the base URL is "checked completely at
  construction, so that no call can fail on it later". With the real transport, a host
  label of 64 or more characters, or an empty label (`https://a..invalid/PLATAFORMA`),
  passes construction, and every call then raises an untyped `UnicodeEncodeError` (a
  `ValueError` subclass) from name resolution. A base URL close to 65,536 characters also
  passes construction, and every call then raises `ValueError`. The architect decides
  whether to extend the construction rules or narrow the guarantee (and the plan's
  § Closed-set justification).

**Warnings** (should fix, not blocking):
- F-3 (LOW): `README.md` says the adapter carries "whatever response arrived, so that
  every response can be stored as evidence", and `CHANGELOG.md` says a typed error
  "carries the response that arrived". Both contradict AC6 Revision 2: a status outside
  100 to 599 is not kept. This is a doc fix by the executor, with no spec change.
- F-4 (LOW): `execution-plan.md` § Guidance consulted still says intent Revision 2 is
  "pending human approval" and that `docs/sources/sercop-observations.md` is "not yet
  committed". Both are stale. This is housekeeping for the architect.

**Recommendations** (nice to have):
- R-1: add a test that anchors the plan's rule that the library's `InvalidURL` is never
  chained (described under § Reservations). The code meets the rule today, but two
  mutants that break it pass all 453 tests.
- R-3: add a `SystemExit` case next to the `KeyboardInterrupt` cases.
- Commit and push the doc edits, then confirm that the PR #16 `Tests` and `feedback`
  checks are green on the audited state.

## Scope of this round

Round 1, 2026-10-10. Auditor: `sdd-auditor` (harny-audit). Reviewed state: branch
`feat/sercop-source-adapter` at `015a72b` (local HEAD), base `main` `fff0f2d`, plus the
uncommitted working tree: `README.md`, `CHANGELOG.md`, `docs/architecture.md` and
`specs/sercop-source-adapter/tasks.md`. No other file differs from HEAD
(`git status --short`).

Read in full:
- specs and decisions: `intent.md` Revision 2 (approved), `execution-plan.md`
  Revision 2, `tasks.md`, ADR 0006 and `docs/sources/sercop-observations.md`;
- code: `domain/source_response.py`, `application/procurement_source.py` and
  `infrastructure/sercop_source.py`;
- tests: `tests/unit/test_source_response.py`, `tests/unit/test_sercop_source.py` and
  the `tests/unit/test_layers.py` diff;
- fixtures: `tests/fixtures/sercop/`;
- the three doc diffs;
- the relevant parts of the installed `httpx` 0.28.1 and `httpcore` 1.0.9 under
  `.venv/Lib/site-packages/`. The format follows `specs/archived/raw-evidence-store/audit.md`.

The audit made no network access and sent no request to SERCOP. Probes ran in the
session scratchpad, outside the repository. They used `httpx.MockTransport`, `.invalid`
or numeric hosts, and a socket guard. One probe stood in for `getaddrinfo` (see F-2).

Evidence labels: `rerun` means the auditor ran it in this round. `reused` means it comes
from a recorded result that is still current. `unavailable` means it could not be
produced.

## AC results

| AC | Status | Evidence |
|---|---|---|
| AC1 | PASS | URL built as a literal string with `quote(buyer, safe="")`, in the order `local=1`, `year`, `page`, `buyer` (`_search_url`). `-k "search_success or query"` -> `11 passed` (rerun). Asserts: `str(request.url)` equals the observed `%20` form, the parameter keys are exactly `local, year, page, buyer`, one `GET`, and the result is 3/1/1/3 with `is_beyond_last_page` false and content equal to the fixture bytes. `git grep "datosabiertos.compraspublicas.gob.ec/PLATAFORMA" -- src` -> exactly 1 match, `sercop_source.py:43` (rerun). |
| AC2 | PASS | `_record_url`. `-k record_success` -> `4 passed` (rerun). Asserts the URL, `ocid`, release count 1, exact bytes and `b"\\/"` kept. |
| AC3 | PASS | The hook keeps `response.headers.raw` decoded as Latin-1, in order, with case and repeats kept, and reads the body with `iter_raw`. `now()` is called once, in `_attempt_from_capture`. `cookies.clear()` runs before each `build_request`. `-k "raw_response or store_shape or cookie"` -> `18 passed` (rerun). The six AC3 pairs come back exactly, the three chunks are joined, `captured_at` keeps `-05:00`, and `wall.calls == 1`. `store_shape` goes through `LocalDiskRawEvidenceStore` for a success, a `429` and a cut-off body, with 3 sequences each, and checks that `Set-Cookie` is dropped. `cookie` covers 3 cases with no `Cookie` header. See note N1. |
| AC4 | PASS | `-k "out_of_range or no_results"` -> `4 passed` (rerun). Page 30 gives 284/30/29/0 and beyond the last page. The no-results case is labelled INFERRED and gives 0/0/0, beyond the last page. |
| AC5 | PASS | Rule 4 of `_outcome`. The capture in the response hook runs before the redirect step (see § Closed-set justification), and errors from that step are dropped in `_send` when a status was captured. `-k status_error` -> `26 passed` (rerun): 13 cases for each of the 2 operations, including the four Revision 2 malformed `Location` cases. Each asserts the status, the exact body, `headers == headers` (so `Location` is unchanged), the URL, `captured_at` and exactly one request. Probe (rerun): two more `Location` values, `//h:abc/` and `http://[zz]/`, also end in `SourceStatusError` with `__cause__` and `__context__` `None`. |
| AC6 | PASS | Rules 1 to 3 of `_outcome`. `-k transport` -> `27 passed` (rerun). Covered: connect error, connect timeout, read timeout and protocol error before the status (no response); a cut-off after 100 bytes (status 200, exact 100 bytes, headers, injected time) for both operations and both error types; a cut-off before any byte; a cut-off `503`; statuses `99`, `600` and `999` for both operations (no response, the message names the operation and the status, no marker anywhere in the chain, one request). Probe (rerun): status `600` with a cut-off body also gives `SourceTransportError` with no response and no chained cause. |
| AC7 | PASS | `_decode_json_object` (strict `utf-8`, then `json.loads`; it returns a verdict and raises nothing), `_search_page_if_complete` and `_record_if_complete`. `-k incomplete` -> `43 passed` (rerun): 25 search bodies and 18 record bodies, which cover every body the plan lists and more. Each asserts `IncompleteResponseError`, status 200, the exact bytes and headers. |
| AC8 | PASS | Messages use only the operation name and integer statuses. `RawResponse.__repr__` shows sizes only. The module has no `logging` import and no `print` (grep, rerun). `-k no_leak`, run over both files -> `17 passed` (rerun): `caplog` at `DEBUG`, `capsys` empty, the chain walked for `JSONDecodeError` and `UnicodeDecodeError`, and the markers absent from every message, `str`, `repr`, argument and record. |
| AC9 | **PARTIAL** | `_attempt`, `_wait_if_due` and `_asks_for_cooldown`. `-k pacing` -> `39 passed` (rerun): every case in the AC9 row, the two Revision 2 status-`600` cases and the four unmapped-exception cases. Probe (rerun): `SystemExit` before the status gives `[3.0]`, and `SystemExit` while reading a `429` body gives `[58.0]`. **F-1**: `X-RateLimit-Remaining: "0" * 4300 + "5"` (or longer) gives `[3.0]`, where the rule gives `[58.0]`. |
| AC10 | **PARTIAL** | Timeouts are set through `httpx.Timeout(connect, read, write=connect, pool=connect)` and `Accept-Encoding: identity` is a client header. A call runs in this order: closed check, argument checks, `build_request`, wait, send. `-k "timeout or accept_encoding or invalid"`, run over both files -> `112 passed` (rerun). These include the 13 Revision 2 base URLs, the no-echo checks, the three port boundaries, the 70,000-character input and the call after `close()`. **F-2**: some base URLs pass every construction rule, yet a later call fails on them. |
| AC11 | PASS | The autouse guard patches `connect`, `connect_ex`, `create_connection` and `getaddrinfo` and fails the test at teardown. `-k no_network` -> `2 passed` (rerun). `git grep -n -i --untracked -e datosabiertos -e compraspublicas -- tests` -> exit 1. `git grep -c "source.invalid" -- tests/unit/test_sercop_source.py` -> 28 (rerun). See note N2. |
| AC12 | PASS | `tests/unit -k "layer or satisfies_port"` -> `9 passed` (rerun). The new `test_layer_only_infrastructure_imports_httpx` cannot pass vacuously: it asserts that the adapter exists and imports `httpx`. `git grep` shows imports of `httpx` only in `infrastructure/sercop_source.py:27` and in the test file (rerun). `uv run mypy .` -> `Success: no issues found in 20 source files` (rerun), with the strict `domain.*` overrides in `pyproject.toml`. `procurement_source.py` imports only `dataclasses`, `typing` and `domain`. |
| AC13 | PASS | Each of the 13 points is under § AC13 below, with its command and result. The Revision 1 test content is a reservation (R-4). |
| AC14 | PASS | The three items are present. Claims checked under § AC14 below. One wording overclaim: F-3 (LOW). |
| AC15 | PASS | No `except Exception` or `except BaseException` (grep exit 1, rerun). `-k "transport_defect or invalid_status or status_error or too_long or after_close or userinfo"` -> `50 passed` (rerun). The same `SyntheticTransportDefect` object propagates, for both operations and from both places. `KeyboardInterrupt` is tested. `SystemExit` was checked by probe only (R-3). The closed-set justification was checked line by line (§ below), with one gap recorded under F-2. |

## Binding-constraint compliance

| Constraint | Status | Evidence |
|---|---|---|
| Public names and signatures | PASS | `RawResponse` has exactly the six attributes. It is frozen, equal by value, and has `repr=False` plus a custom `__repr__`. The four errors have the pinned constructors, and `SourceStatusError` and `IncompleteResponseError` require `response`. `SearchPage` has `is_beyond_last_page` as `page > pages`. `RecordResponse` and the `ProcurementSource` protocol match exactly. `DEFAULT_BASE_URL` matches. `SercopSource` takes keyword arguments only, with the pinned names and defaults, and offers `close()` and a context manager. |
| `RawResponse` validation (100 to 599, `bool` rejected, tuple headers, aware time, `bytes` content) | PASS | `source_response.py:48-68`; `test_source_response.py -k invalid` (rerun inside the AC10 run). F1 is unchanged (§ AC13). |
| Construction rules (scheme, trailing `/`, query, fragment, timeouts, intervals, threshold) | PASS | `_base_url_problem` and `__init__`; 16 Revision 1 cases. |
| Authority of `base_url` (Revision 2) | PASS for every listed rule; see F-2 for the guarantee | User information is rejected for any `@` in the netloc. The host must be non-empty. The port is checked after the last `]` and must be 1 to 5 ASCII digits with a value of 1 to 65535. `httpx.URL` is tried last. Its `InvalidURL` and `ValueError` (and `urlsplit`'s `ValueError`) are caught and replaced by a fixed reason, and the error is raised in `_require_base_url`, outside any `except`. Probe (rerun) on 11 more URLs (`[zz]`, `[::1`, `[::1]:abc`, a fullwidth `@`, a zero-width joiner, a tab, `٣`, and others): every result has `__cause__` and `__context__` `None`, and no message holds `synthetic-user`. One ordering difference: `urlsplit` runs before the `@` check, and the plan asks for the user-information check to run "before any parsing whose message could repeat the URL". `urlsplit`'s message can repeat the netloc (in the NFKC case), but it is caught and dropped, so the plan's intent holds. Treated as a compliant alternative, since the `@` check needs the netloc that `urlsplit` produces. |
| Request format and order of a call | PASS | See AC1, AC2 and AC10. `_build_request` raises `ValueError` outside the `except` block. The `-k too_long` tests show no request, no wait and unchanged pacing (`[3.0]` afterwards). |
| `Location` never decides the outcome | PASS | See AC5 and § Closed-set justification. |
| Timeouts | PASS | AC10 tests read `request.extensions["timeout"]`. |
| Response capture | PASS | `iter_raw` with `close()` in `finally`. Headers decoded as Latin-1. `now()` is called once, and only for a status in 100 to 599. |
| Outcome mapping, six rules in order | PASS | `_outcome` lines 403-433 follow the plan's order exactly: (1) `status is None` gives a transport error with no response; (2) `response is None` with a status gives the invalid-status transport error, with no cause; (3) a failure gives a transport error with the partial response; (4) a status other than 200 gives `SourceStatusError`; (5) a failed check gives `IncompleteResponseError`; (6) otherwise the result. Rule 3 comes before rule 4: a cut-off `503` is a transport error (tested). |
| `InvalidURL` is never chained or quoted (plan § Binding constraints, authority, and § Outcome mapping) | PASS (code); no test (R-1) | Point 2 of the caller's brief is answered in § InvalidURL rule below. |
| Completeness checks | PASS | AC7. Nothing beyond the listed rules is checked (tested by `checks_nothing_beyond_the_ac7_rules`). |
| Pacing | **FAIL for one input class (F-1)**; otherwise PASS | The `finally` in `_attempt` (lines 277-282) runs on every exit after the request is handed to `send`. Before that point (closed, invalid input, URL too long, an exception from `sleep`) the state is unchanged (tested, and the `sleep` case checked by probe, rerun). The cool-down flag reads the captured status and headers, whatever the status. |
| Closed-set justification | PASS line by line, with one gap (F-2) | § below. |
| No content in errors, representations or logs | PASS | AC8. The only `from` chains are `from attempt.failure` (an `httpx.HTTPError`, which the plan allows). The `JSONDecodeError` and `UnicodeDecodeError` names appear only in a docstring. |
| Layer imports | PASS | AC12. |
| Dependency | PASS | `git diff main -- pyproject.toml` changes only `dependencies = [ "httpx>=0.28.1", ]`. `uv.lock`: 72 lines added and 0 removed, namely `anyio` 4.15.1, `certifi` 2026.7.22, `h11` 0.16.0, `httpcore` 1.0.9, `httpx` 0.28.1 and `idna` 3.20 (rerun). The dev group is unchanged. |
| F1 is consumed, not changed; package root | PASS | § AC13 points 9 and 10. |
| Tests stay offline and synthetic | PASS | AC11. Synthetic credentials, bodies and the defect are labelled as such. Hosts are `.invalid` or numeric. No `data/raw` path is used, only `tmp_path`. No secrets (grep, rerun). Fixtures are read-only and unchanged since `74b785d`. |

Consumers and migration: `test_cli.py`, `test_content_hash.py`, `test_raw_evidence.py`
and `test_local_disk_raw_evidence_store.py` are byte-identical to `main`.
`test_layers.py` gains 74 lines and loses none (`git diff main --numstat -- tests`
shows 0 deletions in every file). PASS.

## The `InvalidURL` rule (point 2 of the brief)

Every place in `sercop_source.py` where `httpx.InvalidURL` can be raised or caught:

| Place | What happens | Chained? | Text reaches a message? |
|---|---|---|---|
| `_base_url_problem` lines 109-112, `httpx.URL(base_url)` | caught; the function **returns** a fixed string from inside the `except`, so the exception is no longer being handled when `_require_base_url` (line 119) raises | no (`__cause__` and `__context__` `None`, shown by probe for `999.1.1.1`, newline, tab and zero-width joiner) | no |
| `_base_url_problem` lines 88-91, `urlsplit` (`ValueError`, not `InvalidURL`, but the same risk) | same pattern | no | no |
| `_build_request` lines 261-268, `build_request` -> `_merge_url` -> `URL(url)` | `except httpx.InvalidURL: pass`; the `ValueError` is raised after the `try` statement | no (probe: `too-long` and the long-base-URL case have `__cause__` and `__context__` `None`) | no (fixed text naming the operation) |
| `_send` lines 323-332, `Client.send` | with a captured status, the exception is dropped and not stored; `_outcome` raises later, outside any handler | no (probe: the six malformed `Location` values end in `SourceStatusError` with an empty chain) | no |
| `_send` line 332, with no captured status | re-raised as the same object, not wrapped | no new link | it is the library's own exception propagating (unreachable with the real transport: the URL is already parsed and `HTTPTransport.handle_request` raises only mapped `HTTPError`s or non-`httpx` exceptions; reachable only when an injected transport raises `InvalidURL`, probe rerun) |

The redirect step's `RemoteProtocolError("Invalid URL in location header: {exc}.")`
(`_client.py:523-528`) is an `httpx.HTTPError` that can quote the `Location` value. The
same drop applies to it: it is stored as `capture.failure` only when no status was
captured, which cannot happen for an error raised in the redirect step.

Conclusion: **the code meets the rule, but no test anchors it.** The auditor's mutants
were run against copies in the scratchpad, confirmed as the imported module:
- **m1**: `_build_request` raises `... from exc`. Result: `453 passed`.
- **m2**: `_base_url_problem` raises `ValueError(...) from exc` inside its `except`.
  Result: `453 passed`.

The existing no-echo test looks for the whole base URL and the credential strings. The
library's messages repeat only a fragment, such as the host or the offending character,
so neither mutant is caught. This confirms the gap recorded in `tasks.md` O2b. It is
reservation R-1, not a finding.

## Closed-set justification, checked against the installed package

| Plan line | Installed source (`.venv/Lib/site-packages/`) | Result |
|---|---|---|
| Calls that can raise: `build_request`, `send(stream=True)`, `iter_raw`, `close` | `sercop_source.py` calls only these, plus `cookies.clear()` and `is_closed` | holds |
| Every class in `_exceptions.py` is covered | hierarchy at `httpx/_exceptions.py:1-32`: the `HTTPError` tree, plus `InvalidURL(Exception)` (271), `CookieConflict(Exception)` (280) and `StreamError(RuntimeError)` with its 4 subclasses (297-363) | holds |
| `DecodingError` only from content decoding | raised only in `_decoders.py`; `iter_raw` (`_models.py:935-959`) uses no decoder | holds |
| `TooManyRedirects` cannot happen | `_client.py:971-974` needs `len(history) > max_redirects`; history is `[]` | holds |
| `HTTPStatusError` only from `raise_for_status` | only `_models.py:829` | holds |
| `InvalidURL` (a): base URL | checked at construction | holds for every rule listed; **not** "no call can fail on it later" (F-2) |
| `InvalidURL` (b): request URL, only `MAX_URL_LENGTH` is left | `_urlparse.py:218-219` (too long), 223-229 (control characters), 348-392 (`encode_host`), 395-419 (`normalize_port`), 422-444 (`validate_path`); the appended characters are ASCII digits, `?&=` and the output of `quote(safe="")` | holds for the input; a base URL near 65,536 characters also reaches this path (F-2(b)); the result is still `ValueError` before the wait |
| `InvalidURL` (c): redirect step, ignored after the capture | `_client.py:981-982` runs the response hooks **before** `has_redirect_location` (985) and `_build_redirect_request` (988); `_redirect_url` 523-528 (`URL(location)`, wrapped as `RemoteProtocolError`), 533 (`copy_with`, raw `InvalidURL`, e.g. `https:abc`), 538 (`join`, raw `InvalidURL`, e.g. "URL too long"); `except BaseException: response.close(); raise` at 997-999 | holds; the hook has already read and closed the body |
| `CookieConflict` only from `Cookies.get` | only `_models.py:1161`; `extract_cookies` (`_client.py:1022`) uses `http.cookiejar`, which catches its own parse errors | holds |
| `StreamConsumed` and `StreamClosed` need an already read or closed stream | `_models.py:939-942`; `HTTPTransport.handle_request` returns a fresh `ResponseStream` (`_transports/default.py:254-259`); the adapter reads once, then closes | holds |
| `ResponseNotRead` and `RequestNotRead` | `_models.py:638` (`Response.content`) and 465 (`Request.content`); neither is used | holds |
| `RuntimeError`: closed client, async request, async stream, `AssertionError` | `_client.py:900-901` (pre-empted by `_require_open`), 1008-1011, 1016; `_models.py:943-944`, 966-967 | holds |
| Below `httpx`: `map_httpcore_exceptions`; `httpcore` sync backend maps `OSError` and `socket.timeout`; the only unmapped path is `OverflowError`, closed by the port rule | `_transports/default.py:95-118` (an unmapped exception is re-raised at 114-115); `handle_request` wrapped at 249-250; `ResponseStream.__iter__` wrapped at 125-128; **`ResponseStream.close` (130-132) is not wrapped** (the plan's risk table already covers `close()` at the socket layer); `httpcore/_backends/sync.py:202-213` maps only `socket.timeout` and `OSError` on connect | **incomplete**: `socket.create_connection` -> `getaddrinfo` encodes a `str` host with the `idna` codec, which raises `UnicodeEncodeError` (a `ValueError`, not an `OSError`) for a label of 64 or more characters or an empty label. That error is unmapped and escapes `send` unchanged. The base URL rules do not close this path (F-2(a)) |
| `except Exception` and `except BaseException` are absent | grep exit 1 (rerun) | holds |
| `KeyboardInterrupt` and `SystemExit` propagate unwrapped | no broad `except`; the `KeyboardInterrupt` tests pass; `SystemExit` checked by probe (same object, empty chain) | holds |
| The pacing `finally` covers every exit after the hand-off to `send` | lines 277-282: the `try` contains only `self._send(request)`; the hook errors, the redirect-step errors and unmapped exceptions all pass through it; `now()` runs after it (probe: a failing `now` still leaves `_last_attempt_end` set and the cool-down flag taken from the capture) | holds |

## AC13, point by point

| # | Point | Command | Result |
|---|---|---|---|
| 1 | The 137 earlier tests pass | `uv run pytest -q` | `453 passed` (rerun); the four F1 and F0 test files are byte-identical to `main`, and `test_layers.py` only gains lines |
| 2 | `ruff check` | `uv run ruff check .` | `All checks passed!`, exit 0 (rerun; run because AC13 names it) |
| 3 | `ruff format` | `uv run ruff format --check .` | `75 files already formatted`, exit 0 (rerun) |
| 4 | `mypy` | `uv run mypy .` | `Success: no issues found in 20 source files`, exit 0 (rerun) |
| 5 | Doctor | `uv run node .sdd/doctor/run-doctor.mjs` | `summary: 31 ok, 0 skipped, 0 warned, 0 failed`, exit 0 (rerun) |
| 6 | `--version` | `uv run ec-procurement-quality --version` | `ec-procurement-quality 0.1.0`, exit 0 (rerun) |
| 7 | `uv sync --locked` (and `uv lock --check`) | both | `Resolved 22 packages`, `Checked 22 packages`, exit 0 for both (rerun) |
| 8 | `pyproject.toml` diff shows only `httpx` | `git diff main -- pyproject.toml` | only `"httpx>=0.28.1",` added to `[project] dependencies` (rerun) |
| 9 | F1 modules and `cli.py` unchanged | `git diff main --stat -- <4 F1 modules> interfaces/cli.py __init__.py` | empty (rerun) |
| 10 | Fixtures unchanged | `git log --oneline -- tests/fixtures/sercop`; `git status --short tests/fixtures` | one commit, `74b785d` (gate 1); clean (rerun) |
| 11 | `git diff --check` | `git diff --check`; `git diff main --check` | both clean (rerun) |
| 12 | No test names the real host | `git grep -n -i --untracked -e datosabiertos -e compraspublicas -- tests` | no match, exit 1 (rerun) |
| 13 | Revision 2: the 251 Revision 1 tests still pass, and only additions were made | per-group counts read against `tasks.md` O2 | the Revision 1 file was never committed (`git log` shows the test file first in `7b371b5`), so a content diff is `unavailable`. The counts match exactly, which supports the claim (rerun, by reading): `STATUS_CASES` 13 = 9 + 4; `PACING_CASES` 32 = 30 + 2; `INVALID_SEARCH_ARGUMENTS` 13; record-invalid 3; construction 16 + 13; boundaries 5 + 3; the groups of Revision 1 add up to 205; 205 + 65 = 270 in the file and 453 overall. Content identity is reused from `tasks.md` O2b ("diff ... shows no removed or changed line"). R-4 |

## AC14 and the doc claims

| Check | Result |
|---|---|
| `git grep -n "httpx" -- README.md CHANGELOG.md` | matches in both (`CHANGELOG.md` 40, 46, 49; `README.md` 72, 80) (rerun) |
| `git grep -n "No source access" -- README.md` | no match (rerun) |
| README "Planned" | "The ingestion that will call the SERCOP adapter and the raw evidence store." The adapter is no longer listed as missing. PASS |
| `docs/architecture.md` § Open questions | names `search_ocds` (buyer-name query) and `api/record` for the first flow, cites the observations, and says other response variants stay open. PASS |
| Claims verified by tests | one request per call (`len(requests) == 1` in every outcome test); no retries; pacing from `Remaining` (AC9); explicit timeouts (AC10); user information rejected (AC10); `MockTransport` and the network guard (AC11); a library only, with no CLI command (`cli.py` unchanged); `httpx` only in `infrastructure` (AC12); `httpx>=0.28.1` resolved to 0.28.1; dev dependencies unchanged |
| Claims not backed | README: "carries whatever response arrived, so that every response can be stored as evidence"; CHANGELOG: "raises a typed error that carries the response that arrived". For a status outside 100 to 599 a response arrives and is **not** carried (AC6 Revision 2, the test `invalid_status` asserts `response is None`): F-3. README "its tests use simulated transports" is also slightly loose: `test_no_network_default_transport_is_stopped_by_the_guard` deliberately uses the real transport, which the guard blocks. It is folded into F-3 |
| Unobserved source facts | none of the following is stated in the three doc diffs: the meaning of `local=1`, the window or key of the limit, `Retry-After`, the bodies of a `429` or `5xx`, the answer for an unknown `ocid`, filtering by RUC or `buyerId`. PASS |

## Project decisions versus source facts (point 6)

- Specs and ADR: the pacing values (5 s, 20, 60 s), the timeouts (10 s and 30 s), the
  echoed `page`, `Accept-Encoding: identity`, no cookies, Latin-1 headers and the
  invalid-status reading are all labelled **project decision** in `intent.md` and
  `execution-plan.md`. ADR 0006 calls the timeouts and pacing project decisions.
- Code: nothing presents them as source facts. Only the cookie rule carries an explicit
  "project decision" comment. The pacing values, timeouts, `identity` and the `page`
  echo are bare defaults with no label (see N3). `DEFAULT_BASE_URL` cites the
  observations.
- Tests: synthetic bodies, cookies, credentials and the defect are labelled
  `SYNTHETIC`. The no-results fixture is labelled `INFERRED`, and out-of-range is
  labelled `OBSERVED`. Cookie and Latin-1 tests say "project decision". The pacing tests
  use the defaults without claiming they were observed.
- Docs: none of the values are stated.
- No real data or secrets: the fixtures are sanitized and synthetic, with 3,223 bytes in
  total, and the tests write only under `tmp_path`.

## Lines the tests do not cover (point 7)

Coverage run (rerun): `sercop_source.py` 223 statements, 5 missed (`90-91, 312-313,
332`). TOTAL 522 statements, 18 missed, 97%. `procurement_source.py` and
`source_response.py` are at 100%. The other misses are F1 lines, unchanged.

| Lines | Branch | Behavior shown by probe (rerun) | Assessment |
|---|---|---|---|
| 90-91 | `urlsplit` raises `ValueError` (invalid IPv6 literal, unclosed bracket, NFKC netloc) | `https://[zz]/…`, `https://[::1/…` and a fullwidth `@` give `ValueError("base_url must be an absolute http or https URL")` with an empty chain and no echo | meets AC10; reservation R-2 (no test) |
| 312-313 | `int(text)` raises `ValueError` for more than 4,300 digits; the comment says "not low" | `"9" * 5000` gives `[3.0]`, as the spec requires; `"0" * 4999 + "5"` gives `[3.0]`, where the spec requires `[58.0]` | **finding F-1**: the comment's premise ("too many digits means a large value") is false for leading zeros |
| 332 | bare `raise` of `InvalidURL` with no status | unreachable with the real transport; with a `MockTransport` that raises `InvalidURL`, the same object propagates with an empty chain | consistent with "anything else is not mapped and propagates unchanged"; R-2 |

## Test coverage

| AC | Tests (all in `tests/unit/`) | Status |
|---|---|---|
| AC1 | `test_search_query_*` (7), `test_search_success_*` (3), `test_sercop_source.py` | PASS |
| AC2 | `test_record_query_*`, `test_record_success_*` (4) | PASS |
| AC3 | `test_raw_response_*` (6), `test_store_shape_*` (9), `test_cookie_*` (3) | PASS |
| AC4 | `test_search_out_of_range_*` (3, including the in-range empty case), `test_search_no_results_*` (1) | PASS |
| AC5 | `test_status_error_carries_the_complete_response` (26) | PASS |
| AC6 | `test_transport_*` (27 with `-k transport`) | PASS |
| AC7 | `test_incomplete_search_*` (25), `test_incomplete_record_*` (18) | PASS |
| AC8 | `test_no_leak_*` (12), plus 5 in `test_source_response.py` | PASS |
| AC9 | `test_pacing_*` (39) | PASS for the listed cases; F-1 is an input with no test |
| AC10 | `-k "timeout or accept_encoding or invalid"` (112, both files), `test_construction_accepts_the_documented_boundaries` (8) | PASS for the listed cases; F-2 inputs have no test |
| AC11 | `test_no_network_*` (2) plus the autouse guard | PASS |
| AC12 | `test_layer_*` (7), `test_satisfies_port_*` (1) plus `mypy` | PASS |
| AC13 | no new test; commands | PASS |
| AC14 | none (inspection, as planned) | PASS |
| AC15 | `test_transport_defect_*` (4) plus the Revision 2 cases of AC5, AC6, AC9 and AC10 | PASS |

Red evidence: reused from `tasks.md` O2 (missing modules; 19 broken reference variants)
and O2b (each item's red reason against the O5 code; 9 broken variants). These are
plausible and match the plan. Auditor mutants m1 and m2 are under § InvalidURL rule.
No test seam is dead: the `now`, `monotonic`, `sleep` and `transport` injections are
each exercised.

### Tier Results

Comparison with `execution-plan.md` § Validation, row by row: every row's named tests
exist with the named `-k` tokens and assert at least what the row lists. Where the tests
go further (extra encodings, bodies, pacing boundaries, `ConnectTimeout`, interrupts,
the no-echo test for all 13 rejected URLs, invalid input after `close()`), that is still
within the unit tier the row names. No row has a weaker test, with one exception: the
row's broader `-k` for AC15 includes `userinfo`, and its no-echo assertion is not strong
enough to catch chaining (R-1).

Round 2 updated this table in place. The first seven columns are round 1's,
unchanged. The last four columns hold round 2's results (Revision 3, `19ab9c3`).

| Tier | Tests found | ACs verified | Setup matches § Validation | Ran | Status | Finding | Round 2: tests found | Round 2: ran | Round 2: status | Round 2: finding |
|---|---|---|---|---|---|---|---|---|---|---|
| unit (pytest) | 316 new (`test_sercop_source.py` 270, `test_source_response.py` 45, `test_layers.py` +1) and the 137 baseline tests, all in `tests/unit/` | AC1 to AC12, AC15 | Yes: only `uv sync --locked`; no dev dependency, `conftest.py`, config file or script added (`pyproject.toml` changes only the runtime `httpx` line; `uv.lock` +72/-0; `.github`, `.sdd`, `.claude` and `.gitignore` unchanged against `main`) | rerun (Windows, Python 3.13.9). Ubuntu CI on the audited state: `unavailable` | PASS | none at tier level; F-1 and F-2 are code or spec defects, R-1 | 569 = 137 baseline + 432 F2 (`test_sercop_source.py` 386, of which 116 are O2c; `test_source_response.py` 45; `test_layers.py` +1). Setup unchanged since `015a72b`: `pyproject.toml`, `uv.lock`, `.github`, `.sdd`, `.claude`, `.gitignore` show no diff | rerun (Windows, Python 3.13.9): `569 passed`; Ubuntu CI on `19ab9c3`: `569 passed` (reused from the run log, read in this round) | PARTIAL | F-6: the AC8 tests use a synthetic `httpx.RemoteProtocolError("synthetic cut-off")` and do not cover the messages that the real `h11` path produces; R-2 (m2c survives) |
| unit (mypy, AC12) | the annotated `satisfies_port` assignment | AC12 | Yes | rerun | PASS | none | unchanged | rerun: `Success: no issues found in 20 source files` | PASS | none |
| command (AC13) | the 13 points above | AC13 | Yes | rerun (point 13 partly reused) | PASS | R-4 | the 13 points, plus the Revision 3 `git diff --numstat 015a72b -- tests` | rerun (all 13) | PASS | R-4 closed |
| manual (AC14) | inspection plus the two `git grep` commands | AC14 | Yes (none needed) | rerun | PASS | F-3 (LOW) | the same | rerun | PASS | F-3 closed |
| manual (AC15) | the closed-set justification against `.venv` | AC15 | Yes | rerun | PARTIAL | F-2 | the closed-set justification and the 43 rows of § Family check against `.venv` | rerun | PARTIAL | F-5 (row 2.9) |

No test exists at a tier that § Validation does not name (round 1, and round 2).

## Conventions and feedback

- `harny-standards` (conventions document: `AGENTS.md`). Checked against each rule:
  - layer boundaries: met;
  - raw responses are evidence and are not overwritten: met (the adapter never writes);
  - no invented SERCOP contract: met (labels above);
  - dependency added with approval: met (`httpx` was approved, ADR 0006 is accepted);
  - no new infrastructure, framework or service: met;
  - no secrets or complete datasets: met;
  - verification reported: met (the `tasks.md` evidence matches these reruns, see below).

  No violation found. No AI or Claude attribution appears in the changed source, tests
  or docs, or in the branch's commit messages (grep, rerun).
- `harny-feedback`: the CI workflows `.github/workflows/harny-feedback.yml` and
  `tests.yml` are present, and the Stop and SubagentStop hooks are configured in
  `.claude/settings.json` (rerun, by reading). The CI runs on the audited state are
  `unavailable`: the doc edits are uncommitted and this audit made no network access.
  `tasks.md` O8 records `feedback pass` and `tests pass` for `015a72b` only, so they are
  reused for every code and test file (the working-tree diff touches neither) and are
  not counted for the doc edits. The runner's `N of M command(s) ran` line could not be
  read (no network): `unavailable`. Whether the per-turn hook fired during
  implementation is also `unavailable`, because it leaves no persistent log. `ruff` and
  `mypy` were rerun here only because AC13 names them as acceptance evidence. Both are
  clean.

## Findings

| Id | Severity | Finding and evidence | Closure condition | Status |
|---|---|---|---|---|
| F-1 | MEDIUM (blocking: unmet AC9 and binding pacing rule) | AC9 ("a longer cool-down ... when the previous response had ... a `Remaining` value below a threshold") and the plan's § Pacing ("A valid value is ASCII decimal digits after stripping surrounding whitespace; any other value is ignored"). `_asks_for_cooldown` (`sercop_source.py:310-313`) treats `int()`'s `ValueError` as "not low". Python's default limit of 4,300 digits for converting a string to `int` counts leading zeros, so a valid small value written with more than 4,300 digits is skipped. Reproducer (rerun, `MockTransport`, defaults): a first response with `X-RateLimit-Remaining: "0" * 4999 + "5"`, then a call 2 s later, gives sleeps `[3.0]`; the spec requires `[58.0]`. The same input fails for any header with 4,301 or more digits whose value is below the threshold. An HTTP/1.1 header of about 5 KB fits within `h11`'s default limits. The impact is pathological (one wait shorter than the rule asks), but the rule is unambiguous. `tasks.md` O8 lists lines 312-313 as uncovered but does not record that their behavior differs from the plan. | The architect decides, in a spec revision recorded in `tasks.md`, either (a) to keep the rule and plan a test case (in `PACING_CASES`) plus an executor change, with red evidence on the current code, or (b) to revise AC9 and § Pacing so that they state how a value too long to convert is treated (and say that it is not observed). Then the auditor rechecks. This report proposes no code workaround. | Open |
| F-2 | MEDIUM (blocking: AC10 guarantee not met; spec gap) | AC10 Revision 2: "The base URL is checked completely at construction, so that no call can fail on it later". The plan's § Closed-set justification says that `OverflowError` is the one unmapped path below `httpx`, and that a too-long URL can only come from a long buyer or `ocid`. Every listed construction rule is implemented, but they do not deliver the guarantee. (a) `https://<64 or more ASCII characters>.invalid/PLATAFORMA` or `https://a..invalid/PLATAFORMA` passes construction, because `httpx` accepts any ASCII host without a label check (`_urlparse.py:379-386`). On the first call with the real transport, `getaddrinfo` encodes the host with the `idna` codec and raises `UnicodeEncodeError`. `httpcore` maps only `OSError` and `socket.timeout`, so it escapes `search_page` as an untyped `ValueError` subclass, not a `SourceError`. Evidence: a probe, rerun, that replaced `socket.getaddrinfo` with a stand-in that first does `host.encode("idna")` (as CPython's C `getaddrinfo` does for a `str` host) and then refuses. No resolution was made. The adapter, `httpcore` and `httpx` paths ran for real, and the exception escaped with `isinstance(e, httpx.HTTPError)` false. (b) A base URL of 65,523 characters (`https://source.invalid/` plus 65,500 `p`) passes construction, and every call raises `ValueError("…the request URL is too long…")`. That outcome is in the closed set, but it contradicts "no call can fail on it later". | The architect revises AC10 and the plan in one of two ways: extend the construction rules (for example a host check that matches what name resolution accepts, and room left for the fixed path and query), or narrow the guarantee to the listed rules and add the `idna` path to § Closed-set justification as an exception that propagates unchanged. Either way, the cases are named in § Validation and tested, with red evidence. This report proposes no code workaround. | Open |
| F-3 | LOW | AC14 (docs say what exists) together with AC6 Revision 2. README § Technologies says "carries whatever response arrived, so that every response can be stored as evidence". CHANGELOG says "raises a typed error that carries the response that arrived". For a status outside 100 to 599 no response is carried, and that case is not kept as evidence (the human accepted this in intent § Open questions). README also says the tests "use simulated transports". One test intentionally uses the real transport behind the guard. | The executor (owner of `README.md` and `CHANGELOG.md`) rewords both sentences to state the invalid-status exception (and, optionally, the guard-proof test). This is checked by reading. No spec change is needed. | Open |
| F-4 | LOW | Spec consistency. `execution-plan.md` § Guidance consulted line 4 says "`intent.md` Revision 2 ... pending human approval", while `intent.md` records the approval. Line 14 says the observations file is "modified in the working tree and not yet committed", but it was committed in `5a7bb90`. | The architect updates the two lines, or marks them as history of the drafting time. | Open |

## Reservations (not findings)

- R-1: the rule that the library's `InvalidURL` is never chained (plan § Binding
  constraints, the authority of `base_url`, and § Outcome mapping) is met by the code
  but has no test. Mutants m1 and m2 pass all 453 tests. A suggested test, which the
  test-writer would write once the architect names it in § Validation:
  - for each entry of `REJECTED_BASE_URLS`, for both 70,000-character inputs, and for
    the four malformed-`Location` cases of `STATUS_CASES`, walk `_exception_chain(error)`;
  - assert that no element is an `httpx.InvalidURL` or an `httpx.HTTPError`. For the
    construction and too-long cases, the stricter assertion is
    `error.__cause__ is None and error.__context__ is None`;
  - red evidence: run against m1 and m2.
- R-2: lines 90-91 (`urlsplit` `ValueError`) and 332 (`InvalidURL` re-raise) have no
  test. Their behavior meets the spec (probes above). A `REJECTED_BASE_URLS` entry such
  as `https://[zz]/PLATAFORMA` would cover line 90-91.
- R-3: `SystemExit` is named in AC15 and in the pacing rule, but only `KeyboardInterrupt`
  is tested. The probe shows that `SystemExit` before the status, and while reading a
  `429` body, propagates as the same object and yields `[3.0]` and `[58.0]`.
- R-4: AC13 point 13. The Revision 1 test file was never committed, so "removes or
  weakens none" can be checked only through the per-group counts, which match exactly,
  and through `tasks.md` O2b's recorded diff (reused).
- R-5: the PR #16 checks and the hook's run log are `unavailable` for the audited state
  (§ Conventions and feedback).
- R-6: below `httpx`, `ResponseStream.close()` is not wrapped by
  `map_httpcore_exceptions`, so a socket-level error while closing propagates unmapped,
  as an `httpcore` or OS exception. This is the risk the plan already accepts in its
  § Risks table. Pacing still records the attempt.

## Notes (informational)

- N1: the AC3 example's store step ("the observation keeps the other five pairs") is
  tested with three header pairs, not with the six pairs of AC3. The property (every
  pair except `Set-Cookie`, in order) is asserted, and repeated names through the store
  are F1's tested behavior. The § Validation row asks for no more.
- N2: `test_satisfies_port_*` builds the adapter with the default base URL (the real
  host) over `MockTransport`, as the plan's AC12 row prescribes, and does not close it.
  Nothing reaches the network. A `source.invalid` base URL and a `with` block would make
  the "URLs use `.invalid`" rule hold literally.
- N3: in code, the defaults (5 s, 20, 60 s, 10 s and 30 s), `Accept-Encoding: identity`
  and the `page` echo are not labelled as project decisions, and nothing calls them
  facts either. A one-line comment would match the cookie rule's style. No spec
  requires it.
- N4: an upper-case scheme or host, or an explicit default port, in `base_url` is
  normalized by `httpx`, so `RawResponse.url` (`str(request.url)`, the URL as sent)
  differs from the built string. That is what the plan's primary rule asks for. The
  "equals the built string" sentence assumes a normalized base URL.
- N5: `tasks.md` says nothing about whether the human re-read the Revision 2 blocks of
  `sercop_source.py`. This audit does not depend on it.
- N6: the human or the orchestrator fills `tasks.md` O9 with this verdict. The auditor
  writes only `audit.md`.

## Commands run (all rerun, Windows, Python 3.13.9, `uv` from the repository root)

| Command | Result |
|---|---|
| `uv sync --locked` | `Resolved 22 packages`, `Checked 22 packages`, exit 0 |
| `uv lock --check` | `Resolved 22 packages`, exit 0 |
| `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing` | `453 passed`; TOTAL 522 statements, 18 missed, 97%; `sercop_source.py` 98% (missing 90-91, 312-313, 332) |
| `uv run pytest -q` | `453 passed`, exit 0 |
| `uv run pytest tests/unit/test_sercop_source.py -q -k "search_success or query"` | `11 passed` |
| `… -k record_success` | `4 passed` |
| `… -k "raw_response or store_shape or cookie"` | `18 passed` |
| `… -k "out_of_range or no_results"` | `4 passed` |
| `… -k status_error` | `26 passed` |
| `… -k transport` | `27 passed` |
| `… -k incomplete` | `43 passed` |
| `uv run pytest tests/unit/test_source_response.py tests/unit/test_sercop_source.py -q -k no_leak` | `17 passed` |
| `… test_sercop_source.py -k pacing` | `39 passed` |
| `… both files -k "timeout or accept_encoding or invalid"` | `112 passed` |
| `… -k no_network` | `2 passed` |
| `uv run pytest tests/unit -q -k "layer or satisfies_port"` | `9 passed` |
| `… -k "transport_defect or invalid_status or status_error or too_long or after_close or userinfo"` | `50 passed` |
| `uv run ruff check .` / `uv run ruff format --check .` / `uv run mypy .` | `All checks passed!` / `75 files already formatted` / `Success: no issues found in 20 source files` |
| `uv run node .sdd/doctor/run-doctor.mjs` | `31 ok, 0 skipped, 0 warned, 0 failed` |
| `uv run ec-procurement-quality --version` | `ec-procurement-quality 0.1.0` |
| `git diff --check`; `git diff main --check` | clean |
| `git diff main -- pyproject.toml`; `git diff main --stat -- uv.lock` | only the `httpx` line; `uv.lock` +72/-0 |
| `git diff main --stat -- <F1 modules, cli.py, __init__.py>`; `git log --oneline -- tests/fixtures/sercop` | empty; `74b785d` only |
| `git diff main --numstat -- tests` | 0 deletions in every file |
| `git grep -n -i --untracked -e datosabiertos -e compraspublicas -- tests` | exit 1 |
| `git grep -n "datosabiertos.compraspublicas.gob.ec/PLATAFORMA" -- src` | 1 match (`sercop_source.py:43`) |
| `git grep -n -e "except Exception" -e "except BaseException" -- src/…/sercop_source.py` | exit 1 |
| Scratchpad probes `probe.py` and `probe2.py` (offline, `.venv` interpreter with `-I`) | results quoted in F-1, F-2 and § InvalidURL rule; `getaddrinfo` stood in for in `probe2.py` |
| Scratchpad mutants m1 and m2 (`PYTHONPATH=<copy>/src`, imported path confirmed) | `453 passed` each |

## Not verified, and why

- The PR #16 `Tests` and `feedback` checks on the audited state are `unavailable`: the
  doc edits are uncommitted and the audit made no network access. The result recorded
  for `015a72b` is reused for code and tests only.
- Linux (Ubuntu CI) runs of the 316 new tests on this state are `unavailable`.
- Real name resolution was not exercised for F-2(a). The `idna` step was stood in for
  offline. The `httpcore` and `httpx` behavior after it ran for real.
- The Revision 1 test content behind AC13 point 13 is `unavailable` (never committed).
  Counts were checked instead.
- Whether the Stop hook fired during implementation is `unavailable` (no persistent
  log).

## Round 2

### Scope of round 2

Round 2, 2026-10-10. Auditor: `sdd-auditor` (harny-audit). Reviewed state: branch
`feat/sercop-source-adapter` at `19ab9c3` (committed and pushed, clean working tree,
`git status --short` empty), base `main` `fff0f2d`. Since round 1 (`015a72b`): intent
and plan Revision 3 (approved), 116 new tests (O2c, gate 2 approved),
`infrastructure/sercop_source.py` (O5c), two sentences of `README.md` and
`CHANGELOG.md` (O7b) and `tasks.md`. `git diff --stat 015a72b HEAD -- src` touches only
the adapter. `domain`, `application`, `interfaces`, F1, the fixtures, `docs/adr`,
`pyproject.toml`, `uv.lock`, `.github`, `.sdd`, `.claude`, `.gitignore` and the other
six test files show no diff against `015a72b`.

Read in full for this round: `intent.md` Revision 3, `execution-plan.md` Revision 3,
`tasks.md`, the round 1 report, the whole adapter at `19ab9c3`, and the whole test
diff `015a72b..HEAD`. Library sources read in `.venv/Lib/site-packages/`: `httpx/_client.py` (`send`,
`_send_handling_auth`, `_send_handling_redirects`, `_send_single_request`, proxies),
`httpx/_models.py` (`Response.headers`, `has_redirect_location`,
`Cookies.extract_cookies`, `_CookieCompatRequest` and `_CookieCompatResponse`),
`httpx/_urls.py` (`host`, `raw_host`), `httpx/_urlparse.py` (`MAX_URL_LENGTH`, the
non-printable check, `encode_host`), `httpx/_utils.py` (`URLPattern.matches`),
`httpx/_transports/default.py` (`map_httpcore_exceptions`, `ResponseStream`),
`httpcore/_backends/sync.py` (`connect_tcp`, `start_tls`, read and write mappings),
`httpcore/_sync/http11.py` (`MAX_INCOMPLETE_EVENT_SIZE`), `httpcore/_backends/mock.py`,
`h11/_abnf.py`, `h11/_readers.py`, `h11/_headers.py` and `h11/_connection.py`. From the
standard library: `encodings/idna.py` and `ssl.SSLContext._encode_hostname`, in
`C:\Program Files\Python313\Lib`.

No network access was made to SERCOP or to any resolver. Probes ran with the `.venv`
interpreter and `-I` in the session scratchpad, outside the repository. They used
`httpx.MockTransport`, and `httpcore.MockBackend` under a real `httpx.HTTPTransport`,
so the real `httpx`, `httpcore` and `h11` code ran on synthetic bytes with no socket.
A guard replaced `socket.socket.connect`, `connect_ex`, `create_connection` and
`getaddrinfo`, and recorded 0 attempts. One probe replaced `getaddrinfo` with a
stand-in that applies the `idna` codec and then raises `socket.gaierror`. The only
network access was to GitHub, through `gh`, to read the PR #16 checks and run logs (point
6 of the brief).

### Round 1 findings and reservations, rechecked

| Item | Exact round 1 input, rerun now | Result on `19ab9c3` | Status |
|---|---|---|---|
| F-1 (AC9) | `X-RateLimit-Remaining` `"0" * 4999 + "5"`, then a call 2 s later; `"0" * 4300 + "5"`; `low_remaining_threshold=10**5000` with `"9" * 4400`; plus `"1" + "0" * 5000` against that threshold (equal, so not low) | `[58.0]`, `[58.0]`, `[58.0]`; `[3.0]` (probe, rerun). The same results with `sys.set_int_max_str_digits(640)`, a `decimal` context of precision 1 and every trap on: `[58.0]`, `[58.0]`, and `[3.0]` for `"0" * 5000 + "20"`. `_asks_for_cooldown` has no `int()` and no `ValueError` branch left: `strip(" \t")`, then an ASCII-digit check, then `Decimal(text) < threshold`. The tests `PACING_CASES` `remaining-of-4999-zeros...`, `...4301-digits...`, `a-threshold-of-5001-digits...` pass, and fail against the `015a72b` adapter (rerun, below) | **Resolved** |
| F-2(a) (AC10) | `https://` + 64 `a` + `.invalid/PLATAFORMA`; `https://a..invalid/PLATAFORMA` | `ValueError("base_url must have host labels of 1 to 63 characters")`, with `__cause__` and `__context__` `None` and no echo (probe, rerun). Every base URL that construction accepts was run through the real transport, with the `idna` stand-in in place of `getaddrinfo` (label of 63, host of 253 with and without a trailing dot, trailing dot, `[::1]:8443`, `a%zz.invalid`, `a"b.invalid`, upper case, `a.xn--.invalid`). Each call raised `SourceTransportError` with no response. On the same path, the round 1 inputs, sent past construction on purpose, still raise `builtins.UnicodeEncodeError`, so the rule is what closes the path. Each accepted host also passes `str.encode("idna")` and `ssl` `wrap_bio(server_hostname=...)` with memory BIOs | **Resolved** |
| F-2(b) (AC10) | base URL `https://source.invalid/` + 65,500 `p` (65,523 characters) | `ValueError("base_url must leave room for the request URL")` with an empty chain (probe, rerun). 65,023 characters are accepted, and a 4,000-digit year then raises `ValueError` before any request or wait (test `test_invalid_input_too_long_year_on_a_long_base_url_raises_value_error`) | **Resolved** |
| F-3 (AC14) | the README and CHANGELOG sentences | README: "carries the valid response that arrived, so that it can be stored as evidence; a status outside 100 to 599 is reported without a response". CHANGELOG: "carries the valid response that arrived (a status outside 100 to 599 is reported without a response)". `git grep -n -i "whatever response arrived\|the response that arrived"` finds no match. The optional sentence about the guard was not added, and the closure condition did not require it | **Resolved** |
| F-4 | `execution-plan.md` § Guidance consulted | Line 4 says Revision 3 and Revision 2 were approved. Line 27 says the observations file "was committed in `5a7bb90`". Other stale lines of the same kind remain elsewhere (F-7) | **Resolved** (the two lines named) |
| R-1 (AC8 Revision 3) | the auditor's mutants, recreated on scratch copies of `src/` (imported path printed and confirmed): m1 (`_build_request` raises its `ValueError` `from` the caught `InvalidURL`) and m2 (`_base_url_problem` raises `ValueError(...) from exc` inside the `except` around `httpx.URL(base_url)`) | `-k no_leak_rejections`: m1 gives `2 failed, 35 passed` (`too-long-search-buyer`, `too-long-record-ocid`), and m2 gives `2 failed, 35 passed` (`base-url-invalid-ipv4-host`, `base-url-control-character`). An extra mutant, m2b (the same at the `url.host` decode), gives `2 failed` (`a-label-malformed`, `a-label-disallowed`). A fourth, m2c (the same at the `urlsplit` branch, lines 171 and 172), gives `37 passed`: see R-2 | **Resolved** (m2c is carried as R-2) |
| R-3 (AC9, AC15) | `SystemExit` before the status, and while reading a `429` body | Tests: `UNMAPPED_EXCEPTION_CASES` `system-exit-before-the-status` (`[3.0]`), `system-exit-while-reading-a-429` (`[58.0]`), and `test_transport_defect_system_exit_propagates_unchanged` (2 places by 2 operations). Probe, rerun: the same object both times, an empty chain, sleeps `[3.0]` and `[58.0]` | **Resolved** |
| R-2 | lines 171 and 172 (`urlsplit` `ValueError`) | Still not covered. The behavior is correct (`https://[::1/PLATAFORMA` gives the fixed reason, with an empty chain), but mutant m2c survives the whole no-chain test. The `InvalidURL` re-raise of round 1 line 332 no longer exists | Open (reservation) |
| R-4 | test content behind AC13 point 13 | The reference is now `015a72b`. `git diff --numstat 015a72b -- tests` gives `458 0 tests/unit/test_sercop_source.py` | **Resolved** |
| R-5 | PR checks on the audited state | `19ab9c3`: `feedback pass`, `tests pass` (§ Doc coherence and PR checks) | **Resolved** |
| R-6 | `ResponseStream.close()` not wrapped | Unchanged (`_transports/default.py` `close` is not under `map_httpcore_exceptions`); an accepted risk in plan § Risks | Open (accepted risk) |

### AC results (intent Revision 3)

| AC | Status | Evidence |
|---|---|---|
| AC1 | PASS | `-k "search_success or query"` -> `13 passed` (rerun), including `test_record_query_sends_a_non_ascii_base_path_percent_encoded` (the URL as sent is `.../PLATFORM%C3%81/api/record?...`). `git grep "datosabiertos.compraspublicas.gob.ec/PLATAFORMA" -- src` -> 1 match, `sercop_source.py:50` (rerun) |
| AC2 | PASS | `-k record_success` -> `4 passed` (rerun) |
| AC3 | PASS | `-k "raw_response or store_shape or cookie"` -> `20 passed` (rerun), including `test_cookie_set_cookie_is_never_parsed_and_raises_no_warning` (both operations, with `simplefilter("always")`). The whole suite under `-W error` -> `569 passed` (rerun). Probe through the real client (`httpcore.MockBackend`): a `200` with the 5,000-digit `expires` and a second `Set-Cookie` gives 0 warnings, a jar of size 0, and both `Set-Cookie` pairs kept, and the next request built has no `Cookie` |
| AC4 | PASS | `-k "out_of_range or no_results"` -> `4 passed` (rerun) |
| AC5 | PASS | `-k status_error` -> `30 passed` (rerun), including `302-location-host-not-decodable` and `308-location-scheme-relative-host-not-decodable`. Probe through the real client: a `302` with `Location` `http://xn--/`, `//xn--/`, `https:abc`, the bytes `0xff 0xfe`, `http://[zz]/` or `/` + 65,530 `a` ends in `SourceStatusError` with the exact body, the `Location` kept as received, and `__cause__` and `__context__` `None` |
| AC6 | PASS | `-k transport` -> `31 passed` (rerun). Probe through `h11`: status `099` and `101` without an upgrade give `SourceTransportError` with no response; `600` gives the same with the message naming the status; an informational `103` before a `200` is skipped by `httpcore` and the `200` is the result |
| AC7 | PASS | `-k incomplete` -> `53 passed` (rerun): the 10 Revision 3 bodies. `test_search_success_takes_the_last_value_of_a_repeated_name` passes. `parse_constant=_reject_json_constant` is used, and `RecursionError` and `ValueError` are caught without being chained. The two `nested-too-deep` bodies put the nesting inside an otherwise valid body, not as the whole body. This is a compliant alternative that the human confirmed at gate 2 (N-11) |
| AC8 | **PARTIAL** | `-k no_leak` over both files -> `54 passed` (rerun), including the 37 cases of `test_no_leak_rejections_chain_no_library_exception` (mutants above). **F-6**: with the real `h11` path, the chained `httpx.RemoteProtocolError` quotes body bytes or a whole header line, which the AC8 headline and the test's own chain assertion exclude |
| AC9 | PASS | `-k pacing` -> `50 passed` (rerun). F-1 closed (above). Every Revision 3 example holds by probe as well: byte `0xA0` + `5`, byte `0x85` + `5`, `0x0B` + `19`, byte `0xB2`, empty, `+5`, `5,5` and `1_9` give `[3.0]`; a tab, `19`, a tab gives `[58.0]`; a space, `19`, a space gives `[58.0]` |
| AC10 | **PARTIAL** | `-k "timeout or accept_encoding or invalid"` over both files -> `155 passed`; `-k "documented_boundaries or non_ascii_base_path"` -> `18 passed` (rerun). Every Revision 3 rejection and acceptance in the AC10 example was rechecked by probe, with fixed reasons and empty chains, along with these: `https://./PLATAFORMA`; `https://xn--bcher-kva.ab--cd.invalid/PLATAFORMA` (rejected by the IDNA decode); `[v1.x]` and a 70-character non-ASCII label (rejected by `httpx.URL`); `0x7f.1`, `a_b`, `münchen`, `a.xn--.invalid` and `[::ffff:1.2.3.4]` (accepted, and harmless as shown under F-2(a)). Numbers: `Decimal(5)` and `-inf` are rejected; `5e-324`, `1e-300` and `-0.0` are accepted, and `socket.settimeout(5e-324)` gives 1 ns, with no error. **F-5**: a non-ASCII IPv6 zone is rejected by an unmapped `UnicodeEncodeError`, not by the fixed reason |
| AC11 | PASS | `-k no_network` -> `2 passed` (rerun). `git grep -n -i --untracked -e datosabiertos -e compraspublicas -- tests` -> exit 1. `git grep -c "source.invalid" -- tests/unit/test_sercop_source.py` -> 37 |
| AC12 | PASS | `tests/unit -k "layer or satisfies_port"` -> `9 passed`; `uv run mypy .` -> `Success: no issues found in 20 source files` (rerun). `httpx` is imported only at `infrastructure/sercop_source.py:34` and in the test file. `domain` and `application` are unchanged since `015a72b` |
| AC13 | PASS | the 13 points below, all rerun |
| AC14 | PASS | the AC14 commands and F-3 above |
| AC15 | **PARTIAL** | `-k "transport_defect or invalid_status or status_error or too_long or after_close or userinfo or cookie or no_leak"` -> `113 passed` (rerun). No `except Exception` or `except BaseException` (grep exit 1). `KeyboardInterrupt`, `SystemExit` and `MemoryError` propagate as the same object, and the attempt counts for pacing (tests, and a probe for `MemoryError` from the body read and from `json.loads`: `[58.0]` after a `Remaining` of 5). § Family check: 42 of 43 rows hold; row 2.9 does not (F-5). F-5 keeps the type inside the closed set (`UnicodeEncodeError` is a `ValueError`) but not the binding message rule. F-6 concerns AC8, not the closed set: the chained library exception never escapes on its own |

### Binding constraints added or changed by Revision 3

| Constraint | Status | Evidence |
|---|---|---|
| Numeric options (type, finite, at most 86,400; `bool` and `"60"` give `ValueError`) | PASS | `_require_seconds`; the tests; probe (above) |
| Host and length of `base_url` (labels, 253, IDNA decode, zone, room for the request), with the no-echo and no-chain rules | **FAIL for one input (F-5)**; PASS otherwise | `_base_url_problem` lines 190 to 206. `url.raw_host` (line 198) encodes the host as ASCII outside any `try`. For an IPv6 literal with a non-ASCII zone, `httpx` keeps the zone text as given (`encode_host` returns `host[1:-1]`, and `ipaddress` accepts any scope text), so `raw_host` raises before `_host_problem` can apply the zone rule |
| No cookie processing (`Set-Cookie` never parsed; no warning; no `Cookie`) | PASS | `_NoCookieJar.extract_cookies` does nothing. `httpx` still builds `_CookieCompatRequest` (a `urllib.request.Request` on `str(request.url)`) before calling the jar: probe, rerun, for every accepted base URL, with no error. `_CookieCompatResponse.info()` is never called. `Client.build_request` merges no cookie, because the jar is empty (`Cookies.__bool__`) |
| Nothing derived from `Location` runs or leaves the call, with no broad `except` | PASS | In the hook, the raw headers are captured, then `del response.headers["location"]` (`Headers.__delitem__` removes every case and every repeat). `Response.headers` is a plain attribute (`_models.py:532`), so the deletion reaches the object that `has_redirect_location` reads (`_client.py`: the hooks run, then `has_redirect_location`). Probe: the handler's own header list is unchanged, `RawResponse.headers` keeps `Location` on both of two calls, and `next_request` stays `None`. The deletion touches only the client's response object for this request; no state is shared with the next request |
| Order of a call, step 3 causes (a) to (c) | PASS | `_search_url` (f-string of `year` and `page`, `quote`) runs before `_build_request`; probe and tests: `10**5000` and `"\ud800"` give `ValueError` with no request or wait |
| Completeness checks (RFC 8259 constants, interpreter limits, last value) | PASS | AC7 |
| Pacing: `strip(" \t")`, exact comparison, independent of `sys.get_int_max_str_digits()` | PASS | F-1 row above |
| No content in errors, representations or logs | **FAIL (F-6)** for the chained library exception; PASS for the adapter's own messages, `str`, `repr`, logs and output | § Findings |
| Layer imports; dependency; F1; package root; offline tests | PASS | AC12, AC13; `ls src/ec_procurement_quality` shows only `__init__.py` and the four layers |

### AC13, point by point (round 2)

| # | Point | Command | Result (all rerun) |
|---|---|---|---|
| 1 | The 137 baseline tests and every later one pass | `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing` | `569 passed`; TOTAL 562 statements, 15 missed, 97% |
| 2 | `ruff check` | `uv run ruff check .` | `All checks passed!`, exit 0 |
| 3 | `ruff format` | `uv run ruff format --check .` | `76 files already formatted`, exit 0 |
| 4 | `mypy` | `uv run mypy .` | `Success: no issues found in 20 source files`, exit 0 |
| 5 | Doctor | `uv run node .sdd/doctor/run-doctor.mjs` | `summary: 31 ok, 0 skipped, 0 warned, 0 failed`, exit 0 |
| 6 | `--version` | `uv run ec-procurement-quality --version` | `ec-procurement-quality 0.1.0`, exit 0 |
| 7 | `uv sync --locked` and `uv lock --check` | both | `Resolved 22 packages`, `Checked 22 packages`; exit 0 for both |
| 8 | `pyproject.toml` adds only `httpx` | `git diff main -- pyproject.toml` | only `dependencies = []` -> `["httpx>=0.28.1",]` |
| 9 | F1 modules, `cli.py`, package root unchanged | `git diff main --stat -- <the four F1 modules> interfaces/cli.py __init__.py` | empty |
| 10 | Fixtures unchanged | `git log --oneline -- tests/fixtures/sercop`; `git diff --stat 015a72b HEAD -- tests/fixtures` | one commit, `74b785d`; empty |
| 11 | `git diff --check` | `git diff --check`; `git diff main --check` | clean, exit 0 |
| 12 | No test names the real host | `git grep -n -i --untracked -e datosabiertos -e compraspublicas -- tests` | no match, exit 1 |
| 13 | Revision 2 and Revision 3: nothing removed or weakened | `git diff --numstat 015a72b -- tests`; `git diff --stat 015a72b 83c0b11 -- tests`; added lines searched for `skip`, `xfail`, `filterwarnings`, `importorskip`, `monkeypatch` and `conftest`; repeated `def` and module constants searched | `458 0 tests/unit/test_sercop_source.py`, and no other test file differs; empty; the only match is a `return` inside the new helper `_summary`; no repeated name, so no new definition shadows an old test or case list. 386 tests collected in the file (270 + 116) and 569 in total. The old file's lines are all present, unchanged, and its 270 tests pass inside the 386 |

Red evidence for O2c, checked independently: the current tests were run against the
`015a72b` adapter on a scratch copy (imported path confirmed): `61 failed, 508 passed`.
That is the 61 that `tasks.md` O2c names, with the same ids: 4 `Location`
`IDNAError`, 2 cookie warnings, 5 JSON constants, 14 no-chain, 4 pacing, 32 base URL
and option cases.

### AC14 and the doc claims (round 2)

| Check | Result (rerun) |
|---|---|
| `git grep -n "httpx" -- README.md CHANGELOG.md` | `CHANGELOG.md` 40, 47, 50; `README.md` 72, 81 |
| `git grep -n "No source access" -- README.md` | no match, exit 1 |
| README "Planned" | "The ingestion that will call the SERCOP adapter and the raw evidence store." PASS |
| `docs/architecture.md` § Open questions | names `search_ocds` (buyer-name query) and `api/record`; other variants stay open. PASS |
| F-3 sentences | corrected (above). README "its tests use simulated transports" is unchanged. It was optional under F-3 |
| Claims not backed by a test | none found. Neither doc claims that errors carry no response content, so F-6 contradicts no doc sentence |

### § Family check, row by row against the installed packages

Status: **holds** means that the row's path and its stated behavior were confirmed in
the named source or probe. **Gap** means a defect, with a reproducer.

| Row | Checked in | Result |
|---|---|---|
| 1.1 | `h11/_abnf.py:98` `status_code = r"[0-9]{3}"`; probe `099`, `600` through `h11` | holds |
| 1.2 | only `MockTransport` can give a non-`int` or 4+ digit status | holds (test double) |
| 1.3 | `_client.py` `logger.info(... response.reason_phrase)`; probe: a reason phrase holding a marker appears in the `httpx` INFO record | holds; the reason phrase is neither a header nor a body value (N-9) |
| 1.4 | `value.decode("latin-1")` | holds |
| 1.5 | `h11/_abnf.py:17,21` (`field_name = token`, ASCII only) | holds |
| 1.6 | probe (F-1 row) | holds |
| 1.7 | probe: `0xA0`, `0x85`, `0x0B` give `[3.0]` | holds |
| 1.8 | probe: `0xB2`, `+5`, `5,5`, `1_9`, empty give `[3.0]` | holds |
| 1.9 | probe: threshold `10**5000` | holds |
| 1.10 | `h11/_headers.py:15` (`CONTENT_LENGTH_MAX_DIGITS = 20`), `h11/_abnf.py:118` (1 to 20 hex digits), `h11/_connection.py:485-489` ("Receive buffer too long") | holds in substance; the header-block figure is wrong: `httpcore/_sync/http11.py:45` sets `MAX_INCOMPLETE_EVENT_SIZE = 100 * 1024`, not 16 KiB (F-7) |
| 1.11 | `_client.py` `self.cookies.extract_cookies(response)` before the hooks; `_models.py:1101-1108`; probe through the real client | holds |
| 1.12 | `_client.py` hooks, then `has_redirect_location`; probe with 6 `Location` values through the real client | holds |
| 1.13 | the adapter reads only the status, the raw headers (for the capture and `Remaining`) and the body bytes | holds |
| 1.14 | `content.decode("utf-8")` inside the `try` | holds |
| 1.15 | `parse_constant`; tests | holds |
| 1.16 | tests; `int()` limit raised as `ValueError` inside `json.loads` | holds |
| 1.17 | tests (100,000 levels) | holds |
| 1.18 | test | holds |
| 1.19 | `_is_count`; the existing `total-float` case | holds |
| 1.20 | probe: `MemoryError` from the body read and from `json.loads` propagates unchanged and counts (`[58.0]`) | holds; no test (R-9) |
| 2.1 | Revision 2 tests | holds |
| 2.2 | `_urlparse.py:218` (length), 223 (non-printable), 348-390 (`encode_host`) | holds |
| 2.3 | `encodings/idna.py:193-204` (ASCII fast path: "label empty", "label too long"); probe with the stand-in | holds |
| 2.4 | the same | holds |
| 2.5 | probe: the codec and `ssl` `wrap_bio` accept `source.invalid.` | holds |
| 2.6 | `_host_problem` (`removesuffix(".")`, 253) | holds |
| 2.7 | `_urls.py:169-193` (`idna.decode` only when the host starts with `xn--`; then every label is checked); probe | holds |
| 2.8 | probe `[::1]:8443`, `[::ffff:1.2.3.4]` | holds |
| 2.9 | `encode_host` returns the IPv6 text without its brackets, zone included; `ipaddress` accepts any scope text | **gap: F-5** (a non-ASCII zone) |
| 2.10 | probe with the stand-in: `a%zz.invalid` and `a"b.invalid` give `SourceTransportError`. A real resolver was not run (`unavailable`) | holds |
| 2.11 | probe (F-2(b)) | holds |
| 2.12 | test; probe: a path of 30,000 `Á` is accepted and sent as 180,041 characters (N-10) | holds |
| 2.13 | test | holds |
| 2.14 | round 1 N4 | holds |
| 2.15 | tests (`year-of-5001-digits`, `page-of-5001-digits`) | holds |
| 2.16 | tests (`buyer-lone-surrogate`, `ocid-lone-surrogate`) | holds |
| 2.17 | tests | holds |
| 2.18 | `h11/_abnf.py:83` (`request_target = vchar+`); `httpx` rejects non-printable ASCII and percent-encodes the rest | holds |
| 2.19 | `httpcore/_backends/sync.py` (`settimeout` under maps of `socket.timeout` and `OSError` only); probe | holds |
| 2.20 | `_require_seconds`; tests | holds |
| 2.21 | tests; probe `Decimal(5)` | holds; a non-`str` `base_url` is outside the row (R-8) |
| 2.22 | `_client.py:685` `allow_env_proxies = trust_env and transport is None`; `_utils.py:192-203` reads `other.host` | holds |
| 2.23 | Revision 2 tests | holds |

Result: 42 rows hold and 1 has a gap (2.9, F-5). Row 1.10 holds, with a wrong figure (F-7).

### Beyond § Family check: paths the table does not list

| Path | What was checked | Result |
|---|---|---|
| Text that `h11` rejects and quotes into its exception (`_readers.py:68` "illegal header line: {!r}", `:104` "illegal status line: {!r}", `:183` "illegal chunk header: {!r}", `:168` "malformed chunk footer") | `httpcore` maps it with `str(exc)`, and `httpx` maps it again with `str(exc)` (`map_httpcore_exceptions`). The adapter chains it as `__cause__` (`from attempt.failure`, rules 1 and 3). Probes through `MockBackend` | **F-6** (body bytes and header lines in the chain; also the status line, N-9) |
| `send` before the hook: `_transport_for_url`, the async-stream check, `request_context`, `extract_cookies`, the `INFO` log | read in `_client.py`; probe | no new path. The `INFO` record holds the URL and the status line |
| `send` after the hook: `has_redirect_location`, `auth_flow.send` (default `Auth`), `response.read()` (skipped, `stream=True`) | read | nothing runs that can raise, except `KeyboardInterrupt`-type exceptions |
| `iter_raw`: `StreamConsumed`, `StreamClosed`, async stream | read `_models.py` | test double only |
| `Response.close()` in the hook's `finally` | `BoundSyncStream.close` -> `ResponseStream.close` (not mapped) | R-6. With `MockTransport`, a stream whose `close()` raises an `httpx` error after the status reaches `_send`'s `except httpx.HTTPError`, which drops it, so the outcome is decided from the capture. Test double only, and no test (R-10) |
| `start_tls`: `ssl._encode_hostname` (`idna` codec), "server_hostname cannot ... start with a leading dot" | read; probe with memory BIOs for every accepted host | closed by the label rule |
| `Decimal` | the C `_decimal` comparison with an `int` converts it exactly. Probe under precision 1, every trap on, and a digit limit of 640 | no gap |
| `json.loads` | `ValueError`, `RecursionError` caught; `MemoryError` propagates | no gap |
| `urlsplit` (construction only) | `ValueError` caught (lines 171 and 172); `TypeError` and `AttributeError` for a non-`str` | R-2, R-8 |
| `codecs` | `latin-1` cannot fail; `raw_host` encodes as ASCII and can fail (F-5); `content.decode("utf-8")` is caught | F-5 |
| Hook mutation of the response headers | probe (constraint table above) | isolated from `RawResponse`, from the transport's input and from the next request |
| `_NoCookieJar` beyond extraction | `Cookies.__bool__` iterates an empty jar, so `_merge_cookies` returns `None` and no `Cookie` is set. No `UserWarning` (`-W error` suite, and the probe) | no gap |
| `101 Switching Protocols` without an upgrade, and `1xx` | probe through `h11` and `httpcore` | a transport error with no response for `101`; `103` is skipped (N-8) |

### No regressions against AC8, AC15 and AC12

- AC8: the adapter's own messages stay fixed text plus the operation and an integer
  status. `RawResponse.__repr__` is unchanged (`domain` has no diff). `logging`,
  `print` and `sys.std*` are not used in the adapter (grep exit 1). The only `from`
  clauses are the two `from attempt.failure` of round 1. The new `except` blocks
  (`_library_accepts`, the `url.host` decode, `_send`, the hook) all return,
  `pass`, or store the error, and raise nothing inside the `except`. The
  `JSONDecodeError` and `UnicodeDecodeError` names appear only in a docstring. The
  no-leak test runs over 6 scenarios by 2 operations, and the 37 no-chain cases pass.
  F-6 was there in round 1 as well, so it is not a regression: it is a gap that round
  1 missed.
- AC15: `except` clauses at lines 158, 171, 192, 196, 359, 421, 448 and 556 name
  `httpx.InvalidURL`, `ValueError`, `httpx.HTTPError` or `RecursionError` only. The pacing `try`/`finally`
  (lines 373 to 378) still holds only `self._send(request)`, so every exit after the
  hand-off passes through it: `KeyboardInterrupt`, `SystemExit`, `MemoryError`, a
  synthetic defect, and errors from the hook (tests and probes).
- AC12: `httpx` is imported only in `infrastructure`, and `domain`, `application`, F1,
  `cli.py` and the fixtures are unchanged (AC13 points 9 and 10).

### Lines the tests do not cover (round 2)

Coverage, rerun: `sercop_source.py` has 263 statements, 2 missed (`171-172`). TOTAL is
562 statements, 15 missed, 97% on Windows. Ubuntu CI on `19ab9c3` gives the same 2
adapter misses, and TOTAL 12 missed (98%), because some F1 lines are
platform-specific. The `_send` drop branch (R-10) counts as covered because the
measure is statement coverage, not branch coverage.

| Lines | Branch | Behavior (probe, rerun) | Assessment |
|---|---|---|---|
| 171-172 | `urlsplit` raises `ValueError` | `https://[::1/PLATAFORMA` -> fixed reason, empty chain | meets AC8 and AC10; no test, and mutant m2c survives: R-2 |

Behavior that the spec requires and that no test covers: `MemoryError` (AC15, R-9). The
non-ASCII zone (F-5) and the protocol-error text in the chain (F-6) are findings. They
are not coverage gaps.

### Doc coherence and PR checks

- README, CHANGELOG and `docs/architecture.md` state nothing that the tests do not
  verify (§ AC14 above).
- Specs: § Guidance consulted is corrected (F-4). Stale text remains elsewhere: F-7.
- `tasks.md` records the O2c and O5c counts that this round reproduced (`569`, `386`,
  `458 0`, red `61 failed, 508 passed`, two uncovered lines). Its § Status, O8b,
  § Working state and § Checkpoint describe the pre-commit state (F-7).
- PR checks, rerun on 2026-10-10: `gh pr checks 16` -> `feedback pass 17s`,
  `tests pass 10s`. `gh pr view 16 --json headRefOid,state,statusCheckRollup` ->
  `headRefOid` `19ab9c3e84b86bbd5b134958d9a0ec54b1b73ac7` (the audited HEAD), `state`
  `OPEN`, both checks `COMPLETED` with `SUCCESS`. Run logs, through `gh run view --log`:
  `feedback` (run 38094053231) prints `harny-feedback: 2 of 2 command(s) ran, 0
  skipped.`; `Tests` (run 38094053242) prints `569 passed`. Both runs have `headSha`
  `19ab9c3`.

### Conventions and feedback (round 2)

- `harny-standards`, against `AGENTS.md`: the layer boundaries hold. Raw responses
  are not overwritten: the hook removes `Location` only from the client's own response
  object, and the evidence keeps it. No SERCOP contract is invented. No dependency,
  infrastructure, framework or service was added. No secrets or datasets were added
  (the hosts are `.invalid` or numeric, and the values are labelled SYNTHETIC).
  Verification is reported. No violation. No AI attribution appears in the branch's
  commits or in the changed files (grep exit 1).
- `harny-feedback`: the CI `feedback` job ran 2 of 2 commands on `19ab9c3` and passed.
  `ruff` and `mypy` were rerun here only as AC13 evidence. Whether the per-turn hook
  fired during O5c is `unavailable`, because it leaves no persistent log.

### Findings (round 2)

| Id | Severity | Finding and evidence | Closure condition | Status |
|---|---|---|---|---|
| F-1 to F-4 | (round 1) | rechecked above | met | **Resolved** |
| F-5 | MEDIUM (blocking: unmet binding constraint) | Plan § Binding constraints ("The `ValueError` message names `base_url` and a fixed reason. Its message, `__cause__` and `__context__` never contain the given URL", made binding for the Revision 3 host rules by "with the same no-echo and no-chain rules") and intent AC10 Revision 3 ("raises `ValueError` (with no URL text in its message or chain, as above) when ... the host is an IPv6 literal with a zone identifier"). Reproducer (rerun): `SercopSource(base_url="https://[fe80::1%25é]/PLATAFORMA")`, and `https://[fe80::1%éth0]/PLATAFORMA`. Both raise `UnicodeEncodeError` (a `ValueError`, so the type is in the closed set) with the message `'ascii' codec can't encode character '\xe9' in position 10: ordinal not in range(128)`, `args` `('ascii', 'fe80::1%25é', ...)` and `.object` equal to the host and zone text. With `https://[fe80::1%25synthétic-secret]/PLATAFORMA`, `repr()` shows `fe80::1%25synthétic-secret`. Cause: `_base_url_problem` line 198 reads `url.raw_host` (`self._uri_reference.host.encode("ascii")`) outside any `try`. `urlsplit` (3.13 accepts a scope ID) and `httpx.URL` (`encode_host` keeps the zone text) both accept the URL first, so the zone rule in `_host_problem` is never reached. The current tests would not catch it: `pytest.raises(ValueError)` passes, the cause and context are `None`, and `_assert_base_url_not_echoed` looks only for the whole URL | The architect names the case in § Validation (for example a `REJECTED_BASE_URLS` entry with a non-ASCII zone), with an assertion that the error is exactly `ValueError` with the fixed `base_url ...` message and that no part of the host appears in `str()`, `repr()` or `args`, and corrects § Family check row 2.9. Then the test-writer records red evidence, the executor fixes the code, and the auditor rechecks. This report proposes no code workaround | Open |
| F-6 | MEDIUM (blocking: AC8 not met; spec gap) | Intent AC8: "Nothing leaks response content. Error messages, and `str()` and `repr()` of errors ... contain no body bytes and no header values". The AC8 test `test_no_leak_in_messages_representations_logs_chains_and_output` asserts this for every exception in the chain. Plan § No content: "An `httpx` exception may be chained as `__cause__` of a `SourceTransportError`. It holds no body". With the real transport, `h11` quotes the bytes it rejects into its exception (`_readers.py:68,104,183`), and `httpcore` and `httpx` copy `str(exc)` into each mapped exception. The adapter chains that exception (`_outcome` lines 506 and 517). Reproducers (rerun, real `httpx`, `httpcore` and `h11` over `httpcore.MockBackend`, offline, SYNTHETIC bytes, both operations): (1) a `200` with `Transfer-Encoding: chunked` whose first chunk line is `{"total":3,"page":1,"note":"synthetic-body-marker` + 30,000 `x` + `"}` gives `SourceTransportError` with a partial response of 0 bytes. Its `__cause__` is `httpx.RemoteProtocolError` with a 30,091-character message, `illegal chunk header: bytearray(b'{"total":3,...synthetic-body-marker...')`. The same text is in `httpcore.RemoteProtocolError` and `h11.RemoteProtocolError` further down, and in `traceback.format_exception(error)`. The limit is `httpcore`'s 100 KiB buffer. (2) The header line `Authorization-Synthetic: synthetic-header-marker\x00` gives `SourceTransportError` with no response, and a cause of `illegal header line: bytearray(b'Authorization-Synthetic: synthetic-header-marker\x00')`: the header value, in full. (3) The status line `HTTP/1.1 2000 synthetic-header-marker` puts the status line in the cause in the same way. The test double `httpx.RemoteProtocolError("synthetic cut-off")` does not reproduce these messages, so the suite passes. This was present at `015a72b` and missed in round 1: it is not a regression of round 2 | The architect decides, in a spec revision recorded in `tasks.md`, either (a) to keep AC8 as written and withdraw the plan's permission to chain a library exception into a `SourceTransportError`, with a § Validation case whose injected failure is an `httpx` exception carrying the body or header marker in its message, the form the real `h11` path produces, plus red evidence; or (b) to narrow AC8 to the adapter's own messages and representations, and record in AC8, plan § No content and § Consumers (F4) that a chained library exception can quote malformed protocol bytes (header lines, the status line, and up to about 100 KiB of body before a line break), so F4 must not log or store the chain. Then the auditor rechecks. This report proposes no code workaround | Open |
| F-7 | LOW | Spec consistency. Intent § Constraints: "This reading needs the human's approval (Open questions)", but Revision 2 was approved. Plan § Risks, the Revision 2 status row and the Revision 3 `MemoryError` row: "The human decides at approval", but both were decided. Plan § Family check row 1.10: "the header block (16 KiB)", but `httpcore` sets 100 KiB (`_sync/http11.py:45`). `tasks.md` § Status ("uncommitted"), O8b ("PR #16 ... **unavailable** for this state ... until the human commits and pushes"), § Working state and § Checkpoint ("at HEAD `83c0b11` ... uncommitted"): the work was committed and pushed as `19ab9c3`, and the checks pass. Smaller point: the plan's § Validation still describes the two O2c deviations that the human confirmed at gate 2 in their old form (N-11) | The architect updates the intent and plan lines, or marks them as history. Whoever owns `tasks.md` records the commit and the PR checks under O8b or O9b. Checked by reading | Open |

### Reservations (round 2)

- R-2 (carried): lines 171 and 172 have no test, and m2c (`urlsplit`'s `ValueError`
  chained) passes the whole no-chain test. The behavior is correct today. A
  `REJECTED_BASE_URLS` entry such as `https://[::1/PLATAFORMA` would cover both lines
  and anchor AC8 there.
- R-6 (carried, accepted risk): `ResponseStream.close()` is not mapped.
- R-7: with the real transport and logging at `DEBUG`, `httpcore.http11` writes
  response header values. The probe shows the marker in a `httpcore.http11` `DEBUG`
  record. AC8's "no log record emitted during a call" holds only while that logger
  stays above `DEBUG`. Plan § Risks and § Consumers (F4) already accept this. No spec
  change.
- R-8: `SercopSource(base_url=123)` raises `AttributeError` (`urlsplit`), not
  `ValueError`. `bytes` and `None` give the fixed `ValueError`. The parameter is typed
  `str` and `mypy` rejects the call. No rule names the type of `base_url`, while
  Revision 3 does name it for the numeric options. The architect may add one.
- R-9: `MemoryError` (AC15 Revision 3) has no test. The probe shows the specified
  behavior: the same object, and pacing counted.
- R-10: the "status captured" branch of `_send`'s `except httpx.HTTPError` is reachable
  only through a test double whose stream `close()` raises an `httpx` error. It drops
  the error, so the outcome is decided from the capture. No test covers it, and it is
  harmless.

### Notes (round 2)

- N-8: through `h11` and `httpcore`, a `101` without an upgrade becomes a transport
  error with no response, and an informational `103` before a `200` is skipped. Both
  are library behavior and within AC6.
- N-9: the reason phrase reaches the `httpx` `INFO` record, and a malformed status line
  reaches the chained exception (F-6 reproducer 3). The reason phrase is neither a
  header value nor body bytes, and row 1.3 covers it.
- N-10: `httpx` checks `MAX_URL_LENGTH` before percent-encoding, so a base path of
  30,000 `Á` is accepted and sent as a URL of 180,041 characters. This is not a
  failure.
- N-11: two O2c choices differ from the § Validation wording. One is a separate test,
  `test_invalid_input_too_long_year_on_a_long_base_url_raises_value_error`, instead of
  a case of the `make_rig` test. The other puts the nesting inside an otherwise valid
  body. Both are recorded in `tasks.md` O2c and confirmed by the human at gate 2, and
  both are compliant alternatives.
- N-12: `tasks.md` O9b is left for the human or the orchestrator to fill with this
  verdict. The auditor writes only `audit.md`.

### Commands run in round 2 (all rerun, Windows, Python 3.13.9, `uv`, repository root)

| Command | Result |
|---|---|
| `git status --short`; `git rev-parse HEAD` | empty; `19ab9c3e84b86bbd5b134958d9a0ec54b1b73ac7` |
| `git diff --stat 015a72b HEAD`; `git diff --numstat 015a72b -- tests`; `git diff --stat 015a72b HEAD -- src` | 9 files; `458 0 tests/unit/test_sercop_source.py`; only `infrastructure/sercop_source.py` (150+/42-) |
| `uv sync --locked`; `uv lock --check` | `Checked 22 packages`; `Resolved 22 packages`; exit 0 |
| `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing` | `569 passed`; TOTAL 562/15/97%; `sercop_source.py` 263/2 (171-172) |
| `uv run pytest tests -W error` | `569 passed` |
| `uv run pytest tests/unit/test_sercop_source.py -q` | `386 passed` |
| focused rows: `search_success or query` / `record_success` / `raw_response or store_shape or cookie` / `out_of_range or no_results` / `status_error` / `transport` / `incomplete` / `no_leak` (both files) / `pacing` / `timeout or accept_encoding or invalid` (both files) / `documented_boundaries or non_ascii_base_path` / `no_network` / `layer or satisfies_port` (`tests/unit`) / the AC15 `-k` | 13 / 4 / 20 / 4 / 30 / 31 / 53 / 54 / 50 / 155 / 18 / 2 / 9 / 113, all passed |
| `uv run pytest --collect-only -q tests` and the adapter file | 569; 386 |
| `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy .` | `All checks passed!`; `76 files already formatted`; `Success: no issues found in 20 source files` |
| `uv run node .sdd/doctor/run-doctor.mjs`; `uv run ec-procurement-quality --version` | `31 ok, 0 skipped, 0 warned, 0 failed`; `ec-procurement-quality 0.1.0` |
| `git diff main -- pyproject.toml`; `git diff main --stat` (F1, `cli.py`, `__init__.py`); `git log --oneline -- tests/fixtures/sercop`; `git diff --check`; `git diff main --check` | only `httpx`; empty; `74b785d`; clean; clean |
| `git grep` for the real host in tests, for the default URL in `src`, for `except Exception`/`except BaseException`, for `httpx` imports, for logging and printing, for `from` clauses, for attribution | exit 1; 1 match (`:50`); exit 1; `sercop_source.py:34` and the test file; exit 1; two `from attempt.failure`; exit 1 |
| Scratch mutants m1, m2, m2b, m2c (`PYTHONPATH=<copy>/src`, imported path confirmed), `-k no_leak_rejections` | 2 failed / 2 failed / 2 failed / 37 passed |
| The current tests against the `015a72b` adapter (scratch copy) | `61 failed, 508 passed` |
| Scratch probes `r2/probe_r2.py` (F-1, R-3, construction, the `idna` and `ssl` checks, the real transport with the `getaddrinfo` stand-in), `r2/probe_r2b.py` and an inline probe (the real `httpx`, `httpcore` and `h11` over `MockBackend`: leaks, statuses, `Location`, cookies, the hook mutation), inline probes for `MemoryError` and F-5 | results quoted above; guard attempts 0 |
| `gh pr checks 16`; `gh pr view 16 --json ...`; `gh run view 38094053231 --log`; `gh run view 38094053242 --log` | both checks `pass` on `19ab9c3`; `2 of 2 command(s) ran, 0 skipped`; `569 passed` |

### Not verified in round 2, and why

- Real name resolution and real TLS handshakes were not run (no network by brief). The
  `idna` step of `getaddrinfo` was stood in for, and `ssl` was exercised with memory
  BIOs only. Row 2.10's `gaierror` for the hosts `httpx` keeps is therefore
  `unavailable` beyond the stand-in.
- F-6 was reproduced with `httpcore.MockBackend`, which replaces only the socket. A live
  server sending malformed framing was not used.
- Whether the per-turn Stop hook fired during O2c and O5c is `unavailable` (no
  persistent log). CI `feedback` ran 2 of 2 commands on `19ab9c3`.
- The CI coverage figure (TOTAL 12 missed) differs from Windows (15 missed) only in F1
  lines. This was read from the log; the cause per line was not investigated.

## Audit log

| Round | Date | Verdict | Notes |
|---|---|---|---|
| 1 | 2026-10-10 | REJECTED | Reviewed `015a72b` plus the uncommitted doc and `tasks.md` edits. 453 passed, 97% coverage. AC1 to AC8 and AC11 to AC15 PASS; AC9 and AC10 PARTIAL. Blocking: F-1 (MEDIUM, a zero-padded `Remaining` of more than 4,300 digits is ignored) and F-2 (MEDIUM, spec gap: base URLs that pass construction fail on every call). Non-blocking: F-3 and F-4 (LOW). Reservations R-1 to R-6. `InvalidURL` rule: met by the code, not anchored by any test (mutants m1 and m2 pass). Tier Results: unit PASS, mypy PASS, command PASS, manual AC14 PASS, manual AC15 PARTIAL. CI on the audited state `unavailable`. Next role: architect. |
| 2 | 2026-10-10 | REJECTED (current) | Reviewed `19ab9c3` (intent and plan Revision 3; O2c, O5c, O7b, O8b), with a clean tree. 569 passed locally and in CI; adapter coverage 99% (171-172 missed). Resolved: F-1, F-2, F-3, F-4, R-1 (mutants m1 and m2 now fail the no-chain test), R-3, R-4, R-5. AC1 to AC7, AC9 and AC11 to AC14 PASS; AC8, AC10 and AC15 PARTIAL. § Family check: 42 of 43 rows hold, and row 2.9 has a gap. Blocking: F-5 (MEDIUM, a non-ASCII IPv6 zone raises a raw `UnicodeEncodeError` with the host text instead of the fixed reason) and F-6 (MEDIUM, spec gap: the chained `httpx` exception quotes body bytes or header lines that `h11` rejected). Non-blocking: F-7 (LOW, stale spec and `tasks.md` text). Reservations R-2, R-6 to R-10. Tier Results: unit PARTIAL, mypy PASS, command PASS, manual AC14 PASS, manual AC15 PARTIAL. PR #16 `feedback` and `tests` pass on `19ab9c3`. Next role: architect (F-6 decision; F-5 case in § Validation; F-7). |
