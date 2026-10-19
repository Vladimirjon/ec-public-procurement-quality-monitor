"""Application ports for an ingest run: clock, execution ids, repository, reporting.

The ingest use case reads the time and draws execution ids through these ports,
opens its own repository through `RepositoryOpener`, and says what it is doing
only through `IngestReporter`.
"""

from datetime import datetime
from typing import Protocol

from ec_procurement_quality.application.ingestion_repository import IngestionRepository


class Clock(Protocol):
    """The source of the current time."""

    def now(self) -> datetime:
        """Return the current time, with a UTC offset."""
        ...


class ExecutionIdSource(Protocol):
    """The source of new ingest execution ids."""

    def new_execution_id(self, started_at: datetime) -> str: ...


class ClosableIngestionRepository(IngestionRepository, Protocol):
    """An ingestion repository whose connection the caller closes."""

    def close(self) -> None: ...


class RepositoryOpener(Protocol):
    """Opens a repository for one use of the use case.

    A call raises `PersistenceConnectionError` when the database cannot be reached.
    """

    def __call__(self) -> ClosableIngestionRepository: ...


class IngestReporter(Protocol):
    """Where the use case says what it is doing.

    A message holds only fixed words, integers, content hashes, execution ids and
    project error text; for any other exception it holds the class name only.
    """

    def run_started(self, execution_id: str) -> None: ...

    def progress(self, message: str) -> None: ...
