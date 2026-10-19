"""Feature ingest-command (F4), outcome O6b: PostgreSQL lost during a run (AC8).

The command runs through `run_ingest_command` with the simulated source, the real
store on `tmp_path` and a real throwaway database. The faults are the seams of the
plan's table:

- `connection_loss` (AC8): the adapter's server session is ended with
  `pg_terminate_backend` through the admin connection while page 2 is requested;
  then the new connection works (a), is refused with `ALLOW_CONNECTIONS false`
  (b), or opens while a test session holds the ingest exclusion (c);
- `final_finish` (AC8, decision P-2): the connection is lost around the final
  `finish_run(succeeded)`, through `KillBeforeFinishRepository` (nothing was
  written) and `KillAfterFinishRepository` (the commit happened, the reply was
  lost); the recovery may be refused the same two ways.

Data is synthetic. The real commit-in-flight loss is not deterministic (persistence
U1) and is not tested here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from ec_procurement_quality.infrastructure.postgres_ingestion_repository import (
    INGEST_EXCLUSION_KEY,
)

if TYPE_CHECKING:
    from tests.integration.ingest.conftest import IngestLab

pytestmark = pytest.mark.integration

BUYER = "SYNTHETIC BUYER S.A."


def scope(first: int = 1, last: int = 2) -> list[str]:
    return [
        "--year",
        "2025",
        "--buyer",
        BUYER,
        "--first-page",
        str(first),
        "--last-page",
        str(last),
    ]


# === connection_loss (AC8) =====================================================


def test_connection_loss_when_the_new_connection_works_the_run_closes_failed(
    migrated_lab: IngestLab,
) -> None:
    """AC8 a: `storage-failed` (page 2, `postgresql`), `failed`, exit 1."""
    lab = migrated_lab
    lab.on_request(2, lab.terminate_backends)

    result = lab.run(scope(1, 3))

    run_id = result.run_id
    assert result.code == 1
    assert result.out == f"{run_id} failed\n"
    assert lab.opens == 2
    assert lab.pages.requests == [1, 2]
    assert lab.run_row(run_id)[0] == "failed"
    assert lab.event_types(run_id) == [
        "run-started",
        "page-completed",
        "storage-failed",
    ]
    assert lab.details(run_id, "storage-failed") == [
        {"page": 2, "sequence": 2, "store": "postgresql"}
    ]
    # The lost write was repeated with the same values, and nothing was removed.
    assert [row[0] for row in lab.observation_rows(run_id)] == [1, 2]
    assert lab.local_sequences(run_id) == (1, 2)


def test_connection_loss_when_new_connections_are_refused_the_run_stays_running(
    migrated_lab: IngestLab,
) -> None:
    """AC8 b: no second attempt, `running`, exit 1, stdout `<A> running`, store intact."""
    lab = migrated_lab

    def kill_and_refuse() -> None:
        lab.terminate_backends()
        lab.refuse_connections()

    lab.on_request(2, kill_and_refuse)

    result = lab.run(scope(1, 3))
    lab.allow_connections()

    run_id = result.run_id
    assert result.code == 1
    assert result.out == f"{run_id} running\n"
    assert lab.opens == 2  # the first connection and the one refused attempt
    assert lab.pages.requests == [1, 2]
    assert lab.run_row(run_id)[0] == "running"
    assert lab.event_types(run_id) == ["run-started", "page-completed"]
    assert lab.local_sequences(run_id) == (1, 2)
    assert [row[0] for row in lab.observation_rows(run_id)] == [1]


def test_connection_loss_with_the_exclusion_held_elsewhere_leaves_the_run_untouched(
    migrated_lab: IngestLab,
) -> None:
    """AC8 c: the new connection opens, the exclusion is taken: no event, no finish."""
    lab = migrated_lab

    def kill_then_hold() -> None:
        lab.terminate_backends()
        lab.hold(INGEST_EXCLUSION_KEY)

    lab.on_request(2, kill_then_hold)

    result = lab.run(scope(1, 3))

    run_id = result.run_id
    assert result.code == 1
    assert result.out == f"{run_id} running\n"
    assert lab.opens == 2
    assert lab.run_row(run_id)[0] == "running"
    assert lab.event_types(run_id) == ["run-started", "page-completed"]
    assert lab.local_sequences(run_id) == (1, 2)
    assert lab.pages.requests == [1, 2]


# === final_finish (AC8, decision P-2) ==========================================


def test_final_finish_killed_before_the_commit_is_confirmed_by_the_repeat(
    migrated_lab: IngestLab,
) -> None:
    """P-2: the session dies before `finish_run(succeeded)` -> the repeat finishes it."""
    lab = migrated_lab
    lab.kill_before_final_finish()

    result = lab.run(scope(1, 2))

    run_id = result.run_id
    status, finished_at, _ = lab.run_row(run_id)
    assert result.code == 0
    assert result.out == f"{run_id} succeeded\n"
    assert lab.opens == 2
    assert status == "succeeded"
    assert lab.wrapped[0].finish_calls[0][0].value == "succeeded"
    assert finished_at == lab.wrapped[0].finish_calls[0][1]
    assert lab.event_types(run_id) == [
        "run-started",
        "page-completed",
        "page-completed",
    ]


def test_final_finish_killed_after_the_commit_leaves_the_stored_row_unchanged(
    migrated_lab: IngestLab,
) -> None:
    """P-2: the commit happened, the reply was lost -> the repeat returns that row."""
    lab = migrated_lab
    lab.kill_after_final_finish()

    result = lab.run(scope(1, 2))

    run_id = result.run_id
    status, finished_at, _ = lab.run_row(run_id)
    committed = lab.wrapped[0].committed
    assert result.code == 0
    assert result.out == f"{run_id} succeeded\n"
    assert lab.opens == 2
    assert status == "succeeded"
    assert len(committed) == 1
    assert finished_at == committed[0].finished_at
    assert lab.event_types(run_id) == [
        "run-started",
        "page-completed",
        "page-completed",
    ]


def test_final_finish_with_the_recovery_refused_leaves_the_run_running(
    migrated_lab: IngestLab,
) -> None:
    """P-2: the session dies and new connections are refused -> exit 1, `running`."""
    lab = migrated_lab
    lab.kill_before_final_finish(on_killed=lab.refuse_connections)

    result = lab.run(scope(1, 2))
    lab.allow_connections()

    run_id = result.run_id
    assert result.code == 1
    assert result.out == f"{run_id} running\n"
    assert lab.opens == 2
    assert lab.run_row(run_id)[0] == "running"
    assert lab.event_types(run_id) == [
        "run-started",
        "page-completed",
        "page-completed",
    ]
    assert lab.local_sequences(run_id) == (1, 2)


def test_final_finish_with_the_exclusion_held_elsewhere_leaves_the_run_untouched(
    migrated_lab: IngestLab,
) -> None:
    """P-2: the exclusion cannot be taken again -> no repeat, `running`, exit 1."""
    lab = migrated_lab

    def hold_the_exclusion() -> None:
        lab.hold(INGEST_EXCLUSION_KEY)

    lab.kill_before_final_finish(on_killed=hold_the_exclusion)

    result = lab.run(scope(1, 2))

    run_id = result.run_id
    assert result.code == 1
    assert result.out == f"{run_id} running\n"
    assert lab.opens == 2
    assert lab.run_row(run_id)[0] == "running"
    assert lab.event_types(run_id) == [
        "run-started",
        "page-completed",
        "page-completed",
    ]
    assert len(lab.wrapped[0].finish_calls) == 1
