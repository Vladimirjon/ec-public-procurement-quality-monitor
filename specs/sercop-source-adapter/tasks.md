# Tasks: SERCOP source adapter (F2)

## Status
Intent Revision 2 approved by the human on 2026-10-10 (Revision 1 was approved at gate 1 on the same day, which also accepted ADR 0006, the fixtures in `tests/fixtures/sercop/` and the series of 2026-10-10 in `docs/sources/sercop-observations.md`). O1 to O5 were done under Revision 1. The human's Day 13 review of the adapter found spec gaps, so the specs were revised (Revision 2) instead of working around them in code. O2b (the Revision 2 red tests) was written and approved by the human at gate 2 on 2026-10-10, and O5b made them green (453 tests passed, none edited). Next: the human re-reads the blocks of `infrastructure/sercop_source.py` that Revision 2 changed, then O6 to O8 (executor) and the O9 audit. The plan's rule that the library's `InvalidURL` is never chained into a raised error has no test; it is checked at the O9 audit.

## Baseline
- Base commit: `fff0f2d` (`main`, "Merge pull request #15 from Vladimirjon/feat/raw-evidence-store").
- Branch: `feat/sercop-source-adapter`. The working tree at drafting time held, uncommitted: `docs/sources/sercop-observations.md` (modified), `docs/adr/0006-http-client-for-source-access.md` (new), `tests/fixtures/sercop/` (new), and these three spec files.
- Interpreter: Python 3.13.9 (`.venv\Scripts\python.exe --version`), uv 0.12.23.
- Cwd: the repository root, `ec-public-procurement-quality-monitor`.
- Commands:
  - Install: `uv sync --locked`
  - Test: `uv run pytest` (CI form: `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing`)
  - Lint and format: `uv run ruff check .` and `uv run ruff format --check .`
  - Type check: `uv run mypy .`
  - Readiness: `uv run node .sdd/doctor/run-doctor.mjs`
- Pre-existing failures: none. On 2026-10-10 at `fff0f2d`, measured by the architect:
  - `uv run pytest -q` -> `137 passed`.
  - `uv run ruff check .` -> `All checks passed!`.
  - `uv run ruff format --check .` -> `67 files already formatted`.
  - `uv run mypy .` -> `Success: no issues found in 15 source files`.
  - `git grep -n -i -e datosabiertos -e compraspublicas -- tests` -> no match.
  - `uv run node .sdd/doctor/run-doctor.mjs` -> `31 ok, 0 skipped, 0 warned, 0 failed` (run with these three spec files in place).
- Revision 2 baseline (2026-10-10, measured by the architect): HEAD `59be7df` with the uncommitted O1 to O5 working tree (`pyproject.toml`, `uv.lock`, the three F2 modules, the two new test files, `tests/unit/test_layers.py`, this file). `uv run pytest -q` -> `388 passed`.

## Outcomes
Order and ownership:
1. **O1 (executor) first**, before any red test: add the dependency, so the red tests fail because the F2 modules are missing, not because `httpx` is.
2. **O2 (test-writer)** writes the red tests for O3 to O5 (files and `-k` names from `execution-plan.md` § Proposed approach) and fills their Tests and Red lines.
   - The correct red reason is that a pinned F2 module does not exist yet: `ModuleNotFoundError` for `ec_procurement_quality.domain.source_response`, `ec_procurement_quality.application.procurement_source` or `ec_procurement_quality.infrastructure.sercop_source`.
   - For the new layer check, the reason is `AssertionError` saying `infrastructure/sercop_source.py` is missing.
   - A typo in a test, or a missing `httpx`, is never a correct red reason.
   - The human reviews the red tests at gate 2.
3. **O3 to O5 (executor)**, in that order. Each relies only on the names, signatures and rules in `execution-plan.md` § Binding constraints. Every `httpx` signature is confirmed against `.venv/Lib/site-packages/httpx/`; no MCP is used.
4. Revision 2, after the human approves it: **O2b (test-writer)** writes the Revision 2 tests, red against the O5 code, and the human reviews them. Then **O5b (executor)** turns them green without editing any test.
5. Then **O6 to O8 (executor)** and **O9 (auditor)**.
6. No role creates or edits the fixture files, ADR 0006 or the F1 modules. If a fixture seems wrong, stop and report it.

- [x] **O1** (AC13) — executor: add `httpx` as the first runtime dependency with `uv add httpx`.
  - Done when:
    - `[project] dependencies` holds only the `httpx` entry that `uv` wrote, and `uv.lock` is updated.
    - `uv lock --check` and `uv sync --locked` exit 0.
    - `git diff main -- pyproject.toml` shows only that line.
    - The 137 baseline tests still pass, and `uv run ruff check .`, `uv run ruff format --check .` and `uv run mypy .` exit 0.
    - The resolved `httpx` version and its transitive packages are recorded here.
  - Evidence (2026-10-10, branch `feat/sercop-source-adapter`, HEAD `59be7df`, uv 0.12.23, Python 3.13.9):
    - `uv add httpx` -> exit 0; `pyproject.toml` and `uv.lock` are the only files changed (`git status --short`).
    - `git diff main -- pyproject.toml` -> only `dependencies = []` becomes `dependencies = [` / `"httpx>=0.28.1",` / `]`. The `dev` group, build system and tool sections are untouched.
    - Resolved: `httpx==0.28.1`. Packages added to `uv.lock`: `anyio==4.15.1`, `certifi==2026.7.22`, `h11==0.16.0`, `httpcore==1.0.9`, `httpx==0.28.1`, `idna==3.20`. `typing-extensions==4.16.0` was already locked; the diff only adds an `anyio` edge to it. `httpx` imports no other package in this resolution (no `h2`, `brotli`, `zstandard`, `socksio`, `click`, `rich`).
    - `uv lock --check` -> exit 0 (`Resolved 22 packages`). `uv sync --locked` -> exit 0 (`Checked 22 packages`).
    - `uv run pytest -q` -> `137 passed` (same as baseline).
    - `uv run ruff check .` -> `All checks passed!`. `uv run ruff format --check .` -> `70 files already formatted`, exit 0 (the baseline said 67; no `.py` file changed since `fff0f2d`; the three extra files were not identified, and `ruff` reports no failure).
    - `uv run mypy .` -> `Success: no issues found in 15 source files`.
    - Installed `httpx/` 0.28.1 read directly (no MCP). The plan-evidence items hold, with the notes recorded in the report of this run: `StreamConsumed` derives from `RuntimeError` (via `StreamError`), not from `httpx.HTTPError`; `httpx` itself logs `HTTP Request: ...` at INFO on the `httpx` logger; per-request `cookies=` is deprecated (a client-level jar is the supported route).
- [x] **O2** (AC1 to AC12) — test-writer: the red tests.
  - Files: `tests/unit/test_source_response.py` and `tests/unit/test_sercop_source.py` (new), with the network guard, and `tests/unit/test_layers.py` (new check `test_layer_only_infrastructure_imports_httpx`).
  - Synthetic bodies are labelled as synthetic. `search_no_results.json` is labelled inferred. Fixtures are read only.
  - Tests (251 new, 2026-10-10; 137 baseline plus 251 = 388 collected once the F2 modules exist):
    - `tests/unit/test_source_response.py` (new, 45 tests): `RawResponse` valid values, equality, immutability (6 cases); `invalid` (13 `ValueError` cases and 2 `TypeError` cases for `content`, 2 for the required `response` keyword of two errors); the error hierarchy and `response` attribute (AC10 domain part); `no_leak` for `repr` and `str` of `RawResponse` and of the four errors (AC8).
    - `tests/unit/test_sercop_source.py` (new, 205 tests) with the autouse network guard, fake `monotonic`, `sleep` and `now`, and `httpx.MockTransport` built with `stream=`:
      - AC1 `query` (7) and `search_success` (3);
      - AC2 `record_success` (4);
      - AC3 `raw_response` (6), `store_shape` (9: success, synthetic `429`, cut-off, three sequences each) and `cookie` (3);
      - AC4 `out_of_range` (3) and `no_results` (1, labelled INFERRED);
      - AC5 `status_error` (18: 9 statuses by 2 operations);
      - AC6 `transport` (16);
      - AC7 `incomplete` (43: 25 search and 18 record bodies);
      - AC8 `no_leak` (12: 6 scenarios by 2 operations; also 5 `no_leak` tests in `test_source_response.py`);
      - AC9 `pacing` (33: 30 parametrized sequences plus 3 tests);
      - AC10 `timeout` (4), `accept_encoding` (2) and `invalid` (32 call and construction cases; plus 5 construction-boundary cases and 1 `close` case that carry no `-k` token);
      - AC11 `no_network` (2: the default-transport proof and a direct proof of the four patched socket paths);
      - AC12 `satisfies_port` (1).
    - `tests/unit/test_layers.py`: one new test, `test_layer_only_infrastructure_imports_httpx`; the 6 existing tests are unchanged.
  - Red (2026-10-10, `.venv`, `httpx` 0.28.1; nothing under `src/`, fixtures or F1 changed):
    - `uv run pytest tests/unit/test_source_response.py -q` -> 1 error at collection: `ModuleNotFoundError: No module named 'ec_procurement_quality.domain.source_response'`.
    - `uv run pytest tests/unit/test_sercop_source.py -q` -> 1 error at collection: `ModuleNotFoundError: No module named 'ec_procurement_quality.application.procurement_source'`. It is the first of three missing modules that file imports; `importlib.util.find_spec` returns `None` for all of `domain.source_response`, `application.procurement_source` and `infrastructure.sercop_source`.
    - `uv run pytest tests/unit/test_layers.py -q` -> `1 failed, 6 passed`: `AssertionError: infrastructure needs sercop_source.py (... is missing)`.
    - `uv run pytest -q --ignore tests/unit/test_source_response.py --ignore tests/unit/test_sercop_source.py` -> `1 failed, 137 passed` (the 137 baseline tests still pass; the one failure is the new layer check).
    - `uv run mypy .` -> 4 errors, all `import-untyped` on the three missing F2 modules (expected in red). `uv run ruff format --check tests/unit` clean. `uv run ruff check tests/unit` -> 2 `I001` (one per new test file): ruff 0.16.10 treats an import of a module that does not exist yet as third party; checked on a scratch copy that the same files pass `ruff check` and `mypy` once the three modules exist. The import order written is the one for the final state.
    - Test logic checked outside the repository, against a scratch reference implementation of the three modules (never under `src/`): 257 tests of the three files pass, `uv run mypy` on the tests is clean, and 19 deliberately broken variants of the adapter each fail at least one test. This is evidence about the tests only, not an implementation for O3 to O5.
    - `git grep -n -i --untracked -e datosabiertos -e compraspublicas -- tests` -> no match (exit 1).
- [x] **O3** (AC3, AC8, AC10, AC12) — executor: `src/ec_procurement_quality/domain/source_response.py`.
  - It holds `RawResponse` (the pinned attributes and validation; `repr` and `str` without content or header values) and `SourceError`, `SourceTransportError`, `SourceStatusError` and `IncompleteResponseError`, each with `response`.
  - Standard library only; passes strict `mypy`.
  - Tests: `tests/unit/test_source_response.py`
  - Green: `uv run pytest tests/unit/test_source_response.py -q` -> `45 passed`; `uv run mypy .` -> `Success: no issues found in 20 source files` (strict `domain` flags apply).
- [x] **O4** (AC1, AC2, AC4, AC12) — executor: `src/ec_procurement_quality/application/procurement_source.py`.
  - It holds `SearchPage` (with `is_beyond_last_page`), `RecordResponse` and the `ProcurementSource` protocol, exactly as pinned.
  - It imports only the standard library and `domain`.
  - Tests: covered by `tests/unit/test_sercop_source.py` and `tests/unit/test_layers.py`
  - Green: `uv run pytest tests/unit/test_sercop_source.py -q` -> `205 passed`; `uv run pytest tests/unit -q -k "layer or satisfies_port"` -> `9 passed, 379 deselected`.
- [x] **O5** (AC1 to AC11, AC12) — executor: `src/ec_procurement_quality/infrastructure/sercop_source.py`, with `DEFAULT_BASE_URL` and `SercopSource`.
  - Request format: URL built with `quote(..., safe="")`; `Accept-Encoding: identity`; no cookies; no redirects; one request per call; the pinned timeouts.
  - Response capture: streamed raw bytes, Latin-1 headers in order, `now()` once per response.
  - The closed outcome mapping and the completeness checks.
  - Pacing through the injected `monotonic` and `sleep`.
  - No logging, and no `JSONDecodeError` or `UnicodeDecodeError` in error chains.
  - `close()` and context manager.
  - Tests: `tests/unit/test_sercop_source.py`
  - Green (2026-10-10, `.venv`, `httpx` 0.28.1): AC1 `-k "search_success or query"` -> 11 passed; AC2 `-k record_success` -> 4 passed; AC3 `-k "raw_response or store_shape or cookie"` -> 18 passed; AC4 `-k "out_of_range or no_results"` -> 4 passed; AC5 `-k status_error` -> 18 passed; AC6 `-k transport` -> 17 passed; AC7 `-k incomplete` -> 43 passed; AC8 `tests/unit/test_source_response.py tests/unit/test_sercop_source.py -k no_leak` -> 17 passed; AC9 `-k pacing` -> 33 passed; AC10 `-k "timeout or accept_encoding or invalid"` over both files -> 64 passed; AC11 `-k no_network` -> 2 passed; AC12 `tests/unit -k "layer or satisfies_port"` -> 9 passed. Whole suite `uv run pytest -q` -> `388 passed` (137 baseline + 251 new). `uv run ruff check .` -> `All checks passed!`; `uv run ruff format --check .` -> `75 files already formatted`; `uv run mypy .` -> `Success: no issues found in 20 source files`; `git diff --check` clean; `git grep -n --untracked "datosabiertos.compraspublicas.gob.ec/PLATAFORMA" -- src` -> one match (`DEFAULT_BASE_URL`); `git grep -n -i --untracked -e datosabiertos -e compraspublicas -- tests` -> no match (exit 1). Left for O6 to O8: docs, doctor, CLI version, `uv sync --locked`.
- [x] **O2b** (AC5, AC6, AC9, AC10, AC15; Revision 2) — test-writer: the Revision 2 tests in `tests/unit/test_sercop_source.py` only. `tests/unit/test_source_response.py` and `tests/unit/test_layers.py` do not change. Bodies, credentials and defects are synthetic and labelled so; URLs use `.invalid` or a numeric host that is never contacted. Add cases and tests only; change or remove no existing case.
  - Tests to add (names fixed, because the `-k` commands in `execution-plan.md` § Validation select them; case ids suggested):
    1. `STATUS_CASES`, four cases with body `b"synthetic redirect body"`: `302-location-not-starting-with-slash` (`Location: https:abc`), `302-location-with-a-tab` (`Location: /synthetic\tpath`), `307-location-with-an-invalid-ipv4-host` (`Location: http://999.1.1.1/`), `301-location-longer-than-the-url-limit` (`Location: "/" + "a" * 65_530`). They run in `test_status_error_carries_the_complete_response` for both operations (8 cases).
    2. `test_transport_invalid_status_is_a_transport_error_without_response`, parametrized by operation and status `99`, `600`, `999` (6 cases), as in the AC6 row.
    3. `PACING_CASES`, two cases: `an-invalid-status-with-low-remaining-waits-the-cool-down` (`600`, `Remaining: 5`, then `(58.0,)`) and `an-invalid-status-without-a-rate-limit-header-waits-the-minimum-interval` (`600`, then `(3.0,)`).
    4. `test_pacing_counts_an_attempt_that_ends_in_an_unmapped_exception`, four cases as in the AC9 row, with a test-local `class SyntheticTransportDefect(Exception)`.
    5. `test_transport_defect_from_an_injected_transport_propagates_unchanged`, two cases (before the status; from the body stream after one chunk), as in the AC15 row.
    6. `test_invalid_construction_options_raise_value_error`, 13 cases: `base-url-with-user-and-password` (`https://synthetic-user:synthetic-secret@source.invalid/PLATAFORMA`), `base-url-with-user-only`, `base-url-with-empty-userinfo` (`https://@source.invalid/PLATAFORMA`), `base-url-port-without-host` (`https://:8443/PLATAFORMA`), `base-url-port-not-numeric` (`:abc`), `base-url-port-empty` (`https://source.invalid:/PLATAFORMA`), `base-url-port-zero`, `base-url-port-65536`, `base-url-port-99999`, `base-url-port-with-sign` (`:+8443`), `base-url-port-non-ascii-digit` (`:٣`), `base-url-invalid-ipv4-host` (`https://999.1.1.1/PLATAFORMA`), `base-url-control-character` (`https://source.invalid/PLAT\nAFORMA`).
    7. `test_invalid_base_url_with_userinfo_is_rejected_without_echoing_it`, as in the AC10 row.
    8. `test_construction_accepts_the_documented_boundaries`, three cases: `port-1`, `port-8443`, `port-65535` (`https://source.invalid:<port>/PLATAFORMA`).
    9. `test_invalid_input_too_long_for_a_url_raises_value_error_before_any_request_or_wait`, two cases (search with buyer `"a" * 70_000`, record with `ocid` `"a" * 70_000`), as in the AC10 row.
    10. `test_invalid_use_after_close_raises_runtime_error_before_any_wait`, as in the AC10 row.
  - Correct red reasons against the O5 code (a typo, an import error or a wrong fixture is never a correct red reason):
    - Item 1: `Location: https:abc` and the long `Location` -> `httpx.InvalidURL` escapes `pytest.raises(SourceError)`; the tab and invalid-IPv4 cases -> `AssertionError`, because a `SourceTransportError` without a response arrives instead of a `SourceStatusError`.
    - Items 2 and 3 -> an untyped `ValueError: a status must be an integer from 100 to 599` escapes from `RawResponse`.
    - Item 4 -> `AssertionError` on the sleeps: `[]` instead of `[3.0]` or `[58.0]`, because the escaped exception skipped the pacing update.
    - Items 6 and 7 -> `Failed: DID NOT RAISE <class 'ValueError'>`.
    - Item 9 -> `httpx.InvalidURL: URL too long` escapes, after a sleep of 4.0.
    - Item 10 -> `AssertionError` on the sleeps (`[4.0]` instead of `[]`), because the O5 code waits before the client reports that it is closed.
    - Items 5 and 8 pin behavior the O5 code already has. They are expected green, and their output must say so.
  - Tests (2026-10-10, `tests/unit/test_sercop_source.py` only; 65 new cases (49 for the ten items below plus 16 for items 11 and 12, added at the conductor's request), 205 -> 270 collected in the file; additions only, `diff` against the Revision 1 file shows no removed or changed line; 388 -> 453 collected overall):
    1. `STATUS_CASES`, 4 new cases by 2 operations = 8 (`-k status_error`).
    2. `test_transport_invalid_status_is_a_transport_error_without_response`, 3 statuses by 2 operations = 6 (`-k transport`). It also asserts the message names the operation (`search_ocds` or `record`) and the status number, that neither the body marker nor a header marker is in `str()`, `repr()` or the chain, and one request.
    3. `PACING_CASES`, 2 new cases (`-k pacing`).
    4. `test_pacing_counts_an_attempt_that_ends_in_an_unmapped_exception`, 4 cases, with the test-local `SyntheticTransportDefect(Exception)` (`-k pacing`).
    5. `test_transport_defect_from_an_injected_transport_propagates_unchanged`, 2 places (before the status; from the body stream after one chunk) by 2 operations = 4 (`-k transport`, `-k transport_defect`).
    6. `test_invalid_construction_options_raise_value_error`, 13 new cases (`-k invalid`).
    7. `test_invalid_base_url_with_userinfo_is_rejected_without_echoing_it`, 3 cases (user and password, user only, empty userinfo); it checks `synthetic-user`, `synthetic-secret` and the whole base URL against `str()` and `repr()` of every exception in the chain (`-k "invalid or userinfo"`).
    8. `test_construction_accepts_the_documented_boundaries`, 3 new cases, ports 1, 8443 and 65535 (no `-k` token; runs in the broader command).
    9. `test_invalid_input_too_long_for_a_url_raises_value_error_before_any_request_or_wait`, 2 cases (search buyer, record `ocid`, 70,000 `a`), after one earlier call and 1 s, then a valid call 1 s later expects `[3.0]` (`-k "invalid or too_long"`).
    10. `test_invalid_use_after_close_raises_runtime_error_before_any_wait`, 2 closing ways (`close()`, leaving the `with` block) by 2 operations = 4 (`-k "invalid or after_close"`).
    11. `test_invalid_base_url_is_rejected_without_echoing_it`, 13 cases, one per base URL of item 6 (`REJECTED_BASE_URLS`, shared by item 6): `ValueError` is raised, and the base URL (as given and as `repr()` writes it) and any credential-like part appear in no `str()` or `repr()` of the error or of any exception in its `__cause__`/`__context__` chain (`-k invalid`). Items 7 and 11 share the helper `_assert_base_url_not_echoed`; the three userinfo URLs are therefore checked by both tests.
    12. `test_invalid_input_after_close_raises_runtime_error_not_value_error`, 3 cases (page `0`, empty buyer, empty `ocid`) on a closed adapter -> `RuntimeError` (not `ValueError`), no new request, no sleep (`-k "invalid or after_close"`). It pins the plan's order of a call: the closed check comes before the argument checks.
    - Network guard active in every case; mock responses use `stream=`; fake `monotonic`, `sleep` and `now`; credentials, bodies and the defect are labelled SYNTHETIC; hosts are `.invalid` or numeric.
  - Red (2026-10-10, `.venv`, `httpx` 0.28.1, run against the O5 code; each of the 49 node ids was also run alone). `uv run pytest tests/unit/test_sercop_source.py -q` -> `58 failed, 212 passed` (205 Revision 1 tests plus 7 new cases that pin existing behavior). `uv run pytest -q` -> `58 failed, 395 passed`. `uv run ruff check .` clean, `uv run ruff format --check .` -> `75 files already formatted`, `uv run mypy .` -> `Success: no issues found in 20 source files`.
    - Item 1 (8 failed): `302-location-not-starting-with-slash` and `301-location-longer-than-the-url-limit`, both operations -> `httpx.InvalidURL: For absolute URLs, path must be empty or begin with '/'` and `httpx.InvalidURL: URL too long` escape `pytest.raises(SourceError)`. `302-location-with-a-tab` and `307-location-with-an-invalid-ipv4-host`, both operations -> `AssertionError: ... isinstance(SourceTransportError('search_ocds: the request failed before a response arrived'), SourceStatusError)` (the response was dropped by the client's redirect step). All four are the reasons named above.
    - Item 2 (6 failed) -> `ValueError: a status must be an integer from 100 to 599` escapes from `RawResponse` (not a `SourceTransportError`).
    - Item 3 (2 failed) -> the same `ValueError` escapes `_search_ignoring_source_errors` (it catches `SourceError` only).
    - Item 4 (4 failed) -> `assert [] == [3.0]` for both before-the-status cases and `assert [] == [58.0]` for both body-read cases: the escaped exception skipped the pacing update, so the next call did not wait.
    - Item 5 (4 passed, expected): pins behavior the O5 code already has. The same `SyntheticTransportDefect` object propagates, for both operations and both places.
    - Item 6 (13 failed) -> `Failed: DID NOT RAISE <class 'ValueError'>` for each case.
    - Item 7 (3 failed) -> `Failed: DID NOT RAISE <class 'ValueError'>` for each case.
    - Item 8 (3 passed, expected): pins behavior the O5 code already has.
    - Item 9 (2 failed) -> `httpx.InvalidURL: URL too long` escapes `pytest.raises(ValueError)` from the rejected call (the O5 code builds the request after the wait).
    - Item 10 (4 failed) -> `assert [4.0] == []`: the O5 code sleeps 4 s, then the client raises `RuntimeError`, so the `RuntimeError` type is right and the wait is the failure. Both closing ways fail the same way.
    - Item 11 (13 failed) -> `Failed: DID NOT RAISE ValueError` for each case (the same reason as items 6 and 7: the O5 code accepts every one of these base URLs, so the no-echo assertion is not reached in red; it is exercised in the reference-fix run below).
    - Item 12 (3 failed) -> `ValueError: page must be an integer of 1 or more`, `ValueError: buyer must be a non-empty string` and `ValueError: ocid must be a non-empty string` escape `pytest.raises(RuntimeError)`: the O5 code checks the arguments, and has no closed check.
    - Test logic checked outside the repository, on a scratch copy of the package under the scratchpad directory (never `src/`): a reference fix (response event hook capture before the redirect step, invalid status mapped without a `RawResponse`, base URL authority checks, request built before the wait, closed flag checked first, pacing in a `finally`) makes the file pass (`270 passed`) and the whole suite pass (`453 passed`, the 388 included). Deliberately broken variants of that fix each fail at least one new test: userinfo echoed in the message (3), body echoed in the invalid-status message (6), `with` exit not marking the adapter closed (2), pacing skipped on an exception (2), a rejected too-long call updating pacing (2), a broad `except Exception` wrapping a transport defect (4), the port message echoing the URL (7 of item 11), the host message echoing the URL with `!r` (1 of item 11), the argument check placed before the closed check (1 of item 12). One variant does not fail: chaining the library's `InvalidURL` as `__cause__`, because its text repeats only a fragment (the host or the offending character), never the whole URL or user information; the plan forbids it, but no AC text is violated. This is evidence about the tests only, not an implementation for O5b.
    - Gaps left for the human or the architect (not resolved here): see the report of this run (the 2 places by 2 operations of item 5, the closing ways of item 10, and the overlap of items 7 and 11 on the three userinfo URLs are cases added within the named tests).
- [x] **O5b** (AC5, AC6, AC9, AC10, AC15; Revision 2) — executor: make the O2b tests green without editing any test, following `execution-plan.md` § Binding constraints (Revision 2 items) and confirming every `httpx` behavior against `.venv/Lib/site-packages/httpx/`.
  - `src/ec_procurement_quality/infrastructure/sercop_source.py`:
    - construction checks of the `base_url` authority, with no URL text in the message or chain;
    - the call order: closed check, argument checks, request built, wait, send;
    - the capture before the client's redirect step, with library errors from that step ignored;
    - rule 2 of § Outcome mapping (invalid status);
    - the pacing update on every exit path once the request is handed to `send`.
  - `src/ec_procurement_quality/domain/source_response.py`: only the `SourceTransportError` docstring, if needed, to mention the invalid status. The `RawResponse` validation (100 to 599) does not change.
  - F1, the fixtures, ADR 0006 and the tests are not edited.
  - Green (2026-10-10, `.venv`, `httpx` 0.28.1; only `infrastructure/sercop_source.py` and the `SourceTransportError` docstring in `domain/source_response.py` changed; no test, fixture, F1 module, ADR or other spec file was edited): `uv run pytest tests/unit/test_sercop_source.py -q` -> `270 passed`; AC1 `-k "search_success or query"` -> 11 passed; AC2 `-k record_success` -> 4; AC3 `-k "raw_response or store_shape or cookie"` -> 18; AC4 `-k "out_of_range or no_results"` -> 4; AC5 `-k status_error` -> 26; AC6 `-k transport` -> 27; AC7 `-k incomplete` -> 43; AC8 `-k no_leak` over both files -> 17; AC9 `-k pacing` -> 39; AC10 `-k "timeout or accept_encoding or invalid"` over both files -> 112; AC11 `-k no_network` -> 2; AC12 `tests/unit -k "layer or satisfies_port"` -> 9; AC15 `-k "transport_defect or invalid_status or status_error or too_long or after_close or userinfo"` -> 50. `uv run pytest -q` -> `453 passed`. `uv run ruff check .` -> `All checks passed!`; `uv run ruff format --check .` -> `75 files already formatted`; `uv run mypy .` -> `Success: no issues found in 20 source files`; `uv lock --check` -> exit 0; `git diff --check` -> clean; `git grep -n --untracked "datosabiertos.compraspublicas.gob.ec/PLATAFORMA" -- src` -> one match (`DEFAULT_BASE_URL`); `git grep -n -i --untracked -e datosabiertos -e compraspublicas -- tests` -> no match (exit 1); `git grep -n -e "except Exception" -e "except BaseException" -- src/.../sercop_source.py` -> no match; `git status --short` lists the same files as before O5b. Left for O6 to O8: docs, doctor, CLI version, `uv sync --locked`, the PR checks.
  - Mechanism and choices (the plan left room; each is for the human's re-read):
    - Capture: the plan's response event hook (`httpx.Client(event_hooks={"response": [...]})`). Confirmed in `httpx/_client.py` 0.28.1: `_send_handling_redirects` runs the response hooks (lines 981 to 982) before `has_redirect_location` and `_build_redirect_request` (985 to 988), and its `except BaseException` closes the response and re-raises. The hook reads the body with `iter_raw` and closes the response itself, so the later failure of the redirect step loses nothing.
    - Branches in `_outcome`: six, not five. The plan's rule 2 (a status outside 100 to 599) is a new branch after the first. The five reviewed comments keep their text; only their numbers moved (2 to 3, 3 to 4, 4 to 5, 5 to 6).
    - The status range is repeated in the adapter (`_MIN_STATUS`, `_MAX_STATUS`) because the domain constants are private and `RawResponse` must not be built outside it.
    - The closed check uses the client's `is_closed` property (set by `close()` and by leaving the `with` block) instead of a separate flag, so there is one source of truth.
    - `base_url` checks return fixed reasons from `_base_url_problem` and raise once in `_require_base_url`, outside any `except`; `urlsplit`'s own `ValueError` (it can repeat the whole netloc, user information included) and `httpx.URL`'s `InvalidURL` or `UnicodeEncodeError` are caught and replaced by fixed text, never chained.
    - `now()` is called once per response with a status in 100 to 599, after the body read (in `_attempt_from_capture`), not in the hook; it is not called for an invalid status.
    - Outside the redirect-step case an `httpx.InvalidURL` raised by `send` before any status was captured is re-raised unchanged (unreachable; not a source outcome).
- [ ] **O6** Migration (AC12, AC13): existing consumers keep working.
  - `tests/unit/test_cli.py`, the three F1 test files and the existing tests in `tests/unit/test_layers.py` are not edited (a docstring mention of F2 is allowed) and still pass.
  - The F1 modules and `interfaces/cli.py` are unchanged, and the fixtures are unchanged since gate 1.
  - No new file directly in `src/ec_procurement_quality/`, and no CLI command.
  - Evidence: [the AC13 `git diff` and `git log` commands and their results]
- [ ] **O7** Docs (AC14):
  - `README.md`: § Architecture no longer says no source access exists; § Technologies names the SERCOP adapter as a library with no command and `httpx` as the first runtime dependency, and removes it from "Planned".
  - `CHANGELOG.md` § Unreleased: an `Added` entry.
  - `docs/architecture.md` § Open questions: the first flow uses `search_ocds` with the buyer-name query and `api/record`.
  - Checked with the AC14 commands.
  - Green: [command and result]
- [ ] **O8** Broader suite vs baseline (AC13):
  - `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing` passes, with the 137 baseline tests plus the new ones.
  - `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy .`, `uv lock --check` and `uv sync --locked` exit 0.
  - The doctor reports `0 warned, 0 failed`.
  - `uv run ec-procurement-quality --version` prints `ec-procurement-quality 0.1.0`.
  - `git diff --check` is clean.
  - `git grep -n -i --untracked -e datosabiertos -e compraspublicas -- tests` finds nothing.
  - On the F2 pull request, the `feedback` and `Tests` checks are green. Record a check that has not run yet as unavailable, never as a pass.
  - Green: [commands and results]
- [ ] **O9** Independent audit (`specs/sercop-source-adapter/audit.md`, written by the auditor): [verdict]

## Working state
- Updated: 2026-10-10
- Outcome: O5b done (executor, uncommitted: `src/ec_procurement_quality/infrastructure/sercop_source.py`, and the `SourceTransportError` docstring in `src/ec_procurement_quality/domain/source_response.py`); O2b done earlier (`tests/unit/test_sercop_source.py`, 65 new cases, approved at gate 2); O5 done under Revision 1 (O3, O4 and O5 green, uncommitted: `src/ec_procurement_quality/domain/source_response.py`, `src/ec_procurement_quality/application/procurement_source.py`); O1 and O2 done earlier.
- Phase: Revision 2 implemented (O5b green); awaiting the human's line-by-line re-read of `infrastructure/sercop_source.py`, then O6 to O8
- In progress: nothing
- Last command (executor, O5b): `uv run pytest -q` -> `453 passed`
- Next step:
  1. The human re-reads `infrastructure/sercop_source.py` (the six outcome branches and the design choices recorded under O5b).
  2. Then O6 to O8 (executor) and the audit (O9). Commits are made by the human or the orchestrator; the roles do not commit.

## Finding responses
| Finding | Response | Evidence |
|---|---|---|
| F-A (human review, Day 13): a status outside 100 to 599 raises an untyped `ValueError` from `RawResponse` inside `_send`, and the response is lost | Spec Revision 2: `SourceTransportError` with no response, the message naming the operation and the status; the `RawResponse` range and F1 unchanged; the status and headers still count for pacing. Losing the bytes is put to the human (intent § Open questions) | intent AC6, AC9; plan § Outcome mapping rule 2; O2b items 2 and 3 |
| F-B (human review, Day 13): user information in `base_url` becomes `Authorization: Basic`, stays in `RawResponse.url` and is printed in the `httpx` `INFO` record | Spec Revision 2: rejected at construction with `ValueError`, with no URL text in the message or chain | intent AC10, § Constraints; plan § Binding constraints "the authority of `base_url`"; O2b items 6 and 7 |
| F-C (human review, Day 13): an invalid authority or port (`:abc`) passes construction and raises `httpx.InvalidURL` from `build_request` on the first call | Spec Revision 2: non-empty host, ASCII port 1 to 65535, and `httpx.URL(base_url)` checked at construction (`ValueError`). Range-checking the port also closes an unmapped `OverflowError` and a silent port wrap on Windows | intent AC10; plan § Binding constraints, § Closed-set justification; O2b items 6 and 8 |
| Family check (architect, Revision 2): exceptions outside `httpx.HTTPError` reaching `send` and `iter_raw` | A malformed `Location` on a redirect status (`InvalidURL`, or a dropped response) -> captured before the redirect step, so it is a status error; a URL too long -> `ValueError` before the wait; a call after `close()` -> `RuntimeError` before the wait; pacing counts every attempt handed to `send`; `CookieConflict`, the `StreamError` family and `RequestNotRead` shown unreachable or treated as test-double defects that propagate unchanged | intent AC5, AC9, AC10, AC15; plan § Closed-set justification; O2b items 1, 4, 5, 9 and 10 |

## Checkpoint
Specs Revision 2 drafted on `feat/sercop-source-adapter` (HEAD `59be7df`, O1 to O5 done and uncommitted) on 2026-10-10, pending human approval. Resume at O2b once it is approved.
