"""Recalcula Top-10/20 sin muestreo sobre toda la historia utilizable desde 2016.

Congela la base y reutiliza rankings completos entre motores; no busca pesos,
fechas ni variantes por rentabilidad. No descarga ni modifica los datos fuente.
"""
import argparse
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import exchange_calendars as xcals
import pandas as pd

from . import config, identity, portfolio_metrics, scoring, screener_asof, universe
from . import factor_stability as fs
from . import multifactor_backtest as v1
from . import overfitting_audit as oa
from . import portfolio_backtest as v2


def _save(path: Path, data: dict) -> None:
    path.write_text(json.dumps(fs._json_safe(data), ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")


def prepare(cache: Path, *, start: str = "2016-01-02", stop: str | None = None,
            extra_sources: tuple[Path, ...] = ()) -> dict:
    """Congela la base y precalcula los rankings completos del intervalo.

    ``start``/``stop`` acotan las fechas de ranking (``stop`` exclusivo; por
    defecto hasta el final de la composición histórica). ``extra_sources``
    añade ficheros al fingerprint sin cambiar el de la auditoría 2016+.
    """
    cache.mkdir(parents=True, exist_ok=True)
    manifest_path = cache / "manifest.json"
    source_files = [Path(str(module.__file__)) for module in (v1, v2, screener_asof, scoring, identity)]
    source_files += [config.DATA_DIR / "sp500_historical_membership.csv", config.DATA_DIR / "sec_cik_map.csv"]
    source_files += list(extra_sources)
    hashes = {str(p.relative_to(config.BASE_DIR)).replace("\\", "/"): oa.sha256(p) for p in source_files}
    snapshot = cache / "snapshot.db"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if hashes != manifest["sources_sha256"] or oa.sha256(snapshot) != manifest["snapshot_sha256"]:
            raise ValueError("Cambiaron los inputs/código del snapshot. No se mezclan ejecuciones.")
    else:
        if snapshot.exists():
            raise ValueError("Snapshot sin manifiesto; revisar antes de continuar.")
        with sqlite3.connect(f"file:{config.DB_PATH.as_posix()}?mode=ro", uri=True) as source:
            with sqlite3.connect(snapshot) as target:
                source.backup(target)
        membership = universe.get_historical_membership()
        last_membership = pd.Timestamp(membership["date"].max())
        with sqlite3.connect(snapshot) as connection:
            last_spy = pd.Timestamp(connection.execute("SELECT max(date) FROM prices WHERE symbol='SPY' AND adj_close IS NOT NULL").fetchone()[0])
        calendar = xcals.get_calendar("XNYS")
        starts = []
        current = pd.Timestamp(start)
        while current <= last_membership and (stop is None or current < pd.Timestamp(stop)):
            end = calendar.date_to_session(current + pd.DateOffset(months=3), direction="next")
            if end > last_spy or end > pd.Timestamp(datetime.now(UTC).date()):
                break
            starts.append(current.date().isoformat())
            current += pd.DateOffset(months=3)
        if not starts:
            raise ValueError(f"No hay trimestres completos desde {start}.")
        manifest = {"created_at": datetime.now(UTC).isoformat(), "start": starts[0],
                    "end": current.date().isoformat(), "dates": starts,
                    "membership_last": last_membership.date().isoformat(), "spy_last": last_spy.date().isoformat(),
                    "max_symbols": None, "weights": scoring.DEFAULT_WEIGHTS, "top_n": [10, 20],
                    "months": 3, "min_coverage": .7, "min_universe_coverage": .5,
                    "v1_cost_bps_per_side": 10, "v2_initial_capital": 100000,
                    "v2_commission_usd": 1., "v2_spread_bps_total": 10.,
                    "snapshot_sha256": oa.sha256(snapshot), "sources_sha256": hashes, "rankings": {}}
        _save(manifest_path, manifest)
    original_db = config.DB_PATH
    config.DB_PATH = snapshot
    try:
        for number, date in enumerate(manifest["dates"], 1):
            path = cache / f"ranking-{date}.csv"
            record = manifest["rankings"].get(date)
            if record and path.exists() and oa.sha256(path) == record["sha256"]:
                print(f"{number}/{len(manifest['dates'])} {date}: cached full ranking", flush=True)
                continue
            membership = universe.get_sp500_constituents_asof(date)
            if not membership["is_exact"]:
                raise ValueError(membership["note"])
            print(f"{number}/{len(manifest['dates'])} {date}: ranking ALL {len(membership['symbols'])} constituents", flush=True)
            table = screener_asof.build_ranking_as_of(date, symbols=membership["symbols"],
                                                     weights=manifest["weights"])["table"]
            table.to_csv(path)
            eligible = table.loc[table.composite_score.notna() & (table.score_coverage >= .7)]
            manifest["rankings"][date] = {"sha256": oa.sha256(path), "n_universe": len(membership["symbols"]),
                                          "n_eligible": len(eligible), "symbols": membership["symbols"],
                                          "eligible_symbols": eligible.index.tolist(),
                                          "excluded_symbols": table.index.difference(eligible.index).tolist()}
            _save(manifest_path, manifest)
            print(f"{date}: {len(eligible)}/{len(table)} eligible, saved", flush=True)
    finally:
        config.DB_PATH = original_db
    return manifest


def evaluate(cache: Path, output: Path, *, start: str | None = None) -> dict:
    """Backtests V1/V2 sobre los rankings congelados.

    ``start`` evalúa una vista que empieza en esa fecha de rebalanceo (cartera
    nueva en caja), reutilizando los mismos rankings y el mismo snapshot.
    """
    manifest = json.loads((cache / "manifest.json").read_text(encoding="utf-8"))
    if len(manifest["rankings"]) != len(manifest["dates"]):
        raise ValueError("Faltan rankings; ejecutar preparación completa.")
    if start is not None:
        if start not in manifest["dates"]:
            raise ValueError(f"{start} no es una fecha de rebalanceo del manifiesto.")
        dates = [date for date in manifest["dates"] if date >= start]
        manifest = {**manifest, "start": start, "dates": dates, "view_of": manifest["start"],
                    "rankings": {date: manifest["rankings"][date] for date in dates}}
    if oa.sha256(cache / "snapshot.db") != manifest["snapshot_sha256"]:
        raise ValueError("Cambió el snapshot.")
    for name, expected in manifest["sources_sha256"].items():
        if oa.sha256(config.BASE_DIR / name) != expected:
            raise ValueError(f"Cambió el input: {name}")
    tables = {}
    for date, record in manifest["rankings"].items():
        path = cache / f"ranking-{date}.csv"
        if oa.sha256(path) != record["sha256"]:
            raise ValueError(f"Ranking alterado: {date}")
        tables[date] = pd.read_csv(path, index_col=0)

    def cached_rank(date, weights=None, symbols=None, **kwargs):
        if set(symbols or []) != set(manifest["rankings"][date]["symbols"]):
            raise ValueError("El motor solicitó un universo diferente del completo.")
        return {"table": tables[date].copy(), "universe_info": {"is_exact": True}}

    output.mkdir(parents=True, exist_ok=True)
    report: dict = {"created_at": datetime.now(UTC).isoformat(), "stage": "RESEARCH", "status": "running",
                    "inputs": manifest, "results": {}, "valuation_checks": []}
    original_daily = v2._daily_segment
    original_period_returns = v1._period_returns
    period_cache: dict = {}

    def cached_period_returns(symbols, as_of, months, cost_bps, held_symbols=None):
        key = (tuple(symbols), as_of, months, cost_bps, tuple(sorted(held_symbols or [])))
        if key not in period_cache:
            period_cache[key] = original_period_returns(symbols, as_of, months, cost_bps, held_symbols=held_symbols)
        return period_cache[key].copy()

    def checked_daily(cash, shares, entry_session, exit_session, sessions, *, owners=None):
        if shares:
            histories = identity.backtest_prices(list(shares), entry_session.date().isoformat(), owners)
            for symbol in shares:
                h = histories.get(symbol, pd.DataFrame())
                missing = len(sessions) if h.empty else int(h.adj_close.reindex(sessions).isna().sum())
                if missing:
                    report["valuation_checks"].append({"model": f"v2_top{top_n}", "symbol": symbol, "entry": str(entry_session.date()),
                                                       "end": str(exit_session.date()), "missing_sessions": missing})
        return original_daily(cash, shares, entry_session, exit_session, sessions, owners=owners)

    original_db = config.DB_PATH
    config.DB_PATH = cache / "snapshot.db"
    try:
        with (patch.object(screener_asof, "build_ranking_as_of", cached_rank),
              patch.object(v2, "_daily_segment", checked_daily),
              patch.object(v1, "_period_returns", cached_period_returns)):
            for top_n in manifest["top_n"]:
                print(f"Evaluate V1 full universe Top-{top_n}", flush=True)
                result = v1.run(manifest["start"], manifest["end"], months=3, top_n=top_n, max_symbols=None)
                result["periods"].to_csv(output / f"v1-top{top_n}-periods.csv", index=False)
                report["results"][f"v1_top{top_n}"] = {k: v for k, v in result.items() if k not in ("periods", "data_quality")}
                report["results"][f"v1_top{top_n}"].update(n_periods=len(result["periods"]),
                    actual_start=result["periods"].fecha.iloc[0], actual_end=result["periods"].hasta.iloc[-1])
                _save(output / "audit.json", report)
                print(f"Evaluate V2 full universe Top-{top_n}", flush=True)
                result = v2.run(manifest["start"], manifest["end"], months=3, top_n=top_n, max_symbols=None,
                                mode="validation", initial_capital=100000., commission_usd=1., spread_bps=10.)
                result["periods"].to_csv(output / f"v2-top{top_n}-periods.csv", index=False)
                nav = pd.DataFrame({"strategy": result["nav_curve"], "spy": result["nav_curve_spy"]})
                nav.to_csv(output / f"v2-top{top_n}-nav.csv", index_label="date")
                years = (nav.index[-1] - nav.index[0]).days / 365.25
                metrics = {}
                for column in nav:
                    total = float(nav[column].iloc[-1] / 100000 - 1)
                    metrics[column] = {"total_return_from_initial_cash": total, "cagr_from_initial_cash": (1 + total) ** (1 / years) - 1,
                                       "daily_risk": v1.daily_risk_metrics(nav[column]),
                                       "tail_risk": portfolio_metrics.tail_risk_metrics(portfolio_metrics.returns_from_nav(nav[column]), horizon="una sesión")}
                report["results"][f"v2_top{top_n}"] = {"metrics": metrics, "n_periods": len(result["periods"]),
                    "start": str(nav.index[0].date()), "end": str(nav.index[-1].date()), "n_nav": len(nav),
                    "skipped": result["skipped"], "turnover_medio": result["turnover_medio"],
                    "comision_total": result["comision_total"], "coste_total": result.get("coste_total"),
                    "capital_final": result["capital_final"],
                    "exit_events": result.get("exit_events", []),
                    "strict_result": result.get("strict_result", True)}
                _save(output / "audit.json", report)
                print(f"Top-{top_n}: net CAGR {metrics['strategy']['cagr_from_initial_cash']:.6%}", flush=True)
    finally:
        config.DB_PATH = original_db
    report["runner_sha256"] = fs.content_hash(Path(__file__))
    coverage_rows = []
    for date, record in manifest["rankings"].items():
        eligible = tables[date].loc[record["eligible_symbols"]]
        coverage_rows.append({
            "fecha": date, "n_universe": record["n_universe"], "n_eligible": record["n_eligible"],
            "coverage": record["n_eligible"] / record["n_universe"],
            "eligible_without_entity_id": int(eligible.entity_id.isna().sum()) if "entity_id" in eligible else None,
            "eligible_approximate_sector": int(eligible.sector_is_approximate.sum()) if "sector_is_approximate" in eligible else None,
            "eligible_symbols": ", ".join(record["eligible_symbols"]),
            "excluded_symbols": ", ".join(record["excluded_symbols"]),
        })
    coverage = pd.DataFrame(coverage_rows)
    coverage.to_csv(output / "coverage.csv", index=False)
    report["artifacts"] = {p.name: fs.content_hash(p) for p in output.glob("*.csv")}
    report["status"] = "complete"
    _save(output / "audit.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=config.DATA_DIR / "full_universe_audit")
    parser.add_argument("--output", type=Path, default=config.BASE_DIR / "docs" / "full-universe-audit")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--run-only", action="store_true")
    args = parser.parse_args()
    if not args.run_only:
        prepare(args.cache)
    if not args.prepare_only:
        evaluate(args.cache, args.output)


if __name__ == "__main__":
    main()
