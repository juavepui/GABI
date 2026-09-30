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
