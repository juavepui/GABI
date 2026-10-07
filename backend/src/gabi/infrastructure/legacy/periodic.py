"""Small adapters for the unchanged refresh, ledger and reserved research engines."""

import time
from datetime import UTC, datetime
from pathlib import Path

from gabi.application.administration.periodic import PeriodicTasks
from gabi.application.research.blind import BlindValidationQueries
from gabi.infrastructure.storage.blind import SqliteBlindStore
from gabi.infrastructure.storage.periodic import PeriodicFiles


class LegacyPeriodicOperations:
    def __init__(self, data_dir: Path):
        from gabi import config

        if config.DATA_DIR.resolve() != data_dir.resolve():
            raise ValueError("El mantenimiento y los motores legacy no usan el mismo directorio de datos.")

    def latest_event_id(self):
        from gabi.sync_state import latest_event_id

        return latest_event_id()

    def universe_checkpoint(self):
        from gabi import sync_state

        return sync_state.get("universe", "SP500", "members")

    def universe_due(self, checkpoint):
        from gabi import sync_state

        return sync_state.due(checkpoint, 24)

    def universe_attempt(self):
        from gabi.sync_state import Attempt

        return Attempt("universe", "SP500", "members")

    def universe(self, refresh):
        from gabi import screener

        return screener.get_universe(force_refresh=refresh)

    def fingerprint(self, records):
        from gabi.sync_state import fingerprint

        return fingerprint(records)

    def refresh_symbols(self, symbols, full_refresh):
        from gabi import screener

        return screener.refresh_data(symbols, **({"full_refresh": True} if full_refresh else {}))

    def refresh_macro(self, full_refresh):
        from gabi import macro

        return macro.ensure_macro_data(full_refresh=full_refresh)

    def events_since(self, event_id):
        from gabi.sync_state import events_since

        return events_since(event_id)

    def totals(self, events):
        from gabi.sync_state import totals

        return totals(events)

    def record_rebalance(self, validation_id):
        from gabi.blind_validation import record_rebalance

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
        from gabi import historical_tiingo

        return historical_tiingo.fetch(symbols, window="smallmid")

    def import_tiingo(self):
        from gabi import historical_tiingo

        return historical_tiingo.import_cached("smallmid")

    def mark_tiingo_complete(self, fetched):
        from gabi.smallmid_test import mark_tiingo_complete

        mark_tiingo_complete(fetched)


def build_periodic_tasks(data_dir: Path) -> PeriodicTasks:
    from gabi import smallmid_test

    operations = LegacyPeriodicOperations(data_dir)
    store = PeriodicFiles(data_dir, data_dir / "history_refresh" / "tiingo" / "smallmid",
                          smallmid_test.tiingo_complete_path(), smallmid_test.result_path(),
                          smallmid_test.DATA_FREEZE_DEADLINE)
    def now():
        return datetime.now(UTC)

    blind = BlindValidationQueries(SqliteBlindStore(data_dir), lambda: now().date())
    return PeriodicTasks(store, operations, blind, now, time.perf_counter, time.process_time)
