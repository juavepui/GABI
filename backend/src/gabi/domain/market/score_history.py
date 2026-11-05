"""Puntuación de cada día (#328): qué se guarda cada día y cómo se lee la evolución de una empresa.

La tarea diaria guarda la puntuación y el puesto de todo el universo con el modelo que puntuó; el día es el de
los precios usados, no el del reloj. Dos días de modelos distintos no se comparan: sus puntuaciones no se miden
igual. Es descriptivo: no cambia el ranking ni recomienda nada. Los números del texto están en ``values``.
"""

import math
from datetime import date

import pandas as pd

MONTHS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def _number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _day(value: str) -> str:
    day = date.fromisoformat(value[:10])
    return f"{day.day} {MONTHS[day.month - 1]} {day.year}"


def _decimal(value: float) -> str:
    return f"{value:.1f}".replace(".", ",")


def rows(table: pd.DataFrame) -> list[tuple[str, float, int]]:
    """(symbol, score, position) of every company with a score; the table is the ranking, best first."""
    result = []
    for position, (symbol, row) in enumerate(table.iterrows(), 1):
        score = _number(row.get("composite_score"))
        if score is not None:
            result.append((str(symbol), score, position))
    return result


def reading(points: list[dict], model_id: str) -> dict:
    """The company's recorded days, oldest first: `points` with day, model_id, score, rank and universe.

    Only the days of the active `model_id` are compared; earlier models are named, never mixed in."""
    values: dict = {"days": len(points), "model_id": model_id}
    if not points:
        return {"text": "Todavía no hay días guardados: la tarea diaria empieza a guardar la puntuación de cada "
                        "empresa a partir de ahora.", "values": values}
    same = [point for point in points if point["model_id"] == model_id]
    first = points[0]["day"]
    values |= {"first_day": first}
    text = f"Datos desde el {_day(first)} ({len(points)} {'día' if len(points) == 1 else 'días'} guardados)."
    others = sorted({point["model_id"] for point in points} - {model_id})
    if others:
        values["other_models"] = others
        text += " Los días anteriores puntuaba otro modelo y no se comparan."
    if len(same) >= 2:
        start, end = same[0], same[-1]
        values |= {"start": {k: start[k] for k in ("day", "score", "rank")},
                   "end": {k: end[k] for k in ("day", "score", "rank")}}
        change = end["score"] - start["score"]
        word = "ha subido" if change > 0 else "ha bajado" if change < 0 else "se ha mantenido"
        text += (f" Desde el {_day(start['day'])}, su puntuación {word}"
                 + (f" de {_decimal(start['score'])} a {_decimal(end['score'])}" if change else
                    f" en {_decimal(end['score'])}")
                 + f" y su puesto ha pasado del {start['rank']} al {end['rank']}.")
    elif same:
        text += " Hace falta al menos otro día con el mismo modelo para ver cómo cambia."
    return {"text": text, "values": values}
