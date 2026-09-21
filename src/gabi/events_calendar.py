"""Calendario de eventos corporativos (earnings, dividendos) y sorpresas de
resultados pasadas -- da contexto temporal a las oportunidades del Screener:
una empresa con buen score puede tener earnings mañana.

El calendario hacia delante (próximo earnings, ex-dividendo, pago de
dividendo) se deriva de `fundamentals.info_json`, que ya está cacheado por
data_fetch.fetch_fundamentals_batch -- Yahoo Finance incluye esas fechas
dentro de `Ticker.info` (earningsTimestampStart/End, isEarningsDateEstimate,
exDividendDate, dividendDate), así que no hace falta ninguna llamada de red
adicional ni una tabla nueva: se recalcula sobre lo que ya hay.

"Confirmada" vs "estimada" es el campo explícito de Yahoo
`isEarningsDateEstimate`, no una heurística de GABI -- y si el campo no
viene informado se trata como estimada por defecto (fail closed: mejor
subestimar la certeza que presentar como confirmado algo que no lo es).

El histórico de sorpresas de resultados (EPS estimado vs reportado + gap de
precio posterior) SÍ necesita una llamada de red aparte (`Ticker.earnings_
dates`) y se persiste en `earnings_surprises` como dato de investigación --
deliberadamente NO se usa en scoring.py/screener.py: cualquier validación de
que "la sorpresa reciente predice algo" debe pasar antes por Factor Lab/
Research Lab, igual que cualquier otro factor nuevo candidato."""
import concurrent.futures as cf
from datetime import UTC, date, datetime

import pandas as pd
import yfinance as yf

from . import storage
from .data_fetch import _classify_error, normalize_symbol

SCHEMA = """
CREATE TABLE IF NOT EXISTS earnings_surprises (
    symbol TEXT NOT NULL,
    earnings_date TEXT NOT NULL,
    eps_estimate REAL,
    eps_reported REAL,
    surprise_pct REAL,
    price_reaction_pct REAL,
    source TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    PRIMARY KEY (symbol, earnings_date)
);
"""

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


def parse_corporate_events(symbol: str, info: dict, fetched_at: str, *, today: date | None = None) -> list:
    """Extrae eventos futuros y pasados de un dict `info` ya cacheado
    (yfinance) -- pura, sin red ni base de datos: recibe exactamente lo que
    fetch_fundamentals_batch ya guarda, para poder testearse con dicts
    sintéticos sin tocar la red.

    `today` por defecto es date.today(), pero los tests SIEMPRE lo pasan
    explícito para que "días hasta el evento" sea determinista."""
    if today is None:
        today = date.today()
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


def upcoming_events(symbols: list, *, today: date | None = None) -> pd.DataFrame:
    """Eventos futuros (days_until >= 0) para `symbols`, derivados de
    fundamentals ya cacheado -- sin red. Ordenado por fecha ascendente."""
    cols = ["symbol", "event_type", "event_date", "range_end", "is_estimate", "days_until", "source", "fetched_at"]
    if not symbols:
        return pd.DataFrame(columns=cols)
    if today is None:
        today = date.today()
    fundamentals = storage.get_fundamentals(symbols)
    rows = []
    for sym, record in fundamentals.items():
        rows += parse_corporate_events(sym, record.get("info", {}), record.get("fetched_at", ""), today=today)
    df = pd.DataFrame(rows, columns=cols)
    if df.empty:
        return df
    return df[df["days_until"] >= 0].sort_values("event_date").reset_index(drop=True)


def next_earnings_map(symbols: list, *, today: date | None = None) -> dict:
    """symbol -> {event_date, days_until, is_estimate} del próximo earnings
    (o None si no hay ninguno futuro conocido) -- pensado para añadir una
    columna al Screener/Ficha sin recorrer upcoming_events por símbolo."""
    if today is None:
        today = date.today()
    fundamentals = storage.get_fundamentals(symbols)
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


def _fetch_earnings_history_attempt(symbol: str) -> pd.DataFrame:
    t = yf.Ticker(normalize_symbol(symbol))
    df = t.earnings_dates
    return df if df is not None else pd.DataFrame()


def parse_earnings_history(symbol: str, earnings_dates_df: pd.DataFrame, *, today: date | None = None) -> list:
    """Pura: de la tabla `earnings_dates` de yfinance (o una sintética con la
    misma forma -- índice de fechas, columnas 'EPS Estimate'/'Reported EPS'/
    'Surprise(%)' -- en los tests), se queda solo con lo YA REPORTADO
    (Reported EPS no nulo): lo que todavía no ha pasado no es una sorpresa,
    es una estimación, y ya lo cubre parse_corporate_events."""
    if today is None:
        today = date.today()
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


def store_earnings_surprises(rows: list):
    if not rows:
        return
    recorded_at = datetime.now(UTC).isoformat()
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT OR REPLACE INTO earnings_surprises "
            "(symbol, earnings_date, eps_estimate, eps_reported, surprise_pct, price_reaction_pct, source, recorded_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            [(r["symbol"], r["earnings_date"].isoformat(), r.get("eps_estimate"), r["eps_reported"],
              r.get("surprise_pct"), r.get("price_reaction_pct"), EARNINGS_HISTORY_SOURCE, recorded_at)
             for r in rows],
        )
        conn.commit()


def get_earnings_surprises(symbol: str) -> pd.DataFrame:
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        return pd.read_sql_query(
            "SELECT * FROM earnings_surprises WHERE symbol=? ORDER BY earnings_date DESC", conn, params=(symbol,))


def sync_earnings_surprises(symbols: list, max_workers: int = 6, progress_cb=None) -> dict:
    """Descarga Ticker.earnings_dates (red) por símbolo, se queda con lo ya
    reportado, calcula la reacción de precio con datos YA cacheados (sin red
    extra) y lo persiste. Deliberadamente manual (botón en la Ficha), no
    forma parte de 'Actualizar datos' -- igual que filing_tracker.compare_
    filings, para no añadir peticiones de red al refresco por defecto."""
    failed: dict = {}
    total = len(symbols)
    if total == 0:
        return failed
    today = date.today()
    with cf.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_fetch_earnings_history_attempt, s): s for s in symbols}
        done = 0
        for fut in cf.as_completed(futures):
            sym = futures[fut]
            done += 1
            try:
                raw = fut.result()
                rows = parse_earnings_history(sym, raw, today=today)
                if rows:
                    prices = storage.get_prices(sym)
                    for r in rows:
                        r["price_reaction_pct"] = compute_price_reaction(prices, r["earnings_date"])
                    store_earnings_surprises(rows)
            except Exception as exc:
                _, reason = _classify_error(exc, service="Yahoo Finance")
                failed[sym] = reason
            if progress_cb:
                progress_cb(done, total)
    return failed
