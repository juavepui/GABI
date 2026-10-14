"""Small adapters for the unchanged refresh, ledger and reserved research engines."""

import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from gabi.application.administration.periodic import PeriodicTasks
from gabi.application.administration.sync_events import SyncAttempt
from gabi.application.research.blind import BlindValidationQueries
from gabi.domain.market import sync_events as sync_rules
from gabi.infrastructure.storage.blind import SqliteBlindStore
from gabi.infrastructure.storage.periodic import PeriodicFiles
from gabi.infrastructure.storage.sync_events import OperationSyncEvents


class LegacyPeriodicOperations:
    def __init__(self, data_dir: Path, *, tiingo_fetch: Callable[[list[str]], dict] | None = None,
                 tiingo_import: Callable[[], dict] | None = None,
                 macro_sync: Callable[..., dict] | None = None,
                 sec_sync: Callable[..., dict] | None = None):
        from gabi import config

        if config.DATA_DIR.resolve() != data_dir.resolve():
            raise ValueError("El mantenimiento y los motores legacy no usan el mismo directorio de datos.")
        self.data_dir = data_dir
        self.events = OperationSyncEvents(data_dir / "gabi.db")
        self.tiingo_fetch, self.tiingo_import = tiingo_fetch, tiingo_import
        self.macro_sync = macro_sync
        self.sec_sync = sec_sync

    def latest_event_id(self):
        return self.events.latest_event_id()

    def universe_checkpoint(self):
        return self.events.get("universe", "SP500", "members")

    def universe_due(self, checkpoint):
        return sync_rules.due(checkpoint, 24, datetime.now(UTC))

    def universe_attempt(self):
        return SyncAttempt("universe", "SP500", "members", self.events, now=lambda: datetime.now(UTC),
                           wall_time=lambda: time.perf_counter(), cpu_time=lambda: time.thread_time())

    def universe(self, refresh):
        from gabi import screener

        return screener.get_universe(force_refresh=refresh)

    def fingerprint(self, records):
        return sync_rules.fingerprint(records)

    def refresh_symbols(self, symbols, full_refresh):
        from gabi.infrastructure.legacy.data_fetch import refresh_data

        options: dict = {"full_refresh": True} if full_refresh else {}
        if self.sec_sync is not None:
            options["sec_sync"] = self.sec_sync
        return refresh_data(symbols, **options)

    def refresh_macro(self, full_refresh):
        operation = self.macro_sync
        if operation is None:  # Compatibility callers; the CLI bootstrap supplies the explicit ports.
            from gabi.infrastructure.legacy.fred import fred_operation

            operation = fred_operation(self.data_dir)
        return operation(full_refresh=full_refresh)

    def events_since(self, event_id):
        return self.events.events_since(event_id)

    def totals(self, events):
        return sync_rules.totals(events)

    def record_rebalance(self, validation_id):
        from gabi.infrastructure.legacy.blind_validation import record_rebalance

        return record_rebalance(validation_id)

    def smallmid_final(self):
        from gabi.smallmid_test import final_run

        return final_run()

    def verify_ledger(self):
        from gabi.live_ledger import verify_integrity

        return verify_integrity()

    def capture_ledger(self, error, maintenance):
        from gabi.live_ledger import capture_current

        return capture_current(run_error=error, maintenance=maintenance)

    def fetch_tiingo(self, symbols):
        if self.tiingo_fetch is not None:
            return self.tiingo_fetch(symbols)
        from gabi import historical_tiingo

        return historical_tiingo.fetch(symbols, window="smallmid")

    def import_tiingo(self):
        if self.tiingo_import is not None:
            return self.tiingo_import()
        from gabi import historical_tiingo

        return historical_tiingo.import_cached("smallmid")

    def mark_tiingo_complete(self, fetched):
        from gabi.smallmid_test import mark_tiingo_complete

        mark_tiingo_complete(fetched)


def build_periodic_tasks(data_dir: Path, *, tiingo_fetch: Callable[[list[str]], dict] | None = None,
                         tiingo_import: Callable[[], dict] | None = None,
                         macro_sync: Callable[..., dict] | None = None,
                         sec_sync: Callable[..., dict] | None = None) -> PeriodicTasks:
    from gabi import smallmid_test

    operations = LegacyPeriodicOperations(data_dir, tiingo_fetch=tiingo_fetch, tiingo_import=tiingo_import,
                                          macro_sync=macro_sync, sec_sync=sec_sync)
    store = PeriodicFiles(data_dir, data_dir / "history_refresh" / "tiingo" / "smallmid",
                          smallmid_test.tiingo_complete_path(), smallmid_test.result_path(),
                          smallmid_test.DATA_FREEZE_DEADLINE)
    def now():
        return datetime.now(UTC)

    blind = BlindValidationQueries(SqliteBlindStore(data_dir), lambda: now().date())
    return PeriodicTasks(store, operations, blind, now, time.perf_counter, time.process_time)
