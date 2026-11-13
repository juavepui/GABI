"""Corporate-date and reported-EPS references, explicit sync and bounded price parity."""
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

from gabi.application.market.earnings_sync import EarningsAttempt, sync_earnings_surprises
from gabi.domain.market import events
from gabi.domain.research.live_ledger import safe
from gabi.infrastructure.storage.earnings import SqliteEarnings

TODAY = date(2024, 7, 30)


def event_info(case):
    def epoch(day):
        return int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp())

    if case == "empty":
        return {}
    if case == "invalid":
        return {"earningsTimestampStart": "invalid", "exDividendDate": None, "dividendDate": {}}
    return {"earningsTimestampStart": epoch("2024-07-30"), "earningsTimestampEnd": epoch("2024-08-01"),
            "isEarningsDateEstimate": case != "confirmed", "exDividendDate": epoch("2024-07-29"),
            "dividendDate": epoch("2024-08-02")}


def reported_history():
    return pd.DataFrame({"EPS Estimate": [1., None, 0., 1.], "Reported EPS": [1.1, 0., None, 1.2],
                         "Surprise(%)": [10., None, None, 20.]},
                        index=pd.to_datetime(["2024-04-30", "2024-07-30", "2024-08-01", "2024-10-30"]))


def reaction_frame(case="normal"):
    values = [100., 110., 120., 130.]
    if case == "zero":
        values[1] = 0.
    if case == "missing":
        values[1] = float("nan")
    return pd.DataFrame({"adj_close": values}, index=pd.to_datetime([
        "2024-04-29", "2024-04-30", "2024-07-29", "2024-07-30"]))


def reference():
    return json.loads((Path(__file__).parent / "fixtures/events_migration.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", ["confirmed", "estimated", "invalid", "empty"])
def test_event_dates_match_original(case):
    info = event_info(case)
    before = dict(info)
    assert safe(events.parse_corporate_events("AAA", info, "captured", today=TODAY)) == reference()["events"][case]
    assert info == before


def test_reported_history_reactions_and_required_clock_match_original():
    history = reported_history()
    before = history.copy(deep=True)
    assert safe(events.parse_earnings_history("AAA", history, today=TODAY)) == reference()["reported"]
    for case in ("normal", "zero", "missing"):
        prices = reaction_frame(case)
        reactions = [events.compute_price_reaction(prices, day) for day in (
            date(2024, 4, 29), date(2024, 4, 30), date(2024, 7, 30), date(2024, 8, 1))]
        assert reactions == reference()["reactions"][case]
    pd.testing.assert_frame_equal(history, before)
    with pytest.raises(TypeError, match="today"):
        events.parse_corporate_events("AAA", {}, "captured")


def test_sync_persists_original_units_with_operation_clock_and_classifies_failures(tmp_path):
    prices = reaction_frame()
    import sqlite3

    target = tmp_path / "one"
    target.mkdir()
    with sqlite3.connect(target / "gabi.db") as db:
        db.execute("CREATE TABLE prices(symbol TEXT,date TEXT,adj_close REAL,PRIMARY KEY(symbol,date))")
        db.executemany("INSERT INTO prices VALUES(?,?,?)", [("AAA", day.date().isoformat(), value)
                                                          for day, value in prices.adj_close.items()])
    now = datetime.fromisoformat("2024-07-30T20:30:00+00:00")
    store = SqliteEarnings(target, now=lambda: now)

    class Source:
        def attempts(self, symbols, max_workers):
            yield EarningsAttempt("AAA", reported_history())
            yield EarningsAttempt("BAD", error=ConnectionError("offline"))
            yield EarningsAttempt("EMPTY", pd.DataFrame())

    progress = []
    failed = sync_earnings_surprises(["AAA", "BAD", "EMPTY"], Source(), store, lambda exc: str(exc),
                                    today=TODAY, progress_cb=lambda done, total: progress.append((done, total)))
    assert failed == {"BAD": "offline"} and progress == [(1, 3), (2, 3), (3, 3)]
    rows = store.read("AAA")
    assert rows.earnings_date.tolist() == ["2024-07-30", "2024-04-30"]
    assert rows.recorded_at.tolist() == [now.isoformat()] * 2
    assert rows.price_reaction_pct.tolist() == pytest.approx([100 * (130 / 120 - 1), 10.])
    before = store.path.read_bytes()
    store.read("AAA")
    assert store.path.read_bytes() == before
    assert SqliteEarnings(tmp_path / "other").read("AAA").empty
    assert not (tmp_path / "other").exists()


def test_bounded_prices_match_full_series_including_null_zero_and_large_gaps(tmp_path):
    import sqlite3

    with sqlite3.connect(tmp_path / "gabi.db") as db:
        db.execute("CREATE TABLE prices(symbol TEXT,date TEXT,adj_close REAL,PRIMARY KEY(symbol,date))")
        days = pd.date_range("2010-01-01", "2024-07-30", freq="30D")
        values = [None if i % 11 == 0 else 0. if i % 17 == 0 else float(i + 100) for i in range(len(days))]
        db.executemany("INSERT INTO prices VALUES(?,?,?)", [("AAA", day.date().isoformat(), value)
                                                          for day, value in zip(days, values, strict=True)])
    full = pd.DataFrame({"adj_close": values}, index=days)
    dates = [date(2010, 1, 1), date(2015, 1, 2), date(2020, 6, 10), date(2024, 7, 30)]
    store = SqliteEarnings(tmp_path)
    before = store.path.read_bytes()
    bounded = store.reaction_prices("AAA", dates)
    for day in dates:
        assert events.compute_price_reaction(bounded, day) == events.compute_price_reaction(full, day)
    assert len(bounded) <= 2 * len(dates) and store.path.read_bytes() == before


def test_empty_sync_has_no_source_or_storage_effects():
    assert sync_earnings_surprises([], None, None, None, today=TODAY) == {}
