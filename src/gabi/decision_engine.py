"""Decisiones de cartera deterministas a partir de los scores de GABI y los
datos de mercado ya cacheados.

Sin acceso al bróker: la salida es una asignación objetivo fechada y
auditable, con los cambios respecto a la cartera actual — nunca una orden."""
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
import json

import numpy as np
import pandas as pd

from . import evaluation, storage


@dataclass(frozen=True)
class Policy:
    min_score: float = 65.0
    min_coverage: float = 0.70
    max_positions: int = 10
    max_position_pct: float = 5.0
    max_sector_pct: float = 20.0
    max_invested_pct: float = 50.0
    max_volatility: float = 0.60
    min_drawdown: float = -0.50
    max_price_age_days: int = 7
    trade_threshold_pct: float = 0.50


def _recent_price(history: pd.DataFrame, as_of: pd.Timestamp, max_age_days: int) -> bool:
    return (not history.empty and history.index.max() <= as_of
            and (as_of - history.index.max()).days <= max_age_days)


def _reasons(row: pd.Series, history: pd.DataFrame, today: pd.Timestamp, policy: Policy) -> list[str]:
    reasons = []
    if pd.isna(row.get("composite_score")) or row.get("score_coverage", 0) < policy.min_coverage:
        reasons.append("datos insuficientes")
    elif row["composite_score"] < policy.min_score:
        reasons.append("score inferior al umbral")
    if not _recent_price(history, today, policy.max_price_age_days):
        reasons.append("precio ausente o antiguo")
    recent_year = history.loc[today - pd.Timedelta(days=365):today] if not history.empty else history
    if "adj_close" not in recent_year or recent_year["adj_close"].dropna().shape[0] < 126:
        reasons.append("histórico de rentabilidad insuficiente")
    if pd.isna(row.get("price_vs_sma200")) or row.get("price_vs_sma200") <= 0:
        reasons.append("precio bajo SMA200")
    vol = row.get("volatility")
    if pd.isna(vol) or vol > policy.max_volatility:
        reasons.append("volatilidad excesiva o desconocida")
    dd = row.get("max_drawdown")
    if pd.isna(dd) or dd < policy.min_drawdown:
        reasons.append("drawdown excesivo o desconocido")
    return reasons


def _risk_weights(histories: dict[str, pd.DataFrame], symbols: list[str]) -> tuple[dict[str, float], str]:
    """Usa PyPortfolioOpt (mínima volatilidad con contracción/shrinkage); exige datos alineados en el tiempo."""
    if len(symbols) == 1:
        return {symbols[0]: 1.0}, "una empresa"
    prices = pd.concat({s: histories[s]["adj_close"].tail(252) for s in symbols}, axis=1).dropna()
    if len(prices) < 126:
        raise ValueError("Se necesitan al menos 126 sesiones comunes con Adj Close para asignar pesos.")
    if (prices <= 0).any().any():
        raise ValueError("Hay precios no positivos en el histórico.")
    try:
        from pypfopt import EfficientFrontier, risk_models
        cov = risk_models.CovarianceShrinkage(prices).ledoit_wolf()
        ef = EfficientFrontier(None, cov, weight_bounds=(0, 1))
        ef.min_volatility()
        weights = {s: max(0.0, float(w)) for s, w in ef.clean_weights(cutoff=0, rounding=8).items()}
        method = "PyPortfolioOpt: mínima volatilidad y covarianza Ledoit-Wolf"
    except Exception as exc:
        vol = prices.pct_change().dropna().std().replace(0, np.nan)
        if vol.isna().any():
            raise ValueError("No hay volatilidad válida para asignar pesos.")
        weights = (1 / vol).to_dict()
        method = f"respaldo: pesos inversos a volatilidad ({type(exc).__name__})"
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("El optimizador no devolvió pesos válidos.")
    return {s: w / total for s, w in weights.items()}, method


def _portfolio_risk(histories: dict[str, pd.DataFrame], targets: dict[str, float]) -> dict:
    if not targets:
        return {}
    prices = pd.concat({s: histories[s]["adj_close"].tail(252) for s in targets}, axis=1).dropna()
    if len(prices) < 126:
        return {}
    returns = prices.pct_change().dropna().mul(pd.Series(targets)).sum(axis=1)
    try:
        import quantstats as qs
    except ImportError:
        return {"sessions": len(returns), "historical_sharpe": None, "historical_max_drawdown": None}
    return {
        "historical_sharpe": float(qs.stats.sharpe(returns)),
        "historical_max_drawdown": float(qs.stats.max_drawdown(returns)),
        "sessions": len(returns),
    }


def build_plan(table: pd.DataFrame, histories: dict[str, pd.DataFrame], holdings: dict[str, float] | None = None,
               policy: Policy = Policy(), as_of: str | None = None) -> dict:
    """Devuelve decisiones, pesos objetivo y diagnóstico; todos los pesos son % del patrimonio total."""
    as_of_ts = pd.Timestamp(as_of or date.today().isoformat())
    histories = {s: h[h.index <= as_of_ts] if not h.empty else h for s, h in histories.items()}
    holdings = holdings or {}
    if any(v < 0 or v > 100 for v in holdings.values()) or sum(holdings.values()) > 100.001:
        raise ValueError("Las posiciones actuales deben sumar como máximo 100 % y no ser negativas.")
    if not (0 < policy.max_position_pct <= policy.max_sector_pct <= policy.max_invested_pct <= 100):
        raise ValueError("Los límites de posición, sector y capital invertido no son coherentes.")
    if policy.max_positions < 1:
        raise ValueError("Debe permitirse al menos una posición.")

    reasons = {s: _reasons(row, histories.get(s, pd.DataFrame()), as_of_ts, policy)
               for s, row in table.iterrows()}
    protected_pct = sum(weight for symbol, weight in holdings.items()
                        if symbol not in table.index or any(r in reasons.get(symbol, []) for r in
                        ("datos insuficientes", "precio ausente o antiguo",
                         "histórico de rentabilidad insuficiente")))
    investable_budget = min(policy.max_invested_pct, max(0.0, 100.0 - protected_pct))
    candidates = [s for s in table.index if not reasons[s]][:policy.max_positions]
    if not candidates or investable_budget <= 0:
        return _finish(table, holdings, {}, reasons, "sin candidatas", {}, policy)

    raw, method = _risk_weights(histories, candidates)
    targets = {}
    sectors = {}
    for symbol in sorted(candidates, key=lambda s: raw[s], reverse=True):
        sector = table.loc[symbol].get("sector") or "Desconocido"
        room = policy.max_sector_pct - sectors.get(sector, 0.0)
        target = min(raw[symbol] * investable_budget, policy.max_position_pct, room)
        if target > 0:
            targets[symbol] = round(target, 4)
            sectors[sector] = sectors.get(sector, 0.0) + target
    risk = _portfolio_risk(histories, {s: w / 100 for s, w in targets.items()})
    return _finish(table, holdings, targets, reasons, method, risk, policy)


def _finish(table, holdings, targets, reasons, method, risk, policy):
    rows = []
    ordered = list(dict.fromkeys(list(targets) + list(holdings)))
    for symbol in ordered:
        current = float(holdings.get(symbol, 0))
        target = float(targets.get(symbol, 0))
        gap = target - current
        if symbol in holdings and symbol not in table.index:
            action, reason = "REVISAR", "posición fuera del universo analizado"
            target, gap = current, 0.0
        elif symbol in holdings and any(r in reasons.get(symbol, []) for r in
                                        ("datos insuficientes", "precio ausente o antiguo",
                                         "histórico de rentabilidad insuficiente")):
            action, reason = "REVISAR", "datos insuficientes o antiguos para decidir una venta"
            target, gap = current, 0.0
        elif gap > policy.trade_threshold_pct:
            action, reason = "COMPRAR", "cumple reglas y tiene hueco en cartera"
        elif gap < -policy.trade_threshold_pct:
            action, reason = "VENDER" if target == 0 else "REDUCIR", "; ".join(reasons.get(symbol, [])) or "supera peso objetivo"
        else:
            action, reason = "MANTENER", "diferencia menor que el umbral de operación"
        rows.append({"symbol": symbol, "action": action, "current_pct": current,
                     "target_pct": target, "change_pct": gap, "reason": reason,
                     "score": float(table.loc[symbol, "composite_score"]) if symbol in table.index and pd.notna(table.loc[symbol, "composite_score"]) else None})
    return {"decisions": pd.DataFrame(rows), "targets": targets, "rejections": reasons,
            "method": method, "risk": risk,
            "cash_target_pct": max(0, 100 - sum(row["target_pct"] for row in rows))}


def _init_runs(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS decision_runs (id INTEGER PRIMARY KEY, "
                 "created_at TEXT NOT NULL, method TEXT NOT NULL, decisions_json TEXT NOT NULL, "
                 "policy_json TEXT NOT NULL, holdings_json TEXT NOT NULL, name TEXT)")
    columns = {row[1] for row in conn.execute("PRAGMA table_info(decision_runs)")}
    if "name" not in columns:
        conn.execute("ALTER TABLE decision_runs ADD COLUMN name TEXT")
    conn.execute("UPDATE decision_runs SET name='Plan #' || id WHERE name IS NULL OR TRIM(name)='' ")


def _plan_name(name: str) -> str:
    name = name.strip()
    if not name or len(name) > 80:
        raise ValueError("El nombre del plan debe tener entre 1 y 80 caracteres.")
    return name


def save_plan(plan: dict, policy: Policy, holdings: dict[str, float], name: str | None = None) -> int:
    """Guarda exactamente las decisiones generadas, para poder auditarlas más adelante."""
    payload = plan["decisions"].to_json(orient="records")
    created_at = datetime.now(timezone.utc).isoformat()
    name = _plan_name(name) if name is not None else f"Plan {created_at[:16].replace('T', ' ')}"
    with storage.get_connection() as conn:
        _init_runs(conn)
        cur = conn.execute("INSERT INTO decision_runs "
                           "(created_at, method, decisions_json, policy_json, holdings_json, name) VALUES (?,?,?,?,?,?)",
                           (created_at, plan["method"], payload,
                            json.dumps(asdict(policy)), json.dumps(holdings), name))
        conn.commit()
        return cur.lastrowid


def list_saved_plans() -> pd.DataFrame:
    with storage.get_connection() as conn:
        _init_runs(conn)
        conn.commit()
        return pd.read_sql_query("SELECT id, name, created_at, method FROM decision_runs ORDER BY id DESC", conn)


def load_saved_plan(run_id: int) -> pd.DataFrame:
    with storage.get_connection() as conn:
        _init_runs(conn)
        row = conn.execute("SELECT decisions_json FROM decision_runs WHERE id=?", (run_id,)).fetchone()
        conn.commit()
    return pd.DataFrame(json.loads(row[0])) if row else pd.DataFrame()


def plan_progress(run_id: int, cost_bps: float = 0) -> dict:
    """Progreso de un plan guardado desde que se generó (la fecha de
    `created_at`) hasta hoy, ponderado por el peso OBJETIVO real de cada
    posición — a diferencia de un ranking guardado en 📊 Screener, un plan
    de decisiones sí asigna un peso distinto a cada empresa (vía
    PyPortfolioOpt), así que aquí sí hay que ponderar, no promediar a
    partes iguales. Reutiliza las mismas funciones de precio que
    evaluation.py para no duplicar la lógica de tolerancia de fechas."""
    with storage.get_connection() as conn:
        _init_runs(conn)
        row = conn.execute("SELECT created_at, decisions_json FROM decision_runs WHERE id=?", (run_id,)).fetchone()
        conn.commit()
    if not row:
        return {}
    created_at, decisions_json = row
    as_of_date = created_at[:10]
    decisions = pd.DataFrame(json.loads(decisions_json))
    positions = decisions[decisions["target_pct"] > 0] if not decisions.empty else decisions
    if positions.empty:
        return {"as_of_date": as_of_date, "created_at": created_at, "detail": pd.DataFrame(),
                "portfolio_return": None, "benchmark_return": None, "available": 0, "requested": 0,
                "stale": False, "data_as_of": None, "missing": []}

    start = pd.Timestamp(as_of_date)
    today = pd.Timestamp(date.today())
    symbols = positions["symbol"].tolist()
    data_as_of = evaluation._latest_cached_date(symbols + ["SPY"])
    stale = data_as_of is None or data_as_of.normalize() <= start.normalize()

    detail_rows = []
    for _, pos in positions.iterrows():
        symbol, weight = pos["symbol"], float(pos["target_pct"])
        p0 = evaluation._adjusted_at(symbol, start)
        p1 = evaluation._adjusted_at(symbol, today)
        ret = (p1 / p0 - 1 - 2 * cost_bps / 10000) if p0 and p1 else None
        detail_rows.append({"symbol": symbol, "weight_pct": weight, "price_start": p0, "price_now": p1, "return": ret})
    detail = pd.DataFrame(detail_rows)

    valid = detail["return"].notna()
    total_weight = float(detail.loc[valid, "weight_pct"].sum())
    portfolio_return = (
        float((detail.loc[valid, "return"] * detail.loc[valid, "weight_pct"]).sum() / total_weight)
        if total_weight > 0 else None
    )
    b0 = evaluation._adjusted_at("SPY", start)
    b1 = evaluation._adjusted_at("SPY", today)
    benchmark_return = (b1 / b0 - 1 - 2 * cost_bps / 10000) if b0 and b1 else None

    return {
        "as_of_date": as_of_date, "created_at": created_at, "today": today.date().isoformat(),
        "data_as_of": data_as_of.date().isoformat() if data_as_of is not None else None, "stale": stale,
        "detail": detail, "available": int(valid.sum()), "requested": len(positions),
        "portfolio_return": portfolio_return, "benchmark_return": benchmark_return,
        "excess_return": (portfolio_return - benchmark_return)
        if portfolio_return is not None and benchmark_return is not None else None,
        "missing": sorted(set(symbols) - set(detail.loc[valid, "symbol"])),
    }


def plan_price_curve(run_id: int) -> pd.DataFrame:
    """Curva diaria normalizada (base 100 en la fecha del plan) de la
    cartera ponderada por peso objetivo frente al SPY, desde que se generó
    el plan hasta hoy."""
    with storage.get_connection() as conn:
        _init_runs(conn)
        row = conn.execute("SELECT created_at, decisions_json FROM decision_runs WHERE id=?", (run_id,)).fetchone()
        conn.commit()
    if not row:
        return pd.DataFrame()
    created_at, decisions_json = row
    as_of_date = created_at[:10]
    decisions = pd.DataFrame(json.loads(decisions_json))
    positions = decisions[decisions["target_pct"] > 0] if not decisions.empty else decisions
    if positions.empty:
        return pd.DataFrame()
    weights = dict(zip(positions["symbol"], positions["target_pct"].astype(float)))
    start = pd.Timestamp(as_of_date) - pd.Timedelta(days=7)

    histories = storage.get_prices_multi(list(weights) + ["SPY"])
    series = {}
    for symbol in weights:
        h = histories.get(symbol)
        if h is None or h.empty or "adj_close" not in h:
            continue
        s = h["adj_close"].dropna()
        s = s[s.index >= start]
        if not s.empty:
            series[symbol] = s / s.iloc[0] * 100
    if not series:
        return pd.DataFrame()

    aligned = pd.concat(series, axis=1).ffill()
    weight_vec = pd.Series({sym: weights[sym] for sym in aligned.columns})
    basket = aligned.mul(weight_vec, axis=1).sum(axis=1) / weight_vec.sum()

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


def rename_saved_plan(run_id: int, name: str) -> bool:
    name = _plan_name(name)
    with storage.get_connection() as conn:
        _init_runs(conn)
        cur = conn.execute("UPDATE decision_runs SET name=? WHERE id=?", (name, run_id))
        conn.commit()
        return cur.rowcount > 0


def delete_saved_plan(run_id: int) -> bool:
    with storage.get_connection() as conn:
        _init_runs(conn)
        cur = conn.execute("DELETE FROM decision_runs WHERE id=?", (run_id,))
        conn.commit()
        return cur.rowcount > 0
