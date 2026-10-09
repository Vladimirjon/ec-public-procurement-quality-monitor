"""Command-line entry point for ``ec-procurement-quality``.

Only the standard library is used. The only behavior so far is ``--version``.
"""

import argparse
from importlib.metadata import version

PROGRAM_NAME = "ec-procurement-quality"
DISTRIBUTION_NAME = "ec-procurement-quality"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=PROGRAM_NAME)
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {version(DISTRIBUTION_NAME)}",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """Parse ``argv`` (or the process arguments when ``None``).

    ``--version`` and usage errors end through ``SystemExit`` (code 0 and 2).
    """
    build_parser().parse_args(argv)
