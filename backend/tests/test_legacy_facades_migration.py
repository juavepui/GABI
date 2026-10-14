"""Captured parity of the storage writes and the edgar_sync, entity_master, screener, live_ledger and
history_refresh facades after their SQL moved to explicit infrastructure adapters."""

import ast
import json
import sqlite3
from contextlib import closing, contextmanager, nullcontext
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from gabi import config, identity

REFERENCE = json.loads((Path(__file__).parent / "fixtures/legacy_facades_migration.json").read_text(encoding="utf-8"))
NOW = datetime(2026, 3, 2, 21, 30, tzinfo=UTC)


class FixedDate(date):
    @classmethod
    def today(cls):
        return NOW.date()


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz else NOW.replace(tzinfo=None)


def captured(module: str, names: set[str], namespace: dict) -> dict:
    source = REFERENCE[module]
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef) and node.name in names or isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id in names for target in node.targets):
            code = ast.get_source_segment(source, node)
            code = code.replace("            from .identity import put_observations\n", "")
            exec(code, namespace)
    return namespace


def connection(path: Path):
    @contextmanager
    def get_connection():
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path, timeout=30)) as db:
            db.execute("PRAGMA journal_mode=WAL")
            yield db
    return get_connection


def dump(path: Path) -> dict:
    with closing(sqlite3.connect(path)) as db:
        tables = sorted(name for name, in db.execute("SELECT name FROM sqlite_schema WHERE type='table' "
                                                     "AND name<>'sqlite_sequence'"))
        return {table: sorted(map(repr, db.execute(f"SELECT * FROM {table}").fetchall())) for table in tables}


def with_entity(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as db, db:
        identity.ensure_schema(db)
        db.execute("INSERT INTO entities VALUES (?,?,?,?)", ("cik:0000000001", "0000000001", "Alpha", "2020-01-01"))


def legacy_storage(path: Path) -> dict:
    return captured("storage", {"SCHEMA", "UPDATE_ERRORS_RETENTION_DAYS", "_ensure_price_columns", "_df_to_json",
                                "init_db", "upsert_prices", "upsert_splits", "upsert_fundamentals",
                                "record_update_errors", "get_prices", "get_price_coverage", "get_fundamentals_fetched_at"},
                    {"get_connection": connection(path), "pd": pd, "json": json, "datetime": FixedDatetime, "UTC": UTC,
                     "timedelta": timedelta, "put_observations": identity.put_observations})


def prices_frame(days, *, adjusted=True, start="2024-01-01"):
    index = pd.date_range(start, periods=days, freq="D")
    frame = pd.DataFrame({"Open": range(days), "High": range(days), "Low": range(days),
                          "Close": [10.0 + i for i in range(days)], "Volume": [None] + [1000.0] * (days - 1)},
                         index=index, dtype=float)
    if adjusted:
        frame["Adj Close"] = [9.5 + i for i in range(days)]
    return frame


def write_everything(storage, *, legacy_table=False):
    if legacy_table:
        with closing(sqlite3.connect(config.DB_PATH)) as db:
            db.execute("CREATE TABLE prices (symbol TEXT NOT NULL, date TEXT NOT NULL, open REAL, high REAL, low REAL, "
                       "close REAL, volume REAL, PRIMARY KEY (symbol, date))")
            db.commit()
    storage.init_db()
    storage.upsert_prices("AAA", prices_frame(5))
    storage.upsert_prices("AAA", prices_frame(3, start="2024-01-04"), entity_id="cik:0000000001")
    storage.upsert_prices("BBB", prices_frame(4, adjusted=False))
    storage.upsert_prices("CCC", pd.DataFrame())
    storage.upsert_splits("AAA", {"2024-01-03": 2.0, "2024-01-05": 0.5}, entity_id="cik:0000000001")
    storage.upsert_splits("BBB", {})
    income = pd.DataFrame({"2024-03-31": [1.5, "x"], "2023-12-31": [None, 2]}, index=["Revenue", "EBIT"])
    storage.upsert_fundamentals("AAA", {"sector": "Tech"}, income, None, entity_id="cik:0000000001")
    storage.upsert_fundamentals("BBB", {"beta": float("nan")}, pd.DataFrame(), pd.DataFrame())
    storage.record_update_errors("yahoo_precio", {"AAA": ValueError("boom"), "BBB": "timeout"})
    storage.record_update_errors("sec_edgar", {})


@pytest.mark.parametrize("legacy_table", [False, True])
def test_storage_writes_match_captured_writes(tmp_path, monkeypatch, legacy_table):
    from gabi import storage

    results = []
    for label in ("old", "new"):
        path = tmp_path / label / "gabi.db"
        with_entity(path)
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS update_errors (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT "
                       "NOT NULL, symbol TEXT, reason TEXT NOT NULL, occurred_at TEXT NOT NULL)")
            db.execute("INSERT INTO update_errors (source,symbol,reason,occurred_at) VALUES (?,?,?,?)",
                       ("old", "X", "expired", (NOW - timedelta(days=91)).isoformat()))
        monkeypatch.setattr(config, "DB_PATH", path)
        if label == "old":
            target = SimpleNamespace(**legacy_storage(path))
        else:
            monkeypatch.setattr(storage, "datetime", FixedDatetime)
            target = storage
        write_everything(target, legacy_table=legacy_table)
        results.append(dump(path))
    assert results[0] == results[1]
    assert results[1]["update_errors"] and not any("expired" in row for row in results[1]["update_errors"])


def test_storage_writes_never_use_the_legacy_connection(tmp_path, monkeypatch):
    from gabi import storage

    path = tmp_path / "data" / "gabi.db"
    with_entity(path)
    monkeypatch.setattr(config, "DB_PATH", path)
    monkeypatch.setattr(storage, "get_connection", lambda: pytest.fail("legacy connection"))
    write_everything(storage)
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("PRAGMA journal_mode").fetchone() == ("wal",)
        assert db.execute("SELECT count(*) FROM entity_observations").fetchone()[0] == 6


def test_failed_attribution_rolls_back_the_price_rows(tmp_path, monkeypatch):
    from gabi import storage

    path = tmp_path / "gabi.db"
    monkeypatch.setattr(config, "DB_PATH", path)
    with pytest.raises(ValueError, match="Unknown entity"):
        storage.upsert_prices("AAA", prices_frame(3), entity_id="cik:0000000404")
    assert storage.get_prices("AAA").empty


def test_issuer_sync_uses_the_verified_modern_composition(tmp_path, monkeypatch):
    import test_sec_xbrl_migration as xbrl

    from gabi import edgar, storage
    from gabi.infrastructure.providers import source_retry

    path = tmp_path / "facade" / "gabi.db"
    monkeypatch.setattr(config, "DB_PATH", path)
    monkeypatch.setattr(edgar, "_now", lambda: xbrl.NOW)
    monkeypatch.setattr(edgar, "time", SimpleNamespace(perf_counter=lambda: 4., thread_time=lambda: 2.))
    monkeypatch.setattr(source_retry, "retry", xbrl.counted)
    monkeypatch.setattr(edgar, "fetch_submissions", lambda cik: xbrl.filings())
    monkeypatch.setattr(edgar, "fetch_company_facts", lambda cik: xbrl.payload())
    monkeypatch.setattr(storage, "get_connection", lambda: pytest.fail("legacy connection"))
    modern = xbrl.modern(tmp_path / "modern")
    for full_refresh in (False, False, True):
        assert edgar.synchronize_issuer("A", "1", full_refresh=full_refresh) == modern.run("A", "1", full_refresh=full_refresh)
    assert xbrl.read_tables(path) == xbrl.read_tables(modern.path)


UNIVERSE = pd.DataFrame([
    {"symbol": "AAA", "name": "Alpha", "sector": "Tech", "industry": "Software"},
    {"symbol": "BBB", "name": "Beta", "sector": "Health", "industry": "Pharma", "cik": "2"},
    {"symbol": "CCC", "name": "Gamma", "sector": None, "industry": None},
])


def seed_snapshots(path: Path) -> None:
    with closing(sqlite3.connect(path)) as db, db:
        identity.ensure_schema(db)
        db.execute("CREATE TABLE IF NOT EXISTS entity_snapshots (symbol TEXT NOT NULL, cik TEXT, name TEXT, "
                   "sector TEXT, industry TEXT, effective_date TEXT NOT NULL, PRIMARY KEY (symbol, effective_date))")
        db.executemany("INSERT INTO entity_snapshots VALUES (?,?,?,?,?,?)", [
            ("LEG", None, "Legacy", "Energy", "Oil", "2020-01-01"), ("LEG", None, "Legacy", "Utilities", "Power", "2022-06-01"),
            ("OLD", None, "Old", "Tech", "Chips", "2021-01-01"), ("NEW", None, "New", "Tech", "Cloud", "2019-01-01"),
        ])
        db.execute("INSERT INTO entities VALUES (?,?,?,?)", ("cik:0000000007", "0000000007", "Owner", "2010-01-01"))
        db.execute("INSERT INTO entity_aliases VALUES (?,?,?,?,?,?)",
                   ("cik:0000000007", "NEW", "2015-01-01", None, "test", 1.0))
        db.execute("INSERT INTO entity_aliases VALUES (?,?,?,?,?,?)",
                   ("cik:0000000007", "OLD", "2030-01-01", None, "test", 1.0))
        identity.put_observations(db, "cik:0000000007", "sector", "NEW", [
            {"name": "New", "sector": "Industrials", "industry": "Rail", "cik": "0000000007", "effective_date": "2021-03-01"},
            {"name": "New", "sector": "Tech", "industry": "Cloud", "cik": "0000000007", "effective_date": "2023-03-01"}],
            "test")


@pytest.mark.parametrize("day", ["2018-01-01", "2021-06-01", "2024-01-01"])
@pytest.mark.parametrize("strict", [False, True])
def test_sector_lookup_matches_captured_entity_master(tmp_path, monkeypatch, day, strict):
    from gabi import entity_master

    path = tmp_path / "gabi.db"
    seed_snapshots(path)
    monkeypatch.setattr(config, "DB_PATH", path)
    old = captured("entity_master", {"SCHEMA", "get_sector_asof"}, {
        "storage": SimpleNamespace(get_connection=connection(path)), "identity": identity, "pd": pd})
    symbols = ["LEG", "OLD", "NEW", "NONE", "LEG"]
    assert entity_master.get_sector_asof(symbols, day, strict_identity=strict) == \
        old["get_sector_asof"](symbols, day, strict_identity=strict)


@pytest.mark.parametrize("effective", [None, "2020-01-01"])
def test_snapshot_recording_matches_captured_entity_master(tmp_path, monkeypatch, effective):
    from gabi import edgar, entity_master

    mapping = pd.DataFrame({"symbol": ["AAA"], "cik": ["0000000001"], "title": ["Alpha"]})
    monkeypatch.setattr(edgar, "get_cik_map", lambda **k: mapping)
    monkeypatch.setattr(edgar, "get_cik_for_symbol", lambda symbol, cik_map=None: (
        ("0000000001", "Alpha") if symbol == "AAA" else (_ for _ in ()).throw(KeyError(symbol))))
    monkeypatch.setattr(identity, "date", FixedDate)
    results = []
    for label in ("old", "new"):
        path = tmp_path / label / "gabi.db"
        path.parent.mkdir()
        monkeypatch.setattr(config, "DB_PATH", path)
        if label == "old":
            count = captured("entity_master", {"SCHEMA", "record_snapshot"}, {
                "storage": SimpleNamespace(get_connection=connection(path)), "identity": identity, "edgar": edgar,
                "pd": pd})["record_snapshot"](UNIVERSE, effective)
        else:
            count = entity_master.record_snapshot(UNIVERSE, effective)
        tables = dump(path)
        tables.pop("entity_aliases", None)  # alias ids are random per run
        results.append((count, tables))
    assert results[0] == results[1]


def test_snapshot_reads_never_create_storage(tmp_path, monkeypatch):
    from gabi import entity_master

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "absent" / "gabi.db")
    assert entity_master.get_sector_asof(["AAA"], "2020-01-01")["AAA"]["sector"] is None
    assert not (tmp_path / "absent").exists()


def seed_market(path: Path) -> None:
    from gabi import edgar, storage
    path.parent.mkdir(parents=True, exist_ok=True)
    days = pd.date_range("2023-01-02", periods=300, freq="B")
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript(storage.SCHEMA + edgar.SCHEMA + edgar.FACTS_SCHEMA)
        db.executemany("INSERT INTO edgar_facts VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                       [("AAA", "Revenues", "USD", "2022-01-01", "2022-12-31", 1.0, "10-K", "FY", 2022, day, accn)
                        for day, accn in (("2023-02-01", "a"), ("2024-02-01", "b"))])
        db.execute("CREATE TABLE macro_series (series_id TEXT, date TEXT, value REAL)")
        db.executemany("INSERT INTO macro_series VALUES (?,?,?)", [("DGS10", "2024-01-02", 4.1), ("DGS10", "2024-01-03", 4.25)])
        for k, symbol in enumerate(["AAA", "BBB", "CCC", "SPY"]):
            db.executemany("INSERT INTO prices VALUES (?,?,?,?,?,?,?,?)",
                           [(symbol, day.strftime("%Y-%m-%d"), 10., 11., 9., 10 + k + i * (0.01 + k / 300), 1e6,
                             0.0 if (symbol, i) == ("BBB", 299) else
                             10 + k + i * (0.01 + k / 300) if i < 299 or symbol != "CCC" else None)
                            for i, day in enumerate(days)])
            if symbol != "SPY":
                db.execute("INSERT INTO fundamentals VALUES (?,?,?,?,?)", (symbol, "2024-01-05T00:00:00+00:00",
                           json.dumps({"marketCap": 1e9 * (k + 1), "trailingPE": 10 + k, "returnOnEquity": .1 * k,
                                       "sector": "Tech", "beta": 1.0}), "{}", "{}"))
                db.execute("INSERT INTO edgar_metrics VALUES (?,?,?,?,?,?,?,?,?,?)",
                           (symbol, str(k), "2024-01-06T00:00:00+00:00", .1 * k, .2, .15, "2023-02-01", "u", None, None))


def test_screener_table_matches_captured_facade(tmp_path, monkeypatch):
    from gabi import (
        app_mode,
        data_fetch,
        edgar,
        entity_master,
        metrics,
        risk,
        scoring,
        screener,
        technicals,
        universe,
    )
    from gabi.application.market.ranking import Calculators, MarketBatch, MemoryInputs, build_ranking
    from gabi.domain.market import events as events_calendar
    from gabi.infrastructure.storage.fred import SqliteFred

    path = tmp_path / "gabi.db"
    seed_market(path)
    monkeypatch.setattr(config, "DB_PATH", path)
    storage_old = SimpleNamespace(**legacy_storage(path))
    storage_old.get_prices_multi = captured("storage", {"get_prices_multi", "_ensure_price_columns", "SCHEMA"}, {
        "get_connection": connection(path), "pd": pd})["get_prices_multi"]
    storage_old.get_fundamentals = captured("storage", {"get_fundamentals", "SCHEMA"}, {
        "get_connection": connection(path), "json": json})["get_fundamentals"]
    old = captured("screener", {"_get_risk_free_rate", "build_screener_table"}, {
        "storage": storage_old, "edgar": edgar, "macro": SimpleNamespace(get_series_history=SqliteFred(path, datetime.now).history), "config": config, "metrics": metrics,
        "technicals": technicals, "risk": risk, "scoring": scoring, "events_calendar": events_calendar,
        "MemoryInputs": MemoryInputs, "MarketBatch": MarketBatch, "Calculators": Calculators,
        "build_ranking": build_ranking, "date": date, "pd": pd,
        "data_fetch": data_fetch, "entity_master": entity_master, "universe": universe})
    universe_df = pd.DataFrame({"symbol": ["AAA", "BBB", "CCC", "ZZZ"], "name": list("ABCZ"),
                                "sector": ["Tech", "Tech", "Health", "Tech"], "industry": list("xyzw")})
    for weights in (None, app_mode.FROZEN_WEIGHTS):
        assert_frame_equal(screener.build_screener_table(universe_df, weights),
                           old["build_screener_table"](universe_df, weights))
    assert screener._get_risk_free_rate() == old["_get_risk_free_rate"]() == pytest.approx(.0425)


def legacy_ledger(path: Path, directory: Path) -> dict:
    from gabi.domain.research.live_ledger import UNREADABLE, canonical, fingerprint, safe, verify_chain
    namespace = {"storage": SimpleNamespace(get_connection=connection(path)), "json": json, "os": __import__("os"),
                 "anchor_path": lambda: directory / "live_ledger" / "head.json",
                 "_locked": lambda: (directory / "live_ledger").mkdir(parents=True, exist_ok=True) or nullcontext(),
                 "UNREADABLE": UNREADABLE, "canonical": canonical, "fingerprint": fingerprint, "_safe": safe,
                 "verify_chain": verify_chain, "_now": lambda: NOW}
    return captured("live_ledger", {"SCHEMA", "_write_anchor", "_verify", "verify_integrity", "_append", "events",
                                    "recover_anchor"}, namespace)


def test_ledger_chain_matches_captured_ledger(tmp_path, monkeypatch):
    from gabi import live_ledger, storage

    results = []
    for label in ("old", "new"):
        directory = tmp_path / label
        path = directory / "gabi.db"
        monkeypatch.setattr(config, "DATA_DIR", directory)
        monkeypatch.setattr(config, "DB_PATH", path)
        if label == "old":
            ledger = SimpleNamespace(**legacy_ledger(path, directory))
        else:
            monkeypatch.setattr(live_ledger, "_now", lambda: NOW)
            monkeypatch.setattr(storage, "get_connection", lambda: pytest.fail("legacy connection"))
            ledger = live_ledger
        outputs = [ledger.verify_integrity(), ledger._append({"kind": "DECISION", "value": float("nan")}),
                   ledger._append({"kind": "DECISION", "value": 2})]
        anchor = directory / "live_ledger" / "head.json"
        anchor.write_text(json.dumps({"seq": 1, "hash": outputs[1]["record_hash"]}), encoding="utf-8")
        outputs.append(ledger.verify_integrity())
        outputs.append(ledger.recover_anchor("restored from backup"))
        outputs += [ledger.events(), ledger.verify_integrity()]
        with pytest.raises(ValueError):
            ledger.recover_anchor(" ")
        with closing(sqlite3.connect(path)) as db:
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                db.execute("DELETE FROM live_ledger")
            journal = db.execute("PRAGMA journal_mode").fetchone()
        results.append((outputs, dump(path), anchor.read_bytes(), journal))
    assert results[0] == results[1]


def test_provenance_matches_captured_ledger(tmp_path, monkeypatch):
    from gabi import edgar, live_ledger, storage

    path = tmp_path / "gabi.db"
    seed_market(path)
    monkeypatch.setattr(config, "DB_PATH", path)
    old_storage = SimpleNamespace(get_connection=connection(path), SCHEMA=storage.SCHEMA,
                                  get_fundamentals_fetched_at=storage.get_fundamentals_fetched_at)
    old = captured("live_ledger", {"provenance"}, {"storage": old_storage, "edgar": edgar, "_safe": live_ledger._safe})
    symbols = ["AAA", "BBB", "CCC", "SPY", "ZZZ", "AAA"]
    assert live_ledger.provenance(symbols) == old["provenance"](symbols)
    found = live_ledger.provenance(symbols)
    assert found["CCC"]["price_date"] < found["AAA"]["price_date"] and found["BBB"]["price_date"] < found["AAA"]["price_date"]


def test_history_refresh_reads_and_writes_match_captured(tmp_path, monkeypatch):
    from gabi.infrastructure.legacy import history_refresh

    results = []
    for label in ("old", "new"):
        path = tmp_path / label / "gabi.db"
        seed_market(path)
        with_entity(path)
        frame = prices_frame(8, start="2024-03-01")
        with closing(sqlite3.connect(path)) as db, db:
            for original, canonical, offset in (("BRK.B", "BRK-B", 0), ("BF.B", "BF-B", 0.5)):
                rows = [(s, day.strftime("%Y-%m-%d"), 1., 1., 1., c, 1e3, a) for day, c, a in
                        zip(frame.index, frame["Close"], frame["Adj Close"], strict=True)
                        for s in (original,)]
                db.executemany("INSERT INTO prices VALUES (?,?,?,?,?,?,?,?)", rows)
                db.executemany("INSERT INTO prices VALUES (?,?,?,?,?,?,?,?)",
                               [(canonical, d, o, h, lo, c + offset, v, a + offset) for _s, d, o, h, lo, c, v, a in rows[:6]])
        monkeypatch.setattr(config, "DB_PATH", path)
        if label == "old":
            store = SimpleNamespace(**legacy_storage(path))
            namespace = captured("history_refresh", {"database_coverage", "restore_share_class_spelling"},
                                 {"storage": store, "pd": pd})
            coverage, restored = namespace["database_coverage"](), namespace["restore_share_class_spelling"]("2024-03-09")
        else:
            coverage, restored = history_refresh.database_coverage(), history_refresh.restore_share_class_spelling("2024-03-09")
        results.append((coverage, restored, dump(path)))
    assert results[0] == results[1]
    assert results[1][1] == {"BRK-B": {"source_symbol": "BRK.B", "dates": ["2024-03-07", "2024-03-08"]}}


def test_refresh_prices_writes_like_the_captured_facade(tmp_path, monkeypatch):
    from gabi.infrastructure.legacy import history_refresh

    download = prices_frame(6, start="2024-02-01")
    download["Stock Splits"] = [0, 0, 2.0, 0, float("nan"), 0]
    import yfinance

    fake_yf = SimpleNamespace(Ticker=lambda symbol: SimpleNamespace(history=lambda **k: download.copy()))
    monkeypatch.setattr(yfinance, "Ticker", fake_yf.Ticker)
    results = []
    for label in ("old", "new"):
        path = tmp_path / label / "gabi.db"
        with_entity(path)
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("INSERT INTO entity_aliases VALUES (?,?,?,?,?,?)", ("cik:0000000001", "AAA", "2020-01-01",
                                                                          None, "test", 1.0))
        monkeypatch.setattr(config, "DB_PATH", path)
        if label == "old":
            store = SimpleNamespace(**legacy_storage(path))
            count = captured("history_refresh", {"refresh_prices"}, {
                "storage": store, "pd": pd, "yf": fake_yf, "datetime": datetime, "UTC": UTC,
                "__package__": "gabi", "__name__": "gabi.history_refresh"})["refresh_prices"]("AAA", "AAA", "2024-02-06")
        else:
            count = history_refresh.refresh_prices("AAA", "AAA", "2024-02-06")
        results.append((count, dump(path)))
    assert results[0] == results[1]
    assert results[1][0] == 5


def test_stored_ciks_and_coverage_without_storage(tmp_path):
    from gabi.infrastructure.storage.cache_reads import SqliteCacheReads
    from gabi.infrastructure.storage.sec_reads import SqliteSecReads

    assert SqliteSecReads(tmp_path / "absent.db").stored_ciks() == {}
    coverage = SqliteCacheReads(tmp_path / "absent.db").table_coverage()
    assert coverage["prices"] == {"rows": 0, "first": None, "last": None} and coverage["macro_by_series"] == {}
    assert not (tmp_path / "absent.db").exists()
