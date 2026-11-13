"""V2/V3 comparison over the same signals (#249), with a synthetic market only."""

from datetime import date

import exchange_calendars as xcals
import pandas as pd
import pytest

from gabi.application.research import backtest_v3_comparison as comparison
from gabi.application.research.backtest_market import BacktestMarket

CALENDAR = xcals.get_calendar("XNYS")
SESSIONS = CALENDAR.sessions_in_range(pd.Timestamp("2024-01-02"), pd.Timestamp("2024-07-31"))


def flat(price: float, until: str | None = None) -> pd.DataFrame:
    index = SESSIONS if until is None else SESSIONS[SESSIONS <= pd.Timestamp(until)]
    return pd.DataFrame({"open": price, "close": price, "volume": 1e6, "adj_close": price}, index=index)


def market(frames: dict[str, pd.DataFrame], exits: list) -> BacktestMarket:
    def prices(symbols, as_of, owners=None):
        return {symbol: frames.get(symbol, pd.DataFrame()).loc[lambda f, a=as_of: f.index >= pd.Timestamp(a)]
                for symbol in symbols}

    def exit_value(frame, owner, entry, exit_session):
        exits.append(owner)
        return {"event": {"event_type": "cash_acquisition", "status": "terminal_return_confirmed",
                          "cash_per_share": 30.0}}

    return BacktestMarket(membership=None, ranking=None, quality=None, prices=prices, last_filings=None,
                          owner=None, exit_value=exit_value, calendar=CALENDAR, today=lambda: date(2026, 1, 1),
                          risk_free_rate=0.0)


def v2_result() -> dict:
    periods = pd.DataFrame([
        {"fecha": "2024-01-02", "hasta": "2024-04-01", "held": "", "bought": "AAA, BBB"},
        {"fecha": "2024-04-01", "hasta": "2024-07-01", "held": "AAA", "bought": "CCC"},
    ])
    curve = pd.Series(100_000.0, index=SESSIONS[(SESSIONS >= "2024-01-03") & (SESSIONS <= "2024-07-01")])
    return {"periods": periods, "initial_capital": 100_000.0, "nav_curve": curve, "nav_curve_spy": curve,
            "comision_total": 4.0, "spread_total": 10.0, "strict_result": True, "skipped": []}


def test_plan_keeps_v2_targets_and_windows():
    rows = comparison.plan(market({}, []), v2_result()["periods"], top_n=2)
    assert [row["weights"] for row in rows] == [{"AAA": .5, "BBB": .5}, {"AAA": .5, "CCC": .5}]
    assert [(row["signal"], row["end"]) for row in rows] == [(date(2024, 1, 2), date(2024, 4, 1)),
                                                             (date(2024, 4, 1), date(2024, 7, 1))]
    assert rows[1]["symbols"] == ["AAA", "BBB", "CCC"]


def test_v3_executes_the_same_targets_and_settles_an_exit():
    exits: list = []
    bbb = flat(50.0, until="2024-02-29")
    bbb.attrs.update(entity_id="cik:2", source_id="finsaber:test")
    frames = {"AAA": flat(100.0), "BBB": bbb, "CCC": flat(20.0), "SPY": flat(400.0)}
    result = comparison.compare(market(frames, exits), v2_result(), top_n=2, splits=lambda symbols: {},
                                scenarios={"v2_equivalent": comparison.V2_EQUIVALENT})
    engine = result["v3"]["v2_equivalent"]
    assert result["rebalances"] == 2 and exits == ["cik:2"]
    assert result["data"]["exits"][0]["status"] == "terminal_return_confirmed" and result["data"]["strict"]
    # Constant prices: BBB's cash merger at 30 $ (from 50 $) is the only loss beyond costs.
    # Purchases are scaled so both 1 $ commissions fit in the cash.
    bbb_shares = 50_000 * 100_000 / 100_002 / (50.0 * (1 + 5 / 10000))
    lost_on_exit = bbb_shares * (50.0 - 30.0)
    final = engine["metrics"]["final"]
    assert final == pytest.approx(100_000 - lost_on_exit - engine["commissions"] - engine["execution_costs"])
    assert engine["min_cash"] >= 0 and engine["identity_error"] < 1e-6
    assert engine["benchmark"]["final"] < 100_000 and result["v2"]["excess_cagr"] == 0.0


def test_without_v2_rebalances_there_is_nothing_to_compare():
    with pytest.raises(ValueError, match="ningún rebalanceo"):
        comparison.compare(market({}, []), v2_result() | {"periods": pd.DataFrame()}, top_n=2,
                           splits=lambda symbols: {})


def test_policy_validation_runs_both_allocations_with_contributions():
    from gabi.application.research import policy_validation
    from gabi.domain.portfolio import risk_policy

    frames = {"AAA": flat(100.0), "BBB": flat(50.0), "CCC": flat(20.0), "SPY": flat(400.0)}
    fake = market(frames, [])
    fake = BacktestMarket(**{**fake.__dict__, "owner": lambda symbol, as_of: f"cik:{symbol}"})
    prepared = comparison.prepare(fake, v2_result(), top_n=2, splits=lambda symbols: {})
    policy = risk_policy.Policy(max_issuer_weight=0.5, max_sector_weight=0.3)
    result = policy_validation.validate(fake, prepared, policy=policy,
                                        sectors=lambda symbols, as_of: {s: "Tech" for s in symbols} | {"CCC": None})
    small = result["accounts"]["small"]
    # Each rebalance has a sector above 30 % ("Sin sector" counts as one): the rest stays in cash.
    assert result["rebalances_capped"] == 2 and result["unknown_sector_rows"] == 1
    assert small["limits"]["average_cash_share"] > small["equal_weight"]["average_cash_share"]
    assert small["costs"]["min_order"] == pytest.approx(100.0)
    assert small["equal_weight"]["metrics"]["contributed"] == pytest.approx(11_000 + 6 * 700)
    # Constant prices: the time-weighted return only loses costs.
    assert -0.01 < small["equal_weight"]["metrics"]["cagr"] <= 0
    assert all(run["min_cash"] >= 0 for account in result["accounts"].values()
               for name, run in account.items() if name in {"equal_weight", "limits"})
    assert policy_validation.monthly_flows([date(2024, 1, 2), date(2024, 1, 3), date(2024, 2, 1)], 700) == {
        date(2024, 2, 1): 700}
