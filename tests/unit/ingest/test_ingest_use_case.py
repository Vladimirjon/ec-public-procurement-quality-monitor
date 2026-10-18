"""Feature ingest-command (F4), outcome O4: the unit tests of `run_ingest`.

The use case runs with in-memory doubles of every port (`conftest.py`): no
database, network or disk (the one `tmp_path` store is the AC6 (a) case, which the
plan asks for). Every test calls `run_ingest` and asserts on its `IngestOutcome`,
on what the doubles hold afterwards, and on the order of their writes. Nothing here
is about exit codes, stdout or stderr: those belong to the CLI tests (O6b).

Acceptance criteria covered (intent AC1 to AC13, AC17, AC24), by `-k` token:

- `success` (AC1, AC13), `repeat` (AC2);
- `last_page` (AC3), `last_page_p3` (AC3, decision P-3);
- `failure_with_response` (AC4), `failure_without_response` (AC5),
  `no_retry` (AC17);
- `storage` (AC6), `interrupt` (AC7), `unexpected` (AC15, Q11);
- `connection_loss` (AC8), `connection_loss_final_finish` (AC8, decision P-2);
- `resume` (AC9), `reconcile` (AC10), `closed_run` (AC11), `identity` (AC12);
- `chain` (AC24, decision P-4), `chain_last_page` (AC24, `last-page-reached`).

Data is synthetic: the source is `https://source.invalid/PLATAFORMA`, the buyer
`SYNTHETIC BUYER S.A.`, the year 2025, and page bodies report `pages` 9 unless a
test says another value. Runs `A`, `B`, `C` and `D` are the seeded runs of `Lab`.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import re
import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from ec_procurement_quality.application.ingest_use_case import (
    IngestEnd,
    IngestOutcome,
    IngestRequest,
    ResumeRequest,
    run_ingest,
)
from ec_procurement_quality.application.procurement_source import (
    ProcurementSource,
    SearchPage,
)
from ec_procurement_quality.application.raw_evidence_store import RawEvidenceStore
from ec_procurement_quality.domain.ingestion_audit import (
    AuditEvent,
    JsonValue,
    RunStatus,
    same_json,
)
from ec_procurement_quality.domain.ingestion_catalogue import (
    AuditEventType,
    EvidenceStoreName,
    PageFailure,
    ReconciliationProblem,
)
from ec_procurement_quality.domain.persistence_errors import (
    PersistenceError,
    PersistenceIntegrityError,
)
from ec_procurement_quality.domain.raw_evidence import EvidenceIntegrityError
from ec_procurement_quality.infrastructure.local_disk_raw_evidence_store import (
    LocalDiskRawEvidenceStore,
)

if TYPE_CHECKING:
    from tests.unit.ingest.conftest import (
        Lab,
        TransportScript,
        WireFailure,
        WireReply,
    )

Answer = Callable[["Lab"], "WireReply | WireFailure"]

BASE_URL = "https://source.invalid/PLATAFORMA"
BUYER = "SYNTHETIC BUYER S.A."
YEAR = 2025
BODY_MARKER = "synthetic-body-marker"
HEADER_MARKER = "synthetic-header-marker"
PASSWORD_MARKER = "synthetic-password-marker"
HTML_429 = b"<html><body>synthetic rate limit</body></html>"
FREE_ID = "ingest-20261017t150000z-0a1b2c3d"

# --- Helpers ----------------------------------------------------------------


def fresh(lab: Lab, first_page: int = 1, last_page: int = 2) -> IngestRequest:
    return IngestRequest(scope=lab.scope(first_page, last_page))


def resume(execution_id: str) -> ResumeRequest:
    return ResumeRequest(execution_id=execution_id)


def call(
    lab: Lab,
    request: IngestRequest | ResumeRequest,
    *,
    source: ProcurementSource | None = None,
    store: RawEvidenceStore | None = None,
) -> IngestOutcome:
    """Call the use case with the ports of `lab`, or with the ones given.

    A `KeyboardInterrupt` that escapes is turned into a failure: pytest would
    otherwise end the whole session at that test.
    """
    try:
        return call_propagating(lab, request, source=source, store=store)
    except KeyboardInterrupt as error:
        raise AssertionError("run_ingest let a KeyboardInterrupt escape") from error


def call_propagating(
    lab: Lab,
    request: IngestRequest | ResumeRequest,
    *,
    source: ProcurementSource | None = None,
    store: RawEvidenceStore | None = None,
) -> IngestOutcome:
    """The same call, with every exception left to the caller."""
    return run_ingest(
        request,
        source=lab.source if source is None else source,
        store=lab.store if store is None else store,
        open_repository=lab.opener,
        clock=lab.clock,
        execution_ids=lab.execution_ids,
        reporter=lab.reporter,
    )


def created(outcome: IngestOutcome) -> str:
    """The id of the run this call created (the call must have created one)."""
    assert outcome.execution_id is not None
    return outcome.execution_id


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def completed_detail(page: int, sequence: int, body: bytes) -> dict[str, JsonValue]:
    return {"page": page, "sequence": sequence, "content_hash": digest(body)}


def seed_run(
    lab: Lab,
    run_id: str,
    *,
    first: int = 1,
    last: int = 4,
    resumes: str | None = None,
    first_page: int | None = None,
    pages: tuple[int, ...] = (),
    status: RunStatus = RunStatus.FAILED,
) -> None:
    """A run that reached PostgreSQL: its `run-started` and the pages it completed.

    The sequences of the completed pages are 1, 2, ... in the order given.
    """
    lab.seed.run(run_id, scope=lab.scope(first, last), status=status)
    lab.seed.started(
        run_id,
        resumes=resumes,
        first_page=first if first_page is None else first_page,
    )
    lab.seed.completed(run_id, *pages)


def is_int(value: object) -> bool:
    return type(value) is int


def is_int_or_none(value: object) -> bool:
    return value is None or type(value) is int


def is_text(value: object) -> bool:
    return isinstance(value, str)


def one_of(values: type[enum.StrEnum]) -> Callable[..., bool]:
    allowed = {member.value for member in values}
    return lambda value: value in allowed


def is_reconciliation_problem(value: object) -> bool:
    return value in {member.value for member in ReconciliationProblem}


def is_content_hash(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def is_run_id_or_none(value: object) -> bool:
    return value is None or isinstance(value, str)


# The closed catalogue of intent Q6 and execution-plan § Audit details: the keys
# of each event type and the check of each value.
DETAIL_SHAPES: dict[str, dict[str, Callable[..., bool]]] = {
    "run-started": {"resumes": is_run_id_or_none, "first_page": is_int},
    "page-completed": {
        "page": is_int,
        "sequence": is_int,
        "content_hash": is_content_hash,
    },
    "page-failed": {
        "page": is_int,
        "sequence": is_int_or_none,
        "failure": one_of(PageFailure),
        "status": is_int_or_none,
    },
    "storage-failed": {
        "page": is_int,
        "sequence": is_int_or_none,
        "store": one_of(EvidenceStoreName),
    },
    "last-page-reached": {"page": is_int, "pages": is_int},
    "run-interrupted": {"page": is_int},
    "unexpected-error": {"page": is_int, "error_type": is_text},
    "observation-reconciled": {"sequence": is_int},
    "run-closed-by-reconciliation": {"reconciled_observations": is_int},
    "reconciliation-failed": {
        "sequence": is_int_or_none,
        "problem": is_reconciliation_problem,
    },
}
FORBIDDEN_TEXT = ("://", BODY_MARKER, HEADER_MARKER, PASSWORD_MARKER, "Traceback")


def assert_follows_catalogue(events: list[AuditEvent]) -> None:
    """Every event has a catalogue type and exactly its detail keys and values."""
    assert {member.value for member in AuditEventType} == set(DETAIL_SHAPES)
    for event in events:
        assert event.event_type in DETAIL_SHAPES, event.event_type
        shape = DETAIL_SHAPES[event.event_type]
        assert set(event.detail) == set(shape), event.event_type
        for key, check in shape.items():
            assert check(event.detail[key]), (event.event_type, key)
        for value in event.detail.values():
            if isinstance(value, str):
                assert not any(text in value for text in FORBIDDEN_TEXT)


def written(lab: Lab, kind: str) -> list[tuple[str, str, str]]:
    return [entry for entry in lab.journal.entries if entry[0] == kind]


def position(lab: Lab, operation: str, execution_id: str) -> int:
    """Where in the journal the first write of `operation` to a run is."""
    for index, entry in enumerate(lab.journal.entries):
        if entry[0] == operation and entry[1] == execution_id:
            return index
    raise AssertionError(f"no {operation} for {execution_id} in the journal")


def assert_not_started(outcome: IngestOutcome) -> None:
    assert outcome.end is IngestEnd.NOT_STARTED
    assert outcome.execution_id is None
    assert outcome.run_status is None


def two_pages(lab: Lab) -> tuple[IngestOutcome, str]:
    """The AC1 run: pages 1 and 2, each answering `pages` 3."""
    lab.source.script(1, lab.ok(1, pages=3))
    lab.source.script(2, lab.ok(2, pages=3))
    outcome = call(lab, fresh(lab, 1, 2))
    return outcome, created(outcome)


# === success (AC1, AC13) =====================================================


def test_success_requests_each_page_of_the_range_once_in_order(lab: Lab) -> None:
    """AC1: exactly two requests, for page 1 then page 2, for the scope's buyer."""
    two_pages(lab)

    assert lab.source.calls == [(YEAR, BUYER, 1), (YEAR, BUYER, 2)]
    assert lab.source.record_fetches == []


def test_success_ends_succeeded_with_the_run_this_call_created(lab: Lab) -> None:
    """AC1: outcome SUCCEEDED, the run `succeeded` with a finish time."""
    outcome, run_id = two_pages(lab)

    assert outcome.end is IngestEnd.SUCCEEDED
    assert outcome.run_status is RunStatus.SUCCEEDED
    assert run_id == lab.execution_ids.drawn[0]
    run = lab.database.runs[run_id]
    assert run.status is RunStatus.SUCCEEDED
    assert run.finished_at is not None


def test_success_keeps_each_response_equal_in_both_stores(lab: Lab) -> None:
    """AC1: observations 1 and 2 are in the store and in PostgreSQL, equal."""
    _, run_id = two_pages(lab)

    for sequence in (1, 2):
        body = lab.body(sequence, pages=3)
        stored = lab.store.read_observation(run_id, sequence)
        assert lab.database.observations[(run_id, sequence)] == stored
        assert stored.status == 200
        assert f"page={sequence}" in stored.url
        assert lab.store.read_content(stored.content_hash) == body
        assert lab.database.evidence[stored.content_hash] == len(body)
    assert lab.local_sequences(run_id) == (1, 2)
    assert lab.sequences(run_id) == (1, 2)


def test_success_stores_the_range_as_the_pinned_json_object(lab: Lab) -> None:
    """AC13: the scope has exactly the Q6 keys (compared with `same_json`)."""
    _, run_id = two_pages(lab)

    assert same_json(
        dict(lab.database.runs[run_id].scope),
        {
            "scope_version": 1,
            "source": "sercop-search-ocds",
            "base_url": BASE_URL,
            "buyer": BUYER,
            "year": YEAR,
            "first_page": 1,
            "last_page": 2,
        },
    )


def test_success_appends_the_pinned_events_in_order(lab: Lab) -> None:
    """AC1, AC13: run-started, then one page-completed per page, with their details."""
    _, run_id = two_pages(lab)

    events = lab.events(run_id)
    assert [event.event_type for event in events] == [
        "run-started",
        "page-completed",
        "page-completed",
    ]
    assert same_json(dict(events[0].detail), {"resumes": None, "first_page": 1})
    assert same_json(
        dict(events[1].detail), completed_detail(1, 1, lab.body(1, pages=3))
    )
    assert same_json(
        dict(events[2].detail), completed_detail(2, 2, lab.body(2, pages=3))
    )
    assert_follows_catalogue(events)


def test_success_writes_local_store_then_postgresql_then_event_then_close(
    lab: Lab,
) -> None:
    """AC1, AC4: the write order is the store, the observation, the page event."""
    _, run_id = two_pages(lab)

    assert lab.journal.labels(run_id) == [
        "start_run",
        "run_started",
        "append:run-started",
        "store:1",
        "record_observation:1",
        "append:page-completed",
        "store:2",
        "record_observation:2",
        "append:page-completed",
        "finish_run:succeeded",
    ]


def test_success_takes_the_exclusion_before_anything_is_written(lab: Lab) -> None:
    """AC10, AC12: the exclusion is the first write, before the run exists."""
    two_pages(lab)

    assert lab.journal.labels()[0] == "exclusion:taken"


def test_success_closes_the_repository_it_opened_and_frees_the_exclusion(
    lab: Lab,
) -> None:
    """AC18: one repository for the call, closed before the call returns."""
    two_pages(lab)

    assert lab.opener.opens == 1
    assert lab.opener.all_closed
    assert lab.database.exclusion_holder is None


def test_success_tells_the_reporter_the_run_id_once(lab: Lab) -> None:
    """The reporter learns the id before the outcome (AC7, AC15)."""
    _, run_id = two_pages(lab)

    assert lab.reporter.started == [run_id]


# === repeat (AC2) ============================================================


def test_repeat_creates_a_new_run_and_both_runs_succeed(lab: Lab) -> None:
    first = call(lab, fresh(lab, 1, 2))
    second = call(lab, fresh(lab, 1, 2))

    assert first.end is IngestEnd.SUCCEEDED
    assert second.end is IngestEnd.SUCCEEDED
    assert created(first) != created(second)


def test_repeat_keeps_one_object_and_one_evidence_row_per_content(lab: Lab) -> None:
    call(lab, fresh(lab, 1, 2))
    before = lab.snapshot()

    call(lab, fresh(lab, 1, 2))

    after = lab.snapshot()
    assert len(before.objects) == 2
    assert after.objects == before.objects
    assert after.evidence == before.evidence


def test_repeat_gives_each_run_its_own_observations_and_events(lab: Lab) -> None:
    first_id = created(call(lab, fresh(lab, 1, 2)))
    first_state = lab.database.run_state(first_id)

    second_id = created(call(lab, fresh(lab, 1, 2)))

    assert lab.database.run_state(first_id) == first_state
    assert lab.sequences(first_id) == (1, 2)
    assert lab.sequences(second_id) == (1, 2)
    assert lab.local_sequences(second_id) == (1, 2)
    assert lab.event_types(second_id) == [
        "run-started",
        "page-completed",
        "page-completed",
    ]
    assert len(lab.database.observations) == 4


def test_repeat_with_a_changed_page_adds_one_object_and_one_row(lab: Lab) -> None:
    first = call(lab, fresh(lab, 1, 2))
    before = lab.snapshot()
    lab.source.script(2, lab.ok(2, variant="-changed"))

    second = call(lab, fresh(lab, 1, 2))

    after = lab.snapshot()
    assert first.end is IngestEnd.SUCCEEDED
    assert second.end is IngestEnd.SUCCEEDED
    assert len(after.objects - before.objects) == 1
    assert len(after.evidence - before.evidence) == 1


# === last_page (AC3) =========================================================


def test_last_page_the_reported_last_page_ends_the_run_without_a_failure(
    lab: Lab,
) -> None:
    """AC3: scope 1 to 5, the source reports 2 pages -> two requests, succeeded."""
    lab.source.script(1, lab.ok(1, pages=2))
    lab.source.script(2, lab.ok(2, pages=2))

    outcome = call(lab, fresh(lab, 1, 5))

    run_id = created(outcome)
    assert outcome.end is IngestEnd.SUCCEEDED
    assert outcome.run_status is RunStatus.SUCCEEDED
    assert lab.source.requests == [1, 2]
    assert lab.event_types(run_id) == [
        "run-started",
        "page-completed",
        "page-completed",
        "last-page-reached",
    ]
    assert same_json(
        lab.details(run_id, "last-page-reached")[0], {"page": 2, "pages": 2}
    )


def test_last_page_a_beyond_result_is_stored_and_recorded_as_completed(
    lab: Lab,
) -> None:
    """AC3: scope 4 to 5 and `pages` 2 -> one request, kept, completed, reached."""
    lab.source.script(4, lab.ok(4, pages=2))

    outcome = call(lab, fresh(lab, 4, 5))

    run_id = created(outcome)
    body = lab.body(4, pages=2)
    assert outcome.end is IngestEnd.SUCCEEDED
    assert lab.source.requests == [4]
    assert lab.sequences(run_id) == (1,)
    assert lab.local_sequences(run_id) == (1,)
    assert same_json(
        lab.details(run_id, "page-completed")[0], completed_detail(4, 1, body)
    )
    assert same_json(
        lab.details(run_id, "last-page-reached")[0], {"page": 4, "pages": 2}
    )


# === last_page_p3 (AC3, decision P-3) ========================================


def test_last_page_p3_a_search_with_no_results_reaches_its_last_page(lab: Lab) -> None:
    """P-3: `pages` 0 with scope 1 to 1 -> one request, completed, reached."""
    lab.source.script(1, lab.ok(1, pages=0, total=0))

    outcome = call(lab, fresh(lab, 1, 1))

    run_id = created(outcome)
    assert outcome.end is IngestEnd.SUCCEEDED
    assert outcome.run_status is RunStatus.SUCCEEDED
    assert lab.source.requests == [1]
    assert lab.event_types(run_id) == [
        "run-started",
        "page-completed",
        "last-page-reached",
    ]
    assert same_json(
        lab.details(run_id, "page-completed")[0],
        completed_detail(1, 1, lab.body(1, pages=0, total=0)),
    )
    assert same_json(
        lab.details(run_id, "last-page-reached")[0], {"page": 1, "pages": 0}
    )


def test_last_page_p3_the_reported_last_page_equal_to_the_requested_one_still_reaches_it(
    lab: Lab,
) -> None:
    """P-3: scope 1 to 2 with `pages` 2 -> two requests, the event, no third."""
    lab.source.script(1, lab.ok(1, pages=2))
    lab.source.script(2, lab.ok(2, pages=2))

    outcome = call(lab, fresh(lab, 1, 2))

    run_id = created(outcome)
    assert outcome.end is IngestEnd.SUCCEEDED
    assert lab.source.requests == [1, 2]
    assert same_json(
        lab.details(run_id, "last-page-reached")[0], {"page": 2, "pages": 2}
    )


def test_last_page_p3_more_pages_reported_than_requested_end_without_the_event(
    lab: Lab,
) -> None:
    """P-3: scope 1 to 2 with `pages` 3 (AC1) -> no `last-page-reached`."""
    lab.source.script(1, lab.ok(1, pages=3))
    lab.source.script(2, lab.ok(2, pages=3))

    outcome = call(lab, fresh(lab, 1, 2))

    assert outcome.end is IngestEnd.SUCCEEDED
    assert "last-page-reached" not in lab.event_types(created(outcome))


def test_last_page_p3_a_beyond_result_is_requested_exactly_once(lab: Lab) -> None:
    """P-3, AC17: scope 4 to 5, `pages` 2 -> no page twice, none after the event."""
    lab.source.script(4, lab.ok(4, pages=2))

    call(lab, fresh(lab, 4, 5))

    assert lab.source.requests == [4]


def test_last_page_p3_writes_completed_then_reached_then_close(lab: Lab) -> None:
    """P-3: `page-completed`, then `last-page-reached` for the same page, then close."""
    lab.source.script(1, lab.ok(1, pages=1))

    outcome = call(lab, fresh(lab, 1, 3))

    assert lab.journal.labels(created(outcome))[-3:] == [
        "append:page-completed",
        "append:last-page-reached",
        "finish_run:succeeded",
    ]


def test_last_page_p3_a_resumption_requests_no_page_above_a_recorded_event(
    lab: Lab,
) -> None:
    """P-3, AC9: a chain with a valid `last-page-reached` leaves nothing to request."""
    seed_run(lab, lab.A, last=5, pages=(1, 2))
    lab.seed.last_page(lab.A, 2, 2)
    lab.seed.event(
        lab.A, "storage-failed", {"page": 2, "sequence": None, "store": "postgresql"}
    )

    outcome = call(lab, resume(lab.A))

    assert outcome.end is IngestEnd.SUCCEEDED
    assert lab.source.requests == []
    assert same_json(
        lab.details(created(outcome), "run-started")[0],
        {"resumes": lab.A, "first_page": 6},
    )


# === failure_with_response (AC4), failure_without_response (AC5), no_retry (AC17)


# (the answer for page 2, the failure kind, the status, the bytes received)
RESPONSE_CASES = [
    pytest.param(
        lambda lab: lab.reply(status=429, body=HTML_429),
        "status",
        429,
        lambda lab: HTML_429,
        id="429-html",
    ),
    pytest.param(
        lambda lab: lab.reply(status=500),
        "status",
        500,
        lambda lab: b"",
        id="500-empty",
    ),
    pytest.param(
        lambda lab: lab.reply(body=lab.body(2)[: len(lab.body(2)) // 2]),
        "incomplete",
        200,
        lambda lab: lab.body(2)[: len(lab.body(2)) // 2],
        id="half-body",
    ),
    pytest.param(
        lambda lab: lab.reply(body=lab.body(2), cut_after=100),
        "transport",
        200,
        lambda lab: lab.body(2)[:100],
        id="cut-off-after-100-bytes",
    ),
]
NO_RESPONSE_CASES = [
    pytest.param(lambda lab: lab.connect_error(), id="connect-error"),
    pytest.param(lambda lab: lab.reply(status=600), id="status-600"),
]
EVERY_FAILING_ANSWER = [
    pytest.param(case.values[0], id=case.id) for case in RESPONSE_CASES
] + [pytest.param(case.values[0], id=case.id) for case in NO_RESPONSE_CASES]


def fail_page_two(lab: Lab, answer: Answer) -> tuple[IngestOutcome, TransportScript]:
    """Scope 1 to 3 through `SercopSource`; page 2 gets the failing `answer`."""
    script = lab.transport()
    script.script(2, answer(lab))
    outcome = call(lab, fresh(lab, 1, 3), source=lab.sercop(script))
    return outcome, script


@pytest.mark.parametrize(("answer", "failure", "status", "received"), RESPONSE_CASES)
def test_failure_with_response_keeps_the_exact_bytes_in_both_stores(
    lab: Lab,
    answer: Answer,
    failure: str,
    status: int,
    received: Callable[..., bytes],
) -> None:
    """AC4: the response is stored as received, whatever its status."""
    outcome, _ = fail_page_two(lab, answer)

    run_id = created(outcome)
    expected = received(lab)
    stored = lab.store.read_observation(run_id, 2)
    assert stored.status == status
    assert stored.size == len(expected)
    assert lab.store.read_content(stored.content_hash) == expected
    assert lab.database.observations[(run_id, 2)] == stored


@pytest.mark.parametrize(("answer", "failure", "status", "received"), RESPONSE_CASES)
def test_failure_with_response_records_page_failed_with_the_failure_kind(
    lab: Lab,
    answer: Answer,
    failure: str,
    status: int,
    received: Callable[..., bytes],
) -> None:
    """AC4, AC13: `page-failed` (page, sequence, failure kind, status)."""
    outcome, _ = fail_page_two(lab, answer)

    run_id = created(outcome)
    events = lab.events(run_id)
    assert [event.event_type for event in events] == [
        "run-started",
        "page-completed",
        "page-failed",
    ]
    assert same_json(
        dict(events[2].detail),
        {"page": 2, "sequence": 2, "failure": failure, "status": status},
    )
    assert_follows_catalogue(events)


@pytest.mark.parametrize(("answer", "failure", "status", "received"), RESPONSE_CASES)
def test_failure_with_response_writes_store_then_postgresql_then_event_then_close(
    lab: Lab,
    answer: Answer,
    failure: str,
    status: int,
    received: Callable[..., bytes],
) -> None:
    """AC4: the order is the local store, the observation, the event, the close."""
    outcome, _ = fail_page_two(lab, answer)

    assert lab.journal.labels(created(outcome))[-4:] == [
        "store:2",
        "record_observation:2",
        "append:page-failed",
        "finish_run:failed",
    ]


@pytest.mark.parametrize(("answer", "failure", "status", "received"), RESPONSE_CASES)
def test_failure_with_response_ends_failed_and_requests_no_later_page(
    lab: Lab,
    answer: Answer,
    failure: str,
    status: int,
    received: Callable[..., bytes],
) -> None:
    """AC4: the run is `failed` and page 3 is never requested."""
    outcome, script = fail_page_two(lab, answer)

    assert outcome.end is IngestEnd.RUN_FAILED
    assert outcome.run_status is RunStatus.FAILED
    assert lab.database.runs[created(outcome)].status is RunStatus.FAILED
    assert script.requests_for(3) == 0


@pytest.mark.parametrize("answer", [case.values[0] for case in NO_RESPONSE_CASES])
def test_failure_without_response_records_page_failed_with_no_sequence(
    lab: Lab, answer: Answer
) -> None:
    """AC5: `page-failed` (page 2, sequence None, transport, status None)."""
    outcome, _ = fail_page_two(lab, answer)

    run_id = created(outcome)
    events = lab.events(run_id)
    assert [event.event_type for event in events] == [
        "run-started",
        "page-completed",
        "page-failed",
    ]
    assert same_json(
        dict(events[2].detail),
        {"page": 2, "sequence": None, "failure": "transport", "status": None},
    )
    assert_follows_catalogue(events)


@pytest.mark.parametrize("answer", [case.values[0] for case in NO_RESPONSE_CASES])
def test_failure_without_response_keeps_no_observation_and_uses_no_sequence(
    lab: Lab, answer: Answer
) -> None:
    """AC5: only page 1's observation exists, in both stores."""
    outcome, _ = fail_page_two(lab, answer)

    run_id = created(outcome)
    assert lab.sequences(run_id) == (1,)
    assert lab.local_sequences(run_id) == (1,)
    assert lab.journal.labels(run_id)[-2:] == [
        "append:page-failed",
        "finish_run:failed",
    ]


@pytest.mark.parametrize("answer", [case.values[0] for case in NO_RESPONSE_CASES])
def test_failure_without_response_ends_failed_and_requests_no_later_page(
    lab: Lab, answer: Answer
) -> None:
    outcome, script = fail_page_two(lab, answer)

    assert outcome.end is IngestEnd.RUN_FAILED
    assert outcome.run_status is RunStatus.FAILED
    assert script.requests_for(3) == 0


@pytest.mark.parametrize("answer", EVERY_FAILING_ANSWER)
def test_no_retry_page_two_is_requested_once_by_the_run(
    lab: Lab, answer: Answer
) -> None:
    """AC17: the transport sees exactly one request for the failing page."""
    _, script = fail_page_two(lab, answer)

    assert script.requests_for(1) == 1
    assert script.requests_for(2) == 1
    assert script.requests_for(3) == 0


# === storage (AC6) ===========================================================


def test_storage_a_regular_file_at_observations_stops_the_run(
    lab: Lab, tmp_path: Path
) -> None:
    """AC6 (a): `store` raises `OSError` for page 2 and nothing was written.

    Page 1 is stored first; the page 2 request replaces the `observations`
    folder with a regular file, so storing sequence 2 fails (RE-9).
    """
    root = tmp_path / "evidence"
    blocker = root / "observations"

    def block_the_observations() -> SearchPage:
        shutil.rmtree(blocker)
        blocker.write_bytes(b"synthetic blocker")
        return lab.ok(2)()

    lab.source.script(2, block_the_observations)

    outcome = call(lab, fresh(lab, 1, 3), store=LocalDiskRawEvidenceStore(root))

    run_id = created(outcome)
    assert outcome.end is IngestEnd.RUN_FAILED
    assert outcome.run_status is RunStatus.FAILED
    assert blocker.read_bytes() == b"synthetic blocker"
    assert lab.sequences(run_id) == (1,)
    assert lab.event_types(run_id) == [
        "run-started",
        "page-completed",
        "storage-failed",
    ]
    assert same_json(
        lab.details(run_id, "storage-failed")[0],
        {"page": 2, "sequence": 2, "store": "raw-evidence"},
    )
    assert lab.source.requests == [1, 2]


def test_storage_an_observation_published_before_the_error_is_recorded_first(
    lab: Lab,
) -> None:
    """AC6 (b): `OSError` after publication -> read it back, record it, then close."""
    store = lab.publishes_then_fails(on_call=2)

    outcome = call(lab, fresh(lab, 1, 3), store=store)

    run_id = created(outcome)
    assert outcome.end is IngestEnd.RUN_FAILED
    assert outcome.run_status is RunStatus.FAILED
    assert lab.sequences(run_id) == (1, 2)
    assert lab.database.observations[(run_id, 2)] == lab.store.read_observation(
        run_id, 2
    )
    assert lab.journal.labels(run_id)[-4:] == [
        "store:2",
        "record_observation:2",
        "append:storage-failed",
        "finish_run:failed",
    ]
    assert same_json(
        lab.details(run_id, "storage-failed")[0],
        {"page": 2, "sequence": 2, "store": "raw-evidence"},
    )
    assert lab.source.requests == [1, 2]


@pytest.mark.parametrize("error", [OSError, EvidenceIntegrityError])
def test_storage_a_write_refused_before_publication_records_only_the_failure(
    lab: Lab, error: Callable[[str], BaseException]
) -> None:
    """AC6: nothing published -> nothing to record; the failure names the sequence."""
    store = lab.refuses_to_store(on_call=2, error=lambda: error("synthetic refusal"))

    outcome = call(lab, fresh(lab, 1, 3), store=store)

    run_id = created(outcome)
    assert outcome.end is IngestEnd.RUN_FAILED
    assert lab.sequences(run_id) == (1,)
    assert lab.local_sequences(run_id) == (1,)
    assert lab.journal.labels(run_id)[-2:] == [
        "append:storage-failed",
        "finish_run:failed",
    ]
    assert same_json(
        lab.details(run_id, "storage-failed")[0],
        {"page": 2, "sequence": 2, "store": "raw-evidence"},
    )
    assert lab.source.requests == [1, 2]


@pytest.mark.parametrize("error", [OSError, EvidenceIntegrityError])
def test_storage_a_failed_read_back_counts_the_observation_as_not_recorded(
    lab: Lab, error: Callable[[str], BaseException]
) -> None:
    """AC6 (d): `store` raises `OSError`, then the read-back itself fails."""
    store = lab.fails_read_back(
        on_call=2, read_errors=[lambda: error("synthetic read-back failure")]
    )

    outcome = call(lab, fresh(lab, 1, 3), store=store)

    run_id = created(outcome)
    assert outcome.end is IngestEnd.RUN_FAILED
    assert outcome.run_status is RunStatus.FAILED
    assert lab.database.runs[run_id].status is RunStatus.FAILED
    assert lab.event_types(run_id) == [
        "run-started",
        "page-completed",
        "storage-failed",
    ]
    assert same_json(
        lab.details(run_id, "storage-failed")[0],
        {"page": 2, "sequence": 2, "store": "raw-evidence"},
    )
    assert lab.sequences(run_id) == (1,)
    assert (run_id, 2) not in lab.database.observations
    assert lab.journal.labels(run_id)[-2:] == [
        "append:storage-failed",
        "finish_run:failed",
    ]
    assert lab.source.requests == [1, 2]
    assert lab.opener.all_closed


def test_storage_an_interrupt_from_the_read_back_keeps_the_interrupt_handling(
    lab: Lab,
) -> None:
    """AC6 (d), State machine K: the rule does not catch a `KeyboardInterrupt`.

    The first read-back is interrupted; the cleanup reads the published
    observation back, records it, and closes the run as an interruption.
    """
    store = lab.fails_read_back(
        on_call=2, read_errors=[lambda: KeyboardInterrupt()], publish=True
    )

    outcome = call(lab, fresh(lab, 1, 3), store=store)

    run_id = created(outcome)
    assert outcome.end is IngestEnd.INTERRUPTED
    assert outcome.run_status is RunStatus.FAILED
    assert lab.event_types(run_id) == [
        "run-started",
        "page-completed",
        "run-interrupted",
    ]
    assert same_json(lab.details(run_id, "run-interrupted")[0], {"page": 2})
    assert lab.sequences(run_id) == (1, 2)
    assert lab.source.requests == [1, 2]


@pytest.mark.parametrize("error", [PersistenceIntegrityError, PersistenceError])
def test_storage_postgresql_refusing_an_observation_stops_the_run(
    lab: Lab, error: Callable[[str], PersistenceError]
) -> None:
    """AC6 (c): `record_observation` refused -> `storage-failed` (postgresql)."""
    lab.opener.faults[1] = [
        lab.faults.refuses(
            "record_observation", lambda: error("synthetic refusal"), detail="1"
        )
    ]

    outcome = call(lab, fresh(lab, 1, 3))

    run_id = created(outcome)
    assert outcome.end is IngestEnd.RUN_FAILED
    assert outcome.run_status is RunStatus.FAILED
    assert lab.event_types(run_id) == ["run-started", "storage-failed"]
    assert same_json(
        lab.details(run_id, "storage-failed")[0],
        {"page": 1, "sequence": 1, "store": "postgresql"},
    )
    assert lab.source.requests == [1]
    assert lab.local_sequences(run_id) == (1,)
    assert lab.sequences(run_id) == ()
    assert_follows_catalogue(lab.events(run_id))


def test_storage_progress_text_holds_no_url_body_or_header_value(lab: Lab) -> None:
    """AC6 (c), AC15: a refusal is reported by operation and identity only."""
    lab.opener.faults[1] = [
        lab.faults.refuses(
            "record_observation",
            lambda: PersistenceIntegrityError("record_observation x/1: refused"),
            detail="1",
        )
    ]

    call(lab, fresh(lab, 1, 3))

    for message in lab.reporter.messages:
        assert not any(text in message for text in FORBIDDEN_TEXT)


# === interrupt (AC7) =========================================================


def test_interrupt_while_a_page_is_requested_closes_the_run_failed(lab: Lab) -> None:
    """AC7: page 1 stays completed; `run-interrupted` (page 2); `failed`."""
    lab.source.script(2, KeyboardInterrupt())

    outcome = call(lab, fresh(lab, 1, 3))

    run_id = created(outcome)
    assert outcome.end is IngestEnd.INTERRUPTED
    assert outcome.run_status is RunStatus.FAILED
    assert lab.database.runs[run_id].status is RunStatus.FAILED
    assert lab.event_types(run_id) == [
        "run-started",
        "page-completed",
        "run-interrupted",
    ]
    assert same_json(lab.details(run_id, "run-interrupted")[0], {"page": 2})
    assert lab.journal.labels(run_id)[-2:] == [
        "append:run-interrupted",
        "finish_run:failed",
    ]
    assert lab.source.requests == [1, 2]
    assert lab.opener.all_closed


def test_interrupt_after_the_local_store_records_the_observation_first(
    lab: Lab,
) -> None:
    """AC7: stored locally, interrupted before PostgreSQL -> recorded, then closed."""
    store = lab.publishes_then_fails(on_call=2, error=lambda: KeyboardInterrupt())

    outcome = call(lab, fresh(lab, 1, 3), store=store)

    run_id = created(outcome)
    assert outcome.end is IngestEnd.INTERRUPTED
    assert outcome.run_status is RunStatus.FAILED
    assert lab.sequences(run_id) == (1, 2)
    assert lab.journal.labels(run_id)[-4:] == [
        "store:2",
        "record_observation:2",
        "append:run-interrupted",
        "finish_run:failed",
    ]
    assert same_json(lab.details(run_id, "run-interrupted")[0], {"page": 2})


def test_interrupt_during_the_cleanup_propagates_and_leaves_the_run_running(
    lab: Lab,
) -> None:
    """AC7, Q11: a second `KeyboardInterrupt` on the audit append is not caught."""
    lab.source.script(2, KeyboardInterrupt())
    lab.script_ids(FREE_ID)
    lab.opener.faults[1] = [
        lab.faults.interrupts("append_audit_event", detail="run-interrupted")
    ]

    with pytest.raises(KeyboardInterrupt):
        call_propagating(lab, fresh(lab, 1, 3))

    assert lab.database.runs[FREE_ID].status is RunStatus.RUNNING
    assert "finish_run:failed" not in lab.journal.labels(FREE_ID)
    assert lab.reporter.started == [FREE_ID]
    assert lab.opener.all_closed


def test_interrupt_cleanup_that_meets_a_database_error_leaves_the_run_running(
    lab: Lab,
) -> None:
    """AC7, Q11: no new connection; the call still returns INTERRUPTED, `running`."""
    lab.source.script(2, KeyboardInterrupt())
    lab.opener.faults[1] = [
        lab.faults.lost_before_commit("append_audit_event", detail="run-interrupted")
    ]

    outcome = call(lab, fresh(lab, 1, 3))

    assert outcome.end is IngestEnd.INTERRUPTED
    assert outcome.run_status is RunStatus.RUNNING
    assert lab.database.runs[created(outcome)].status is RunStatus.RUNNING
    assert lab.opener.opens == 1
    assert lab.opener.all_closed


def test_interrupt_before_start_run_returned_leaves_no_run(lab: Lab) -> None:
    """Q11: nothing to clean before the run exists; INTERRUPTED with no run."""
    lab.opener.faults[1] = [lab.faults.interrupts("start_run")]

    outcome = call(lab, fresh(lab, 1, 3))

    assert outcome.end is IngestEnd.INTERRUPTED
    assert outcome.execution_id is None
    assert outcome.run_status is None
    assert lab.database.runs == {}
    assert lab.source.requests == []
    assert lab.opener.all_closed


# === unexpected (AC15, Q11) ==================================================


class SyntheticDefect(Exception):
    """SYNTHETIC: an exception that is not a project error."""


UNEXPECTED_ERRORS = [
    pytest.param(lambda: SyntheticDefect(BODY_MARKER), id="synthetic-defect"),
    pytest.param(lambda: MemoryError(), id="memory-error"),
]


@pytest.mark.parametrize("make_error", UNEXPECTED_ERRORS)
def test_unexpected_exception_is_audited_by_class_name_and_closes_failed(
    lab: Lab, make_error: Callable[[], BaseException]
) -> None:
    """AC15, Q11: `unexpected-error` (page, class name); no message text anywhere."""
    error = make_error()
    lab.source.script(2, error)

    outcome = call(lab, fresh(lab, 1, 3))

    run_id = created(outcome)
    assert outcome.end is IngestEnd.RUN_FAILED
    assert outcome.run_status is RunStatus.FAILED
    assert lab.event_types(run_id) == [
        "run-started",
        "page-completed",
        "unexpected-error",
    ]
    assert same_json(
        lab.details(run_id, "unexpected-error")[0],
        {"page": 2, "error_type": type(error).__name__},
    )
    assert lab.journal.labels(run_id)[-2:] == [
        "append:unexpected-error",
        "finish_run:failed",
    ]
    assert_follows_catalogue(lab.events(run_id))
    assert lab.source.requests == [1, 2]


def test_unexpected_exception_text_never_reaches_the_reporter(lab: Lab) -> None:
    """AC15: the reporter gets the class name of an unknown exception, nothing else."""
    lab.source.script(2, SyntheticDefect(BODY_MARKER))

    call(lab, fresh(lab, 1, 3))

    assert not any(BODY_MARKER in message for message in lab.reporter.messages)


def test_unexpected_cleanup_that_meets_a_database_error_leaves_the_run_running(
    lab: Lab,
) -> None:
    """Q11: best effort -> RUN_FAILED with the run still `running`, no new connection."""
    lab.source.script(2, MemoryError())
    lab.opener.faults[1] = [
        lab.faults.lost_before_commit("append_audit_event", detail="unexpected-error")
    ]

    outcome = call(lab, fresh(lab, 1, 3))

    assert outcome.end is IngestEnd.RUN_FAILED
    assert outcome.run_status is RunStatus.RUNNING
    assert lab.database.runs[created(outcome)].status is RunStatus.RUNNING
    assert lab.opener.opens == 1
    assert lab.opener.all_closed


def test_unexpected_system_exit_is_never_caught(lab: Lab) -> None:
    """Q11: `SystemExit` propagates, and the repository is still closed."""
    lab.source.script(2, SystemExit(3))

    with pytest.raises(SystemExit):
        call(lab, fresh(lab, 1, 3))

    assert lab.opener.all_closed


# === connection_loss (AC8) ===================================================

WHEN = ["before", "after"]


def lost_at(
    lab: Lab, operation: str, detail: str | None, when: str, *, open_index: int = 1
) -> None:
    """Lose the connection of repository number `open_index` at a call."""
    fault = (
        lab.faults.lost_before_commit(operation, detail=detail)
        if when == "before"
        else lab.faults.lost_after_commit(operation, detail=detail)
    )
    lab.opener.faults.setdefault(open_index, []).append(fault)


@pytest.mark.parametrize("when", WHEN)
def test_connection_loss_on_an_observation_records_it_again_with_the_same_values(
    lab: Lab, when: str
) -> None:
    """AC8: committed or not, the observation ends in PostgreSQL once, then closes."""
    lost_at(lab, "record_observation", "2", when)

    outcome = call(lab, fresh(lab, 1, 3))

    run_id = created(outcome)
    attempts = lab.opener.attempts_of("record_observation", "2")
    assert [attempt.open_index for attempt in attempts] == [1, 2]
    assert attempts[0].args == attempts[1].args
    assert lab.sequences(run_id) == (1, 2)
    assert lab.database.observations[(run_id, 2)] == lab.store.read_observation(
        run_id, 2
    )
    assert outcome.end is IngestEnd.RUN_FAILED
    assert outcome.run_status is RunStatus.FAILED
    assert lab.event_types(run_id) == [
        "run-started",
        "page-completed",
        "storage-failed",
    ]
    assert same_json(
        lab.details(run_id, "storage-failed")[0],
        {"page": 2, "sequence": 2, "store": "postgresql"},
    )


@pytest.mark.parametrize("when", WHEN)
def test_connection_loss_opens_exactly_one_new_connection_and_takes_the_exclusion(
    lab: Lab, when: str
) -> None:
    """AC8, Q3: one new connection, the exclusion again, both repositories closed."""
    lost_at(lab, "record_observation", "2", when)

    call(lab, fresh(lab, 1, 3))

    assert lab.opener.opens == 2
    assert lab.opener.all_closed
    assert [
        attempt.open_index
        for attempt in lab.opener.attempts_of("try_acquire_ingest_exclusion")
    ] == [1, 2]
    assert lab.database.exclusion_holder is None


@pytest.mark.parametrize("when", WHEN)
def test_connection_loss_on_the_closing_write_of_a_failure_completes_that_path(
    lab: Lab, when: str
) -> None:
    """AC8, Q3: `finish_run(failed)` again with the same values; no `storage-failed`."""
    lab.source.script(2, lab.status_failure(2, 500))
    lost_at(lab, "finish_run", "failed", when)

    outcome = call(lab, fresh(lab, 1, 3))

    run_id = created(outcome)
    attempts = lab.opener.attempts_of("finish_run", "failed")
    assert [attempt.open_index for attempt in attempts] == [1, 2]
    assert attempts[0].args == attempts[1].args
    assert outcome.end is IngestEnd.RUN_FAILED
    assert outcome.run_status is RunStatus.FAILED
    assert lab.event_types(run_id) == ["run-started", "page-completed", "page-failed"]
    run = lab.database.runs[run_id]
    assert run.status is RunStatus.FAILED
    assert run.finished_at == attempts[0].args[2]
    assert run.finished_at in lab.clock.issued


@pytest.mark.parametrize("when", WHEN)
def test_connection_loss_on_the_failure_event_leaves_it_once_and_closes_failed(
    lab: Lab, when: str
) -> None:
    """AC8, Q3: the lost `page-failed` is in the run once; the failure path ends."""
    lab.source.script(2, lab.status_failure(2, 500))
    lost_at(lab, "append_audit_event", "page-failed", when)

    outcome = call(lab, fresh(lab, 1, 3))

    run_id = created(outcome)
    first = lab.opener.attempts_of("append_audit_event", "page-failed")[0]
    assert outcome.end is IngestEnd.RUN_FAILED
    assert outcome.run_status is RunStatus.FAILED
    assert lab.event_types(run_id) == ["run-started", "page-completed", "page-failed"]
    assert lab.events(run_id)[2].occurred_at == first.args[1]
    assert lab.database.runs[run_id].status is RunStatus.FAILED


@pytest.mark.parametrize("when", WHEN)
def test_connection_loss_on_the_closing_write_keeps_one_finish_time(
    lab: Lab, when: str
) -> None:
    """AC8: `finish_run` again with the same `finished_at`; the stored row is that."""
    lab.source.script(2, lab.status_failure(2, 500))
    lost_at(lab, "finish_run", "failed", when)

    outcome = call(lab, fresh(lab, 1, 3))

    attempts = lab.opener.attempts_of("finish_run", "failed")
    finished_at = attempts[0].args[2]
    assert attempts[1].args[2] == finished_at
    assert lab.database.runs[created(outcome)].finished_at == finished_at


@pytest.mark.parametrize("when", WHEN)
def test_connection_loss_on_an_audit_event_leaves_that_event_once(
    lab: Lab, when: str
) -> None:
    """AC8, Q3: committed or not, the event is in the run exactly once."""
    lost_at(lab, "append_audit_event", "page-completed", when)

    outcome = call(lab, fresh(lab, 1, 3))

    run_id = created(outcome)
    attempts = lab.opener.attempts_of("append_audit_event", "page-completed")
    assert lab.event_types(run_id) == [
        "run-started",
        "page-completed",
        "storage-failed",
    ]
    completed = lab.events(run_id)[1]
    assert completed.occurred_at == attempts[0].args[1]
    assert same_json(dict(completed.detail), completed_detail(1, 1, lab.body(1)))
    assert same_json(
        lab.details(run_id, "storage-failed")[0],
        {"page": 1, "sequence": 1, "store": "postgresql"},
    )
    assert outcome.run_status is RunStatus.FAILED


@pytest.mark.parametrize("when", WHEN)
def test_connection_loss_on_the_opening_event_leaves_it_once(
    lab: Lab, when: str
) -> None:
    """AC8: `run-started` lost -> once in the run, then the failure is recorded."""
    lost_at(lab, "append_audit_event", "run-started", when)

    outcome = call(lab, fresh(lab, 1, 3))

    run_id = created(outcome)
    assert lab.event_types(run_id) == ["run-started", "storage-failed"]
    assert same_json(
        lab.details(run_id, "storage-failed")[0],
        {"page": 1, "sequence": None, "store": "postgresql"},
    )
    assert outcome.end is IngestEnd.RUN_FAILED
    assert outcome.run_status is RunStatus.FAILED
    assert lab.source.requests == []


@pytest.mark.parametrize("when", WHEN)
def test_connection_loss_on_start_run_makes_the_run_once_and_closes_it_failed(
    lab: Lab, when: str
) -> None:
    """AC8: `start_run` again with the same scope and `started_at`; one run."""
    lost_at(lab, "start_run", None, when)

    outcome = call(lab, fresh(lab, 1, 3))

    run_id = created(outcome)
    attempts = lab.opener.attempts_of("start_run")
    assert [attempt.open_index for attempt in attempts] == [1, 2]
    assert attempts[0].args == attempts[1].args
    assert list(lab.database.runs) == [run_id]
    assert lab.database.runs[run_id].status is RunStatus.FAILED
    assert outcome.end is IngestEnd.RUN_FAILED
    assert outcome.run_status is RunStatus.FAILED
    assert lab.source.requests == []
    assert lab.details(run_id, "storage-failed") == [
        {"page": 1, "sequence": None, "store": "postgresql"}
    ]


def test_connection_loss_a_second_loss_opens_no_third_connection(lab: Lab) -> None:
    """AC8: the run is left `running`; the call returns RUN_FAILED with `running`."""
    lost_at(lab, "record_observation", "2", "after")
    lost_at(lab, "append_audit_event", "storage-failed", "before", open_index=2)

    outcome = call(lab, fresh(lab, 1, 3))

    assert outcome.end is IngestEnd.RUN_FAILED
    assert outcome.run_status is RunStatus.RUNNING
    assert lab.database.runs[created(outcome)].status is RunStatus.RUNNING
    assert lab.opener.opens == 2
    assert lab.opener.all_closed


@pytest.mark.parametrize("when", WHEN)
def test_connection_loss_when_the_new_connection_is_refused_leaves_the_run_running(
    lab: Lab, when: str
) -> None:
    """AC8 (b): no second attempt, the run stays `running`, the store is intact."""
    lost_at(lab, "record_observation", "2", when)
    lab.opener.fail_opens = {2}

    outcome = call(lab, fresh(lab, 1, 3))

    run_id = created(outcome)
    assert outcome.end is IngestEnd.RUN_FAILED
    assert outcome.run_status is RunStatus.RUNNING
    assert lab.database.runs[run_id].status is RunStatus.RUNNING
    assert lab.opener.opens == 2
    assert lab.event_types(run_id) == ["run-started", "page-completed"]
    assert lab.local_sequences(run_id) == (1, 2)
    assert lab.opener.all_closed


def test_connection_loss_when_another_session_holds_the_exclusion_touches_nothing(
    lab: Lab,
) -> None:
    """AC8 (c): the exclusion is refused again -> no event, no `finish_run`."""
    fault = lab.faults.lost_before_commit(
        "record_observation", detail="2", hook=lab.database.hold_exclusion_elsewhere
    )
    lab.opener.faults[1] = [fault]

    outcome = call(lab, fresh(lab, 1, 3))

    run_id = created(outcome)
    assert outcome.end is IngestEnd.RUN_FAILED
    assert outcome.run_status is RunStatus.RUNNING
    assert lab.database.runs[run_id].status is RunStatus.RUNNING
    assert lab.event_types(run_id) == ["run-started", "page-completed"]
    assert lab.sequences(run_id) == (1,)
    assert lab.opener.opens == 2
    assert lab.opener.all_closed


@pytest.mark.parametrize(
    "operation", ["try_acquire_ingest_exclusion", "list_runs", "read_run"]
)
def test_connection_loss_before_the_run_exists_opens_no_new_connection(
    lab: Lab, operation: str
) -> None:
    """AC8, State machine C: before `start_run`, the call ends NOT_STARTED."""
    lab.opener.faults[1] = [lab.faults.lost_before_commit(operation)]

    outcome = call(lab, fresh(lab, 1, 3))

    assert_not_started(outcome)
    assert lab.opener.opens == 1
    assert lab.database.runs == {}
    assert lab.source.requests == []
    assert lab.opener.all_closed


@pytest.mark.parametrize("operation", ["read_run", "list_audit_events", "list_runs"])
def test_connection_loss_while_checking_a_resumption_opens_no_new_connection(
    lab: Lab, operation: str
) -> None:
    seed_run(lab, lab.A, pages=(1, 2))
    before = lab.snapshot()
    lab.opener.faults[1] = [lab.faults.lost_before_commit(operation)]

    outcome = call(lab, resume(lab.A))

    assert_not_started(outcome)
    assert lab.opener.opens == 1
    assert lab.snapshot() == before
    assert lab.source.requests == []


# === connection_loss_final_finish (AC8, decision P-2) ========================


def lose_the_final_finish(
    lab: Lab, when: str, *, hook: Callable[[], None] | None = None
) -> None:
    """Script ids and a fault for the closing `finish_run(succeeded)`."""
    lab.script_ids(FREE_ID)
    fault = (
        lab.faults.lost_before_commit("finish_run", detail="succeeded", hook=hook)
        if when == "before"
        else lab.faults.lost_after_commit("finish_run", detail="succeeded", hook=hook)
    )
    lab.opener.faults[1] = [fault]


@pytest.mark.parametrize("when", WHEN)
def test_connection_loss_final_finish_is_confirmed_by_the_exact_second_attempt(
    lab: Lab, when: str
) -> None:
    """P-2 (a), (b): the repeat on the new connection returns `succeeded`."""
    lose_the_final_finish(lab, when)

    outcome = call(lab, fresh(lab, 1, 2))

    assert outcome.end is IngestEnd.SUCCEEDED
    assert outcome.run_status is RunStatus.SUCCEEDED
    assert outcome.execution_id == FREE_ID
    assert lab.database.runs[FREE_ID].status is RunStatus.SUCCEEDED
    assert lab.opener.opens == 2
    assert lab.opener.all_closed


@pytest.mark.parametrize("when", WHEN)
def test_connection_loss_final_finish_is_made_again_with_the_same_finish_time(
    lab: Lab, when: str
) -> None:
    """P-2: the repeat carries the same `finished_at`, and it is the stored one."""
    lose_the_final_finish(lab, when)

    call(lab, fresh(lab, 1, 2))

    attempts = lab.opener.attempts_of("finish_run", "succeeded")
    assert [attempt.open_index for attempt in attempts] == [1, 2]
    assert attempts[0].args == attempts[1].args
    assert lab.database.runs[FREE_ID].finished_at == attempts[0].args[2]


@pytest.mark.parametrize("when", WHEN)
def test_connection_loss_final_finish_adds_no_failure_and_never_closes_failed(
    lab: Lab, when: str
) -> None:
    """P-2: no `storage-failed`, and no `finish_run(failed)` is attempted."""
    lose_the_final_finish(lab, when)

    call(lab, fresh(lab, 1, 2))

    assert lab.event_types(FREE_ID) == [
        "run-started",
        "page-completed",
        "page-completed",
    ]
    assert lab.opener.attempts_of("finish_run", "failed") == []


def test_connection_loss_final_finish_after_the_commit_leaves_the_row_unchanged(
    lab: Lab,
) -> None:
    """P-2 (b): the repeat returns the stored run; the row is the committed one."""
    committed = []
    lose_the_final_finish(
        lab, "after", hook=lambda: committed.append(lab.database.runs[FREE_ID])
    )

    call(lab, fresh(lab, 1, 2))

    assert committed
    assert lab.database.runs[FREE_ID] == committed[0]
    assert lab.database.runs[FREE_ID].status is RunStatus.SUCCEEDED


@pytest.mark.parametrize("when", WHEN)
def test_connection_loss_final_finish_without_a_new_connection_is_not_confirmed(
    lab: Lab, when: str
) -> None:
    """P-2 (c): the second open fails -> no repeat; `running` is the last confirmed."""
    lose_the_final_finish(lab, when)
    lab.opener.fail_opens = {2}

    outcome = call(lab, fresh(lab, 1, 2))

    assert outcome.end is IngestEnd.RUN_FAILED
    assert outcome.run_status is RunStatus.RUNNING
    assert len(lab.opener.attempts_of("finish_run")) == 1
    assert lab.event_types(FREE_ID) == [
        "run-started",
        "page-completed",
        "page-completed",
    ]
    assert lab.opener.all_closed


def test_connection_loss_final_finish_with_the_exclusion_held_is_not_made_again(
    lab: Lab,
) -> None:
    """P-2 (c): the exclusion is refused -> no repeat, the run is not touched."""
    lose_the_final_finish(lab, "before", hook=lab.database.hold_exclusion_elsewhere)

    outcome = call(lab, fresh(lab, 1, 2))

    assert outcome.end is IngestEnd.RUN_FAILED
    assert outcome.run_status is RunStatus.RUNNING
    assert lab.database.runs[FREE_ID].status is RunStatus.RUNNING
    assert len(lab.opener.attempts_of("finish_run")) == 1
    assert lab.event_types(FREE_ID) == [
        "run-started",
        "page-completed",
        "page-completed",
    ]


def test_connection_loss_final_finish_a_second_loss_leaves_the_run_running(
    lab: Lab,
) -> None:
    """P-2, State machine C step 6: no third connection."""
    lose_the_final_finish(lab, "before")
    lab.opener.faults[2] = [lab.faults.lost_before_commit("finish_run")]

    outcome = call(lab, fresh(lab, 1, 2))

    assert outcome.end is IngestEnd.RUN_FAILED
    assert outcome.run_status is RunStatus.RUNNING
    assert lab.opener.opens == 2
    assert lab.opener.all_closed


def test_connection_loss_final_finish_refused_by_the_second_attempt_reports_the_stored_run(
    lab: Lab,
) -> None:
    """P-2: a conflict on the repeat -> RUN_FAILED with the status of the stored run."""
    lose_the_final_finish(
        lab,
        "before",
        hook=lambda: lab.other_session_finishes(
            FREE_ID, RunStatus.FAILED, lab.clock.now() + timedelta(hours=1)
        ),
    )

    outcome = call(lab, fresh(lab, 1, 2))

    assert outcome.end is IngestEnd.RUN_FAILED
    assert outcome.run_status is RunStatus.FAILED
    assert lab.database.runs[FREE_ID].status is RunStatus.FAILED


# === resume (AC9) ============================================================


def test_resume_requests_only_the_pages_the_earlier_runs_did_not_complete(
    lab: Lab,
) -> None:
    """AC9: A completed 1 and 2 and failed on 3 -> B requests 3 and 4 only."""
    seed_run(lab, lab.A, pages=(1, 2))
    lab.seed.failed_page(lab.A, 3, 3)

    outcome = call(lab, resume(lab.A))

    assert outcome.end is IngestEnd.SUCCEEDED
    assert outcome.run_status is RunStatus.SUCCEEDED
    assert lab.source.requests == [3, 4]


def test_resume_links_the_new_run_and_copies_the_original_range(lab: Lab) -> None:
    """AC9: `run-started` {"resumes": A, "first_page": 3}; the same scope JSON."""
    seed_run(lab, lab.A, pages=(1, 2))
    lab.seed.failed_page(lab.A, 3, 3)

    outcome = call(lab, resume(lab.A))

    run_id = created(outcome)
    assert run_id != lab.A
    assert same_json(
        lab.details(run_id, "run-started")[0], {"resumes": lab.A, "first_page": 3}
    )
    assert same_json(
        dict(lab.database.runs[run_id].scope), dict(lab.database.runs[lab.A].scope)
    )


def test_resume_numbers_the_sequences_of_the_new_run_from_one(lab: Lab) -> None:
    seed_run(lab, lab.A, pages=(1, 2))
    lab.seed.failed_page(lab.A, 3, 3)

    run_id = created(call(lab, resume(lab.A)))

    assert lab.sequences(run_id) == (1, 2)
    assert lab.local_sequences(run_id) == (1, 2)
    assert [d["page"] for d in lab.details(run_id, "page-completed")] == [3, 4]


def test_resume_of_a_resumption_requests_only_the_page_left(lab: Lab) -> None:
    """AC9: B fails on page 4 -> C requests page 4 only."""
    seed_run(lab, lab.A, pages=(1, 2))
    lab.seed.failed_page(lab.A, 3, 3)
    lab.source.script(4, lab.status_failure(4, 500))
    second = call(lab, resume(lab.A))
    requested = len(lab.source.requests)

    third = call(lab, resume(created(second)))

    assert second.end is IngestEnd.RUN_FAILED
    assert third.end is IngestEnd.SUCCEEDED
    assert lab.source.requests[requested:] == [4]
    assert same_json(
        lab.details(created(third), "run-started")[0],
        {"resumes": created(second), "first_page": 4},
    )


def test_resume_requests_again_a_page_stored_without_its_page_completed(
    lab: Lab,
) -> None:
    """AC9: stored in both stores but never recorded as completed -> requested again."""
    seed_run(lab, lab.A, last=3, pages=(1,))
    lab.seed.page(lab.A, 2, 2, event=False)
    before = lab.snapshot()

    outcome = call(lab, resume(lab.A))

    after = lab.snapshot()
    assert outcome.end is IngestEnd.SUCCEEDED
    assert lab.source.requests == [2, 3]
    assert after.objects - before.objects == {
        lab.store.read_observation(created(outcome), 2).content_hash
    }
    assert len(after.evidence - before.evidence) == 1


def test_resume_requests_again_a_page_that_has_only_an_orphan_object(lab: Lab) -> None:
    """AC9: an object with no observation counts for nothing; identical bytes add none."""
    seed_run(lab, lab.A, last=3, pages=(1,))
    orphan = lab.store.put_object(lab.body(2))
    before = lab.snapshot()

    outcome = call(lab, resume(lab.A))

    run_id = created(outcome)
    after = lab.snapshot()
    assert lab.source.requests == [2, 3]
    assert lab.store.read_observation(run_id, 1).content_hash == orphan
    assert len(after.objects - before.objects) == 1


def test_resume_with_every_page_completed_but_running_requests_nothing(
    lab: Lab,
) -> None:
    """AC9, P-4: closed by reconciliation, nothing requested, `first_page` 5."""
    seed_run(lab, lab.A, pages=(1, 2, 3, 4), status=RunStatus.RUNNING)

    outcome = call(lab, resume(lab.A))

    run_id = created(outcome)
    assert outcome.end is IngestEnd.SUCCEEDED
    assert lab.source.requests == []
    assert lab.database.runs[lab.A].status is RunStatus.FAILED
    assert same_json(
        lab.details(run_id, "run-started")[0], {"resumes": lab.A, "first_page": 5}
    )
    assert lab.event_types(run_id) == ["run-started"]
    assert position(lab, "finish_run", lab.A) < position(lab, "start_run", run_id)


def test_resume_of_a_running_run_with_a_valid_reached_event_requests_nothing(
    lab: Lab,
) -> None:
    """AC9, AC3: a valid `last-page-reached` in the chain leaves no page to request."""
    seed_run(lab, lab.A, pages=(1, 2), status=RunStatus.RUNNING)
    lab.seed.last_page(lab.A, 2, 2)

    outcome = call(lab, resume(lab.A))

    assert outcome.end is IngestEnd.SUCCEEDED
    assert lab.source.requests == []
    assert same_json(
        lab.details(created(outcome), "run-started")[0],
        {"resumes": lab.A, "first_page": 5},
    )


@pytest.mark.parametrize("target", ["absent", "succeeded"])
def test_resume_of_an_invalid_target_is_refused_and_writes_nothing(
    lab: Lab, target: str
) -> None:
    """AC9, AC14: an unknown id or a `succeeded` run -> INVALID_TARGET, nothing written.

    A reconcilable `running` run exists: the target check comes before it.
    """
    seed_run(lab, lab.D, pages=(1,), status=RunStatus.RUNNING)
    lab.seed.page(lab.D, 2, 2, postgres=False, event=False)
    if target == "succeeded":
        seed_run(lab, lab.C, pages=(1, 2, 3, 4), status=RunStatus.SUCCEEDED)
    request = resume(lab.ABSENT if target == "absent" else lab.C)
    before = lab.snapshot()

    outcome = call(lab, request)

    assert outcome.end is IngestEnd.INVALID_TARGET
    assert outcome.execution_id is None
    assert outcome.run_status is None
    assert request.execution_id in outcome.message
    assert lab.snapshot() == before
    assert lab.source.requests == []
    assert lab.execution_ids.drawn == []
    assert lab.opener.all_closed


def test_resume_while_another_session_holds_the_exclusion_changes_nothing(
    lab: Lab,
) -> None:
    """AC9: refused at the exclusion -> NOT_STARTED, nothing changed."""
    seed_run(lab, lab.A, pages=(1, 2))
    lab.database.hold_exclusion_elsewhere()
    before = lab.snapshot()

    outcome = call(lab, resume(lab.A))

    assert_not_started(outcome)
    assert lab.snapshot() == before
    assert lab.source.requests == []


def test_resume_checks_the_exclusion_before_the_target(lab: Lab) -> None:
    """Q9: the exclusion is taken first; an unknown target is not even looked at."""
    lab.database.hold_exclusion_elsewhere()

    outcome = call(lab, resume(lab.ABSENT))

    assert_not_started(outcome)


# === reconcile (AC10) ========================================================


def seed_crashed_run(
    lab: Lab, run_id: str, *, local_only: tuple[int, ...] = (3,)
) -> None:
    """A `running` run with observations 1 and 2 in both stores, more only locally."""
    lab.seed.run(run_id, scope=lab.scope(1, 4), status=RunStatus.RUNNING)
    lab.seed.page(run_id, 1, 1, event=False)
    lab.seed.page(run_id, 2, 2, event=False)
    for sequence in local_only:
        lab.seed.page(run_id, sequence, sequence, postgres=False, event=False)


def test_reconcile_records_a_local_only_observation_and_audits_it(lab: Lab) -> None:
    """AC10: local {1,2,3}, PostgreSQL {1,2} -> 3 recorded, two events, `failed`."""
    seed_crashed_run(lab, lab.A)

    outcome = call(lab, fresh(lab, 1, 2))

    assert outcome.end is IngestEnd.SUCCEEDED
    assert lab.sequences(lab.A) == (1, 2, 3)
    assert lab.database.observations[(lab.A, 3)] == lab.store.read_observation(lab.A, 3)
    assert lab.event_types(lab.A) == [
        "observation-reconciled",
        "run-closed-by-reconciliation",
    ]
    assert same_json(lab.details(lab.A, "observation-reconciled")[0], {"sequence": 3})
    assert same_json(
        lab.details(lab.A, "run-closed-by-reconciliation")[0],
        {"reconciled_observations": 1},
    )
    assert lab.database.runs[lab.A].status is RunStatus.FAILED
    assert_follows_catalogue(lab.events(lab.A))


def test_reconcile_never_decides_a_page_is_completed_from_stored_bytes(
    lab: Lab,
) -> None:
    """Q14: reconciliation appends no `page-completed`."""
    seed_crashed_run(lab, lab.A)

    call(lab, fresh(lab, 1, 2))

    assert "page-completed" not in lab.event_types(lab.A)


def test_reconcile_closes_the_run_before_the_new_run_starts(lab: Lab) -> None:
    """AC10: reconciliation first, and only then the run of this call."""
    seed_crashed_run(lab, lab.A)

    outcome = call(lab, fresh(lab, 1, 2))

    assert position(lab, "finish_run", lab.A) < position(
        lab, "start_run", created(outcome)
    )
    assert lab.database.runs[created(outcome)].status is RunStatus.SUCCEEDED


def test_reconcile_examines_every_running_run_in_start_order(lab: Lab) -> None:
    seed_crashed_run(lab, lab.A, local_only=())
    seed_crashed_run(lab, lab.B, local_only=(3,))

    outcome = call(lab, fresh(lab, 1, 2))

    run_id = created(outcome)
    assert lab.database.runs[lab.A].status is RunStatus.FAILED
    assert lab.database.runs[lab.B].status is RunStatus.FAILED
    assert same_json(
        lab.details(lab.A, "run-closed-by-reconciliation")[0],
        {"reconciled_observations": 0},
    )
    assert same_json(
        lab.details(lab.B, "run-closed-by-reconciliation")[0],
        {"reconciled_observations": 1},
    )
    assert (
        position(lab, "finish_run", lab.A)
        < position(lab, "finish_run", lab.B)
        < position(lab, "start_run", run_id)
    )


def test_reconcile_leaves_orphan_objects_in_place_and_counts_them_for_nothing(
    lab: Lab,
) -> None:
    seed_crashed_run(lab, lab.A, local_only=())
    orphan = lab.store.put_object(b"synthetic orphan bytes")

    outcome = call(lab, fresh(lab, 1, 2))

    assert outcome.end is IngestEnd.SUCCEEDED
    assert orphan in lab.store.objects
    assert lab.event_types(lab.A) == ["run-closed-by-reconciliation"]


def test_reconcile_examines_only_the_runs_listed_as_running(lab: Lab) -> None:
    """AC10: a `failed` run keeps its local-only observation; nothing is added to it."""
    lab.seed.run(lab.A, scope=lab.scope(1, 4), status=RunStatus.FAILED)
    lab.seed.page(lab.A, 1, 1, event=False)
    lab.seed.page(lab.A, 2, 2, postgres=False, event=False)
    before = lab.database.run_state(lab.A)

    outcome = call(lab, fresh(lab, 1, 2))

    assert outcome.end is IngestEnd.SUCCEEDED
    assert lab.database.run_state(lab.A) == before
    assert lab.sequences(lab.A) == (1,)


def test_reconcile_with_the_exclusion_held_elsewhere_touches_nothing(lab: Lab) -> None:
    """AC10: a run whose process holds the exclusion is never touched."""
    seed_crashed_run(lab, lab.A)
    lab.database.hold_exclusion_elsewhere()
    before = lab.snapshot()

    outcome = call(lab, fresh(lab, 1, 2))

    assert_not_started(outcome)
    assert lab.snapshot() == before
    assert lab.database.runs[lab.A].status is RunStatus.RUNNING
    assert lab.source.requests == []


def break_a_missing_local(lab: Lab) -> tuple[int | None, str]:
    seed_crashed_run(lab, lab.A, local_only=())
    del lab.store.observations[(lab.A, 2)]
    return 2, "local-observation-missing"


def break_a_different_local(lab: Lab) -> tuple[int | None, str]:
    seed_crashed_run(lab, lab.A, local_only=())
    stored = lab.store.read_observation(lab.A, 2)
    lab.store.replace_observation(dataclasses.replace(stored, url=stored.url + "&x=1"))
    return 2, "local-observation-different"


def break_an_unreadable_local(lab: Lab) -> tuple[int | None, str]:
    seed_crashed_run(lab, lab.A, local_only=())
    lab.store.make_unreadable(lab.A, 2)
    return 2, "local-observation-unreadable"


def break_a_missing_object(lab: Lab) -> tuple[int | None, str]:
    seed_crashed_run(lab, lab.A, local_only=())
    lab.store.remove_object(lab.store.read_observation(lab.A, 1).content_hash)
    return 1, "object-missing"


def break_a_tampered_object(lab: Lab) -> tuple[int | None, str]:
    seed_crashed_run(lab, lab.A, local_only=())
    lab.store.tamper_object(
        lab.store.read_observation(lab.A, 1).content_hash, b"synthetic tampered bytes"
    )
    return 1, "object-integrity"


def break_with_a_gap(lab: Lab) -> tuple[int | None, str]:
    lab.seed.run(lab.A, scope=lab.scope(1, 4), status=RunStatus.RUNNING)
    lab.seed.page(lab.A, 1, 1, event=False)
    lab.seed.page(lab.A, 3, 3, postgres=False, event=False)
    return 2, "sequence-gap"


def break_with_a_gap_and_a_bad_later_object(lab: Lab) -> tuple[int | None, str]:
    """Observation 3 is still verified: its missing object is found before the gap."""
    break_with_a_gap(lab)
    lab.store.remove_object(lab.store.read_observation(lab.A, 3).content_hash)
    return 3, "object-missing"


def break_with_a_zero_sequence(lab: Lab) -> tuple[int | None, str]:
    lab.seed.run(lab.A, scope=lab.scope(1, 4), status=RunStatus.RUNNING)
    lab.seed.page(lab.A, 1, 0, postgres=False, event=False)
    lab.seed.page(lab.A, 2, 1, postgres=False, event=False)
    return 0, "sequence-gap"


def break_with_a_postgresql_conflict(lab: Lab) -> tuple[int | None, str]:
    seed_crashed_run(lab, lab.A, local_only=(3,))
    lab.opener.faults[1] = [
        lab.faults.refuses(
            "record_observation",
            lambda: PersistenceIntegrityError("synthetic conflict"),
            detail="3",
        )
    ]
    return 3, "postgresql-observation-conflict"


def break_the_listing_with_an_integrity_error(lab: Lab) -> tuple[int | None, str]:
    seed_crashed_run(lab, lab.A, local_only=())
    lab.store.fail_listing(lab.A, EvidenceIntegrityError("synthetic bad entry"))
    return None, "local-listing-failed"


def break_the_listing_with_an_os_error(lab: Lab) -> tuple[int | None, str]:
    seed_crashed_run(lab, lab.A, local_only=())
    lab.store.fail_listing(lab.A, OSError("synthetic listing failure"))
    return None, "local-listing-failed"


RECONCILE_PROBLEMS = [
    pytest.param(break_a_missing_local, id="missing-local"),
    pytest.param(break_a_different_local, id="different-local"),
    pytest.param(break_an_unreadable_local, id="unreadable-local"),
    pytest.param(break_a_missing_object, id="missing-object"),
    pytest.param(break_a_tampered_object, id="tampered-object"),
    pytest.param(break_with_a_gap, id="gap"),
    pytest.param(break_with_a_gap_and_a_bad_later_object, id="gap-after-a-bad-object"),
    pytest.param(break_with_a_zero_sequence, id="zero-sequence"),
    pytest.param(break_with_a_postgresql_conflict, id="postgresql-conflict"),
    pytest.param(break_the_listing_with_an_integrity_error, id="listing-integrity"),
    pytest.param(break_the_listing_with_an_os_error, id="listing-os-error"),
]


@pytest.mark.parametrize("break_it", RECONCILE_PROBLEMS)
def test_reconcile_a_problem_is_audited_with_its_sequence_and_value(
    lab: Lab, break_it: Callable[[Lab], tuple[int | None, str]]
) -> None:
    """AC10: `reconciliation-failed` (sequence, problem), `failed`, no new run."""
    sequence, problem = break_it(lab)

    outcome = call(lab, fresh(lab, 1, 2))

    assert_not_started(outcome)
    assert lab.event_types(lab.A) == ["reconciliation-failed"]
    assert same_json(
        lab.details(lab.A, "reconciliation-failed")[0],
        {"sequence": sequence, "problem": problem},
    )
    assert lab.database.runs[lab.A].status is RunStatus.FAILED
    assert lab.journal.labels(lab.A)[-2:] == [
        "append:reconciliation-failed",
        "finish_run:failed",
    ]
    assert list(lab.database.runs) == [lab.A]
    assert lab.source.requests == []
    assert lab.reporter.started == []
    assert_follows_catalogue(lab.events(lab.A))


@pytest.mark.parametrize(
    "break_it", [break_with_a_gap, break_with_a_postgresql_conflict]
)
def test_reconcile_a_problem_records_no_local_only_observation(
    lab: Lab, break_it: Callable[[Lab], tuple[int | None, str]]
) -> None:
    """AC10: nothing is recorded in PostgreSQL once a problem is found."""
    break_it(lab)
    recorded = lab.sequences(lab.A)

    call(lab, fresh(lab, 1, 2))

    assert lab.sequences(lab.A) == recorded


def test_reconcile_stops_at_the_first_run_with_a_problem(lab: Lab) -> None:
    """Plan: the runs not yet examined stay `running` for the next invocation."""
    break_a_missing_local(lab)
    seed_crashed_run(lab, lab.B, local_only=())

    outcome = call(lab, fresh(lab, 1, 2))

    assert_not_started(outcome)
    assert lab.database.runs[lab.A].status is RunStatus.FAILED
    assert lab.database.runs[lab.B].status is RunStatus.RUNNING
    assert lab.event_types(lab.B) == []


# === closed_run (AC11) =======================================================


def test_closed_run_a_second_run_adds_nothing_to_the_earlier_run(lab: Lab) -> None:
    """AC11: A's events and observations are the same after B resumed it."""
    seed_run(lab, lab.A, pages=(1, 2))
    lab.seed.failed_page(lab.A, 3, 3)
    before = lab.database.run_state(lab.A)

    outcome = call(lab, resume(lab.A))

    assert outcome.end is IngestEnd.SUCCEEDED
    assert lab.database.run_state(lab.A) == before
    assert lab.details(created(outcome), "run-started")[0]["resumes"] == lab.A


def test_closed_run_a_refused_resumption_adds_nothing_to_any_run(lab: Lab) -> None:
    """AC11: an AC24 refusal leaves every run as it was."""
    seed_run(lab, lab.A, resumes=lab.ABSENT, first_page=3, pages=(3,))
    seed_run(lab, lab.B, pages=(1, 2))
    before = lab.snapshot()

    outcome = call(lab, resume(lab.A))

    assert_not_started(outcome)
    assert lab.snapshot() == before


def test_closed_run_a_new_ingest_leaves_a_finished_run_untouched(lab: Lab) -> None:
    seed_run(lab, lab.A, pages=(1, 2))
    lab.seed.failed_page(lab.A, 3, 3)
    before = lab.database.run_state(lab.A)

    outcome = call(lab, fresh(lab, 1, 2))

    assert outcome.end is IngestEnd.SUCCEEDED
    assert lab.database.run_state(lab.A) == before


# === identity (AC12) =========================================================


def test_identity_skips_an_id_the_repository_knows_or_the_store_lists(lab: Lab) -> None:
    """AC12: a known id, then a listed one, then a free one -> `start_run` once."""
    lab.seed.run(lab.C, scope=lab.scope(1, 2))
    lab.seed.page(lab.D, 1, 1, postgres=False, event=False)
    lab.script_ids(lab.C, lab.D, FREE_ID)

    outcome = call(lab, fresh(lab, 1, 2))

    assert outcome.end is IngestEnd.SUCCEEDED
    assert outcome.execution_id == FREE_ID
    assert lab.execution_ids.drawn == [lab.C, lab.D, FREE_ID]
    assert written(lab, "start_run") == [("start_run", FREE_ID, "")]


def test_identity_three_taken_ids_end_the_call_without_a_run(lab: Lab) -> None:
    lab.seed.run(lab.C, scope=lab.scope(1, 2))
    lab.seed.run(lab.A, scope=lab.scope(1, 2))
    lab.seed.page(lab.D, 1, 1, postgres=False, event=False)
    lab.script_ids(lab.C, lab.D, lab.A)
    before = lab.snapshot()

    outcome = call(lab, fresh(lab, 1, 2))

    assert_not_started(outcome)
    assert len(lab.execution_ids.drawn) == 3
    assert written(lab, "start_run") == []
    assert lab.snapshot() == before
    assert lab.source.requests == []
    assert lab.opener.all_closed


@pytest.mark.parametrize(
    "bad_id",
    [
        "Synthetic_Id",
        "con",
        "lpt1",
        "synthetic-exec-001",
        "ingest-20261017t150000z-ABCDEF12",
        "ingest-20261017t150000z-0a1b2c3",
        "ingest-20261017t150000z-0a1b2c3d\n",
    ],
)
def test_identity_an_id_that_breaks_the_rule_is_never_used(
    lab: Lab, bad_id: str
) -> None:
    """AC12: the id must match the ingest form and avoid reserved names."""
    lab.script_ids(bad_id)

    outcome = call(lab, fresh(lab, 1, 2))

    assert_not_started(outcome)
    assert written(lab, "start_run") == []
    assert lab.database.runs == {}
    assert lab.source.requests == []


def test_identity_the_id_is_drawn_with_the_start_time_the_run_records(lab: Lab) -> None:
    outcome, run_id = two_pages(lab)

    assert lab.execution_ids.drawn_at == [lab.database.runs[run_id].started_at]
    assert outcome.end is IngestEnd.SUCCEEDED


def test_identity_every_time_written_comes_from_the_one_clock(lab: Lab) -> None:
    """AC12: started, finished, event and capture times, all with a UTC offset."""
    _, run_id = two_pages(lab)

    run = lab.database.runs[run_id]
    assert run.finished_at is not None
    times = [run.started_at, run.finished_at]
    times += [event.occurred_at for event in lab.events(run_id)]
    times += [
        observation.captured_at
        for (stored_id, _), observation in lab.database.observations.items()
        if stored_id == run_id
    ]
    assert len(times) == 7
    for moment in times:
        assert moment.utcoffset() is not None
        assert moment in lab.clock.issued


def test_identity_sequences_number_the_responses_from_one_without_gaps(
    lab: Lab,
) -> None:
    run_id = created(call(lab, fresh(lab, 1, 3)))

    assert lab.sequences(run_id) == (1, 2, 3)
    assert lab.local_sequences(run_id) == (1, 2, 3)


def test_identity_no_id_is_drawn_without_the_exclusion(lab: Lab) -> None:
    """AC12: the check and `start_run` happen under the exclusion, never without it."""
    lab.database.hold_exclusion_elsewhere()

    outcome = call(lab, fresh(lab, 1, 2))

    assert_not_started(outcome)
    assert written(lab, "start_run") == []
    assert lab.execution_ids.drawn == []


# === chain (AC24, decision P-4) ==============================================


@dataclass(frozen=True)
class ChainCase:
    """A resumption chain that exists but is cyclic, malformed or contradictory."""

    build: Callable[[Lab], str]


def chain_link_to_no_run(lab: Lab) -> str:
    seed_run(lab, lab.A, resumes=lab.ABSENT, first_page=3, pages=(3,))
    return lab.A


def chain_cycle(lab: Lab) -> str:
    seed_run(lab, lab.A, resumes=lab.B)
    seed_run(lab, lab.B, resumes=lab.A)
    return lab.A


def chain_without_run_started(lab: Lab) -> str:
    lab.seed.run(lab.A, scope=lab.scope(1, 4))
    return lab.A


def chain_with_two_run_started(lab: Lab) -> str:
    seed_run(lab, lab.A, pages=(1,))
    lab.seed.started(lab.A)
    return lab.A


def chain_with_a_run_started_detail(
    detail: Mapping[str, JsonValue],
) -> Callable[[Lab], str]:
    def build(lab: Lab) -> str:
        lab.seed.run(lab.A, scope=lab.scope(1, 4))
        lab.seed.event(lab.A, "run-started", detail)
        return lab.A

    return build


def chain_with_another_scope(lab: Lab) -> str:
    other = dataclasses.replace(lab.scope(1, 4), buyer="ANOTHER SYNTHETIC BUYER S.A.")
    lab.seed.run(lab.B, scope=other)
    lab.seed.started(lab.B)
    seed_run(lab, lab.A, resumes=lab.B, first_page=1)
    return lab.A


def chain_page_completed_without_a_postgresql_observation(lab: Lab) -> str:
    seed_run(lab, lab.A)
    lab.seed.page(lab.A, 1, 1, postgres=False)
    return lab.A


def chain_page_completed_without_a_local_observation(lab: Lab) -> str:
    seed_run(lab, lab.A)
    lab.seed.page(lab.A, 1, 1, local=False)
    return lab.A


def chain_page_completed_for_a_429_observation(lab: Lab) -> str:
    seed_run(lab, lab.A)
    lab.seed.page(lab.A, 1, 1, status=429)
    return lab.A


def chain_page_completed_with_another_content_hash(lab: Lab) -> str:
    seed_run(lab, lab.A)
    lab.seed.page(lab.A, 1, 1, event_hash="0" * 64)
    return lab.A


def chain_page_completed_naming_a_missing_sequence(lab: Lab) -> str:
    seed_run(lab, lab.A)
    lab.seed.event(lab.A, "page-completed", completed_detail(1, 7, lab.body(1)))
    return lab.A


def chain_page_completed_with_an_extra_key(lab: Lab) -> str:
    seed_run(lab, lab.A)
    observation = lab.seed.page(lab.A, 1, 1, event=False)
    detail = completed_detail(1, 1, lab.body(1))
    detail["note"] = observation.content_hash.hexdigest[:4]
    lab.seed.event(lab.A, "page-completed", detail)
    return lab.A


def chain_page_completed_outside_the_scope(lab: Lab) -> str:
    seed_run(lab, lab.A)
    lab.seed.page(lab.A, 9, 1)
    return lab.A


def chain_with_a_succeeded_run_in_the_middle(lab: Lab) -> str:
    seed_run(lab, lab.B, pages=(1, 2, 3, 4), status=RunStatus.SUCCEEDED)
    seed_run(lab, lab.A, resumes=lab.B, first_page=5)
    return lab.A


def chain_fresh_run_with_another_first_page(lab: Lab) -> str:
    seed_run(lab, lab.A, first_page=2)
    return lab.A


def chain_resumption_with_first_page(first_page: int) -> Callable[[Lab], str]:
    def build(lab: Lab) -> str:
        seed_run(lab, lab.A, pages=(1, 2))
        seed_run(lab, lab.B, resumes=lab.A, first_page=first_page)
        return lab.B

    return build


def chain_sentinel_run_holding_a_page_completed(lab: Lab) -> str:
    seed_run(lab, lab.A, pages=(1, 2, 3, 4))
    seed_run(lab, lab.B, resumes=lab.A, first_page=5)
    lab.seed.page(lab.B, 4, 1)
    return lab.B


def chain_sentinel_run_holding_a_page_failed(lab: Lab) -> str:
    seed_run(lab, lab.A, pages=(1, 2, 3, 4))
    seed_run(lab, lab.B, resumes=lab.A, first_page=5)
    lab.seed.event(
        lab.B,
        "page-failed",
        {"page": 4, "sequence": None, "failure": "transport", "status": None},
    )
    return lab.B


BROKEN_CHAINS = [
    pytest.param(chain_link_to_no_run, id="link-to-no-run"),
    pytest.param(chain_cycle, id="cycle"),
    pytest.param(chain_without_run_started, id="no-run-started"),
    pytest.param(chain_with_two_run_started, id="two-run-started"),
    pytest.param(
        chain_with_a_run_started_detail({"first_page": 1}), id="detail-no-link"
    ),
    pytest.param(
        chain_with_a_run_started_detail({"resumes": None}), id="detail-no-first-page"
    ),
    pytest.param(
        chain_with_a_run_started_detail(
            {"resumes": None, "first_page": 1, "note": "x"}
        ),
        id="detail-extra-key",
    ),
    pytest.param(
        chain_with_a_run_started_detail({"resumes": 7, "first_page": 1}),
        id="detail-link-int",
    ),
    pytest.param(
        chain_with_a_run_started_detail({"resumes": "Synthetic_Id", "first_page": 1}),
        id="detail-link-bad-id",
    ),
    pytest.param(
        chain_with_a_run_started_detail({"resumes": None, "first_page": "1"}),
        id="detail-first-page-text",
    ),
    pytest.param(
        chain_with_a_run_started_detail({"resumes": None, "first_page": True}),
        id="detail-first-page-bool",
    ),
    pytest.param(chain_with_another_scope, id="other-buyer-in-the-chain"),
    pytest.param(
        chain_page_completed_without_a_postgresql_observation,
        id="completed-without-postgresql-observation",
    ),
    pytest.param(
        chain_page_completed_without_a_local_observation,
        id="completed-without-local-observation",
    ),
    pytest.param(
        chain_page_completed_for_a_429_observation, id="completed-for-a-429-observation"
    ),
    pytest.param(
        chain_page_completed_with_another_content_hash, id="completed-other-hash"
    ),
    pytest.param(
        chain_page_completed_naming_a_missing_sequence, id="completed-missing-sequence"
    ),
    pytest.param(chain_page_completed_with_an_extra_key, id="completed-extra-key"),
    pytest.param(
        chain_page_completed_outside_the_scope, id="completed-outside-the-range"
    ),
    pytest.param(
        chain_with_a_succeeded_run_in_the_middle, id="succeeded-in-the-middle"
    ),
    pytest.param(chain_fresh_run_with_another_first_page, id="fresh-first-page"),
    pytest.param(chain_resumption_with_first_page(0), id="first-page-0"),
    pytest.param(chain_resumption_with_first_page(4), id="first-page-unjustified"),
    pytest.param(chain_resumption_with_first_page(5), id="first-page-sentinel-early"),
    pytest.param(chain_resumption_with_first_page(6), id="first-page-last-plus-2"),
    pytest.param(
        chain_sentinel_run_holding_a_page_completed, id="sentinel-with-page-completed"
    ),
    pytest.param(
        chain_sentinel_run_holding_a_page_failed, id="sentinel-with-page-failed"
    ),
]


@pytest.mark.parametrize("build", BROKEN_CHAINS)
def test_chain_a_broken_chain_ends_not_started_and_names_the_target(
    lab: Lab, build: Callable[[Lab], str]
) -> None:
    """AC24: cyclic, malformed or contradictory -> NOT_STARTED, no run."""
    target = build(lab)

    outcome = call(lab, resume(target))

    assert_not_started(outcome)
    assert target in outcome.message
    assert lab.execution_ids.drawn == []
    assert lab.reporter.started == []
    assert lab.opener.all_closed


@pytest.mark.parametrize("build", BROKEN_CHAINS)
def test_chain_a_broken_chain_requests_nothing_and_starts_no_run(
    lab: Lab, build: Callable[[Lab], str]
) -> None:
    target = build(lab)

    call(lab, resume(target))

    assert lab.source.requests == []
    assert written(lab, "start_run") == []


@pytest.mark.parametrize("build", BROKEN_CHAINS)
def test_chain_a_broken_chain_adds_nothing_to_any_run(
    lab: Lab, build: Callable[[Lab], str]
) -> None:
    target = build(lab)
    before = lab.snapshot()

    call(lab, resume(target))

    assert lab.snapshot() == before


def test_chain_a_running_target_is_closed_by_reconciliation_before_its_chain_is_refused(
    lab: Lab,
) -> None:
    """AC24: the only additions are those of reconciliation, which runs first."""
    seed_run(
        lab,
        lab.A,
        resumes=lab.ABSENT,
        first_page=3,
        pages=(3,),
        status=RunStatus.RUNNING,
    )
    events_before = lab.event_types(lab.A)

    outcome = call(lab, resume(lab.A))

    assert_not_started(outcome)
    assert lab.database.runs[lab.A].status is RunStatus.FAILED
    assert lab.event_types(lab.A) == [*events_before, "run-closed-by-reconciliation"]
    assert same_json(
        lab.details(lab.A, "run-closed-by-reconciliation")[0],
        {"reconciled_observations": 0},
    )
    assert list(lab.database.runs) == [lab.A]


# === chain_last_page (AC24, validation of `last-page-reached`) ===============


def base_chain(lab: Lab) -> None:
    """Run A, scope 1 to 4, `failed`, with `page-completed` for pages 1 and 2."""
    seed_run(lab, lab.A, pages=(1, 2))


def reached(detail: Mapping[str, JsonValue]) -> Callable[[Lab], str]:
    def build(lab: Lab) -> str:
        base_chain(lab)
        lab.seed.event(lab.A, "last-page-reached", detail)
        return lab.A

    return build


def reached_twice_in_one_run(lab: Lab) -> str:
    base_chain(lab)
    lab.seed.last_page(lab.A, 2, 2)
    lab.seed.last_page(lab.A, 2, 2)
    return lab.A


def reached_in_two_runs(lab: Lab) -> str:
    base_chain(lab)
    lab.seed.last_page(lab.A, 2, 2)
    seed_run(lab, lab.B, resumes=lab.A, first_page=5)
    lab.seed.last_page(lab.B, 2, 2)
    return lab.B


def reached_without_a_page_completed(lab: Lab) -> str:
    base_chain(lab)
    lab.seed.last_page(lab.A, 3, 3)
    return lab.A


def reached_before_its_page_completed(lab: Lab) -> str:
    base_chain(lab)
    lab.seed.last_page(lab.A, 3, 3)
    lab.seed.completed(lab.A, 3, first_sequence=3)
    return lab.A


def reached_then_a_page_completed(lab: Lab) -> str:
    base_chain(lab)
    lab.seed.last_page(lab.A, 2, 2)
    lab.seed.completed(lab.A, 3, first_sequence=3)
    return lab.A


def reached_then_a_page_failed(lab: Lab) -> str:
    base_chain(lab)
    lab.seed.last_page(lab.A, 2, 2)
    lab.seed.failed_page(lab.A, 3, 3)
    return lab.A


def reached_with_the_page_completed_by_another_run(lab: Lab) -> str:
    """Pages 1 and 2 were completed by A, but B holds the event for page 2."""
    base_chain(lab)
    seed_run(lab, lab.B, resumes=lab.A, first_page=3)
    lab.seed.last_page(lab.B, 2, 2)
    return lab.B


def reached_with_pages_not_covered(lab: Lab) -> str:
    """Scope 1 to 4: pages 1 and 4 completed, the event for page 4, no 2 or 3."""
    seed_run(lab, lab.A)
    lab.seed.page(lab.A, 1, 1)
    lab.seed.page(lab.A, 4, 2)
    lab.seed.last_page(lab.A, 4, 4)
    return lab.A


INVALID_REACHED = [
    pytest.param(reached({"page": 2}), id="missing-key"),
    pytest.param(reached({"page": 2, "pages": 2, "note": 1}), id="extra-key"),
    pytest.param(reached({"page": True, "pages": 1}), id="page-bool"),
    pytest.param(reached({"page": 2, "pages": False}), id="pages-bool"),
    pytest.param(reached({"page": 5, "pages": 2}), id="page-above-last-page"),
    pytest.param(reached({"page": 2, "pages": 3}), id="page-below-pages"),
    pytest.param(reached({"page": 2, "pages": -1}), id="negative-pages"),
    pytest.param(reached_twice_in_one_run, id="two-in-one-run"),
    pytest.param(reached_in_two_runs, id="one-in-each-of-two-runs"),
    pytest.param(reached_without_a_page_completed, id="no-page-completed-for-it"),
    pytest.param(reached_before_its_page_completed, id="page-completed-only-after"),
    pytest.param(reached_then_a_page_completed, id="followed-by-page-completed"),
    pytest.param(reached_then_a_page_failed, id="followed-by-page-failed"),
    pytest.param(
        reached_with_the_page_completed_by_another_run,
        id="page-completed-by-another-run",
    ),
    pytest.param(reached_with_pages_not_covered, id="pages-not-covered"),
]


@pytest.mark.parametrize("build", INVALID_REACHED)
def test_chain_last_page_an_invalid_event_ends_not_started_and_skips_no_page(
    lab: Lab, build: Callable[[Lab], str]
) -> None:
    """AC24: an invalid `last-page-reached` makes the chain malformed (exit 1)."""
    target = build(lab)

    outcome = call(lab, resume(target))

    assert_not_started(outcome)
    assert target in outcome.message
    assert lab.source.requests == []
    assert written(lab, "start_run") == []


@pytest.mark.parametrize("build", INVALID_REACHED)
def test_chain_last_page_an_invalid_event_adds_nothing_to_any_run(
    lab: Lab, build: Callable[[Lab], str]
) -> None:
    target = build(lab)
    before = lab.snapshot()

    call(lab, resume(target))

    assert lab.snapshot() == before


def control_valid_event_then_storage_failed(lab: Lab) -> str:
    """(i) A's valid event after pages 1 and 2, followed only by `storage-failed`."""
    base_chain(lab)
    lab.seed.last_page(lab.A, 2, 2)
    lab.seed.event(
        lab.A, "storage-failed", {"page": 2, "sequence": None, "store": "postgresql"}
    )
    return lab.A


def control_event_in_the_second_run_closed_by_reconciliation(lab: Lab) -> str:
    """(ii) A: 1, 2 and failed on 3; B: 3, 4 and the event, left `running`."""
    seed_run(lab, lab.A, pages=(1, 2))
    lab.seed.failed_page(lab.A, 3, 3)
    seed_run(
        lab, lab.B, resumes=lab.A, first_page=3, pages=(3, 4), status=RunStatus.RUNNING
    )
    lab.seed.last_page(lab.B, 4, 4)
    return lab.B


def control_event_for_a_page_completed_by_the_second_run(lab: Lab) -> str:
    """(iii) A: pages 1 and 2; B: page 3 and the event for page 3."""
    base_chain(lab)
    seed_run(lab, lab.B, resumes=lab.A, first_page=3, pages=(3,))
    lab.seed.last_page(lab.B, 3, 3)
    return lab.B


VALID_REACHED = [
    pytest.param(control_valid_event_then_storage_failed, id="then-a-failure-event"),
    pytest.param(
        control_event_in_the_second_run_closed_by_reconciliation,
        id="second-run-closed-by-reconciliation",
    ),
    pytest.param(
        control_event_for_a_page_completed_by_the_second_run, id="second-run-page-3"
    ),
]


@pytest.mark.parametrize("build", VALID_REACHED)
def test_chain_last_page_a_valid_event_leaves_nothing_to_request_and_succeeds(
    lab: Lab, build: Callable[[Lab], str]
) -> None:
    """AC24 controls: not rejected; nothing requested; `first_page` 5; succeeded."""
    target = build(lab)

    outcome = call(lab, resume(target))

    assert outcome.end is IngestEnd.SUCCEEDED
    assert outcome.run_status is RunStatus.SUCCEEDED
    assert lab.source.requests == []
    assert same_json(
        lab.details(created(outcome), "run-started")[0],
        {"resumes": target, "first_page": 5},
    )
