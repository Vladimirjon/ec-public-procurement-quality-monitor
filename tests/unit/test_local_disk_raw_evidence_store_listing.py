"""Feature ingest-command (F4), AC22, outcome O1: the F1 listing.

`LocalDiskRawEvidenceStore.list_observation_sequences` lists the sequence numbers
of the observations of one execution, read-only, without stopping at a gap. These
tests use a pytest `tmp_path` as the store root, synthetic data, and `.invalid`
URLs. They never touch the network or the real `data/raw/`.
"""

import os
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NoReturn

import pytest

from ec_procurement_quality.domain.raw_evidence import (
    EvidenceIntegrityError,
    Observation,
)
from ec_procurement_quality.infrastructure.local_disk_raw_evidence_store import (
    LocalDiskRawEvidenceStore,
)

EXECUTION_ID = "synthetic-exec-001"
OTHER_EXECUTION_ID = "synthetic-exec-002"
URL = "https://source.invalid/api/search?year=2025&page=1"
CAPTURED_AT = datetime(2026, 10, 9, 10, 15, tzinfo=timezone(timedelta(hours=-5)))
HEADERS = (("Content-Type", "application/json"),)
LONG_AGO_NS = 946_684_800_000_000_000  # 2000-01-01T00:00:00Z, far from "now"
PLANTED_TEXT = b"synthetic-planted-body"


# --- Helpers ----------------------------------------------------------------


def _store_response(
    store: LocalDiskRawEvidenceStore,
    *,
    execution_id: str = EXECUTION_ID,
    sequence: int = 1,
    content: bytes | None = None,
) -> Observation:
    body = content if content is not None else f"synthetic-body-{sequence}".encode()
    return store.store(
        execution_id=execution_id,
        sequence=sequence,
        method="GET",
        url=URL,
        status=200,
        headers=HEADERS,
        captured_at=CAPTURED_AT,
        content=body,
    )


def _store_sequences(
    store: LocalDiskRawEvidenceStore,
    *sequences: int,
    execution_id: str = EXECUTION_ID,
) -> dict[int, Observation]:
    return {
        sequence: _store_response(store, execution_id=execution_id, sequence=sequence)
        for sequence in sequences
    }


def _execution_dir(root: Path, execution_id: str = EXECUTION_ID) -> Path:
    return root / "observations" / execution_id


def _observation_path(root: Path, execution_id: str, sequence: int) -> Path:
    return _execution_dir(root, execution_id) / f"{sequence}.json"


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


def _snapshot(root: Path) -> dict[Path, tuple[bytes | None, int]]:
    """Every entry below `root` with its bytes (None for a folder) and mtime."""
    return {
        entry: (
            entry.read_bytes() if entry.is_file() else None,
            entry.stat().st_mtime_ns,
        )
        for entry in _entries_under(root)
    }


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """A store root that does not exist yet: directories appear on first write."""
    return tmp_path / "raw"


@pytest.fixture
def store(root: Path) -> LocalDiskRawEvidenceStore:
    return LocalDiskRawEvidenceStore(root)


# --- What the listing finds (AC22) ------------------------------------------


def test_listing_returns_the_sequences_of_one_execution_ignoring_the_others(
    store: LocalDiskRawEvidenceStore,
) -> None:
    _store_sequences(store, 1, 2, 5)
    _store_sequences(store, 1, execution_id=OTHER_EXECUTION_ID)

    assert store.list_observation_sequences(EXECUTION_ID) == (1, 2, 5)
    assert store.list_observation_sequences(OTHER_EXECUTION_ID) == (1,)


def test_listing_does_not_stop_at_a_gap(store: LocalDiskRawEvidenceStore) -> None:
    _store_sequences(store, 1, 2, 5)

    sequences = store.list_observation_sequences(EXECUTION_ID)

    assert 3 not in sequences
    assert 4 not in sequences
    assert sequences[-1] == 5
    assert sequences == (1, 2, 5)


def test_listing_includes_sequence_zero(store: LocalDiskRawEvidenceStore) -> None:
    _store_sequences(store, 0, 1)

    assert store.list_observation_sequences(EXECUTION_ID) == (0, 1)


def test_listing_returns_a_tuple_of_ints_sorted_numerically(
    store: LocalDiskRawEvidenceStore,
) -> None:
    _store_sequences(store, 10, 2, 100, 1)

    sequences = store.list_observation_sequences(EXECUTION_ID)

    assert isinstance(sequences, tuple)
    assert all(type(sequence) is int for sequence in sequences)
    assert sequences == (1, 2, 10, 100)


def test_listing_of_an_unknown_execution_is_empty_and_creates_nothing(
    tmp_path: Path, root: Path, store: LocalDiskRawEvidenceStore
) -> None:
    assert store.list_observation_sequences("synthetic-exec-404") == ()

    assert _entries_under(tmp_path) == []
    assert not root.exists()


def test_listing_of_an_unknown_execution_in_a_written_store_is_empty_and_changes_nothing(
    root: Path, store: LocalDiskRawEvidenceStore
) -> None:
    _store_sequences(store, 1)
    _age(*_files_under(root))
    before = _snapshot(root)

    assert store.list_observation_sequences("synthetic-exec-404") == ()

    assert _snapshot(root) == before
    assert not _execution_dir(root, "synthetic-exec-404").exists()


def test_listing_never_lists_tmp_or_orphan_objects(
    root: Path, store: LocalDiskRawEvidenceStore
) -> None:
    _store_sequences(store, 1)
    # Names that would read as sequences if these folders were scanned.
    _plant(root / "tmp" / "7.json", PLANTED_TEXT)
    _plant(root / "tmp" / "publish-orphan.tmp", PLANTED_TEXT)
    _plant(root / "objects" / "ab" / "8.json", PLANTED_TEXT)
    _plant(root / "objects" / "cd" / ("cd" + "0" * 62), PLANTED_TEXT)

    assert store.list_observation_sequences(EXECUTION_ID) == (1,)
    assert store.list_observation_sequences(OTHER_EXECUTION_ID) == ()


def test_listing_of_an_execution_with_only_an_orphan_object_is_empty(
    root: Path, store: LocalDiskRawEvidenceStore
) -> None:
    _plant(root / "objects" / "ab" / ("ab" + "0" * 62), PLANTED_TEXT)

    assert store.list_observation_sequences(EXECUTION_ID) == ()


# --- Read-only (AC22) -------------------------------------------------------


def test_listing_changes_nothing_on_disk(
    root: Path, store: LocalDiskRawEvidenceStore
) -> None:
    _store_sequences(store, 1, 2, 5)
    _store_sequences(store, 1, execution_id=OTHER_EXECUTION_ID)
    _plant(root / "tmp" / "publish-orphan.tmp", PLANTED_TEXT)
    _age(*_files_under(root))
    before = _snapshot(root)

    first = store.list_observation_sequences(EXECUTION_ID)
    second = store.list_observation_sequences(EXECUTION_ID)
    store.list_observation_sequences(OTHER_EXECUTION_ID)
    store.list_observation_sequences("synthetic-exec-404")

    assert first == second == (1, 2, 5)
    assert _snapshot(root) == before


# --- Corrupt records are still listed (AC22) --------------------------------


def test_listing_still_lists_a_corrupted_record_and_reading_decides(
    root: Path, store: LocalDiskRawEvidenceStore
) -> None:
    stored = _store_sequences(store, 1, 2, 5)
    _observation_path(root, EXECUTION_ID, 2).write_bytes(b"{not json")

    assert store.list_observation_sequences(EXECUTION_ID) == (1, 2, 5)
    with pytest.raises(EvidenceIntegrityError):
        store.read_observation(EXECUTION_ID, 2)
    assert store.read_observation(EXECUTION_ID, 1) == stored[1]
    assert store.read_observation(EXECUTION_ID, 5) == stored[5]


def test_listing_does_not_read_file_contents(
    root: Path, store: LocalDiskRawEvidenceStore
) -> None:
    _store_sequences(store, 1)
    _observation_path(root, EXECUTION_ID, 2).write_bytes(b"")
    _observation_path(root, EXECUTION_ID, 3).write_bytes(b"[]")

    assert store.list_observation_sequences(EXECUTION_ID) == (1, 2, 3)


# --- Invalid input (AC22) ---------------------------------------------------


@pytest.mark.parametrize(
    "execution_id",
    [
        pytest.param("../escape", id="path-traversal-id"),
        pytest.param("Synthetic-Exec", id="uppercase-id"),
        pytest.param("", id="empty-id"),
        pytest.param("a" * 65, id="65-character-id"),
    ],
)
def test_listing_invalid_execution_id_raises_value_error_before_any_access(
    tmp_path: Path, execution_id: str
) -> None:
    store = LocalDiskRawEvidenceStore(tmp_path / "raw")

    with pytest.raises(ValueError):
        store.list_observation_sequences(execution_id)

    assert _entries_under(tmp_path) == []


def test_listing_invalid_execution_id_does_not_reach_a_sibling_folder(
    root: Path, store: LocalDiskRawEvidenceStore
) -> None:
    _plant(root / "escape" / "1.json", PLANTED_TEXT)
    before = _snapshot(root)

    with pytest.raises(ValueError):
        store.list_observation_sequences("../escape")

    assert _snapshot(root) == before


# --- Entries that are not observations (AC22) -------------------------------


def _plant_file(execution_dir: Path, name: str) -> None:
    _plant(execution_dir / name, PLANTED_TEXT)


def _plant_directory(execution_dir: Path, name: str) -> None:
    (execution_dir / name).mkdir(parents=True)


@pytest.mark.parametrize(
    ("name", "plant"),
    [
        pytest.param("x.json", _plant_file, id="non-numeric-name"),
        pytest.param("01.json", _plant_file, id="leading-zero"),
        pytest.param("00.json", _plant_file, id="double-zero"),
        pytest.param("-1.json", _plant_file, id="signed-name"),
        pytest.param("1.txt", _plant_file, id="other-extension"),
        pytest.param("sub", _plant_directory, id="subdirectory"),
        pytest.param("7.json", _plant_directory, id="directory-named-like-a-sequence"),
    ],
)
def test_listing_an_unexpected_entry_raises_integrity_error_naming_the_execution(
    root: Path,
    store: LocalDiskRawEvidenceStore,
    name: str,
    plant: Callable[[Path, str], None],
) -> None:
    _store_sequences(store, 1, 2)
    plant(_execution_dir(root), name)
    _age(*_files_under(root))
    before = _snapshot(root)

    with pytest.raises(EvidenceIntegrityError) as error_info:
        store.list_observation_sequences(EXECUTION_ID)

    message = str(error_info.value)
    assert EXECUTION_ID in message
    assert PLANTED_TEXT.decode() not in message
    assert _snapshot(root) == before


def test_listing_a_file_at_the_execution_path_raises_integrity_error(
    root: Path, store: LocalDiskRawEvidenceStore
) -> None:
    _plant(_execution_dir(root), PLANTED_TEXT)
    _age(_execution_dir(root))
    before = _snapshot(root)

    with pytest.raises(EvidenceIntegrityError) as error_info:
        store.list_observation_sequences(EXECUTION_ID)

    message = str(error_info.value)
    assert EXECUTION_ID in message
    assert PLANTED_TEXT.decode() not in message
    assert _snapshot(root) == before


# --- Listing failures propagate (AC22, RE-7) --------------------------------


def test_listing_os_error_from_the_file_system_propagates_unwrapped(
    store: LocalDiskRawEvidenceStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    _store_sequences(store, 1, 2)
    failure = PermissionError("synthetic listing failure")

    def failing(*args: object, **kwargs: object) -> NoReturn:
        raise failure

    # Every way of listing a folder, so the test does not depend on which one
    # the adapter uses; the checks on the path (exists, is_dir) stay real.
    with monkeypatch.context() as patched:
        patched.setattr(os, "scandir", failing)
        patched.setattr(os, "listdir", failing)
        patched.setattr(Path, "iterdir", failing)
        patched.setattr(Path, "glob", failing)
        patched.setattr(Path, "rglob", failing)
        with pytest.raises(OSError) as error_info:
            store.list_observation_sequences(EXECUTION_ID)

    assert error_info.value is failure
    assert not isinstance(error_info.value, EvidenceIntegrityError)
