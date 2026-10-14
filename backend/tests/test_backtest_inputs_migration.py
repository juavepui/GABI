"""Exact parity of the V1/V2 backtests after moving them to explicit inputs (#132).

The previous ``multifactor_backtest``/``portfolio_backtest`` are captured in a fixture and
run next to the new facades on one synthetic market that reaches every branch: holding
band, score hurdle, sampling, free holding cost, recycled ticker, missing price, accredited
exit, inexact composition and an unfinished period. The use cases are also run with an
explicit ``BacktestMarket`` that touches no old module.
"""

import json
from datetime import date
from pathlib import Path
from types import ModuleType

import exchange_calendars as xcals
import numpy as np
import pandas as pd
import pytest

from gabi import config, data_quality, historical_pit, identity, screener_asof, universe
from gabi import multifactor_backtest as v1
from gabi import portfolio_backtest as v2
from gabi.application.research import backtest_v1, backtest_v2
from gabi.application.research.backtest_market import BacktestMarket

REFERENCE = json.loads((Path(__file__).parent / "fixtures/backtest_inputs_migration.json").read_text(encoding="utf-8"))
CALENDAR = xcals.get_calendar("XNYS")
SESSIONS = CALENDAR.sessions_in_range("2020-12-01", "2023-03-31")
SYMBOLS = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "EXT", "REC", "MIS"]
EXIT_DAY = pd.Timestamp("2021-08-16")


def captured(name: str, **overrides) -> ModuleType:
    module = ModuleType(f"captured_{name}")
    module.__package__ = "gabi"
    exec(compile(REFERENCE[name], f"captured_{name}", "exec"), module.__dict__)
    module.__dict__.update(overrides)
    return module


def _history(symbol: str) -> pd.DataFrame:
    rng = np.random.default_rng(sum(map(ord, symbol)))
    prices = 100 * np.cumprod(1 + rng.normal(.0004, .015, len(SESSIONS)))
    frame = pd.DataFrame({"adj_close": prices, "close": prices}, index=SESSIONS)
    if symbol == "EXT":
        frame = frame[frame.index <= EXIT_DAY]
        frame.attrs["entity_id"] = "cik:EXT"
    if symbol == "MIS":
        frame = frame.drop(pd.Timestamp("2021-10-05"))  # entry of the 2021-10-04 rebalance
    return frame


HISTORIES = {symbol: _history(symbol) for symbol in [*SYMBOLS, "SPY"]}


def prices(symbols, as_of, owners=None):
    result = {}
    for symbol in symbols:
        frame = HISTORIES[symbol].copy()
        frame.attrs = dict(HISTORIES[symbol].attrs)
        result[symbol] = frame
    return result


def last_filings(symbols, as_of):
    day = pd.Timestamp(as_of)
    stale = pd.Timestamp("2021-09-01") <= day <= pd.Timestamp("2021-10-10")  # one period only
    return {s: ("2019-01-02" if s == "REC" and stale else (day - pd.Timedelta(days=40)).date().isoformat())
            for s in symbols if s != "GGG"}


def exit_value(frame, entity, entry, exit_session):
    return {"value": float(frame["adj_close"].iloc[-1]) * .8, "date": frame.index[-1], "status": "delisted",
            "strict": entity == "cik:EXT"}


def membership(as_of):
    if as_of == "2022-04-04":
        return {"symbols": [], "is_exact": False, "note": "sin composición exacta"}
    members = [s for s in SYMBOLS if (s != "EXT" or as_of <= "2021-07-04") and (s != "MIS" or as_of == "2021-10-04")]
    return {"symbols": members, "is_exact": True, "note": ""}


def ranking(as_of, symbols):
    rng = np.random.default_rng(int(as_of.replace("-", "")))
    scores = pd.Series(rng.uniform(0, 100, len(symbols)), index=symbols).round(1)
    table = pd.DataFrame({"composite_score": scores, "score_coverage": 1.0})
    table.loc[table.index == "FFF", "score_coverage"] = .5
    return table.sort_values("composite_score", ascending=False)


def quality(table):
    return {"filas": len(table), "cobertura": float(table["score_coverage"].mean())}


@pytest.fixture
def market(monkeypatch):
    monkeypatch.setattr(universe, "get_sp500_constituents_asof", membership)
    monkeypatch.setattr(screener_asof, "build_ranking_as_of", lambda as_of, symbols: {"table": ranking(as_of, symbols)})
    monkeypatch.setattr(data_quality, "ranking_quality", quality)
    monkeypatch.setattr(identity, "backtest_prices", prices)
    monkeypatch.setattr(identity, "last_filings", lambda symbols, as_of: last_filings(symbols, as_of))
    monkeypatch.setattr(identity, "resolve", lambda symbol, as_of: {"entity_id": f"cik:{symbol}"})
    monkeypatch.setattr(historical_pit, "exit_value", exit_value)
    return BacktestMarket(membership=membership, ranking=ranking, quality=quality, prices=prices,
                          last_filings=last_filings, owner=lambda symbol, as_of: f"cik:{symbol}",
                          exit_value=exit_value, calendar=CALENDAR, today=date.today,
                          risk_free_rate=config.RISK_FREE_RATE)


def same(old, new, path="result"):
    if isinstance(old, pd.DataFrame):
        pd.testing.assert_frame_equal(old, new, check_exact=True, obj=path)
    elif isinstance(old, pd.Series):
        pd.testing.assert_series_equal(old, new, check_exact=True, obj=path)
    elif isinstance(old, dict):
        assert list(old) == list(new), path
        for key in old:
            same(old[key], new[key], f"{path}.{key}")
    elif isinstance(old, list):
        assert len(old) == len(new), path
        for n, (a, b) in enumerate(zip(old, new, strict=True)):
            same(a, b, f"{path}[{n}]")
    elif isinstance(old, float) and np.isnan(old):
        assert isinstance(new, float) and np.isnan(new), path
    else:
        assert old == new and type(old) is type(new), path


V1_RUNS = [{"top_n": 5}, {"top_n": 3, "buffer_multiplier": 1.5}, {"top_n": 4, "rotation_hurdle_points": 20.0},
           {"top_n": 3, "max_symbols": 6, "cost_bps": 25}, {"months": 6, "top_n": 2, "min_universe_coverage": .8}]


@pytest.mark.parametrize("options", V1_RUNS)
def test_v1_matches_captured_engine(market, options):
    old = captured("multifactor_backtest")
    args = ("2021-01-04", "2023-01-04")
    before, after = old.run(*args, **options), v1.run(*args, **options)
    same(before, after)
    same(old.daily_capital_curve(before["periods"]), v1.daily_capital_curve(after["periods"]))
    same(old.daily_benchmark_curve(before["periods"]), v1.daily_benchmark_curve(after["periods"]))
    same(old.daily_risk_metrics(old.daily_capital_curve(before["periods"])),
         v1.daily_risk_metrics(v1.daily_capital_curve(after["periods"])))
    explicit = backtest_v1.run(market, lambda *a, **k: backtest_v1.period_returns(market, *a, **k), *args, **options)
    same(before, explicit)
    assert len(before["periods"]) >= 2


def test_v1_branches_are_reached(market):
    result = v1.run("2021-01-04", "2023-01-04", top_n=9, min_coverage=.4)
    reasons = " | ".join(item["motivo"] for item in result["skipped"])
    assert "reciclado" in reasons and "Faltan precios" in reasons and "sin composición exacta" in reasons
    period = v1._period_returns(["EXT", "AAA"], pd.Timestamp("2021-07-01"), 3, 10)
    assert period["exit_events"] == [{"symbol": "EXT", "estado": "delisted", "estricto": True}]
    same(captured("multifactor_backtest")._period_returns(["EXT", "AAA"], pd.Timestamp("2021-07-01"), 3, 10,
                                                          held_symbols={"AAA"}),
         v1._period_returns(["EXT", "AAA"], pd.Timestamp("2021-07-01"), 3, 10, held_symbols={"AAA"}))
    with pytest.raises(ValueError, match="aún no tiene salida"):
        v1._period_returns(["AAA"], pd.Timestamp(date.today()), 3, 10)


def test_required_symbols_matches_captured_engine(market):
    old = captured("multifactor_backtest")
    assert v1.required_symbols("2021-01-04", "2022-01-04", 3, 6) == old.required_symbols("2021-01-04", "2022-01-04", 3, 6)


V2_RUNS = [{"top_n": 4}, {"top_n": 3, "mode": "fast_dev", "max_symbols": 6},
           {"top_n": 4, "rotation_hurdle_points": 15.0, "commission_usd": 0.0, "spread_bps": 25.0},
           {"months": 6, "top_n": 3, "initial_capital": 50_000.0}]


@pytest.mark.parametrize("options", V2_RUNS)
def test_v2_matches_captured_engine(market, options):
    old_v1 = captured("multifactor_backtest")
    old = captured("portfolio_backtest", v1=old_v1)
    args = ("2021-01-04", "2023-01-04")
    before, after = old.run(*args, **options), v2.run(*args, **options)
    same(before, after)
    explicit = backtest_v2.run(market, lambda *a, **k: v2._rebalance(*a, **k),
                               lambda *a, **k: backtest_v2.daily_segment(market, *a, **k), *args, **options)
    same(before, explicit)
    assert len(before["periods"]) >= 2


def test_v2_accredited_exit_and_benchmark_match(market):
    old = captured("portfolio_backtest", v1=captured("multifactor_backtest"))
    shares, owners = {"EXT": 10.0, "AAA": 5.0}, {"EXT": "cik:EXT", "AAA": "cik:AAA"}
    entry, exit_session = pd.Timestamp("2021-07-02"), pd.Timestamp("2021-10-01")
    sessions = CALENDAR.sessions_in_range(entry, exit_session)
    same(old._daily_segment(100.0, dict(shares), entry, exit_session, sessions, owners=dict(owners)),
         v2._daily_segment(100.0, dict(shares), entry, exit_session, sessions, owners=dict(owners)))
    histories = prices(list(shares), "2021-07-02")
    same(old._historical_exits(histories, shares, owners, entry, exit_session),
         v2._historical_exits(histories, shares, owners, entry, exit_session))
    same(old.buy_and_hold_curve("SPY", "2021-01-05", "2022-12-30"), v2.buy_and_hold_curve("SPY", "2021-01-05", "2022-12-30"))
    result = v2.run("2021-04-01", "2022-01-03", top_n=9, min_coverage=.4)
    assert result["exit_events"] == [{"symbol": "EXT", "fecha": "2021-08-16", "estado": "delisted", "estricto": True}]
    old_result = old.run("2021-04-01", "2022-01-03", top_n=9, min_coverage=.4)
    same(old_result, result)


def test_pure_rules_keep_their_historical_names():
    assert v1._sample_symbols is v1.rules.sample_symbols and v1._MAX_DAYS_WITHOUT_FILING == 450
    assert v2._rebalance_to_weights is v2.rules.rebalance_to_weights and v2.VALID_MODES == ("validation", "fast_dev")
    curve = pd.Series([1.0, 1.01, .99, 1.03], index=SESSIONS[:4])
    same(captured("multifactor_backtest").daily_risk_metrics(curve), v1.daily_risk_metrics(curve))
    returns = pd.Series([.02, -.01, .03])
    same(captured("multifactor_backtest")._risk_metrics(returns, 4, years=.75), v1._risk_metrics(returns, 4, years=.75))
