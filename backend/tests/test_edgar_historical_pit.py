import pytest

from gabi import config, edgar, historical_archive, identity, storage


@pytest.fixture(autouse=True)
def offline_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr("requests.sessions.Session.request",
                        lambda *args, **kwargs: pytest.fail("No network allowed"))


def _row(tag, end, value, filed, accn, *, start="", unit="USD"):
    return {"tag": tag, "unit": unit, "start_date": start, "end_date": end,
            "val": value, "form": "10-K", "fp": "FY", "fy": int(end[:4]),
            "filed_date": filed, "accn": accn}


def test_issuer_facts_as_of_keeps_versions_and_exact_source_without_ticker_alias():
    original = _row("Revenues", "2011-12-31", 100, "2012-02-01", "first", start="2011-01-01")
    restated = _row("Revenues", "2011-12-31", 110, "2013-02-01", "later", start="2011-01-01")
    historical_archive.import_sec_facts("bulk", "OLD", "1", [original], source_url="https://www.sec.gov/first.xml")
    historical_archive.import_sec_facts("bulk", "OLD", "1", [restated], source_url="https://www.sec.gov/later.xml")
    assert edgar.get_issuer_facts_as_of("1", "2012-01-01").empty
    before = edgar.get_issuer_facts_as_of("1", "2012-06-01")
    assert before[["val", "source_url"]].to_dict("records") == [
        {"val": 100, "source_url": "https://www.sec.gov/first.xml"}]
    after = edgar.get_issuer_facts_as_of("1", "2013-06-01")
    assert after.val.tolist() == [100, 110]
    assert edgar.get_issuer_facts_as_of("1", "2013-06-01", tags=["NetIncomeLoss"]).empty
    assert identity.resolve("OLD", "2012-06-01")["status"] == "unresolved"
    with storage.get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM entity_aliases").fetchone()[0] == 0


def test_annual_alias_bridge_requires_matching_overlap_and_contiguous_periods():
    def annual(values):
        return {"units": {"USD": [dict(start=f"{year}-01-01", end=f"{year}-12-31",
                                       val=value, form="10-K", fp="FY", filed=f"{year+1}-02-01",
                                       accn=str(year)) for year, value in values.items()]}}

    facts = {"facts": {"us-gaap": {
        "RevenueFromContractWithCustomerExcludingAssessedTax": annual({2017: 120, 2018: 130, 2019: 140}),
        "Revenues": annual({2016: 100, 2017: 120, 2018: 130}),
    }}}
    assert edgar._extract_annual_values(facts, edgar.REVENUE_TAGS) == [
        ("2016-12-31", 100), ("2017-12-31", 120), ("2018-12-31", 130), ("2019-12-31", 140)]
    assert edgar.compute_edgar_metrics(facts)["revenue_cagr_3y"] == pytest.approx((140 / 100) ** (1 / 3) - 1)
    facts["facts"]["us-gaap"]["Revenues"] = annual({2016: 100, 2017: 999, 2018: 130})
    assert edgar.compute_edgar_metrics(facts)["revenue_cagr_3y"] is None


def test_missing_year_cannot_turn_decade_gap_into_three_year_cagr():
    series = [("2008-12-31", 10), ("2016-12-31", 100), ("2017-12-31", 110), ("2018-12-31", 121)]
    assert edgar._cagr_from_series(series, 3) is None
    assert edgar._yoy_growth({"2016-12-31": 100, "2018-12-31": 121}) is None


def test_later_restatement_never_reaches_earlier_cutoff():
    rows = [_row("Revenues", "2011-12-31", 100, "2012-02-01", "a", start="2011-01-01"),
            {**_row("Revenues", "2011-12-31", 200, "2014-02-01", "b", start="2011-01-01"),
             "form": "10-K/A"}]
    edgar.upsert_edgar_facts("OLD", rows, cik="1")
    before = edgar.compute_edgar_metrics_as_of("OLD", "2013-12-31", entity_id="cik:0000000001")
    after = edgar.compute_edgar_metrics_as_of("OLD", "2014-12-31", entity_id="cik:0000000001")
    assert before["latest_revenue"] == 100
    assert after["latest_revenue"] == 200


def test_identity_evidence_as_of_reports_two_filings_and_future_recycling_without_alias():
    records = [
        {"symbol": "OLD", "cik": cik, "historical_name": "Issuer", "sha256": "a" * 64,
         "accession": f"{cik}-{year}-000001", "filed_date": f"{year}-03-01",
         "source_url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{year}/x.xml"}
        for cik, year in [("1", 2011), ("1", 2012), ("2", 2014)]]
    historical_archive.import_filing_identity_evidence(records)
    assert historical_archive.list_filing_identity_evidence_as_of("OLD", "2010-12-31")["status"] == "no_evidence"
    before = historical_archive.list_filing_identity_evidence_as_of("OLD", "2012-12-31")
    assert before["status"] == "observed"
    assert len(before["evidence"]) == 2
    after = historical_archive.list_filing_identity_evidence_as_of("OLD", "2014-12-31")
    assert after["status"] == "conflicting_ciks"
    assert after["ciks"] == ["0000000001", "0000000002"]
    assert identity.resolve("OLD", "2012-12-31")["status"] == "unresolved"
