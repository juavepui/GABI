"""The whole research data refresh against the captured flat module (F7.28), with synthetic sources."""

import json
import sqlite3
import sys
from contextlib import closing
from datetime import UTC, date, datetime
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

from gabi import config, edgar, identity, storage, universe
from gabi.infrastructure.legacy import data_fetch
from gabi.infrastructure.legacy import history_refresh as bridge
from gabi.infrastructure.providers import yahoo
from gabi.infrastructure.providers.fred import FredSource
from gabi.infrastructure.providers.sp500_sources import SP500Sources
from gabi.membership_extension import fingerprint

REFERENCE = json.loads((Path(__file__).parent / "fixtures/history_refresh_migration.json").read_text(encoding="utf-8"))
NOW = datetime(2025, 9, 24, 21, 30, tzinfo=UTC)


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz else NOW.replace(tzinfo=None)


class FixedDate(date):
    @classmethod
    def today(cls):
        return NOW.date()


def captured(monkeypatch) -> ModuleType:
    # It imported the flat data_fetch retired in F7.30; the bridge keeps its names.
    monkeypatch.setitem(sys.modules, "gabi.data_fetch", data_fetch)
    module = ModuleType("gabi.history_refresh")
    module.__package__ = "gabi"
    exec(compile(REFERENCE["history_refresh"], "captured_history_refresh.py", "exec"), module.__dict__)
    return module


def prices(start: str, periods: int, splits: bool = False) -> pd.DataFrame:
    index = pd.bdate_range(start, periods=periods)
    frame = pd.DataFrame({"Open": 10., "High": 11., "Low": 9., "Close": 10., "Adj Close": 9.5, "Volume": 1e3},
                         index=index)
    if splits:
        frame["Stock Splits"] = [0.] * (periods - 1) + [2.]
    return frame


def workspace(root: Path, monkeypatch) -> tuple[Path, Path]:
    root.mkdir(parents=True)
    for name, value in (("DATA_DIR", root), ("DB_PATH", root / "gabi.db"), ("SP500_CACHE", root / "sp500.csv")):
        monkeypatch.setattr(config, name, value)
    monkeypatch.setattr(universe, "HISTORICAL_MEMBERSHIP_CACHE", root / "membership.csv")
    monkeypatch.setattr(edgar, "CIK_CACHE", root / "cik.csv")
    pd.DataFrame([("2025-08-23", "AAA,BBB")], columns=["date", "tickers"]).to_csv(root / "membership.csv", index=False)
    (root / "cik.csv").write_text("symbol,cik\nBBB,2\n", encoding="utf-8")
    resources = root / "resources"
    resources.mkdir()
    ledger = resources / "ledger.json"
    ledger.write_text(json.dumps({
        "anchor_date": "2025-08-23", "anchor_sha256": fingerprint({"AAA", "BBB"}), "verified_through": "2025-09-24",
        "endpoint_symbols": ["BBB", "CCC"],
        "events": [{"effective_date": "2025-09-22", "removed": "AAA", "added": "CCC", "kind": "ticker_change",
                    "source_url": "https://example.com/announcement"}]}), encoding="utf-8")
    (resources / "former_issuers_2025_2026.json").write_text(json.dumps({"AAA": {"cik": "9"}}), encoding="utf-8")
    storage.init_db()
    with closing(sqlite3.connect(root / "gabi.db")) as db, db:
        db.executemany("INSERT INTO prices (symbol,date,open,high,low,close,volume,adj_close) VALUES (?,?,?,?,?,?,?,?)",
                       [("SPY", day.strftime("%Y-%m-%d"), 1., 1., 1., 1., 1., 1.)
                        for day in pd.bdate_range("2025-09-01", "2025-09-24")])
    return ledger, root


def dump(path: Path) -> dict:
    with closing(sqlite3.connect(path)) as db:
        tables = sorted(n for n, in db.execute("SELECT name FROM sqlite_schema WHERE type='table'"))
        return {t: sorted(map(repr, db.execute(f"SELECT * FROM {t}").fetchall())) for t in tables}


@pytest.fixture
def sources(monkeypatch):
    calls = []

    def history(symbol, **options):
        calls.append(("history", symbol, sorted(options.items())))
        if symbol == "BBB":
            raise ValueError("No data found, symbol may be delisted")
        return prices("2025-09-15", 8, splits=symbol == "CCC")

    def fred(self, sid, key, units, limit, **options):
        calls.append(("fred", sid, key, units, limit, sorted(options.items())))
        if sid == "DGS10":
            raise RuntimeError(f"timeout https://fred/?api_key={key}")
        return [("2025-09-01", 1.0)]

    monkeypatch.setattr(yahoo, "history", history)
    monkeypatch.setattr(yahoo, "use_timezone_cache", lambda directory: calls.append(("tz", directory.name)))
    monkeypatch.setattr(identity, "resolve", lambda symbol, day: {"entity_id": None})
    monkeypatch.setattr(SP500Sources, "wikipedia_page", lambda self: b"<html>current</html>")
    monkeypatch.setattr(SP500Sources, "wikipedia_tables", staticmethod(lambda page: [pd.DataFrame({"raw": [1]})]))
    monkeypatch.setattr(universe, "_normalize", lambda raw: pd.DataFrame({"symbol": ["BBB", "CCC"], "name": ["B", "C"]}))
    monkeypatch.setattr(edgar, "get_cik_map", lambda force_refresh=False: pd.DataFrame(
        {"symbol": ["BBB", "CCC"], "cik": ["2", "3"], "title": ["B", "C"]}))

    def edgar_batch(symbols, ciks, max_workers, progress_cb, incremental):
        calls.append(("edgar", symbols, sorted(ciks.items()), max_workers, incremental))
        for done, symbol in enumerate(symbols, 1):
            progress_cb(done, len(symbols), symbol)
        return {"CCC": "SEC no responde"}

    monkeypatch.setattr(edgar, "fetch_edgar_batch", edgar_batch)
    monkeypatch.setattr(data_fetch, "fetch_fundamentals_batch",
                        lambda symbols, max_workers: calls.append(("fundamentals", symbols, max_workers)) or {"CCC": "x"})
    monkeypatch.setattr(FredSource, "fetch", fred)
    monkeypatch.setattr(config, "load_fred_key", lambda: "secret")
    return calls


def test_refresh_matches_the_captured_module(tmp_path, monkeypatch, sources, capsys):
    results = []
    for label in ("old", "new"):
        ledger, root = workspace(tmp_path / label, monkeypatch)
        sources.clear()
        if label == "old":
            module = captured(monkeypatch)
            module.datetime, module.date, module.LEDGER_PATH = FixedDatetime, FixedDate, ledger
            run = module.run
        else:
            monkeypatch.setattr(bridge, "datetime", FixedDatetime)
            monkeypatch.setattr(bridge, "date", FixedDate)
            monkeypatch.setattr(bridge, "LEDGER_PATH", ledger)
            run = bridge.run
        report = run()
        directory = root / "history_refresh" / "20250924T213000"
        files = sorted(p.relative_to(directory).as_posix() for p in directory.iterdir())
        def text(value: str, root: Path = root) -> str:  # the two run folders, plain and JSON-escaped
            return value.replace(json.dumps(str(root))[1:-1], "<root>").replace(str(root), "<root>")

        results.append((text(json.dumps(report, sort_keys=True)), text((directory / "report.json").read_text("utf-8")),
                        files, (root / "membership.csv").read_text("utf-8"), (root / "sp500.csv").read_text("utf-8"),
                        dump(root / "gabi.db"), list(sources), text(capsys.readouterr().out)))
    for index, (old, new) in enumerate(zip(*results, strict=True)):
        assert old == new, index
    report = json.loads(results[1][0])
    assert report["identity_unresolved"] == {"AAA": "Stored CIK differs from live issuer; requires identity review"}
    assert set(report["prices"]["updated"]) == {"CCC"} and set(report["prices"]["failed"]) == {"BBB"}
    assert report["macro"]["failed"]["DGS10"] == "FRED download failed; API key omitted from log"
    assert "secret" not in results[1][1]


def test_refresh_requires_the_ledger_reviewed_through_today(tmp_path, monkeypatch, sources):
    ledger, root = workspace(tmp_path / "late", monkeypatch)
    monkeypatch.setattr(bridge, "LEDGER_PATH", ledger)
    with pytest.raises(ValueError, match="through today"):
        bridge.run()
    assert not (root / "history_refresh").exists()
