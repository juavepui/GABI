import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gabi import config, edgar, storage
from gabi import multifactor_backtest as bt


def _seed_prices(dates, symbol_closes):
    for symbol, closes in symbol_closes:
        storage.upsert_prices(symbol, pd.DataFrame({"Open": closes, "High": closes,
            "Low": closes, "Close": closes, "Adj Close": closes, "Volume": [1] * len(closes)}, index=dates))


def _seed_filing(symbol, filed_date):
    edgar.upsert_edgar_facts(symbol, [{
        "tag": "NetIncomeLoss", "unit": "USD", "start_date": "2020-01-01", "end_date": "2020-12-31",
        "val": 1, "form": "10-K", "fp": "FY", "fy": 2020, "filed_date": filed_date, "accn": "0001-20-000001",
    }])


def test_rebalances_using_each_periods_ranking(monkeypatch):
    seen = []
    monkeypatch.setattr(bt.universe, "get_sp500_constituents_asof",
                        lambda day: {"is_exact": True, "symbols": ["AAA", "BBB"], "note": ""})

    def rank(day, symbols):
        seen.append(day)
        winner = "AAA" if len(seen) == 1 else "BBB"
        return {"table": pd.DataFrame({"composite_score": [80, 70], "score_coverage": [.9, .9]},
                                      index=[winner, "BBB" if winner == "AAA" else "AAA"])}

    monkeypatch.setattr(bt.screener_asof, "build_ranking_as_of", rank)
    monkeypatch.setattr(bt, "_period_returns",
                        lambda symbols, day, months, cost, held_symbols=None: {"end_date": str(day.date()),
                                                             "portfolio_return": .1, "benchmark_return": .05})
    result = bt.run("2023-01-02", "2023-07-02", months=3, top_n=1)
    assert seen == ["2023-01-02", "2023-04-02"]
    assert result["periods"]["candidatas"].tolist() == ["AAA", "BBB"]
    assert result["return"] == pytest.approx(.21)


def test_required_symbols_unions_memberships(monkeypatch):
    monkeypatch.setattr(bt.universe, "get_sp500_constituents_asof",
                        lambda day: {"is_exact": True,
                                     "symbols": ["AAA"] if day.endswith("01-02") else ["BBB"]})
    assert bt.required_symbols("2023-01-02", "2023-07-02", 3) == ["AAA", "BBB"]


def test_default_min_universe_coverage_is_low_enough_for_pre_2022_history():
    """~16% de los simbolos necesarios para cubrir 2016-2025 no resuelven CIK
    en SEC EDGAR (empresas deslistadas antes de 2022 que ya no aparecen en
    company_tickers.json) -- eso limita la cobertura alcanzable de cualquier
    trimestre anterior a 2022 a un techo estructural de ~57-69%, comprobado
    con datos reales. Un default mas alto que eso descarta en silencio TODO
    2016-2021 (incluido el crash de covid) en cualquier backtest lanzado
    desde la UI con los valores por defecto -- ver README, "Verificacion
    final: un tercer problema de medida"."""
    import inspect
    assert inspect.signature(bt.run).parameters["min_universe_coverage"].default <= 0.5


def test_rejects_when_every_period_lacks_coverage(monkeypatch):
    """Si TODOS los periodos del rango carecen de composición histórica
    verificable, no hay nada que backtest-ear: debe fallar."""
    monkeypatch.setattr(bt.universe, "get_sp500_constituents_asof",
                        lambda day: {"is_exact": False, "note": "fuera de cobertura"})
    with pytest.raises(ValueError, match="Ningún periodo"):
        bt.run("2023-01-02", "2023-04-02")


def test_skips_single_bad_period_instead_of_aborting_whole_range(monkeypatch):
    """Un solo trimestre sin cobertura suficiente (frecuente en años con poca
    cobertura SEC EDGAR) no debe tumbar todo el backtest — se salta y se
    sigue con los periodos que sí tienen datos."""
    monkeypatch.setattr(bt.universe, "get_sp500_constituents_asof",
                        lambda day: {"is_exact": True, "symbols": ["AAA", "BBB"], "note": ""})

    def rank(day, symbols):
        if day == "2023-01-02":  # primer periodo: sin cobertura suficiente
            return {"table": pd.DataFrame({"composite_score": [80, None], "score_coverage": [.9, 0]},
                                          index=symbols)}
        return {"table": pd.DataFrame({"composite_score": [80, 70], "score_coverage": [.9, .9]},
                                      index=symbols)}

    monkeypatch.setattr(bt.screener_asof, "build_ranking_as_of", rank)
    monkeypatch.setattr(bt, "_period_returns",
                        lambda symbols, day, months, cost, held_symbols=None: {"end_date": str(day.date()),
                                                             "portfolio_return": .1, "benchmark_return": .05})
    # min_universe_coverage explicito: el test verifica el mecanismo de saltar
    # y seguir, no el valor por defecto (que ya no es 0.7 -- ver docstring de
    # run() sobre el techo estructural de cobertura pre-2022).
    result = bt.run("2023-01-02", "2023-07-02", months=3, top_n=1, min_universe_coverage=.7)
    assert len(result["periods"]) == 1
    assert len(result["skipped"]) == 1
    assert result["skipped"][0]["fecha"] == "2023-01-02"
    assert "cobertura insuficiente" in result["skipped"][0]["motivo"]


def test_period_buys_after_signal_session(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    dates = pd.to_datetime(["2024-01-05", "2024-01-08", "2024-02-05"])
    for symbol, closes in (("AAA", [100, 200, 220]), ("SPY", [100, 100, 110])):
        storage.upsert_prices(symbol, pd.DataFrame({"Open": closes, "High": closes,
            "Low": closes, "Close": closes, "Adj Close": closes, "Volume": [1] * 3}, index=dates))
    result = bt._period_returns(["AAA"], pd.Timestamp("2024-01-05"), 1, 0)
    assert result["portfolio_return"] == pytest.approx(.1)
    assert result["benchmark_return"] == pytest.approx(.1)


def test_period_returns_charges_no_cost_to_held_symbols(tmp_path, monkeypatch):
    """Sin held_symbols, cost_bps se cobra a todo el mundo -- con
    held_symbols, una posicion que ya se tenia en el periodo anterior no
    paga coste de entrada/salida porque no se ha comprado ni vendido nada."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    dates = pd.to_datetime(["2024-01-05", "2024-01-08", "2024-02-05"])
    for symbol, closes in (("AAA", [100, 100, 110]), ("BBB", [100, 100, 110]), ("SPY", [100, 100, 100])):
        storage.upsert_prices(symbol, pd.DataFrame({"Open": closes, "High": closes,
            "Low": closes, "Close": closes, "Adj Close": closes, "Volume": [1] * 3}, index=dates))

    no_buffer = bt._period_returns(["AAA", "BBB"], pd.Timestamp("2024-01-05"), 1, 100)
    with_held = bt._period_returns(["AAA", "BBB"], pd.Timestamp("2024-01-05"), 1, 100,
                                   held_symbols={"AAA"})
    assert with_held["portfolio_return"] > no_buffer["portfolio_return"]  # menos coste total
    raw_return = .10  # 110/100 - 1, sin coste
    aaa_no_cost = raw_return  # held: factor=1.0
    bbb_with_cost = (1 + raw_return) * (1 - 100 / 10000) ** 2 - 1
    assert with_held["portfolio_return"] == pytest.approx((aaa_no_cost + bbb_with_cost) / 2)


def test_period_returns_charges_no_cost_to_spy(tmp_path, monkeypatch):
    """SPY es la referencia pasiva (comprar y mantener), no una posición que
    se rota cada rebalanceo -- nunca debe pagar el coste de compra/venta,
    a diferencia de las posiciones de la estrategia (que sí lo pagan salvo
    que estén en held_symbols)."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    dates = pd.to_datetime(["2024-01-05", "2024-01-08", "2024-02-05"])
    for symbol, closes in (("AAA", [100, 100, 110]), ("SPY", [100, 100, 110])):
        storage.upsert_prices(symbol, pd.DataFrame({"Open": closes, "High": closes,
            "Low": closes, "Close": closes, "Adj Close": closes, "Volume": [1] * 3}, index=dates))

    result = bt._period_returns(["AAA"], pd.Timestamp("2024-01-05"), 1, 100)
    assert result["benchmark_return"] == pytest.approx(.10)  # SPY: sin coste
    assert result["portfolio_return"] < .10  # AAA: con coste, al no estar en held_symbols


def test_risk_metrics_on_steady_positive_returns():
    """Una serie de retornos trimestrales positivos (con algo de variación,
    si no la volatilidad es 0 y Sharpe queda indefinido) debe dar
    Sharpe/Sortino positivos y drawdown cero (nunca cae respecto a su máximo)."""
    returns = pd.Series([.02, -.01, .03, .05])
    m = bt._risk_metrics(returns, periods_per_year=4)
    assert m["anualizado"] > 0
    assert m["sharpe"] > 0
    assert m["sortino"] > 0
    assert m["max_drawdown"] < 0


def test_risk_metrics_flags_drawdown_after_a_loss():
    returns = pd.Series([.10, -.20, .05])
    m = bt._risk_metrics(returns, periods_per_year=4)
    assert m["max_drawdown"] < 0


def test_run_includes_universo_ew_benchmark_and_metrics(monkeypatch):
    monkeypatch.setattr(bt.universe, "get_sp500_constituents_asof",
                        lambda day: {"is_exact": True, "symbols": ["AAA", "BBB"], "note": ""})
    monkeypatch.setattr(bt.screener_asof, "build_ranking_as_of",
                        lambda day, symbols: {"table": pd.DataFrame(
                            {"composite_score": [80, 70], "score_coverage": [.9, .9]}, index=symbols)})

    def fake_period_returns(symbols, day, months, cost, held_symbols=None):
        # El universo completo (2 empresas) rinde distinto que el top-1, para
        # poder comprobar que no son la misma columna por accidente.
        portfolio_return = .1 if len(symbols) == 1 else .04
        return {"end_date": str(day.date()), "portfolio_return": portfolio_return, "benchmark_return": .05}

    monkeypatch.setattr(bt, "_period_returns", fake_period_returns)
    result = bt.run("2023-01-02", "2023-04-02", months=3, top_n=1)
    assert result["periods"]["universo_ew"].iloc[0] == pytest.approx(.04)
    assert result["universo_ew_return"] == pytest.approx(.04)
    assert set(result["metrics"]) == {"estrategia", "universo_ew", "spy"}


def test_period_returns_rejects_symbol_with_no_recent_sec_filing(tmp_path, monkeypatch):
    """Si una empresa lleva años sin presentar nada ante la SEC pero yfinance
    sigue devolviendo cotización 'viva' bajo su ticker, lo más probable es
    que la bolsa haya reciclado ese símbolo a otra empresa distinta (caso
    real comprobado: BBBY) — debe rechazarse en vez de usarse en silencio."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    dates = pd.to_datetime(["2024-01-05", "2024-01-08", "2024-02-05"])
    _seed_prices(dates, [("ZOMBIE", [100, 200, 220]), ("SPY", [100, 100, 110])])
    _seed_filing("ZOMBIE", "2018-01-01")  # ultimo filing hace mas de 450 dias
    with pytest.raises(ValueError, match="reciclado"):
        bt._period_returns(["ZOMBIE"], pd.Timestamp("2024-01-05"), 1, 0)


def test_period_returns_accepts_symbol_with_recent_sec_filing(tmp_path, monkeypatch):
    """Una empresa que sí sigue presentando filings regularmente no debe
    activar la comprobación de reciclaje, aunque tenga historial en edgar_facts."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    dates = pd.to_datetime(["2024-01-05", "2024-01-08", "2024-02-05"])
    _seed_prices(dates, [("AAA", [100, 200, 220]), ("SPY", [100, 100, 110])])
    _seed_filing("AAA", "2024-01-01")  # filing reciente, empresa viva
    result = bt._period_returns(["AAA"], pd.Timestamp("2024-01-05"), 1, 0)
    assert result["portfolio_return"] == pytest.approx(.1)


def test_period_returns_ignores_future_filing_from_recycled_ticker(tmp_path, monkeypatch):
    """Caso señalado en revisión externa: si el guard de reciclaje mirase el
    filing MÁS RECIENTE sin acotar por fecha, un ticker reciclado a una
    empresa nueva que SÍ presenta filings (pero años después del periodo que
    se evalúa) coincidiría con un filing 'reciente' y el guard no saltaría
    -- justo el fallo que se supone que detecta. Aquí la empresa tiene un
    filing viejo (2018) Y uno futuro (2026, de la 'empresa nueva' que se
    quedó el ticker) -- el guard debe usar solo lo conocido HASTA la fecha
    evaluada (2024) e ignorar el filing futuro."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    dates = pd.to_datetime(["2024-01-05", "2024-01-08", "2024-02-05"])
    _seed_prices(dates, [("ZOMBIE", [100, 200, 220]), ("SPY", [100, 100, 110])])
    _seed_filing("ZOMBIE", "2018-01-01")
    edgar.upsert_edgar_facts("ZOMBIE", [{
        "tag": "NetIncomeLoss", "unit": "USD", "start_date": "2026-01-01", "end_date": "2026-12-31",
        "val": 1, "form": "10-K", "fp": "FY", "fy": 2026, "filed_date": "2026-03-01", "accn": "0002-26-000001",
    }])
    with pytest.raises(ValueError, match="reciclado"):
        bt._period_returns(["ZOMBIE"], pd.Timestamp("2024-01-05"), 1, 0)


def test_holding_buffer_disabled_uses_strict_top_n():
    ranked_pool = ["A", "B", "C", "D", "E"]
    picks = bt._apply_holding_buffer(["X", "Y"], ranked_pool, top_n=3, buffer_multiplier=1.0)
    assert picks == ["A", "B", "C"]  # sin banda: top-N estricto, ignora lo que hubiera antes


def test_holding_buffer_keeps_position_that_slipped_but_stays_in_band():
    # "C" era una posicion en cartera; ahora ha caido al puesto 4, fuera del
    # top-3 estricto pero dentro de la banda ampliada (top_n*2=6).
    ranked_pool = ["A", "B", "D", "C", "E", "F", "G"]
    picks = bt._apply_holding_buffer(["C", "X", "Y"], ranked_pool, top_n=3, buffer_multiplier=2.0)
    assert "C" in picks  # se mantiene aunque ya no este en el top-3 estricto
    assert len(picks) == 3


def test_holding_buffer_sells_position_that_falls_outside_the_band():
    # "Z" ha caido fuera incluso de la banda ampliada (top_n*1.5=4 con top_n=3, redondeado a 4)
    ranked_pool = ["A", "B", "C", "D", "E", "Z"]
    picks = bt._apply_holding_buffer(["Z"], ranked_pool, top_n=3, buffer_multiplier=1.5)
    assert "Z" not in picks
    assert picks == ["A", "B", "C"]


def test_holding_buffer_reduces_turnover_across_a_full_run(monkeypatch):
    """Con la banda activa, una empresa que sube y baja de posicion sin salir
    de la banda ancha no se compra/vende cada trimestre -- turnover mas bajo
    que con top-N estricto para la misma serie de rankings."""
    monkeypatch.setattr(bt.universe, "get_sp500_constituents_asof",
                        lambda day: {"is_exact": True, "symbols": ["A", "B", "C", "D"], "note": ""})
    # El ranking alterna C dentro/fuera del top-2 estricto cada periodo, pero
    # siempre se queda dentro del top-4 (banda con buffer_multiplier=2.0, top_n=2).
    scores_by_period = {
        "2023-01-02": {"A": 90, "C": 80, "B": 70, "D": 60},
        "2023-04-02": {"A": 90, "B": 85, "C": 80, "D": 60},
        "2023-07-02": {"A": 90, "C": 80, "B": 70, "D": 60},
    }

    def rank(day, symbols):
        scores = scores_by_period[day]
        ordered = sorted(symbols, key=lambda s: -scores[s])
        return {"table": pd.DataFrame({"composite_score": [scores[s] for s in ordered],
                                       "score_coverage": [.9] * len(ordered)}, index=ordered)}

    monkeypatch.setattr(bt.screener_asof, "build_ranking_as_of", rank)
    monkeypatch.setattr(bt, "_period_returns",
                        lambda symbols, day, months, cost, held_symbols=None: {"end_date": str((day + pd.DateOffset(months=months)).date()),
                                                             "portfolio_return": .01, "benchmark_return": .01})

    strict = bt.run("2023-01-02", "2023-10-02", months=3, top_n=2, buffer_multiplier=1.0)
    buffered = bt.run("2023-01-02", "2023-10-02", months=3, top_n=2, buffer_multiplier=2.0)
    assert buffered["turnover_medio"] < strict["turnover_medio"]
    # con la banda, "C" se mantiene todo el tiempo aunque salga del top-2 estricto en el segundo periodo
    assert all("C" in row for row in buffered["periods"]["candidatas"])


def test_run_annualizes_by_real_calendar_span_not_period_count(monkeypatch):
    """Si se salta un periodo, los años reales transcurridos son mayores que
    len(periodos_validos)/periodos_por_año -- anualizar con el recuento
    (el bug señalado en revisión externa) infla el retorno anualizado."""
    monkeypatch.setattr(bt.universe, "get_sp500_constituents_asof",
                        lambda day: {"is_exact": True, "symbols": ["AAA"], "note": ""})

    def rank(day, symbols):
        # El periodo de abril se salta (cobertura insuficiente); enero y julio si.
        if day == "2023-04-02":
            return {"table": pd.DataFrame({"composite_score": [None], "score_coverage": [0]}, index=symbols)}
        return {"table": pd.DataFrame({"composite_score": [80], "score_coverage": [.9]}, index=symbols)}

    monkeypatch.setattr(bt.screener_asof, "build_ranking_as_of", rank)

    def fake_period_returns(symbols, day, months, cost, held_symbols=None):
        end = day + pd.DateOffset(months=months)
        return {"end_date": end.date().isoformat(), "portfolio_return": .1, "benchmark_return": .05}

    monkeypatch.setattr(bt, "_period_returns", fake_period_returns)
    result = bt.run("2023-01-02", "2023-10-02", months=3, top_n=1)
    assert len(result["periods"]) == 2  # enero y julio; abril saltado
    assert len(result["skipped"]) == 1

    # 2 periodos validos de +10% cada uno = +21% acumulado, pero el primero
    # empieza en enero y el ultimo termina en octubre: 9 meses reales de
    # calendario (0.75 anios), NO 2 periodos/4 = 0.5 anios como saldria
    # contando solo periodos validos.
    naive_years = 2 / 4  # el calculo INCORRECTO que habria dado el bug
    correct_years = (pd.Timestamp("2023-10-02") - pd.Timestamp("2023-01-02")).days / 365.25
    assert correct_years > naive_years * 1.3  # confirma que el hueco importa

    ann_naive = (1.21) ** (1 / naive_years) - 1
    ann_correct = result["metrics"]["estrategia"]["anualizado"]
    assert ann_correct < ann_naive  # el anualizado correcto es menor, no inflado
    assert ann_correct == pytest.approx((1.21) ** (1 / correct_years) - 1, rel=1e-6)


def test_daily_capital_curve_reveals_intraperiod_drawdown(tmp_path, monkeypatch):
    """La curva diaria debe revelar una caida y recuperacion completa DENTRO
    de un periodo -- invisible para periods["capital"], que solo mira el
    cierre de cada periodo (el problema senalado en revision externa)."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    calendar = bt.xcals.get_calendar("XNYS")
    as_of = pd.Timestamp("2024-01-05")
    signal_session = calendar.date_to_session(as_of, direction="previous")
    entry = calendar.next_session(signal_session)
    exit_session = calendar.date_to_session(as_of + pd.DateOffset(months=3), direction="next")
    sessions = calendar.sessions_in_range(entry, exit_session)
    assert len(sessions) > 10  # suficientes sesiones para un dip y recuperacion claros

    # AAA cae un 30% a mitad del periodo y se recupera para terminar en +5%.
    mid = len(sessions) // 2
    prices = [100.0] * len(sessions)
    prices[mid] = 70.0
    prices[-1] = 105.0
    # interpola el resto de forma monotona hacia el dip y de vuelta, no aporta
    # nada al test pero evita un salto brusco irrealista en un solo dia
    for i in range(1, mid):
        prices[i] = 100 - (30 * i / mid)
    for i in range(mid + 1, len(sessions) - 1):
        frac = (i - mid) / (len(sessions) - 1 - mid)
        prices[i] = 70 + (35 * frac)

    df = pd.DataFrame({"Open": prices, "High": prices, "Low": prices, "Close": prices,
                       "Adj Close": prices, "Volume": [1] * len(prices)}, index=sessions)
    storage.upsert_prices("AAA", df)

    periods = pd.DataFrame([{
        "fecha": as_of.date().isoformat(), "hasta": exit_session.date().isoformat(),
        "candidatas": "AAA", "retorno": 0.05,
    }])
    curve = bt.daily_capital_curve(periods)
    assert len(curve) == len(sessions)
    assert curve.iloc[-1] == pytest.approx(1.05, abs=1e-6)  # coincide con el retorno ya validado
    metrics = bt.daily_risk_metrics(curve)
    assert metrics["max_drawdown"] < -0.25  # revela el dip real, no 0% como periods["capital"] veria


def test_daily_capital_curve_chains_periods_compounding_correctly(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    calendar = bt.xcals.get_calendar("XNYS")
    as_of1 = pd.Timestamp("2024-01-05")
    entry1 = calendar.next_session(calendar.date_to_session(as_of1, direction="previous"))
    exit1 = calendar.date_to_session(as_of1 + pd.DateOffset(months=3), direction="next")
    exit2 = calendar.date_to_session(exit1 + pd.DateOffset(months=3), direction="next")

    for symbol in ("AAA", "BBB"):
        sessions = calendar.sessions_in_range(entry1, exit2)
        storage.upsert_prices(symbol, pd.DataFrame(
            {"Open": [100.0] * len(sessions), "High": [100.0] * len(sessions), "Low": [100.0] * len(sessions),
             "Close": [100.0] * len(sessions), "Adj Close": [100.0] * len(sessions), "Volume": [1] * len(sessions)},
            index=sessions))

    periods = pd.DataFrame([
        {"fecha": as_of1.date().isoformat(), "hasta": exit1.date().isoformat(), "candidatas": "AAA", "retorno": .10},
        {"fecha": exit1.date().isoformat(), "hasta": exit2.date().isoformat(), "candidatas": "BBB", "retorno": .10},
    ])
    curve = bt.daily_capital_curve(periods)
    assert curve.iloc[-1] == pytest.approx(1.10 * 1.10, rel=1e-6)  # se encadena, no se reinicia


def test_daily_benchmark_curve_uses_return_column_and_matches_strategy_dates(tmp_path, monkeypatch):
    """daily_benchmark_curve debe dar la misma longitud/fechas que
    daily_capital_curve para el mismo rango, usando el retorno del benchmark
    (columna `spy`) en vez del de la estrategia -- para que el max_drawdown de
    los dos se pueda comparar con la misma metodologia (el problema que
    senalo la revision: comparar drawdown diario de la estrategia contra
    drawdown por snapshots del indice no es una comparacion justa)."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    calendar = bt.xcals.get_calendar("XNYS")
    as_of = pd.Timestamp("2024-01-05")
    entry = calendar.next_session(calendar.date_to_session(as_of, direction="previous"))
    exit_session = calendar.date_to_session(as_of + pd.DateOffset(months=3), direction="next")
    sessions = calendar.sessions_in_range(entry, exit_session)

    prices = [100.0] * len(sessions)
    prices[-1] = 90.0
    df = pd.DataFrame({"Open": prices, "High": prices, "Low": prices, "Close": prices,
                       "Adj Close": prices, "Volume": [1] * len(prices)}, index=sessions)
    storage.upsert_prices("SPY", df)

    periods = pd.DataFrame([{
        "fecha": as_of.date().isoformat(), "hasta": exit_session.date().isoformat(),
        "candidatas": "AAPL", "retorno": 0.05, "spy": -0.10,
    }])
    curve = bt.daily_benchmark_curve(periods)
    assert len(curve) == len(sessions)
    assert curve.iloc[-1] == pytest.approx(0.90, abs=1e-6)  # coincide con periods["spy"], no con "retorno"


def test_sharpe_standard_error_matches_manual_formula():
    se = bt.sharpe_standard_error(0.74, 9.4)
    assert se == pytest.approx(np.sqrt((1 + 0.74 ** 2 / 2) / 9.4), rel=1e-9)


def test_sharpe_standard_error_shrinks_with_more_years():
    assert bt.sharpe_standard_error(0.7, 20) < bt.sharpe_standard_error(0.7, 5)


def test_sharpe_standard_error_rejects_non_positive_years():
    with pytest.raises(ValueError):
        bt.sharpe_standard_error(0.7, 0)
