import hashlib

import pandas as pd
import pytest

from gabi import config, historical_archive, historical_membership, identity, sec_history, storage
from gabi import historical_identity_audit as audit
from gabi.historical_membership import REFERENCE_SOURCE


@pytest.fixture(autouse=True)
def offline_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr("requests.sessions.Session.request",
                        lambda *args, **kwargs: pytest.fail("No network allowed"))


def _instance(path, cik="1", symbol="AAA", name="Original Corp"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '<xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" '
        'xmlns:dei="http://xbrl.sec.gov/dei/2014-01-31">'
        f'<xbrli:context><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">{cik}'
        '</xbrli:identifier></xbrli:entity></xbrli:context>'
        f'<dei:TradingSymbol>{symbol}</dei:TradingSymbol>'
        f'<dei:EntityRegistrantName>{name}</dei:EntityRegistrantName></xbrl>', encoding="utf-8")


def test_sec_instance_requires_matching_issuer_and_unambiguous_ticker(tmp_path):
    path = tmp_path / "filing.xml"
    _instance(path, cik="1", symbol="BRK.B")
    proof = audit.extract_sec_instance(path, cik="0000000001")
    assert proof["symbol"] == "BRK-B"
    assert proof["historical_name"] == "Original Corp"
    assert proof["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="CIK mismatch"):
        audit.extract_sec_instance(path, cik="2")
    _instance(path, symbol="AAA,BBB")
    with pytest.raises(ValueError, match="Missing or ambiguous"):
        audit.extract_sec_instance(path, cik="1")


def test_filing_evidence_is_idempotent_dated_and_does_not_activate_aliases():
    base = {"symbol": "REC", "historical_name": "Original Corp", "sha256": "a" * 64,
            "accession": "0000000001-14-000001", "filed_date": "2014-05-01",
            "source_url": "https://www.sec.gov/Archives/edgar/data/1/000000000114000001/x.xml"}
    old = {**base, "cik": "0000000001"}
    new = {**base, "cik": "0000000002", "accession": "0000000002-15-000001",
           "filed_date": "2015-05-01", "source_url": "https://www.sec.gov/Archives/edgar/data/2/000000000215000001/y.xml"}
    for _ in range(2):
        assert historical_archive.import_filing_identity_evidence([old, new]) == 2
    assert historical_archive.get_filing_identity_evidence("REC", "2014-05-01")["cik"] == "0000000001"
    assert historical_archive.get_filing_identity_evidence("REC", "2015-05-01")["cik"] == "0000000002"
    assert historical_archive.get_filing_identity_evidence("REC", "2014-05-02")["status"] == "unresolved"
    assert identity.resolve("REC", "2014-05-01")["status"] == "unresolved"
    with storage.get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM entity_observations WHERE dataset='filing_identity'").fetchone()[0] == 2


def test_same_day_conflicting_sec_evidence_is_ambiguous():
    rows = [{"symbol": "REC", "cik": cik, "historical_name": "Different Corp",
             "sha256": "a" * 64, "accession": f"{cik}-14-000001", "filed_date": "2014-05-01",
             "source_url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/x/y.xml"}
            for cik in ("0000000001", "0000000002")]
    historical_archive.import_filing_identity_evidence(rows)
    result = historical_archive.get_filing_identity_evidence("REC", "2014-05-01")
    assert result["status"] == "ambiguous"
    assert result["entity_id"] is None


def test_ticker_and_name_change_keep_cik_while_index_reentry_is_separate():
    rows = [
        {"symbol": "OLD", "cik": "1", "historical_name": "Original Corp", "sha256": "a" * 64,
         "accession": "0000000001-12-000001", "filed_date": "2012-05-01",
         "source_url": "https://www.sec.gov/Archives/edgar/data/1/old.xml"},
        {"symbol": "NEW", "cik": "1", "historical_name": "Renamed Corp", "sha256": "b" * 64,
         "accession": "0000000001-14-000001", "filed_date": "2014-05-01",
         "source_url": "https://www.sec.gov/Archives/edgar/data/1/new.xml"},
    ]
    historical_archive.import_filing_identity_evidence(rows)
    old = historical_archive.get_filing_identity_evidence("OLD", "2012-05-01")
    new = historical_archive.get_filing_identity_evidence("NEW", "2014-05-01")
    assert old["entity_id"] == new["entity_id"] == "cik:0000000001"
    assert old["evidence"][0]["historical_name"] == "Original Corp"
    assert new["evidence"][0]["historical_name"] == "Renamed Corp"
    periods = historical_membership.intervals(pd.DataFrame([
        ("2012-01-01", "OLD"), ("2012-06-01", "AAA"), ("2013-01-01", "OLD,AAA"),
    ], columns=["date", "tickers"]), "2014-01-01")
    assert [(row["valid_from"], row["valid_to"]) for row in periods if row["symbol"] == "OLD"] == [
        ("2012-01-01", "2012-06-01"), ("2013-01-01", "2014-01-01")]


def test_candidate_dates_and_recycling_do_not_auto_resolve():
    rows = [("REC", "1", "Original", "2010-01-01", "2012-01-01", "2010-01-01"),
            ("REC", "2", "New", "2013-01-01", None, "2014-01-01")]
    assert audit._candidate_map(rows, "2011-01-01")["REC"]["cik"] == "0000000001"
    assert "REC" not in audit._candidate_map(rows, "2012-06-01")
    assert audit._candidate_map(rows, "2013-06-01")["REC"]["cik"] == "0000000002"
    assert not audit._candidate_map(rows, "2013-06-01")["REC"]["row_created_by_date"]
    assert identity.resolve("REC", "2013-06-01")["status"] == "unresolved"


def test_local_scan_keeps_sec_vs_community_cik_conflict_visible(tmp_path):
    accn = "0000000001-14-000001"
    path = tmp_path / "history_refresh" / "validation_1996_2015" / "instances" / f"{accn}.xml"
    _instance(path, cik="1", symbol="REC")
    historical_archive.register_source(REFERENCE_SOURCE, {"start": "2010-01-01", "end_exclusive": "2016-01-01"})
    historical_archive.import_membership(REFERENCE_SOURCE,
                                         pd.DataFrame([("2010-01-01", "REC")], columns=["date", "tickers"]),
                                         "2010-01-01", "2016-01-01")
    with storage.get_connection() as conn:
        conn.executescript(sec_history.SCHEMA)
        conn.execute("INSERT INTO sec_bulk_submissions (accn,cik,filed_date,instance) VALUES (?,?,?,?)",
                     (accn, "0000000001", "2014-05-01", "original.xml"))
        conn.execute("INSERT INTO historical_issuer_candidates VALUES (?,?,?,?,?,?,?)",
                     (audit.CANDIDATE_SOURCE, "REC", "0000000002", "Other Corp",
                      "2010-01-01", None, "2010-01-01"))
        conn.commit()
    records, summary = audit.scan_local_sec_instances()
    assert summary["ticker_proofs"] == 1
    assert summary["candidate_crosscheck"]["conflicts"] == 1
    assert records[0]["member_in_fja"]
    assert records[0]["source_url"].endswith("/original.xml")
