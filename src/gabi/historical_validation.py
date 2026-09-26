"""Validación de GABI en 2010-2015 sin reoptimizar (issue #33).

Reutiliza ``full_universe_audit`` (snapshot congelado de la base, rankings
completos con hash, V1/V2 Top-10/20 con la configuración vigente) sobre las
fechas de rebalanceo trimestrales equivalentes a las de 2016+ (día 2 de
enero/abril/julio/octubre). Encima añade lo que exige el #28 para este
periodo:

- diagnóstico de cobertura por rebalanceo (identidad, precio acreditado,
  fundamentales, 13 métricas, elegibles y motivos de exclusión) y si el corte
  es concluyente;
- benchmarks del mismo universo cubierto (equiponderado y ponderado por
  capitalización) además de SPY;
- retorno implícito del grupo sin precio acreditado (SPY menos la contribución
  de los cubiertos, con pesos de *public float* SEC);
- cotas de sensibilidad del universo completo suponiendo que los excluidos
  rinden como el peor o el mejor decil de los cubiertos.

No cambia pesos, umbrales ni fechas en función del resultado.
"""

import argparse
import json
from pathlib import Path

import exchange_calendars as xcals
import numpy as np
import pandas as pd

from . import config, historical_pit, identity, scoring, storage
from . import factor_stability as fs
from . import full_universe_audit as fua

START, STOP = "2010-01-02", "2016-01-01"
CACHE = config.DATA_DIR / "historical_validation_2010_2015"
OUTPUT = config.BASE_DIR / "docs" / "historical-validation-2010-2015"
QUARTERLY_AUDIT = config.BASE_DIR / "docs" / "historical-prices-quarterly-2010-2015.csv"
QUARTERLY_SUMMARY = config.BASE_DIR / "docs" / "historical-prices-quarterly-2010-2015.json"
CONCLUSIVE_ACCREDITED = 0.85  # restricción heredada del #28
# Pesos plausibles: fuera de este rango el dato XBRL es un error de unidad
# (p. ej. un float de 1,2e16 USD); la mayor empresa de 2010-2015 rondaba 0,7e12.
MIN_WEIGHT_USD, MAX_WEIGHT_USD = 1e8, 1.5e12
MIN_COVERAGE, MIN_UNIVERSE = 0.7, 0.5  # mismos umbrales que la auditoría 2016+
FUNDAMENTAL_METRICS = [*scoring.SCORE_METRICS["value"], *scoring.SCORE_METRICS["quality"], "debt_to_equity"]
PRICE_METRICS = [*scoring.SCORE_METRICS["momentum"], "volatility", "max_drawdown"]
ALL_METRICS = [metric for group in scoring.SCORE_METRICS.values() for metric in group]


def extra_sources() -> tuple[Path, ...]:
    root = Path(__file__).parent
    names = ["historical_pit.py", "historical_price_policy.py", "historical_price_audit.py",
             "historical_issuer_evidence.py", "universe.py"]
    return (*[root / name for name in names], QUARTERLY_AUDIT)


def _audit_rebalance(date: str) -> dict | None:
    """Última fecha de la auditoría trimestral de precios anterior al ranking."""
    summary = json.loads(QUARTERLY_SUMMARY.read_text(encoding="utf-8"))
    prior = [row for row in summary["rebalances"] if row["as_of"] <= date]
    return prior[-1] if prior else None


def coverage_by_rebalance(tables: dict[str, pd.DataFrame], executed: set[str]) -> pd.DataFrame:
    rows = []
    for date, table in tables.items():
        members = len(table)
        identity_ok = table["entity_id"].notna()
        priced = table["price_source"].notna()
        present = table.reindex(columns=ALL_METRICS).notna()
        fundamentals = table.reindex(columns=FUNDAMENTAL_METRICS).notna().sum(axis=1)
        eligible = table["composite_score"].notna() & (table["score_coverage"] >= MIN_COVERAGE)
        audit = _audit_rebalance(date)
        accredited = audit["usable_pct"] / 100 if audit else None
        eligible_share = eligible.sum() / members
        reasons = {"identidad_no_acreditada": int((~identity_ok).sum()),
                   "sin_precio_acreditado": int((identity_ok & ~priced).sum()),
                   "cobertura_metricas_inferior_70": int((identity_ok & priced & ~eligible).sum())}
        conclusive = bool(date in executed and accredited is not None and accredited >= CONCLUSIVE_ACCREDITED
                          and eligible_share >= MIN_UNIVERSE)
        rows.append({
            "fecha": date, "auditoria_precios": audit["as_of"] if audit else None,
            "constituyentes": members, "identidad_acreditada": int(identity_ok.sum()),
            "precio_acreditado": int(priced.sum()),
            "cobertura_precio_auditoria": round(accredited, 4) if accredited is not None else None,
            "fundamentales_suficientes_6_de_8": int((fundamentals >= 6).sum()),
            "metricas_momentum_riesgo_completas": int(table.reindex(columns=PRICE_METRICS).notna().all(axis=1).sum()),
            "13_metricas_calculables": int(present.all(axis=1).sum()),
            "elegibles": int(eligible.sum()), "cobertura_elegible": round(eligible_share, 4),
            "ejecutado": date in executed, "concluyente": conclusive,
            **reasons,
        })
    return pd.DataFrame(rows)


def _returns(symbols: list[str], date: str, entry: pd.Timestamp, exit_session: pd.Timestamp) -> dict:
    """Retornos sin costes entre entrada y salida con la misma regla de salida
    que el backtest (evento terminal o último precio no estricto)."""
    histories = identity.backtest_prices(symbols, date)
    result = {}
    for symbol in symbols:
        frame = histories.get(symbol, pd.DataFrame())
        if frame.empty or entry not in frame.index or frame.loc[entry, "adj_close"] <= 0:
            continue
        if exit_session in frame.index:
            result[symbol] = float(frame.loc[exit_session, "adj_close"] / frame.loc[entry, "adj_close"] - 1)
        elif frame.attrs.get("entity_id"):
            info = historical_pit.exit_value(frame, frame.attrs["entity_id"], entry, exit_session)
            if info["value"] is not None:
                result[symbol] = float(info["value"] / frame.loc[entry, "adj_close"] - 1)
    return result


def _floats(date: str) -> dict[str, float]:
    audit = pd.read_csv(QUARTERLY_AUDIT)
    prior = audit[audit.as_of <= date]
    if prior.empty:
        return {}
    rows = prior[prior.as_of == prior.as_of.max()]
    return {row.symbol: float(row.public_float_usd) for row in rows.itertuples()
            if pd.notna(row.public_float_usd) and row.public_float_usd > 0}


def _plausible(value) -> bool:
    return value is not None and not pd.isna(value) and MIN_WEIGHT_USD <= float(value) <= MAX_WEIGHT_USD


def weights(table: pd.DataFrame, floats: dict[str, float]) -> tuple[dict[str, float], int]:
    """Pesos por capitalización robustos a errores de unidad XBRL.

    Se usa el *public float* SEC (disponible también para miembros sin precio)
    si es plausible y, cuando hay capitalización calculada, coherente con ella;
    si no, la capitalización plausible. Devuelve los pesos y cuántos miembros
    quedan sin peso válido.
    """
    result, dropped = {}, 0
    caps = table["market_cap"] if "market_cap" in table else pd.Series(dtype=float)
    for symbol in table.index:
        free, cap = floats.get(symbol), caps.get(symbol)
        if free is not None and _plausible(free) and (not _plausible(cap) or 0.2 <= free / float(cap) <= 1.5):
            result[symbol] = float(free)
        elif _plausible(cap):
            result[symbol] = float(cap)
        else:
            dropped += 1
    return result, dropped


def benchmarks_by_period(tables: dict[str, pd.DataFrame], manifest: dict) -> pd.DataFrame:
    calendar = xcals.get_calendar("XNYS")
    dates = manifest["dates"]
    boundaries = [*dates, manifest["end"]]
    spy = storage.get_prices("SPY")["adj_close"]
    rows = []
    for date, following in zip(dates, boundaries[1:], strict=True):
        table = tables[date]
        signal = calendar.date_to_session(pd.Timestamp(date), direction="previous")
        entry = calendar.next_session(signal)
        exit_session = calendar.date_to_session(pd.Timestamp(following), direction="next")
        eligible = table.index[table["composite_score"].notna() & (table["score_coverage"] >= MIN_COVERAGE)]
        priced = table.index[table["price_source"].notna()].tolist()
        returns = _returns(priced, date, entry, exit_session)
        eligible_returns = pd.Series({s: returns[s] for s in eligible if s in returns}, dtype=float)
        member_weights, dropped = weights(table, _floats(date))
        weighted = [s for s in eligible_returns.index if s in member_weights]
        cap_weighted = float(sum(member_weights[s] * eligible_returns[s] for s in weighted) /
                             sum(member_weights[s] for s in weighted)) if weighted else np.nan
        spy_return = float(spy.loc[exit_session] / spy.loc[entry] - 1)
        covered = [s for s in returns if s in member_weights]
        total_weight = sum(member_weights.values())
        covered_weight = sum(member_weights[s] for s in covered)
        share = covered_weight / total_weight if total_weight else np.nan
        covered_return = sum(member_weights[s] * returns[s] for s in covered) / covered_weight \
            if covered_weight else np.nan
        implied = (spy_return - share * covered_return) / (1 - share) if share < 0.98 else np.nan
        all_returns = pd.Series(returns, dtype=float)
        n_members, n_covered = len(table), len(all_returns)
        low, high = (all_returns.quantile(0.1), all_returns.quantile(0.9)) if n_covered else (np.nan, np.nan)
        mean_covered = float(all_returns.mean()) if n_covered else np.nan
        rows.append({
            "fecha": date, "entrada": entry.date().isoformat(), "salida": exit_session.date().isoformat(),
            "spy": spy_return, "universo_elegible_ew": float(eligible_returns.mean()) if len(eligible_returns) else np.nan,
            "universo_elegible_cap": cap_weighted,
            "miembros": n_members, "miembros_con_retorno": n_covered,
            "cubiertos_ew": mean_covered,
            "peso_cubierto": share, "cubiertos_ponderados": covered_return, "excluidos_implicito": implied,
            "miembros_sin_peso_valido": dropped,
            "universo_completo_ew_cota_baja": (n_covered * mean_covered + (n_members - n_covered) * low) / n_members,
            "universo_completo_ew_cota_alta": (n_covered * mean_covered + (n_members - n_covered) * high) / n_members,
        })
    return pd.DataFrame(rows)


def _compound(series: pd.Series) -> float:
    clean = series.dropna()
    return float((1 + clean).prod() - 1) if len(clean) else np.nan


def summarize(report: dict, coverage: pd.DataFrame, benchmarks: pd.DataFrame, output: Path) -> dict:
    v1 = {top: pd.read_csv(output / f"v1-top{top}-periods.csv") for top in (10, 20)}
    merged = benchmarks.copy()
    for top, periods in v1.items():
        merged = merged.merge(periods[["fecha", "retorno"]].rename(columns={"retorno": f"v1_top{top}"}),
                              on="fecha", how="left")
    executed = merged.dropna(subset=["v1_top20"])
    conclusive_dates = set(coverage.loc[coverage.concluyente, "fecha"])
    conclusive = executed[executed.fecha.isin(conclusive_dates)]
    columns = ["v1_top10", "v1_top20", "spy", "universo_elegible_ew", "universo_elegible_cap", "cubiertos_ponderados",
               "excluidos_implicito", "universo_completo_ew_cota_baja", "universo_completo_ew_cota_alta"]
    years = len(executed) / 4
    return {
        "periodos_previstos": len(benchmarks), "periodos_ejecutados_v1_top20": len(executed),
        "periodos_concluyentes": len(conclusive),
        "compuesto_periodos_ejecutados": {c: _compound(executed[c]) for c in columns},
        "anualizado_periodos_ejecutados": {c: (1 + _compound(executed[c])) ** (1 / years) - 1 if years else None
                                           for c in columns},
        "compuesto_periodos_concluyentes": {c: _compound(conclusive[c]) for c in columns},
        "exceso_medio_trimestral_top20_vs_spy": float((executed.v1_top20 - executed.spy).mean()),
        "exceso_medio_trimestral_top20_vs_universo_ew": float((executed.v1_top20 - executed.universo_elegible_ew).mean()),
        "trimestres_top20_supera_spy": int((executed.v1_top20 > executed.spy).sum()),
        "excluidos_vs_cubiertos_medio_trimestral": float((executed.excluidos_implicito - executed.cubiertos_ponderados).mean()),
        # El residual SPY - cubiertos se divide por el peso excluido: cualquier
        # error de los pesos proxy se amplifica por este factor.
        "desfase_medio_trimestral_cubiertos_vs_spy": float((executed.cubiertos_ponderados - executed.spy).mean()),
        "amplificacion_media_residual": float((1 / (1 - executed.peso_cubierto)).mean()),
        "cobertura_media_precio_auditoria": float(coverage.cobertura_precio_auditoria.mean()),
        "cobertura_media_elegible": float(coverage.cobertura_elegible.mean()),
    }


def run(cache: Path = CACHE, output: Path = OUTPUT, *, analysis_only: bool = False) -> dict:
    if analysis_only:
        # Reutiliza rankings y backtests ya congelados; solo rehace el análisis.
        manifest = json.loads((cache / "manifest.json").read_text(encoding="utf-8"))
        report = json.loads((output / "audit.json").read_text(encoding="utf-8"))
    else:
        manifest = fua.prepare(cache, start=START, stop=STOP, extra_sources=extra_sources())
        report = fua.evaluate(cache, output)
    tables = {date: pd.read_csv(cache / f"ranking-{date}.csv", index_col=0) for date in manifest["dates"]}
    executed = set(pd.read_csv(output / "v2-top20-periods.csv").fecha)
    original_db = config.DB_PATH
    config.DB_PATH = cache / "snapshot.db"
    try:
        coverage = coverage_by_rebalance(tables, executed)
        benchmarks = benchmarks_by_period(tables, manifest)
    finally:
        config.DB_PATH = original_db
    coverage.to_csv(output / "coverage-by-rebalance.csv", index=False)
    benchmarks.to_csv(output / "benchmarks-by-period.csv", index=False)
    report["historical_validation"] = {
        "issue": 33, "config": {"start": START, "stop_exclusive": STOP, "weights": scoring.DEFAULT_WEIGHTS,
                                "min_coverage": MIN_COVERAGE, "min_universe_coverage": MIN_UNIVERSE,
                                "conclusive_accredited_price_coverage": CONCLUSIVE_ACCREDITED},
        "summary": summarize(report, coverage, benchmarks, output),
        "analysis_sha256": fs.content_hash(Path(__file__)),
        "artifacts": {p.name: fs.content_hash(p) for p in output.glob("*.csv")}}
    fua._save(output / "audit.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=CACHE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--analysis-only", action="store_true",
                        help="Rehace solo el análisis sobre rankings y backtests ya congelados")
    args = parser.parse_args()
    report = run(args.cache, args.output, analysis_only=args.analysis_only)
    print(json.dumps(fs._json_safe(report["historical_validation"]), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
