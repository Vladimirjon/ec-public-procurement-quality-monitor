"""The ``ingest`` command: composition of the F4 use case (skeleton).

This module only fixes the names and signatures of the command. The wiring
and the command itself are written in a later outcome.
"""

import argparse
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol, TextIO

from ec_procurement_quality.application.ingest_ports import (
    Clock,
    ClosableIngestionRepository,
    ExecutionIdSource,
)
from ec_procurement_quality.application.procurement_source import ProcurementSource
from ec_procurement_quality.application.raw_evidence_store import RawEvidenceStore
from ec_procurement_quality.infrastructure.postgres_settings import PostgresSettings


class ClosableSource(ProcurementSource, Protocol):
    """A procurement source that releases its resources on ``close``."""

    def close(self) -> None: ...


@dataclass(frozen=True, kw_only=True)
class IngestWiring:
    """The collaborators of one invocation; tests inject their own."""

    base_url: str
    make_source: Callable[[Callable[[], datetime]], ClosableSource]
    make_store: Callable[[Path], RawEvidenceStore]
    make_repository: Callable[[PostgresSettings], ClosableIngestionRepository]
    migrate: Callable[[PostgresSettings, Path], tuple[str, ...]]
    clock: Clock
    execution_ids: ExecutionIdSource


def default_wiring() -> IngestWiring:
    raise NotImplementedError


def run_ingest_command(
    arguments: argparse.Namespace,
    *,
    environ: Mapping[str, str],
    wiring: IngestWiring,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    raise NotImplementedError
