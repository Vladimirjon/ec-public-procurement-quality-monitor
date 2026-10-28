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

The audit round 1 of 2026-10-18 added, at the end of the file (plan Revision 6):

- `interrupt_during_record` (AC7, F-01), `cleanup_read_back` (AC7, AC15, F-02);
- `interrupt_after_finish` (AC7, AC11, F-05);
- `database_refusal` (AC6 e, AC13, F-11), `reconcile_os_error` (AC10, F-10);
- `chain_unreadable_record` (AC24, F-06), `progress_line` (AC6 c, AC15, F-07).

The two tests that were vacuous (`progress_text` in `storage`, and
`text_never_reaches_the_reporter` in `unexpected`) now assert first that the
reporter received messages.

The audit round 2 of 2026-10-18 added, at the end of the file (plan Revision 7):

- `cleanup_database_error` (AC7, AC15, F-13: the K cleanup writes one line when one
  of its own database operations fails) and `final_finish_read_run` (AC8, AC15,
  F-13: the `read_run` after a refused P-2 repeat);
- `pre_run_database_error` (AC9, AC10, AC12, AC15, AC24, F-14, F-15: a database
  operation refused or lost before the run exists gives one line and a message that
  names the identity, never INVALID_TARGET);
- `repository_open_error` (AC15, F-16 a: the first `open_repository()`);
- two `connection_loss` tests for the lines of the second opening and the second
  exclusion of State machine C (required progress 2 and 3).

`test_unexpected_cleanup_that_meets_a_database_error_leaves_the_run_running` was
extended with the progress-line check (additions only).

The audit round 3 of 2026-10-18 added, at the end of the file (plan Revision 8):

- `reconnect_exclusion_interrupt` (AC7, AC8 c, AC15, F-18) and
  `reconnect_open_interrupt` (AC7, AC15, F-19): an interrupt or an exception while a
  lost connection is recovered (the second `open_repository()`, the second
  exclusion) writes nothing, reads nothing, closes the second repository and leaves
  the run `running`, with one line that names the operation that raised;
- `start_run_unconfirmed` (AC8, AC15, F-20): a lost `start_run` whose recovery fails;
- `read_back_record_failure` (AC6 b, AC6 c, AC8, AC15, F-20): the read-back path
  whose `record_observation` is refused or lost.

The first two are red against the use case of `d83cd55`; the last two protect
behavior that already holds (F-20).

The audit round 5 rework of 2026-10-20 added, at the end of the file (plan
Revisions 9 and 10; the section comment there lists the tokens): the lost
repository's close, the loss line and the closes of the second repository
(`reconnect_close_interrupt`, `reconnect_loss_line_interrupt`,
`reconnect_false_close_interrupt`, F-21), the final close (`final_close_error`,
`final_close_interrupt`, F-22), `generic_fallback` (F-20), and the sweep A2 tokens
`start_run_second_loss`, `unexpected_cleanup_interrupt`, `recovery_double_fault` and
`refusal_not_retried`.

The audit round 6 rework of 2026-10-23 added, at the end of the file (outcome O10,
plan Revision 12, finding F-28; the section comment there explains them):
`system_exit_first_wins`, `window_system_exit_line` and `cleanup_system_exit` (AC7,
AC8 c, AC15). They protect behavior that already holds: a `SystemExit` always wins.

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
from typing import TYPE_CHECKING, Literal

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
    PersistenceConnectionError,
    PersistenceError,
    PersistenceIntegrityError,
    PersistenceNotFoundError,
)
from ec_procurement_quality.domain.raw_evidence import (
    EvidenceIntegrityError,
    EvidenceNotFoundError,
)
from ec_procurement_quality.infrastructure.local_disk_raw_evidence_store import (
    LocalDiskRawEvidenceStore,
)

if TYPE_CHECKING:
    from tests.unit.ingest.conftest import (
        Lab,
        LabState,
        ReadFaultStore,
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

    assert lab.reporter.messages, "the refusal was reported to nobody"
    assert any(
        "record_observation" in message
        and lab.reporter.started[0] in message
        and number_in(message, 1)
        for message in lab.reporter.messages
    ), lab.reporter.messages
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

    assert lab.reporter.messages, "page 1 was completed and nothing was reported"
    assert not any(BODY_MARKER in message for message in lab.reporter.messages)


def test_unexpected_cleanup_that_meets_a_database_error_leaves_the_run_running(
    lab: Lab,
) -> None:
    """Q11: best effort -> RUN_FAILED with the run still `running`, no new connection.

    AC15, K (audit round 2, F-13): the lost append gets exactly one progress line,
    naming the operation, the event type and the run, with at most the class name.
    """
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
    lines = progress_lines(
        lab, "append_audit_event", "unexpected-error", created(outcome)
    )
    assert len(lines) == 1, lab.reporter.messages
    assert_names_at_most(lines[0], PersistenceConnectionError)
    assert_clean_messages(lab)


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


# === Audit round 1 (2026-10-18), findings F-01 to F-07, F-10 and F-11 ========
#
# The tests below were written red against the Revision 6 specs after the audit of
# 2026-10-18 rejected the implementation. Tokens: `interrupt_during_record` (F-01),
# `cleanup_read_back` (F-02), `interrupt_after_finish` (F-05),
# `chain_unreadable_record` (F-06), `progress_line` (F-07), `reconcile_os_error`
# (F-10) and `database_refusal` (F-11).

REFUSAL_TEXT = "synthetic database refusal text"
REFUSALS = [PersistenceIntegrityError, PersistenceNotFoundError, PersistenceError]
Moment = Literal["before", "after"]


def number_in(text: str, number: int) -> bool:
    """`number` stands on its own in `text`: not inside a word or a content hash."""
    return re.search(rf"(?<![0-9A-Za-z]){number}(?![0-9A-Za-z])", text) is not None


def progress_lines(lab: Lab, *words: str, numbers: tuple[int, ...] = ()) -> list[str]:
    """The progress messages that hold every word and every stand-alone number."""
    return [
        message
        for message in lab.reporter.messages
        if all(word in message for word in words)
        and all(number_in(message, number) for number in numbers)
    ]


def assert_clean_messages(lab: Lab) -> None:
    """No progress message holds a marker, a URL, a traceback or an error text."""
    for message in lab.reporter.messages:
        assert not any(text in message for text in FORBIDDEN_TEXT), message
        assert REFUSAL_TEXT not in message
        assert "synthetic:" not in message


def refuse(
    lab: Lab,
    operation: str,
    error: Callable[[str], PersistenceError],
    *,
    detail: str | None = None,
    nth: int = 1,
) -> None:
    """The first repository refuses a call: nothing is delegated, nothing is written."""
    lab.opener.faults.setdefault(1, []).append(
        lab.faults.refuses(
            operation, lambda: error(REFUSAL_TEXT), detail=detail, nth=nth
        )
    )


# === interrupt_during_record (AC7, F-01) =====================================


@pytest.mark.parametrize("when", ["before", "after"])
def test_interrupt_during_record_the_cleanup_records_the_pending_observation(
    lab: Lab, when: Moment
) -> None:
    """AC7, K, P step 3: Ctrl+C while `record_observation` of sequence 2 runs.

    The observation is pending until that call has returned, so the cleanup reads
    it back from the local store and records it before it closes the run.
    """
    lab.opener.faults[1] = [
        lab.faults.interrupts("record_observation", detail="2", when=when)
    ]

    outcome = call(lab, fresh(lab, 1, 3))

    run_id = created(outcome)
    assert outcome.end is IngestEnd.INTERRUPTED
    assert outcome.run_status is RunStatus.FAILED
    assert lab.database.runs[run_id].status is RunStatus.FAILED
    assert lab.sequences(run_id) == (1, 2)
    assert lab.database.observations[(run_id, 2)] == lab.store.read_observation(
        run_id, 2
    )
    assert lab.event_types(run_id) == [
        "run-started",
        "page-completed",
        "run-interrupted",
    ]
    assert same_json(lab.details(run_id, "run-interrupted")[0], {"page": 2})
    assert lab.opener.all_closed


def test_interrupt_during_record_the_observation_is_in_postgresql_before_the_close(
    lab: Lab,
) -> None:
    """AC7: in the journal, observation 2 is recorded before `finish_run(FAILED)`."""
    lab.opener.faults[1] = [lab.faults.interrupts("record_observation", detail="2")]

    outcome = call(lab, fresh(lab, 1, 3))

    run_id = created(outcome)
    assert lab.journal.labels(run_id)[-4:] == [
        "store:2",
        "record_observation:2",
        "append:run-interrupted",
        "finish_run:failed",
    ]


def test_interrupt_during_record_the_repeat_after_a_connection_loss_is_covered(
    lab: Lab,
) -> None:
    """P step 3: pending lasts through the repeat of State machine C as well."""
    lab.opener.faults[1] = [
        lab.faults.lost_before_commit("record_observation", detail="2")
    ]
    lab.opener.faults[2] = [lab.faults.interrupts("record_observation", detail="2")]

    outcome = call(lab, fresh(lab, 1, 3))

    run_id = created(outcome)
    assert outcome.end is IngestEnd.INTERRUPTED
    assert outcome.run_status is RunStatus.FAILED
    assert lab.sequences(run_id) == (1, 2)
    assert lab.event_types(run_id) == [
        "run-started",
        "page-completed",
        "run-interrupted",
    ]
    assert lab.opener.opens == 2
    assert lab.opener.all_closed


# === cleanup_read_back (AC7, AC15, F-02) =====================================

INSIDE_STORE = [
    pytest.param(
        lambda: KeyboardInterrupt(),
        IngestEnd.INTERRUPTED,
        "run-interrupted",
        {"page": 2},
        id="keyboard-interrupt",
    ),
    pytest.param(
        lambda: MemoryError(),
        IngestEnd.RUN_FAILED,
        "unexpected-error",
        {"page": 2, "error_type": "MemoryError"},
        id="memory-error",
    ),
]


@pytest.mark.parametrize(("make_error", "end", "event_type", "detail"), INSIDE_STORE)
def test_cleanup_read_back_nothing_published_still_audits_and_closes_the_run(
    lab: Lab,
    make_error: Callable[[], BaseException],
    end: IngestEnd,
    event_type: str,
    detail: dict[str, JsonValue],
) -> None:
    """AC7, K step 2: `store` of sequence 2 is cut short before it publishes.

    The cleanup's read-back finds nothing; it records nothing for sequence 2, and
    still appends its event and closes the run. Nothing escapes `run_ingest`.
    """
    store = lab.refuses_to_store(on_call=2, error=make_error)

    outcome = call(lab, fresh(lab, 1, 3), store=store)

    run_id = created(outcome)
    assert outcome.end is end
    assert outcome.run_status is RunStatus.FAILED
    assert lab.database.runs[run_id].status is RunStatus.FAILED
    assert lab.sequences(run_id) == (1,)
    assert lab.local_sequences(run_id) == (1,)
    assert lab.event_types(run_id) == ["run-started", "page-completed", event_type]
    assert same_json(lab.details(run_id, event_type)[0], detail)
    assert lab.journal.labels(run_id)[-2:] == [
        f"append:{event_type}",
        "finish_run:failed",
    ]
    assert lab.source.requests == [1, 2]
    assert lab.opener.all_closed


@pytest.mark.parametrize("read_error", [EvidenceIntegrityError, OSError])
@pytest.mark.parametrize(("make_error", "end", "event_type", "detail"), INSIDE_STORE)
def test_cleanup_read_back_an_unreadable_record_is_absorbed_and_the_run_closed(
    lab: Lab,
    make_error: Callable[[], BaseException],
    end: IngestEnd,
    event_type: str,
    detail: dict[str, JsonValue],
    read_error: Callable[[str], BaseException],
) -> None:
    """AC7, K step 2: the file was published but the cleanup cannot read it.

    The read-back error is absorbed: sequence 2 stays out of PostgreSQL (a
    resumption requests page 2 again), and the event and the close still follow.
    """
    store = lab.fails_read_back(
        on_call=2,
        read_errors=[lambda: read_error("synthetic read-back failure")],
        publish=True,
        store_error=make_error,
    )

    outcome = call(lab, fresh(lab, 1, 3), store=store)

    run_id = created(outcome)
    assert outcome.end is end
    assert outcome.run_status is RunStatus.FAILED
    assert lab.database.runs[run_id].status is RunStatus.FAILED
    assert lab.sequences(run_id) == (1,)
    assert lab.local_sequences(run_id) == (1, 2)
    assert lab.event_types(run_id) == ["run-started", "page-completed", event_type]
    assert same_json(lab.details(run_id, event_type)[0], detail)
    assert lab.opener.all_closed


# === interrupt_after_finish (AC7, AC11, F-05) ================================


def test_interrupt_after_finish_a_succeeded_run_gets_nothing_more(lab: Lab) -> None:
    """AC11, K step 1: Ctrl+C right after `finish_run(SUCCEEDED)` committed."""
    lab.opener.faults[1] = [
        lab.faults.interrupts("finish_run", detail="succeeded", when="after")
    ]

    outcome = call(lab, fresh(lab, 1, 2))

    run_id = created(outcome)
    assert outcome.end is IngestEnd.INTERRUPTED
    assert outcome.run_status is RunStatus.SUCCEEDED
    assert lab.database.runs[run_id].status is RunStatus.SUCCEEDED
    assert lab.event_types(run_id) == [
        "run-started",
        "page-completed",
        "page-completed",
    ]
    assert lab.sequences(run_id) == (1, 2)
    assert len(lab.opener.attempts_of("finish_run")) == 1
    assert lab.opener.opens == 1
    assert lab.opener.all_closed


def test_interrupt_after_finish_a_failed_run_gets_nothing_more(lab: Lab) -> None:
    """AC11, K step 1: the same after the failure path's `finish_run(FAILED)`."""
    lab.source.script(2, lab.status_failure(2, 500))
    lab.opener.faults[1] = [
        lab.faults.interrupts("finish_run", detail="failed", when="after")
    ]

    outcome = call(lab, fresh(lab, 1, 3))

    run_id = created(outcome)
    assert outcome.end is IngestEnd.INTERRUPTED
    assert outcome.run_status is RunStatus.FAILED
    assert lab.database.runs[run_id].status is RunStatus.FAILED
    assert lab.event_types(run_id) == ["run-started", "page-completed", "page-failed"]
    assert len(lab.opener.attempts_of("finish_run")) == 1
    assert lab.opener.all_closed


def test_interrupt_after_finish_an_unexpected_exception_adds_nothing_either(
    lab: Lab,
) -> None:
    """K step 1: a `MemoryError` after the commit -> `RUN_FAILED`, stored status."""
    lab.opener.faults[1] = [
        lab.faults.raises(
            "finish_run", lambda: MemoryError(), detail="succeeded", when="after"
        )
    ]

    outcome = call(lab, fresh(lab, 1, 2))

    run_id = created(outcome)
    assert outcome.end is IngestEnd.RUN_FAILED
    assert outcome.run_status is RunStatus.SUCCEEDED
    assert lab.database.runs[run_id].status is RunStatus.SUCCEEDED
    assert lab.event_types(run_id) == [
        "run-started",
        "page-completed",
        "page-completed",
    ]
    assert len(lab.opener.attempts_of("finish_run")) == 1


def refuse_the_cleanup_read_run(lab: Lab) -> None:
    # The first `read_run` is the identity check; the second is the cleanup's.
    refuse(lab, "read_run", PersistenceError, nth=2)


def lose_the_cleanup_read_run(lab: Lab) -> None:
    lab.opener.faults[1] = [lab.faults.lost_before_commit("read_run", nth=2)]


@pytest.mark.parametrize(
    "break_read_run",
    [
        pytest.param(refuse_the_cleanup_read_run, id="refused"),
        pytest.param(lose_the_cleanup_read_run, id="lost-connection"),
    ],
)
def test_interrupt_after_finish_a_read_run_that_fails_leaves_the_run_untouched(
    lab: Lab, break_read_run: Callable[[Lab], None]
) -> None:
    """AC11, K: the cleanup cannot show the run is open -> it writes nothing."""
    lab.source.script(2, KeyboardInterrupt())
    break_read_run(lab)

    outcome = call(lab, fresh(lab, 1, 3))

    run_id = created(outcome)
    assert outcome.end is IngestEnd.INTERRUPTED
    assert outcome.run_status is RunStatus.RUNNING
    assert lab.database.runs[run_id].status is RunStatus.RUNNING
    assert lab.event_types(run_id) == ["run-started", "page-completed"]
    assert lab.sequences(run_id) == (1,)
    assert lab.opener.attempts_of("finish_run") == []
    assert lab.opener.opens == 1
    assert lab.opener.all_closed


# === chain_unreadable_record (AC24, F-06) ====================================

UNREADABLE = [EvidenceIntegrityError, EvidenceNotFoundError, OSError]


@pytest.mark.parametrize("error", UNREADABLE)
def test_chain_unreadable_record_ends_not_started_and_names_the_target(
    lab: Lab, error: Callable[[str], BaseException]
) -> None:
    """AC24, H step 2: the local record of a `page-completed` cannot be read."""
    seed_run(lab, lab.A, pages=(1, 2))
    store = lab.faulty_reads()
    store.fail_observation(lab.A, 2, lambda: error("synthetic unreadable record"))

    outcome = call(lab, resume(lab.A), store=store)

    assert_not_started(outcome)
    assert lab.A in outcome.message
    assert outcome.message != error.__name__
    if error is OSError:
        assert "synthetic unreadable record" not in outcome.message
    assert lab.execution_ids.drawn == []
    assert lab.reporter.started == []
    assert lab.opener.all_closed


@pytest.mark.parametrize("error", UNREADABLE)
def test_chain_unreadable_record_requests_nothing_and_adds_nothing_to_any_run(
    lab: Lab, error: Callable[[str], BaseException]
) -> None:
    """AC24, AC11: no request, no `start_run`, every run as it was."""
    seed_run(lab, lab.A, pages=(1, 2))
    store = lab.faulty_reads()
    store.fail_observation(lab.A, 2, lambda: error("synthetic unreadable record"))
    before = lab.snapshot()

    call(lab, resume(lab.A), store=store)

    assert lab.source.requests == []
    assert written(lab, "start_run") == []
    assert lab.snapshot() == before


# === reconcile_os_error (AC10, F-10) =========================================


def os_error_in_the_listing(lab: Lab) -> tuple[ReadFaultStore, int | None, str]:
    seed_crashed_run(lab, lab.A, local_only=())
    store = lab.faulty_reads()
    store.fail_listing(lab.A, lambda: PermissionError("synthetic listing refusal"))
    return store, None, "local-listing-failed"


def os_error_reading_a_listed_record(
    lab: Lab,
) -> tuple[ReadFaultStore, int | None, str]:
    seed_crashed_run(lab, lab.A, local_only=())
    store = lab.faulty_reads()
    store.fail_observation(lab.A, 2, lambda: PermissionError("synthetic refusal"))
    return store, 2, "local-observation-unreadable"


def a_listed_record_that_vanished(lab: Lab) -> tuple[ReadFaultStore, int | None, str]:
    seed_crashed_run(lab, lab.A, local_only=())
    store = lab.faulty_reads()
    store.fail_observation(lab.A, 2, lambda: EvidenceNotFoundError("synthetic: gone"))
    return store, 2, "local-observation-unreadable"


def os_error_reading_an_object(lab: Lab) -> tuple[ReadFaultStore, int | None, str]:
    seed_crashed_run(lab, lab.A, local_only=())
    store = lab.faulty_reads()
    content_hash = lab.store.read_observation(lab.A, 1).content_hash
    store.fail_content(content_hash, lambda: PermissionError("synthetic refusal"))
    return store, 1, "object-integrity"


RECONCILE_OS_ERRORS = [
    pytest.param(os_error_in_the_listing, id="listing"),
    pytest.param(os_error_reading_a_listed_record, id="record-os-error"),
    pytest.param(a_listed_record_that_vanished, id="record-vanished"),
    pytest.param(os_error_reading_an_object, id="object-os-error"),
]


@pytest.mark.parametrize("break_it", RECONCILE_OS_ERRORS)
def test_reconcile_os_error_is_a_problem_of_the_closed_list(
    lab: Lab, break_it: Callable[[Lab], tuple[ReadFaultStore, int | None, str]]
) -> None:
    """AC10, R: `reconciliation-failed`, run `failed`, no new run; nothing escapes."""
    store, sequence, problem = break_it(lab)

    outcome = call(lab, fresh(lab, 1, 2), store=store)

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
    assert written(lab, "start_run") == []
    assert lab.source.requests == []
    assert lab.reporter.started == []
    assert_follows_catalogue(lab.events(lab.A))
    assert lab.opener.all_closed


# === database_refusal (AC6 e, AC13, F-11) ====================================


def assert_refusal_audit(lab: Lab, run_id: str) -> None:
    """Catalogue values only, never `unexpected-error`, one `postgresql` failure."""
    events = lab.events(run_id)
    assert_follows_catalogue(events)
    assert "unexpected-error" not in [event.event_type for event in events]
    postgresql_failures = [
        detail
        for detail in lab.details(run_id, "storage-failed")
        if detail["store"] == "postgresql"
    ]
    assert len(postgresql_failures) <= 1


@pytest.mark.parametrize("error", REFUSALS)
def test_database_refusal_of_start_run_ends_not_started_with_no_run(
    lab: Lab, error: Callable[[str], PersistenceError]
) -> None:
    """P "Refused writes": nothing is written and the run is never announced."""
    lab.script_ids(FREE_ID)
    refuse(lab, "start_run", error)

    outcome = call(lab, fresh(lab, 1, 2))

    assert_not_started(outcome)
    assert lab.reporter.started == []
    assert lab.database.runs == {}
    assert lab.source.requests == []
    assert lab.opener.opens == 1
    assert lab.opener.all_closed
    assert progress_lines(lab, "start_run", FREE_ID)
    assert_clean_messages(lab)


# What each refused normal-path write leaves behind: the operation and detail of the
# fault, `pages` of the source for page 1, the events the run holds, and the page and
# sequence of the one `storage-failed` (`postgresql`).
NORMAL_REFUSALS = [
    pytest.param(
        "append_audit_event",
        "run-started",
        None,
        ["storage-failed"],
        1,
        None,
        [],
        id="run-started",
    ),
    pytest.param(
        "append_audit_event",
        "page-completed",
        None,
        ["run-started", "storage-failed"],
        1,
        1,
        [1],
        id="page-completed",
    ),
    pytest.param(
        "append_audit_event",
        "last-page-reached",
        1,
        ["run-started", "page-completed", "storage-failed"],
        1,
        1,
        [1],
        id="last-page-reached",
    ),
    pytest.param(
        "finish_run",
        "succeeded",
        None,
        ["run-started", "page-completed", "page-completed", "storage-failed"],
        2,
        None,
        [1, 2],
        id="final-finish-at-the-end-of-the-range",
    ),
    pytest.param(
        "finish_run",
        "succeeded",
        1,
        ["run-started", "page-completed", "last-page-reached", "storage-failed"],
        1,
        None,
        [1],
        id="final-finish-after-last-page-reached",
    ),
]


@pytest.mark.parametrize(
    ("operation", "detail", "pages", "events", "page", "sequence", "requests"),
    NORMAL_REFUSALS,
)
@pytest.mark.parametrize("error", REFUSALS)
def test_database_refusal_of_a_normal_path_write_adds_one_failure_and_closes_failed(
    lab: Lab,
    error: Callable[[str], PersistenceError],
    operation: str,
    detail: str,
    pages: int | None,
    events: list[str],
    page: int,
    sequence: int | None,
    requests: list[int],
) -> None:
    """P "Refused writes": `storage-failed` (`postgresql`) once, then `finish_run`."""
    lab.script_ids(FREE_ID)
    if pages is not None:
        lab.source.script(1, lab.ok(1, pages=pages))
    refuse(lab, operation, error, detail=detail)

    outcome = call(lab, fresh(lab, 1, 2))

    assert outcome.end is IngestEnd.RUN_FAILED
    assert outcome.run_status is RunStatus.FAILED
    assert outcome.execution_id == FREE_ID
    assert lab.database.runs[FREE_ID].status is RunStatus.FAILED
    assert lab.event_types(FREE_ID) == events
    assert same_json(
        lab.details(FREE_ID, "storage-failed")[0],
        {"page": page, "sequence": sequence, "store": "postgresql"},
    )
    assert lab.journal.labels(FREE_ID)[-2:] == [
        "append:storage-failed",
        "finish_run:failed",
    ]
    assert lab.source.requests == requests
    assert lab.opener.opens == 1
    assert lab.opener.all_closed
    assert_refusal_audit(lab, FREE_ID)
    words = (operation, detail) if operation == "append_audit_event" else (operation,)
    assert progress_lines(lab, *words, FREE_ID)
    assert_clean_messages(lab)


@pytest.mark.parametrize("error", REFUSALS)
def test_database_refusal_of_the_final_finish_closes_with_a_new_clock_reading(
    lab: Lab, error: Callable[[str], PersistenceError]
) -> None:
    """P "Refused writes": `finish_run(FAILED)` carries a new `finished_at`."""
    refuse(lab, "finish_run", error, detail="succeeded")

    outcome = call(lab, fresh(lab, 1, 2))

    run_id = created(outcome)
    attempts = lab.opener.attempts_of("finish_run")
    assert [attempt.detail for attempt in attempts] == ["succeeded", "failed"]
    assert attempts[1].args[2] != attempts[0].args[2]
    assert lab.database.runs[run_id].finished_at == attempts[1].args[2]


@pytest.mark.parametrize("error", REFUSALS)
def test_database_refusal_of_page_failed_adds_no_further_event(
    lab: Lab, error: Callable[[str], PersistenceError]
) -> None:
    """P "Refused writes": a refused failure-path append -> `finish_run(FAILED)`."""
    lab.script_ids(FREE_ID)
    lab.source.script(2, lab.status_failure(2, 500))
    refuse(lab, "append_audit_event", error, detail="page-failed")

    outcome = call(lab, fresh(lab, 1, 3))

    assert outcome.end is IngestEnd.RUN_FAILED
    assert outcome.run_status is RunStatus.FAILED
    assert lab.event_types(FREE_ID) == ["run-started", "page-completed"]
    assert lab.sequences(FREE_ID) == (1, 2)
    assert lab.journal.labels(FREE_ID)[-1:] == ["finish_run:failed"]
    assert lab.source.requests == [1, 2]
    assert_refusal_audit(lab, FREE_ID)
    assert progress_lines(lab, "append_audit_event", "page-failed", FREE_ID)
    assert_clean_messages(lab)


@pytest.mark.parametrize("error", REFUSALS)
def test_database_refusal_of_the_storage_failed_answer_adds_no_further_event(
    lab: Lab, error: Callable[[str], PersistenceError]
) -> None:
    """P "Refused writes": no event answers a refused `storage-failed` append."""
    lab.script_ids(FREE_ID)
    refuse(lab, "record_observation", error, detail="1")
    refuse(lab, "append_audit_event", error, detail="storage-failed")

    outcome = call(lab, fresh(lab, 1, 3))

    assert outcome.end is IngestEnd.RUN_FAILED
    assert outcome.run_status is RunStatus.FAILED
    assert lab.event_types(FREE_ID) == ["run-started"]
    assert lab.journal.labels(FREE_ID)[-1:] == ["finish_run:failed"]
    assert lab.source.requests == [1]
    assert_refusal_audit(lab, FREE_ID)
    assert progress_lines(lab, "record_observation", FREE_ID, numbers=(1,))
    assert progress_lines(lab, "append_audit_event", "storage-failed", FREE_ID)
    assert_clean_messages(lab)


def source_fails_page_two(lab: Lab) -> None:
    lab.source.script(2, lab.status_failure(2, 500))


def refuse_the_record_of_page_one(lab: Lab) -> None:
    refuse(lab, "record_observation", PersistenceIntegrityError, detail="1")


@pytest.mark.parametrize(
    ("setup", "events"),
    [
        pytest.param(
            source_fails_page_two,
            ["run-started", "page-completed", "page-failed"],
            id="after-page-failed",
        ),
        pytest.param(
            refuse_the_record_of_page_one,
            ["run-started", "storage-failed"],
            id="after-storage-failed",
        ),
    ],
)
@pytest.mark.parametrize("error", REFUSALS)
def test_database_refusal_of_the_failing_finish_leaves_the_run_running(
    lab: Lab,
    error: Callable[[str], PersistenceError],
    setup: Callable[[Lab], None],
    events: list[str],
) -> None:
    """P "Refused writes": nothing more is written; AC10 closes it next time."""
    lab.script_ids(FREE_ID)
    setup(lab)
    refuse(lab, "finish_run", error, detail="failed")

    outcome = call(lab, fresh(lab, 1, 3))

    assert outcome.end is IngestEnd.RUN_FAILED
    assert outcome.run_status is RunStatus.RUNNING
    assert outcome.execution_id == FREE_ID
    assert lab.database.runs[FREE_ID].status is RunStatus.RUNNING
    assert lab.event_types(FREE_ID) == events
    assert len(lab.opener.attempts_of("finish_run", "failed")) == 1
    assert lab.opener.opens == 1
    assert lab.opener.all_closed
    assert_refusal_audit(lab, FREE_ID)
    assert progress_lines(lab, "finish_run", FREE_ID)
    assert_clean_messages(lab)


@pytest.mark.parametrize("error", REFUSALS)
def test_database_refusal_of_a_reconciled_observation_is_a_conflict(
    lab: Lab, error: Callable[[str], PersistenceError]
) -> None:
    """R step 5: any refusal of `record_observation` is a PostgreSQL conflict."""
    seed_crashed_run(lab, lab.A, local_only=(3,))
    refuse(lab, "record_observation", error, detail="3")

    outcome = call(lab, fresh(lab, 1, 2))

    assert_not_started(outcome)
    assert lab.event_types(lab.A) == ["reconciliation-failed"]
    assert same_json(
        lab.details(lab.A, "reconciliation-failed")[0],
        {"sequence": 3, "problem": "postgresql-observation-conflict"},
    )
    assert lab.database.runs[lab.A].status is RunStatus.FAILED
    assert list(lab.database.runs) == [lab.A]
    assert lab.sequences(lab.A) == (1, 2)
    assert lab.source.requests == []
    assert_refusal_audit(lab, lab.A)
    assert progress_lines(lab, "record_observation", lab.A, numbers=(3,))
    assert_clean_messages(lab)


def reconcile_with_a_local_only_observation(lab: Lab) -> None:
    seed_crashed_run(lab, lab.A, local_only=(3,))


def reconcile_to_a_clean_close(lab: Lab) -> None:
    seed_crashed_run(lab, lab.A, local_only=())


def reconcile_to_a_problem(lab: Lab) -> None:
    break_a_missing_local(lab)


# What a refused reconciliation write leaves in run A: the setup, the refused
# operation and detail, and the events A holds afterwards. A stays `running`.
RECONCILE_REFUSALS = [
    pytest.param(
        reconcile_with_a_local_only_observation,
        "append_audit_event",
        "observation-reconciled",
        [],
        id="observation-reconciled",
    ),
    pytest.param(
        reconcile_to_a_clean_close,
        "append_audit_event",
        "run-closed-by-reconciliation",
        [],
        id="run-closed-by-reconciliation",
    ),
    pytest.param(
        reconcile_to_a_clean_close,
        "finish_run",
        "failed",
        ["run-closed-by-reconciliation"],
        id="finish-after-the-close-event",
    ),
    pytest.param(
        reconcile_to_a_problem,
        "append_audit_event",
        "reconciliation-failed",
        [],
        id="reconciliation-failed",
    ),
    pytest.param(
        reconcile_to_a_problem,
        "finish_run",
        "failed",
        ["reconciliation-failed"],
        id="finish-after-reconciliation-failed",
    ),
    pytest.param(
        reconcile_to_a_clean_close,
        "list_observations",
        None,
        [],
        id="list-observations",
    ),
]


@pytest.mark.parametrize(("setup", "operation", "detail", "events"), RECONCILE_REFUSALS)
@pytest.mark.parametrize("error", REFUSALS)
def test_database_refusal_during_reconciliation_writes_nothing_more_to_the_run(
    lab: Lab,
    error: Callable[[str], PersistenceError],
    setup: Callable[[Lab], None],
    operation: str,
    detail: str | None,
    events: list[str],
) -> None:
    """R: a refusal -> `NOT_STARTED` naming the run; the run stays as it was."""
    setup(lab)
    refuse(lab, operation, error, detail=detail)

    outcome = call(lab, fresh(lab, 1, 2))

    assert_not_started(outcome)
    assert lab.A in outcome.message
    assert lab.event_types(lab.A) == events
    assert lab.database.runs[lab.A].status is RunStatus.RUNNING
    assert list(lab.database.runs) == [lab.A]
    assert lab.source.requests == []
    assert lab.reporter.started == []
    assert written(lab, "start_run") == []
    assert_refusal_audit(lab, lab.A)
    words = (operation, detail) if operation == "append_audit_event" else (operation,)
    assert progress_lines(lab, *[word for word in words if word], lab.A)
    assert_clean_messages(lab)
    assert lab.opener.all_closed


@pytest.mark.parametrize("error", REFUSALS)
def test_database_refusal_of_list_runs_ends_not_started_and_writes_nothing(
    lab: Lab, error: Callable[[str], PersistenceError]
) -> None:
    """R: a refused `list_runs` -> `NOT_STARTED`, no run, nothing written."""
    seed_crashed_run(lab, lab.A, local_only=())
    refuse(lab, "list_runs", error)
    before = lab.snapshot()

    outcome = call(lab, fresh(lab, 1, 2))

    assert_not_started(outcome)
    assert lab.snapshot() == before
    assert lab.source.requests == []
    assert lab.opener.all_closed


# === progress_line (AC6 c, AC15, F-07) =======================================


def test_progress_line_each_page_names_its_page_sequence_status_and_hash(
    lab: Lab,
) -> None:
    """Required progress 1: the page is not the sequence, so both must show."""
    outcome = call(lab, fresh(lab, 3, 4))

    run_id = created(outcome)
    for page, sequence in ((3, 1), (4, 2)):
        observation = lab.database.observations[(run_id, sequence)]
        assert progress_lines(
            lab, observation.content_hash.hexdigest, numbers=(page, sequence, 200)
        ), (page, sequence, lab.reporter.messages)
    assert_clean_messages(lab)


def test_progress_line_a_failed_page_with_a_response_names_status_and_hash(
    lab: Lab,
) -> None:
    """Required progress 1: a stored response is named even when the page failed."""
    lab.source.script(4, lab.status_failure(4, 429, HTML_429))

    outcome = call(lab, fresh(lab, 3, 4))

    observation = lab.database.observations[(created(outcome), 2)]
    assert progress_lines(
        lab, observation.content_hash.hexdigest, numbers=(4, 2, 429)
    ), lab.reporter.messages
    assert_clean_messages(lab)


def test_progress_line_a_page_without_a_response_is_named_without_a_hash(
    lab: Lab,
) -> None:
    """Required progress 1: `page 4 no response`: the page, and nothing stored."""
    lab.source.script(4, lab.failure_without_response())

    call(lab, fresh(lab, 3, 4))

    lines = [
        message
        for message in lab.reporter.messages
        if number_in(message, 4) and re.search(r"[0-9a-f]{64}", message) is None
    ]
    assert lines, lab.reporter.messages
    assert_clean_messages(lab)


@pytest.mark.parametrize("error", REFUSALS)
def test_progress_line_a_refused_observation_names_the_operation_and_identity(
    lab: Lab, error: Callable[[str], PersistenceError]
) -> None:
    """AC6 (c): operation and identity (run, sequence); at most the class name."""
    lab.script_ids(FREE_ID)
    refuse(lab, "record_observation", error, detail="1")

    call(lab, fresh(lab, 1, 3))

    assert progress_lines(lab, "record_observation", FREE_ID, numbers=(1,)), (
        lab.reporter.messages
    )
    assert_clean_messages(lab)


@pytest.mark.parametrize(
    ("operation", "detail"),
    [
        pytest.param("start_run", None, id="start_run"),
        pytest.param("record_observation", "2", id="record_observation"),
        pytest.param("append_audit_event", "page-completed", id="append_audit_event"),
        pytest.param("finish_run", "succeeded", id="finish_run"),
    ],
)
def test_progress_line_a_lost_connection_names_the_operation_and_the_run(
    lab: Lab, operation: str, detail: str | None
) -> None:
    """Required progress 3: each loss from `start_run` on is reported on stderr."""
    lab.script_ids(FREE_ID)
    lost_at(lab, operation, detail, "before")

    call(lab, fresh(lab, 1, 2))

    assert progress_lines(lab, operation, FREE_ID), lab.reporter.messages
    assert_clean_messages(lab)


# === Audit round 2 (2026-10-18), findings F-13 to F-16 =======================
#
# Written red against the Revision 7 specs. Tokens: `cleanup_database_error` and
# `final_finish_read_run` (F-13), `pre_run_database_error` (F-14, F-15) and
# `repository_open_error` (F-16 a). The extended test of F-13 is
# `test_unexpected_cleanup_that_meets_a_database_error_leaves_the_run_running`.
# The `connection_loss` tests of the second opening and the second exclusion follow
# plan § Public names (required progress 2 and 3) and § State machine C steps 2, 3.

DB_ERRORS = [PersistenceIntegrityError, PersistenceError, PersistenceConnectionError]
INVALID_WORDS = ("invalid", "malformed", "cyclic", "contradictory")
CAMEL_CASE = re.compile(r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)+\b")
EXECUTION_ID = re.compile(r"ingest-[0-9]{8}t[0-9]{6}z-[0-9a-f]{8}")


def fail(
    lab: Lab,
    operation: str,
    error: Callable[[str], BaseException],
    *,
    detail: str | None = None,
    nth: int = 1,
    execution_id: str | None = None,
    open_index: int = 1,
) -> None:
    """Repository number `open_index` raises `error` on a call, delegating nothing.

    The error carries `REFUSAL_TEXT`, so a progress line or an outcome message that
    repeats the text of the error is caught. A `PersistenceConnectionError` also ends
    that repository's connection, as in the real adapter.
    """
    lab.opener.faults.setdefault(open_index, []).append(
        lab.faults.raises(
            operation,
            lambda: error(REFUSAL_TEXT),
            detail=detail,
            nth=nth,
            execution_id=execution_id,
        )
    )


def assert_names_at_most(message: str, error: type[BaseException]) -> None:
    """Of the error, the line holds at most its class name (and none of its text)."""
    assert REFUSAL_TEXT not in message, message
    assert set(CAMEL_CASE.findall(message)) <= {error.__name__}, message


def assert_one_progress_line(
    lab: Lab,
    operation: str,
    error: type[BaseException],
    *words: str,
    numbers: tuple[int, ...] = (),
) -> str:
    """Exactly one line names `operation`, with `words` and `numbers`, and is safe."""
    lines = [message for message in lab.reporter.messages if operation in message]
    assert len(lines) == 1, (operation, lab.reporter.messages)
    for word in words:
        assert word in lines[0], (word, lines[0])
    for number in numbers:
        assert number_in(lines[0], number), (number, lines[0])
    assert_names_at_most(lines[0], error)
    assert_clean_messages(lab)
    return lines[0]


def assert_names_no_run(line: str) -> None:
    """An operation that concerns no run is named alone: no execution id."""
    assert EXECUTION_ID.search(line) is None, line


def assert_identity_message(
    outcome: IngestOutcome, identity: str, error: type[BaseException]
) -> None:
    """A fixed message that names the identity and gives no verdict on it."""
    assert identity in outcome.message, outcome.message
    assert outcome.message != error.__name__
    assert REFUSAL_TEXT not in outcome.message
    assert not any(word in outcome.message.lower() for word in INVALID_WORDS), (
        outcome.message
    )


def assert_stopped_before_the_run(lab: Lab, before: LabState) -> None:
    """Nothing was written, no run was announced, and no new connection was made."""
    assert lab.snapshot() == before
    assert written(lab, "start_run") == []
    assert lab.reporter.started == []
    assert lab.source.requests == []
    assert lab.opener.opens == 1
    assert lab.opener.all_closed


# === cleanup_database_error (AC7, AC15, F-13) ================================

CLEANUP_TRIGGERS = [
    pytest.param(
        IngestEnd.INTERRUPTED,
        "run-interrupted",
        lambda: KeyboardInterrupt(),
        id="ctrl-c",
    ),
    pytest.param(
        IngestEnd.RUN_FAILED, "unexpected-error", lambda: MemoryError(), id="memory"
    ),
]
# The four database operations of State machine K, in order. Once one fails, the
# writes of the later ones (and its own) must not reach the journal.
CLEANUP_OPERATIONS = [
    "read_run",
    "record_observation",
    "append_audit_event",
    "finish_run",
]
FIRST_WRITE_LOST = {
    "read_run": 0,
    "record_observation": 0,
    "append_audit_event": 1,
    "finish_run": 2,
}
CLEANUP_ERRORS = [*DB_ERRORS, SyntheticDefect]


@pytest.mark.parametrize("error", CLEANUP_ERRORS)
@pytest.mark.parametrize("operation", CLEANUP_OPERATIONS)
@pytest.mark.parametrize(("end", "event_type", "make_trigger"), CLEANUP_TRIGGERS)
def test_cleanup_database_error_writes_one_line_and_stops_with_the_run_running(
    lab: Lab,
    end: IngestEnd,
    event_type: str,
    make_trigger: Callable[[], BaseException],
    operation: str,
    error: type[Exception],
) -> None:
    """AC15, K: one of the cleanup's own database operations raises.

    Exactly one progress line names the operation (with the event type for the
    append, sequence 2 for the record, `failed` for `finish_run`) and the run, with
    at most the error's class name. The cleanup stops there: nothing is written
    after it, no new connection is opened, and the run is left `running`.
    """
    lab.script_ids(FREE_ID)
    store: RawEvidenceStore | None = None
    words: tuple[str, ...] = (FREE_ID,)
    numbers: tuple[int, ...] = ()
    if operation == "record_observation":
        # The interrupt lands after sequence 2 was published: the cleanup records it.
        store = lab.publishes_then_fails(on_call=2, error=make_trigger)
        fail(lab, operation, error, detail="2")
        numbers = (2,)
    else:
        lab.source.script(2, make_trigger())
        if operation == "read_run":
            # The first `read_run` of the run is the identity check.
            fail(lab, operation, error, nth=2, execution_id=FREE_ID)
        elif operation == "append_audit_event":
            fail(lab, operation, error, detail=event_type)
            words = (event_type, FREE_ID)
        else:
            fail(lab, operation, error, detail="failed")
            words = ("failed", FREE_ID)

    outcome = call(lab, fresh(lab, 1, 3), store=store)

    assert outcome.end is end
    assert outcome.execution_id == FREE_ID
    assert outcome.run_status is RunStatus.RUNNING
    assert lab.database.runs[FREE_ID].status is RunStatus.RUNNING
    assert_one_progress_line(lab, operation, error, *words, numbers=numbers)
    steps = ["record_observation:2", f"append:{event_type}", "finish_run:failed"]
    written_labels = set(lab.journal.labels(FREE_ID))
    assert not set(steps[FIRST_WRITE_LOST[operation] :]) & written_labels
    assert lab.opener.opens == 1
    assert lab.opener.all_closed


# === final_finish_read_run (AC8, AC15, F-13) =================================


@pytest.mark.parametrize("error", DB_ERRORS)
def test_final_finish_read_run_that_cannot_read_the_stored_run_is_named(
    lab: Lab, error: type[PersistenceError]
) -> None:
    """C step 5, P-2: the repeat is refused and then the `read_run` fails.

    The `read_run` gets its own line (the operation and the run); nothing more is
    written, no third connection is opened, and the run is left `running`.
    """
    lose_the_final_finish(lab, "before")
    fail(
        lab,
        "finish_run",
        PersistenceIntegrityError,
        detail="succeeded",
        open_index=2,
    )
    fail(lab, "read_run", error, open_index=2)

    outcome = call(lab, fresh(lab, 1, 2))

    assert outcome.end is IngestEnd.RUN_FAILED
    assert outcome.run_status is RunStatus.RUNNING
    assert outcome.execution_id == FREE_ID
    assert lab.database.runs[FREE_ID].status is RunStatus.RUNNING
    assert_one_progress_line(lab, "read_run", error, FREE_ID)
    assert "storage-failed" not in lab.event_types(FREE_ID)
    assert lab.opener.attempts_of("finish_run", "failed") == []
    assert lab.opener.opens == 2
    assert lab.opener.all_closed


# === pre_run_database_error (AC9, AC10, AC12, AC15, AC24; F-14, F-15) ========


@pytest.mark.parametrize("error", DB_ERRORS)
def test_pre_run_database_error_the_exclusion_that_cannot_be_taken_is_named(
    lab: Lab, error: type[PersistenceError]
) -> None:
    """Invocation step 5.2: the exclusion is refused or lost -> NOT_STARTED."""
    before = lab.snapshot()
    fail(lab, "try_acquire_ingest_exclusion", error)

    outcome = call(lab, fresh(lab, 1, 2))

    assert_not_started(outcome)
    line = assert_one_progress_line(lab, "try_acquire_ingest_exclusion", error)
    assert_names_no_run(line)
    assert outcome.message != error.__name__
    assert REFUSAL_TEXT not in outcome.message
    assert_stopped_before_the_run(lab, before)


@pytest.mark.parametrize("error", DB_ERRORS)
def test_pre_run_database_error_list_runs_that_fails_is_named(
    lab: Lab, error: type[PersistenceError]
) -> None:
    """State machine R: `list_runs` is refused or lost -> NOT_STARTED."""
    before = lab.snapshot()
    fail(lab, "list_runs", error)

    outcome = call(lab, fresh(lab, 1, 2))

    assert_not_started(outcome)
    line = assert_one_progress_line(lab, "list_runs", error)
    assert_names_no_run(line)
    assert outcome.message != error.__name__
    assert REFUSAL_TEXT not in outcome.message
    assert_stopped_before_the_run(lab, before)


@pytest.mark.parametrize("error", DB_ERRORS)
def test_pre_run_database_error_the_target_read_is_not_started_and_never_invalid(
    lab: Lab, error: type[PersistenceError]
) -> None:
    """State machine T: an unreadable target is NOT_STARTED, not INVALID_TARGET.

    Its existence is unknown, so it is not an input error (exit 1, not 2).
    """
    seed_run(lab, lab.A, pages=(1, 2))
    before = lab.snapshot()
    fail(lab, "read_run", error, execution_id=lab.A)

    outcome = call(lab, resume(lab.A))

    assert_not_started(outcome)
    assert_one_progress_line(lab, "read_run", error, lab.A)
    assert_identity_message(outcome, lab.A, error)
    assert_stopped_before_the_run(lab, before)


@pytest.mark.parametrize(("setup", "operation", "detail", "events"), RECONCILE_REFUSALS)
@pytest.mark.parametrize("error", DB_ERRORS)
def test_pre_run_database_error_reconciliation_names_the_run(
    lab: Lab,
    error: type[PersistenceError],
    setup: Callable[[Lab], None],
    operation: str,
    detail: str | None,
    events: list[str],
) -> None:
    """State machine R: a refused or lost read or write names the operation and `X`.

    Nothing more is written to `X`, which stays `running`; no new connection.
    """
    setup(lab)
    fail(lab, operation, error, detail=detail)

    outcome = call(lab, fresh(lab, 1, 2))

    assert_not_started(outcome)
    words = [detail, lab.A] if operation == "append_audit_event" and detail else [lab.A]
    assert_one_progress_line(lab, operation, error, *words)
    assert_identity_message(outcome, lab.A, error)
    assert lab.event_types(lab.A) == events
    assert lab.database.runs[lab.A].status is RunStatus.RUNNING
    assert list(lab.database.runs) == [lab.A]
    assert written(lab, "start_run") == []
    assert lab.source.requests == []
    assert lab.reporter.started == []
    assert lab.opener.opens == 1
    assert lab.opener.all_closed


def test_pre_run_database_error_reconciliation_record_that_is_lost_names_the_run(
    lab: Lab,
) -> None:
    """State machine R step 5: a lost `record_observation` of `X` sequence 3.

    A refusal is the `postgresql-observation-conflict` problem; a loss is not a
    verdict, so `X` is left as it was.
    """
    reconcile_with_a_local_only_observation(lab)
    fail(lab, "record_observation", PersistenceConnectionError, detail="3")

    outcome = call(lab, fresh(lab, 1, 2))

    assert_not_started(outcome)
    assert_one_progress_line(
        lab, "record_observation", PersistenceConnectionError, lab.A, numbers=(3,)
    )
    assert_identity_message(outcome, lab.A, PersistenceConnectionError)
    assert lab.event_types(lab.A) == []
    assert lab.sequences(lab.A) == (1, 2)
    assert lab.database.runs[lab.A].status is RunStatus.RUNNING
    assert written(lab, "start_run") == []
    assert lab.opener.opens == 1
    assert lab.opener.all_closed


def a_two_run_chain(lab: Lab) -> None:
    """B completed pages 1 and 2; A resumes B, completed page 3 and failed."""
    seed_run(lab, lab.B, pages=(1, 2))
    seed_run(lab, lab.A, resumes=lab.B, first_page=3, pages=(3,))


# (operation, the run it reads, the sequence for `read_observation`)
CHAIN_READS = [
    pytest.param("read_run", "B", None, id="earlier-run"),
    pytest.param("list_audit_events", "A", None, id="events-of-the-target"),
    pytest.param("read_observation", "B", "2", id="postgresql-observation"),
]


@pytest.mark.parametrize(("operation", "whose", "sequence"), CHAIN_READS)
@pytest.mark.parametrize("error", DB_ERRORS)
def test_pre_run_database_error_chain_read_is_an_operational_failure_not_a_verdict(
    lab: Lab,
    error: type[PersistenceError],
    operation: str,
    whose: str,
    sequence: str | None,
) -> None:
    """State machine H: the read fails; the chain is not called malformed.

    The line names the run that was read; the message names the target.
    """
    a_two_run_chain(lab)
    run_read = lab.A if whose == "A" else lab.B
    before = lab.snapshot()
    fail(lab, operation, error, detail=sequence, execution_id=run_read)

    outcome = call(lab, resume(lab.A))

    assert_not_started(outcome)
    numbers = () if sequence is None else (int(sequence),)
    assert_one_progress_line(lab, operation, error, run_read, numbers=numbers)
    assert_identity_message(outcome, lab.A, error)
    assert_stopped_before_the_run(lab, before)


@pytest.mark.parametrize("error", DB_ERRORS)
def test_pre_run_database_error_the_drawn_id_that_cannot_be_checked_is_named(
    lab: Lab, error: type[PersistenceError]
) -> None:
    """State machine I: the `read_run` of the drawn id fails -> no `start_run`."""
    lab.script_ids(FREE_ID)
    before = lab.snapshot()
    fail(lab, "read_run", error, execution_id=FREE_ID)

    outcome = call(lab, fresh(lab, 1, 2))

    assert_not_started(outcome)
    assert_one_progress_line(lab, "read_run", error, FREE_ID)
    assert_identity_message(outcome, FREE_ID, error)
    assert_stopped_before_the_run(lab, before)


@pytest.mark.parametrize("error", [OSError, EvidenceIntegrityError])
def test_pre_run_database_error_the_store_listing_of_the_drawn_id_that_fails_is_named(
    lab: Lab, error: Callable[[str], BaseException]
) -> None:
    """State machine I: `list_observation_sequences` of the drawn id raises."""
    lab.script_ids(FREE_ID)
    before = lab.snapshot()
    store = lab.faulty_reads()
    store.fail_listing(FREE_ID, lambda: error(REFUSAL_TEXT))

    outcome = call(lab, fresh(lab, 1, 2), store=store)

    assert_not_started(outcome)
    assert_identity_message(outcome, FREE_ID, PersistenceError)
    assert_stopped_before_the_run(lab, before)


# What a state machine reads as an answer is not a refusal: it gets no line.


def test_pre_run_database_error_an_unknown_target_is_an_answer_and_gets_no_line(
    lab: Lab,
) -> None:
    """State machine T: `PersistenceNotFoundError` -> INVALID_TARGET, no line."""
    outcome = call(lab, resume(lab.ABSENT))

    assert outcome.end is IngestEnd.INVALID_TARGET
    assert not any(
        "read_run" in message or "PersistenceNotFoundError" in message
        for message in lab.reporter.messages
    ), lab.reporter.messages


def test_pre_run_database_error_a_held_exclusion_is_an_answer_and_gets_no_line(
    lab: Lab,
) -> None:
    """Invocation step 5.2: a `False` from the exclusion is not a refusal."""
    lab.database.hold_exclusion_elsewhere()

    outcome = call(lab, fresh(lab, 1, 2))

    assert_not_started(outcome)
    assert not any(
        "try_acquire_ingest_exclusion" in message for message in lab.reporter.messages
    ), lab.reporter.messages


@pytest.mark.parametrize(
    "build",
    [chain_link_to_no_run, chain_page_completed_without_a_postgresql_observation],
)
def test_pre_run_database_error_a_missing_chain_row_is_an_answer_and_gets_no_line(
    lab: Lab, build: Callable[[Lab], str]
) -> None:
    """State machine H steps 1 and 2: `PersistenceNotFoundError` is a verdict."""
    target = build(lab)

    outcome = call(lab, resume(target))

    assert_not_started(outcome)
    assert not any(
        "read_run" in message
        or "read_observation" in message
        or "PersistenceNotFoundError" in message
        for message in lab.reporter.messages
    ), lab.reporter.messages


def test_pre_run_database_error_a_free_drawn_id_is_an_answer_and_gets_no_line(
    lab: Lab,
) -> None:
    """State machine I: `read_run` of the drawn id raising `PersistenceNotFoundError`."""
    outcome = call(lab, fresh(lab, 1, 2))

    assert outcome.end is IngestEnd.SUCCEEDED
    assert not any(
        "read_run" in message or "PersistenceNotFoundError" in message
        for message in lab.reporter.messages
    ), lab.reporter.messages


# === connection_loss: the second opening and the second exclusion of C ========


def lose_record_two(lab: Lab) -> None:
    lab.script_ids(FREE_ID)
    lost_at(lab, "record_observation", "2", "before")


@pytest.mark.parametrize("error", [PersistenceConnectionError, PersistenceError])
def test_connection_loss_the_second_opening_that_fails_is_named(
    lab: Lab, error: type[PersistenceError]
) -> None:
    """C step 2: `open_repository()` fails -> a line naming it; the run is `running`."""
    lose_record_two(lab)
    lab.opener.open_errors[2] = lambda: error(REFUSAL_TEXT)

    outcome = call(lab, fresh(lab, 1, 3))

    assert outcome.end is IngestEnd.RUN_FAILED
    assert outcome.run_status is RunStatus.RUNNING
    line = assert_one_progress_line(lab, "open_repository", error)
    assert_names_no_run(line)
    assert lab.opener.opens == 2
    assert lab.opener.all_closed


@pytest.mark.parametrize("error", [PersistenceError, PersistenceConnectionError])
def test_connection_loss_the_second_exclusion_that_fails_is_named(
    lab: Lab, error: type[PersistenceError]
) -> None:
    """C step 3: the exclusion on the new connection fails -> a line naming it."""
    lose_record_two(lab)
    fail(lab, "try_acquire_ingest_exclusion", error, open_index=2)

    outcome = call(lab, fresh(lab, 1, 3))

    assert outcome.end is IngestEnd.RUN_FAILED
    assert outcome.run_status is RunStatus.RUNNING
    line = assert_one_progress_line(lab, "try_acquire_ingest_exclusion", error)
    assert_names_no_run(line)
    assert lab.event_types(FREE_ID) == ["run-started", "page-completed"]
    assert lab.opener.opens == 2
    assert lab.opener.all_closed


# === repository_open_error (AC15, F-16 a) ====================================


def nothing_was_written(lab: Lab) -> bool:
    return (
        lab.journal.entries == []
        and lab.database.runs == {}
        and lab.source.requests == []
        and lab.reporter.started == []
        and lab.store.observations == {}
    )


def test_repository_open_error_a_keyboard_interrupt_ends_interrupted_with_no_run(
    lab: Lab,
) -> None:
    """Public names, `run_ingest`: Ctrl+C in the first `open_repository()`.

    The call returns INTERRUPTED with no run; the exception does not escape.
    """
    lab.opener.open_errors[1] = lambda: KeyboardInterrupt()

    outcome = call(lab, fresh(lab, 1, 2))

    assert outcome.end is IngestEnd.INTERRUPTED
    assert outcome.execution_id is None
    assert outcome.run_status is None
    assert nothing_was_written(lab)
    assert lab.opener.opens == 1


@pytest.mark.parametrize(
    "make_error",
    [
        pytest.param(lambda: MemoryError(), id="memory-error"),
        pytest.param(lambda: SyntheticDefect(BODY_MARKER), id="synthetic-defect"),
    ],
)
def test_repository_open_error_any_other_exception_ends_not_started(
    lab: Lab, make_error: Callable[[], Exception]
) -> None:
    """The opening fails with a defect: NOT_STARTED, a fixed message, nothing written.

    The message names the opening of the repository and at most the class name.
    """
    error = make_error()
    lab.opener.open_errors[1] = lambda: error

    outcome = call(lab, fresh(lab, 1, 2))

    assert_not_started(outcome)
    message = outcome.message.lower()
    assert "repository" in message or "open" in message, outcome.message
    assert outcome.message != type(error).__name__
    assert BODY_MARKER not in outcome.message
    assert set(CAMEL_CASE.findall(outcome.message)) <= {type(error).__name__}
    assert nothing_was_written(lab)
    assert lab.opener.opens == 1


@pytest.mark.parametrize("error", DB_ERRORS)
def test_repository_open_error_a_database_error_is_named_on_stderr(
    lab: Lab, error: type[PersistenceError]
) -> None:
    """Required progress 2 and 3: `open_repository` refused or lost gets its line."""
    lab.opener.open_errors[1] = lambda: error(REFUSAL_TEXT)

    outcome = call(lab, fresh(lab, 1, 2))

    assert_not_started(outcome)
    line = assert_one_progress_line(lab, "open_repository", error)
    assert_names_no_run(line)
    assert REFUSAL_TEXT not in outcome.message
    assert nothing_was_written(lab)
    assert lab.opener.opens == 1


def test_repository_open_error_a_keyboard_interrupt_before_the_exclusion_is_closed(
    lab: Lab,
) -> None:
    """Ctrl+C once a repository was obtained: INTERRUPTED, and it is closed."""
    lab.opener.faults[1] = [lab.faults.interrupts("try_acquire_ingest_exclusion")]

    outcome = call(lab, fresh(lab, 1, 2))

    assert outcome.end is IngestEnd.INTERRUPTED
    assert outcome.execution_id is None
    assert outcome.run_status is None
    assert nothing_was_written(lab)
    assert lab.opener.opens == 1
    assert len(lab.opener.repositories) == 1
    assert lab.opener.all_closed


# === reconnect_exclusion_interrupt, reconnect_open_interrupt (F-18, F-19) =====
#
# Plan Revision 8, § State machine C "The current repository" and the first bullet of
# § State machine K. After a lost connection no repository is current until the
# second repository's `try_acquire_ingest_exclusion()` has returned `True`. Anything
# that is raised in that window (while the second `open_repository()` runs, or while
# the second exclusion is taken) ends State machine C: the run is not read or written
# by any path, State machine K does not run, the second repository is closed, one
# line names the operation that raised, and the run stays `running`.


class Loss:
    """What the test saw at the moment the first connection was lost.

    It is the `hook` of the lost operation. With `other_session` it first gives the
    shared exclusion to another session (the auditor's experiment X1). It keeps what
    the doubles held at that moment and who held the exclusion, so that the end of
    the call can be compared with it.
    """

    def __init__(self, lab: Lab, *, other_session: bool) -> None:
        self._lab = lab
        self._other_session = other_session
        self.happened = False
        self.snapshot: LabState | None = None
        self.holder: object | None = None

    def __call__(self) -> None:
        if self._other_session:
            self._lab.database.hold_exclusion_elsewhere()
        self.snapshot = self._lab.snapshot()
        self.holder = self._lab.database.exclusion_holder
        self.happened = True


def arrange_loss(lab: Lab, place: str, loss: Loss) -> tuple[IngestRequest, str, str]:
    """Lose the first connection before the commit of one operation.

    Return the request, the lost operation and its detail (`""` for `start_run`).
    """
    lab.script_ids(FREE_ID)
    if place == "observation":
        lab.opener.faults[1] = [
            lab.faults.lost_before_commit("record_observation", detail="2", hook=loss)
        ]
        return fresh(lab, 1, 3), "record_observation", "2"
    if place == "final-finish":
        lose_the_final_finish(lab, "before", hook=loss)
        return fresh(lab, 1, 2), "finish_run", "succeeded"
    assert place == "start-run"
    lab.opener.faults[1] = [lab.faults.lost_before_commit("start_run", hook=loss)]
    return fresh(lab, 1, 3), "start_run", ""


def attempts_after_the_loss(lab: Lab, operation: str, detail: str) -> list[str]:
    """What every repository was asked after the lost call: `<open index> <operation>`."""
    attempts = lab.opener.attempts
    lost = next(
        index
        for index, attempt in enumerate(attempts)
        if attempt.open_index == 1
        and attempt.operation == operation
        and (not detail or attempt.detail == detail)
    )
    return [f"{a.open_index} {a.operation}" for a in attempts[lost + 1 :]]


def messages_after_the_loss(lab: Lab, operation: str) -> list[str]:
    """The progress messages that follow the line of the lost operation."""
    messages = lab.reporter.messages
    lost = next(
        index
        for index, message in enumerate(messages)
        if operation in message and FREE_ID in message
    )
    return messages[lost + 1 :]


def assert_the_run_was_not_touched(lab: Lab, loss: Loss) -> None:
    """Nothing was written to the run or to any store since the connection was lost."""
    assert loss.happened
    assert lab.snapshot() == loss.snapshot
    assert written(lab, "finish_run") == []
    assert lab.database.exclusion_holder is loss.holder


# What a recovery that is interrupted or fails with a non-database exception gives.
# `end` is the outcome once the run exists; `window_end` the one while `start_run`
# itself is the lost operation (the earlier rules, kept by the plan).
RECOVERY_ERRORS = [
    pytest.param(
        lambda: KeyboardInterrupt(),
        KeyboardInterrupt,
        IngestEnd.INTERRUPTED,
        IngestEnd.INTERRUPTED,
        id="ctrl-c",
    ),
    pytest.param(
        lambda: MemoryError(),
        MemoryError,
        IngestEnd.RUN_FAILED,
        IngestEnd.NOT_STARTED,
        id="memory-error",
    ),
    pytest.param(
        lambda: SyntheticDefect(REFUSAL_TEXT),
        SyntheticDefect,
        IngestEnd.RUN_FAILED,
        IngestEnd.NOT_STARTED,
        id="synthetic-defect",
    ),
]
EXCLUSION_STATES = pytest.mark.parametrize(
    "other_session", [False, True], ids=["exclusion-free", "exclusion-held"]
)
FORBIDDEN_AFTER_THE_LOSS = (
    "read_run",
    "record_observation",
    "append_audit_event",
    "finish_run",
)


def assert_window_outcome(
    lab: Lab, outcome: IngestOutcome, end: IngestEnd, error: type[BaseException]
) -> None:
    """`start_run` is the lost operation: no run is known, nothing was announced."""
    assert outcome.end is end
    assert outcome.execution_id is None
    assert outcome.run_status is None
    assert lab.reporter.started == []
    assert lab.database.runs == {}
    assert REFUSAL_TEXT not in outcome.message
    assert set(CAMEL_CASE.findall(outcome.message)) <= {error.__name__}


@EXCLUSION_STATES
@pytest.mark.parametrize("place", ["observation", "final-finish"])
@pytest.mark.parametrize(("make_error", "error", "end", "window_end"), RECOVERY_ERRORS)
def test_reconnect_exclusion_interrupt_writes_nothing_and_leaves_the_run_running(
    lab: Lab,
    make_error: Callable[[], BaseException],
    error: type[BaseException],
    end: IngestEnd,
    window_end: IngestEnd,
    place: str,
    other_session: bool,
) -> None:
    """F-18, C step 3: the second exclusion raises -> the cleanup does not run.

    The lost operation is an observation, or the final `finish_run` (P-2: no
    repeat). Nothing is read from or written to the run, whether the exclusion is
    free or another session took it at the loss (X1); the second repository is
    closed, and one line names `try_acquire_ingest_exclusion`, alone.
    """
    loss = Loss(lab, other_session=other_session)
    request, operation, detail = arrange_loss(lab, place, loss)
    lab.opener.faults[2] = [
        lab.faults.raises("try_acquire_ingest_exclusion", make_error)
    ]

    outcome = call(lab, request)

    assert outcome.end is end
    assert outcome.execution_id == FREE_ID
    assert outcome.run_status is RunStatus.RUNNING
    assert lab.reporter.started == [FREE_ID]
    assert lab.database.runs[FREE_ID].status is RunStatus.RUNNING
    assert_the_run_was_not_touched(lab, loss)
    assert attempts_after_the_loss(lab, operation, detail) == [
        "2 try_acquire_ingest_exclusion"
    ]
    line = assert_one_progress_line(lab, "try_acquire_ingest_exclusion", error)
    assert_names_no_run(line)
    assert not any(
        name in message
        for message in messages_after_the_loss(lab, operation)
        for name in FORBIDDEN_AFTER_THE_LOSS
    ), lab.reporter.messages
    assert REFUSAL_TEXT not in outcome.message
    assert set(CAMEL_CASE.findall(outcome.message)) <= {error.__name__}
    assert lab.opener.opens == 2
    assert len(lab.opener.repositories) == 2
    assert lab.opener.all_closed


@EXCLUSION_STATES
@pytest.mark.parametrize(("make_error", "error", "end", "window_end"), RECOVERY_ERRORS)
def test_reconnect_exclusion_interrupt_while_start_run_is_pending_keeps_the_outcome(
    lab: Lab,
    make_error: Callable[[], BaseException],
    error: type[BaseException],
    end: IngestEnd,
    window_end: IngestEnd,
    other_session: bool,
) -> None:
    """C step 3 with `start_run` lost before commit: no run is known.

    Ctrl+C gives INTERRUPTED and any other exception NOT_STARTED, with no run and
    `run_started` not called (K, "Before `start_run` returned"). Nothing is
    written, and the same one line is written.
    """
    loss = Loss(lab, other_session=other_session)
    request, operation, detail = arrange_loss(lab, "start-run", loss)
    lab.opener.faults[2] = [
        lab.faults.raises("try_acquire_ingest_exclusion", make_error)
    ]

    outcome = call(lab, request)

    assert_window_outcome(lab, outcome, window_end, error)
    assert_the_run_was_not_touched(lab, loss)
    assert attempts_after_the_loss(lab, operation, detail) == [
        "2 try_acquire_ingest_exclusion"
    ]
    line = assert_one_progress_line(lab, "try_acquire_ingest_exclusion", error)
    assert_names_no_run(line)
    assert lab.opener.opens == 2
    assert lab.opener.all_closed


@pytest.mark.parametrize("place", ["observation", "final-finish"])
def test_reconnect_exclusion_interrupt_after_the_true_is_in_the_window_too(
    lab: Lab, place: str
) -> None:
    """C, "The current repository": Ctrl+C once the exclusion call has taken it.

    The second repository holds the exclusion but was not made current. Nothing is
    written, it is closed (which frees the exclusion), and the line names the call.
    """
    loss = Loss(lab, other_session=False)
    request, operation, detail = arrange_loss(lab, place, loss)
    lab.opener.faults[2] = [
        lab.faults.interrupts("try_acquire_ingest_exclusion", when="after")
    ]

    outcome = call(lab, request)

    assert outcome.end is IngestEnd.INTERRUPTED
    assert outcome.execution_id == FREE_ID
    assert outcome.run_status is RunStatus.RUNNING
    assert lab.database.runs[FREE_ID].status is RunStatus.RUNNING
    assert_the_run_was_not_touched(lab, loss)
    assert lab.database.exclusion_holder is None
    assert attempts_after_the_loss(lab, operation, detail) == [
        "2 try_acquire_ingest_exclusion"
    ]
    line = assert_one_progress_line(
        lab, "try_acquire_ingest_exclusion", KeyboardInterrupt
    )
    assert_names_no_run(line)
    assert lab.opener.opens == 2
    assert lab.opener.all_closed


@pytest.mark.parametrize("place", ["observation", "final-finish", "start-run"])
def test_reconnect_exclusion_interrupt_system_exit_propagates_and_closes_it(
    lab: Lab, place: str
) -> None:
    """`SystemExit` is never caught; the second repository is closed all the same."""
    loss = Loss(lab, other_session=False)
    request, _, _ = arrange_loss(lab, place, loss)
    lab.opener.faults[2] = [
        lab.faults.raises("try_acquire_ingest_exclusion", lambda: SystemExit(3))
    ]

    with pytest.raises(SystemExit):
        call_propagating(lab, request)

    assert_the_run_was_not_touched(lab, loss)
    assert lab.opener.opens == 2
    assert len(lab.opener.repositories) == 2
    assert lab.opener.all_closed


@EXCLUSION_STATES
@pytest.mark.parametrize("place", ["observation", "final-finish"])
@pytest.mark.parametrize(("make_error", "error", "end", "window_end"), RECOVERY_ERRORS)
def test_reconnect_open_interrupt_touches_nothing_and_leaves_the_run_running(
    lab: Lab,
    make_error: Callable[[], BaseException],
    error: type[BaseException],
    end: IngestEnd,
    window_end: IngestEnd,
    place: str,
    other_session: bool,
) -> None:
    """F-19, C step 2: the second `open_repository()` raises -> no cleanup.

    No repository is asked anything after the loss, in particular not the closed
    first one. The run is not written, and one line names `open_repository`, alone.
    """
    loss = Loss(lab, other_session=other_session)
    request, operation, detail = arrange_loss(lab, place, loss)
    lab.opener.open_errors[2] = make_error

    outcome = call(lab, request)

    assert outcome.end is end
    assert outcome.execution_id == FREE_ID
    assert outcome.run_status is RunStatus.RUNNING
    assert lab.reporter.started == [FREE_ID]
    assert lab.database.runs[FREE_ID].status is RunStatus.RUNNING
    assert_the_run_was_not_touched(lab, loss)
    assert attempts_after_the_loss(lab, operation, detail) == []
    line = assert_one_progress_line(lab, "open_repository", error)
    assert_names_no_run(line)
    assert not any(
        name in message
        for message in messages_after_the_loss(lab, operation)
        for name in (*FORBIDDEN_AFTER_THE_LOSS, "RuntimeError")
    ), lab.reporter.messages
    assert REFUSAL_TEXT not in outcome.message
    assert set(CAMEL_CASE.findall(outcome.message)) <= {error.__name__}
    assert lab.opener.opens == 2
    assert len(lab.opener.repositories) == 1
    assert lab.opener.all_closed


@EXCLUSION_STATES
@pytest.mark.parametrize(("make_error", "error", "end", "window_end"), RECOVERY_ERRORS)
def test_reconnect_open_interrupt_while_start_run_is_pending_keeps_the_outcome(
    lab: Lab,
    make_error: Callable[[], BaseException],
    error: type[BaseException],
    end: IngestEnd,
    window_end: IngestEnd,
    other_session: bool,
) -> None:
    """C step 2 with `start_run` lost before commit: no run is known.

    Ctrl+C gives INTERRUPTED and any other exception NOT_STARTED, with no run;
    nothing is written, and one line names `open_repository`.
    """
    loss = Loss(lab, other_session=other_session)
    request, operation, detail = arrange_loss(lab, "start-run", loss)
    lab.opener.open_errors[2] = make_error

    outcome = call(lab, request)

    assert_window_outcome(lab, outcome, window_end, error)
    assert_the_run_was_not_touched(lab, loss)
    assert attempts_after_the_loss(lab, operation, detail) == []
    line = assert_one_progress_line(lab, "open_repository", error)
    assert_names_no_run(line)
    assert lab.opener.opens == 2
    assert lab.opener.all_closed


def test_reconnect_open_interrupt_never_asks_the_closed_first_repository(
    lab: Lab,
) -> None:
    """F-19: no `read_run failed ... (RuntimeError)` line for a read that never ran.

    The first repository is closed at the loss. It is not called again, and no
    message names an operation that was not attempted.
    """
    loss = Loss(lab, other_session=False)
    request, operation, detail = arrange_loss(lab, "observation", loss)
    lab.opener.open_errors[2] = lambda: MemoryError()

    call(lab, request)

    assert lab.opener.repositories[0].inner.closed
    assert attempts_after_the_loss(lab, operation, detail) == []
    assert not any("RuntimeError" in message for message in lab.reporter.messages)
    assert not any(
        "read_run" in message for message in messages_after_the_loss(lab, operation)
    )
    assert_one_progress_line(lab, "open_repository", MemoryError)


@pytest.mark.parametrize("place", ["observation", "final-finish", "start-run"])
def test_reconnect_open_interrupt_system_exit_propagates_and_leaves_nothing_open(
    lab: Lab, place: str
) -> None:
    """`SystemExit` from the second opening is never caught; nothing is left open."""
    loss = Loss(lab, other_session=False)
    request, _, _ = arrange_loss(lab, place, loss)
    lab.opener.open_errors[2] = lambda: SystemExit(3)

    with pytest.raises(SystemExit):
        call_propagating(lab, request)

    assert_the_run_was_not_touched(lab, loss)
    assert lab.opener.opens == 2
    assert lab.opener.all_closed


# === start_run_unconfirmed (AC8, AC15; F-20) ===================================
#
# A `start_run` whose connection is lost, when the recovery fails too: the run is
# `running` with its id, nothing was announced, and the README documents the case.


@pytest.mark.parametrize("recovery", ["open-refused", "exclusion-held"])
@pytest.mark.parametrize("when", WHEN)
def test_start_run_unconfirmed_leaves_the_run_running_and_announces_nothing(
    lab: Lab, when: str, recovery: str
) -> None:
    """C steps 2 and 3 with `start_run` pending: the recovery fails.

    RUN_FAILED with the drawn id and `running`; `run_started` is not called; no
    event is written; no page is requested. One line names the lost `start_run` and
    the id; a refused opening adds one that names `open_repository`; a `False` adds
    none.
    """
    lab.script_ids(FREE_ID)
    loss = Loss(lab, other_session=recovery == "exclusion-held")
    lab.opener.faults[1] = [
        lab.faults.lost_before_commit("start_run", hook=loss)
        if when == "before"
        else lab.faults.lost_after_commit("start_run", hook=loss)
    ]
    if recovery == "open-refused":
        lab.opener.fail_opens = {2}

    outcome = call(lab, fresh(lab, 1, 3))

    assert outcome.end is IngestEnd.RUN_FAILED
    assert outcome.execution_id == FREE_ID
    assert outcome.run_status is RunStatus.RUNNING
    assert lab.reporter.started == []
    assert lab.source.requests == []
    assert lab.events(FREE_ID) == []
    assert_the_run_was_not_touched(lab, loss)
    if when == "after":
        assert lab.database.runs[FREE_ID].status is RunStatus.RUNNING
    else:
        assert lab.database.runs == {}
    start_lines = progress_lines(lab, "start_run", FREE_ID)
    assert len(start_lines) == 1, lab.reporter.messages
    assert_names_at_most(start_lines[0], PersistenceConnectionError)
    assert progress_lines(lab, "try_acquire_ingest_exclusion") == []
    if recovery == "open-refused":
        line = assert_one_progress_line(
            lab, "open_repository", PersistenceConnectionError
        )
        assert_names_no_run(line)
        assert attempts_after_the_loss(lab, "start_run", "") == []
    else:
        assert progress_lines(lab, "open_repository") == []
        assert attempts_after_the_loss(lab, "start_run", "") == [
            "2 try_acquire_ingest_exclusion"
        ]
    assert_clean_messages(lab)
    assert lab.opener.opens == 2
    assert lab.opener.all_closed


# === read_back_record_failure (AC6 b, AC6 c, AC8, AC15; F-20) ==================
#
# The AC6 (b) path: the store publishes sequence 2 and then raises `OSError`, the
# read-back finds the observation, and recording it is refused or lost.


@pytest.mark.parametrize("error", [PersistenceIntegrityError, PersistenceError])
def test_read_back_record_failure_a_refused_record_is_one_postgresql_failure(
    lab: Lab, error: type[PersistenceError]
) -> None:
    """P step 3 then step 4: the read-back finds 2 and PostgreSQL refuses it.

    One line names `record_observation`, the run and sequence 2; exactly one
    `storage-failed` (`postgresql`, page 2, sequence 2) and no `raw-evidence` one;
    `finish_run(FAILED)`; PostgreSQL holds no observation 2, the local store does.
    """
    lab.script_ids(FREE_ID)
    refuse(lab, "record_observation", error, detail="2")
    store = lab.publishes_then_fails(on_call=2)

    outcome = call(lab, fresh(lab, 1, 3), store=store)

    assert outcome.end is IngestEnd.RUN_FAILED
    assert outcome.execution_id == FREE_ID
    assert outcome.run_status is RunStatus.FAILED
    assert lab.event_types(FREE_ID) == [
        "run-started",
        "page-completed",
        "storage-failed",
    ]
    assert lab.details(FREE_ID, "storage-failed") == [
        {"page": 2, "sequence": 2, "store": "postgresql"}
    ]
    assert_follows_catalogue(lab.events(FREE_ID))
    assert lab.sequences(FREE_ID) == (1,)
    assert lab.local_sequences(FREE_ID) == (1, 2)
    assert lab.journal.labels(FREE_ID)[-3:] == [
        "store:2",
        "append:storage-failed",
        "finish_run:failed",
    ]
    assert_one_progress_line(lab, "record_observation", error, FREE_ID, numbers=(2,))
    assert lab.opener.opens == 1
    assert lab.opener.all_closed


@pytest.mark.parametrize("when", WHEN)
def test_read_back_record_failure_a_lost_record_with_no_new_connection_stays_running(
    lab: Lab, when: str
) -> None:
    """P step 3, then C: the record is lost and the second opening is refused.

    RUN_FAILED, `running`; nothing is written after the loss; the observation is
    still in the local store; one line names the lost `record_observation` and the
    run, one names `open_repository`.
    """
    lab.script_ids(FREE_ID)
    loss = Loss(lab, other_session=False)
    lab.opener.faults[1] = [
        lab.faults.lost_before_commit("record_observation", detail="2", hook=loss)
        if when == "before"
        else lab.faults.lost_after_commit("record_observation", detail="2", hook=loss)
    ]
    lab.opener.fail_opens = {2}
    store = lab.publishes_then_fails(on_call=2)

    outcome = call(lab, fresh(lab, 1, 3), store=store)

    assert outcome.end is IngestEnd.RUN_FAILED
    assert outcome.execution_id == FREE_ID
    assert outcome.run_status is RunStatus.RUNNING
    assert lab.database.runs[FREE_ID].status is RunStatus.RUNNING
    assert lab.event_types(FREE_ID) == ["run-started", "page-completed"]
    assert_the_run_was_not_touched(lab, loss)
    assert lab.local_sequences(FREE_ID) == (1, 2)
    assert_follows_catalogue(lab.events(FREE_ID))
    lost_lines = progress_lines(lab, "record_observation", FREE_ID, numbers=(2,))
    assert len(lost_lines) == 1, lab.reporter.messages
    assert_names_at_most(lost_lines[0], PersistenceConnectionError)
    line = assert_one_progress_line(lab, "open_repository", PersistenceConnectionError)
    assert_names_no_run(line)
    assert attempts_after_the_loss(lab, "record_observation", "2") == []
    assert lab.opener.opens == 2
    assert lab.opener.all_closed


# === Audit round 5 rework (2026-10-20), plan Revisions 9 and 10 ================
#
# Written red against the Revision 12/10/7 specs (approved on 2026-10-20), before the
# round 5 fix of `run_ingest`. Tokens of Revision 9: `reconnect_close_interrupt`,
# `reconnect_loss_line_interrupt`, `reconnect_false_close_interrupt` (F-21),
# `final_close_error`, `final_close_interrupt` (F-22) and `generic_fallback` (F-20).
# Tokens of Revision 10 (the architect's sweep A2): `start_run_second_loss` (N-1),
# `unexpected_cleanup_interrupt` (N-2), `recovery_double_fault` (N-3) and
# `refusal_not_retried` (N-4). The seams are new in `conftest.py`: the close fault
# (`lab.opener.close_faults`, `lab.faults.close_raises`) and the raising reporter
# (`lab.raising_reporter`).


def call_without_escape(
    lab: Lab,
    request: IngestRequest | ResumeRequest,
    *,
    store: RawEvidenceStore | None = None,
) -> IngestOutcome:
    """The call of `call`, where any exception that escapes fails the test by name.

    `call` turns only a `KeyboardInterrupt` into a failure. A defect of Revision 9
    is an `OSError` or a `MemoryError` that escapes from a `close()`, so this one
    names whatever escaped.
    """
    try:
        return call_propagating(lab, request, store=store)
    except (Exception, KeyboardInterrupt) as error:
        raise AssertionError(f"run_ingest let {type(error).__name__} escape") from error


# What the lost repository's close, the second repository's close and the reporter
# raise: Ctrl+C ends `INTERRUPTED`, a `MemoryError` ends `RUN_FAILED` once the run
# exists and `NOT_STARTED` while `start_run` is the lost operation.
CLOSE_ERRORS = [
    pytest.param(
        lambda: KeyboardInterrupt(),
        KeyboardInterrupt,
        IngestEnd.INTERRUPTED,
        IngestEnd.INTERRUPTED,
        id="ctrl-c",
    ),
    pytest.param(
        lambda: MemoryError(),
        MemoryError,
        IngestEnd.RUN_FAILED,
        IngestEnd.NOT_STARTED,
        id="memory-error",
    ),
]
# Plan Revision 9, F-21: nothing after the loss line may name one of these.
NAMES_AFTER_THE_LOSS = (
    "read_run",
    "append_audit_event",
    "finish_run",
    "open_repository",
    "try_acquire_ingest_exclusion",
    "RuntimeError",
)


def assert_names_nothing_after_the_loss(lab: Lab, operation: str) -> None:
    """No line after the one of the lost operation names an operation of the cleanup."""
    after = messages_after_the_loss(lab, operation)
    assert not any(
        name in message for message in after for name in NAMES_AFTER_THE_LOSS
    ), lab.reporter.messages


def assert_names_no_read_of_the_run(lab: Lab) -> None:
    """No message names `read_run` or holds `RuntimeError` (it was never attempted)."""
    assert not any(
        "read_run" in message or "RuntimeError" in message
        for message in lab.reporter.messages
    ), lab.reporter.messages


def arrange_lost_page_completed(lab: Lab, loss: Loss) -> tuple[IngestRequest, str, str]:
    """Lose the first connection before the commit of the `page-completed` of page 1."""
    lab.script_ids(FREE_ID)
    lab.opener.faults[1] = [
        lab.faults.lost_before_commit(
            "append_audit_event", detail="page-completed", hook=loss
        )
    ]
    return fresh(lab, 1, 3), "append_audit_event", "page-completed"


# === reconnect_close_interrupt (AC7, AC8 c, AC15, AC18; F-21, E1, E13) ========
#
# Plan Revision 9, § State machine C step 1 and "The explicit record": from the loss
# on no repository is current. A `KeyboardInterrupt` or a `MemoryError` raised by the
# lost repository's `close()` ends C in the window: nothing is read or written, the
# cleanup is not entered, and the final close attempts the lost repository once more.


@EXCLUSION_STATES
@pytest.mark.parametrize("when", WHEN)
@pytest.mark.parametrize("place", ["observation", "final-finish"])
@pytest.mark.parametrize(("make_error", "error", "end", "window_end"), CLOSE_ERRORS)
def test_reconnect_close_interrupt_runs_no_cleanup_and_leaves_the_run_running(
    lab: Lab,
    make_error: Callable[[], BaseException],
    error: type[BaseException],
    end: IngestEnd,
    window_end: IngestEnd,
    place: str,
    when: Moment,
    other_session: bool,
) -> None:
    """F-21, C step 1: the lost repository's `close()` raises Ctrl+C or `MemoryError`.

    After the lost call nothing is attempted on any repository (in particular no
    `read_run`); C ends at step 1, so only one repository was opened; `<A>` is
    stored `running` with what it held at the loss; no line after the loss line names
    an operation of the cleanup; the lost repository is closed by the final close.
    """
    loss = Loss(lab, other_session=other_session)
    request, operation, detail = arrange_loss(lab, place, loss)
    lab.opener.close_faults[1] = [lab.faults.close_raises(make_error, when=when)]

    outcome = call_without_escape(lab, request)

    assert outcome.end is end
    assert outcome.execution_id == FREE_ID
    assert outcome.run_status is RunStatus.RUNNING
    assert lab.reporter.started == [FREE_ID]
    assert lab.database.runs[FREE_ID].status is RunStatus.RUNNING
    assert_the_run_was_not_touched(lab, loss)
    assert attempts_after_the_loss(lab, operation, detail) == []
    assert_names_nothing_after_the_loss(lab, operation)
    assert lab.opener.opens == 1
    assert lab.opener.all_closed


@EXCLUSION_STATES
@pytest.mark.parametrize("when", WHEN)
@pytest.mark.parametrize(("make_error", "error", "end", "window_end"), CLOSE_ERRORS)
def test_reconnect_close_interrupt_while_start_run_is_pending_keeps_the_outcome(
    lab: Lab,
    make_error: Callable[[], BaseException],
    error: type[BaseException],
    end: IngestEnd,
    window_end: IngestEnd,
    when: Moment,
    other_session: bool,
) -> None:
    """C step 1 with `start_run` lost before commit: no run is known.

    Ctrl+C gives INTERRUPTED and `MemoryError` NOT_STARTED, with no run and
    `run_started` not called; nothing is written; every repository is closed.
    """
    loss = Loss(lab, other_session=other_session)
    request, operation, detail = arrange_loss(lab, "start-run", loss)
    lab.opener.close_faults[1] = [lab.faults.close_raises(make_error, when=when)]

    outcome = call_without_escape(lab, request)

    assert_window_outcome(lab, outcome, window_end, error)
    assert_the_run_was_not_touched(lab, loss)
    assert attempts_after_the_loss(lab, operation, detail) == []
    assert_names_no_read_of_the_run(lab)
    assert lab.opener.opens == 1
    assert lab.opener.all_closed


@EXCLUSION_STATES
@pytest.mark.parametrize("when", WHEN)
@pytest.mark.parametrize("place", ["observation", "final-finish"])
def test_reconnect_close_interrupt_an_os_error_from_the_lost_close_changes_nothing(
    lab: Lab, place: str, when: Moment, other_session: bool
) -> None:
    """C step 1: an `Exception` other than `MemoryError` is suppressed, no line.

    The recovery goes on: a second repository is opened. With the exclusion free the
    run ends as the AC8 (a) path (a lost observation) or is confirmed by the repeat
    (the final `finish_run`, P-2); with another session holding it the exclusion
    returns `False` and the run is untouched.
    """
    loss = Loss(lab, other_session=other_session)
    request, operation, detail = arrange_loss(lab, place, loss)
    lab.opener.close_faults[1] = [
        lab.faults.close_raises(lambda: OSError(REFUSAL_TEXT), when=when)
    ]

    outcome = call_without_escape(lab, request)

    assert outcome.execution_id == FREE_ID
    assert lab.opener.opens == 2
    assert not any(
        "OSError" in message or REFUSAL_TEXT in message
        for message in lab.reporter.messages
    ), lab.reporter.messages
    if other_session:
        assert outcome.end is IngestEnd.RUN_FAILED
        assert outcome.run_status is RunStatus.RUNNING
        assert_the_run_was_not_touched(lab, loss)
        assert attempts_after_the_loss(lab, operation, detail) == [
            "2 try_acquire_ingest_exclusion"
        ]
    elif place == "observation":
        assert outcome.end is IngestEnd.RUN_FAILED
        assert outcome.run_status is RunStatus.FAILED
        assert lab.details(FREE_ID, "storage-failed") == [
            {"page": 2, "sequence": 2, "store": "postgresql"}
        ]
    else:
        assert outcome.end is IngestEnd.SUCCEEDED
        assert outcome.run_status is RunStatus.SUCCEEDED
    if when == "after":
        # Raised before delegating, the lost repository stays open: an `OSError`
        # counts the repository as closed, so nothing attempts it again.
        assert lab.opener.all_closed


# === reconnect_loss_line_interrupt (AC7, AC15; F-21, E3) =======================
#
# The reporter raises while the line of the lost operation is written. The record of
# the current repository is *none* before that line, so the cleanup is not entered.

LOSS_LINES = [
    pytest.param("observation", ("record_observation", FREE_ID), id="observation"),
    pytest.param(
        "page-completed",
        ("append_audit_event", "page-completed", FREE_ID),
        id="page-completed-append",
    ),
]


@pytest.mark.parametrize("when", WHEN)
@pytest.mark.parametrize(("make_error", "error", "end", "window_end"), CLOSE_ERRORS)
@pytest.mark.parametrize(("place", "words"), LOSS_LINES)
def test_reconnect_loss_line_interrupt_runs_no_cleanup_and_leaves_the_run_running(
    lab: Lab,
    place: str,
    words: tuple[str, ...],
    make_error: Callable[[], BaseException],
    error: type[BaseException],
    end: IngestEnd,
    window_end: IngestEnd,
    when: Moment,
) -> None:
    """F-21, experiment E3: the line of the lost operation raises Ctrl+C or `MemoryError`.

    The line is recorded first (`after`) or lost (`before`). Nothing is attempted
    after the lost call, nothing is written, no second repository is opened, and no
    message names `read_run` or holds `RuntimeError`.
    """
    loss = Loss(lab, other_session=False)
    if place == "observation":
        request, operation, detail = arrange_loss(lab, "observation", loss)
    else:
        request, operation, detail = arrange_lost_page_completed(lab, loss)
    reporter = lab.raising_reporter(*words, error=make_error, when=when)

    outcome = call_without_escape(lab, request)

    assert reporter.fired
    assert outcome.end is end
    assert outcome.execution_id == FREE_ID
    assert outcome.run_status is RunStatus.RUNNING
    assert reporter.started == [FREE_ID]
    assert lab.database.runs[FREE_ID].status is RunStatus.RUNNING
    assert_the_run_was_not_touched(lab, loss)
    assert attempts_after_the_loss(lab, operation, detail) == []
    assert_names_no_read_of_the_run(lab)
    assert lab.opener.opens == 1
    assert lab.opener.all_closed


@pytest.mark.parametrize("when", WHEN)
def test_reconnect_loss_line_interrupt_the_line_of_a_refused_second_exclusion(
    lab: Lab, when: Moment
) -> None:
    """F-21: the second exclusion is refused and the reporter raises Ctrl+C on its line.

    INTERRUPTED with `running`; nothing is read or written; the only attempt after
    the lost call is the second exclusion; both repositories are closed.
    """
    loss = Loss(lab, other_session=False)
    request, operation, detail = arrange_loss(lab, "observation", loss)
    lab.opener.faults[2] = [
        lab.faults.refuses(
            "try_acquire_ingest_exclusion",
            lambda: PersistenceIntegrityError(REFUSAL_TEXT),
        )
    ]
    reporter = lab.raising_reporter(
        "try_acquire_ingest_exclusion", error=lambda: KeyboardInterrupt(), when=when
    )

    outcome = call_without_escape(lab, request)

    assert reporter.fired
    assert outcome.end is IngestEnd.INTERRUPTED
    assert outcome.execution_id == FREE_ID
    assert outcome.run_status is RunStatus.RUNNING
    assert_the_run_was_not_touched(lab, loss)
    assert attempts_after_the_loss(lab, operation, detail) == [
        "2 try_acquire_ingest_exclusion"
    ]
    assert_names_no_read_of_the_run(lab)
    assert lab.opener.opens == 2
    assert lab.opener.all_closed


# === reconnect_false_close_interrupt (AC7, AC8 c, AC15, AC18; F-21, E2, E2b) ===
#
# Another session holds the exclusion at the loss, so the second exclusion returns
# `False`, and then the second repository's `close()` raises.


@pytest.mark.parametrize("when", WHEN)
@pytest.mark.parametrize(("make_error", "error", "end", "window_end"), CLOSE_ERRORS)
def test_reconnect_false_close_interrupt_runs_no_cleanup_and_leaves_the_run_running(
    lab: Lab,
    make_error: Callable[[], BaseException],
    error: type[BaseException],
    end: IngestEnd,
    window_end: IngestEnd,
    when: Moment,
) -> None:
    """F-21, C step 3: `False`, then the second repository's close raises.

    The only attempt after the lost call is the second exclusion; the `False` adds no
    line; the other session still holds the exclusion; both repositories end closed
    (the second one, when its close raised before delegating, by the final close).
    """
    loss = Loss(lab, other_session=True)
    request, operation, detail = arrange_loss(lab, "observation", loss)
    lab.opener.close_faults[2] = [lab.faults.close_raises(make_error, when=when)]

    outcome = call_without_escape(lab, request)

    assert outcome.end is end
    assert outcome.execution_id == FREE_ID
    assert outcome.run_status is RunStatus.RUNNING
    assert_the_run_was_not_touched(lab, loss)
    assert attempts_after_the_loss(lab, operation, detail) == [
        "2 try_acquire_ingest_exclusion"
    ]
    assert progress_lines(lab, "try_acquire_ingest_exclusion") == []
    assert_names_no_read_of_the_run(lab)
    assert lab.database.exclusion_holder is loss.holder
    assert lab.opener.opens == 2
    assert lab.opener.all_closed


@pytest.mark.parametrize("when", WHEN)
def test_reconnect_false_close_interrupt_an_os_error_from_that_close_changes_nothing(
    lab: Lab, when: Moment
) -> None:
    """C step 3: an `Exception` other than `MemoryError` from that close is suppressed.

    The `False` outcome is unchanged: RUN_FAILED with `running`, the run untouched.
    """
    loss = Loss(lab, other_session=True)
    request, operation, detail = arrange_loss(lab, "observation", loss)
    lab.opener.close_faults[2] = [
        lab.faults.close_raises(lambda: OSError(REFUSAL_TEXT), when=when)
    ]

    outcome = call_without_escape(lab, request)

    assert outcome.end is IngestEnd.RUN_FAILED
    assert outcome.execution_id == FREE_ID
    assert outcome.run_status is RunStatus.RUNNING
    assert_the_run_was_not_touched(lab, loss)
    assert attempts_after_the_loss(lab, operation, detail) == [
        "2 try_acquire_ingest_exclusion"
    ]
    assert progress_lines(lab, "try_acquire_ingest_exclusion") == []
    assert not any("OSError" in message for message in lab.reporter.messages)
    assert lab.opener.opens == 2


# === final_close_error, final_close_interrupt (AC7, AC15; F-22, E7, E8) =======
#
# Plan Revision 9, § Public names, "The final close": closing the final repository
# never changes how the run ended. An `Exception` from that `close()` is suppressed; a
# `KeyboardInterrupt` returns the determined outcome as `INTERRUPTED`, with the same
# run and the same confirmed status.


@dataclass(frozen=True)
class FinalClose:
    """One ending of `run_ingest` and the repository whose close is faulty."""

    request: IngestRequest
    open_index: int
    end: IngestEnd
    run_status: RunStatus | None
    events: list[str] | None
    last_write: str | None


def arrange_final_close(lab: Lab, name: str) -> FinalClose:
    """The four endings of plan Revision 9 (AC1, AC4, a refused exclusion, AC8 a)."""
    if name == "ac1-run":
        lab.script_ids(FREE_ID)
        lab.source.script(1, lab.ok(1, pages=3))
        lab.source.script(2, lab.ok(2, pages=3))
        return FinalClose(
            fresh(lab, 1, 2),
            1,
            IngestEnd.SUCCEEDED,
            RunStatus.SUCCEEDED,
            ["run-started", "page-completed", "page-completed"],
            "finish_run:succeeded",
        )
    if name == "ac4-run":
        lab.script_ids(FREE_ID)
        lab.source.script(2, lab.status_failure(2, 500))
        return FinalClose(
            fresh(lab, 1, 3),
            1,
            IngestEnd.RUN_FAILED,
            RunStatus.FAILED,
            ["run-started", "page-completed", "page-failed"],
            "finish_run:failed",
        )
    if name == "refused-exclusion":
        lab.database.hold_exclusion_elsewhere()
        return FinalClose(fresh(lab, 1, 2), 1, IngestEnd.NOT_STARTED, None, None, None)
    assert name == "recovery"
    lab.script_ids(FREE_ID)
    lab.opener.faults[1] = [
        lab.faults.lost_before_commit("record_observation", detail="2")
    ]
    return FinalClose(
        fresh(lab, 1, 3),
        2,
        IngestEnd.RUN_FAILED,
        RunStatus.FAILED,
        ["run-started", "page-completed", "storage-failed"],
        "finish_run:failed",
    )


FINAL_CLOSE_ENDINGS = ["ac1-run", "ac4-run", "refused-exclusion", "recovery"]
FINAL_CLOSE_ERRORS = [
    pytest.param(lambda: OSError(REFUSAL_TEXT), OSError, id="os-error"),
    pytest.param(lambda: MemoryError(), MemoryError, id="memory-error"),
]


def assert_the_run_ended_as_determined(
    lab: Lab, outcome: IngestOutcome, ending: FinalClose
) -> None:
    """Nothing was added to the run after the outcome, and the stored run is as is."""
    if ending.events is None:
        assert lab.database.runs == {}
        assert lab.reporter.started == []
        return
    run_id = created(outcome)
    assert lab.event_types(run_id) == ending.events
    assert lab.journal.labels(run_id)[-1] == ending.last_write
    assert len(written(lab, "finish_run")) == 1
    assert lab.database.runs[run_id].status is ending.run_status


@pytest.mark.parametrize("name", FINAL_CLOSE_ENDINGS)
@pytest.mark.parametrize(("make_error", "error"), FINAL_CLOSE_ERRORS)
def test_final_close_error_never_changes_how_the_run_ended(
    lab: Lab,
    make_error: Callable[[], BaseException],
    error: type[BaseException],
    name: str,
) -> None:
    """F-22, experiment E8: an `Exception` from the final close is suppressed.

    The outcome already determined is returned unchanged, nothing escapes, nothing is
    added to the run, and no message names the close or the error.
    """
    ending = arrange_final_close(lab, name)
    lab.opener.close_faults[ending.open_index] = [
        lab.faults.close_raises(make_error, when="after")
    ]

    outcome = call_without_escape(lab, ending.request)

    assert outcome.end is ending.end
    assert outcome.run_status is ending.run_status
    assert (outcome.execution_id is None) == (ending.run_status is None)
    assert_the_run_ended_as_determined(lab, outcome, ending)
    assert not any(
        "close" in message.lower()
        or error.__name__ in message
        or REFUSAL_TEXT in message
        for message in lab.reporter.messages
    ), lab.reporter.messages
    assert lab.opener.all_closed


@pytest.mark.parametrize("name", FINAL_CLOSE_ENDINGS)
def test_final_close_interrupt_keeps_the_outcome_and_records_the_interrupt(
    lab: Lab, name: str
) -> None:
    """F-22, experiment E7: Ctrl+C during the final close, after it delegated.

    The determined outcome is returned as INTERRUPTED with the same run and the same
    confirmed status (`None` when no run exists); the message says the ingest was
    interrupted; the run is not read or written because of it; nothing escapes.
    """
    ending = arrange_final_close(lab, name)
    lab.opener.close_faults[ending.open_index] = [
        lab.faults.close_raises(lambda: KeyboardInterrupt(), when="after")
    ]

    outcome = call_without_escape(lab, ending.request)

    assert outcome.end is IngestEnd.INTERRUPTED
    assert outcome.run_status is ending.run_status
    assert (outcome.execution_id is None) == (ending.run_status is None)
    assert "interrupt" in outcome.message.lower(), outcome.message
    assert_the_run_ended_as_determined(lab, outcome, ending)
    assert lab.opener.all_closed


# === generic_fallback (AC15; F-20, E6) =========================================
#
# Plan Revision 9: a non-database exception before the run exists, with no lost
# connection, outside the recovery window, ends `NOT_STARTED` with no run.


@pytest.mark.parametrize(
    ("make_error", "error"),
    [
        pytest.param(lambda: MemoryError(), MemoryError, id="memory-error"),
        pytest.param(
            lambda: SyntheticDefect(BODY_MARKER), SyntheticDefect, id="synthetic-defect"
        ),
    ],
)
def test_generic_fallback_a_start_run_defect_ends_not_started_with_no_run(
    lab: Lab, make_error: Callable[[], BaseException], error: type[BaseException]
) -> None:
    """E6: `start_run` raises before delegating -> NOT_STARTED, nothing written.

    No run, no id, no `run_started`, no request; the message is at most the class
    name and holds no marker; one repository is opened and closed.
    """
    lab.script_ids(FREE_ID)
    lab.opener.faults[1] = [lab.faults.raises("start_run", make_error)]

    outcome = call_without_escape(lab, fresh(lab, 1, 3))

    assert_not_started(outcome)
    assert BODY_MARKER not in outcome.message
    assert set(CAMEL_CASE.findall(outcome.message)) <= {error.__name__}
    assert lab.database.runs == {}
    assert lab.reporter.started == []
    assert lab.source.requests == []
    assert not any(BODY_MARKER in message for message in lab.reporter.messages)
    assert lab.opener.opens == 1
    assert lab.opener.all_closed


# === start_run_second_loss (AC8, AC15; sweep N-1) ==============================
#
# Plan Revision 10, § State machine C step 6: when the repeat of `start_run` on the
# second repository is lost too, the second loss gives `RUN_FAILED` with `running`;
# a Ctrl+C that lands afterwards gives no run, and so does any other exception. The
# code behaves this way at `beadcf8`: these tests protect the round 5 restructuring.


def lose_start_run_twice(lab: Lab, first: Moment, second: Moment) -> None:
    """`start_run` is lost on the first repository and again on the second one."""
    lab.script_ids(FREE_ID)
    lost_at(lab, "start_run", None, first)
    lost_at(lab, "start_run", None, second, open_index=2)


def assert_nothing_after_the_second_loss(lab: Lab) -> None:
    """The second lost `start_run` is the last call any repository received."""
    attempts = lab.opener.attempts
    assert [a.open_index for a in lab.opener.attempts_of("start_run")] == [1, 2]
    assert attempts[-1].operation == "start_run"
    assert attempts[-1].open_index == 2
    assert not any("read_run" in message for message in lab.reporter.messages)
    assert lab.reporter.started == []
    assert lab.events(FREE_ID) == []
    assert lab.source.requests == []
    stored = lab.database.runs.get(FREE_ID)
    assert stored is None or stored.status is RunStatus.RUNNING
    assert lab.opener.opens == 2
    assert lab.opener.all_closed


def assert_no_run_is_known(
    outcome: IngestOutcome, end: IngestEnd, error: type[BaseException]
) -> None:
    """The outcome names no run, whether or not the first `start_run` committed."""
    assert outcome.end is end
    assert outcome.execution_id is None
    assert outcome.run_status is None
    assert REFUSAL_TEXT not in outcome.message
    assert set(CAMEL_CASE.findall(outcome.message)) <= {error.__name__}


@pytest.mark.parametrize("second", WHEN)
@pytest.mark.parametrize("first", WHEN)
def test_start_run_second_loss_leaves_the_run_running_with_two_lines(
    lab: Lab, first: Moment, second: Moment
) -> None:
    """C step 6: `RUN_FAILED`, the drawn id, `running`; two lines name `start_run`."""
    lose_start_run_twice(lab, first, second)

    outcome = call_without_escape(lab, fresh(lab, 1, 3))

    assert outcome.end is IngestEnd.RUN_FAILED
    assert outcome.execution_id == FREE_ID
    assert outcome.run_status is RunStatus.RUNNING
    lines = progress_lines(lab, "start_run", FREE_ID)
    assert len(lines) == 2, lab.reporter.messages
    for line in lines:
        assert_names_at_most(line, PersistenceConnectionError)
    assert_clean_messages(lab)
    assert_nothing_after_the_second_loss(lab)


SECOND_LOSS_INTERRUPTIONS = [
    pytest.param(
        lambda: KeyboardInterrupt(),
        IngestEnd.INTERRUPTED,
        KeyboardInterrupt,
        id="ctrl-c",
    ),
    pytest.param(
        lambda: MemoryError(), IngestEnd.NOT_STARTED, MemoryError, id="memory-error"
    ),
]


@pytest.mark.parametrize("when", WHEN)
@pytest.mark.parametrize(("make_error", "end", "error"), SECOND_LOSS_INTERRUPTIONS)
@pytest.mark.parametrize("second", WHEN)
@pytest.mark.parametrize("first", WHEN)
def test_start_run_second_loss_an_exception_on_the_second_line_gives_no_run(
    lab: Lab,
    first: Moment,
    second: Moment,
    make_error: Callable[[], BaseException],
    end: IngestEnd,
    error: type[BaseException],
    when: Moment,
) -> None:
    """C step 6: the reporter raises on the second line that names `start_run`.

    Ctrl+C gives INTERRUPTED and `MemoryError` NOT_STARTED, both with no run and
    `run_started` not called; nothing is written; no third connection is opened.
    """
    lose_start_run_twice(lab, first, second)
    reporter = lab.raising_reporter(
        "start_run", FREE_ID, error=make_error, nth=2, when=when
    )

    outcome = call_without_escape(lab, fresh(lab, 1, 3))

    assert reporter.fired
    assert_no_run_is_known(outcome, end, error)
    assert_nothing_after_the_second_loss(lab)


# === unexpected_cleanup_interrupt (AC7, AC15; sweep N-2) =======================
#
# Plan Revision 10, § Public names and § State machine K: any `KeyboardInterrupt`
# during the cleanup propagates out of `run_ingest`, whatever the cleanup was entered
# for. Here it was entered for a `MemoryError` or a synthetic exception at page 2.
# `_cleanup_step` and K's handler catch `Exception` only, so these protect the code.


@dataclass(frozen=True)
class CleanupInterrupt:
    """Where the second Ctrl+C lands in the cleanup, and what must hold after it."""

    store: RawEvidenceStore | None
    last_operation: str
    appended: bool
    status: RunStatus


def arrange_cleanup_interrupt(
    lab: Lab, where: str, make_error: Callable[[], BaseException]
) -> CleanupInterrupt:
    """Page 1 completes; `make_error` is raised at page 2; Ctrl+C lands in `where`."""
    lab.script_ids(FREE_ID)
    store: RawEvidenceStore | None = None
    if where == "record":
        # The store publishes sequence 2 and then raises: sequence 2 is pending.
        store = lab.publishes_then_fails(on_call=2, error=make_error)
    else:
        lab.source.script(2, make_error())
    faults = lab.opener.faults.setdefault(1, [])
    if where == "read-run":
        faults.append(
            lab.faults.raises(
                "read_run", lambda: KeyboardInterrupt(), nth=2, execution_id=FREE_ID
            )
        )
        return CleanupInterrupt(None, "read_run", False, RunStatus.RUNNING)
    if where == "reporter-line":
        faults.append(
            lab.faults.refuses(
                "read_run",
                lambda: PersistenceIntegrityError(REFUSAL_TEXT),
                nth=2,
                execution_id=FREE_ID,
            )
        )
        lab.raising_reporter(
            "read_run", FREE_ID, error=lambda: KeyboardInterrupt(), when="after"
        )
        return CleanupInterrupt(None, "read_run", False, RunStatus.RUNNING)
    if where == "record":
        faults.append(lab.faults.interrupts("record_observation", detail="2"))
        return CleanupInterrupt(store, "record_observation", False, RunStatus.RUNNING)
    moment: Moment = "after" if where.endswith("after") else "before"
    if where.startswith("append"):
        faults.append(
            lab.faults.interrupts(
                "append_audit_event", detail="unexpected-error", when=moment
            )
        )
        return CleanupInterrupt(
            None, "append_audit_event", moment == "after", RunStatus.RUNNING
        )
    assert where.startswith("finish")
    faults.append(lab.faults.interrupts("finish_run", detail="failed", when=moment))
    return CleanupInterrupt(
        None,
        "finish_run",
        True,
        RunStatus.FAILED if moment == "after" else RunStatus.RUNNING,
    )


CLEANUP_INTERRUPT_PLACES = [
    "read-run",
    "append-before",
    "append-after",
    "finish-before",
    "finish-after",
    "record",
    "reporter-line",
]
UNEXPECTED_TRIGGERS = [
    pytest.param(lambda: MemoryError(), id="memory-error"),
    pytest.param(lambda: SyntheticDefect(BODY_MARKER), id="synthetic-defect"),
]


@pytest.mark.parametrize("where", CLEANUP_INTERRUPT_PLACES)
@pytest.mark.parametrize("make_error", UNEXPECTED_TRIGGERS)
def test_unexpected_cleanup_interrupt_propagates_and_leaves_the_run_running(
    lab: Lab, make_error: Callable[[], BaseException], where: str
) -> None:
    """N-2: Ctrl+C during the cleanup of a `MemoryError` or a defect escapes.

    Nothing is attempted after the operation that raised, no event follows the
    `unexpected-error` append, and the run stays `running` (`failed` only when the
    `finish_run(FAILED)` delegated before it raised). The final close was attempted.
    """
    case = arrange_cleanup_interrupt(lab, where, make_error)

    with pytest.raises(KeyboardInterrupt):
        call_propagating(lab, fresh(lab, 1, 3), store=case.store)

    assert lab.opener.attempts[-1].operation == case.last_operation
    expected_events = ["run-started", "page-completed"]
    if case.appended:
        expected_events.append("unexpected-error")
    assert lab.event_types(FREE_ID) == expected_events
    assert lab.database.runs[FREE_ID].status is case.status
    assert lab.sequences(FREE_ID) == (1,)
    assert lab.reporter.started == [FREE_ID]
    assert lab.opener.opens == 1
    assert lab.opener.all_closed


# === recovery_double_fault (AC7, AC8 c, AC15; sweep N-3) =======================
#
# Plan Revision 10, § State machine C, "Two or more exceptions": a Ctrl+C among them
# decides INTERRUPTED; otherwise the other exception decides, and it prevails over a
# `False`. Nothing is read or written and the cleanup is not entered.


@dataclass(frozen=True)
class DoubleFault:
    """What one case of N-3 expects once the faults are set."""

    exclusion_error: type[BaseException] | None
    end: IngestEnd
    opens: int
    other_session: bool


def arrange_double_fault(lab: Lab, kind: str, when: Moment) -> DoubleFault:
    """Set the two faults of one case; `when` places the close of the second repository."""
    exclusion = lab.faults
    if kind == "a":
        lab.opener.faults[2] = [
            exclusion.raises("try_acquire_ingest_exclusion", lambda: MemoryError())
        ]
        lab.opener.close_faults[2] = [
            lab.faults.close_raises(lambda: KeyboardInterrupt(), when=when)
        ]
        return DoubleFault(MemoryError, IngestEnd.INTERRUPTED, 2, False)
    if kind == "b":
        lab.opener.faults[2] = [
            exclusion.raises(
                "try_acquire_ingest_exclusion", lambda: KeyboardInterrupt()
            )
        ]
        lab.opener.close_faults[2] = [
            lab.faults.close_raises(lambda: MemoryError(), when=when)
        ]
        return DoubleFault(KeyboardInterrupt, IngestEnd.INTERRUPTED, 2, False)
    if kind == "c-memory-then-ctrl-c":
        lab.opener.close_faults[1] = [
            lab.faults.close_raises(lambda: MemoryError(), when="before"),
            lab.faults.close_raises(lambda: KeyboardInterrupt(), when="after"),
        ]
        return DoubleFault(None, IngestEnd.INTERRUPTED, 1, False)
    if kind == "c-ctrl-c-then-memory":
        lab.opener.close_faults[1] = [
            lab.faults.close_raises(lambda: KeyboardInterrupt(), when="before"),
            lab.faults.close_raises(lambda: MemoryError(), when="after"),
        ]
        return DoubleFault(None, IngestEnd.INTERRUPTED, 1, False)
    if kind == "d-os-error":
        lab.opener.faults[2] = [
            exclusion.raises("try_acquire_ingest_exclusion", lambda: MemoryError())
        ]
        lab.opener.close_faults[2] = [
            lab.faults.close_raises(lambda: OSError(REFUSAL_TEXT), when="after")
        ]
        return DoubleFault(MemoryError, IngestEnd.RUN_FAILED, 2, False)
    assert kind == "d-false"
    lab.opener.close_faults[2] = [
        lab.faults.close_raises(lambda: MemoryError(), when="after")
    ]
    return DoubleFault(None, IngestEnd.RUN_FAILED, 2, True)


DOUBLE_FAULTS = [
    pytest.param("a", "after", id="a-memory-error-exclusion-ctrl-c-close-after"),
    pytest.param("a", "before", id="a-memory-error-exclusion-ctrl-c-close-before"),
    pytest.param("b", "after", id="b-ctrl-c-exclusion-memory-error-close-after"),
    pytest.param("b", "before", id="b-ctrl-c-exclusion-memory-error-close-before"),
    pytest.param("c-memory-then-ctrl-c", "after", id="c-memory-error-then-ctrl-c"),
    pytest.param("c-ctrl-c-then-memory", "after", id="c-ctrl-c-then-memory-error"),
    pytest.param("d-os-error", "after", id="d-exclusion-memory-error-close-os-error"),
    pytest.param("d-false", "after", id="d-false-close-memory-error"),
]


@pytest.mark.parametrize(("kind", "when"), DOUBLE_FAULTS)
def test_recovery_double_fault_the_precedence_decides_and_nothing_is_touched(
    lab: Lab, kind: str, when: Moment
) -> None:
    """N-3: a Ctrl+C among two exceptions gives INTERRUPTED, else the other decides.

    The lost operation is the observation of sequence 2. After the lost call nothing
    is attempted but the second opening, the second exclusion and the closes; the
    exclusion line is written only when the exclusion raised, named alone; every
    repository ends closed; nothing escapes.
    """
    probe = Loss(lab, other_session=kind == "d-false")
    request, operation, detail = arrange_loss(lab, "observation", probe)
    case = arrange_double_fault(lab, kind, when)

    outcome = call_without_escape(lab, request)

    assert outcome.end is case.end
    assert outcome.execution_id == FREE_ID
    assert outcome.run_status is RunStatus.RUNNING
    assert lab.database.runs[FREE_ID].status is RunStatus.RUNNING
    assert_the_run_was_not_touched(lab, probe)
    expected_attempts = ["2 try_acquire_ingest_exclusion"] if case.opens == 2 else []
    assert attempts_after_the_loss(lab, operation, detail) == expected_attempts
    if case.exclusion_error is None:
        assert progress_lines(lab, "try_acquire_ingest_exclusion") == []
    else:
        line = assert_one_progress_line(
            lab, "try_acquire_ingest_exclusion", case.exclusion_error
        )
        assert_names_no_run(line)
    assert_names_no_read_of_the_run(lab)
    assert lab.opener.opens == case.opens
    assert lab.opener.all_closed


WINDOW_DOUBLE_FAULTS = [
    pytest.param("a", "after", IngestEnd.INTERRUPTED, KeyboardInterrupt, id="a-after"),
    pytest.param(
        "a", "before", IngestEnd.INTERRUPTED, KeyboardInterrupt, id="a-before"
    ),
    pytest.param("b", "after", IngestEnd.INTERRUPTED, KeyboardInterrupt, id="b-after"),
    pytest.param(
        "b", "before", IngestEnd.INTERRUPTED, KeyboardInterrupt, id="b-before"
    ),
    pytest.param("d-false", "after", IngestEnd.NOT_STARTED, MemoryError, id="d-false"),
]


@pytest.mark.parametrize(("kind", "when", "end", "error"), WINDOW_DOUBLE_FAULTS)
def test_recovery_double_fault_while_start_run_is_pending_gives_no_run(
    lab: Lab, kind: str, when: Moment, end: IngestEnd, error: type[BaseException]
) -> None:
    """N-3 with `start_run` lost before commit: a `False` yields to a `MemoryError`.

    (a) and (b) give INTERRUPTED with no run; the `False` with a `MemoryError` from
    the close gives NOT_STARTED with no run; nothing is written, nothing announced.
    """
    probe = Loss(lab, other_session=kind == "d-false")
    request, operation, detail = arrange_loss(lab, "start-run", probe)
    case = arrange_double_fault(lab, kind, when)

    outcome = call_without_escape(lab, request)

    assert_window_outcome(lab, outcome, end, error)
    assert_the_run_was_not_touched(lab, probe)
    assert attempts_after_the_loss(lab, operation, detail) == [
        "2 try_acquire_ingest_exclusion"
    ]
    assert_names_no_read_of_the_run(lab)
    assert lab.opener.opens == case.opens
    assert lab.opener.all_closed


# === refusal_not_retried (AC6 c, AC6 e, AC7, AC15; sweep N-4) ==================
#
# Plan Revision 10, § State machine P and K: a write the database refused is answered
# and never attempted again in the invocation, the cleanup included. A refused
# `record_observation` ends its pending period at the refusal; after a refused
# `finish_run(FAILED)` nothing more is written. The refusal wrapper refuses every call
# of the operation, so a retry would be refused again.

REFUSAL_FLAVORS = [PersistenceIntegrityError, PersistenceError]
INTERRUPTIONS = [
    pytest.param(
        lambda: KeyboardInterrupt(),
        IngestEnd.INTERRUPTED,
        "run-interrupted",
        id="ctrl-c",
    ),
    pytest.param(
        lambda: MemoryError(),
        IngestEnd.RUN_FAILED,
        "unexpected-error",
        id="memory-error",
    ),
]


def refuse_every_call(
    lab: Lab,
    operation: str,
    error: Callable[[str], PersistenceError],
    *,
    detail: str | None = None,
    open_index: int = 1,
) -> None:
    """The repository number `open_index` refuses each of the next calls."""
    lab.opener.faults.setdefault(open_index, []).extend(
        lab.faults.refuses(operation, lambda: error(REFUSAL_TEXT), detail=detail)
        for _ in range(3)
    )


def assert_refusal_answered_once(
    lab: Lab,
    outcome: IngestOutcome,
    *,
    end: IngestEnd,
    event_type: str,
    recorded: bool,
    records: list[int],
    current: int,
    lines_before: int = 0,
) -> None:
    """The refused observation 2 is attempted once per repository, never by the cleanup."""
    assert [
        a.open_index for a in lab.opener.attempts_of("record_observation", "2")
    ] == records
    assert outcome.end is end
    assert outcome.execution_id == FREE_ID
    assert outcome.run_status is RunStatus.FAILED
    assert lab.event_types(FREE_ID) == ["run-started", "page-completed", event_type]
    expected = (
        {"page": 2}
        if event_type == "run-interrupted"
        else {
            "page": 2,
            "error_type": "MemoryError",
        }
    )
    assert lab.details(FREE_ID, event_type) == [expected]
    assert lab.details(FREE_ID, "storage-failed") == []
    assert_follows_catalogue(lab.events(FREE_ID))
    assert lab.sequences(FREE_ID) == (1,)
    assert lab.local_sequences(FREE_ID) == (1, 2)
    # The cleanup ran on the current repository: `read_run`, then the close of the run.
    assert lab.opener.attempts_of("read_run")[-1].open_index == current
    assert [a.open_index for a in lab.opener.attempts_of("finish_run", "failed")] == [
        current
    ]
    lines = progress_lines(lab, "record_observation", FREE_ID)
    assert len(lines) == lines_before + (1 if recorded else 0), lab.reporter.messages
    if recorded:
        assert number_in(lines[-1], 2), lines
    assert lab.opener.all_closed


@pytest.mark.parametrize("when", WHEN)
@pytest.mark.parametrize(("make_error", "end", "event_type"), INTERRUPTIONS)
@pytest.mark.parametrize("refusal", REFUSAL_FLAVORS)
def test_refusal_not_retried_a_refused_observation_is_not_recorded_by_the_cleanup(
    lab: Lab,
    refusal: type[PersistenceError],
    make_error: Callable[[], BaseException],
    end: IngestEnd,
    event_type: str,
    when: Moment,
) -> None:
    """Case (i), P step 4: the interruption lands on the line of the refusal.

    `record_observation` of sequence 2 is attempted once; the cleanup reads the run,
    appends `run-interrupted` (or `unexpected-error`) and closes it `failed`; there is
    no `storage-failed` and no observation 2 in PostgreSQL, while the store keeps it.
    """
    lab.script_ids(FREE_ID)
    refuse_every_call(lab, "record_observation", refusal, detail="2")
    reporter = lab.raising_reporter(
        "record_observation", FREE_ID, error=make_error, when=when
    )

    outcome = call_without_escape(lab, fresh(lab, 1, 3))

    assert reporter.fired
    assert_refusal_answered_once(
        lab,
        outcome,
        end=end,
        event_type=event_type,
        recorded=when == "after",
        records=[1],
        current=1,
    )
    assert lab.opener.opens == 1


@pytest.mark.parametrize("when", WHEN)
@pytest.mark.parametrize(("make_error", "end", "event_type"), INTERRUPTIONS)
@pytest.mark.parametrize("refusal", REFUSAL_FLAVORS)
def test_refusal_not_retried_a_refused_read_back_record_is_not_recorded_by_the_cleanup(
    lab: Lab,
    refusal: type[PersistenceError],
    make_error: Callable[[], BaseException],
    end: IngestEnd,
    event_type: str,
    when: Moment,
) -> None:
    """Case (ii), the read-back path: the store publishes 2 and fails, PostgreSQL refuses.

    The read-back finds observation 2 and its record is refused once; the interruption
    on the refusal's line does not make the cleanup record it again.
    """
    lab.script_ids(FREE_ID)
    refuse_every_call(lab, "record_observation", refusal, detail="2")
    reporter = lab.raising_reporter(
        "record_observation", FREE_ID, error=make_error, when=when
    )
    store = lab.publishes_then_fails(on_call=2)

    outcome = call_without_escape(lab, fresh(lab, 1, 3), store=store)

    assert reporter.fired
    assert_refusal_answered_once(
        lab,
        outcome,
        end=end,
        event_type=event_type,
        recorded=when == "after",
        records=[1],
        current=1,
    )
    assert lab.opener.opens == 1


@pytest.mark.parametrize("when", WHEN)
@pytest.mark.parametrize(("make_error", "end", "event_type"), INTERRUPTIONS)
@pytest.mark.parametrize("refusal", REFUSAL_FLAVORS)
def test_refusal_not_retried_a_refused_repeat_on_the_second_repository_is_not_recorded_again(
    lab: Lab,
    refusal: type[PersistenceError],
    make_error: Callable[[], BaseException],
    end: IngestEnd,
    event_type: str,
    when: Moment,
) -> None:
    """Case (iii): the record is lost on the first repository, refused on the second.

    It is attempted once on each; the interruption on the refusal's line (the second
    line that names `record_observation`, the first being the loss) does not make the
    cleanup record it a third time; the cleanup runs on the second repository.
    """
    lab.script_ids(FREE_ID)
    lab.opener.faults[1] = [
        lab.faults.lost_before_commit("record_observation", detail="2")
    ]
    refuse_every_call(lab, "record_observation", refusal, detail="2", open_index=2)
    reporter = lab.raising_reporter(
        "record_observation", FREE_ID, error=make_error, nth=2, when=when
    )

    outcome = call_without_escape(lab, fresh(lab, 1, 3))

    assert reporter.fired
    assert_refusal_answered_once(
        lab,
        outcome,
        end=end,
        event_type=event_type,
        recorded=when == "after",
        records=[1, 2],
        current=2,
        lines_before=1,
    )
    assert lab.opener.opens == 2


@pytest.mark.parametrize("when", WHEN)
@pytest.mark.parametrize(
    ("make_error", "end"),
    [
        pytest.param(lambda: KeyboardInterrupt(), IngestEnd.INTERRUPTED, id="ctrl-c"),
        pytest.param(lambda: MemoryError(), IngestEnd.RUN_FAILED, id="memory-error"),
    ],
)
@pytest.mark.parametrize("refusal", REFUSAL_FLAVORS)
def test_refusal_not_retried_a_refused_failing_finish_writes_nothing_more(
    lab: Lab,
    refusal: type[PersistenceError],
    make_error: Callable[[], BaseException],
    end: IngestEnd,
    when: Moment,
) -> None:
    """Case (iv): `finish_run(FAILED)` is refused on the AC4 path (page 2 answers 500).

    The interruption lands on the refusal's line. `finish_run(FAILED)` is attempted
    once; nothing is read or written after the refusal (no `run-interrupted`, no
    `unexpected-error`); the run stays `running`.
    """
    lab.script_ids(FREE_ID)
    lab.source.script(2, lab.status_failure(2, 500))
    refuse_every_call(lab, "finish_run", refusal, detail="failed")
    reporter = lab.raising_reporter("finish_run", FREE_ID, error=make_error, when=when)

    outcome = call_without_escape(lab, fresh(lab, 1, 3))

    assert reporter.fired
    assert outcome.end is end
    assert outcome.execution_id == FREE_ID
    assert outcome.run_status is RunStatus.RUNNING
    assert [a.open_index for a in lab.opener.attempts_of("finish_run", "failed")] == [1]
    assert lab.opener.attempts[-1].operation == "finish_run"
    assert lab.event_types(FREE_ID) == ["run-started", "page-completed", "page-failed"]
    assert lab.database.runs[FREE_ID].status is RunStatus.RUNNING
    lines = progress_lines(lab, "finish_run", FREE_ID)
    assert len(lines) == (1 if when == "after" else 0), lab.reporter.messages
    assert lab.opener.opens == 1
    assert lab.opener.all_closed


@pytest.mark.parametrize("refusal", REFUSAL_FLAVORS)
def test_refusal_not_retried_control_the_answering_append_interrupted(
    lab: Lab, refusal: type[PersistenceError]
) -> None:
    """Control (v), expected green: the `storage-failed` append that answers (i) raises Ctrl+C.

    It raises before delegating, so no run write was refused again: observation 2 was
    attempted once and the cleanup appends `run-interrupted` and finishes `failed`.
    """
    lab.script_ids(FREE_ID)
    refuse_every_call(lab, "record_observation", refusal, detail="2")
    lab.opener.faults[1].append(
        lab.faults.interrupts("append_audit_event", detail="storage-failed")
    )

    outcome = call_without_escape(lab, fresh(lab, 1, 3))

    assert outcome.end is IngestEnd.INTERRUPTED
    assert outcome.execution_id == FREE_ID
    assert outcome.run_status is RunStatus.FAILED
    assert [
        a.open_index for a in lab.opener.attempts_of("record_observation", "2")
    ] == [1]
    assert lab.event_types(FREE_ID) == [
        "run-started",
        "page-completed",
        "run-interrupted",
    ]
    assert lab.details(FREE_ID, "run-interrupted") == [{"page": 2}]
    assert_follows_catalogue(lab.events(FREE_ID))
    assert lab.opener.opens == 1
    assert lab.opener.all_closed


def test_refusal_not_retried_control_an_interrupt_before_any_write_records_once(
    lab: Lab,
) -> None:
    """Control (vi), expected green: Ctrl+C on the page line of sequence 2 (F-01).

    No write was attempted yet, so the cleanup records observation 2 exactly once,
    then appends `run-interrupted` and closes the run `failed`.
    """
    lab.script_ids(FREE_ID)
    reporter = lab.raising_reporter(
        digest(lab.body(2)), error=lambda: KeyboardInterrupt(), when="after"
    )

    outcome = call_without_escape(lab, fresh(lab, 1, 3))

    assert reporter.fired
    assert outcome.end is IngestEnd.INTERRUPTED
    assert outcome.execution_id == FREE_ID
    assert outcome.run_status is RunStatus.FAILED
    assert [
        a.open_index for a in lab.opener.attempts_of("record_observation", "2")
    ] == [1]
    assert lab.sequences(FREE_ID) == (1, 2)
    assert lab.event_types(FREE_ID) == [
        "run-started",
        "page-completed",
        "run-interrupted",
    ]
    assert lab.journal.labels(FREE_ID)[-4:] == [
        "store:2",
        "record_observation:2",
        "append:run-interrupted",
        "finish_run:failed",
    ]
    assert lab.opener.all_closed


# === Audit round 5 rework, step 2 (2026-10-21), plan Revision 11 ================
#
# Written against the Revision 13/11/8 specs (approved on 2026-10-21), before the
# rework of `run_ingest`. Tokens, by finding:
#
# - F-24 (decision D-1, option A: a `SystemExit` always wins and is preserved):
#   `system_exit_window` and `system_exit_final_close` (the command-tier tokens
#   `exit_code_system_exit_final_close` and `system_exit_command_end` are in
#   `test_ingest_command.py`). Kills M5, M14 and M15.
# - F-25 (required paths that no test pinned): `window_line_fault` (M16),
#   `close_while_propagating` (M15), `p2_read_run_loss_line` (M28) and
#   `interrupted_outcome_close`. They protect behavior that already holds.
# - F-23 (decision D-2, option 1: the current behavior): `refusal_then_interrupt`.
#
# No new double: the faults, the close fault, the raising reporter and the refusal
# wrapper already accept any `BaseException`. `Raised` only remembers the exception
# objects a fault made, so that a test can check that the very object propagates.


class Raised:
    """A maker of exceptions that remembers each one it made.

    It is passed wherever a fault takes `Callable[[], BaseException]`, so that the
    test can check, by identity, which exception object leaves `run_ingest`.
    """

    def __init__(self, make: Callable[[], BaseException]) -> None:
        self._make = make
        self.made: list[BaseException] = []

    def __call__(self) -> BaseException:
        error = self._make()
        self.made.append(error)
        return error

    @property
    def first(self) -> BaseException:
        assert self.made, "the fault never raised"
        return self.made[0]


def interrupt_error() -> BaseException:
    return KeyboardInterrupt()


def memory_error() -> BaseException:
    return MemoryError()


def os_error() -> BaseException:
    return OSError(REFUSAL_TEXT)


def synthetic_defect() -> BaseException:
    return SyntheticDefect(BODY_MARKER)


def call_exiting(
    lab: Lab,
    request: IngestRequest | ResumeRequest,
    *,
    store: RawEvidenceStore | None = None,
) -> SystemExit:
    """The call, which must end through a `SystemExit`: return that very object.

    Any other exception that escapes (a `KeyboardInterrupt` included, which would end
    the whole pytest session) fails the test by name.
    """
    try:
        with pytest.raises(SystemExit) as stop:
            call_propagating(lab, request, store=store)
    except (Exception, KeyboardInterrupt) as error:
        raise AssertionError(
            f"run_ingest let {type(error).__name__} escape in place of the SystemExit"
        ) from error
    return stop.value


# === system_exit_window (AC7, AC8 c, AC15; F-24, decision D-1, M5) ==============
#
# Plan § Public names, "`SystemExit`": in the window of State machine C a
# `SystemExit` always wins, whatever else arrives and in whatever order. It leaves
# `run_ingest` as the very object that was raised, nothing more is read or written,
# K is not entered, and every repository is still closed.


def arrange_system_exit_window(
    lab: Lab, case: str, when: Moment
) -> tuple[Raised, list[str]]:
    """Set the faults of one case of F-24 in the window; `record_observation` 2 is lost.

    Return the maker of the `SystemExit(3)` and the attempts expected after the lost
    call (the second exclusion, when a second repository was opened).
    """
    exits = Raised(lambda: SystemExit(3))
    after_a_second_open = ["2 try_acquire_ingest_exclusion"]
    if case == "a":
        lab.opener.faults[2] = [
            lab.faults.raises("try_acquire_ingest_exclusion", interrupt_error)
        ]
        lab.opener.close_faults[2] = [lab.faults.close_raises(exits, when=when)]
        return exits, after_a_second_open
    if case == "b":
        lab.opener.faults[2] = [
            lab.faults.raises("try_acquire_ingest_exclusion", exits)
        ]
        lab.opener.close_faults[2] = [
            lab.faults.close_raises(interrupt_error, when=when)
        ]
        return exits, after_a_second_open
    if case == "c":
        lab.opener.faults[2] = [
            lab.faults.raises("try_acquire_ingest_exclusion", interrupt_error)
        ]
        lab.raising_reporter("try_acquire_ingest_exclusion", error=exits, when=when)
        return exits, after_a_second_open
    if case == "d":
        lab.opener.close_faults[1] = [
            lab.faults.close_raises(exits, when="before"),
            lab.faults.close_raises(interrupt_error, when="after"),
        ]
        return exits, []
    assert case == "e"
    lab.opener.close_faults[1] = [
        lab.faults.close_raises(interrupt_error, when="before"),
        lab.faults.close_raises(exits, when="after"),
    ]
    return exits, []


SYSTEM_EXIT_WINDOW_CASES = [
    pytest.param("a", "after", id="a-exclusion-ctrl-c-close-system-exit-after"),
    pytest.param("a", "before", id="a-exclusion-ctrl-c-close-system-exit-before"),
    pytest.param("b", "after", id="b-exclusion-system-exit-close-ctrl-c-after"),
    pytest.param("b", "before", id="b-exclusion-system-exit-close-ctrl-c-before"),
    pytest.param("c", "after", id="c-exclusion-ctrl-c-line-system-exit-after"),
    pytest.param("c", "before", id="c-exclusion-ctrl-c-line-system-exit-before"),
    pytest.param("d", "after", id="d-step-1-close-system-exit-final-close-ctrl-c"),
    pytest.param("e", "after", id="e-step-1-close-ctrl-c-final-close-system-exit"),
]


@pytest.mark.parametrize(("case", "when"), SYSTEM_EXIT_WINDOW_CASES)
def test_system_exit_window_a_system_exit_wins_and_nothing_is_touched(
    lab: Lab, case: str, when: Moment
) -> None:
    """F-24, D-1: the `SystemExit(3)` the fault raised leaves `run_ingest` itself.

    After the lost call nothing is attempted except the window operations and the
    closes (no `read_run`); `<A>` keeps what it held at the loss and is `running`,
    with no `run-interrupted` and no `unexpected-error`; every repository is closed.
    """
    loss = Loss(lab, other_session=False)
    request, operation, detail = arrange_loss(lab, "observation", loss)
    exits, expected_attempts = arrange_system_exit_window(lab, case, when)

    stop = call_exiting(lab, request)

    assert stop is exits.first
    assert stop.code == 3
    assert lab.reporter.started == [FREE_ID]
    assert_the_run_was_not_touched(lab, loss)
    assert attempts_after_the_loss(lab, operation, detail) == expected_attempts
    assert lab.event_types(FREE_ID) == ["run-started", "page-completed"]
    assert lab.sequences(FREE_ID) == (1,)
    assert lab.database.runs[FREE_ID].status is RunStatus.RUNNING
    assert_names_no_read_of_the_run(lab)
    assert lab.opener.opens == (2 if expected_attempts else 1)
    assert lab.opener.all_closed


@pytest.mark.parametrize("when", WHEN)
def test_system_exit_window_while_start_run_is_pending_nothing_is_written(
    lab: Lab, when: Moment
) -> None:
    """Case (a) with `start_run` lost before commit: no run is known.

    The `SystemExit(3)` propagates, nothing is written and `run_started` is not called.
    """
    loss = Loss(lab, other_session=False)
    request, operation, detail = arrange_loss(lab, "start-run", loss)
    exits, expected_attempts = arrange_system_exit_window(lab, "a", when)

    stop = call_exiting(lab, request)

    assert stop is exits.first
    assert_the_run_was_not_touched(lab, loss)
    assert attempts_after_the_loss(lab, operation, detail) == expected_attempts
    assert lab.database.runs == {}
    assert lab.reporter.started == []
    assert_names_no_read_of_the_run(lab)
    assert lab.opener.opens == 2
    assert lab.opener.all_closed


# === system_exit_final_close (AC7, AC15; F-24, decision D-1, M14, M15) ==========
#
# Plan § Public names, "The final close" and "`SystemExit`": a `SystemExit` from the
# final close after the outcome was determined propagates and no outcome is returned;
# while a `SystemExit` propagates, nothing the final close raises replaces it, and
# every repository is attempted once; while another exception propagates, a
# `SystemExit` from the close replaces it.


@pytest.mark.parametrize("name", ["ac1-run", "ac4-run", "refused-exclusion"])
def test_system_exit_final_close_after_the_outcome_propagates_and_returns_no_outcome(
    lab: Lab, name: str
) -> None:
    """(f): the final close raises `SystemExit(3)` after delegating, outcome known.

    After the AC1 run, the AC4 run and a refused exclusion: the `SystemExit` leaves
    `run_ingest` and no outcome is returned; nothing was added to the run after the
    outcome (journal); the close was attempted once.
    """
    ending = arrange_final_close(lab, name)
    exits = Raised(lambda: SystemExit(3))
    lab.opener.close_faults[ending.open_index] = [
        lab.faults.close_raises(exits, when="after")
    ]

    stop = call_exiting(lab, ending.request)

    assert stop is exits.first
    assert stop.code == 3
    assert len(exits.made) == 1
    assert lab.opener.repositories[0].close_calls == 1
    if ending.events is None:
        assert lab.database.runs == {}
        assert lab.reporter.started == []
    else:
        assert lab.event_types(FREE_ID) == ending.events
        assert lab.journal.labels(FREE_ID)[-1] == ending.last_write
        assert len(written(lab, "finish_run")) == 1
        assert lab.database.runs[FREE_ID].status is ending.run_status
    assert lab.opener.all_closed


def test_system_exit_final_close_replaces_a_ctrl_c_that_propagates_from_the_cleanup(
    lab: Lab,
) -> None:
    """(g): the N-2 setup, with the final close raising `SystemExit(3)` after delegating.

    A `MemoryError` at page 2, then Ctrl+C from K's `unexpected-error` append before
    delegating: the `SystemExit(3)` propagates in place of the Ctrl+C; `<A>` is
    `running` with the events it had.
    """
    lab.script_ids(FREE_ID)
    lab.source.script(2, MemoryError())
    lab.opener.faults[1] = [
        lab.faults.interrupts("append_audit_event", detail="unexpected-error")
    ]
    exits = Raised(lambda: SystemExit(3))
    lab.opener.close_faults[1] = [lab.faults.close_raises(exits, when="after")]

    stop = call_exiting(lab, fresh(lab, 1, 3))

    assert stop is exits.first
    assert stop.code == 3
    assert lab.opener.attempts[-1].operation == "append_audit_event"
    assert lab.event_types(FREE_ID) == ["run-started", "page-completed"]
    assert lab.database.runs[FREE_ID].status is RunStatus.RUNNING
    assert lab.opener.repositories[0].close_calls == 1
    assert lab.opener.all_closed


@pytest.mark.parametrize(
    ("make_close_error", "when"),
    [
        pytest.param(interrupt_error, "after", id="close-ctrl-c-after"),
        pytest.param(interrupt_error, "before", id="close-ctrl-c-before"),
        pytest.param(lambda: SystemExit(4), "after", id="close-system-exit-4-after"),
    ],
)
def test_system_exit_final_close_the_first_system_exit_propagates(
    lab: Lab, make_close_error: Callable[[], BaseException], when: Moment
) -> None:
    """(h): the transport raises `SystemExit(3)` at page 2; the final close raises too.

    Whether it raises Ctrl+C (after or before delegating) or another `SystemExit`, the
    first one propagates; the close is attempted exactly once; `<A>` is `running` with
    page 1's events and nothing after them.
    """
    lab.script_ids(FREE_ID)
    first = SystemExit(3)
    lab.source.script(2, first)
    lab.opener.close_faults[1] = [lab.faults.close_raises(make_close_error, when=when)]

    stop = call_exiting(lab, fresh(lab, 1, 3))

    assert stop is first
    assert stop.code == 3
    assert lab.opener.repositories[0].close_calls == 1
    assert lab.event_types(FREE_ID) == ["run-started", "page-completed"]
    assert lab.sequences(FREE_ID) == (1,)
    assert lab.database.runs[FREE_ID].status is RunStatus.RUNNING
    assert lab.reporter.started == [FREE_ID]


# === window_line_fault (AC7, AC8 c, AC15; F-25, M16) ============================
#
# Plan § State machine C, "Two or more exceptions" and "The line rule of the window":
# a window operation (the second `open_repository()` or the second exclusion) that
# raises something other than a `PersistenceError` has its own line written; when
# that line raises in turn, `_prevailing` decides, so a Ctrl+C is never hidden.

WINDOW_LINE_CASES = [
    pytest.param(
        "exclusion",
        interrupt_error,
        memory_error,
        IngestEnd.INTERRUPTED,
        id="exclusion-ctrl-c-line-memory-error",
    ),
    pytest.param(
        "exclusion",
        interrupt_error,
        os_error,
        IngestEnd.INTERRUPTED,
        id="exclusion-ctrl-c-line-os-error",
    ),
    pytest.param(
        "open",
        interrupt_error,
        memory_error,
        IngestEnd.INTERRUPTED,
        id="open-ctrl-c-line-memory-error",
    ),
    pytest.param(
        "open",
        interrupt_error,
        os_error,
        IngestEnd.INTERRUPTED,
        id="open-ctrl-c-line-os-error",
    ),
    pytest.param(
        "exclusion",
        memory_error,
        interrupt_error,
        IngestEnd.INTERRUPTED,
        id="control-exclusion-memory-error-line-ctrl-c",
    ),
    pytest.param(
        "exclusion",
        synthetic_defect,
        memory_error,
        IngestEnd.RUN_FAILED,
        id="control-exclusion-defect-line-memory-error",
    ),
]


@pytest.mark.parametrize("when", WHEN)
@pytest.mark.parametrize(
    ("place", "make_window_error", "make_line_error", "end"), WINDOW_LINE_CASES
)
def test_window_line_fault_the_line_of_a_window_operation_never_hides_a_ctrl_c(
    lab: Lab,
    place: str,
    make_window_error: Callable[[], BaseException],
    make_line_error: Callable[[], BaseException],
    end: IngestEnd,
    when: Moment,
) -> None:
    """F-25: the window operation raises and the reporter raises on its line.

    A Ctrl+C among the two gives INTERRUPTED, else the window operation's exception
    decides (RUN_FAILED); `running` with `<A>` either way. After the lost call only the
    window operations and the closes are attempted (no `read_run`); nothing is written.
    """
    loss = Loss(lab, other_session=False)
    request, operation, detail = arrange_loss(lab, "observation", loss)
    if place == "exclusion":
        lab.opener.faults[2] = [
            lab.faults.raises("try_acquire_ingest_exclusion", make_window_error)
        ]
        words = "try_acquire_ingest_exclusion"
        expected_attempts = ["2 try_acquire_ingest_exclusion"]
    else:
        lab.opener.open_errors[2] = make_window_error
        words = "open_repository"
        expected_attempts = []
    reporter = lab.raising_reporter(words, error=make_line_error, when=when)

    outcome = call_without_escape(lab, request)

    assert reporter.fired
    assert outcome.end is end
    assert outcome.execution_id == FREE_ID
    assert outcome.run_status is RunStatus.RUNNING
    assert reporter.started == [FREE_ID]
    assert_the_run_was_not_touched(lab, loss)
    assert attempts_after_the_loss(lab, operation, detail) == expected_attempts
    assert lab.event_types(FREE_ID) == ["run-started", "page-completed"]
    assert lab.sequences(FREE_ID) == (1,)
    assert lab.database.runs[FREE_ID].status is RunStatus.RUNNING
    assert_names_no_read_of_the_run(lab)
    assert lab.opener.opens == 2
    assert lab.opener.all_closed


# === close_while_propagating (AC7, AC15; F-25, N-9, M15) ========================
#
# Plan § Public names, "The final close", last bullets: while a `KeyboardInterrupt`
# propagates out of `run_ingest`, the final close is still attempted; a
# `KeyboardInterrupt` from it propagates in its place (its own object); an `Exception`
# from it is suppressed and the propagating Ctrl+C goes on unchanged.


def arrange_propagating_ctrl_c(lab: Lab, setup: str) -> Raised:
    """A Ctrl+C that leaves `run_ingest` from State machine K; return its maker.

    `n2`: a `MemoryError` at page 2, then K's `unexpected-error` append raises Ctrl+C
    before delegating. `ac7`: Ctrl+C at page 2, then K's `run-interrupted` append
    raises a second one before delegating.
    """
    own = Raised(interrupt_error)
    lab.script_ids(FREE_ID)
    if setup == "n2":
        lab.source.script(2, MemoryError())
        event_type = "unexpected-error"
    else:
        assert setup == "ac7"
        lab.source.script(2, KeyboardInterrupt())
        event_type = "run-interrupted"
    lab.opener.faults[1] = [
        lab.faults.raises("append_audit_event", own, detail=event_type, when="before")
    ]
    return own


def assert_the_cleanup_wrote_nothing(lab: Lab) -> None:
    """K's append raised before delegating: `<A>` holds page 1's events and is `running`."""
    assert lab.event_types(FREE_ID) == ["run-started", "page-completed"]
    assert lab.sequences(FREE_ID) == (1,)
    assert lab.database.runs[FREE_ID].status is RunStatus.RUNNING
    assert lab.opener.repositories[0].close_calls == 1


@pytest.mark.parametrize("when", WHEN)
@pytest.mark.parametrize("setup", ["n2", "ac7"])
def test_close_while_propagating_a_ctrl_c_from_the_close_replaces_the_propagating_one(
    lab: Lab, setup: str, when: Moment
) -> None:
    """The close raises Ctrl+C (after delegating, and before) while K's Ctrl+C propagates.

    The Ctrl+C that leaves `run_ingest` is the close's own object, not K's; the close
    is attempted exactly once; in the after-delegating case the repository is closed.
    """
    own = arrange_propagating_ctrl_c(lab, setup)
    closing = Raised(interrupt_error)
    lab.opener.close_faults[1] = [lab.faults.close_raises(closing, when=when)]

    with pytest.raises(KeyboardInterrupt) as stop:
        call_propagating(lab, fresh(lab, 1, 3))

    assert stop.value is closing.first
    assert stop.value is not own.first
    assert_the_cleanup_wrote_nothing(lab)
    if when == "after":
        assert lab.opener.all_closed


@pytest.mark.parametrize("setup", ["n2", "ac7"])
def test_close_while_propagating_an_os_error_from_the_close_leaves_the_ctrl_c_unchanged(
    lab: Lab, setup: str
) -> None:
    """The close raises `OSError`: it is suppressed and K's own Ctrl+C leaves unchanged."""
    own = arrange_propagating_ctrl_c(lab, setup)
    lab.opener.close_faults[1] = [lab.faults.close_raises(os_error, when="after")]

    with pytest.raises(KeyboardInterrupt) as stop:
        call_propagating(lab, fresh(lab, 1, 3))

    assert stop.value is own.first
    assert_the_cleanup_wrote_nothing(lab)
    assert lab.opener.all_closed


# === p2_read_run_loss_line (AC8, AC15; F-25, C step 6, M28) =====================
#
# Plan § State machine C, step 6 (P-2): the final `finish_run(SUCCEEDED)` is lost, its
# repeat on the second repository is refused, and the `read_run` that decides what the
# refusal means is lost too. A loss makes no repository current before its line is
# written, so an exception on that line ends C with nothing more attempted.


@pytest.mark.parametrize("when", WHEN)
@pytest.mark.parametrize(
    ("make_error", "end"),
    [
        pytest.param(interrupt_error, IngestEnd.INTERRUPTED, id="ctrl-c"),
        pytest.param(memory_error, IngestEnd.RUN_FAILED, id="memory-error"),
    ],
)
def test_p2_read_run_loss_line_an_exception_on_the_line_ends_the_recovery(
    lab: Lab, make_error: Callable[[], BaseException], end: IngestEnd, when: Moment
) -> None:
    """The reporter raises on the line of the lost P-2 `read_run`.

    INTERRUPTED (or RUN_FAILED) with `<A>` and `running`; nothing is attempted on any
    repository after the lost `read_run`; at most one message names it; no
    `run-interrupted`, `unexpected-error`, `storage-failed` or `finish_run(FAILED)`.
    """
    lose_the_final_finish(lab, "before")
    lab.opener.faults[2] = [
        lab.faults.refuses(
            "finish_run",
            lambda: PersistenceIntegrityError(REFUSAL_TEXT),
            detail="succeeded",
        ),
        lab.faults.lost_before_commit("read_run", execution_id=FREE_ID),
    ]
    reporter = lab.raising_reporter("read_run", FREE_ID, error=make_error, when=when)

    outcome = call_without_escape(lab, fresh(lab, 1, 2))

    assert reporter.fired
    assert outcome.end is end
    assert outcome.execution_id == FREE_ID
    assert outcome.run_status is RunStatus.RUNNING
    last = lab.opener.attempts[-1]
    assert (last.open_index, last.operation) == (2, "read_run")
    # The drawn id was checked with a `read_run` on the first repository; the second
    # repository received only the P-2 `read_run`, never a second one from the cleanup.
    reads = [a for a in lab.opener.attempts_of("read_run") if a.open_index == 2]
    assert len(reads) == 1
    assert len(progress_lines(lab, "read_run")) <= 1, lab.reporter.messages
    assert lab.event_types(FREE_ID) == [
        "run-started",
        "page-completed",
        "page-completed",
    ]
    assert lab.opener.attempts_of("finish_run", "failed") == []
    assert lab.database.runs[FREE_ID].status is RunStatus.RUNNING
    assert lab.opener.opens == 2
    assert lab.opener.all_closed


# === interrupted_outcome_close (AC7, AC15; F-25) ================================
#
# Plan § Public names, "The final close": an `INTERRUPTED` outcome whose final close
# is interrupted keeps its run and its status.


def test_interrupted_outcome_close_keeps_the_run_and_its_status(lab: Lab) -> None:
    """The AC7 run (Ctrl+C at page 2), then Ctrl+C from the final close.

    K appends `run-interrupted` and finishes the run `failed`; the outcome stays
    INTERRUPTED with `<A>` and `failed`, and says the ingest was interrupted;
    `finish_run` was called once and nothing follows `run-interrupted`.
    """
    lab.script_ids(FREE_ID)
    lab.source.script(2, KeyboardInterrupt())
    lab.opener.close_faults[1] = [
        lab.faults.close_raises(interrupt_error, when="after")
    ]

    outcome = call_without_escape(lab, fresh(lab, 1, 3))

    assert outcome.end is IngestEnd.INTERRUPTED
    assert outcome.execution_id == FREE_ID
    assert outcome.run_status is RunStatus.FAILED
    assert "interrupt" in outcome.message.lower(), outcome.message
    assert len(written(lab, "finish_run")) == 1
    assert lab.event_types(FREE_ID) == [
        "run-started",
        "page-completed",
        "run-interrupted",
    ]
    assert lab.journal.labels(FREE_ID)[-2:] == [
        "append:run-interrupted",
        "finish_run:failed",
    ]
    assert lab.database.runs[FREE_ID].status is RunStatus.FAILED
    assert lab.opener.all_closed


# === refusal_then_interrupt (AC6 e, AC7, AC15; F-23, decision D-2 option 1) =====
#
# Plan § State machine K, with decision D-2 (option 1, the current behavior): after a
# refused write other than `finish_run(FAILED)`, an interruption that lands before the
# run is closed enters K. The cleanup audits it and closes the run `failed`; the
# refused write is not attempted again and its event is not added.

REFUSED_WRITES = ["page-failed", "storage-failed", "page-completed", "final-finish"]


@dataclass(frozen=True)
class RefusedWrite:
    """One refused write of F-23 and what the cleanup that follows must show."""

    request: IngestRequest
    store: RawEvidenceStore | None
    operation: str
    detail: str
    page: int
    events: list[str]

    @property
    def words(self) -> tuple[str, str]:
        """The two words of the refusal's line: the operation and its detail."""
        return self.operation, self.detail


def arrange_refused_write(
    lab: Lab, name: str, refusal: type[PersistenceError]
) -> RefusedWrite:
    """Refuse every call of one write (so that a retry would be refused again)."""
    lab.script_ids(FREE_ID)
    if name == "page-failed":
        lab.source.script(2, lab.status_failure(2, 500))
        refuse_every_call(lab, "append_audit_event", refusal, detail="page-failed")
        return RefusedWrite(
            fresh(lab, 1, 3),
            None,
            "append_audit_event",
            "page-failed",
            2,
            ["run-started", "page-completed"],
        )
    if name == "storage-failed":
        refuse_every_call(lab, "append_audit_event", refusal, detail="storage-failed")
        return RefusedWrite(
            fresh(lab, 1, 3),
            lab.refuses_to_store(on_call=2),
            "append_audit_event",
            "storage-failed",
            2,
            ["run-started", "page-completed"],
        )
    if name == "page-completed":
        refuse_every_call(lab, "append_audit_event", refusal, detail="page-completed")
        return RefusedWrite(
            fresh(lab, 1, 3),
            None,
            "append_audit_event",
            "page-completed",
            1,
            ["run-started"],
        )
    assert name == "final-finish"
    refuse_every_call(lab, "finish_run", refusal, detail="succeeded")
    return RefusedWrite(
        fresh(lab, 1, 2),
        None,
        "finish_run",
        "succeeded",
        2,
        ["run-started", "page-completed", "page-completed"],
    )


@pytest.mark.parametrize("when", WHEN)
@pytest.mark.parametrize(("make_error", "end", "event_type"), INTERRUPTIONS)
@pytest.mark.parametrize("refusal", REFUSAL_FLAVORS)
@pytest.mark.parametrize("name", REFUSED_WRITES)
def test_refusal_then_interrupt_the_cleanup_audits_it_and_closes_the_run_failed(
    lab: Lab,
    name: str,
    refusal: type[PersistenceError],
    make_error: Callable[[], BaseException],
    end: IngestEnd,
    event_type: str,
    when: Moment,
) -> None:
    """The interruption lands on the line of the refusal: K runs on the first repository.

    The refused call is attempted once; K reads the run, appends `run-interrupted` (or
    `unexpected-error`) for the page being processed and finishes the run `failed`;
    the refused event is not stored; there is no `storage-failed` and no second
    `finish_run`.
    """
    case = arrange_refused_write(lab, name, refusal)
    reporter = lab.raising_reporter(*case.words, error=make_error, when=when)

    outcome = call_without_escape(lab, case.request, store=case.store)

    assert reporter.fired
    assert outcome.end is end
    assert outcome.execution_id == FREE_ID
    assert outcome.run_status is RunStatus.FAILED
    assert len(lab.opener.attempts_of(case.operation, case.detail)) == 1
    assert lab.event_types(FREE_ID) == [*case.events, event_type]
    expected = (
        {"page": case.page}
        if event_type == "run-interrupted"
        else {"page": case.page, "error_type": "MemoryError"}
    )
    assert lab.details(FREE_ID, event_type) == [expected]
    assert lab.details(FREE_ID, "storage-failed") == []
    assert_follows_catalogue(lab.events(FREE_ID))
    assert lab.opener.attempts_of("read_run")[-1].open_index == 1
    assert len(lab.opener.attempts_of("finish_run", "failed")) == 1
    assert lab.database.runs[FREE_ID].status is RunStatus.FAILED
    assert lab.opener.opens == 1
    assert lab.opener.all_closed


@pytest.mark.parametrize("when", WHEN)
@pytest.mark.parametrize(("make_error", "end", "event_type"), INTERRUPTIONS)
@pytest.mark.parametrize("refusal", REFUSAL_FLAVORS)
def test_refusal_then_interrupt_a_refused_cleanup_append_stops_the_cleanup(
    lab: Lab,
    refusal: type[PersistenceError],
    make_error: Callable[[], BaseException],
    end: IngestEnd,
    event_type: str,
    when: Moment,
) -> None:
    """(v): case (i) with the cleanup's own append refused too.

    K's `run-interrupted` (or `unexpected-error`) append is refused, writes its one
    line and stops K: no `finish_run(FAILED)`, `<A>` stays `running`.
    """
    case = arrange_refused_write(lab, "page-failed", refusal)
    refuse_every_call(lab, "append_audit_event", refusal, detail=event_type)
    reporter = lab.raising_reporter(*case.words, error=make_error, when=when)

    outcome = call_without_escape(lab, case.request)

    assert reporter.fired
    assert outcome.end is end
    assert outcome.execution_id == FREE_ID
    assert outcome.run_status is RunStatus.RUNNING
    assert lab.event_types(FREE_ID) == case.events
    assert lab.opener.attempts_of("finish_run") == []
    assert len(progress_lines(lab, "append_audit_event", event_type)) == 1, (
        lab.reporter.messages
    )
    assert_follows_catalogue(lab.events(FREE_ID))
    assert lab.database.runs[FREE_ID].status is RunStatus.RUNNING
    assert lab.opener.opens == 1
    assert lab.opener.all_closed


# === Audit round 6 rework (2026-10-23), plan Revision 12 ========================
#
# Feature ingest-command (F4), outcome O10, rework of round 6, audit finding F-28
# (AC7, AC8 c, AC15; decision D-1: a `SystemExit` always wins and is preserved). The
# code already behaves as planned (audit experiments X29 to X31); these tests exist so
# that removing that behavior fails a test. Tokens: `system_exit_first_wins` (N31),
# `window_system_exit_line` (N38) and `cleanup_system_exit` (N39); the command-tier
# twin `exit_code_cleanup_system_exit` is in `test_ingest_command.py`. No new double:
# the faults, the close fault, the raising reporter and `RepositoryOpenerDouble` accept
# any `BaseException`, and `Raised` remembers the objects they made.


# === system_exit_first_wins (AC7, AC8 c, AC15; F-28, D-1, N31) ==================
#
# Plan § State machine C, "Two or more exceptions": of two `SystemExit` in the window
# the first one propagates, whatever order the closes and the line arrive in.


def arrange_first_system_exit(
    lab: Lab, case: str, when: Moment
) -> tuple[Raised, Raised]:
    """`record_observation` 2 is lost; two `SystemExit` meet in the window.

    `exclusion`: the second exclusion raises `SystemExit(3)` and the second
    repository's `close()` raises `SystemExit(4)`. `line`: the second exclusion raises
    Ctrl+C, its line raises `SystemExit(3)` (reporter, `when`) and that close raises
    `SystemExit(4)`. Return the makers of the first and of the second.
    """
    first = Raised(lambda: SystemExit(3))
    second = Raised(lambda: SystemExit(4))
    if case == "exclusion":
        lab.opener.faults[2] = [
            lab.faults.raises("try_acquire_ingest_exclusion", first)
        ]
    else:
        assert case == "line"
        lab.opener.faults[2] = [
            lab.faults.raises("try_acquire_ingest_exclusion", interrupt_error)
        ]
        lab.raising_reporter("try_acquire_ingest_exclusion", error=first, when=when)
    lab.opener.close_faults[2] = [lab.faults.close_raises(second, when=when)]
    return first, second


@pytest.mark.parametrize("when", WHEN)
@pytest.mark.parametrize(
    "case",
    [
        pytest.param("exclusion", id="exclusion-system-exit"),
        pytest.param("line", id="exclusion-ctrl-c-line-system-exit"),
    ],
)
def test_system_exit_first_wins_of_two_system_exit_in_the_window(
    lab: Lab, case: str, when: Moment
) -> None:
    """F-28, D-1: the `SystemExit(3)` raised first leaves `run_ingest`, never the second.

    The second repository's `close()` raises `SystemExit(4)` (after delegating, and
    before): the object that propagates is the first one. After the lost call only the
    second exclusion is attempted, nothing is read or written, `<A>` stays `running`,
    and every repository is closed.
    """
    loss = Loss(lab, other_session=False)
    request, operation, detail = arrange_loss(lab, "observation", loss)
    first, second = arrange_first_system_exit(lab, case, when)

    stop = call_exiting(lab, request)

    assert second.made, "the second SystemExit was never raised"
    assert stop is first.first
    assert stop is not second.first
    assert stop.code == 3
    assert_the_run_was_not_touched(lab, loss)
    assert attempts_after_the_loss(lab, operation, detail) == [
        "2 try_acquire_ingest_exclusion"
    ]
    assert lab.event_types(FREE_ID) == ["run-started", "page-completed"]
    assert lab.database.runs[FREE_ID].status is RunStatus.RUNNING
    assert_names_no_read_of_the_run(lab)
    assert lab.opener.opens == 2
    assert lab.opener.all_closed


# === window_system_exit_line (AC7, AC8 c, AC15; F-28, D-1, N38) =================
#
# Plan § State machine C, "The line rule of the window": a `SystemExit` in the window
# gets no progress line, so that no line names `try_acquire_ingest_exclusion` or
# `open_repository` and none holds `SystemExit`.


@pytest.mark.parametrize("place", ["exclusion", "open"])
def test_window_system_exit_line_a_system_exit_in_the_window_gets_no_progress_line(
    lab: Lab, place: str
) -> None:
    """F-28, D-1: the second exclusion (or the second `open_repository()`) raises it.

    `record_observation` 2 is lost. The `SystemExit(3)` object propagates; no message
    after the loss line names an operation of the window, and none holds `SystemExit`.
    """
    loss = Loss(lab, other_session=False)
    request, operation, detail = arrange_loss(lab, "observation", loss)
    exits = Raised(lambda: SystemExit(3))
    if place == "exclusion":
        lab.opener.faults[2] = [
            lab.faults.raises("try_acquire_ingest_exclusion", exits)
        ]
        expected_attempts = ["2 try_acquire_ingest_exclusion"]
    else:
        lab.opener.open_errors[2] = exits
        expected_attempts = []

    stop = call_exiting(lab, request)

    assert stop is exits.first
    assert stop.code == 3
    assert_names_nothing_after_the_loss(lab, operation)
    assert not any("SystemExit" in message for message in lab.reporter.messages), (
        lab.reporter.messages
    )
    assert_the_run_was_not_touched(lab, loss)
    assert attempts_after_the_loss(lab, operation, detail) == expected_attempts
    assert lab.database.runs[FREE_ID].status is RunStatus.RUNNING
    assert lab.opener.opens == 2
    assert lab.opener.all_closed


# === cleanup_system_exit (AC7, AC15; F-28, D-1, N39) ============================
#
# Plan § State machine K: K never turns a `SystemExit` into an outcome. A `SystemExit`
# raised by one of its operations propagates out of `run_ingest` as that object; nothing
# is read or written after it and no event follows the one that raised.


def arrange_cleanup_system_exit(
    lab: Lab, where: str, when: Moment
) -> tuple[Raised, str, list[str]]:
    """Page 1 completes, page 2 fails, and K's `where` raises `SystemExit(3)`.

    Return the maker, the operation that raised (the last attempt) and the events the
    run must hold afterwards.
    """
    lab.script_ids(FREE_ID)
    exits = Raised(lambda: SystemExit(3))
    faults = lab.opener.faults.setdefault(1, [])
    stored = ["run-started", "page-completed"]
    if where == "unexpected-error":
        lab.source.script(2, MemoryError())
        faults.append(
            lab.faults.raises(
                "append_audit_event", exits, detail="unexpected-error", when=when
            )
        )
        return (
            exits,
            "append_audit_event",
            stored + (["unexpected-error"] if when == "after" else []),
        )
    lab.source.script(2, KeyboardInterrupt())
    if where == "read-run":
        faults.append(lab.faults.raises("read_run", exits, nth=2, execution_id=FREE_ID))
        return exits, "read_run", stored
    if where == "run-interrupted":
        faults.append(
            lab.faults.raises(
                "append_audit_event", exits, detail="run-interrupted", when=when
            )
        )
        return (
            exits,
            "append_audit_event",
            stored + (["run-interrupted"] if when == "after" else []),
        )
    assert where == "finish-run"
    faults.append(lab.faults.raises("finish_run", exits, detail="failed", when=when))
    return exits, "finish_run", [*stored, "run-interrupted"]


CLEANUP_SYSTEM_EXIT_CASES = [
    pytest.param("read-run", "before", id="read-run-before"),
    pytest.param("run-interrupted", "before", id="ctrl-c-append-before"),
    pytest.param("run-interrupted", "after", id="ctrl-c-append-after"),
    pytest.param("finish-run", "before", id="finish-run-before"),
    pytest.param("unexpected-error", "before", id="unexpected-append-before"),
]


@pytest.mark.parametrize(("where", "when"), CLEANUP_SYSTEM_EXIT_CASES)
def test_cleanup_system_exit_k_never_turns_a_system_exit_into_an_outcome(
    lab: Lab, where: str, when: Moment
) -> None:
    """F-28, D-1: a Ctrl+C (or `MemoryError`) at page 2 enters K; K's operation raises.

    The `SystemExit(3)` object leaves `run_ingest` and no outcome is returned; the last
    attempt is the operation that raised and nothing follows it; no event follows the
    one that raised; `<A>` is stored `running` (with the `run-interrupted` event only
    when that append delegated first); every repository is closed.
    """
    exits, operation, events = arrange_cleanup_system_exit(lab, where, when)

    stop = call_exiting(lab, fresh(lab, 1, 3))

    assert stop is exits.first
    assert stop.code == 3
    assert len(exits.made) == 1
    assert lab.opener.attempts[-1].operation == operation
    assert lab.event_types(FREE_ID) == events
    assert lab.database.runs[FREE_ID].status is RunStatus.RUNNING
    assert lab.sequences(FREE_ID) == (1,)
    assert lab.reporter.started == [FREE_ID]
    assert lab.opener.opens == 1
    assert lab.opener.all_closed
