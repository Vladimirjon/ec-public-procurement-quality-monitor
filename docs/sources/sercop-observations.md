# SERCOP source observations

## Observation scope

- Observation date: `2026-10-03`
- Time zone: `UTC-05:00`
- Source: SERCOP open-contracting portal
- Portal: [https://datosabiertos.compraspublicas.gob.ec/PLATAFORMA](https://datosabiertos.compraspublicas.gob.ec/PLATAFORMA)
- Target buyer: `EMPRESA ELÉCTRICA QUITO S.A. E.E.Q.` (EEQ)

This note contains only behavior observed in the SERCOP web interface or
reproduced through direct HTTP requests. It does not include complete
responses, cookies, session identifiers, or other sensitive headers.

## Confirmed search endpoint

The official frontend uses:

```http
GET /PLATAFORMA/api/search_ocds
```

The EEQ buyer-only search for 2025 generated this query:

```text
local=1&year=2025&page=1&buyer=EMPRESA%20EL%C3%89CTRICA%20QUITO%20S.A.%20E.E.Q.
```

Full reproducible URL:

```text
https://datosabiertos.compraspublicas.gob.ec/PLATAFORMA/api/search_ocds?local=1&year=2025&page=1&buyer=EMPRESA%20EL%C3%89CTRICA%20QUITO%20S.A.%20E.E.Q.
```

The request uses the complete buyer name, including accents and
punctuation. It does not include a general `search` keyword.

## Verified EEQ 2025 result

The frontend search and the direct request returned the same total:

```text
HTTP=200 TIME=5.344970s SIZE=5944bytes
total=284
page=1
pages=29
```

Page 1 contained 10 records; 29 pages were reported for 284 total. This
does not establish that every page contains exactly 10 records.

The web search produced these counts:

| Filters                                                |         Result |
| ------------------------------------------------------ | -------------: |
| Year`2025` + EEQ buyer, without keyword              | 284 procedures |
| Year`2025` + EEQ buyer + keyword `ELECTRICA QUITO` |   3 procedures |

Therefore, the keyword adds a restriction and must not be used when the
goal is to retrieve all EEQ procedures for the selected year.

## Observed response fields

Items in `data` exposed: `id`, `ocid`, `year`, `month`, `method`,
`internal_type`, `locality`, `region`, `suppliers`, `buyer`, `amount`,
`date`, `title`, `description`, and `budget`.

Missing values were observed in some procedures, including:

```json
{
  "suppliers": null,
  "budget": null
}
```

Consumers must therefore handle these fields as nullable.

## Example record

One record visible in the first page contained:

```text
ocid:   ocds-5wno2w-CE-20250002783776-3214
buyer:  EMPRESA ELÉCTRICA QUITO S.A. E.E.Q.
amount: 623575.816500
budget: 623575.8165
```

The differing decimal representations were returned by the source and
should not be normalized before preserving the raw response.

## Out-of-range pagination observation

An earlier request used `page=999999` with an obsolete query whose base
result was already empty (`total=0`, `pages=0`). It returned:

```text
HTTP=200 TIME=3.989063s SIZE=45bytes
```

This only shows that the server did not reject that large positive page at
the HTTP level. It does not establish what happens when `page > pages` for
the confirmed, non-empty EEQ query. That case remains untested.

## Record endpoint and rate limiting

The tested record request was:

```text
GET https://datosabiertos.compraspublicas.gob.ec/PLATAFORMA/api/record?ocid=ocds-5wno2w-CPC-EEQ-2025-003-3214
```

After several preceding requests, it returned:

```text
HTTP=429 TIME=0.251794s SIZE=6625bytes
```

The `429` response headers and body were not preserved or inspected. It is
therefore unknown whether it included `Retry-After` and whether its body
was JSON, HTML, or another format. No claim should be made about either.

Successful responses separately exposed:

```http
Content-Type: application/json
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 7
```

`X-RateLimit-Remaining: 33` was observed at another time. This confirms
active rate limiting, but not the quota window or key. Future clients
should pace requests conservatively and handle `429` with backoff.

## Minimum pending checks

- functional meaning of `local=1`;
- exact rate-limit window and key;
- `Retry-After` and body format for `429` responses;
- out-of-range behavior for a non-empty result set;
- direct filtering by EEQ RUC or `buyerId`.

Until verified, ingestion should reproduce the confirmed buyer-name query
and avoid assigning undocumented semantics to `local=1`.

## Observation series of 2026-10-10

- Time: two blocks, 06:58 to 06:59 and 07:27 to 07:28 `UTC-05:00` (`Date`
  headers: 11:58 and 12:27 to 12:28 GMT).
- Method: `curl` with its default user agent, from a terminal, one request at
  a time and 4 to 14 seconds apart inside a block, against the confirmed
  buyer-name query for 2025 (and one `api/record` request).
- Scope: six requests were sent. The first block stopped by its own rule
  when `X-RateLimit-Remaining` fell below 20, and the second block resumed
  after a pause of 29 minutes. A planned re-check at 5 minutes was replaced by
  request 5. Bodies were analyzed locally and were not preserved.

| # | Query | HTTP | Total time | Bytes | `X-RateLimit-Remaining` |
| - | ----- | ---: | ---------: | ----: | ----------------------: |
| 1 | confirmed query, `page=1` | 200 | 8.70 s | 5944 | 47 |
| 2 | confirmed query, `page=29` | 200 | 6.57 s | 2100 | 34 |
| 3 | confirmed query, `page=30` | 200 | 5.88 s | 44 | 22 |
| 4 | confirmed query without `local=1`, `page=1` | 200 | 10.34 s | 5944 | 8 |
| 5 | confirmed query, `page=1`, 29 minutes after 4 | 200 | 12.01 s | 5944 | 57 |
| 7 | `api/record` for one `ocid` | 200 | 8.05 s | 33833 | 44 |

### Response body

- Compact JSON with no whitespace. Top-level keys, in order: `total`, `page`,
  `pages`, `data`. `total`, `page` and `pages` are integers; `data` is a list.
- Non-ASCII characters are written as `\uXXXX` escapes, so the body is pure
  ASCII. `Content-Type: application/json` carries no charset. There is no
  `Content-Length`: the responses use `Transfer-Encoding: chunked`.
- Every record carried the same 15 keys in the same order, with these types:
  `id` integer, `ocid` string, `year` integer, `month` integer, `method`
  string, `internal_type` string, `locality` string, `region` string,
  `suppliers` string or `null`, `buyer` string, `amount` string, `date`
  string, `title` string, `description` string, `budget` string or `null`.
- `amount` and `budget` are JSON strings, not numbers. `amount` had 6
  decimals in all 14 records and `budget` had 1 to 4. Both held the same
  numeric value in 11 of the 12 records that had a `budget`. They must be
  preserved as received.
- `date` is an ISO 8601 timestamp with a UTC offset (`-05:00`).
- Nulls over the 14 records of pages 1 and 29: `suppliers` was `null` in 3,
  `budget` in 2, and both in the same record in 2.

### Pagination

- Page 1 held 10 records and page 29 held 4, which is `284 - 28 x 10`. This
  is consistent with a page size of 10, but only these two pages were seen.
- `page=30` with `pages=29` returned HTTP 200, not an error. `page` echoed the
  requested number, `total` and `pages` were unchanged, and `data` was empty.
  An empty `data` therefore does not by itself mean that the search has no
  results.
- The 45-byte reply of 2026-10-03 for `page=999999` is exactly the size of this
  shape with `total` 0, `pages` 0 and the page echoed. That is consistent with
  it, not an observation of its content.

### `local=1`

For this query and page 1, removing `local=1` returned the same `total` and a
byte-identical body (same SHA-256 as request 1). The parameter changed nothing
here. Its meaning for other queries is still unknown.

### Rate limiting

- `X-RateLimit-Limit: 60` and `X-RateLimit-Remaining` were present on every
  `200`. No `Retry-After` and no reset header appeared on a `200`.
- Within the first block, `Remaining` read 47, 34, 22 and 8, with `Date`
  gaps of 11, 10 and 14 seconds: drops of 13, 12 and 14. In the second block,
  requests 5 and 7 read 57 and 44, 13 seconds apart: a drop of 13. The drop
  tracks the seconds elapsed between requests, about one unit per second, not
  the number of requests sent by this client.
- The first request of each block already read below 60 (47 and 57), so units
  had been consumed before it by something other than this client.
- Request 5 came 29 minutes after request 4, which read 8, and read 57. The
  counter had refilled within 29 minutes. The window length itself was not
  measured.
- This fits a window of about a minute that other callers also consume at
  roughly one unit per second, that is, a key shared with other callers. It
  is an inference from these values and cannot be told apart from a
  time-based counter. A first interpretation of "about 13 units per request"
  was wrong: request 5 read 57 from a refilled counter.
- The available budget at a moment is therefore not a function of this
  client's own request count. `Remaining`, read on each response, is the only
  signal observed. The values 7 and 33 seen on 2026-10-03 are compatible.

### `api/record`

- Request 7 asked for the `ocid` that returned `429` on 2026-10-03. It
  returned HTTP 200 with `Content-Type: application/json`, 33833 bytes,
  chunked, and `Remaining` 44.
- The body is a JSON OCDS release package, ASCII only and compact, with `/`
  written as `\/` (95 times; the search bodies have none). Top-level keys, in
  order: `uri`, `license`, `version` (`1.1`), `releases`, `publisher`,
  `extensions` (8 entries), `publishedDate`, `publicationPolicy`.
- `releases` held one release whose `ocid` equals the requested one. Its keys,
  in order: `id`, `tag`, `date`, `ocid`, `buyer`, `awards`, `tender`,
  `parties`, `language`, `planning`, `contracts`, `initiationType`. `tag` was
  `planning`, `tender`, `award`, `contract`.
- Money amounts under `value.amount` are JSON numbers (floats), while the
  search results carry `amount` and `budget` as strings.
- Only one record was seen. Whether sections vary between records, and the
  response for an `ocid` that does not exist, are unknown.

### Other response behavior

- `Docker-Distribution-Api-Version` appeared twice in every response, so
  header names can repeat. `Server` was absent in request 1 and present in the
  others. `Cache-Control: no-cache, private` was present.
- Total time per request was 5.9 to 12.0 s here, against 4.0 to 5.3 s for the
  successful requests of 2026-10-03.

### Still unverified after this series

- Meaning of `local=1`, beyond having no effect on this query.
- Rate-limit window length (known only to be 29 minutes or less, consistent
  with about a minute) and key (consistent with a shared key, not shown).
- `Retry-After` and body of a `429`. They were not provoked on purpose.
- Variation of the `api/record` structure between records, and the response
  for an unknown `ocid`.
- Direct filtering by EEQ RUC or `buyerId`.
