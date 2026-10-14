"""Captured parity of macro, insider and data_fetch persistence after leaving the storage facade (#134).

The retired `macro`/`insider` facades are compared through the stores that replaced them."""

import ast
import json
import sqlite3
import sys
import time
from contextlib import closing, contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pandas as pd
import pytest
import yfinance

from gabi import config, identity, storage
from gabi.infrastructure.legacy import data_fetch
from gabi.infrastructure.storage.fred import SqliteFred
from gabi.infrastructure.storage.insiders import SqliteInsiders

REFERENCE = json.loads((Path(__file__).parent / "fixtures/operational_sources_migration.json").read_text(encoding="utf-8"))
NOW = datetime(2026, 2, 3, 15, tzinfo=UTC)


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz else NOW.replace(tzinfo=None)


def connection(path: Path):
    @contextmanager
    def get_connection():
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path, timeout=30)) as db:
            db.execute("PRAGMA journal_mode=WAL")
            yield db
    return get_connection


def legacy_storage(path: Path) -> SimpleNamespace:
    namespace = {"get_connection": connection(path), "datetime": FixedDatetime, "UTC": UTC, "timedelta": timedelta}
    for node in ast.parse(REFERENCE["storage"]).body:
        if isinstance(node, ast.FunctionDef) and node.name == "record_update_errors" or isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id in {"SCHEMA", "UPDATE_ERRORS_RETENTION_DAYS"} for t in node.targets):
            exec(ast.get_source_segment(REFERENCE["storage"], node), namespace)
    return SimpleNamespace(**namespace)


def legacy_module(name: str, **names) -> ModuleType:
    module = ModuleType(f"captured_{name}")
    module.__package__ = "gabi"  # lazy relative imports inside functions resolve to the real package
    source = REFERENCE[name]
    for line in ("from . import config, storage\n", "from . import config, edgar, storage\n",
                 "from . import config, identity, storage\n"):
        source = source.replace(line, "")
    module.__dict__.update(names)
    exec(compile(source, f"captured_{name}.py", "exec"), module.__dict__)
    return module


def dump(path: Path) -> dict:
    if not path.exists():
        return {}
    with closing(sqlite3.connect(path)) as db:
        tables = sorted(n for n, in db.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name<>'sqlite_sequence'"))
        return {t: sorted(map(repr, db.execute(f"SELECT * FROM {t}").fetchall())) for t in tables}


@pytest.fixture(autouse=True)
def retired_data_fetch(monkeypatch):
    """The captured modules imported the flat data_fetch retired in F7.30; the bridge keeps its names."""
    monkeypatch.setitem(sys.modules, "gabi.data_fetch", data_fetch)


@pytest.fixture
def clock(monkeypatch):
    from gabi.infrastructure.storage import sync_events
    for module in (data_fetch, sync_events):
        monkeypatch.setattr(module, "datetime", FixedDatetime)
    monkeypatch.setattr(time, "perf_counter", lambda: 3.)
    monkeypatch.setattr(time, "thread_time", lambda: 1.)
    monkeypatch.setattr(time, "sleep", lambda seconds: None)


def test_macro_series_match_capture(tmp_path, monkeypatch, clock):
    results = []
    for label in ("old", "new"):
        path = tmp_path / label / "gabi.db"
        monkeypatch.setattr(config, "DB_PATH", path)
        if label == "old":
            target = legacy_module("macro", storage=legacy_storage(path), config=config)
            target.datetime = FixedDatetime
        else:
            series = SqliteFred(path, lambda: NOW)
            target = SimpleNamespace(get_series_history=series.history, get_all_fetched_at=series.fetched_at_all,
                                     upsert_series=series.upsert)
        outcomes = [target.get_series_history("DGS10"), target.get_all_fetched_at()]
        target.upsert_series("DGS10", [("2026-01-02", 4.1), ("2026-01-05", None), ("2026-01-03", 4.2)])
        target.upsert_series("DGS10", [("2026-01-05", 4.3)])
        target.upsert_series("CPIAUCSL", [])
        outcomes += [target.get_series_history("DGS10"), target.get_series_history("CPIAUCSL"),
                     target.get_series_history("NONE"), target.get_all_fetched_at()]
        results.append(([o.to_dict("split") if isinstance(o, pd.DataFrame) else o for o in outcomes], dump(path)))
    assert results[0] == results[1]


def form4(i, symbol="AAA"):
    return {"symbol": symbol, "cik": "0000000001", "accn": f"a{i}", "line_no": i, "owner_name": "Doe", "owner_title": "CEO",
            "is_officer": True, "is_director": False, "is_ten_pct_owner": False, "is_10b5_1_plan": i % 2 == 0,
            "transaction_date": f"2026-01-0{i + 1}", "transaction_code": "P", "acquired_disposed": "A",
            "shares": 100. * i, "price_per_share": 10., "shares_owned_after": None, "filed_date": "2026-01-20"}


def test_insider_persistence_matches_capture(tmp_path, monkeypatch, clock):
    results = []
    for label in ("old", "new"):
        path = tmp_path / label / "gabi.db"
        monkeypatch.setattr(config, "DB_PATH", path)
        if label == "old":
            target = legacy_module("insider", storage=legacy_storage(path), config=config,
                                   edgar=SimpleNamespace(), datetime=FixedDatetime)
            target.datetime = FixedDatetime
        else:
            store = SqliteInsiders(path.parent, database=path, now=lambda: NOW)
            target = SimpleNamespace(get_insider_transactions=store.transactions, get_insider_fetched_at=store.fetched_at,
                                     upsert_insider_transactions=store.save)
        outcomes = [target.get_insider_transactions("AAA").to_dict("split"), target.get_insider_fetched_at(["AAA"])]
        target.upsert_insider_transactions("AAA", [form4(i) for i in range(3)])
        target.upsert_insider_transactions("BBB", [])
        target.upsert_insider_transactions("AAA", [form4(1)])
        outcomes += [target.get_insider_transactions("AAA").to_dict("split"),
                     target.get_insider_fetched_at(["AAA", "BBB", "CCC"]), target.get_insider_fetched_at([])]
        results.append((outcomes, dump(path)))
    assert results[0] == results[1]
    assert results[1][0][2]["data"][0][10] == "2026-01-03"  # newest transaction first


def yahoo_panel(symbols):
    index = pd.bdate_range("2026-01-05", "2026-01-09")
    frame = pd.DataFrame({"Open": 10., "High": 11., "Low": 9., "Close": 10., "Adj Close": 9.5, "Volume": 1e3}, index=index)
    return pd.concat({symbol: frame for symbol in symbols}, axis=1) if len(symbols) > 1 else frame


class FakeTicker:
    def __init__(self, symbol):
        self.symbol = symbol
        self.splits = pd.Series([4.0], index=pd.to_datetime(["2020-08-31"])) if symbol == "AAA" else pd.Series(dtype=float)
        self.info = {} if symbol == "EMPTY" else {"marketCap": 1e9, "sector": "Tech", "beta": 1.1}
        self.quarterly_income_stmt = pd.DataFrame({"2025-12-31": [1e6]}, index=["Total Revenue"])
        self.quarterly_cashflow = pd.DataFrame()


def test_data_fetch_batches_match_capture(tmp_path, monkeypatch, clock):
    monkeypatch.setattr(yfinance, "download", lambda tickers, **k: yahoo_panel(tickers))
    monkeypatch.setattr(yfinance, "Ticker", FakeTicker)
    monkeypatch.setattr(identity, "resolve", lambda symbol, day: {"entity_id": None})
    results = []
    for label in ("old", "new"):
        path = tmp_path / label / "gabi.db"
        path.parent.mkdir()
        monkeypatch.setattr(config, "DATA_DIR", path.parent)
        monkeypatch.setattr(config, "DB_PATH", path)
        if label == "old":
            import sync_checkpoints

            # The captured data_fetch imported the flat sync_state retired in F7.29.
            monkeypatch.setitem(sys.modules, "gabi.sync_state", sync_checkpoints)
            target = legacy_module("data_fetch", config=config, identity=identity, storage=storage)
            target.datetime = FixedDatetime
            monkeypatch.setattr(storage, "datetime", FixedDatetime)
        else:
            target = data_fetch
        outcomes = [target.fetch_prices_batch(["AAA", "BRK.B"]), target.fetch_prices_batch(["AAA"], period="max"),
                    target.fetch_splits_batch(["AAA", "BBB"], max_workers=1),
                    target.fetch_fundamentals_batch(["AAA", "EMPTY"], max_workers=1),
                    target.fetch_fundamentals_batch(["AAA"], max_workers=1),
                    target.ensure_decision_prices(["AAA", "CCC"])]
        results.append((outcomes, dump(path)))
    assert results[0] == results[1]


def test_name_candidates_are_read_only(tmp_path, monkeypatch):
    path = tmp_path / "gabi.db"
    monkeypatch.setattr(config, "DB_PATH", path)
    assert list(identity.name_candidates("AAA").columns) == ["symbol", "entity_id", "name", "source", "reason"]
    assert not path.exists()
    with closing(sqlite3.connect(path)) as db, db:
        identity.ensure_schema(db)
        db.execute("INSERT INTO entities VALUES ('cik:1','0000000001','Alpha','2020-01-01')")
        db.execute("INSERT INTO entity_candidates VALUES ('BRK-B','cik:1','Alpha','src','name')")
    before = path.read_bytes()
    with closing(sqlite3.connect(path)) as db:
        expected = pd.read_sql_query("SELECT * FROM entity_candidates WHERE symbol=? LIMIT 200", db, params=("BRK-B",))
    pd.testing.assert_frame_equal(identity.name_candidates("BRK.B"), expected)
    assert path.read_bytes() == before
