"""Offline, repeatable comparison; measures payload estimates, never wire bytes."""

import argparse
import json
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "src"))

import exchange_calendars as xcals
import pandas as pd

from gabi import config, data_fetch, price_sync, storage
from gabi import sync_state as sync


def benchmark(output: Path) -> dict:
    output.parent.mkdir(parents=True, exist_ok=True)
    symbols = [f"S{i:03d}" for i in range(20)]
    dates = xcals.get_calendar("XNYS").sessions_window(pd.Timestamp("2024-01-10"), -503).tz_localize(None)
    panel = pd.DataFrame({"Open": 10., "High": 10., "Low": 10., "Close": 10., "Adj Close": 10., "Volume": 100.}, index=dates)
    now = datetime(2024, 1, 10, 22, tzinfo=UTC)
    rows = []
    with tempfile.TemporaryDirectory(prefix="gabi-sync-", dir=output.parent) as temporary:
        root = Path(temporary).resolve()
        assert root.is_relative_to(output.parent.resolve())
        for variant in ("previous_full_window", "incremental", "repeat_same_session"):
            db = root / ("previous.db" if variant == "previous_full_window" else "incremental.db")
            count = {"yfinance_invocations": 0, "returned_rows": 0, "payload_bytes": 0}

            def download(tickers, **kwargs):
                selected = panel.loc[panel.index >= pd.Timestamp(kwargs["start"])] if "start" in kwargs else panel
                count["yfinance_invocations"] += 1
                count["returned_rows"] += len(selected) * len(tickers)
                count["payload_bytes"] += sum(len(selected.to_csv().encode()) for _ in tickers)
                return pd.concat({s: selected for s in tickers}, axis=1)

            with patch.multiple(config, DATA_DIR=root, DB_PATH=db), patch.object(data_fetch.yf, "download", download), \
                    patch.object(sync, "_pace", lambda *_: None):
                storage.init_db()
                if variant != "repeat_same_session":
                    for symbol in symbols:
                        storage.upsert_prices(symbol, panel.iloc[:-4])
                with storage.get_connection() as conn:
                    before = conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
                start, cpu = time.perf_counter(), time.process_time()
                if variant == "previous_full_window":
                    failed = data_fetch.fetch_prices_batch(symbols)
                    changed_rows = len(panel) * len(symbols)
                else:
                    result = price_sync.run(symbols, now=now)
                    failed = result["failed"]
                    changed_rows = result["metrics"]["new"] + result["metrics"]["revised"]
                elapsed, cpu_elapsed = time.perf_counter() - start, time.process_time() - cpu
                with storage.get_connection() as conn:
                    after = conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
                rows.append({"variant": variant, **count, "seconds": elapsed, "cpu_seconds": cpu_elapsed,
                             "rows_written": changed_rows, "actually_new_rows": after - before, "failed": failed})
        result = {"method": f"offline provider fixture: 20 symbols, {len(panel)} XNYS sessions, 4 new sessions; independent databases",
                  "limitations": "No network: timings measure local processing only. Payload bytes are per-ticker CSV estimates. "
                                 "yfinance invocations are not underlying HTTP requests; its internal traffic is not observed.",
                  "results": rows}
        output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("docs/incremental-updates/benchmark.json"))
    args = parser.parse_args()
    print(json.dumps(benchmark(args.output), indent=2))
