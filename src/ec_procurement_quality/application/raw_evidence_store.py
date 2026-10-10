"""Application port for storing and reading immutable raw evidence."""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from ec_procurement_quality.domain.content_hash import ContentHash
from ec_procurement_quality.domain.raw_evidence import Observation


class RawEvidenceStore(Protocol):
    """Storage operations required by application use cases."""

    def store(
        self,
        *,
        execution_id: str,
        sequence: int,
        method: str,
        url: str,
        status: int,
        headers: Sequence[tuple[str, str]],
        captured_at: datetime,
        content: bytes,
    ) -> Observation: ...

    def read_content(self, content_hash: ContentHash) -> bytes: ...

    def read_observation(self, execution_id: str, sequence: int) -> Observation: ...
