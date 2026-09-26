"""Revalidación 2016-2025 y serie continua 2011-2025 con la capa acreditada (#35).

No es un motor nuevo: orquesta ``full_universe_audit`` (snapshot congelado,
rankings con hash, V1/V2 Top-10/20 con la configuración vigente) y
``historical_validation`` (cobertura por rebalanceo, benchmarks del universo
cubierto, cotas y retorno implícito de los excluidos) bajo tres variantes
fijadas en el protocolo (docs/historical-revalidation-2011-2025/PROTOCOL.md)
antes de ejecutar:

- ``operativo``: camino actual por ticker con el código de hoy (base limpia; la
  auditoría publicada se generó con código anterior);
- ``acreditado``: capa acreditada 2016-2025 (#34), fundamentales vigentes;
- ``operativo-38``: camino actual por ticker con la corrección de ejercicios (#38);
- ``acreditado-38``: capa acreditada 2010-2025 con la corrección (#38): la
  variante principal. Se evalúa como vista 2016-2025 y como serie continua.

Las diferencias con la auditoría de universo completo publicada se
descomponen en pasos: publicada → operativo (deriva de código y datos),
operativo → acreditado (capa acreditada), acreditado → acreditado-38 (#38) y,
como control, operativo → operativo-38.
"""

import argparse
import json
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import config, edgar, historical_pit, scoring
from . import factor_stability as fs
from . import full_universe_audit as fua
from . import historical_validation as hv
from . import multifactor_backtest as v1
from . import overfitting_audit as oa

ISSUE = 35
STOP = "2025-07-03"  # último rebalanceo 2025-07-02, como la auditoría de referencia
ACCREDITED = ("2010-2015", "2016-2025")
CACHE_ROOT = config.DATA_DIR / "revalidation_2011_2025"
OUTPUT = config.BASE_DIR / "docs" / "historical-revalidation-2011-2025"
REFERENCE_CACHE = config.DATA_DIR / "full_universe_audit"
REFERENCE_OUTPUT = config.BASE_DIR / "docs" / "full-universe-audit"
FACTORS = config.BASE_DIR / "docs" / "factor-stability" / "inputs.csv"
PRIMARY_TOP = 20  # ensayo seleccionado del #12 (top20_q); Top-10 se reporta como secundario
MIN_COVERAGE = hv.MIN_COVERAGE
FUNDAMENTAL = [*scoring.SCORE_METRICS["value"], *scoring.SCORE_METRICS["quality"]]
PRICE = [*scoring.SCORE_METRICS["momentum"], *scoring.SCORE_METRICS["risk"]]


@dataclass(frozen=True)
class Variant:
    key: str
    start: str
    periods: tuple[str, ...]
    fiscal_alignment: bool

    @property
    def cache(self) -> Path:
        return CACHE_ROOT / self.key


VARIANTS = {v.key: v for v in (
    Variant("operativo", "2016-01-02", (), False),
    Variant("acreditado", "2016-01-02", ACCREDITED, False),
    Variant("operativo-38", "2016-01-02", (), True),
    Variant("acreditado-38", "2010-01-02", ACCREDITED, True),
)}
# Vistas evaluadas: (variante, primer rebalanceo). La serie continua empieza en 2010-01-02
# y, como en el #33, invierte desde el primer trimestre con cobertura suficiente.
VIEWS = {
    "operativo": ("operativo", "2016-01-02"),
    "acreditado": ("acreditado", "2016-01-02"),
    "operativo-38": ("operativo-38", "2016-01-02"),
    "acreditado-38-2016": ("acreditado-38", "2016-01-02"),
    "acreditado-38-continua": ("acreditado-38", "2010-01-02"),
}
PUBLISHED = "publicada"
# Pasos de la descomposición (desde, hasta), todos sobre 2016-01-02 → 2025-10-02.
STEPS = [(PUBLISHED, "operativo"), ("operativo", "acreditado"), ("acreditado", "acreditado-38-2016"),
         ("operativo", "operativo-38"), (PUBLISHED, "acreditado-38-2016")]


def extra_sources() -> tuple[Path, ...]:
    root = Path(__file__).parent
    names = ["edgar.py", "historical_period.py", "historical_membership.py", "historical_ticker_corrections.py",
             "resources/historical_identity_corrections_2010_2015.json",
             "resources/historical_identity_corrections_2016_2025.json"]
    return (*hv.extra_sources(), *[root / name for name in names], *[path for path, _ in hv.QUARTERLY_AUDITS[1:]])


def _context(variant: Variant) -> ExitStack:
    stack = ExitStack()
    stack.enter_context(historical_pit.accredited_periods(*variant.periods))
    stack.enter_context(edgar.fiscal_alignment(variant.fiscal_alignment))
    return stack


def prepare(key: str) -> dict:
    variant = VARIANTS[key]
    with _context(variant):
        return fua.prepare(variant.cache, start=variant.start, stop=STOP, extra_sources=extra_sources())


def evaluate(view: str) -> dict:
    key, start = VIEWS[view]
    variant = VARIANTS[key]
    output = OUTPUT / view
    with _context(variant):
        report = fua.evaluate(variant.cache, output, start=start)
        if variant.periods:
            manifest = report["inputs"]
            config_record = {"variant": key, "view": view, "start": start, "stop_exclusive": STOP,
                             "accredited_periods": list(variant.periods),
                             "fiscal_alignment": variant.fiscal_alignment, "weights": scoring.DEFAULT_WEIGHTS,
                             "min_coverage": MIN_COVERAGE, "min_universe_coverage": hv.MIN_UNIVERSE,
                             "conclusive_accredited_price_coverage": hv.CONCLUSIVE_ACCREDITED}
            report = hv.analyze(variant.cache, output, manifest, report, issue=ISSUE, config_record=config_record)
    return report


# --- Comparación con la auditoría de referencia -------------------------------------------------

def _positions(periods: pd.DataFrame, column: str) -> dict[str, set[str]]:
    return {row.fecha: {s.strip() for s in str(getattr(row, column)).split(",") if s.strip() and s != "nan"}
            for row in periods.itertuples()}


def _v2_holdings(periods: pd.DataFrame) -> dict[str, set[str]]:
    result = {}
    for row in periods.itertuples():
        names = set()
        for column in ("held", "bought"):
            value = getattr(row, column)
            if isinstance(value, str):
                names |= {s.strip() for s in value.split(",") if s.strip()}
        result[row.fecha] = names
    return result


def _metrics(report: dict, top: int) -> dict:
    v2 = report["results"][f"v2_top{top}"]
    strategy, spy = v2["metrics"]["strategy"], v2["metrics"]["spy"]
    years = (pd.Timestamp(v2["end"]) - pd.Timestamp(v2["start"])).days / 365.25

    def pack(m):
        risk = m["daily_risk"]
        return {"cagr": m["cagr_from_initial_cash"], "vol": risk["vol_anualizada"], "sharpe": risk["sharpe"],
                "sharpe_se": v1.sharpe_standard_error(risk["sharpe"], years), "max_drawdown": risk["max_drawdown"],
                "es95_diario": m["tail_risk"]["95"]["expected_shortfall"]}
    return {"estrategia": pack(strategy), "spy": pack(spy), "n_periodos": v2["n_periods"],
            "rotacion_media": v2["turnover_medio"], "coste_total": v2.get("coste_total"),
            "estricto": v2.get("strict_result", True), "inicio": v2["start"], "fin": v2["end"]}


def _table(cache: Path, date: str) -> pd.DataFrame:
    return pd.read_csv(cache / f"ranking-{date}.csv", index_col=0)


def _eligible(table: pd.DataFrame) -> pd.Series:
    return table["composite_score"].notna() & (table["score_coverage"] >= MIN_COVERAGE)


def _changed(a: pd.Series, b: pd.Series, columns: list[str]) -> bool:
    for column in columns:
        x, y = a.get(column), b.get(column)
        if pd.isna(x) != pd.isna(y):
            return True
        if not pd.isna(x) and not np.isclose(float(x), float(y), rtol=1e-6, atol=1e-12):
            return True
    return False


def classify_exit(symbol: str, reference: pd.DataFrame, other: pd.DataFrame, accredited: bool) -> str:
    """Por qué una posición de la referencia no está en la cartera de la otra variante."""
    if symbol not in other.index:
        return "fuera_de_la_composicion"
    row = other.loc[symbol]
    if accredited and pd.isna(row.get("entity_id")):
        return "identidad_no_acreditada"
    if accredited and pd.isna(row.get("price_source")):
        return "sin_precio_acreditado"
    if pd.isna(row["composite_score"]) or row["score_coverage"] < MIN_COVERAGE:
        return "no_elegible"
    base = reference.loc[symbol]
    fundamentals, prices = _changed(base, row, FUNDAMENTAL), _changed(base, row, PRICE)
    if fundamentals and prices:
        return "desplazada_fundamentales_y_precio"
    if fundamentals:
        return "desplazada_fundamentales"
    if prices:
        return "desplazada_precio"
    return "desplazada_por_otras_entradas"


def classify_entry(symbol: str, reference: pd.DataFrame, other: pd.DataFrame) -> str:
    """Por qué entra en la otra variante una posición que la referencia no tenía."""
    if symbol not in reference.index:
        return "miembro_ausente_en_la_referencia"
    base = reference.loc[symbol]
    if pd.isna(base["composite_score"]) or base["score_coverage"] < MIN_COVERAGE:
        return "no_elegible_en_la_referencia"
    row = other.loc[symbol]
    fundamentals, prices = _changed(base, row, FUNDAMENTAL), _changed(base, row, PRICE)
    return ("sube_fundamentales_y_precio" if fundamentals and prices else "sube_fundamentales" if fundamentals
            else "sube_precio" if prices else "sube_por_otras_salidas")


def _locate(view: str) -> tuple[Path, Path, bool]:
    """(caché de rankings, carpeta de resultados, acreditada) de una vista o de la auditoría publicada."""
    if view == PUBLISHED:
        return REFERENCE_CACHE, REFERENCE_OUTPUT, False
    variant = VARIANTS[VIEWS[view][0]]
    return variant.cache, OUTPUT / view, bool(variant.periods)


def compare(base: str, view: str) -> dict:
    """Rebalanceo a rebalanceo de ``view`` frente a ``base`` (2016-2025)."""
    reference_cache, reference_output, _ = _locate(base)
    other_cache, output, accredited = _locate(view)
    reference_report = json.loads((reference_output / "audit.json").read_text(encoding="utf-8"))
    report = json.loads((output / "audit.json").read_text(encoding="utf-8"))
    step = OUTPUT / "pasos" / f"{base}__{view}"
    step.mkdir(parents=True, exist_ok=True)
    dates = [d for d in reference_report["inputs"]["dates"] if d in report["inputs"]["dates"]]
    rows, exits, entries, not_accredited = [], [], [], []
    for top in (10, 20):
        ref_v1 = pd.read_csv(reference_output / f"v1-top{top}-periods.csv")
        oth_v1 = pd.read_csv(output / f"v1-top{top}-periods.csv")
        ref_v2 = _v2_holdings(pd.read_csv(reference_output / f"v2-top{top}-periods.csv"))
        oth_v2 = _v2_holdings(pd.read_csv(output / f"v2-top{top}-periods.csv"))
        ref_pos, oth_pos = _positions(ref_v1, "candidatas"), _positions(oth_v1, "candidatas")
        ref_ret = ref_v1.set_index("fecha")["retorno"]
        oth_ret = oth_v1.set_index("fecha")["retorno"]
        for date in dates:
            reference, other = _table(reference_cache, date), _table(other_cache, date)
            a, b = ref_pos.get(date, set()), oth_pos.get(date, set())
            ha, hb = ref_v2.get(date, set()), oth_v2.get(date, set())
            rows.append({"top": top, "fecha": date,
                         "elegibles_referencia": int(_eligible(reference).sum()),
                         "elegibles_variante": int(_eligible(other).sum()),
                         "miembros_referencia": len(reference), "miembros_variante": len(other),
                         "v1_retorno_referencia": ref_ret.get(date), "v1_retorno_variante": oth_ret.get(date),
                         "v1_comunes": len(a & b), "v1_jaccard": len(a & b) / len(a | b) if a | b else None,
                         "v2_comunes": len(ha & hb), "v2_jaccard": len(ha & hb) / len(ha | hb) if ha | hb else None})
            if top != PRIMARY_TOP:
                continue
            for symbol in sorted(a - b):
                exits.append({"fecha": date, "simbolo": symbol,
                              "motivo": classify_exit(symbol, reference, other, accredited)})
            for symbol in sorted(b - a):
                entries.append({"fecha": date, "simbolo": symbol, "motivo": classify_entry(symbol, reference, other)})
            if accredited:
                for symbol in sorted(ha):
                    row = other.loc[symbol] if symbol in other.index else None
                    reason = ("fuera_de_la_composicion" if row is None else
                              "identidad_no_acreditada" if pd.isna(row.get("entity_id")) else
                              "sin_precio_acreditado" if pd.isna(row.get("price_source")) else None)
                    if reason:
                        not_accredited.append({"fecha": date, "simbolo": symbol, "motivo": reason})
    by_rebalance = pd.DataFrame(rows)
    by_rebalance.to_csv(step / "comparacion-por-rebalanceo.csv", index=False)
    pd.DataFrame(exits, columns=["fecha", "simbolo", "motivo"]).to_csv(step / "atribucion-salidas.csv", index=False)
    pd.DataFrame(entries, columns=["fecha", "simbolo", "motivo"]).to_csv(step / "atribucion-entradas.csv", index=False)
    pd.DataFrame(not_accredited, columns=["fecha", "simbolo", "motivo"]).to_csv(
        step / "posiciones-base-no-acreditables.csv", index=False)
    primary = by_rebalance[by_rebalance.top == PRIMARY_TOP]
    return {
        "desde": base, "hasta": view, "fechas_comparadas": len(dates),
        "metricas": {f"top{top}": {"base": _metrics(reference_report, top), "variante": _metrics(report, top)}
                     for top in (10, 20)},
        "v1_jaccard_medio_top20": float(primary.v1_jaccard.mean()),
        "v2_jaccard_medio_top20": float(primary.v2_jaccard.mean()),
        "elegibles_medios": {"base": float(primary.elegibles_referencia.mean()),
                             "variante": float(primary.elegibles_variante.mean())},
        "salidas_por_motivo": pd.Series([e["motivo"] for e in exits]).value_counts().to_dict(),
        "entradas_por_motivo": pd.Series([e["motivo"] for e in entries]).value_counts().to_dict(),
        "posiciones_v2_base_no_acreditables": len(not_accredited),
        "posiciones_v2_base_no_acreditables_por_motivo":
            pd.Series([e["motivo"] for e in not_accredited]).value_counts().to_dict(),
    }


# --- Significación --------------------------------------------------------------------------

def overfitting(view: str) -> dict:
    """PBO/DSR (#12) sobre la familia documentada de configuraciones, con los rankings de la vista."""
    key, _start = VIEWS[view]
    variant = VARIANTS[key]
    with _context(variant):
        matrix = oa.reconstruct_matrix(variant.cache, progress=lambda *a, **k: None)
    matrix.to_csv(OUTPUT / view / "overfitting-returns.csv")
    return oa.analyze_matrix(matrix)


def regimes(view: str) -> dict:
    """Estabilidad temporal (#13): FF5 + Momentum sobre los mismos 36 trimestres 2016-07 → 2025-07."""
    factors = pd.read_csv(FACTORS)
    periods = pd.read_csv(OUTPUT / view / f"v1-top{PRIMARY_TOP}-periods.csv")
    merged = factors.drop(columns=["retorno", "excess_return"]).merge(
        periods[["fecha", "hasta", "retorno"]], on="fecha", how="left", suffixes=("", "_variante"))
    if merged.retorno.isna().any() or (merged.hasta != merged.hasta_variante).any():
        raise ValueError("Los trimestres de la vista no coinciden con los del #13.")
    merged["excess_return"] = merged["retorno"] - merged["RF"]
    inputs = merged[["fecha", "hasta", "retorno", "RF", "excess_return", *[c for c in factors.columns
                     if c not in {"fecha", "hasta", "retorno", "RF", "excess_return"}]]]
    inputs.to_csv(OUTPUT / view / "regimes-inputs.csv", index=False)
    audit = fs.analyze(inputs)
    return {"completa": audit["full"], "mitades": audit["halves"], "rolling": audit["rolling"],
            "episodios": audit["events"], "anios": audit["calendar_years"]}


def quarterly_excess(view: str, top: int = PRIMARY_TOP) -> dict:
    """Exceso trimestral V1 frente al SPY: media, t simple y número de trimestres por encima."""
    periods = pd.read_csv(OUTPUT / view / f"v1-top{top}-periods.csv").dropna(subset=["retorno"])
    excess = periods["retorno"] - periods["spy"]
    n = len(excess)
    se = float(excess.std(ddof=1) / np.sqrt(n)) if n > 1 else np.nan
    return {"n": n, "exceso_medio": float(excess.mean()), "error_estandar": se,
            "t": float(excess.mean() / se) if se else np.nan, "trimestres_por_encima": int((excess > 0).sum())}


def invested_span(view: str, top: int = PRIMARY_TOP) -> dict:
    """Métricas del V2 sobre el tramo realmente invertido (desde el primer rebalanceo ejecutado)."""
    periods = pd.read_csv(OUTPUT / view / f"v2-top{top}-periods.csv")
    nav = pd.read_csv(OUTPUT / view / f"v2-top{top}-nav.csv", index_col=0, parse_dates=True)
    first = pd.Timestamp(periods.fecha.iloc[0])
    nav = nav[nav.index >= first]
    years = (nav.index[-1] - nav.index[0]).days / 365.25
    result = {"inicio": str(nav.index[0].date()), "fin": str(nav.index[-1].date()), "anios": years}
    for column in nav:
        series = nav[column]
        risk = v1.daily_risk_metrics(series)
        result[column] = {"cagr": float((series.iloc[-1] / series.iloc[0]) ** (1 / years) - 1),
                          "sharpe": risk["sharpe"], "sharpe_se": v1.sharpe_standard_error(risk["sharpe"], years),
                          "max_drawdown": risk["max_drawdown"]}
    return result


def conclusion(summary: dict) -> str:
    """Regla fijada en el protocolo antes de ejecutar."""
    principal = summary["acreditado-38-2016"]
    m = principal["metricas"][f"top{PRIMARY_TOP}"]
    excess = m["estrategia"]["cagr"] - m["spy"]["cagr"]
    if excess <= 0:
        return "no_sobrevive"
    dsr = principal["overfitting"].get("dsr", {}).get("dsr", 0.0)
    significant = principal["exceso_trimestral"]["t"] > 1.96 and dsr > 0.95
    return "sobrevive_y_es_significativa" if significant else "sobrevive_sin_significacion"


def summarize() -> dict:
    summary: dict = {"issue": ISSUE, "reference": str(REFERENCE_OUTPUT.relative_to(config.BASE_DIR)),
                     "pasos": [compare(base, view) for base, view in STEPS]}
    for view in VIEWS:
        audit = json.loads((OUTPUT / view / "audit.json").read_text(encoding="utf-8"))
        item: dict = {"metricas": {f"top{top}": _metrics(audit, top) for top in (10, 20)},
                      "exceso_trimestral": quarterly_excess(view), "tramo_invertido": invested_span(view)}
        if "historical_validation" in audit:
            item["validacion"] = audit["historical_validation"]["summary"]
        summary[view] = item
    for view in ("operativo", "acreditado-38-2016"):
        try:
            summary[view]["overfitting"] = overfitting(view)
        except ValueError as exc:  # p. ej. cobertura < 50 % o candidatas insuficientes en una fecha
            summary[view]["overfitting"] = {"error": str(exc)}
    summary["acreditado-38-2016"]["regimenes"] = regimes("acreditado-38-2016")
    summary["conclusion"] = conclusion(summary)
    summary["analysis_sha256"] = fs.content_hash(Path(__file__))
    summary["artifacts"] = {f"{view}/{p.name}": fs.content_hash(p)
                            for view in VIEWS for p in sorted((OUTPUT / view).glob("*.csv"))}
    fua._save(OUTPUT / "summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", choices=sorted(VARIANTS))
    parser.add_argument("--evaluate", choices=sorted(VIEWS))
    parser.add_argument("--summarize", action="store_true")
    args = parser.parse_args()
    if args.prepare:
        manifest = prepare(args.prepare)
        print(json.dumps({"variant": args.prepare, "dates": len(manifest["dates"])}))
    if args.evaluate:
        report = evaluate(args.evaluate)
        print(json.dumps(fs._json_safe(report.get("historical_validation", {}).get("summary", {})),
                         ensure_ascii=False, indent=2))
    if args.summarize:
        print(json.dumps(fs._json_safe(summarize()), ensure_ascii=False, indent=2)[:4000])


if __name__ == "__main__":
    main()
