"""The ``ingest`` command: composition of the F4 use case.

This is the composition root of ``ingest``. It reads the environment from the
mapping it is given, resolves the paths once, applies the migrations, builds the
source, the store and the repository opener through an ``IngestWiring``, runs
``run_ingest`` and maps its outcome to an exit code (0, 1, 2 or 130), one result
line on stdout and progress on stderr. Nothing here prints a traceback, an
exception chain, a URL, a header, a body, a setting or the password: an
exception that escapes is reported by its class name only.
"""

import argparse
import logging
import re
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol, TextIO

from ec_procurement_quality.application.ingest_ports import (
    Clock,
    ClosableIngestionRepository,
    ExecutionIdSource,
)
from ec_procurement_quality.application.ingest_use_case import (
    IngestEnd,
    IngestOutcome,
    IngestRequest,
    ResumeRequest,
    run_ingest,
)
from ec_procurement_quality.application.procurement_source import ProcurementSource
from ec_procurement_quality.application.raw_evidence_store import RawEvidenceStore
from ec_procurement_quality.domain.ingestion_catalogue import IngestScope
from ec_procurement_quality.domain.persistence_errors import (
    MigrationError,
    MigrationLockError,
    PersistenceError,
)
from ec_procurement_quality.domain.raw_evidence import validate_execution_id
from ec_procurement_quality.infrastructure.local_disk_raw_evidence_store import (
    LocalDiskRawEvidenceStore,
)
from ec_procurement_quality.infrastructure.postgres_ingestion_repository import (
    PostgresIngestionRepository,
)
from ec_procurement_quality.infrastructure.postgres_migrations import apply_migrations
from ec_procurement_quality.infrastructure.postgres_settings import PostgresSettings
from ec_procurement_quality.infrastructure.sercop_source import (
    DEFAULT_BASE_URL,
    SercopSource,
)
from ec_procurement_quality.infrastructure.system_clock import (
    RandomExecutionIdSource,
    SystemClock,
)

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_INTERRUPTED = 130

DEFAULT_POSTGRES_HOST = "127.0.0.1"
DEFAULT_POSTGRES_PORT = 5432
_REQUIRED_VARIABLES = ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")
_STORE_RELATIVE_ROOT = Path("data") / "raw"
_SCOPE_OPTIONS = (
    ("year", "--year"),
    ("buyer", "--buyer"),
    ("first_page", "--first-page"),
    ("last_page", "--last-page"),
)


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
    """The real collaborators: SERCOP over HTTP, the local disk and PostgreSQL."""
    return IngestWiring(
        base_url=DEFAULT_BASE_URL,
        make_source=lambda now: SercopSource(base_url=DEFAULT_BASE_URL, now=now),
        make_store=LocalDiskRawEvidenceStore,
        make_repository=PostgresIngestionRepository,
        migrate=apply_migrations,
        clock=SystemClock(),
        execution_ids=RandomExecutionIdSource(),
    )


def request_from_arguments(
    arguments: argparse.Namespace, *, base_url: str
) -> IngestRequest | ResumeRequest:
    """Turn the parsed ``ingest`` arguments into a request.

    Raises ``ValueError`` for every rule ``argparse`` cannot express: a missing
    option on a fresh run, ``--resume`` together with a scope option, a
    ``--resume`` id outside the F1 pattern and any ``IngestScope`` rule. The
    messages name the option or field and never its value.
    """
    if arguments.resume is not None:
        if any(getattr(arguments, name) is not None for name, _ in _SCOPE_OPTIONS):
            raise ValueError(
                "--resume cannot be combined with --year, --buyer, --first-page "
                "or --last-page"
            )
        try:
            validate_execution_id(arguments.resume)
        except ValueError as error:
            raise ValueError(f"--resume: {error}") from None
        return ResumeRequest(execution_id=arguments.resume)
    missing = [
        option
        for name, option in _SCOPE_OPTIONS
        if name != "first_page" and getattr(arguments, name) is None
    ]
    if missing:
        raise ValueError(f"the following arguments are required: {', '.join(missing)}")
    first_page = 1 if arguments.first_page is None else arguments.first_page
    return IngestRequest(
        scope=IngestScope(
            base_url=base_url,
            buyer=arguments.buyer,
            year=arguments.year,
            first_page=first_page,
            last_page=arguments.last_page,
        )
    )


def _settings_from(environ: Mapping[str, str]) -> PostgresSettings:
    """Build the connection settings from ``environ`` alone.

    Raises ``ValueError`` naming the variable or field, never its value.
    """
    for variable in _REQUIRED_VARIABLES:
        if variable not in environ:
            raise ValueError(f"{variable} is not set")
    port = DEFAULT_POSTGRES_PORT
    if "POSTGRES_PORT" in environ:
        text = environ["POSTGRES_PORT"]
        # The length bound keeps `int` away from absurd digit strings.
        if re.fullmatch(r"[0-9]{1,9}", text) is None:
            raise ValueError("POSTGRES_PORT must be a decimal integer from 1 to 65535")
        port = int(text)
    return PostgresSettings(
        host=environ.get("POSTGRES_HOST", DEFAULT_POSTGRES_HOST),
        port=port,
        dbname=environ["POSTGRES_DB"],
        user=environ["POSTGRES_USER"],
        password=environ["POSTGRES_PASSWORD"],
    )


@contextmanager
def _httpcore_above_debug() -> Iterator[None]:
    """Keep the ``httpcore`` logger above ``DEBUG`` and restore it afterwards.

    At ``DEBUG`` it logs request headers. Only its own level changes; no handler
    is added and nothing else is configured.
    """
    logger = logging.getLogger("httpcore")
    own_level = logger.level
    if logger.getEffectiveLevel() <= logging.DEBUG:
        logger.setLevel(logging.WARNING)
    try:
        yield
    finally:
        logger.setLevel(own_level)


class _StderrReporter:
    """Writes the progress to stderr and remembers the id of the run it started."""

    def __init__(self, stderr: TextIO) -> None:
        self._stderr = stderr
        self.execution_id: str | None = None

    def run_started(self, execution_id: str) -> None:
        self.execution_id = execution_id
        print(f"run {execution_id} started", file=self._stderr)

    def progress(self, message: str) -> None:
        print(message, file=self._stderr)


_EXIT_CODES = {
    IngestEnd.SUCCEEDED: EXIT_OK,
    IngestEnd.RUN_FAILED: EXIT_FAILED,
    IngestEnd.NOT_STARTED: EXIT_FAILED,
    IngestEnd.INVALID_TARGET: EXIT_USAGE,
    IngestEnd.INTERRUPTED: EXIT_INTERRUPTED,
}


def _report(outcome: IngestOutcome, stdout: TextIO, stderr: TextIO) -> int:
    """Write the final message and the result line; return the exit code."""
    print(outcome.message, file=stderr)
    if outcome.execution_id is not None and outcome.run_status is not None:
        print(f"{outcome.execution_id} {outcome.run_status.value}", file=stdout)
    return _EXIT_CODES[outcome.end]


def _migrate(
    wiring: IngestWiring,
    settings: PostgresSettings,
    directory: Path,
    stderr: TextIO,
) -> int | None:
    """Apply the migrations; return an exit code when they stop the command."""
    try:
        applied = wiring.migrate(settings, directory)
    except MigrationLockError as error:
        print(str(error), file=stderr)
        return EXIT_FAILED
    except MigrationError as error:
        print(str(error), file=stderr)
        return EXIT_USAGE
    except PersistenceError as error:
        print(str(error), file=stderr)
        return EXIT_FAILED
    for name in applied:
        print(f"applied migration {name}", file=stderr)
    return None


def _invoke(
    request: IngestRequest | ResumeRequest,
    *,
    wiring: IngestWiring,
    settings: PostgresSettings,
    migrations_dir: Path,
    store_root: Path,
    reporter: _StderrReporter,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    stopped = _migrate(wiring, settings, migrations_dir, stderr)
    if stopped is not None:
        return stopped
    source = wiring.make_source(wiring.clock.now)
    try:
        store = wiring.make_store(store_root)
        outcome = run_ingest(
            request,
            source=source,
            store=store,
            open_repository=lambda: wiring.make_repository(settings),
            clock=wiring.clock,
            execution_ids=wiring.execution_ids,
            reporter=reporter,
        )
        return _report(outcome, stdout, stderr)
    finally:
        # Closing must not change how the run ended.
        with suppress(Exception):
            source.close()


def run_ingest_command(
    arguments: argparse.Namespace,
    *,
    environ: Mapping[str, str],
    wiring: IngestWiring,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """Run ``ingest`` and return the exit code: 0, 1, 2 or 130.

    The result line ``<execution id> <status>`` goes to ``stdout`` when the
    outcome names a run. Everything else goes to ``stderr``. A
    ``KeyboardInterrupt`` that escapes the use case after the run was started
    prints ``<execution id> running``, because closing was not confirmed.
    """
    reporter = _StderrReporter(stderr)
    try:
        request = request_from_arguments(arguments, base_url=wiring.base_url)
        settings = _settings_from(environ)
    except ValueError as error:
        print(f"error: {error}", file=stderr)
        return EXIT_USAGE
    try:
        # Resolved once; nothing later reads the current directory.
        cwd = Path.cwd()
        store_root = cwd / _STORE_RELATIVE_ROOT
        migrations_dir = cwd / arguments.migrations_dir
        with _httpcore_above_debug():
            return _invoke(
                request,
                wiring=wiring,
                settings=settings,
                migrations_dir=migrations_dir,
                store_root=store_root,
                reporter=reporter,
                stdout=stdout,
                stderr=stderr,
            )
    except KeyboardInterrupt:
        if reporter.execution_id is not None:
            print(f"{reporter.execution_id} running", file=stdout)
        print("interrupted", file=stderr)
        return EXIT_INTERRUPTED
    except Exception as error:  # noqa: BLE001 -- only the class name is reported.
        print(f"unexpected error: {type(error).__name__}", file=stderr)
        return EXIT_FAILED
