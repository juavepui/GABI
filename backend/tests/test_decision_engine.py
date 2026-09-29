import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gabi import config, decision_engine, storage


def _seed_to_today(symbol, p_start, p_today, start_date):
    df = pd.DataFrame({
        "Open": [p_start, p_today], "High": [p_start, p_today], "Low": [p_start, p_today],
        "Close": [p_start, p_today], "Adj Close": [p_start, p_today], "Volume": [100, 100],
    }, index=pd.to_datetime([start_date, date.today().isoformat()]))
    storage.upsert_prices(symbol, df)


def _history():
    dates = pd.date_range("2026-01-01", periods=180, freq="B")
    return pd.DataFrame({"adj_close": [100 + i * .1 for i in range(180)]}, index=dates)


def _table():
    return pd.DataFrame({
        "composite_score": [80, 75, 72], "score_coverage": [.9, .9, .9],
        "price_vs_sma200": [.1, .1, -.1], "volatility": [.2, .3, .2],
        "max_drawdown": [-.2, -.3, -.2], "sector": ["Tech", "Tech", "Energy"],
    }, index=["AAA", "BBB", "CCC"])


def test_decisions_respect_sector_and_position_caps(monkeypatch):
    monkeypatch.setattr(decision_engine, "_risk_weights",
                        lambda h, s: ({"AAA": .6, "BBB": .4}, "fake optimiser"))
    monkeypatch.setattr(decision_engine, "_portfolio_risk", lambda h, w: {})
    history = _history()
    plan = decision_engine.build_plan(_table(), {s: history for s in "AAA BBB CCC".split()},
                                      {"AAA": 1, "CCC": 2},
                                      decision_engine.Policy(max_position_pct=5, max_sector_pct=8),
                                      as_of="2026-09-10")
    assert plan["targets"]["AAA"] == 5
    assert plan["targets"]["BBB"] == 3
    actions = plan["decisions"].set_index("symbol")["action"]
    assert actions["AAA"] == "COMPRAR"
    assert actions["BBB"] == "COMPRAR"
    assert actions["CCC"] == "VENDER"


def test_stale_holding_is_review_not_sell():
    table = _table().iloc[:1]
    plan = decision_engine.build_plan(table, {}, {"AAA": 4}, as_of="2026-09-10")
    row = plan["decisions"].iloc[0]
    assert row["action"] == "REVISAR"
    assert row["target_pct"] == 4
    assert plan["cash_target_pct"] == 96


def test_unreviewable_holding_reserves_capital(monkeypatch):
    monkeypatch.setattr(decision_engine, "_risk_weights", lambda h, s: ({"AAA": 1.0}, "fake"))
    monkeypatch.setattr(decision_engine, "_portfolio_risk", lambda h, w: {})
    table = _table().iloc[:1]
    plan = decision_engine.build_plan(table, {"AAA": _history()}, {"UNKNOWN": 98},
                                      decision_engine.Policy(max_position_pct=5), as_of="2026-09-10")
    assert plan["targets"]["AAA"] == 2
    assert plan["cash_target_pct"] == 0


def test_invalid_holdings_are_rejected():
    try:
        decision_engine.build_plan(_table(), {}, {"AAA": 101})
    except ValueError as exc:
        assert "100" in str(exc)
    else:
        raise AssertionError("must reject impossible holdings")


def test_real_portfolio_libraries_produce_capped_plan():
    dates = pd.date_range("2026-01-01", periods=180, freq="B")
    histories = {
        "AAA": pd.DataFrame({"adj_close": [100 + i * .12 + (i % 7) * .15 for i in range(180)]}, index=dates),
        "BBB": pd.DataFrame({"adj_close": [90 + i * .08 + (i % 5) * .25 for i in range(180)]}, index=dates),
    }
    plan = decision_engine.build_plan(_table().iloc[:2], histories, as_of=dates[-1].date().isoformat())
    assert plan["method"].startswith("PyPortfolioOpt")
    assert sum(plan["targets"].values()) <= 10
    assert plan["risk"]["sessions"] >= 126


def test_plan_audit_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    plan = {"decisions": pd.DataFrame([{"symbol": "AAA", "action": "COMPRAR"}]), "method": "test"}
    run_id = decision_engine.save_plan(plan, decision_engine.Policy(), {"AAA": 2})
    assert decision_engine.list_saved_plans().iloc[0]["id"] == run_id
    assert decision_engine.load_saved_plan(run_id).iloc[0]["action"] == "COMPRAR"
    assert decision_engine.rename_saved_plan(run_id, "Prueba renovada")
    assert decision_engine.list_saved_plans().iloc[0]["name"] == "Prueba renovada"
    assert decision_engine.delete_saved_plan(run_id)
    assert decision_engine.list_saved_plans().empty


def _backdate_plan(run_id, days_ago):
    """save_plan siempre usa datetime.now() real como created_at (fecha de
    origen del plan) — para poder probar 'progreso desde entonces hasta
    hoy' hace falta retrasarlo manualmente, igual que ya hace
    test_existing_plan_table_gets_name_column con una fila insertada a mano."""
    past = (pd.Timestamp(date.today()) - pd.Timedelta(days=days_ago)).isoformat()
    with storage.get_connection() as conn:
        conn.execute("UPDATE decision_runs SET created_at=? WHERE id=?", (past, run_id))
        conn.commit()
    return past[:10]


def test_plan_progress_weights_by_target_pct_not_equally(tmp_path, monkeypatch):
    """A diferencia de un ranking de Screener (equiponderado), un plan de
    decisiones SI pondera por target_pct real de cada posicion."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    plan = {"decisions": pd.DataFrame([
        {"symbol": "AAA", "action": "COMPRAR", "target_pct": 80.0},
        {"symbol": "BBB", "action": "COMPRAR", "target_pct": 20.0},
    ]), "method": "test"}
    run_id = decision_engine.save_plan(plan, decision_engine.Policy(), {})
    origin_date = _backdate_plan(run_id, days_ago=3)
    _seed_to_today("AAA", 100, 150, origin_date)  # +50%, pesa 80%
    _seed_to_today("BBB", 100, 100, origin_date)  # +0%, pesa 20%
    _seed_to_today("SPY", 100, 110, origin_date)  # +10%

    result = decision_engine.plan_progress(run_id)
    assert result["requested"] == 2
    assert result["available"] == 2
    # 0.8*50% + 0.2*0% = 40%, NO el 25% que saldria equiponderado
    assert round(result["portfolio_return"], 3) == .40
    assert round(result["benchmark_return"], 3) == .10
    assert len(result["detail"]) == 2


def test_plan_progress_ignores_zero_weight_positions(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    plan = {"decisions": pd.DataFrame([
        {"symbol": "AAA", "action": "COMPRAR", "target_pct": 100.0},
        {"symbol": "CCC", "action": "VENDER", "target_pct": 0.0},
    ]), "method": "test"}
    run_id = decision_engine.save_plan(plan, decision_engine.Policy(), {})
    result = decision_engine.plan_progress(run_id)
    assert result["requested"] == 1  # CCC (peso 0, ya fuera de cartera) no cuenta


def test_plan_price_curve_weighted_normalizes_to_100(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    plan = {"decisions": pd.DataFrame([
        {"symbol": "AAA", "action": "COMPRAR", "target_pct": 75.0},
        {"symbol": "BBB", "action": "COMPRAR", "target_pct": 25.0},
    ]), "method": "test"}
    run_id = decision_engine.save_plan(plan, decision_engine.Policy(), {})
    origin_date = _backdate_plan(run_id, days_ago=3)
    _seed_to_today("AAA", 100, 200, origin_date)  # x2
    _seed_to_today("BBB", 100, 100, origin_date)  # sin cambio
    _seed_to_today("SPY", 100, 105, origin_date)

    curve = decision_engine.plan_price_curve(run_id)
    assert curve.iloc[0]["Cartera"] == 100
    # 0.75*200 + 0.25*100 = 175
    assert round(curve.iloc[-1]["Cartera"], 1) == 175.0
    assert round(curve.iloc[-1]["SPY"], 1) == 105.0


def test_existing_plan_table_gets_name_column(tmp_path, monkeypatch):
    from gabi import storage
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    with storage.get_connection() as conn:
        conn.execute("CREATE TABLE decision_runs (id INTEGER PRIMARY KEY, created_at TEXT, method TEXT, "
                     "decisions_json TEXT, policy_json TEXT, holdings_json TEXT)")
        conn.execute("INSERT INTO decision_runs VALUES (1, '2026-01-01', 'test', '[]', '{}', '{}')")
        conn.commit()
    saved = decision_engine.list_saved_plans()
    assert saved.iloc[0]["name"] == "Plan #1"
    assert decision_engine.rename_saved_plan(1, "Histórico")
    assert decision_engine.list_saved_plans().iloc[0]["name"] == "Histórico"


# --- Portfolio Engine V2: optimizador con límites dentro del problema (opt-in) ---

def _diverse_histories(symbols, n=200):
    dates = pd.date_range("2026-01-01", periods=n, freq="B")
    histories = {}
    for i, symbol in enumerate(symbols):
        base = 50 + i * 20
        trend = 0.05 + i * 0.03
        noise_period = 5 + i
        prices = [base + j * trend + (j % noise_period) * (0.3 + i * 0.1) for j in range(n)]
        histories[symbol] = pd.DataFrame({"adj_close": prices}, index=dates)
    return histories


def test_risk_weights_constrained_respects_position_and_sector_bounds():
    symbols = ["AAA", "BBB", "CCC", "DDD"]
    histories = _diverse_histories(symbols)
    sector_by_symbol = {"AAA": "Tech", "BBB": "Tech", "CCC": "Energy", "DDD": "Energy"}
    # Presupuesto invertible 50; limite por posicion 20 (=0.4 de fraccion) y por
    # sector 30 (=0.6): factible (4*0.4=1.6 >= 1, 2*0.6=1.2 >= 1) y a la vez
    # mas estrecho que dejar que 2 posiciones de 0.4 llenen un sector (0.8 > 0.6).
    weights, method, ok = decision_engine._risk_weights_constrained(
        histories, symbols, investable_budget=50.0, max_position_pct=20.0, max_sector_pct=30.0,
        sector_by_symbol=sector_by_symbol,
    )
    assert ok is True
    assert method.startswith("PyPortfolioOpt")
    for w in weights.values():
        assert w <= 0.4 + 1e-6
    tech_total = weights.get("AAA", 0) + weights.get("BBB", 0)
    energy_total = weights.get("CCC", 0) + weights.get("DDD", 0)
    assert tech_total <= 0.6 + 1e-6
    assert energy_total <= 0.6 + 1e-6


def test_risk_weights_constrained_falls_back_when_bounds_infeasible():
    """max_positions*max_position_pct < max_invested_pct -> imposible sumar
    el 100% del presupuesto invertible dentro del limite por posicion.
    Debe caer a _risk_weights sin restringir, no lanzar excepcion."""
    symbols = ["AAA", "BBB"]
    histories = _diverse_histories(symbols)
    sector_by_symbol = {"AAA": "Tech", "BBB": "Tech"}
    weights, method, ok = decision_engine._risk_weights_constrained(
        histories, symbols, investable_budget=50.0, max_position_pct=1.0,  # 1/50=0.02 * 2 = 0.04 << 1.0
        max_sector_pct=1.0, sector_by_symbol=sector_by_symbol,
    )
    assert ok is False
    assert "recortados después" in method
    assert sum(weights.values()) == pytest.approx(1.0)


def test_build_plan_constrained_optimizer_targets_respect_caps(monkeypatch):
    table = pd.DataFrame({
        "composite_score": [80, 78, 76, 74], "score_coverage": [.9, .9, .9, .9],
        "price_vs_sma200": [.1, .1, .1, .1], "volatility": [.2, .2, .2, .2],
        "max_drawdown": [-.2, -.2, -.2, -.2], "sector": ["Tech", "Tech", "Energy", "Energy"],
    }, index=["AAA", "BBB", "CCC", "DDD"])
    histories = _diverse_histories(list(table.index))
    monkeypatch.setattr(decision_engine, "_portfolio_risk", lambda h, w: {})
    policy = decision_engine.Policy(max_position_pct=20, max_sector_pct=30, max_invested_pct=50,
                                    constrained_optimizer=True)
    plan = decision_engine.build_plan(table, histories, {}, policy, as_of=list(histories.values())[0].index[-1].date().isoformat())
    assert plan["method"].startswith("PyPortfolioOpt")
    assert "dentro del problema" in plan["method"]
    for target in plan["targets"].values():
        assert target <= 20.0 + 1e-6
    tech = sum(w for s, w in plan["targets"].items() if s in ("AAA", "BBB"))
    energy = sum(w for s, w in plan["targets"].items() if s in ("CCC", "DDD"))
    assert tech <= 30.0 + 1e-6
    assert energy <= 30.0 + 1e-6


def test_turnover_penalty_keeps_weights_closer_to_previous_holdings():
    symbols = ["AAA", "BBB", "CCC"]
    histories = _diverse_histories(symbols)
    sector_by_symbol = {"AAA": "Tech", "BBB": "Tech", "CCC": "Energy"}
    # Cartera actual muy alejada del minimo-varianza natural (todo en AAA).
    w_prev = {"AAA": 1.0, "BBB": 0.0, "CCC": 0.0}

    no_penalty, _, ok1 = decision_engine._risk_weights_constrained(
        histories, symbols, investable_budget=50.0, max_position_pct=50.0, max_sector_pct=100.0,
        sector_by_symbol=sector_by_symbol, w_prev=w_prev, turnover_penalty=0.0,
    )
    with_penalty, method, ok2 = decision_engine._risk_weights_constrained(
        histories, symbols, investable_budget=50.0, max_position_pct=50.0, max_sector_pct=100.0,
        sector_by_symbol=sector_by_symbol, w_prev=w_prev, turnover_penalty=5.0,
    )
    assert ok1 and ok2
    assert "penalización por turnover" in method

    def _distance(w):
        return sum(abs(w.get(s, 0) - w_prev[s]) for s in symbols)

    assert _distance(with_penalty) <= _distance(no_penalty) + 1e-9
