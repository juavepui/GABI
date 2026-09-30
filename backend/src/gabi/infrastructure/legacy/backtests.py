"""Run the unchanged V1/V2 backtest engines with the metrics Streamlit showed."""

import sqlite3
from contextlib import closing
from pathlib import Path


def run_backtest_v1(start: str, end: str, options: dict) -> dict:
    from gabi import multifactor_backtest

    return multifactor_backtest.run(
        start, end, options["months"], options["top_n"], options["cost_bps"],
        max_symbols=options["universe_size"],
        rotation_hurdle_points=options["rotation_hurdle_points"],
    )


def run_backtest_v2(start: str, end: str, options: dict) -> dict:
    from gabi import multifactor_backtest, portfolio_backtest, portfolio_metrics

    result = portfolio_backtest.run(
        start, end, months=options["months"], top_n=options["top_n"],
        max_symbols=options["max_symbols"], mode=options["mode"],
        initial_capital=options["initial_capital"], commission_usd=options["commission_usd"],
        spread_bps=options["spread_bps"], rotation_hurdle_points=options["rotation_hurdle_points"],
    )
    nav, nav_spy = result["nav_curve"], result["nav_curve_spy"]
    daily = multifactor_backtest.daily_risk_metrics(nav)
    returns, returns_spy = nav.pct_change().dropna(), nav_spy.pct_change().dropna()
    result["metrics"] = {
        "estrategia": daily,
        "spy": multifactor_backtest.daily_risk_metrics(nav_spy),
        "calmar": portfolio_metrics.calmar_ratio(daily["anualizado"], daily["max_drawdown"]),
        "recovery_days": portfolio_metrics.recovery_time(nav),
        "beta": portfolio_metrics.beta_vs_benchmark(returns, returns_spy),
        "information_ratio": portfolio_metrics.information_ratio(returns, returns_spy),
        "capture": portfolio_metrics.capture_ratios(returns, returns_spy),
    }
    return result


def _already_registered(data_dir: Path, source_job_id: str) -> int | None:
    path = data_dir / "gabi.db"
    if not path.is_file():
        return None
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=30)) as db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='experiments'").fetchone() is None:
            return None
        row = db.execute("SELECT id FROM experiments WHERE json_valid(result_json) "
                         "AND json_extract(result_json,'$.backtest_job_id')=?", (source_job_id,)).fetchone()
    return row[0] if row else None


def register_backtest(data_dir: Path, registration: dict) -> dict:
    """Log a verified backtest artifact once, with the same fields and data fingerprint as Streamlit."""
    from gabi import data_quality, research_lab
    from gabi.application.research.backtests import experiment_from_backtest
    from gabi.infrastructure.storage.jobs import SqliteJobs

    source = registration["source_job_id"]
    jobs = SqliteJobs(data_dir)
    job = jobs.get(source)
    if job["kind"] not in {"backtest_v1", "backtest_v2"}:
        raise ValueError("El trabajo de origen no es un backtest V1/V2.")
    artifact = jobs.result(source)  # Verifies the stored SHA-256 before reading it.
    existing = _already_registered(data_dir, source)
    if existing is not None:
        raise ValueError(f"Este backtest ya está registrado como experimento #{existing}.")
    record = experiment_from_backtest(artifact, registration, job["result_sha256"])
    fingerprint = data_quality.compute_data_fingerprint()
    experiment_id = research_lab.log_experiment(
        record.pop("model_id"), record.pop("stage"), record.pop("hypothesis_registered"),
        data_fingerprint=fingerprint, **record)
    return {"kind": "backtest_register", "experiment_id": experiment_id, "source_job_id": source,
            "source_result_sha256": job["result_sha256"], "data_fingerprint": fingerprint,
            "data_fingerprint_scope": "registration", "stage": registration["stage"],
            "family": registration["family"], "hypothesis_registered": registration["hypothesis_registered"]}


class LegacyBacktestMath:
    """Pure legacy formulas shared with the Streamlit page; no storage access."""

    @staticmethod
    def tail_risk(returns, horizon: str) -> dict:
        from gabi import portfolio_metrics

        return portfolio_metrics.tail_risk_metrics(returns, horizon=horizon)

    @staticmethod
    def returns_from_nav(nav):
        from gabi import portfolio_metrics

        return portfolio_metrics.returns_from_nav(nav)

    @staticmethod
    def tax_drag(periods, initial_capital: float) -> dict:
        from gabi import tax_drag

        return tax_drag.simulate_tax_drag(periods, initial_capital=initial_capital)

    @staticmethod
    def zero_turnover(periods, return_column: str):
        from gabi import tax_drag

        return tax_drag.zero_turnover_periods(periods, return_column)

    @staticmethod
    def tax_limitations() -> list[str]:
        from gabi import tax_drag

        return list(tax_drag.LIMITATIONS)


def run_factor_contrast(periods, hac_lags: int | None) -> dict:
    """The Fama-French block of the old V1 page: cached factors, HAC regression, stability, benchmark."""
    import hashlib

    from gabi import academic_factors, config, factor_benchmark, factor_stability

    factors = academic_factors.fetch_ff_factors()  # Reads data/ff_factors.csv; downloads only if absent.
    cache = config.DATA_DIR / "ff_factors.csv"
    source = {"file": "ff_factors.csv", "sha256": hashlib.sha256(cache.read_bytes()).hexdigest(),
              "first_month": factors.index.min().date().isoformat(),
              "last_month": factors.index.max().date().isoformat(),
              "url": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html"}
    result: dict = {"factors_source": source}
    try:
        result["regression"] = academic_factors.regress_returns_on_factors(periods, factors, hac_lags=hac_lags)
    except (ValueError, RuntimeError) as exc:
        result["regression"] = str(exc)
    try:
        result["stability"] = factor_stability.analyze(factor_stability.aligned_quarters(periods, factors))
    except (ValueError, KeyError) as exc:
        result["stability"] = f"Diagnóstico temporal no disponible: {exc}"
    try:
        result["benchmark"] = factor_benchmark.analyze(factor_benchmark.aligned_inputs(periods, factors))
    except (ValueError, KeyError) as exc:
        result["benchmark"] = f"Benchmark trimestral no disponible: {exc}"
    return result


def contrast_backtest(data_dir: Path, request: dict) -> dict:
    from gabi.application.research.backtest_factors import build_factor_contrast
    from gabi.infrastructure.storage.jobs import SqliteJobs

    jobs = SqliteJobs(data_dir)
    source = jobs.get(request["source_job_id"])
    artifact = jobs.result(request["source_job_id"])  # Verifies the stored SHA-256.
    return build_factor_contrast(artifact, request, source["result_sha256"], run_factor_contrast)
