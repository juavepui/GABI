"""Execute the three previously declared rotation policies on frozen full-universe data.

No downloads, parameter search, live recommendations or blind-validation reads.
Run: python -m gabi.rotation_experiment
"""
import argparse
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import exchange_calendars as xcals
import numpy as np
import pandas as pd

from . import config, identity, rotation_policy, screener_asof
from . import portfolio_backtest as v2
from . import variant_validation as vv
from .factor_stability import _json_safe, content_hash
from .overfitting_audit import sha256


def save(path: Path, value: dict) -> None:
    path.write_text(json.dumps(_json_safe(value), ensure_ascii=False, indent=2,
                               allow_nan=False) + "\n", encoding="utf-8")


def execute(cache: Path, output: Path, *, resume: bool = False) -> dict:
    manifest_path = cache / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest["start"], manifest["end"], len(manifest["dates"])) != (vv.DEFAULT_START, vv.DEFAULT_END, 39):
        raise ValueError("The source audit does not have the prescribed 39 quarters.")
    source_db = cache / "snapshot.db"
    if sha256(source_db) != manifest["snapshot_sha256"]:
        raise ValueError("Frozen database hash mismatch.")
    for name in ("sp500_historical_membership.csv", "sec_cik_map.csv"):
        if sha256(config.DATA_DIR / name) != manifest["sources_sha256"][f"data/{name}"]:
            raise ValueError(f"Source changed: {name}")
    tables = {}
    for day in manifest["dates"]:
        path = cache / f"ranking-{day}.csv"
        if sha256(path) != manifest["rankings"][day]["sha256"]:
            raise ValueError(f"Frozen ranking hash mismatch: {day}")
        tables[day] = pd.read_csv(path, index_col=0)

    output.mkdir(parents=True, exist_ok=True)
    protocol_path = output / "protocol.json"
    if protocol_path.exists() and not resume:
        raise ValueError("Output already contains a protocol; choose a new output directory.")
    protocol = {
        "declared_at": datetime.now(UTC).isoformat(), "stage": "retrospective_research",
        "variants": {"control_composite": 0, "hurdle_5": 5, "hurdle_10": 10},
        "start": vv.DEFAULT_START, "end": vv.DEFAULT_END, "top_n": 20, "months": 3,
        "initial_capital": 100000., "commission_usd": 1., "spread_bps": 10.,
        "weights": manifest["weights"], "max_symbols": None,
        "windows": vv.DEFAULT_WINDOWS, "future": "not_evaluated",
        "snapshot_sha256": manifest["snapshot_sha256"],
        "source_manifest_sha256": sha256(manifest_path),
        "rankings_sha256": {day: manifest["rankings"][day]["sha256"] for day in tables},
        "code_sha256": {Path(str(module.__file__)).name: sha256(Path(str(module.__file__)))
                         for module in (v2, rotation_policy, vv, identity)},
        "limitations": [
            "Frozen rankings and source coverage from the previous full-universe audit.",
            "Historical identity and sector approximations remain.",
            "Development/validation split is retrospective, not an untouched holdout.",
            "Only the rotation change is tested; descriptive metrics do not change selection.",
            "USD returns net of commissions/spread, before tax/FX, without final liquidation.",
            "Turnover is gross buys plus sells divided by NAV, including weight adjustments.",
            "V2 retains its small negative cash balances after costs; no funding charge.",
        ],
    }
    if resume:
        previous_protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
        for key in protocol:
            if key != "declared_at" and json.loads(json.dumps(_json_safe(protocol[key]))) != previous_protocol[key]:
                raise ValueError(f"Protocol changed: {key}")
        protocol = previous_protocol
    else:
        save(protocol_path, protocol)  # Written BEFORE the first backtest.
    print("Protocol saved. Testing exactly 0, 5, 10 points on Top-20.", flush=True)

    # Preserve the source snapshot; all incidental schema initialization is isolated.
    working_db = config.DATA_DIR / "rotation_experiment_work.db"
    if working_db.exists() and not resume:
        raise ValueError("Working database already exists; review before rerunning.")
    if not working_db.exists():
        shutil.copyfile(source_db, working_db)
    original_db = config.DB_PATH
    config.DB_PATH = working_db
    daily = v2._daily_segment
    rebalance = v2._rebalance
    current_name = ""
    checks = []
    counts: dict[str, int] = {}
    trades = []

    def cached_rank(day, weights=None, symbols=None, **kwargs):
        if set(symbols or []) != set(manifest["rankings"][day]["symbols"]):
            raise ValueError(f"Universe mismatch at {day}")
        return {"table": tables[day].copy(), "universe_info": {"is_exact": True}}

    def checked_daily(cash, shares, entry_session, exit_session, sessions, *, owners=None):
        histories = identity.backtest_prices(list(shares), str(entry_session.date()), owners)
        for symbol in shares:
            h = histories[symbol]
            if h.empty or h.adj_close.reindex(sessions).isna().any():
                raise ValueError(f"Missing daily valuations: {current_name} {symbol} {entry_session}")
        checks.append({"variant": current_name, "entry": str(entry_session.date()),
                       "exit": str(exit_session.date()), "positions": len(shares),
                       "sessions": len(sessions)})
        return daily(cash, shares, entry_session, exit_session, sessions, owners=owners)

    def logged_rebalance(*args, **kwargs):
        result = rebalance(*args, **kwargs)
        counts[current_name] = counts.get(current_name, 0) + 1
        trades.append({"variant": current_name, "period": counts[current_name],
                       "held_count": len(result["held"]), "bought_count": len(result["bought"]),
                       "sold_count": len(result["sold"]), "cash_after": result["cash"]})
        print(f"{current_name}: {counts[current_name]}/39 rebalances", flush=True)
        return result

    def runner(start: str, end: str, **kwargs):
        nonlocal current_name
        hurdle = kwargs.get("rotation_hurdle_points", 0)
        current_name = "control_composite" if hurdle == 0 else f"hurdle_{hurdle}"
        params = {**kwargs, "initial_capital": 100000., "commission_usd": 1., "spread_bps": 10.}
        periods_path = output / f"{current_name}-periods.csv"
        nav_path = output / f"{current_name}-nav.csv"
        if resume and periods_path.exists() and nav_path.exists():
            periods = pd.read_csv(periods_path).fillna({"held": "", "bought": "", "sold": ""})
            if periods.fecha.tolist() != manifest["dates"]:
                raise ValueError("Incomplete saved trial.")
            nav = pd.read_csv(nav_path, index_col=0, parse_dates=True)
            result = {"periods": periods, "nav_curve": nav.strategy, "nav_curve_spy": nav.spy,
                      "initial_capital": 100000., "skipped": []}
            # Independently recheck valuations of the completed trial from its holdings.
            calendar = xcals.get_calendar("XNYS")
            symbols: set[str] = set()
            for row in periods.itertuples():
                symbols.update(s for s in (row.held + ", " + row.bought).split(", ") if s)
            histories = identity.backtest_prices(sorted(symbols), start)
            for i, row in enumerate(periods.itertuples(), 1):
                positions = [s for s in (row.held + ", " + row.bought).split(", ") if s]
                entry = calendar.next_session(calendar.date_to_session(pd.Timestamp(row.fecha), direction="previous"))
                sessions = calendar.sessions_in_range(entry, pd.Timestamp(row.hasta))
                for symbol in positions:
                    if histories[symbol].adj_close.reindex(sessions).isna().any():
                        raise ValueError(f"Missing saved trial prices: {symbol}")
                checks.append({"variant": current_name, "entry": str(entry.date()), "exit": row.hasta,
                               "positions": len(positions), "sessions": len(sessions)})
                trades.append({"variant": current_name, "period": i,
                               "held_count": len([s for s in row.held.split(", ") if s]),
                               "bought_count": len([s for s in row.bought.split(", ") if s]),
                               "sold_count": len([s for s in row.sold.split(", ") if s]),
                               "cash_after": None})
            print(f"{current_name}: restored all 39 completed quarters, valuations rechecked.", flush=True)
        else:
            result = v2.run(start, end, **params)
        result["periods"].to_csv(output / f"{current_name}-periods.csv", index=False)
        pd.DataFrame({"strategy": result["nav_curve"], "spy": result["nav_curve_spy"]}).to_csv(
            output / f"{current_name}-nav.csv", index_label="date")
        if current_name == "control_composite":
            old = pd.read_csv(config.BASE_DIR / "docs/full-universe-audit/v2-top20-nav.csv",
                              index_col=0, parse_dates=True)
            pd.testing.assert_index_equal(result["nav_curve"].index.as_unit("ns"),
                                          old.index.as_unit("ns"), check_names=False)
            np.testing.assert_allclose(result["nav_curve"], old.strategy, rtol=1e-10, atol=1e-7)
            print("Control reproduces the previously published Top-20 NAV.", flush=True)
        return result

    try:
        with (patch.object(screener_asof, "build_ranking_as_of", cached_rank),
              patch.object(v2, "_daily_segment", checked_daily),
              patch.object(v2, "_rebalance", logged_rebalance)):
            outcome = vv.run_validation([vv.VariantSpec("hurdle_5", {"rotation_hurdle_points": 5}),
                                         vv.VariantSpec("hurdle_10", {"rotation_hurdle_points": 10})],
                                        runner=runner)
    finally:
        config.DB_PATH = original_db

    control = outcome["results"]["control_composite"]
    spy = control["nav_curve_spy"]
    spy_result = {**control, "nav_curve": spy}
    spy_rows = []
    for window, (start, end) in vv.DEFAULT_WINDOWS.items():
        row = vv._window_metrics(spy_result, start, end)
        # Cost/turnover rows belong to the active strategy, not the passive benchmark.
        for key in ("turnover", "commissions", "spread_cost", "cost_total", "n_periods"):
            row[key] = None
        spy_rows.append({"variant": "spy_buy_hold", "window": window, **row})
    summary = pd.concat([outcome["report"], pd.DataFrame(spy_rows)], ignore_index=True)
    summary.to_csv(output / "metrics.csv", index=False)
    pd.DataFrame(trades).to_csv(output / "trades.csv", index=False)

    # Quarterly returns include boundary rebalances in the new quarter, without overlap.
    quarterly: dict[str, list[float]] = {}
    for name, result in outcome["results"].items():
        quarterly[name] = []
        for i, start in enumerate(manifest["dates"]):
            end = manifest["dates"][i + 1] if i + 1 < 39 else vv.DEFAULT_END
            metrics = vv._window_metrics(result, start, end)
            quarterly[name].append(metrics["final_value"] / metrics["initial_value"] - 1)
    quarter_table = pd.DataFrame(quarterly, index=manifest["dates"])
    quarter_table.to_csv(output / "quarterly-returns.csv", index_label="fecha")
    paired = {}
    for name in ("hurdle_5", "hurdle_10"):
        delta = quarter_table[name] - quarter_table.control_composite
        paired[name] = {"quarters_better": int((delta > 1e-12).sum()),
                        "quarters_worse": int((delta < -1e-12).sum()),
                        "quarters_tied": int((delta.abs() <= 1e-12).sum()),
                        "mean_quarterly_difference": float(delta.mean())}
    report = {"protocol": protocol, "completed_at": datetime.now(UTC).isoformat(),
              "status": "complete", "control_reproduces_prior_audit": True,
              "metrics": summary.to_dict("records"), "quarterly_comparison": paired,
              "daily_valuation_checks": checks, "future": outcome["future"],
              "artifacts_sha256": {p.name: sha256(p) for p in output.glob("*.csv")}}
    report["artifacts_canonical_sha256"] = {p.name: content_hash(p) for p in output.glob("*.csv")}
    save(output / "audit.json", report)
    print(summary.to_string(index=False), flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=config.DATA_DIR / "full_universe_audit")
    parser.add_argument("--output", type=Path, default=config.BASE_DIR / "docs/rotation-experiment")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    execute(args.cache, args.output, resume=args.resume)


if __name__ == "__main__":
    main()
