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

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date

import pandas as pd

from gabi.application.research import historical_pit as historical_queries
from gabi.domain.market.sec_identity import accredited_resolution
from gabi.domain.research import historical_pit as historical_rules
from gabi.infrastructure.storage.historical_pit import SqliteHistoricalPit
from gabi.infrastructure.storage.identity import SqliteIdentityReads

from . import historical_membership, historical_period, identity

YAHOO_SOURCE = historical_rules.YAHOO_SOURCE
ADJUSTED = historical_rules.ADJUSTED

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
    found = SqliteIdentityReads(_reader().path).accredited(
        {identity.normalize_symbol(symbol)}, as_of, _period(as_of).identity_source)
    return accredited_resolution(found[identity.normalize_symbol(symbol)])


def _intervals(entity_id: str) -> list[tuple]:
    return historical_queries.intervals(_reader(), entity_id, {period.price_producer for period in _active})


def _windows(entity_id: str, source_id: str, symbol: str, valid_from: str, valid_to: str) -> list[dict] | None:
    return _reader().windows(entity_id, source_id, symbol, valid_from, valid_to)


def rankable(windows: list[dict] | None, day: str) -> bool:
    return historical_rules.rankable(windows, day, QUARTER_ENDS)


def has_series(entity_id: str | None, day: str) -> bool:
    if not entity_id:
        return False
    return any(start <= day[:10] < end for _s, _y, start, end, _t in _intervals(entity_id))


def _read(source_id: str, symbol: str, start: str, end: str) -> pd.DataFrame:
    return _reader().prices(source_id, symbol, start, end)


def _pick(rows: list[tuple], *, covering: tuple[str, str]) -> tuple | None:
    return historical_rules._pick(rows, covering=covering)


def _series_for(entity_id: str, row: tuple) -> pd.DataFrame:
    return historical_queries.series_for(_reader(), entity_id, row)


def ranking_series(entity_id: str | None, as_of: str) -> pd.DataFrame:
    return historical_queries.ranking_series(_reader(), entity_id, as_of,
        producers={period.price_producer for period in _active}, quarter_ends=QUARTER_ENDS, trailing_days=TRAILING_DAYS)


def holding_series(entity_id: str | None, day: str) -> pd.DataFrame:
    return historical_queries.holding_series(_reader(), entity_id, day,
        producers={period.price_producer for period in _active})


def as_traded_close(frame: pd.DataFrame, as_of: str) -> float | None:
    return historical_queries.as_traded_close(_reader(), frame, as_of)


def terminal_event(entity_id: str, start: str, end: str) -> dict | None:
    return _reader().terminal_event(entity_id, start, end)


def exit_value(frame: pd.DataFrame, entity_id: str, entry: pd.Timestamp, exit_session: pd.Timestamp) -> dict:
    return historical_queries.exit_value(_reader(), frame, entity_id, entry, exit_session)


def _reader() -> SqliteHistoricalPit:
    return SqliteHistoricalPit(identity._reader().path)
