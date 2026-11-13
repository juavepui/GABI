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


def rebased(histories: dict[str, list[tuple[str, float | None]]]) -> tuple[str | None, list[dict]]:
    """Adjusted closes of every series as 100 at the first session all of them have a positive close.

    Sessions before that common start are dropped; a missing close stays None, never filled forward."""
    closes = {symbol: {day: value for day, value in rows
                       if isinstance(value, int | float) and math.isfinite(value) and value > 0}
              for symbol, rows in histories.items()}
    days = sorted({day for rows in histories.values() for day, _ in rows})
    start = next((day for day in days if all(day in series for series in closes.values())), None)
    if start is None:
        return None, []
    points = [{"date": day, "values": {symbol: (series[day] / series[start] * 100 if day in series else None)
                                       for symbol, series in closes.items()}}
              for day in days if day >= start]
    return start, points
