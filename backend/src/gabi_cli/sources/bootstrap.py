"""Shared source composition for research CLI and persistent workers."""

import time
from collections.abc import Callable
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

from gabi.domain.research.tiingo_prices import PACE_SECONDS
from gabi.infrastructure.settings import Settings


def build_tiingo_operations(settings: Settings, *, window_name: str = "smallmid",
                            cache_directory: Path | None = None, database: Path | None = None,
                            now: Callable[[], datetime] | None = None,
                            wait: Callable[[float], None] = time.sleep,
                            wall_time: Callable[[], float] = time.perf_counter,
                            cpu_time: Callable[[], float] = time.thread_time,
                            progress: Callable[[str], None] | None = None,
                            pace: float = PACE_SECONDS) -> tuple[Callable[[list[str]], dict], Callable[[], dict]]:
    import sqlite3
    from contextlib import closing

    from gabi.application.administration.sync_events import SyncAttempt
    from gabi.application.research.tiingo_prices import fetch, import_cached
    from gabi.domain.research.tiingo_prices import window
    from gabi.infrastructure.providers.tiingo_prices import TiingoPrices
    from gabi.infrastructure.storage.historical_prices import SqliteHistoricalPrices
    from gabi.infrastructure.storage.sync_events import OperationSyncEvents
    from gabi.infrastructure.storage.tiingo_prices import FileTiingoCache, tiingo_key

    clock = now or (lambda: datetime.now(UTC))
    spec = window(window_name)
    cache = FileTiingoCache(cache_directory or settings.data_dir / "history_refresh/tiingo" / spec.subdirectory)
    path = database or settings.data_dir / "gabi.db"
    events = OperationSyncEvents(path)
    source = TiingoPrices(partial(tiingo_key, settings.data_dir))

    def attempt(symbol: str, dataset: str) -> SyncAttempt:
        return SyncAttempt("tiingo", symbol, dataset, events, now=clock, wall_time=wall_time, cpu_time=cpu_time)

    download = partial(fetch, spec=spec, cache=cache, source=source, attempt_factory=attempt,
                       wait=wait, progress=progress or (lambda message: print(message, flush=True)),
                       pace=pace, max_symbols=settings.max_symbols)

    def import_prices() -> dict:
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path, timeout=30)) as connection:
            return import_cached(spec, cache, SqliteHistoricalPrices(connection), events, attempt_factory=attempt)

    return download, import_prices

