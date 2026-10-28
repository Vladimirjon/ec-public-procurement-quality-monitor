# Ingestion Specification

> Last synced: 2026-10-28. Owned artifacts: `src/ec_procurement_quality/domain/ingestion_catalogue.py`, `src/ec_procurement_quality/application/ingest_ports.py`, `src/ec_procurement_quality/application/ingest_use_case.py`, `src/ec_procurement_quality/infrastructure/system_clock.py`, `tests/unit/ingest/test_ingest_use_case.py`, `tests/unit/ingest/test_ingestion_catalogue.py`, `tests/unit/ingest/test_ingest_layers.py`, `tests/unit/ingest/conftest.py`, `tests/integration/ingest/`.

## Purpose

How one bounded ingestion works: `run_ingest` requests the search pages of one
buyer and year from the source one by one, keeps every response in the local
raw evidence store and in PostgreSQL, and records the run and its audit events
from a closed catalogue, so that a run can be interrupted, reconciled and
resumed. It is its own capability because it is the use case that joins
`source-access`, `raw-evidence` and `persistence` through ports (the human
wrote it by hand, Day 19), while `cli` owns only the command, its arguments,
its output and its exit codes. The real portal has not been queried yet: it is
verified with in-memory doubles, simulated transports and throwaway databases.

## Requirements

### Requirement: IG-1 — Pages are requested in order, stored in both stores, and the run ends `succeeded`

The system SHALL request the pages of the scope in increasing order, store each
response in both stores, append `page-completed` for each page, and end the run
`succeeded`. No page above the last page the source reports SHALL be requested,
and reaching it is not a failure: whenever a completed page `p` satisfies
`p >= pages`, the run appends `last-page-reached` (after that page's
`page-completed`), requests nothing more and ends `succeeded`, whatever the
scope's last page is. Repeating a scope SHALL create a new run with a new
execution id, keep one object and one `raw_evidence` row per content, and give
each run its own observations and events.

**Source:** ingest-command · intent.md § AC1, AC2, AC3

#### Scenario: Two pages
- **WHEN** the scope is pages 1 to 2 of a year and buyer and the source answers pages 1 and 2 with `200` page bodies whose `pages` is 3
- **THEN** exactly two requests are made, in order; the run `<A>` has status `succeeded`, two observations and the events `run-started`, `page-completed` (page 1, sequence 1) and `page-completed` (page 2, sequence 2), in that order

#### Scenario: End of the result set
- **WHEN** the scope is pages 1 to 5 and the source reports `pages` 2
- **THEN** only pages 1 and 2 are requested, `last-page-reached` (page 2, `pages` 2) is appended and the run ends `succeeded`

### Requirement: IG-2 — A failure with a response keeps the response first; a failure without one records no observation

The system SHALL, when a page fails and a response was received, store that
response in both stores first (local store, then the PostgreSQL observation),
then append `page-failed`, request no later page, and end the run `failed`. When
a failure happens before any response arrives, the system SHALL append
`page-failed` with no sequence number, record no observation, use no sequence
number, and end the run `failed`.

**Source:** ingest-command · intent.md § AC4, AC5

#### Scenario: A `500` on page 2
- **WHEN** page 1 answers `200` and page 2 answers `500` with an empty body
- **THEN** page 2's response is in both stores with its status as received and size 0, `page-failed` (page 2, sequence 2) follows, page 3 is not requested and the run ends `failed`

#### Scenario: A connect error on page 2
- **WHEN** page 2 raises a connect error before the status arrives
- **THEN** there is no observation for sequence 2, `page-failed` has sequence `None` and failure `transport`, and the run ends `failed`

### Requirement: IG-3 — Storage and integrity failures stop the run, and an `OSError` from the store is never proof that nothing was written

The system SHALL end the run `failed` when the local store or an integrity check
fails, append `storage-failed`, and, after an `OSError` from `store`, ask the
store port for that observation (`read_observation`) and record it in
PostgreSQL when it was published; when that read-back itself fails, the
observation SHALL be treated as not recorded. A database write that PostgreSQL
refused SHALL be answered once and never attempted again in the same invocation,
not even by the cleanup after a Ctrl+C; when the refused write is itself a
failure-path write, no further event is added and, if `finish_run(failed)` is
refused, the run stays `running`.

**Source:** ingest-command · intent.md § AC6; execution-plan.md § State machines

#### Scenario: Observation published, then `OSError`
- **WHEN** a store double publishes the observation for sequence 2 and then raises `OSError`
- **THEN** the use case reads it back, records it in PostgreSQL before closing the run, and the run ends `failed`

#### Scenario: Refused `finish_run(failed)`
- **WHEN** PostgreSQL refuses `finish_run(failed)` and a Ctrl+C then lands while the refusal is reported
- **THEN** nothing more is written to the run, which stays `running`

### Requirement: IG-4 — No retries

The system SHALL request each page at most once per run; a failed page is
retried only by a resumption (IG-8), which is a new, audited run.

**Source:** ingest-command · intent.md § AC17

#### Scenario: Failing page
- **WHEN** page 2 fails in any way of IG-2
- **THEN** the simulated source receives exactly one request for page 2 from that run

### Requirement: IG-5 — An interruption keeps what was completed and closes the run on a best-effort basis

The system SHALL, on Ctrl+C, keep what was completed, attempt to record the
pending observation, append `run-interrupted` and close the run `failed`, and
leave exit code 130 to `cli`; a `MemoryError` or another unexpected exception
SHALL be audited as `unexpected-error` in the same way. When the cleanup cannot
finish (a second Ctrl+C, an unreachable or refusing database) the run MAY stay
`running`, to be closed by the next ingest (IG-7). The cleanup SHALL read the run
first and add nothing to a run already finished. It SHALL write only through a
connection that holds the ingest exclusion: when the interruption or exception
lands after a lost connection and before the exclusion is held again, nothing is
read from or written to the run, every connection obtained is closed and the run
stays `running`. Nothing guarantees that the cleanup completes.

**Source:** ingest-command · intent.md § AC7, AC11; execution-plan.md § State machine K

#### Scenario: Ctrl+C while page 2 is requested
- **WHEN** a `KeyboardInterrupt` is raised by the transport while page 2 is requested and PostgreSQL is reachable
- **THEN** page 1 keeps its `page-completed`, `run-interrupted` (page 2) is appended and the run ends `failed`

#### Scenario: Ctrl+C after the final `finish_run` committed
- **WHEN** a `KeyboardInterrupt` lands just after `finish_run` committed and before it returned
- **THEN** the cleanup finds the run finished, adds no event or observation and calls no `finish_run`

### Requirement: IG-6 — A lost database connection never leads to the assumption that the write did not happen

The system SHALL, when the database connection is lost, open exactly one new
connection, take the ingest exclusion again on it, repeat only idempotent
operations with exactly the same values (an event is appended again only when
`list_audit_events` shows none with the same type, detail and instant), and
close the run `failed`; when it cannot, it SHALL leave the run `running` for
reconciliation. Every connection loss SHALL give exit code 1 (via `cli`) except
when the lost operation is the final `finish_run(succeeded)` and its exact repeat
on the new connection returns the run `succeeded` with the same `finished_at`:
then the run is confirmed `succeeded`. Closing the database connection at the
end SHALL never change how the run ended.

**Source:** ingest-command · intent.md § AC8, AC15 (decision P-2); execution-plan.md § State machine C

#### Scenario: Server session terminated while page 2 is requested
- **WHEN** the adapter's session is terminated and the new connection opens and takes the exclusion
- **THEN** `storage-failed` (page 2, store `postgresql`) is appended and the run ends `failed`

#### Scenario: New connection refused
- **WHEN** new connections to the database are refused
- **THEN** no second attempt is made and the run stays `running`

### Requirement: IG-7 — Every ingest holds the exclusion and reconciles runs left `running` before it starts its own

The system SHALL, before creating its own run and holding the ingest exclusion
(one ingest per database; a second one refuses to start and changes nothing),
reconcile each run that PostgreSQL lists as `running`: verify every PostgreSQL
observation against the local store (using the listing of `raw-evidence`),
record every observation present only in the local store, append
`observation-reconciled` and `run-closed-by-reconciliation`, and finish the run
`failed`. A problem SHALL be recorded as `reconciliation-failed` with one value
of the closed list (`local-observation-missing`, `local-observation-different`,
`local-observation-unreadable`, `object-missing`, `object-integrity`,
`sequence-gap`, `postgresql-observation-conflict`, `local-listing-failed`), the
run SHALL be finished `failed`, no new run created, and the exit code is 1 (via
`cli`). A run whose process still holds the exclusion SHALL never be touched,
and an orphan object SHALL be left in place and count for nothing.

**Source:** ingest-command · intent.md § AC10, AC23; execution-plan.md § State machine R

#### Scenario: Crash between the two writes
- **WHEN** run `<A>` is `running`, PostgreSQL holds its observations 1 and 2 and the local store lists 1, 2 and 3
- **THEN** the next ingest records observation 3, appends `observation-reconciled` (sequence 3) and `run-closed-by-reconciliation` (`reconciled_observations` 1), finishes `<A>` as `failed` and only then starts its own run

### Requirement: IG-8 — A resumption is a new run that requests only what the chain has not completed

The system SHALL, for a resumption of an existing run that is not `succeeded`,
create a new run with the scope of the run it resumes, link it with a
`run-started` event whose detail holds `{"resumes": "<A>", "first_page": N}`,
request nothing that the chain of earlier runs completed, and start at the first
page not completed (`first_page` equal to the scope's `last_page + 1` when
nothing is left). A chain that is cyclic, malformed or contradictory (including
a `last-page-reached` event that is not valid, and a run closed before its
`run-started` event) SHALL be an integrity failure: nothing is added to any run
of the chain and no new run is created. The target SHALL be checked right after
the exclusion is taken and before reconciliation.

**Source:** ingest-command · intent.md § AC9, AC11, AC24

#### Scenario: Resume after page 3 failed
- **WHEN** run `<A>` (pages 1 to 4) completed pages 1 and 2 and failed on page 3, and `--resume <A>` is run
- **THEN** run `<B>` has the same scope, its `run-started` detail is `{"resumes": "<A>", "first_page": 3}`, pages 3 and 4 only are requested, and `<B>` ends `succeeded`

### Requirement: IG-9 — Identities, times and scope

The system SHALL give every run a new execution id of the form
`ingest-<UTC time>-<8 hex>` that follows the F1 pattern and is never a Windows
reserved device name, check a new id against both stores through their ports
before `start_run` while holding the exclusion, number the responses a run
obtains from 1 without gaps, take every time written from the one injected
clock with a UTC offset, and store as the run's scope a JSON object with exactly
the keys `scope_version`, `source`, `base_url`, `buyer`, `year`, `first_page`
and `last_page`, with no float. Every audit event SHALL have a type of the closed
catalogue (`run-started`, `page-completed`, `page-failed`, `storage-failed`,
`last-page-reached`, `run-interrupted`, `unexpected-error`,
`observation-reconciled`, `run-closed-by-reconciliation`,
`reconciliation-failed`) and a detail that holds only identities, numbers and
fixed words, never a URL, a header value, body bytes, a setting or the text of
an exception message.

**Source:** ingest-command · intent.md § AC12, AC13; execution-plan.md § Audit details

#### Scenario: Colliding id
- **WHEN** an id source first returns an id for which `read_run` finds a run
- **THEN** that id is not used, a new one is drawn and `start_run` is never called with the taken id

### Requirement: IG-10 — Progress and errors are reported without secrets

The system SHALL report through the reporter port at least one line for each page
processed (naming the page and, when a response was stored, its sequence, status
and content hash), and exactly one line for each database operation refused or
lost, naming the operation and the identity concerned, with nothing from the
error but at most its class name; a message SHALL never include a URL, a header
value, a body, a setting or a password. An exception from a progress line (for
example an `OSError` of a stderr pipe whose reader has gone, when stderr exists)
is handled by the use case's rules: an `OSError` closes the run `failed` with
`unexpected-error`, and a Ctrl+C follows IG-5. No exception chain or traceback
SHALL be printed.

**Source:** ingest-command · intent.md § AC15 (accounting correction of 2026-10-28, finding F-33); execution-plan.md § Outcome table "Other stderr lines of the command"

#### Scenario: Markers
- **WHEN** the password is `synthetic-password-marker`, a body holds `synthetic-body-marker`, a header value is `synthetic-header-marker` and a `Set-Cookie` carries a session value
- **THEN** none of the markers or the cookie value appears in stdout, stderr or any stored audit detail

### Requirement: IG-11 — The use case lives in `application` and works only through ports

The system SHALL keep `run_ingest` and its ports in `application`, using only the
standard library, `domain` and the ports (the F2 source port, the
`RawEvidenceStore` port with its listing, the `IngestionRepository` port with
`list_runs` and the exclusion, a clock, an execution-id source, a repository
opener and a reporter), with no SQL and no mechanism name (`advisory`, `pg_`) in
`application`, the catalogue and scope in `domain`, and the real clock in
`infrastructure`. One `SercopSource` and one repository SHALL serve an
invocation from one thread and be closed when it ends, the repository being
replaced only by the single new connection of IG-6. `interfaces` SHALL read the
arguments and the environment and build the adapters; no dependency is added.

**Source:** ingest-command · intent.md § AC18, AC19; execution-plan.md § Ownership

#### Scenario: Layer tests
- **WHEN** `uv run pytest tests/unit -q -k layer` is run
- **THEN** it passes, and a grep of `src/ec_procurement_quality/application/` for SQL keywords, `advisory`, `pg_`, `psycopg` and `httpx` finds nothing

## Invariants

1. A response is stored before it is recorded as an event: the order is the
   local store, the PostgreSQL observation, the page event, then `finish_run`
   (IG-2).
2. A database write that PostgreSQL refused is never attempted again in the same
   invocation (IG-3), and a finished run is closed to additions (IG-5).
3. The cleanup writes only through a connection that holds the ingest exclusion
   (IG-5, IG-6).
4. `page-completed` is the only statement of the ingestion that a `200` body
   passed the source adapter's checks; a later stage (F5) should take its inputs
   from it and not from every `200` observation, and must keep normalized
   records free of duplicates when a scope is repeated.
5. `api/record` is not fetched by the ingestion; nothing designs the
   normalization.
6. Raw responses are evidence and are never overwritten (ADR 0002); the
   ingestion only appends.

## Open reservations

| ID | Reservation | Severity | Source |
|---|---|---|---|
| F-20 | Two second-order double-fault paths have no test: a normal-path append (`run-started`, `page-completed`, `last-page-reached`) lost when the recovery then fails (`ingest_use_case.py` line 598 at `108c5a0`), and an append on the new connection lost again after the re-check of State machine C (lines 388-389). Planned behavior shown by the auditor's experiments: nothing is lost and the run stays `running`. Restated and accepted by the human on 2026-10-28 | LOW | ingest-command · tasks.md § Carried reservations; audit.md round 8 § Accepted limitations |
| F-23 | After a refused write (`page-failed`, `storage-failed`, a normal-path event or the final `finish_run(succeeded)`), a Ctrl+C or a `MemoryError` that lands before the run is closed makes the cleanup read the run, append `run-interrupted` (or `unexpected-error`) and close it `failed` (decision D-2 option 1). The refused write is not attempted again. Accepted by the human on 2026-10-28 | LOW | ingest-command · audit.md round 8 § Accepted limitations |
| F-34 | A run closed before its `run-started` event cannot be resumed: `--resume` answers `invalid resumption chain <A>`, exit 1. By design (IG-8): such a run requested nothing, and a fresh ingest of the scope does the same work. Accepted by the human on 2026-10-28 | LOW | ingest-command · audit.md round 8 § B F-34 |
| U1 | No run against the real SERCOP portal has been made: the first comparison of the live responses with the observations is the human's manual run (Day 20), which has not happened. Restated on 2026-10-28 (the same reservation as `source-access` U1) | MED | ingest-command · tasks.md § Carried reservations |

## Contributing features

| Feature | Shipped | What it established |
|---|---|---|
| ingest-command (F4) | 2026-10-28 | The `run_ingest` use case and its ports in `application`, the closed catalogue, scope and execution-id rule in `domain`, and the real clock in `infrastructure`: page loop, write order, failure, interruption, lost connection, reconciliation, resumption and identities (IG-1 to IG-11) |

## Related ADRs

None registered here. The binding decisions are the project-level ADRs in
`docs/adr/`, which carry no `Capability:` field: ADR 0001 (modular monolith),
ADR 0002 (immutable raw storage), ADR 0005 (raw evidence store layout), ADR 0006
(HTTP client for source access) and ADR 0007 (PostgreSQL persistence).
