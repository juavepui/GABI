"""The names of the retired ``sync_state`` facade over the pieces production now uses (F7.29).

Tests and the measuring scripts read checkpoints of ``config.DB_PATH`` through these; the
production modules compose the same store, attempt factory and paced retry directly.
"""

import time  # noqa: F401 - tests patch time.sleep/perf_counter through this name
from datetime import UTC, datetime

from gabi import config
from gabi.domain.market import sync_events as rules
from gabi.domain.market.observations import change_status as change_status
from gabi.domain.market.observations import delta_rows as delta_rows
from gabi.domain.market.sync_events import fingerprint as fingerprint
from gabi.domain.market.sync_events import totals as totals
from gabi.infrastructure.providers.source_retry import retry as retry
from gabi.infrastructure.storage.sync_events import OperationSyncEvents, measured_attempt


def _events() -> OperationSyncEvents:
    return OperationSyncEvents(config.DB_PATH)


def get(source: str, entity: str, dataset: str) -> dict:
    return _events().get(source, entity, dataset)


def Attempt(source: str, entity: str, dataset: str):  # noqa: N802 - the retired facade's name
    return measured_attempt(_events(), source, entity, dataset)


def due(checkpoint: dict, hours: float, now: datetime | None = None) -> bool:
    return rules.due(checkpoint, hours, now or datetime.now(UTC))


def events_since(event_id: int = 0) -> list[dict]:
    return _events().events_since(event_id)


def latest_event_id() -> int:
    return _events().latest_event_id()


def failed_datasets(source: str) -> set[tuple[str, str]]:
    return _events().failed_datasets(source)
