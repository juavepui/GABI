"""¿Está cara o barata para ella? (#326): cada múltiplo frente a su propia historia y frente a su sector.

Plantillas fijas, sin IA; cada número del texto está en ``values``. Las reglas:

- La referencia es la **mediana**, no los extremos: un año raro (beneficio hundido → PER disparado) estira el rango
  y haría parecer barato cualquier valor. El rango mínimo–máximo se dibuja, pero la frase se apoya en la mediana y
  en cuántos años cotizó más cara o más barata que hoy.
- «En línea» si hoy está a menos de un ``BAND`` (15 %) de la mediana; si no, «más barata» o «más cara».
- Con menos de ``MIN_YEARS`` años con dato, no se saca conclusión.
- Un múltiplo negativo o sin dato no se compara: se explica (pérdidas, caja negativa, banco…).
- «Barata» no es «buena»: si en la propia ficha fallan más criterios de rentabilidad y de calidad de la caja de
  los que pasan, la frase lo recuerda. Nada de esto recomienda comprar ni cambia la puntuación.
"""

import math

from gabi.domain.market.checklist import EV_MULTIPLES, MIN_HISTORY_VALUES, MULTIPLE_KEYS

BAND = 0.15
MIN_YEARS = MIN_HISTORY_VALUES
QUALITY_BLOCKS = ("Rentabilidad", "Calidad de la caja")
LABELS = {"pe": "PER", "ev_ebitda": "EV/EBITDA", "ev_ebit": "EV/EBIT", "ev_fcf": "EV/FCF"}


def _number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _decimal(value: float) -> str:
    return f"{value:.1f}".replace(".", ",")


def _side(current: float, reference: float) -> str:
    if current < reference * (1 - BAND):
        return "cheaper"
    if current > reference * (1 + BAND):
        return "pricier"
    return "inline"


def weak_quality(criteria: list[dict]) -> bool:
    """More profitability and cash-quality criteria fail than pass, with at least 3 of them evaluated."""
    verdicts = [item.get("verdict") for item in criteria if item.get("block") in QUALITY_BLOCKS]
    passed, failed = verdicts.count("pass"), verdicts.count("fail")
    return passed + failed >= 3 and failed > passed


def own(key: str, current, history: list, *, financial: bool, weak: bool) -> dict:
    """One multiple today against its own last years (`history`: that multiple per fiscal year, any order)."""
    label, value = LABELS[key], _number(current)
    years = [number for item in history if (number := _number(item)) is not None and number > 0]
    base = {"key": key, "label": label, "current": value, "min": min(years) if years else None,
            "max": max(years) if years else None, "median": None, "years": len(years),
            "cheaper_years": None, "pricier_years": None, "side": None}
    if financial and key in EV_MULTIPLES:
        return base | {"status": "not_applicable",
                       "text": f"{label}: no se usa en bancos y aseguradoras, porque su deuda es parte del negocio."}
    if value is None:
        return base | {"status": "missing", "text": f"{label}: sin dato de hoy (faltan sus cuentas o su precio)."}
    if value <= 0:
        return base | {"status": "negative",
                       "text": f"{label}: negativo, porque el último año tuvo pérdidas o caja negativa; "
                               "así no sirve para comparar."}
    if len(years) < MIN_YEARS:
        return base | {"status": "few_years",
                       "text": f"{label} de hoy: {_decimal(value)}. Solo hay {len(years)} años con dato en su "
                               f"historia; con menos de {MIN_YEARS} no se saca conclusión."}
    ordered = sorted(years)
    middle = len(ordered) // 2
    median = ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2
    pricier, cheaper = sum(year > value for year in years), sum(year < value for year in years)
    side = _side(value, median)
    if side == "cheaper":
        text = (f"{label} de {_decimal(value)}: más barata de lo habitual en ella (mediana de {_decimal(median)}); "
                f"cotizó más cara en {pricier} de sus últimos {len(years)} años.")
        if weak:
            text += " Ojo: su rentabilidad y la calidad de su caja son flojas, y a veces está barata por eso."
    elif side == "pricier":
        text = (f"{label} de {_decimal(value)}: más cara de lo habitual en ella (mediana de {_decimal(median)}); "
                f"cotizó más barata en {cheaper} de sus últimos {len(years)} años.")
    else:
        text = f"{label} de {_decimal(value)}: en línea con lo habitual en ella (mediana de {_decimal(median)})."
    return base | {"status": "ok", "median": median, "cheaper_years": cheaper, "pricier_years": pricier,
                   "side": side, "text": text}


def sector(key: str, current, median, peers: int) -> dict:
    """One multiple today against the median of its sector peers."""
    label, value, reference = LABELS[key], _number(current), _number(median)
    base = {"key": key, "label": label, "current": value, "median": reference, "peers": peers, "side": None}
    if value is None or value <= 0 or reference is None or reference <= 0:
        return base | {"status": "missing", "text": f"{label}: sin comparación con su sector."}
    side = _side(value, reference)
    word = {"cheaper": "más barata que", "pricier": "más cara que", "inline": "en línea con"}[side]
    return base | {"status": "ok", "side": side,
                   "text": f"{label} de {_decimal(value)}: {word} la mediana de su sector ({_decimal(reference)}, "
                           f"{peers} empresas)."}


def own_readings(current: dict, by_year: list[dict], criteria: list[dict], *, financial: bool) -> list[dict]:
    weak = weak_quality(criteria)
    return [own(key, current.get(key), [row.get(key) for row in by_year], financial=financial, weak=weak)
            for key in MULTIPLE_KEYS]


def sector_readings(current: dict, medians: dict, peers: int) -> list[dict]:
    return [sector(key, current.get(key), (medians.get(key) or {}).get("median"), peers) for key in MULTIPLE_KEYS]
