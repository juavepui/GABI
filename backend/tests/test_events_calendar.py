import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gabi import config, events_calendar, storage


def _isolate_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")


def _epoch(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp())


TODAY = date(2026, 9, 20)


def test_parse_corporate_events_confirmed_earnings():
    info = {
        "earningsTimestampStart": _epoch(date(2026, 10, 29)),
        "earningsTimestampEnd": _epoch(date(2026, 10, 29)),
        "isEarningsDateEstimate": False,
    }
    events = events_calendar.parse_corporate_events("AAPL", info, "2026-09-20T00:00:00", today=TODAY)
    assert len(events) == 1
    e = events[0]
    assert e["event_type"] == "earnings"
    assert e["event_date"] == date(2026, 10, 29)
    assert e["range_end"] is None
    assert e["is_estimate"] is False
    assert e["days_until"] == 39
    assert e["source"] == "Yahoo Finance (info)"
    assert e["fetched_at"] == "2026-09-20T00:00:00"


def test_parse_corporate_events_estimated_range():
    info = {
        "earningsTimestampStart": _epoch(date(2026, 10, 27)),
        "earningsTimestampEnd": _epoch(date(2026, 10, 31)),
        "isEarningsDateEstimate": True,
    }
    events = events_calendar.parse_corporate_events("MSFT", info, "2026-09-20T00:00:00", today=TODAY)
    e = events[0]
    assert e["event_date"] == date(2026, 10, 27)
    assert e["range_end"] == date(2026, 10, 31)
    assert e["is_estimate"] is True


def test_parse_corporate_events_missing_estimate_flag_defaults_to_estimated():
    """Fail closed: si Yahoo no informa isEarningsDateEstimate, GABI no
    afirma que la fecha esté confirmada."""
    info = {"earningsTimestampStart": _epoch(date(2026, 10, 29))}
    events = events_calendar.parse_corporate_events("XXX", info, "2026-09-20T00:00:00", today=TODAY)
    assert events[0]["is_estimate"] is True


def test_parse_corporate_events_includes_dividend_events():
    info = {
        "exDividendDate": _epoch(date(2026, 8, 10)),
        "dividendDate": _epoch(date(2026, 8, 13)),
    }
    events = events_calendar.parse_corporate_events("AAPL", info, "2026-09-20T00:00:00", today=TODAY)
    types = {e["event_type"] for e in events}
    assert types == {"ex_dividend", "dividend_payment"}
    for e in events:
        assert e["is_estimate"] is False


def test_parse_corporate_events_empty_info_returns_no_events():
    assert events_calendar.parse_corporate_events("ZZZ", {}, "2026-09-20T00:00:00", today=TODAY) == []


def test_parse_corporate_events_days_until_can_be_negative_for_past_dates():
    info = {"earningsTimestampStart": _epoch(date(2026, 9, 1)), "isEarningsDateEstimate": False}
    events = events_calendar.parse_corporate_events("AAA", info, "2026-09-20T00:00:00", today=TODAY)
    assert events[0]["days_until"] == -19


def test_upcoming_events_filters_out_past_and_sorts_by_date(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    storage.upsert_fundamentals("AAA", {
        "earningsTimestampStart": _epoch(date(2026, 10, 1)), "isEarningsDateEstimate": False,
    }, pd.DataFrame(), pd.DataFrame())
    storage.upsert_fundamentals("BBB", {
        "earningsTimestampStart": _epoch(date(2026, 9, 1)), "isEarningsDateEstimate": True,
    }, pd.DataFrame(), pd.DataFrame())
    storage.upsert_fundamentals("CCC", {
        "earningsTimestampStart": _epoch(date(2026, 9, 25)), "isEarningsDateEstimate": True,
    }, pd.DataFrame(), pd.DataFrame())

    df = events_calendar.upcoming_events(["AAA", "BBB", "CCC"], today=TODAY)
    assert list(df["symbol"]) == ["CCC", "AAA"]  # BBB queda fuera (pasado); orden ascendente por fecha


def test_upcoming_events_empty_symbols_returns_empty_dataframe():
    df = events_calendar.upcoming_events([], today=TODAY)
    assert df.empty


def test_next_earnings_map_returns_none_for_symbol_without_data(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    storage.upsert_fundamentals("AAA", {
        "earningsTimestampStart": _epoch(date(2026, 10, 1)), "isEarningsDateEstimate": False,
    }, pd.DataFrame(), pd.DataFrame())

    result = events_calendar.next_earnings_map(["AAA", "BBB"], today=TODAY)
    assert result["AAA"]["days_until"] == 11
    assert result["BBB"] is None


def test_parse_earnings_history_keeps_only_reported_rows():
    df = pd.DataFrame(
        {"EPS Estimate": [1.98, 1.89, 1.94], "Reported EPS": [None, 2.02, 2.01], "Surprise(%)": [None, 6.74, 3.46]},
        index=pd.to_datetime(["2026-10-29", "2026-07-30", "2026-04-30"], utc=True),
    )
    rows = events_calendar.parse_earnings_history("AAPL", df, today=TODAY)
    assert len(rows) == 2
    assert rows[0]["earnings_date"] == date(2026, 7, 30)
    assert rows[0]["eps_reported"] == 2.02
    assert rows[0]["surprise_pct"] == 6.74


def test_parse_earnings_history_empty_dataframe_returns_empty_list():
    assert events_calendar.parse_earnings_history("AAPL", pd.DataFrame(), today=TODAY) == []
    assert events_calendar.parse_earnings_history("AAPL", None, today=TODAY) == []


def test_compute_price_reaction_computes_gap_around_earnings_date():
    prices = pd.DataFrame(
        {"adj_close": [100.0, 101.0, 120.0, 121.0]},
        index=pd.to_datetime(["2026-07-28", "2026-07-29", "2026-07-31", "2026-08-01"]),
    )
    reaction = events_calendar.compute_price_reaction(prices, date(2026, 7, 30))
    # última sesión antes del 30 (29 jul, 101.0) -> primera sesión en/después (31 jul, 120.0)
    assert round(reaction, 2) == round((120.0 / 101.0 - 1) * 100, 2)


def test_compute_price_reaction_none_when_no_data_before_or_after():
    prices = pd.DataFrame({"adj_close": [100.0]}, index=pd.to_datetime(["2026-07-29"]))
    assert events_calendar.compute_price_reaction(prices, date(2026, 7, 25)) is None  # nada antes
    assert events_calendar.compute_price_reaction(prices, date(2026, 8, 1)) is None  # nada después


def test_compute_price_reaction_empty_or_missing_column_returns_none():
    assert events_calendar.compute_price_reaction(pd.DataFrame(), date(2026, 7, 30)) is None
    assert events_calendar.compute_price_reaction(None, date(2026, 7, 30)) is None
    prices = pd.DataFrame({"close": [100.0]}, index=pd.to_datetime(["2026-07-29"]))
    assert events_calendar.compute_price_reaction(prices, date(2026, 7, 30)) is None


def test_store_and_get_earnings_surprises_roundtrip(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    rows = [
        {"symbol": "AAA", "earnings_date": date(2026, 7, 30), "eps_estimate": 1.89,
         "eps_reported": 2.02, "surprise_pct": 6.74, "price_reaction_pct": 3.1},
        {"symbol": "AAA", "earnings_date": date(2026, 4, 30), "eps_estimate": 1.94,
         "eps_reported": 2.01, "surprise_pct": 3.46, "price_reaction_pct": -1.2},
    ]
    events_calendar.store_earnings_surprises(rows)
    df = events_calendar.get_earnings_surprises("AAA")
    assert len(df) == 2
    assert list(df["earnings_date"]) == ["2026-07-30", "2026-04-30"]  # descendente
    assert df.iloc[0]["source"] == "Yahoo Finance (earnings_dates)"


def test_store_earnings_surprises_is_idempotent_on_reinsert(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    row = [{"symbol": "AAA", "earnings_date": date(2026, 7, 30), "eps_estimate": 1.89,
           "eps_reported": 2.02, "surprise_pct": 6.74, "price_reaction_pct": 3.1}]
    events_calendar.store_earnings_surprises(row)
    events_calendar.store_earnings_surprises(row)
    df = events_calendar.get_earnings_surprises("AAA")
    assert len(df) == 1


def test_store_earnings_surprises_empty_list_is_noop(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    events_calendar.store_earnings_surprises([])
    assert events_calendar.get_earnings_surprises("AAA").empty


def test_sync_earnings_surprises_classifies_network_failures(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)

    def _boom(symbol):
        raise ConnectionError("network unreachable")

    monkeypatch.setattr(events_calendar, "_fetch_earnings_history_attempt", _boom)
    failed = events_calendar.sync_earnings_surprises(["AAA"])
    assert "AAA" in failed


def test_sync_earnings_surprises_empty_symbols_returns_empty_dict():
    assert events_calendar.sync_earnings_surprises([]) == {}
