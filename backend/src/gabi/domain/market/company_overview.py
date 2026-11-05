"""Las primeras líneas de la ficha (#310): qué es la empresa, cómo puntúa y cuánto suele moverse con sus resultados.

Plantillas fijas, sin IA: cada número del texto está en ``values``. Nada de esto cambia la puntuación ni
recomienda comprar o vender.

- Nivel de la puntuación: «alta» desde 70, «baja» hasta 40 y «media» entre ambos (los mismos 70/30 de los
  apartados fuertes y débiles del resumen del ranking serían demasiado estrictos para la nota global).
- Punto débil: el apartado más bajo si no llega a 50 puntos; si además hay un aviso del resumen del ranking
  (datos incompletos, resultados pronto o una caída muy grande), se nombra el aviso.
- Movimiento típico: media de la reacción absoluta del precio en las últimas ``MAX_REACTIONS`` presentaciones
  con dato. Con menos de ``MIN_REACTIONS`` se marca como orientativo.
"""

import math
from collections.abc import Mapping

HIGH, LOW = 70.0, 40.0
WEAK_BLOCK = 50.0
MAX_REACTIONS, MIN_REACTIONS = 8, 4
BLOCKS = {"value": "la valoración (si su precio es razonable)", "quality": "la calidad del negocio",
          "momentum": "la tendencia de su cotización", "risk": "el riesgo"}


def _number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _decimal(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def headline(*, name: str | None, symbol: str, sector: str | None, row: Mapping, rank: int, universe: int,
             warning_text: str | None) -> dict:
    """Two plain sentences: what the company is, and how it scores with its weakest point."""
    who = name or symbol
    first = f"{who} es una empresa del sector {sector}." if sector else f"{who}: sector no disponible."
    score = _number(row.get("composite_score"))
    blocks = {key: _number(row.get(key + "_score")) for key in BLOCKS}
    known = {key: value for key, value in blocks.items() if value is not None}
    weakest = min(known, key=lambda key: (known[key], list(BLOCKS).index(key))) if known else None
    values: dict = {"composite_score": score, "rank": rank, "universe": universe}
    if score is None:
        second, level = "Hoy no tiene puntuación GABI: le faltan datos para calcularla.", None
    else:
        level = "high" if score >= HIGH else "low" if score <= LOW else "medium"
        word = {"high": "alta", "medium": "media", "low": "baja"}[level]
        second = f"Su puntuación GABI es {word}: {_decimal(score)} de 100, puesto {rank} de {universe}"
        if warning_text:
            second += f"; ojo: {warning_text[0].lower() + warning_text[1:]}."
        elif weakest is not None and known[weakest] < WEAK_BLOCK:
            second += f"; su punto más débil es {BLOCKS[weakest]} ({_decimal(known[weakest])} de 100)."
            values["weakest"] = {"block": weakest, "score": known[weakest]}
        else:
            second += "."
    return {"text": first + " " + second, "level": level, "values": values}


def typical_move(reactions: list) -> dict:
    """Mean absolute price reaction of the latest reports with data, newest last in `reactions`.

    `reactions` are percentages (6.3 = 6,3 %) in date order; missing ones are skipped."""
    known = [abs(value) for value in (_number(item) for item in reactions) if value is not None][-MAX_REACTIONS:]
    if not known:
        return {"count": 0, "mean_abs_pct": None, "enough": False, "max_abs_pct": None,
                "text": "Sin datos de cómo reaccionó el precio a sus presentaciones de resultados."}
    mean = sum(known) / len(known)
    enough = len(known) >= MIN_REACTIONS
    text = (f"El día de resultados su precio suele moverse un ±{_decimal(mean)} % (media de las últimas "
            f"{len(known)} presentaciones; la mayor, ±{_decimal(max(known))} %).")
    if not enough:
        text += f" Son menos de {MIN_REACTIONS}: tómalo solo como orientación."
    return {"count": len(known), "mean_abs_pct": mean, "max_abs_pct": max(known), "enough": enough, "text": text}
