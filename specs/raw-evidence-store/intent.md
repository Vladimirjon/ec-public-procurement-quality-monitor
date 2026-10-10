# Intent: Raw evidence store (F1)

Revision: 1
Approval: Approved revision 1 by Vladimirjon on 2026-10-09

## Outcome
The system can preserve every source response it obtains as raw evidence on
the local disk, following [ADR 0005](../../docs/adr/0005-raw-evidence-store-layout.md):
the exact bytes are stored once under their SHA-256 (an *object*), and each
time a response is obtained a separate JSON *observation* records who obtained
it, from which request, with which status and headers, and when. Evidence is
never overwritten: storing the same bytes again adds only an observation,
different content under an identity that already exists is an explicit
integrity error, and reading an object verifies its bytes against its name.
F1 delivers the domain concepts, the storage port and the local-disk adapter;
nothing calls them yet (no CLI command, no HTTP, no PostgreSQL).

## Acceptance criteria
All examples use synthetic data. `sha256(b"abc")` is
`ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad` and
`sha256(b"")` is `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
`<root>` is the directory the local-disk store is given (in tests, a pytest
`tmp_path`; in operation, `data/raw/`).

- **AC1** A content hash value object identifies bytes by their SHA-256, as 64 lowercase hexadecimal characters. It is immutable and compares and hashes by value. Anything that is not exactly 64 lowercase hex characters is rejected.
  Example: hashing `b"abc"` -> hexdigest `ba7816bf...20015ad`; two hashes of `b"abc"` are equal and usable as the same dict key; building one from `"BA7816BF..."` (uppercase), from 63 characters, or from `"zz..."` -> `ValueError`; assigning to its hexdigest -> an exception.
- **AC2** Storing a response writes its object and its observation in the ADR 0005 layout, and both can be read back exactly.
  Example: store execution `synthetic-exec-001`, sequence `1`, `GET https://source.invalid/api/search?year=2025&page=1`, status `200`, headers `[("Content-Type", "application/json")]`, captured at `2026-10-09T10:15:00-05:00`, content `b"abc"` -> the file `<root>/objects/ba/ba7816bf...20015ad` holds exactly `b"abc"`; the file `<root>/observations/synthetic-exec-001/1.json` is a JSON record with the fields fixed in `execution-plan.md` § Binding constraints (execution id, sequence, capture time with its UTC offset, method, URL with its query string as given, status, headers, `sha256`, `size` `3`); reading the content by hash returns `b"abc"`; reading the observation by execution and sequence returns a record equal to the one `store` returned; no other file remains under `<root>`.
- **AC3** Identical content obtained twice produces one object and two observations, and the existing object is not rewritten.
  Example: the same bytes stored by `synthetic-exec-001` sequence `1` and by `synthetic-exec-002` sequence `1` -> exactly one file under `<root>/objects/`, exactly two files under `<root>/observations/`, both naming the same `sha256`; the object file's bytes and modification time are the same before and after the second store.
- **AC4** Error and incomplete responses are preserved as received, with their status as is. The store never judges whether a response is usable.
  Example: status `429` with an HTML body, status `503` with an empty body (`size` `0`, object `e3b0c442...b855`), and status `200` with a truncated JSON body `b'{"total": 1, "data": [{"oc'` -> each is stored without error, each observation records its status unchanged, and reading each object returns the exact bytes given.
- **AC5** `Set-Cookie` response headers are never persisted; every other response header is kept with its name as received, in order, including repeated names. Request headers are not accepted or recorded.
  Example: headers `[("Content-Type", "application/json"), ("Set-Cookie", "synthetic-session=s1"), ("X-RateLimit-Remaining", "7"), ("set-cookie", "synthetic-other=s2"), ("X-RateLimit-Remaining", "6")]` -> the returned observation and the observation file hold only the `Content-Type` header and both `X-RateLimit-Remaining` headers, in that order; the bytes of the observation file contain neither `synthetic-session` nor `synthetic-other`. Building an observation directly with a `SET-COOKIE` header -> `ValueError`.
- **AC6** (failure) Reading an object verifies it: an object whose bytes no longer match its name is an explicit integrity error, and a missing object is an explicit not-found error. Neither error message contains the stored bytes.
  Example: store `b"abc"`, overwrite `<root>/objects/ba/ba7816bf...20015ad` from outside with `b"abd"`, read by hash -> `EvidenceIntegrityError` naming the hash; reading a hash never stored -> `EvidenceNotFoundError`.
- **AC7** (failure) Different content under an identity that already exists is an explicit integrity error and never overwrites the existing evidence. Presenting the same observation again is not an error and changes nothing.
  Example (object): `<root>/objects/ba/ba7816bf...20015ad` already holds `b"tampered"`; storing content `b"abc"` -> `EvidenceIntegrityError`; that file still holds `b"tampered"` and no observation file is written.
  Example (observation): `synthetic-exec-001` sequence `1` is stored with content `b"abc"`; storing the same execution and sequence again with content `b"xyz"` (or the same content with status `500`) -> `EvidenceIntegrityError`, and `1.json` keeps its exact bytes; storing the identical response again -> returns an equal observation, and the bytes and modification times of `1.json` and of the object are unchanged.
- **AC8** (failure) A failure between writing the object and writing its observation never leaves an observation without its object. The orphan object that may remain is valid evidence and is not deleted.
  Example: a regular file placed at `<root>/observations` so the observation cannot be written -> `store` raises an `OSError`, `<root>/objects/ba/ba7816bf...20015ad` exists and holds `b"abc"`, and no observation file exists. A regular file placed at `<root>/objects` so the object cannot be written -> `store` raises an `OSError` and nothing exists under `<root>/observations`.
- **AC9** (failure) An interrupted object write never leaves a partial or empty file under a final object name, and a later attempt stores the complete content.
  Example: `os.fsync` made to raise `OSError` while storing `b"abc"` -> `store` raises `OSError`, `<root>/objects/ba/ba7816bf...20015ad` does not exist, no observation exists, and no temporary file is left under `<root>`; with `os.fsync` restored, the same store succeeds and the object holds exactly `b"abc"`.
- **AC10** (failure) Invalid input is rejected before anything is written.
  Example: execution id `../escape`, `Synthetic-Exec` (uppercase), `""` or a 65-character id; sequence `-1`; status `99` or `600`; a capture time without a UTC offset -> `ValueError`, and `<root>` contains no file.
- **AC11** The layers keep their boundaries: the hash value object, the observation, and the evidence errors live in `domain` and use only the standard library; the storage port lives in `application` and imports only the standard library and `domain`; the local-disk adapter lives in `infrastructure` and satisfies the port without the port knowing it. `domain` passes strict `mypy`.
  Example: `uv run pytest tests/unit -q -k layer` -> passes, including a check of the `application` imports; `uv run mypy .` -> exit 0 with a test that assigns the adapter to a variable typed as the port.
- **AC12** (compatibility) Everything that worked keeps working, with no new dependency and no tracked evidence.
  Example: the 7 F0 tests still pass inside `uv run pytest`; `uv run ruff check .`, `uv run ruff format --check .` and `uv run mypy .` exit 0; `uv run node .sdd/doctor/run-doctor.mjs` reports `0 warned, 0 failed`; `uv run ec-procurement-quality --version` still prints `ec-procurement-quality 0.1.0`; `git diff main -- pyproject.toml uv.lock` is empty; `git check-ignore data/raw/objects/ab/x data/raw/observations/e/1.json` reports both as ignored; `git diff --check` is clean; no test touches the network.
- **AC13** (documentation) The documentation says what exists.
  Example: `README.md` no longer says the layer packages are empty or that storage adapters are only planned, and names the local raw evidence store (no CLI command yet); `docs/architecture.md` § Raw evidence boundary points to ADR 0005 for the layout; `CHANGELOG.md` § Unreleased lists the store.

## Scope
**In**
- `domain`: the content hash value object; the observation (the metadata record of one obtained response); the evidence error types (integrity error and not-found error, with a common base).
- `application`: the raw evidence storage port (an interface), with operations to store a response, read an object's content by hash, and read an observation by execution and sequence.
- `infrastructure`: the local-disk adapter implementing the port under a root directory it is given, with the ADR 0005 layout, write-once atomic publication, integrity checks, and the `Set-Cookie` rule.
- Unit tests under `tests/unit/` for AC1 to AC11, using `tmp_path` and synthetic data only, and an `application` import-boundary check added next to the existing `domain` one.
- Documentation updates for AC13.

**Out**
- Any CLI command, any default root path wired in code (F4 decides how `data/raw/` is passed), and any use case that calls the store.
- HTTP, SERCOP access, retries, deciding whether a `200` body is complete, and capturing responses (F2).
- PostgreSQL, indexes over observations, and listing or searching observations (F3).
- Generating execution ids, assigning sequence numbers, and resuming executions (F4).
- Normalization and quarantine (F5).
- Compression, retention, automatic deletion of orphan objects or leftover temporary files, read-only file permissions, and a bulk verification command over the whole store (ADR 0005 consequences).
- Recording request headers.
- Concurrent writers to the same store, beyond what write-once publication already guarantees; it is not tested.
- New dependencies of any kind.

## Constraints
- ADR 0002 and ADR 0005 are binding: layout `objects/<xx>/<sha256>` and `observations/<execution-id>/<sequence>.json` under the store root; objects written once and published atomically only if absent; one observation per response obtained, written once and only after its object; error responses preserved with their status; response headers except `Set-Cookie`; no request headers; integrity verified on read; mismatch or different content under an existing identity is an explicit error; no compression or retention. ADR 0005 is `Proposed`; approving this spec does not change its status, which is the human's edit.
- Hashing uses `hashlib` from the standard library. No dependency is added (`[project] dependencies` stays empty and `uv.lock` does not change), per `AGENTS.md`.
- Layer boundaries from `AGENTS.md` and `docs/architecture.md`; `domain` is checked by strict `mypy` (ADR 0004).
- Human-written parts (`docs/learning/plan.md`, Day 10): the human writes the content hash value object and the port by hand; the executor writes the local-disk adapter. The names and signatures the adapter and the tests depend on are fixed in `execution-plan.md` § Binding constraints so the parts can be written separately.
- Tests, fixtures and docs hold no secrets, cookies, real SERCOP records or real raw responses. URLs use the reserved `.invalid` domain; bodies are invented, like the glossary examples.
- Raw evidence may be sensitive: the store never logs content or header values, and its error messages name hashes, identities and paths only.
- Current-truth note (harny-sync lookup): `project-toolchain` PT-3 says `domain`, `application` and `infrastructure` "hold only what makes them packages", and PT-6 counts 7 tests "at F0". F1 deliberately adds modules to those three layers and more tests, so PT-3's emptiness clause is retired for these layers (the rest of PT-3, including `domain` importing only the standard library and itself, stays) and PT-6's count grows. Invariant 3 of `project-toolchain` (at most 2 files directly in `src/ec_procurement_quality/`) is kept: every new module goes inside a layer package. The `cli` capability is untouched.

## Open questions
- None

## Revision history
- Revision 1 (2026-10-09): First draft, based on ADR 0005 (Proposed, decisions made by the human on Day 9) and the Day 10 split between hand-written and executor-written parts.
