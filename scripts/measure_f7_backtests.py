"""Timing of the V1/V2 backtests, captured versus explicit inputs, on the synthetic parity market (#132).

Usage: .venv/Scripts/python.exe scripts/measure_f7_backtests.py
No network and no data directory: every source is the in-memory market of the parity test.
"""

import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "backend/tests")]
REPEATS = 25
ARGS = ("2021-01-04", "2023-01-04")


def timed(call) -> float:
    call()
    values = []
    for _ in range(REPEATS):
        start = time.perf_counter()
        call()
        values.append(time.perf_counter() - start)
    return statistics.median(values)


def main() -> None:
    import test_backtest_inputs_migration as parity
    from _pytest.monkeypatch import MonkeyPatch

    from gabi import data_quality, historical_pit, identity, screener_asof, universe

    patches = MonkeyPatch()
    patches.setattr(universe, "get_sp500_constituents_asof", parity.membership)
    patches.setattr(screener_asof, "build_ranking_as_of",
                    lambda as_of, symbols: {"table": parity.ranking(as_of, symbols)})
    patches.setattr(data_quality, "ranking_quality", parity.quality)
    patches.setattr(identity, "backtest_prices", parity.prices)
    patches.setattr(identity, "last_filings", lambda symbols, as_of: parity.last_filings(symbols, as_of))
    patches.setattr(identity, "resolve", lambda symbol, as_of: {"entity_id": f"cik:{symbol}"})
    patches.setattr(historical_pit, "exit_value", parity.exit_value)
    old_v1 = parity.captured("multifactor_backtest")
    old_v2 = parity.captured("portfolio_backtest", v1=old_v1)
    try:
        for label, call in [("V1 anterior", lambda: old_v1.run(*ARGS, top_n=5)),
                            ("V1 nuevo", lambda: parity.v1.run(*ARGS, top_n=5)),
                            ("V2 anterior", lambda: old_v2.run(*ARGS, top_n=4)),
                            ("V2 nuevo", lambda: parity.v2.run(*ARGS, top_n=4))]:
            print(f"{label}: {timed(call):.4f} s")
    finally:
        patches.undo()


if __name__ == "__main__":
    main()
