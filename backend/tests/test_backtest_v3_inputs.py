"""Backtest V3 inputs from cached price series (#249), over synthetic frames and temporary databases."""

import sqlite3
from contextlib import closing
from datetime import date

import pandas as pd
import pytest

from gabi.application.research import backtest_v3_data
from gabi.domain.portfolio import backtest_v3 as v3
from gabi.domain.portfolio import backtest_v3_inputs as inputs
from gabi.infrastructure.storage.ticker_prices import SqliteTickerPrices

DAYS = pd.to_datetime(["2024-03-01", "2024-03-04", "2024-03-05", "2024-03-06", "2024-03-07", "2024-03-08",
                       "2024-03-11"])
# As traded: a 2 $ dividend on 03-04, a 2:1 split on 03-06 and a 1 $ dividend on 03-08.
TRADED = [100.0, 100.0, 104.0, 52.0, 53.0, 52.0, 53.0]
TRADED_VOLUME = [1000.0, 1000.0, 1000.0, 2000.0, 2000.0, 2000.0, 2000.0]
SPLIT_DAY = pd.Timestamp("2024-03-06")


def adjusted(closes: list[float]) -> list[float]:
    """Adjusted close (splits and dividends) of an as-traded series, as Yahoo and the archives compute it."""
    split = [2.0 if day < SPLIT_DAY else 1.0 for day in DAYS]
    on_today = [close / factor for close, factor in zip(closes, split, strict=True)]
    m2, m6 = 1 - 1 / on_today[0], 1 - 1 / on_today[4]
    return [close * (m6 if i < 5 else 1) * (m2 if i < 1 else 1) for i, close in enumerate(on_today)]


def yahoo_frame() -> pd.DataFrame:
    split = [2.0 if day < SPLIT_DAY else 1.0 for day in DAYS]
    close = [price / factor for price, factor in zip(TRADED, split, strict=True)]
    return pd.DataFrame({"open": close, "close": close, "volume": [v * f for v, f in zip(TRADED_VOLUME, split, strict=True)],
                         "adj_close": adjusted(TRADED)}, index=DAYS)


def archive_frame() -> pd.DataFrame:
    frame = pd.DataFrame({"open": TRADED, "close": TRADED, "volume": TRADED_VOLUME, "adj_close": adjusted(TRADED)},
                         index=DAYS)
    frame.attrs.update(source_id="finsaber:test", source_symbol="AAA")
    return frame


SPLITS = pd.Series({SPLIT_DAY: 2.0})


def summary(series: inputs.SeriesInputs):
    bars = {day: (round(bar.open, 9), round(bar.close, 9), round(bar.volume, 9), bar.suspended)
            for day, bar in series.bars.items()}
    events = [(event.kind, event.day, round(event.ratio, 9), round(event.cash, 9)) for event in series.events]
    return bars, events


def test_both_bases_give_the_traded_bars_and_the_same_events():
    today = inputs.series_inputs("AAA", yahoo_frame(), basis=inputs.TODAY_SPLITS, splits=SPLITS)
    traded = inputs.series_inputs("AAA", archive_frame(), basis=inputs.AS_TRADED)
    assert summary(today) == summary(traded)
    bars, events = summary(today)
    assert [bar[1] for bar in bars.values()] == TRADED
    assert [bar[2] for bar in bars.values()] == TRADED_VOLUME
    assert events == [("dividend", date(2024, 3, 4), 1.0, 2.0), ("split", date(2024, 3, 6), 2.0, 0.0),
                      ("dividend", date(2024, 3, 8), 1.0, 1.0)]
    assert today.anomalies == traded.anomalies == []


def test_absent_and_halted_sessions_are_never_priced():
    frame = yahoo_frame()
    frame.loc[DAYS[2], ["open", "close"]] = float("nan")
    frame.loc[DAYS[3], "volume"] = 0.0
    series = inputs.series_inputs("AAA", frame, basis=inputs.TODAY_SPLITS, splits=SPLITS,
                                  start=date(2024, 3, 5), end=date(2024, 3, 8))
    assert DAYS[2].date() not in series.bars and DAYS[1].date() not in series.bars
    assert series.bars[DAYS[3].date()].suspended
    assert DAYS[-1].date() not in series.bars
    # The split still applies on its ex-date; the dividend before the window does not.
    assert [(event.kind, event.day) for event in series.events] == [("split", date(2024, 3, 6)),
                                                                    ("dividend", date(2024, 3, 8))]
    with pytest.raises(ValueError, match="Base de precios"):
        inputs.series_inputs("AAA", frame, basis="adjusted")


def test_an_unexplained_jump_is_reported_not_paid():
    frame = yahoo_frame()
    frame.loc[DAYS[4]:, "adj_close"] *= 3.0  # A tripled adjusted close: not a dividend.
    series = inputs.series_inputs("AAA", frame, basis=inputs.TODAY_SPLITS, splits=SPLITS)
    assert [anomaly["day"] for anomaly in series.anomalies] == ["2024-03-07"]
    assert all(event.day != date(2024, 3, 7) for event in series.events)


def test_v3_over_the_inputs_reconciles_shares_dividends_and_nav():
    data = backtest_v3_data.load({"AAA": yahoo_frame()}, lambda symbols: {"AAA": SPLITS},
                                 start=DAYS[0].date(), end=DAYS[-1].date())
    sessions = [day.date() for day in DAYS]
    result = v3.run(sessions, data.bars, rebalances=[v3.Rebalance(sessions[0], {"AAA": 1.0})],
                    costs=v3.Costs(participation=1.0, cost_reserve=0.0), initial_cash=10_000.0, events=data.events)
    (buy,) = result["trades"]
    # Bought at the 03-04 open (100 $, after its ex-dividend): 100 shares, 200 after the split.
    assert buy["day"] == "2024-03-04" and buy["shares"] == pytest.approx(100.0)
    assert result["final_shares"]["AAA"] == pytest.approx(200.0)
    assert result["dividends"] == pytest.approx(200.0)
    assert result["daily"][-1]["nav"] == pytest.approx(200 * 53.0 + 200.0)
    assert result["identity_error"] < 1e-9


def test_load_picks_the_basis_by_provenance_and_reads_splits_once():
    requested = []

    def splits(symbols):
        requested.append(symbols)
        return {"AAA.OLD": SPLITS}

    yahoo = yahoo_frame()
    yahoo.attrs["source_symbol"] = "AAA.OLD"
    data = backtest_v3_data.load({"AAA": yahoo, "BBB": archive_frame(), "CCC": None, "DDD": pd.DataFrame()},
                                 splits, start=DAYS[0].date(), end=DAYS[-1].date())
    assert requested == [["AAA.OLD"]]
    assert data.bases == {"AAA": inputs.TODAY_SPLITS, "BBB": inputs.AS_TRADED}
    assert data.missing == ["CCC", "DDD"]
    assert data.bars["AAA"] == data.bars["BBB"]
    assert len(data.events) == 6


def test_split_ratios_come_from_the_cache_in_one_bounded_read(tmp_path):
    path = tmp_path / "gabi.db"
    assert SqliteTickerPrices(path).splits_many(["AAA"])["AAA"].empty
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("CREATE TABLE splits (symbol TEXT NOT NULL, date TEXT NOT NULL, ratio REAL NOT NULL, "
                   "PRIMARY KEY (symbol, date))")
        db.executemany("INSERT INTO splits VALUES (?,?,?)",
                       [("AAA", "2020-08-31", 4.0), ("AAA", "2014-06-09", 7.0), ("BBB", "2022-07-18", 20.0)])
    found = SqliteTickerPrices(path).splits_many(["AAA", "CCC", "AAA"])
    assert list(found) == ["AAA", "CCC"] and found["CCC"].empty
    assert found["AAA"].to_dict() == {pd.Timestamp("2014-06-09"): 7.0, pd.Timestamp("2020-08-31"): 4.0}


def ended(last=4):
    """The archive series up to its ``last`` session; the calendar continues."""
    frame = archive_frame().iloc[:last + 1]
    frame.attrs.update(archive_frame().attrs)
    return frame


def test_an_ended_series_exits_with_v2_terminal_semantics():
    sessions = [day.date() for day in DAYS]
    after = DAYS[5].date()
    cases = {
        None: ("delisting", 53.0, "series_ended_without_event", False),
        ("cash_acquisition", "terminal_return_confirmed", 60.0, None): ("cash_merger", 60.0, "terminal_return_confirmed", True),
        ("bankruptcy_liquidation", "terminal_return_confirmed", 0.0, None): ("bankruptcy", 0.0, "terminal_return_confirmed", True),
        ("succession", "terminal_return_confirmed", None, 1.0): ("cash_merger", 53.0, "succession_one_for_one", True),
        ("stock_acquisition", "terminal_return_confirmed", None, 0.5): ("delisting", 53.0, "terminal_return_confirmed", False),
        ("merger", "terminal_return_bounded", 70.0, None): ("delisting", 53.0, "terminal_return_bounded", False),
    }
    for key, (kind, cash, status, strict) in cases.items():
        event = None if key is None else dict(zip(("event_type", "status", "cash_per_share", "exchange_ratio"), key,
                                                 strict=True))
        data = backtest_v3_data.load({"AAA": ended()}, lambda symbols: {}, start=sessions[0], end=sessions[-1],
                                     sessions=sessions, terminal_event=lambda symbol, frame, event=event: event)
        exit_event = data.events[-1]
        assert (exit_event.kind, exit_event.day, exit_event.cash) == (kind, after, cash), key
        (record,) = data.exits
        assert (record["status"], record["strict"], data.strict) == (status, strict, strict), key


def test_a_series_reaching_the_last_session_has_no_exit_and_v3_settles_an_ended_one():
    sessions = [day.date() for day in DAYS]
    full = backtest_v3_data.load({"AAA": archive_frame()}, lambda symbols: {}, start=sessions[0], end=sessions[-1],
                                 sessions=sessions, terminal_event=lambda symbol, frame: pytest.fail("not asked"))
    assert full.exits == [] and full.strict
    event = {"event_type": "cash_acquisition", "status": "terminal_return_confirmed", "cash_per_share": 60.0}
    data = backtest_v3_data.load({"AAA": ended()}, lambda symbols: {}, start=sessions[0], end=sessions[-1],
                                 sessions=sessions, terminal_event=lambda symbol, frame: event)
    result = v3.run(sessions, data.bars, rebalances=[v3.Rebalance(sessions[0], {"AAA": 1.0})],
                    costs=v3.Costs(participation=1.0, cost_reserve=0.0), initial_cash=10_000.0, events=data.events)
    # 100 shares, 200 after the split; the 03-08 dividend falls after the exit, the cash merger pays 60 $.
    assert result["final_shares"] == {}
    assert result["daily"][-1]["nav"] == pytest.approx(200 * 60.0)
    assert result["identity_error"] < 1e-9
