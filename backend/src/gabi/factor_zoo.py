"""STAT-5 (#48): mapa preregistrado de señales individuales de GABI."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from . import config, cross_section_test as cs, historical_revalidation as hr, scoring
from .tail_effect_test import _holm


OUTPUT = config.BASE_DIR / "docs" / "factor-zoo"
LOWER = set(scoring.VALUE_METRICS_LOWER_BETTER + scoring.RISK_METRICS_LOWER_BETTER)
SIGNALS = tuple((family, metric, "lower" if metric in LOWER else "higher")
                for family, metrics in scoring.SCORE_METRICS.items() for metric in metrics)
WINDOWS = cs.WINDOWS
SPEC = {
    "issue": 48,
    "stage": "RESEARCH_RETROSPECTIVE",
    "signals": [{"family": family, "metric": metric, "raw_expected": direction,
                 "tested_column": metric + "_pct", "tested_expected": "higher"}
                for family, metric, direction in SIGNALS],
    "selection": "exactamente las 13 métricas representativas de scoring.SCORE_METRICS; otras métricas correlacionadas excluidas antes del run",
    "data": "57 fechas, elegibles y retornos futuros congelados de #40; columna _pct orientada y sector-normalizada existente en ranking",
    "missing": "filas sin señal o retorno se excluyen; mínimo 30 pares por trimestre y 30 trimestres para inferencia; sin imputación",
    "primary": "IC Spearman trimestral por señal; media > 0 con t HAC Bartlett 3 retardos fijos sobre calendario trimestral (huecos conservan su posición) y p unilateral; Holm de 13 señales, alpha 0,05",
    "secondary": "ICIR=media/desviación temporal; proporción IC positivo; quintiles y deciles equiponderados, spreads extremos; Fama-MacBeth con sector y log-capitalización; ventanas fijas, sectores y terciles de tamaño descriptivos",
    "correlation": "media temporal de Spearman entre señales en elegibles con datos pareados, mínimo 30 por trimestre",
    "classification": {"sin_evidencia": "IC medio <= 0 o señal no evaluable",
                       "indicio": "IC medio > 0 y p Holm >= 0,05",
                       "requiere_OOS": "p Holm < 0,05 pero menos de 2/3 ventanas con IC positivo o menos de 2/3 terciles de tamaño positivos",
                       "robusta_retrospectivamente": "p Holm < 0,05 y al menos 2/3 ventanas y 2/3 terciles positivos; siempre requiere validación OOS independiente"},
    "model_changes": "ninguno; no seleccionar pesos por CAGR Top-N ni añadir automáticamente factores al Composite",
}


def spec_hash() -> str:
    return hashlib.sha256(json.dumps(SPEC, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _save(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def preregister() -> dict:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / "preregistro.json"
    if path.exists():
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("sha256") != spec_hash() or record.get("spec") != SPEC:
            raise ValueError("El preregistro #48 ha cambiado.")
        return record
    record = {"sha256": spec_hash(), "spec": SPEC}
    _save(path, record)
    return record


def _ic(frame: pd.DataFrame, column: str) -> float | None:
    valid = frame[[column, "retorno"]].replace([np.inf, -np.inf], np.nan).dropna()
    if len(valid) < 30 or valid[column].nunique() < 2 or valid.retorno.nunique() < 2:
        return None
    return float(stats.spearmanr(valid[column], valid.retorno).statistic)


def _hac_calendar(values: pd.Series) -> dict:
    """HAC de una media; los huecos no acortan el retardo trimestral."""
    array = values.to_numpy(dtype=float)
    observed = np.isfinite(array)
    n = int(observed.sum())
    if n < 30:
        raise ValueError("Se requieren al menos 30 trimestres evaluables.")
    mean = float(array[observed].mean())
    residual = np.where(observed, array - mean, 0.0)
    meat = float(residual @ residual)
    for lag in range(1, 4):
        meat += 2 * (1 - lag / 4) * float(residual[lag:] @ residual[:-lag])
    se = float(np.sqrt(max((n / (n - 1)) * meat / n**2, 0)))
    t = mean / se if se > 0 else float("nan")
    if not np.isfinite(t):
        raise ValueError("No se puede estimar el estadístico HAC.")
    return {"n": n, "media": mean, "se_hac": se, "t_hac": t,
            "p": float(stats.t.sf(t, df=n - 1)), "hac_lags": 3}


def _quarter(date: str) -> tuple[pd.DataFrame, dict]:
    ranking_path = hr.VARIANTS[cs.SOURCE_VARIANT].cache / f"ranking-{date}.csv"
    return_path = cs.WORK / f"forward-{date}.csv"
    ranking = pd.read_csv(ranking_path, index_col=0)
    forward = pd.read_csv(return_path, index_col=0)
    eligible = ranking.loc[ranking.composite_score.notna() & (ranking.score_coverage >= .70)]
    if set(eligible.index) != set(forward.index):
        raise ValueError(f"Universo del #40 distinto en {date}.")
    columns = ["sector", "market_cap", *[metric + "_pct" for _, metric, _ in SIGNALS]]
    missing = set(columns) - set(eligible.columns)
    if missing:
        raise ValueError(f"Faltan columnas de señales en {date}: {sorted(missing)}")
    frame = eligible[columns].join(forward[["retorno"]], validate="one_to_one")
    if frame.index.has_duplicates:
        raise ValueError(f"Símbolos duplicados en {date}.")
    return frame, {str(ranking_path.relative_to(config.BASE_DIR)): _hash(ranking_path),
                   str(return_path.relative_to(config.BASE_DIR)): _hash(return_path)}


def _signal_rows(frame: pd.DataFrame, date: str, metric: str) -> tuple[dict, list[dict], list[dict]]:
    column = metric + "_pct"
    valid = frame[[column, "retorno", "sector", "market_cap"]].replace([np.inf, -np.inf], np.nan)
    valid = valid.dropna(subset=[column, "retorno"]).sort_index()
    if len(valid) < 30 or valid[column].nunique() < 2:
        return {"fecha": date, "metric": metric, "n": len(valid), "ic": None, "fm": None,
                "q_spread": None, "d_spread": None}, [], []
    ic = _ic(valid, column)
    fm = cs.fama_macbeth_slope(valid.rename(columns={column: "composite_score"}))
    ranked = valid[column].rank(method="first")
    q = pd.qcut(ranked, 5, labels=False) + 1
    d = pd.qcut(ranked, 10, labels=False) + 1
    quantiles = ([{"fecha": date, "metric": metric, "bins": "quintile", "bin": k,
                   "return": float(valid.retorno[q == k].mean())} for k in range(1, 6)] +
                 [{"fecha": date, "metric": metric, "bins": "decile", "bin": k,
                   "return": float(valid.retorno[d == k].mean())} for k in range(1, 11)])
    stability = []
    for sector, group in valid.groupby("sector"):
        value = _ic(group, column) if len(group) >= 30 else None
        if value is not None:
            stability.append({"fecha": date, "metric": metric, "group_type": "sector",
                              "group": str(sector), "ic": value, "n": len(group)})
    with_cap = valid[valid.market_cap > 0].copy()
    if len(with_cap) >= 90:
        size = pd.qcut(with_cap.market_cap.rank(method="first"), 3, labels=["small", "middle", "large"])
        for label in ("small", "middle", "large"):
            group = with_cap[size == label]
            value = _ic(group, column)
            if value is not None:
                stability.append({"fecha": date, "metric": metric, "group_type": "size",
                                  "group": label, "ic": value, "n": len(group)})
    return ({"fecha": date, "metric": metric, "n": len(valid), "ic": ic, "fm": fm,
             "q_spread": float(valid.retorno[q == 5].mean() - valid.retorno[q == 1].mean()),
             "d_spread": float(valid.retorno[d == 10].mean() - valid.retorno[d == 1].mean())},
            quantiles, stability)


def analyze() -> dict:
    record = preregister()
    dates = cs.dates()
    if len(dates) != 57 or dates[0] != cs.FIRST or dates[-1] != cs.LAST:
        raise ValueError("El calendario congelado de #40 ha cambiado.")
    rows, quantiles, stability, correlations, fingerprints = [], [], [], [], {}
    manifest = hr.VARIANTS[cs.SOURCE_VARIANT].cache / "manifest.json"
    fingerprints[str(manifest.relative_to(config.BASE_DIR))] = _hash(manifest)
    columns = [metric + "_pct" for _, metric, _ in SIGNALS]
    for date in dates:
        frame, hashes = _quarter(date)
        fingerprints.update(hashes)
        for _, metric, _ in SIGNALS:
            row, q_rows, st_rows = _signal_rows(frame, date, metric)
            rows.append(row)
            quantiles.extend(q_rows)
            stability.extend(st_rows)
        for i, a in enumerate(columns):
            for b in columns[i + 1:]:
                pair = frame[[a, b]].replace([np.inf, -np.inf], np.nan).dropna()
                if len(pair) >= 30 and pair[a].nunique() > 1 and pair[b].nunique() > 1:
                    correlations.append({"fecha": date, "a": a[:-4], "b": b[:-4],
                                         "rho": float(stats.spearmanr(pair[a], pair[b]).statistic),
                                         "n": len(pair)})
    panel = pd.DataFrame(rows)
    st = pd.DataFrame(stability)
    corr = pd.DataFrame(correlations)
    primary = {}
    for family, metric, direction in SIGNALS:
        sub = panel[panel.metric == metric].copy()
        complete = sub.dropna(subset=["ic"])
        if len(complete) < 30:
            primary[metric] = {"family": family, "raw_expected": direction, "n_periods": len(complete),
                               "media": None, "p": 1.0, "status": "no_evaluable"}
            continue
        infer = _hac_calendar(sub.ic)
        fm = _hac_calendar(sub.fm) if sub.fm.notna().sum() >= 30 else None
        primary[metric] = {**infer, "family": family, "raw_expected": direction,
                           "n_periods": len(complete), "n_mean": float(complete.n.mean()),
                           "icir": float(complete.ic.mean() / complete.ic.std(ddof=1)),
                           "positive_fraction": float((complete.ic > 0).mean()),
                           "q_spread": float(complete.q_spread.mean()),
                           "d_spread": float(complete.d_spread.mean()),
                           "fm_hac_descriptive": fm,
                           "windows": {name: float(complete.loc[(complete.fecha >= start) &
                                                                 (complete.fecha < end), "ic"].mean())
                                       for name, (start, end) in WINDOWS.items()}}
    _holm(primary)
    for metric, result in primary.items():
        sectors, sizes = {}, {}
        subset = st[st.metric == metric]
        for kind, target in (("sector", sectors), ("size", sizes)):
            for group, group_frame in subset[subset.group_type == kind].groupby("group"):
                target[group] = {"ic_mean": float(group_frame.ic.mean()), "n_periods": len(group_frame)}
        result["sector_stability"] = sectors
        result["size_stability"] = sizes
        if result["media"] is None or result["media"] <= 0:
            label = "sin_evidencia"
        elif result["p_holm"] >= .05:
            label = "indicio"
        elif (sum(v > 0 for v in result["windows"].values()) < 2 or
              sum(v["ic_mean"] > 0 for v in sizes.values()) < 2):
            label = "requiere_OOS"
        else:
            label = "robusta_retrospectivamente"
        result["classification"] = label
    corr_summary = corr.groupby(["a", "b"], as_index=False).agg(rho_mean=("rho", "mean"), n_periods=("rho", "size"))
    matrix = pd.DataFrame(np.eye(len(SIGNALS)), index=[x[1] for x in SIGNALS],
                          columns=[x[1] for x in SIGNALS])
    for row in corr_summary.itertuples(index=False):
        matrix.loc[row.a, row.b] = row.rho_mean
        matrix.loc[row.b, row.a] = row.rho_mean
    OUTPUT.mkdir(parents=True, exist_ok=True)
    panel.to_csv(OUTPUT / "factor_ic.csv", index=False)
    pd.DataFrame(quantiles).to_csv(OUTPUT / "quantile_returns.csv", index=False)
    st.to_csv(OUTPUT / "stability.csv", index=False)
    corr_summary.to_csv(OUTPUT / "correlation_pairs.csv", index=False)
    matrix.to_csv(OUTPUT / "correlations.csv")
    result = {"spec_sha256": record["sha256"], "code_sha256": _hash(Path(__file__)),
              "inputs_sha256": fingerprints, "n_dates": len(dates), "factors": primary,
              "interpretation": "retrospectivo; ninguna clasificación constituye validación independiente"}
    _save(OUTPUT / "resultado.json", result)
    pd.DataFrame([{"metric": metric, **{k: v for k, v in data.items() if not isinstance(v, (dict, list))}}
                  for metric, data in primary.items()]).to_csv(OUTPUT / "factor_summary.csv", index=False)
    pd.DataFrame([{"factor": metric + "_pct", "horizonte": 3, "sector_neutral": False,
                   "ic_mean": data["media"], "icir": data.get("icir"),
                   "pct_ic_positive": data.get("positive_fraction"),
                   "q_spread": data.get("q_spread"), "n_periods": data["n_periods"],
                   "p_holm": data["p_holm"], "classification": data["classification"]}
                  for metric, data in primary.items()]).to_csv(OUTPUT / "factor_lab_summary.csv", index=False)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preregister", action="store_true")
    parser.add_argument("--analyze", action="store_true")
    args = parser.parse_args()
    if args.preregister:
        print(preregister()["sha256"])
    if args.analyze:
        result = analyze()
        print(json.dumps({k: {"ic": v["media"], "p_holm": v["p_holm"],
                              "classification": v["classification"]}
                          for k, v in result["factors"].items()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
