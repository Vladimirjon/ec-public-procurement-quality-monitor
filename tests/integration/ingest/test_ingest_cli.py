"""Feature ingest-command (F4), outcome O6b: the command against a real PostgreSQL.

Names to focus on, by `-k`:

- `migrations` (AC16, decision P-1): the pending migrations are applied before the
  repository is built, a changed or missing applied file exits 2, the migration lock
  held elsewhere exits 1. Since plan Revision 6 the source is built first (invocation
  step 2), so a refused migration records `["make_source", "migrate"]`;
- `root` (AC25): the store root is `data/raw/` resolved once against the current
  directory, from a synthetic repository root `<T>` that holds a copy of the
  repository's `migrations/`;
- `cli_` (AC14, AC8, AC9): `main([...])` ends through `SystemExit`; an argument or
  environment error exits 2 before the database is touched; an unreachable database
  or a held exclusion exits 1 and starts nothing.

Each test runs in its own throwaway database, never the one named by `POSTGRES_DB`.
The simulated source is `SercopSource` over `httpx.MockTransport`; the real
`data/raw/` is never used (`root` enters a temporary directory). Data is synthetic.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from ec_procurement_quality.domain.ingestion_audit import same_json
from ec_procurement_quality.infrastructure.local_disk_raw_evidence_store import (
    LocalDiskRawEvidenceStore,
)
from ec_procurement_quality.infrastructure.postgres_ingestion_repository import (
    INGEST_EXCLUSION_KEY,
)
from ec_procurement_quality.infrastructure.postgres_migrations import (
    MIGRATION_LOCK_KEY,
)

if TYPE_CHECKING:
    from tests.integration.ingest.conftest import IngestLab

pytestmark = pytest.mark.integration

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS = REPOSITORY_ROOT / "migrations"
FIRST_MIGRATION = "0001_initial_schema.sql"
BASE_URL = "https://source.invalid/PLATAFORMA"
BUYER = "SYNTHETIC BUYER S.A."
YEAR = 2025
HTML_429 = b"<html><body>synthetic rate limit</body></html>"


def scope(first: int = 1, last: int = 2) -> list[str]:
    return [
        "--year",
        str(YEAR),
        "--buyer",
        BUYER,
        "--first-page",
        str(first),
        "--last-page",
        str(last),
    ]


def copy_of_migrations(destination: Path) -> Path:
    """A temporary copy of the repository's migration files."""
    shutil.copytree(MIGRATIONS, destination)
    return destination


def assert_no_setting_leaked(lab: IngestLab, *texts: str) -> None:
    """Neither the database name nor the password shows in the given texts."""
    settings = lab.settings
    for text in texts:
        assert settings.dbname not in text
        if len(settings.password) >= 6:
            assert settings.password not in text


# === migrations (AC16, decision P-1) ===========================================


def test_migrations_an_empty_database_gets_0001_then_the_run_succeeds(
    empty_lab: IngestLab,
) -> None:
    """AC16: `0001` is applied and named on stderr, then the run goes as AC1."""
    lab = empty_lab
    assert not lab.table_exists("schema_migration")

    result = lab.run(scope(1, 2))

    run_id = result.run_id
    assert result.code == 0
    assert result.out == f"{run_id} succeeded\n"
    assert FIRST_MIGRATION in result.err
    assert FIRST_MIGRATION not in result.out
    assert_no_setting_leaked(lab, result.err, result.out)
    assert lab.query("SELECT filename FROM schema_migration") == [(FIRST_MIGRATION,)]
    assert lab.run_row(run_id)[0] == "succeeded"
    assert lab.pages.requests == [1, 2]


def test_migrations_a_migrated_database_applies_nothing(
    migrated_lab: IngestLab,
) -> None:
    """AC16: nothing pending -> no file named on stderr, the record unchanged."""
    lab = migrated_lab

    result = lab.run(scope(1, 2))

    assert result.code == 0
    assert ".sql" not in result.err
    assert lab.query("SELECT filename FROM schema_migration") == [(FIRST_MIGRATION,)]


def test_migrations_return_before_the_repository_is_built(
    empty_lab: IngestLab,
) -> None:
    """AC16: `apply_migrations` returns before `make_repository` is called."""
    lab = empty_lab

    result = lab.run(scope(1, 2))

    assert result.code == 0
    assert lab.calls.index("migrate") < lab.calls.index("migrate:done")
    assert lab.calls.index("migrate:done") < lab.calls.index("make_repository")
    assert lab.calls.count("migrate") == 1


def test_migrations_the_source_is_built_before_the_migrations_run(
    empty_lab: IngestLab,
) -> None:
    """AC14, AC16 (plan Revision 6, step 2): `make_source` comes before `migrate`."""
    lab = empty_lab

    result = lab.run(scope(1, 2))

    assert result.code == 0
    assert lab.calls.count("make_source") == 1
    assert lab.calls[:3] == ["make_source", "migrate", "migrate:done"]
    assert lab.calls.index("migrate:done") < lab.calls.index("make_store")


def test_migrations_a_changed_applied_file_exits_2_and_creates_no_run(
    migrated_lab: IngestLab, tmp_path: Path
) -> None:
    """AC16: a `MigrationError` that is not a lock error -> exit 2, no run."""
    lab = migrated_lab
    directory = copy_of_migrations(tmp_path / "changed-migrations")
    changed = directory / FIRST_MIGRATION
    changed.write_text(changed.read_text(encoding="utf-8") + "\n-- changed\n")

    result = lab.run([*scope(1, 2), "--migrations-dir", str(directory)])

    assert result.code == 2
    assert result.out == ""
    assert result.err.strip() != ""
    assert_no_setting_leaked(lab, result.err)
    assert lab.calls == ["make_source", "migrate"]
    assert lab.run_ids() == []
    assert lab.pages.requests == []
    assert lab.files() == {}


def test_migrations_a_missing_applied_file_exits_2(
    migrated_lab: IngestLab, tmp_path: Path
) -> None:
    """AC16: the directory lacks an applied file -> exit 2, no run."""
    lab = migrated_lab
    directory = tmp_path / "no-migrations"
    directory.mkdir()

    result = lab.run([*scope(1, 2), "--migrations-dir", str(directory)])

    assert result.code == 2
    assert result.out == ""
    assert lab.calls == ["make_source", "migrate"]
    assert lab.run_ids() == []
    assert lab.pages.requests == []


def _missing_directory(tmp_path: Path) -> Path:
    return tmp_path / "missing-migrations"


def _numbering_gap(tmp_path: Path) -> Path:
    directory = tmp_path / "gap-migrations"
    directory.mkdir()
    (directory / "0002_second.sql").write_text("SELECT 1;\n", encoding="utf-8")
    return directory


def _misnamed_file(tmp_path: Path) -> Path:
    directory = tmp_path / "misnamed-migrations"
    directory.mkdir()
    (directory / "first.sql").write_text("SELECT 1;\n", encoding="utf-8")
    return directory


@pytest.mark.parametrize(
    "make_directory",
    [_missing_directory, _numbering_gap, _misnamed_file],
    ids=["missing-directory", "numbering-gap", "misnamed-file"],
)
def test_migrations_an_invalid_directory_exits_2_and_the_database_stays_empty(
    empty_lab: IngestLab, tmp_path: Path, make_directory: Callable[[Path], Path]
) -> None:
    """AC14, AC16: the directory is refused before any connection is opened."""
    lab = empty_lab
    directory = make_directory(tmp_path)

    result = lab.run([*scope(1, 2), "--migrations-dir", str(directory)])

    assert result.code == 2
    assert result.out == ""
    assert not lab.table_exists("schema_migration")
    assert not lab.table_exists("ingestion_run")
    assert lab.calls == ["make_source", "migrate"]
    assert lab.pages.requests == []
    assert lab.files() == {}


def test_migrations_the_lock_held_elsewhere_exits_1_and_creates_no_run(
    migrated_lab: IngestLab,
) -> None:
    """AC16 (P-1): `MigrationLockError` -> exit 1, stdout empty, no run."""
    lab = migrated_lab
    lab.hold(MIGRATION_LOCK_KEY)

    result = lab.run(scope(1, 2))

    assert result.code == 1
    assert result.out == ""
    assert result.err.strip() != ""
    assert_no_setting_leaked(lab, result.err)
    assert lab.calls == ["make_source", "migrate"]
    assert lab.run_ids() == []
    assert lab.pages.requests == []
    assert lab.files() == {}


# === root (AC25) ===============================================================


def test_root_the_store_is_resolved_once_from_the_synthetic_repository_root(
    migrated_lab: IngestLab, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC25: a change of directory during the run moves nothing; resume finds page 1.

    `<T>` stands for the repository root and holds a copy of `migrations/`; the
    command uses its default relative `--migrations-dir` and its own store root.
    While page 1 is requested the process moves to `<U>`; every file of the run
    must be under `<T>/data/raw/` and none under `<U>`.
    """
    lab = migrated_lab
    root = tmp_path / "synthetic-repository-root"
    elsewhere = tmp_path / "somewhere-else"
    copy_of_migrations(root / "migrations")
    elsewhere.mkdir()
    monkeypatch.chdir(root)
    lab.on_request(1, lambda: monkeypatch.chdir(elsewhere))
    lab.pages.reply(2, lab.reply(status=429, body=HTML_429))
    wiring = lab.wiring(make_store=LocalDiskRawEvidenceStore)

    first = lab.run(scope(1, 3), wiring=wiring)

    run_id = first.run_id
    assert first.code == 1
    assert first.out == f"{run_id} failed\n"
    store_files = lab.files(root / "data" / "raw")
    assert f"observations/{run_id}/1.json" in store_files
    assert f"observations/{run_id}/2.json" in store_files
    assert any(name.startswith("objects/") for name in store_files)
    assert sorted(elsewhere.iterdir()) == []
    assert lab.files() == {}  # the lab's own store was never the one used
    assert lab.pages.requests == [1, 2]

    # A later resumption, started from `<T>`, does not request page 1 again.
    monkeypatch.chdir(root)
    second = lab.run(["--resume", run_id], wiring=wiring)

    assert second.code == 0
    assert second.out == f"{second.run_id} succeeded\n"
    assert lab.pages.requests == [1, 2, 2, 3]
    assert lab.details(second.run_id, "run-started") == [
        {"resumes": run_id, "first_page": 2}
    ]
    assert same_json(lab.run_row(second.run_id)[2], lab.run_row(run_id)[2])
    assert sorted(elsewhere.iterdir()) == []
    assert f"observations/{second.run_id}/1.json" in lab.files(root / "data" / "raw")


# === cli_ (AC14, AC8, AC9) =====================================================


def test_cli_main_runs_the_command_and_ends_through_systemexit(
    migrated_lab: IngestLab,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CLI-3: `main(["ingest", ...])` exits through `SystemExit` with the code."""
    lab = migrated_lab

    result = lab.run_main(scope(1, 2), monkeypatch=monkeypatch, capsys=capsys)

    run_id = result.run_id
    assert result.code == 0
    assert result.out == f"{run_id} succeeded\n"
    assert lab.run_row(run_id)[0] == "succeeded"
    assert lab.pages.requests == [1, 2]


def test_cli_main_a_failed_run_exits_1_with_its_id_on_stdout(
    migrated_lab: IngestLab,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC4, AC15: exit 1, one line `<A> failed`, and no secret on stderr."""
    lab = migrated_lab
    lab.pages.reply(2, lab.reply(status=500, body=b""))

    result = lab.run_main(scope(1, 3), monkeypatch=monkeypatch, capsys=capsys)

    assert result.code == 1
    assert result.out == f"{result.run_id} failed\n"
    assert_no_setting_leaked(lab, result.err, result.out)
    assert "://" not in result.err
    assert "Traceback" not in result.err


INVALID_COMMANDS = [
    pytest.param(["--year", "2025", "--buyer", BUYER], id="no-last-page"),
    pytest.param(scope(0, 1), id="first-page-0"),
    pytest.param(
        ["--year", "2025", "--buyer", BUYER, "--last-page", "1", "--first-page", "2"],
        id="first-page-after-last-page",
    ),
    pytest.param(
        ["--year", "abc", "--buyer", BUYER, "--last-page", "1"], id="year-abc"
    ),
    pytest.param(["--year", "2025", "--buyer", "", "--last-page", "1"], id="no-buyer"),
    pytest.param([*scope(1, 2), "--raw-root", "somewhere"], id="raw-root"),
    pytest.param(["--resume", "Synthetic_Id"], id="resume-bad-id"),
    pytest.param(
        ["--resume", "ingest-20261016t100000z-aaaaaaaa", "--year", "2025"],
        id="resume-with-year",
    ),
]


@pytest.mark.parametrize("argv", INVALID_COMMANDS)
def test_cli_invalid_arguments_exit_2_before_the_database_is_touched(
    empty_lab: IngestLab, argv: list[str]
) -> None:
    """AC14: exit 2 with nothing requested, stored or applied (no connection)."""
    lab = empty_lab

    result = lab.run(argv)

    assert result.code == 2
    assert result.out == ""
    assert "usage" in result.err.lower()
    assert lab.calls == []
    assert lab.opens == 0
    assert lab.pages.requests == []
    assert lab.files() == {}
    assert not lab.table_exists("schema_migration")
    assert not lab.table_exists("ingestion_run")


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        pytest.param("POSTGRES_DB", None, id="no-database"),
        pytest.param("POSTGRES_USER", None, id="no-user"),
        pytest.param("POSTGRES_PASSWORD", None, id="no-password"),
        pytest.param("POSTGRES_PORT", "abc", id="port-abc"),
        pytest.param("POSTGRES_PORT", "70000", id="port-70000"),
    ],
)
def test_cli_invalid_environment_exits_2_before_the_database_is_touched(
    empty_lab: IngestLab, variable: str, value: str | None
) -> None:
    """AC14: a missing or invalid variable -> exit 2, naming it, never its value."""
    lab = empty_lab
    environ = lab.environ()
    if value is None:
        del environ[variable]
    else:
        environ[variable] = value

    result = lab.run(scope(1, 2), environ=environ)

    assert result.code == 2
    assert result.out == ""
    assert variable in result.err or (
        variable == "POSTGRES_PORT" and "port" in result.err
    )
    assert value is None or value not in result.err
    assert_no_setting_leaked(lab, result.err)
    assert lab.calls == []
    assert lab.pages.requests == []
    assert not lab.table_exists("schema_migration")
    assert not lab.table_exists("ingestion_run")


def test_cli_an_unreachable_database_exits_1_and_starts_nothing(
    migrated_lab: IngestLab,
) -> None:
    """Exit table: the database refuses connections -> `NOT_STARTED`, exit 1."""
    lab = migrated_lab
    lab.refuse_connections()

    result = lab.run(scope(1, 2))
    lab.allow_connections()

    assert result.code == 1
    assert result.out == ""
    assert result.err.strip() != ""
    assert_no_setting_leaked(lab, result.err)
    assert lab.run_ids() == []
    assert lab.pages.requests == []
    assert lab.files() == {}


def test_cli_the_exclusion_held_elsewhere_exits_1_and_creates_no_run(
    migrated_lab: IngestLab,
) -> None:
    """AC9, AC10: another ingest is active -> exit 1, stdout empty, nothing written."""
    lab = migrated_lab
    lab.hold(INGEST_EXCLUSION_KEY)

    result = lab.run(scope(1, 2))

    assert result.code == 1
    assert result.out == ""
    assert result.err.strip() != ""
    assert lab.run_ids() == []
    assert lab.counts()["audit_event"] == 0
    assert lab.pages.requests == []
    assert lab.files() == {}
