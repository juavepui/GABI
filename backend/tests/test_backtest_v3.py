"""Self-financing backtest V3 (#249) over independent synthetic fixtures; no data files or reservations."""

from datetime import date, timedelta

import pytest

from gabi.domain.portfolio import backtest as v2
from gabi.domain.portfolio import backtest_v3 as v3

DAYS = [date(2025, 1, 6) + timedelta(days=i) for i in range(5)]  # Monday to Friday.
FREE = v3.Costs(cost_reserve=0.0, participation=1.0)


def flat(price=100.0, volume=1e9, days=DAYS, changes=None):
    changes = changes or {}
    return {day: changes.get(day, v3.Bar(price, price, volume)) for day in days}


def test_a_signal_executes_at_the_next_open_and_cash_plus_positions_is_nav():
    bars = {"A": flat(100.0, changes={DAYS[1]: v3.Bar(110.0, 120.0, 1e9)})}
    result = v3.run(DAYS, bars, rebalances=[v3.Rebalance(DAYS[0], {"A": 1.0})], costs=FREE, initial_cash=1100.0)
    trade = result["trades"][0]
    assert (trade["day"], trade["price"], trade["shares"]) == (DAYS[1].isoformat(), 110.0, 10.0)
    assert result["daily"][1]["nav"] == pytest.approx(1200.0)
    assert result["identity_error"] < 1e-9


def test_costs_are_reserved_and_cash_never_goes_negative_unlike_v2():
    costs = v3.Costs(commission_fixed=5.0, spread_bps=20.0, slippage_bps=10.0, cost_reserve=0.0, participation=1.0)
    bars = {symbol: flat(10.0) for symbol in "ABCD"}
    weights = {symbol: 0.25 for symbol in "ABCD"}
    result = v3.run(DAYS, bars, rebalances=[v3.Rebalance(DAYS[0], weights)], costs=costs, initial_cash=1000.0)
    assert result["min_cash"] >= 0
    # V2 targets the whole value and charges the commission on top: a full rebalance overdraws.
    shares: dict = {}
    legacy = v2.rebalance_to_weights(1000.0, shares, weights, dict.fromkeys("ABCD", 10.0), 5.0, 20.0)
    assert legacy["cash"] < 0


def test_costs_are_reconciled_with_the_net_asset_value():
    costs = v3.Costs(commission_fixed=1.0, commission_pct=0.001, spread_bps=10.0, slippage_bps=5.0,
                     cost_reserve=0.01, participation=1.0)
    bars = {"A": flat(50.0), "B": flat(20.0)}
    rebalances = [v3.Rebalance(DAYS[0], {"A": 1.0}), v3.Rebalance(DAYS[2], {"B": 1.0})]
    result = v3.run(DAYS, bars, rebalances=rebalances, costs=costs, initial_cash=10_000.0)
    # Prices never move, so all the value lost is commissions plus spread and slippage.
    lost = 10_000.0 - result["daily"][-1]["nav"]
    assert lost == pytest.approx(result["commissions"] + result["execution_costs"])
    assert [trade["side"] for trade in result["trades"]] == ["BUY", "SELL", "BUY"]


def test_participation_caps_an_order_and_the_minimum_skips_small_ones():
    bars = {"A": flat(10.0, volume=100.0)}  # 1,000 $ a day: 10 % allows 100 $.
    capped = v3.run(DAYS, bars, rebalances=[v3.Rebalance(DAYS[0], {"A": 1.0})],
                    costs=v3.Costs(cost_reserve=0.0, participation=0.1), initial_cash=1000.0)
    assert capped["trades"][0]["notional"] == pytest.approx(100.0) and capped["trades"][0]["partial"]
    skipped = v3.run(DAYS, {"A": flat(10.0)}, rebalances=[v3.Rebalance(DAYS[0], {"A": 1.0})],
                     costs=v3.Costs(cost_reserve=0.0, min_order=5000.0), initial_cash=1000.0)
    assert skipped["trades"] == [] and skipped["daily"][-1]["cash"] == 1000.0


def test_split_and_dividend_change_shares_and_cash_without_double_counting():
    bars = {"A": flat(100.0, changes={day: v3.Bar(50.0, 50.0, 1e9) for day in DAYS[3:]})}
    events = [v3.Event("split", "A", DAYS[3], ratio=2.0), v3.Event("dividend", "A", DAYS[4], cash=1.0)]
    result = v3.run(DAYS, bars, rebalances=[v3.Rebalance(DAYS[0], {"A": 1.0})],
                    costs=v3.Costs(cost_reserve=0.0, participation=1.0, dividend_withholding=0.15),
                    initial_cash=1000.0, events=events)
    assert result["final_shares"]["A"] == pytest.approx(20.0)
    assert result["daily"][3]["nav"] == pytest.approx(1000.0)  # The split alone changes nothing.
    assert result["dividends"] == pytest.approx(20 * 1.0 * 0.85)
    assert result["daily"][4]["nav"] == pytest.approx(1000.0 + 17.0)


def test_mergers_and_bankruptcy_settle_positions():
    bars = {"A": flat(10.0, days=DAYS[:3]), "B": flat(20.0), "C": flat(5.0, days=DAYS[:3]), "D": flat(40.0)}
    events = [v3.Event("cash_merger", "A", DAYS[3], cash=12.0),
              v3.Event("bankruptcy", "C", DAYS[3]),
              v3.Event("stock_merger", "B", DAYS[4], ratio=0.5, target="D")]
    result = v3.run(DAYS, bars, rebalances=[v3.Rebalance(DAYS[0], {"A": 1 / 3, "B": 1 / 3, "C": 1 / 3})],
                    costs=FREE, initial_cash=3000.0, events=events)
    assert set(result["final_shares"]) == {"D"} and result["final_shares"]["D"] == pytest.approx(25.0)
    # A paid 12 per share (100 × 12) and C went to zero: 1,200 cash plus 25 D at 40.
    assert result["daily"][-1]["nav"] == pytest.approx(1200.0 + 25 * 40.0)
    assert [event["kind"] for event in result["events"]] == ["cash_merger", "bankruptcy", "stock_merger"]


def test_suspended_or_absent_prices_block_trading_and_are_reported_never_filled_backwards():
    bars = {"A": flat(10.0, changes={DAYS[2]: v3.Bar(10.0, 10.0, 0.0, suspended=True)}),
            "LATE": {day: v3.Bar(30.0, 30.0, 1e9) for day in DAYS[3:]}}  # No bar before Thursday.
    rebalances = [v3.Rebalance(DAYS[0], {"A": 1.0}), v3.Rebalance(DAYS[1], {"LATE": 1.0})]
    result = v3.run(DAYS, bars, rebalances=rebalances, costs=FREE, initial_cash=1000.0)
    assert {(row["symbol"], row["reason"]) for row in result["blocked"]} == {("A", "suspended"),
                                                                           ("LATE", "absent")}
    assert result["stale"][0]["positions"] == [{"symbol": "A", "reason": "suspended"}]
    assert result["final_shares"] == {"A": pytest.approx(100.0)}  # Nothing bought from a later price.


def test_a_position_without_any_known_price_fails_instead_of_inventing_one():
    bars = {"A": flat(10.0, days=DAYS[:2]), "B": {}}
    events = [v3.Event("stock_merger", "A", DAYS[2], ratio=1.0, target="B")]
    with pytest.raises(ValueError, match="no se inventa"):
        v3.run(DAYS, bars, rebalances=[v3.Rebalance(DAYS[0], {"A": 1.0})], costs=FREE, initial_cash=100.0,
               events=events)


def test_benchmark_uses_the_same_calendar_flows_and_accounting():
    bars = {"SPY": flat(100.0, changes={day: v3.Bar(110.0, 110.0, 1e9) for day in DAYS[3:]})}
    flows = {DAYS[2]: 500.0}
    result = v3.benchmark("SPY", DAYS, bars, costs=FREE, initial_cash=1000.0, flows=flows)
    buys = [trade for trade in result["trades"] if trade["side"] == "BUY"]
    assert [trade["day"] for trade in buys] == [DAYS[1].isoformat(), DAYS[3].isoformat()]
    assert result["daily"][-1]["nav"] == pytest.approx(10 * 110 + 500 / 110 * 110)


def test_benchmark_reinvests_its_dividends_like_a_total_return_index():
    bars = {"SPY": flat(100.0)}
    events = [v3.Event("dividend", "SPY", DAYS[2], cash=2.0)]
    result = v3.benchmark("SPY", DAYS, bars, costs=FREE, initial_cash=1000.0, events=events)
    buys = [trade["day"] for trade in result["trades"] if trade["side"] == "BUY"]
    assert buys == [DAYS[1].isoformat(), DAYS[3].isoformat()]
    assert result["daily"][-1]["cash"] == pytest.approx(0.0) and result["final_shares"]["SPY"] == pytest.approx(10.2)


def test_leverage_is_off_by_default_and_only_explicit():
    assert v3.Costs().leverage is False and v3.BASE.leverage is False and v3.STRESS.leverage is False
    with pytest.raises(ValueError):
        v3.Event("spin_off", "A", DAYS[0])
