"""Synthetic parity and timing of the Tiingo pinned-file read and SEC cover coordination, captured versus migrated."""

import ast
import json
import sqlite3
import statistics
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import closing, contextmanager
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
PINNED = 5000
CANDIDATES = 400
REPEATS = 20


def captured(module: str, names: set[str], namespace: dict) -> dict:
    reference = json.loads((ROOT / "backend/tests/fixtures/historical_audits_migration.json").read_text(encoding="utf-8"))
    for node in ast.parse(reference[module]).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names:
            exec(ast.get_source_segment(reference[module], node), namespace)
    return namespace


def timed(function: Callable[[], object]) -> tuple[object, float]:
    samples, result = [], None
    for _ in range(REPEATS):
        began = time.perf_counter()
        result = function()
        samples.append(time.perf_counter() - began)
    return result, round(statistics.median(samples), 6)


def connections(path: Path):
    @contextmanager
    def get_connection():
        with closing(sqlite3.connect(path, timeout=30)) as db:
            yield db
    return get_connection


def main():
    import requests

    from gabi import config, historical_tiingo
    from gabi.domain.market.identity import normalize_cik
    from gabi.infrastructure.legacy import historical_identity_audit, sec_history
    from gabi.infrastructure.storage import historical_prices

    results = {}
    with tempfile.TemporaryDirectory(prefix="gabi-historical-audits-") as directory:
        root = Path(directory)
        path = root / "gabi.db"
        with closing(sqlite3.connect(path)) as db:
            db.executescript(historical_prices.SCHEMA)
            db.execute("INSERT INTO historical_sources VALUES (?,?)",
                       ("tiingo", json.dumps({"files_sha256": {f"S{i}": f"{i:064x}" for i in range(PINNED)}})))
            db.executescript("""
                CREATE TABLE historical_issuer_candidates (source_id TEXT, symbol TEXT, cik TEXT, name TEXT,
                    date_added TEXT, date_removed TEXT, observed_from TEXT);
                CREATE TABLE historical_identity_intervals (source_id TEXT, symbol TEXT, cik TEXT, valid_from TEXT,
                    valid_to TEXT, status TEXT);
                CREATE TABLE sec_bulk_submissions (accn TEXT, cik TEXT, name TEXT, sic TEXT, form TEXT,
                    filed_date TEXT, period TEXT, fy TEXT, fp TEXT, instance TEXT, source_url TEXT);
            """)
            source = historical_identity_audit.CANDIDATE_SOURCE
            db.executemany("INSERT INTO historical_issuer_candidates VALUES (?,?,?,?,?,?,?)",
                           [(source, f"S{i}", str(i), "n", "2010-01-01", None, "2010-01-01") for i in range(1, CANDIDATES + 1)])
            db.executemany("INSERT INTO sec_bulk_submissions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                           [(f"{i}-{year}", f"{i:010d}", "n", "", "10-K", f"{year}-03-01", "", str(year), "FY",
                             "i.xml", "src") for i in range(1, CANDIDATES + 1) for year in range(2010, 2016)])
            db.commit()
        config.DB_PATH = path
        old_archive = captured("historical_tiingo", {"_Archive"}, {
            "json": json, "storage": SimpleNamespace(get_connection=connections(path)),
            "historical_archive": SimpleNamespace(SCHEMA=historical_prices.SCHEMA)})["_Archive"]()
        old, old_time = timed(lambda: old_archive.pinned("tiingo"))
        new, new_time = timed(lambda: historical_tiingo._Archive().pinned("tiingo"))
        assert old == new and len(new) == PINNED
        results["pinned_tiingo_median_s"] = {"anterior": old_time, "nuevo": new_time}

        clock = SimpleNamespace(monotonic=lambda: 0.0, sleep=lambda seconds: None)
        reports = {}
        for label in ("anterior", "nuevo"):
            config.DATA_DIR = root / label

            def download(url, target):
                Path(target).parent.mkdir(parents=True, exist_ok=True)
                Path(target).write_bytes(b"cover")
                return target

            if label == "anterior":
                function = captured("historical_identity_audit", {"fetch_candidate_instances"}, {
                    "storage": SimpleNamespace(get_connection=connections(path)),
                    "sec_history": SimpleNamespace(download=download), "identity_nominations": lambda: (),
                    "identity": SimpleNamespace(normalize_cik=normalize_cik), "CANDIDATE_SOURCE": source,
                    "P2010": None, "Period": object, "date": date, "timedelta": timedelta, "Path": Path,
                    "_date": historical_identity_audit._date, "config": config, "time": clock,
                    "threading": threading, "requests": requests, "ThreadPoolExecutor": ThreadPoolExecutor,
                    "as_completed": as_completed})["fetch_candidate_instances"]
            else:
                historical_identity_audit.time = clock
                historical_identity_audit.identity_nominations = lambda: ()
                sec_history.download = download
                function = historical_identity_audit.fetch_candidate_instances
            period = SimpleNamespace(start="2010-01-01", end_exclusive="2016-01-01", identity_source="hist")
            began = time.perf_counter()
            reports[label] = function(CANDIDATES * 3, period=period)
            first = time.perf_counter() - began
            cached = []
            for _ in range(5):
                began = time.perf_counter()
                function(CANDIDATES * 3, period=period)
                cached.append(time.perf_counter() - began)
            results.setdefault("covers_s", {})[label] = {"primera": round(first, 4),
                                                       "ya_en_cache_mediana_5": round(statistics.median(cached), 4)}
        assert reports["anterior"] == reports["nuevo"]
    print(json.dumps({"pinned_files": PINNED, "candidates": CANDIDATES, "covers": reports["nuevo"]["fetched"],
                      "parity": True, "downloads": 0, "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
