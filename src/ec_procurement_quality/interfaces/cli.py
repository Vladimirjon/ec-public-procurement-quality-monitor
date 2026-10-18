"""Command-line entry point for ``ec-procurement-quality``.

Only the standard library is used by this module. The commands are
``--version`` and ``ingest``.
"""

import argparse
import os
import sys
from importlib.metadata import version

from ec_procurement_quality.interfaces.ingest_command import (
    default_wiring,
    run_ingest_command,
)

PROGRAM_NAME = "ec-procurement-quality"
DISTRIBUTION_NAME = "ec-procurement-quality"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=PROGRAM_NAME)
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {version(DISTRIBUTION_NAME)}",
    )
    subparsers = parser.add_subparsers(dest="command")
    ingest = subparsers.add_parser("ingest")
    ingest.add_argument("--year", type=int)
    ingest.add_argument("--buyer")
    ingest.add_argument("--last-page", type=int)
    ingest.add_argument("--first-page", type=int, default=1)
    ingest.add_argument("--resume")
    ingest.add_argument("--migrations-dir", default="migrations")
    return parser


def main(argv: list[str] | None = None) -> None:
    """Parse ``argv`` (or the process arguments when ``None``).

    ``--version``, usage errors and the ``ingest`` command end through
    ``SystemExit`` (code 0, 2 and the command's exit code).
    """
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if arguments.command == "ingest":
        code = run_ingest_command(
            arguments,
            environ=os.environ,
            wiring=default_wiring(),
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        raise SystemExit(code)
    parser.print_usage(sys.stderr)
    raise SystemExit(2)
