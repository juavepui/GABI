import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gabi import (
    config,
    data_quality,
    edgar,
    entity_master,
    entity_migration,
    identity,
    multifactor_backtest,
    screener_asof,
    storage,
)


@pytest.fixture(autouse=True)
def offline_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")

    def no_network(*args, **kwargs):
        pytest.fail("Identity operations must be offline")

    monkeypatch.setattr("requests.sessions.Session.request", no_network)
    monkeypatch.setattr("socket.create_connection", no_network)


def _prices(day, price):
    return pd.DataFrame({c: [price] for c in ["Open", "High", "Low", "Close", "Adj Close", "Volume"]},
                        index=pd.to_datetime([day]))


def _fact(value, accn="test"):
    return {"tag": "Revenues", "unit": "USD", "start_date": "2018-01-01", "end_date": "2018-12-31",
            "val": value, "form": "10-K", "fp": "FY", "fy": 2018, "filed_date": "2019-02-01", "accn": accn}


def _alias(cik, symbol, start="2010-01-01", end=None):
    entity = identity.ensure_entity(cik)
    identity.add_alias(entity, symbol, start, end, source="test:dated-evidence")
    return entity


def test_real_fb_meta_and_antm_elv_change_with_exclusive_boundary():
    entity_migration.migrate()
    assert identity.resolve("FB", "2022-06-08")["entity_id"] == identity.resolve("META", "2022-06-09")["entity_id"]
    assert identity.resolve("FB", "2022-06-09")["status"] == "unresolved"
    assert identity.resolve("ANTM", "2022-06-27")["entity_id"] == identity.resolve("ELV", "2022-06-28")["entity_id"]


def test_recycled_symbol_has_two_entities_and_no_legacy_contamination():
    old = _alias("1", "REC", end="2020-01-01")
    new = _alias("2", "REC", start="2021-01-01")
    storage.upsert_prices("REC", _prices("2019-06-01", 10), entity_id=old)
    # The provider returns a historical date under today's reused ticker.
    storage.upsert_prices("REC", _prices("2019-06-01", 999), entity_id=new)
    assert identity.resolve("REC", "2019-06-01")["entity_id"] == old
    assert identity.resolve("REC", "2021-06-01")["entity_id"] == new
    assert identity.price_history("REC", "2019-06-01")["close"].iloc[0] == 10
    assert identity.price_history("REC", "2021-06-01").empty
    assert storage.get_prices("REC")["close"].iloc[0] == 999  # old API preserved


def test_delisted_entity_does_not_extend_into_new_listing():
    entity = _alias("1", "OLD", end="2020-01-01")
    storage.upsert_prices("OLD", _prices("2021-01-01", 50), entity_id=entity)
    assert identity.price_history("OLD", "2019-01-01").empty
    assert identity.resolve("OLD", "2021-01-01")["entity_id"] is None


def test_conflicting_aliases_fail_closed_and_diagnose_ambiguity():
    _alias("1", "REC")
    _alias("2", "REC", start="2020-01-01")
    resolved = identity.resolve("REC", "2021-01-01")
    assert resolved["status"] == "ambiguous"
    assert resolved["entity_id"] is None
    assert len(resolved["candidates"]) == 2
    assert identity.diagnostics(["REC"], "2021-01-01").iloc[0]["status"] == "ambiguous"


def test_local_entity_without_cik_is_persistent_and_not_name_merged():
    first = identity.ensure_entity(name="Same Name")
    second = identity.ensure_entity(name="Same Name")
    assert first != second
    assert identity.ensure_entity(name="Same Name", entity_id=first) == first
    identity.add_alias(first, "LOCAL", "2020-01-01", source="reviewed:listing")
    resolved = identity.resolve("LOCAL", "2021-01-01")
    assert resolved["entity_id"] == first and resolved["cik"] is None


def test_facts_survive_ticker_recycling_and_are_shared_across_aliases():
    first = _alias("1", "OLD", end="2020-01-01")
    _alias("1", "NEW", start="2020-01-01")
    _alias("2", "OLD", start="2021-01-01")
    edgar.upsert_edgar_facts("OLD", [_fact(10)], cik="1")
    edgar.upsert_edgar_facts("OLD", [_fact(999)], cik="2")
    assert edgar.get_value_as_of("NEW", ["Revenues"], "2020-06-01", entity_id=first) == 10
    assert edgar.get_edgar_facts("OLD")["val"].iloc[0] == 999


def test_sector_follows_entity_across_ticker_changes_without_recycling():
    entity = _alias("1", "OLD", end="2020-01-01")
    _alias("1", "NEW", start="2020-01-01")
    _alias("2", "OLD", start="2021-01-01")
    with storage.get_connection() as conn:
        identity.put_observations(conn, entity, "sector", "OLD", [{
            "effective_date": "2018-01-01", "sector": "Tech", "cik": "0000000001",
            "name": "Original", "industry": "Software"}], "test:filing")
        conn.commit()
    assert entity_master.get_sector_asof(["NEW"], "2020-06-01")["NEW"]["sector"] == "Tech"
    assert entity_master.get_sector_asof(["OLD"], "2021-06-01")["OLD"]["sector"] is None


def test_name_fallback_is_candidate_only_even_when_unique():
    matched = identity.import_submissions_candidates("OLD", "Original Inc.", {
        "cik": "1", "name": "Renamed Inc", "formerNames": [{"name": "Original Inc."}],
    }, source="https://data.sec.gov/submissions/CIK0000000001.json")
    assert matched
    assert identity.resolve("OLD", "2019-01-01")["status"] == "unresolved"
    identity.import_filing_identity("OLD", "1", "2019-02-01", source="test:10-k-cover")
    assert identity.resolve("OLD", "2019-02-01")["status"] == "resolved"
    assert identity.resolve("OLD", "2019-02-02")["status"] == "unresolved"


def test_migration_is_idempotent_and_does_not_assign_legacy_prices():
    storage.upsert_prices("FB", _prices("2019-01-01", 10))
    entity_migration.migrate()
    before = identity.attributed_fingerprint()
    entity_migration.migrate()
    assert identity.attributed_fingerprint() == before
    assert identity.price_history("FB", "2019-01-01").empty
    assert len(storage.get_prices("FB")) == 1
    entity_migration.attribute_legacy("FB", "cik:0001326801", "prices", source="test:verified-owner")
    assert identity.price_history("FB", "2019-01-01")["close"].iloc[0] == 10


def test_historical_ranking_excludes_unattributed_legacy_data():
    storage.upsert_prices("REC", _prices("2019-01-01", 100))
    edgar.upsert_edgar_facts("REC", [_fact(999)])
    result = screener_asof.build_ranking_as_of("2019-06-01", symbols=["REC"])["table"]
    assert result.loc["REC", "identity_status"] == "unresolved"
    assert pd.isna(result.loc["REC", "composite_score"])


def test_same_cik_share_classes_are_not_spliced():
    entity = _alias("1", "CLASS-A")
    _alias("1", "CLASS-B")
    storage.upsert_prices("CLASS-B", _prices("2019-01-01", 999), entity_id=entity)
    assert identity.price_history("CLASS-A", "2019-06-01").empty


def test_renamed_ticker_can_use_attributed_successor_full_history():
    entity = _alias("1", "OLD", end="2020-01-01")
    _alias("1", "NEW", start="2020-01-01")
    storage.upsert_prices("NEW", _prices("2019-01-01", 10), entity_id=entity)
    assert identity.price_history("OLD", "2019-06-01")["close"].iloc[0] == 10


def test_report_distinguishes_lexical_and_date_verified_coverage():
    history = pd.DataFrame([{"date": "2019-01-01", "tickers": "FB,UNKNOWN"}])
    current = pd.DataFrame({"symbol": ["META"]})
    assert entity_migration.coverage_report(history, current)["before_unmapped_pct"] == 100
    entity_migration.migrate()
    report = entity_migration.coverage_report(history, current)
    assert report["after_unmapped_pct"] == 50
    assert report["verified_symbol_date_pairs"] == 1
    assert report["recovered_symbols"] == ["FB"]


def test_period_return_cannot_cross_into_recycled_ticker():
    old = _alias("1", "REC", end="2024-02-01")
    new = _alias("2", "REC", start="2024-02-01")
    storage.upsert_prices("REC", _prices("2024-01-08", 10), entity_id=old)
    storage.upsert_prices("REC", _prices("2024-02-05", 100), entity_id=new)
    storage.upsert_prices("SPY", pd.concat([_prices("2024-01-08", 100), _prices("2024-02-05", 100)]))
    with pytest.raises(ValueError, match="Faltan precios"):
        multifactor_backtest._period_returns(["REC"], pd.Timestamp("2024-01-05"), 1, 0)


def test_fact_correction_under_new_alias_replaces_old_alias_copy():
    entity = _alias("1", "OLD", end="2020-01-01")
    _alias("1", "NEW", start="2020-01-01")
    edgar.upsert_edgar_facts("OLD", [_fact(10)], cik="1")
    edgar.upsert_edgar_facts("NEW", [_fact(20)], cik="1")
    assert len(identity.observations(entity, "edgar_facts")) == 1
    assert edgar.get_value_as_of("OLD", ["Revenues"], "2019-06-01", entity_id=entity) == 20


def test_invalid_owner_rolls_back_legacy_and_attributed_writes():
    with pytest.raises(ValueError, match="Unknown entity"):
        storage.upsert_prices("AAA", _prices("2019-01-01", 10), entity_id="missing")
    assert storage.get_prices("AAA").empty


def test_data_fingerprint_tracks_alias_changes():
    entity = identity.ensure_entity("1")
    before = data_quality.compute_data_fingerprint(["OLD"])
    identity.add_alias(entity, "OLD", "2010-01-01", source="test:filing")
    assert before != data_quality.compute_data_fingerprint(["OLD"])


def test_current_cik_is_not_historical_fallback(monkeypatch):
    monkeypatch.setattr(edgar, "get_cik_map", lambda: pytest.fail("Historical lookup must not use today's map"))
    result = edgar.ensure_edgar_data(["REC"], as_of="2019-01-01")
    assert "REC" in result["failed"]


def test_download_uses_successor_not_recycled_symbol():
    _alias("1", "OLD", end="2020-01-01")
    _alias("1", "NEW", start="2020-01-01")
    _alias("2", "OLD", start="2021-01-01")
    assert identity.price_download_symbol("OLD", "2019-01-01", today="2024-01-01") == "NEW"
    assert identity.price_download_symbol("OLD", "2022-01-01", today="2024-01-01") == "OLD"


def test_backdated_snapshot_does_not_certify_todays_cik(monkeypatch):
    monkeypatch.setattr(edgar, "get_cik_map", lambda: pytest.fail("No current-map lookup for a historical snapshot"))
    entity_master.record_snapshot(pd.DataFrame([{"symbol": "OLD", "name": "New owner", "sector": "Tech"}]),
                                  effective_date="2019-01-01")
    assert identity.resolve("OLD", "2019-01-01")["entity_id"] is None


def test_missing_snapshot_fields_are_stored_as_null():
    entity = _alias("1", "AAA")
    with storage.get_connection() as conn:
        identity.put_observations(conn, entity, "sector", "AAA", [{
            "effective_date": "2019-01-01", "sector": float("nan"), "name": pd.NA,
        }], "test:missing-values")
        conn.commit()
    frame = identity.observations(entity, "sector")
    assert pd.isna(frame.iloc[0]["sector"])
    assert pd.isna(frame.iloc[0]["name"])
