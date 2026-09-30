"""A simulated trade executes at the first exchange session with a cached close."""

from datetime import date

import exchange_calendars as xcals
import pandas as pd

MARKETS = {"XNYS": "NYSE / Nasdaq (EE. UU.)", "XETR": "Xetra (Alemania)",
           "XLON": "Londres", "XMAD": "Madrid", "XPAR": "París"}


def execution_quote(history: pd.DataFrame, requested_date: str, market: str, today: date) -> dict:
    target = pd.Timestamp(requested_date)
    if target.date() > today:
        raise ValueError("No se puede simular una operación futura.")
    if market not in MARKETS:
        raise ValueError("Mercado no admitido.")
    session = xcals.get_calendar(market).date_to_session(target, direction="next")
    if session.date() > today:
        raise ValueError("Todavía no hay una sesión bursátil cerrada para esta fecha.")
    if history.empty or "adj_close" not in history:
        raise ValueError("No hay precios descargados para este símbolo.")
    if session not in history.index:
        raise ValueError(f"Falta el precio de la primera sesión bursátil ({session.date()}).")
    row = history.loc[session]
    if pd.isna(row["close"]) or pd.isna(row["adj_close"]) or row["close"] <= 0 or row["adj_close"] <= 0:
        raise ValueError("El precio de ejecución no es válido.")
    return {"date": session.date().isoformat(), "close": float(row["close"]),
            "adj_close": float(row["adj_close"])}
