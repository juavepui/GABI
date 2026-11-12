"""The tested engine's company metrics, scored live by GABI-MF-v5 (#347).

The historical evidence of GABI (#35: 20.1 % a year against 15.0 % for SPY in 2016-2025, ``operativo-38``) is for
the Composite as ``screener_asof`` computes it: SEC fundamentals with the fiscal alignment of #38. The live
ranking took PER, P/B, EV/EBITDA, operating margin and debt/equity from Yahoo and ROIC and revenue growth from
later rules, so its Top-20 shared 7 of 20 companies with the tested one (#291). The daily task stores the eight
company metrics of the Composite as that engine computes them today; v5 scores with them, nothing else.

A missing, outdated or other-rule row leaves the metric missing: it never falls back to Yahoo.
"""

import math
from datetime import date

RULE_VERSION = "engine-fundamentals-v1"
METRICS_VERSION = "sec-engine-v1"
METRICS = ("pe", "pb", "ev_ebitda", "roic", "operating_margin", "revenue_cagr_3y", "fcf_cagr_3y", "debt_to_equity")
# The task runs Tuesday to Saturday; a week covers a long weekend and a failed night, not a stale quarter.
MAX_AGE_DAYS = 7


def _finite(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def rows(table, as_of: date) -> list[dict]:
    """One stored row per company of the engine's table (indexed by symbol), its eight metrics finite or None."""
    return [{"symbol": str(symbol), "as_of": as_of.isoformat(), "rule_version": RULE_VERSION,
             **{metric: _finite(record.get(metric)) for metric in METRICS}}
            for symbol, record in table.to_dict("index").items()]


def stored(row: dict | None, today: date) -> dict[str, float | None]:
    """The eight metrics a ranking of ``today`` may use from a stored row; all missing if it cannot be used."""
    empty = dict.fromkeys(METRICS)
    if not row or row.get("rule_version") != RULE_VERSION:
        return empty
    try:
        age = (today - date.fromisoformat(str(row.get("as_of")))).days
    except ValueError:
        return empty
    if age < 0 or age > MAX_AGE_DAYS:
        return empty
    return {metric: _finite(row.get(metric)) for metric in METRICS}
