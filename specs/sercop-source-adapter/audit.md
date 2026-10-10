# Audit: SERCOP source adapter (F2)

## Final verdict

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

| Tier | Tests found | ACs verified | Setup matches § Validation | Ran | Status | Finding |
|---|---|---|---|---|---|---|
| unit (pytest) | 316 new (`test_sercop_source.py` 270, `test_source_response.py` 45, `test_layers.py` +1) and the 137 baseline tests, all in `tests/unit/` | AC1 to AC12, AC15 | Yes: only `uv sync --locked`; no dev dependency, `conftest.py`, config file or script added (`pyproject.toml` changes only the runtime `httpx` line; `uv.lock` +72/-0; `.github`, `.sdd`, `.claude` and `.gitignore` unchanged against `main`) | rerun (Windows, Python 3.13.9). Ubuntu CI on the audited state: `unavailable` | PASS | none at tier level; F-1 and F-2 are code or spec defects, R-1 |
| unit (mypy, AC12) | the annotated `satisfies_port` assignment | AC12 | Yes | rerun | PASS | none |
| command (AC13) | the 13 points above | AC13 | Yes | rerun (point 13 partly reused) | PASS | R-4 |
| manual (AC14) | inspection plus the two `git grep` commands | AC14 | Yes (none needed) | rerun | PASS | F-3 (LOW) |
| manual (AC15) | the closed-set justification against `.venv` | AC15 | Yes | rerun | PARTIAL | F-2 |

No test exists at a tier that § Validation does not name.

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

## Audit log

| Round | Date | Verdict | Notes |
|---|---|---|---|
| 1 | 2026-10-10 | REJECTED | Reviewed `015a72b` plus the uncommitted doc and `tasks.md` edits. 453 passed, 97% coverage. AC1 to AC8 and AC11 to AC15 PASS; AC9 and AC10 PARTIAL. Blocking: F-1 (MEDIUM, a zero-padded `Remaining` of more than 4,300 digits is ignored) and F-2 (MEDIUM, spec gap: base URLs that pass construction fail on every call). Non-blocking: F-3 and F-4 (LOW). Reservations R-1 to R-6. `InvalidURL` rule: met by the code, not anchored by any test (mutants m1 and m2 pass). Tier Results: unit PASS, mypy PASS, command PASS, manual AC14 PASS, manual AC15 PARTIAL. CI on the audited state `unavailable`. Next role: architect. |
