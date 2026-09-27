"""La idea de GABI con 60 años y varios mercados (issue #45).

Mezcla mensual de factores long-short con los pesos del Composite:
valor 30 % (HML), calidad/rentabilidad 35 % (RMW), momentum 25 % (Mom/WML) y
bajo riesgo 10 % (quintil de menor varianza menos el de mayor varianza, solo
EE. UU.). Datos gratuitos de la Kenneth French Data Library, guardados con su
SHA-256. La especificación se congela con hash antes de calcular la mezcla.

Responde si la idea tiene una prima fiable a largo plazo y fuera de EE. UU.
No responde si la implementación concreta de GABI (Top-20 del S&P 500) la
captura.
"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from . import academic_factors as af
from . import config, research_lab, scoring
from . import factor_stability as fs

OUTPUT = config.BASE_DIR / "docs" / "factor-history"
WORK = config.DATA_DIR / "factor_history"
BASE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
WEIGHTS = {"value": 0.30, "quality": 0.35, "momentum": 0.25, "risk": 0.10}
US_PRIMARY = ("1963-07-01", "2015-12-31")  # antes del diseño de GABI (2016-2025)
REGIONS = {"europa": "Europe", "japon": "Japan", "asia_pacifico": "Asia_Pacific_ex_Japan"}

SPEC = {
    "issue": 45, "stage": "RESEARCH",
    "hypothesis": "Una mezcla long-short de valor, rentabilidad, momentum y bajo riesgo con los pesos de GABI "
                  "(30/35/25/10) tiene una prima mensual media positiva.",
    "weights": WEIGHTS, "weights_match_scoring_default": WEIGHTS == scoring.DEFAULT_WEIGHTS,
    "factors": {"value": "HML (Fama-French 5 factores 2x3)", "quality": "RMW (Fama-French 5 factores 2x3)",
                "momentum": "Mom (EE. UU.) / WML (regiones)",
                "risk": "EE. UU.: 'Lo 20' menos 'Hi 20' de Portfolios Formed on Variance (ponderados por valor); "
                        "regiones: sin factor, pesos reescalados sobre 0,9"},
    "primary": {"sample": "EE. UU. 1963-07 → 2015-12 (antes del diseño de GABI)",
                "test": "media mensual de la mezcla > 0, t Newey-West (retardos automáticos), unilateral",
                "alpha": 0.05},
    "replications": {"samples": {k: f"{v}, 1990-11 → último mes publicado" for k, v in REGIONS.items()},
                     "correction": "Holm sobre las 3, unilateral, alpha 0,05"},
    "descriptive": ["EE. UU. 2016-2025 (muestra de diseño de GABI; no confirmatorio)", "cada factor aislado",
                    "décadas", "peor racha acumulada (drawdown) de la mezcla"],
    "decision": {"idea_respaldada": "principal significativa y al menos 2 de 3 réplicas significativas tras Holm",
                 "respaldo_parcial": "solo una de las dos condiciones",
                 "sin_respaldo": "ninguna"},
    "caveat": "Las primas de estos factores son conocidas en la literatura: la prueba no es ciega respecto a su "
              "existencia; lo nuevo es la mezcla con los pesos de GABI y la regla fijada de antemano.",
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
        "factor_mix_30_35_25_10", "RESEARCH", True, family="stat_5", universe="Kenneth French factors",
        weights=WEIGHTS, rebalance="mensual (factores)", is_start=US_PRIMARY[0], is_end=US_PRIMARY[1],
        notes=f"Preregistro #45, sha256 {digest}; sin resultados")
    record = {"sha256": digest, "spec": SPEC, "experiment_id": experiment}
    _save(path, record)
    return record


# --- Datos ------------------------------------------------------------------------------------

def _first_monthly_table(text: str) -> pd.DataFrame:
    """Primera tabla mensual de un CSV de French (los ficheros encadenan varias: ponderada por valor,
    equiponderada, anuales...)."""
    header: list[str] = []
    rows: list[list[str]] = []
    started = False
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(",")]
        token = parts[0] if parts else ""
        if len(token) == 6 and token.isdigit():
            started = True
            rows.append(parts)
        elif started:
            break
        elif len(parts) > 2 and token == "" and any(parts[1:]):
            header = parts[1:]
    frame = pd.DataFrame([r[1:] for r in rows], columns=header[:len(rows[0]) - 1],
                         index=pd.to_datetime([r[0] for r in rows], format="%Y%m"))
    return frame.apply(pd.to_numeric, errors="coerce") / 100


def _download(name: str) -> tuple[str, str]:
    WORK.mkdir(parents=True, exist_ok=True)
    path = WORK / name.replace(".zip", ".csv")
    if not path.exists():
        path.write_text(af._download_zip_csv(BASE + name), encoding="utf-8")
    text = path.read_text(encoding="utf-8")
    return text, hashlib.sha256(text.encode()).hexdigest()


def load_data() -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    """Factores mensuales por mercado (fracciones, no %) y SHA-256 de cada fichero."""
    digests: dict[str, str] = {}
    markets = {}
    text, digests["us_5f"] = _download("F-F_Research_Data_5_Factors_2x3_CSV.zip")
    us = _first_monthly_table(text)[["HML", "RMW", "RF"]]
    text, digests["us_mom"] = _download("F-F_Momentum_Factor_CSV.zip")
    us = us.join(_first_monthly_table(text).iloc[:, [0]].set_axis(["MOM"], axis=1), how="inner")
    text, digests["us_var"] = _download("Portfolios_Formed_on_VAR_CSV.zip")
    variance = _first_monthly_table(text)
    us = us.join((variance["Lo 20"] - variance["Hi 20"]).rename("RISK"), how="inner")
    markets["eeuu"] = us
    for key, region in REGIONS.items():
        text, digests[f"{key}_5f"] = _download(f"{region}_5_Factors_CSV.zip")
        frame = _first_monthly_table(text)[["HML", "RMW", "RF"]]
        text, digests[f"{key}_mom"] = _download(f"{region}_Mom_Factor_CSV.zip")
        markets[key] = frame.join(_first_monthly_table(text).iloc[:, [0]].set_axis(["MOM"], axis=1), how="inner")
    return markets, digests


# --- Análisis ---------------------------------------------------------------------------------

def mix(frame: pd.DataFrame) -> pd.Series:
    parts = {"HML": WEIGHTS["value"], "RMW": WEIGHTS["quality"], "MOM": WEIGHTS["momentum"]}
    if "RISK" in frame:
        parts["RISK"] = WEIGHTS["risk"]
    total = sum(parts.values())
    return sum(frame[column] * weight / total for column, weight in parts.items())


def _test(series: pd.Series) -> dict:
    values = series.dropna().to_numpy(dtype=float)
    fit = af._ols(values, np.ones((len(values), 1)), ["media"])
    t = float(fit["t_stat"]["media"])
    wealth = np.cumprod(1 + values)
    return {"meses": len(values), "desde": str(series.dropna().index[0].date()),
            "hasta": str(series.dropna().index[-1].date()),
            "media_mensual": float(values.mean()), "media_anualizada": float((1 + values.mean()) ** 12 - 1),
            "volatilidad_anual": float(values.std(ddof=1) * np.sqrt(12)),
            "sharpe_anual": float(values.mean() / values.std(ddof=1) * np.sqrt(12)),
            "t_nw": t, "hac_lags": fit["hac_lags"], "p_unilateral": float(1 - stats.t.cdf(t, df=len(values) - 1)),
            "peor_racha": float((wealth / np.maximum.accumulate(wealth) - 1).min())}


def analyze() -> dict:
    record = preregister()
    markets, digests = load_data()
    us = markets["eeuu"]
    mixes = {name: mix(frame) for name, frame in markets.items()}
    primary = _test(mixes["eeuu"].loc[US_PRIMARY[0]:US_PRIMARY[1]])
    replications = {key: _test(mixes[key].loc["1990-11-01":]) for key in REGIONS}
    ordered = sorted(replications, key=lambda k: replications[k]["p_unilateral"])
    running = 0.0
    for rank, key in enumerate(ordered):
        running = max(running, min(1.0, (len(ordered) - rank) * replications[key]["p_unilateral"]))
        replications[key]["p_holm"] = running
    primary_ok = primary["p_unilateral"] < 0.05  # SPEC["primary"]["alpha"]
    replicated = sum(r["p_holm"] < 0.05 for r in replications.values()) >= 2
    decision = ("idea_respaldada" if primary_ok and replicated else
                "respaldo_parcial" if primary_ok or replicated else "sin_respaldo")
    decades = {f"{start}s": _test(mixes["eeuu"].loc[f"{start}-01-01":f"{start + 9}-12-31"])
               for start in range(1970, 2030, 10) if len(mixes["eeuu"].loc[f"{start}-01-01":f"{start + 9}-12-31"]) > 24}
    descriptive = {
        "eeuu_2016_2025_diseno": _test(mixes["eeuu"].loc["2016-01-01":]),
        "eeuu_completo": _test(mixes["eeuu"]),
        "factores_aislados_eeuu_1963_2015": {c: _test(us[c].loc[US_PRIMARY[0]:US_PRIMARY[1]])
                                             for c in ("HML", "RMW", "MOM", "RISK")},
        "decadas_eeuu": decades,
        "correlaciones_eeuu": us[["HML", "RMW", "MOM", "RISK"]].corr().round(3).to_dict(),
    }
    result = {"spec_sha256": record["sha256"], "datos_sha256": digests, "principal": primary,
              "replicas": replications, "descriptivas": descriptive, "decision": decision,
              "code_sha256": fs.content_hash(Path(__file__))}
    _save(OUTPUT / "resultado.json", result)
    pd.DataFrame(mixes).to_csv(OUTPUT / "mezcla-mensual.csv", index_label="mes")
    research_lab.log_experiment(
        "factor_mix_30_35_25_10", "RESEARCH", True, family="stat_5", universe="Kenneth French factors",
        weights=WEIGHTS, is_start=US_PRIMARY[0], is_end=US_PRIMARY[1], periods_per_year=12,
        n_periods=primary["meses"], sharpe=primary["sharpe_anual"], annualized_return=primary["media_anualizada"],
        max_drawdown=primary["peor_racha"], notes=f"Resultado #45; preregistro sha256 {record['sha256']}; {decision}",
        result={"principal": primary, "replicas": replications, "decision": decision})
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preregister", action="store_true")
    parser.add_argument("--analyze", action="store_true")
    args = parser.parse_args()
    if args.preregister:
        print(json.dumps({"sha256": preregister()["sha256"]}))
    if args.analyze:
        result = analyze()
        print(json.dumps(fs._json_safe({k: result[k] for k in ("principal", "replicas", "decision")}),
                         ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
