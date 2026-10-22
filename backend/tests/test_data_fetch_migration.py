"""The Yahoo download flows moved out of the flat data_fetch (F7.30), against its captured source."""

import ast
import json
import sqlite3
import time
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pandas as pd
import pytest
import yfinance
from test_operational_sources_migration import FakeTicker, yahoo_panel

from gabi import config, identity, storage
from gabi.infrastructure.legacy import data_fetch
from gabi.infrastructure.storage import sync_events as event_store

REFERENCE = json.loads((Path(__file__).parent / "fixtures/data_fetch_migration.json").read_text(encoding="utf-8"))
NOW = datetime(2026, 1, 9, 22, tzinfo=UTC)


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz else NOW.replace(tzinfo=None)


def captured() -> ModuleType:
    module = ModuleType("gabi.data_fetch")
    module.__package__ = "gabi"
    exec(compile(REFERENCE["data_fetch"], "captured_data_fetch.py", "exec"), module.__dict__)
    module.datetime = FixedDatetime
    return module


def captured_refresh_data(old_data_fetch, edgar) -> object:
    source = REFERENCE["screener_refresh_data"]
    node = next(n for n in ast.parse(source).body if getattr(n, "name", "") == "refresh_data")
    namespace = {"data_fetch": old_data_fetch, "edgar": edgar}
    exec(ast.get_source_segment(source, node), namespace)
    return namespace["refresh_data"]


def dump(path: Path) -> dict:
    """Every table's rows; autoincrement ids are dropped because the fundamentals pool finishes in any order."""
    with closing(sqlite3.connect(path)) as db:
        tables = sorted(n for n, in db.execute("SELECT name FROM sqlite_schema WHERE type='table'"))
        result = {}
        for table in tables:
            cursor = db.execute(f"SELECT * FROM {table}")
            skip = 1 if cursor.description and cursor.description[0][0] == "id" else 0
            result[table] = sorted(repr(row[skip:]) for row in cursor.fetchall())
        return result


@pytest.fixture
def market(monkeypatch):
    calls = []

    def download(tickers, **options):
        calls.append(("download", tuple(tickers), options.get("period")))
        if "MISS" in tickers and len(tickers) == 1:
            raise ValueError("No data found, symbol may be delisted")
        return yahoo_panel([t for t in tickers if t != "MISS"] or ["X"])

    monkeypatch.setattr(yfinance, "download", download)
    monkeypatch.setattr(yfinance, "Ticker", FakeTicker)
    monkeypatch.setattr(identity, "resolve", lambda symbol, day: {"entity_id": None})
    monkeypatch.setattr(event_store, "datetime", FixedDatetime)
    monkeypatch.setattr(data_fetch, "datetime", FixedDatetime)
    # Parity with the capture; the extra checklist fields (#167) are tested separately.
    monkeypatch.setattr(data_fetch, "EXTRA_INFO_KEYS", [])
    monkeypatch.setattr(time, "perf_counter", lambda: 2.)
    monkeypatch.setattr(time, "thread_time", lambda: 1.)
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    return calls


def use(root: Path, monkeypatch) -> Path:
    root.mkdir(parents=True)
    monkeypatch.setattr(config, "DATA_DIR", root)
    monkeypatch.setattr(config, "DB_PATH", root / "gabi.db")
    storage.init_db()
    return root / "gabi.db"


def test_universe_data_and_refresh_match_capture(tmp_path, monkeypatch, market):
    results = []
    for label in ("old", "new"):
        path = use(tmp_path / label, monkeypatch)
        market.clear()
        target = captured() if label == "old" else data_fetch
        edgar = SimpleNamespace(ensure_edgar_data=lambda symbols, **k: {"failed": {"AAA": "sin SEC"},
                                                                         "edgar_refreshed": len(symbols) - 1})
        refresh = captured_refresh_data(target, edgar) if label == "old" else data_fetch.refresh_data
        outcomes = [refresh(["AAA", "EMPTY", "AAA"], sec_sync=edgar.ensure_edgar_data),
                    target.ensure_universe_data(["AAA", "EMPTY"]),
                    target.ensure_universe_data(["AAA"], force=True, max_age_hours=1)]
        results.append((json.dumps(outcomes, sort_keys=True, default=str), dump(path), list(market)))
    assert results[0] == results[1]
    first = json.loads(results[1][0])[0]
    assert first["failed"]["EMPTY"]["fundamentales"] and first["failed"]["AAA"]["edgar"] == "sin SEC"


@pytest.mark.parametrize("as_of", ["2026-01-07", "2025-06-30"])
def test_price_history_as_of_matches_capture(tmp_path, monkeypatch, market, as_of):
    histories = {"OLD": pd.DataFrame({"adj_close": [1.0]}, index=pd.to_datetime(["2025-01-02"])),
                 "EMPTY": pd.DataFrame(columns=["adj_close"])}
    monkeypatch.setattr(identity, "price_history", lambda symbol, day, **k: histories.get(symbol, pd.DataFrame(
        columns=["adj_close"])))
    monkeypatch.setattr(identity, "price_download_symbol",
                        lambda symbol, day, **k: {"AAA": "AAA", "MISS": "MISS"}.get(symbol))
    results = []
    for label in ("old", "new"):
        path = use(tmp_path / label, monkeypatch)
        market.clear()
        target = captured() if label == "old" else data_fetch
        progress = []
        outcome = target.ensure_price_history_asof(["OLD", "AAA", "MISS", "EMPTY", config.BENCHMARK_SYMBOL], as_of,
                                                   progress_cb=lambda *args: progress.append(args))
        results.append((outcome, progress, dump(path), list(market)))
    assert results[0] == results[1]
    assert results[1][0]["failed"]["EMPTY"].startswith("Sin identidad temporal")


def test_decision_prices_match_capture(tmp_path, monkeypatch, market):
    results = []
    for label in ("old", "new"):
        path = use(tmp_path / label, monkeypatch)
        market.clear()
        target = captured() if label == "old" else data_fetch
        outcome = [target.ensure_decision_prices(["AAA", "MISS", "AAA"]), target.ensure_decision_prices(["AAA"])]
        results.append((outcome, dump(path), list(market)))
    assert results[0] == results[1]


def test_bridge_keeps_the_names_its_callers_and_scripts_use():
    for name in ("sync_prices", "normalize_symbol", "_classify_error", "fetch_prices_batch", "fetch_splits_batch",
                 "ensure_price_history_asof", "ensure_decision_prices", "fetch_fundamentals_one",
                 "fetch_fundamentals_batch", "ensure_universe_data", "refresh_data", "RETRYABLE_CATEGORIES"):
        assert hasattr(data_fetch, name), name
