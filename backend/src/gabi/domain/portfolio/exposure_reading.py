"""¿Tengo demasiados huevos en una cesta? (#324): el reparto por sector y el peso por empresa, en una frase.

Plantillas fijas, sin IA; cada número del texto está en ``values``. Solo describe: el límite es **de aviso**
(la regla fija de GABI no limita sectores) y nada aquí cambia la selección ni ordena vender.
"""

import math


def _number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _pct(value: float) -> str:
    return f"{value:.1f}".replace(".", ",") + " %"


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " y " + items[-1]


def plan_sectors(sectors: list[dict], warnings: list[dict], limit_percent: float) -> dict:
    """The proposed portfolio by sector against the S&P 500 and the warning limit (percentages, 0–100)."""
    over = [row for row in warnings if row.get("kind") == "sector"]
    compared = [row for row in sectors if _number(row.get("difference_pp")) is not None]
    values: dict = {"limit_percent": limit_percent, "over_limit": [row["name"] for row in over]}
    parts = []
    if over:
        names = _join([f"{row['name']} ({_pct(row['weight_pct'])})" for row in over])
        values["over"] = {row["name"]: row["weight_pct"] for row in over}
        parts.append(f"{'Pasa' if len(over) == 1 else 'Pasan'} tu límite de aviso del {_pct(limit_percent)}: "
                     f"{names}.")
    if compared:
        most = max(compared, key=lambda row: row["difference_pp"])
        least = min(compared, key=lambda row: row["difference_pp"])
        values["most"] = {key: most[key] for key in ("sector", "weight_pct", "index_weight_pct")}
        sentence = (f"Frente al S&P 500, la cartera propuesta pesa más en {most['sector']} "
                    f"({_pct(most['weight_pct'])} frente a {_pct(most['index_weight_pct'])})")
        if least is not most and least["difference_pp"] < 0:
            values["least"] = {key: least[key] for key in ("sector", "weight_pct", "index_weight_pct")}
            sentence += (f" y menos en {least['sector']} ({_pct(least['weight_pct'])} frente a "
                         f"{_pct(least['index_weight_pct'])})")
        parts.append(sentence + ".")
    elif sectors:
        parts.append("Sin el peso de cada sector en el S&P 500 para comparar.")
    if not over and sectors:
        parts.append(f"Ningún sector pasa tu límite de aviso del {_pct(limit_percent)}.")
    if not sectors:
        parts.append("La cartera propuesta todavía no tiene empresas.")
    return {"text": " ".join(parts), "values": values}


def holdings_issuers(issuers: list[dict], limit: float) -> dict:
    """Mi cartera by issuer against the policy's limit per company (fractions, 0–1)."""
    values: dict = {"limit_percent": limit * 100, "positions": len(issuers)}
    if not issuers:
        return {"text": "Mi cartera no tiene posiciones valoradas.", "values": values}
    top = max(issuers, key=lambda row: row["weight"])
    over = [row for row in issuers if row.get("exceeds")]
    values |= {"top": {"issuer": top["issuer"], "weight_percent": top["weight"] * 100}, "over": len(over)}
    text = f"Tu mayor posición es {top['issuer']}, con el {_pct(top['weight'] * 100)} de tu cartera"
    if over:
        text += (f"; {len(over)} {'empresa pasa' if len(over) == 1 else 'empresas pasan'} tu límite por empresa "
                 f"del {_pct(limit * 100)}.")
    else:
        text += f"; ninguna pasa tu límite por empresa del {_pct(limit * 100)}."
    return {"text": text, "values": values}
