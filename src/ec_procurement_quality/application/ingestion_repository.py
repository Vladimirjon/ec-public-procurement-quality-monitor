"""Application port for recording ingestion runs, observations and audit events."""

from collections.abc import Mapping
from datetime import datetime
from typing import Protocol

from ec_procurement_quality.domain.ingestion_audit import (
    AuditEvent,
    IngestionRun,
    JsonValue,
    RunStatus,
)
from ec_procurement_quality.domain.raw_evidence import Observation


class IngestionRepository(Protocol):
    """Persistence operations required by application use cases."""

    def start_run(
        self, *, execution_id: str, scope: Mapping[str, JsonValue], started_at: datetime
    ) -> IngestionRun: ...

    def finish_run(
        self, *, execution_id: str, status: RunStatus, finished_at: datetime
    ) -> IngestionRun: ...

    def read_run(self, execution_id: str) -> IngestionRun: ...

    def list_runs(self, status: RunStatus) -> tuple[IngestionRun, ...]: ...

    def try_acquire_ingest_exclusion(self) -> bool: ...

    def record_observation(self, observation: Observation) -> Observation: ...

    def read_observation(self, execution_id: str, sequence: int) -> Observation: ...

    def list_observations(self, execution_id: str) -> tuple[Observation, ...]: ...

    def append_audit_event(
        self,
        *,
        execution_id: str,
        occurred_at: datetime,
        event_type: str,
        detail: Mapping[str, JsonValue],
    ) -> AuditEvent: ...

    def list_audit_events(self, execution_id: str) -> tuple[AuditEvent, ...]: ...
