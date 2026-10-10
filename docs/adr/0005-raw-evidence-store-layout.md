# ADR 0005: Raw evidence store layout

- Status: Accepted
- Date: 2026-10-09

## Context

[ADR 0002](0002-immutable-raw-storage.md) requires raw evidence to be
append-only, identifiable, integrity-checkable, and linked to its source and
ingestion execution, but it deliberately left paths, compression, retention,
and the metadata schema open. The first vertical flow (F1) must now fix them.

Two questions remained open from the domain glossary. First, whether error
responses (for example the `429` seen in the source observations) are raw
evidence. The `429` body and headers were not preserved on 2026-10-03, so it is
still unknown whether SERCOP sends `Retry-After`. Second, how two executions
that obtained identical content are represented without duplicating the bytes,
while still recording that each execution obtained it (glossary: ingestion
execution).

## Decision

Store content by hash and record each retrieval separately, both on the local
disk under `data/raw/` (ignored by git).

- **Object.** The exact bytes of a response, named by their lowercase
  hexadecimal SHA-256 and sharded by its first two characters
  (`objects/<xx>/<sha256>`). An object is written once and never replaced.
  It is written to a temporary file in the same store and published
  atomically only if it does not already exist.
- **Observation.** One JSON record per response obtained, stored under
  `observations/<execution-id>/` and identified by its execution and a
  sequence number within it. It holds the source request (method and URL with
  query parameters), the response status and headers, the capture time, the
  execution identity, and the hash and size of the object. An observation is
  written once, after its object, so it never points to a missing object.
- **Duplicates.** Identical content obtained by two executions produces two
  observations and one object.
- **Error responses are evidence.** Every response received is preserved as
  received, whatever its status (`429`, `5xx`, truncated bodies). The status is
  recorded as is. The store does not judge usability: only successful
  responses are inputs to normalization.
- **Headers.** Response headers are recorded, except `Set-Cookie`. Request
  headers are not recorded; only the method, URL, and query parameters are.
- **Integrity.** Reading an object verifies its bytes against its name. A
  mismatch, or a different content presented under an identity that already
  exists, is an explicit integrity error and never a silent overwrite.
- **Compression and retention.** None in v1. Objects hold the original bytes,
  and no automatic deletion exists.

This needs no new dependency: hashing uses the standard library.

## Alternatives considered

A folder per execution holding its own copy of the bytes and metadata was
rejected because it duplicates identical content and cannot show that two
executions obtained the same thing. What is lost is simplicity: that layout
can be read without following a hash. Embedding the metadata in the object
file was rejected because it would break byte-faithfulness and make the hash
no longer the hash of the source response. Preserving only successful
responses was rejected because it discards the evidence needed to learn the
source's rate limiting and error behavior; what is lost is lower volume.
Storing the bytes in PostgreSQL was rejected for F1 because the database
arrives in F3, and it would make the evidence depend on a service; what is
lost is a single place for bytes and metadata.

## Consequences

Evidence is verifiable and readable without a database, and repeated
executions cost one small record instead of a copy. The cost is that finding
who obtained a piece of content requires scanning observations until
PostgreSQL indexes them (F3), and that a crash between writing an object and
its observation can leave an object with no observation. That orphan is
harmless and is never deleted automatically.

Preserving errors and headers increases volume, and any downloaded content may
be sensitive, so `data/raw/` must stay out of version control and out of logs.
The filesystem does not prevent tampering; integrity verification detects it.
The store does not decide whether a `200` body is complete: that belongs to the
source adapter (F2) and normalization (F5).

This decision should be revisited if evidence volume makes uncompressed
storage impractical, if a retention requirement appears, or if F3 moves the
evidence into PostgreSQL.
