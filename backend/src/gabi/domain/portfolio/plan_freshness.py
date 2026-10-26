"""Whether a saved decision plan still matches today's ranking (#191); never recalculates the plan."""

from datetime import date
from math import isfinite

# Points on the 0-100 Composite Score: a smaller move is ordinary noise between data refreshes.
SCORE_CHANGE = 5.0


def _score(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def freshness(created_at: str, decisions: list[dict], current: dict[str, float | None],
              min_score: float | None, today: date) -> dict:
    """Each position the plan buys or keeps, against its score today with the same frozen weights.

    A change is material when a position no longer has a score, falls below the plan's own minimum,
    or its score moved by `SCORE_CHANGE` points or more."""
    positions = [row for row in decisions if (_score(row.get("target_pct")) or 0) > 0]
    changes = []
    for row in positions:
        symbol = str(row["symbol"])
        saved, now = _score(row.get("score")), _score(current.get(symbol))
        if now is None:
            label = "Ya no tiene score en el ranking actual"
        elif min_score is not None and now < min_score:
            label = f"Por debajo del score mínimo del plan ({min_score:g})"
        elif saved is not None and abs(now - saved) >= SCORE_CHANGE:
            label = f"Su score ha cambiado {SCORE_CHANGE:g} puntos o más"
        else:
            continue
        changes.append({"symbol": symbol, "saved_score": saved, "current_score": now, "label": label})
    # Saved with the wall clock; `today` may be an earlier injected date: never a negative age.
    age = max(0, (today - date.fromisoformat(created_at[:10])).days)
    return {"age_days": age, "today": today.isoformat(),
            "positions": len(positions), "threshold_points": SCORE_CHANGE, "material": bool(changes),
            "changes": changes}
