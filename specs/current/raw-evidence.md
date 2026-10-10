# Raw Evidence Specification

> Last synced: 2026-10-09. Owned artifacts: `src/ec_procurement_quality/domain/content_hash.py`, `src/ec_procurement_quality/domain/raw_evidence.py`, `src/ec_procurement_quality/application/raw_evidence_store.py`, `src/ec_procurement_quality/infrastructure/local_disk_raw_evidence_store.py`, `tests/unit/test_content_hash.py`, `tests/unit/test_raw_evidence.py`, `tests/unit/test_local_disk_raw_evidence_store.py`.

## Purpose

How a source response is preserved as raw evidence on the local disk: the
exact bytes once under their SHA-256 (an *object*), one JSON *observation* per
response obtained, write-once publication, and integrity checks on read. The
layout is fixed by ADR 0005 (and ADR 0002). It is its own capability, separate
from `cli` and `project-toolchain`, because it is the first piece of product
domain behavior. It is a library only: no CLI command, HTTP access, use case
or PostgreSQL code calls it yet.

## Requirements

### Requirement: RE-1 — Content hash value object

The system SHALL identify bytes by `ContentHash`, an immutable value object
holding the SHA-256 of the bytes as exactly 64 lowercase hexadecimal
characters, built with `ContentHash(hexdigest)` or `ContentHash.of(content)`,
equal and hashable by value, and SHALL raise `ValueError` for anything that is
not exactly 64 lowercase hex characters.

**Source:** raw-evidence-store · intent.md § AC1

#### Scenario: Hash and compare
- **WHEN** `ContentHash.of(b"abc")` is built twice
- **THEN** `hexdigest` is `ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad`, the two values are equal, have the same `hash()` and are one dict key

#### Scenario: Invalid digest
- **WHEN** `ContentHash` is built from an uppercase string, a 63-character string, a non-hex string, or a string with a trailing newline
- **THEN** it raises `ValueError`, and assigning to `hexdigest` of a valid value raises

### Requirement: RE-2 — Layout of the store

The system SHALL keep each object at `objects/<first two characters of the
hexdigest>/<hexdigest>` (no extension, exactly the content bytes) and each
observation at `observations/<execution id>/<sequence>.json` (decimal sequence,
no sign, no leading zeros) under a root directory given to the adapter, with
temporary files under the root but outside `objects/` and `observations/`, and
SHALL read and write nothing outside the root. The root need not exist;
directories are created on the first write.

**Source:** raw-evidence-store · intent.md § AC2; execution-plan.md § Binding constraints "On-disk layout"

#### Scenario: Store one response
- **WHEN** execution `synthetic-exec-001`, sequence `1`, `GET https://source.invalid/api/search?year=2025&page=1`, status `200`, header `Content-Type: application/json`, captured at `2026-10-09T10:15:00-05:00`, content `b"abc"` is stored
- **THEN** `objects/ba/ba7816bf...20015ad` holds exactly `b"abc"`, `observations/synthetic-exec-001/1.json` exists, reading the content by hash returns `b"abc"`, reading the observation by execution and sequence returns a record equal to the one `store` returned, and no other file remains under the root

### Requirement: RE-3 — Observation record structure

The system SHALL write each observation as a UTF-8 JSON object with exactly the
keys `schema_version` (`1`), `execution_id`, `sequence`, `captured_at`
(`datetime.isoformat()` output, keeping the UTC offset given), `request`
(`method` and `url`, exactly as given, no normalization), `response`
(`status` and `headers`, a list of `[name, value]` pairs with names as
received, in order, repeats kept) and `content` (`sha256` and `size`), and the
same observation SHALL always serialize to the same bytes. The structure and
semantics are the contract; the exact bytes (ASCII-only JSON, indent 2, keys in
the order above, one trailing newline) are as built, not a contract.

**Source:** raw-evidence-store · execution-plan.md § Binding constraints "Observation record format" and § Proposed approach "Implementation notes (as built, Revision 2)"; audit.md § Notes N1

#### Scenario: Record fields
- **WHEN** the response of RE-2 is stored
- **THEN** `json.loads` of `1.json` has exactly the keys above with `schema_version` `1`, `captured_at` `2026-10-09T10:15:00-05:00`, the URL with its query string, `size` `3` and the `sha256` of `b"abc"`

### Requirement: RE-4 — Identical content is one object and one observation per response

The system SHALL, when identical bytes are obtained by two responses, keep one
object and write one observation for each response, each naming the same
`sha256`, and SHALL NOT rewrite the existing object.

**Source:** raw-evidence-store · intent.md § AC3

#### Scenario: Same bytes from two executions
- **WHEN** the same bytes are stored by `synthetic-exec-001` sequence `1` and by `synthetic-exec-002` sequence `1`
- **THEN** exactly one file exists under `objects/`, exactly two under `observations/`, and the object's bytes and modification time are the same before and after the second store

### Requirement: RE-5 — Error and incomplete responses are preserved as received

The system SHALL preserve every response it is given with its status as is, and
SHALL NOT judge whether a response is usable.

**Source:** raw-evidence-store · intent.md § AC4

#### Scenario: Error, empty and truncated bodies
- **WHEN** status `429` with an HTML body, status `503` with an empty body, and status `200` with the truncated body `b'{"total": 1, "data": [{"oc'` are stored
- **THEN** each is stored without error, each observation keeps its status, the empty body has `size` `0` and the object `e3b0c442...b855`, and each object reads back as the exact bytes given

### Requirement: RE-6 — `Set-Cookie` is never persisted; request headers are not recorded

The system SHALL drop every response header whose name is `set-cookie`
(ignoring case) before building the observation, keep every other response
header with its name as received, in order, including repeated names, SHALL
reject an `Observation` built directly with a `Set-Cookie` header with
`ValueError`, and SHALL NOT accept or record request headers.

**Source:** raw-evidence-store · intent.md § AC5

#### Scenario: Mixed headers
- **WHEN** headers `Content-Type`, `Set-Cookie: synthetic-session=s1`, `X-RateLimit-Remaining: 7`, `set-cookie: synthetic-other=s2`, `X-RateLimit-Remaining: 6` are stored
- **THEN** the returned observation and the file hold only `Content-Type` and the two `X-RateLimit-Remaining` headers in that order, and the file bytes contain neither cookie value

#### Scenario: Observation built with Set-Cookie
- **WHEN** an `Observation` is built with a `SET-COOKIE` header
- **THEN** it raises `ValueError`

### Requirement: RE-7 — Reads verify; errors are explicit and carry no content

The system SHALL verify on read: reading an object whose bytes no longer match
its name raises `EvidenceIntegrityError`; a missing object or observation
raises `EvidenceNotFoundError`; and reading an observation raises
`EvidenceIntegrityError` for a file that is not valid UTF-8 JSON, lacks or adds
a key, has a `schema_version` other than the integer `1`, fails `Observation`
validation, has a `captured_at` that is not the `isoformat()` of the value
parsed from it, or names an execution or sequence other than its path. Both
errors SHALL share the base `RawEvidenceError`, and their messages SHALL name
hashes, execution ids, sequences, paths and fixed reasons only, never content
bytes or header values. `OSError` SHALL propagate unwrapped.

**Source:** raw-evidence-store · intent.md § AC6; execution-plan.md § Binding constraints "Errors"

#### Scenario: Tampered object
- **WHEN** `b"abc"` is stored, its object file is overwritten from outside with `b"abd"`, and it is read by hash
- **THEN** `EvidenceIntegrityError` is raised, its message names the hash and contains neither body

#### Scenario: Missing object
- **WHEN** a hash that was never stored is read
- **THEN** `EvidenceNotFoundError` is raised

### Requirement: RE-8 — Existing evidence is never overwritten

The system SHALL treat different content under an identity that already exists
as `EvidenceIntegrityError` and leave the existing file untouched, SHALL
compare an existing observation by its bytes (so any input that changes the
record, such as another status, headers, method, URL or capture time, is a
conflict), and SHALL treat presenting the identical response again as no error
and no change. No code path SHALL replace, truncate, append to or delete a
file under `objects/` or `observations/`. A final name that appears between the
absence check and publication SHALL be read and verified, not overwritten: other
bytes raise `EvidenceIntegrityError`, identical bytes are reused untouched.

**Source:** raw-evidence-store · intent.md § AC7; execution-plan.md § Binding constraints "Atomic, write-once publication"; audit.md § Round 2 A1

#### Scenario: Conflicting object
- **WHEN** `objects/ba/ba7816bf...20015ad` already holds `b"tampered"` and content `b"abc"` is stored
- **THEN** `EvidenceIntegrityError` is raised, the file still holds `b"tampered"`, and no observation is written

#### Scenario: Conflicting and identical observation
- **WHEN** `synthetic-exec-001` sequence `1` is stored again with other content, or the same content with status `500`, and then with the identical response
- **THEN** the first two raise `EvidenceIntegrityError` with `1.json` unchanged; the identical one returns an equal observation and changes the bytes and modification times of neither `1.json` nor the object

#### Scenario: Name appears before publication
- **WHEN** the final object name (or observation name) appears holding other bytes after `store` checked it absent and before it is published
- **THEN** `EvidenceIntegrityError` is raised and the planted bytes are kept; with exactly the bytes `store` would write, `store` returns an equal observation and the planted file is unchanged (guarded by the four `race` tests)

### Requirement: RE-9 — Observation after its object; orphan objects are kept

The system SHALL publish an observation only after its object, so that an
observation never points to a missing object, and SHALL NOT delete an orphan
object left by a failure between the two writes.

**Source:** raw-evidence-store · intent.md § AC8

#### Scenario: Observation cannot be written
- **WHEN** a regular file sits at `<root>/observations` and a response is stored
- **THEN** `store` raises `OSError`, the object exists with the exact bytes, and no observation file exists

#### Scenario: Object cannot be written
- **WHEN** a regular file sits at `<root>/objects` and a response is stored
- **THEN** `store` raises `OSError` and nothing exists under `observations/`

### Requirement: RE-10 — Atomic publication

The system SHALL write each file completely to a temporary file in the same
store, flush it and sync it with `os.fsync` (called through the `os` module),
and only then make it visible under its final name with an operation that fails
when the name exists, so that an interrupted write never leaves a partial or
empty file under a final name and a later attempt stores the complete content.
On any exception the temporary file SHALL be removed when possible and the
exception SHALL propagate.

**Source:** raw-evidence-store · intent.md § AC9; execution-plan.md § Binding constraints "Atomic, write-once publication"

#### Scenario: Interrupted sync
- **WHEN** `os.fsync` raises `OSError` while `b"abc"` is stored
- **THEN** `store` raises `OSError`, the final object name does not exist, no observation exists and no temporary file is left; with `os.fsync` restored, the same store succeeds and the object holds exactly `b"abc"`

### Requirement: RE-11 — Invalid input is rejected before anything is written

The system SHALL raise `ValueError` before creating any file or directory when:
the execution id does not match `[a-z0-9][a-z0-9-]{0,63}`; the sequence is not
an `int` (a `bool` is rejected) or is negative; the method or URL is empty; the
status is outside 100 to 599; the capture time has no UTC offset; the size is
negative; or `Observation.headers` is not a `tuple` of `(str, str)` tuples.
`validate_execution_id` and `validate_sequence` SHALL apply the first two rules
to both `Observation` and `read_observation`. A wrong type that no rule covers
SHALL raise `TypeError`: `content` that is not `bytes` (a `bytearray` too), a
`content_hash` that is not a `ContentHash`, and a header element that cannot be
unpacked into two items.

**Source:** raw-evidence-store · intent.md § AC10; execution-plan.md § Binding constraints "Public names and signatures" and § Proposed approach "Implementation notes (as built, Revision 2)"

#### Scenario: Invalid identity or time
- **WHEN** `store` is given execution id `../escape`, `Synthetic-Exec`, `""` or a 65-character id, sequence `-1`, status `99` or `600`, or a naive capture time
- **THEN** it raises `ValueError` and the root contains no file (it need not exist)

#### Scenario: Invalid read identity
- **WHEN** `read_observation("../escape", 1)` is called
- **THEN** it raises `ValueError`

### Requirement: RE-12 — Port, adapter and layer placement

The system SHALL expose the store through the `RawEvidenceStore` protocol in
`application` with exactly `store(*, execution_id, sequence, method, url,
status, headers, captured_at, content) -> Observation`,
`read_content(content_hash) -> bytes` and
`read_observation(execution_id, sequence) -> Observation`; SHALL provide
`LocalDiskRawEvidenceStore(root: Path)` in `infrastructure`, which satisfies
the protocol structurally; and SHALL keep `ContentHash`, `Observation` and the
errors (`RawEvidenceError`, `EvidenceIntegrityError`, `EvidenceNotFoundError`)
in `domain`. The adapter SHALL write no log output and SHALL add no dependency.

**Source:** raw-evidence-store · intent.md § AC11, AC12; execution-plan.md § Binding constraints "Public names and signatures", "No logging and no secrets", "Layer imports"

#### Scenario: Adapter typed as the port
- **WHEN** a test assigns `LocalDiskRawEvidenceStore(tmp_path)` to a variable annotated `RawEvidenceStore` and `uv run mypy .` is run
- **THEN** `mypy` exits 0, and `uv run pytest tests/unit -q -k layer` passes, including the check that `application` imports only the standard library, `domain` and itself

## Invariants

1. A file under `objects/` or `observations/` is written once and
   never replaced, truncated, appended to or deleted by the store; the only
   deletion in the code is of its own temporary file under `tmp/`.
2. An observation is written only after its object; an orphan object is valid
   evidence and is never deleted.
3. Execution ids and hexdigests are lowercase only, so case-insensitive file
   systems cannot merge two names. An execution id equal to a Windows reserved
   device name (`con`, `nul`, ...) is not rejected; F4 must generate ids that
   avoid them.
4. An existing observation is compared by its bytes and `read_observation`
   accepts only `schema_version` `1`; any future change of the record bytes
   must bump `schema_version`, keep version 1 readable, and compare an
   idempotent re-store against the bytes of the existing file's version, or an
   identical re-store becomes a false conflict (audit N1).
5. Messages, logs and tests never contain content bytes, header values, cookies
   or real SERCOP records; URLs in tests use the reserved `.invalid` domain.
6. Not a guarantee of the store, whatever the code does today: (a) the record
   bytes are as built, not a contract; (b) the POSIX file mode of published
   files is `0600` only because the published name is a hard link to a
   `tempfile` temporary file, it is incidental, no requirement asks for it and
   no test asserts it, and permission hardening and read-only evidence are out
   of scope (ADR 0005).
7. The store does not scale or retain: no compression, retention, automatic
   cleanup of orphan objects or leftover temporary files, listing, indexing, or
   bulk verification command exists (ADR 0005 consequences).

## Open reservations

| ID | Reservation | Severity | Source |
|---|---|---|---|
| U1 | Behaviors no test asserts, none required by an acceptance criterion: the POSIX file mode; the `TypeError` cases (non-`bytes` `content`, non-`ContentHash` `content_hash`, a header element that cannot be unpacked) and the `ValueError` for a header element of the wrong length or a non-`str` header name given to `store`; on `Observation`, rejection of a list as `headers` or of a pair of another length or type; on `read_observation`, `response.headers` that is not a list, a header that is not a `[name, value]` pair of text, a non-text `captured_at`, a `captured_at` not in `isoformat()` form, and a `schema_version` of `true` or `1.0`; a failed cleanup of a temporary file | LOW | raw-evidence-store · audit.md § Spec and code consistency, § Round 2 A3; execution-plan.md § "Not asserted by any test" |
| U2 | Real concurrent writers to one store are untested and out of scope; only the deterministic simulation (the final name appears between the absence check and publication, through the `os.fsync` seam, four `race` tests) guards the taken-name branch | LOW | raw-evidence-store · intent.md § Scope Out; audit.md § Round 2 A1 |
| U3 | The effect of the POSIX directory sync is not checked (power-loss durability cannot be shown by a unit test) | LOW | raw-evidence-store · audit.md § Separate assessment |
| N1 | Any change to the record bytes needs a `schema_version` bump and a compatible comparison for idempotent re-store (Invariant 4) | LOW | raw-evidence-store · audit.md § Notes N1 |
| N2 | A failure of the POSIX directory `fsync` after the link raises `OSError` although the file is already published; a retry is idempotent, so F4 must not read an `OSError` from `store` as "nothing was written" | LOW | raw-evidence-store · audit.md § Notes N2 |
| N3 | Integrity errors use `from None`, but `__context__` still links to the `JSONDecodeError`, whose `doc` attribute holds the record text, header values included; it matters only if a caller serializes exception contexts (for example when F4 adds logging) | LOW | raw-evidence-store · audit.md § Notes N3 |

## Contributing features

| Feature | Shipped | What it established |
|---|---|---|
| raw-evidence-store (F1) | 2026-10-09 | The content hash, the observation and the evidence errors in `domain`, the `RawEvidenceStore` port in `application`, and the local-disk adapter in `infrastructure`, with the ADR 0005 layout, write-once atomic publication, the `Set-Cookie` rule and integrity checks on read (RE-1 to RE-12) |

## Related ADRs

None registered here. The binding decisions are the project-level ADRs in
`docs/adr/`, which carry no `Capability:` field: ADR 0002 (immutable raw
storage) and ADR 0005 (raw evidence store layout, Accepted on 2026-10-09).
