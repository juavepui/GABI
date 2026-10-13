"""Synthetic parity and timing of the point-in-time ranking and data fingerprint, captured versus migrated."""

import json
import statistics
import sys
import tempfile
import time
from pathlib import Path
from types import ModuleType

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
SYMBOLS = 120
REPEATS = 3
DAY = "2019-06-03"


def captured(reference: dict, name: str, anchor: Path) -> ModuleType:
    module = ModuleType(f"gabi.{name}")
    module.__package__, module.__file__ = "gabi", str(anchor.with_name(f"{name}.py"))
    exec(reference[name], module.__dict__)
    return module


def median(function) -> tuple[object, float]:
    samples, result = [], None
    for _ in range(REPEATS):
        began = time.perf_counter()
        result = function()
        samples.append(time.perf_counter() - began)
    return result, round(statistics.median(samples), 4)


def main():
    from gabi import config, data_quality, edgar, identity, screener_asof, storage

    reference = json.loads((ROOT / "backend/tests/fixtures/ranking_quality_migration.json").read_text(encoding="utf-8"))
    anchor = Path(screener_asof.__file__)
    for name in ("capital_allocation", "valuation_expectations", "quality_persistence", "broker_costs", "rotation_policy"):
        sys.modules[f"gabi.{name}"] = captured(reference, name, anchor)
    old = {name: captured(reference, name, anchor) for name in ("screener_asof", "data_quality")}
    symbols = [f"S{i:03d}" for i in range(SYMBOLS)]
    index = pd.bdate_range("2018-01-02", periods=400)
    with tempfile.TemporaryDirectory(prefix="gabi-ranking-") as directory:
        config.DATA_DIR, config.DB_PATH = Path(directory), Path(directory) / "gabi.db"
        storage.init_db()
        rng = np.random.default_rng(7)
        for position, symbol in enumerate([*symbols, "SPY"]):
            close = 20 * np.cumprod(1 + rng.normal(0.0004, 0.01, len(index)))
            frame = pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close, "Adj Close": close,
                                  "Volume": 1e6}, index=index)
            # Half the issuers carry a registered alias; the rest are read from the ticker cache.
            entity = identity.ensure_entity(str(position + 1)) if position % 2 == 0 and symbol != "SPY" else None
            if entity:
                identity.add_alias(entity, symbol, "2000-01-01", source="synthetic")
            storage.upsert_prices(symbol, frame, entity_id=entity)
            if symbol != "SPY":
                rows = [{"tag": tag, "unit": unit, "start_date": "2018-01-01" if unit == "USD" and tag != "StockholdersEquity" else "",
                         "end_date": "2018-12-31", "val": float(value), "form": "10-K", "fp": "FY", "fy": 2018,
                         "filed_date": "2019-02-01", "accn": f"{symbol}-{tag}"}
                        for tag, unit, value in (("Revenues", "USD", rng.integers(500, 5000)),
                                                 ("NetIncomeLoss", "USD", rng.integers(-50, 500)),
                                                 ("StockholdersEquity", "USD", rng.integers(100, 2000)),
                                                 ("CommonStockSharesOutstanding", "shares", rng.integers(50, 500)))]
                edgar.upsert_edgar_facts(symbol, rows, cik=str(position + 1) if entity else None)
        results = {}
        expected, results_old = median(lambda: old["screener_asof"].build_ranking_as_of(DAY, symbols=symbols))
        actual, results_new = median(lambda: screener_asof.build_ranking_as_of(DAY, symbols=symbols))
        pd.testing.assert_frame_equal(actual["table"], expected["table"])
        results["ranking_s"] = {"anterior": results_old, "nuevo": results_new}
        before, old_time = median(lambda: old["data_quality"].compute_data_fingerprint(symbols))
        after, new_time = median(lambda: data_quality.compute_data_fingerprint(symbols))
        assert before == after
        results["fingerprint_s"] = {"anterior": old_time, "nuevo": new_time}
    print(json.dumps({"symbols": SYMBOLS, "sessions": len(index), "parity": True, "downloads": 0,
                      "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
