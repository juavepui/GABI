"""FRED synchronization through the shared checkpoints and the process-wide source pacer."""

import time
from collections.abc import Callable
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

from gabi.application.administration.fred import synchronize
from gabi.application.administration.sync_events import SyncAttempt
from gabi.domain.market.fred import SERIES
from gabi.infrastructure.legacy.source_errors import fred_error, retry
from gabi.infrastructure.providers.fred import FredSource, fred_key
from gabi.infrastructure.storage.fred import SqliteFred
from gabi.infrastructure.storage.sync_events import OperationSyncEvents


def fred_operation(data_dir: Path, *, now: Callable[[], datetime] | None = None,
                   wall_time: Callable[[], float] = time.perf_counter,
                   cpu_time: Callable[[], float] = time.thread_time) -> Callable[..., dict]:
    clock = now or (lambda: datetime.now(UTC))
    path = data_dir / "gabi.db"
    events = OperationSyncEvents(path)

    def attempt(provider: str, sid: str, dataset: str) -> SyncAttempt:
        return SyncAttempt(provider, sid, dataset, events, now=clock, wall_time=wall_time, cpu_time=cpu_time)

    return partial(synchronize, SqliteFred(path, clock), SERIES, partial(fred_key, data_dir), FredSource().fetch,
                   events.get, attempt, retry, fred_error, clock)
