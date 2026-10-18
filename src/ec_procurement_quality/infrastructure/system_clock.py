"""The real clock and the real execution id source for an ingest run."""

import secrets
from datetime import UTC, datetime


class SystemClock:
    """Reads the system time, with the local UTC offset."""

    def now(self) -> datetime:
        return datetime.now().astimezone()


class RandomExecutionIdSource:
    """Draws ingest execution ids: the UTC start time and 8 random hex digits."""

    def new_execution_id(self, started_at: datetime) -> str:
        stamp = started_at.astimezone(UTC).strftime("%Y%m%dt%H%M%Sz")
        return f"ingest-{stamp}-{secrets.token_hex(4)}"
