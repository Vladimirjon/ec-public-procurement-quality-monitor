"""The ``ingest`` command: composition of the F4 use case.

This is the composition root of ``ingest``. It reads the environment from the
mapping it is given, resolves the paths once, builds the source, applies the
migrations, builds the store and the repository opener through an
``IngestWiring``, runs ``run_ingest`` and maps its outcome to an exit code (0, 1, 2 or 130), one result
line on stdout and progress on stderr. Nothing here prints a traceback, an
exception chain, a URL, a header, a body, a setting or the password: an
exception that escapes is reported by its class name only.
"""

import argparse
import logging
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
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
from ec_procurement_quality.interfaces.output_streams import write_line

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
    """Writes the progress to stderr and remembers the id of the run it started.

    It also remembers that the result line was attempted: at most one per invocation.
    """

    def __init__(self, stderr: TextIO | None) -> None:
        self._stderr = stderr
        self.execution_id: str | None = None
        self.result_written = False

    def run_started(self, execution_id: str) -> None:
        self.execution_id = execution_id
        write_line(self._stderr, f"run {execution_id} started")

    def progress(self, message: str) -> None:
        write_line(self._stderr, message)


# `interfaces` may not import `httpx`, and `SercopSource` lets the library's own
# construction errors through, so any `Exception` from building the source is
# reported as configuration. Only the class name follows: `httpx` quotes the URL.
_SOURCE_CONFIGURATION_MESSAGE = (
    "error: the source cannot be built from the proxy or certificate settings of "
    "the environment (HTTP_PROXY, HTTPS_PROXY, ALL_PROXY, NO_PROXY, SSL_CERT_FILE, "
    "SSL_CERT_DIR)"
)

_EXIT_CODES = {
    IngestEnd.SUCCEEDED: EXIT_OK,
    IngestEnd.RUN_FAILED: EXIT_FAILED,
    IngestEnd.NOT_STARTED: EXIT_FAILED,
    IngestEnd.INVALID_TARGET: EXIT_USAGE,
    IngestEnd.INTERRUPTED: EXIT_INTERRUPTED,
}


def _attempt(write: Callable[[], None]) -> BaseException | None:
    """Make one write of the result; return what it raised instead of raising it.

    A failing stream never lets an exception escape the command, and the write is
    not repeated. `SystemExit` is not caught.
    """
    try:
        write()
    except (Exception, KeyboardInterrupt) as error:  # noqa: BLE001 -- see above.
        return error
    return None


def _settled_code(code: int, failures: Sequence[BaseException | None]) -> int:
    """The exit code after the result was written, or failed to be.

    A `KeyboardInterrupt` while writing gives 130; any other exception gives 1,
    unless 130 was already determined.
    """
    if any(isinstance(failure, KeyboardInterrupt) for failure in failures):
        return EXIT_INTERRUPTED
    if code != EXIT_INTERRUPTED and any(failure is not None for failure in failures):
        return EXIT_FAILED
    return code


def _report(
    outcome: IngestOutcome,
    reporter: _StderrReporter,
    stdout: TextIO | None,
    stderr: TextIO | None,
) -> int:
    """Write the final message and the result line; return the exit code.

    The outcome's line is the only result line attempted, once, with the status
    the run confirmed: a failure of either write changes only the exit code.
    """
    reporter.result_written = True
    failures = [_attempt(lambda: write_line(stderr, outcome.message))]
    if outcome.execution_id is not None and outcome.run_status is not None:
        line = f"{outcome.execution_id} {outcome.run_status.value}"
        failures.append(_attempt(lambda: write_line(stdout, line)))
    return _settled_code(_EXIT_CODES[outcome.end], failures)


def _print_running(reporter: _StderrReporter, stdout: TextIO | None) -> None:
    """An exception escaped after the run was announced: closing is unconfirmed.

    Nothing is printed when a result line was already attempted.
    """
    if reporter.execution_id is not None and not reporter.result_written:
        reporter.result_written = True
        write_line(stdout, f"{reporter.execution_id} running")


def _end_after_escape(
    reporter: _StderrReporter,
    stdout: TextIO | None,
    stderr: TextIO | None,
    code: int,
    text: str,
) -> int:
    """The handlers of an exception that escaped `run_ingest`: the line, then `text`."""
    failures = [
        _attempt(lambda: _print_running(reporter, stdout)),
        _attempt(lambda: write_line(stderr, text)),
    ]
    return _settled_code(code, failures)


def _migrate(
    wiring: IngestWiring,
    settings: PostgresSettings,
    directory: Path,
    stderr: TextIO | None,
) -> int | None:
    """Apply the migrations; return an exit code when they stop the command."""
    try:
        applied = wiring.migrate(settings, directory)
    except MigrationLockError as error:
        write_line(stderr, str(error))
        return EXIT_FAILED
    except MigrationError as error:
        write_line(stderr, str(error))
        return EXIT_USAGE
    except PersistenceError as error:
        write_line(stderr, str(error))
        return EXIT_FAILED
    for name in applied:
        write_line(stderr, f"applied migration {name}")
    return None


def _invoke(
    request: IngestRequest | ResumeRequest,
    *,
    wiring: IngestWiring,
    settings: PostgresSettings,
    migrations_dir: Path,
    store_root: Path,
    reporter: _StderrReporter,
    stdout: TextIO | None,
    stderr: TextIO | None,
) -> int:
    try:
        source = wiring.make_source(wiring.clock.now)
    except MemoryError:
        raise
    except Exception as error:  # noqa: BLE001 -- see `_SOURCE_CONFIGURATION_MESSAGE`.
        write_line(stderr, f"{_SOURCE_CONFIGURATION_MESSAGE}: {type(error).__name__}")
        return EXIT_USAGE
    exiting = False
    try:
        stopped = _migrate(wiring, settings, migrations_dir, stderr)
        if stopped is not None:
            return stopped
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
        return _report(outcome, reporter, stdout, stderr)
    except SystemExit:
        exiting = True
        raise
    finally:
        # Closing must not change how the run ended. A `SystemExit` that propagates
        # goes on whatever the close raises: it is preserved, never replaced.
        try:
            with suppress(Exception):
                source.close()
        except BaseException:
            if not exiting:
                raise


def run_ingest_command(
    arguments: argparse.Namespace,
    *,
    environ: Mapping[str, str],
    wiring: IngestWiring,
    stdout: TextIO | None,
    stderr: TextIO | None,
) -> int:
    """Run ``ingest`` and return the exit code: 0, 1, 2 or 130.

    The result line ``<execution id> <status>`` goes to ``stdout`` when the
    outcome names a run. Everything else goes to ``stderr``. An exception that
    escapes the use case after the run was started prints
    ``<execution id> running``, because closing was not confirmed: exit 130 for
    a ``KeyboardInterrupt``, 1 for any other exception. A stream that fails while
    the result is written never lets an exception escape: the confirmed status
    stays in the one line attempted, a ``KeyboardInterrupt`` gives 130 and any
    other exception gives 1 unless 130 was already determined.
    """
    reporter = _StderrReporter(stderr)
    try:
        request = request_from_arguments(arguments, base_url=wiring.base_url)
        settings = _settings_from(environ)
    except ValueError as error:
        write_line(stderr, f"error: {error}")
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
        return _end_after_escape(
            reporter, stdout, stderr, EXIT_INTERRUPTED, "interrupted"
        )
    except Exception as error:  # noqa: BLE001 -- only the class name is reported.
        return _end_after_escape(
            reporter,
            stdout,
            stderr,
            EXIT_FAILED,
            f"unexpected error: {type(error).__name__}",
        )
