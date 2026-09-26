"""#34: the accredited layer per period; 2010-2015 identifiers stay frozen."""

import json

import pandas as pd
import pytest

from gabi import config, historical_archive, historical_membership, historical_period, historical_pit, storage, universe
from gabi.historical_price_audit import continued_price_symbols
from gabi.historical_price_policy import ADJUSTED, YAHOO_SOURCE, record_series
from gabi.historical_ticker_corrections import identity_nominations

P2010, P2016 = historical_period.P2010, historical_period.P2016


def test_2010_2015_identifiers_are_the_ones_cited_by_the_frozen_validation():
    assert P2010.membership_source == historical_membership.REFERENCE_SOURCE
    assert P2010.identity_source == historical_archive.IDENTITY_INTERVAL_SOURCE == "sec-identity-evidence:2010-2015:v1"
    assert P2010.price_producer == "historical_price_audit:v2"
    assert (P2010.start, P2010.end_exclusive, P2010.series_end) == ("2010-01-01", "2016-01-01", "2016-06-30")
    assert not P2010.price_symbol_fallback


def test_periods_do_not_share_sources_and_have_quarterly_rebalances():
    assert len({P2010.identity_source, P2016.identity_source}) == 2
    assert len({P2010.price_producer, P2016.price_producer}) == 2
    assert P2016.membership_source != P2010.membership_source
    assert P2016.quarters[0] == "2016-03-31" and P2016.quarters[-1] == "2025-12-31" and len(P2016.quarters) == 40
    assert P2010.last_day == "2015-12-31" and P2016.last_day == "2025-12-31"
    assert historical_period.for_date("2015-12-31") is P2010
    assert historical_period.for_date("2016-01-04") is P2016
    assert historical_period.for_date("2026-01-02") is None
    with pytest.raises(ValueError):
        historical_period.get("2030-2035")


def test_nomination_ledgers_load_together_without_overlaps():
    rows = identity_nominations()
    assert {row["label"] for row in rows if row["valid_from"] >= "2016-01-01"} >= {"BHGE", "KDP", "DIS", "XOM"}
    # AVGO changes CIK inside 2016-2025: consecutive, never overlapping.
    avgo = sorted((row["valid_from"], row["valid_to"], row["cik"]) for row in rows if row["label"] == "AVGO")
    assert all(left[1] <= right[0] for left, right in zip(avgo, avgo[1:]))
    assert len(avgo) == 3 and [row[2] for row in avgo][-1] == "0001649338"


def test_producer_pattern_of_one_period_never_matches_the_other():
    other = json.dumps([{"kind": "source", "producer": P2016.price_producer}], sort_keys=True)
    assert f'"producer": "{P2010.price_producer}"' not in other
    assert f'"producer": "{P2016.price_producer}"' in other


def test_price_symbol_follows_the_issuer_only_when_the_label_is_no_longer_its_ticker():
    life = {"current_tickers": ["META"]}
    complete = {("yahoo", "META"), ("finsaber", "FB")}
    result = continued_price_symbols("FB", {"yahoo": "FB", "finsaber": "FB", "tiingo": "FB"}, life,
                                     lambda name, symbol: (name, symbol) in complete)
    assert result == {"yahoo": "META", "finsaber": "FB", "tiingo": "FB"}
    # The label is still one of the CIK's tickers: keep it.
    assert continued_price_symbols("GOOGL", {"yahoo": "GOOGL"}, {"current_tickers": ["GOOGL", "GOOG"]},
                                   lambda *_: True) == {"yahoo": "GOOGL"}
    # A reviewed nomination (symbol differs from the label) wins.
    assert continued_price_symbols("IR", {"yahoo": "TT"}, {"current_tickers": ["XYZ"]},
                                   lambda *_: True) == {"yahoo": "TT"}
    # No SEC tickers (delisted issuer): nothing to follow.
    assert continued_price_symbols("GONE", {"yahoo": "GONE"}, None, lambda *_: False) == {"yahoo": "GONE"}


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr("requests.sessions.Session.request",
                        lambda *args, **kwargs: pytest.fail("No network allowed"))
    storage.init_db()
    frame = pd.DataFrame([("2012-01-03", "OLD,KEEP"), ("2017-01-03", "KEEP,NEW")], columns=["date", "tickers"])
    historical_archive.register_source(P2010.membership_source, {"start": "2010-01-01", "end_exclusive": "2016-01-01"})
    historical_archive.import_membership(P2010.membership_source, frame, "2010-01-01", "2016-01-01")
    historical_archive.register_source(P2016.membership_source, {"start": "2010-01-01", "end_exclusive": "2020-01-01"})
    historical_archive.import_membership(P2016.membership_source, frame, "2010-01-01", "2020-01-01")
    historical_archive.replace_identity_intervals(P2010.identity_source, [
        {"symbol": "KEEP", "cik": "2", "valid_from": "2012-01-03", "valid_to": "2016-01-01",
         "status": "confirmed_by_multiple_evidence", "evidence_count": 2}])
    historical_archive.replace_identity_intervals(P2016.identity_source, [
        {"symbol": "KEEP", "cik": "2", "valid_from": "2016-01-01", "valid_to": "2020-01-01",
         "status": "confirmed_by_multiple_evidence", "evidence_count": 2},
        {"symbol": "NEW", "cik": "3", "valid_from": "2017-01-03", "valid_to": "2020-01-01",
         "status": "confirmed_historical_ticker", "evidence_count": 2}])


def test_2016_2025_layer_is_used_only_when_activated(db):
    assert historical_pit.active_periods() == ("2010-2015",)
    assert not historical_pit.covers("2018-06-29")
    with historical_pit.accredited_periods("2010-2015", "2016-2025"):
        assert historical_pit.covers("2018-06-29") and historical_pit.covers("2012-06-29")
        info = historical_pit.universe("2018-06-29")
        assert info["symbols"] == ["KEEP", "NEW"] and info["identity_accredited"] == 2
        assert info["source_id"] == P2016.membership_source and "2016-2025" in info["note"]
        assert historical_pit.resolve("NEW", "2018-06-29")["entity_id"] == "cik:0000000003"
        # The 2010-2015 identity source knows nothing about 2018.
        assert historical_pit.resolve("KEEP", "2012-06-29")["entity_id"] == "cik:0000000002"
        assert universe.get_sp500_constituents_asof("2018-06-29")["source_id"] == P2016.membership_source
    assert historical_pit.active_periods() == ("2010-2015",)
    assert not historical_pit.covers("2018-06-29")


def test_same_source_may_overlap_only_across_period_producers(db):
    dates = pd.bdate_range("2015-06-01", periods=200)
    values = pd.Series([100 + i * 0.2 for i in range(len(dates))], index=dates)
    storage.upsert_prices("KEEP", pd.DataFrame({"Open": values, "High": values, "Low": values, "Close": values,
                                                "Adj Close": values, "Volume": 100.}, index=dates))

    def refs(producer):
        return [{"kind": "identity", "source_url": "https://www.sec.gov/identity"},
                {"kind": "source", "source_url": "https://finance.yahoo.com", "producer": producer}]

    day = [d.date().isoformat() for d in dates]
    record_series(cik="2", symbol="KEEP", valid_from=day[0], valid_to=day[150], source_id=YAHOO_SOURCE,
                  adjustment_basis=ADJUSTED, status="tier_a", evidence=refs(P2010.price_producer))
    # The 2016-2025 audit accredits a trailing window over the same Yahoo rows.
    record_series(cik="2", symbol="KEEP", valid_from=day[50], valid_to=day[199], source_id=YAHOO_SOURCE,
                  adjustment_basis=ADJUSTED, status="tier_a", evidence=refs(P2016.price_producer))
    # Within one producer an overlap is still a stale interval.
    with pytest.raises(ValueError, match="Overlapping accredited"):
        record_series(cik="2", symbol="KEEP", valid_from=day[100], valid_to=day[180], source_id=YAHOO_SOURCE,
                      adjustment_basis=ADJUSTED, status="tier_a", evidence=refs(P2016.price_producer))


def test_2010_2015_price_audit_keeps_its_evidence_horizon(monkeypatch):
    from gabi import historical_issuer_evidence as evidence
    rows = [{"accn": "a", "start": None, "end": end, "val": 1.0, "frame": frame, "source_url": "u"}
            for end, frame in (("2016-06-30", "CY2016Q2I"), ("2017-06-30", "CY2017Q2I"))]
    monkeypatch.setattr(evidence, "load_frames", lambda: {"0000000001": {"public_float": rows}})
    assert len(evidence.issuer_facts("1")["public_float"]) == 2
    assert [row["end"] for row in evidence.issuer_facts("1", P2010.frame_year_max)["public_float"]] == ["2016-06-30"]
    assert P2010.archive_until("finsaber") == "2015-12-31" and P2016.archive_until("finsaber") == P2016.series_end
    assert P2010.life_horizon == ("2016-01-01", 2016) and P2016.frame_year_max is None
