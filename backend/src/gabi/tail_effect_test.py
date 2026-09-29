"""Prueba retrospectiva preregistrada de la cola del Composite (#47)."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from . import academic_factors as af
from . import config, cross_section_test as cs
from . import historical_revalidation as hr


OUTPUT = config.BASE_DIR / "docs" / "tail-effect-test"
BENCHMARKS = (config.BASE_DIR / "docs" / "historical-revalidation-2011-2025"
              / "acreditado-38-continua" / "benchmarks-by-period.csv")
BANDS = (("top_1", 0.00, 0.01), ("p1_5", 0.01, 0.05),
         ("p5_10", 0.05, 0.10), ("p10_20", 0.10, 0.20),
         ("p20_40", 0.20, 0.40), ("p40_60", 0.40, 0.60),
         ("p60_80", 0.60, 0.80), ("p80_100", 0.80, 1.00))
WINDOWS = {"2011_2015": ("2011-07-02", "2016-01-02"),
           "2016_2020": ("2016-01-02", "2021-01-02"),
           "2021_2025": ("2021-01-02", "2025-10-02")}
SPEC = {
    "issue": 47,
    "stage": "RESEARCH_RETROSPECTIVE",
    "prior_observation": "Top-20 vs universo +1,36 pp/trimestre ya observado en #40; ningún resultado de esta muestra es confirmatorio independiente",
    "hypothesis": "La ventaja se concentra en el 5 % superior y presenta una curvatura positiva frente a los percentiles siguientes",
    "data": {
        "rankings": "data/revalidation_2011_2025/acreditado-38/ranking-{fecha}.csv",
        "forward": "data/cross_section_test/forward-{fecha}.csv",
        "dates": "57 rebalanceos invertidos, 2011-07-02 a 2025-07-02, según el manifest de #40",
        "eligible": "composite_score finito y score_coverage >= 0,70; ranking antes de descartar retornos ausentes",
        "return": "retorno bruto equiponderado del trimestre siguiente de #40; sin costes",
        "benchmark": "SPY del benchmarks-by-period.csv de la variante acreditado-38-continua; RSP no está en el dataset congelado",
        "missing_returns": "las bandas se fijan antes de excluir retornos ausentes; se informa cobertura; abortar si una banda no tiene retorno en cualquier trimestre",
    },
    "bands": [{"name": name, "from": low, "to": high} for name, low, high in BANDS],
    "assignment": "orden descendente por composite_score; empates por símbolo ascendente; percentil=(posición-0,5)/N; intervalos [from,to), último incluye 1",
    "primary": {
        "contrasts": ["top_5 - p5_20", "(top_5 - p5_20) - (p5_20 - p20_100)"],
        "aggregation": "media equiponderada por trimestre de cada grupo de bandas, no media de medias de bandas",
        "test": "media trimestral > 0, t unilateral con SE Newey-West Bartlett, 3 retardos fijos, df=n-1",
        "multiplicity": "Holm sobre los 2 contrastes, alpha 0,05",
        "success": "ambos contrastes positivos y p ajustada Holm < 0,05; se denomina patrón histórico compatible con cola, nunca confirmación independiente",
    },
    "secondary": {
        "band_excess": "8 excesos de banda frente al universo elegible, pruebas bilaterales HAC(3) con Holm entre las 8",
        "benchmarks": "medias de cada banda frente a universo y SPY, descriptivas; SPY no participa en la decisión",
        "windows": "2011-15, 2016-20, 2021-25: medias por banda y contrastes, solo descriptivas",
        "top_20": "Top-20 menos universo, descriptivo y ya observado; no participa en la decisión",
    },
    "interpretation": "si falla algún contraste: señal de cola no distinguible de ruido/selección con esta muestra; si ambos pasan: patrón retrospectivo compatible, todavía compatible con selección previa",
    "model_changes": "ninguno; no modificar pesos ni Investor sin evidencia independiente",
}


def spec_hash() -> str:
    return hashlib.sha256(json.dumps(SPEC, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def preregister() -> dict:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / "preregistro.json"
    digest = spec_hash()
    if path.exists():
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("sha256") != digest or record.get("spec") != SPEC:
            raise ValueError("El preregistro #47 difiere de la especificación congelada.")
        return record
    record = {"sha256": digest, "spec": SPEC}
    _write_json(path, record)
    return record


def _inference(series: pd.Series, *, alternative: str = "greater") -> dict:
    values = series.to_numpy(dtype=float)
    if not np.isfinite(values).all() or len(values) < 5:
        raise ValueError("La serie trimestral debe estar completa y tener al menos 5 observaciones.")
    fit = af._ols(values, np.ones((len(values), 1)), ["media"], hac_lags=3)
    mean, se, t = float(values.mean()), float(fit["se"]["media"]), float(fit["t_stat"]["media"])
    if not np.isfinite(t):
        raise ValueError("No puede estimarse la incertidumbre HAC de una serie constante.")
    p = float(stats.t.sf(t, df=len(values) - 1)) if alternative == "greater" else float(2 * stats.t.sf(abs(t), df=len(values) - 1))
    critical = float(stats.t.ppf(0.975, df=len(values) - 1))
    return {"n": len(values), "media": mean, "se_hac": se, "t_hac": t, "p": p,
            "ic95": [mean - critical * se, mean + critical * se], "hac_lags": 3}


def _holm(results: dict) -> None:
    ordered = sorted(results, key=lambda key: results[key]["p"])
    adjusted = 0.0
    for i, key in enumerate(ordered):
        adjusted = max(adjusted, min(1.0, (len(ordered) - i) * results[key]["p"]))
        results[key]["p_holm"] = adjusted


def quarter(date: str) -> tuple[dict, dict]:
    ranking_path = hr.VARIANTS[cs.SOURCE_VARIANT].cache / f"ranking-{date}.csv"
    return_path = cs.WORK / f"forward-{date}.csv"
    ranking = pd.read_csv(ranking_path, index_col=0)
    forward = pd.read_csv(return_path, index_col=0)
    eligible = ranking.loc[ranking.composite_score.notna() & np.isfinite(ranking.composite_score)
                           & (ranking.score_coverage >= 0.70), ["composite_score"]]
    if set(eligible.index) != set(forward.index) or eligible.index.has_duplicates or forward.index.has_duplicates:
        raise ValueError(f"Universo de #40 distinto en {date}.")
    eligible = eligible.sort_index().sort_values("composite_score", ascending=False, kind="stable")
    eligible = eligible.join(forward[["retorno"]], validate="one_to_one")
    eligible["percentile"] = (np.arange(len(eligible)) + 0.5) / len(eligible)
    observed = eligible.dropna(subset=["retorno"])
    if observed.empty:
        raise ValueError(f"Sin retornos en {date}.")
    row = {"fecha": date, "elegibles": len(eligible), "con_retorno": len(observed),
           "universo": float(observed.retorno.mean()),
           "top_20": float(eligible.head(20).retorno.mean())}
    for name, low, high in BANDS:
        members = eligible[(eligible.percentile >= low) & (eligible.percentile < high)]
        returns = members.retorno.dropna()
        if returns.empty:
            raise ValueError(f"Banda {name} sin retornos en {date}.")
        row[name] = float(returns.mean())
        row[f"n_{name}"] = len(members)
        row[f"n_return_{name}"] = len(returns)
    for name, low, high in (("top_5", 0, .05), ("p5_20", .05, .20), ("p20_100", .20, 1)):
        returns = eligible.loc[(eligible.percentile >= low) & (eligible.percentile < high), "retorno"].dropna()
        row[name] = float(returns.mean())
    row["tail_step"] = row["top_5"] - row["p5_20"]
    row["tail_convexity"] = row["top_5"] - 2 * row["p5_20"] + row["p20_100"]
    return row, {str(ranking_path.relative_to(config.BASE_DIR)): _hash(ranking_path),
                 str(return_path.relative_to(config.BASE_DIR)): _hash(return_path)}


def analyze() -> dict:
    record = preregister()
    dates = cs.dates()
    if len(dates) != 57 or dates[0] != cs.FIRST or dates[-1] != cs.LAST:
        raise ValueError("El calendario de #40 ha cambiado.")
    rows, fingerprints = [], {}
    manifest = hr.VARIANTS[cs.SOURCE_VARIANT].cache / "manifest.json"
    fingerprints[str(manifest.relative_to(config.BASE_DIR))] = _hash(manifest)
    for date in dates:
        row, hashes = quarter(date)
        rows.append(row)
        fingerprints.update(hashes)
    benchmark = pd.read_csv(BENCHMARKS).set_index("fecha")
    panel = pd.DataFrame(rows).set_index("fecha")
    panel["spy"] = benchmark.loc[panel.index, "spy"]
    if panel.spy.isna().any():
        raise ValueError("Falta SPY en los trimestres analizados.")
    fingerprints[str(BENCHMARKS.relative_to(config.BASE_DIR))] = _hash(BENCHMARKS)
    primary = {"tail_step": _inference(panel.tail_step),
               "tail_convexity": _inference(panel.tail_convexity)}
    _holm(primary)
    band_excess = {name: _inference(panel[name] - panel.universo, alternative="two-sided")
                   for name, _, _ in BANDS}
    _holm(band_excess)
    bands = {name: {"media": float(panel[name].mean()),
                    "vs_universo": float((panel[name] - panel.universo).mean()),
                    "vs_spy": float((panel[name] - panel.spy).mean()),
                    "n_min": int(panel[f"n_{name}"].min()),
                    "cobertura_min": float((panel[f"n_return_{name}"] / panel[f"n_{name}"]).min())}
             for name, _, _ in BANDS}
    windows = {name: {key: float(panel.loc[(panel.index >= start) & (panel.index < end), key].mean())
                      for key in ["tail_step", "tail_convexity", "universo", "spy", *[band[0] for band in BANDS]]}
               for name, (start, end) in WINDOWS.items()}
    success = all(v["media"] > 0 and v["p_holm"] < .05 for v in primary.values())
    result = {"spec_sha256": record["sha256"], "code_sha256": _hash(Path(__file__)),
              "inputs_sha256": fingerprints, "trimestres": len(panel),
              "primary": primary, "band_excess": band_excess, "bands": bands,
              "windows": windows, "universo_media": float(panel.universo.mean()),
              "spy_media": float(panel.spy.mean()),
              "top20_vs_universo": float((panel.top_20 - panel.universo).mean()),
              "decision": "patron_historico_compatible_sin_confirmacion_independiente" if success else
                          "senal_de_cola_no_distinguible_de_ruido_o_seleccion"}
    OUTPUT.mkdir(parents=True, exist_ok=True)
    panel.reset_index().to_csv(OUTPUT / "por-trimestre.csv", index=False)
    _write_json(OUTPUT / "resultado.json", result)
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
        print(json.dumps({"sha256": result["spec_sha256"], "decision": result["decision"],
                          "primary": result["primary"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
