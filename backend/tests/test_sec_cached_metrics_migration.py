"""Captured parity and read-only boundaries for cached EDGAR metric reads."""

import ast
import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest

from gabi.application.market.sec_reads import cached_metrics, fetched_at, symbols_with_facts
from gabi.infrastructure.storage.sec_reads import SqliteSecReads

REFERENCE = json.loads((Path(__file__).parent / "fixtures/sec_cached_metrics_migration.json").read_text(encoding="utf-8"))
NAMES = {"SCHEMA", "FACTS_SCHEMA", "get_edgar_metrics", "get_symbols_with_facts", "get_edgar_fetched_at"}


def captured(path, monkeypatch):
    from gabi import config, storage
    monkeypatch.setattr(config, "DB_PATH", path)
    namespace = {"storage": storage, "datetime": datetime}
    source = REFERENCE["edgar"]
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef) and node.name in NAMES or isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id in NAMES for target in node.targets):
            exec(ast.get_source_segment(source, node), namespace)
    return namespace


def seed(path, count=450):
    from gabi import edgar
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as db:
        db.executescript(edgar.SCHEMA + edgar.FACTS_SCHEMA)
        for i in range(count):
            stamp = datetime(2026, 1, 1, i % 24, tzinfo=UTC).isoformat()
            if i % 50 == 7:
                stamp = "not-a-date"
            db.execute("INSERT INTO edgar_metrics VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (f"S{i}", f"{i:010d}", stamp, i / 100 if i % 3 else None, -0.5, None,
                        "2025-02-01", f"https://sec.example/{i}", None if i % 4 else "2025-11-01", None))
            if i % 2:
                db.executemany("INSERT INTO edgar_facts VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                               [(f"S{i}", "Revenues", "USD", "2024-01-01", "2024-12-31", 1.0, "10-K", "FY", 2024,
                                 "2025-02-01", f"a{i}-{n}") for n in range(3)])
        db.commit()


SYMBOLS = [
    [], ["S1"], ["absent"], ["S1", "S1", "S2"],
    [f"S{i}" for i in range(450)] + ["absent", "S3"],
]


@pytest.mark.parametrize("symbols", SYMBOLS)
def test_cached_reads_match_captured_facade(tmp_path, monkeypatch, symbols):
    from gabi import edgar

    path = tmp_path / "gabi.db"
    seed(path)
    old = captured(path, monkeypatch)
    reader = SqliteSecReads(path)
    expected = old["get_edgar_metrics"](symbols), old["get_edgar_fetched_at"](symbols), old["get_symbols_with_facts"](symbols)
    assert (cached_metrics(reader, symbols), fetched_at(reader, symbols), symbols_with_facts(reader, symbols)) == expected
    assert (edgar.get_edgar_metrics(symbols), edgar.get_edgar_fetched_at(symbols),
            edgar.get_symbols_with_facts(symbols)) == expected
    if len(symbols) > 400:
        assert fetched_at(reader, symbols)["S7"] is None


def test_missing_database_or_tables_return_absence_without_creating(tmp_path, monkeypatch):
    from gabi import config, edgar

    missing = tmp_path / "absent" / "gabi.db"
    monkeypatch.setattr(config, "DB_PATH", missing)
    assert (edgar.get_edgar_metrics(["S1"]), edgar.get_edgar_fetched_at(["S1"]), edgar.get_symbols_with_facts(["S1"])) == ({}, {}, set())
    assert not missing.parent.exists()

    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()
    monkeypatch.setattr(config, "DB_PATH", empty)
    assert (edgar.get_edgar_metrics(["S1"]), edgar.get_edgar_fetched_at(["S1"]), edgar.get_symbols_with_facts(["S1"])) == ({}, {}, set())
    with closing(sqlite3.connect(empty)) as db:
        assert db.execute("SELECT count(*) FROM sqlite_schema").fetchone() == (0,)


def test_reads_are_batched_read_only_and_never_use_legacy_connections(tmp_path, monkeypatch):
    from gabi import config, edgar, storage

    path = tmp_path / "gabi.db"
    seed(path)
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
    symbols = [f"S{i}" for i in range(450)]
    assert len(edgar.get_edgar_metrics(symbols)) == 450
    assert len(edgar.get_symbols_with_facts(symbols)) == 225
    selects = [s for s in statements if s.lstrip().upper().startswith("SELECT") and "sqlite_schema" not in s]
    assert len(selects) == 6  # 3 batches of 200 per query
    assert not [s for s in statements if s.lstrip().upper().startswith(("CREATE", "INSERT", "UPDATE", "DELETE", "PRAGMA JOURNAL"))]
    assert path.read_bytes() == before


def test_oversized_cached_row_fails_instead_of_truncating(tmp_path):
    path = tmp_path / "gabi.db"
    seed(path, count=3)
    with closing(sqlite3.connect(path)) as db:
        db.execute("UPDATE edgar_metrics SET latest_10k_url=? WHERE symbol='S1'", ("x" * 5000,))
        db.commit()
    reader = SqliteSecReads(path, max_row_bytes=4096)
    with pytest.raises(ValueError, match="límite"):
        reader.cached_metrics(["S0", "S1", "S2"])
    assert set(reader.cached_metrics(["S0", "S2"])) == {"S0", "S2"}
