"""Feature ingest-command (F4), outcome O4 (AC18, AC19): layers, ports and the guard.

`-k` token: `layer`. The existing `tests/unit/test_layers.py` already checks that
`application` imports only the standard library, `domain` and itself, and that
only `infrastructure` imports `httpx` or `psycopg`. This file adds what AC18 asks
of the ingest use case:

- no module under `application/` holds SQL, the words of the PostgreSQL lock
  mechanism or a piece of the store layout;
- the ingest use case and its ports import only the standard library, `domain`
  and `application`, and no module that touches the disk, a socket or a log;
- the doubles of `conftest.py` implement every operation of the ports they stand
  for, with the same parameters (a port that grows must make a double fail here);
- the unit network guard blocks a socket and a name resolution (its proof test,
  AC19).

The `mypy` half of AC18 (the doubles are accepted as the extended ports) is
`uv run mypy .`.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import socket
import sys
import typing
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import pytest

from ec_procurement_quality.application.ingest_ports import (
    Clock,
    ClosableIngestionRepository,
    ExecutionIdSource,
    IngestReporter,
    RepositoryOpener,
)
from ec_procurement_quality.application.procurement_source import ProcurementSource
from ec_procurement_quality.application.raw_evidence_store import RawEvidenceStore

if TYPE_CHECKING:
    from tests.unit.ingest.conftest import Lab, NetworkGuard

APPLICATION_PACKAGE = "ec_procurement_quality.application"
FORBIDDEN_IN_APPLICATION = (
    "advisory",
    "pg_",
    "SELECT ",
    "INSERT ",
    "UPDATE ",
    "DELETE ",
    "objects/",
    "observations/",
    ".json",
)
# Modules that reach the disk, a socket, a process or a log: the use case works
# only through its ports (AC18: no database, network or disk).
EFFECTFUL_MODULES = frozenset(
    {
        "os",
        "pathlib",
        "shutil",
        "tempfile",
        "socket",
        "ssl",
        "subprocess",
        "sqlite3",
        "logging",
        "http",
        "urllib",
        "glob",
    }
)


def application_root() -> Path:
    package = importlib.import_module(APPLICATION_PACKAGE)
    assert package.__file__ is not None, "application needs an __init__.py"
    return Path(next(iter(package.__path__)))


def imported_modules(path: Path) -> list[tuple[str, int]]:
    """(module name, relative level) of every import in the file."""
    found: list[tuple[str, int]] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.extend((alias.name, 0) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append((node.module or "", node.level))
    return found


def test_layer_application_holds_no_sql_lock_words_or_store_layout() -> None:
    """AC18: `application` reaches the store and the database only through ports."""
    modules = sorted(application_root().glob("*.py"))
    # Not vacuous: the ingest modules are among those searched.
    assert {"ingest_use_case.py", "ingest_ports.py"} <= {m.name for m in modules}

    offenders = [
        f"{module.name}: {text!r}"
        for module in modules
        for text in FORBIDDEN_IN_APPLICATION
        if text in module.read_text(encoding="utf-8")
    ]

    assert offenders == []


@pytest.mark.parametrize("module_name", ["ingest_use_case.py", "ingest_ports.py"])
def test_layer_ingest_modules_import_only_stdlib_domain_and_application(
    module_name: str,
) -> None:
    """AC18: nothing from `infrastructure`, `interfaces` or a third party."""
    path = application_root() / module_name
    assert path.is_file(), f"application needs {module_name}"

    offenders: list[str] = []
    for name, level in imported_modules(path):
        if level > 0:
            offenders.append(f"relative import {'.' * level}{name}")
            continue
        top = name.split(".")[0]
        inside = name == "ec_procurement_quality" or name.startswith(
            ("ec_procurement_quality.domain", f"{APPLICATION_PACKAGE}")
        )
        if top not in sys.stdlib_module_names and not inside:
            offenders.append(name)

    assert offenders == []


@pytest.mark.parametrize("module_name", ["ingest_use_case.py", "ingest_ports.py"])
def test_layer_ingest_modules_use_no_disk_socket_process_or_log_module(
    module_name: str,
) -> None:
    """AC18: the use case runs with in-memory doubles only."""
    path = application_root() / module_name

    used = sorted(
        {
            name.split(".")[0]
            for name, level in imported_modules(path)
            if level == 0 and name.split(".")[0] in EFFECTFUL_MODULES
        }
    )

    assert used == []


# The doubles stand for these protocols: each one is checked member by member.


def protocol_members(protocol: type) -> list[str]:
    return sorted(typing.get_protocol_members(protocol))


def parameters_of(function: Callable[..., object]) -> list[tuple[str, object]]:
    """(name, kind) of each parameter, without `self`."""
    return [
        (parameter.name, parameter.kind)
        for parameter in inspect.signature(function).parameters.values()
        if parameter.name != "self"
    ]


def test_layer_the_doubles_implement_every_operation_of_their_ports(lab: Lab) -> None:
    """AC18: same operations, same parameter names and kinds as the extended ports."""
    pairs: list[tuple[type, object]] = [
        (RawEvidenceStore, lab.store),
        (RawEvidenceStore, lab.publishes_then_fails(on_call=1)),
        (RawEvidenceStore, lab.refuses_to_store(on_call=1)),
        (ClosableIngestionRepository, lab.opener()),
        (ProcurementSource, lab.source),
        (Clock, lab.clock),
        (ExecutionIdSource, lab.execution_ids),
        (IngestReporter, lab.reporter),
        (RepositoryOpener, lab.opener),
    ]
    for protocol, double in pairs:
        members = protocol_members(protocol)
        assert members, protocol.__name__
        for name in members:
            assert callable(getattr(double, name, None)), (protocol.__name__, name)
            assert parameters_of(getattr(double, name)) == parameters_of(
                getattr(protocol, name)
            ), (protocol.__name__, name)


def test_layer_the_extended_ports_name_the_new_operations() -> None:
    """AC22, AC23: the operations O1 and O2 added are part of the ports."""
    assert "list_observation_sequences" in protocol_members(RawEvidenceStore)
    repository = protocol_members(ClosableIngestionRepository)
    assert {"list_runs", "try_acquire_ingest_exclusion", "close"} <= set(repository)


# The proof test of the unit guard (AC19).


def test_layer_the_network_guard_blocks_sockets_and_name_resolution(
    network_guard: NetworkGuard,
) -> None:
    """AC19: any socket or name resolution fails, and the guard records it."""
    with pytest.raises(OSError):
        socket.getaddrinfo("source.invalid", 443)
    with pytest.raises(OSError):
        socket.create_connection(("source.invalid", 443))
    with pytest.raises(OSError), socket.socket() as plain:
        plain.connect(("source.invalid", 443))
    with pytest.raises(OSError), socket.socket() as plain:
        plain.connect_ex(("source.invalid", 443))
    with pytest.raises(httpx.ConnectError), httpx.Client() as client:
        client.get("https://source.invalid/PLATAFORMA/api/search_ocds")

    assert {
        "getaddrinfo",
        "create_connection",
        "socket.connect",
        "socket.connect_ex",
    } <= set(network_guard.attempts)
    # The attempts were the point of this test: the teardown check must not fail it.
    network_guard.attempts.clear()
