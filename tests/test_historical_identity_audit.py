import hashlib
import json

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


def test_early_sec_dei_namespace_is_accepted(tmp_path):
    path = tmp_path / "filing.xml"
    _instance(path, symbol="AAA")
    path.write_text(path.read_text(encoding="utf-8").replace(
        "http://xbrl.sec.gov/dei/2014-01-31", "http://xbrl.us/dei/2009-01-31"), encoding="utf-8")
    assert audit.extract_sec_instance(path, cik="1")["symbol"] == "AAA"


@pytest.mark.parametrize(("candidate", "sec_name", "expected"), [
    ("D. R. Horton", "HORTON D R INC /DE/", True),
    ("Abercrombie & Fitch Company A", "ABERCROMBIE & FITCH CO /DE/", True),
    ("Harman Int'l Industries", "HARMAN INTERNATIONAL INDUSTRIES INC", True),
    ("IBM", "INTERNATIONAL BUSINESS MACHINES CORP", True),
    ("BNY Mellon", "BANK OF NEW YORK MELLON CORP", True),
    ("Meta", "Meta Platforms, Inc.", True),
    ("Andeavor", "TESORO CORP", False),
    ("Chubb Limited", "ACE LTD", False),
    ("American Airlines", "AMERICAN ELECTRIC POWER CO", False),
])
def test_conservative_historical_name_normalization(candidate, sec_name, expected):
    assert audit._name_matches(candidate, sec_name) is expected


def test_sec_sub_index_name_is_used_when_dei_name_is_absent(tmp_path):
    accn = "0000000001-14-000002"
    path = tmp_path / "history_refresh" / "validation_1996_2015" / "instances" / f"{accn}.xml"
    _instance(path, name="")
    historical_archive.register_source(REFERENCE_SOURCE, {"start": "2010-01-01", "end_exclusive": "2016-01-01"})
    historical_archive.import_membership(REFERENCE_SOURCE,
                                         pd.DataFrame([("2010-01-01", "AAA")], columns=["date", "tickers"]),
                                         "2010-01-01", "2016-01-01")
    with storage.get_connection() as conn:
        conn.executescript(sec_history.SCHEMA)
        conn.execute("INSERT INTO sec_bulk_submissions (accn,cik,filed_date,instance,name) VALUES (?,?,?,?,?)",
                     (accn, "0000000001", "2014-05-01", "a.xml", "ALPHA CORPORATION"))
        conn.commit()
    rows, summary = audit.scan_local_sec_instances()
    assert summary["historical_names"] == 1
    assert rows[0]["historical_name"] == "ALPHA CORPORATION"
    assert rows[0]["historical_name_source"] == "sec_sub_index"


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


def test_multiple_sec_filings_corroborrate_bounded_interval_without_alias():
    historical_archive.register_source(REFERENCE_SOURCE, {"start": "2010-01-01", "end_exclusive": "2016-01-01"})
    historical_archive.import_membership(REFERENCE_SOURCE, pd.DataFrame([
        ("2010-01-01", "AAA,ACT"), ("2012-01-01", "ACT"),
        ("2013-01-01", "AAA,ACT"), ("2015-01-01", "AAA,ACT"),
    ], columns=["date", "tickers"]), "2010-01-01", "2016-01-01")
    with storage.get_connection() as conn:
        conn.executemany("INSERT INTO historical_issuer_candidates VALUES (?,?,?,?,?,?,?)", [
            (audit.CANDIDATE_SOURCE, "AAA", "0000000001", "Alpha Corp", "2010-01-01", None, "2020-01-01"),
            (audit.CANDIDATE_SOURCE, "ACT", "0000000002", "Action Inc", "2010-01-01", None, "2020-01-01"),
        ])
        conn.commit()
    records = []
    for symbol, cik, name, dates in [
        ("AAA", "1", "Alpha Corporation", ["2010-03-01", "2011-03-01", "2013-03-01", "2014-03-01"]),
        ("ACT", "2", "Action Inc", ["2010-03-01", "2011-03-01"]),
        ("ACT", "3", "Different Corp", ["2014-03-01"]),
    ]:
        for day in dates:
            accession = f"{int(cik):010d}-{day[2:4]}-{day[5:7]}{day[8:10]}01"
            records.append({"symbol": symbol, "cik": cik, "historical_name": name,
                            "sha256": "a" * 64, "accession": accession, "filed_date": day,
                            "source_url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/x.xml"})
    historical_archive.import_filing_identity_evidence(records)
    rows = audit.build_evidence_intervals()
    by_symbol = {symbol: [row for row in rows if row["symbol"] == symbol] for symbol in ("AAA", "ACT")}
    assert [(row["valid_from"], row["valid_to"], row["status"]) for row in by_symbol["AAA"]] == [
        ("2010-01-01", "2012-01-01", "confirmed_by_multiple_evidence"),
        ("2013-01-01", "2016-01-01", "confirmed_by_multiple_evidence")]
    assert by_symbol["ACT"][0]["status"] == "ambiguous"
    assert historical_archive.replace_identity_intervals(audit.INTERVAL_SOURCE, rows) == len(rows)
    assert historical_archive.replace_identity_intervals(audit.INTERVAL_SOURCE, rows) == len(rows)
    query = historical_membership.constituents_as_of("2010-06-30", source_id=REFERENCE_SOURCE,
                                                      compare_reference=False)
    members = {row["symbol"]: row for row in query["members"]}
    assert query["accredited_symbols"] == ["AAA"]
    assert query["excluded_identity_symbols"] == ["ACT"]
    assert members["AAA"]["identity_status"] == "resolved"
    assert members["AAA"]["identity_tier"] == "confirmed_by_multiple_evidence"
    assert members["ACT"]["identity_status"] == "ambiguous"
    # #32: in 2010-2015 the accredited interval resolves the issuer for the
    # backtest, without ever creating an operational alias.
    resolved = identity.resolve("AAA", "2010-06-30")
    assert (resolved["status"], resolved["entity_id"]) == ("resolved", "cik:0000000001")
    assert identity.resolve("ACT", "2010-06-30")["status"] == "ambiguous"
    assert not identity.has_aliases("AAA")
    annual = audit.coverage_report()["by_year"]["2010"]
    assert annual["confirmed_by_multiple_evidence"] == 4
    assert annual["ambiguous_identity"] == 4
    assert annual["percent"]["accredited_total"] == 50.0
    assert all(row["symbol"] != "AAA" for row in historical_membership.constituents_as_of(
        "2012-06-30", source_id=REFERENCE_SOURCE, compare_reference=False)["members"])
    conflicting = identity.ensure_entity("9")
    identity.add_alias(conflicting, "AAA", "2010-01-01", "2012-01-01", source="reviewed-conflict")
    conflicting_query = historical_membership.constituents_as_of(
        "2010-06-30", source_id=REFERENCE_SOURCE, compare_reference=False)
    assert next(row for row in conflicting_query["members"] if row["symbol"] == "AAA")[
        "identity_status"] == "ambiguous"


def test_repeated_direct_ticker_proof_outweighs_candidate_name_but_one_filing_does_not():
    historical_archive.register_source(REFERENCE_SOURCE, {"start": "2010-01-01", "end_exclusive": "2016-01-01"})
    historical_archive.import_membership(REFERENCE_SOURCE, pd.DataFrame([
        ("2010-01-01", "AAA,BBB")], columns=["date", "tickers"]), "2010-01-01", "2016-01-01")
    with storage.get_connection() as conn:
        conn.executemany("INSERT INTO historical_issuer_candidates VALUES (?,?,?,?,?,?,?)", [
            (audit.CANDIDATE_SOURCE, "AAA", "0000000001", "Unrelated Inc", "2010-01-01", None, "2020-01-01"),
            (audit.CANDIDATE_SOURCE, "BBB", "0000000002", "Beta Corp", "2010-01-01", None, "2020-01-01"),
        ])
        conn.commit()
    historical_archive.import_filing_identity_evidence([
        {"symbol": symbol, "cik": cik, "historical_name": name,
         "sha256": "a" * 64, "accession": f"{cik}-10-{index:06d}",
         "filed_date": f"2010-0{index}-01",
         "source_url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{index}/x.xml"}
        for symbol, cik, name, indices in [
            ("AAA", "1", "Alpha Corporation", [3, 6]), ("BBB", "2", "Beta Corp", [3])]
        for index in indices])
    rows = audit.build_evidence_intervals()
    assert {row["symbol"]: row["status"] for row in rows} == {
        "AAA": "confirmed_by_multiple_evidence", "BBB": "unresolved"}


def test_recycled_ticker_is_split_by_candidate_dates():
    historical_archive.register_source(REFERENCE_SOURCE, {"start": "2010-01-01", "end_exclusive": "2016-01-01"})
    historical_archive.import_membership(REFERENCE_SOURCE, pd.DataFrame([
        ("2010-01-01", "REC")], columns=["date", "tickers"]), "2010-01-01", "2016-01-01")
    with storage.get_connection() as conn:
        conn.executemany("INSERT INTO historical_issuer_candidates VALUES (?,?,?,?,?,?,?)", [
            (audit.CANDIDATE_SOURCE, "REC", "0000000001", "Original Corp", "2010-01-01", "2012-01-01", "2020-01-01"),
            (audit.CANDIDATE_SOURCE, "REC", "0000000002", "New Corp", "2013-01-01", None, "2020-01-01"),
        ])
        conn.commit()
    historical_archive.import_filing_identity_evidence([
        {"symbol": "REC", "cik": cik, "historical_name": name, "sha256": "a" * 64,
         "accession": f"{cik}-{year}-000001", "filed_date": f"{year}-03-01",
         "source_url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{year}/x.xml"}
        for cik, name, years in [("1", "Original Corp", [2010, 2011]),
                                 ("2", "New Corp", [2013, 2014])]
        for year in years])
    rows = audit.build_evidence_intervals()
    assert [(row["cik"], row["valid_from"], row["valid_to"], row["status"]) for row in rows] == [
        ("0000000001", "2010-01-01", "2012-01-01", "confirmed_by_multiple_evidence"),
        ("0000000002", "2013-01-01", "2016-01-01", "confirmed_by_multiple_evidence")]


def test_candidate_download_selection_is_bounded_and_resumable(monkeypatch):
    historical_archive.register_source(REFERENCE_SOURCE, {"start": "2010-01-01", "end_exclusive": "2016-01-01"})
    with storage.get_connection() as conn:
        conn.execute("INSERT INTO historical_issuer_candidates VALUES (?,?,?,?,?,?,?)",
                     (audit.CANDIDATE_SOURCE, "AAA", "0000000001", "Alpha Corp",
                      "2010-01-01", None, "2020-01-01"))
        conn.executescript(sec_history.SCHEMA)
        conn.executemany("INSERT INTO sec_bulk_submissions (accn,cik,filed_date,form,instance) "
                         "VALUES (?,?,?,?,?)", [
                             (f"1-{year}-000001", "0000000001", f"{year}-02-01", "10-K", f"{year}.xml")
                             for year in (2010, 2012, 2015)])
        conn.commit()
    seen = []

    def fake_download(url, path):
        seen.append(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"cached")
        return path

    monkeypatch.setattr(audit.sec_history, "download", fake_download)
    first = audit.fetch_candidate_instances(2)
    second = audit.fetch_candidate_instances(2)
    assert first["fetched"] == 2
    assert second["fetched"] == 1
    assert len(seen) == 3
    assert audit.fetch_candidate_instances(2)["fetched"] == 0


def test_unresolved_second_pass_uses_only_bounded_non_conflicting_filings(monkeypatch):
    historical_archive.register_source(REFERENCE_SOURCE, {"start": "2010-01-01", "end_exclusive": "2016-01-01"})
    with storage.get_connection() as conn:
        conn.executescript(sec_history.SCHEMA)
        conn.execute("INSERT INTO historical_issuer_candidates VALUES (?,?,?,?,?,?,?)",
                     (audit.CANDIDATE_SOURCE, "AAA", "0000000001", "Alpha Corp",
                      "2010-01-01", None, "2020-01-01"))
        conn.executemany("INSERT INTO sec_bulk_submissions "
                         "(accn,cik,filed_date,form,instance) VALUES (?,?,?,?,?)", [
                             (f"1-201{year}-000001", "0000000001", f"201{year}-03-01", "10-K", "x.xml")
                             for year in range(5)])
        conn.commit()
    historical_archive.replace_identity_intervals(audit.INTERVAL_SOURCE, [
        {"symbol": "AAA", "cik": "1", "valid_from": "2011-01-01", "valid_to": "2014-01-01",
         "status": "unresolved", "evidence_count": 0, "source_refs": []}])
    normal = audit.fetch_candidate_instances(0)
    extra = audit.fetch_candidate_instances(0, prioritize_unresolved=True)
    assert normal["selected_filings"] == 3
    assert extra["selected_filings"] == 5
    assert extra["fetched"] == 0


def test_repeated_sec_issuer_name_is_separate_from_direct_ticker_proof():
    historical_archive.register_source(REFERENCE_SOURCE, {"start": "2010-01-01", "end_exclusive": "2016-01-01"})
    historical_archive.import_membership(REFERENCE_SOURCE, pd.DataFrame([
        ("2010-01-01", "ABB")], columns=["date", "tickers"]), "2010-01-01", "2016-01-01")
    with storage.get_connection() as conn:
        conn.executescript(sec_history.SCHEMA)
        conn.execute("INSERT INTO historical_issuer_candidates VALUES (?,?,?,?,?,?,?)",
                     (audit.CANDIDATE_SOURCE, "ABB", "0000000001", "Abbott Laboratories",
                      "2010-01-01", None, "2020-01-01"))
        conn.executemany("INSERT INTO sec_bulk_submissions "
                         "(accn,cik,filed_date,form,name,source_url) VALUES (?,?,?,?,?,?)", [
                             (f"1-{year}-000001", "0000000001", f"{year}-02-01", "10-K",
                              "ABBOTT LABORATORIES", f"https://www.sec.gov/{year}.zip")
                             for year in (2010, 2011)])
        conn.executemany("INSERT INTO sec_archive_files VALUES (?,?,?,?)", [
            (f"https://www.sec.gov/{year}.zip", "a" * 64, 100, "2026-01-01")
            for year in (2010, 2011)])
        conn.commit()
    rows = audit.build_evidence_intervals()
    assert len(rows) == 1
    assert rows[0]["status"] == "corroborated_candidate"
    assert rows[0]["direct_ticker_proofs"] == 0
    assert rows[0]["sec_issuer_filings"] == 2
    assert {ref["evidence_kind"] for ref in rows[0]["source_refs"]} == {
        "sec_bulk_issuer_name_no_ticker"}
    historical_archive.replace_identity_intervals(audit.INTERVAL_SOURCE, rows)
    result = historical_membership.constituents_as_of(
        "2010-06-30", source_id=REFERENCE_SOURCE, compare_reference=False)
    assert result["members"][0]["identity_tier"] == "corroborated_candidate"
    assert result["members"][0]["identity_confidence"] is None


def test_official_sec_rename_chain_corroborates_but_other_ticker_blocks(tmp_path):
    historical_archive.register_source(REFERENCE_SOURCE, {"start": "2010-01-01", "end_exclusive": "2016-01-01"})
    historical_archive.import_membership(REFERENCE_SOURCE, pd.DataFrame([
        ("2010-01-01", "NEW")], columns=["date", "tickers"]), "2010-01-01", "2016-01-01")
    with storage.get_connection() as conn:
        conn.executescript(sec_history.SCHEMA)
        conn.execute("INSERT INTO historical_issuer_candidates VALUES (?,?,?,?,?,?,?)",
                     (audit.CANDIDATE_SOURCE, "NEW", "0000000001", "New Holdings",
                      "2010-01-01", None, "2020-01-01"))
        conn.executemany("INSERT INTO sec_bulk_submissions "
                         "(accn,cik,filed_date,form,name,source_url) VALUES (?,?,?,?,?,?)", [
                             (f"1-{year}-000001", "0000000001", f"{year}-02-01", "10-K",
                              "OLD CORPORATION", f"https://www.sec.gov/{year}.zip")
                             for year in (2010, 2011)])
        conn.executemany("INSERT INTO sec_archive_files VALUES (?,?,?,?)", [
            (f"https://www.sec.gov/{year}.zip", "a" * 64, 100, "2026-01-01")
            for year in (2010, 2011)])
        conn.commit()
    path = (tmp_path / "history_refresh" / "validation_1996_2015" / "identity_submissions" /
            "CIK0000000001.json")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"cik": 1, "name": "New Holdings Inc", "formerNames": [
        {"name": "Old Corporation", "from": "2009-01-01", "to": "2016-01-01"}]}), encoding="utf-8")
    rows = audit.build_evidence_intervals()
    assert rows[0]["status"] == "corroborated_candidate"
    assert rows[0]["official_name_chain_match"]
    assert any(ref["evidence_kind"] == "sec_official_name_chain_no_ticker"
               for ref in rows[0]["source_refs"])
    historical_archive.import_filing_identity_evidence([
        {"symbol": "OLD", "cik": "1", "historical_name": "Old Corporation",
         "sha256": "a" * 64, "accession": "1-10-000099", "filed_date": "2010-05-01",
         "source_url": "https://www.sec.gov/Archives/edgar/data/1/2010/old.xml"}])
    blocked = audit.build_evidence_intervals()[0]
    assert blocked["status"] == "ambiguous"
    assert blocked["other_sec_tickers_same_cik"] == ["OLD"]


def _nomination(**overrides):
    return {"label": "NEWL", "cik": "0000000007", "valid_from": "2010-01-01", "valid_to": "2016-01-01",
            "sec_tickers": ("OLDT",), "evidence_window_days": 0, "reason": "retrospective_label", **overrides}


def _membership_with_candidate(symbol="NEWL", cik="0000000009"):
    historical_archive.register_source(REFERENCE_SOURCE, {"start": "2010-01-01", "end_exclusive": "2016-01-01"})
    historical_archive.import_membership(REFERENCE_SOURCE, pd.DataFrame([
        ("2010-01-01", symbol)], columns=["date", "tickers"]), "2010-01-01", "2016-01-01")
    with storage.get_connection() as conn:
        conn.execute("INSERT INTO historical_issuer_candidates VALUES (?,?,?,?,?,?,?)",
                     (audit.CANDIDATE_SOURCE, symbol, cik, "Later Holding Plc", "2010-01-01", None, "2020-01-01"))
        conn.commit()


def _proofs(rows):
    historical_archive.import_filing_identity_evidence([
        {"symbol": symbol, "cik": cik, "historical_name": "Issuer", "sha256": "a" * 64,
         "accession": f"{int(cik):010d}-{day[2:4]}-{day[5:7]}{day[8:10]}01", "filed_date": day,
         "source_url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{day}/x.xml"}
        for symbol, cik, day in rows])


def test_retroactive_label_is_confirmed_by_historical_sec_ticker(monkeypatch):
    from gabi import historical_ticker_corrections
    monkeypatch.setattr(historical_ticker_corrections, "identity_nominations", lambda: (_nomination(),))
    _membership_with_candidate()
    _proofs([("OLDT", "7", "2011-02-01"), ("OLDT", "7", "2013-02-01")])
    [row] = audit.build_evidence_intervals()
    assert (row["cik"], row["status"]) == ("0000000007", "confirmed_historical_ticker")


def test_nominated_historical_ticker_used_by_another_issuer_is_ambiguous(monkeypatch):
    from gabi import historical_ticker_corrections
    monkeypatch.setattr(historical_ticker_corrections, "identity_nominations", lambda: (_nomination(),))
    _membership_with_candidate()
    _proofs([("OLDT", "7", "2011-02-01"), ("OLDT", "7", "2013-02-01"), ("OLDT", "8", "2014-02-01")])
    assert [row["status"] for row in audit.build_evidence_intervals()] == ["ambiguous"]


def test_successor_cik_that_starts_filing_later_is_not_backdated(monkeypatch):
    _membership_with_candidate(symbol="HOLD", cik="0000000009")
    _proofs([("HOLD", "9", "2015-02-01"), ("HOLD", "9", "2015-05-01")])
    monkeypatch.setattr(audit.issuer_evidence, "listing_life",
                        lambda cik: {"first_periodic": "2014-12-31", "current_tickers": []})
    assert [row["status"] for row in audit.build_evidence_intervals()] == ["unresolved"]


def test_nominations_trim_community_rows_and_price_only_entries_leave_identity(monkeypatch):
    from gabi import historical_ticker_corrections as corrections
    community = {"NEWL": [{"cik": "0000000009", "name": "Later", "start": "2009-01-01", "end": "9999-12-31"}]}
    monkeypatch.setattr(corrections, "identity_nominations",
                        lambda: (_nomination(valid_from="2010-01-01", valid_to="2014-12-31"),))
    rows = corrections.apply_nominations(community)["NEWL"]
    assert [(row["cik"], row["start"], row["end"]) for row in rows] == [
        ("0000000009", "2009-01-01", "2010-01-01"), ("0000000009", "2014-12-31", "9999-12-31"),
        ("0000000007", "2010-01-01", "2014-12-31")]
    monkeypatch.setattr(corrections, "identity_nominations", lambda: (_nomination(price_only=True),))
    assert corrections.apply_nominations(community) == community
