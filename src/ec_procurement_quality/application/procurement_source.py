"""Application port for asking the procurement source for search pages and records.

A call sends one request and either returns a checked result or raises a
`SourceError` (see `domain.source_response`) that carries whatever response was
received. Every result keeps the raw response it was read from, so the caller can
store the evidence unchanged.
"""

from dataclasses import dataclass
from typing import Protocol

from ec_procurement_quality.domain.source_response import RawResponse


@dataclass(frozen=True)
class SearchPage:
    """One page of a buyer-name search, read from a complete and usable response."""

    response: RawResponse
    total: int
    page: int
    pages: int
    record_count: int

    @property
    def is_beyond_last_page(self) -> bool:
        """True when the page asked for lies after the last one (or there are none).

        An empty `data` is not enough to say this: use this property instead.
        """
        return self.page > self.pages


@dataclass(frozen=True)
class RecordResponse:
    """One record, read from a complete and usable response."""

    response: RawResponse
    ocid: str
    release_count: int


class ProcurementSource(Protocol):
    """Source operations required by application use cases.

    Both methods raise `SourceError` subclasses for source failures and
    `ValueError` for invalid input (before any request is sent).
    """

    def search_page(self, *, year: int, buyer: str, page: int) -> SearchPage: ...

    def fetch_record(self, ocid: str) -> RecordResponse: ...
