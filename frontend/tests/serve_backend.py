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
                "quantile_returns": [{"quantil": 5, "retorno_medio": 0.04}],
                "turnover": [{"factor": "value_score", "quantil": 5, "turnover": 0.2}],
                "skipped": []}
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
