"""Original Factor Lab reference metrics on a fixed, synthetic observation window."""

import json
from copy import deepcopy
from datetime import date
from pathlib import Path

import exchange_calendars as xcals
import numpy as np
import pandas as pd
import pytest

from gabi import config, storage
from gabi.application.administration.jobs import JobCommand
from gabi.application.research.factor_engine import run_factor_analysis
from gabi.domain.research import factors
from gabi.infrastructure.legacy.jobs import LegacyExecutor
from gabi.infrastructure.settings import Settings

TODAY = date(2024, 6, 30)
CASES = ("normal", "ties", "absent_sector", "partial_sector", "missing_exit", "insufficient", "inexact")


class MemoryFactorInputs:
    def __init__(self, case):
        self.case, self.windows = case, []
        self.symbols = [f"S{i:02}" for i in range(20)]
        dates = pd.bdate_range("2024-01-01", "2024-04-10")
        self.histories = {symbol: pd.DataFrame({"adj_close": [100 + i * .2 + j * (.02 + i * .002)
                                                           + .1 * np.sin(j / 3 + i) for j in range(len(dates))]}, index=dates)
                          for i, symbol in enumerate(self.symbols)}
        if case == "missing_exit":
            self.histories["S00"] = self.histories["S00"].drop(pd.Timestamp("2024-02-02"))

    def membership(self, as_of):
        return {"symbols": self.symbols, "is_exact": self.case != "inexact", "note": "synthetic inexact membership"}

    @staticmethod
    def sample(symbols, maximum):
        return list(symbols)

    def ranking(self, as_of, symbols):
        scores = np.arange(len(symbols), dtype=float)
        if as_of == "2024-02-02":
            scores = np.roll(scores, 5)
        if self.case == "ties":
            scores = np.repeat([10., 30.], 10)
        frame = pd.DataFrame({"composite_score": scores, "score_coverage": .9,
                              "sector": ["Tech" if i < 10 else "Energy" for i in range(len(symbols))]}, index=symbols)
        if self.case == "absent_sector":
            frame = frame.drop(columns="sector")
        elif self.case == "partial_sector":
            frame.loc["S00", "sector"] = None
        elif self.case == "insufficient":
            frame.loc[frame.index[5:], "composite_score"] = np.nan
        return frame

    def prices(self, symbols, first, last):
        self.windows.append((list(symbols), first, last))
        return {symbol: self.histories[symbol].loc[first:last] for symbol in symbols}


def run_memory(case, today=TODAY):
    inputs = MemoryFactorInputs(case)
    result = run_factor_analysis("2024-01-02", "2024-03-02", inputs=inputs, today=today, months=1,
                                 factor_cols=("composite_score",), horizons_months=(1,), n_quantiles=5)
    return inputs, result


@pytest.mark.parametrize("case", CASES)
def test_factor_tables_match_original_reference(case):
    reference = json.loads((Path(__file__).parent / "fixtures/factor_migration.json").read_text(encoding="utf-8"))
    _, result = run_memory(case)
    for name in ("summary", "ic_series", "quantile_returns", "turnover"):
        # JSON serialization is also the published artifact's missing-value convention.
        actual = json.loads(result[name].to_json(orient="split", double_precision=15))
        expected = reference[case][name]
        assert actual["columns"] == expected["columns"] and actual["index"] == expected["index"]
        assert len(actual["data"]) == len(expected["data"])
        for observed, old in zip(actual["data"], expected["data"], strict=True):
            for value, old_value in zip(observed, old, strict=True):
                if isinstance(old_value, float):
                    assert value == pytest.approx(old_value, rel=1e-12, abs=1e-14)
                else:
                    assert value == old_value
    assert result["skipped"] == reference[case]["skipped"] and result["mode"] == reference[case]["mode"]


def test_explicit_observation_day_and_exact_price_windows():
    inputs, result = run_memory("normal")
    assert [window[1:] for window in inputs.windows] == [("2024-01-03", "2024-02-02"), ("2024-02-05", "2024-03-04")]
    assert result["ic_series"]["fecha"].tolist() == ["2024-01-02", "2024-02-02"]
    _, early = run_memory("normal", date(2024, 3, 2))
    assert early["ic_series"]["fecha"].tolist() == ["2024-01-02"]
    with pytest.raises(ValueError, match="hoy"):
        run_memory("normal", date(2024, 2, 1))


def test_domain_does_not_mutate_inputs_or_access_storage_network(monkeypatch):
    inputs = MemoryFactorInputs("normal")
    eligible = inputs.ranking("2024-01-02", inputs.symbols)
    before = eligible.copy(deep=True)
    state = {"composite_score": {1: {"previous"}}}
    previous = deepcopy(state)
    calendar = xcals.get_calendar("XNYS")
    monkeypatch.setattr(storage, "get_connection", lambda: pytest.fail("Domain accessed SQLite"))
    monkeypatch.setattr("requests.sessions.Session.request", lambda *a, **k: pytest.fail("Domain accessed network"))
    factors.analyze_period(eligible, inputs.histories, pd.Timestamp("2024-01-02"), calendar=calendar,
                           today=TODAY, factor_cols=("composite_score",), horizons_months=(1,),
                           previous_quantile_members=state)
    pd.testing.assert_frame_equal(eligible, before)
    assert state == previous


def test_factor_job_passes_injected_observation_day(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)

    def fake_run(start, end, **options):
        calls.append((start, end, options))
        return {"summary": pd.DataFrame(), "ic_series": pd.DataFrame(), "quantile_returns": pd.DataFrame(),
                "turnover": pd.DataFrame(), "skipped": []}

    monkeypatch.setattr("gabi.infrastructure.legacy.factors.run_factors", fake_run)
    executor = LegacyExecutor(Settings(tmp_path), today=lambda: TODAY)
    result = executor(JobCommand("factor_analysis", start="2024-01-02", end="2024-03-02", factor_months=1,
                                 factor_mode="validation"))
    assert result["kind"] == "factor_analysis"
    assert calls[0][2]["today"] == TODAY and calls[0][2]["data_dir"] == tmp_path
