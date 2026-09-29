"""Experimento preregistrado R3 E6 (issue #36), con la variante de ventana de riesgo del #37.

El control es el Composite vigente sobre los rankings congelados de la
revalidación del #35 (capa acreditada + #38, 2010-01-02 → 2025-10-02). Las
variantes recalculan la puntuación sobre **esas mismas tablas**, con la misma
maquinaria de ``scoring`` y el **mismo conjunto de elegibles del control**, de
modo que fechas, universo, costes y rebalanceos ejecutados son idénticos:

- ``e6a_calidad_persistente``: Calidad = las cuatro métricas vigentes más la
  persistencia (fracción de años positivos y dispersión del ROIC, con al menos
  tres ejercicios); Valor = los tres múltiplos vigentes más la brecha entre el
  crecimiento histórico del FCF y el implícito en el precio (reverse DCF).
- ``e6b_riesgo_756``: ``volatility`` y ``max_drawdown`` sobre las últimas 756
  sesiones de la misma serie acreditada, en vez de toda la serie disponible.

La especificación se escribe con hash en docs/r3-e6-experiment/ y en la tabla
``experiments`` antes de ejecutar ningún backtest. No toca la prueba ciega.
"""

import argparse
import hashlib
import json
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from scipy import stats

from . import academic_factors as af
from . import config, edgar, historical_pit, research_lab, risk, scoring, screener_asof, stats_rigor
from . import factor_stability as fs
from . import historical_revalidation as hr
from . import portfolio_backtest as v2
from . import variant_validation as vv

ISSUE = 36
SOURCE_VARIANT = "acreditado-38"
OUTPUT = config.BASE_DIR / "docs" / "r3-e6-experiment"
WORK = config.DATA_DIR / "r3_e6"
RISK_WINDOW = 756  # sesiones (#37); 757 cierres
MIN_PERSISTENCE_YEARS = 3
FULL = ("2011-07-02", "2025-10-02")
WINDOWS = {"completa_2011_2025": FULL, "2011_2015": ("2011-07-02", "2016-01-02"),
           "2016_2020": ("2016-01-02", "2021-01-02"), "2021_2025": ("2021-01-02", "2025-10-02")}
SUB_WINDOWS = ("2011_2015", "2016_2020", "2021_2025")
TOP = (20, 10)  # Top-20 principal (#12, #35); Top-10 secundario
PBO_START = "2011-10-02"  # 56 trimestres completos, 8 bloques de 7 sin recortar
PRIOR_TRIALS = 24 + 2  # #12 (24 configuraciones V1) + #23 rotación (2 umbrales)
VARIANTS = ("e6a_calidad_persistente", "e6b_riesgo_756")
NAMES = ("control_composite", *VARIANTS)

SPEC = {
    "issue": ISSUE, "linked_issue": 37, "stage": "RESEARCH",
    "hypothesis": ("Puntuar la persistencia de la calidad y el precio frente a expectativas (E6a), o medir "
                   "el riesgo en una ventana común de 3 años (E6b), mejora la cartera V2 Top-20 frente al "
                   "Composite vigente sin empeorar su riesgo de cola."),
    "control": {"name": "control_composite", "weights": scoring.DEFAULT_WEIGHTS,
                "score_metrics": scoring.SCORE_METRICS},
    "variants": {
        "e6a_calidad_persistente": {
            "weights": scoring.DEFAULT_WEIGHTS,
            "added_to_quality": {"quality_persistence_score": "higher_is_better",
                                 "roic_persistence_std": "lower_is_better"},
            "added_to_value": {"expectations_gap": "higher_is_better"},
            "validity": f"métricas de persistencia solo con roic_years >= {MIN_PERSISTENCE_YEARS}",
            "note": "Cada bloque promedia sus percentiles sectoriales con igual peso, como el control."},
        "e6b_riesgo_756": {
            "weights": scoring.DEFAULT_WEIGHTS,
            "risk_window_sessions": RISK_WINDOW,
            "recomputed": ["volatility", "max_drawdown"],
            "note": "Misma serie acreditada y misma función risk.compute_risk_metrics sobre los últimos 757 cierres."},
    },
    "sample": {"rankings": f"data/revalidation_2011_2025/{SOURCE_VARIANT}", "start": "2010-01-02",
               "end": "2025-10-02", "months": 3, "invested_from": FULL[0], "windows": WINDOWS},
    "eligibility": "el conjunto elegible (composite y score_coverage >= 0,70) es el del control en todas las variantes",
    "engine": {"motor": "V2", "mode": "validation", "top_n": list(TOP), "initial_capital": 100000.,
               "commission_usd": 1., "spread_bps": 10., "max_symbols": None},
    "metrics": ["CAGR neto", "ES 95/99 diario", "drawdown máximo", "rotación", "costes", "beta SPY",
                "FF5+Mom con HAC (#11) sobre retornos trimestrales", "PBO (CSCV, 8 bloques, 56 trimestres)",
                "DSR con todas las configuraciones documentadas"],
    "decision_rule": {
        "primary": "V2 Top-20, serie 2011-07 → 2025-10",
        "adoptar": ("(a) CAGR neto >= control + 1,0 pp; (b) mejor CAGR que el control en al menos 2 de 3 ventanas "
                    "(2011-2015, 2016-2020, 2021-2025); (c) ES 95 % no peor en más de un 10 % relativo y drawdown "
                    "máximo no peor en más de 3 pp; (d) diferencia trimestral frente al control con p HAC "
                    "unilateral < 0,05 tras Holm sobre las 2 variantes y DSR > 0,95"),
        "pendiente": "cumple (a), (b) y (c) pero no (d): hipótesis pendiente de validación prospectiva",
        "descartar": "no cumple (a), (b) o (c)",
        "default_model": "El modelo por defecto no cambia salvo 'adoptar'.",
    },
    "multiple_testing": {"holm_over": 2, "dsr_trials": PRIOR_TRIALS + 3,
                         "prior_trials": "24 configuraciones del #12 + 2 umbrales de rotación del #23"},
    "blind_validation": "no se lee ni se modifica",
}


def spec_hash() -> str:
    return hashlib.sha256(json.dumps(SPEC, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def preregister() -> dict:
    """Escribe la especificación con hash y la registra en ``experiments`` antes de ejecutar."""
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / "preregistro.json"
    digest = spec_hash()
    if path.exists():
        previous = json.loads(path.read_text(encoding="utf-8"))
        if previous["sha256"] != digest:
            raise ValueError("La especificación cambió después del preregistro.")
        return previous
    ids = {}
    for name in NAMES:
        ids[name] = research_lab.log_experiment(
            f"r3_e6:{name}", "RESEARCH", True, family="r3_e6", universe="S&P 500 acreditado (fja05680)",
            weights=scoring.DEFAULT_WEIGHTS, n_positions=20, rebalance="trimestral día 2",
            cost_model="V2: 1 USD + 10 pb", is_start=FULL[0], is_end=FULL[1],
            notes=f"Preregistro #36, sha256 {digest}; sin resultados")
    record = {"sha256": digest, "spec": SPEC, "experiment_ids": ids}
    fua_save(path, record)
    return record


def fua_save(path: Path, value: dict) -> None:
    path.write_text(json.dumps(fs._json_safe(value), ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")


# --- Datos derivados de la variante E6b ---------------------------------------------------------

def _context() -> ExitStack:
    variant = hr.VARIANTS[SOURCE_VARIANT]
    stack = ExitStack()
    stack.enter_context(historical_pit.accredited_periods(*variant.periods))
    stack.enter_context(edgar.fiscal_alignment(variant.fiscal_alignment))
    stack.enter_context(patch.object(config, "DB_PATH", variant.cache / "snapshot.db"))
    return stack


def _manifest() -> dict:
    return json.loads((hr.VARIANTS[SOURCE_VARIANT].cache / "manifest.json").read_text(encoding="utf-8"))


def _table(date: str) -> pd.DataFrame:
    return pd.read_csv(hr.VARIANTS[SOURCE_VARIANT].cache / f"ranking-{date}.csv", index_col=0)


def risk_window_metrics(date: str, table: pd.DataFrame) -> pd.DataFrame:
    """Volatilidad y drawdown sobre las últimas 756 sesiones de la serie que usó el ranking.

    Devuelve también las métricas de toda la serie para comprobar que se
    reproduce exactamente la tabla congelada.
    """
    as_of = pd.Timestamp(date)
    rows = []
    for symbol, row in table.iterrows():
        entity_id = row.get("entity_id")
        entity_id = entity_id if isinstance(entity_id, str) else None
        prices = screener_asof._price_history_as_of(symbol, as_of, entity_id=entity_id) if entity_id else pd.DataFrame()
        if prices.empty:
            rows.append({"symbol": symbol})
            continue
        full = risk.compute_risk_metrics(prices)
        window = risk.compute_risk_metrics(prices.tail(RISK_WINDOW + 1))
        rows.append({"symbol": symbol, "sessions": len(prices),
                     "volatility_full": full["volatility"], "max_drawdown_full": full["max_drawdown"],
                     "volatility": window["volatility"], "max_drawdown": window["max_drawdown"]})
    columns = ["sessions", "volatility_full", "max_drawdown_full", "volatility", "max_drawdown"]
    return pd.DataFrame(rows).set_index("symbol").reindex(columns=columns)


def prepare_risk_window() -> dict:
    manifest = _manifest()
    WORK.mkdir(parents=True, exist_ok=True)
    report = {}
    with _context():
        for date in manifest["dates"]:
            path = WORK / f"risk756-{date}.csv"
            if not path.exists():
                risk_window_metrics(date, _table(date)).to_csv(path)
            frame = pd.read_csv(path, index_col=0)
            table = _table(date).reindex(columns=["volatility", "max_drawdown"])
            common = frame.index.intersection(table.index)
            mismatch = int(sum(not np.isclose(frame.loc[s, f"{m}_full"], table.loc[s, m], equal_nan=True, rtol=1e-9)
                               for s in common for m in ("volatility", "max_drawdown")))
            report[date] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "reproduction_mismatches": mismatch}
            print(date, report[date], flush=True)
    fua_save(WORK / "risk756-manifest.json", report)
    if any(item["reproduction_mismatches"] for item in report.values()):
        raise ValueError("Las métricas de toda la serie no reproducen la tabla congelada.")
    return report


# --- Rescoring ------------------------------------------------------------------------------

def _control_eligible(table: pd.DataFrame) -> pd.Series:
    return table["composite_score"].notna() & (table["score_coverage"] >= hr.MIN_COVERAGE)


def _with_control_eligibility(scored: pd.DataFrame, control: pd.DataFrame) -> pd.DataFrame:
    eligible = _control_eligible(control).reindex(scored.index, fill_value=False)
    scored = scored.copy()
    scored.loc[~eligible, "composite_score"] = np.nan
    scored["score_coverage"] = control["score_coverage"].reindex(scored.index)
    return scored.sort_values("composite_score", ascending=False)


def rescore(table: pd.DataFrame, variant: str, date: str) -> pd.DataFrame:
    base = table.drop(columns=[c for c in table.columns if c.endswith("_pct") or c in
                               {"value_score", "quality_score", "momentum_score", "risk_score", "composite_score",
                                "metrics_available", "metrics_possible", "score_coverage"}])
    if variant == "control_composite":
        scored = scoring.build_scores(base, scoring.DEFAULT_WEIGHTS)
    elif variant == "e6a_calidad_persistente":
        base = base.copy()
        short = base["roic_years"].fillna(0) < MIN_PERSISTENCE_YEARS
        base.loc[short, ["quality_persistence_score", "roic_persistence_std"]] = np.nan
        metrics = {**scoring.SCORE_METRICS,
                   "quality": [*scoring.SCORE_METRICS["quality"], "quality_persistence_score", "roic_persistence_std"],
                   "value": [*scoring.SCORE_METRICS["value"], "expectations_gap"]}
        with (patch.dict(scoring.SCORE_METRICS, metrics),
              patch.object(scoring, "QUALITY_METRICS_HIGHER_BETTER",
                           [*scoring.QUALITY_METRICS_HIGHER_BETTER, "quality_persistence_score", "expectations_gap"]),
              patch.object(scoring, "RISK_METRICS_LOWER_BETTER",
                           [*scoring.RISK_METRICS_LOWER_BETTER, "roic_persistence_std"])):
            scored = scoring.build_scores(base, scoring.DEFAULT_WEIGHTS)
    elif variant == "e6b_riesgo_756":
        window = pd.read_csv(WORK / f"risk756-{date}.csv", index_col=0)
        base = base.copy()
        base["volatility"] = window["volatility"].reindex(base.index)
        base["max_drawdown"] = window["max_drawdown"].reindex(base.index)
        scored = scoring.build_scores(base, scoring.DEFAULT_WEIGHTS)
    else:
        raise ValueError(f"Variante no registrada: {variant}")
    return _with_control_eligibility(scored, table)


def check_control_reproduction() -> dict:
    """El control rescorado debe coincidir con el composite congelado de cada fecha."""
    result = {}
    for date in _manifest()["dates"]:
        table = _table(date)
        scored = rescore(table, "control_composite", date)
        diff = (scored["composite_score"] - table["composite_score"].reindex(scored.index)).abs()
        result[date] = float(diff.max(skipna=True)) if diff.notna().any() else 0.0
    if max(result.values()) > 1e-9:
        raise ValueError(f"El control rescorado no reproduce el composite congelado: {max(result.values())}")
    return result


# --- Ejecución ------------------------------------------------------------------------------

def run_variant(variant: str) -> dict:
    manifest = _manifest()
    output = OUTPUT / variant
    output.mkdir(parents=True, exist_ok=True)
    tables = {date: rescore(_table(date), variant, date) for date in manifest["dates"]}

    def cached_rank(date, weights=None, symbols=None, **kwargs):
        if set(symbols or []) != set(manifest["rankings"][date]["symbols"]):
            raise ValueError("El motor solicitó un universo diferente del congelado.")
        return {"table": tables[date].copy(), "universe_info": {"is_exact": True}}

    results = {}
    with _context(), patch.object(screener_asof, "build_ranking_as_of", cached_rank):
        for top in TOP:
            result = v2.run(manifest["start"], manifest["end"], months=3, top_n=top, max_symbols=None,
                            mode="validation", initial_capital=100000., commission_usd=1., spread_bps=10.)
            result["periods"].to_csv(output / f"v2-top{top}-periods.csv", index=False)
            nav = pd.DataFrame({"strategy": result["nav_curve"], "spy": result["nav_curve_spy"]})
            nav.to_csv(output / f"v2-top{top}-nav.csv", index_label="date")
            windows = {name: vv._window_metrics(result, start, end) for name, (start, end) in WINDOWS.items()}
            results[f"top{top}"] = {"windows": windows, "skipped": result["skipped"],
                                    "exit_events": result.get("exit_events", []),
                                    "strict_result": result.get("strict_result", True),
                                    "executed": result["periods"]["fecha"].tolist()}
    fua_save(output / "result.json", results)
    return results


def quarterly_returns(variant: str, top: int = 20) -> pd.DataFrame:
    periods = pd.read_csv(OUTPUT / variant / f"v2-top{top}-periods.csv")
    nav = pd.read_csv(OUTPUT / variant / f"v2-top{top}-nav.csv", index_col=0, parse_dates=True)
    exits = [pd.Timestamp(day) for day in periods.hasta]
    starts = [nav.index[0], *exits[:-1]]
    return pd.DataFrame({"fecha": periods.fecha, "hasta": periods.hasta,
                         "retorno": [float(nav["strategy"].asof(e) / nav["strategy"].asof(s) - 1)
                                     for s, e in zip(starts, exits, strict=True)],
                         "spy": [float(nav["spy"].asof(e) / nav["spy"].asof(s) - 1)
                                 for s, e in zip(starts, exits, strict=True)]})


def _paired_test(variant: pd.DataFrame, control: pd.DataFrame) -> dict:
    merged = variant.merge(control, on=["fecha", "hasta"], suffixes=("", "_control"))
    diff = (merged["retorno"] - merged["retorno_control"]).to_numpy()
    fit = af._ols(diff, np.ones((len(diff), 1)), ["diferencia"])
    t = fit["t_stat"]["diferencia"]
    return {"n": len(diff), "media_trimestral": float(diff.mean()), "t_hac": float(t),
            "p_unilateral": float(1 - stats.t.cdf(t, df=len(diff) - 1)), "hac_lags": fit["hac_lags"]}


def analyze() -> dict:
    names = list(NAMES)
    results = {name: json.loads((OUTPUT / name / "result.json").read_text(encoding="utf-8")) for name in names}
    executed = {name: tuple(results[name]["top20"]["executed"]) for name in names}
    if len(set(executed.values())) != 1:
        raise ValueError("Control y variantes no ejecutaron los mismos rebalanceos.")
    returns = {name: quarterly_returns(name) for name in names}
    factors = af.fetch_ff_factors()
    analysis: dict = {"spec_sha256": spec_hash(), "rebalanceos_ejecutados": len(executed["control_composite"])}
    for name in names:
        q = returns[name]
        full = q[q.fecha >= FULL[0]]
        item = {"ventanas": {top: results[name][top]["windows"] for top in ("top20", "top10")},
                "estricto": results[name]["top20"]["strict_result"],
                "factores": af.regress_returns_on_factors(full[["fecha", "hasta", "retorno"]], factors),
                "sharpe_trimestral": stats_rigor.probabilistic_sharpe_ratio_from_returns(full["retorno"], 4, 0.04)}
        if name != "control_composite":
            item["frente_al_control"] = _paired_test(full, returns["control_composite"])
        analysis[name] = item
    # Holm sobre las dos variantes (unilateral).
    variants = list(VARIANTS)
    ordered = sorted(variants, key=lambda n: analysis[n]["frente_al_control"]["p_unilateral"])
    running = 0.0
    for rank, name in enumerate(ordered):
        adjusted = min(1.0, (len(ordered) - rank) * analysis[name]["frente_al_control"]["p_unilateral"])
        running = max(running, adjusted)
        analysis[name]["frente_al_control"]["p_holm"] = running
    # PBO sobre la familia de este experimento y DSR con todas las configuraciones documentadas.
    matrix = pd.concat({n: returns[n].set_index(pd.to_datetime(returns[n].hasta))["retorno"]
                        for n in names}, axis=1)
    matrix = matrix[[pd.Timestamp(f) >= pd.Timestamp(PBO_START) for f in returns["control_composite"].fecha]]
    excess = matrix - ((1.04) ** .25 - 1)
    analysis["pbo"] = stats_rigor.pbo_cscv(excess, n_splits=8) if len(matrix) % 8 == 0 else {
        "error": f"{len(matrix)} trimestres no divisibles en 8 bloques"}
    prior = json.loads((config.BASE_DIR / "docs" / "overfitting-audit" / "audit.json").read_text(encoding="utf-8"))
    prior_sharpes = [s["sharpe_anualizado"] for s in prior["including_cost_sensitivity"]["trial_statistics"].values()]
    sharpes = prior_sharpes + [analysis[n]["sharpe_trimestral"]["sharpe_anualizado"] for n in names]
    for name in variants:
        stat = analysis[name]["sharpe_trimestral"]
        analysis[name]["dsr"] = stats_rigor.deflated_sharpe_ratio(
            selected_sharpe=stat["sharpe_anualizado"], trial_sharpes=sharpes, n_obs=stat["n"],
            periods_per_year=4, skew=stat["skew"], kurtosis=stat["kurtosis"], n_trials=PRIOR_TRIALS + 3)
    analysis["decisiones"] = {name: decide(analysis, name) for name in variants}
    fua_save(OUTPUT / "analysis.json", analysis)
    return analysis


def decide(analysis: dict, name: str) -> dict:
    """Regla preregistrada (SPEC['decision_rule'])."""
    control = analysis["control_composite"]["ventanas"]["top20"]
    variant = analysis[name]["ventanas"]["top20"]
    full_c, full_v = control["completa_2011_2025"], variant["completa_2011_2025"]
    a = full_v["cagr_net"] >= full_c["cagr_net"] + 0.01
    b = sum(variant[w]["cagr_net"] > control[w]["cagr_net"] for w in SUB_WINDOWS) >= 2
    c = full_v["es_95"] <= full_c["es_95"] * 1.10 and full_v["drawdown"] >= full_c["drawdown"] - 0.03
    d = analysis[name]["frente_al_control"]["p_holm"] < 0.05 and analysis[name]["dsr"]["dsr"] > 0.95
    decision = "adoptar" if a and b and c and d else "pendiente_validacion_prospectiva" if a and b and c else "descartar"
    return {"a_cagr_mas_1pp": bool(a), "b_mejor_en_2_de_3_ventanas": bool(b), "c_riesgo_no_peor": bool(c),
            "d_significativa": bool(d), "decision": decision}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preregister", action="store_true")
    parser.add_argument("--prepare-risk", action="store_true")
    parser.add_argument("--check-control", action="store_true")
    parser.add_argument("--run", choices=NAMES)
    parser.add_argument("--analyze", action="store_true")
    args = parser.parse_args()
    if args.preregister:
        print(json.dumps({"sha256": preregister()["sha256"]}))
    if args.prepare_risk:
        prepare_risk_window()
    if args.check_control:
        print(json.dumps({"max_diff": max(check_control_reproduction().values())}))
    if args.run:
        record = json.loads((OUTPUT / "preregistro.json").read_text(encoding="utf-8"))
        if record["sha256"] != spec_hash():
            raise ValueError("Especificación distinta de la preregistrada.")
        print(json.dumps(fs._json_safe(run_variant(args.run)["top20"]["windows"]), ensure_ascii=False)[:2000])
    if args.analyze:
        print(json.dumps(fs._json_safe(analyze()["decisiones"]), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
