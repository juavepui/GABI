"""Captured identity parity, read-only historical boundaries and atomic writes."""

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from gabi import config, historical_pit, identity, storage
from gabi.application.market.identity import last_filings
from gabi.infrastructure.storage.historical_pit import SqliteHistoricalPit
from gabi.infrastructure.storage.identity import SqliteIdentityReads
from gabi.infrastructure.storage.identity_writes import SqliteIdentityWrites, ensure_schema, put_observations

REFERENCE = json.loads((Path(__file__).parent / "fixtures/identity_migration.json").read_text(encoding="utf-8"))


def captured(name="identity"):
    namespace = {"__name__": f"gabi._captured_{name}", "__package__": "gabi"}
    exec(REFERENCE[name], namespace)
    return namespace


def seed(path):
    writer = SqliteIdentityWrites(path, lambda: date(2020, 1, 1), lambda: "fixed")
    first, second = writer.ensure_entity("1"), writer.ensure_entity("2")
    for owner, symbol, start, end, confidence in (
        (first, "OLD", "2016-01-01", "2020-01-01", 1.),
        (first, "NEW", "2020-01-01", None, 1.),
        (second, "OLD", "2021-01-01", None, 1.),
        (first, "AMB", "2016-01-01", None, 1.),
        (second, "AMB", "2016-01-01", None, .2),
        (first, "LOW", "2016-01-01", None, .5),
        (first, "CLASS-A", "2016-01-01", None, 1.),
        (first, "CLASS-B", "2016-01-01", None, 1.),
    ):
        writer.add_alias(owner, symbol, start, end, source="reviewed:é", confidence=confidence)
    with closing(sqlite3.connect(path)) as db:
        prices = [{"date": day, "close": value, "adj_close": value / 2} for day, value in
                  (("2015-01-01", 5), ("2019-01-01", 10), ("2020-01-01", 15), ("2021-01-01", 20))]
        put_observations(db, first, "prices", "NEW", prices, "fixture")
        for symbol, filed, accn in (("OLD", "2022-02-01", "duplicate"), ("NEW", "2019-02-01", "duplicate")):
            # Deliberate legacy duplicates: last_filings must consider both,
            # independently of the SEC facts reader's deduplication policy.
            payload = {"tag": "Revenues", "unit": "USD", "start_date": "2018-01-01", "end_date": "2018-12-31",
                       "val": 10, "form": "10-K", "fp": "FY", "fy": 2018, "filed_date": filed, "accn": accn}
            db.execute("INSERT INTO entity_observations VALUES (?,?,?,?,?,?)",
                       (first, "edgar_facts", symbol, accn, json.dumps(payload), "fixture"))
        db.execute("CREATE TABLE edgar_facts(symbol TEXT,filed_date TEXT)")
        db.executemany("INSERT INTO edgar_facts VALUES (?,?)", [(symbol, "2019-03-01") for symbol in ("RAW", "AMB", "LOW", "OLD")])
        db.commit()
    return first


@pytest.mark.parametrize("day", ["2016-01-01", "2019-06-01", "2020-01-01", "2021-06-01", "2023-01-01"])
def test_core_queries_match_captured_implementation(tmp_path, monkeypatch, day):
    path = tmp_path / "gabi.db"
    owner = seed(path)
    monkeypatch.setattr(config, "DB_PATH", path)
    old = captured()
    symbols = ["OLD", "NEW", "AMB", "LOW", "CLASS-A", "CLASS-B", "RAW", " old ", "UNKNOWN"]
    reader = SqliteIdentityReads(path)
    for symbol in symbols:
        assert identity.resolve(symbol, day) == old["resolve"](symbol, day)
        assert identity.has_aliases(symbol) == old["has_aliases"](symbol)
        assert_frame_equal(identity.price_history(symbol, day), old["price_history"](symbol, day))
        assert identity.price_download_symbol(symbol, day, today="2024-01-01") == old["price_download_symbol"](symbol, day, today="2024-01-01")
    for dataset in ("prices", "edgar_facts", "sector"):
        assert_frame_equal(identity.observations(owner, dataset), old["observations"](owner, dataset))
    assert last_filings(reader, symbols, day) == old["last_filings"](symbols, day)
    assert identity.attributed_fingerprint() == old["attributed_fingerprint"]()


def test_queries_never_initialize_missing_storage_or_use_legacy_connections(tmp_path, monkeypatch):
    path = tmp_path / "absent/gabi.db"
    monkeypatch.setattr(config, "DB_PATH", path)
    monkeypatch.setattr(storage, "get_connection", lambda: pytest.fail("legacy SQL query"))
    monkeypatch.setattr("requests.sessions.Session.request", lambda *a, **k: pytest.fail("network"))
    assert identity.resolve("UNKNOWN", "2019-01-01")["entity_id"] is None
    assert identity.resolve("UNKNOWN", "2012-01-01")["entity_id"] is None
    assert identity.price_history("UNKNOWN", "2019-01-01").empty
    assert identity.observations("cik:0000000001", "prices").empty
    assert identity.last_filings(["UNKNOWN"], "2019-01-01") == {}
    assert not identity.has_aliases("UNKNOWN")
    assert identity.price_download_symbol("UNKNOWN", "2019-01-01", today="2024-01-01") is None
    empty = {name: [] for name in ("entities", "entity_aliases", "entity_observations", "entity_candidates")}
    assert identity.attributed_fingerprint() == hashlib.sha256(json.dumps(empty, sort_keys=True).encode()).hexdigest()
    assert historical_pit.resolve("UNKNOWN", "2012-01-01")["entity_id"] is None
    assert historical_pit.ranking_series("cik:0000000001", "2012-01-01").empty
    assert historical_pit.holding_series("cik:0000000001", "2012-01-01").empty
    assert historical_pit.terminal_event("cik:0000000001", "2012-01-01", "2013-01-01") is None
    assert not path.parent.exists()


def test_facade_queries_preserve_database_and_observe_alias_corrections(tmp_path, monkeypatch):
    path = tmp_path / "gabi.db"
    owner = seed(path)
    monkeypatch.setattr(config, "DB_PATH", path)
    monkeypatch.setattr(storage, "get_connection", lambda: pytest.fail("legacy SQL query"))
    statements = []
    actual = sqlite3.connect
    def traced(*args, **kwargs):
        db = actual(*args, **kwargs)
        db.set_trace_callback(statements.append)
        return db
    monkeypatch.setattr(sqlite3, "connect", traced)
    before = path.read_bytes()
    assert identity.resolve("OLD", "2019-06-01")["entity_id"] == owner
    assert identity.last_filings(["OLD", "LOW", "AMB", "RAW"], "2019-12-31") == {"OLD": "2019-02-01", "RAW": "2019-03-01"}
    assert not identity.price_history("OLD", "2019-06-01").empty
    identity.attributed_fingerprint()
    assert path.read_bytes() == before
    assert not any(sql.lstrip().upper().startswith(("CREATE", "INSERT", "UPDATE", "DELETE")) for sql in statements)
    with closing(actual(path)) as db:
        db.execute("UPDATE entity_aliases SET valid_to='2019-01-01' WHERE symbol='OLD' AND entity_id=?", (owner,))
        db.commit()
    assert identity.resolve("OLD", "2019-06-01")["entity_id"] is None


def test_atomic_dual_write_and_explicit_clock_and_identifiers(tmp_path):
    path = tmp_path / "gabi.db"
    writer = SqliteIdentityWrites(path, lambda: date(2001, 2, 3), lambda: "fixed-local")
    owner = writer.ensure_entity(name="Local")
    assert owner == "local:fixed-local"
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT created_at FROM entities").fetchone() == ("2001-02-03",)
        db.execute("CREATE TABLE marker(value)")
        db.commit()
        with pytest.raises(RuntimeError):
            with db:
                db.execute("INSERT INTO marker VALUES (1)")
                ensure_schema(db)
                put_observations(db, owner, "prices", "A", [{"date": "2001-01-01", "close": float("nan")}], "source")
                raise RuntimeError("rollback")
        assert db.execute("SELECT COUNT(*) FROM marker").fetchone() == (0,)
        assert db.execute("SELECT COUNT(*) FROM entity_observations").fetchone() == (0,)


def test_fingerprint_preserves_canonical_hash_for_large_unicode_payloads(tmp_path, monkeypatch):
    path = tmp_path / "gabi.db"
    owner = seed(path)
    monkeypatch.setattr(config, "DB_PATH", path)
    with closing(sqlite3.connect(path)) as db:
        put_observations(db, owner, "fundamentals", "NEW",
                         [{"fetched_at": "2020-01-01", "info": "é" * 70000, "missing": None}], "fixture:é")
        db.commit()
    assert identity.attributed_fingerprint() == captured()["attributed_fingerprint"]()


def test_accredited_series_source_priority_windows_splits_and_exits_match_reference(tmp_path, monkeypatch):
    from gabi import historical_archive
    from gabi.domain.research.historical_pit import YAHOO_SOURCE
    from gabi.historical_price_policy import SCHEMA

    path = tmp_path / "gabi.db"
    monkeypatch.setattr(config, "DB_PATH", path)
    owner = "cik:0000000001"
    with closing(sqlite3.connect(path)) as db:
        db.executescript(storage.SCHEMA + historical_archive.SCHEMA + SCHEMA)
        for source, producer in ((YAHOO_SOURCE, None), ("archive", None), ("inactive", "another-audit")):
            evidence = [{"kind": "source", "producer": producer},
                        {"kind": "accredited_windows", "windows": [{"as_of": "2012-03-31", "holding_until": "2012-07-07"}]}]
            db.execute("INSERT INTO historical_price_provenance VALUES (?,?,?,?,?,?,?,?,?)",
                       (owner, "0000000001", "A", "2011-01-01", "2013-01-01", source,
                        "split_and_dividend_adjusted", "tier_a", json.dumps(evidence)))
        for day in pd.bdate_range("2011-01-03", "2012-05-15"):
            day = day.date().isoformat()
            db.execute("INSERT INTO prices(symbol,date,close,adj_close) VALUES (?,?,?,?)", ("A", day, 10., 5.))
            db.execute("INSERT INTO historical_prices VALUES (?,?,?,?,?,?,?,?,?,?)",
                       ("archive", "A", day, 20., 20., 20., 20., 10., 1., "as_traded"))
        db.execute("INSERT INTO splits VALUES (?,?,?)", ("A", "2013-01-01", 4.))
        db.execute("INSERT INTO historical_terminal_events VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                   (owner, "A", "2012-05-16", "cash_acquisition", "terminal_return_confirmed", 12., None, None, None, None, "[]"))
        db.commit()
    old = captured("historical_pit")
    assert historical_pit._intervals(owner) == old["_intervals"](owner)
    for day in ("2012-03-31", "2012-05-01", "2012-06-30", "2012-07-02"):
        for name in ("ranking_series", "holding_series"):
            actual, expected = getattr(historical_pit, name)(owner, day), old[name](owner, day)
            assert_frame_equal(actual, expected)
            assert actual.attrs == expected.attrs
    frame = historical_pit.holding_series(owner, "2012-04-02")
    assert frame.attrs["source_id"] == YAHOO_SOURCE
    assert historical_pit.as_traded_close(frame, "2012-04-02") == old["as_traded_close"](frame, "2012-04-02") == 40.
    for exit_day in ("2012-04-03", "2012-07-02"):
        args = frame, owner, pd.Timestamp("2012-04-02"), pd.Timestamp(exit_day)
        assert historical_pit.exit_value(*args) == old["exit_value"](*args)
    # The migrated historical path is independent of all legacy SQL connections.
    monkeypatch.setattr(storage, "get_connection", lambda: pytest.fail("legacy SQL query"))
    assert not historical_pit.ranking_series(owner, "2012-05-01").empty
    assert historical_pit.exit_value(frame, owner, pd.Timestamp("2012-04-02"), pd.Timestamp("2012-07-02"))["strict"]


@pytest.mark.parametrize("limit", [{"max_rows": 1}, {"max_bytes": 1}, {"max_field_bytes": 1}])
def test_identity_and_historical_reads_reject_overflow(tmp_path, limit):
    path = tmp_path / "gabi.db"
    owner = seed(path)
    reader = SqliteIdentityReads(path, **limit)
    with pytest.raises(ValueError, match="límite"):
        reader.observations(owner, "prices")
    from gabi.historical_price_policy import SCHEMA
    with closing(sqlite3.connect(path)) as db:
        db.executescript(SCHEMA)
        for source in ("first", "second"):
            db.execute("INSERT INTO historical_price_provenance VALUES (?,?,?,?,?,?,?,?,?)",
                       (owner, "0000000001", "A", "2010-01-01", "2013-01-01", source,
                        "split_and_dividend_adjusted", "tier_a", "[]"))
        db.commit()
    with pytest.raises(ValueError, match="límite"):
        SqliteHistoricalPit(path, **limit).provenance(owner)
