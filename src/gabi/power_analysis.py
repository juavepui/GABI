"""Análisis de potencia: cuánta evidencia hace falta para descartar la suerte (issue #39).

Solo usa resultados ya publicados (#35: exceso trimestral V1 Top-20 frente al
SPY y frente al universo elegible) y supuestos declarados. No calcula el IC
real del Composite: eso es el resultado de la prueba preregistrada del #40, y
mirarlo aquí la contaminaría. Para la sección cruzada se usan escenarios de IC
y la dispersión mínima teórica del IC con N empresas.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

from . import config, stats_rigor
from . import factor_stability as fs

REVALIDATION = config.BASE_DIR / "docs" / "historical-revalidation-2011-2025"
OUTPUT = config.BASE_DIR / "docs" / "power-analysis"
ALPHA = 0.05  # unilateral: la hipótesis es que GABI supera, no que difiere
POWER = 0.80
YEARS = (10, 14.25, 20, 25)
IC_SCENARIOS = (0.02, 0.03, 0.05, 0.08)
IC_SD_SCENARIOS = (0.10, 0.15)  # dispersión trimestral del IC; el mínimo teórico con N=350 es 1/sqrt(N)≈0,053
DOCUMENTED_TRIALS = 29  # #12 (24) + #23 (2) + #36 (3)


def z(power: float = POWER, alpha: float = ALPHA) -> float:
    return float(norm.ppf(1 - alpha) + norm.ppf(power))


def quarters_needed(mean: float, sd: float, *, power: float = POWER) -> float:
    """Trimestres para detectar ``mean`` con desviación típica ``sd`` (t unilateral, aproximación normal)."""
    return float((z(power) * sd / mean) ** 2) if mean > 0 else float("inf")


def minimum_detectable(sd: float, quarters: float, *, power: float = POWER) -> float:
    return float(z(power) * sd / np.sqrt(quarters))


def power_at(mean: float, sd: float, quarters: float) -> float:
    return float(norm.cdf(mean / sd * np.sqrt(quarters) - norm.ppf(1 - ALPHA)))


def observed_series() -> dict[str, pd.Series]:
    """Excesos trimestrales ya publicados en el #35 (V1 Top-20, serie continua acreditada)."""
    periods = pd.read_csv(REVALIDATION / "acreditado-38-continua" / "v1-top20-periods.csv").dropna(subset=["retorno"])
    bench = pd.read_csv(REVALIDATION / "acreditado-38-continua" / "benchmarks-by-period.csv")
    merged = periods.merge(bench[["fecha", "universo_elegible_ew"]], on="fecha", how="left")
    recent = merged[merged.fecha >= "2016-01-02"]
    return {"vs_spy_2011_2025": merged.retorno - merged.spy,
            "vs_universo_2011_2025": (merged.retorno - merged.universo_elegible_ew).dropna(),
            "vs_spy_2016_2025": recent.retorno - recent.spy,
            "vs_universo_2016_2025": (recent.retorno - recent.universo_elegible_ew).dropna()}


def portfolio_tests() -> list[dict]:
    rows = []
    for name, series in observed_series().items():
        mean, sd, n = float(series.mean()), float(series.std(ddof=1)), len(series)
        rows.append({"prueba": name, "trimestres": n, "exceso_medio": mean, "desviacion": sd,
                     "ir_anual": mean / sd * 2, "t": mean / sd * np.sqrt(n),
                     "potencia_actual": power_at(mean, sd, n),
                     "trimestres_80": quarters_needed(mean, sd), "anios_80": quarters_needed(mean, sd) / 4,
                     "efecto_minimo_detectable_por_anios": {str(y): minimum_detectable(sd, y * 4) for y in YEARS}})
    return rows


def cross_section_tests() -> list[dict]:
    """Potencia de la prueba de IC medio (una observación por trimestre) por escenarios."""
    rows = []
    for sd in IC_SD_SCENARIOS:
        for ic in IC_SCENARIOS:
            rows.append({"ic_medio": ic, "desviacion_ic": sd, "ir_del_ic_anual": ic / sd * 2,
                         "trimestres_80": quarters_needed(ic, sd), "anios_80": quarters_needed(ic, sd) / 4,
                         "potencia_con_57_trimestres": power_at(ic, sd, 57)})
    return rows


def multiple_testing() -> dict:
    """Listón de Sharpe esperable por azar con las configuraciones documentadas (DSR)."""
    prior = json.loads((config.BASE_DIR / "docs" / "overfitting-audit" / "audit.json").read_text(encoding="utf-8"))
    sharpes = [s["sharpe_anualizado"] for s in prior["including_cost_sensitivity"]["trial_statistics"].values()]
    sr0 = stats_rigor.expected_max_sharpe(sharpes, n_trials=DOCUMENTED_TRIALS)
    return {"n_trials": DOCUMENTED_TRIALS, "sharpe_maximo_esperado_por_azar_anual": sr0,
            "nota": "El DSR compara el Sharpe elegido con este listón, no con 0: con más configuraciones "
                    "probadas, más alto el listón. Cada prueba nueva lo sube."}


def prospective() -> dict:
    """Años prospectivos para una conclusión con el efecto de la serie continua, solos o combinados."""
    series = observed_series()["vs_spy_2011_2025"]
    mean, sd = float(series.mean()), float(series.std(ddof=1))
    needed = quarters_needed(mean, sd)
    retro = len(series)
    return {"supuesto": "el efecto futuro igual al observado 2011-2025 (optimista si hubo sobreajuste)",
            "anios_prospectivos_solos_80": needed / 4,
            "anios_prospectivos_si_se_combinan_con_2011_2025_80": max(0.0, (needed - retro) / 4),
            "advertencia": "Combinar exige una regla fijada de antemano y tratar 2016-2025 como muestra de diseño (#42)."}


def run() -> dict:
    report = {"issue": 39, "alpha_unilateral": ALPHA, "potencia_objetivo": POWER,
              "cartera": portfolio_tests(), "seccion_cruzada": cross_section_tests(),
              "multiples_pruebas": multiple_testing(), "prospectiva": prospective(),
              "code_sha256": fs.content_hash(Path(__file__)),
              "inputs_sha256": {p.name: fs.content_hash(p) for p in (
                  REVALIDATION / "acreditado-38-continua" / "v1-top20-periods.csv",
                  REVALIDATION / "acreditado-38-continua" / "benchmarks-by-period.csv")}}
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "power.json").write_text(json.dumps(fs._json_safe(report), ensure_ascii=False, indent=2) + "\n",
                                       encoding="utf-8")
    return report


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    print(json.dumps(fs._json_safe(run()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
