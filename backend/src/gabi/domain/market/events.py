"""Corporate event dates, reported EPS and price reactions from explicit cached values."""
from datetime import UTC, date, datetime

import pandas as pd

EVENT_TYPES = ("earnings", "ex_dividend", "dividend_payment")
EVENT_LABELS = {
    "earnings": "Earnings", "ex_dividend": "Ex-dividendo", "dividend_payment": "Pago de dividendo",
}
INFO_SOURCE = "Yahoo Finance (info)"
EARNINGS_HISTORY_SOURCE = "Yahoo Finance (earnings_dates)"


def _epoch_to_date(value) -> date | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=UTC).date()
    except (TypeError, ValueError, OSError):
        return None


def parse_corporate_events(symbol: str, info: dict, fetched_at: str, *, today: date) -> list:
    """Extrae eventos futuros y pasados de un dict `info` ya cacheado
    (yfinance) -- pura, sin red ni base de datos: recibe exactamente lo que
    fetch_fundamentals_batch ya guarda, para poder testearse con dicts
    sintéticos sin tocar la red.

    `today` es obligatorio para que "días hasta el evento" sea determinista."""
    info = info or {}
    events = []

    start = _epoch_to_date(info.get("earningsTimestampStart"))
    end = _epoch_to_date(info.get("earningsTimestampEnd"))
    earnings_date = start or end
    if earnings_date is not None:
        range_end = end if (start and end and end != start) else None
        events.append({
            "symbol": symbol, "event_type": "earnings",
            "event_date": earnings_date, "range_end": range_end,
            "is_estimate": bool(info.get("isEarningsDateEstimate", True)),
            "source": INFO_SOURCE, "fetched_at": fetched_at, "days_until": (earnings_date - today).days,
        })

    ex_div = _epoch_to_date(info.get("exDividendDate"))
    if ex_div is not None:
        events.append({
            "symbol": symbol, "event_type": "ex_dividend",
            "event_date": ex_div, "range_end": None,
            # Yahoo solo publica esta fecha una vez declarada oficialmente por
            # la empresa -- a diferencia de earnings, no hay ventana estimada.
            "is_estimate": False,
            "source": INFO_SOURCE, "fetched_at": fetched_at, "days_until": (ex_div - today).days,
        })

    div_date = _epoch_to_date(info.get("dividendDate"))
    if div_date is not None:
        events.append({
            "symbol": symbol, "event_type": "dividend_payment",
            "event_date": div_date, "range_end": None,
            "is_estimate": False,
            "source": INFO_SOURCE, "fetched_at": fetched_at, "days_until": (div_date - today).days,
        })

    return events


def parse_earnings_history(symbol: str, earnings_dates_df: pd.DataFrame, *, today: date) -> list:
    """Pura: de la tabla `earnings_dates` de yfinance (o una sintética con la
    misma forma -- índice de fechas, columnas 'EPS Estimate'/'Reported EPS'/
    'Surprise(%)' -- en los tests), se queda solo con lo YA REPORTADO
    (Reported EPS no nulo): lo que todavía no ha pasado no es una sorpresa,
    es una estimación, y ya lo cubre parse_corporate_events."""
    if earnings_dates_df is None or earnings_dates_df.empty:
        return []
    out = []
    for idx, row in earnings_dates_df.iterrows():
        reported = row.get("Reported EPS")
        if pd.isna(reported):
            continue
        edate = idx.date() if hasattr(idx, "date") else pd.Timestamp(idx).date()
        if edate > today:
            continue
        estimate = row.get("EPS Estimate")
        surprise = row.get("Surprise(%)")
        out.append({
            "symbol": symbol, "earnings_date": edate,
            "eps_estimate": None if pd.isna(estimate) else float(estimate),
            "eps_reported": float(reported),
            "surprise_pct": None if pd.isna(surprise) else float(surprise),
        })
    return out


def compute_price_reaction(prices_df: pd.DataFrame, earnings_date: date) -> float | None:
    """% de cambio del cierre ajustado entre la última sesión antes de
    `earnings_date` y la primera sesión en/después de esa fecha -- pura,
    opera sobre el DataFrame ya cacheado de storage.get_prices (sin red).
    None si no hay cierres suficientes a ambos lados (dato muy reciente o
    hueco de cobertura)."""
    if prices_df is None or prices_df.empty or "adj_close" not in prices_df.columns:
        return None
    dates = prices_df.index.date
    before_mask = dates < earnings_date
    after_mask = dates >= earnings_date
    if not before_mask.any() or not after_mask.any():
        return None
    price_before = prices_df.loc[before_mask, "adj_close"].iloc[-1]
    price_after = prices_df.loc[after_mask, "adj_close"].iloc[0]
    if pd.isna(price_before) or pd.isna(price_after) or price_before == 0:
        return None
    return float((price_after / price_before - 1) * 100)


def upcoming_events(symbols: list, fundamentals: dict, *, today: date) -> pd.DataFrame:
    """Eventos futuros (days_until >= 0) para `symbols`, derivados de
    fundamentals ya cacheado -- sin red. Ordenado por fecha ascendente."""
    cols = ["symbol", "event_type", "event_date", "range_end", "is_estimate", "days_until", "source", "fetched_at"]
    if not symbols:
        return pd.DataFrame(columns=cols)
    rows = []
    for sym, record in fundamentals.items():
        rows += parse_corporate_events(sym, record.get("info", {}), record.get("fetched_at", ""), today=today)
    df = pd.DataFrame(rows, columns=cols)
    if df.empty:
        return df
    return df[df["days_until"] >= 0].sort_values("event_date").reset_index(drop=True)


def next_earnings_map(symbols: list, fundamentals: dict, *, today: date) -> dict:
    """symbol -> {event_date, days_until, is_estimate} del próximo earnings
    (o None si no hay ninguno futuro conocido) -- pensado para añadir una
    columna al Screener/Ficha sin recorrer upcoming_events por símbolo."""
    result = dict.fromkeys(symbols)
    for sym in symbols:
        record = fundamentals.get(sym)
        if not record:
            continue
        events = parse_corporate_events(sym, record.get("info", {}), record.get("fetched_at", ""), today=today)
        earnings = [e for e in events if e["event_type"] == "earnings" and e["days_until"] >= 0]
        if earnings:
            result[sym] = earnings[0]
    return result


