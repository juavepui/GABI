"""NSI-v1 exploratory evaluation (#252) on a synthetic market: selection, euro account, V3 and the decision."""

import math
from datetime import date

import exchange_calendars as xcals
import numpy as np
import pandas as pd
import pytest

from gabi.application.errors import QueryError
from gabi.application.research import nsi_evaluation
from gabi.application.research.backtest_market import BacktestMarket

CALENDAR = xcals.get_calendar("XNYS")
SESSIONS = CALENDAR.sessions_in_range(pd.Timestamp("2022-06-01"), pd.Timestamp("2024-07-31"))
SIGNALS = [date(2022, 7, 1), date(2023, 7, 3), date(2024, 7, 1)]
SYMBOLS = [f"S{index}" for index in range(10)]


def frame(daily_growth: float) -> pd.DataFrame:
    prices = 50.0 * (1 + daily_growth) ** np.arange(len(SESSIONS))
    return pd.DataFrame({"open": prices, "close": prices, "volume": 1e7, "adj_close": prices}, index=SESSIONS)


def facts(growth: float) -> dict:
    """10-Ks filed every February with the year's basic shares and the comparative, growing at ``growth``."""
    entries = []
    for year in range(2021, 2024):
        for fiscal in (year, year - 1):
            entries.append({"val": 1e6 * (1 + growth) ** (fiscal - 2015), "start": f"{fiscal}-01-01",
                            "end": f"{fiscal}-12-31", "filed": f"{year + 1}-02-15", "accn": f"a{year}",
                            "form": "10-K", "fp": "FY"})
    return {"facts": {"us-gaap": {"WeightedAverageNumberOfSharesOutstandingBasic": {"units": {"shares": entries}}}}}


def market(frames: dict[str, pd.DataFrame]) -> BacktestMarket:
    def prices(symbols, as_of, owners=None):
        return {symbol: frames[symbol].loc[lambda f, a=as_of: f.index >= pd.Timestamp(a)] for symbol in symbols}

    return BacktestMarket(membership=None, ranking=None, quality=None, prices=prices, last_filings=None,
                          owner=None, exit_value=lambda *args: {}, calendar=CALENDAR, today=lambda: date(2026, 1, 1),
                          risk_free_rate=0.0)


def factors() -> pd.DataFrame:
    months = pd.period_range("2022-06", "2024-08", freq="M")
    table = pd.DataFrame(np.random.default_rng(3).normal(0, 0.03, (len(months), 6)),
                         columns=["Mkt-RF", "SMB", "HML", "RMW", "CMA", "Mom"])
    return table.assign(RF=0.001, date=months.to_timestamp())


def run(**overrides):
    # S0 and S1 issue least (they buy back) and their prices rise; the rest issue and stay flat.
    growth = {symbol: (-0.05 if symbol in {"S0", "S1"} else 0.02 + index / 100) for index, symbol in enumerate(SYMBOLS)}
    frames = {symbol: frame(0.001 if symbol in {"S0", "S1"} else 0.0) for symbol in SYMBOLS} | {"SPY": frame(0.0002)}
    members = {signal: {symbol: f"cik{symbol}" for symbol in SYMBOLS} for signal in SIGNALS}
    arguments = dict(market=market(frames), facts=lambda cik: facts(growth[cik[3:]]), sic=lambda cik: 3571,
                     sectors=lambda symbols, as_of: {symbol: "Tech" for symbol in symbols},
                     splits=lambda symbols: {}, euros_per_dollar=pd.Series(0.9, index=SESSIONS), factors=factors())
    return nsi_evaluation.evaluate(SIGNALS, members, **(arguments | overrides))


def test_the_evaluation_selects_buyers_back_and_measures_them_in_euros_against_spy():
    result = run()
    assert result["returns_read"] is True and result["independent_evidence"] is False
    assert [row["selected"] for row in result["selections"]] == [["S0", "S1"], ["S0", "S1"]]
    primary = result["configurations"]["primary"]
    assert primary["net_excess_cagr_eur"] == pytest.approx(
        primary["strategy"]["metrics_eur"]["cagr"] - primary["benchmark"]["metrics_eur"]["cagr"])
    assert primary["decision"]["applies"] is True
    assert result["configurations"]["stress"]["decision"]["applies"] is False
    contributed = primary["strategy"]["metrics_eur"]["contributed"]
    assert contributed == pytest.approx(primary["strategy"]["metrics_eur"]["initial"] + 700 * 24, rel=1e-6)
    assert primary["strategy"]["metrics_eur"]["initial"] == pytest.approx(11_000 * (1 - nsi_evaluation.FX_COST))
    # Two names of a Top-20: the other eighteen slots stay in cash; contributions are invested monthly.
    assert 0.85 < primary["strategy"]["average_cash_share"] < 0.95
    assert primary["benchmark"]["trades"] >= 24  # The index invests each contribution the next session.
    assert result["equal_weight_universe"]["metrics_eur"]["cagr"] is not None
    assert not math.isnan(primary["alpha_ff5_umd"]["alpha_annual"])


def test_amendment_one_invests_each_contribution_in_the_current_selection():
    row = {"signal": date(2022, 7, 1), "end": date(2023, 7, 3)}
    flows = {date(2022, 6, 1): 1.0, date(2022, 8, 1): 1.0, date(2023, 6, 1): 1.0, date(2023, 7, 3): 1.0}
    plan = nsi_evaluation.with_contributions(row, {"S0": 0.05}, flows)
    assert [rebalance.signal_day for rebalance in plan] == [date(2022, 7, 1), date(2022, 8, 1), date(2023, 6, 1)]
    assert all(rebalance.weights == {"S0": 0.05} for rebalance in plan)


def test_policy_weights_start_at_one_over_top_n_and_empty_slots_stay_in_cash():
    from gabi.domain.portfolio.risk_policy import Policy

    row = {"selected": ["A", "B", "C", "D"], "issuers": {"A": "1", "B": "2", "C": "3", "D": "4"}}
    target, capped = nsi_evaluation.weights(row, 20, {"A": "Tech", "B": "Tech", "C": "Tech", "D": "Energy"},
                                            Policy())
    assert target == {name: pytest.approx(0.05) for name in "ABCD"} and not capped
    crowded = {"selected": [f"T{i}" for i in range(20)], "issuers": {f"T{i}": str(i) for i in range(20)}}
    target, capped = nsi_evaluation.weights(crowded, 20, {f"T{i}": "Tech" for i in range(20)}, Policy())
    assert capped and sum(target.values()) == pytest.approx(0.30)  # Sector cap: the rest is cash.


def test_a_missing_exchange_rate_stops_the_evaluation_and_reserved_dates_are_refused():
    with pytest.raises(ValueError, match="USDEUR"):
        run(euros_per_dollar=pd.Series(0.9, index=SESSIONS[SESSIONS >= "2023-01-01"]))
    with pytest.raises(QueryError):
        nsi_evaluation.evaluate([date(2024, 7, 1), date(2025, 7, 3)], {}, market=None, facts=None, sic=None,
                                sectors=None, splits=None, euros_per_dollar=pd.Series(dtype=float),
                                factors=pd.DataFrame())
