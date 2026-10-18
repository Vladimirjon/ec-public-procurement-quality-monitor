"""Feature ingest-command (F4), outcome O6b: the end-to-end rows through the command.

Every test calls `run_ingest_command` with an injected wiring (`IngestLab` of this
folder's `conftest.py`): the simulated source (`SercopSource` over
`httpx.MockTransport`, no pause), the real `LocalDiskRawEvidenceStore` on `tmp_path`,
the real PostgreSQL repository and migration runner on a throwaway database, and the
stepping clock. Assertions read the exit code, stdout, the files under the store root
and the stored rows by direct SQL.

Names to focus on, by `-k`: `e2e_success` (AC1), `e2e_repeat` (AC2), `e2e_failure`
(AC4, AC17), `e2e_resume` (AC9, AC11), `e2e_reconcile` (AC10), `e2e_last_page` (AC3,
decision P-3), `e2e_chain_last_page` (AC24, `last-page-reached`). Data is synthetic.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import TYPE_CHECKING

import httpx
import pytest

from ec_procurement_quality.domain.content_hash import ContentHash
from ec_procurement_quality.domain.ingestion_audit import same_json
from ec_procurement_quality.infrastructure.postgres_ingestion_repository import (
    INGEST_EXCLUSION_KEY,
)

if TYPE_CHECKING:
    from tests.integration.ingest.conftest import IngestLab, Reply

pytestmark = pytest.mark.integration

BASE_URL = "https://source.invalid/PLATAFORMA"
BUYER = "SYNTHETIC BUYER S.A."
YEAR = 2025
HTML_429 = b"<html><body>synthetic rate limit</body></html>"
SCOPE_1_TO_2 = {
    "scope_version": 1,
    "source": "sercop-search-ocds",
    "base_url": BASE_URL,
    "buyer": BUYER,
    "year": YEAR,
    "first_page": 1,
    "last_page": 2,
}


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


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def success(lab: IngestLab, first: int = 1, last: int = 2) -> str:
    """Run an ingest that must succeed; return the id of its run."""
    result = lab.run(scope(first, last))
    assert result.code == 0, result.err
    assert result.status == "succeeded"
    return result.run_id


# === e2e_success (AC1) =========================================================


def test_e2e_success_two_pages_end_succeeded_in_both_stores(
    migrated_lab: IngestLab,
) -> None:
    """AC1: two requests, two observations in both stores, events in order, exit 0."""
    lab = migrated_lab
    lab.pages.pages_reported = 3

    result = lab.run(scope(1, 2))

    run_id = result.run_id
    assert result.code == 0
    assert result.out == f"{run_id} succeeded\n"
    assert lab.pages.requests == [1, 2]
    # The test store: one object per distinct body and the two observation files.
    files = lab.files()
    assert f"observations/{run_id}/1.json" in files
    assert f"observations/{run_id}/2.json" in files
    assert len(lab.object_files()) == 2
    assert lab.local_sequences(run_id) == (1, 2)
    # PostgreSQL: the run, the evidence rows, the observations and the events.
    status, finished_at, stored_scope = lab.run_row(run_id)
    assert status == "succeeded"
    assert finished_at is not None
    assert finished_at.utcoffset() is not None
    assert same_json(stored_scope, SCOPE_1_TO_2)
    bodies = [lab.pages.body(1), lab.pages.body(2)]
    assert lab.evidence_rows() == sorted((digest(body), len(body)) for body in bodies)
    assert lab.observation_rows(run_id) == [
        (1, 200, digest(bodies[0])),
        (2, 200, digest(bodies[1])),
    ]
    for sequence in (1, 2):
        stored = lab.stored_observation(run_id, sequence)
        assert stored == lab.store.read_observation(run_id, sequence)
        assert f"page={sequence}" in stored.url
        assert stored.captured_at.utcoffset() is not None
    assert lab.events(run_id) == [
        ("run-started", {"resumes": None, "first_page": 1}),
        (
            "page-completed",
            {"page": 1, "sequence": 1, "content_hash": digest(bodies[0])},
        ),
        (
            "page-completed",
            {"page": 2, "sequence": 2, "content_hash": digest(bodies[1])},
        ),
    ]


def test_e2e_success_every_stored_time_comes_from_the_one_clock(
    migrated_lab: IngestLab,
) -> None:
    """AC12: `started_at`, `captured_at` and `finished_at` are on the wiring clock."""
    lab = migrated_lab

    run_id = success(lab)

    _, finished_at, _ = lab.run_row(run_id)
    started_at = lab.started_at(run_id)
    captured = [
        lab.stored_observation(run_id, sequence).captured_at for sequence in (1, 2)
    ]
    assert finished_at is not None
    assert started_at < min(captured) <= max(captured) < finished_at
    assert started_at.year == 2026
    assert lab.ids.drawn == [run_id]


# === e2e_repeat (AC2) ==========================================================


def test_e2e_repeat_a_second_run_adds_no_object_and_no_evidence_row(
    migrated_lab: IngestLab,
) -> None:
    """AC2: new run, same objects (bytes and mtimes), own observations and events."""
    lab = migrated_lab
    first = success(lab)
    objects = lab.object_files()
    evidence = lab.evidence_rows()
    first_events = lab.events(first)

    second = success(lab)

    assert second != first
    assert lab.object_files() == objects
    assert lab.evidence_rows() == evidence
    assert lab.counts()["observation"] == 4
    assert lab.counts()["ingestion_run"] == 2
    assert lab.local_sequences(second) == (1, 2)
    assert lab.event_types(second) == [
        "run-started",
        "page-completed",
        "page-completed",
    ]
    assert lab.events(first) == first_events
    status_first, _, _ = lab.run_row(first)
    status_second, _, _ = lab.run_row(second)
    assert (status_first, status_second) == ("succeeded", "succeeded")


def test_e2e_repeat_a_changed_page_adds_one_object_and_one_evidence_row(
    migrated_lab: IngestLab,
) -> None:
    """AC2: page 2 changes -> one more object and row; both runs still succeed."""
    lab = migrated_lab
    first = success(lab)
    lab.pages.reply(2, lab.reply(body=lab.pages.body(2, variant="-changed")))

    second = success(lab)

    assert len(lab.object_files()) == 3
    assert len(lab.evidence_rows()) == 3
    assert lab.counts()["observation"] == 4
    assert lab.run_row(first)[0] == "succeeded"
    assert lab.run_row(second)[0] == "succeeded"


# === e2e_failure (AC4, AC17) ===================================================


def _half_body(lab: IngestLab) -> bytes:
    body = lab.pages.body(2)
    return body[: len(body) // 2]


def _cut_body(lab: IngestLab) -> bytes:
    return lab.pages.body(2)[:100]


FAILURE_CASES = [
    pytest.param(
        lambda lab: lab.reply(status=429, body=HTML_429),
        lambda lab: HTML_429,
        "status",
        429,
        id="429-html",
    ),
    pytest.param(
        lambda lab: lab.reply(status=500, body=b""),
        lambda lab: b"",
        "status",
        500,
        id="500-empty",
    ),
    pytest.param(
        lambda lab: lab.reply(body=_half_body(lab)),
        _half_body,
        "incomplete",
        200,
        id="half-body",
    ),
    pytest.param(
        lambda lab: lab.reply(cut_after=100),
        _cut_body,
        "transport",
        200,
        id="cut-off-after-100-bytes",
    ),
]


@pytest.mark.parametrize(("make_reply", "received", "failure", "status"), FAILURE_CASES)
def test_e2e_failure_the_response_is_stored_first_then_the_failure_then_a_stop(
    migrated_lab: IngestLab,
    make_reply: Callable[[IngestLab], Reply],
    received: Callable[[IngestLab], bytes],
    failure: str,
    status: int,
) -> None:
    """AC4, AC17: page 2 fails after a response -> stored in both stores, exit 1."""
    lab = migrated_lab
    lab.pages.reply(2, make_reply(lab))

    result = lab.run(scope(1, 3))

    run_id = result.run_id
    expected = received(lab)
    assert result.code == 1
    assert result.out == f"{run_id} failed\n"
    assert lab.pages.requests == [1, 2]
    assert lab.pages.requests_for(2) == 1
    assert lab.run_row(run_id)[0] == "failed"
    assert lab.local_sequences(run_id) == (1, 2)
    assert lab.observation_rows(run_id)[1] == (2, status, digest(expected))
    assert (digest(expected), len(expected)) in lab.evidence_rows()
    stored = lab.store.read_observation(run_id, 2)
    assert stored.status == status
    assert stored.size == len(expected)
    assert lab.store.read_content(ContentHash(digest(expected))) == expected
    assert lab.events(run_id) == [
        ("run-started", {"resumes": None, "first_page": 1}),
        (
            "page-completed",
            {"page": 1, "sequence": 1, "content_hash": digest(lab.pages.body(1))},
        ),
        (
            "page-failed",
            {"page": 2, "sequence": 2, "failure": failure, "status": status},
        ),
    ]


def test_e2e_failure_without_a_response_records_an_event_and_no_sequence(
    migrated_lab: IngestLab,
) -> None:
    """AC5, AC17: a connect error before the status -> `page-failed`, no sequence 2."""
    lab = migrated_lab
    lab.pages.fail(
        2,
        lambda request: httpx.ConnectError(
            "synthetic connect failure", request=request
        ),
    )

    result = lab.run(scope(1, 3))

    run_id = result.run_id
    assert result.code == 1
    assert result.out == f"{run_id} failed\n"
    assert lab.pages.requests == [1, 2]
    assert lab.local_sequences(run_id) == (1,)
    assert [row[0] for row in lab.observation_rows(run_id)] == [1]
    assert lab.details(run_id, "page-failed") == [
        {"page": 2, "sequence": None, "failure": "transport", "status": None}
    ]


# === e2e_resume (AC9, AC11) ====================================================


def _failed_on_page_3(lab: IngestLab) -> str:
    """Run A over pages 1 to 4: pages 1 and 2 complete, page 3 answers 429."""
    lab.pages.reply(3, lab.reply(status=429, body=HTML_429))
    result = lab.run(scope(1, 4))
    assert result.code == 1
    assert result.status == "failed"
    return result.run_id


def test_e2e_resume_requests_only_the_pages_not_completed(
    migrated_lab: IngestLab,
) -> None:
    """AC9, AC11: B continues A's scope from page 3 and A gains nothing."""
    lab = migrated_lab
    first = _failed_on_page_3(lab)
    first_events = lab.events(first)
    first_sequences = lab.local_sequences(first)

    result = lab.run(["--resume", first])

    second = result.run_id
    assert result.code == 0
    assert result.out == f"{second} succeeded\n"
    assert second != first
    assert lab.pages.requests == [1, 2, 3, 3, 4]
    assert same_json(lab.run_row(second)[2], lab.run_row(first)[2])
    assert lab.events(second) == [
        ("run-started", {"resumes": first, "first_page": 3}),
        (
            "page-completed",
            {"page": 3, "sequence": 1, "content_hash": digest(lab.pages.body(3))},
        ),
        (
            "page-completed",
            {"page": 4, "sequence": 2, "content_hash": digest(lab.pages.body(4))},
        ),
    ]
    assert lab.local_sequences(second) == (1, 2)
    assert [row[0] for row in lab.observation_rows(second)] == [1, 2]
    # AC11: the link lives only in B; A is exactly as it was when it finished.
    assert lab.events(first) == first_events
    assert lab.local_sequences(first) == first_sequences
    assert lab.run_row(first)[0] == "failed"


def test_e2e_resume_of_a_resumption_requests_only_the_page_that_failed(
    migrated_lab: IngestLab,
) -> None:
    """AC9: B fails on page 4 -> `--resume B` requests page 4 only."""
    lab = migrated_lab
    first = _failed_on_page_3(lab)
    lab.pages.reply(4, lab.reply(status=500, body=b""))
    resumed = lab.run(["--resume", first])
    assert (resumed.code, resumed.status) == (1, "failed")
    second = resumed.run_id

    result = lab.run(["--resume", second])

    third = result.run_id
    assert result.code == 0
    assert result.out == f"{third} succeeded\n"
    assert lab.pages.requests == [1, 2, 3, 3, 4, 4]
    assert lab.details(third, "run-started") == [{"resumes": second, "first_page": 4}]
    assert lab.details(third, "page-completed") == [
        {"page": 4, "sequence": 1, "content_hash": digest(lab.pages.body(4))}
    ]


def test_e2e_resume_an_unknown_target_exits_2_and_writes_nothing(
    migrated_lab: IngestLab,
) -> None:
    """AC9, AC14: a well-formed id that names no run -> exit 2, nothing written."""
    lab = migrated_lab

    result = lab.run(["--resume", lab.ABSENT])

    assert result.code == 2
    assert result.out == ""
    assert lab.ABSENT in result.err
    assert lab.pages.requests == []
    assert lab.counts() == {
        "ingestion_run": 0,
        "raw_evidence": 0,
        "observation": 0,
        "audit_event": 0,
    }
    assert lab.files() == {}


def test_e2e_resume_a_succeeded_target_exits_2_and_writes_nothing(
    migrated_lab: IngestLab,
) -> None:
    """AC9, AC11, AC14: a `succeeded` run needs no resumption -> exit 2."""
    lab = migrated_lab
    finished = success(lab)
    counts = lab.counts()
    events = lab.events(finished)
    files = lab.files()

    result = lab.run(["--resume", finished])

    assert result.code == 2
    assert result.out == ""
    assert finished in result.err
    assert lab.counts() == counts
    assert lab.events(finished) == events
    assert lab.files() == files
    assert lab.pages.requests == [1, 2]


def test_e2e_resume_with_the_exclusion_held_elsewhere_exits_1_and_changes_nothing(
    migrated_lab: IngestLab,
) -> None:
    """AC9: another session holds the exclusion -> exit 1, stdout empty, no change."""
    lab = migrated_lab
    first = _failed_on_page_3(lab)
    counts = lab.counts()
    events = lab.events(first)
    files = lab.files()
    requests = list(lab.pages.requests)
    lab.hold(INGEST_EXCLUSION_KEY)

    result = lab.run(["--resume", first])

    assert result.code == 1
    assert result.out == ""
    assert lab.counts() == counts
    assert lab.events(first) == events
    assert lab.files() == files
    assert lab.pages.requests == requests


# === e2e_reconcile (AC10) ======================================================


def _crashed_run(lab: IngestLab) -> None:
    """Run A is `running`: PostgreSQL holds observations 1 and 2, the store 1 to 3."""
    with lab.seeding() as seed:
        seed.run(lab.A)
        seed.started(lab.A)
        seed.completed(lab.A, 1, 2)
        seed.page(lab.A, 3, 3, postgres=False, event=False)


def test_e2e_reconcile_a_crashed_run_is_closed_before_the_new_run_starts(
    migrated_lab: IngestLab,
) -> None:
    """AC10: the local-only observation is recorded, A is closed `failed`, B runs."""
    lab = migrated_lab
    _crashed_run(lab)
    assert lab.local_sequences(lab.A) == (1, 2, 3)
    assert [row[0] for row in lab.observation_rows(lab.A)] == [1, 2]

    result = lab.run(scope(1, 2))

    new_run = result.run_id
    assert result.code == 0
    assert result.out == f"{new_run} succeeded\n"
    assert new_run != lab.A
    assert [row[0] for row in lab.observation_rows(lab.A)] == [1, 2, 3]
    assert lab.events(lab.A)[-2:] == [
        ("observation-reconciled", {"sequence": 3}),
        ("run-closed-by-reconciliation", {"reconciled_observations": 1}),
    ]
    status, finished_at, _ = lab.run_row(lab.A)
    assert status == "failed"
    assert finished_at is not None
    assert finished_at < lab.started_at(new_run)
    assert lab.run_row(new_run)[0] == "succeeded"


def test_e2e_reconcile_with_the_exclusion_held_elsewhere_touches_nothing(
    migrated_lab: IngestLab,
) -> None:
    """AC10: a run whose process holds the exclusion is never touched: exit 1."""
    lab = migrated_lab
    _crashed_run(lab)
    events = lab.events(lab.A)
    counts = lab.counts()
    files = lab.files()
    lab.hold(INGEST_EXCLUSION_KEY)

    result = lab.run(scope(1, 2))

    assert result.code == 1
    assert result.out == ""
    assert lab.run_row(lab.A)[0] == "running"
    assert lab.events(lab.A) == events
    assert lab.run_ids() == [lab.A]
    assert lab.counts() == counts
    assert lab.files() == files
    assert lab.pages.requests == []


def _missing_local(lab: IngestLab) -> None:
    with lab.seeding() as seed:
        seed.run(lab.A)
        seed.started(lab.A)
        seed.page(lab.A, 1, 1)
        seed.page(lab.A, 2, 2, local=False)


def _sequence_gap(lab: IngestLab) -> None:
    with lab.seeding() as seed:
        seed.run(lab.A)
        seed.started(lab.A)
        seed.page(lab.A, 1, 1)
        seed.page(lab.A, 3, 3, postgres=False, event=False)


def _tampered_object(lab: IngestLab) -> None:
    with lab.seeding() as seed:
        seed.run(lab.A)
        seed.started(lab.A)
        seed.page(lab.A, 1, 1)
    name = digest(lab.pages.body(1))
    (lab.root / "objects" / name[:2] / name).write_bytes(b"synthetic tampering")


def _stray_file(lab: IngestLab) -> None:
    with lab.seeding() as seed:
        seed.run(lab.A)
        seed.started(lab.A)
        seed.page(lab.A, 1, 1)
    (lab.root / "observations" / lab.A / "x.json").write_text("{}", encoding="utf-8")


RECONCILE_PROBLEMS = [
    pytest.param(_missing_local, 2, "local-observation-missing", id="missing"),
    pytest.param(_sequence_gap, 2, "sequence-gap", id="gap"),
    pytest.param(_tampered_object, 1, "object-integrity", id="tampered-object"),
    pytest.param(_stray_file, None, "local-listing-failed", id="listing-failed"),
]


@pytest.mark.parametrize(("build", "sequence", "problem"), RECONCILE_PROBLEMS)
def test_e2e_reconcile_a_problem_closes_the_old_run_and_starts_no_new_one(
    migrated_lab: IngestLab,
    build: Callable[[IngestLab], None],
    sequence: int | None,
    problem: str,
) -> None:
    """AC10: `reconciliation-failed`, the old run `failed`, no new run, exit 1."""
    lab = migrated_lab
    build(lab)

    result = lab.run(scope(1, 2))

    assert result.code == 1
    assert result.out == ""
    assert lab.run_ids() == [lab.A]
    assert lab.run_row(lab.A)[0] == "failed"
    assert lab.details(lab.A, "reconciliation-failed") == [
        {"sequence": sequence, "problem": problem}
    ]
    assert lab.pages.requests == []


# === e2e_last_page (AC3, decision P-3) =========================================


def test_e2e_last_page_a_search_with_no_results_ends_with_the_event(
    migrated_lab: IngestLab,
) -> None:
    """AC3 (P-3): `total` 0, `pages` 0, scope 1 to 1 -> one request, the event."""
    lab = migrated_lab
    lab.pages.pages_reported = 0

    result = lab.run(scope(1, 1))

    run_id = result.run_id
    assert result.code == 0
    assert result.out == f"{run_id} succeeded\n"
    assert lab.pages.requests == [1]
    assert lab.event_types(run_id) == [
        "run-started",
        "page-completed",
        "last-page-reached",
    ]
    assert lab.details(run_id, "last-page-reached") == [{"page": 1, "pages": 0}]
    assert lab.run_row(run_id)[0] == "succeeded"


def test_e2e_last_page_no_page_above_the_reported_last_page_is_requested(
    migrated_lab: IngestLab,
) -> None:
    """AC3: scope 1 to 5 with `pages` 2 -> two requests, the event, `succeeded`."""
    lab = migrated_lab
    lab.pages.pages_reported = 2

    result = lab.run(scope(1, 5))

    run_id = result.run_id
    assert result.code == 0
    assert lab.pages.requests == [1, 2]
    assert lab.details(run_id, "last-page-reached") == [{"page": 2, "pages": 2}]
    assert lab.event_types(run_id)[-2:] == ["page-completed", "last-page-reached"]


# === e2e_chain_last_page (AC24, `last-page-reached`) ===========================


def _bool_page(lab: IngestLab) -> str:
    """A: pages 1 and 2 completed, then `{"page": True, "pages": 1}`."""
    with lab.seeding() as seed:
        seed.run(lab.A)
        seed.started(lab.A)
        seed.completed(lab.A, 1, 2)
        seed.last_page(lab.A, True, 1)
        seed.finish(lab.A)
    return lab.A


def _uncovered_pages(lab: IngestLab) -> str:
    """A: pages 1 and 4 completed, then the event for page 4; 2 and 3 are missing."""
    with lab.seeding() as seed:
        seed.run(lab.A)
        seed.started(lab.A)
        seed.page(lab.A, 1, 1)
        seed.page(lab.A, 4, 2)
        seed.last_page(lab.A, 4, 4)
        seed.finish(lab.A)
    return lab.A


@pytest.mark.parametrize(
    "build", [_bool_page, _uncovered_pages], ids=["bool-page", "coverage"]
)
def test_e2e_chain_last_page_an_invalid_event_makes_the_chain_malformed(
    migrated_lab: IngestLab, build: Callable[[IngestLab], str]
) -> None:
    """AC24: exit 1, no request, no new run, nothing added to any run."""
    lab = migrated_lab
    target = build(lab)
    counts = lab.counts()
    events = lab.events(target)
    files = lab.files()

    result = lab.run(["--resume", target])

    assert result.code == 1
    assert result.out == ""
    assert target in result.err
    assert lab.pages.requests == []
    assert lab.run_ids() == [target]
    assert lab.counts() == counts
    assert lab.events(target) == events
    assert lab.files() == files


def test_e2e_chain_last_page_a_valid_event_across_two_runs_requests_nothing(
    migrated_lab: IngestLab,
) -> None:
    """AC24 control: A completes 1 and 2, B completes 3 and 4 and the event (4, 4).

    B is left `running`, so reconciliation closes it first; the resumption then
    requests nothing, starts at `first_page` 5 and succeeds.
    """
    lab = migrated_lab
    with lab.seeding() as seed:
        seed.run(lab.A)
        seed.started(lab.A)
        seed.completed(lab.A, 1, 2)
        seed.event(
            lab.A,
            "page-failed",
            {"page": 3, "sequence": None, "failure": "transport", "status": None},
        )
        seed.finish(lab.A)
        seed.run(lab.B)
        seed.started(lab.B, resumes=lab.A, first_page=3)
        seed.completed(lab.B, 3, 4)
        seed.last_page(lab.B, 4, 4)

    result = lab.run(["--resume", lab.B])

    new_run = result.run_id
    assert result.code == 0
    assert result.out == f"{new_run} succeeded\n"
    assert lab.pages.requests == []
    assert lab.run_row(lab.B)[0] == "failed"
    assert lab.details(lab.B, "run-closed-by-reconciliation") == [
        {"reconciled_observations": 0}
    ]
    assert lab.events(new_run) == [
        ("run-started", {"resumes": lab.B, "first_page": 5}),
    ]
    assert lab.run_row(new_run)[0] == "succeeded"
