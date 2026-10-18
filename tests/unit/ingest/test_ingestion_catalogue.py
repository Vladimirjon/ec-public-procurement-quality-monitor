"""Feature ingest-command (F4), outcome O4 (AC12, AC13, decision P-4): the catalogue.

The closed lists of an ingest run, its scope, the ingest execution id rule and the
pure helper that computes the pages left to request. `-k` tokens: `catalogue`
(the closed lists and the helper), `scope` (the scope value) and `execution_id`
(the id rule, the reserved names and the random id source).

These tests need no double: they exercise `domain.ingestion_catalogue` and
`infrastructure.system_clock.RandomExecutionIdSource` directly. Data is synthetic.
"""

import enum
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta, timezone
from typing import cast

import pytest

from ec_procurement_quality.domain.ingestion_audit import JsonValue, same_json
from ec_procurement_quality.domain.ingestion_catalogue import (
    SCOPE_SOURCE,
    SCOPE_VERSION,
    WINDOWS_RESERVED_NAMES,
    AuditEventType,
    EvidenceStoreName,
    IngestScope,
    PageFailure,
    ReconciliationProblem,
    pages_left_to_request,
    validate_ingest_execution_id,
)
from ec_procurement_quality.domain.raw_evidence import validate_execution_id
from ec_procurement_quality.infrastructure.system_clock import RandomExecutionIdSource

BASE_URL = "https://source.invalid/PLATAFORMA"
BUYER = "SYNTHETIC BUYER S.A."
VALID_ID = "ingest-20261017t150000z-0a1b2c3d"

# --- The closed lists (AC13, plan § Public names) ---------------------------

CLOSED_LISTS: list[tuple[type[enum.StrEnum], dict[str, str]]] = [
    (
        AuditEventType,
        {
            "RUN_STARTED": "run-started",
            "PAGE_COMPLETED": "page-completed",
            "PAGE_FAILED": "page-failed",
            "STORAGE_FAILED": "storage-failed",
            "LAST_PAGE_REACHED": "last-page-reached",
            "RUN_INTERRUPTED": "run-interrupted",
            "UNEXPECTED_ERROR": "unexpected-error",
            "OBSERVATION_RECONCILED": "observation-reconciled",
            "RUN_CLOSED_BY_RECONCILIATION": "run-closed-by-reconciliation",
            "RECONCILIATION_FAILED": "reconciliation-failed",
        },
    ),
    (
        PageFailure,
        {"STATUS": "status", "INCOMPLETE": "incomplete", "TRANSPORT": "transport"},
    ),
    (
        EvidenceStoreName,
        {"RAW_EVIDENCE": "raw-evidence", "POSTGRESQL": "postgresql"},
    ),
    (
        ReconciliationProblem,
        {
            "LOCAL_OBSERVATION_MISSING": "local-observation-missing",
            "LOCAL_OBSERVATION_DIFFERENT": "local-observation-different",
            "LOCAL_OBSERVATION_UNREADABLE": "local-observation-unreadable",
            "OBJECT_MISSING": "object-missing",
            "OBJECT_INTEGRITY": "object-integrity",
            "SEQUENCE_GAP": "sequence-gap",
            "POSTGRESQL_OBSERVATION_CONFLICT": "postgresql-observation-conflict",
            "LOCAL_LISTING_FAILED": "local-listing-failed",
        },
    ),
]


@pytest.mark.parametrize(
    ("closed_list", "expected"),
    CLOSED_LISTS,
    ids=[closed_list.__name__ for closed_list, _ in CLOSED_LISTS],
)
def test_catalogue_closed_list_has_exactly_the_pinned_names_and_values(
    closed_list: type[enum.StrEnum], expected: dict[str, str]
) -> None:
    """AC13: no member is missing, extra or spelled differently."""
    assert {member.name: member.value for member in closed_list} == expected


@pytest.mark.parametrize(
    "closed_list", [closed_list for closed_list, _ in CLOSED_LISTS]
)
def test_catalogue_closed_list_members_are_stored_as_their_text_value(
    closed_list: type[enum.StrEnum],
) -> None:
    """Plan § Audit details: an enum value is stored as its `str` value."""
    for member in closed_list:
        assert isinstance(member, str)
        assert str(member) == member.value
        assert same_json({"value": member}, {"value": member.value})


# --- The scope (AC13, Q6) ---------------------------------------------------


def a_scope(
    *, first_page: int = 1, last_page: int = 2, year: int = 2025
) -> IngestScope:
    return IngestScope(
        base_url=BASE_URL,
        buyer=BUYER,
        year=year,
        first_page=first_page,
        last_page=last_page,
    )


def scope_json(**changes: JsonValue) -> dict[str, JsonValue]:
    """The exact JSON of `a_scope()`, with `changes` applied."""
    scope: dict[str, JsonValue] = {
        "scope_version": 1,
        "source": "sercop-search-ocds",
        "base_url": BASE_URL,
        "buyer": BUYER,
        "year": 2025,
        "first_page": 1,
        "last_page": 2,
    }
    scope.update(changes)
    return scope


def test_scope_constants_are_the_pinned_version_and_source() -> None:
    assert SCOPE_VERSION == 1
    assert SCOPE_SOURCE == "sercop-search-ocds"


def test_scope_to_json_is_exactly_the_seven_pinned_keys() -> None:
    """AC13: the literal object of the AC1 run, compared with `same_json`."""
    assert same_json(a_scope().to_json(), scope_json())


def test_scope_to_json_holds_only_integers_and_text() -> None:
    """AC13, PS-10: no float and no bool in a scope."""
    for key, value in a_scope().to_json().items():
        assert type(value) in (int, str), key


def test_scope_to_json_follows_the_fields_of_the_scope() -> None:
    scope = a_scope(first_page=4, last_page=9, year=2030)

    assert same_json(scope.to_json(), scope_json(first_page=4, last_page=9, year=2030))


def test_scope_round_trips_through_json() -> None:
    scope = a_scope(first_page=3, last_page=7)

    assert IngestScope.from_json(scope.to_json()) == scope


def test_scope_accepts_a_single_page_range() -> None:
    assert a_scope(first_page=5, last_page=5).first_page == 5


def case_ids(cases: Sequence[tuple[str, object]]) -> list[str]:
    """Ids that do not repeat a field name verbatim (so `-k` tokens stay apart)."""
    return [f"{key.replace('_', '-')}-{index}" for index, (key, _) in enumerate(cases)]


INVALID_FIELDS: list[tuple[str, object]] = [
    ("base_url", ""),
    ("base_url", 123456789),
    ("buyer", ""),
    ("buyer", b"synthetic-body-marker"),
    ("year", 0),
    ("year", -987654),
    ("year", True),
    ("year", "2025"),
    ("year", 2025.5),
    ("first_page", 0),
    ("first_page", True),
    ("first_page", 1.5),
    ("last_page", 0),
    ("last_page", -987654),
    ("last_page", True),
    ("last_page", "2"),
]


@pytest.mark.parametrize(
    ("field", "value"), INVALID_FIELDS, ids=case_ids(INVALID_FIELDS)
)
def test_scope_rejects_an_invalid_field_naming_it_and_never_its_value(
    field: str, value: object
) -> None:
    """Plan: `ValueError` naming the field; the value is never in the message."""
    fields: dict[str, object] = {
        "base_url": BASE_URL,
        "buyer": BUYER,
        "year": 2025,
        "first_page": 1,
        "last_page": 2,
    }
    fields[field] = value

    with pytest.raises(ValueError, match=field) as caught:
        IngestScope(
            base_url=cast(str, fields["base_url"]),
            buyer=cast(str, fields["buyer"]),
            year=cast(int, fields["year"]),
            first_page=cast(int, fields["first_page"]),
            last_page=cast(int, fields["last_page"]),
        )

    assert not str(value) or str(value) not in str(caught.value)


def test_scope_rejects_a_range_that_ends_before_it_starts() -> None:
    with pytest.raises(ValueError, match="first_page"):
        a_scope(first_page=3, last_page=2)


def test_scope_from_json_rejects_a_missing_key() -> None:
    for key in scope_json():
        scope = scope_json()
        del scope[key]
        with pytest.raises(ValueError):
            IngestScope.from_json(scope)


def test_scope_from_json_rejects_an_extra_key() -> None:
    with pytest.raises(ValueError):
        IngestScope.from_json(scope_json(note="x"))


INVALID_STORED_VALUES: list[tuple[str, JsonValue]] = [
    ("scope_version", 2),
    ("scope_version", 0),
    ("scope_version", True),
    ("scope_version", "1"),
    ("source", "another-source"),
    ("source", None),
    ("base_url", ""),
    ("base_url", 7),
    ("buyer", ""),
    ("buyer", None),
    ("year", 0),
    ("year", True),
    ("year", "2025"),
    ("first_page", 0),
    ("first_page", False),
    ("first_page", "1"),
    ("last_page", 0),
    ("last_page", True),
    ("last_page", None),
    ("first_page", 3),
]


@pytest.mark.parametrize(
    ("key", "value"),
    INVALID_STORED_VALUES,
    ids=case_ids(INVALID_STORED_VALUES),
)
def test_scope_from_json_rejects_a_value_a_scope_cannot_have(
    key: str, value: JsonValue
) -> None:
    """A resumption reads its original's scope: only a real scope is accepted."""
    with pytest.raises(ValueError):
        IngestScope.from_json(scope_json(**{key: value}))


def test_scope_from_json_rejects_a_float() -> None:
    """A float is not a JSON value of the catalogue (PS-10)."""
    scope = cast(Mapping[str, JsonValue], {**scope_json(), "year": 2025.0})

    with pytest.raises(ValueError):
        IngestScope.from_json(scope)


def test_scope_from_json_rejects_what_is_not_an_object() -> None:
    with pytest.raises(ValueError):
        IngestScope.from_json(cast(Mapping[str, JsonValue], ["scope_version", 1]))


def test_scope_from_json_accepts_any_key_order() -> None:
    reordered = dict(reversed(list(scope_json().items())))

    assert IngestScope.from_json(reordered) == a_scope()


# --- Execution ids (AC12, Q7) -----------------------------------------------


def test_execution_id_of_the_ingest_form_is_returned_unchanged() -> None:
    assert validate_ingest_execution_id(VALID_ID) == VALID_ID
    assert validate_execution_id(VALID_ID) == VALID_ID


@pytest.mark.parametrize(
    "bad_id",
    [
        "",
        "synthetic-exec-001",
        "Synthetic_Id",
        "ingest-20261017t150000z-0a1b2c3",
        "ingest-20261017t150000z-0a1b2c3d4",
        "ingest-20261017t150000z-0A1B2C3D",
        "ingest-20261017t150000z-0a1b2c3g",
        "ingest-20261017T150000Z-0a1b2c3d",
        "Ingest-20261017t150000z-0a1b2c3d",
        "ingest-2026101t150000z-0a1b2c3d",
        "ingest-20261017t150000z0a1b2c3d",
        "xingest-20261017t150000z-0a1b2c3d",
        " ingest-20261017t150000z-0a1b2c3d",
        "ingest-20261017t150000z-0a1b2c3d\n",
    ],
)
def test_execution_id_that_is_not_of_the_ingest_form_is_rejected(bad_id: str) -> None:
    with pytest.raises(ValueError):
        validate_ingest_execution_id(bad_id)


@pytest.mark.parametrize("not_text", [None, 5, b"ingest-20261017t150000z-0a1b2c3d"])
def test_execution_id_that_is_not_text_is_rejected(not_text: object) -> None:
    with pytest.raises(ValueError):
        validate_ingest_execution_id(cast(str, not_text))


def test_execution_id_reserved_names_are_exactly_the_windows_device_names() -> None:
    expected = {"con", "prn", "aux", "nul"}
    expected |= {f"com{digit}" for digit in range(10)}
    expected |= {f"lpt{digit}" for digit in range(10)}

    assert WINDOWS_RESERVED_NAMES == frozenset(expected)


@pytest.mark.parametrize("name", sorted(WINDOWS_RESERVED_NAMES))
def test_execution_id_every_reserved_name_is_rejected(name: str) -> None:
    with pytest.raises(ValueError):
        validate_ingest_execution_id(name)
    with pytest.raises(ValueError):
        validate_ingest_execution_id(name.upper())


def test_execution_id_source_gives_two_different_valid_ids() -> None:
    """AC12: new for every run, of the ingest form, off the reserved names."""
    source = RandomExecutionIdSource()
    started_at = datetime(2026, 10, 17, 10, 0, 0, tzinfo=timezone(timedelta(hours=-5)))

    first = source.new_execution_id(started_at)
    second = source.new_execution_id(started_at)

    assert first != second
    for new_id in (first, second):
        assert validate_ingest_execution_id(new_id) == new_id
        assert new_id not in WINDOWS_RESERVED_NAMES


def test_execution_id_source_writes_the_start_time_in_utc() -> None:
    source = RandomExecutionIdSource()
    local = datetime(2026, 10, 17, 10, 0, 0, tzinfo=timezone(timedelta(hours=-5)))
    utc = datetime(2026, 10, 17, 15, 0, 0, tzinfo=UTC)

    assert source.new_execution_id(local).startswith("ingest-20261017t150000z-")
    assert source.new_execution_id(utc).startswith("ingest-20261017t150000z-")


# --- Pages left to request (decision P-4) -----------------------------------


def test_catalogue_pages_left_is_the_whole_range_when_nothing_is_known() -> None:
    assert pages_left_to_request(a_scope(last_page=4), frozenset(), None) == (
        1,
        2,
        3,
        4,
    )


def test_catalogue_pages_left_leaves_out_the_completed_pages() -> None:
    assert pages_left_to_request(a_scope(last_page=4), frozenset({1, 2}), None) == (
        3,
        4,
    )


def test_catalogue_pages_left_are_in_increasing_order() -> None:
    assert pages_left_to_request(a_scope(last_page=5), frozenset({2, 4}), None) == (
        1,
        3,
        5,
    )


def test_catalogue_pages_left_stops_at_the_event_page() -> None:
    scope = a_scope(last_page=5)

    assert pages_left_to_request(scope, frozenset({1}), 3) == (2, 3)


def test_catalogue_pages_left_is_empty_once_the_pages_up_to_the_event_are_done() -> (
    None
):
    assert pages_left_to_request(a_scope(last_page=4), frozenset({1, 2}), 2) == ()


def test_catalogue_pages_left_is_empty_when_everything_is_completed() -> None:
    assert pages_left_to_request(a_scope(last_page=3), frozenset({1, 2, 3}), None) == ()


def test_catalogue_pages_left_ignores_an_event_page_above_the_scope() -> None:
    assert pages_left_to_request(a_scope(last_page=3), frozenset({1}), 9) == (2, 3)


def test_catalogue_pages_left_is_empty_when_the_event_precedes_the_first_page() -> None:
    assert (
        pages_left_to_request(a_scope(first_page=3, last_page=5), frozenset(), 2) == ()
    )


def test_catalogue_pages_left_ignores_completed_pages_outside_the_scope() -> None:
    scope = a_scope(first_page=2, last_page=3)

    assert pages_left_to_request(scope, frozenset({1, 9}), None) == (2, 3)


def test_catalogue_pages_left_of_a_beyond_result_scope_is_its_first_page() -> None:
    """Scope 4 to 5: the first page is left until it is completed."""
    scope = a_scope(first_page=4, last_page=5)

    assert pages_left_to_request(scope, frozenset(), 4) == (4,)
    assert pages_left_to_request(scope, frozenset({4}), 4) == ()
