"""Synthetic parity and timing of the incremental Yahoo price sync, captured versus migrated (no network)."""

import json
import sqlite3
import statistics
import sys
import tempfile
import time
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
SYMBOLS = 100
NOW = datetime(2024, 1, 10, 22, tzinfo=UTC)


def main():
    import yfinance

    from gabi import config, data_fetch, history_refresh, identity, storage
    from gabi import sync_state as sync

    reference = json.loads((ROOT / "backend/tests/fixtures/price_sync_migration.json").read_text(encoding="utf-8"))
    symbols = [f"S{i}" for i in range(SYMBOLS)]
    index = pd.bdate_range("2022-01-03", "2024-01-10")
    close = pd.Series(np.linspace(10, 20, len(index)), index=index)
    frame = pd.DataFrame({"Open": close, "High": close + 1, "Low": close - 1, "Close": close, "Adj Close": close,
                          "Volume": 1e3})
    yfinance.download = lambda tickers, **k: pd.concat({t: frame for t in tickers}, axis=1)
    identity.resolve = lambda symbol, day: {"entity_id": None}
    time.sleep = lambda seconds: None
    source = reference["price_sync"]
    for line in ("from . import identity, storage\n", "from . import sync_state as sync\n",
                 "from .data_fetch import _classify_error, normalize_symbol, yf\n",
                 "from .history_refresh import last_completed_session\n"):
        source = source.replace(line, "")
    namespace = {"__name__": "captured_price_sync", "identity": identity, "storage": storage, "sync": sync,
                 "_classify_error": data_fetch._classify_error, "normalize_symbol": data_fetch.normalize_symbol,
                 "yf": SimpleNamespace(download=lambda *a, **k: yfinance.download(*a, **k)),
                 "last_completed_session": history_refresh.last_completed_session}
    exec(source, namespace)
    rows = {}
    with tempfile.TemporaryDirectory(prefix="gabi-price-sync-") as directory:
        tables = []
        for label, run in (("anterior", namespace["run"]), ("nuevo", data_fetch.sync_prices)):
            path = Path(directory) / label / "gabi.db"
            path.parent.mkdir()
            config.DATA_DIR, config.DB_PATH = path.parent, path
            began = time.perf_counter()
            run(symbols, now=NOW)
            first = time.perf_counter() - began
            skipped = []
            for _ in range(3):
                began = time.perf_counter()
                run(symbols, now=NOW)
                skipped.append(time.perf_counter() - began)
            with closing(sqlite3.connect(path)) as db:
                tables.append(db.execute("SELECT * FROM prices ORDER BY symbol,date").fetchall())
            rows[label] = {"first_load_s": round(first, 4), "skipped_session_median_s": round(statistics.median(skipped), 4)}
        assert tables[0] == tables[1]
    print(json.dumps({"symbols": SYMBOLS, "sessions": len(index), "parity": True, "downloads": 0, "results": rows},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
