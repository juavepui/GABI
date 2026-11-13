"""Prueba preregistrada de capacidad predictiva en sección cruzada (issue #40).

¿Ordena el Composite a las empresas del S&P 500 según su rentabilidad del
trimestre siguiente mejor que el azar? Usa ~350-450 empresas por trimestre, así
que tiene mucha más potencia que comparar el Top-20 con el SPY (#39).

Datos: rankings congelados de la variante principal del #35 (capa acreditada +
#38) y los mismos elegibles (composite y cobertura >= 70 %). El retorno
siguiente usa las series acreditadas y la misma regla de salida que el
backtest (``historical_validation._returns``: evento terminal o último precio
no estricto). La especificación se guarda con hash antes de calcular nada.
"""

import argparse
import hashlib
import json
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import exchange_calendars as xcals
import numpy as np
import pandas as pd
from scipy import stats

from . import academic_factors as af
from . import config, edgar, historical_pit, research_lab, scoring
from . import factor_stability as fs
from . import historical_revalidation as hr
from . import historical_validation as hv

ISSUE = 40
SOURCE_VARIANT = "acreditado-38"
FIRST, LAST = "2011-07-02", "2025-07-02"  # 57 rebalanceos invertidos, como el V2 del #35
OUTPUT = config.BASE_DIR / "docs" / "cross-section-test"
WORK = config.DATA_DIR / "cross_section_test"
WINDOWS = {"2011_2015": ("2011-07-02", "2016-01-02"), "2016_2020": ("2016-01-02", "2021-01-02"),
           "2021_2025": ("2021-01-02", "2025-10-02")}
BLOCKS = ("value_score", "quality_score", "momentum_score", "risk_score")

SPEC = {
    "issue": ISSUE, "stage": "RESEARCH",
    "hypothesis": "El Composite vigente predice la rentabilidad relativa del trimestre siguiente entre los "
                  "miembros elegibles del S&P 500 (IC medio > 0).",
    "data": {"rankings": f"data/revalidation_2011_2025/{SOURCE_VARIANT}", "first": FIRST, "last": LAST,
             "eligible": "composite_score no vacío y score_coverage >= 0,70 (el mismo que el backtest)",
             "forward_return": "de la sesión siguiente a la señal a la primera sesión tras +3 meses; serie acreditada; "
                               "salida por evento terminal o último precio no estricto (como el backtest)",
             "weights": scoring.DEFAULT_WEIGHTS},
    "primary": {"test": "IC de Spearman trimestral (composite_score vs retorno siguiente); media de los "
                        "trimestres; error estándar Newey-West (retardos automáticos de academic_factors._ols)",
                "hypothesis": "unilateral, IC medio > 0", "alpha": 0.05},
    "secondary": {"tests": ["Fama-MacBeth: pendiente del percentil del composite (0-1) con dummies de sector y "
                            "log(capitalización); t Newey-West de la pendiente media",
                            "Diferencia de quintiles Q5 - Q1 equiponderada por trimestre; t Newey-West"],
                  "correction": "Holm sobre las 2 secundarias, unilateral, alpha 0,05"},
    "descriptive": ["Top-20 frente al universo elegible (ya visto en #39, no confirmatorio)",
                    "IC de cada bloque (valor, calidad, momentum, riesgo)", "IC por ventana 2011-15, 2016-20, 2021-25",
                    "medias de los cinco quintiles", "proporción de trimestres con IC > 0"],
    "decision": {"capacidad_predictiva_confirmada": "principal p < 0,05 y las dos secundarias con estimación > 0",
                 "capacidad_predictiva_robusta": "lo anterior y las dos secundarias significativas tras Holm",
                 "indicio_no_concluyente": "IC medio > 0 con p >= 0,05",
                 "sin_capacidad_predictiva": "IC medio <= 0"},
    "model_changes": "ninguno; la prueba ciega no se lee ni se modifica",
}


def spec_hash() -> str:
    return hashlib.sha256(json.dumps(SPEC, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _save(path, value) -> None:
    path.write_text(json.dumps(fs._json_safe(value), ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")


def preregister() -> dict:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / "preregistro.json"
    digest = spec_hash()
    if path.exists():
        record = json.loads(path.read_text(encoding="utf-8"))
        if record["sha256"] != digest:
            raise ValueError("La especificación cambió después del preregistro.")
        return record
    experiment = research_lab.log_experiment(
        "cross_section_ic", "RESEARCH", True, family="stat_2", universe="S&P 500 acreditado (fja05680)",
        weights=scoring.DEFAULT_WEIGHTS, rebalance="trimestral día 2", is_start=FIRST, is_end=LAST,
        notes=f"Preregistro #40, sha256 {digest}; sin resultados")
    record = {"sha256": digest, "spec": SPEC, "experiment_id": experiment}
    _save(path, record)
    return record


def _context() -> ExitStack:
    variant = hr.VARIANTS[SOURCE_VARIANT]
    stack = ExitStack()
    stack.enter_context(historical_pit.accredited_periods(*variant.periods))
    stack.enter_context(edgar.fiscal_alignment(variant.fiscal_alignment))
    stack.enter_context(patch.object(config, "DB_PATH", variant.cache / "snapshot.db"))
    return stack


def dates() -> list[str]:
    manifest = json.loads((hr.VARIANTS[SOURCE_VARIANT].cache / "manifest.json").read_text(encoding="utf-8"))
    return [d for d in manifest["dates"] if FIRST <= d <= LAST]


def forward_returns() -> dict:
    """Retorno del trimestre siguiente de cada elegible (datos, no resultados)."""
    WORK.mkdir(parents=True, exist_ok=True)
    calendar = xcals.get_calendar("XNYS")
    report = {}
    with _context():
        for date in dates():
            path = WORK / f"forward-{date}.csv"
            if not path.exists():
                table = pd.read_csv(hr.VARIANTS[SOURCE_VARIANT].cache / f"ranking-{date}.csv", index_col=0)
                eligible = table.index[table["composite_score"].notna() & (table["score_coverage"] >= 0.7)]
                signal = calendar.date_to_session(pd.Timestamp(date), direction="previous")
                entry = calendar.next_session(signal)
                exit_session = calendar.date_to_session(pd.Timestamp(date) + pd.DateOffset(months=3), direction="next")
                returns = hv._returns(list(eligible), date, entry, exit_session)
                pd.DataFrame({"retorno": pd.Series(returns, dtype=float)}).reindex(eligible).to_csv(path)
            frame = pd.read_csv(path, index_col=0)
            report[date] = {"elegibles": len(frame), "con_retorno": int(frame.retorno.notna().sum()),
                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            print(date, report[date], flush=True)
    _save(WORK / "forward-manifest.json", report)
    return report


def _nw(series: pd.Series) -> dict:
    values = series.dropna().to_numpy(dtype=float)
    fit = af._ols(values, np.ones((len(values), 1)), ["media"])
    t = float(fit["t_stat"]["media"])
    return {"n": len(values), "media": float(values.mean()), "t_nw": t, "hac_lags": fit["hac_lags"],
            "p_unilateral": float(1 - stats.t.cdf(t, df=len(values) - 1))}


def quarter_panel(date: str) -> pd.DataFrame:
    table = pd.read_csv(hr.VARIANTS[SOURCE_VARIANT].cache / f"ranking-{date}.csv", index_col=0)
    forward = pd.read_csv(WORK / f"forward-{date}.csv", index_col=0)
    frame = table.loc[forward.index, ["composite_score", "sector", "market_cap", *BLOCKS]].join(forward)
    return frame.dropna(subset=["composite_score", "retorno"])


def fama_macbeth_slope(frame: pd.DataFrame) -> float | None:
    data = frame.dropna(subset=["market_cap"])
    data = data[data.market_cap > 0]
    if len(data) < 30:
        return None
    rank = data.composite_score.rank(pct=True)
    sectors = pd.get_dummies(data.sector.fillna("desconocido"), drop_first=True, dtype=float)
    X = np.column_stack([np.ones(len(data)), rank, np.log(data.market_cap), sectors.to_numpy()])
    beta, *_ = np.linalg.lstsq(X, data.retorno.to_numpy(dtype=float), rcond=None)
    return float(beta[1])


def analyze() -> dict:
    record = preregister()
    rows = []
    for date in dates():
        frame = quarter_panel(date)
        quintile = pd.qcut(frame.composite_score.rank(method="first"), 5, labels=False) + 1
        top20 = frame.nlargest(20, "composite_score")
        row = {"fecha": date, "n": len(frame),
               "ic": float(stats.spearmanr(frame.composite_score, frame.retorno).statistic),
               "fm_pendiente": fama_macbeth_slope(frame),
               **{f"q{q}": float(frame.retorno[quintile == q].mean()) for q in range(1, 6)},
               "top20_menos_universo": float(top20.retorno.mean() - frame.retorno.mean())}
        for block in BLOCKS:
            valid = frame.dropna(subset=[block])
            row[f"ic_{block}"] = float(stats.spearmanr(valid[block], valid.retorno).statistic) if len(valid) > 30 else None
        rows.append(row)
    panel = pd.DataFrame(rows)
    panel["q5_menos_q1"] = panel.q5 - panel.q1
    OUTPUT.mkdir(parents=True, exist_ok=True)
    panel.to_csv(OUTPUT / "por-trimestre.csv", index=False)
    primary = _nw(panel.ic)
    secondary = {"fama_macbeth": _nw(panel.fm_pendiente), "q5_menos_q1": _nw(panel.q5_menos_q1)}
    ordered = sorted(secondary, key=lambda k: secondary[k]["p_unilateral"])
    running = 0.0
    for rank, key in enumerate(ordered):
        running = max(running, min(1.0, (len(ordered) - rank) * secondary[key]["p_unilateral"]))
        secondary[key]["p_holm"] = running
    if primary["media"] <= 0:
        decision = "sin_capacidad_predictiva"
    elif primary["p_unilateral"] >= 0.05:
        decision = "indicio_no_concluyente"
    elif all(v["media"] > 0 for v in secondary.values()):
        decision = ("capacidad_predictiva_robusta" if all(v["p_holm"] < 0.05 for v in secondary.values())
                    else "capacidad_predictiva_confirmada")
    else:
        decision = "principal_significativa_sin_coherencia_secundaria"
    descriptive = {
        "trimestres_ic_positivo": int((panel.ic > 0).sum()),
        "top20_menos_universo": _nw(panel.top20_menos_universo),
        "quintiles_media_trimestral": {f"q{q}": float(panel[f"q{q}"].mean()) for q in range(1, 6)},
        "ic_por_bloque": {block: _nw(panel[f"ic_{block}"]) for block in BLOCKS},
        "ic_por_ventana": {name: _nw(panel[(panel.fecha >= a) & (panel.fecha < b)].ic)
                           for name, (a, b) in WINDOWS.items()},
    }
    result = {"spec_sha256": record["sha256"], "trimestres": len(panel), "empresas_media": float(panel.n.mean()),
              "principal_ic": primary, "secundarias": secondary, "descriptivas": descriptive, "decision": decision,
              "code_sha256": fs.content_hash(Path(__file__))}
    _save(OUTPUT / "resultado.json", result)
    research_lab.log_experiment(
        "cross_section_ic", "RESEARCH", True, family="stat_2", universe="S&P 500 acreditado (fja05680)",
        weights=scoring.DEFAULT_WEIGHTS, rebalance="trimestral día 2", is_start=FIRST, is_end=LAST,
        n_periods=len(panel), returns=pd.Series(panel.ic.values, index=panel.fecha.values),
        notes=f"Resultado #40 (serie = IC trimestral); preregistro sha256 {record['sha256']}; decisión {decision}",
        result={"principal": primary, "secundarias": secondary, "decision": decision})
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preregister", action="store_true")
    parser.add_argument("--forward-returns", action="store_true")
    parser.add_argument("--analyze", action="store_true")
    args = parser.parse_args()
    if args.preregister:
        print(json.dumps({"sha256": preregister()["sha256"]}))
    if args.forward_returns:
        forward_returns()
    if args.analyze:
        result = analyze()
        print(json.dumps(fs._json_safe({k: result[k] for k in ("principal_ic", "secundarias", "decision")}),
                         ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
