"""Versioned investment card (#246): the investor's thesis, scenarios and invalidation, and its states.

Version ``investment-card-v1``. The quantitative selection only prioritises what to
analyse; the decision is the investor's, and the card records it explicitly:

- ``incompleta`` → ``analizada`` → ``publicada``; any of them → ``descartada`` with a
  reason. Discarding is a valid outcome: there may be no opportunity defensible
  enough. A published version is immutable; changing it opens a new version.
- Publishing requires the whole card: a thesis in at most three lines, the
  discrepant expectation (what the market prices that the investor disagrees with),
  bear ≤ base ≤ bull prices with their assumptions, dated catalysts, risks, at
  least one measurable invalidation condition (metric, source, threshold,
  persistence, review date), the subjective confidence and the review date.
- Data coverage, statistical evidence and subjective confidence are kept apart;
  none of them is a probability of profit.

- The planned position (euros) is required to publish, so that the card shows
  what it costs, how it changes the portfolio's concentration against the #248
  limits, and how the base scenario compares with the passive alternative: the
  S&P 500 in euros with the investor's own contributions. That comparison uses
  the index's past return, never a forecast.

Nothing here reads market data: the snapshot of inputs is captured by the use case.
"""

from datetime import date

VERSION = "investment-card-v1"
STATES = ("incompleta", "analizada", "publicada", "descartada")
EDITABLE = ("incompleta", "analizada")
CONFIDENCE = ("baja", "media", "alta")
OPERATORS = ("<", "<=", ">", ">=")
SCENARIOS = ("bear", "base", "bull")
MAX_THESIS_LINES = 3
MAX_TEXT = 2000
MAX_ITEMS = 10
NOT_A_PROBABILITY = ("La cobertura del dato, la evidencia estadística y la confianza subjetiva son cosas distintas; "
                     "ninguna es una probabilidad de beneficio.")


class CardError(ValueError):
    """A card that cannot be stored or moved to the requested state; the message is for the investor."""


def _text(value, field: str, *, limit: int = MAX_TEXT) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise CardError(f"«{field}» debe ser texto.")
    text = value.strip()
    if len(text) > limit:
        raise CardError(f"«{field}» supera {limit} caracteres.")
    return text


def _number(value, field: str) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise CardError(f"«{field}» debe ser un número.") from exc
    if number != number or number in (float("inf"), float("-inf")) or abs(number) > 1e12:
        raise CardError(f"«{field}» debe ser un número finito.")
    return number


def _day(value, field: str) -> str | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError as exc:
        raise CardError(f"«{field}» debe ser una fecha AAAA-MM-DD.") from exc


def _items(value, field: str) -> list:
    if value is None:
        return []
    if not isinstance(value, list):
        raise CardError(f"«{field}» debe ser una lista.")
    if len(value) > MAX_ITEMS:
        raise CardError(f"«{field}» admite como máximo {MAX_ITEMS} elementos.")
    return value


def _position(value) -> float | None:
    amount = _number(value, "importe previsto")
    if amount is not None and not 0 < amount <= 1e8:
        raise CardError("El importe previsto debe ser positivo.")
    return amount


def normalize(raw: dict) -> dict:
    """The card content with types checked and blanks removed; it may still be incomplete."""
    if not isinstance(raw, dict):
        raise CardError("La ficha debe ser un objeto.")
    thesis = [line for line in (_text(item, "tesis", limit=300) for item in _items(raw.get("thesis"), "tesis"))
              if line]
    if len(thesis) > MAX_THESIS_LINES:
        raise CardError("La tesis admite como máximo tres líneas.")
    scenarios = {}
    source = raw.get("scenarios") or {}
    if not isinstance(source, dict):
        raise CardError("«escenarios» debe ser un objeto.")
    for name in SCENARIOS:
        item = source.get(name) or {}
        price = _number(item.get("price"), f"precio {name}")
        if price is not None and price <= 0:
            raise CardError(f"El precio {name} debe ser positivo.")
        scenarios[name] = {"price": price, "assumptions": _text(item.get("assumptions"), f"supuestos {name}")}
    catalysts = []
    for item in _items(raw.get("catalysts"), "catalizadores"):
        description = _text((item or {}).get("description"), "catalizador", limit=500)
        if description:
            catalysts.append({"description": description, "horizon": _day(item.get("horizon"), "horizonte")})
    risks = [risk for risk in (_text(item, "riesgo", limit=500) for item in _items(raw.get("risks"), "riesgos"))
             if risk]
    invalidation = []
    for item in _items(raw.get("invalidation"), "invalidación"):
        item = item or {}
        operator = item.get("operator") or None
        if operator is not None and operator not in OPERATORS:
            raise CardError("El operador de invalidación debe ser <, <=, > o >=.")
        persistence = _number(item.get("persistence"), "persistencia")
        if persistence is not None and (persistence < 1 or persistence != int(persistence) or persistence > 20):
            raise CardError("La persistencia es un número entero de periodos entre 1 y 20.")
        condition = {"description": _text(item.get("description"), "condición", limit=500),
                     "metric": _text(item.get("metric"), "métrica", limit=100),
                     "source": _text(item.get("source"), "fuente", limit=200), "operator": operator,
                     "threshold": _number(item.get("threshold"), "umbral"),
                     "persistence": int(persistence) if persistence is not None else None,
                     "review_by": _day(item.get("review_by"), "revisión de la condición")}
        if any(value not in (None, "") for value in condition.values()):
            invalidation.append(condition)
    confidence = raw.get("confidence") or None
    if confidence is not None and confidence not in CONFIDENCE:
        raise CardError("La confianza subjetiva es baja, media o alta.")
    return {"thesis": thesis, "discrepancy": _text(raw.get("discrepancy"), "expectativa discrepante"),
            "scenarios": scenarios, "sensitivity": _text(raw.get("sensitivity"), "sensibilidad"),
            "catalysts": catalysts, "risks": risks, "invalidation": invalidation, "confidence": confidence,
            "review_due": _day(raw.get("review_due"), "fecha de revisión"),
            "position_eur": _position(raw.get("position_eur")),
            "notes": _text(raw.get("notes"), "notas")}


def missing(content: dict) -> list[str]:
    """What is still missing to publish, in the investor's words; empty when the card is complete."""
    gaps = []
    if not content["thesis"]:
        gaps.append("la tesis")
    if not content["discrepancy"]:
        gaps.append("la expectativa discrepante")
    prices = [content["scenarios"][name]["price"] for name in SCENARIOS]
    if any(price is None for price in prices) or any(not content["scenarios"][name]["assumptions"]
                                                      for name in SCENARIOS):
        gaps.append("los tres escenarios con precio y supuestos")
    elif not prices[0] <= prices[1] <= prices[2]:
        gaps.append("escenarios ordenados (bear ≤ base ≤ bull)")
    if not any(item["horizon"] for item in content["catalysts"]):
        gaps.append("un catalizador con horizonte")
    if not content["risks"]:
        gaps.append("un riesgo")
    if not any(all(item[key] not in (None, "") for key in
                   ("description", "metric", "source", "operator", "threshold", "persistence", "review_by"))
               for item in content["invalidation"]):
        gaps.append("una condición de invalidación medible (métrica, fuente, umbral, persistencia y revisión)")
    if content["confidence"] is None:
        gaps.append("la confianza subjetiva")
    if content["review_due"] is None:
        gaps.append("la fecha de revisión")
    if content.get("position_eur") is None:
        gaps.append("el importe previsto de la posición")
    return gaps


def transition(state: str, target: str, content: dict, *, today: date, reason: str = "") -> str:
    """The new state, or CardError explaining why the move is not allowed."""
    if target not in STATES or target == "incompleta":
        raise CardError("Estado de destino no válido.")
    if state == "descartada":
        raise CardError("Una ficha descartada no cambia de estado; abre una versión nueva.")
    if target == "descartada":
        if not reason.strip():
            raise CardError("Indica por qué se descarta: también es una conclusión válida.")
        return target
    if state == "publicada":
        raise CardError("Una versión publicada no se modifica; abre una versión nueva.")
    if target == "analizada":
        if not content["thesis"] or any(content["scenarios"][name]["price"] is None for name in SCENARIOS):
            raise CardError("Para marcarla como analizada hacen falta la tesis y los tres precios de escenario.")
        return target
    gaps = missing(content)
    if gaps:
        raise CardError("Falta " + "; ".join(gaps) + ".")
    if content["review_due"] is not None and date.fromisoformat(content["review_due"]) <= today:
        raise CardError("La fecha de revisión debe ser futura.")
    return target


def scenario_returns(content: dict, price: float | None) -> dict[str, float | None]:
    """Each scenario's move from the price captured at publication; ``None`` without a price."""
    return {name: (content["scenarios"][name]["price"] / price - 1
                   if price and content["scenarios"][name]["price"] is not None else None) for name in SCENARIOS}


def position_costs(amount_eur: float | None, profile: dict | None) -> dict | None:
    """Buying and later selling the planned amount through the investor's broker (commission and FX)."""
    if amount_eur is None or not profile:
        return None
    fixed = float(profile.get("commission_fixed_eur") or 0.0)
    rate = float(profile.get("commission_pct") or 0.0) + float(profile.get("fx_cost_pct") or 0.0)
    one_way = fixed + rate * amount_eur
    return {"amount_eur": amount_eur, "buy_eur": one_way, "round_trip_eur": 2 * one_way,
            "round_trip_share": 2 * one_way / amount_eur}


def concentration(symbol: str, sector: str | None, amount_eur: float | None, exposure: dict | None,
                  caps: dict | None) -> dict | None:
    """Issuer and sector weights now and after adding the planned amount, against the policy caps."""
    if amount_eur is None or exposure is None or caps is None:
        return None
    total = float(exposure.get("total_eur") or 0.0)
    issuer_now = sum(row["weight"] * total for row in exposure.get("issuers", []) if symbol in row.get("symbols", []))
    sector_now = sum(row["weight"] * total for row in exposure.get("sectors", []) if sector and row["name"] == sector)
    after = total + amount_eur
    issuer_after, sector_after = (issuer_now + amount_eur) / after, (sector_now + amount_eur) / after
    return {"portfolio_eur": total, "issuer_weight_now": issuer_now / total if total else 0.0,
            "issuer_weight_after": issuer_after, "issuer_cap": caps["max_issuer_weight"],
            "issuer_exceeds": issuer_after > caps["max_issuer_weight"] + 1e-9, "sector": sector,
            "sector_weight_now": sector_now / total if total else 0.0,
            "sector_weight_after": sector_after if sector else None, "sector_cap": caps["max_sector_weight"],
            "sector_exceeds": bool(sector) and sector_after > caps["max_sector_weight"] + 1e-9}


def passive_comparison(content: dict, price: float | None, published: date, index_annual: float | None,
                       costs: dict | None) -> dict | None:
    """The base scenario, annualised to the review date and net of round-trip costs, beside the index's past
    return in euros with the investor's contributions. Not a forecast of either."""
    base = content["scenarios"]["base"]["price"]
    if price is None or base is None or content["review_due"] is None:
        return None
    days = (date.fromisoformat(content["review_due"]) - published).days
    if days <= 0:
        return None
    gross = base / price
    net = gross * (1 - (costs or {}).get("round_trip_share", 0.0))
    annual = net ** (365 / days) - 1 if net > 0 else -1.0
    return {"horizon_days": days, "base_move": gross - 1, "base_annualised_net": annual,
            "costs_included": costs is not None, "index_annualised_past": index_annual,
            "margin_over_index": annual - index_annual if index_annual is not None else None,
            "note": "El índice es su rentabilidad pasada con tus aportaciones; ninguna cifra es una previsión."}
