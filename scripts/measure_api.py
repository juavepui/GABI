"""Measure the F2 ranking paths using synthetic temporary data, never data/gabi.db."""
import argparse
import gc
import json
import platform
import sqlite3
import sys
import tracemalloc
from pathlib import Path
from tempfile import TemporaryDirectory, gettempdir
from time import perf_counter

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/tests"))
from market_fixture import TODAY, seed_fixture  # noqa: E402

from gabi import app_mode, config, screener  # noqa: E402
from gabi.domain.market.selection import RankingFilter  # noqa: E402
from gabi.infrastructure.settings import Settings  # noqa: E402
from gabi_api.bootstrap import create_app  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--companies", type=int, default=500)
    parser.add_argument("--sessions", type=int, default=1250)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 1 <= args.companies <= 996 or not 253 <= args.sessions <= 5000:
        parser.error("companies: 1..996; sessions: 253..5000")
    with TemporaryDirectory(prefix="gabi-api-measure-") as temporary:
        root = Path(temporary).resolve()
        assert root.is_relative_to(Path(gettempdir()).resolve())
        assert root.name.startswith("gabi-api-measure-")
        universe = seed_fixture(root, args.companies, args.sessions)
        previous_data = config.DATA_DIR
        previous = {name: value for name, value in vars(config).items()
                    if isinstance(value, Path) and value.is_relative_to(previous_data)}
        for name, value in previous.items():
            setattr(config, name, root / value.relative_to(previous_data))
        statements: list[str] = []
        connect = sqlite3.connect

        def observed_connect(*positional, **kwargs):
            connection = connect(*positional, **kwargs)
            connection.set_trace_callback(statements.append)
            return connection

        sqlite3.connect = observed_connect
        app = create_app(Settings(root), today=lambda: TODAY)
        repository = app.state.market.repository

        def measure(operation):
            gc.collect()
            statements.clear()
            prior_rows = repository.row_count
            tracemalloc.start()
            started = perf_counter()
            result = operation()
            elapsed = perf_counter() - started
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            return result, {"seconds": round(elapsed, 4), "peak_python_mib": round(peak / 1024**2, 3),
                            "sql_statements": len(statements),
                            "select_queries": sum(statement.lstrip().upper().startswith("SELECT") for statement in statements),
                            "adapter_rows_returned": repository.row_count - prior_rows}

        try:
            legacy, baseline = measure(lambda: screener.build_screener_table(universe, app_mode.FROZEN_WEIGHTS))
            cold, cold_measure = measure(lambda: app.state.market.ranking(RankingFilter(hide_no_data=False)))
            warm, warm_measure = measure(lambda: app.state.market.ranking(RankingFilter(hide_no_data=False)))
            pd.testing.assert_frame_equal(legacy, cold.snapshot.table)
            pd.testing.assert_frame_equal(legacy, warm.snapshot.table)
            price_rows = (args.companies + 3) * args.sessions + 5
            baseline["adapter_rows_returned"] = None  # This counter exists only on the new adapter.
            report = {"python": platform.python_version(), "platform": platform.system(), "fixture_seed": 64,
                      "companies": len(universe), "sessions": args.sessions, "price_rows_including_benchmark": price_rows,
                      "rows_and_all_metrics_equal": True,
                      "memory_scope": "tracemalloc Python allocations; excludes native allocations and total process RSS",
                      "cold_scope": "empty process ranking cache; OS file cache not controlled; no HTTP serialization",
                      "legacy_streamlit": baseline, "api_cold": cold_measure, "api_warm": warm_measure}
            rendered = json.dumps(report, indent=2) + "\n"
            if args.output:
                args.output.write_text(rendered, encoding="utf-8")
            print(rendered)
        finally:
            repository.close()
            sqlite3.connect = connect
            for name, value in previous.items():
                setattr(config, name, value)


if __name__ == "__main__":
    main()
