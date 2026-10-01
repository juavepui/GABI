"""Which compared company is better on each metric, from the scoring directions; nothing else is inferred."""

import math

SCORES = ("composite_score", "value_score", "quality_score", "momentum_score", "risk_score", "confidence",
          "score_coverage")


def positions(values: dict[str, dict[str, float | None]], directions: dict[str, str]) -> dict[str, dict]:
    """Per metric with a direction: 1 = best and 0 = worst among the compared companies, linear in between.

    Metrics without a direction (price, capitalisation...) are left out: there is no better or worse.
    A metric where every available value is equal, or with fewer than two values, has no winner (None)."""
    result: dict[str, dict] = {}
    for metric, direction in directions.items():
        cells = {symbol: row.get(metric) for symbol, row in values.items()}
        known = {symbol: value for symbol, value in cells.items()
                 if isinstance(value, int | float) and math.isfinite(value)}
        low, high = (min(known.values()), max(known.values())) if len(known) >= 2 else (0.0, 0.0)
        result[metric] = {
            symbol: None if symbol not in known or high == low else
            ((known[symbol] - low) / (high - low) if direction == "higher" else (high - known[symbol]) / (high - low))
            for symbol in cells}
    return result
