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
