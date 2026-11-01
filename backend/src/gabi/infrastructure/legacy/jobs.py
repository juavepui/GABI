"""Allowlisted legacy operations called only by the worker process."""

import sqlite3
from collections.abc import Callable
from contextlib import closing
from datetime import date
from pathlib import Path

import pandas as pd

from gabi.application.administration.jobs import JobCommand, SourceFailures, refresh_failures
from gabi.application.research.academic_factors import FactorSnapshot
from gabi.infrastructure.settings import Settings


class LegacyExecutor:
    def __init__(self, settings: Settings, blind_plans_root: Path | None = None,
                 *, today: Callable[[], date] = date.today,
                 insider_sync: Callable[..., dict] | None = None,
                 factor_loader: Callable[[], FactorSnapshot] | None = None,
                 tiingo_fetch: Callable[[list[str]], dict] | None = None,
                 tiingo_import: Callable[[], dict] | None = None,
                 macro_sync: Callable[..., dict] | None = None,
                 sec_sync: Callable[..., dict] | None = None):
        self.settings = settings
        self.today = today
        self.insider_sync = insider_sync
        self.factor_loader = factor_loader
        self.tiingo_fetch, self.tiingo_import = tiingo_fetch, tiingo_import
        self.macro_sync = macro_sync
        self.sec_sync = sec_sync
        self.blind_plans_root = blind_plans_root or settings.data_dir.parent

    reports_progress = True  # The worker passes progress(fraction, phase) to long downloads.

    def __call__(self, command: JobCommand, progress: Callable[[float, str], None] | None = None) -> dict:
        if command.kind == "quality":
            return quality_snapshot(self.settings.data_dir)
        if command.kind == "sim_result":
            from datetime import date

            from gabi.application.portfolio.simulations import Simulations
            from gabi.infrastructure.storage.simulations import SqliteSimulations

            assert command.portfolio_id is not None
            return Simulations(SqliteSimulations(self.settings.data_dir), date.today).result(
                command.portfolio_id, long=True)
        if command.kind == "sim_prices":
            from gabi.application.portfolio.sim_prices import refresh_prices
            from gabi.domain.portfolio.simulation import fx_symbol
            from gabi.infrastructure.legacy.sim_prices import fetch_max_history
            from gabi.infrastructure.storage.simulations import SqliteSimulations

            assert command.portfolio_id is not None
            return refresh_prices(SqliteSimulations(self.settings.data_dir), command.portfolio_id,
                                  command.symbols[0] if command.symbols else None, fx_symbol, fetch_max_history)
        if command.kind == "holdings_prices":
            from gabi.application.portfolio.holdings import refresh_prices as refresh_holdings
            from gabi.infrastructure.legacy.sim_prices import fetch_max_history
            from gabi.infrastructure.storage.holdings import SqliteHoldings

            return refresh_holdings(SqliteHoldings(self.settings.data_dir), fetch_max_history)
        if command.kind == "metrics_comparison":
            from gabi.application.market.cached_data import fundamentals_info
            from gabi.application.market.metrics_comparison import compare_metrics
            from gabi.domain.market.model_version import SEC_METRICS_V1
            from gabi.domain.market.sec_facts import compute_edgar_metrics
            from gabi.domain.market.sec_reads import companyfacts
            from gabi.infrastructure.legacy.market import calculators, model_policy
            from gabi.infrastructure.model_versions import active_model
            from gabi.infrastructure.storage.cache_reads import SqliteCacheReads
            from gabi.infrastructure.storage.market import ReadOnlyMarket
            from gabi.infrastructure.storage.sec_reads import SqliteSecReads

            model = active_model()
            policy = model_policy(model)
            calculator = calculators(model.technical)
            # The comparison's baseline is the V1 ranking, whatever metrics the active version uses.
            market = ReadOnlyMarket(self.settings, calculator, policy, model.benchmark_symbol, model.risk_free_rate,
                                    metrics_version=SEC_METRICS_V1)
            database = self.settings.data_dir / "gabi.db"
            reader, cache, today = SqliteSecReads(database), SqliteCacheReads(database), self.today()
            try:
                return compare_metrics(
                    universe=lambda: [(row.symbol, row.sector) for row in market.universe(
                        market.small_file("sp500_constituents.csv")).itertuples(index=False)],
                    facts=lambda symbol, day: companyfacts(reader.issuer_facts(symbol, as_of=day), day),
                    v1_metrics=compute_edgar_metrics,
                    infos=lambda symbols: fundamentals_info(cache, symbols),
                    ranking=lambda: market.ranking(dict(policy.weights), today).table,
                    rescore=lambda table: calculator.scores(table, weights=dict(policy.weights)),
                    as_of=date.fromisoformat(command.start) if command.start else today, today=today,
                    progress=lambda done, total: progress(done / total, "Comparando métricas") if progress else None)
            finally:
                market.close()
        if command.kind == "benchmark_prices":
            from gabi.application.portfolio.benchmark import refresh_prices as refresh_benchmark
            from gabi.infrastructure.legacy.sim_prices import fetch_max_history

            return refresh_benchmark(fetch_max_history)
        if command.kind == "sim_compare":
            from datetime import date

            from gabi.application.portfolio.simulations import Simulations
            from gabi.infrastructure.storage.simulations import SqliteSimulations

            return Simulations(SqliteSimulations(self.settings.data_dir), date.today).compare()
        if command.kind == "decision_plan":
            from datetime import date

            from gabi.application.administration.jobs import Jobs
            from gabi.application.portfolio.decisions import Decisions
            from gabi.infrastructure.legacy.market import calculators, model_policy
            from gabi.infrastructure.model_versions import active_model
            from gabi.infrastructure.serialization.decisions import build_decisions
            from gabi.infrastructure.storage.decisions import SqliteDecisions
            from gabi.infrastructure.storage.jobs import SqliteJobs
            from gabi.infrastructure.storage.market import ReadOnlyMarket

            assert command.decision_policy is not None and command.holdings_text is not None
            model = active_model()
            policy = model_policy(model)
            market = ReadOnlyMarket(self.settings, calculators(model.technical), policy, model.benchmark_symbol,
                                    model.risk_free_rate, metrics_version=model.metrics_version)
            try:
                service = Decisions(market, SqliteDecisions(self.settings.data_dir), policy, date.today,
                                    build_decisions, Jobs(SqliteJobs(self.settings.data_dir)))
                return service.generate(command.decision_policy, command.holdings_text)
            finally:
                market.close()
        if command.kind == "filing_check":
            from datetime import date

            from gabi.application.administration.jobs import Jobs
            from gabi.application.market.signals import SignalMonitor
            from gabi.domain.market.signals import compare_snapshots
            from gabi.infrastructure.legacy.filings import compare_cached
            from gabi.infrastructure.legacy.market import calculators, model_policy
            from gabi.infrastructure.model_versions import active_model
            from gabi.infrastructure.storage.jobs import SqliteJobs
            from gabi.infrastructure.storage.market import ReadOnlyMarket
            from gabi.infrastructure.storage.signals import SqliteSignals

            assert command.snapshot_id is not None
            model = active_model()
            policy = model_policy(model)
            market = ReadOnlyMarket(self.settings, calculators(model.technical), policy, model.benchmark_symbol,
                                    model.risk_free_rate, metrics_version=model.metrics_version)
            try:
                monitor = SignalMonitor(SqliteSignals(self.settings.data_dir), market, policy,
                                        date.today, compare_snapshots, compare_cached,
                                        Jobs(SqliteJobs(self.settings.data_dir)))
                return monitor.filings(command.snapshot_id)
            finally:
                market.close()
        if command.kind in {"experiment_pbo", "experiment_bootstrap"}:
            from gabi.application.research.experiment_analysis import build_bootstrap, build_pbo
            from gabi.infrastructure.legacy.experiments import LegacyExperimentMath
            from gabi.infrastructure.storage.experiments import SqliteExperiments

            assert command.experiment_analysis is not None
            build = build_pbo if command.kind == "experiment_pbo" else build_bootstrap
            return build(SqliteExperiments(self.settings.data_dir), command.experiment_analysis,
                         LegacyExperimentMath())
        # Published legacy engines keep their immutable project-root config.
        from gabi import config

        if config.DATA_DIR.resolve() != self.settings.data_dir.resolve():
            raise RuntimeError("El worker y la API no usan el mismo directorio de datos.")
        if command.kind in {"blind_rebalance", "blind_performance", "blind_export"}:
            from gabi.infrastructure.legacy.blind import run_blind_job

            assert command.blind is not None
            return run_blind_job(command.kind, self.settings.data_dir, self.blind_plans_root, command.blind)
        if command.kind == "live_forward_report":
            from gabi.infrastructure.legacy.live_ledger import run_live_report

            assert command.live_report is not None
            return run_live_report(command.live_report["model_version"])
        if command.kind == "historical_ranking":
            from gabi.application.research.historical import build_historical_ranking
            from gabi.infrastructure.legacy.historical import run_historical

            assert command.start is not None
            return build_historical_ranking(command.start, run_historical)
        if command.kind == "factor_analysis":
            from gabi.application.research.factors import build_factor_analysis
            from gabi.infrastructure.legacy.factors import run_factors

            assert command.start is not None and command.end is not None
            assert command.factor_months is not None and command.factor_mode is not None
            return build_factor_analysis(command.start, command.end, command.factor_months,
                                         command.factor_mode, command.factor_max_symbols,
                                         lambda start, end, **options: run_factors(
                                             start, end, data_dir=self.settings.data_dir, today=self.today(), **options))
        if command.kind == "estimate_analysis":
            from gabi.application.research.estimate_analysis import build_estimate_analysis
            from gabi.infrastructure.legacy.estimates import run_estimate_analysis

            return build_estimate_analysis(lambda cutoff: run_estimate_analysis(self.settings.data_dir, cutoff))
        if command.kind in {"backtest_v1", "backtest_v2"}:
            from gabi.application.research.backtests import build_backtest
            from gabi.infrastructure.legacy.backtests import run_backtest_v1, run_backtest_v2

            assert command.start is not None and command.end is not None
            assert command.backtest_options is not None
            return build_backtest(command.kind, command.start, command.end, command.backtest_options,
                                  run_backtest_v1 if command.kind == "backtest_v1" else run_backtest_v2)
        if command.kind == "backtest_v3_comparison":
            from gabi.application.research.backtest_v3_comparison import build as build_comparison
            from gabi.infrastructure.legacy.backtests import run_backtest_v3_comparison

            assert command.start is not None and command.end is not None
            assert command.backtest_options is not None
            return build_comparison(command.start, command.end, command.backtest_options, run_backtest_v3_comparison)
        if command.kind == "portfolio_lab":
            from gabi.application.research.portfolio_lab import build_portfolio_lab
            from gabi.infrastructure.legacy.portfolio_lab import run_portfolio_lab

            assert command.start is not None and command.end is not None
            assert command.portfolio_options is not None
            return build_portfolio_lab(command.start, command.end, command.portfolio_options, run_portfolio_lab)
        if command.kind == "historical_outcomes":
            from gabi.infrastructure.legacy.historical import run_outcomes

            assert command.outcomes is not None
            return run_outcomes(self.settings.data_dir, command.outcomes)
        if command.kind == "prepare_history":
            from gabi.infrastructure.legacy.preparation import prepare_history

            assert command.start is not None and command.preparation is not None
            return prepare_history(command.start, command.end, command.preparation)
        if command.kind == "backtest_factors":
            from gabi.infrastructure.legacy.backtests import contrast_backtest

            assert command.factor_contrast is not None
            return contrast_backtest(self.settings.data_dir, command.factor_contrast, factor_loader=self.factor_loader)
        if command.kind == "backtest_register":
            from gabi.infrastructure.legacy.backtests import register_backtest

            assert command.research_log is not None
            return register_backtest(self.settings.data_dir, command.research_log)
        if command.kind == "company_sync":
            from gabi.infrastructure.legacy.company import sync_company

            assert command.company is not None
            return sync_company(self.settings.data_dir, command.company["symbol"], command.company["dataset"],
                                today=self.today(), insider_sync=self.insider_sync)
        if command.kind == "data_health":
            from datetime import date

            from gabi.application.administration.data_health import build_data_health
            from gabi.infrastructure.legacy.data_health import LegacyDataHealth

            assert command.health is not None
            return build_data_health(command.health, LegacyDataHealth(self.settings.data_dir), date.today())
        if command.kind == "data_update":
            from gabi.infrastructure.legacy.data_update import run_data_update

            assert command.update is not None
            return run_data_update(command.update, progress, sec_sync=self.sec_sync)
        if command.kind == "symbols":
            from gabi.infrastructure.legacy.data_fetch import refresh_data

            options: dict = {"sec_sync": self.sec_sync} if self.sec_sync else {}
            result = refresh_data(list(command.symbols), **options)
            if result.get("failed"):
                raise SourceFailures(refresh_failures(result))
            return {"symbols": list(command.symbols), "updated": len(command.symbols)}
        if command.kind == "refresh":
            from gabi.infrastructure.legacy.periodic import build_periodic_tasks

            result = build_periodic_tasks(self.settings.data_dir, tiingo_fetch=self.tiingo_fetch,
                                          tiingo_import=self.tiingo_import, macro_sync=self.macro_sync,
                                          sec_sync=self.sec_sync).refresh_data()
            if result["fallos"] or result["failed_events"]:
                raise SourceFailures(refresh_failures(result))
            return {"symbols": result["simbolos"], "sync": result["sync"]}
        if command.kind == "backtest":
            from gabi import multifactor_backtest

            result = multifactor_backtest.run(command.start or "", command.end or "")
            return {"kind": "exploratory", "start": command.start, "end": command.end,
                    "periods": result["periods"].to_dict(orient="records"),
                    "skipped": result["skipped"], "metrics": result["metrics"],
                    "return": result["return"], "spy_return": result["spy_return"]}
        if command.kind == "maintenance":
            from gabi.infrastructure.legacy.periodic import build_periodic_tasks

            result = build_periodic_tasks(self.settings.data_dir, tiingo_fetch=self.tiingo_fetch,
                                          tiingo_import=self.tiingo_import, macro_sync=self.macro_sync).run(refresh=False)
            if result.get("error") or result.get("ledger", {}).get("status") == "ERROR":
                raise RuntimeError("El mantenimiento terminó con errores.")
            # Never surface pending #43/#44 results through jobs.
            return {"maintenance": "completed"}
        if command.kind == "tiingo":
            from gabi.infrastructure.legacy.periodic import build_periodic_tasks

            result = build_periodic_tasks(self.settings.data_dir, tiingo_fetch=self.tiingo_fetch,
                                          tiingo_import=self.tiingo_import, macro_sync=self.macro_sync).resume_tiingo()
            if result.get("omitido"):
                raise RuntimeError("La cola Tiingo ya está en curso.")
            return {"download": "completed"}
        raise ValueError("Unsupported job")


def quality_snapshot(data_dir: Path) -> dict:
    """Small, read-only coverage audit; no schema initialization or network."""
    universe = data_dir / "sp500_constituents.csv"
    db_path = data_dir / "gabi.db"
    if not universe.is_file() or not db_path.is_file():
        raise RuntimeError("Faltan datos cacheados para la auditoría.")
    if universe.stat().st_size > 1_000_000:
        raise RuntimeError("El universo supera el límite de lectura.")
    symbols = pd.read_csv(universe, usecols=["symbol"], nrows=1001)["symbol"].dropna().astype(str).tolist()
    if len(symbols) > 1000:
        raise RuntimeError("El universo supera el límite de auditoría.")
    with closing(sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
        db.execute("PRAGMA query_only=ON")
        tables = {name for (name,) in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
        result: dict = {"universe": len(symbols), "sources": {}}
        for table in ("prices", "fundamentals", "edgar_metrics"):
            if table not in tables:
                result["sources"][table] = {"covered": 0, "total": len(symbols)}
                continue
            covered = 0
            for start in range(0, len(symbols), 200):
                chunk = symbols[start:start + 200]
                marks = ",".join("?" for _ in chunk)
                covered += db.execute(f"SELECT COUNT(DISTINCT symbol) FROM {table} WHERE symbol IN ({marks})",
                                      chunk).fetchone()[0]
            result["sources"][table] = {"covered": covered, "total": len(symbols)}
        return result
