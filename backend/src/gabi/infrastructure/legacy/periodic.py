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

# Code that scores the active model besides the sealed files the ledger already hashes (#290).
ACTIVE_MODEL_CODE = ("infrastructure/model_versions.py", "domain/market/model_version.py",
                     "domain/market/sec_metrics_v2.py", "application/market/stored_metrics_v2.py",
                     "application/market/ranking.py", "infrastructure/storage/market.py",
                     "infrastructure/legacy/market.py", "domain/market/input_checks.py",
                     "domain/market/revenue_growth.py", "application/market/stored_revenue_growth.py",
                     "domain/market/engine_fundamentals.py", "infrastructure/legacy/engine_fundamentals.py",
                     "infrastructure/storage/engine_fundamentals.py", "screener_asof.py")


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

    def refresh_symbols(self, symbols, full_refresh, sec_symbols):
        from gabi.infrastructure.legacy.data_fetch import refresh_data

        options: dict = {"sec_symbols": sec_symbols}
        if full_refresh:
            options["full_refresh"] = True
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

    def record_scores(self):
        """Score and position of every company with the active model, dated by its prices (#328)."""
        from gabi.application.market.queries import describe_data
        from gabi.domain.market import score_history
        from gabi.infrastructure.legacy.market import calculators, model_policy
        from gabi.infrastructure.model_versions import active_model
        from gabi.infrastructure.settings import Settings
        from gabi.infrastructure.storage.market import ReadOnlyMarket
        from gabi.infrastructure.storage.score_history import SqliteScoreHistory

        model = active_model()
        market = ReadOnlyMarket(Settings(self.data_dir.resolve()),
                                calculators(model.technical, input_checks=model.input_checks), model_policy(model),
                                model.benchmark_symbol, model.risk_free_rate, metrics_version=model.metrics_version)
        try:
            today = datetime.now(UTC).date()
            snapshot = market.ranking(dict(model.weights), today)
            day = describe_data(snapshot, today).latest_price_date
            if day is None:
                return {"guardadas": 0, "motivo": "sin precios"}
            rows = score_history.rows(snapshot.table)
            saved = SqliteScoreHistory(self.data_dir).record(day.isoformat(), model.model_id,
                                                               model.metrics_version, rows, len(snapshot.table))
            return {"dia": day.isoformat(), "modelo": model.model_id, "guardadas": saved}
        finally:
            market.close()

    def record_engine_fundamentals(self):
        """The tested engine's company metrics of today for GABI-MF-v5 (#347); explicit write."""
        from datetime import date

        from gabi.infrastructure.legacy.engine_fundamentals import record
        from gabi.infrastructure.settings import Settings

        return record(Settings(self.data_dir.resolve()), date.today())

    def install_ranking_revision(self):
        """Triggers that count changes of the ranking's inputs (#342); idempotent explicit write."""
        from gabi.infrastructure.storage import ranking_revision

        return ranking_revision.install(self.data_dir / "gabi.db")

    def save_ranking(self):
        """The active model's ranking for today, saved so the next server start reuses it (#342).

        Same weights, date (local, like the API) and calculators as the ranking the server would build."""
        from datetime import date

        from gabi.infrastructure.legacy.market import calculators, model_policy
        from gabi.infrastructure.model_versions import active_model
        from gabi.infrastructure.settings import Settings
        from gabi.infrastructure.storage.market import ReadOnlyMarket

        model = active_model()
        policy = model_policy(model)
        market = ReadOnlyMarket(Settings(self.data_dir.resolve()),
                                calculators(model.technical, input_checks=model.input_checks), policy,
                                model.benchmark_symbol, model.risk_free_rate, metrics_version=model.metrics_version)
        try:
            return market.save_snapshot(dict(policy.weights), date.today())
        finally:
            market.close()

    def capture_active_ledger(self, error, maintenance):
        """The decision of the active model when it is not the sealed v1 (#290); None otherwise."""
        from datetime import date

        from gabi.domain.market.model_policy import FROZEN_MODEL_ID
        from gabi.infrastructure.legacy.market import calculators, model_policy
        from gabi.infrastructure.model_versions import active_model
        from gabi.infrastructure.settings import Settings
        from gabi.infrastructure.storage.market import ReadOnlyMarket
        from gabi.live_ledger import ModelCapture, capture_current

        model = active_model()
        if model.model_id == FROZEN_MODEL_ID:
            return None
        market = ReadOnlyMarket(Settings(self.data_dir.resolve()), calculators(model.technical, input_checks=model.input_checks), model_policy(model),
                                model.benchmark_symbol, model.risk_free_rate, metrics_version=model.metrics_version)

        def ranking():
            universe = market.universe(market.small_file("sp500_constituents.csv"))
            return universe, market.ranking(dict(model.weights), date.today()).table

        capture = ModelCapture(model.model_id, model.weights, model.metrics_version, ACTIVE_MODEL_CODE, ranking)
        try:
            return capture_current(run_error=error, maintenance=maintenance, model=capture)
        finally:
            market.close()

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
