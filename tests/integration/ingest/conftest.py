"""Feature ingest-command (F4), outcome O2 (AC19, AC23): the guards of
`tests/integration/ingest`.

What this file provides, as `execution-plan.md` § Tests pins it:

- `network_guard` (autouse): the same guard as F2's, except that name resolution
  is allowed for the configured `POSTGRES_HOST` only. It patches
  `socket.socket.connect`, `connect_ex`, `socket.create_connection` and
  `socket.getaddrinfo`. `libpq` opens its own sockets outside Python, so
  PostgreSQL keeps working while any `httpx` attempt fails. A test that attempts
  the network on purpose (the proof tests) empties `attempts` itself; for every
  other test an attempt fails it at teardown;
- `real_raw_directory_is_untouched` (session, autouse): the names, sizes and
  modification times under the repository's real `data/raw/` at session start
  must be the same at session end. File contents are never read.

The host is read from `POSTGRES_HOST` in the process environment (unset or empty
means `127.0.0.1`, as in `tests/integration/conftest.py`); this file never reads
`.env` and never prints a setting. O6b extends this file with the seams and the
composition helpers of the CLI tests; keep each part below self-contained.
"""

from __future__ import annotations

import os
import socket
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NoReturn

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
REAL_RAW_ROOT = REPOSITORY_ROOT / "data" / "raw"
DEFAULT_POSTGRES_HOST = "127.0.0.1"

# --- The network guard ------------------------------------------------------


@dataclass
class NetworkGuard:
    """What the guard allows and what it refused during one test."""

    allowed_host: str
    attempts: list[str] = field(default_factory=list)


@pytest.fixture(autouse=True)
def network_guard(monkeypatch: pytest.MonkeyPatch) -> Iterator[NetworkGuard]:
    """Fail the test if it opens a socket or resolves any host but PostgreSQL's."""
    guard = NetworkGuard(
        allowed_host=os.environ.get("POSTGRES_HOST") or DEFAULT_POSTGRES_HOST
    )
    resolve = socket.getaddrinfo

    def blocked(name: str) -> Callable[..., NoReturn]:
        def refuse(*args: Any, **kwargs: Any) -> NoReturn:
            guard.attempts.append(name)
            raise OSError(f"synthetic network guard: {name} is blocked in tests")

        return refuse

    def resolve_configured_host_only(host: Any, *args: Any, **kwargs: Any) -> Any:
        if isinstance(host, str) and host == guard.allowed_host:
            return resolve(host, *args, **kwargs)
        guard.attempts.append("getaddrinfo")
        raise OSError("synthetic network guard: getaddrinfo is blocked in tests")

    monkeypatch.setattr(socket.socket, "connect", blocked("connect"))
    monkeypatch.setattr(socket.socket, "connect_ex", blocked("connect_ex"))
    monkeypatch.setattr(socket, "create_connection", blocked("create_connection"))
    monkeypatch.setattr(socket, "getaddrinfo", resolve_configured_host_only)

    yield guard

    assert guard.attempts == [], (
        f"the test tried to reach the network: {guard.attempts}"
    )


# --- The real data/raw/ stays untouched -------------------------------------

RawSnapshot = dict[str, tuple[str, int, int]]


def snapshot_of(root: Path) -> RawSnapshot:
    """Relative path -> (kind, size, modification time in ns) for everything
    under `root`. A missing `root` gives an empty snapshot. No file is opened."""
    if not root.exists():
        return {}
    entries: RawSnapshot = {}
    for path in sorted(root.rglob("*")):
        status = path.lstat()
        kind = "dir" if path.is_dir() and not path.is_symlink() else "file"
        entries[path.relative_to(root).as_posix()] = (
            kind,
            status.st_size,
            status.st_mtime_ns,
        )
    return entries


@pytest.fixture(scope="session", autouse=True)
def real_raw_directory_is_untouched() -> Iterator[None]:
    """The names, sizes and times under the real `data/raw/` do not change."""
    before = snapshot_of(REAL_RAW_ROOT)
    yield
    after = snapshot_of(REAL_RAW_ROOT)
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(
        name for name in set(before) & set(after) if before[name] != after[name]
    )
    assert (added, removed, changed) == ([], [], []), (
        "the integration session touched the real data/raw/: "
        f"added {added}, removed {removed}, changed {changed}"
    )
