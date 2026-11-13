"""How often the S&P 500 meets each Checklist threshold (#171), and threshold presets.

Descriptive context only: a pass rate never changes a verdict, the Composite, the ranking or the
selection. The reference holds the values each issuer had on a dated audit; the rate is computed
for whatever threshold applies now, so an edited threshold or a preset shows its own rate.
"""

from bisect import bisect_left, bisect_right

from gabi.domain.market.checklist import RULES_BY_KEY, THRESHOLDS_VERSION, defaults

REFERENCE_VERSION = 1
# Fewer issuers than this with a value give no sector rate: one or two companies are not a reference.
MIN_SECTOR_VALUES = 5

PRESETS: dict[str, dict] = {
    "excel": {
        "label": "Excel original",
        "description": "Los umbrales de la hoja de cálculo de partida (vídeos de Javier DV, Memorias de Tiburón y "
                       "La Pizarra de Andrés), pensados para empresas de cualquier tamaño.",
        "values": {},
    },
    "large_cap": {
        "label": "Gran empresa S&P 500",
        "description": "Para grandes empresas cotizadas: relaja los umbrales que casi ninguna cumple en el S&P 500 "
                       "(directivos ≥ 1 %, cobertura de intereses ≥ 8x, PER ≤ 25x, EV/EBITDA ≤ 16x, "
                       "EV/EBIT ≤ 20x, EV/FCF ≤ 25x), redondeados cerca de su mediana en la auditoría de "
                       "referencia. Los demás umbrales son los del Excel.",
        "values": {"insiders_pct": 0.01, "interest_coverage": 8.0, "pe": 25.0, "ev_ebitda": 16.0, "ev_ebit": 20.0,
                   "ev_fcf": 25.0},
    },
}


def presets() -> list[dict]:
    """Every preset with its full threshold set, versioned with the thresholds."""
    base = defaults()
    return [{"key": key, "label": preset["label"], "description": preset["description"],
             "version": THRESHOLDS_VERSION, "values": base | preset["values"]} for key, preset in PRESETS.items()]


def preset_overrides(key: str) -> dict[str, float]:
    """The edits a preset makes over the defaults; ``KeyError`` for an unknown preset."""
    return dict(PRESETS[key]["values"])


def _passing(values: list[float], comparison: str, threshold: float) -> int:
    """How many of the sorted values meet the threshold."""
    if comparison == ">=":
        return len(values) - bisect_left(values, threshold)
    if comparison == ">":
        return len(values) - bisect_right(values, threshold)
    if comparison == "<=":
        return bisect_right(values, threshold)
    if comparison == "<":
        return bisect_left(values, threshold)
    raise ValueError(comparison)


def _rate(groups: list[dict], comparison: str, threshold: float) -> dict:
    evaluated = sum(len(group["values"]) + group.get("always_pass", 0) for group in groups)
    passed = sum(_passing(group["values"], comparison, threshold) + group.get("always_pass", 0) for group in groups)
    return {"rate": passed / evaluated if evaluated else None, "evaluated": evaluated}


def pass_rates(reference: dict | None, thresholds: dict[str, float], sector: str | None) -> dict[str, dict]:
    """Share of the reference universe, and of the sector, meeting each threshold that applies now."""
    if not reference or reference.get("version") != REFERENCE_VERSION:
        return {}
    result: dict[str, dict] = {}
    for key, sectors in reference["criteria"].items():
        rule = RULES_BY_KEY.get(key)
        threshold = thresholds.get(key)
        if rule is None or threshold is None or rule.comparison not in {">=", ">", "<=", "<"}:
            continue
        universe = _rate(list(sectors.values()), rule.comparison, threshold)
        own = _rate([sectors[sector]], rule.comparison, threshold) if sector in sectors else None
        if own is not None and own["evaluated"] < MIN_SECTOR_VALUES:
            own = {"rate": None, "evaluated": own["evaluated"]}
        result[key] = {"universe": universe, "sector": own}
    return result


def reference_from_values(as_of: str, issuers: int, values: dict[str, dict[str, dict]]) -> dict:
    """Compact reference: per criterion and sector, the sorted values and the issuers that always pass."""
    return {"version": REFERENCE_VERSION, "as_of": as_of, "issuers": issuers,
            "criteria": {key: {sector: {"values": sorted(round(value, 6) for value in group["values"]),
                                        "always_pass": group.get("always_pass", 0)}
                               for sector, group in sorted(sectors.items())}
                         for key, sectors in sorted(values.items())}}
