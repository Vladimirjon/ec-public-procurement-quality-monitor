# Tasks: SERCOP source adapter (F2)

## Status
Intent Revision 3 approved by the human on 2026-10-10. The O9 audit, round 1, returned REJECTED ([audit.md](audit.md)): two blocking findings (F-1, F-2) and two LOW findings (F-3, F-4). Following the project rule of no technical debt, the specs were revised (Revision 3, drafted by the architect on 2026-10-10) instead of working around the findings in code. Revision 3 was approved by the human on 2026-10-10, with the four open questions accepted as recommended. Next: O2c (test-writer), gate 2 review, O5c (executor), O7b and O8b (executor), O9b (auditor, round 2).

History before Revision 3: Intent Revision 2 approved by the human on 2026-10-10 (Revision 1 was approved at gate 1 on the same day, which also accepted ADR 0006, the fixtures in `tests/fixtures/sercop/` and the series of 2026-10-10 in `docs/sources/sercop-observations.md`). O1 to O5 were done under Revision 1. The human's Day 13 review of the adapter found spec gaps, so the specs were revised (Revision 2) instead of working around them in code. O2b (the Revision 2 red tests) was written and approved by the human at gate 2 on 2026-10-10, and O5b made them green (453 tests passed, none edited). O6 (migration), O7 (docs) and O8 (suite against the baseline) were done by the executor on 2026-10-10: 453 tests passed (137 baseline plus 316 new), the F1 modules, `interfaces/cli.py`, the fixtures and the existing tests are unchanged, and `README.md`, `CHANGELOG.md` and `docs/architecture.md` were updated (uncommitted). The PR #16 `tests` and `feedback` checks are `SUCCESS` on the committed head `015a72b` only; they have not run on the uncommitted doc edits. Next: the O9 audit (auditor). Whether the human's re-read of the blocks of `infrastructure/sercop_source.py` that Revision 2 changed has happened is not recorded here. The plan's rule that the library's `InvalidURL` is never chained into a raised error has no test; it is checked at the O9 audit. Documentation after gate 3 (`specs/current`, "Shipped", archiving) is not part of O6 to O8 and is not done.

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
- Revision 3 baseline (2026-10-10, measured by the architect): HEAD `015a72b` with the uncommitted O7 doc edits (`README.md`, `CHANGELOG.md`, `docs/architecture.md`), this file and the auditor's untracked `audit.md`; no file under `src/` or `tests/` differs from `015a72b`. `uv run pytest -q` -> `453 passed`. The test files at `015a72b` are the reference for "adds only" from now on (`git diff --numstat 015a72b -- tests`).

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
7. Revision 3, after the human approves it: **O2c (test-writer)** writes the Revision 3 tests, red against the `015a72b` code where § Validation says so, and the human reviews them at gate 2. Then **O5c (executor)** turns them green without editing any test, **O7b (executor)** corrects the two doc sentences of audit F-3, **O8b (executor)** reruns the broader suite against the Revision 3 baseline, and **O9b (auditor)** writes round 2 of `audit.md`.

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
- [x] **O6** Migration (AC12, AC13): existing consumers keep working.
  - `tests/unit/test_cli.py`, the three F1 test files and the existing tests in `tests/unit/test_layers.py` are not edited (a docstring mention of F2 is allowed) and still pass.
  - The F1 modules and `interfaces/cli.py` are unchanged, and the fixtures are unchanged since gate 1.
  - No new file directly in `src/ec_procurement_quality/`, and no CLI command.
  - Evidence (2026-10-10, branch `feat/sercop-source-adapter`, HEAD `015a72b`, base `main` `fff0f2d`; every command run from the repository root; no discrepancy found):
    - `git diff main --stat -- src/ec_procurement_quality/domain/content_hash.py src/ec_procurement_quality/domain/raw_evidence.py src/ec_procurement_quality/application/raw_evidence_store.py src/ec_procurement_quality/infrastructure/local_disk_raw_evidence_store.py src/ec_procurement_quality/interfaces/cli.py` -> empty. `git diff main --stat -- src/ec_procurement_quality/__init__.py src/ec_procurement_quality/interfaces` -> empty.
    - `git diff main -- pyproject.toml` -> only `dependencies = []` becomes `dependencies = [` / `"httpx>=0.28.1",` / `]`.
    - `git log --oneline -- tests/fixtures/sercop` -> one commit, `74b785d` ("Add F2 sercop-source-adapter specs and sanitized fixtures (gate 1 approved)"). The tree was clean at HEAD, so the fixtures are unchanged since gate 1.
    - `git diff main --stat -- tests/unit/test_cli.py tests/unit/test_content_hash.py tests/unit/test_raw_evidence.py tests/unit/test_local_disk_raw_evidence_store.py` -> empty (the four files are byte-identical to `main`).
    - `git diff main -- tests/unit/test_layers.py` -> a single hunk `@@ -112,3 +112,77 @@`: 74 lines added at the end of the file (`INFRASTRUCTURE_PACKAGE`, `SERCOP_ADAPTER_MODULE`, `HTTP_CLIENT_LIBRARY`, `_names_http_client_library` and `test_layer_only_infrastructure_imports_httpx`), 0 removed. The six existing tests and the module docstring are unchanged. `git diff main --numstat -- tests` shows 0 deletions in every file.
    - `git diff main --name-status --diff-filter=A -- src` -> exactly three added files, `application/procurement_source.py`, `domain/source_response.py` and `infrastructure/sercop_source.py`; no other file under `src/` changed. `ls src/ec_procurement_quality` -> `__init__.py` and the four layer directories only (no new file directly in the package root).
    - No CLI command: `interfaces/cli.py` is unchanged (above), and its only `add_argument` is the original `--version`.
    - The 137 baseline tests pass unchanged inside the 453 (see O8).
- [x] **O7** Docs (AC14):
  - `README.md`: § Architecture no longer says no source access exists; § Technologies names the SERCOP adapter as a library with no command and `httpx` as the first runtime dependency, and removes it from "Planned".
  - `CHANGELOG.md` § Unreleased: an `Added` entry.
  - `docs/architecture.md` § Open questions: the first flow uses `search_ocds` with the buyer-name query and `api/record`.
  - Checked with the AC14 commands.
  - Green (2026-10-10; only `README.md`, `CHANGELOG.md` and `docs/architecture.md` were edited for O7, and only with behavior already verified by AC1 to AC15):
    - `README.md` § Architecture: the sentence "No source access, ingestion, normalization, or quality behavior exists yet." now says the layers hold the local raw evidence store and the SERCOP source adapter, that nothing calls the adapter yet, and that no ingestion, normalization or quality behavior exists. The accepted-decisions list gains ADR 0006.
    - `README.md` § Technologies, "Implemented": a new SERCOP adapter bullet (a library only, no CLI command, one request per call, no retries, tests offline) and a new bullet naming `httpx` as the first runtime dependency, used only in `infrastructure`, with `ruff`, `mypy`, `pytest` and `pytest-cov` as the development-only dependencies. "Planned": the item "A SERCOP adapter and the ingestion ..." became "The ingestion that will call the SERCOP adapter and the raw evidence store."
    - `CHANGELOG.md` § Unreleased: two `Added` entries, the adapter (F2) and the `httpx` dependency.
    - `docs/architecture.md` § Open questions: the first bullet now says the first flow uses `search_ocds` with the buyer-name query and `api/record`, and that other response variants stay open until observed.
    - Not stated anywhere in the docs: the meaning of `local=1`, the rate-limit window or key, `Retry-After`, the bodies of `429` and `5xx`, the answer for an unknown `ocid`, filtering by RUC or `buyerId`.
    - `git grep -n "httpx" -- README.md CHANGELOG.md` -> matches in both (`CHANGELOG.md` lines 40, 46 and 49; `README.md` lines 72 and 80); none at baseline.
    - `git grep -n "No source access" -- README.md` -> no match (exit 1).
    - `git diff --stat -- README.md CHANGELOG.md docs/architecture.md` -> 3 files, 41 insertions, 7 deletions. `git diff --check` clean.
    - Left for the documentation step after gate 3, by instruction: `specs/current`, sealing "Shipped", archiving the specs, and the `harny-sync` modifications of PT-3, PT-6, PT-10 and PT-11.
- [x] **O8** Broader suite vs baseline (AC13):
  - `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing` passes, with the 137 baseline tests plus the new ones.
  - `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy .`, `uv lock --check` and `uv sync --locked` exit 0.
  - The doctor reports `0 warned, 0 failed`.
  - `uv run ec-procurement-quality --version` prints `ec-procurement-quality 0.1.0`.
  - `git diff --check` is clean.
  - `git grep -n -i --untracked -e datosabiertos -e compraspublicas -- tests` finds nothing.
  - On the F2 pull request, the `feedback` and `Tests` checks are green. Record a check that has not run yet as unavailable, never as a pass.
  - Green (2026-10-10, `.venv`, Python 3.13.9, `httpx` 0.28.1, after the O7 doc edits; the working tree held only the three doc edits and this file):
    - `uv sync --locked` -> exit 0 (`Resolved 22 packages`, `Checked 22 packages`).
    - `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing` -> exit 0, `453 passed in 3.50s` (137 baseline plus 316 new: 251 under Revision 1 and 65 under Revision 2). Per file: `test_cli.py` 2, `test_content_hash.py` 17, `test_layers.py` 7, `test_local_disk_raw_evidence_store.py` 60, `test_raw_evidence.py` 52, `test_sercop_source.py` 270, `test_source_response.py` 45. TOTAL row: `522 statements, 18 missed, 97%`. Misses by file: `domain/raw_evidence.py` 2 (lines 99, 107), `infrastructure/local_disk_raw_evidence_store.py` 11 (all F1, unchanged), `infrastructure/sercop_source.py` 5 (lines 90-91, 312-313, 332: the `urlsplit` `ValueError` branch of `_base_url_problem`, the `int()` `ValueError` branch for a digit string too long to convert, and the re-raise of an `httpx.InvalidURL` that no input reaches). The new `application/procurement_source.py` and `domain/source_response.py` are at 100%. No coverage threshold applies (PT-12).
    - `uv run ruff check .` -> `All checks passed!` (exit 0).
    - `uv run ruff format --check .` -> `75 files already formatted` (exit 0).
    - `uv run mypy .` -> `Success: no issues found in 20 source files` (exit 0).
    - `uv lock --check` -> `Resolved 22 packages` (exit 0).
    - `uv run node .sdd/doctor/run-doctor.mjs` -> `summary: 31 ok, 0 skipped, 0 warned, 0 failed` (exit 0; it ran `pytest` as one of its checks, `OK pytest`).
    - `uv run ec-procurement-quality --version` -> `ec-procurement-quality 0.1.0` (exit 0).
    - `git diff --check` -> no output (exit 0).
    - `git grep -n -i --untracked -e datosabiertos -e compraspublicas -- tests` -> no match (exit 1).
    - `git grep -n "datosabiertos.compraspublicas.gob.ec/PLATAFORMA" -- src` -> one match, `infrastructure/sercop_source.py:43` (`DEFAULT_BASE_URL`).
    - `git grep -n -e "except Exception" -e "except BaseException" -- src/ec_procurement_quality/infrastructure/sercop_source.py` -> no match (exit 1).
    - PR #16 checks: `gh pr checks 16` -> `feedback pass`, `tests pass`; `gh pr view 16 --json headRefOid,state,statusCheckRollup` -> `state` `OPEN`, `headRefOid` `015a72b5b6688cb5785ece5b32a4f78f6c752d1b` (equal to the local HEAD), `tests` and `feedback` both `COMPLETED` with `SUCCESS`. These results cover the committed head `015a72b` only. They do not cover the uncommitted O7 doc edits or this file: for that state the PR checks are unavailable until the human commits and pushes, and are not recorded as a pass.
- [x] **O9** Independent audit, round 1 (`specs/sercop-source-adapter/audit.md`, written by the auditor on 2026-10-10): **REJECTED**. See [audit.md](audit.md) § Final verdict and § Findings. Blocking: F-1 (MEDIUM, AC9: a `Remaining` value of more than 4,300 digits with a low value was ignored) and F-2 (MEDIUM, AC10: base URLs that passed construction failed on every call). Non-blocking: F-3 and F-4 (LOW). Reservations R-1 to R-6. AC1 to AC8 and AC11 to AC15 PASS; AC9 and AC10 PARTIAL. The responses are in § Finding responses, and the repair is O2c to O9b below (intent Revision 3).
- [ ] **O2c** (AC3, AC5, AC7, AC8, AC9, AC10, AC13, AC15; Revision 3) — test-writer: the Revision 3 tests, in `tests/unit/test_sercop_source.py` only. `tests/unit/test_source_response.py` and `tests/unit/test_layers.py` do not change. Add cases and tests only; change or remove no existing line (`git diff --numstat 015a72b -- tests` shows 0 deletions). Bodies, cookies, hosts and values are synthetic and labelled so; hosts are `.invalid` or numeric, the IPv6 literals are never contacted, and the network guard stays active.
  - Tests to add (names fixed where § Validation gives them, because the `-k` commands select them; case ids suggested). Expected new tests: 116, so 453 -> 569 collected.
    1. `STATUS_CASES`, 2 cases with body `b"synthetic redirect body"`: `302-location-host-not-decodable` (`Location: http://xn--/`), `308-location-scheme-relative-host-not-decodable` (`Location: //xn--/`); both operations (4).
    2. `test_cookie_set_cookie_is_never_parsed_and_raises_no_warning`, both operations (2), as in the AC3 row.
    3. `INCOMPLETE_SEARCH_CASES`, 6 cases (`nan-in-data`, `infinity-in-data`, `negative-infinity-in-data`, `integer-of-5001-digits-in-data`, `total-of-4301-digits`, `nested-too-deep`); `INCOMPLETE_RECORD_CASES`, 4 cases (`infinity-in-a-release`, `nan-in-a-release`, `integer-of-5001-digits-in-a-release`, `nested-too-deep`); `test_search_success_takes_the_last_value_of_a_repeated_name` (1). Build these bodies as bytes: `json.dumps` cannot write an integer of more than 4,300 digits (11).
    4. `test_no_leak_rejections_chain_no_library_exception`, three groups as in the AC8 row: every `REJECTED_BASE_URLS` entry (23), the two too-long inputs (2), the six malformed-`Location` cases by two operations (12) (37).
    5. `PACING_CASES`, 9 cases as in the AC9 row; `UNMAPPED_EXCEPTION_CASES`, 2 `SystemExit` cases (11).
    6. `REJECTED_BASE_URLS`, 10 entries as in the AC10 row, each run by two existing tests (20); `test_invalid_construction_options_raise_value_error`, 12 option cases; `test_construction_accepts_the_documented_boundaries`, 9 cases (41).
    7. `INVALID_SEARCH_ARGUMENTS`, 3 cases (`year-of-5001-digits`, `page-of-5001-digits`, `buyer-lone-surrogate`); the record invalid-input list, 1 case (`ocid-lone-surrogate`); `test_invalid_input_too_long_for_a_url_raises_value_error_before_any_request_or_wait`, 1 case (`search-year-with-a-long-base-url`); `test_record_query_sends_a_non_ascii_base_path_percent_encoded` (1) (6).
    8. `test_transport_defect_system_exit_propagates_unchanged`, 2 places by 2 operations (4).
  - Notes from the family check: give non-ASCII header values as `bytes` (`httpx.Response` raises `UnicodeEncodeError` for a non-ASCII `str` value); give every parameter that holds 10**5000 an explicit `id`, because writing it as text raises; build mock responses with `stream=`.
  - Correct red reasons against the `015a72b` code (a typo, an import error or a wrong fixture is never a correct red reason). Expected: 61 new tests fail, 55 pass.
    - Item 1 (4 failed) -> `idna.IDNAError: Malformed A-label, no Punycode eligible content found` escapes `pytest.raises(SourceError)`.
    - Item 2 (2 failed) -> `AssertionError`: one `UserWarning` ("http.cookiejar bug!") recorded.
    - Item 3: the 5 `NaN` and `Infinity` cases fail with `DID NOT RAISE` (a result is returned); the other 5 incomplete cases and the repeated-name test pass (they pin behavior the code already has).
    - Item 4: the 10 Revision 3 base URLs fail with `DID NOT RAISE <class 'ValueError'>`, and the 4 `xn--` `Location` cases fail with the escaping `idna.IDNAError`; the other 23 pass. Because the code already meets the chaining rule for them, the red evidence for this item is the auditor's two mutants run on a scratch copy (never `src/`): m1 (`_build_request` raises `from` the `InvalidURL`) must fail at least one group-2 case, and m2 (`_base_url_problem` raises `from` the caught exception inside its `except`) at least one group-1 case.
    - Item 5: 4 fail (`"0" * 4999 + "5"`, `"0" * 4300 + "5"` and the 10**5000 threshold give `[3.0]` instead of `[58.0]`; `b"\xa05"` gives `[58.0]` instead of `[3.0]`); the other 5 pacing cases and the 2 `SystemExit` cases pass.
    - Item 6: the 20 base URL runs fail with `DID NOT RAISE <class 'ValueError'>`; 11 option cases fail with `DID NOT RAISE`, and `cooldown="60"` fails with a `TypeError` escaping `pytest.raises(ValueError)`; the 9 boundary cases pass.
    - Items 7 and 8 pass (they pin behavior the code already has); their output must say so.
  - Tests: [file, count]
  - Red: [command and result, per item, plus the mutant runs]
- [ ] **O5c** (AC3, AC5, AC7, AC8, AC9, AC10, AC15; Revision 3) — executor: make the O2c tests green without editing any test, following `execution-plan.md` § Binding constraints (Revision 3 items) and confirming each library behavior against `.venv/Lib/site-packages/`.
  - `src/ec_procurement_quality/infrastructure/sercop_source.py` only:
    - the `Remaining` value: `strip(" \t")` and an exact comparison for any length and any threshold (F-1);
    - no cookie processing (a jar that never stores is suggested);
    - nothing derived from `Location` runs or leaves the call (removing `Location` from the `httpx` response in the hook, after the capture, is suggested), with no `except Exception` or `except BaseException`;
    - the JSON constants rejected (for example `parse_constant`);
    - the base URL host rules (labels, length, IDNA decoding, zone identifier) and the room for the shortest request URL, with fixed reasons and nothing chained;
    - the numeric option rules (type, finite, at most 86,400).
  - Nothing else changes: not `domain`, not `application`, not the tests, the fixtures, F1, ADR 0006 or the other specs.
  - Green: [the focused command of each § Validation row and the whole suite]
- [ ] **O7b** (AC14; audit F-3) — executor: correct two doc sentences; no spec change.
  - `README.md` § Technologies (the SERCOP adapter bullet): "raises a typed error that carries whatever response arrived, so that every response can be stored as evidence" becomes "raises a typed error that carries the valid response that arrived, so that it can be stored as evidence; a status outside 100 to 599 is reported without a response".
  - `CHANGELOG.md` § Unreleased (the adapter entry): "raises a typed error that carries the response that arrived" becomes "raises a typed error that carries the valid response that arrived (a status outside 100 to 599 is reported without a response)".
  - Optional, from the same finding: README "its tests use simulated transports and never reach the network" may add that one test shows the network guard stopping the real transport.
  - State nothing that Revision 3 did not verify, and no unobserved source fact.
  - Green: [`git diff -- README.md CHANGELOG.md` and the AC14 commands]
- [ ] **O8b** Broader suite vs the Revision 3 baseline (AC13): the O8 commands again, with `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing` at 453 plus the O2c tests, and `git diff --numstat 015a72b -- tests` with 0 deletions. Record the PR #16 checks for the head that holds the Revision 3 changes, or record them as unavailable if that head was not pushed.
  - Green: [commands and results]
- [ ] **O9b** Independent audit, round 2 (auditor): `audit.md` gains round 2, which rechecks F-1 to F-4, R-1 and R-3 and § Family check of `execution-plan.md` row by row against the installed packages. [verdict]

## Working state
- Updated: 2026-10-10
- Outcome: O9 round 1 done (REJECTED). Revision 3 of `intent.md`, `execution-plan.md` and this file drafted by the architect and approved by the human on 2026-10-10. Uncommitted in the working tree at HEAD `015a72b`: `README.md`, `CHANGELOG.md`, `docs/architecture.md` (O7), the three spec files (Revision 3) and the auditor's untracked `audit.md`. Nothing under `src/` or `tests/` differs from `015a72b`.
- Phase: Repairing; intent Revision 3 approved, O2c (test-writer, red tests) next
- In progress: nothing
- Last command (architect): `uv run pytest -q` -> `453 passed` (the Revision 3 baseline)
- Next step:
  1. The human reviews Revision 3 (intent § Open questions has three Revision 3 questions with recommendations) and records the approval in `intent.md`.
  2. Commits are made by the human or the orchestrator; the roles do not commit. Committing the Revision 3 specs, `audit.md` and the O7 doc edits before O2c keeps each step's diff readable. The "adds only" reference for the tests stays `015a72b` either way, because no test file changed after it.
  3. O2c (test-writer), then gate 2, O5c, O7b and O8b (executor), and O9b (auditor, round 2).
  4. After gate 3, the documentation step (`specs/current`, "Shipped", archive) runs outside these outcomes.

## Finding responses
| Finding | Response | Evidence |
|---|---|---|
| F-A (human review, Day 13): a status outside 100 to 599 raises an untyped `ValueError` from `RawResponse` inside `_send`, and the response is lost | Spec Revision 2: `SourceTransportError` with no response, the message naming the operation and the status; the `RawResponse` range and F1 unchanged; the status and headers still count for pacing. Losing the bytes is put to the human (intent § Open questions) | intent AC6, AC9; plan § Outcome mapping rule 2; O2b items 2 and 3 |
| F-B (human review, Day 13): user information in `base_url` becomes `Authorization: Basic`, stays in `RawResponse.url` and is printed in the `httpx` `INFO` record | Spec Revision 2: rejected at construction with `ValueError`, with no URL text in the message or chain | intent AC10, § Constraints; plan § Binding constraints "the authority of `base_url`"; O2b items 6 and 7 |
| F-C (human review, Day 13): an invalid authority or port (`:abc`) passes construction and raises `httpx.InvalidURL` from `build_request` on the first call | Spec Revision 2: non-empty host, ASCII port 1 to 65535, and `httpx.URL(base_url)` checked at construction (`ValueError`). Range-checking the port also closes an unmapped `OverflowError` and a silent port wrap on Windows | intent AC10; plan § Binding constraints, § Closed-set justification; O2b items 6 and 8 |
| Family check (architect, Revision 2): exceptions outside `httpx.HTTPError` reaching `send` and `iter_raw` | A malformed `Location` on a redirect status (`InvalidURL`, or a dropped response) -> captured before the redirect step, so it is a status error; a URL too long -> `ValueError` before the wait; a call after `close()` -> `RuntimeError` before the wait; pacing counts every attempt handed to `send`; `CookieConflict`, the `StreamError` family and `RequestNotRead` shown unreachable or treated as test-double defects that propagate unchanged | intent AC5, AC9, AC10, AC15; plan § Closed-set justification; O2b items 1, 4, 5, 9 and 10 |
| F-1 (audit round 1, MEDIUM, blocking): `X-RateLimit-Remaining` of more than 4,300 digits with a low value (`"0" * 4300 + "5"`) is ignored, so the next wait is 3 s instead of 58 s | Spec Revision 3: **keep the rule** and make it exact for any number of digits and any threshold, independent of the interpreter's conversion limit; define "surrounding whitespace" as HTTP's space and tab. Reason: the value is the source's own advice, ignoring it shortens the wait the source asked for, the exact comparison is a few lines (`decimal.Decimal` or a digit-count comparison), and revising AC9 to ignore long values would turn a CPython limit into a pacing rule. Rejected: revising AC9 to say such a value is ignored | intent AC9; plan § Pacing, § Family check rows 1.6, 1.7 and 1.9; O2c item 5 |
| F-2 (audit round 1, MEDIUM, blocking, spec gap): a host label of 64 or more characters or an empty label passes construction, then name resolution raises an unmapped `UnicodeEncodeError`; a base URL near 65,536 characters passes construction, then every call raises `ValueError` | Spec Revision 3: **extend the construction rules and state the guarantee precisely**. Rules: labels of 1 to 63 characters (one final empty label allowed), a host of at most 253 characters, a host the library can decode from IDNA, no IPv6 zone identifier, and room for the shortest request URL of each operation, all checked through the library's own parse; plus numeric options that are numbers, finite and at most 86,400 s. Guarantee: a call can fail because of the base URL only as a transport error when the host does not resolve or cannot be reached, and a URL too long can only come from the call's input. Reason: each rule is grounded in RFC 1035, CPython's `idna` codec, the `httpx` and `idna` sources or a probe, and narrowing the guarantee alone would leave unmapped exceptions escaping the closed set (AC15). Rejected: narrowing AC10 to the Revision 2 rules and listing the `idna` path as an exception that propagates | intent AC10; plan § Binding constraints (the host and the length of `base_url`, the numeric options), § Family check rows 2.3 to 2.21; O2c items 4, 6 and 7 |
| F-3 (audit round 1, LOW): `README.md` and `CHANGELOG.md` say a typed error carries "whatever response arrived" or "the response that arrived", but a status outside 100 to 599 is reported without a response (AC6 Revision 2) | No spec change. O7b corrects both sentences with the exact text given there: the valid response that arrived, and a status outside 100 to 599 is reported without a response. The intent § Outcome sentence with the same overclaim was also corrected in Revision 3 | O7b; intent § Outcome |
| F-4 (audit round 1, LOW): `execution-plan.md` § Guidance consulted said intent Revision 2 was "pending human approval" and the observations file "not yet committed" | Corrected in Revision 3: Revision 2 approved on 2026-10-10; the observations file committed in `5a7bb90` | plan § Guidance consulted |
| R-1 (audit round 1, reservation): the rule that the library's `InvalidURL` is never chained has no test; mutants m1 and m2 pass all 453 tests | Made a requirement: intent AC8 Revision 3, tested by `test_no_leak_rejections_chain_no_library_exception` over the rejected base URLs, the too-long inputs and the malformed `Location` cases, with the mutant runs as red evidence | intent AC8; plan § Validation AC8 row; O2c item 4 |
| R-3 (audit round 1, reservation): `SystemExit` is named but only `KeyboardInterrupt` is tested | Two pacing cases and one propagation test (2 places by 2 operations) added | intent AC9, AC15; O2c items 5 and 8 |
| R-4 (audit round 1, reservation): the Revision 1 test file was never committed, so "removes or weakens none" could be checked only by counts | Not fixable in the spec: that content is gone. From Revision 3 on, the committed `015a72b` is the reference, and `git diff --numstat 015a72b -- tests` with 0 deletions is an AC13 check (O2c, O8b). R-2, R-5 and R-6 need no spec change: R-2's line 332 becomes dead code with the suggested `Location` mechanism, R-5 is O8b's PR-check record, and R-6 is an accepted risk in plan § Risks | intent AC13; plan § Validation AC13 row |
| Family check (architect, Revision 3), new gaps of the same families | (a) A redirect status with `Location: http://xn--/` or `//xn--/` let `idna.IDNAError` escape (AC5). (b) A base URL whose first label is an invalid `xn--` A-label failed every call with the same error from `build_request` (AC10). (c) A `Set-Cookie` value made the client's cookie jar issue a `UserWarning` with a traceback (AC3). (d) `NaN` and `Infinity` were accepted in a `200` body (AC7). (e) `NaN`, infinite or very large timeouts and intervals switched pacing off or failed every call with an unmapped error (AC10). (f) An ASCII host above 253 characters and an IPv6 zone identifier reached name resolution (AC10). (g) `str.strip()` removed non-HTTP whitespace around `Remaining` (AC9). Pinned without a code change: integers of more than 4,300 digits and deep nesting in a body, a repeated name, long years and pages, lone surrogates, a non-ASCII or `%` base path, `MemoryError` (decision for the human) | intent AC3, AC5, AC7, AC9, AC10, AC15; plan § Family check; O2c |

## Checkpoint
On 2026-10-10, on `feat/sercop-source-adapter` at HEAD `015a72b` (base `main` `fff0f2d`), O1 to O9 round 1 are done; the audit is REJECTED ([audit.md](audit.md)). Intent Revision 3 and its plan and tasks were approved by the human on 2026-10-10 (recorded in `intent.md`); the suite is `453 passed` and no file under `src/` or `tests/` differs from `015a72b`. Resume at O2c (test-writer).

Previous checkpoint (before the audit): O1 to O8 done and verified; intent Revision 2 approved; the O5b code and the O2b tests committed; ruff, mypy, `uv lock --check`, `uv sync --locked` and the doctor (`31 ok, 0 skipped, 0 warned, 0 failed`) clean.
