# SERCOP fixtures

Minimal, sanitized fixtures for the source adapter tests. None of them is a
complete SERCOP response, and tests that use them never reach the network.

The shape of every fixture comes from
[sercop-observations.md](../../../docs/sources/sercop-observations.md). Values
are synthetic: identifiers use `SYNTHETIC`, URLs use the reserved `.invalid`
domain, and names are invented. The buyer name is the public name already used
in the confirmed query.

| File | Basis | What it carries |
| ---- | ----- | --------------- |
| `search_single_page.json` | Observed shape of a `search_ocds` page (series of 2026-10-10), synthetic values | `total` 3, `page` 1, `pages` 1 and three records covering the observed null patterns: both present, `suppliers` null, both `suppliers` and `budget` null. `amount` and `budget` are strings written with different decimals. Compact JSON with `\uXXXX` escapes, as the source sends it. |
| `search_page_out_of_range.json` | Observed: `page=30` with `pages=29`, exact bytes (numbers only) | `total` 284, `page` 30, `pages` 29 and an empty `data`, as a successful response. |
| `search_no_results.json` | **Inferred**, not observed: built from the out-of-range shape and the 45-byte reply of 2026-10-03 | `total` 0, `pages` 0 and an empty `data`. |
| `record_single_release.json` | Observed shape of an `api/record` response (series of 2026-10-10), trimmed, synthetic values | An OCDS release package with one release. Only keys that were observed are used, in the observed order; sections and keys are omitted. Money amounts are JSON numbers and `/` is written as `\/`, as the source sends it. |

A truncated body, a `429` and a `5xx` have no fixture: their bodies were never
observed. Tests build them from these files or give a synthetic status, and
claim nothing about the source's own error format.
