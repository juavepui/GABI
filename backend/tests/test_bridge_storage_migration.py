"""Captured parity of the identity-migration, 1996-2015 backfill and 10-K pilot bridges without storage (#134)."""

import ast
import json
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pandas as pd
import pytest

from gabi import config, edgar, storage
from gabi.domain.research.historical_identity_audit import CANDIDATE_SOURCE
from gabi.infrastructure.legacy import entity_migration, historical_backfill, tenk_extraction
from gabi.infrastructure.storage.entity_snapshots import SCHEMA as SNAPSHOTS
from gabi.infrastructure.storage.historical_archive_schema import SCHEMA as ARCHIVE
from gabi.infrastructure.storage.historical_backfill import SqliteHistoricalBackfill
from gabi.infrastructure.storage.historical_identity_audit import SqliteIdentityAuditReads

REFERENCE = json.loads((Path(__file__).parent / "fixtures/bridge_storage_migration.json").read_text(encoding="utf-8"))


def connection(path: Path):
    @contextmanager
    def get_connection():
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path, timeout=30)) as db:
            db.execute("PRAGMA journal_mode=WAL")
            yield db
    return get_connection


def use(monkeypatch, path: Path) -> None:
    monkeypatch.setattr(config, "DATA_DIR", path.parent)
    monkeypatch.setattr(config, "DB_PATH", path)


def captured_entity_migration(path: Path) -> ModuleType:
    module = ModuleType("captured_entity_migration")
    module.__package__ = "gabi.infrastructure.legacy"
    source = REFERENCE["entity_migration"].replace("from gabi import identity, storage\n", "from gabi import identity\n")
    module.storage = SimpleNamespace(get_connection=connection(path))
    exec(compile(source, "captured_entity_migration", "exec"), module.__dict__)
    return module


def dump(path: Path) -> dict:
    with closing(sqlite3.connect(path)) as db:
        tables = [name for name, in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        return {table: sorted(map(repr, db.execute(f'SELECT * FROM "{table}"'))) for table in tables}


def _prices(day, price):
    return pd.DataFrame({c: [price] for c in ["Open", "High", "Low", "Close", "Adj Close", "Volume"]},
                        index=pd.to_datetime([day]))


def seed_identity(path: Path) -> None:
    storage.upsert_prices("FB", _prices("2019-01-01", 10))
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript(SNAPSHOTS)
        db.executemany("INSERT INTO entity_snapshots VALUES (?,?,?,?,?,?)", [
            ("FB", "1326801", "Facebook", "Technology", "Internet", "2019-01-02"),
            ("AAA", "", "No CIK", "Energy", "Oil", "2019-01-02"),
            ("BBB", "0000000002", "Bravo", "Utilities", "Power", "2020-05-01"),
        ])


def run_identity(module, path: Path) -> tuple:
    migrated = module.migrate()
    attributed = module.attribute_legacy("FB", "cik:0001326801", "prices", source="test:verified-owner")
    missing = module.attribute_legacy("FB", "cik:0001326801", "edgar_facts", source="test:verified-owner")
    history = pd.DataFrame([{"date": "2019-01-01", "tickers": "FB,UNKNOWN,BBB"}])
    report = module.coverage_report(history, pd.DataFrame({"symbol": ["META"]}))
    tables = dump(path)
    tables["entities"] = [row.rsplit(",", 1)[0] for row in tables["entities"]]  # created_at is today's date
    return migrated, attributed, missing, report, tables


def test_entity_migration_matches_captured_bridge(tmp_path, monkeypatch):
    old, new = tmp_path / "old" / "gabi.db", tmp_path / "new" / "gabi.db"
    results = []
    for path, module in ((old, None), (new, entity_migration)):
        use(monkeypatch, path)
        seed_identity(path)
        results.append(run_identity(module or captured_entity_migration(path), path))
    assert results[0] == results[1]
    assert results[1][0]["snapshots_imported"] == 2 and results[1][1] == 1 and results[1][2] == 0


def test_entity_migration_never_uses_the_storage_connection(tmp_path, monkeypatch):
    use(monkeypatch, tmp_path / "gabi.db")
    monkeypatch.setattr(storage, "get_connection", lambda: pytest.fail("legacy connection"))
    entity_migration.migrate()
    assert entity_migration.coverage_report(pd.DataFrame(columns=["date", "tickers"]),
                                            pd.DataFrame({"symbol": []}))["verified_symbol_date_pairs"] == 0


def _function(source: str, name: str) -> ast.FunctionDef:
    return next(node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == name)


def _storage_blocks(source: str, name: str) -> list[str]:
    """Bodies of ``with storage.get_connection() as conn`` blocks in a captured function."""
    blocks = []
    for node in ast.walk(_function(source, name)):
        if isinstance(node, ast.With) and len(node.items) == 1 and "get_connection" in ast.unparse(node.items[0]):
            blocks.append("\n".join(ast.unparse(statement) for statement in node.body))
    return blocks


def seed_backfill(path: Path) -> None:
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript(edgar.SCHEMA + edgar.FACTS_SCHEMA + storage.SCHEMA + ARCHIVE)
        db.executemany("INSERT INTO edgar_metrics(symbol,cik,fetched_at) VALUES (?,?,?)",
                       [("AAA", "0000000001", "2026-01-01"), ("BBB", None, "2026-01-01")])
        db.executemany("INSERT INTO edgar_facts(symbol,tag,unit,start_date,end_date,val,filed_date,accn) "
                       "VALUES (?,?,?,?,?,?,?,?)",
                       [("AAA", "Revenues", "USD", "2014-01-01", "2014-12-31", 1, "2015-02-01", "a"),
                        ("CCC", "Revenues", "USD", "2016-01-01", "2016-12-31", 1, "2017-02-01", "b")])
        db.executemany("INSERT INTO prices(symbol,date,open,high,low,close,adj_close,volume) VALUES (?,?,?,?,?,?,?,?)",
                       [("AAA", "2015-06-01", 1, 1, 1, 1, 1, 1), ("BBB", "2015-06-01", 1, 1, 1, 1, None, 1),
                        ("CCC", "2017-06-01", 1, 1, 1, 1, 1, 1)])
        db.executemany("INSERT INTO historical_prices VALUES (?,?,?,?,?,?,?,?,?,?)",
                       [("prices", "AAA", "2010-01-04", 1, 1, 1, 1, 1, 1, "raw"),
                        ("prices", "DDD", "2012-01-04", 1, 1, 1, 1, 1, 1, "raw"),
                        ("other", "EEE", "2013-01-04", 1, 1, 1, 1, 1, 1, "raw")])
        db.executemany("INSERT INTO historical_facts VALUES (?,?,?,?,?,?)",
                       [("issuers", "AAA", "0000000001", "k1", "2011-02-01", "{}"),
                        ("issuers", "DDD", "0000000004", "k2", "2013-02-01", "{}")])


def test_backfill_sql_matches_captured_blocks(tmp_path):
    path = tmp_path / "gabi.db"
    seed_backfill(path)
    end, targets = "2016-01-01", {"AAA", "BBB", "CCC", "DDD"}
    manifest = {"price_source_id": "prices", "issuer_source_id": "issuers"}
    before, after = _storage_blocks(REFERENCE["historical_backfill"], "run")
    captured = {"end": end, "targets": targets, "manifest": manifest, "report": {}}
    with connection(path)() as conn:
        exec(before, {**captured, "conn": conn}, scope := {})
        exec(after, {**captured, "conn": conn})

    store = SqliteHistoricalBackfill(path)
    assert store.operational(end) == (scope["stored"], scope["old_facts"], scope["old_prices"])
    summary = store.summary("prices", "issuers", end)
    report = {"archive_coverage": summary["archive_coverage"], "archived_sec_facts": summary["archived_sec_facts"],
              "sqlite_integrity": summary["sqlite_integrity"],
              "after_old_coverage": {"symbols_with_prices": len(targets & summary["old_prices"]),
                                     "symbols_with_facts": len(targets & summary["old_facts"])}}
    assert report == captured["report"]
    assert captured["report"]["archive_coverage"]["rows"] == 2

    store.backup(tmp_path / "copy.db")
    assert dump(tmp_path / "copy.db") == dump(path)


def test_backfill_prices_match_captured_storage_writes(tmp_path, monkeypatch):
    frame = pd.DataFrame({"Open": [1.0, 2.0], "High": [1.0, 2.0], "Low": [1.0, 2.0], "Close": [1.0, 2.0],
                          "Adj Close": [.5, 1.0], "Volume": [10, 20], "Stock Splits": [0.0, 2.0]},
                         index=pd.to_datetime(["2015-01-02", "2015-01-05"]))
    old, new = tmp_path / "old" / "gabi.db", tmp_path / "new" / "gabi.db"
    use(monkeypatch, old)
    storage.upsert_prices("AAA", frame)
    storage.upsert_splits("AAA", {"2015-01-05": 2.0})
    use(monkeypatch, new)
    monkeypatch.setattr(storage, "upsert_prices", lambda *a, **k: pytest.fail("storage facade"))
    monkeypatch.setattr(historical_backfill.yahoo, "history", lambda *a, **k: frame)
    monkeypatch.setattr(historical_backfill, "overlaps_membership", lambda *a: True)
    assert historical_backfill.fetch_missing_history("AAA", pd.DataFrame(), "2016-01-01") == 2
    assert dump(old) == dump(new)


def test_tenk_candidates_match_captured_query(tmp_path, monkeypatch):
    path = tmp_path / "gabi.db"
    use(monkeypatch, path)
    with pytest.raises(ValueError, match="historical_issuer_candidates"):
        SqliteIdentityAuditReads(path).issuer_candidates()
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript(ARCHIVE)
        db.executemany("INSERT INTO historical_issuer_candidates VALUES (?,?,?,?,?,?,?)",
                       [(CANDIDATE_SOURCE, "AAA", "1", "Alpha", "2000-01-01", None, "2000-01-01"),
                        (CANDIDATE_SOURCE, "BBB", "2", "Bravo", None, "2009-01-01", None),
                        ("other", "CCC", "3", "Charlie", None, None, None)])
    block, = _storage_blocks(REFERENCE["tenk_extraction"], "sample")
    with connection(path)() as conn:
        exec(block, {"conn": conn, "CANDIDATE_SOURCE": CANDIDATE_SOURCE}, scope := {})
    assert SqliteIdentityAuditReads(path).issuer_candidates() == scope["cands"]
    assert "storage" not in vars(tenk_extraction)
