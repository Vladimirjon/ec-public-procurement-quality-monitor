"""Ingestion catalogue: the closed lists of an ingest run, its scope and its ids.

The audit event types, the page failure kinds, the evidence store names and the
reconciliation problems are closed lists; an event detail holds only their `str`
values, identities and numbers. The *scope* of a run is the JSON object that says
what the run asks the source for. An ingest execution id is an F1 execution id
with one fixed form, and never a Windows reserved device name.
"""

import enum
import re
from collections.abc import Mapping
from dataclasses import dataclass

from ec_procurement_quality.domain.ingestion_audit import JsonValue
from ec_procurement_quality.domain.raw_evidence import validate_execution_id

_INGEST_EXECUTION_ID = re.compile(r"ingest-[0-9]{8}t[0-9]{6}z-[0-9a-f]{8}")
_MIN_NUMBER = 1
_SCOPE_KEYS = frozenset(
    {
        "scope_version",
        "source",
        "base_url",
        "buyer",
        "year",
        "first_page",
        "last_page",
    }
)

SCOPE_VERSION = 1
SCOPE_SOURCE = "sercop-search-ocds"
WINDOWS_RESERVED_NAMES: frozenset[str] = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{digit}" for digit in range(10)}
    | {f"lpt{digit}" for digit in range(10)}
)


class AuditEventType(enum.StrEnum):
    """The type of an audit event appended by an ingest run."""

    RUN_STARTED = "run-started"
    PAGE_COMPLETED = "page-completed"
    PAGE_FAILED = "page-failed"
    STORAGE_FAILED = "storage-failed"
    LAST_PAGE_REACHED = "last-page-reached"
    RUN_INTERRUPTED = "run-interrupted"
    UNEXPECTED_ERROR = "unexpected-error"
    OBSERVATION_RECONCILED = "observation-reconciled"
    RUN_CLOSED_BY_RECONCILIATION = "run-closed-by-reconciliation"
    RECONCILIATION_FAILED = "reconciliation-failed"


class PageFailure(enum.StrEnum):
    """How a page request failed."""

    STATUS = "status"
    INCOMPLETE = "incomplete"
    TRANSPORT = "transport"


class EvidenceStoreName(enum.StrEnum):
    """The store that failed to keep an observation."""

    RAW_EVIDENCE = "raw-evidence"
    POSTGRESQL = "postgresql"


class ReconciliationProblem(enum.StrEnum):
    """Why the reconciliation of a `running` run could not be completed."""

    LOCAL_OBSERVATION_MISSING = "local-observation-missing"
    LOCAL_OBSERVATION_DIFFERENT = "local-observation-different"
    LOCAL_OBSERVATION_UNREADABLE = "local-observation-unreadable"
    OBJECT_MISSING = "object-missing"
    OBJECT_INTEGRITY = "object-integrity"
    SEQUENCE_GAP = "sequence-gap"
    POSTGRESQL_OBSERVATION_CONFLICT = "postgresql-observation-conflict"
    LOCAL_LISTING_FAILED = "local-listing-failed"


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _number(value: object, name: str) -> int:
    # `bool` is a subclass of `int`; a flag is never a year or a page number.
    if isinstance(value, bool) or not isinstance(value, int) or value < _MIN_NUMBER:
        raise ValueError(f"{name} must be an integer of at least 1")
    return value


@dataclass(frozen=True, kw_only=True)
class IngestScope:
    """What an ingest run asks the source for: a buyer and a year, over a page range.

    The pages run from `first_page` to `last_page`, both included. A rejected
    field is named in the message and its value never is.
    """

    base_url: str
    buyer: str
    year: int
    first_page: int
    last_page: int

    def __post_init__(self) -> None:
        _text(self.base_url, "base_url")
        _text(self.buyer, "buyer")
        _number(self.year, "year")
        _number(self.first_page, "first_page")
        _number(self.last_page, "last_page")
        if self.first_page > self.last_page:
            raise ValueError("first_page must not be greater than last_page")

    def to_json(self) -> dict[str, JsonValue]:
        """Return the scope as the JSON object stored with the run."""
        return {
            "scope_version": SCOPE_VERSION,
            "source": SCOPE_SOURCE,
            "base_url": self.base_url,
            "buyer": self.buyer,
            "year": self.year,
            "first_page": self.first_page,
            "last_page": self.last_page,
        }

    @classmethod
    def from_json(cls, scope: Mapping[str, JsonValue]) -> "IngestScope":
        """Read a stored scope; raise `ValueError` if it is not exactly a scope."""
        if not isinstance(scope, Mapping) or set(scope) != _SCOPE_KEYS:
            raise ValueError("a scope must have exactly the scope keys")
        version = scope["scope_version"]
        if type(version) is not int or version != SCOPE_VERSION:
            raise ValueError("scope_version is not a supported version")
        source = scope["source"]
        if not isinstance(source, str) or source != SCOPE_SOURCE:
            raise ValueError("source is not the supported source")
        return cls(
            base_url=_text(scope["base_url"], "base_url"),
            buyer=_text(scope["buyer"], "buyer"),
            year=_number(scope["year"], "year"),
            first_page=_number(scope["first_page"], "first_page"),
            last_page=_number(scope["last_page"], "last_page"),
        )


def validate_ingest_execution_id(execution_id: str) -> str:
    """Return `execution_id` if it is an ingest id: `ingest-<UTC time>-<8 hex>`.

    The time is `YYYYMMDDtHHMMSSz`. The id is 33 characters, passes
    `validate_execution_id` and is not a Windows reserved device name.
    """
    if (
        not isinstance(execution_id, str)
        or _INGEST_EXECUTION_ID.fullmatch(execution_id) is None
    ):
        raise ValueError(
            "an ingest execution id must be 'ingest-', 16 characters of UTC time "
            "as YYYYMMDDtHHMMSSz, '-' and 8 lowercase hexadecimal digits"
        )
    validate_execution_id(execution_id)
    if execution_id in WINDOWS_RESERVED_NAMES:
        raise ValueError("an ingest execution id must not be a reserved device name")
    return execution_id


def pages_left_to_request(
    scope: IngestScope, completed: frozenset[int], last_reached: int | None
) -> tuple[int, ...]:
    """Return, in increasing order, the pages of the scope that are still to request.

    A page is left when it is inside `[scope.first_page, scope.last_page]`, is not
    in `completed` and is not above `last_reached`, the page of the chain's valid
    `last-page-reached` event (`None` when the chain has none).
    """
    return tuple(
        page
        for page in range(scope.first_page, scope.last_page + 1)
        if page not in completed and (last_reached is None or page <= last_reached)
    )
