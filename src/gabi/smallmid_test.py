"""Prueba preregistrada de GABI fuera del S&P 500, con cotas para los datos que faltan (issue #44).

GABI se diseñó con el S&P 500; las empresas medianas y pequeñas de EE. UU. no
se usaron para diseñarlo. Aquí se aplica **sin cambios** (Composite 30/35/25/10,
mismas métricas, mismo filtro de cobertura) a un universo construido solo con
datos SEC, y se mide si ordena a esas empresas por su rentabilidad del
trimestre siguiente.

Los precios gratuitos no cubren a la mayoría de las empresas que desaparecen
(#44, estudio de viabilidad). Por eso la conclusión se juzga con **cotas
adversas**: a las empresas elegibles sin retorno siguiente se les asigna el
peor caso para la hipótesis. Este módulo contiene la especificación y la
construcción del universo; el resto de la tubería se añade por etapas sin
cambiar la especificación.
"""

import argparse
import hashlib
import json
from datetime import date, timedelta

import pandas as pd

from . import config, research_lab, scoring
from . import factor_stability as fs
from . import smallmid_feasibility as feas

OUTPUT = config.BASE_DIR / "docs" / "smallmid-test"
WORK = config.DATA_DIR / "smallmid_test"
FIRST, LAST = "2011-07-02", "2025-07-02"  # los mismos 57 rebalanceos que el #35 y el #40

SIC_SECTORS = [  # división SIC → sector amplio (aproximación documentada al GICS)
    ((100, 999), "Materials"), ((1000, 1499), "Materials"), ((1311, 1389), "Energy"),
    ((1500, 1799), "Industrials"), ((2000, 2199), "Consumer Staples"), ((2200, 2399), "Consumer Discretionary"),
    ((2400, 2799), "Materials"), ((2800, 2829), "Materials"), ((2830, 2836), "Health Care"),
    ((2840, 2899), "Consumer Staples"), ((2900, 2999), "Energy"), ((3000, 3499), "Industrials"),
    ((3500, 3569), "Industrials"), ((3570, 3579), "Information Technology"), ((3580, 3659), "Industrials"),
    ((3660, 3699), "Information Technology"), ((3700, 3799), "Industrials"), ((3800, 3840), "Industrials"),
    ((3841, 3851), "Health Care"), ((3852, 3999), "Consumer Discretionary"), ((4000, 4799), "Industrials"),
    ((4800, 4899), "Communication Services"), ((4900, 4999), "Utilities"), ((5000, 5199), "Industrials"),
    ((5200, 5999), "Consumer Discretionary"), ((6000, 6499), "Financials"), ((6500, 6553), "Real Estate"),
    ((6770, 6799), "Financials"), ((6798, 6798), "Real Estate"), ((7000, 7369), "Consumer Discretionary"),
    ((7370, 7379), "Information Technology"), ((7380, 7999), "Industrials"), ((8000, 8099), "Health Care"),
    ((8100, 8999), "Industrials"),
]

SPEC = {
    "issue": 44, "stage": "RESEARCH",
    "hypothesis": "El Composite de GABI, sin cambios, predice la rentabilidad relativa del trimestre siguiente entre "
                  "las empresas cotizadas de EE. UU. fuera del S&P 500 (IC medio > 0).",
    "why_out_of_sample": "GABI se diseñó con el S&P 500; estas empresas no se usaron para diseñarlo.",
    "universe": {"source": "frames XBRL de SEC (dei:EntityPublicFloat), sin índices de pago",
                 "rule": f"public float fechado en los {feas.LOOKBACK_DAYS} días anteriores, entre "
                         f"{feas.FLOAT_MIN:.0f} y {feas.FLOAT_MAX:.0f} USD; excluidos los emisores del S&P 500 "
                         "en la fecha (identidad acreditada #27/#34)",
                 "dates": f"rebalanceos trimestrales día 2 de {FIRST} a {LAST}"},
    "model": {"weights": scoring.DEFAULT_WEIGHTS, "metrics": scoring.SCORE_METRICS,
              "eligibility": "composite no vacío y cobertura >= 70 % de las 13 métricas (como GABI)",
              "sector": "sector amplio derivado del SIC de SEC (GABI usa fotos de Yahoo que no existen para "
                        "estas empresas); solo afecta al grupo de percentiles",
              "fundamentals": "Company Facts de SEC por CIK, point-in-time por fecha de presentación, con la "
                              "corrección de ejercicios del #38"},
    "prices": {"sources": ["Yahoo (tickers vigentes; serie archivada aparte, sin tocar la caché operativa)",
                           "Tiingo (tickers deslistados)", "Nasdaq Data Link WIKI (hasta 2018-03)"],
               "identity": "ticker por CIK: ticker SEC vigente o declarado en un 10-K/portada XBRL del emisor en el "
                           "intervalo; serie aceptada solo si pasa la comprobación de nivel de precio SEC "
                           "(public float / acciones × cierre, #28)",
               "forward_return": "de la sesión siguiente a la señal a la primera sesión tras +3 meses; si la serie "
                                 "termina antes, último precio (sin evento terminal acreditado: no estricto)"},
    "primary": {"test": "IC de Spearman trimestral entre composite_score y retorno siguiente; media de los "
                        "trimestres; t Newey-West unilateral", "alpha": 0.05},
    "bounds": {"adverse": "elegibles sin retorno siguiente: los de puntuación por encima de la mediana reciben el "
                          "percentil 10 del retorno observado del trimestre y los de debajo el percentil 90",
               "favourable": "el caso simétrico", "complete_case": "solo empresas con retorno"},
    "decision": {"robusta": "IC medio > 0 con p < 0,05 también con la cota adversa",
                 "condicionada_a_los_datos": "p < 0,05 con los casos completos pero no con la cota adversa",
                 "no_concluyente": "IC medio > 0 con p >= 0,05 en los casos completos",
                 "sin_capacidad_predictiva": "IC medio <= 0 en los casos completos"},
    "reporting": ["cobertura por trimestre: universo, con precio, elegibles y sin retorno siguiente",
                  "empresas excluidas por falta de precio, separadas entre las que desaparecen y las que no",
                  "quintiles y Top-20 frente al universo (descriptivos)", "IC por ventana 2011-15, 2016-20, 2021-25"],
    "model_changes": "ninguno; las pruebas ciegas no se tocan",
}


def spec_hash() -> str:
    return hashlib.sha256(json.dumps(SPEC, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


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
        "gabi_smallmid_ic", "RESEARCH", True, family="stat_4", universe="EE. UU. fuera del S&P 500 (SEC)",
        weights=scoring.DEFAULT_WEIGHTS, rebalance="trimestral día 2", is_start=FIRST, is_end=LAST,
        notes=f"Preregistro #44, sha256 {digest}; sin resultados")
    record = {"sha256": digest, "spec": SPEC, "experiment_id": experiment}
    path.write_text(json.dumps(fs._json_safe(record), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return record


def sector_from_sic(sic) -> str | None:
    try:
        code = int(sic)
    except (TypeError, ValueError):
        return None
    matches = [(hi - lo, name) for (lo, hi), name in SIC_SECTORS if lo <= code <= hi]
    return min(matches)[1] if matches else None  # el rango más específico gana


def rebalance_dates() -> list[str]:
    days, current = [], pd.Timestamp(FIRST)
    while current <= pd.Timestamp(LAST):
        days.append(current.date().isoformat())
        current += pd.DateOffset(months=3)
    return days


def build_universe() -> pd.DataFrame:
    """Universo de cada rebalanceo (datos, no resultados), con la regla preregistrada."""
    WORK.mkdir(parents=True, exist_ok=True)
    path = WORK / "universe.csv"
    if path.exists():
        return pd.read_csv(path, dtype={"cik": str})
    frames = []
    for day in rebalance_dates():
        # La regla usa el último cierre de trimestre previo a la señal.
        anchor = (date.fromisoformat(day) - timedelta(days=2)).isoformat()
        frame = feas.universe(anchor)
        frame.insert(0, "fecha", day)
        frames.append(frame)
        print(day, len(frame), flush=True)
    result = pd.concat(frames, ignore_index=True)
    result.to_csv(path, index=False)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preregister", action="store_true")
    parser.add_argument("--universe", action="store_true")
    args = parser.parse_args()
    if args.preregister:
        print(json.dumps({"sha256": preregister()["sha256"]}))
    if args.universe:
        frame = build_universe()
        print(json.dumps({"filas": len(frame), "ciks": frame.cik.nunique()}))


if __name__ == "__main__":
    main()
