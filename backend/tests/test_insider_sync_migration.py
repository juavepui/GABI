"""Original sync outcome, SEC policy, SQL parity and explicit clocks/directories."""

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from gabi.application.market.insider_sync import InsiderAttempt, fetch_transactions, sync_insiders
from gabi.infrastructure.providers.form4 import SecForm4Documents
from gabi.infrastructure.storage.insiders import SCHEMA, SqliteInsiders

REFERENCE = json.loads((Path(__file__).parent / "fixtures/insider_sync_migration.json").read_text(encoding="utf-8"))
NOW = datetime.fromisoformat(REFERENCE["now"])


class Source:
    def __init__(self):
        self.calls = []

    def mapping(self):
        return {"AAA": "0000000001", "BAD": "0000000002"}

    def resolve(self, symbol, mapping):
        return mapping.get(symbol)

    def attempts(self, ciks, max_workers):
        assert max_workers == 4
        for symbol, cik in ciks.items():
            self.calls.append([symbol, cik])
            yield InsiderAttempt(symbol, rows=REFERENCE["rows"] if symbol == "AAA" else None,
                                 error=RuntimeError("synthetic") if symbol == "BAD" else None)


def test_complete_sync_matches_original_sql_and_result(tmp_path):
    store = SqliteInsiders(tmp_path, now=lambda: NOW)
    with closing(sqlite3.connect(store.path)) as db:
        db.executescript(SCHEMA)
        db.executemany("INSERT INTO insider_fetch_meta VALUES (?,?)", [
            ("FRESH", (NOW - timedelta(hours=24)).isoformat()), ("FUTURE", (NOW + timedelta(days=1)).isoformat())])
        db.commit()
    source, progress = Source(), []
    result = sync_insiders(REFERENCE["symbols"], source, store, lambda exc: "fallo sintético", now=lambda: NOW,
                           max_age_hours=0, progress_cb=lambda *values: progress.append(values))
    assert result == REFERENCE["result"]
    assert source.calls == REFERENCE["calls"]
    assert progress == [(1, 3, "AAA"), (2, 3, "BAD")]
    with closing(sqlite3.connect(store.path)) as db:
        db.row_factory = sqlite3.Row
        assert [dict(row) for row in db.execute("SELECT * FROM insider_transactions ORDER BY symbol,accn,line_no")] == REFERENCE["records"]
        assert [list(row) for row in db.execute("SELECT * FROM insider_fetch_meta ORDER BY symbol")] == REFERENCE["meta"]
        assert dict(db.execute("SELECT symbol,reason FROM update_errors")) == REFERENCE["result"]["failed"]
    # A repeat keeps the same transaction key and timestamp, without duplicating rows.
    store.save("AAA", REFERENCE["rows"])
    assert len(store.transactions("AAA")) == 1


def test_metadata_reads_never_initialize_or_write(tmp_path):
    store = SqliteInsiders(tmp_path)
    assert store.fetched_at(["AAA"]) == {}
    assert store.transactions("AAA").empty
    assert not store.path.exists()
    with closing(sqlite3.connect(store.path)) as db:
        db.execute("CREATE TABLE other(value TEXT)")
        db.commit()
    before = store.path.read_bytes()
    assert store.fetched_at(["AAA"]) == {}
    assert store.transactions("AAA").empty
    assert store.path.read_bytes() == before


def test_metadata_batches_and_malformed_dates(tmp_path):
    store = SqliteInsiders(tmp_path)
    symbols = [f"S{i}" for i in range(1_201)]
    with closing(sqlite3.connect(store.path)) as db:
        db.executescript(SCHEMA)
        db.executemany("INSERT INTO insider_fetch_meta VALUES (?,?)", [(symbol, NOW.isoformat()) for symbol in symbols])
        db.execute("UPDATE insider_fetch_meta SET fetched_at='invalid' WHERE symbol='S600'")
        db.commit()
    before = store.path.read_bytes()
    result = store.fetched_at(symbols)
    assert len(result) == len(symbols)
    assert result["S600"] is None and result["S1200"] == NOW
    assert store.path.read_bytes() == before


def test_empty_filings_are_successfully_recorded_and_errors_are_pruned(tmp_path):
    store = SqliteInsiders(tmp_path, now=lambda: NOW)
    store.save("EMPTY", [])
    assert store.fetched_at(["EMPTY"])["EMPTY"] == NOW
    assert store.transactions("EMPTY").empty
    store.errors({"OLD": "old"})
    with closing(sqlite3.connect(store.path)) as db:
        db.execute("UPDATE update_errors SET occurred_at=?", ((NOW - timedelta(days=91)).isoformat(),))
        db.commit()
    store.errors({"AAA": "new"})
    with closing(sqlite3.connect(store.path)) as db:
        assert db.execute("SELECT symbol,reason FROM update_errors").fetchall() == [("AAA", "new")]


def test_mapping_failure_and_write_failure_preserve_error_policy(tmp_path):
    class BrokenSource(Source):
        def mapping(self):
            raise RuntimeError("unavailable")

    store = SqliteInsiders(tmp_path, now=lambda: NOW)
    result = sync_insiders(["AAA", "AAA", "BAD"], BrokenSource(), store, lambda exc: str(exc), now=lambda: NOW)
    assert result == {"refreshed": 0, "failed": {"AAA": "unavailable", "BAD": "unavailable"}}

    class BrokenStore(SqliteInsiders):
        def save(self, symbol, rows):
            raise RuntimeError("cannot write")

    result = sync_insiders(["AAA"], Source(), BrokenStore(tmp_path, now=lambda: NOW), lambda exc: str(exc), now=lambda: NOW)
    assert result == {"refreshed": 0, "failed": {"AAA": "cannot write"}}


def test_form4_limit_counts_failed_filings_and_skips_derivatives():
    from test_insider import SAMPLE_XML_BUY

    calls = []

    class Documents:
        def submissions(self, cik):
            return {"filings": {"recent": {"form": ["10-K", "4", "4", "4"],
                     "accessionNumber": ["skip", "a-1", "a-2", "a-3"],
                     "primaryDocument": ["skip", "xslF345X06/bad.xml", "xslF345X06/good.xml", "skip"],
                     "filingDate": ["skip", "2024-01-01", "2024-01-02"]}}}

        def xml(self, url):
            calls.append(url)
            return "broken" if url.endswith("bad.xml") else SAMPLE_XML_BUY

    rows = fetch_transactions("AAA", "0000000001", Documents(), limit_filings=2)
    assert calls == ["https://www.sec.gov/Archives/edgar/data/1/a1/bad.xml",
                     "https://www.sec.gov/Archives/edgar/data/1/a2/good.xml"]
    assert len(rows) == 1 and rows[0]["accn"] == "a-2" and rows[0]["filed_date"] == "2024-01-02"
    assert rows[0]["symbol"] == "AAA" and rows[0]["transaction_code"] == "P"


def test_http_user_agent_and_timeouts_are_explicit(monkeypatch):
    import requests

    calls = []

    class Response:
        status_code = 200
        text = "<xml/>"

        def json(self):
            return {"filings": {}}

        def raise_for_status(self):
            pass

    def request(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr(requests, "get", request)
    source = SecForm4Documents("test contact")
    assert source.submissions("0000000001") == {"filings": {}}
    assert source.xml("https://www.sec.gov/example.xml") == "<xml/>"
    assert [params for _, params in calls] == [
        {"headers": {"User-Agent": "test contact"}, "timeout": 30},
        {"headers": {"User-Agent": "test contact"}, "timeout": 20}]
    Response.status_code = 404
    with pytest.raises(ValueError, match="historial"):
        source.submissions("0000000001")


def test_legacy_entry_point_delegates_to_the_same_case(monkeypatch):
    from gabi import insider

    calls = []

    def run(symbols, source, store, classify_error, **options):
        calls.append((symbols, options))
        assert source.resolve("AAA", {"AAA": "1"}) == "1"
        return {"refreshed": 0, "failed": {}}

    monkeypatch.setattr(insider, "sync_insiders", run)
    monkeypatch.setattr(insider.edgar, "get_cik_for_symbol", lambda symbol, cik_map: (cik_map[symbol], None))
    assert insider.ensure_insider_data(["AAA"], max_age_hours=0) == {"refreshed": 0, "failed": {}}
    assert calls[0][0] == ["AAA"] and calls[0][1]["max_age_hours"] == 0
    assert callable(calls[0][1]["now"])


def test_cli_bootstrap_supplies_directory_clock_and_sources(tmp_path, monkeypatch):
    from gabi.infrastructure.legacy.insiders import SecInsiders
    from gabi.infrastructure.settings import Settings
    from gabi_cli.bootstrap import build_executor

    monkeypatch.setattr(SecInsiders, "mapping", lambda self: {"AAA": "0000000001"})
    monkeypatch.setattr(SecInsiders, "resolve", lambda self, symbol, mapping: mapping.get(symbol))
    monkeypatch.setattr(SecInsiders, "attempts", lambda self, ciks, workers: [InsiderAttempt("AAA", rows=REFERENCE["rows"])])
    executor = build_executor(Settings(tmp_path), now=lambda: NOW)
    assert executor.insider_sync is not None
    assert executor.insider_sync(["AAA"]) == {"refreshed": 1, "failed": {}}
    assert SqliteInsiders(tmp_path).fetched_at(["AAA"]) == {"AAA": NOW}
