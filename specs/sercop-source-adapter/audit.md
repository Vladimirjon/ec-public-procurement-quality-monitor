# Audit: SERCOP source adapter (F2)

Current round: **round 4** (2026-10-12, intent Revision 5, `1cd2f1e` plus the
uncommitted O2e tests and O5e code, at HEAD `dc78500`). Its full report is § Round 4,
after § Round 3. Rounds 1 to 3 are kept below as written, as history. Three things
changed outside § Round 4: this header and § Final verdict (the round 3 verdict moved
below, marked superseded), the Tier Results table gained round 4 columns, because the
procedure keeps a single Tier Results table, and the round 3 row of the audit log is
marked superseded.

## Final verdict

APPROVED WITH RESERVATIONS (round 4, current)

**Summary**: Revision 5 closes every round 3 item, each rerun on the exact round 3
inputs. F-8: inside the caller's `except KeyError`, `finally` and `__exit__`, and in a
retry inside `except SourceError as first`, the error has no `__cause__`, its
`__context__` is the caller's own exception and is not hidden, as I2 now says. F-9: the
message names the nearest class that `httpx` exports (`Falloé` -> `ReadError`,
`Bad\nName` -> `RemoteProtocolError`, the marker -> `ConnectError`, 200 `X` ->
`ReadTimeout`). F-10 and R-11 are closed by reading. All 961 tests pass (rerun, also with
`-W error`), the 890 tests of `1cd2f1e` lost no line, and the O2e red (`44 failed, 917
passed` against `1cd2f1e`) is reproduced. All 25 rows of § Statement check, the Revision
5 rows of § Exit check, and I1 to I4 against all 20 raise sites hold. The adversarial
family check found no new gap. Two LOW stale-text findings remain, neither blocking, and
the PR #16 checks have not run on the reviewed state.

**Critical Issues** (must fix before merge):
- none.

**Warnings** (should fix, not blocking):
- F-11 (LOW): the adapter's module docstring (`sercop_source.py` lines 14 to 17) still
  says that every exception the adapter raises "has no `__cause__` and no
  `__context__`", the Revision 4 wording that AC8 Revision 5 restated (F-8). O5e could
  not change it, because O5e listed the only lines it could touch. **Resolved** (round 4
  addendum).
- F-12 (LOW): stale bookkeeping in `tasks.md` § Status. **Resolved** (round 4 addendum). Line 12 says "The Revision 5
  changes to the three spec files and this file are uncommitted", but `dc78500` holds
  them. Line 11 ("Next: the human's approval") is marked superseded only by a later
  bullet (line 14). The "Previous working state (architect, Revision 5 draft)" entry has
  no note that `dc78500` then committed that state, unlike its predecessors.
- New in the round 4 addendum, both not blocking: F-13 (LOW, the docstring's
  "starts with the operation or the parameter" omits the closed-adapter message) and F-14
  (LOW, `tasks.md` R-12 row cites "§ Working state step 3"; it is step 2). **Both
  resolved** (round 4 second addendum).
- New in the round 4 second addendum, open and not blocking: F-15 (LOW, the `tasks.md`
  R-12 row omits O5g from what the human commits) and F-16 (LOW, the O7f record says no
  other record cites a numbered step, but the F-10 record does). Note N-22 (the AC15
  sentence and the § Risks row give one caller-code path as if it were the only one).

**Recommendations** (nice to have):
- R-12 (new reservation): PR #16 `feedback` and `Tests` are `unavailable` for the
  reviewed state. They pass on `dc78500`, but that commit holds neither the O2e tests nor
  the O5e code (its `Tests` run shows `890 passed`). After the human commits and pushes,
  confirm both checks on the new head: `Tests` with `961 passed`, and `feedback` with
  `2 of 2 command(s) ran`. Do this before gate 3.
- N-17: the D-1 drop covers every way a read can end. Its outcome is the same as the
  plan's flag form (mutant m16 passes all 961 tests), but the `_send` drop branch no
  longer has any path to it. The architect may update the § Exit check K15 wording at
  the next revision. **Closed** (round 4 addendum). N-21 is new: "no path" holds only for
  `httpx`'s own code. **N-21 closed** (round 4 second addendum); N-22 is its residue.
- R-6 and R-7 stay accepted risks.

### Round 3 final verdict (superseded by round 4)

REJECTED (round 3)

**Summary**: Revision 4 closes every round 2 item, each rerun on the exact round 2
inputs. F-5, F-6, F-7, R-2, R-8, R-9 and R-10 are resolved. On F-6, sixteen malformed
framings were sent through the real `httpx`, `httpcore` and `h11` stack with no socket,
and none leaves anything chained or any marker in the error. All 890 tests pass,
locally and in CI on `1cd2f1e`, and the 569 tests of `19ab9c3` lost no line. The four
mutants of round 2 (m1, m2, m2b, m2c) and eight new ones each fail tests. All 39 rows
of § Exit check hold against the installed packages. Two inputs still break the letter
of the new § Output invariant, which AC8 says holds "whatever the input". Neither one
leaks response content. (F-8) A call made while the caller is handling an exception
raises an error whose `__context__` is the caller's exception. Python sets that link
itself, so no implementation can meet I2 as written. (F-9) An `httpx.HTTPError`
subclass raised by an injected transport puts its class name verbatim into the
message, which can then be non-ASCII or hold a marker (I3, I4). Only a test double can
do this. Both are spec gaps for the architect. The rule that an unmet binding
constraint blocks at any severity makes them blocking.

**Critical Issues** (must fix before merge):
- F-8 (LOW, blocking: AC8 Revision 4 "No exception the adapter raises has a
  `__cause__` or a `__context__`, whatever its type"; plan § Output invariant I2;
  AC10 Revision 4 "nothing is chained"; spec gap). Input: call
  `source.search_page(...)` inside the caller's own `except KeyError:` block. The
  `SourceStatusError` it raises has `__context__` set to the `KeyError`. The same
  happens for a construction `ValueError`. F4's natural retry inside an
  `except SourceError` block hits this. The context is the caller's own exception,
  and its text is fixed, so nothing leaks. Route: the architect qualifies I2 (for
  example "nothing chained by the adapter; a context that Python sets from an
  exception the caller is handling belongs to the caller"). No code change is
  implied.
- F-9 (LOW, blocking: plan § Output invariant I3 "printable ASCII" and I4, which the
  plan says hold "whatever the input"; plan § Outcome mapping Revision 4 prescribes
  `type(failure).__name__`; § Exit check K11 maps an injected transport's
  `httpx.HTTPError`; spec gap). Input: a `MockTransport` whose handler raises an
  instance of `type("Falloé", (httpx.ReadError,), {})`, or of a class whose name holds
  `synthetic-leak-marker`. The result is `SourceTransportError("search_ocds: the request
  failed before a response arrived (Falloé)")`, which is not ASCII, or a message that
  holds the marker. The real transport only raises `httpx`'s own ASCII class names.
  Route: the architect either classifies this as a test-double case (as row 1.2 and
  K19 already do for a status that cannot be written) or requires a name that the
  library defines. No code workaround is proposed here.

**Warnings** (should fix, not blocking):
- F-10 (LOW): stale text of the F-7 kind. Intent § Revision history (Revision 4) says
  "the header now reads `Approval: Pending`", but the header records the approval.
  `tasks.md` § Status, O8c, § Working state and § Checkpoint describe the O2d tests
  and the O5d code as uncommitted at `eb93264`, with the PR checks unavailable. Both
  were committed and pushed as `1cd2f1e`, and both checks pass on it.

**Recommendations** (nice to have):
- R-11: one `SercopSource` instance keeps the capture and the pacing state of the
  request in progress. Two threads that share an instance can mix the evidence of
  their calls, with no error raised. Concurrency is out of scope (intent § Scope), but
  no spec line or docstring says that an instance must not be shared. The architect
  may add this to plan § Consumers (F4).
- R-6 and R-7 stay accepted risks.

### Round 2 final verdict (superseded by round 3)

REJECTED (round 2)

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
unchanged. The next four columns hold round 2's results (Revision 3, `19ab9c3`). Round 3
added the next four (Revision 4, `1cd2f1e`), and round 4 the last four (Revision 5,
`1cd2f1e` plus the uncommitted O2e tests and O5e code).

| Tier | Tests found | ACs verified | Setup matches § Validation | Ran | Status | Finding | Round 2: tests found | Round 2: ran | Round 2: status | Round 2: finding | Round 3: tests found | Round 3: ran | Round 3: status | Round 3: finding | Round 4: tests found | Round 4: ran | Round 4: status | Round 4: finding |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| unit (pytest) | 316 new (`test_sercop_source.py` 270, `test_source_response.py` 45, `test_layers.py` +1) and the 137 baseline tests, all in `tests/unit/` | AC1 to AC12, AC15 | Yes: only `uv sync --locked`; no dev dependency, `conftest.py`, config file or script added (`pyproject.toml` changes only the runtime `httpx` line; `uv.lock` +72/-0; `.github`, `.sdd`, `.claude` and `.gitignore` unchanged against `main`) | rerun (Windows, Python 3.13.9). Ubuntu CI on the audited state: `unavailable` | PASS | none at tier level; F-1 and F-2 are code or spec defects, R-1 | 569 = 137 baseline + 432 F2 (`test_sercop_source.py` 386, of which 116 are O2c; `test_source_response.py` 45; `test_layers.py` +1). Setup unchanged since `015a72b`: `pyproject.toml`, `uv.lock`, `.github`, `.sdd`, `.claude`, `.gitignore` show no diff | rerun (Windows, Python 3.13.9): `569 passed`; Ubuntu CI on `19ab9c3`: `569 passed` (reused from the run log, read in this round) | PARTIAL | F-6: the AC8 tests use a synthetic `httpx.RemoteProtocolError("synthetic cut-off")` and do not cover the messages that the real `h11` path produces; R-2 (m2c survives) | 890 = 137 baseline + 753 F2 (`test_sercop_source.py` 707, of which 321 are O2d; `test_source_response.py` 45; `test_layers.py` +1). Every named O2d group exists with the § Validation counts (29, 32, 144, 34, 58, 6, plus 18 list runs). Setup unchanged since `19ab9c3`: `pyproject.toml`, `uv.lock`, `.github`, `.sdd`, `.claude` and `.gitignore` show no diff, and no test imports `httpcore` | rerun (Windows, Python 3.13.9): `890 passed`, and `890 passed` with `-W error`; Ubuntu CI on `1cd2f1e`: `890 passed` (read from the run log) | PASS | none at tier level. F-8 and F-9 are spec gaps, and no test can be named for them before the architect decides | 961 = 137 baseline + 824 F2 (`test_sercop_source.py` 778, of which 71 are O2e: T5 25, T6 28, T7 8, the failing-close test 8 and the chaining test 2, as § Validation counts them; `test_source_response.py` 45; `test_layers.py` +1). Setup unchanged since `1cd2f1e`: `pyproject.toml`, `uv.lock`, `.github`, `.sdd`, `.claude` and `.gitignore` show no diff. No test imports `httpcore` | rerun (Windows, Python 3.13.9): `961 passed`, and `961 passed` with `-W error`. Ubuntu CI on the reviewed state: `unavailable` (not pushed; R-12) | PASS | none at tier level |
| unit (mypy, AC12) | the annotated `satisfies_port` assignment | AC12 | Yes | rerun | PASS | none | unchanged | rerun: `Success: no issues found in 20 source files` | PASS | none | unchanged | rerun: `Success: no issues found in 20 source files` | PASS | none | unchanged | rerun: `Success: no issues found in 20 source files` | PASS | none |
| command (AC13) | the 13 points above | AC13 | Yes | rerun (point 13 partly reused) | PASS | R-4 | the 13 points, plus the Revision 3 `git diff --numstat 015a72b -- tests` | rerun (all 13) | PASS | R-4 closed | the 13 points, plus `git diff --numstat 19ab9c3 -- tests` | rerun (all 13) | PASS | none | the 13 points, plus `git diff --numstat 1cd2f1e -- tests` and the O8d list of unchanged paths | rerun (all 13) | PASS | none (N-19 on the `015a72b` count) |
| manual (AC14) | inspection plus the two `git grep` commands | AC14 | Yes (none needed) | rerun | PASS | F-3 (LOW) | the same | rerun | PASS | F-3 closed | the same | rerun | PASS | none | the same | rerun | PASS | none |
| manual (AC15) | the closed-set justification against `.venv` | AC15 | Yes | rerun | PARTIAL | F-2 | the closed-set justification and the 43 rows of § Family check against `.venv` | rerun | PARTIAL | F-5 (row 2.9) | the 39 rows of § Exit check against `.venv` and the code, and § Output invariant against every `raise` | rerun | PARTIAL | the 39 rows hold. The Output invariant does not hold for two inputs: F-8 (I2) and F-9 (I3, I4) | the 25 rows of § Statement check, the Revision 5 rows of § Exit check, the one-caller docstring, and § Output invariant against every `raise` | rerun | PASS | none. N-17 and N-18 are notes |

No test exists at a tier that § Validation does not name (rounds 1 to 4).

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

## Round 3

### Scope of round 3

Round 3, 2026-10-10. Auditor: `sdd-auditor` (harny-audit). Reviewed state: branch
`feat/sercop-source-adapter` at `1cd2f1e`, base `main` `fff0f2d`. The commit is pushed,
and `git status --short` is empty. Changes since round 2 (`19ab9c3`):
- intent and plan Revision 4, approved and committed as `eb93264`;
- 321 new tests (O2d, gate 2 approved);
- `infrastructure/sercop_source.py` (O5d, 77 lines added and 12 deleted);
- `tasks.md`.

`git diff --stat 19ab9c3 HEAD` touches only the four spec files, the adapter and
`tests/unit/test_sercop_source.py`. These show no diff against `19ab9c3`: `domain`,
`application`, `interfaces`, F1, the fixtures, `docs/` (ADRs included), `README.md`,
`CHANGELOG.md`, `pyproject.toml`, `uv.lock`, `.github`, `.sdd`, `.claude`,
`.gitignore` and the other six test files.

Read in full for this round:
- `intent.md` and `execution-plan.md` Revision 4 (with the new § Output invariant and
  § Exit check), `tasks.md`, and rounds 1 and 2 of this report;
- the whole adapter at `1cd2f1e`, and the whole source and test diff `19ab9c3..HEAD`.

Library sources read in `.venv/Lib/site-packages/`:
- `httpx/_client.py`: `BaseClient.__init__`, `build_request`, `_merge_url`,
  `_merge_cookies`, `_merge_headers`, `_build_request_auth`, `Client.__init__`,
  `_init_transport`, `_transport_for_url`, `send`, `_send_handling_auth`,
  `_send_handling_redirects`, `_send_single_request`, `close` and `__enter__`.
- `httpx/_models.py`: `Headers.encoding`, `__contains__` and `__delitem__`;
  `Request.__init__` and `_prepare`; `Response.__init__`, `http_version`,
  `reason_phrase`, `iter_raw` and `close`; `Cookies.__init__`, `extract_cookies` and
  `__bool__`; `_CookieCompatRequest`.
- `httpx/_urls.py` (`host`, `raw_host`, `port`, `netloc`), `httpx/_urlparse.py`
  (`MAX_URL_LENGTH`, the non-printable check, `encode_host`) and `httpx/_exceptions.py`
  (`request_context`).
- `httpx/_transports/default.py` (`map_httpcore_exceptions`, `ResponseStream`,
  `HTTPTransport.__init__` and `handle_request`), `base.py` and `mock.py`.
- `httpcore/_backends/mock.py`, `httpcore/_sync/http11.py:45`, `httpcore/_trace.py` and
  `h11/_readers.py`.

`grep -rn "def __del__"` finds none in `httpx`, `httpcore` or `h11`.

No network access was made to SERCOP or to any resolver. Probes ran in the session
scratchpad under `r3/`, outside the repository, with the `.venv` interpreter run with
`-I`. They used `httpx.MockTransport`, and `httpcore.MockBackend` under a real
`httpx.HTTPTransport`. A guard on `socket.socket.connect`, `connect_ex`,
`create_connection` and `getaddrinfo` recorded 0 attempts in every probe. The only
network access was to GitHub, through `gh`, to read the PR #16 checks and run logs.

### Round 2 findings and reservations, rechecked

| Item | Exact round 2 input, rerun now | Result on `1cd2f1e` | Status |
|---|---|---|---|
| F-5 (AC10) | `https://[fe80::1%25é]/PLATAFORMA`; `https://[fe80::1%éth0]/PLATAFORMA`; `https://[::1%25é]:8443/PLATAFORMA`; zones holding U+0663 and U+200D (the latter with and without a port); `https://[fe80::1%25synthétic-secret]/PLATAFORMA` | Each raises exactly `ValueError("base_url must not hold an IPv6 zone identifier")`: `args == (str(error),)`, printable ASCII, `__cause__` and `__context__` `None`, and no host or zone text in `str`, `repr`, `args` or the formatted traceback (probe, rerun). Further zone forms give the same reason: ASCII, an empty `%25`, a lone surrogate, an IPv4-mapped literal and a 64-character zone. `[fe80::1%]` and `[fe80::1%25%C3%A9]` give the `urlsplit` reason. Tests pass: the 4 new zone entries of `REJECTED_BASE_URLS`, in the 4 tests that read the list (U+200D verified by code point in the file), and the 6 zone cases of T2 (é, U+0663 and U+200D in both zone templates). Against the `19ab9c3` adapter, those 10 fail (rerun). Mutant m5, which switches the zone rule off, fails 18 tests | **Resolved** |
| F-6 (AC8) | Through the real `httpx`, `httpcore` and `h11` over `httpcore.MockBackend`, both operations: a chunked `200` whose first chunk line is `{"total":3,"page":1,"note":"synthetic-body-marker` + 30,000 `x`; the header line `Authorization-Synthetic: synthetic-header-marker\x00`; the status line `HTTP/1.1 2000 synthetic-header-marker`. Also 13 other framings: a bad `Content-Length`, conflicting `Content-Length`, an unsupported `Transfer-Encoding`, an invalid header name, a continuation line first, a malformed chunk footer, a bad trailer, a body cut off before its `Content-Length`, a header block over 100 KiB, status `099`, a `101` without an upgrade, no bytes at all, and status `600` | Each of the 15 library failures ends in `SourceTransportError` with a chain of length 1 (no cause, no context). Its message names `RemoteProtocolError` and takes nothing else from the library. In all 16 framings, neither marker appears in `str`, `repr`, `args`, the formatted traceback, the response's `repr` or `str`, or any log record outside `httpcore`. Cut-off bodies keep their bytes (5 and 31). `600` gives rule 2, and a valid `429` the status error. T4 (58 cases) passes, and its 38 failure cases fail against `19ab9c3` (rerun). Mutants: m3 (rule 1 chained again) fails 26 tests, m4 (the library's text added to the rule 3 message) 12, and m8 (a base-class name in the message) 38. `git grep -n -e ") from " -e "raise .* from "` on the adapter -> exit 1 | **Resolved** |
| F-7 | the five places that round 2 named | Intent § Constraints records the Revision 2 approval. Plan § Risks records both acceptances. Plan row 1.10 gives 100 KiB, and `httpcore/_sync/http11.py:45` confirms it. `tasks.md` § Status, the O8b record, O9b and § Checkpoint record `19ab9c3` as committed and pushed. Plan § Validation AC7 and AC10 describe the two N-11 forms | **Resolved** (new stale text of the same kind is F-10) |
| R-2 | `https://[::1/PLATAFORMA`, `https://[zz]/PLATAFORMA` | The fixed `urlsplit` reason, with an empty chain. Both are `REJECTED_BASE_URLS` entries, so 4 tests read them. Mutant m2c now fails 2 of the 43 no-chain cases (`base-url-ipv6-unclosed-bracket`, `base-url-ipv6-invalid-literal`) and 38 tests of the suite. The branch is covered | **Resolved** |
| R-8 (extended) | `base_url` `123`, plus the extension | `base_url` `123`, `1.5`, `None`, `bytes`, `bytearray`, a list or `object()` -> `ValueError("base_url must be a string")`. `transport` `5`, `"mock"` or `httpx.AsyncHTTPTransport()` -> `ValueError("transport must be None or an httpx.BaseTransport")`. `now`, `monotonic` or `sleep` `5` -> `ValueError("<name> must be callable")`. Each is exactly `ValueError`, with an empty chain (probe). The 11 type cases of `INVALID_OPTION_CASES` pass. Mutant m7 (no transport rule) fails 2 | **Resolved** |
| R-9 (AC15) | `MemoryError` before the status, and during a `429` body | The same object both times, and the next call waits `[3.0]` and `[58.0]` (probe). The 2 `UNMAPPED_EXCEPTION_CASES` and 4 propagation tests pass | **Resolved** |
| R-10 (AC15) | `close()` failing after a complete body and after a cut | A complete body whose `close()` raises `ReadError` gives `SourceTransportError(... (ReadError))` with all 40 bytes. A cut (`ReadError`) followed by a `close()` that raises `CloseError` gives `(ReadError)` with the 1 byte; the `CloseError` is neither raised nor named. Nothing is chained. Pacing is `[3.0]`, or `[58.0]` with `Remaining: 5` (probe). The `close-after-a-complete-body` and `close-after-cut` cases pass for both operations. Mutant m9 (the later failure escapes `_send`) fails 2. Also by probe: a `close()` raising `KeyboardInterrupt` after a complete body propagates and counts (`[58.0]`). One raising `OSError` (the R-6 shape) or `httpx.InvalidURL` propagates unchanged, as K15 says | **Resolved** |
| R-6 | `ResponseStream.close()` not mapped | Unchanged (`_transports/default.py:130-132`) | Open (accepted risk) |
| R-7 | `httpcore` `DEBUG` trace | AC8 Revision 4 now states it. Not re-probed in this round | Open (accepted risk) |

### AC results (intent Revision 4)

| AC | Status | Evidence (all rerun) |
|---|---|---|
| AC1 | PASS | `-k "search_success or query"` -> `13 passed`. `git grep "datosabiertos.compraspublicas.gob.ec/PLATAFORMA" -- src` -> 1 match, `sercop_source.py:57` |
| AC2 | PASS | `-k record_success` -> `4 passed` |
| AC3 | PASS | `-k "raw_response or store_shape or cookie"` -> `20 passed`. Whole suite with `-W error` -> `890 passed` |
| AC4 | PASS | `-k "out_of_range or no_results"` -> `4 passed` |
| AC5 | PASS | `-k status_error` -> `30 passed`. The T4 status cases (`301` to `308` with `Location: http://xn--/<marker>`) pass for both operations |
| AC6 | PASS | `-k transport` -> `37 passed`. This includes 6 Revision 4 ids that hold the token, as `tasks.md` O2d explains. `h11` probe: `099`, `101` and cut-off bodies (above) |
| AC7 | PASS | `-k incomplete` -> `53 passed` |
| AC8 | **PARTIAL** | `-k no_leak` over both files -> `296 passed`; `-k invariant` -> `236 passed`. F-6 is resolved (above). **F-8**: I2 does not hold for a call made while the caller is handling an exception. **F-9**: I3 and I4 do not hold for a class name that an injected transport chooses |
| AC9 | PASS | `-k pacing` -> `52 passed`, including the two `MemoryError` cases |
| AC10 | PASS | `-k "timeout or accept_encoding or invalid"` over both files -> `239 passed`; `-k "documented_boundaries or non_ascii_base_path"` -> `18 passed`; `-k "exactly_value_error or invariant"` -> `297 passed`. F-5, R-2 and R-8 are resolved (above). Call input: `"\ud800"`, `"\udfff"`, `10**5000` and `10**4300` give the adapter's own `ValueError` naming the parameter (T3 and the fuzz below). AC10's "nothing is chained" shares the wording of F-8, which is filed once, under AC8 |
| AC11 | PASS | `-k no_network` -> `2 passed`. `git grep -n -i --untracked -e datosabiertos -e compraspublicas -- tests` -> exit 1. `git grep -c "source.invalid" -- tests/unit/test_sercop_source.py` -> 43 |
| AC12 | PASS | `tests/unit -k "layer or satisfies_port"` -> `9 passed`; `uv run mypy .` -> `Success: no issues found in 20 source files`. In `src`, `httpx` is imported only at `infrastructure/sercop_source.py:41`. `domain` and `application` show no diff against `19ab9c3` |
| AC13 | PASS | the 13 points below |
| AC14 | PASS | § AC14 below. Revision 4 changes no doc, and the docs claim nothing that Revision 4 changes |
| AC15 | PASS | The AC15 `-k` -> `420 passed`. `git grep` finds no `except Exception` or `except BaseException`, and no `raise ... from`. `KeyboardInterrupt`, `SystemExit` and `MemoryError` propagate as the same object, and the attempt counts (tests, probe). All 39 rows of § Exit check hold (below). F-9 concerns the text of a message, not the closed set of types |

### AC13, point by point (round 3)

| # | Point | Command | Result (all rerun) |
|---|---|---|---|
| 1 | Every test passes | `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing` | `890 passed`; TOTAL 590 statements, 14 missed, 98%; `sercop_source.py` 291 statements, 1 missed (547) |
| 2 | `ruff check` | `uv run ruff check .` | `All checks passed!` |
| 3 | `ruff format` | `uv run ruff format --check .` | `76 files already formatted` |
| 4 | `mypy` | `uv run mypy .` | `Success: no issues found in 20 source files` |
| 5 | Doctor | `uv run node .sdd/doctor/run-doctor.mjs` | `summary: 31 ok, 0 skipped, 0 warned, 0 failed` (with `OK pytest`) |
| 6 | `--version` | `uv run ec-procurement-quality --version` | `ec-procurement-quality 0.1.0` |
| 7 | Lock and sync | `uv sync --locked`; `uv lock --check` | `Checked 22 packages`; `Resolved 22 packages`; exit 0 for both |
| 8 | Only `httpx` added | `git diff main -- pyproject.toml` | only `dependencies = []` -> `["httpx>=0.28.1",]` |
| 9 | F1, `cli.py` and the package root unchanged | `git diff main --stat -- <the four F1 modules> interfaces/cli.py __init__.py` | empty |
| 10 | Fixtures unchanged | `git log --oneline -- tests/fixtures/sercop`; `git diff --stat 19ab9c3 HEAD -- tests/fixtures` | `74b785d` only; empty |
| 11 | Whitespace | `git diff --check`; `git diff main --check` | clean; clean |
| 12 | No real host in tests | `git grep -n -i --untracked -e datosabiertos -e compraspublicas -- tests` | no match, exit 1 |
| 13 | Nothing removed or weakened | `git diff --numstat 19ab9c3 -- tests`; `git diff --numstat 015a72b -- tests`; the added lines searched for `skip`, `xfail`, `filterwarnings`, `importorskip`, `monkeypatch`, `conftest` and `httpcore`; repeated top-level `def`, `class` and constant names searched | `615 0 tests/unit/test_sercop_source.py`; `1073 0 tests/unit/test_sercop_source.py`, and no other test file differs; no match (exit 1); none repeated. 707 tests are collected in the file and 890 in total. The 569 tests of `19ab9c3` pass inside them unchanged |

Red evidence for O2d, checked independently: the current tests run against the
`19ab9c3` adapter, on a scratch copy whose imported path was printed and confirmed,
give `65 failed, 825 passed`. The failures are 4 `exactly_value_error` base URLs, 9
option cases, 6 T2 cases, 8 T3 cases and 38 T4 cases. That is the 65 that `tasks.md`
O2d records, per group.

### AC14 and the doc claims (round 3)

| Check | Result (rerun) |
|---|---|
| `git grep -n "httpx" -- README.md CHANGELOG.md` | `CHANGELOG.md` 40, 47, 50; `README.md` 72, 81 |
| `git grep -n "No source access" -- README.md` | no match, exit 1 |
| README "Planned"; `docs/architecture.md` § Open questions | unchanged since round 2, and still accurate |
| Claims about chaining, causes, class names or the invariant | `git grep -n -i -w -e chain -e chained -e cause -e __cause__ -e "class name" -e invariant -- README.md CHANGELOG.md docs/architecture.md` -> exit 1. No doc states anything Revision 4 changed, so `tasks.md`'s "no README or CHANGELOG change is needed" holds |
| Claims not backed by a test | none found. README's "its tests use simulated transports and never reach the network" stays true: the `no_network` proof test uses the real transport, and the guard stops it |

### § Exit check, row by row against the installed packages and the code

Status: **holds** means that the row's statement, the exception types it lists and
the way each ends were confirmed in the named source, test or probe.

| Row | Checked in | Result |
|---|---|---|
| C1 | `_require_base_url` (`isinstance(base_url, str)` before `urlsplit`); probe with 7 types | holds |
| C2 | `urlsplit` `ValueError` caught at line 206, reason returned; probes: unclosed bracket, invalid literal, NFKC netloc (`／`, `℀`) | holds |
| C3 | `SplitResult.hostname` (partition on `%`, `lower`) and the `str` operations raise nothing | holds |
| C4 | `_is_port`: `isascii` and `isdigit` and length checked before `int` | holds |
| C5 | `httpx.URL` raises `InvalidURL` (a lone surrogate in the host, through IDNA) or a `ValueError` subclass (`UnicodeEncodeError` for a lone surrogate in the path, from its own percent-encoding); both are caught at line 227 (probe) | holds |
| C6 | `_urls.py:188-191` (`idna.decode` only for an `xn--` host), caught at line 233 | holds |
| C7 | the zone rule (line 235) runs on `url.host` before `url.raw_host` (line 241). `url.host` encodes nothing. For a host that `httpx` accepts, `":"` and `"%"` are both in it only for an IPv6 literal with a scope. A non-bracketed host cannot hold `":"` in the `httpx` authority grammar, and `ipaddress` needs `%` for a scope. Probe of 15 zone forms, plus the fuzz | holds (F-5 closed) |
| C8, C9, C10 | `_host_problem` string operations; `_search_url` and `_record_url` with constant ASCII arguments; `_library_accepts` catches `(InvalidURL, ValueError)` | holds |
| C11, C12 | `_require_seconds`, threshold check; `INVALID_OPTION_CASES` | holds |
| C13 | `_require_transport`, `_require_callable`; probe | holds (R-8 closed) |
| C14 | `Client.__init__` with a transport: `allow_env_proxies` false (`_client.py:685`), `Cookies(_NoCookieJar())` keeps the jar (`_models.py:1099`), `Timeout` and `Headers` take validated values | holds |
| C15 | `_client.py:685-696`, `HTTPTransport.__init__` (`create_ssl_context`, `Proxy`, `ImportError` for SOCKS) | holds; untested by design (environment) |
| C16 | `MemoryError`, `KeyboardInterrupt` and `SystemExit` are never caught (no broad `except`) | holds |
| K1, K2 | `_require_open`, `_require_positive_int`, `_require_text`; T3 | holds |
| K3, K4 | `str(value)` and `value.encode("utf-8")` tried in step 2, with the raise after the `try` (lines 91-97, 105-111). After step 2, `_search_url` and `_record_url` cannot raise: the f-string of a checked `int` and `quote` of encodable text. T3 and the call fuzz | holds |
| K5 | `build_request`: `_merge_url` (`URL`), `_merge_headers`, `_merge_cookies` (`Cookies.__bool__` iterates an empty jar), `Request.__init__` and `_prepare` (`url.host`, `url.netloc`, both safe once C6 and C7 hold). Only `InvalidURL` for length, caught at line 413, with the raise after the `try` | holds |
| K6 | `_wait_if_due`: injected callables propagate; with `time.sleep` the wait is at most `cooldown` | holds |
| K7 | `_attempt` `finally` (lines 427-432); `Decimal(text) < threshold` on ASCII digits | holds |
| K8 | `send`: closed check (pre-empted by K1), `_set_timeout`, `_build_request_auth` (no user information, so `Auth()`) | holds |
| K9 | `_transport_for_url`: no mounts with an injected transport; with `NO_PROXY`, `URLPattern.matches` reads `url.host` (C6) | holds |
| K10 | `HTTPTransport.handle_request`: `raw_scheme`, `raw_host` and `raw_path` are ASCII after C7, and the pool runs under `map_httpcore_exceptions` (`str(exc)` and `from exc`). `h11` probe over `MockBackend`: 16 malformed framings, nothing chained, the class named for the 15 library failures | holds (F-6 closed) |
| K11 | injected transport: an `httpx.HTTPError` is mapped, and anything else propagates (`SyntheticTransportDefect`, `SystemExit`, `KeyboardInterrupt`, `MemoryError`; probe: `InvalidURL` from `close()`) | holds as to types and endings; the class name of a double's error reaches the message (F-9) |
| K12 | `extract_cookies` (`_NoCookieJar` does nothing; `_CookieCompatRequest` on an absolute URL), `logger.info` | holds |
| K13 | `Headers.encoding` falls back to ISO-8859-1; `__contains__` before `__delitem__` | holds |
| K14 | `iter_raw` (`_models.py:935-959`) under `request_context`; the close after the last chunk is inside the hook's `try` | holds |
| K15 | `Response.close` sets `is_closed` before `stream.close()`, so the hook's second close is a no-op after a close failure in `iter_raw`; a later `httpx.HTTPError` is dropped in `_send` (line 475); probe | holds (R-10 closed) |
| K16 | `_send_handling_redirects`: hooks (981-982), then `has_redirect_location` is false (`Location` removed); `_send_handling_auth`: `StopIteration` returns | holds |
| K17 | `_send` keeps the failure when no status arrived | holds |
| K18 | `_attempt_from_capture`: injected `now` propagates | holds |
| K19 | `_outcome`: the status from `h11` has three digits; a status of 10**5000 from a double raises the interpreter's `ValueError` (probe), as the row says | holds; the class-name part is F-9 |
| K20, K21 | `_decode_json_object` catches `ValueError` and `RecursionError` and returns a verdict; the completeness checks raise nothing | holds |
| X1 | `Client.close` sets `CLOSED` before `transport.close()`; C13 guarantees `close` exists | holds |
| X2 | `__enter__` returns `self` | holds |

Result: all 39 rows hold for the exception types and the way each exit ends. The
class-name text of K11 and K19 is a § Output invariant matter (F-9).

### § Output invariant, against every `raise` in the adapter

Raise sites:
- call input: lines 87, 97, 102 and 111;
- construction: 118, 123, 137, 139, 141, 143, 257, 260 and 337;
- the request URL: 416;
- a closed adapter: 532;
- `_outcome`: 567, 573, 578, 585 and 592.

Line 607 raises inside `json.loads` and is caught at line 621, so it never leaves the
adapter. No `raise` sits inside an `except` block. Each `except` block (lines 93, 107,
193, 206, 227, 233, 413, 475, 502 and 621) passes, returns or stores the error, and
the two `finally` blocks (429, 504) raise nothing of their own.

| Rule | Result | Evidence |
|---|---|---|
| I1 type | holds | every site names one of the five types; the fuzz below; T2 to T4 |
| I2 nothing chained | holds for every call made outside an exception handler. **F-8** otherwise | tests, probes, fuzz; the F-8 reproducer |
| I3 fixed text | holds for every message built from fixed text, the operation, a parameter name, `_MAX_SECONDS`, a status from `h11` and the class name of an `httpx` exception. **F-9** for a class that a double defines | probes; T2 to T4; the F-9 reproducer |
| I4 no input text | holds for every input slot of the sweeps and the fuzz. **F-9**: a marker in a double's class name reaches the message | the same |

Fuzz (seed 33, offline, scratchpad `r3/fuzz_r3b.py`), with a guard that recorded 0 attempts:
- Base URLs: 12,000 built from 45 pathological pieces (non-ASCII letters and digits,
  U+200D, NUL, tab, newline, `%`, `%zz`, `%25`, brackets, `@`, `:`, `xn--`, labels of
  63 and 64, a lone surrogate, NFKC-sensitive characters) in the scheme, userinfo,
  host, IPv6 zone, port and path. 972 were accepted and 11,028 rejected. Every
  rejection satisfies I1 to I4, with the marker absent from the traceback, `repr`
  and `args`. Every accepted host passes `str.encode("idna")` (what `getaddrinfo`
  applies) and `ssl` `wrap_bio(server_hostname=...)` with memory BIOs. Each of its two
  calls, through the real `HTTPTransport` over `MockBackend`, ends in
  `SourceStatusError` satisfying I1 to I3. No violations.
- Call inputs: 8,000 random buyers and `ocid`s (lone surrogates, NUL, CR LF, emoji,
  BOM, `%`, reserved characters, empty), and years and pages (`0`, `-1`, `True`, a
  float, text, `None`, `10**5000`, `10**4300`, `10**4299`, `2**63`). The results:
  4,675 `ValueError` and 3,325 `SourceStatusError`, all satisfying I1 to I4. No
  violations.

A first run used a `MockTransport` reply built with `content=` and gave
`StreamConsumed` on every call. The plan already names that a test-double defect
(§ Closed-set justification), so the run was repeated with `stream=`.

### Beyond § Exit check: what the table does not cover

| Path | What was checked | Result |
|---|---|---|
| Class name in the message (`_failure_class`, `type(failure).__name__`) | A `MockTransport` raising an instance of `type(name, (httpx.ReadError,), {})` before the status and during the body. The names tried were `synthetic-leak-marker`, `Falloé`, `Bad\nName`, 200 `X`, and a class whose `__name__` was reassigned after creation. `type()` refuses NUL. The real transport maps only to `httpx`'s own classes (`HTTPCORE_EXC_MAP`), whose names are fixed ASCII | **F-9**: the messages are `... (synthetic-leak-marker)`, `... (Falloé)`, `... (Bad\nName)` and a 200-character name, so not ASCII, not printable, or holding the marker |
| The caller's own exception context | `search_page` called inside the caller's `except KeyError:` raises `SourceStatusError` with `__context__` = the `KeyError`. The same holds for a construction `ValueError`. CPython sets the context at the `raise` from the exception being handled, and `from None` only suppresses its display | **F-8** |
| Per-instance state shared between calls (`self._capture`, the pacing fields) | Re-entry: a transport that calls `fetch_record` from inside its own request. Two threads on one instance, interleaved by an event; 3 runs, same result | The outer response's content is the inner body followed by the outer body. With two threads, one call's `RawResponse` has an empty body (`b''`) while the other keeps its own. Nothing is raised. Concurrency is out of scope (intent § Scope): **R-11** |
| `__del__` | `grep` | none in the adapter, `httpx`, `httpcore` or `h11` |
| Hooks and the cookie jar | `event_hooks` holds only the adapter's response hook. `_NoCookieJar` takes nothing, and `Cookies.__bool__` is false, so no `Cookie` header is built | no gap |
| `Decimal`, `json`, `codecs`, `quote` | `Decimal` of ASCII digits is exact. `json.loads` errors are caught, and `MemoryError` propagates. Latin-1 decoding cannot fail. The adapter's own UTF-8 check runs before `quote`, and `content.decode("utf-8")` is caught | no gap |
| `urlsplit`, `host`, `raw_host`, `port`, `netloc` | C2, C6 and C7; `port` is read only by the transport, after the port rule; `netloc` encodes an ASCII host | no gap |
| The type rules and compatibility | Accepted: a `BaseTransport` subclass, `HTTPTransport`, `MockTransport`, `unittest.mock.Mock(spec=httpx.BaseTransport)`, and a `str` subclass as `base_url`. Rejected: a duck-typed object with `handle_request` and `close`, a bare `MagicMock()`, and `AsyncHTTPTransport()`. The plan requires `isinstance(..., httpx.BaseTransport)` (§ Binding constraints, option types) | compliant; the duck-typed double is a deliberate break (N-14) |
| `str` and `int` subclasses | Accepted by the spec. A subclass that overrides `__format__` changes the text the URL is built from after the checks ran | caller code; N-14 |
| A status that cannot be written, from a double | `httpx.Response(10**5000)` -> the interpreter's `ValueError` from `_outcome` | as row 1.2 and K19 say |
| The reason phrase | `HTTP/1.1 200 synthetic-header-marker\x01`: `h11` accepts it, and the marker reaches the `httpx` `INFO` record | known, N-9 of round 2 (status line, not a header or body value) |
| `trace` extension | the request's extensions hold only `timeout` | no `httpcore` trace callback |

### Points the brief asked to review

- The two `# noqa: TRY004` (lines 118 and 257). ruff's TRY004 asks for `TypeError` after a
  type check. AC10 Revision 4 requires exactly `ValueError` for every construction
  rejection, so each suppression is justified, targeted and commented, and the ruff
  configuration did not change. ruff does not flag the other type checks
  (`_require_transport`, `_require_seconds`, `_require_positive_int`): `ruff check`
  passes with no suppression on them. Targeted `noqa` already appears in the F1 tests.
  Not a convention violation.
- Line 547 (`return ""` in `_failure_class` for a failure of `None`). It is reached only
  through rule 1 when `send` returns normally with no status captured. In `httpx`
  0.28.1, `_send_handling_redirects` runs the response hooks on every response it
  returns (lines 979-982), and the hook sets the status first. Rule 3 needs a failure.
  So the line is unreachable, a defensive branch, not a dead test seam. CI shows the
  same single miss.
- The zone rule on `url.host` (the executor's choice). The plan suggested the bracketed
  part of the `urlsplit` netloc, and allowed any mechanism that meets the rule. The
  binding requirement is that nothing encodes the host as ASCII before the rule runs.
  `httpx.URL.host` returns the parsed text and decodes only an `xn--` host, so it holds.
  The rule catches exactly the hosts the plan names (C7 above). This is a compliant
  alternative. Mutant m5 shows that the tests pin it.

### No regressions against AC8, AC12 and AC15

- AC8: every message is fixed text plus the operation, a parameter name, a status
  number or a class name. `RawResponse.__repr__` is unchanged (no `domain` diff). The
  adapter has no `logging`, `print` or `sys.std*` (grep exit 1). Nothing is chained,
  and no `JSONDecodeError` or `UnicodeDecodeError` can be reached (`-k no_leak`, T4,
  the `h11` probe). The only new text paths are F-8 and F-9.
- AC12: `httpx` is imported only in `infrastructure` (`sercop_source.py:41`). `domain`,
  `application`, F1, `cli.py` and the fixtures are unchanged.
- AC15: no `except Exception` or `except BaseException` (grep exit 1). The `except`
  clauses name `ValueError`, `UnicodeEncodeError`, `httpx.InvalidURL`,
  `httpx.HTTPError` or `RecursionError` only. The pacing `try`/`finally` (lines
  427-432) still holds only `self._send(request)`, so every exit after the hand-off
  counts: `KeyboardInterrupt`, `SystemExit` and `MemoryError` (tests), and a
  `KeyboardInterrupt` raised by `close()` (probe, `[58.0]`).

### Lines the tests do not cover (round 3)

Coverage, rerun on Windows: `sercop_source.py` has 291 statements and 1 miss (547), and
TOTAL is 590 statements, 14 missed, 98%. Ubuntu CI on `1cd2f1e` gives the same adapter
miss and TOTAL 11 missed (98%). The difference is in F1, as in round 2. Line 547 is
assessed above. No other behavior that the spec requires lacks a test, apart from
C15, which has no test by design.

### Doc coherence and PR checks

- README, CHANGELOG and `docs/architecture.md` claim nothing that the tests do not
  verify (§ AC14 above).
- Specs: the § Exit check counts are consistent (16 C rows, 21 K rows and 2 X rows make
  39, of which 27 hold unchanged and 12 change). The § Validation counts match the tests
  (29, 32, 144, 34, 58 and 6, plus 18 list runs, total 321). Stale text: F-10.
- `tasks.md` records the O2d and O5d numbers that this round reproduced: `890`, `707`,
  `615 0`, `1073 0`, red `65 failed, 825 passed`, the single uncovered line 547. O9c is
  `[ ]`, which is correct before this verdict. The auditor writes only `audit.md`.
- PR checks, read on 2026-10-10. `gh pr checks 16` -> `feedback pass 10s`,
  `tests pass 14s`. `gh pr view 16 --json headRefOid,state,statusCheckRollup` ->
  `headRefOid` `1cd2f1e6816930cadc5a04f95a6388aba0be6f46` (the audited HEAD), `state`
  `OPEN`, and both checks `COMPLETED` with `SUCCESS`. The run logs, read with
  `gh run view --log`:
  - `feedback` (run 38109963964) prints `harny-feedback: 2 of 2 command(s) ran, 0
    skipped.`;
  - `Tests` (run 38109963941) prints `890 passed`, with `sercop_source.py` 291
    statements, 1 missed (547).

  `gh run view --json headSha` gives `1cd2f1e` for both runs.

### Conventions and feedback (round 3)

- `harny-standards`, against `AGENTS.md`. The layer boundaries hold. Raw responses are
  not overwritten. No SERCOP contract is invented. No dependency, infrastructure,
  framework or service was added. No secret or dataset was added: markers, hosts and
  bodies are SYNTHETIC, and hosts are `.invalid`, numeric or never contacted.
  Verification is reported. No violation. No AI attribution appears in the 12 branch
  commits since `main` (grep count 0) or in the changed files (grep exit 1).
- `harny-feedback`: the CI `feedback` job ran 2 of 2 commands on `1cd2f1e` and passed.
  `ruff` and `mypy` were rerun here only as AC13 evidence. Whether the per-turn hook
  fired during O2d and O5d is `unavailable`, because it leaves no persistent log.

### Findings (round 3)

| Id | Severity | Finding and evidence | Closure condition | Status |
|---|---|---|---|---|
| F-5, F-6, F-7 | (round 2) | rechecked above | met | **Resolved** |
| F-8 | LOW (blocking: AC8 Revision 4 and plan § Output invariant I2 are not met for one calling context; spec gap) | AC8 Revision 4: "No exception the adapter raises has a `__cause__` or a `__context__`, whatever its type". Plan § Output invariant I2: "`error.__cause__ is None and error.__context__ is None`", a property that "the tests check structurally, whatever the input". AC10 Revision 4: "nothing is chained". Reproducer (probe, rerun): `try: raise KeyError("callers-own-error")` / `except KeyError: source.search_page(year=2025, buyer="a", page=1)` against a `404` -> `SourceStatusError` whose `__context__` is that `KeyError`. Inside the same handler, `SercopSource(base_url="https://[::1/P")` -> `ValueError` with the same context. CPython links the exception being handled at every `raise`, and `raise ... from None` only hides the link. No implementation can meet I2 for a call made inside a handler. F4's retry inside `except SourceError` is such a call: the second error then carries the first. Nothing leaks, because the context is the caller's own exception and its text is fixed. The suite checks I2 only outside handlers | The architect revises I2 (with AC8 and AC10 Revision 4) to say what the adapter controls. For example: the adapter chains nothing of its own, and any `__context__` is an exception the caller was already handling. The architect also decides whether § Consumers (F4) should say so. If the wording changes only, no code or test change follows. Then the auditor rechecks. No code workaround is proposed here | Open |
| F-9 | LOW (blocking: plan § Output invariant I3 and I4, stated for "whatever the input", are not met for an input that the spec maps instead of treating as a test-double defect; spec gap) | Plan § Outcome mapping Revision 4 prescribes `type(failure).__name__` in the message of rules 1 and 3. § Exit check K11 maps every `httpx.HTTPError` from an injected transport, and K19 lists only the long status as a test-double exception. I3 requires a printable ASCII message whose only variable parts are a status and "the class name of an `httpx.HTTPError`". I4 requires that no marker reaches the message. Reproducer (probe, rerun, `MockTransport`, both places): a handler that raises `type("Falloé", (httpx.ReadError,), {})("plain")` -> `SourceTransportError("search_ocds: the request failed before a response arrived (Falloé)")`, which is not ASCII. A class named `Bad\nName` gives a message that is not printable. A class named `synthetic-leak-marker` puts the marker in the message and the traceback. A non-ASCII class name is a legal Python identifier and plausible in a Spanish-language test suite. Only an injected transport can produce this: the real stack maps only to `httpx`'s own ASCII class names. No source content can reach a class name | The architect decides, in a spec revision recorded in `tasks.md`. One option is to classify a double's own `httpx.HTTPError` subclass as a test-double case for I3 and I4, as row 1.2 and K19 already do for a status that cannot be written, and to narrow I3 to "the class name of an exception the HTTP library defines". The other is to require that the message names a class the library itself defines, with a § Validation case and red evidence. Then the auditor rechecks. No code workaround is proposed here | Open |
| F-10 | LOW | Spec consistency (stale text of the F-7 kind). Intent § Revision history, Revision 4: "because the header now reads `Approval: Pending`", but the header reads "Approved revision 4 by Vladimirjon on 2026-10-10". `tasks.md` § Status (lines 8-10: "the O5d code and the O2d tests uncommitted", "are not committed"), O8c ("PR #16 ... **unavailable** for this state ... until the human commits and pushes"), § Working state ("Uncommitted in the working tree") and § Checkpoint ("with the Revision 4 code and tests uncommitted ... The PR checks are unavailable"). The human committed and pushed this state as `1cd2f1e`, and both checks pass on it (§ Doc coherence above) | The architect updates the intent sentence or marks it as drafting-time history. Whoever owns `tasks.md` records `1cd2f1e` and the PR checks, as O7c did for `19ab9c3`. Checked by reading | Open |

### Reservations (round 3)

- R-2, R-8, R-9 and R-10: resolved (above).
- R-6 (carried, accepted risk): `ResponseStream.close()` is not mapped.
- R-7 (carried, accepted risk, now stated in AC8): `httpcore` writes header values at
  `DEBUG`.
- R-11 (new): one `SercopSource` holds the capture and the pacing state of the request
  in progress (`self._capture`, `_last_attempt_end`, `_cooldown_required`). It is not
  safe to share between threads, or to re-enter from inside a call, and misuse fails
  silently: the probe gives one call an empty body, and a re-entered call a body that
  mixes two responses. Intent § Scope puts concurrency out of scope, so this is not a
  finding. But neither the specs nor the adapter's docstrings say that an instance must
  not be shared, while the `httpx.Client` underneath is documented as thread-safe, and
  the failure corrupts evidence (ADR 0005) instead of raising. The architect may add one
  line to plan § Consumers (F4): one instance per thread, never called from its own
  transport or callables.

### Notes (round 3)

- N-13: line 547 is unreachable and defensive (above). Statement coverage counts it as
  the adapter's only miss, locally and in CI.
- N-14: the type rules change compatibility in the way the plan chose. A duck-typed
  transport and a bare `MagicMock()` are now rejected, and `Mock(spec=httpx.BaseTransport)`
  is accepted. `str` and `int` subclasses stay accepted. One that overrides
  `__format__` or `__str__` can build a request URL other than the checked text.
  That is the caller's code, outside any input rule.
- N-15: the T4 sweep injects `httpx` exceptions with the message shape of the real
  `h11` path, and no test imports `httpcore`. This round's `MockBackend` probe confirms
  that the real stack produces exactly those classes and ends the same way. The sweep
  therefore stands for the real path, and its structural I2 check does not depend on
  the text.
- N-16: `-k` tokens also match parameter ids, so several focused counts include
  Revision 4 cases (`transport` 37, the AC10 command 239). `tasks.md` O2d explains this,
  and the counts were reproduced exactly.

### Commands run in round 3 (all rerun, Windows, Python 3.13.9, `uv`, repository root)

| Command | Result |
|---|---|
| `git status --short`; `git rev-parse HEAD` | empty; `1cd2f1e6816930cadc5a04f95a6388aba0be6f46` |
| `git diff --stat 19ab9c3 HEAD`; `git diff --stat 19ab9c3 HEAD -- src`; `git diff --stat 19ab9c3 -- <domain, application, interfaces, fixtures, docs/adr, pyproject.toml, uv.lock, test_layers.py, test_source_response.py, README.md, CHANGELOG.md, docs/architecture.md, .github, .sdd, .claude, .gitignore>` | 6 files (4 specs, the adapter, the test file); adapter only, `77 +, 12 -`; empty |
| `git diff --numstat 19ab9c3 -- tests`; `git diff --numstat 015a72b -- tests` | `615 0`; `1073 0` |
| `uv sync --locked`; `uv lock --check` | `Checked 22 packages`; `Resolved 22 packages` |
| `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing` | `890 passed`; TOTAL 590/14/98%; `sercop_source.py` 291/1 (547) |
| `uv run pytest tests -W error` | `890 passed` |
| `uv run pytest --collect-only -q tests` and the adapter file | 890; 707 |
| focused rows: `search_success or query` / `record_success` / `raw_response or store_shape or cookie` / `out_of_range or no_results` / `status_error` / `transport` / `incomplete` / `no_leak` (both files) / `invariant` / `pacing` / `timeout or accept_encoding or invalid` (both files) / `documented_boundaries or non_ascii_base_path` / `exactly_value_error or invariant` / `no_network` / `layer or satisfies_port` (`tests/unit`) / the AC15 `-k` / `memory_error` / `transport_defect` | 13 / 4 / 20 / 4 / 30 / 37 / 53 / 296 / 236 / 52 / 239 / 18 / 297 / 2 / 9 / 420 / 4 / 12, all passed |
| `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy .` | `All checks passed!`; `76 files already formatted`; `Success: no issues found in 20 source files` |
| `uv run node .sdd/doctor/run-doctor.mjs`; `uv run ec-procurement-quality --version` | `31 ok, 0 skipped, 0 warned, 0 failed`; `ec-procurement-quality 0.1.0` |
| `git diff main -- pyproject.toml`; `git diff main --stat` (F1, `cli.py`, `__init__.py`); `git log --oneline -- tests/fixtures/sercop`; `git diff --check`; `git diff main --check` | only `httpx`; empty; `74b785d`; clean; clean |
| `git grep` for the real host in tests, the default URL in `src`, `except Exception`/`except BaseException`, `raise ... from`, `httpx` imports in `src`, logging and printing in the adapter, `noqa` in `src`, attribution in changed files; commit messages since `main` searched for attribution | exit 1; 1 match (`:57`); exit 1; exit 1; `sercop_source.py:41` only; exit 1; lines 118 and 257; exit 1; 0 of 12 commits |
| Scratch mutants (`PYTHONPATH=<copy>/src`, imported path printed and confirmed): m1, m2, m2b and m2c with `-k test_no_leak_rejections_chain_no_library_exception` | 2 failed of 43 each (m1: `too-long-search-buyer`, `too-long-record-ocid`; m2: `base-url-invalid-ipv4-host`, `base-url-control-character`; m2b: `base-url-a-label-malformed`, `base-url-a-label-disallowed`; m2c: `base-url-ipv6-unclosed-bracket`, `base-url-ipv6-invalid-literal`) |
| The same 4 mutants and 8 new ones (m3 rule 1 chained, m4 library text in rule 3, m5 no zone rule, m6 no UTF-8 check, m7 no transport rule, m8 base-class name, m9 later failure escapes, m10 no digit check) against the whole suite | failed: m1 4, m2 23, m2b 5, m2c 38, m3 26, m4 12, m5 18, m6 4, m7 2, m8 38, m9 2, m10 4 (of 890) |
| The current tests against the `19ab9c3` adapter (scratch copy from `git archive`) | `65 failed, 825 passed` (4 + 9 + 6 + 8 + 38) |
| Scratch probes `r3/probe_construct.py` (F-5, R-2, R-8, compatibility), `r3/probe_h11.py` (20 cases by 2 operations over `MockBackend`: 16 malformed framings, a reason phrase with a control character, a valid `429`, a `200` with an unusable body and a valid search page), `r3/probe_calls.py` (R-9, R-10, class names, the caller's context, the long status), `r3/probe_reentry.py` (3 runs) and `r3/fuzz_r3b.py` | results quoted above; guard attempts 0 |
| `gh pr checks 16`; `gh pr view 16 --json ...`; `gh run view 38109963964 --log`; `gh run view 38109963941 --log`; `gh run view <id> --json headSha` | both `pass` on `1cd2f1e`; `2 of 2 command(s) ran, 0 skipped`; `890 passed`; `1cd2f1e` for both |

### Not verified in round 3, and why

- Real name resolution and real TLS handshakes were not run (no network by brief). For
  every host that the fuzz accepted, the `idna` codec that `getaddrinfo` applies, and
  `ssl` with memory BIOs, were run directly instead.
- The F-6 recheck used `httpcore.MockBackend`, which replaces only the socket. No live
  server sent malformed framing.
- R-7 (`httpcore` at `DEBUG`) was not re-probed in this round.
- C15 (environment proxy and certificate settings with the default transport) was not
  exercised, because changing the process environment is outside this audit's offline
  probes. The row was checked by reading the source only.
- R-11's thread case depends on scheduling. It gave the same result in 3 runs, which
  shows that the state is shared, not how often the mix-up happens.
- Whether the per-turn Stop hook fired during O2d and O5d is `unavailable` (no persistent
  log). CI `feedback` ran 2 of 2 commands on `1cd2f1e`.

## Round 4

### Scope of round 4

Round 4 ran on 2026-10-12. Auditor: `sdd-auditor` (harny-audit). The reviewed state is
the working tree on branch `feat/sercop-source-adapter`, at HEAD `dc78500` (base `main`
`fff0f2d`). `dc78500` commits the round 3 report and Revision 5 of the intent and the
plan. On top of it, `git status --short` shows three uncommitted files:
- `tests/unit/test_sercop_source.py` (O2e, gate 2 approved; `git diff --numstat 1cd2f1e
  -- tests` -> `646 0`);
- `src/ec_procurement_quality/infrastructure/sercop_source.py` (O5e; `49 6`);
- `tasks.md`.

Against `1cd2f1e`, the code and test baseline, `git diff --stat 1cd2f1e` touches only
these six files: the four spec files, the adapter and the adapter's test file. These
paths show no diff against `1cd2f1e`:
- `domain`, `application` and `interfaces`;
- `tests/fixtures`, `docs` (ADRs included), `README.md` and `CHANGELOG.md`;
- `pyproject.toml` and `uv.lock`;
- `.github`, `.sdd`, `.claude` and `.gitignore`;
- `test_layers.py` and `test_source_response.py`.

The command exits 0 with empty output.

Read in full for this round:
- `intent.md` and `execution-plan.md` Revision 5, including § Output invariant, § Statement
  check and § Exit check with its Revision 5 rows;
- `tasks.md` and rounds 1 to 3 of this report;
- the whole adapter, the whole adapter diff against `1cd2f1e`, and every added test line
  (the docstring paragraph and lines 3183 to 3817).

The added test lines contain no `skip`, `xfail`, `filterwarnings`, `importorskip`,
`conftest`, `monkeypatch` or `httpcore` (`grep` exit 1). `_assert_output_invariant` has
no changed line, and the new helper is `_assert_invariant_with_context`.

Library behavior was confirmed in `.venv` (Python 3.13.9, `httpx` 0.28.1):
- `httpx/_models.py`: `Response.iter_raw` ends with `self.close()` inside the
  generator, after the flush. `Response.close` sets `is_closed` before it calls
  `stream.close()`.
- `httpx/_client.py`: `_send_handling_redirects` runs the response hooks inside
  `try`/`except BaseException`.
- `grep -rn "def __del__"` finds none in `src`, `httpx`, `httpcore` or `h11`.

No network access was made to SERCOP or to any resolver. Probes ran in the session
scratchpad under `r4/`, outside the repository, with the `.venv` interpreter run with
`-I` and `httpx.MockTransport`. A guard on `socket.socket.connect`, `connect_ex`,
`create_connection` and `getaddrinfo` recorded 0 attempts. The only network access was
to GitHub, through `gh`, to read the PR #16 checks.

### Round 3 findings and reservations, rechecked

| Item | Exact round 3 input, rerun now | Result on the reviewed state | Status |
|---|---|---|---|
| F-8 (AC8, AC10; I2) | `try: raise KeyError("callers-own-error")` / `except KeyError: source.search_page(year=2025, buyer="a", page=1)` against a `404`. In the same handler, `SercopSource(base_url="https://[::1/P")`. Variants: the same call inside a `finally` while the `KeyError` propagates; inside a context manager's `__exit__` while it propagates; a second call inside `except SourceStatusError as first` | Every case (probe `r4/probe_r4.py`) has exactly one of the five types, `__cause__` `None` and `__suppress_context__` `False`. `__context__` is the caller's exception: the `KeyError`, or `first` for the retry. The text is printable ASCII, with `args == (str(error),)`. A first call made outside any handler has `__context__` `None`. These are exactly the Revision 5 I2 and the AC8 Revision 5 chaining rule. T5 (25 cases) passes. Red evidence (scratch mutants, rerun by the auditor): m11 (`from None` on rule 4) fails exactly the 6 T5 cases that § Validation names (the two rule-4 cases, the two retry cases and the two `finally` cases), plus 2 T7 rule-4 cases (8 in the suite). m12 (rule 4 raised inside `except LookupError`) fails the same 6 T5 cases, and 60 in the suite. `git grep` finds no `) from`, `raise ... from`, `from None` or `suppress` in the adapter (exit 1) | **Resolved** |
| F-9 (AC8; I3, I4) | A `MockTransport` raising, before the status and after the chunk `b"{"`, for both operations, an instance of `type("Falloé", (httpx.ReadError,), {})`, `type("Bad\nName", (httpx.RemoteProtocolError,), {})`, a class named `synthetic-leak-marker`, and a class named with 200 `X`. Also: a class whose `__name__` is set to the marker after creation, a direct subclass of `httpx.HTTPError`, a class with two `httpx` bases, and a subclass of a marker-named subclass of `PoolTimeout` | The messages end with `(ReadError)`, `(RemoteProtocolError)`, `(ConnectError)` and `(ReadTimeout)`, and with `(WriteError)`, `(HTTPError)`, `(ReadError)` and `(PoolTimeout)` for the others. Each message is printable ASCII, and no marker appears in the formatted traceback, `repr`, `args` or the carried response (probe: 32 cases, 8 classes by 2 places by 2 operations, 0 violations). T6 (28 cases) passes. Against `1cd2f1e`, all 28 fail (rerun). Mutant m13 (back to `type(failure).__name__`) fails 28 | **Resolved** |
| F-10 | the five places named in round 3 | Intent § Revision history, Revision 4, now says that the header read `Approval: Pending` while Revision 4 was a draft, and it holds the moved approval record. `tasks.md` records `1cd2f1e` as committed and pushed, with both checks passing, in four places: § Status (line 12), the O8c record (Revision 5 record, line 464), § Working state (line 580) and § Checkpoint (line 630) | **Resolved**. New stale text of the same kind is F-12 |
| R-11 | Round 3's re-entry and thread cases: a transport that calls `fetch_record` on the same instance from inside its own request, and two threads on one instance, interleaved by events (3 runs) | The behavior is unchanged, as the closure intended (a documented rule, no mechanism; accepted by the human at the Revision 5 approval). The outer call's response holds the inner body, and in the thread case the first call's response holds the second call's body (`b'SECOND'`). No error is raised in either case. The rule is now stated in four places: the `SercopSource` docstring, lines 321 to 326 (`git grep "one thread at a time"` gives 1 match, line 321); intent AC15 Revision 5; plan § Binding constraints and § Consumers (F4); and § Risks | **Resolved** (documented rule) |
| R-6, R-7 | — | Unchanged | Open (accepted risks) |

### AC results (intent Revision 5)

| AC | Status | Evidence (all rerun) |
|---|---|---|
| AC1 | PASS | `-k "search_success or query"` -> `13 passed`. `git grep "datosabiertos.compraspublicas.gob.ec/PLATAFORMA" -- src` -> 1 match, `sercop_source.py:58` |
| AC2 | PASS | `-k record_success` -> `4 passed` |
| AC3 | PASS | `-k "raw_response or store_shape or cookie"` -> `20 passed`. The whole suite with `-W error` -> `961 passed` |
| AC4 | PASS | `-k "out_of_range or no_results"` -> `4 passed` |
| AC5 | PASS | `-k status_error` -> `30 passed` |
| AC6 | PASS | `-k transport` -> `48 passed`. That is 37, plus the 10 Revision 5 `transport_defect` tests and the T5 id `construction-transport-of-the-wrong-type`, which also matches the token (N-16) |
| AC7 | PASS | `-k incomplete` -> `53 passed` |
| AC8 | PASS | `-k no_leak` over both files -> `357 passed`. `-k invariant` -> `297 passed`. `-k "invariant or transport_defect"` -> `319 passed`. F-8 and F-9 are resolved (above). The AC8 Revision 5 example holds: `SyntheticStatus(404)` gives a message ending with `status 404` and a response status of exactly `int` 404, and no marker appears anywhere (T7 and the probe). The adapter has no `logging`, `print`, `sys.std*` or `warnings` (`git grep` exit 1) |
| AC9 | PASS | `-k pacing` -> `52 passed`. In every D-1 case, the following call waits `[58.0]` (`Remaining: 5`) |
| AC10 | PASS | `-k "timeout or accept_encoding or invalid"` over both files -> `245 passed`. `-k "documented_boundaries or non_ascii_base_path"` -> `18 passed`. `-k "exactly_value_error or invariant"` -> `358 passed`. The chaining wording of Revision 5 holds for the construction and call-input cases of T5 and the probe |
| AC11 | PASS | `-k no_network` -> `2 passed`. `git grep -n -i --untracked -e datosabiertos -e compraspublicas -- tests` -> exit 1. `git grep -c "source.invalid"` on the adapter test file -> 43 |
| AC12 | PASS | `tests/unit -k "layer or satisfies_port"` -> `9 passed`. `uv run mypy .` -> `Success: no issues found in 20 source files`. `httpx` is imported in `src` only at `sercop_source.py:42` |
| AC13 | PASS | the 13 points below |
| AC14 | PASS | § AC14 below |
| AC15 | PASS | The AC15 `-k` -> `491 passed`. `-k memory_error` -> `4 passed`, `-k transport_defect` -> `22 passed`. The three `git grep` checks of the row: no `except Exception` or `except BaseException`; no `) from` or `raise ... from`; and one `one thread at a time`, at line 321, in the `SercopSource` docstring. D-1 holds in every kind of read end (below). § Statement check and the Revision 5 rows of § Exit check hold (below) |

### Test coverage (round 4, the Revision 5 tests)

| AC | Test (`tests/unit/test_sercop_source.py`) | Cases | Red against `1cd2f1e` (rerun) | Status |
|---|---|---|---|---|
| AC8, AC10 (I2) | `test_no_leak_invariant_context_is_the_callers_own_exception` (T5) | 25 | 0, as planned. The red evidence is m11 and m12, which each fail the named 6 cases | PASS |
| AC8 (I3, I4; class names) | `test_no_leak_invariant_names_only_a_class_that_httpx_exports` (T6) | 28 | 28 | PASS |
| AC8 (I3, I4; status) | `test_no_leak_invariant_reads_the_status_as_an_exact_int` (T7) | 8 | 8 | PASS |
| AC15 (D-1) | `test_transport_defect_survives_a_failing_stream_close` | 8 | 8 (`DID NOT RAISE`) | PASS |
| AC15 (Python's rule) | `test_transport_defect_from_the_stream_close_follows_python_chaining` | 2 | 0, as planned. Mutant m18 (`except Exception: pass` around the close) fails both | PASS |

The red run reproduces the `44 failed, 917 passed` that `tasks.md` O2e records. It runs
the current tests against the `1cd2f1e` adapter, on a scratch copy made with
`git archive`, and the printed import path confirms that copy was used. The test seams
are all live: the T6 classes, the `SyntheticStatus` and the `ClosingReply` close errors
each change the outcome under some mutant.

### AC13, point by point (round 4)

| # | Point | Command | Result (all rerun) |
|---|---|---|---|
| 1 | Every test passes | `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing` | `961 passed`; TOTAL 599 statements, 15 missed, 97%; `sercop_source.py` 300 statements, 2 missed (584, 590) |
| 2 | `ruff check` | `uv run ruff check .` | `All checks passed!` |
| 3 | `ruff format` | `uv run ruff format --check .` | `76 files already formatted` |
| 4 | `mypy` | `uv run mypy .` | `Success: no issues found in 20 source files` |
| 5 | Doctor | `uv run node .sdd/doctor/run-doctor.mjs` | `summary: 31 ok, 0 skipped, 0 warned, 0 failed` (with `OK pytest`) |
| 6 | `--version` | `uv run ec-procurement-quality --version` | `ec-procurement-quality 0.1.0` |
| 7 | Lock and sync | `uv sync --locked`; `uv lock --check` | `Checked 22 packages`; `Resolved 22 packages`; exit 0 for both |
| 8 | Only `httpx` added | `git diff main -- pyproject.toml` | only `dependencies = []` -> `["httpx>=0.28.1",]` |
| 9 | F1, `cli.py` and the package root unchanged | `git diff main --stat -- <the four F1 modules> interfaces/cli.py __init__.py` | empty |
| 10 | Fixtures unchanged | `git log --oneline -- tests/fixtures/sercop`; `git diff --stat 1cd2f1e -- tests/fixtures` | `74b785d` only; empty |
| 11 | Whitespace | `git diff --check`; `git diff main --check` | clean; clean |
| 12 | No real host in tests | `git grep -n -i --untracked -e datosabiertos -e compraspublicas -- tests` | no match, exit 1 |
| 13 | Nothing removed or weakened | `git diff --numstat 1cd2f1e -- tests`; `git diff --numstat 19ab9c3 -- tests`; `git diff --numstat --minimal 015a72b -- tests`; the O8d list of unchanged paths; the added lines searched as in the scope above | `646 0`, `1261 0` and `1719 0`, all in `tests/unit/test_sercop_source.py`, and no other test file differs. The default `git diff --numstat 015a72b` prints `1756 37`, a diff-alignment artifact (N-19). The unchanged-paths list (O8d) is empty. 778 tests are collected in the file and 961 in total. The 890 tests of `1cd2f1e` pass unchanged inside them |

### AC14 and the doc claims (round 4)

| Check | Result (rerun) |
|---|---|
| `git grep -n "httpx" -- README.md CHANGELOG.md` | `CHANGELOG.md` 40, 47, 50; `README.md` 72, 81 |
| `git grep -n "No source access" -- README.md` | no match, exit 1 |
| README "Planned" (lines 88 to 93); `docs/architecture.md` § Open questions (lines 84 to 88) | unchanged since round 3, and still accurate |
| Claims about chains, causes, class names, the invariant, threads or the close | `git grep -n -i -w -e chain -e chained -e cause -e __cause__ -e "class name" -e invariant -e thread -e threads -e close -- README.md CHANGELOG.md docs/architecture.md` -> exit 1. No doc states anything that Revision 5 changed, so `tasks.md`'s "No README or CHANGELOG change is needed" holds. `git diff --stat 1cd2f1e -- README.md CHANGELOG.md docs` is empty |
| The README and CHANGELOG paragraphs on F2, read in full | accurate: one request per call, typed errors with the valid response, a status outside 100 to 599 with none, no retries, pacing, timeouts, user information rejected, simulated transports |
| O7d (F-10) corrections, by reading | see F-10 above: present and accurate |

### § Statement check, row by row

Each row was checked against the code of the reviewed state, the named tests and the
round 4 probes.

| # | Revision 5 action | Checked in | Result |
|---|---|---|---|
| S1 | "creates"; caller-code rule | every one of the 20 raise sites creates one of the five types; the caller-code rule is in plan § Binding constraints and intent AC15 Revision 5. Probe: a float status raises `TypeError` from `operator.index`, which propagates unchanged | holds |
| S2 | I2 restated | T5 (25); probe (`except`, `finally`, `__exit__`, retry); m11, m12 | holds |
| S3 | the exported-class list; the exact `int` status | `_failure_class` (lines 576 to 590), `_HTTPX_ERROR_CLASSES` (79 to 83), `operator.index` (513); T6, T7; probe; m13, m14 | holds |
| S4 | I4 with `chain=False`; the input slots | `_assert_invariant_with_context`: format_exception(`chain=False`), `repr`, `args`, and the response when the transport delivered the marker. Every marker is passed through a variable (`LEAK_MARKER`, `_SURROGATE_TEXT`, `_TOO_LONG_TEXT`) | holds |
| S5 | unchanged | `-k no_leak` (357) | holds |
| S6 | read as I2 | decoding and parsing errors are caught at line 664 and returned as a verdict, and rule 5 is raised outside. T5 `rule-5-unusable-200` in a handler | holds |
| S7 | narrowed to the adapter's and the library's records | no logging in the adapter (`git grep`); the `caplog` tests at `DEBUG` | holds |
| S8, S9 | read as I2 | `test_no_leak_rejections_chain_no_library_exception`; T5 | holds |
| S10 | the nearest exported class | as S3 | holds |
| S11 | unchanged (R-7) | — | holds (accepted risk) |
| S12 | caller-code rule (AC10 Revision 5) | invalid-input tests (245); stated in AC10 Revision 5 | holds |
| S13 | read as I2 | T5 construction case `https://[::1/PLATAFORMA`; `_assert_base_url_not_echoed` tests | holds |
| S14, S15, S17 | caller-code rule | stated in AC10 and AC15 Revision 5. No code path depends on it | holds |
| S16 | "exactly" kept; "nothing chained" read as I2 | `exactly_value_error` tests; T5 construction cases | holds |
| S18 | unchanged | T3 | holds |
| S19 | caller-code rule | `_build_request` catches `httpx.InvalidURL` and raises the fixed `ValueError` after the `try` (lines 429 to 436). Anything else propagates | holds |
| S20 | unchanged | § Exit check, all rows; the closed-set tests | holds |
| S21, S22, S23 | the first exception decides; Python's rule for a non-`httpx` close error | hook `finally`, lines 525 to 537; the two tests (10 cases); probe of 10 kinds of read end by 2 operations (below); m15 fails 8 | holds |
| S24 | the one-caller rule | docstring, lines 321 to 326; plan § Consumers (F4) and § Risks; R-11 probe | holds (documented, no mechanism) |
| S25 | unchanged | no `__del__` in `src`, `httpx`, `httpcore` or `h11` | holds |

Result: all 25 rows hold. The counts in the plan (5 hold unchanged, 4 clarified and 16
restated, 3 of them needing code) match the rows.

### § Exit check, the Revision 5 rows

| Row | Checked in | Result |
|---|---|---|
| K13 (status) | Line 513 reads `operator.index(response.status_code)` once, and pacing, rule 2, the messages and `RawResponse` use that value. Probe: `SyntheticStatus(404)`, `(600)` and `(429)`, whose `__format__`, `__str__`, `__repr__` and even `__index__` are overridden, give the exact `int` (its `__index__` never runs) and the right wait (`[3.0]` or `[58.0]`). Edge cases: a float status raises `TypeError`, which propagates as caller code, and the next wait is `[3.0]` (no status was captured). `True` gives rule 2 with `status 1`. An object with `__index__` has that method run (caller code), giving 404 | holds |
| K14a (the close after another read end) | Hook `finally`, lines 525 to 537. See D-1 below | holds |
| K19 (the class named) | `_failure_class` walks `type(failure).__mro__` and compares by identity with the 21 exported classes. `type()` cannot be spoofed through `__class__`. Probe: 32 cases. Line 590 is reachable only through a metaclass (N-18) | holds |
| R (every `raise`; F-8 wording) | no `from` clause; no `raise` inside an `except` or a `finally` (below); T5 and the probe | holds |
| CC (caller code) | stated in plan § Binding constraints and intent AC15 Revision 5; the probe's caller-code cases | holds (stated) |

The 39 Revision 4 rows were not rerun one by one. The code they describe is unchanged
apart from these three statements, and the whole suite passes. Their exception types and
endings are as round 3 recorded. K15's text ("escapes the hook and is dropped in
`_send`") now describes the wrong place, although the behavior it binds holds (N-17).

### § Output invariant, against every `raise` in the adapter

Raise sites at the reviewed state:
- call input: lines 97, 107, 112 and 121;
- construction: 128, 133, 147, 149, 151, 153, 267, 270 and 355;
- the request URL: 434;
- a closed adapter: 564;
- `_outcome`: 610, 616, 621, 628 and 635.

Line 650 raises inside `json.loads` and is caught at line 664, so it never leaves the
adapter. No `raise` sits inside an `except` block. Each `except` block (lines 103, 117,
203, 216, 237, 243, 431, 493, 523, 536 and 664) passes, returns or stores the error. The
two `finally` blocks (447, 525) raise nothing of their own.

The variable parts of the messages are these:
- the constant parameter or option names;
- `_MAX_SECONDS`;
- the fixed reasons of `_base_url_problem`;
- the constant operation names;
- the exact `int` status (lines 513, 616, 621 and 628);
- a name from `_HTTPX_ERROR_CLASSES`, written as that class's own `__name__`.

| Rule | Result | Evidence |
|---|---|---|
| I1 type | holds | every site names one of the five types; T2 to T7; the probe |
| I2 nothing chained from the call | holds, inside and outside handlers | T5; the F-8 probe; m11, m12 |
| I3 fixed text | holds | the list above; T6, T7; the probe (32 class cases, 3 status subclasses) |
| I4 no input text | holds | T2 to T7; the probe |

### D-1 (point 5a of the brief): the drop around the hook's close

The binding text is plan § Outcome mapping. Revision 4 already says: "Any later
`httpx.HTTPError` is dropped, as is the response hook's own `response.close()` once a
status was captured". Revision 5 adds the read that ends in another exception. The flag
form in § Proposed approach is introduced by "For example". So a drop that covers every
kind of read end is within the plan's words. The question is whether the outcome holds
in every case. The probe ran a `200` with `X-RateLimit-Remaining: 5` for both
operations, followed by a `404` two seconds later:

| Read end, then the close | Outcome (probe) | Spec | Next wait |
|---|---|---|---|
| clean read, close raises `httpx.CloseError` | `SourceTransportError` with all the bytes, `(CloseError)`. The close inside `iter_raw` fails within the hook's `try`, so this is rule 3. The second close in `finally` does nothing (`is_closed`) | AC15 Revision 4: rule 3 with all the bytes | `[58.0]` |
| cut by `httpx.ReadError`, close raises `httpx.CloseError` | `SourceTransportError` with `b"{"`, `(ReadError)`. The close error is dropped in the hook | the first failure decides | `[58.0]` |
| cut by `httpx.ReadError`, close raises `OSError` | `OSError` propagates | R-6 (accepted) | `[58.0]` |
| clean read, close raises `KeyboardInterrupt` | `KeyboardInterrupt` propagates | pass-through | `[58.0]` |
| `KeyboardInterrupt`, `SystemExit`, `MemoryError`, a defect or `httpx.StreamConsumed`, then `httpx.CloseError` or `httpx.ReadError` | the first exception propagates as the same object, with `__context__` `None` | AC15 Revision 5: the first exception decides | `[58.0]` |
| a defect, then a second defect from the close | the second defect propagates, with the first as its `__context__` | Python's rule | `[58.0]` |

Mutants confirm what the tests pin:
- m16 (the plan's flag form: the drop only after a non-`httpx` read end) passes all 961
  tests;
- m17 (`_send` re-raises a library error once a status was captured) also passes all
  961;
- m19 (both together) fails the 2 `close-after-cut` cases of T4.

So the wide drop gives the same outcome as the flag form in every case the spec names.
It changes one thing: `_send`'s drop branch has no path left with `httpx` 0.28.1, and
the R-10 case (`close-after-cut`) is now dropped in the hook. **Judgement: a note
(N-17), not a finding.** No outcome, type, chain or pacing result differs from the spec,
and the T4 cases pin the drop wherever it happens.

### Points the brief asked to review

- (a) D-1: above, N-17.
- (b) Line 584 (`return ""` for a failure of `None`) is reached only through rule 1 when
  `send` returns normally with no status captured. The hook runs on every response that
  `_send_handling_redirects` returns, and it sets the status at line 513 before it does
  anything else. If `operator.index` raises, that exception propagates. So the line is
  unreachable, a defensive branch.
  Line 590 (the fallback `HTTPError`) is reachable, but only through a test double whose
  metaclass overrides `__mro__`. For example, a property that returns `(cls, object)` for
  a subclass of `httpx.ReadError`. `except httpx.HTTPError` matches on the real
  hierarchy, not on that attribute. The message is then `... (HTTPError)`, a name from the
  closed list, and I1 to I4 hold (probe). A `__mro__` property that raises makes its
  `KeyError` propagate from `_outcome`. That is caller code (intent AC15 Revision 5:
  exception classes are caller code), and the attempt still counted (`[3.0]`). Neither
  line can put text of the double into a message. The comment "Not reachable" is
  imprecise for that one double (N-18).
- (c) `tasks.md` § Status: F-12 below.

### Family check (point 6): new gaps of the same families

The search covered every statement added or changed by O5e and every raise site above.
It looked for statements that can raise outside the closed set, and for response content
or test-double text reaching a message, a `repr`, `args` or a chain. Inputs tried:
- the 8 class shapes of F-9;
- metaclass `__mro__` overrides;
- `int` subclasses with every formatting method and `__index__` overridden;
- a float status, a `bool` status and an object with `__index__`;
- 10 kinds of read end, by 2 operations, each followed by a failing close;
- calls inside `except`, `finally` and `__exit__`;
- the R-11 re-entry and thread cases.

Results:
- `_HTTPX_ERROR_CLASSES` is built at import from `httpx.__all__`. All 69 names resolve,
  and 21 are `HTTPError` subclasses (probe; it matches the plan's list).
- `operator.index` on the real status (an `int` from `h11`) cannot raise.
- No adapter-created exception is raised while an internal exception is being handled.
- A pass-through exception that the hook's `finally` lets through keeps its identity and
  its context. The dropped close error is not linked to it.

No new finding of these families. The two findings below are stale text.

### No regressions against AC8, AC12 and AC15

- AC8: `RawResponse` and the `domain` errors are unchanged (no `domain` diff). The
  status in a response is an exact `int`. Nothing is chained from the call.
- AC12: `httpx` is imported only in `infrastructure` (line 42). `domain`, `application`,
  F1, `cli.py` and the fixtures are unchanged.
- AC15: no `except Exception`, `except BaseException` or `suppress`. The `except`
  clauses name only these:
  - `ValueError` and `UnicodeEncodeError`;
  - `httpx.InvalidURL` and `httpx.HTTPError`;
  - `RecursionError`.

  The pacing `try`/`finally` (lines 445 to 450) still holds only `self._send(request)`.

### Lines the tests do not cover (round 4)

Coverage, rerun on Windows: `sercop_source.py` has 300 statements and 2 misses (584 and
590). TOTAL is 599 statements, 15 missed, 97%. Both lines are assessed above. CI coverage
for this state is `unavailable` (R-12).

### Doc coherence and PR checks

- README, CHANGELOG and `docs/architecture.md` claim nothing that the tests do not
  verify (§ AC14 above).
- Specs: the § Validation counts match the tests: 25, 28, 8, 8 and 2, so 71; 778 in the
  file and 961 in total. The § Statement check counts match its rows. Stale text: F-12.
  The adapter's module docstring: F-11.
- `tasks.md` records the numbers this round reproduced: `961 passed`, `44 failed, 917
  passed`, `646 0`, the `49 6` adapter diff, 599/15/97% and lines 584 and 590. O9d is
  `[ ]`, which is correct before this verdict. The auditor writes only `audit.md`.
- PR checks, read on 2026-10-12. `gh pr checks 16` -> `feedback pass 15s`,
  `tests pass 15s`. `gh pr view 16 --json headRefOid,state` -> `headRefOid`
  `dc785003fa5ea3db0b3a95065d8499359e43d8e3`, `state` `OPEN`. The run logs:
  - `feedback` (run 38116192621) prints `harny-feedback: 2 of 2 command(s) ran, 0
    skipped.`;
  - `Tests` (run 38116192632) prints `890 passed`, with `sercop_source.py` 291
    statements, 1 missed (547).

  Both runs have `headSha` `dc78500`. They test the `1cd2f1e` code and tests, not the
  reviewed state. The checks are therefore **`unavailable`** for this round, not a pass
  (R-12).

### Conventions and feedback (round 4)

- `harny-standards`, against `AGENTS.md`: no violation.
  - The layer boundaries hold.
  - Raw responses are not overwritten, and no SERCOP contract is invented.
  - No dependency, infrastructure, framework or service was added.
  - No secret or dataset was added: markers, classes, statuses and defects are SYNTHETIC,
    and hosts are `.invalid`.
  - The executor reported its verification (O5e, O8d).
  - No attribution line appears in the added `src` or test lines (`grep` exit 1), or in
    the commit messages since `main` (count 0).
- `harny-feedback`: the CI `feedback` job has not run on the reviewed state (R-12). Its
  latest run, on `dc78500`, ran 2 of 2 commands. `ruff` and `mypy` were rerun here only
  as AC13 evidence. Whether the per-turn hook fired during O2e and O5e is `unavailable`,
  because the hook leaves no persistent log.

### Findings (round 4)

| Id | Severity | Finding and evidence | Closure condition | Status |
|---|---|---|---|---|
| F-8, F-9, F-10 | (round 3) | rechecked above | met | **Resolved** |
| F-11 | LOW (not blocking: no AC or binding constraint covers a code docstring; AC8 Revision 5) | `sercop_source.py` lines 14 to 17 (module docstring): "Every exception the adapter raises itself ... has no `__cause__` and no `__context__`". That is the Revision 4 wording that F-8 showed no code can meet. AC8 Revision 5 restates it for "this criterion or AC10", and the plan's reading rule covers "this plan", but neither covers the code's own docstring. Reproducer: the F-8 probe. `search_page` inside `except KeyError` raises an error whose `__context__` is the `KeyError`, which contradicts the docstring as written. O5e could not change it: O5e listed the only lines it could touch. No behavior is affected | The docstring states the I2 rule (for example "chains nothing from the call; a context the caller was already handling stays visible"), in a change the architect authorizes. Or the human accepts the wording as a note. Checked by reading | **Resolved** (round 4 addendum: O5f states I2; a remaining clause is F-13) |
| F-12 | LOW (not blocking; AC13 bookkeeping, the same kind as F-7 and F-10) | `tasks.md` § Status, line 12: "The Revision 5 changes to the three spec files and this file are uncommitted". `git show --stat dc78500` lists `intent.md`, `execution-plan.md`, `tasks.md` and `audit.md`, so that state was committed and pushed (PR #16 head `dc78500`). Line 11 ("Next: the human's approval of Revision 5 ...") is stale, and is marked superseded only by the later bullet on line 14. "Previous working state (architect, Revision 5 draft, 2026-10-10)" (line 567) says "Uncommitted: `audit.md` ... and the Revision 5 changes" and, unlike the entries before it, has no note that `dc78500` then committed that state | Whoever owns `tasks.md` records `dc78500` as committing the Revision 5 specs and the round 3 report. That record goes in § Status and as a note on the previous working state, as O7d did for `1cd2f1e`. Checked by reading | **Resolved** (round 4 addendum, O7e; a new stale reference is F-14) |

### Reservations (round 4)

- R-11: resolved as a documented rule (above).
- R-12 (new): the PR #16 `feedback` and `Tests` checks are `unavailable` for the reviewed
  state. Both pass on `dc78500`, whose `Tests` run shows `890 passed` on the `1cd2f1e`
  code. Before gate 3, after the human commits and pushes, confirm three things on the
  new head:
  - `Tests` prints `961 passed`;
  - `feedback` prints `2 of 2 command(s) ran` (not 0 of M);
  - both runs have that head's `headSha`.
- R-6 (carried, accepted risk): `ResponseStream.close()` is not mapped. The probe's `OSError`
  from the close propagates and still counts.
- R-7 (carried, accepted risk): `httpcore` writes header values at `DEBUG`.

### Notes (round 4)

- N-17: the D-1 drop covers every kind of read end (above). It is equivalent to the
  plan's flag form (m16 passes 961), and it leaves `_send`'s drop branch with no path
  (m17 passes 961; m19 fails 2). Three texts now describe the old place of the drop:
  - § Exit check K15: "escapes the hook and is dropped in `_send`";
  - the § Validation AC15 Revision 4 sentence: "the second of which reaches the drop
    ... in `_send`";
  - the comment in `_send` (lines 496 to 497).

  The behavior they bind holds. The architect may reword them at the next revision.
  Status: **closed** in the round 4 addendum (O7e and O5f place the drop in the hook's
  `finally`). The remaining "no path" wording is N-21.
- N-18: line 584 is unreachable, and line 590 is reachable only through a metaclass that
  overrides `__mro__`. In that case it writes the fixed `HTTPError` (above).
- N-19: `git diff --numstat 015a72b -- tests` prints `1756 37` with git's default diff
  algorithm. `--minimal`, `--patience` and `--histogram` all print `1719 0`, which is
  1073 + 646. The references that bind now, `1cd2f1e` and `19ab9c3`, print `646 0` and
  `1261 0` with the default algorithm. No line was deleted.
- N-20: a status from a test double that the interpreter cannot write (more than 4,300
  digits) still raises the interpreter's `ValueError` in rule 2. Row 1.2 and K19 record
  this, and it is caller code under AC15 Revision 5.

### Commands run in round 4 (all rerun, Windows, Python 3.13.9, `uv`, repository root)

| Command | Result |
|---|---|
| `git rev-parse HEAD`; `git status --short` | `dc785003fa5ea3db0b3a95065d8499359e43d8e3`; ` M` `tasks.md`, the adapter and its test file |
| `git diff --numstat 1cd2f1e -- tests`; `-- src`; `git diff --numstat 19ab9c3 -- tests`; `git diff --numstat 015a72b -- tests` (`myers`, `minimal`, `patience`, `histogram`) | `646 0`; `49 6` (adapter only); `1261 0`; `1756 37`, `1719 0`, `1719 0`, `1719 0` |
| `git diff --stat 1cd2f1e -- <domain, application, interfaces, tests/fixtures, docs, pyproject.toml, uv.lock, test_layers.py, test_source_response.py, README.md, CHANGELOG.md, .github, .sdd, .claude, .gitignore>`; `git diff --stat 1cd2f1e` | empty (exit 0); 6 files (4 specs, the adapter, the test file) |
| `uv sync --locked`; `uv lock --check` | `Checked 22 packages`; `Resolved 22 packages` |
| `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing` | `961 passed in 12.75s`; TOTAL 599/15/97%; `sercop_source.py` 300/2 (584, 590) |
| `uv run pytest tests -q -W error` | `961 passed` |
| `uv run pytest --collect-only -q tests` and the adapter file | 961; 778 |
| focused rows, in order: `search_success or query`, `record_success`, `raw_response or store_shape or cookie`, `out_of_range or no_results`, `status_error`, `transport`, `incomplete`, `no_leak` (both files), `invariant`, `invariant or transport_defect`, `pacing`, `timeout or accept_encoding or invalid` (both files), `documented_boundaries or non_ascii_base_path`, `exactly_value_error or invariant`, `no_network`, `layer or satisfies_port` (`tests/unit`), the AC15 `-k`, `memory_error`, `transport_defect`, the five O2e names together | 13, 4, 20, 4, 30, 48, 53, 357, 297, 319, 52, 245, 18, 358, 2, 9, 491, 4, 22 and 71, all passed |
| `--co -k` for each O2e test | 25, 28, 8, 8, 2 |
| `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy .` | `All checks passed!`; `76 files already formatted`; `Success: no issues found in 20 source files` |
| `uv run node .sdd/doctor/run-doctor.mjs`; `uv run ec-procurement-quality --version` | `31 ok, 0 skipped, 0 warned, 0 failed`; `ec-procurement-quality 0.1.0` |
| `git diff main -- pyproject.toml`; `git diff main --stat` (F1, `cli.py`, `__init__.py`); `git log --oneline -- tests/fixtures/sercop`; `git diff --check`; `git diff main --check` | only `httpx`; empty; `74b785d`; clean; clean |
| `git grep` checks: the real host in tests; the default URL in `src`; `except Exception` and `except BaseException`; `) from` and `raise ... from`; `suppress` and `from None`; `one thread at a time`; `logging`, `print`, `sys.std` and `warnings` in the adapter; `httpx` imports in `src`; `noqa` in `src`; `source.invalid` in the test file; attribution in the added lines and in the commit messages | exit 1; 1 match (`:58`); exit 1; exit 1; exit 1; 1 match (`:321`); exit 1; `:42` only; lines 128 and 267; 43; exit 1, 0 |
| The current tests against the `1cd2f1e` adapter (scratch copy from `git archive`, import path printed); and per group | `44 failed, 917 passed`; T5 25 passed, T6 28 failed, T7 8 failed, failing close 8 failed, chaining 2 passed |
| Scratch mutants (`r4/make_mutants.py`, `PYTHONPATH=<copy>/src`, import path printed): m11 `from None` on rule 4; m12 rule 4 inside `except LookupError`; m13 `type(failure).__name__`; m14 no `operator.index`; m15 unguarded close; m16 the flag form; m17 `_send` re-raises once a status was captured; m18 `except Exception` around the close; m19 m16 plus m17 | failures, of 961 in the suite: m11 8 (the 6 named T5 cases plus 2 T7 cases); m12 60 (the 6 named T5 cases, of 25); m13 28; m14 8; m15 8; m16 0; m17 0; m18 2 (the chaining test); m19 2 (`close-after-cut`) |
| Scratch probes `r4/probe_r4.py`, which covers F-8 (`except`, `finally`, `__exit__`, retry), F-9 (8 class shapes by 2 places by 2 operations), the `__mro__` metaclasses, the status variants, D-1 (10 read ends by 2 operations) and the docstring, and `r4/probe_r11.py` (re-entry and threads, 3 runs) | 370 checks, 0 violations; R-11 mixes as documented; guard attempts 0 |
| `.venv` interpreter with `-I`: `httpx.__all__`, the exported classes deriving from `httpx.HTTPError`, compared with the adapter's `_HTTPX_ERROR_CLASSES` | 69 names; 21 classes, the plan's list; equal sets |
| `gh pr checks 16`; `gh pr view 16 --json headRefOid,state`; `gh run view 38116192621 --log`; `gh run view 38116192632 --log`; `gh run view <id> --json headSha` | both `pass` on `dc78500`; `2 of 2 command(s) ran, 0 skipped`; `890 passed`; `dc78500` for both. These do not cover the reviewed state |

### Not verified in round 4, and why

- The PR #16 checks on the reviewed state: `unavailable`, because it is not committed
  (R-12).
- The 39 Revision 4 rows of § Exit check were not re-probed one by one. Their code is
  unchanged apart from the three Revision 5 statements, and round 3 confirmed them on the
  same installed packages.
- No real network, name resolution or TLS was used (offline by brief). The `h11` stack
  was not re-probed over `MockBackend`, because O5e changes no statement on that path
  other than the status read and the close. Both were probed with `MockTransport`.
- The R-11 thread case depends on scheduling. Events forced the interleaving in 3 runs.
- Whether the per-turn Stop hook fired during O2e and O5e is `unavailable` (no persistent
  log).

### Round 4 addendum (scoped re-check, 2026-10-12)

Scope: the text-only closure of F-11, F-12 and N-17 (O7e by the architect, O5f by the
executor), read-only, after gate 3. Reviewed state: HEAD `dc78500` plus the uncommitted
O2e tests and the O5e and O5f code, `audit.md`, `execution-plan.md` and `tasks.md`. Not a
new round: the round 4 verdict stands. All evidence below is `rerun` unless marked.

**O5f diff.** The executor's pre-O5f copy (`sercop_source.before.py`, scratch) is the
state round 4 reviewed: it equals my round 4 m17 mutant with the mutation undone, and it
gives `49 6` against `1cd2f1e`. Against it, the working file has three hunks only (`14,19c14,23`,
`496,497c500,504`, `589c596,597`), every changed line outside the docstring is a `#`
comment, and the AST minus the docstring is equal (`True`). 706 -> 714 lines. `git diff
--numstat 1cd2f1e -- src tests` -> `65 14`, `646 0`. **Holds.**

**F-11, sentence by sentence** (the paragraph at lines 14 to 23):
- "no `__cause__`", "`__context__` is only the exception the caller was handling ... or
  `None`", "nothing raised during that call or construction ... is reachable", "no `from`
  clause": hold. `r4/probe_r4.py` rerun: 370 checks, 0 violations, covering construction
  and calls inside `except`, `finally` and `__exit__`, and the retry. `git grep` for
  `) from`, `raise ... from`, `suppress` and `from None`: exit 1.
- "A reason found inside an `except` block is returned or flagged, and raised after the
  block": holds. Every `except` passes, returns or stores, and no `raise` sits inside one.
- "exactly one of the source errors, `ValueError` or `RuntimeError`, with fixed printable
  ASCII text": holds (I1, I3; the probe).
- "that starts with the operation or the parameter": **does not hold for one message.**
  `RuntimeError("the source adapter is closed")` (line 571) starts with neither. Plan I3
  names it as the one exception ("or it equals `the source adapter is closed`"). The
  Revision 4 text had the same clause, and round 4 missed it. This is F-13 below.
  Read literally, "creates and raises" also covers the internal `ValueError` of
  `_reject_json_constant` (line 658). It never leaves the adapter: a `NaN` body gives
  `IncompleteResponseError` with `__context__` `None` (probe).
- F-11's closure condition (the I2 rule stated, checked by reading) is met: **F-11
  resolved.**

**N-17**, each statement checked against `httpx` 0.28.1 in `.venv` and by probe:
- `Response.iter_raw` calls `self.close()` after the last chunk (`_models.py` line 959).
  `Response.close` sets `is_closed = True` before `self.stream.close()` (lines 969 to
  972). Probe: after a clean read, the stream's `close()` ran once, so the hook's
  `finally` close is a no-op. **Holds.**
- "(a failure of that earlier close is K14, rule 3)": holds for an `httpx.HTTPError`
  (probe: `(CloseError)`, all bytes). A non-`httpx` failure of that close is K14's
  pass-through, not rule 3 (probe: `KeyboardInterrupt` propagates). The parenthesis is
  short, and the K14 row it cites is right. See N-21.
- "an `httpx.HTTPError` from this close is dropped by the hook's `finally` itself,
  whatever way the read ended": holds (lines 541 to 544; D-1 probe rerun, 10 read ends
  by 2 operations, all as in round 4, next wait `[58.0]`).
- "A close exception of any other type ... with the read's exception as its `__context__`
  when that exception is still in flight": holds. Probe: a `Defect` read followed by an
  `OSError` close gives context `Defect`. A `ReadError` read followed by an `OSError` close
  gives context `None`, because the read's error was already handled.
- The note's figures: m16 -> `961 passed`; m17 -> `961 passed`; m19 -> `2 failed`
  (`close-after-cut-search`, `close-after-cut-record`); m15 -> `8 failed`. The "For
  example" wording of the flag form is in § Proposed approach (line 469). **Hold.**
- "`_send`'s drop ... no path reaches it with `httpx` 0.28.1" (plan note, K15 by
  reference, the AC15 sentence, and the `_send` comment "no error reaches this point"):
  true for `httpx`'s own code and for stream doubles. It is not true for every transport
  double. A transport that returns an `httpx.Response` subclass whose
  `has_redirect_location` raises an `httpx.HTTPError` reaches the branch after the hook:
  - with the current code, a `200` returns a `SearchPage` and a `404` raises
    `SourceStatusError` (the error is dropped, as § Outcome mapping Revision 4 says);
  - with m17, both raise `RemoteProtocolError`.

  My round 4 wording ("no path left") was the source of this claim. The behavior is the
  plan's, so this is a note (N-21), of the same kind as N-18.
- The texts now place the drop where the code has it. N-17's purpose is met: **N-17
  closed**, and the residual wording is N-21.

**N-18.** The fallback comment holds. A metaclass `__mro__` property returning
`(cls, object)` gives `... (HTTPError)`. A metaclass `mro()` method cannot reach the
fallback: the class is then not an `httpx.HTTPError` at runtime, and it propagates
uncaught through `_send` line 496. `httpx.HTTPError` is in `_HTTPX_ERROR_CLASSES`. Line
591 (`return ""`) carries no comment and no claim. Coverage misses: `591, 598`.

**F-12 and the rest of `tasks.md`.** The closure condition is met. § Status line 12
records `dc78500` as committing the Revision 5 specs and the round 3 report, and the
"Previous working state (architect, Revision 5 draft)" entry has the same kind of note
(line 686). The "Next" lines are marked superseded where they stand (lines 11, 14, 16).
§ Working state, § Checkpoint and the O7e and O5f records match `git status` and the
reruns (`961`, `646 0`, `65 14`, 706 -> 714, lines 325, 591 and 598). The historical
records (O5e, O8d, the previous states) keep their numbers, as the N-18 response states.
**F-12 resolved.** One new stale cross-reference was found: F-14 below.

**intent.md.** `git diff --stat -- specs/sercop-source-adapter/intent.md` is empty: O7e
did not touch it.

| Id | Severity | Finding and reproducer | Closure condition | Status |
|---|---|---|---|---|
| F-13 | LOW (not blocking: no AC or binding constraint covers a code docstring; plan I3) | `sercop_source.py` module docstring, lines 14 to 16: "with fixed printable ASCII text that starts with the operation or the parameter". Reproducer: `SercopSource(transport=httpx.MockTransport(h))`, `close()`, then `search_page(year=2025, buyer="a", page=1)` raises `RuntimeError('the source adapter is closed')`, whose first word is `the`. Plan I3 lists this exact text as the one exception | The sentence admits the closed-adapter message, for example "... or the parameter, or says that the adapter is closed". Optionally it also says "raises to its caller" instead of "creates and raises". A comment-only change, by the executor with the architect's text, AST equal. Checked by reading | **Resolved** (round 4 second addendum, O5g (a)) |
| F-14 | LOW (not blocking; AC13 bookkeeping, the same kind as F-12) | `tasks.md` § Finding responses, R-12 row, Evidence column: "§ Working state step 3". In the current § Working state, the R-12 confirmation is step 2 (line 668), and step 3 is the documentation step (line 669) | The reference names step 2, or no step number. Checked by reading | **Resolved** (round 4 second addendum, O7f; two new bookkeeping items are F-15 and F-16) |

Note N-21: "no path reaches `_send`'s drop with `httpx` 0.28.1" (the `_send` comment, the
plan's K15 note, the AC15 sentence, and `tasks.md` O7e and the N-17 response) is true
only for `httpx`'s own code. Caller code reaches the drop: a transport that returns a
`Response` subclass with a raising `has_redirect_location`. The behavior is the plan's,
and the reproducer is above. Suggested wording: "no path inside `httpx` 0.28.1 reaches
it; only caller code can (a `Response` subclass from the transport)". K15's parenthesis
can say "K14: rule 3 for an `httpx.HTTPError`, pass-through otherwise". Not blocking.
Status: **closed** in the round 4 second addendum (O7f and O5g (b)). The remaining
wording is N-22.

Commands rerun for this addendum (Windows, Python 3.13.9, `httpx` 0.28.1):
- `git rev-parse HEAD` -> `dc785003...`.
- `git status --short` -> ` M` for `audit.md`, `execution-plan.md`, `tasks.md`, the
  adapter and its test file.
- `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing` -> `961 passed`.
  `sercop_source.py` 300/2 (`591, 598`); TOTAL 599/15/97%.
- `uv run ruff check .` -> `All checks passed!`.
- `uv run ruff format --check .` -> `76 files already formatted`.
- `uv run mypy .` -> `Success: no issues found in 20 source files`.
- `git diff --check` -> exit 0.
- The four `git grep` checks -> exit 1, exit 1, exit 1, and `:325`.
- Mutants (`r4b/mut`, built from the current file; import path printed): m15 `8 failed`;
  m16 `961 passed`; m17 `961 passed`; m19 `2 failed`.
- Probes: `r4/probe_r4.py` -> 370 checks, 0 violations, 0 guard attempts.
  `r4b/probe_addendum.py` -> the results above, 0 guard attempts. Against m17 it gives
  `RemoteProtocolError` for both late-error cases.

Unchanged: R-12 stays open until the human commits and pushes and the PR #16 checks are
confirmed on the new head. The verdict stays **APPROVED WITH RESERVATIONS**, with no
blocking item. Next role: the architect, if the human wants F-13, F-14 and N-21 closed
before the commit (text only; F-13 through the executor). Otherwise the human commits
and pushes.

### Round 4 second addendum (scoped re-read, 2026-10-12)

Scope: the text that answers the first addendum (O7f by the architect, O5g by the
executor), read-only, approved by the human on 2026-10-12. Reviewed state: HEAD
`dc78500` plus the uncommitted O2e tests, the O5e, O5f and O5g code, `execution-plan.md`
and `tasks.md`. Not a new round: the round 4 verdict stands. Evidence is `rerun` unless
marked. Stopping rule agreed with the human: new items are filed with exact wording,
the architect applies them, and the conductor verifies them mechanically, with no
further audit read.

**O5g diff.** The executor's pre-edit copy (`sercop_source.pre.py`, scratch) is the
file the first addendum reviewed: undoing my addendum m17 mutation gives it exactly
(`True`). Against it, the working file has two hunks only (`14,16c14,17` and
`501,504c502,506`). The AST minus the docstring is equal (`True`), every changed line
outside the docstring is a `#` comment, the new lines are at most 80 characters, and
the file has no CR. It went from 714 to 716 lines. **Holds.**

**F-13, sentence by sentence** (docstring lines 14 to 24). I triggered every raise site
(26 cases), both outside and inside a caller's `except KeyError`. That covers the 12
construction checks, the 6 call-input checks, the request URL that is too long, the
closed adapter, and rules 1 to 5, including a `NaN` body:
- "creates and raises to its caller ... exactly one of the source errors, `ValueError` or
  `RuntimeError`, with fixed printable ASCII text": holds in all 52 checks. The internal
  `ValueError("a constant that RFC 8259 does not allow")` of `_reject_json_constant`
  (line 660) is caught at line 674. The `NaN` body gives `IncompleteResponseError`, with
  `__context__` `None` outside an `except` and the caller's `KeyError` inside one, so
  "to its caller" correctly leaves the internal error out.
- "starts with the operation or the parameter, or it is exactly `the source adapter is
  closed`": holds. Every message starts with `search_ocds:`, `record:` or one of the 14
  parameter names, except `RuntimeError('the source adapter is closed')` (line 573),
  which is now admitted word for word.
- "no `__cause__`", the context rule, and "no `from` clause": hold. `__cause__` is
  `None` and `__suppress_context__` is false everywhere. The context is `None` outside an
  `except` and the caller's object inside one. `r4/probe_r4.py` rerun: 370 checks, 0
  violations. `git grep` for `) from` or `raise .* from`, and for `suppress` or
  `from None`: exit 1 both.
- **F-13 resolved.**

**N-21.** Checked against `httpx` 0.28.1 in `.venv`, the code, and `r4c/probe_r4c.py`:
- `_send_handling_redirects` (`_client.py` lines 979 to 999) runs the response hooks
  inside the `try` that starts at line 980, then sets `response.history` (983), then
  reads `has_redirect_location` (985). "Reads that property after the response hook,
  inside its `try`" holds.
- The `_send` comment (lines 501 to 506), the second K15 note, the AC15 sentence and the
  § Risks row all hold. With a `Response` subclass whose `has_redirect_location` raises
  `httpx.RemoteProtocolError`, a search `200` returns the AC1 `SearchPage` (`3/1/1/3`,
  same bytes), and a search `404` raises `SourceStatusError` with the complete body,
  with `__cause__` and `__context__` both `None`. Under m17 both raise
  `RemoteProtocolError`. m17 passes all 961 tests and m19 fails the 2 `close-after-cut`
  cases (both rerun, with the import path printed).
- The K15 parenthesis "K14: rule 3 for an `httpx.HTTPError`, pass-through for any other
  exception" holds (`r4c/probe_k14.py`). A failing close inside `iter_raw` after the
  whole body gives `(CloseError)` with all bytes; with `KeyboardInterrupt` the same
  object propagates; the stream is closed once.
- **The record-call case in the `tasks.md` N-21 row holds** (probed). A `200` with the
  AC2 fixture returns `RecordResponse` (`ocid` `ocds-5wno2w-SYNTHETIC-A`, 1 release,
  same bytes). A `404` raises `SourceStatusError` with the complete body and no chain.
  Under m17 both raise `RemoteProtocolError`. The row's "the auditor did not probe it"
  is now out of date. That is expected bookkeeping, not a finding.
- **N-21 closed.** The residue is N-22 below: a second caller-code point exists.

**F-14, F-12 and the rest of `tasks.md`.** The R-12 row's Evidence column now names the
step by what it does, with no number. **F-14 resolved.** § Status (lines 3 to 33), the
current and previous § Working state entries, § Checkpoint and § Finding responses
otherwise match `git status` and the reruns:
- `961`; `646 0` and `67 14`; 714 -> 716 lines;
- misses at `593, 600`; `one thread at a time` at `:326`; the closed-adapter text at
  `:17` and `:573`;
- O7e, O5f, O7f and O5g, and steps 1 to 3 of the current § Working state.

F-12's closure still holds. The "auditor has not re-checked O7f or O5g" lines (§ Status
line 32, § Working state lines 732 and 742, § Checkpoint lines 832 and 836) are true up
to this addendum. Updating them is the next bookkeeping step. Two stale statements
remain, F-15 and F-16.

**intent.md.** `git diff --stat -- specs/sercop-source-adapter/intent.md` is empty.

| Id | Severity | Finding and reproducer | Closure condition | Status |
|---|---|---|---|---|
| F-15 | LOW (not blocking; AC13 bookkeeping, the same kind as F-12 and F-14) | `tasks.md` § Finding responses, R-12 row, Response column: "After the human commits and pushes the O2e tests, the O5e code and O5f, confirm on the new head ...". It omits O5g. § Status line 25 lists "the O2e tests, the O5e code, O5f and O5g" | Replace "the O2e tests, the O5e code and O5f, confirm" with "the O2e tests, the O5e code, O5f and O5g, confirm". Checked mechanically (`grep -n "O5f and O5g, confirm" tasks.md`) | Open |
| F-16 | LOW (not blocking; AC13 bookkeeping) | `tasks.md` O7f record, line 664: "no other row or record cites a numbered step." The F-10 record of the Revision 4 working state (line 773, "step 2 above then happened"), written by the architect in O7d, does, and the F-14 row (line 825) lists it | Replace that bullet with "the other "step 2" mentions are the call order of plan § Request format, or the F-10 record of the Revision 4 working state, and are right." Checked mechanically (the old sentence is gone, by `grep -n "no other row or record"`) | Open |

Note N-22 (not blocking, wording only): the AC15 sentence ("Only caller code can: a
transport that returns a `Response` subclass whose `has_redirect_location` raises an
`httpx.HTTPError`") and the § Risks N-21 row ("Caller code can: a transport that returns
a `Response` subclass whose `has_redirect_location` raises") give one path as if it were
the only one. A `Response` subclass whose `history` setter raises an `httpx.HTTPError`
on its second set (`_client.py` line 983, after the hook) also reaches `_send`'s drop.
The outcomes are the same: `SearchPage` or `RecordResponse` for a `200`,
`SourceStatusError` for a `404`, and `RemoteProtocolError` under m17 (probe). The `_send`
comment ("a transport may return") and the second K15 note ("The reproducer is") are
already worded as examples. Corrected wording, `execution-plan.md` only:
- AC15: "Only caller code can, for example a transport that returns a `Response`
  subclass whose `has_redirect_location` raises an `httpx.HTTPError`."
- § Risks: "Caller code can, for example a transport that returns a `Response` subclass
  whose `has_redirect_location` raises."

Checked mechanically: `grep -c "Caller code can, for example\|Only caller code can, for
example" execution-plan.md` gives 2.

Commands rerun for this addendum (Windows, Python 3.13.9, `httpx` 0.28.1):
- `git rev-parse HEAD` -> `dc785003...`. `git status --short` -> ` M` for `audit.md`,
  `execution-plan.md`, `tasks.md`, the adapter and its test file.
- `uv run pytest -q` -> `961 passed`. The coverage command -> `961 passed`;
  `sercop_source.py` 300/2 (`593, 600`); TOTAL 599/15/97%.
- `uv run ruff check .` -> `All checks passed!`. `uv run ruff format --check .` -> `76
  files already formatted`. `uv run mypy .` -> `Success: no issues found in 20 source
  files`. `git diff --check` -> exit 0.
- `git diff --numstat 1cd2f1e -- src tests` -> `67 14` (adapter only) and `646 0`.
  `git diff --stat -- .../intent.md` -> empty.
- `git grep`: `except Exception` or `except BaseException` -> exit 1; `) from` or
  `raise .* from` -> exit 1; `suppress` or `from None` -> exit 1; `one thread at a time`
  -> `:326`; `the source adapter is closed` -> `:17`, `:573`.
- Scratch, `.venv` Python with `-I`, sockets blocked: `cmp.py` (AST and hunks), `r4b/unmut.py`
  (the pre-edit copy equals the reviewed file), `r4c/probe_r4c.py` (52 raise-site checks
  and 8 late-error cases, 0 violations; against m17, 8 `RemoteProtocolError`),
  `r4c/probe_k14.py`, and `r4/probe_r4.py` (370 checks, 0 violations). Guard attempts 0.
- Mutants against the suite (`PYTHONPATH`, import path printed): m17 `961 passed`; m19
  `2 failed, 959 passed`.

Unchanged: R-12 stays open until the human commits and pushes and the PR #16 checks are
confirmed on the new head. The verdict stays **APPROVED WITH RESERVATIONS**, with no
blocking item. Next role: the architect, for the text of F-15, F-16 and N-22, verified
mechanically by the conductor. Then the human commits and pushes (R-12).

## Audit log

| Round | Date | Verdict | Notes |
|---|---|---|---|
| 1 | 2026-10-10 | REJECTED | Reviewed `015a72b` plus the uncommitted doc and `tasks.md` edits. 453 passed, 97% coverage. AC1 to AC8 and AC11 to AC15 PASS; AC9 and AC10 PARTIAL. Blocking: F-1 (MEDIUM, a zero-padded `Remaining` of more than 4,300 digits is ignored) and F-2 (MEDIUM, spec gap: base URLs that pass construction fail on every call). Non-blocking: F-3 and F-4 (LOW). Reservations R-1 to R-6. `InvalidURL` rule: met by the code, not anchored by any test (mutants m1 and m2 pass). Tier Results: unit PASS, mypy PASS, command PASS, manual AC14 PASS, manual AC15 PARTIAL. CI on the audited state `unavailable`. Next role: architect. |
| 2 | 2026-10-10 | REJECTED (superseded by round 3) | Reviewed `19ab9c3` (intent and plan Revision 3; O2c, O5c, O7b, O8b), with a clean tree. 569 passed locally and in CI; adapter coverage 99% (171-172 missed). Resolved: F-1, F-2, F-3, F-4, R-1 (mutants m1 and m2 now fail the no-chain test), R-3, R-4, R-5. AC1 to AC7, AC9 and AC11 to AC14 PASS; AC8, AC10 and AC15 PARTIAL. § Family check: 42 of 43 rows hold, and row 2.9 has a gap. Blocking: F-5 (MEDIUM, a non-ASCII IPv6 zone raises a raw `UnicodeEncodeError` with the host text instead of the fixed reason) and F-6 (MEDIUM, spec gap: the chained `httpx` exception quotes body bytes or header lines that `h11` rejected). Non-blocking: F-7 (LOW, stale spec and `tasks.md` text). Reservations R-2, R-6 to R-10. Tier Results: unit PARTIAL, mypy PASS, command PASS, manual AC14 PASS, manual AC15 PARTIAL. PR #16 `feedback` and `tests` pass on `19ab9c3`. Next role: architect (F-6 decision; F-5 case in § Validation; F-7). |
| 3 | 2026-10-10 | REJECTED (superseded by round 4) | Reviewed `1cd2f1e` (intent and plan Revision 4; O2d, O5d, O8c), with a clean tree. 890 passed locally (also with `-W error`) and in CI. Adapter coverage 99%: line 547 missed, unreachable. Resolved: F-5, F-6 (16 malformed framings through the real `h11` stack, nothing chained), F-7, R-2 (m2c now fails), R-8, R-9 and R-10. Mutants m1, m2, m2b and m2c and 8 new ones each fail tests. Red for O2d reproduced: `65 failed`. AC1 to AC7 and AC9 to AC15 PASS; AC8 PARTIAL. § Exit check: all 39 rows hold. § Output invariant: I1 holds; I2 does not hold for a call made inside the caller's exception handler (F-8); I3 and I4 do not hold for a class name chosen by an injected transport (F-9). Blocking: F-8 and F-9 (LOW, spec gaps; no response content leaks). Non-blocking: F-10 (LOW, stale text). Reservations: R-11 (new: a shared instance can mix evidence under concurrent or re-entrant use), R-6 and R-7 (accepted). Tier Results: unit PASS, mypy PASS, command PASS, manual AC14 PASS, manual AC15 PARTIAL. PR #16 `feedback` (2 of 2 commands) and `tests` (890 passed) pass on `1cd2f1e`. Next role: architect (F-8 wording; F-9 decision; F-10; optionally R-11 in § Consumers). |
| 4 | 2026-10-12 | APPROVED WITH RESERVATIONS (current) | Reviewed `1cd2f1e` plus the uncommitted O2e tests (`646 0`), the O5e code (`49 +, 6 -`) and `tasks.md`, at HEAD `dc78500` (intent and plan Revision 5). 961 passed (also with `-W error`). Adapter coverage 99%: lines 584 and 590 missed, both defensive. Red for O2e reproduced against `1cd2f1e`: `44 failed, 917 passed` (T5 0, T6 28, T7 8, failing close 8, chaining 0). Resolved on the exact round 3 inputs: F-8, F-9, F-10, R-11. Mutants m11 and m12 each fail the 6 T5 cases that § Validation names (whole suite 8 and 60); m13 fails 28, m14 8, m15 8, m18 2; m16 (the plan's flag form) and m17 (no `_send` drop branch) pass all 961, because they are behavior-equivalent; m19 (both together) fails 2. AC1 to AC15 PASS. § Statement check: all 25 rows hold. § Exit check: the Revision 5 rows (K13, K14a, K19, R, CC) hold. § Output invariant: I1 to I4 hold at all 20 raise sites. The family check found no new gap. Non-blocking: F-11 (LOW, the module docstring keeps the Revision 4 "no `__context__`" wording) and F-12 (LOW, stale `tasks.md` § Status lines). Reservation R-12: the PR #16 checks are `unavailable` for the reviewed state. They pass on `dc78500`, but that run tested the `1cd2f1e` code (`890 passed`). R-6 and R-7 are accepted. Tier Results: unit PASS, mypy PASS, command PASS, manual AC14 PASS, manual AC15 PASS. Next role: the human (commit and push, confirm the PR checks on the new head, gate 3). F-11 and F-12 can be closed in the same commit, or later through the architect. |
| 4 (addendum) | 2026-10-12 | APPROVED WITH RESERVATIONS (unchanged; scoped read-only re-check) | Rechecked O7e and O5f at HEAD `dc78500`, with O2e, O5e and O5f uncommitted. O5f is comments and the docstring only: AST equal apart from the docstring, against the executor's pre-O5f copy, which equals the round 4 reviewed file. `65 14` and `646 0`; 961 passed; `ruff`, `ruff format --check`, `mypy` and `git diff --check` clean. Resolved: F-11, F-12. Closed: N-17 (the drop is now placed in the hook's `finally`; `httpx` source and probes confirm K15; m16 and m17 pass 961, m19 fails 2). The N-18 comment holds. `intent.md` is unchanged. New, not blocking: F-13 (LOW, the docstring clause "starts with the operation or the parameter" omits `the source adapter is closed`), F-14 (LOW, `tasks.md` R-12 row cites "§ Working state step 3", which is step 2), and N-21 (note: a transport that returns a `Response` subclass reaches `_send`'s drop, so "no path" holds only for `httpx`'s own code). R-12 open. Next role: the architect, for F-13, F-14 and N-21 if the human wants them closed before the commit; otherwise the human commits and pushes. |
| 4 (second addendum) | 2026-10-12 | APPROVED WITH RESERVATIONS (unchanged; scoped read-only re-read) | Rechecked O7f and O5g at HEAD `dc78500`, with O2e, O5e, O5f and O5g uncommitted. O5g is two hunks, docstring and comments only. Its AST is equal apart from the docstring, against the executor's pre-edit copy, which equals the reviewed file. `67 14` and `646 0`; 961 passed; `ruff`, `ruff format --check`, `mypy` and `git diff --check` clean; `intent.md` unchanged. Resolved: F-13 (every raise site probed, 52 checks, 0 violations) and F-14. Closed: N-21. The `has_redirect_location` reproducer gives `SearchPage` or `RecordResponse` for a `200` and `SourceStatusError` for a `404`; the record-call case of the `tasks.md` N-21 row holds. m17 gives `RemoteProtocolError`, passes 961; m19 fails 2. New, not blocking, with exact wording for the architect, verified mechanically, no further read: F-15 (LOW, the R-12 row omits O5g), F-16 (LOW, the O7f record says no other record cites a numbered step), and N-22 (note, a `history` setter is a second caller-code path; "for example" in the AC15 sentence and the § Risks row). R-12 open. Next role: the architect (F-15, F-16, N-22), then the human commits and pushes. |
