"""Feature raw-evidence-store (F1), AC2 to AC11, outcomes O3 and O4.

The local-disk adapter stores each response as an object (the exact bytes under
their SHA-256) plus a JSON observation, following ADR 0005. These tests use a
pytest `tmp_path` as the store root, synthetic data, and `.invalid` URLs. They
never touch the network or the real `data/raw/`.
"""

import hashlib
import json
import os
import stat
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from ec_procurement_quality.application.raw_evidence_store import RawEvidenceStore
from ec_procurement_quality.domain.content_hash import ContentHash
from ec_procurement_quality.domain.raw_evidence import (
    EvidenceIntegrityError,
    EvidenceNotFoundError,
    Observation,
)
from ec_procurement_quality.infrastructure.local_disk_raw_evidence_store import (
    LocalDiskRawEvidenceStore,
)

ABC_HEXDIGEST = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
EMPTY_HEXDIGEST = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
EXECUTION_ID = "synthetic-exec-001"
URL = "https://source.invalid/api/search?year=2025&page=1"
CAPTURED_AT = datetime(2026, 10, 9, 10, 15, tzinfo=timezone(timedelta(hours=-5)))
HEADERS = (("Content-Type", "application/json"),)
LONG_AGO_NS = 946_684_800_000_000_000  # 2000-01-01T00:00:00Z, far from "now"


# --- Helpers ----------------------------------------------------------------


def _store_response(
    store: LocalDiskRawEvidenceStore,
    *,
    execution_id: str = EXECUTION_ID,
    sequence: int = 1,
    method: str = "GET",
    url: str = URL,
    status: int = 200,
    headers: tuple[tuple[str, str], ...] = HEADERS,
    captured_at: datetime = CAPTURED_AT,
    content: bytes = b"abc",
) -> Observation:
    return store.store(
        execution_id=execution_id,
        sequence=sequence,
        method=method,
        url=url,
        status=status,
        headers=headers,
        captured_at=captured_at,
        content=content,
    )


def _object_path(root: Path, hexdigest: str) -> Path:
    return root / "objects" / hexdigest[:2] / hexdigest


def _observation_path(root: Path, execution_id: str, sequence: int) -> Path:
    return root / "observations" / execution_id / f"{sequence}.json"


def _entries_under(path: Path) -> list[Path]:
    """Every file and folder below `path` (empty when `path` does not exist)."""
    if not path.exists():
        return []
    return sorted(path.rglob("*"))


def _files_under(path: Path) -> list[Path]:
    """Every file below `path` (empty when `path` does not exist)."""
    return [entry for entry in _entries_under(path) if entry.is_file()]


def _age(*paths: Path) -> None:
    """Set an old modification time, so a later rewrite would visibly change it."""
    for path in paths:
        os.utime(path, ns=(LONG_AGO_NS, LONG_AGO_NS))


def _plant(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """A store root that does not exist yet: directories appear on first write."""
    return tmp_path / "raw"


@pytest.fixture
def store(root: Path) -> LocalDiskRawEvidenceStore:
    return LocalDiskRawEvidenceStore(root)


# --- Round trip (AC2) -------------------------------------------------------


def test_store_round_trip_writes_object_and_observation_at_the_pinned_paths(
    root: Path, store: LocalDiskRawEvidenceStore
) -> None:
    _store_response(store)

    object_path = _object_path(root, ABC_HEXDIGEST)
    observation_path = _observation_path(root, EXECUTION_ID, 1)
    assert object_path.read_bytes() == b"abc"
    assert json.loads(observation_path.read_bytes()) == {
        "schema_version": 1,
        "execution_id": "synthetic-exec-001",
        "sequence": 1,
        "captured_at": "2026-10-09T10:15:00-05:00",
        "request": {"method": "GET", "url": URL},
        "response": {
            "status": 200,
            "headers": [["Content-Type", "application/json"]],
        },
        "content": {"sha256": ABC_HEXDIGEST, "size": 3},
    }
    assert _files_under(root) == sorted([object_path, observation_path])


def test_store_round_trip_reads_back_content_and_observation(
    store: LocalDiskRawEvidenceStore,
) -> None:
    stored = _store_response(store)

    content = store.read_content(ContentHash(ABC_HEXDIGEST))
    observation = store.read_observation(EXECUTION_ID, 1)

    assert content == b"abc"
    assert observation == stored
    assert observation.captured_at.utcoffset() == timedelta(hours=-5)
    assert stored.content_hash == ContentHash.of(b"abc")
    assert stored.size == 3
    assert stored.status == 200
    assert stored.headers == HEADERS


@pytest.mark.parametrize("sequence", [0, 1, 12, 100])
def test_store_round_trip_names_the_observation_file_by_its_decimal_sequence(
    root: Path, store: LocalDiskRawEvidenceStore, sequence: int
) -> None:
    stored = _store_response(store, sequence=sequence)

    assert _observation_path(root, EXECUTION_ID, sequence).is_file()
    assert store.read_observation(EXECUTION_ID, sequence) == stored


def test_store_round_trip_keeps_request_and_header_text_as_given(
    store: LocalDiskRawEvidenceStore,
) -> None:
    url = "https://source.invalid/api/search?q=a%20b&year=2025&year=2026&page=1#frag"
    headers = (
        ("content-TYPE", "application/json; charset=utf-8"),
        ("X-Note", 'café "quoted" \\ back'),
        ("X-Empty", ""),
    )

    stored = _store_response(store, method="get", url=url, headers=headers)
    observation = store.read_observation(EXECUTION_ID, 1)

    assert stored.method == "get"
    assert stored.url == url
    assert stored.headers == headers
    assert observation == stored
    assert observation.method == "get"
    assert observation.url == url
    assert observation.headers == headers


def test_store_round_trip_serializes_the_same_response_to_the_same_bytes(
    tmp_path: Path,
) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"

    _store_response(LocalDiskRawEvidenceStore(first_root))
    _store_response(LocalDiskRawEvidenceStore(second_root))

    assert (
        _observation_path(first_root, EXECUTION_ID, 1).read_bytes()
        == _observation_path(second_root, EXECUTION_ID, 1).read_bytes()
    )


def test_store_round_trip_writes_only_inside_the_root(
    tmp_path: Path,
) -> None:
    root = tmp_path / "inside" / "raw"

    _store_response(LocalDiskRawEvidenceStore(root))

    assert _files_under(tmp_path) == _files_under(root)


# --- Duplicate content (AC3) ------------------------------------------------


def test_store_duplicate_content_keeps_one_object_and_adds_an_observation(
    root: Path, store: LocalDiskRawEvidenceStore
) -> None:
    _store_response(store, execution_id="synthetic-exec-001", sequence=1)
    object_path = _object_path(root, ABC_HEXDIGEST)
    _age(object_path)
    bytes_before = object_path.read_bytes()
    mtime_before = object_path.stat().st_mtime_ns

    _store_response(store, execution_id="synthetic-exec-002", sequence=1)

    assert _files_under(root / "objects") == [object_path]
    assert len(_files_under(root / "observations")) == 2
    for execution_id in ("synthetic-exec-001", "synthetic-exec-002"):
        record = json.loads(_observation_path(root, execution_id, 1).read_bytes())
        assert record["content"]["sha256"] == ABC_HEXDIGEST
    assert object_path.read_bytes() == bytes_before
    assert object_path.stat().st_mtime_ns == mtime_before
    assert len(_files_under(root)) == 3


# --- Error and incomplete responses (AC4) -----------------------------------


@pytest.mark.parametrize(
    ("status", "content"),
    [
        pytest.param(
            429, b"<html><body>Too Many Requests</body></html>", id="429-html"
        ),
        pytest.param(503, b"", id="503-empty"),
        pytest.param(200, b'{"total": 1, "data": [{"oc', id="200-truncated-json"),
    ],
)
def test_store_error_response_is_preserved_as_received(
    root: Path, store: LocalDiskRawEvidenceStore, status: int, content: bytes
) -> None:
    stored = _store_response(store, status=status, content=content)

    hexdigest = hashlib.sha256(content).hexdigest()
    record = json.loads(_observation_path(root, EXECUTION_ID, 1).read_bytes())
    assert stored.status == status
    assert record["response"]["status"] == status
    assert record["content"] == {"sha256": hexdigest, "size": len(content)}
    assert _object_path(root, hexdigest).read_bytes() == content
    assert store.read_content(ContentHash(hexdigest)) == content
    assert store.read_observation(EXECUTION_ID, 1).status == status


def test_store_error_response_with_empty_body_uses_the_empty_hash(
    root: Path, store: LocalDiskRawEvidenceStore
) -> None:
    stored = _store_response(store, status=503, content=b"")

    assert stored.size == 0
    assert stored.content_hash.hexdigest == EMPTY_HEXDIGEST
    assert _object_path(root, EMPTY_HEXDIGEST).read_bytes() == b""
    assert store.read_content(ContentHash(EMPTY_HEXDIGEST)) == b""


# --- Set-Cookie (AC5) -------------------------------------------------------


def test_store_set_cookie_headers_are_never_persisted(
    root: Path, store: LocalDiskRawEvidenceStore
) -> None:
    headers = (
        ("Content-Type", "application/json"),
        ("Set-Cookie", "synthetic-session=s1"),
        ("X-RateLimit-Remaining", "7"),
        ("set-cookie", "synthetic-other=s2"),
        ("X-RateLimit-Remaining", "6"),
    )
    expected = (
        ("Content-Type", "application/json"),
        ("X-RateLimit-Remaining", "7"),
        ("X-RateLimit-Remaining", "6"),
    )

    stored = _store_response(store, headers=headers)

    observation_path = _observation_path(root, EXECUTION_ID, 1)
    persisted = observation_path.read_bytes()
    record = json.loads(persisted)
    assert stored.headers == expected
    assert record["response"]["headers"] == [list(pair) for pair in expected]
    assert store.read_observation(EXECUTION_ID, 1).headers == expected
    assert b"synthetic-session" not in persisted
    assert b"synthetic-other" not in persisted
    assert b"set-cookie" not in persisted.lower()


def test_store_set_cookie_only_headers_leave_no_headers(
    root: Path, store: LocalDiskRawEvidenceStore
) -> None:
    headers = (("SET-COOKIE", "synthetic-session=s1"), ("Set-cookie", "a=b"))

    stored = _store_response(store, headers=headers)

    record = json.loads(_observation_path(root, EXECUTION_ID, 1).read_bytes())
    assert stored.headers == ()
    assert record["response"]["headers"] == []


# --- Corrupt and missing evidence (AC6) -------------------------------------


@pytest.mark.parametrize(
    "replacement",
    [
        pytest.param(b"synthetic-tampered-body", id="other-bytes"),
        pytest.param(b"", id="truncated-to-empty"),
    ],
)
def test_read_content_corrupt_object_raises_integrity_error_naming_the_hash(
    root: Path, store: LocalDiskRawEvidenceStore, replacement: bytes
) -> None:
    original = b"synthetic-original-body"
    stored = _store_response(store, content=original)
    hexdigest = stored.content_hash.hexdigest
    _object_path(root, hexdigest).write_bytes(replacement)

    with pytest.raises(EvidenceIntegrityError) as error_info:
        store.read_content(stored.content_hash)

    message = str(error_info.value)
    assert hexdigest in message
    assert original.decode() not in message
    if replacement:
        assert replacement.decode() not in message


def test_read_content_missing_object_raises_not_found(
    store: LocalDiskRawEvidenceStore,
) -> None:
    _store_response(store, content=b"synthetic-stored-body")
    never_stored = ContentHash.of(b"synthetic-never-stored-body")

    with pytest.raises(EvidenceNotFoundError) as error_info:
        store.read_content(never_stored)

    assert never_stored.hexdigest in str(error_info.value)


def test_read_content_missing_object_in_a_store_that_was_never_written(
    store: LocalDiskRawEvidenceStore,
) -> None:
    with pytest.raises(EvidenceNotFoundError):
        store.read_content(ContentHash.of(b"abc"))


def test_read_observation_missing_identity_raises_not_found(
    store: LocalDiskRawEvidenceStore,
) -> None:
    with pytest.raises(EvidenceNotFoundError):
        store.read_observation("synthetic-exec-404", 1)


def test_read_observation_missing_sequence_of_a_stored_execution_raises_not_found(
    store: LocalDiskRawEvidenceStore,
) -> None:
    _store_response(store, sequence=1)

    with pytest.raises(EvidenceNotFoundError):
        store.read_observation(EXECUTION_ID, 2)


def _without(key: str) -> Callable[[dict[str, Any]], None]:
    def mutate(record: dict[str, Any]) -> None:
        del record[key]

    return mutate


def _with(key: str, value: Any) -> Callable[[dict[str, Any]], None]:
    def mutate(record: dict[str, Any]) -> None:
        record[key] = value

    return mutate


def _with_status(value: int) -> Callable[[dict[str, Any]], None]:
    def mutate(record: dict[str, Any]) -> None:
        record["response"]["status"] = value

    return mutate


def _with_naive_capture_time(record: dict[str, Any]) -> None:
    record["captured_at"] = "2026-10-09T10:15:00"


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(_with("sequence", 2), id="names-another-sequence"),
        pytest.param(
            _with("execution_id", "synthetic-exec-999"), id="names-another-execution"
        ),
        pytest.param(_without("content"), id="lacks-a-key"),
        pytest.param(_with("unexpected", True), id="adds-a-key"),
        pytest.param(_with("schema_version", 2), id="other-schema-version"),
        pytest.param(_with_status(99), id="fails-observation-validation"),
        pytest.param(_with_naive_capture_time, id="capture-time-without-offset"),
    ],
)
def test_read_observation_corrupt_record_raises_integrity_error(
    root: Path,
    store: LocalDiskRawEvidenceStore,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    _store_response(store)
    path = _observation_path(root, EXECUTION_ID, 1)
    record = json.loads(path.read_bytes())
    mutate(record)
    path.write_bytes(json.dumps(record).encode("utf-8"))

    with pytest.raises(EvidenceIntegrityError):
        store.read_observation(EXECUTION_ID, 1)


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param(b"{not json", id="malformed-json"),
        pytest.param(b"", id="empty-file"),
        pytest.param(b"[]", id="not-an-object"),
    ],
)
def test_read_observation_corrupt_file_raises_integrity_error(
    root: Path, store: LocalDiskRawEvidenceStore, raw: bytes
) -> None:
    _store_response(store)
    _observation_path(root, EXECUTION_ID, 1).write_bytes(raw)

    with pytest.raises(EvidenceIntegrityError):
        store.read_observation(EXECUTION_ID, 1)


# --- Conflicts on an existing identity (AC7) --------------------------------


def test_store_conflict_existing_object_with_other_bytes_is_integrity_error(
    root: Path, store: LocalDiskRawEvidenceStore
) -> None:
    object_path = _object_path(root, ABC_HEXDIGEST)
    _plant(object_path, b"tampered")

    with pytest.raises(EvidenceIntegrityError) as error_info:
        _store_response(store, content=b"abc")

    assert ABC_HEXDIGEST in str(error_info.value)
    assert "tampered" not in str(error_info.value)
    assert object_path.read_bytes() == b"tampered"
    assert _files_under(root / "observations") == []
    assert _files_under(root) == [object_path]


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"content": b"xyz"}, id="other-content"),
        pytest.param({"status": 500}, id="other-status"),
        pytest.param({"headers": (("Content-Type", "text/html"),)}, id="other-headers"),
        pytest.param(
            {"captured_at": datetime(2026, 10, 9, 11, 0, tzinfo=UTC)},
            id="other-capture-time",
        ),
    ],
)
def test_store_conflict_existing_observation_with_other_data_is_integrity_error(
    root: Path, store: LocalDiskRawEvidenceStore, changes: dict[str, Any]
) -> None:
    _store_response(store)
    observation_path = _observation_path(root, EXECUTION_ID, 1)
    object_path = _object_path(root, ABC_HEXDIGEST)
    _age(observation_path, object_path)
    observation_bytes = observation_path.read_bytes()
    observation_mtime = observation_path.stat().st_mtime_ns

    with pytest.raises(EvidenceIntegrityError):
        _store_response(store, **changes)

    assert observation_path.read_bytes() == observation_bytes
    assert observation_path.stat().st_mtime_ns == observation_mtime
    assert object_path.read_bytes() == b"abc"
    assert store.read_observation(EXECUTION_ID, 1).status == 200


def test_store_same_response_again_is_not_a_conflict_and_changes_nothing(
    root: Path, store: LocalDiskRawEvidenceStore
) -> None:
    first = _store_response(store)
    observation_path = _observation_path(root, EXECUTION_ID, 1)
    object_path = _object_path(root, ABC_HEXDIGEST)
    _age(observation_path, object_path)
    observation_bytes = observation_path.read_bytes()
    observation_mtime = observation_path.stat().st_mtime_ns
    object_mtime = object_path.stat().st_mtime_ns
    files_before = _files_under(root)

    second = _store_response(store)

    assert second == first
    assert observation_path.read_bytes() == observation_bytes
    assert observation_path.stat().st_mtime_ns == observation_mtime
    assert object_path.read_bytes() == b"abc"
    assert object_path.stat().st_mtime_ns == object_mtime
    assert _files_under(root) == files_before


# --- A name appears between the absence check and publication (AC7, race) ---


def _plant_when_publishing(
    monkeypatch: pytest.MonkeyPatch, path: Path, content: bytes
) -> list[Path]:
    """Make `path` appear (aged) while `store` publishes its first file.

    Another writer creating `path` after `store` saw it absent and before
    `store` gives it a name is simulated at the `os.fsync` of the first
    temporary file `store` publishes. The directory sync that follows a
    publication on POSIX is a directory descriptor and is never acted on.
    Returns the paths planted, so a test can assert that the wrapper acted.
    """
    real_fsync = os.fsync
    acted: list[Path] = []

    def planting_fsync(fd: int) -> None:
        if not acted and stat.S_ISREG(os.fstat(fd).st_mode):
            if path.exists():
                raise AssertionError("the name existed before the race")
            _plant(path, content)
            _age(path)
            acted.append(path)
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", planting_fsync)
    return acted


def _reference_observation(tmp_path: Path) -> tuple[Observation, bytes]:
    """The observation and record bytes `_store_response` produces by default."""
    reference_root = tmp_path / "reference"
    observation = _store_response(LocalDiskRawEvidenceStore(reference_root))
    record = _observation_path(reference_root, EXECUTION_ID, 1).read_bytes()
    return observation, record


def test_store_race_object_appearing_with_other_bytes_is_integrity_error(
    root: Path, store: LocalDiskRawEvidenceStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    object_path = _object_path(root, ABC_HEXDIGEST)
    acted = _plant_when_publishing(monkeypatch, object_path, b"tampered")

    with pytest.raises(EvidenceIntegrityError) as error_info:
        _store_response(store, content=b"abc")

    assert acted == [object_path]
    assert ABC_HEXDIGEST in str(error_info.value)
    assert "tampered" not in str(error_info.value)
    assert object_path.read_bytes() == b"tampered"
    assert object_path.stat().st_mtime_ns == LONG_AGO_NS
    assert _files_under(root / "observations") == []


def test_store_race_observation_appearing_with_other_bytes_is_integrity_error(
    root: Path, store: LocalDiskRawEvidenceStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    _plant(_object_path(root, ABC_HEXDIGEST), b"abc")
    observation_path = _observation_path(root, EXECUTION_ID, 1)
    planted = b"synthetic-other-record"
    acted = _plant_when_publishing(monkeypatch, observation_path, planted)

    with pytest.raises(EvidenceIntegrityError):
        _store_response(store)

    assert acted == [observation_path]
    assert observation_path.read_bytes() == planted
    assert observation_path.stat().st_mtime_ns == LONG_AGO_NS
    assert _object_path(root, ABC_HEXDIGEST).read_bytes() == b"abc"


def test_store_race_object_appearing_with_the_same_bytes_is_not_a_conflict(
    tmp_path: Path,
    root: Path,
    store: LocalDiskRawEvidenceStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected, _ = _reference_observation(tmp_path)
    object_path = _object_path(root, ABC_HEXDIGEST)
    acted = _plant_when_publishing(monkeypatch, object_path, b"abc")

    stored = _store_response(store)

    assert acted == [object_path]
    assert stored == expected
    assert object_path.read_bytes() == b"abc"
    assert object_path.stat().st_mtime_ns == LONG_AGO_NS
    assert store.read_observation(EXECUTION_ID, 1) == expected


def test_store_race_observation_appearing_with_the_same_bytes_is_not_a_conflict(
    tmp_path: Path,
    root: Path,
    store: LocalDiskRawEvidenceStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected, record = _reference_observation(tmp_path)
    _plant(_object_path(root, ABC_HEXDIGEST), b"abc")
    observation_path = _observation_path(root, EXECUTION_ID, 1)
    acted = _plant_when_publishing(monkeypatch, observation_path, record)

    stored = _store_response(store)

    assert acted == [observation_path]
    assert stored == expected
    assert observation_path.read_bytes() == record
    assert observation_path.stat().st_mtime_ns == LONG_AGO_NS
    assert store.read_observation(EXECUTION_ID, 1) == expected


# --- Failure between object and observation (AC8) ---------------------------


def test_store_orphan_object_remains_when_the_observation_cannot_be_written(
    root: Path, store: LocalDiskRawEvidenceStore
) -> None:
    root.mkdir()
    blocker = root / "observations"
    blocker.write_bytes(b"not a directory")

    with pytest.raises(OSError):
        _store_response(store)

    assert _object_path(root, ABC_HEXDIGEST).read_bytes() == b"abc"
    assert list(root.rglob("*.json")) == []
    assert blocker.read_bytes() == b"not a directory"


def test_store_orphan_observation_is_never_written_when_the_object_cannot_be_written(
    root: Path, store: LocalDiskRawEvidenceStore
) -> None:
    root.mkdir()
    blocker = root / "objects"
    blocker.write_bytes(b"not a directory")

    with pytest.raises(OSError):
        _store_response(store)

    assert _entries_under(root / "observations") == []
    assert blocker.read_bytes() == b"not a directory"


# --- Interrupted writes (AC9) -----------------------------------------------


def test_store_interrupted_write_leaves_no_file_and_a_retry_stores_the_content(
    root: Path,
    store: LocalDiskRawEvidenceStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_fsync(fd: int) -> None:
        raise OSError("synthetic fsync failure")

    monkeypatch.setattr(os, "fsync", failing_fsync)

    with pytest.raises(OSError):
        _store_response(store)

    assert not _object_path(root, ABC_HEXDIGEST).exists()
    assert _files_under(root / "observations") == []
    assert _files_under(root) == []

    monkeypatch.undo()
    stored = _store_response(store)

    assert _object_path(root, ABC_HEXDIGEST).read_bytes() == b"abc"
    assert store.read_content(stored.content_hash) == b"abc"
    assert store.read_observation(EXECUTION_ID, 1) == stored


# --- Invalid input (AC10) ---------------------------------------------------


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"execution_id": "../escape"}, id="path-traversal-id"),
        pytest.param({"execution_id": "Synthetic-Exec"}, id="uppercase-id"),
        pytest.param({"execution_id": ""}, id="empty-id"),
        pytest.param({"execution_id": "a" * 65}, id="65-character-id"),
        pytest.param({"sequence": -1}, id="negative-sequence"),
        pytest.param({"sequence": True}, id="bool-sequence"),
        pytest.param({"status": 99}, id="status-below-range"),
        pytest.param({"status": 600}, id="status-above-range"),
        pytest.param({"method": ""}, id="empty-method"),
        pytest.param({"url": ""}, id="empty-url"),
        pytest.param({"captured_at": datetime(2026, 10, 9, 10, 15)}, id="naive-time"),  # noqa: DTZ001,
    ],
)
def test_store_invalid_input_is_rejected_before_anything_is_written(
    tmp_path: Path, changes: dict[str, Any]
) -> None:
    root = tmp_path / "raw"
    store = LocalDiskRawEvidenceStore(root)

    with pytest.raises(ValueError):
        _store_response(store, **changes)

    assert _files_under(tmp_path) == []


@pytest.mark.parametrize(
    ("execution_id", "sequence"),
    [
        pytest.param("../escape", 1, id="path-traversal-id"),
        pytest.param("Synthetic-Exec", 1, id="uppercase-id"),
        pytest.param(EXECUTION_ID, -1, id="negative-sequence"),
    ],
)
def test_read_observation_invalid_identity_raises_value_error(
    store: LocalDiskRawEvidenceStore, execution_id: str, sequence: int
) -> None:
    with pytest.raises(ValueError):
        store.read_observation(execution_id, sequence)


# --- Port (AC11) ------------------------------------------------------------


def test_local_disk_store_satisfies_port_and_works_through_it(tmp_path: Path) -> None:
    port: RawEvidenceStore = LocalDiskRawEvidenceStore(tmp_path / "raw")

    stored = port.store(
        execution_id=EXECUTION_ID,
        sequence=1,
        method="GET",
        url=URL,
        status=200,
        headers=list(HEADERS),
        captured_at=CAPTURED_AT,
        content=b"abc",
    )

    assert port.read_content(stored.content_hash) == b"abc"
    assert port.read_observation(EXECUTION_ID, 1) == stored
