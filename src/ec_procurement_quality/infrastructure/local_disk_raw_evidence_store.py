"""Local-disk adapter for the raw evidence store (ADR 0005).

Layout under the store root:

- `objects/<xx>/<sha256>`: the exact response bytes, named by their SHA-256
  (`xx` is the first two characters of the hexdigest);
- `observations/<execution-id>/<sequence>.json`: one JSON record per response
  obtained;
- `tmp/`: temporary files used while publishing; never read as evidence.

Evidence is write-once: a file is first written completely under `tmp/`, synced,
and only then given its final name with `os.link`, which fails when that name
already exists. No code path here replaces, truncates, appends to or deletes a
file under `objects/` or `observations/`.

The adapter writes no log output, and its error messages never contain content
bytes or header values.
"""

import json
import os
import tempfile
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from ec_procurement_quality.domain.content_hash import ContentHash
from ec_procurement_quality.domain.raw_evidence import (
    EvidenceIntegrityError,
    EvidenceNotFoundError,
    Observation,
    validate_execution_id,
    validate_sequence,
)

_SCHEMA_VERSION = 1
_OBJECTS = "objects"
_OBSERVATIONS = "observations"
_TEMPORARY = "tmp"
_SET_COOKIE = "set-cookie"

_RECORD_KEYS = frozenset(
    {
        "schema_version",
        "execution_id",
        "sequence",
        "captured_at",
        "request",
        "response",
        "content",
    }
)
_REQUEST_KEYS = frozenset({"method", "url"})
_RESPONSE_KEYS = frozenset({"status", "headers"})
_CONTENT_KEYS = frozenset({"sha256", "size"})


class _InvalidRecord(Exception):
    """An observation file is not a valid record; the reason holds no values."""


class LocalDiskRawEvidenceStore:
    """Raw evidence store that keeps objects and observations under `root`.

    The root does not need to exist; directories are created on first write.
    """

    def __init__(self, root: Path) -> None:
        self._root = root

    # --- Port ---------------------------------------------------------------

    def store(
        self,
        *,
        execution_id: str,
        sequence: int,
        method: str,
        url: str,
        status: int,
        headers: Sequence[tuple[str, str]],
        captured_at: datetime,
        content: bytes,
    ) -> Observation:
        """Preserve a response as an object plus an observation, write-once."""
        # Step 1: validate everything before any file or directory exists.
        if not isinstance(content, bytes):
            raise TypeError("content must be bytes")
        kept_headers = tuple(
            (name, value)
            for name, value in headers
            if not (isinstance(name, str) and name.lower() == _SET_COOKIE)
        )
        content_hash = ContentHash.of(content)
        observation = Observation(
            execution_id=execution_id,
            sequence=sequence,
            method=method,
            url=url,
            status=status,
            headers=kept_headers,
            captured_at=captured_at,
            content_hash=content_hash,
            size=len(content),
        )
        record = _serialize(observation)

        # Step 2: the object, only if absent; an existing one must match.
        self._ensure_object(content_hash, content)
        # Step 3: the observation, only after its object.
        self._ensure_observation(observation, record)
        return observation

    def read_content(self, content_hash: ContentHash) -> bytes:
        """Return the stored bytes for `content_hash`, verified against its name."""
        path = self._object_path(content_hash)
        content = _read_if_present(path)
        if content is None:
            raise EvidenceNotFoundError(
                f"no object for sha256 {content_hash.hexdigest} at {path}"
            )
        if ContentHash.of(content) != content_hash:
            raise EvidenceIntegrityError(
                f"object {content_hash.hexdigest} at {path} does not match its name"
            )
        return content

    def read_observation(self, execution_id: str, sequence: int) -> Observation:
        """Return the observation recorded for `execution_id` and `sequence`."""
        validate_execution_id(execution_id)
        validate_sequence(sequence)
        path = self._observation_path(execution_id, sequence)
        raw = _read_if_present(path)
        if raw is None:
            raise EvidenceNotFoundError(
                f"no observation {execution_id}/{sequence} at {path}"
            )
        try:
            observation = _parse_record(raw)
        except _InvalidRecord as error:
            raise EvidenceIntegrityError(
                f"observation {execution_id}/{sequence} at {path} is not a valid "
                f"record: {error}"
            ) from None
        if observation.execution_id != execution_id or observation.sequence != sequence:
            raise EvidenceIntegrityError(
                f"observation {execution_id}/{sequence} at {path} names another "
                "execution or sequence"
            )
        return observation

    # --- Paths --------------------------------------------------------------

    def _object_path(self, content_hash: ContentHash) -> Path:
        hexdigest = content_hash.hexdigest
        return self._root / _OBJECTS / hexdigest[:2] / hexdigest

    def _observation_path(self, execution_id: str, sequence: int) -> Path:
        return self._root / _OBSERVATIONS / execution_id / f"{sequence}.json"

    # --- Write-once publication ---------------------------------------------

    def _ensure_object(self, content_hash: ContentHash, content: bytes) -> None:
        path = self._object_path(content_hash)
        existing = _read_if_present(path)
        if existing is None and self._publish_if_absent(path, content):
            return
        if existing is None:
            # Another writer published the name between the check and the link.
            existing = _read_if_present(path)
        if existing is None or ContentHash.of(existing) != content_hash:
            raise EvidenceIntegrityError(
                f"object {content_hash.hexdigest} at {path} exists with bytes that "
                "do not match its name"
            )

    def _ensure_observation(self, observation: Observation, record: bytes) -> None:
        path = self._observation_path(observation.execution_id, observation.sequence)
        existing = _read_if_present(path)
        if existing is None and self._publish_if_absent(path, record):
            return
        if existing is None:
            existing = _read_if_present(path)
        if existing != record:
            raise EvidenceIntegrityError(
                f"observation {observation.execution_id}/{observation.sequence} at "
                f"{path} already exists with different data"
            )

    def _publish_if_absent(self, final: Path, data: bytes) -> bool:
        """Write `data` completely, then give it `final` only if that name is free.

        Returns `True` when `final` was created and `False` when it already
        existed (left untouched). Any failure leaves nothing under `final`.
        """
        temporary_dir = self._root / _TEMPORARY
        temporary_dir.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=temporary_dir, prefix="publish-", suffix=".tmp", delete=False
            ) as handle:
                temporary = Path(handle.name)
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            final.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(temporary, final)
            except FileExistsError:
                return False
            _sync_directory(final.parent)
            return True
        finally:
            if temporary is not None:
                _remove_quietly(temporary)


def _read_if_present(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def _remove_quietly(path: Path) -> None:
    """Best-effort removal of a temporary file; never hides the original error."""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _sync_directory(directory: Path) -> None:
    """Make a new name durable after power loss (POSIX only; Windows skips)."""
    if os.name != "posix":
        return
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


# --- Observation record -----------------------------------------------------


def _serialize(observation: Observation) -> bytes:
    """Serialize an observation to its record bytes, the same on every platform."""
    record: dict[str, Any] = {
        "schema_version": _SCHEMA_VERSION,
        "execution_id": observation.execution_id,
        "sequence": observation.sequence,
        "captured_at": observation.captured_at.isoformat(),
        "request": {"method": observation.method, "url": observation.url},
        "response": {
            "status": observation.status,
            "headers": [[name, value] for name, value in observation.headers],
        },
        "content": {
            "sha256": observation.content_hash.hexdigest,
            "size": observation.size,
        },
    }
    # ASCII-only JSON (non-ASCII text is escaped) so that any header or URL text
    # received, even one that is not valid Unicode, is stored and read back.
    return (json.dumps(record, indent=2) + "\n").encode("ascii")


def _object_of(value: object, keys: frozenset[str], what: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise _InvalidRecord(f"{what} is not an object with exactly the pinned keys")
    return value


def _parse_headers(value: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, list):
        raise _InvalidRecord("headers is not a list")
    headers: list[tuple[str, str]] = []
    for pair in value:
        if (
            not isinstance(pair, list)
            or len(pair) != 2
            or not isinstance(pair[0], str)
            or not isinstance(pair[1], str)
        ):
            raise _InvalidRecord("a header is not a [name, value] pair of text")
        headers.append((pair[0], pair[1]))
    return tuple(headers)


def _parse_record(raw: bytes) -> Observation:
    """Rebuild an `Observation` from record bytes, rejecting anything unexpected."""
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (ValueError, RecursionError):
        raise _InvalidRecord("it is not UTF-8 JSON") from None
    record = _object_of(decoded, _RECORD_KEYS, "the record")
    version = record["schema_version"]
    if type(version) is not int or version != _SCHEMA_VERSION:
        raise _InvalidRecord("its schema_version is not supported")
    request = _object_of(record["request"], _REQUEST_KEYS, "request")
    response = _object_of(record["response"], _RESPONSE_KEYS, "response")
    content = _object_of(record["content"], _CONTENT_KEYS, "content")
    captured_text = record["captured_at"]
    if not isinstance(captured_text, str):
        raise _InvalidRecord("captured_at is not text")
    try:
        observation = Observation(
            execution_id=record["execution_id"],
            sequence=record["sequence"],
            method=request["method"],
            url=request["url"],
            status=response["status"],
            headers=_parse_headers(response["headers"]),
            captured_at=datetime.fromisoformat(captured_text),
            content_hash=ContentHash(content["sha256"]),
            size=content["size"],
        )
    except (ValueError, TypeError):
        raise _InvalidRecord("its fields fail observation validation") from None
    if observation.captured_at.isoformat() != captured_text:
        raise _InvalidRecord("captured_at is not in the recorded form")
    return observation
