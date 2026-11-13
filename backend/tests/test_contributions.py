"""Contributions in EUR, benchmark with identical flows and flow-adjusted performance (#244); no data files."""

from datetime import date

import pandas as pd
import pytest

from gabi.domain.portfolio import contributions as c

TODAY = date(2026, 10, 31)
PROFILE = c.Profile(initial_eur=11_000, monthly_eur=700, horizon_months=24, loss_tolerance=0.20)


def series(values, start="2025-01-02"):
    return pd.Series(values, index=pd.bdate_range(start, periods=len(values)), dtype=float)


def test_profile_validation_and_capital_need():
    profile = c.validate_profile({"initial_eur": "11000", "monthly_eur": 700, "horizon_months": 24,
                                  "loss_tolerance": 0.2, "capital_needed_by": "2027-06-30",
                                  "tax_residence": "es"}, TODAY)
    assert (profile.version, profile.tax_residence) == (c.PROFILE_VERSION, "ES")
    assert c.capital_need_before_horizon(profile, TODAY) is True
    assert c.capital_need_before_horizon(PROFILE, TODAY) is None
    for bad in ({"initial_eur": -1, "horizon_months": 12, "loss_tolerance": 0.2},
                {"initial_eur": 1000, "horizon_months": 12, "loss_tolerance": 1.2},
                {"initial_eur": 1000, "horizon_months": 12, "loss_tolerance": 0.2, "capital_needed_by": "2026-01-01"}):
        with pytest.raises(ValueError):
            c.validate_profile(bad, TODAY)


def test_schedule_keeps_the_day_of_month_and_clamps_short_months():
    flows = c.schedule(PROFILE, date(2025, 1, 31), date(2025, 4, 30))
    assert flows == [(date(2025, 1, 31), 11_000), (date(2025, 2, 28), 700), (date(2025, 3, 31), 700),
                     (date(2025, 4, 30), 700)]


def test_eur_vehicle_without_costs_reconciles_wealth_and_twr():
    prices = series([100, 110, 99, 121])
    flows = [(date(2025, 1, 2), 1000.0), (date(2025, 1, 4), 500.0)]  # Saturday: executes on Monday.
    result = c.simulate(flows, prices, c.Vehicle("IDX", currency="EUR"))
    daily = result["daily"]
    assert daily["flow_eur"].tolist() == [1000, 0, 500, 0]
    assert daily["value_eur"].iloc[-1] == pytest.approx((10 + 500 / 99) * 121)
    performance = c.performance(result, PROFILE)
    assert performance["twr"] == pytest.approx(121 / 100 - 1)
    assert performance["contributed_eur"] == 1500
    assert performance["final_value_eur"] - performance["contributed_eur"] == pytest.approx(
        (10 + 500 / 99) * 121 - 1500)


def test_new_money_does_not_hide_the_drawdown():
    prices = series([100, 70, 70, 80])
    flows = [(date(2025, 1, 2), 1000.0), (date(2025, 1, 3), 100_000.0)]
    performance = c.performance(c.simulate(flows, prices, c.Vehicle("IDX", currency="EUR")), PROFILE)
    assert performance["max_drawdown"] == pytest.approx(-0.30)
    assert performance["review_threshold_reached_on"] == date(2025, 1, 3)
    assert performance["max_euros_lost"] == pytest.approx(-300)
    # Over contributions the loss looks tiny: that is why skill uses the unitised drawdown.
    assert performance["max_loss_on_contributions"] == pytest.approx(-300 / 101_000)


def test_drawdown_recovery_clears_the_current_drawdown():
    performance = c.performance(c.simulate([(date(2025, 1, 2), 1000.0)], series([100, 85, 95, 105]),
                                           c.Vehicle("IDX", currency="EUR")), PROFILE)
    assert performance["max_drawdown"] == pytest.approx(-0.15)
    assert performance["current_drawdown"] == 0
    assert performance["review_threshold_reached_on"] is None


def test_usd_vehicle_converts_euros_with_the_same_dated_rate_and_costs():
    prices = series([100.0, 100.0])
    fx = series([1.10, 1.00])  # USD per EUR; the dollar strengthens.
    vehicle = c.Vehicle("SPY", currency="USD", commission_fixed_eur=1.0, fx_cost_pct=0.006)
    result = c.simulate([(date(2025, 1, 2), 1001.0)], prices, vehicle, fx)
    units = 1000 * (1 - 0.006) * 1.10 / 100
    assert result["daily"]["units"].iloc[0] == pytest.approx(units)
    assert result["costs_eur"] == pytest.approx(1 + 6)
    assert result["daily"]["value_eur"].iloc[-1] == pytest.approx(units * 100 / 1.00)


def test_whole_shares_and_minimum_order_keep_cash_without_losing_it():
    vehicle = c.Vehicle("SPY", currency="EUR", fractional=False, min_order_eur=300)
    flows = [(date(2025, 1, 2), 250.0), (date(2025, 1, 3), 250.0)]
    daily = c.simulate(flows, series([120.0, 120.0, 120.0]), vehicle)["daily"]
    assert daily["units"].tolist() == [0, 4, 4]
    assert daily["value_eur"].tolist() == pytest.approx([250, 500, 500])


def test_theoretical_index_cost_applies_once_and_etf_has_none():
    prices = pd.Series([100.0, 100.0], index=pd.to_datetime(["2025-01-02", "2026-01-02"]))
    flows = [(date(2025, 1, 2), 1000.0)]
    index = c.simulate(flows, prices, c.Vehicle("SP500TR", currency="EUR", annual_cost_pct=0.0007,
                                                 theoretical=True))
    etf = c.simulate(flows, prices, c.Vehicle("CSPX", currency="EUR"))
    assert index["daily"]["value_eur"].iloc[-1] == pytest.approx(1000 * (1 - 0.0007) ** (365 / 365))
    assert etf["daily"]["value_eur"].iloc[-1] == 1000


def test_missing_prices_leave_contributions_pending_and_reported():
    prices = series([100.0, None, 100.0])
    result = c.simulate([(date(2025, 1, 3), 500.0), (date(2025, 2, 1), 700.0)], prices,
                        c.Vehicle("IDX", currency="EUR"))
    assert result["daily"].index[1] == pd.Timestamp("2025-01-06")
    assert result["pending"] == [(date(2025, 2, 1), 700.0)]
    with pytest.raises(ValueError, match="cambio"):
        c.simulate([(date(2025, 1, 2), 1.0)], prices, c.Vehicle("SPY"))


def test_xirr_matches_a_known_annual_rate():
    assert c.xirr([(date(2024, 1, 1), 1000.0)], date(2025, 1, 1), 1100.0) == pytest.approx(0.10, abs=1e-3)
    assert c.xirr([], date(2025, 1, 1), 1.0) is None


def test_compare_requires_identical_contributions():
    flows = [(date(2025, 1, 2), 1000.0)]
    eur = c.Vehicle("IDX", currency="EUR")
    a = c.performance(c.simulate(flows, series([100, 120]), eur), PROFILE)
    b = c.performance(c.simulate(flows, series([100, 110]), eur), PROFILE)
    assert c.compare(a, b)["wealth_difference_eur"] == pytest.approx(100)
    other = c.performance(c.simulate([(date(2025, 1, 2), 2000.0)], series([100, 110]), eur), PROFILE)
    with pytest.raises(ValueError):
        c.compare(a, other)


def _lot(symbol="AAA", shares=10.0, price=100.0, day="2025-01-02", currency="USD", commission=1.0, fx_rate=None):
    return {"id": 1, "symbol": symbol, "shares": shares, "price": price, "purchase_date": day,
            "currency": currency, "commission": commission, "fx_rate": fx_rate}


def test_lots_history_follows_the_adjusted_close_and_the_rate_of_each_session():
    sessions = pd.bdate_range("2025-01-02", periods=3)
    adjusted = {"AAA": pd.Series([100.0, 110.0, 121.0], index=sessions)}  # Includes reinvested dividends.
    rates = {"USD": pd.Series([0.90, 0.90, 0.80], index=sessions)}  # Euros per dollar.
    result = c.lots_history([_lot(fx_rate=0.92)], adjusted, rates, sessions)
    daily = result["daily"]
    assert daily["flow_eur"].tolist() == pytest.approx([1001 * 0.92, 0, 0])
    assert daily["value_eur"].tolist() == pytest.approx([900, 990, 968])
    assert result["costs_eur"] == pytest.approx(0.92)
    assert result["flows"] == [(date(2025, 1, 2), pytest.approx(1001 * 0.92))]


def test_lots_without_purchase_price_or_rate_are_excluded_and_reported():
    sessions = pd.bdate_range("2025-01-02", periods=3)
    adjusted = {"AAA": pd.Series([100.0, 100.0, 100.0], index=sessions), "SAN": pd.Series(dtype=float)}
    result = c.lots_history([_lot(), _lot(symbol="SAN", currency="EUR", day="2025-01-03")], adjusted, {},
                            sessions)
    assert [(row["symbol"], row["reason"]) for row in result["excluded"]] == [("AAA", "missing_fx"),
                                                                             ("SAN", "missing_price")]
    assert result["flows"] == [] and result["daily"].empty


def test_an_incomplete_session_is_dropped_and_its_flow_enters_on_the_next_one():
    sessions = pd.bdate_range("2025-01-02", periods=3)
    lots = [_lot(currency="EUR", commission=0), _lot(symbol="BBB", price=50, currency="EUR", commission=0)]
    # BBB has its purchase price from the day before, but no close in the first two sessions.
    adjusted = {"AAA": pd.Series([100.0, 100.0, 100.0], index=sessions),
                "BBB": pd.Series([50.0, 50.0], index=pd.to_datetime(["2025-01-01", "2025-01-06"]))}
    result = c.lots_history(lots, adjusted, {}, sessions)
    daily = result["daily"]
    assert result["incomplete_sessions"] == 2
    assert daily.index.tolist() == [pd.Timestamp("2025-01-06")]
    assert daily["flow_eur"].tolist() == [1500] and daily["value_eur"].tolist() == [1500]
    assert c.performance(result, PROFILE)["twr"] == pytest.approx(0.0)


def test_scenarios_convert_market_and_euro_shocks_and_flag_the_tolerance():
    rows = {row["id"]: row for row in c.scenarios(10_000, 1.0, 0.20)}
    assert rows["market_-10"]["change_eur"] == pytest.approx(-1_000)
    assert rows["euro_+10"]["change"] == pytest.approx(1 / 1.1 - 1)
    assert rows["market_-20_euro_+10"]["change"] == pytest.approx(0.8 / 1.1 - 1)
    assert rows["market_-20_euro_+10"]["exceeds_tolerance"] and not rows["market_-10"]["exceeds_tolerance"]
    euro_only = {row["id"]: row for row in c.scenarios(10_000, 0.0, 0.20)}
    assert euro_only["euro_+10"]["change"] == 0 and euro_only["market_-20"]["change"] == pytest.approx(-0.2)
    with pytest.raises(ValueError):
        c.scenarios(1.0, 1.5, 0.2)


def test_combine_adds_two_results_and_keeps_the_last_value_of_a_missing_session():
    eur = c.Vehicle("IDX", currency="EUR")
    a = c.simulate([(date(2025, 1, 2), 1000.0)], series([100, 110, 121]), eur)
    b = c.simulate([(date(2025, 1, 3), 500.0)], series([50, 50, 50]), eur)
    b["daily"] = b["daily"].drop(pd.Timestamp("2025-01-06"))
    combined = c.combine(a, b)
    daily = combined["daily"]
    assert daily["contributed_eur"].tolist() == [1000, 1500, 1500]
    assert daily["flow_eur"].tolist() == [1000, 500, 0]
    assert daily["value_eur"].iloc[-1] == pytest.approx(1210 + 500)
