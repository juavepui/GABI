"""Captured parity of the incremental Yahoo price sync after moving to domain/application/infrastructure."""

import json
import sqlite3
import time
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import sync_checkpoints as sync
import yfinance

from gabi import config, identity, storage
from gabi.domain.market import freshness
from gabi.infrastructure.legacy import data_fetch
from gabi.infrastructure.storage import sync_events as event_store

REFERENCE = json.loads((Path(__file__).parent / "fixtures/price_sync_migration.json").read_text(encoding="utf-8"))
NOW = datetime(2024, 1, 10, 22, tzinfo=UTC)


def panel(symbols, start="2024-01-02", end="2024-01-10", *, factor=1.0, bad=False):
    index = pd.bdate_range(start, end)
    frames = {}
    for i, symbol in enumerate(symbols):
        close = pd.Series(np.linspace(10, 11, len(index)) + i, index=index)
        frame = pd.DataFrame({"Open": close, "High": close + .5, "Low": close - .5, "Close": close,
                              "Adj Close": close * factor, "Volume": 100.})
        if bad and symbol == "B":
            frame.iloc[2, 0] = -1.
        frames[symbol] = frame
    return pd.concat(frames, axis=1) if len(symbols) > 1 else frames[symbols[0]]


def legacy_run():
    namespace = {"__name__": "captured_price_sync"}
    source = REFERENCE["price_sync"].replace("from . import identity, storage\n", "").replace(
        "from . import sync_state as sync\n", "").replace(
        "from .data_fetch import _classify_error, normalize_symbol, yf\n", "").replace(
        "from .history_refresh import last_completed_session\n", "")
    namespace.update(identity=identity, storage=storage, sync=sync, _classify_error=data_fetch._classify_error,
                     normalize_symbol=data_fetch.normalize_symbol, yf=SimpleNamespace(download=lambda *a, **k: yfinance.download(*a, **k)),
                     last_completed_session=freshness.market_date)
    exec(source, namespace)
    return namespace["run"]


def dump(path):
    with closing(sqlite3.connect(path)) as db:
        return {table: db.execute(f"SELECT * FROM {table} ORDER BY 1,2,3").fetchall()
                for table in ("prices", "sync_checkpoints") if db.execute(
                    "SELECT 1 FROM sqlite_schema WHERE name=?", (table,)).fetchone()}


def scenario_steps():
    later = NOW + timedelta(days=2)
    return [
        (lambda s, **k: panel(s), {"symbols": ["A", "B"], "now": NOW}),
        (lambda s, **k: panel(s), {"symbols": ["A", "B"], "now": NOW}),
        (lambda s, **k: panel(s, "2023-12-27", "2024-01-12"), {"symbols": ["A", "B"], "now": later, "force": True}),
        # Same closes as the previous step: only the dividend/split adjustment changes.
        (lambda s, **k: panel(s, "2023-12-27", "2024-01-12", factor=.5), {"symbols": ["A"], "now": later, "force": True}),
        (lambda s, **k: panel(s, "2024-01-03", "2024-01-12"), {"symbols": ["A"], "now": later, "full_refresh": True}),
        (lambda s, **k: panel(s, "2023-12-27", "2024-01-12", bad=True), {"symbols": ["A", "B"], "now": later, "force": True}),
        (lambda s, **k: (_ for _ in ()).throw(ValueError("No data found, symbol may be delisted")),
         {"symbols": ["C"], "now": later}),
        (lambda s, **k: "not a frame", {"symbols": ["D"], "now": later}),
    ]


def test_scenario_sequence_matches_capture(tmp_path, monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    monkeypatch.setattr(time, "perf_counter", lambda: 5.)
    monkeypatch.setattr(time, "thread_time", lambda: 1.)
    monkeypatch.setattr(identity, "resolve", lambda symbol, day: {"entity_id": None})
    fixed = SimpleNamespace(now=lambda tz=None: NOW, fromisoformat=datetime.fromisoformat)
    monkeypatch.setattr(sync, "datetime", fixed)
    monkeypatch.setattr(event_store, "datetime", fixed)
    results = []
    for label in ("old", "new"):
        path = tmp_path / label / "gabi.db"
        path.parent.mkdir()
        monkeypatch.setattr(config, "DATA_DIR", path.parent)
        monkeypatch.setattr(config, "DB_PATH", path)
        run = legacy_run() if label == "old" else data_fetch.sync_prices
        outcomes = []
        for answer, options in scenario_steps():
            calls = []
            monkeypatch.setattr(yfinance, "download", lambda tickers, **kw: calls.append((tuple(tickers), sorted(kw.items())))
                                or answer(tickers, **kw))
            options = dict(options)
            symbols = options.pop("symbols")
            outcome = run(symbols, **options)
            outcomes.append((outcome["failed"], [(e["status"], e["new"], e["revised"], e["unchanged"], e["reason"],
                                                  e["skipped"], e["payload_bytes"], e["calls"]) for e in outcome["events"]],
                             outcome["metrics"]["statuses"], calls))
        results.append((outcomes, dump(path)))
    assert results[0] == results[1]
    statuses = [step[2] for step in results[1][0]]
    assert statuses[1]["new"] == 0 and any(step[2]["failed"] for step in results[1][0])
    assert results[1][0][3][1][0][4].startswith("reparación histórica")


def test_reads_do_not_create_storage(tmp_path, monkeypatch):
    from gabi.infrastructure.storage.cache_reads import SqliteCacheReads

    reader = SqliteCacheReads(tmp_path / "absent.db")
    assert reader.adjusted_span("A") == (None, None) and reader.prices_from("A", "2024-01-01") == []
    assert not (tmp_path / "absent.db").exists()
    path = tmp_path / "old.db"
    with closing(sqlite3.connect(path)) as db:
        db.execute("CREATE TABLE prices (symbol TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL)")
        db.execute("INSERT INTO prices VALUES ('A','2024-01-02',1,1,1,1,1)")
        db.commit()
    reader = SqliteCacheReads(path)
    assert reader.adjusted_span("A") == (None, None)
    assert reader.prices_from("A", "2024-01-01") == [("2024-01-02", 1., 1., 1., 1., None, 1.)]


@pytest.mark.parametrize("latest, checkpoint, due, expected", [
    (None, {}, False, False), ("2024-01-10", {}, False, True), ("2024-01-09", {"checked_session": "2024-01-10"}, False, True),
    ("2024-01-09", {}, False, False), ("2024-01-10", {}, True, False)])
def test_skip_rule(latest, checkpoint, due, expected):
    from gabi.domain.market.price_sync import already_checked
    assert already_checked(latest, "2024-01-10", checkpoint, force=False, full_refresh=False, due=due) is expected
    assert already_checked(latest, "2024-01-10", checkpoint, force=True, full_refresh=False, due=due) is False
