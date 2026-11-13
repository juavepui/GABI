"""Captured parity and read-only boundaries for the cached price/fundamental reads."""

import ast
import json
import sqlite3
from contextlib import closing, contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from gabi.application.market import cached_data
from gabi.infrastructure.storage.cache_reads import SqliteCacheReads

REFERENCE = json.loads((Path(__file__).parent / "fixtures/storage_cache_reads_migration.json").read_text(encoding="utf-8"))
NAMES = {"SCHEMA", "UPDATE_ERRORS_RETENTION_DAYS", "_ensure_price_columns", "get_prices", "get_prices_multi",
         "get_price_coverage", "get_price_as_of", "has_verified_price_as_of", "get_split_factor_since",
         "get_fundamentals", "get_fundamentals_fetched_at", "get_recent_update_errors"}
READS = sorted(NAMES - {"SCHEMA", "UPDATE_ERRORS_RETENTION_DAYS", "_ensure_price_columns"})


def captured(path):
    @contextmanager
    def get_connection():
        with closing(sqlite3.connect(path, timeout=30)) as db:
            yield db
    namespace = {"get_connection": get_connection, "pd": pd, "json": json, "datetime": datetime, "UTC": UTC,
                 "timedelta": timedelta}
    source = REFERENCE["storage"]
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef) and node.name in NAMES or isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id in NAMES for target in node.targets):
            exec(ast.get_source_segment(source, node), namespace)
    return namespace


def seed(path, *, symbols=30, legacy_prices=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    with closing(sqlite3.connect(path)) as db:
        db.executescript(captured(path)["SCHEMA"])
        if legacy_prices:
            db.executescript("DROP TABLE prices; CREATE TABLE prices (symbol TEXT NOT NULL, date TEXT NOT NULL, "
                             "open REAL, high REAL, low REAL, close REAL, volume REAL, PRIMARY KEY (symbol, date));")
        for i in range(symbols):
            symbol = f"S{i}"
            for day in range(40):
                stamp = (datetime(2019, 1, 1) + timedelta(days=day * (i % 3 + 1))).strftime("%Y-%m-%d")
                values = (symbol, stamp, None if day == 0 else 10.0 + day, 11.0, 9.0, 10.0 + day + i / 7,
                          1000.0 if day % 5 else None)
                if legacy_prices:
                    db.execute("INSERT INTO prices VALUES (?,?,?,?,?,?,?)", values)
                else:
                    db.execute("INSERT INTO prices VALUES (?,?,?,?,?,?,?,?)",
                               (*values, None if day % 4 == 0 or i % 5 == 0 else 9.5 + day))
            if i % 2:
                db.executemany("INSERT INTO splits VALUES (?,?,?)",
                               [(symbol, "2019-01-20", 2.0), (symbol, "2019-02-10", 0.0), (symbol, "2018-06-01", 3.0)])
            if i % 3:
                fetched = "garbage" if i % 7 == 0 else (now - timedelta(hours=i)).isoformat()
                db.execute("INSERT INTO fundamentals VALUES (?,?,?,?,?)",
                           (symbol, fetched, json.dumps({"sector": "Tech", "beta": i / 10}),
                            json.dumps({"2024-03-31": {"Total Revenue": i * 1e6, "EBIT": None}}), "{}"))
            db.execute("INSERT INTO update_errors (source,symbol,reason,occurred_at) VALUES (?,?,?,?)",
                       ("yahoo_precio" if i % 2 else "sec_edgar", symbol, f"fallo {i}",
                        (now - timedelta(hours=i * 10)).isoformat()))
        db.commit()


def compare(new, old):
    if isinstance(old, pd.DataFrame):
        assert_frame_equal(new, old)
    elif isinstance(old, dict) and old and isinstance(next(iter(old.values())), pd.DataFrame):
        assert list(new) == list(old)
        for key in old:
            assert_frame_equal(new[key], old[key])
    else:
        assert new == old


def calls(symbols):
    return [
        ("get_prices", (symbols[0],)), ("get_prices", ("absent",)),
        ("get_prices_multi", (symbols,)), ("get_prices_multi", ([],)), ("get_prices_multi", (["absent"],)),
        ("get_price_coverage", (symbols,)), ("get_price_coverage", ([],)),
        ("get_price_as_of", (symbols[1], "2019-01-15")), ("get_price_as_of", (symbols[0], "2010-01-01")),
        ("get_price_as_of", (symbols[0], "2019-01-01")),
        ("has_verified_price_as_of", (symbols[1], "2019-01-15")), ("has_verified_price_as_of", (symbols[0], "2019-03-01")),
        ("has_verified_price_as_of", (symbols[1], "2019-01-01")),
        ("get_split_factor_since", (symbols[1], "2019-01-01")), ("get_split_factor_since", (symbols[1], "2019-01-25")),
        ("get_split_factor_since", (symbols[1], "2017-01-01")), ("get_split_factor_since", (symbols[0], "2017-01-01")),
        ("get_fundamentals", (symbols,)), ("get_fundamentals", ([],)),
        ("get_fundamentals_fetched_at", (symbols,)), ("get_fundamentals_fetched_at", ([],)),
        ("get_recent_update_errors", ()), ("get_recent_update_errors", ("sec_edgar",)),
        ("get_recent_update_errors", (None, 50)),
    ]


@pytest.mark.parametrize("legacy_prices", [False, True])
@pytest.mark.parametrize("count", [3, 30, 1100])
def test_reads_match_captured_storage(tmp_path, monkeypatch, legacy_prices, count):
    from gabi import config, storage

    path = tmp_path / "gabi.db"
    seed(path, symbols=count, legacy_prices=legacy_prices)
    monkeypatch.setattr(config, "DB_PATH", path)
    symbols = [f"S{i}" for i in range(count)] + ["S1", "absent"]
    expected = {}
    # The captured reads run first: they may add the adj_close column to the old table,
    # so the facade is compared on the reference's view of the same rows.
    reference = captured(tmp_path / "reference.db")
    reference_path = tmp_path / "reference.db"
    reference_path.write_bytes(path.read_bytes())
    for name, args in calls(symbols):
        expected[name, repr(args)] = reference[name](*args)
    for name, args in calls(symbols):
        compare(getattr(storage, name)(*args), expected[name, repr(args)])


def test_use_cases_accept_an_explicit_reader(tmp_path):
    path = tmp_path / "gabi.db"
    seed(path, symbols=4)
    reader = SqliteCacheReads(path)
    old = captured(path)
    assert_frame_equal(cached_data.prices(reader, "S1"), old["get_prices"]("S1"))
    assert cached_data.split_factor_since(reader, "S1", "2017-01-01") == old["get_split_factor_since"]("S1", "2017-01-01")
    now = datetime.now(UTC)
    assert len(cached_data.recent_update_errors(reader, now=now, since_hours=1)) == 1


def test_missing_database_or_tables_return_absence_without_creating(tmp_path, monkeypatch):
    from gabi import config, storage

    missing = tmp_path / "absent" / "gabi.db"
    monkeypatch.setattr(config, "DATA_DIR", missing.parent)
    monkeypatch.setattr(config, "DB_PATH", missing)
    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()
    for path in (missing, empty):
        monkeypatch.setattr(config, "DB_PATH", path)
        assert storage.get_prices("S1").empty
        assert storage.get_prices_multi(["S1"]) == {}
        assert storage.get_price_coverage(["S1"]) == {}
        assert storage.get_price_as_of("S1", "2020-01-01") is None
        assert storage.has_verified_price_as_of("S1", "2020-01-01") is False
        assert storage.get_split_factor_since("S1", "2020-01-01") == 1.0
        assert storage.get_fundamentals(["S1"]) == {}
        assert storage.get_fundamentals_fetched_at(["S1"]) == {}
        assert list(storage.get_recent_update_errors().columns) == ["source", "symbol", "reason", "occurred_at"]
    assert not missing.parent.exists()
    with closing(sqlite3.connect(empty)) as db:
        assert db.execute("SELECT count(*) FROM sqlite_schema").fetchone() == (0,)


def test_reads_are_read_only_batched_and_avoid_legacy_connections(tmp_path, monkeypatch):
    from gabi import config, storage

    path = tmp_path / "gabi.db"
    seed(path, symbols=1100, legacy_prices=True)
    before = path.read_bytes()
    monkeypatch.setattr(config, "DB_PATH", path)
    monkeypatch.setattr(storage, "get_connection", lambda: pytest.fail("legacy connection"))
    statements = []
    real_connect = sqlite3.connect

    def tracing(*args, **kwargs):
        db = real_connect(*args, **kwargs)
        db.set_trace_callback(statements.append)
        return db

    monkeypatch.setattr(sqlite3, "connect", tracing)
    symbols = [f"S{i}" for i in range(1100)]
    assert len(storage.get_prices_multi(symbols)) == 1100
    assert len(storage.get_fundamentals(symbols)) == 733
    assert storage.has_verified_price_as_of("S1", "2019-12-31") is False  # old table: no adj_close
    assert len([s for s in statements if "FROM prices WHERE symbol IN" in s]) == 3
    mutations = ("CREATE", "INSERT", "UPDATE", "DELETE", "ALTER", "DROP", "PRAGMA JOURNAL")
    assert not [s for s in statements if s.lstrip().upper().startswith(mutations)]
    assert path.read_bytes() == before


@pytest.mark.parametrize("limits, call", [
    ({"max_rows": 100}, lambda reader: reader.prices_multi(["S0", "S1", "S2"])),
    ({"max_series_rows": 39}, lambda reader: reader.prices("S0")),
    ({"max_bytes": 1000}, lambda reader: reader.prices_multi(["S0", "S1"])),
    ({"max_field_bytes": 40}, lambda reader: reader.fundamentals(["S1"])),
    ({"max_rows": 1, "batch_size": 1}, lambda reader: reader.prices_multi(["S0", "S1"])),
])
def test_limits_fail_instead_of_truncating(tmp_path, limits, call):
    path = tmp_path / "gabi.db"
    seed(path, symbols=3)
    with pytest.raises(ValueError, match="límite"):
        call(SqliteCacheReads(path, **limits))


def test_invalid_limits_are_rejected(tmp_path):
    for limits in ({"max_rows": 0}, {"batch_size": 501}):
        with pytest.raises(ValueError):
            SqliteCacheReads(tmp_path / "gabi.db", **limits)
