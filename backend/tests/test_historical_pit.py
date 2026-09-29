"""#32: 2010-2015 through the existing ranking/backtest path, point in time."""

import pandas as pd
import pytest

from gabi import config, historical_archive, historical_pit, identity, storage, universe
from gabi.historical_membership import REFERENCE_SOURCE
from gabi.historical_price_policy import ADJUSTED, YAHOO_SOURCE, record_series, record_terminal

ARCHIVE = "archive:test"


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr("requests.sessions.Session.request",
                        lambda *args, **kwargs: pytest.fail("No network allowed"))
    storage.init_db()
    historical_archive.register_source(REFERENCE_SOURCE, {"start": "2010-01-01", "end_exclusive": "2016-01-01"})
    historical_archive.register_source(ARCHIVE, {"start": "2010-01-01", "end_exclusive": "2016-07-01"})
    # GONE left the index (and later stopped trading); NEWCO entered in 2013.
    historical_archive.import_membership(REFERENCE_SOURCE, pd.DataFrame([
        ("2010-01-04", "GONE,KEEP"), ("2013-01-02", "KEEP,NEWCO"),
    ], columns=["date", "tickers"]), "2010-01-01", "2016-01-01")
    historical_archive.replace_identity_intervals(historical_archive.IDENTITY_INTERVAL_SOURCE, [
        {"symbol": "GONE", "cik": "1", "valid_from": "2010-01-01", "valid_to": "2013-01-02",
         "status": "confirmed_by_multiple_evidence", "evidence_count": 2},
        {"symbol": "KEEP", "cik": "2", "valid_from": "2010-01-01", "valid_to": "2016-01-01",
         "status": "confirmed_historical_ticker", "evidence_count": 2},
        {"symbol": "NEWCO", "cik": "3", "valid_from": "2013-01-02", "valid_to": "2016-01-01",
         "status": "unresolved", "evidence_count": 0},
    ])


def _yahoo(symbol, dates, start=100.0):
    values = pd.Series([start + i * 0.1 for i in range(len(dates))], index=dates)
    storage.upsert_prices(symbol, pd.DataFrame({"Open": values, "High": values, "Low": values, "Close": values,
                                                "Adj Close": values, "Volume": 100.}, index=dates))


def _archive(symbol, dates, start=50.0):
    values = [start + i * 0.1 for i in range(len(dates))]
    historical_archive.import_price_chunk(ARCHIVE, pd.DataFrame({
        "symbol": symbol, "date": dates.strftime("%Y-%m-%d"), "open": values, "high": values, "low": values,
        "close": values, "adjusted_close": values, "volume": 100.}), {symbol}, "2010-01-01", "2016-07-01")


def _refs(start, end):
    refs = [{"kind": kind, "source_url": f"https://www.sec.gov/{kind}"} for kind in
            ("identity", "source", "first_trade", "last_trade", "adjustment", "corporate_actions")]
    for ref in refs:
        ref.update({"first_trade": {"date": "2001-01-01"}, "last_trade": {"date": "2020-01-01"},
                    "adjustment": {"method": "split_dividend_reconciliation"},
                    "corporate_actions": {"valid_from": start, "valid_to": end}}.get(ref["kind"], {}))
    return refs


def test_2012_universe_uses_the_accredited_reference_with_members_that_no_longer_exist(db):
    info = universe.get_sp500_constituents_asof("2012-06-29")
    assert info["symbols"] == ["GONE", "KEEP"]  # GONE is not in today's index
    assert info["source_id"] == REFERENCE_SOURCE and info["identity_accredited"] == 2
    later = universe.get_sp500_constituents_asof("2013-06-28")
    assert later["symbols"] == ["KEEP", "NEWCO"]  # entry and exit follow the dated membership
    assert later["identity_accredited"] == 1


def test_identity_is_resolved_by_interval_before_and_after_a_ticker_change(db):
    # KEEP is a label applied retroactively (confirmed_historical_ticker): the
    # same CIK before and after the change, and never an operational alias.
    assert identity.resolve("KEEP", "2011-03-31")["entity_id"] == "cik:0000000002"
    assert identity.resolve("KEEP", "2015-03-31")["entity_id"] == "cik:0000000002"
    assert identity.resolve("GONE", "2013-06-28")["status"] == "unresolved"  # outside its interval
    assert identity.resolve("NEWCO", "2013-06-28")["status"] == "unresolved"
    assert not identity.has_aliases("KEEP")


def test_2010_2015_never_reads_the_ticker_cache_and_uses_only_accredited_intervals(db):
    dates = pd.bdate_range("2010-01-04", "2012-12-31")
    _yahoo("KEEP", dates)
    _yahoo("NEWCO", dates)  # prices exist, identity does not: must stay out
    assert identity.backtest_prices(["KEEP", "NEWCO"], "2012-06-29")["KEEP"].empty  # no interval yet
    record_series(cik="2", symbol="KEEP", valid_from="2010-01-04", valid_to="2013-01-01",
                  source_id=YAHOO_SOURCE, adjustment_basis=ADJUSTED, status="tier_a",
                  evidence=[{"kind": "identity", "source_url": "https://sec"},
                            {"kind": "source", "source_url": "https://yahoo"}])
    prices = identity.backtest_prices(["KEEP", "NEWCO", "SPY"], "2012-06-29")
    assert prices["KEEP"].attrs["price_source_status"] == "tier_a" and not prices["KEEP"].empty
    assert prices["NEWCO"].empty
    ranking = historical_pit.ranking_series("cik:0000000002", "2012-06-29")
    assert ranking.index.max() <= pd.Timestamp("2012-06-29")
    # 2016+: the legacy path is untouched.
    assert identity.resolve("KEEP", "2016-06-30")["status"] == "unresolved"
    assert historical_pit.covers("2016-01-04") is False


def test_filing_published_after_the_ranking_date_is_not_visible(db):
    from gabi import edgar
    edgar.upsert_edgar_facts("CIK0000000002", [
        {"tag": "Revenues", "unit": "USD", "start_date": "2011-01-01", "end_date": "2011-12-31", "val": 100.0,
         "form": "10-K", "fp": "FY", "fy": 2011, "filed_date": "2012-02-20", "accn": "a1"},
        {"tag": "Revenues", "unit": "USD", "start_date": "2012-01-01", "end_date": "2012-12-31", "val": 200.0,
         "form": "10-K", "fp": "FY", "fy": 2012, "filed_date": "2013-02-20", "accn": "a2"}], cik="2")
    known = edgar.get_issuer_facts_as_of("2", "2012-06-29", tags=["Revenues"])
    assert known["val"].tolist() == [100.0]


def test_confirmed_cash_exit_settles_and_unknown_exit_is_flagged(db):
    dates = pd.bdate_range("2012-01-02", "2012-05-15")
    _archive("GONE", dates)
    end = "2012-05-16"
    record_series(cik="1", symbol="GONE", valid_from="2012-01-02", valid_to=end, source_id=ARCHIVE,
                  adjustment_basis=ADJUSTED, status="tier_b", evidence=_refs("2012-01-02", end))
    frame = historical_pit.holding_series("cik:0000000001", "2012-04-02")
    entry, exit_session = pd.Timestamp("2012-04-02"), pd.Timestamp("2012-07-02")
    unknown = historical_pit.exit_value(frame, "cik:0000000001", entry, exit_session)
    assert unknown["strict"] is False and unknown["date"] == dates[-1]
    record_terminal(cik="1", symbol="GONE", event_date="2012-05-16", event_type="cash_acquisition",
                    status="terminal_return_confirmed", cash_per_share=60.0,
                    evidence=[{"kind": "terms", "source_url": "https://sec/8k"}])
    confirmed = historical_pit.exit_value(frame, "cik:0000000001", entry, exit_session)
    last = frame.iloc[-1]
    assert confirmed["strict"] is True and confirmed["status"] == "terminal_return_confirmed"
    assert confirmed["value"] == pytest.approx(last["adj_close"] * 60.0 / last["close"])


def test_ranking_rejects_unaccredited_names_and_reports_coverage(db, monkeypatch):
    from gabi import screener_asof
    dates = pd.bdate_range("2011-06-01", "2012-07-10")
    _yahoo("KEEP", dates)
    _yahoo("GONE", dates)  # identity accredited but no accredited price interval
    _yahoo("SPY", dates)
    record_series(cik="2", symbol="KEEP", valid_from="2011-06-01", valid_to="2012-07-11",
                  source_id=YAHOO_SOURCE, adjustment_basis=ADJUSTED, status="tier_a",
                  evidence=[{"kind": "identity", "source_url": "https://sec"},
                            {"kind": "source", "source_url": "https://yahoo"}])
    result = screener_asof.build_ranking_as_of("2012-06-29")
    table, coverage = result["table"], result["universe_info"]["historical_coverage"]
    assert table.loc["KEEP", "price_source"] == YAHOO_SOURCE
    assert pd.isna(table.loc["GONE", "price_source"])  # never the ticker cache
    assert coverage["members"] == 2 and coverage["accredited_prices"] == 1
    assert coverage["excluded"]["no_accredited_price_series"] == 1


def test_backtest_v2_rejects_2010_2015_periods_with_insufficient_coverage_explicitly(db):
    from gabi import portfolio_backtest
    dates = pd.bdate_range("2011-01-03", "2012-12-31")
    _yahoo("SPY", dates)
    with pytest.raises(ValueError, match="Ningún periodo") as error:
        portfolio_backtest.run("2012-03-30", "2012-09-28", months=3, top_n=1, mode="fast_dev", max_symbols=2)
    assert "se saltaron los 1 periodos por falta de cobertura" in str(error.value)


def test_backtest_v2_settles_a_position_that_stops_trading_into_cash(db):
    from gabi import portfolio_backtest
    dates = pd.bdate_range("2012-01-02", "2012-05-15")
    _archive("GONE", dates)
    record_series(cik="1", symbol="GONE", valid_from="2012-01-02", valid_to="2012-05-16", source_id=ARCHIVE,
                  adjustment_basis=ADJUSTED, status="tier_b", evidence=_refs("2012-01-02", "2012-05-16"))
    record_terminal(cik="1", symbol="GONE", event_date="2012-05-16", event_type="cash_acquisition",
                    status="terminal_return_confirmed", cash_per_share=60.0,
                    evidence=[{"kind": "terms", "source_url": "https://sec/8k"}])
    shares, owners, warnings = {"GONE": 10.0}, {"GONE": "cik:0000000001"}, []
    entry, exit_session = pd.Timestamp("2012-04-02"), pd.Timestamp("2012-07-02")
    histories = identity.backtest_prices(["GONE"], "2012-04-02", owners)
    exits = portfolio_backtest._historical_exits(histories, shares, owners, entry, exit_session)
    sessions = pd.bdate_range(entry, exit_session)
    segment = portfolio_backtest._daily_segment(0.0, shares, entry, exit_session, sessions, owners=owners)
    cash = portfolio_backtest._settle_exits(0.0, shares, owners, exits, warnings)
    last = histories["GONE"].iloc[-1]
    assert cash == pytest.approx(10 * last["adj_close"] * 60.0 / last["close"])
    assert segment.iloc[-1] == pytest.approx(cash)  # valued at the settlement after the last trade
    assert shares == {} and owners == {} and warnings[0]["estricto"] is True


def test_ranking_on_an_audited_date_needs_that_window_accredited():
    windows = [{"as_of": "2015-03-31", "window_last": "2015-03-31", "holding_until": "2015-07-07"}]
    # NFLX-like: the 2015-06-30 window failed the audit; the previous holding
    # period reaching into July must not make it rankable on that date.
    assert historical_pit.rankable(windows, "2015-06-30") is False
    assert historical_pit.rankable(windows, "2015-03-31") is True
    # Between audited dates only the verified holding of an earlier window counts.
    assert historical_pit.rankable(windows, "2015-05-15") is True
    assert historical_pit.rankable(windows, "2015-08-03") is False
    # A rebalance on 2015-07-02 cannot fall back on the March window: the latest
    # audited window (2015-06-30) was rejected.
    assert historical_pit.rankable(windows, "2015-07-02") is False
    assert historical_pit.rankable(windows, "2010-01-02") is False  # before the first audited window
    assert historical_pit.rankable(None, "2015-06-30") is True  # manual/test intervals


def test_one_for_one_succession_is_a_strict_exit_at_the_last_price(db):
    from gabi.historical_issuer_evidence import one_for_one_quote
    assert one_for_one_quote("each share of Google Class A Common Stock was converted automatically into "
                             "one share of Alphabet Class A Common Stock")
    assert one_for_one_quote("converted into the right to receive 0.5 shares of Parent") is None
    dates = pd.bdate_range("2015-07-01", "2015-10-01")
    _archive("KEEP", dates)
    record_series(cik="2", symbol="KEEP", valid_from="2015-07-01", valid_to="2015-10-02", source_id=ARCHIVE,
                  adjustment_basis=ADJUSTED, status="tier_b", evidence=_refs("2015-07-01", "2015-10-02"))
    record_terminal(cik="2", symbol="KEEP", event_date="2015-10-02", event_type="succession",
                    status="terminal_return_confirmed", exchange_ratio=1.0, successor_symbol="KEEP",
                    evidence=[{"kind": "succession", "source_url": "https://sec/8k12b"}])
    frame = historical_pit.holding_series("cik:0000000002", "2015-07-01")
    info = historical_pit.exit_value(frame, "cik:0000000002", pd.Timestamp("2015-07-01"),
                                     pd.Timestamp("2015-12-31"))
    assert info["status"] == "succession_one_for_one" and info["strict"] is True
    assert info["value"] == pytest.approx(frame.iloc[-1]["adj_close"])
