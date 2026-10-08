"""Shared source composition for research CLI and persistent workers."""

import time
from collections.abc import Callable
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

from gabi.domain.research.tiingo_prices import PACE_SECONDS
from gabi.infrastructure.settings import Settings


def build_cik_resolver(settings: Settings, user_agent: str, *, now: Callable[[], datetime] | None = None,
                       wall_time: Callable[[], float] = time.perf_counter,
                       cpu_time: Callable[[], float] = time.thread_time):
    from gabi.application.administration.sync_events import SyncAttempt
    from gabi.application.market.sec_cik import CikResolver
    from gabi.infrastructure.legacy.source_errors import fingerprint, retry
    from gabi.infrastructure.providers.sec_cik import SecTickerMap
    from gabi.infrastructure.storage.sec_cik import FileCikMap, SqliteCikResolutions
    from gabi.infrastructure.storage.sync_events import OperationSyncEvents

    clock = now or (lambda: datetime.now(UTC))
    path = settings.data_dir / "gabi.db"
    events = OperationSyncEvents(path)

    def attempt() -> SyncAttempt:
        return SyncAttempt("sec", "all", "ticker-map", events, now=clock,
                           wall_time=wall_time, cpu_time=cpu_time)

    return CikResolver(FileCikMap(settings.data_dir / "sec_cik_map.csv"), SqliteCikResolutions(path, clock),
                       SecTickerMap(user_agent).fetch, attempt, retry,
                       partial(events.get, "sec", "all", "ticker-map"), fingerprint,
                       lambda: clock().timestamp())


def build_xbrl_operation(settings: Settings, user_agent: str, *, now: Callable[[], datetime] | None = None,
                         wall_time: Callable[[], float] = time.perf_counter,
                         cpu_time: Callable[[], float] = time.thread_time):
    from gabi.application.administration.sync_events import SyncAttempt
    from gabi.application.market.sec_selection import batch, refresh
    from gabi.application.market.sec_xbrl import download_complete, synchronize
    from gabi.domain.market.sec_facts import compute_edgar_metrics
    from gabi.infrastructure.jobs.sec_batch import run
    from gabi.infrastructure.legacy.source_errors import fingerprint, retry, sec_error
    from gabi.infrastructure.providers.sec_xbrl import SecXbrl
    from gabi.infrastructure.storage.sec_selection import SqliteSecSelection
    from gabi.infrastructure.storage.sec_xbrl import SqliteXbrl
    from gabi.infrastructure.storage.sync_events import OperationSyncEvents

    clock = now or (lambda: datetime.now(UTC))
    path = settings.data_dir / "gabi.db"
    store, events, source = SqliteXbrl(path, clock), OperationSyncEvents(path), SecXbrl(user_agent)

    def attempt(provider: str, entity: str, dataset: str) -> SyncAttempt:
        return SyncAttempt(provider, entity, dataset, events, now=clock, wall_time=wall_time, cpu_time=cpu_time)

    operation = partial(synchronize, store=store, submissions=source.submissions, companyfacts=source.companyfacts,
                        checkpoint=events.get, attempt_factory=attempt, retry=retry, fingerprint=fingerprint, now=clock)
    complete = partial(download_complete, store=store, companyfacts=source.companyfacts,
                       submissions=source.submissions, compute=compute_edgar_metrics)
    ciks = build_cik_resolver(settings, user_agent, now=clock, wall_time=wall_time, cpu_time=cpu_time)

    def download(symbols, resolved, *, full_refresh=False, incremental=True, progress_cb=None):
        selected = partial(operation, full_refresh=full_refresh) if incremental else complete
        return batch(symbols, resolved, operation=selected, runner=run, classify_error=sec_error, progress_cb=progress_cb)

    # Preserve the frozen compatibility setting without changing it per operation.
    from gabi.infrastructure.legacy.sec_defaults import cache_max_age_hours
    return partial(refresh, store=SqliteSecSelection(path, clock, max_symbols=settings.max_symbols),
                   mapping=ciks.mapping, resolutions=ciks.resolutions, download_batch=download,
                   classify_error=sec_error, now=clock, default_max_age_hours=cache_max_age_hours(),
                   max_symbols=settings.max_symbols)


def build_fred_operation(settings: Settings, *, now: Callable[[], datetime] | None = None,
                         wall_time: Callable[[], float] = time.perf_counter,
                         cpu_time: Callable[[], float] = time.thread_time) -> Callable[..., dict]:
    from gabi.application.administration.fred import synchronize
    from gabi.application.administration.sync_events import SyncAttempt
    from gabi.domain.market.fred import SERIES
    from gabi.infrastructure.legacy.source_errors import fred_error, retry
    from gabi.infrastructure.providers.fred import FredSource, fred_key
    from gabi.infrastructure.storage.fred import SqliteFred
    from gabi.infrastructure.storage.sync_events import OperationSyncEvents

    clock = now or (lambda: datetime.now(UTC))
    path = settings.data_dir / "gabi.db"
    events = OperationSyncEvents(path)
    repository = SqliteFred(path, clock)
    source = FredSource()

    def attempt(provider: str, sid: str, dataset: str) -> SyncAttempt:
        return SyncAttempt(provider, sid, dataset, events, now=clock,
                           wall_time=wall_time, cpu_time=cpu_time)

    return partial(synchronize, repository, SERIES, partial(fred_key, settings.data_dir), source.fetch,
                   events.get, attempt, retry, fred_error, clock)


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
