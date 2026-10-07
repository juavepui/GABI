"""Operation-scoped measured attempts with injected storage and clocks."""

import json
from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from gabi.domain.market.sync_events import event_checkpoint, validate_status


class SyncEvents(Protocol):
    def get(self, source: str, entity: str, dataset: str) -> dict: ...
    def save(self, event: dict, checkpoint: dict, *, skipped: bool) -> None: ...


class SyncAttempt:
    def __init__(self, source: str, entity: str, dataset: str, store: SyncEvents, *, now: Callable[[], datetime],
                 wall_time: Callable[[], float], cpu_time: Callable[[], float]):
        self.source, self.entity, self.dataset, self.store = source, entity, dataset, store
        self.now, self.wall_time, self.cpu_time = now, wall_time, cpu_time
        self.calls = self.payload_bytes = 0
        self.started, self.cpu_started = wall_time(), cpu_time()

    def payload(self, value) -> None:
        self.payload_bytes += len(json.dumps(value, default=str).encode())

    def finish(self, status: str, *, state: dict | None = None, new: int = 0, revised: int = 0,
               unchanged: int = 0, reason: str = "", skipped: bool = False) -> dict:
        validate_status(status)
        at = self.now().isoformat()
        previous = self.store.get(self.source, self.entity, self.dataset)
        event, checkpoint = event_checkpoint(self.source, self.entity, self.dataset, previous, at,
            status=status, calls=self.calls, payload_bytes=self.payload_bytes,
            seconds=self.wall_time() - self.started, cpu_seconds=self.cpu_time() - self.cpu_started,
            state=state, new=new, revised=revised, unchanged=unchanged, reason=reason, skipped=skipped)
        self.store.save(event, checkpoint, skipped=skipped)
        return event
