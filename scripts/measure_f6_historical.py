"""Measure only F6 ranking serialization with synthetic, never reserved, data.

Usage: python scripts/measure_f6_historical.py
This does not measure the legacy point-in-time ranking computation or disk I/O.
"""

import json
import time
import tracemalloc

import numpy as np
import pandas as pd

from gabi.application.research.historical import build_historical_ranking


def main() -> None:
    count = 500
    frame = pd.DataFrame(
        {f"metric_{index}": np.linspace(0, 100, count) for index in range(60)},
        index=pd.Index([f"T{index:03d}" for index in range(count)], name="symbol"),
    )
    frame["composite_score"] = np.linspace(100, 0, count)
    frame["score_coverage"] = 0.9
    frame.iloc[0, 0] = np.nan
    tracemalloc.start()
    started = time.perf_counter()
    result = build_historical_ranking(
        "2019-01-02", lambda _as_of: {"table": frame, "universe_info": {"is_exact": True}}
    )
    raw = json.dumps(result, ensure_ascii=False, allow_nan=False).encode("utf-8")
    elapsed = time.perf_counter() - started
    peak = tracemalloc.get_traced_memory()[1] / 1_048_576
    assert result["rows"][0]["metric_0"] is None
    print(f"rows={count} columns={len(frame.columns)} bytes={len(raw)} "
          f"seconds={elapsed:.4f} python_peak_mib={peak:.3f}")


if __name__ == "__main__":
    main()
