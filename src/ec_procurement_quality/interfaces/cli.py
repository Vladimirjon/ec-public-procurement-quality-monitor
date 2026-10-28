"""Command-line entry point for ``ec-procurement-quality``.

Only the standard library is used by this module. The commands are
``--version`` and ``ingest``. Every write goes through ``output_streams``, and
``main`` flushes both streams once more as its last step.
"""

import argparse
import os
import sys
from collections.abc import Iterable
from contextlib import suppress
from importlib.metadata import version
from typing import Any

from ec_procurement_quality.infrastructure.sercop_source import DEFAULT_BASE_URL
from ec_procurement_quality.interfaces.ingest_command import (
    EXIT_FAILED,
    EXIT_INTERRUPTED,
    default_wiring,
    request_from_arguments,
    run_ingest_command,
)
from ec_procurement_quality.interfaces.output_streams import (
    flush_for_exit,
    write_line,
    write_text,
)

PROGRAM_NAME = "ec-procurement-quality"
DISTRIBUTION_NAME = "ec-procurement-quality"


# "No file given" must differ from an explicit ``None``, which is a missing stream.
_NO_FILE: Any = object()


class _CliParser(argparse.ArgumentParser):
    """The parser of the command line: ``argparse``'s own, but a failing write shows.

    ``argparse`` suppresses an ``OSError`` from its own writes (``--version``,
    ``--help``, the usage and the error message). Here it reaches the handler of
    ``main``, and the message is flushed in the same attempt. A message meant for a
    missing stream (``None``) is not written, nor written on the other stream, where
    ``argparse`` would fall back to it. Only the writing hook and ``print_usage``
    change; ``argparse`` itself is not patched.
    """

    def _print_message(self, message: str, file: Any = _NO_FILE) -> None:
        if file is _NO_FILE:
            file = sys.stderr
        if message and file is not None:
            with suppress(AttributeError):
                write_text(file, message)

    def print_usage(self, file: Any = _NO_FILE) -> None:
        if file is _NO_FILE:
            file = sys.stdout
        self._print_message(self.format_usage(), file)


class _IngestParser(_CliParser):
    """The ``ingest`` parser, which also checks the rules ``argparse`` cannot state.

    A problem ends in ``error``: the usage line on stderr and exit code 2, before
    anything else happens.
    """

    def parse_known_args(
        self, args: Iterable[str] | None = None, namespace: Any = None
    ) -> Any:
        arguments, extras = super().parse_known_args(args, namespace)
        try:
            request_from_arguments(arguments, base_url=DEFAULT_BASE_URL)
        except ValueError as error:
            self.error(str(error))
        return arguments, extras


def build_parser() -> argparse.ArgumentParser:
    parser = _CliParser(prog=PROGRAM_NAME)
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {version(DISTRIBUTION_NAME)}",
    )
    subparsers = parser.add_subparsers(dest="command", parser_class=_IngestParser)
    ingest = subparsers.add_parser("ingest")
    ingest.add_argument("--year", type=int)
    ingest.add_argument("--buyer")
    ingest.add_argument("--last-page", type=int)
    # No default: `--resume` together with `--first-page` must be detectable. A
    # fresh run starts at page 1 when it is absent.
    ingest.add_argument("--first-page", type=int)
    ingest.add_argument("--resume")
    ingest.add_argument("--migrations-dir", default="migrations")
    return parser


def _code_after_writing(text: str, code: int) -> int:
    """Make one attempt to write ``text`` on stderr; return the code to exit with.

    A ``KeyboardInterrupt`` while it is written makes the code 130 and a
    ``SystemExit`` propagates in its place. Any other exception is ignored.
    """
    with suppress(Exception):
        try:
            write_line(sys.stderr, text)
        except KeyboardInterrupt:
            code = EXIT_INTERRUPTED
    return code


def _code_of(argv: list[str] | None) -> int:
    """Run ``argv`` and return the code ``main`` itself exits with.

    A ``SystemExit`` raised inside (``argparse``'s, or the one of a defect) is never
    caught here.
    """
    try:
        parser = build_parser()
        arguments = parser.parse_args(argv)
        if arguments.command == "ingest":
            return run_ingest_command(
                arguments,
                environ=os.environ,
                wiring=default_wiring(),
                stdout=sys.stdout,
                stderr=sys.stderr,
            )
        parser.print_usage(sys.stderr)
        return 2
    except KeyboardInterrupt:
        return _code_after_writing("interrupted", EXIT_INTERRUPTED)
    except Exception as error:  # noqa: BLE001 -- only the class name is reported.
        return _code_after_writing(
            f"unexpected error: {type(error).__name__}", EXIT_FAILED
        )


def main(argv: list[str] | None = None) -> None:
    """Parse ``argv`` (or the process arguments when ``None``).

    ``--version``, usage errors and the ``ingest`` command end through
    ``SystemExit`` (code 0, 2 and the command's exit code). Anything else that is
    raised ends the same way, naming only its class on stderr: 130 for a
    ``KeyboardInterrupt``, 1 otherwise. A ``SystemExit`` is never converted.

    The last step, by any path, flushes stdout and then stderr (no text is written):
    a failure there changes nothing, a ``KeyboardInterrupt`` makes the code 130 when
    ``main`` exits with its own code, and a ``SystemExit`` there replaces that code.
    A ``SystemExit`` that is already propagating is the first one and always wins.
    """
    try:
        code = _code_of(argv)
    except SystemExit:
        flush_for_exit(sys.stdout, sys.stderr)
        raise
    raised = flush_for_exit(sys.stdout, sys.stderr)
    if isinstance(raised, SystemExit):
        raise raised
    raise SystemExit(EXIT_INTERRUPTED if raised is not None else code)
