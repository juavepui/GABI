"""Compatibility facade over shared checkpoints, measured attempts, source retry and pacing."""

import threading
import time
from datetime import UTC, datetime

import requests

from gabi.application.administration.sync_events import SyncAttempt
from gabi.application.administration.sync_events import retry as retry_use_case
from gabi.domain.market import sync_events as rules
from gabi.domain.market.observations import change_status as change_status
from gabi.domain.market.observations import delta_rows as delta_rows
from gabi.domain.market.source_errors import RETRYABLE_CATEGORIES, classify
from gabi.domain.market.sync_events import fingerprint as fingerprint
from gabi.domain.market.sync_events import totals as totals
from gabi.infrastructure.storage.sync_events import SCHEMA as SCHEMA
from gabi.infrastructure.storage.sync_events import OperationSyncEvents

from . import config


def _events() -> OperationSyncEvents:
    # The compatibility path is captured per operation, never mutated.
    return OperationSyncEvents(config.DB_PATH)


_PACE_LOCK = threading.Lock()
_NEXT_REQUEST: dict[str, float] = {}


def _pace(source: str, seconds: float) -> None:
    # The one process-wide pacer: legacy facades and the bootstrap bridge both retry through here,
    # so SEC's four threads cannot each burst independently.
    with _PACE_LOCK:
        now = time.perf_counter()
        delay = max(0., _NEXT_REQUEST.get(source, now) - now)
        _NEXT_REQUEST[source] = now + delay + seconds
    if delay:
        time.sleep(delay)


def _transient(exc: Exception) -> bool:
    category, _ = classify(str(exc))
    response = getattr(exc, "response", None)
    return (category in RETRYABLE_CATEGORIES or isinstance(exc, (requests.Timeout, requests.ConnectionError))
            or (response is not None and response.status_code >= 500))


def _retry_after(exc: Exception) -> tuple[bool, object]:
    response = getattr(exc, "response", None)
    return (False, None) if response is None else (True, response.headers.get("Retry-After"))


def get(source: str, entity: str, dataset: str) -> dict:
    return _events().get(source, entity, dataset)


def due(checkpoint: dict, hours: float, now: datetime | None = None) -> bool:
    return rules.due(checkpoint, hours, now or datetime.now(UTC))


def Attempt(source: str, entity: str, dataset: str) -> SyncAttempt:  # noqa: N802 - historical public name
    return SyncAttempt(source, entity, dataset, _events(), now=lambda: datetime.now(UTC),
                       wall_time=lambda: time.perf_counter(), cpu_time=lambda: time.thread_time())


def retry(call, attempt, *, attempts: int = 3, pace: float = .25):
    """Bounded retry; only transient network/rate failures. Never checkpoint here."""
    return retry_use_case(call, attempt, transient=_transient, retry_after=_retry_after,
                          pace=lambda source, seconds: _pace(source, seconds),
                          sleep=lambda seconds: time.sleep(seconds), attempts=attempts, pace_seconds=pace)


def events_since(event_id: int = 0) -> list[dict]:
    return _events().events_since(event_id)


def latest_event_id() -> int:
    return _events().latest_event_id()


def failed_datasets(source: str) -> set[tuple[str, str]]:
    return _events().failed_datasets(source)
