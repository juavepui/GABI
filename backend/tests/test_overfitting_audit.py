import json
import sys
from pathlib import Path

import exchange_calendars as xcals
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gabi import config, identity, research_lab, stats_rigor
from gabi import multifactor_backtest as bt
from gabi import overfitting_audit as audit


def _matrix():
    rng = np.random.default_rng(91)
    return pd.DataFrame({"top20_q": rng.normal(.035, .07, 36), "alternative": rng.normal(.015, .08, 36)},
                        index=pd.date_range("2016-10-01", periods=36, freq="3MS"))


def test_catalog_has_only_documented_variants_and_separates_cost_sensitivity():
    trials = audit.documented_trials()
    assert len(trials) == 24
    assert len({t.trial_id for t in trials}) == 24
    assert sum(t.role == "strategy" for t in trials) == 9
    assert all(t.cost_bps == 10 for t in trials if t.role == "strategy")
    assert {t.cost_bps for t in trials if t.top_n == 10 and not t.sma_filter} == {10, 25, 50, 100}
    assert all(t.cost_bps == 10 for t in trials if t.top_n == 30 or t.sma_filter)
    assert all(t.evidence for t in trials)


@pytest.mark.parametrize("months", [3, 6, 12])
@pytest.mark.parametrize("exposure", [.5, 1.0])
def test_quarterly_marks_compound_to_v1_terminal_return_without_interpolation(months, exposure, monkeypatch):
    start = pd.Timestamp("2016-07-02")
    calendar = xcals.get_calendar("XNYS")
    entry = calendar.next_session(calendar.date_to_session(start, direction="previous"))
    dates = [entry, *[calendar.date_to_session(start + pd.DateOffset(months=m), direction="next")
                     for m in range(3, months + 1, 3)]]
    prices_a = [100, 80, 120, 90, 140][:len(dates)]
    prices_b = [100, 110, 100, 130, 120][:len(dates)]
    histories = {"A": pd.DataFrame({"adj_close": prices_a}, index=dates),
                 "B": pd.DataFrame({"adj_close": prices_b}, index=dates),
                 "SPY": pd.DataFrame({"adj_close": np.linspace(100, 120, len(dates))}, index=dates)}
    monkeypatch.setattr(identity, "backtest_prices", lambda *a, **k: histories)
    monkeypatch.setattr(identity, "last_filings", lambda *a, **k: {})
    trial = audit.Trial("test", top_n=2, months=months, cost_bps=50)
    marks = audit._quarterly_marks(histories, ["A", "B"], start, trial, {"B"}, exposure)
    expected = bt._period_returns(["A", "B"], start, months, 50, held_symbols={"B"})
    assert (1 + marks).prod() - 1 == pytest.approx(exposure * expected["portfolio_return"])
    first_nav = 1 - exposure + exposure * (.8 * .995 ** 2 + 1.1) / 2
    assert marks.iloc[0] == pytest.approx(first_nav - 1)
    assert len(marks) == months // 3
    if months > 3:
        assert marks.iloc[0] != pytest.approx(marks.iloc[-1])


def test_marks_reject_missing_midpoint_even_when_final_prices_exist():
    dates = pd.to_datetime(["2016-07-05", "2017-01-03"])
    histories = {"A": pd.DataFrame({"adj_close": [100., 120.]}, index=dates)}
    with pytest.raises(ValueError, match="marcas trimestrales"):
        audit._quarterly_marks(histories, ["A"], pd.Timestamp("2016-07-02"),
                               audit.Trial("test", months=6), set(), 1.0)


def test_analysis_uses_common_arithmetic_excess_sharpe_and_fixed_selected_trial():
    matrix = _matrix()
    result = audit.analyze_matrix(matrix)
    excess = matrix - (1.04 ** .25 - 1)
    sharpe = excess.mean() / excess.std(ddof=1) * 2
    assert result["dsr"]["selected_sharpe"] == pytest.approx(sharpe["top20_q"])
    assert result["dsr"]["sr0_benchmark"] == pytest.approx(stats_rigor.expected_max_sharpe(sharpe.tolist()))
    assert result["pbo"]["pbo"] == stats_rigor.pbo_cscv(excess, n_splits=6)["pbo"]
    assert result["n_obs"] == 36
    assert result["periods_per_year"] == 4
    assert result["dsr_trial_count_sensitivity"]["100"]["dsr"] < result["dsr"]["dsr"]
    assert set(result["pbo_sensitivity"]) == {"4", "12"}


@pytest.mark.parametrize("case", ["gap", "nan", "inf", "duplicate_date", "duplicate_trial", "order", "constant", "total_loss"])
def test_analysis_rejects_invalid_or_incomparable_matrix(case):
    matrix = _matrix()
    if case == "gap":
        matrix = matrix.drop(matrix.index[5])
    elif case in ("nan", "inf", "total_loss"):
        matrix.iloc[3, 0] = {"nan": np.nan, "inf": np.inf, "total_loss": -1.0}[case]
    elif case == "duplicate_date":
        matrix = pd.concat([matrix, matrix.iloc[[0]]])
    elif case == "duplicate_trial":
        matrix.columns = ["top20_q", "top20_q"]
    elif case == "order":
        matrix = matrix.iloc[::-1]
    else:
        matrix["alternative"] = 0.0
    with pytest.raises(ValueError):
        audit.analyze_matrix(matrix)


def test_portable_artifact_and_registration_preserve_every_return(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    monkeypatch.setattr(research_lab, "_current_git_commit", lambda: "test")
    trials = [audit.Trial("top20_q"), audit.Trial("alternative", months=6)]
    monkeypatch.setattr(audit, "documented_trials", lambda: trials)
    matrix = _matrix()
    # Persistence is checked independently of the numerical tests above.
    calculated = audit.analyze_matrix(matrix)
    monkeypatch.setattr(audit, "analyze_matrix", lambda frame: calculated)
    output = tmp_path / "report"
    manifest = {"max_symbols": 200, "rankings": {}}
    first = audit.write_audit(matrix, None, output, input_manifest=manifest, register=True)
    second = audit.write_audit(matrix, None, output, input_manifest=manifest, register=True)
    assert first["research_lab_ids"] == second["research_lab_ids"]
    assert len(research_lab.list_experiments()) == 2
    report, loaded = audit.load_audit(output)
    pd.testing.assert_frame_equal(loaded, matrix, check_freq=False)
    for trial, exp_id in zip(trials, report["research_lab_ids"]):
        exp = research_lab.get_experiment(exp_id)
        np.testing.assert_array_equal(exp["returns"].to_numpy(), matrix[trial.trial_id].to_numpy())
        assert exp["periods_per_year"] == 4
        assert exp["stage"] == "RESEARCH"
        assert exp["result"]["trial"]["months"] == trial.months
    # A fresh checkout can recompute with only the published CSV + JSON.
    portable = audit.write_audit(loaded, None, output, input_manifest=report["inputs"])
    assert portable["research_lab_ids"] == report["research_lab_ids"]
    csv = output / "returns.csv"
    csv.write_bytes(csv.read_bytes().replace(b"\n", b"\r\n"))
    audit.load_audit(output)  # Git's Windows line endings are not corruption.
    csv.write_bytes(csv.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="huella"):
        audit.load_audit(output)


def test_reconstruction_rejects_modified_snapshot(tmp_path):
    (tmp_path / "snapshot.db").write_bytes(b"changed")
    (tmp_path / "manifest.json").write_text(json.dumps({"snapshot_sha256": "not-the-same"}))
    with pytest.raises(ValueError, match="snapshot"):
        audit.reconstruct_matrix(tmp_path)
