"""¿Aguantaría una crisis? ¿Compensa elegir acciones? (#325): las crisis en euros y las opciones, en una frase.

Plantillas fijas, sin IA; cada número del texto está en ``values``. Las crisis son golpes declarados, no
previsiones, y pasar lo que aceptas perder es motivo para revisar el plan, nunca para vender. La comparación entre
elegir acciones y comprar el índice usa datos del pasado y no demuestra que la regla de GABI gane al S&P 500.
"""


def _eur(value: float) -> str:
    """«3.850 €», sin decimales y con punto de miles."""
    return f"{abs(value):,.0f}".replace(",", ".") + " €"


def _pct(value: float) -> str:
    return f"{abs(value) * 100:.1f}".replace(".", ",") + " %"


def scenarios(rows: list[dict], loss_tolerance: float, value_eur: float) -> dict:
    """The declared shocks against what the investor accepts to lose (fraction of today's value)."""
    tolerance_eur = loss_tolerance * value_eur
    values: dict = {"value_eur": value_eur, "loss_tolerance": loss_tolerance, "tolerance_eur": tolerance_eur,
                    "scenarios": len(rows)}
    if not rows or value_eur <= 0:
        return {"text": "Sin valor actual con el que calcular las crisis.", "values": values}
    worst = min(rows, key=lambda row: row["change_eur"])
    over = [row for row in rows if row.get("exceeds_tolerance")]
    values |= {"worst": {"label": worst["label"], "change": worst["change"], "change_eur": worst["change_eur"]},
               "over": len(over)}
    text = (f"Con los {_eur(value_eur)} de hoy, la peor de estas crisis ({worst['label']}) te quitaría "
            f"{_eur(worst['change_eur'])}, el {_pct(worst['change'])}. Aceptas perder hasta el "
            f"{_pct(loss_tolerance)} ({_eur(tolerance_eur)}): ")
    if over:
        text += (f"{len(over)} de los {len(rows)} escenarios {'lo pasa' if len(over) == 1 else 'lo pasan'}. "
                 "Es motivo para revisar tu plan, no para vender.")
    else:
        text += "ninguno de los escenarios lo pasa."
    return {"text": text, "values": values}


def alternatives(rows: list[dict]) -> dict:
    """Same purchases split between the active portfolio and the index: which ended higher and which fell less."""
    known = [row for row in rows if (row.get("performance") or {}).get("final_value_eur") is not None]
    values: dict = {"options": len(known)}
    if len(known) < 2:
        return {"text": "Sin datos suficientes para comparar las opciones.", "values": values}
    best = max(known, key=lambda row: row["performance"]["final_value_eur"])
    worst = min(known, key=lambda row: row["performance"]["final_value_eur"])
    values |= {"best": {"label": best["label"], "final_value_eur": best["performance"]["final_value_eur"]},
               "worst": {"label": worst["label"], "final_value_eur": worst["performance"]["final_value_eur"]}}
    text = (f"Con tus mismas compras, la opción que más valdría hoy es «{best['label']}» "
            f"({_eur(best['performance']['final_value_eur'])}) y la que menos, «{worst['label']}» "
            f"({_eur(worst['performance']['final_value_eur'])}).")
    falls = [row for row in known if row["performance"].get("max_drawdown") is not None]
    if falls:
        calm = max(falls, key=lambda row: row["performance"]["max_drawdown"])  # Drawdowns are negative.
        values["calmest"] = {"label": calm["label"], "max_drawdown": calm["performance"]["max_drawdown"]}
        text += (f" La que menos cayó en su peor momento fue «{calm['label']}» "
                 f"(−{_pct(calm['performance']['max_drawdown'])}).")
    text += (" Es lo que pasó con datos del pasado: todavía no está demostrado que la regla de GABI gane al "
             "S&P 500, y la diferencia puede ser suerte.")
    return {"text": text, "values": values}
