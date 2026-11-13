"""Accredited series eligibility and terminal settlement over explicit inputs."""

import pandas as pd

YAHOO_SOURCE = "yahoo:legacy-cache"
ADJUSTED = "split_and_dividend_adjusted"


def rankable(windows: list[dict] | None, day: str, quarter_ends: set[str]) -> bool:
    """A ranking on ``day`` may use the interval only if the audit accredited
    the window of the latest audited quarter end on or before ``day`` and
    ``day`` lies within that window's verified holding period. A rejected
    latest window is never bypassed with an older one, and a later
    accreditation is never used."""
    if windows is None:
        return True  # intervals recorded outside the quarterly audit (tests, manual)
    prior = [quarter for quarter in quarter_ends if quarter <= day]
    if not prior:
        return False
    latest = max(prior)
    return any(window["as_of"] == latest and day <= window["holding_until"] for window in windows)


def _pick(rows: list[tuple], *, covering: tuple[str, str]) -> tuple | None:
    start, end = covering
    candidates = [row for row in rows if row[2] <= start and row[3] > end]
    if not candidates:
        return None
    # Varias fuentes solo solapan si coinciden en retornos; se prefiere Yahoo.
    return sorted(candidates, key=lambda row: (row[0] != YAHOO_SOURCE, row[0]))[0]


def as_traded_close(frame: pd.DataFrame, as_of: str, split_factor: float = 1.0) -> float | None:
    """Cierre negociado en ``as_of``: los archivos ya lo guardan así; la caché
    Yahoo guarda cierres ajustados por splits posteriores (se deshacen)."""
    history = frame[frame.index <= pd.Timestamp(as_of)]
    if history.empty:
        return None
    close = float(history["close"].iloc[-1])
    if frame.attrs.get("source_id") == YAHOO_SOURCE:
        close *= split_factor
    return close


def exit_value(frame: pd.DataFrame, entity_id: str, entry: pd.Timestamp, exit_session: pd.Timestamp, event: dict | None) -> dict:
    """Valor por unidad de ``adj_close`` al salir de una posición.

    Si la serie llega a ``exit_session`` es el precio negociado. Si termina
    antes: evento terminal confirmado → contraprestación en efectivo pasada a
    la base ajustada (misma fórmula que ``historical_price_policy.terminal_return``);
    si no hay evento confirmado, último precio con ``strict=False``.
    """
    series = frame.loc[frame.index >= entry, ["close", "adj_close"]]
    if exit_session in series.index:
        return {"value": float(series.loc[exit_session, "adj_close"]), "date": exit_session,
                "status": "traded", "strict": True}
    if series.empty:
        return {"value": None, "date": None, "status": "no_prices", "strict": False}
    last_day = series.index[-1]
    last = series.iloc[-1]
    if event and event["status"] == "terminal_return_confirmed" and event["event_type"] == "succession" \
            and event.get("exchange_ratio") == 1.0:
        # Canje 1:1 acreditado en el 8-K12B: la posición continúa en el sucesor
        # al mismo valor; se liquida a ese valor y se reinvierte en el rebalanceo.
        return {"value": float(last["adj_close"]), "date": last_day, "status": "succession_one_for_one",
                "strict": True, "event": event}
    if event and event["status"] == "terminal_return_confirmed" and event.get("cash_per_share"):
        return {"value": float(last["adj_close"]) * float(event["cash_per_share"]) / float(last["close"]),
                "date": last_day, "status": "terminal_return_confirmed", "strict": True, "event": event}
    return {"value": float(last["adj_close"]), "date": last_day,
            "status": event["status"] if event else "series_ended_without_event", "strict": False,
            "event": event}


