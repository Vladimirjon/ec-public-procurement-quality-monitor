"""AC4, AC5: the `ec-procurement-quality` CLI contract.

The CLI entry point is `ec_procurement_quality.interfaces.cli:main`. It takes an
optional list of argument strings and ends through `SystemExit`.
"""

import tomllib
from pathlib import Path

import pytest

from ec_procurement_quality.interfaces.cli import main

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROGRAM_NAME = "ec-procurement-quality"


def _declared_version() -> str:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as handle:
        version = tomllib.load(handle)["project"]["version"]
    assert isinstance(version, str)
    return version


def test_version_prints_program_name_and_pyproject_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])

    captured = capsys.readouterr()
    assert exit_info.value.code == 0
    assert captured.out == f"{PROGRAM_NAME} {_declared_version()}\n"
    assert captured.err == ""


def test_bogus_option_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--bogus"])

    captured = capsys.readouterr()
    assert exit_info.value.code == 2
    assert captured.out == ""
    assert "unrecognized arguments: --bogus" in captured.err
