import pandas as pd
import pytest

from gabi import config, entity_migration, historical_archive, identity, universe
from gabi import historical_membership as membership


def _frame(rows):
    return pd.DataFrame(rows, columns=["date", "tickers"])


def test_intervals_record_exit_reentry_and_source_boundary():
    rows = membership.intervals(_frame([
        ("2010-01-04", "AAA,BBB"),
        ("2010-03-01", "BBB,CCC"),
        ("2010-06-01", "AAA,CCC"),
    ]), "2011-01-01")
    assert [row for row in rows if row["symbol"] == "AAA"] == [
        {"symbol": "AAA", "valid_from": "2010-01-04", "valid_to": "2010-03-01", "end_reason": "exit"},
        {"symbol": "AAA", "valid_from": "2010-06-01", "valid_to": "2011-01-01",
         "end_reason": "source_boundary"},
    ]
    assert [row for row in rows if row["symbol"] == "BBB"][0]["valid_to"] == "2010-06-01"


def test_constituents_by_date_disclose_source_conflicts_and_resolved_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(universe, "HISTORICAL_MEMBERSHIP_CACHE", tmp_path / "members.csv")
    _frame([("2010-01-04", "AAA,BBB"), ("2010-03-01", "BBB,CCC"),
            ("2010-06-01", "AAA,CCC")]).to_csv(universe.HISTORICAL_MEMBERSHIP_CACHE, index=False)
    historical_archive.register_source(membership.REFERENCE_SOURCE,
                                       {"start": "2010-01-04", "end_exclusive": "2011-01-01"})
    historical_archive.import_membership(membership.REFERENCE_SOURCE,
                                         _frame([("2010-01-04", "AAA,DDD")]),
                                         "2010-01-04", "2011-01-01")
    entity_id = identity.ensure_entity("123")
    identity.add_alias(entity_id, "AAA", "2010-01-04", "2010-03-01",
                       source="reviewed_document", confidence=1)

    first = membership.constituents_as_of("2010-01-04")
    assert first["source_date"] == "2010-01-04"
    assert first["source_end_exclusive"] == "2010-06-02"
    assert first["comparison"]["status"] == "conflict"
    assert first["comparison"]["primary_only"] == ["BBB"]
    assert first["comparison"]["reference_only"] == ["DDD"]
    aaa = next(row for row in first["members"] if row["symbol"] == "AAA")
    assert aaa["entity_id"] == entity_id
    assert aaa["cik"] == "0000000123"
    assert aaa["valid_to"] == "2010-03-01"

    at_exit = membership.constituents_as_of("2010-03-01")
    assert "AAA" not in at_exit["symbols"]
    at_reentry = membership.constituents_as_of("2010-06-01")
    aaa = next(row for row in at_reentry["members"] if row["symbol"] == "AAA")
    assert aaa["entity_id"] is None
    assert aaa["identity_status"] == "unresolved"
    assert aaa["valid_from"] == "2010-06-01"
    assert aaa["end_reason"] == "source_boundary"
    with pytest.raises(ValueError, match="outside"):
        membership.constituents_as_of("2010-06-02")


def test_no_cache_no_network_and_no_implicit_reference_promotion(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(universe, "HISTORICAL_MEMBERSHIP_CACHE", tmp_path / "missing.csv")
    monkeypatch.setattr(universe, "get_historical_membership",
                        lambda: (_ for _ in ()).throw(AssertionError("network-capable loader used")))
    with pytest.raises(ValueError, match="not available locally"):
        membership.constituents_as_of("2010-01-04")


def test_conflicting_duplicate_snapshot_is_rejected():
    with pytest.raises(ValueError, match="Conflicting"):
        membership.intervals(_frame([("2010-01-04", "AAA"), ("2010-01-04", "BBB")]), "2011-01-01")


def test_equivalent_duplicate_snapshot_is_deduplicated():
    rows = membership.intervals(_frame([("2010-01-04", "BF.B,AAA"),
                                        ("2010-01-04", "AAA,BF-B")]), "2011-01-01")
    assert [row["symbol"] for row in rows] == ["AAA", "BF-B"]


def test_conflicting_day_creates_unknown_gap_until_next_clean_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(universe, "HISTORICAL_MEMBERSHIP_CACHE", tmp_path / "members.csv")
    _frame([("2010-01-04", "AAA"), ("2010-02-01", "AAA"),
            ("2010-02-01", "BBB"), ("2010-03-01", "BBB")]).to_csv(
                universe.HISTORICAL_MEMBERSHIP_CACHE, index=False)
    before = membership.constituents_as_of("2010-01-31", compare_reference=False)
    assert before["members"][0]["end_reason"] == "source_gap"
    assert before["members"][0]["valid_to"] == "2010-02-01"
    with pytest.raises(ValueError, match="Conflicting"):
        membership.constituents_as_of("2010-02-01", compare_reference=False)
    with pytest.raises(ValueError, match="outside"):
        membership.constituents_as_of("2010-02-02", compare_reference=False)
    after = membership.constituents_as_of("2010-03-01", compare_reference=False)
    assert after["symbols"] == ["BBB"]


def test_sec_filing_resolves_only_filing_day_without_activating_legacy_alias(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(universe, "HISTORICAL_MEMBERSHIP_CACHE", tmp_path / "members.csv")
    _frame([("2010-01-04", "AAA"), ("2010-06-01", "AAA,BBB")]).to_csv(
        universe.HISTORICAL_MEMBERSHIP_CACHE, index=False)
    historical_archive.import_filing_identity_evidence([{
        "symbol": "AAA", "cik": "123", "historical_name": "Old Name Inc",
        "sha256": "a" * 64, "accession": "0000000123-10-000001", "filed_date": "2010-05-01",
        "source_url": "https://www.sec.gov/Archives/edgar/data/123/x/a.xml",
    }])
    on_day = membership.constituents_as_of("2010-05-01", compare_reference=False)["members"][0]
    assert on_day["identity_status"] == "resolved"
    assert on_day["cik"] == "0000000123"
    assert on_day["historical_name"] == "Old Name Inc"
    assert membership.constituents_as_of("2010-05-02", compare_reference=False)["members"][0]["identity_status"] == "unresolved"
    assert identity.resolve("AAA", "2010-05-01")["status"] == "unresolved"


def test_reviewed_wlp_ticker_correction_has_explicit_change_boundary(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(universe, "HISTORICAL_MEMBERSHIP_CACHE", tmp_path / "members.csv")
    _frame([("2009-12-01", "ANTM,AAA"), ("2014-12-03", "ANTM,AAA")]).to_csv(
        universe.HISTORICAL_MEMBERSHIP_CACHE, index=False)
    entity_migration.activate_reviewed_symbol("WLP")
    before = membership.constituents_as_of("2010-06-30", compare_reference=False)
    wlp = next(row for row in before["members"] if row["symbol"] == "WLP")
    assert wlp["valid_from"] == "2009-12-01"
    assert wlp["valid_to"] == "2014-12-03"
    assert wlp["end_reason"] == "ticker_change"
    assert wlp["cik"] == "0001156039"
    after = membership.constituents_as_of("2014-12-03", compare_reference=False)
    antm = next(row for row in after["members"] if row["symbol"] == "ANTM")
    assert antm["valid_from"] == "2014-12-03"
