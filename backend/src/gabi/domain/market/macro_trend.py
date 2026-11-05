"""¿Esto sube, baja o es lo normal? (#327): la historia de cada serie macro, resumida y leída con reglas fijas.

- Un punto por mes: el último dato publicado de ese mes (así una serie diaria y una mensual se ven igual y no se
  mandan miles de puntos).
- Dirección en 12 meses: «subiendo» o «bajando» si el cambio supera ``MOVE_SHARE`` (10 %) del recorrido de sus
  últimos 5 años (máximo menos mínimo); si no, «estable». Con menos de 13 meses no se dice.
- Nivel: por encima o por debajo de su **mediana de 5 años**, o «en su nivel habitual» si está a menos del mismo
  10 % del recorrido. Con menos de 24 meses no se dice.

Es contexto: no predice nada ni cambia la puntuación de las empresas. Los números del texto están en ``values``.
"""

from datetime import date

MOVE_SHARE = 0.10
TREND_MONTHS = 12
MIN_LEVEL_MONTHS = 24
WINDOW_MONTHS = 60
# Units whose values read well in a sentence; others («USD», «personas») keep the words without the figure.
SPOKEN_UNITS = {"%", "% interanual", "p. p.", "índice"}


def monthly(points: list[tuple[date, float]]) -> list[tuple[date, float]]:
    """The last value of each month, oldest first; `points` in any order."""
    by_month: dict[tuple[int, int], tuple[date, float]] = {}
    for day, value in sorted(points):
        by_month[(day.year, day.month)] = (day, value)
    return [by_month[key] for key in sorted(by_month)][-WINDOW_MONTHS:]


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def _number(value: float) -> str:
    """One decimal; two below 1, where one would turn 0,08 and 0,03 into «0,1» and «0,0»."""
    digits = 2 if abs(value) < 1 else 1
    return f"{value:.{digits}f}".replace(".", ",").replace("-", "−")


def read(points: list[tuple[date, float]], unit: str) -> dict:
    """Direction over 12 months and level against the 5-year median, with the monthly points."""
    series = monthly(points)
    values = [value for _, value in series]
    result: dict = {"points": [{"date": day.isoformat(), "value": value} for day, value in series],
                    "direction": None, "level": None, "median": None, "months": len(series), "text": None}
    if len(series) <= TREND_MONTHS:
        result["text"] = "Todavía no hay 12 meses de datos guardados para ver hacia dónde va."
        return result
    span = max(values) - min(values)
    threshold = span * MOVE_SHARE
    start, end = values[-1 - TREND_MONTHS], values[-1]
    change = end - start
    direction = "up" if change > threshold else "down" if change < -threshold else "flat"
    words = {"up": "Subiendo", "down": "Bajando", "flat": "Estable"}[direction]
    spoken = unit in SPOKEN_UNITS
    text = f"{words} en los últimos 12 meses" + (f" (de {_number(start)} a {_number(end)})" if spoken else "") + "."
    result |= {"direction": direction, "start": start, "end": end}
    if len(series) >= MIN_LEVEL_MONTHS:
        median = _median(values)
        level = "above" if end > median + threshold else "below" if end < median - threshold else "usual"
        years = len(series) // 12
        where = {"above": "por encima de", "below": "por debajo de", "usual": "en el nivel habitual de"}[level]
        text += f" Hoy está {where} sus últimos {years} años" + (
            f" (mediana de {_number(median)})" if spoken else "") + "."
        result |= {"level": level, "median": median, "years": years}
    result["text"] = text
    return result
