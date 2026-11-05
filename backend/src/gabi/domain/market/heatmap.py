"""Mapa de calor del universo (#311): cada empresa con su sector, tamaño en bolsa y puntuación GABI.

Solo ordena y agrupa valores que el ranking ya calculó; no puntúa nada. El tamaño de cada cuadro es el valor en
bolsa (capitalización); el color, la puntuación. Una empresa sin puntuación va en gris con su motivo; una sin valor
en bolsa no puede dibujarse con su tamaño y se lista aparte, también con su motivo.

Bandas de color (las de «alta / media / baja» de la ficha, #310, con dos tramos más para leer el mapa):
80 o más, 70-80, 40-70, 30-40 y menos de 30.
"""

import math

import pandas as pd

BANDS = ((80.0, "very_high"), (70.0, "high"), (40.0, "medium"), (30.0, "low"), (-math.inf, "very_low"))
TOP_SHARE = 0.20  # «Entre las mejores»: the top fifth of the scored companies.


def _number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _text(value) -> str | None:
    return None if value is None or value != value else str(value)


def band(score: float | None) -> str:
    if score is None:
        return "none"
    return next(name for limit, name in BANDS if score >= limit)


def reason(score: float | None, cap: float | None) -> str | None:
    if score is None:
        return "Sin puntuación: le faltan datos de su precio o de sus cuentas para calcularla."
    if cap is None:
        return "Sin valor en bolsa guardado: no se puede dibujar con su tamaño."
    return None


def build(table: pd.DataFrame) -> dict:
    """`table`: the ranking, indexed by symbol and sorted by score (position 1 = best)."""
    companies = []
    for position, (symbol, row) in enumerate(table.iterrows(), 1):
        score, cap = _number(row.get("composite_score")), _number(row.get("market_cap"))
        cap = cap if cap is not None and cap > 0 else None
        companies.append({"symbol": str(symbol), "name": _text(row.get("name")),
                          "sector": _text(row.get("sector")) or "Sin sector", "market_cap": cap,
                          "composite_score": score, "rank": position if score is not None else None,
                          "band": band(score), "reason": reason(score, cap)})
    scored = sorted((item for item in companies if item["composite_score"] is not None),
                    key=lambda item: item["rank"])
    top = {item["symbol"] for item in scored[:math.ceil(len(scored) * TOP_SHARE)]}
    sectors = []
    for name in sorted({item["sector"] for item in companies}):
        members = [item for item in companies if item["sector"] == name]
        scores = [item["composite_score"] for item in members if item["composite_score"] is not None]
        caps = [item["market_cap"] for item in members if item["market_cap"] is not None]
        sectors.append({"sector": name, "companies": len(members), "scored": len(scores),
                        "mean_score": sum(scores) / len(scores) if scores else None,
                        "in_top": sum(item["symbol"] in top for item in members),
                        "market_cap": sum(caps) if caps else None})
    sectors.sort(key=lambda item: (-(item["mean_score"] if item["mean_score"] is not None else -1), item["sector"]))
    return {"companies": companies, "sectors": sectors, "scored": len(scored), "top_count": len(top),
            "top_share": TOP_SHARE, "bands": [{"band": name, "min_score": None if limit == -math.inf else limit}
                                              for limit, name in BANDS]}
