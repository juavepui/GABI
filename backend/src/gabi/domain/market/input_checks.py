"""Plausibility checks on the data GABI scores with (#295). Version ``input-checks-v1``.

What **blocks** (the data never enters the cache): a price download with a non-positive
price, an incoherent high/low, a non-finite value or a duplicated session
(``price_sync.clean_prices``, unchanged).

What **marks** (the data is kept and shown, with its reason):

- a Yahoo field outside its plausible range (``RANGES``);
- a daily price move larger than ``JUMP`` with no split recorded around that day;
- a Yahoo market capitalisation far from the cached close × the SEC shares outstanding.

A model version that applies this policy (``ModelVersion.input_checks``) scores a marked
field as missing: it counts as an explained absence, never as a value. A range mark
drops that field; a price jump drops the price-based metrics. The market-cap
cross-check only informs: issuers with several share classes report the shares of one
class, so it would drop sound multiples.
"""

import math

import pandas as pd

VERSION = "input-checks-v1"
BLOCKS = ("Precio no positivo o no finito", "Máximo o mínimo incoherentes con apertura y cierre",
          "Sesión duplicada")
# Field → (lowest plausible, highest plausible), both included. Ratios as Yahoo gives them:
# margins and returns as fractions, debt/equity in percent.
RANGES: dict[str, tuple[float, float]] = {
    "pe": (0.0, 1000.0), "peg": (0.0, 100.0), "pb": (0.0, 200.0), "ps": (0.0, 200.0), "ev_ebitda": (0.0, 500.0),
    "roe": (-5.0, 5.0), "roa": (-2.0, 2.0),
    "gross_margin": (-10.0, 1.0), "operating_margin": (-10.0, 1.0), "profit_margin": (-10.0, 1.0),
    "debt_to_equity": (0.0, 10000.0), "current_ratio": (0.0, 100.0),
    "revenue_growth_yoy": (-1.0, 50.0), "earnings_growth_yoy": (-50.0, 50.0), "revenue_growth_ttm_yoy": (-1.0, 50.0),
    "dividend_yield": (0.0, 0.5), "beta": (-10.0, 10.0), "market_cap": (1.0, 1e14),
}
JUMP = 0.5  # |daily return| above 50 %.
JUMP_WINDOW = 252  # Sessions whose jumps affect the price-based metrics.
SPLIT_MARGIN_DAYS = 3
PRICE_METRICS = ("momentum_6m", "momentum_12m", "rel_strength_6m", "price_vs_sma50", "price_vs_sma200",
                 "volatility", "max_drawdown", "sharpe_ratio", "sortino_ratio")
MARKET_CAP_TOLERANCE = 0.5  # ±50 % between Yahoo and close × SEC shares.


def _number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def check_fields(metrics: dict) -> list[dict]:
    """One mark per field outside its range; a non-finite number is marked too, an absent one is not."""
    marks = []
    for field, (low, high) in RANGES.items():
        raw = metrics.get(field)
        if raw is None:
            continue
        value = _number(raw)
        if value is None or not low <= value <= high:
            marks.append({"rule": "range", "field": field, "value": value, "low": low, "high": high,
                          "reason": f"Fuera del rango plausible [{low:g}, {high:g}]" if value is not None
                          else "No es un número finito"})
    return marks


def outside_range(field: str, value) -> tuple[float, float] | None:
    """The plausible range of ``field`` when a finite ``value`` falls outside it (#353); else None.

    For display only: it marks a shown figure, it never changes what a model scores with."""
    bounds, number = RANGES.get(field), _number(value)
    if bounds is None or number is None or bounds[0] <= number <= bounds[1]:
        return None
    return bounds


def check_jumps(prices: pd.DataFrame | None, splits: list[str] | None = None) -> list[dict]:
    """Daily moves above ``JUMP`` within the last ``JUMP_WINDOW`` sessions with no split recorded near them.

    Uses the adjusted close when present (dividends and splits already removed by the source),
    else the close; a split recorded within ``SPLIT_MARGIN_DAYS`` explains the move."""
    if prices is None or prices.empty:
        return []
    column = "adj_close" if "adj_close" in prices and prices["adj_close"].notna().any() else "close"
    series = prices[column].dropna()
    series = series[series > 0].sort_index().iloc[-(JUMP_WINDOW + 1):]
    moves = series.pct_change(fill_method=None).dropna()
    days = [pd.Timestamp(day) for day in (splits or [])]
    marks = []
    for day, move in moves[moves.abs() > JUMP].items():
        if any(abs((day - split).days) <= SPLIT_MARGIN_DAYS for split in days):
            continue
        marks.append({"rule": "jump", "field": "price", "date": day.date().isoformat(), "value": float(move),
                      "threshold": JUMP, "reason": f"Movimiento de {move * 100:+.0f} % en un día sin split registrado"})
    return marks


def check_market_cap(yahoo: float | None, close: float | None, shares: float | None) -> dict | None:
    """Yahoo's capitalisation against close × SEC shares; ``None`` when either side is missing or they agree."""
    yahoo, close, shares = _number(yahoo), _number(close), _number(shares)
    if not yahoo or not close or not shares or yahoo <= 0 or close <= 0 or shares <= 0:
        return None
    computed = close * shares
    gap = yahoo / computed - 1
    if abs(gap) <= MARKET_CAP_TOLERANCE:
        return None
    return {"rule": "market_cap", "field": "market_cap", "value": yahoo, "computed": computed, "gap": gap,
            "tolerance": MARKET_CAP_TOLERANCE,
            "reason": f"La capitalización de Yahoo difiere un {gap * 100:+.0f} % de precio × acciones de la SEC"}


def apply(metrics: dict, marks: list[dict]) -> dict:
    """The metrics a checked model scores with: marked fields, and the price metrics after a jump, as missing."""
    dropped = {mark["field"] for mark in marks if mark["rule"] == "range"}
    if any(mark["rule"] == "jump" for mark in marks):
        dropped |= set(PRICE_METRICS)
    return {key: (None if key in dropped else value) for key, value in metrics.items()}
