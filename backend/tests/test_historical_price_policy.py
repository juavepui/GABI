import pandas as pd
import pytest

from gabi import config, historical_archive, storage
from gabi.historical_price_policy import (
    ADJUSTED,
    YAHOO_SOURCE,
    price_history,
    qualify_fallback,
    record_series,
    record_terminal,
    terminal_event,
    terminal_return,
)


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    storage.init_db()
    historical_archive.register_source("archive:test", {"start": "2010-01-01", "end_exclusive": "2016-01-01"})


def _refs(*kinds):
    return [{"kind": kind, "source_url": f"https://www.sec.gov/Archives/{kind}"} for kind in kinds]


def test_fallback_without_yahoo_requires_independent_boundaries_and_adjustments():
    archive = {"complete": True, "first": "2012-01-03", "last": "2012-12-31"}
    proof = {"first_trade": "2010-01-01", "last_trade": "2013-12-31",
             "boundary_evidence": ["sec-filing"], "adjustment_basis": ADJUSTED,
             "adjustment_evidence": ["dividend-reconciliation"],
             "corporate_action_evidence": ["split-and-dividend-ledger"]}
    assert qualify_fallback(identity_tier="confirmed_by_multiple_evidence", recycled=False,
                            archive=archive, overlap="insufficient_overlap", proof=proof) == (
        True, "fallback_accredited")
    assert qualify_fallback(identity_tier="confirmed_by_multiple_evidence", recycled=False,
                            archive=archive, overlap="divergent_overlap", proof=proof)[0] is False
    assert qualify_fallback(identity_tier="confirmed_by_multiple_evidence", recycled=True,
                            archive=archive, overlap="insufficient_overlap", proof=proof)[0] is False
    assert qualify_fallback(identity_tier="confirmed_by_multiple_evidence", recycled=False,
                            archive=archive, overlap="insufficient_overlap",
                            proof={**proof, "first_trade": "2013-01-01"}) == (
        False, "archive_outside_trading_life")
    assert qualify_fallback(identity_tier="confirmed_by_multiple_evidence", recycled=False,
                            archive=archive, overlap="insufficient_overlap",
                            proof={**proof, "adjustment_basis": "split_adjusted"}) == (
        False, "archive_adjustment_unverified")


def test_attributed_read_is_idempotent_rejects_recycling_and_missing_session(db):
    dates = pd.to_datetime(["2012-01-03", "2012-01-04", "2012-01-06"])
    prices = pd.DataFrame({"Open": [10., 11., 12.], "High": [10., 11., 12.],
                           "Low": [10., 11., 12.], "Close": [10., 11., 12.],
                           "Adj Close": [9., 10., 11.], "Volume": [100.] * 3}, index=dates)
    storage.upsert_prices("OLD", prices)
    refs = _refs("identity", "source")
    for _ in range(2):
        record_series(cik="1", symbol="OLD", valid_from="2012-01-03", valid_to="2012-01-07",
                      source_id=YAHOO_SOURCE, adjustment_basis=ADJUSTED, status="tier_a", evidence=refs)
    with storage.get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM historical_price_provenance").fetchone()[0] == 1
    frame = price_history(cik="1", symbol="OLD", start="2012-01-03", end="2012-01-07")
    assert frame.attrs["entity_id"] == "cik:0000000001"
    assert frame.attrs["price_source_status"] == "tier_a"
    assert frame.loc[pd.Timestamp("2012-01-03"), "adj_close"] == 9.
    with pytest.raises(ValueError, match="Missing exchange session"):
        price_history(cik="1", symbol="OLD", start="2012-01-03", end="2012-01-07",
                      sessions=pd.to_datetime(["2012-01-03", "2012-01-04", "2012-01-05", "2012-01-06"]))
    with pytest.raises(ValueError, match="another issuer"):
        record_series(cik="2", symbol="OLD", valid_from="2012-01-04", valid_to="2012-01-07",
                      source_id=YAHOO_SOURCE, adjustment_basis=ADJUSTED, status="tier_a", evidence=refs)
    with pytest.raises(ValueError, match="adjusted"):
        record_series(cik="1", symbol="OLD", valid_from="2012-01-03", valid_to="2012-01-07",
                      source_id="archive:test", adjustment_basis="as_traded", status="tier_b",
                      evidence=_refs("identity", "source", "first_trade", "last_trade", "adjustment", "corporate_actions"))


def test_confirmed_cash_event_uses_consideration_and_stock_needs_successor(db):
    refs = _refs("terms")
    record_terminal(cik="1", symbol="OLD", event_date="2013-01-04", event_type="cash_acquisition",
                    status="terminal_return_confirmed", cash_per_share=30., evidence=refs)
    event = {"status": "terminal_return_confirmed", "cash_per_share": 30.}
    assert terminal_return(event, entry_adj_close=10., last_close=20., last_adj_close=18.) == pytest.approx(1.7)
    with pytest.raises(ValueError, match="consideration"):
        record_terminal(cik="1", symbol="SWAP", event_date="2013-01-04", event_type="stock_acquisition",
                        status="terminal_return_confirmed", cash_per_share=0., evidence=refs)
    stock = {"status": "terminal_return_confirmed", "exchange_ratio": 0.5}
    with pytest.raises(ValueError, match="successor"):
        terminal_return(stock, entry_adj_close=10., last_close=20., last_adj_close=18.)
    assert terminal_return(stock, entry_adj_close=10., last_close=20., last_adj_close=18.,
                           successor_close=40.) == pytest.approx(0.8)
    with pytest.raises(ValueError, match="not confirmed"):
        terminal_return({"status": "terminal_return_unknown"}, entry_adj_close=10.,
                        last_close=20., last_adj_close=18.)


def test_archive_without_yahoo_and_ticker_change_stay_in_distinct_intervals(db):
    rows = pd.DataFrame({"symbol": ["OLD", "NEW"], "date": ["2012-01-03", "2012-01-04"],
                         "open": [10., 11.], "high": [10., 11.], "low": [10., 11.],
                         "close": [10., 11.], "adjusted_close": [8., 9.], "volume": [100., 100.]})
    historical_archive.import_price_chunk("archive:test", rows, {"OLD", "NEW"},
                                          "2010-01-01", "2016-01-01")
    refs = _refs("identity", "source", "first_trade", "last_trade", "adjustment", "corporate_actions")
    for ref in refs:
        if ref["kind"] == "first_trade":
            ref["date"] = "2012-01-03"
        elif ref["kind"] == "last_trade":
            ref["date"] = "2012-01-04"
        elif ref["kind"] == "adjustment":
            ref["method"] = "split_dividend_reconciliation"
        elif ref["kind"] == "corporate_actions":
            ref.update(valid_from="2012-01-03", valid_to="2012-01-05")
    record_series(cik="1", symbol="OLD", valid_from="2012-01-03", valid_to="2012-01-04",
                  source_id="archive:test", adjustment_basis=ADJUSTED, status="tier_b", evidence=refs)
    record_series(cik="1", symbol="NEW", valid_from="2012-01-04", valid_to="2012-01-05",
                  source_id="archive:test", adjustment_basis=ADJUSTED, status="tier_b", evidence=refs)
    assert price_history(cik="1", symbol="OLD", start="2012-01-03", end="2012-01-04").attrs[
        "price_source_status"] == "tier_b"
    assert price_history(cik="1", symbol="NEW", start="2012-01-04", end="2012-01-05").iloc[0].adj_close == 9.
    with pytest.raises(ValueError, match="No unique accredited"):
        price_history(cik="1", symbol="OLD", start="2012-01-03", end="2012-01-05")
    with pytest.raises(ValueError, match="Overlapping accredited"):
        record_series(cik="1", symbol="OLD", valid_from="2012-01-03", valid_to="2012-01-04",
                      source_id=YAHOO_SOURCE, adjustment_basis=ADJUSTED, status="tier_a",
                      evidence=_refs("identity", "source"))


def test_unknown_terminal_event_blocks_strict_price_read(db):
    dates = pd.to_datetime(["2012-01-03", "2012-01-04"])
    frame = pd.DataFrame({"Open": [10., 11.], "High": [10., 11.], "Low": [10., 11.],
                          "Close": [10., 11.], "Adj Close": [10., 11.],
                          "Volume": [100., 100.]}, index=dates)
    storage.upsert_prices("OLD", frame)
    record_series(cik="1", symbol="OLD", valid_from="2012-01-03", valid_to="2012-01-05",
                  source_id=YAHOO_SOURCE, adjustment_basis=ADJUSTED,
                  status="tier_a", evidence=_refs("identity", "source"))
    record_terminal(cik="1", symbol="OLD", event_date="2012-01-04", event_type="delisting",
                    status="terminal_return_unknown", evidence=_refs("filing"))
    assert terminal_event(cik="1", symbol="OLD", start="2012-01-03", end="2012-01-05")[
        "status"] == "terminal_return_unknown"
    with pytest.raises(ValueError, match="terminal event"):
        price_history(cik="1", symbol="OLD", start="2012-01-03", end="2012-01-05")


def test_divergent_archive_cannot_be_accredited_even_with_evidence(db):
    dates = pd.bdate_range("2012-01-03", periods=80)
    values = pd.Series(range(100, 180), index=dates, dtype=float)
    yahoo = pd.DataFrame({"Open": values * 2, "High": values * 2,
                          "Low": values * 2, "Close": values * 2,
                          "Adj Close": values * 2, "Volume": 100.}, index=dates)
    storage.upsert_prices("OLD", yahoo)
    archive = pd.DataFrame({"symbol": "OLD", "date": dates.strftime("%Y-%m-%d"),
                            "open": values.to_numpy(), "high": values.to_numpy(),
                            "low": values.to_numpy(), "close": values.to_numpy(),
                            "adjusted_close": values.to_numpy(), "volume": 100.})
    archive.loc[40:, "adjusted_close"] *= 0.5
    historical_archive.import_price_chunk("archive:test", archive, {"OLD"},
                                          "2010-01-01", "2016-01-01")
    refs = _refs("identity", "source", "first_trade", "last_trade", "adjustment", "corporate_actions")
    first, last = dates[0].date().isoformat(), dates[-1].date().isoformat()
    end = (dates[-1] + pd.Timedelta(days=1)).date().isoformat()
    for ref in refs:
        if ref["kind"] == "first_trade":
            ref["date"] = first
        elif ref["kind"] == "last_trade":
            ref["date"] = last
        elif ref["kind"] == "adjustment":
            ref["method"] = "split_dividend_reconciliation"
        elif ref["kind"] == "corporate_actions":
            ref.update(valid_from=first, valid_to=end)
    with pytest.raises(ValueError, match="diverge"):
        record_series(cik="1", symbol="OLD", valid_from=first, valid_to=end,
                      source_id="archive:test", adjustment_basis=ADJUSTED,
                      status="tier_b", evidence=refs)


def test_overlapping_windows_from_two_sources_need_agreeing_returns(db):
    dates = pd.bdate_range("2012-01-03", periods=120)
    values = pd.Series([100 + i * 0.3 for i in range(120)], index=dates)
    storage.upsert_prices("OLD", pd.DataFrame({"Open": values, "High": values, "Low": values, "Close": values,
                                               "Adj Close": values, "Volume": 100.}, index=dates))
    archive = pd.DataFrame({"symbol": "OLD", "date": dates.strftime("%Y-%m-%d"), "open": values.to_numpy() * 2,
                            "high": values.to_numpy() * 2, "low": values.to_numpy() * 2,
                            "close": values.to_numpy() * 2, "adjusted_close": values.to_numpy() * 2,
                            "volume": 100.})
    historical_archive.import_price_chunk("archive:test", archive, {"OLD"}, "2010-01-01", "2016-01-01")
    record_series(cik="1", symbol="OLD", valid_from=dates[0].date().isoformat(),
                  valid_to=dates[99].date().isoformat(), source_id=YAHOO_SOURCE, adjustment_basis=ADJUSTED,
                  status="tier_a", evidence=_refs("identity", "source"))
    refs = _refs("identity", "source", "first_trade", "last_trade", "adjustment", "corporate_actions")
    start, end = dates[20].date().isoformat(), (dates[-1] + pd.Timedelta(days=1)).date().isoformat()
    for ref in refs:
        ref.update({"first_trade": {"date": "2001-01-01"}, "last_trade": {"date": "2020-01-01"},
                    "adjustment": {"method": "split_dividend_reconciliation"},
                    "corporate_actions": {"valid_from": start, "valid_to": end}}.get(ref["kind"], {}))
    # Same returns on the shared span: consecutive windows may use either source.
    record_series(cik="1", symbol="OLD", valid_from=start, valid_to=end, source_id="archive:test",
                  adjustment_basis=ADJUSTED, status="tier_b", evidence=refs)
    shared = price_history(cik="1", symbol="OLD", start=dates[30].date().isoformat(),
                           end=dates[50].date().isoformat())
    assert shared.attrs["source_id"] == YAHOO_SOURCE
    with storage.get_connection() as conn:
        conn.execute("UPDATE historical_prices SET adj_close=adj_close*0.5 WHERE source_id='archive:test' "
                     "AND date>=?", (dates[60].date().isoformat(),))
        conn.execute("DELETE FROM historical_price_provenance WHERE source_id='archive:test'")
        conn.commit()
    with pytest.raises(ValueError, match="diverge|Overlapping accredited"):
        record_series(cik="1", symbol="OLD", valid_from=start, valid_to=end, source_id="archive:test",
                      adjustment_basis=ADJUSTED, status="tier_b", evidence=refs)
