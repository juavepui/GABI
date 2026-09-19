"""Guarda candidatas rankeadas y evalúa más adelante su rentabilidad total frente al SPY."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd

from . import storage

MADRID_TZ = ZoneInfo("Europe/Madrid")


def _now_madrid_iso() -> str:
    """Fecha y hora local española (con el desfase de horario de verano ya
    resuelto), no solo la fecha — para saber a qué hora del día se guardó
    un ranking, no solo en qué día."""
    return datetime.now(MADRID_TZ).isoformat(timespec="seconds")

SCHEMA = """
CREATE TABLE IF NOT EXISTS ranking_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    as_of_date TEXT NOT NULL,
    source TEXT NOT NULL,
    symbol TEXT NOT NULL,
    rank INTEGER NOT NULL,
    score REAL NOT NULL,
    coverage REAL NOT NULL
);
"""


def _ensure_snapshot_columns(conn):
    """`name` se añadió después — misma migración ligera que ya usa
    decision_engine.py para sus planes guardados: ALTER TABLE si falta la
    columna, y un nombre por defecto para snapshots antiguos sin nombre."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(ranking_snapshots)")}
    if "name" not in columns:
        conn.execute("ALTER TABLE ranking_snapshots ADD COLUMN name TEXT")
    conn.execute(
        "UPDATE ranking_snapshots SET name = 'Ranking ' || as_of_date "
        "WHERE name IS NULL OR TRIM(name) = ''"
    )


def _snapshot_name(name: str) -> str:
    name = name.strip()
    if not name or len(name) > 80:
        raise ValueError("El nombre del ranking debe tener entre 1 y 80 caracteres.")
    return name


def save_snapshot(table: pd.DataFrame, as_of_date: str, source: str = "live", top_n: int = 10,
                  name: str | None = None) -> int:
    """Guarda solo las filas rankeadas con cobertura suficiente; devuelve el id del snapshot."""
    candidates = table[table["composite_score"].notna()].head(top_n)
    if candidates.empty:
        return 0
    name = _snapshot_name(name) if name else f"Ranking {as_of_date}"
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        _ensure_snapshot_columns(conn)
        snapshot_id = conn.execute("SELECT COALESCE(MAX(snapshot_id), 0) + 1 FROM ranking_snapshots").fetchone()[0]
        conn.executemany(
            "INSERT INTO ranking_snapshots (snapshot_id, created_at, as_of_date, source, symbol, rank, score, coverage, name) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            [(snapshot_id, _now_madrid_iso(), as_of_date, source, symbol, rank,
              float(row.composite_score), float(row.score_coverage), name)
             for rank, (symbol, row) in enumerate(candidates.iterrows(), 1)],
        )
        conn.commit()
    return snapshot_id


def list_snapshots() -> pd.DataFrame:
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        _ensure_snapshot_columns(conn)
        conn.commit()
        return pd.read_sql_query(
            "SELECT snapshot_id AS id, name, created_at, as_of_date, source, COUNT(*) AS candidates "
            "FROM ranking_snapshots GROUP BY snapshot_id, name, created_at, as_of_date, source ORDER BY snapshot_id DESC", conn,
        )


def rename_snapshot(snapshot_id: int, name: str) -> bool:
    name = _snapshot_name(name)
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        _ensure_snapshot_columns(conn)
        cur = conn.execute("UPDATE ranking_snapshots SET name=? WHERE snapshot_id=?", (name, snapshot_id))
        conn.commit()
        return cur.rowcount > 0


def snapshot_symbols(snapshot_id: int) -> list[str]:
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        return [r[0] for r in conn.execute(
            "SELECT symbol FROM ranking_snapshots WHERE snapshot_id=? ORDER BY rank", (snapshot_id,)
        )]


def _adjusted_at(symbol: str, target: pd.Timestamp, after: bool = False):
    prices = storage.get_prices(symbol)
    if prices.empty or "adj_close" not in prices:
        return None
    values = prices["adj_close"].dropna()
    if after:
        values = values[(values.index >= target) & (values.index <= target + pd.Timedelta(days=7))]
        return float(values.iloc[0]) if not values.empty else None
    values = values[(values.index <= target) & (values.index >= target - pd.Timedelta(days=7))]
    return float(values.iloc[-1]) if not values.empty else None


def _latest_cached_date(symbols: list[str]):
    """La fecha real más reciente con precio en caché entre estos símbolos
    — 'hoy' en la interfaz en realidad usa esto, no la fecha del calendario:
    si el caché no se ha actualizado, puede ser de ayer o de antes, y
    entonces no hay ningún día nuevo que comparar todavía."""
    latest = None
    for symbol in symbols:
        prices = storage.get_prices(symbol)
        if prices.empty or "adj_close" not in prices:
            continue
        valid = prices["adj_close"].dropna()
        if valid.empty:
            continue
        candidate = valid.index.max()
        if latest is None or candidate > latest:
            latest = candidate
    return latest


def snapshot_progress(snapshot_id: int, cost_bps: float = 0) -> dict:
    """Progreso de un ranking guardado HASTA HOY (no un plazo fijo de 6/12
    meses): precio en la fecha guardada, precio más reciente disponible,
    retorno de cada candidata individualmente (equiponderada, mismo peso
    para todas — un ranking guardado no lleva pesos distintos por empresa,
    a diferencia de un plan de 🧭 Decisiones de cartera) y de la cesta
    completa frente al SPY en el mismo periodo."""
    snapshots = list_snapshots()
    row = snapshots[snapshots["id"] == snapshot_id]
    if row.empty:
        return {}
    as_of_date = row.iloc[0]["as_of_date"]
    symbols = snapshot_symbols(snapshot_id)
    start = pd.Timestamp(as_of_date)
    today = pd.Timestamp(date.today())

    data_as_of = _latest_cached_date(symbols + ["SPY"])
    # "Obsoleto" = el caché de precios no llega a ningún día DESPUÉS de la
    # fecha guardada todavía — no hay literalmente ningún dato nuevo que
    # comparar, así que un 0.0% aquí no significaría "sin cambios", sino
    # "no hay datos más recientes" — hay que distinguir los dos casos.
    stale = data_as_of is None or data_as_of.normalize() <= start.normalize()

    detail_rows = []
    for symbol in symbols:
        p0 = _adjusted_at(symbol, start)
        p1 = _adjusted_at(symbol, today)
        ret = (p1 / p0 - 1 - 2 * cost_bps / 10000) if p0 and p1 else None
        detail_rows.append({"symbol": symbol, "price_start": p0, "price_now": p1, "return": ret})
    detail = pd.DataFrame(detail_rows)

    valid_returns = detail["return"].dropna()
    portfolio_return = float(valid_returns.mean()) if not valid_returns.empty else None
    b0 = _adjusted_at("SPY", start)
    b1 = _adjusted_at("SPY", today)
    benchmark_return = (b1 / b0 - 1 - 2 * cost_bps / 10000) if b0 and b1 else None

    return {
        "as_of_date": as_of_date, "today": today.date().isoformat(),
        "data_as_of": data_as_of.date().isoformat() if data_as_of is not None else None,
        "stale": stale,
        "detail": detail, "available": int(valid_returns.shape[0]), "requested": len(symbols),
        "portfolio_return": portfolio_return, "benchmark_return": benchmark_return,
        "excess_return": (portfolio_return - benchmark_return)
        if portfolio_return is not None and benchmark_return is not None else None,
        "missing": sorted(set(symbols) - set(detail.loc[detail["return"].notna(), "symbol"])),
    }


def snapshot_price_curve(snapshot_id: int) -> pd.DataFrame:
    """Curva diaria normalizada (base 100 en la fecha guardada) de la cesta
    equiponderada frente al SPY, desde la fecha del snapshot hasta hoy —
    para dibujar la comparación, no solo dar el número final. Si el caché
    todavía no tiene ningún precio en la fecha exacta del snapshot, arranca
    en el más cercano disponible (misma tolerancia que _adjusted_at) en vez
    de devolver una curva vacía."""
    snapshots = list_snapshots()
    row = snapshots[snapshots["id"] == snapshot_id]
    if row.empty:
        return pd.DataFrame()
    as_of_date = row.iloc[0]["as_of_date"]
    symbols = snapshot_symbols(snapshot_id)
    start = pd.Timestamp(as_of_date) - pd.Timedelta(days=7)

    histories = storage.get_prices_multi(symbols + ["SPY"])
    series = {}
    for symbol in symbols:
        h = histories.get(symbol)
        if h is None or h.empty or "adj_close" not in h:
            continue
        s = h["adj_close"].dropna()
        s = s[s.index >= start]
        if not s.empty:
            series[symbol] = s / s.iloc[0] * 100

    if not series:
        return pd.DataFrame()
    basket = pd.concat(series, axis=1).mean(axis=1, skipna=True)

    spy_h = histories.get("SPY")
    spy = pd.Series(dtype=float)
    if spy_h is not None and not spy_h.empty and "adj_close" in spy_h:
        spy = spy_h["adj_close"].dropna()
        spy = spy[spy.index >= start]
        if not spy.empty:
            spy = spy / spy.iloc[0] * 100

    curve = pd.DataFrame({"Cartera": basket})
    if not spy.empty:
        curve["SPY"] = spy
    return curve.dropna(how="all")


def evaluate(symbols: list[str], as_of_date: str, months: int = 6, cost_bps: float = 0) -> dict:
    """Rentabilidad total con el mismo peso por candidata, incluyendo el coste de ida y vuelta; los datos que faltan nunca cuentan como cero."""
    start = pd.Timestamp(as_of_date)
    end = start + pd.DateOffset(months=months)
    if end > pd.Timestamp(date.today()):
        return {"status": "pending", "end_date": end.date().isoformat()}
    returns = {}
    for symbol in dict.fromkeys(symbols):
        p0 = _adjusted_at(symbol, start)
        p1 = _adjusted_at(symbol, end, after=True)
        if p0 and p1:
            returns[symbol] = p1 / p0 - 1 - 2 * cost_bps / 10000
    b0 = _adjusted_at("SPY", start)
    b1 = _adjusted_at("SPY", end, after=True)
    benchmark = b1 / b0 - 1 - 2 * cost_bps / 10000 if b0 and b1 else None
    portfolio = sum(returns.values()) / len(returns) if returns else None
    return {
        "status": "complete" if len(returns) == len(set(symbols)) and benchmark is not None else "incomplete",
        "end_date": end.date().isoformat(), "available": len(returns), "requested": len(set(symbols)),
        "portfolio_return": portfolio, "benchmark_return": benchmark,
        "excess_return": portfolio - benchmark if portfolio is not None and benchmark is not None else None,
        "missing": sorted(set(symbols) - returns.keys()),
    }
