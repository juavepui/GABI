"""Blind Forward Validation: convierte la promesa de
`HIPOTESIS_CONGELADA.md` (4 rebalanceos trimestrales reales, sin tocar la
estrategia hasta 2027-09-17) en una funcionalidad real, no solo un
compromiso en Markdown que cualquiera puede romper sin darse cuenta.

Cada rebalanceo se registra de forma inmutable (ranking, picks, precios de
entrada, hash encadenado con el anterior, commit de código) y el
**rendimiento frente al SPY queda oculto hasta la fecha de desbloqueo**. La
tentación que esto evita es muy concreta: "llevamos seis meses perdiendo,
quizá Momentum debería pasar de 25 a 35%..." — en cuanto se mira el
resultado a medias y se ajusta la estrategia, la prueba prospectiva ha
muerto, sin que nadie necesite hacer trampa conscientemente.

Una app local no puede impedir de verdad que su propio dueño mire la base de
datos a mano -- por eso `break_seal_early()` no finge ser un candado
criptográfico irrompible, sino que dejar constancia honesta y permanente de
que la prueba se rompió antes de tiempo y por qué, igual que se documentó la
propia ruptura de `HIPOTESIS_CONGELADA.md` esta sesión."""
import hashlib
import json
from datetime import date

import pandas as pd

from . import screener_asof, storage
from .research_lab import _current_git_commit, log_experiment

SCHEMA = """
CREATE TABLE IF NOT EXISTS blind_validations (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    name TEXT NOT NULL,
    model_id TEXT NOT NULL,
    weights_json TEXT NOT NULL,
    n_positions INTEGER NOT NULL,
    rebalance_months INTEGER NOT NULL,
    start_date TEXT NOT NULL,
    unlock_date TEXT NOT NULL,
    git_commit_created TEXT,
    status TEXT NOT NULL DEFAULT 'locked',
    broken_early_at TEXT,
    broken_early_reason TEXT
);
CREATE TABLE IF NOT EXISTS blind_validation_periods (
    id INTEGER PRIMARY KEY,
    validation_id INTEGER NOT NULL,
    rebalance_date TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    symbols_json TEXT NOT NULL,
    weights_json TEXT NOT NULL,
    entry_prices_json TEXT NOT NULL,
    git_commit TEXT,
    prev_hash TEXT,
    record_hash TEXT NOT NULL,
    UNIQUE(validation_id, rebalance_date)
);
"""


def _ensure_schema(conn):
    conn.executescript(SCHEMA)


def _canonical_payload(rebalance_date: str, symbols: list, entry_prices: dict) -> str:
    return json.dumps({
        "rebalance_date": rebalance_date,
        "symbols": sorted(symbols),
        "entry_prices": {s: entry_prices[s] for s in sorted(entry_prices)},
    }, sort_keys=True)


def create_validation(name: str, weights: dict, n_positions: int, rebalance_months: int,
                      start_date: str, unlock_date: str, model_id: str = "GABI-MF-v1") -> int:
    if pd.Timestamp(unlock_date) <= pd.Timestamp(start_date):
        raise ValueError("La fecha de desbloqueo debe ser posterior a la de inicio.")
    if n_positions < 1:
        raise ValueError("n_positions debe ser al menos 1.")
    with storage.get_connection() as conn:
        _ensure_schema(conn)
        cur = conn.execute(
            "INSERT INTO blind_validations (created_at, name, model_id, weights_json, n_positions, "
            "rebalance_months, start_date, unlock_date, git_commit_created, status) "
            "VALUES (?,?,?,?,?,?,?,?,?,'locked')",
            (pd.Timestamp.now().isoformat(), name, model_id, json.dumps(weights), n_positions,
             rebalance_months, start_date, unlock_date, _current_git_commit()),
        )
        conn.commit()
        return cur.lastrowid


def _get_validation_row(conn, validation_id: int) -> dict:
    columns = [d[0] for d in conn.execute("SELECT * FROM blind_validations LIMIT 0").description]
    row = conn.execute("SELECT * FROM blind_validations WHERE id = ?", (validation_id,)).fetchone()
    return dict(zip(columns, row)) if row else {}


def _get_periods(conn, validation_id: int) -> list:
    columns = [d[0] for d in conn.execute("SELECT * FROM blind_validation_periods LIMIT 0").description]
    rows = conn.execute(
        "SELECT * FROM blind_validation_periods WHERE validation_id = ? ORDER BY rebalance_date",
        (validation_id,),
    ).fetchall()
    return [dict(zip(columns, r)) for r in rows]


def record_rebalance(validation_id: int, as_of: str = None) -> dict:
    """Fija los picks y precios de entrada de un rebalanceo real de forma
    INMUTABLE (`UNIQUE(validation_id, rebalance_date)` -- reintentar el
    mismo periodo lanza, no sobrescribe). `as_of` por defecto hoy; usar una
    fecha distinta de hoy es una desviación de integridad real (no es un
    registro "en vivo" de verdad) -- se permite para pruebas, pero queda
    marcado en el resultado (`"as_of_is_today": bool`).

    Precio de entrada = último cierre ajustado disponible EN o ANTES de
    `as_of` (no el patrón señal→sesión siguiente de un backtest: aquí no se
    simula nada, se registra el precio real más reciente en el momento en
    que se pulsa el botón)."""
    with storage.get_connection() as conn:
        _ensure_schema(conn)
        validation = _get_validation_row(conn, validation_id)
        if not validation:
            raise ValueError(f"No existe la validación #{validation_id}.")
        periods = _get_periods(conn, validation_id)

    as_of = as_of or date.today().isoformat()
    as_of_ts = pd.Timestamp(as_of)
    ranked = screener_asof.build_ranking_as_of(as_of)["table"]
    eligible = ranked[ranked["composite_score"].notna() & (ranked["score_coverage"] >= .7)]
    n_positions = validation["n_positions"]
    if len(eligible) < n_positions:
        raise ValueError(f"Solo {len(eligible)}/{n_positions} candidatas con cobertura suficiente hoy.")
    picks = eligible.index.tolist()[:n_positions]

    histories = storage.get_prices_multi(picks)
    entry_prices, missing = {}, []
    for symbol in picks:
        h = histories.get(symbol, pd.DataFrame())
        h = h[h.index <= as_of_ts] if not h.empty else h
        if h.empty or "adj_close" not in h or h["adj_close"].dropna().empty:
            missing.append(symbol)
            continue
        entry_prices[symbol] = float(h["adj_close"].dropna().iloc[-1])
    if missing:
        raise ValueError(f"Faltan precios recientes para: {', '.join(missing)}")

    weights = {s: 1.0 / n_positions for s in picks}
    prev_hash = periods[-1]["record_hash"] if periods else None
    payload = _canonical_payload(as_of, picks, entry_prices)
    record_hash = hashlib.sha256(f"{prev_hash or ''}{payload}".encode()).hexdigest()

    with storage.get_connection() as conn:
        _ensure_schema(conn)
        try:
            conn.execute(
                "INSERT INTO blind_validation_periods (validation_id, rebalance_date, recorded_at, "
                "symbols_json, weights_json, entry_prices_json, git_commit, prev_hash, record_hash) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (validation_id, as_of, pd.Timestamp.now().isoformat(), json.dumps(picks),
                 json.dumps(weights), json.dumps(entry_prices), _current_git_commit(), prev_hash, record_hash),
            )
            conn.commit()
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise ValueError(f"Ya existe un rebalanceo registrado para {as_of} en esta validación — "
                                 "es inmutable, no se puede repetir ni sobrescribir.") from exc
            raise
    return {"rebalance_date": as_of, "symbols": picks, "entry_prices": entry_prices,
           "record_hash": record_hash, "as_of_is_today": as_of == date.today().isoformat()}


def verify_integrity(validation_id: int) -> dict:
    with storage.get_connection() as conn:
        _ensure_schema(conn)
        periods = _get_periods(conn, validation_id)
    prev_hash = None
    for period in periods:
        payload = _canonical_payload(period["rebalance_date"], json.loads(period["symbols_json"]),
                                     json.loads(period["entry_prices_json"]))
        expected = hashlib.sha256(f"{prev_hash or ''}{payload}".encode()).hexdigest()
        if expected != period["record_hash"] or period["prev_hash"] != prev_hash:
            return {"ok": False, "broken_at": period["rebalance_date"], "n_periods": len(periods)}
        prev_hash = period["record_hash"]
    return {"ok": True, "broken_at": None, "n_periods": len(periods)}


def _is_revealed(validation: dict) -> bool:
    if validation["status"] == "broken_early":
        return True
    return date.today().isoformat() >= validation["unlock_date"]


def _last_price_on_or_before(history: pd.DataFrame, as_of_ts: pd.Timestamp) -> float:
    if history.empty or "adj_close" not in history:
        return None
    prices = history[history.index <= as_of_ts]["adj_close"].dropna()
    return float(prices.iloc[-1]) if not prices.empty else None


def _mark_to_market_return(symbols: list, entry_prices: dict, as_of_ts: pd.Timestamp) -> float:
    histories = storage.get_prices_multi(symbols)
    rets = []
    for s in symbols:
        h = histories.get(s, pd.DataFrame())
        h = h[h.index <= as_of_ts] if not h.empty else h
        if h.empty or "adj_close" not in h or h["adj_close"].dropna().empty:
            continue
        last_price = float(h["adj_close"].dropna().iloc[-1])
        rets.append(last_price / entry_prices[s] - 1)
    return float(sum(rets) / len(rets)) if rets else None


def get_status(validation_id: int, reveal: bool = False) -> dict:
    """Sin rendimiento (ninguna clave de retorno/Sharpe) mientras
    `status == 'locked'` y no se haya llegado a `unlock_date`, salvo que se
    pase `reveal=True` explícitamente -- por defecto la UI nunca lo hace sin
    que el usuario pase antes por `break_seal_early`."""
    with storage.get_connection() as conn:
        _ensure_schema(conn)
        validation = _get_validation_row(conn, validation_id)
        if not validation:
            raise ValueError(f"No existe la validación #{validation_id}.")
        periods = _get_periods(conn, validation_id)

    next_rebalance = None
    if periods:
        last_date = pd.Timestamp(periods[-1]["rebalance_date"])
        next_rebalance = (last_date + pd.DateOffset(months=validation["rebalance_months"])).date().isoformat()
    elif validation["start_date"]:
        next_rebalance = validation["start_date"]

    days_to_unlock = (pd.Timestamp(validation["unlock_date"]) - pd.Timestamp(date.today())).days
    base = {
        "id": validation_id, "name": validation["name"], "status": validation["status"],
        "unlock_date": validation["unlock_date"], "n_periods": len(periods),
        "next_rebalance_due": next_rebalance, "days_to_unlock": max(0, days_to_unlock),
        "integrity": verify_integrity(validation_id),
        "revealed": _is_revealed(validation) or reveal,
    }
    if not base["revealed"]:
        return base

    if not periods:
        base["performance"] = None
        return base

    spy_history = storage.get_prices_multi(["SPY"]).get("SPY", pd.DataFrame())
    period_returns = []
    for i, period in enumerate(periods):
        symbols = json.loads(period["symbols_json"])
        entry_prices = json.loads(period["entry_prices_json"])
        rebalance_ts = pd.Timestamp(period["rebalance_date"])
        as_of_ts = (pd.Timestamp(periods[i + 1]["rebalance_date"]) if i + 1 < len(periods)
                   else pd.Timestamp(date.today()))
        ret = _mark_to_market_return(symbols, entry_prices, as_of_ts)
        spy_entry = _last_price_on_or_before(spy_history, rebalance_ts)
        spy_ret = (_mark_to_market_return(["SPY"], {"SPY": spy_entry}, as_of_ts)
                  if spy_entry is not None else None)
        period_returns.append({"rebalance_date": period["rebalance_date"], "retorno": ret,
                               "retorno_spy": spy_ret})
    base["performance"] = {"periods": period_returns}
    return base


def break_seal_early(validation_id: int, reason: str) -> None:
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("Hace falta un motivo para romper el sello antes de tiempo.")
    with storage.get_connection() as conn:
        _ensure_schema(conn)
        conn.execute(
            "UPDATE blind_validations SET status='broken_early', broken_early_at=?, broken_early_reason=? "
            "WHERE id = ?",
            (pd.Timestamp.now().isoformat(), reason, validation_id),
        )
        conn.commit()


def list_validations() -> pd.DataFrame:
    with storage.get_connection() as conn:
        _ensure_schema(conn)
        return pd.read_sql_query("SELECT * FROM blind_validations ORDER BY id DESC", conn)


def export_to_research_lab(validation_id: int) -> int:
    with storage.get_connection() as conn:
        _ensure_schema(conn)
        validation = _get_validation_row(conn, validation_id)
    if not validation:
        raise ValueError(f"No existe la validación #{validation_id}.")
    if not _is_revealed(validation):
        raise ValueError("Esta validación sigue bloqueada -- no se puede exportar sin desbloquear antes.")
    status = get_status(validation_id, reveal=True)
    perf = status.get("performance")
    returns = None
    if perf and perf["periods"]:
        rets = {p["rebalance_date"]: p["retorno"] for p in perf["periods"] if p["retorno"] is not None}
        if rets:
            returns = pd.Series(rets)
            returns.index = pd.to_datetime(returns.index)
    weights = json.loads(validation["weights_json"])
    return log_experiment(
        validation["model_id"], "LIVE_FORWARD", True, git_commit=validation["git_commit_created"],
        universe="S&P 500 en vivo (hoy)", factors="Value/Quality/Momentum/Risk", weights=weights,
        n_positions=validation["n_positions"], rebalance=f"Every {validation['rebalance_months']}mo",
        cost_model="Sin coste (mark-to-market de precios reales, no una cartera ejecutada)",
        is_start=validation["start_date"], is_end=date.today().isoformat(),
        family=f"blind_validation_{validation_id}", n_periods=status["n_periods"], returns=returns,
        notes=f"Blind Forward Validation '{validation['name']}' -- estado {validation['status']}, "
             f"desbloqueo {validation['unlock_date']}.",
        result={"broken_early_reason": validation.get("broken_early_reason")},
    )
