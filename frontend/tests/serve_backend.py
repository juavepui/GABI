"""Loopback test API. No real configuration, credentials, database or network sources."""
import hashlib
import json
import shutil
import sqlite3
import sys
import threading
import time
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory, gettempdir

import uvicorn

from gabi import research_lab
from gabi.application.research.backtests import build_backtest
from gabi.domain.research.blind import canonical_payload
from gabi.infrastructure.jobs.worker import Worker
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.jobs import SqliteJobs
from gabi.infrastructure.storage.published_factors import FilePublishedFactors
from gabi_api.bootstrap import create_app

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend" / "tests"))
from market_fixture import TODAY, seed_fixture  # noqa: E402


def main():
    with TemporaryDirectory(prefix="gabi-react-e2e-") as directory:
        root = Path(directory).resolve()
        assert root.is_relative_to(Path(gettempdir()).resolve())
        seed_fixture(root)
        published_root = Path(__file__).resolve().parents[2]
        for source in FilePublishedFactors(published_root)._paths():
            if source.is_relative_to(published_root / "docs"):
                destination = root / source.relative_to(published_root)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
        payload = canonical_payload("2026-07-01", ["SEALED_TICKER"], {"SEALED_TICKER": 100.0})
        with closing(sqlite3.connect(root / "gabi.db")) as db:
            db.execute("INSERT INTO blind_validations "
                       "(id,created_at,name,model_id,weights_json,n_positions,rebalance_months,start_date,unlock_date,status) "
                       "VALUES (1,'2026-07-01',?,'fixture','{}',1,?,?,?,?)",
                       ("Fixture ciega", 3, "2026-07-01", "2027-09-17", "locked"))
            db.execute("INSERT INTO blind_validation_periods "
                       "(validation_id,rebalance_date,symbols_json,entry_prices_json,prev_hash,record_hash,recorded_at,weights_json) "
                       "VALUES (?,?,?,?,?,?,'2026-07-01','{}')",
                       (1, "2026-07-01", json.dumps(["SEALED_TICKER"]),
                        json.dumps({"SEALED_TICKER": 100.0}), None,
                        hashlib.sha256(payload.encode()).hexdigest()))
            db.executescript("DROP TABLE experiments;" + research_lab.SCHEMA)
            db.execute("INSERT INTO experiments (created_at,model_id,git_commit,hypothesis_registered,stage,family,"
                       "n_positions,rebalance,sharpe,max_drawdown,periods_per_year,n_periods,returns_json,deps_json,"
                       "python_version,env_fingerprint,data_fingerprint) "
                       "VALUES ('2026-09-01','GABI-MF-v1.0','abc1234',0,'RESEARCH','mf-v1',20,'Quarterly',0.61,"
                       "-0.21,4,3,?,?,'3.13.7','0123456789ab','fixture-data')",
                       (json.dumps({"2019-03-29": 0.02, "2019-06-28": -0.01, "2019-09-30": 0.03}),
                        json.dumps({"pandas": "2.3.0", "numpy": "2.2.0"})))
            db.execute("INSERT INTO experiments (created_at,model_id,hypothesis_registered,stage,family,sharpe,notes) "
                       "VALUES ('2026-09-02','GABI-MF-v2.0',1,'OUT_OF_SAMPLE','mf-v2',0.4,'Fixture fuera de muestra')")
            db.commit()
        published = root / "published-ledger.json"
        published.write_text(json.dumps({
            "as_of": "2026-09-29", "scope": "explicit_published_repository_artifacts_only",
            "counts": {"legacy_guard_entries": 2}, "exhaustive_search_history": False,
            "global_error_control_established": False, "limitations": ["Fixture no exhaustiva"],
            "diagnostics": [], "unresolved_groups": [], "legacy_entries": [
                {"id": "trial/failed", "family": "test_family", "configuration_sha256": "a" * 64,
                 "specification_ref": "docs/test/protocol.json", "result_ref": "docs/test/result.json",
                 "observed_sample": {"start": "2016-01-01"}, "planned_sample": None,
                 "state": "observed", "decision": "failed_daily_gate", "failures": ["negative_excess"],
                 "demonstrated_superiority": False},
                {"id": "trial/pending", "family": "forward_family", "configuration_sha256": "b" * 64,
                 "specification_ref": "docs/forward/protocol.json", "result_ref": None,
                 "observed_sample": None, "planned_sample": {"start": "2026-10-01"},
                 "state": "pending_prospective", "decision": "await_preregistered_looks", "failures": None,
                 "demonstrated_superiority": False}],
            "additional_observed_records": [],
        }), encoding="utf-8")
        app = create_app(Settings(root), today=lambda: TODAY, published_ledger=published,
                         published_factors_root=root)

        worker = Worker(SqliteJobs(root), lambda command: synthetic_job(command, app), root)
        threading.Thread(target=lambda: work_forever(worker), daemon=True).start()
        uvicorn.run(app, host="127.0.0.1", port=8001, log_level="warning")


def synthetic_backtest_v1(start, end, options):
    import pandas as pd

    periods = pd.DataFrame([
        {"fecha": "2019-01-02", "hasta": "2019-04-02", "candidatas": "T000, T001",
         "cobertura universo": "45/50", "retorno": 0.05, "spy": 0.02, "universo_ew": 0.03,
         "turnover_pct": None},
        {"fecha": "2019-04-02", "hasta": "2019-07-02", "candidatas": "T000, T002",
         "cobertura universo": "44/50", "retorno": 0.01, "spy": 0.03, "universo_ew": 0.02,
         "turnover_pct": 50.0},
    ])
    periods["capital"] = (1 + periods["retorno"]).cumprod()
    periods["spy_capital"] = (1 + periods["spy"]).cumprod()
    periods["universo_capital"] = (1 + periods["universo_ew"]).cumprod()
    metrics = {"anualizado": 0.12, "vol_anualizada": 0.18, "sharpe": 0.45, "sortino": 0.6,
               "max_drawdown": -0.04}
    return {"periods": periods, "skipped": [{"fecha": "2019-07-02", "motivo": "cobertura insuficiente"}],
            "data_quality": {}, "rotation_hurdle_points": options["rotation_hurdle_points"],
            "turnover_medio": 50.0, "return": float(periods["capital"].iloc[-1] - 1),
            "spy_return": float(periods["spy_capital"].iloc[-1] - 1),
            "universo_ew_return": float(periods["universo_capital"].iloc[-1] - 1), "drawdown": 0.0,
            "metrics": {"estrategia": metrics, "universo_ew": metrics, "spy": metrics}}



def synthetic_factor_contrast(periods, hac_lags):
    names = ["alpha", "Mkt-RF", "SMB", "HML", "RMW", "CMA", "Mom"]
    values = dict(zip(names, (0.004, 1.02, 0.1, -0.05, 0.2, 0.03, 0.08)))
    return {"factors_source": {"file": "ff_factors.csv", "sha256": "0" * 64, "first_month": "1990-01-01",
                               "last_month": "2025-06-01", "url": "https://example.invalid"},
            "regression": {"n_obs": 20, "dof": 13, "r2": 0.91, "coef": values,
                           "se": {name: 0.002 for name in names},
                           "t_stat": {name: 2.1 for name in names},
                           "t_stat_ols": {name: 2.5 for name in names}, "hac_lags": hac_lags or 3,
                           "periods_per_year": 4, "alpha_anualizado": 0.0161,
                           "periodos_alineados": 20, "periodos_totales": 20},
            "stability": "Diagnóstico temporal no disponible: fixture sin trimestres suficientes",
            "benchmark": "Benchmark trimestral no disponible: fixture sin trimestres suficientes"}

def synthetic_job(command, app):
    time.sleep(0.5)
    if command.kind == "factor_analysis":
        return {"kind": "factor_analysis", "status": "RETROSPECTIVE_EXPLORATORY",
                "independent_advantage_demonstrated": False, "start": command.start, "end": command.end,
                "months": command.factor_months, "mode": command.factor_mode,
                "max_symbols": command.factor_max_symbols,
                "summary": [{"factor": "value_score", "horizonte": 3, "sector_neutral": False,
                             "ic_mean": 0.12, "ic_std": 0.02, "icir": 6.0,
                             "pct_ic_positive": 0.75, "q_spread": 0.03, "n_periods": 4}],
                "ic_series": [{"fecha": "2019-01-02", "ic_raw": 0.12}],
                "quantile_returns": [
                    {"fecha": fecha, "factor": "value_score", "horizonte": 3, "quantil": quantil,
                     "retorno_medio": retorno, "retorno_medio_neutral": None}
                    for fecha, quantil, retorno in (("2019-01-02", 1, 0.01), ("2019-04-02", 1, 0.03),
                                                    ("2019-01-02", 5, 0.04), ("2019-04-02", 5, 0.06))],
                "turnover": [{"factor": "value_score", "quantil": 5, "turnover": 0.2}],
                "skipped": [{"fecha": "2019-07-02", "motivo": "cobertura insuficiente del universo (10/50)"}]}
    if command.kind == "backtest_v1":
        return build_backtest(command.kind, command.start, command.end, command.backtest_options,
                              synthetic_backtest_v1)
    if command.kind == "historical_outcomes":
        from gabi.application.research.historical_outcomes import build_outcomes
        from gabi.infrastructure.storage.jobs import SqliteJobs as Jobs

        source = Jobs(Path(app.state.settings.data_dir))
        source_id = command.outcomes["source_job_id"]
        return build_outcomes(source.result(source_id), command.outcomes, source.get(source_id)["result_sha256"],
                              lambda symbols, as_of, months, cost: {
                                  "status": "complete", "end_date": "2019-07-02", "available": len(symbols),
                                  "requested": len(symbols), "portfolio_return": 0.05 if months == 6 else 0.12,
                                  "benchmark_return": 0.03, "excess_return": 0.02, "missing": []})
    if command.kind == "prepare_history":
        from gabi.application.research.preparation import preparation_result

        limit = command.preparation.get("universe_limit") or 500
        return preparation_result(command.start, command.end, command.preparation, {
            "symbols": limit, "universe_note": "Composición registrada (fixture).", "universe_is_exact": True,
            "edgar_refreshed": 2, "prices_deep_fetched": 1, "prices_already_covered": limit - 1,
        }, {"T009": {"precio": "sin histórico en la fuente"}})
    if command.kind == "backtest_factors":
        from gabi.application.research.backtest_factors import build_factor_contrast
        from gabi.infrastructure.storage.jobs import SqliteJobs as Jobs

        source = Jobs(Path(app.state.settings.data_dir))
        source_id = command.factor_contrast["source_job_id"]
        return build_factor_contrast(source.result(source_id), command.factor_contrast,
                                     source.get(source_id)["result_sha256"], synthetic_factor_contrast)
    if command.kind == "backtest_register":
        return {"kind": "backtest_register", "experiment_id": 7,
                "source_job_id": command.research_log["source_job_id"], "data_fingerprint": "fixture",
                "data_fingerprint_scope": "registration", "stage": command.research_log["stage"]}
    if command.kind == "historical_ranking":
        return {"as_of": command.start, "status": "RETROSPECTIVE_EXPLORATORY",
                "independent_advantage_demonstrated": False,
                "universe_info": {"is_exact": True, "source_date": command.start},
                "total": 2, "rows": [
                    {"symbol": "T000", "name": "Fixture A", "sector": "Industrials",
                     "composite_score": 72.5, "score_coverage": 0.9, "identity_status": "resolved",
                     "sector_is_approximate": False, "price": 100.0},
                    {"symbol": "T001", "name": "Fixture B", "sector": None,
                     "composite_score": None, "score_coverage": 0.3, "identity_status": "unresolved",
                     "sector_is_approximate": True, "price": None}]}
    if command.kind == "decision_plan":
        return app.state.decisions.generate(command.decision_policy, command.holdings_text)
    if command.kind == "filing_check":
        return app.state.signals.filings(command.snapshot_id)
    if command.kind == "sim_compare":
        return app.state.simulations.compare()
    if command.kind == "quality":
        return {"universe": 2, "sources": {"prices": {"covered": 2, "total": 2},
                                            "fundamentals": {"covered": 1, "total": 2}}}
    return {"fixture": True, "kind": command.kind}


def work_forever(worker):
    while True:
        if not worker.run_once():
            time.sleep(0.1)


if __name__ == "__main__":
    main()

