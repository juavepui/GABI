"""Synthetic parity and timing of the Research Lab log and blind validation reads, captured versus migrated."""

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
EXPERIMENTS = 2000
PERIODS = 40
REPEATS = 5


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
    from gabi import config, research_lab, screener_asof, storage
    from gabi.infrastructure.legacy import blind_validation

    reference = json.loads((ROOT / "backend/tests/fixtures/research_ledgers_migration.json").read_text(encoding="utf-8"))
    research_lab._current_git_commit = lambda: "abc1234"
    old_lab = captured(reference, "research_lab", Path(research_lab.__file__))
    old_blind = captured(reference, "blind_validation", Path(research_lab.__file__))
    rng = np.random.default_rng(3)
    index = pd.bdate_range("2016-01-01", periods=240)
    results = {}
    with tempfile.TemporaryDirectory(prefix="gabi-research-") as directory:
        config.DATA_DIR, config.DB_PATH = Path(directory), Path(directory) / "gabi.db"
        storage.init_db()
        for number in range(EXPERIMENTS):
            research_lab.log_experiment(f"M{number % 7}", ("RESEARCH", "IN_SAMPLE", "LIVE_FORWARD")[number % 3], True,
                                        family=f"f{number % 25}", sharpe=float(rng.normal()),
                                        returns=pd.Series(rng.normal(0, .01, len(index)), index=index))
        values = [100.0 + i for i in range(PERIODS * 7)]
        dates = pd.date_range("2023-01-01", periods=len(values), freq="D")
        for symbol in ("A", "B", "SPY"):
            storage.upsert_prices(symbol, pd.DataFrame({"Open": values, "High": values, "Low": values, "Close": values,
                                                        "Adj Close": values, "Volume": 1e6}, index=dates))
        screener_asof.build_ranking_as_of = lambda day, symbols=None, weights=None: {"table": pd.DataFrame(
            {"composite_score": [90.0, 80.0], "score_coverage": [.9, .9]}, index=["A", "B"])}
        vid = blind_validation.create_validation("V", {"value": 1.0}, 2, 1, "2023-01-01", "2023-06-01")
        for period in range(PERIODS):
            blind_validation.record_rebalance(vid, dates[period * 7].date().isoformat())
        for label, function_old, function_new in (
                ("listar_experimentos", old_lab.list_experiments, research_lab.list_experiments),
                ("detalle_experimento", lambda: old_lab.get_experiment(EXPERIMENTS // 2),
                 lambda: research_lab.get_experiment(EXPERIMENTS // 2)),
                ("estado_validacion", lambda: old_blind.get_status(vid), lambda: blind_validation.get_status(vid))):
            before, old_time = median(function_old)
            after, new_time = median(function_new)
            if isinstance(before, pd.DataFrame):
                pd.testing.assert_frame_equal(after, before)
            elif isinstance(before, dict) and isinstance(before.get("returns"), pd.Series):
                pd.testing.assert_series_equal(after.pop("returns"), before.pop("returns"))
                assert after == before
            else:
                assert after == before
            results[label] = {"anterior": old_time, "nuevo": new_time}
    print(json.dumps({"experiments": EXPERIMENTS, "returns_per_experiment": len(index), "blind_periods": PERIODS,
                      "parity": True, "downloads": 0, "results_s": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
