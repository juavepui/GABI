"""Adaptador point-in-time acreditado para Ranking histórico y Backtest V1/V2 (#32, #34).

El motor existente (``universe`` → ``screener_asof`` → ``identity``) se usa tal
cual; este módulo solo le da, para fechas cubiertas por la capa histórica
acreditada en #26-#28, lo que antes obtenía de la caché por ticker:

- universo: composición de referencia fja05680 con la corrección WLP/ANTM
  (la misma sobre la que se acreditaron identidad y precios);
- identidad: intervalos SEC acreditados (#27/#29/#28), nunca alias actuales;
- precios: solo intervalos de ``historical_price_provenance`` (una fuente por
  lectura, sin concatenar ni rellenar), que incluyen el periodo de tenencia
  verificado hasta el siguiente rebalanceo;
- salida de una posición: evento terminal confirmado (contraprestación en
  efectivo) o, si no lo hay, el último precio marcado explícitamente como no
  estricto. Nunca se oculta.

Por defecto solo está activo 2010-2015 (``[HISTORICAL_START, HISTORICAL_END)``);
fuera de él no cambia nada. La capa 2016-2025 (#34) se activa explícitamente con
``accredited_periods("2010-2015", "2016-2025")`` para compararla con el camino
operativo (#35); sin activarla, los rankings 2016+ son los de siempre.
"""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, timedelta

import pandas as pd

from . import historical_archive, historical_membership, historical_period, identity, storage
from .historical_price_policy import ADJUSTED, YAHOO_SOURCE
from .historical_price_policy import SCHEMA as PROVENANCE_SCHEMA

HISTORICAL_START = historical_period.P2010.start
HISTORICAL_END = historical_period.P2010.end_exclusive
TRAILING_DAYS = 365  # ~253 sesiones: la ventana que exigen momentum y riesgo
# Fechas auditadas por las auditorías trimestrales de precios (#28, #34). Cada
# periodo solo tiene ventanas acreditadas si se ejecutó su auditoría.
QUARTER_ENDS = {quarter for period in historical_period.PERIODS.values() for quarter in period.quarters}
_active: tuple[historical_period.Period, ...] = (historical_period.P2010,)


@contextmanager
def accredited_periods(*keys: str) -> Iterator[None]:
    """Activa temporalmente los periodos acreditados indicados (p. ej. 2016-2025)."""
    global _active
    previous = _active
    _active = tuple(historical_period.get(key) for key in keys)
    try:
        yield
    finally:
        _active = previous


def active_periods() -> tuple[str, ...]:
    return tuple(period.key for period in _active)


def period_for(as_of: str) -> historical_period.Period | None:
    day = date.fromisoformat(as_of[:10]).isoformat()
    return next((period for period in _active if period.covers(day)), None)


def covers(as_of: str) -> bool:
    return period_for(as_of) is not None


def _period(as_of: str) -> historical_period.Period:
    period = period_for(as_of)
    if period is None:
        raise ValueError(f"{as_of[:10]} is outside the active accredited periods {active_periods()}")
    return period


def _constituents(as_of: str) -> dict:
    period = _period(as_of)
    return historical_membership.constituents_as_of(
        as_of, source_id=period.membership_source, compare_reference=False,
        identity_source=period.identity_source)


def universe(as_of: str) -> dict:
    """Mismo contrato que ``universe.get_sp500_constituents_asof``."""
    data = _constituents(as_of)
    members = data["members"]
    accredited = sum(1 for row in members if row["identity_status"] == "resolved")
    return {"symbols": data["symbols"], "source_date": data["source_date"], "is_exact": True,
            "label_corrections": data["label_corrections"],
            "source_id": data["source_id"], "quality": data["quality"],
            "identity_accredited": accredited,
            "note": (f"Composición histórica de referencia ({data['source_id']}) del {data['source_date']}, "
                     f"aplicable a {as_of}; identidad acreditada {accredited}/{len(members)}. "
                     f"Capa {_period(as_of).key}: solo precios y entidades acreditados por SEC.")}


def resolve(symbol: str, as_of: str) -> dict:
    """Mismo contrato que ``identity.resolve`` con la identidad histórica acreditada."""
    found = historical_membership._identities({identity.normalize_symbol(symbol)}, as_of,
                                              interval_source=_period(as_of).identity_source)
    row = found[identity.normalize_symbol(symbol)]
    # Solo los niveles acreditados por intervalo (#27/#28); una prueba SEC de
    # un solo día no activa identidad para un backtest.
    resolved = (row["identity_status"] == "resolved" and row["entity_id"] and
                row["identity_tier"] in historical_archive.ACCREDITED_IDENTITY_TIERS)
    return {"entity_id": row["entity_id"] if resolved else None,
            "cik": row["cik"] if resolved else None,
            "status": "resolved" if resolved else
            ("ambiguous" if row["identity_status"] == "ambiguous" else "unresolved"),
            "candidates": [row["entity_id"]] if row["entity_id"] else [],
            "source": row["identity_source"] or "historical_identity_interval",
            "confidence": 1.0 if resolved else None,
            "identity_tier": row["identity_tier"]}


def _intervals(entity_id: str) -> list[tuple]:
    with storage.get_connection() as conn:
        conn.executescript(historical_archive.SCHEMA + PROVENANCE_SCHEMA)
        return conn.execute(
            "SELECT source_id,symbol,valid_from,valid_to,status FROM historical_price_provenance "
            "WHERE entity_id=? AND status IN ('tier_a','tier_b') AND adjustment_basis=?",
            (entity_id, ADJUSTED)).fetchall()


def _windows(entity_id: str, source_id: str, symbol: str, valid_from: str, valid_to: str) -> list[dict] | None:
    """Audited windows recorded for an interval (None when not recorded)."""
    with storage.get_connection() as conn:
        row = conn.execute(
            "SELECT evidence_json FROM historical_price_provenance WHERE entity_id=? AND source_id=? "
            "AND symbol=? AND valid_from=? AND valid_to=?",
            (entity_id, source_id, symbol, valid_from, valid_to)).fetchone()
    if row is None:
        return None
    refs = [ref for ref in json.loads(row[0]) if ref.get("kind") == "accredited_windows"]
    return refs[0]["windows"] if refs else None


def rankable(windows: list[dict] | None, day: str) -> bool:
    """A ranking on ``day`` may use the interval only if the audit accredited
    the window of the latest audited quarter end on or before ``day`` and
    ``day`` lies within that window's verified holding period. A rejected
    latest window is never bypassed with an older one, and a later
    accreditation is never used."""
    if windows is None:
        return True  # intervals recorded outside the quarterly audit (tests, manual)
    prior = [quarter for quarter in QUARTER_ENDS if quarter <= day]
    if not prior:
        return False
    latest = max(prior)
    return any(window["as_of"] == latest and day <= window["holding_until"] for window in windows)


def has_series(entity_id: str | None, day: str) -> bool:
    if not entity_id:
        return False
    return any(start <= day[:10] < end for _s, _y, start, end, _t in _intervals(entity_id))


def _read(source_id: str, symbol: str, start: str, end: str) -> pd.DataFrame:
    params: tuple[str, ...]
    if source_id == YAHOO_SOURCE:
        query, params = ("SELECT date,close,adj_close FROM prices WHERE symbol=? AND date>=? AND date<? "
                         "ORDER BY date", (symbol, start, end))
    else:
        query, params = ("SELECT date,close,adj_close FROM historical_prices WHERE source_id=? AND symbol=? "
                         "AND date>=? AND date<? ORDER BY date", (source_id, symbol, start, end))
    with storage.get_connection() as conn:
        frame = pd.read_sql_query(query, conn, params=params)
    frame.index = pd.to_datetime(frame.pop("date"))
    return frame[(frame["adj_close"] > 0) & (frame["close"] > 0)]


def _pick(rows: list[tuple], *, covering: tuple[str, str]) -> tuple | None:
    start, end = covering
    candidates = [row for row in rows if row[2] <= start and row[3] > end]
    if not candidates:
        return None
    # Varias fuentes solo solapan si coinciden en retornos; se prefiere Yahoo.
    return sorted(candidates, key=lambda row: (row[0] != YAHOO_SOURCE, row[0]))[0]


def _series_for(entity_id: str, row: tuple) -> pd.DataFrame:
    source_id, symbol, valid_from, valid_to, status = row
    frame = _read(source_id, symbol, valid_from, valid_to)
    frame.attrs.update(entity_id=entity_id, source_id=source_id, source_symbol=symbol,
                       valid_from=valid_from, valid_to=valid_to, price_source_status=status)
    return frame


def ranking_series(entity_id: str | None, as_of: str) -> pd.DataFrame:
    """Serie acreditada que cubre la ventana previa a ``as_of`` (o la historia
    corta acreditada si la acción empezó a cotizar dentro de ella)."""
    if not entity_id:
        return pd.DataFrame()
    day = as_of[:10]
    rows = [row for row in _intervals(entity_id) if rankable(_windows(entity_id, *row[:4]), day)]
    trailing = (date.fromisoformat(day) - timedelta(days=TRAILING_DAYS)).isoformat()
    row = _pick(rows, covering=(trailing, day)) or _pick(rows, covering=(day, day))
    if row is None:
        return pd.DataFrame()
    frame = _series_for(entity_id, row)
    return frame[frame.index <= pd.Timestamp(day)]


def holding_series(entity_id: str | None, day: str) -> pd.DataFrame:
    """Serie acreditada desde ``day`` con el tramo de tenencia más largo."""
    if not entity_id:
        return pd.DataFrame()
    rows = [row for row in _intervals(entity_id) if row[2] <= day[:10] < row[3]]
    if not rows:
        return pd.DataFrame()
    furthest = max(row[3] for row in rows)
    row = sorted([r for r in rows if r[3] == furthest], key=lambda r: (r[0] != YAHOO_SOURCE, r[0]))[0]
    return _series_for(entity_id, row)


def as_traded_close(frame: pd.DataFrame, as_of: str) -> float | None:
    """Cierre negociado en ``as_of``: los archivos ya lo guardan así; la caché
    Yahoo guarda cierres ajustados por splits posteriores (se deshacen)."""
    history = frame[frame.index <= pd.Timestamp(as_of)]
    if history.empty:
        return None
    close = float(history["close"].iloc[-1])
    if frame.attrs.get("source_id") == YAHOO_SOURCE:
        close *= storage.get_split_factor_since(frame.attrs["source_symbol"], as_of)
    return close


def terminal_event(entity_id: str, start: str, end: str) -> dict | None:
    with storage.get_connection() as conn:
        conn.executescript(PROVENANCE_SCHEMA)
        row = conn.execute(
            "SELECT event_date,event_type,status,cash_per_share,exchange_ratio FROM historical_terminal_events "
            "WHERE entity_id=? AND event_date>? AND event_date<=? ORDER BY event_date LIMIT 1",
            (entity_id, start[:10], end[:10])).fetchone()
    if row is None:
        return None
    return dict(zip(("event_date", "event_type", "status", "cash_per_share", "exchange_ratio"), row, strict=True))


def exit_value(frame: pd.DataFrame, entity_id: str, entry: pd.Timestamp, exit_session: pd.Timestamp) -> dict:
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
    event = terminal_event(entity_id, (entry - pd.Timedelta(days=1)).date().isoformat(),
                           (exit_session + pd.Timedelta(days=10)).date().isoformat())
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
