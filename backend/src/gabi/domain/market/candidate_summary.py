"""«Por qué está aquí» (#184): one plain sentence per company from values the ranking already computed.

It describes the score, it never changes it nor recommends anything. The rules are fixed:

- Strong block: a block score of at least 70 points; at most the two highest are named, best first.
- Weak block: the lowest block score when it is 30 points or less.
- Main warning, the first that applies: fewer than 70 % of the scored metrics available, results
  within 14 days, a maximum drawdown of 50 % or more.

A missing block is never strong nor weak; with no block at all the sentence says so.
"""

import math
from collections.abc import Mapping

BLOCKS = {"value": "valoración", "quality": "calidad", "momentum": "momentum", "risk": "riesgo"}
STRONG_POINTS = 70.0
WEAK_POINTS = 30.0
MIN_COVERAGE = 0.70
EARNINGS_DAYS = 14
DRAWDOWN = -0.50


def _number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _decimal(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}".replace(".", ",").replace("-", "−")


def _names(keys: list[str]) -> str:
    names = [BLOCKS[key] for key in keys]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " y " + names[-1]


def _warning(row: Mapping) -> tuple[str | None, str | None]:
    coverage = _number(row.get("score_coverage"))
    if coverage is not None and coverage < MIN_COVERAGE:
        return "coverage", f"Datos incompletos ({_decimal(coverage * 100, 0)} % de las métricas)"
    days = _number(row.get("next_earnings_days"))
    if days is not None and 0 <= days <= EARNINGS_DAYS:
        days = int(days)
        when = "hoy" if days == 0 else "mañana" if days == 1 else f"en {days} días"
        return "earnings", "Resultados " + when
    drawdown = _number(row.get("max_drawdown"))
    if drawdown is not None and drawdown <= DRAWDOWN:
        return "drawdown", f"Caída máxima {_decimal(drawdown * 100)} %"
    return None, None


def summarize(row: Mapping) -> dict:
    """Strong blocks, weak block, main warning and the sentence that joins them with « · »."""
    blocks = {key: _number(row.get(key + "_score")) for key in BLOCKS}
    known = {key: value for key, value in blocks.items() if value is not None}
    ranked = sorted(known, key=lambda key: (-known[key], list(BLOCKS).index(key)))
    strengths = [key for key in ranked if known[key] >= STRONG_POINTS][:2]
    lowest = ranked[-1] if ranked else None
    weakness = lowest if lowest is not None and known[lowest] <= WEAK_POINTS else None
    warning, warning_text = _warning(row)
    parts = []
    if strengths:
        parts.append("Fuerte en " + _names(strengths))
    if weakness:
        parts.append("Débil en " + BLOCKS[weakness])
    if known and not strengths and not weakness:
        parts.append("Sin bloques destacados")
    if not known:
        parts.append("Sin bloques del score calculados")
    if warning_text:
        parts.append(warning_text)
    return {"text": " · ".join(parts), "blocks": blocks, "strengths": strengths, "weakness": weakness,
            "warning": warning}
