"""Tests for preregistered decisions, funding and research evidence boundaries."""

import json
import sqlite3

import numpy as np
import pandas as pd
import pytest

from gabi import strategy_discovery as sd


def features(n=40):
    frame = pd.DataFrame(index=[f"S{i:03}" for i in range(n)])
    frame["entity_id"] = [f"cik:{i:010}" for i in range(n)]
    frame["division"] = ["D", "E", "H", "I"] * (n // 4)
    for key in ("pe", "pb", "ev_ebitda", "roic_persistence_mean", "operating_margin_persistence_mean",
                "momentum_12m", "rel_strength_6m", "price_vs_sma200", "historical_fcf_cagr"):
        frame[key] = np.arange(n, dtype=float) + 1
    for key in ("roic_years", "operating_margin_years", "fcf_years"):
        frame[key] = 4
    frame["fcf_positive_years"] = 3
    frame["implied_fcf_growth"] = .05
    frame["expectations_discount_rate"] = .09
    frame["expectations_terminal_growth"] = .025
    frame["expectations_forecast_years"] = 5
    return frame


def test_scores_ignore_future_and_apply_availability_rules():
    frame = features()
    actual = sd.score_frame(frame)
    frame["retorno"] = np.arange(len(frame)) * -100
    frame["composite_score"] = 999
    pd.testing.assert_frame_equal(actual, sd.score_frame(frame))
    frame.loc["S000", ["pe", "pb"]] = [-1, np.nan]
    frame.loc["S001", ["roic_years", "operating_margin_years"]] = 2
    frame.loc["S002", "implied_fcf_growth"] = np.nan
    result = sd.score_frame(frame)
    assert pd.isna(result.loc["S000", "QV"])
    assert pd.isna(result.loc["S001", "QE"])
    assert pd.isna(result.loc["S002", "QE"])
    assert result.loc["S001", "quality_available"] == 1


def test_bad_expectations_parameters_fail_instead_of_changing_hypothesis():
    frame = features()
    frame.loc["S000", "expectations_discount_rate"] = .10
    with pytest.raises(ValueError, match="DCF"):
        sd.score_frame(frame)


def test_percentiles_use_eight_finite_observations_and_oriented_ties():
    values = pd.Series([1., 2., 3., 4., 5., 6., 7., 8., 1., 1., 100.])
    sector = pd.Series(["D"] * 8 + ["I"] * 3)
    rank, fallback = sd.percentile(values, sector, lower=True)
    assert rank.iloc[0] == 1 and rank.iloc[7] == .125
    assert not fallback.iloc[:8].any() and fallback.iloc[8:].all()
    assert rank.iloc[8] == rank.iloc[9]
    values.iloc[7] = np.nan
    _, fallback = sd.percentile(values, sector)
    assert fallback.iloc[:7].all() and not fallback.iloc[7]


def test_selection_caps_ties_cash_and_all_exclusions():
    scores = features().iloc[::-1][["entity_id", "division"]].copy()
    scores["QV"] = 1.
    scores["division"] = "D"
    chosen = sd.decisions(scores, "QV")
    selected = chosen[chosen.reason == "selected"]
    assert selected.symbol.tolist() == [f"S{i:03}" for i in range(6)]
    assert len(chosen) == 40 and (chosen.reason == "division_cap").sum() == 34
    assert selected.budget_weight.sum() == pytest.approx(.30)
    assert sd.funded_return(np.zeros(6), 10) > -.001  # 70% remains cash
    scores.loc[scores.index[:24], "division"] = ["E", "H", "I", "D"] * 6
    selected = sd.decisions(scores, "QV").query("reason == 'selected'")
    assert len(selected) == 20 and selected.groupby("division").size().max() <= 6


def test_funding_accounts_for_both_sides_commissions_and_total_loss():
    budget, side = 5000., .001
    notional = (budget - 2) / (1 + side)
    assert sd.funded_return(np.array([.10]), 10) == pytest.approx((95000 + notional * 1.1 * (1 - side)) / 100000 - 1)
    assert sd.funded_return(np.full(20, -1.), 25) == -1
    assert sd.funded_return(np.array([]), 25) == 0
    assert sd.funded_return(np.array([np.nan, .50]), 10) is None
    assert sd.funded_return(np.array([-1.001]), 10) is None
    assert sd.funded_return(np.zeros(20), 10) < sd.funded_return(np.zeros(1), 10, slots=1)


def test_ic_retains_calendar_gaps_and_requires_observations():
    series = pd.Series(np.sin(np.arange(57)) * .1 + .02)
    series.iloc[::3] = np.nan
    full, compressed = sd.ic_test(series), sd.ic_test(series.dropna())
    assert full["n"] == 38 and full["se_hac"] != compressed["se_hac"]
    assert sd.ic_test(series.iloc[:40])["status"] == "insufficient"
    tests = {"QV": {"p": .01}, "QVM": {"p": .04}, "QE": {"p": .03}}
    sd.holm_three(tests)
    assert [tests[x]["p_holm"] for x in sd.MODELS] == [.03, .06, .06]
    with pytest.raises(ValueError, match="exactamente"):
        sd.holm_three({"QV": {"p": .01}})


def test_bootstrap_joint_reproducible_and_missing_blocks_inference():
    series = np.sin(np.arange(57)) * .1 + .02
    excess = pd.DataFrame({"QV_base": series, "QE_base": series * 2, "QVM_base": series})
    excess.loc[4, "QVM_base"] = np.nan
    first = sd.bootstrap_bounds(excess)
    assert first == sd.bootstrap_bounds(excess)
    assert first["QE_base"] == pytest.approx(first["QV_base"] * 2)
    assert first["QVM_base"] is None


def mock_panel():
    rows = []
    for date in pd.date_range("2011-07-01", periods=57, freq="QS"):
        for model in sd.MODELS:
            rows.append({"fecha": date.strftime("%Y-%m-%d"), "model": model,
                         "ic": .5 + .01 * np.sin(len(rows)), "n_selected": 20,
                         "excess_base": .03, "excess_stress": .02})
    return pd.DataFrame(rows)


def test_even_a_passing_diagnostic_cannot_certify_an_edge():
    panel = mock_panel()
    result = sd.summarize(panel)
    assert all(row["audit_daily"] for row in result.values())
    assert not any(row["demonstrated"] for row in result.values())
    panel.loc[(panel.model == "QE") & (panel.fecha >= "2021"), "excess_stress"] = -.01
    failed = sd.summarize(panel)["QE"]
    assert not failed["audit_daily"]
    assert "stress_2021-25_insufficient_or_nonpositive" in failed["failures"]


def test_preregister_and_analysis_refuse_mutations(tmp_path, monkeypatch):
    monkeypatch.setattr(sd, "OUTPUT", tmp_path)
    (tmp_path / "PROTOCOLO.md").write_text("frozen protocol\n", encoding="utf-8")
    first = sd.preregister()
    assert first == sd.preregister()
    sd.save_json(tmp_path / "resultado.json", {})
    with pytest.raises(ValueError, match="congelado"):
        sd.analyze(tmp_path)
    (tmp_path / "PROTOCOLO.md").write_text("changed protocol\n", encoding="utf-8")
    with pytest.raises(ValueError, match="protocolo"):
        sd.preregister()


def test_benchmark_snapshot_hash_and_exact_sessions(tmp_path, monkeypatch):
    monkeypatch.setattr(sd, "RANKINGS", tmp_path)
    snapshot = tmp_path / "snapshot.db"
    with sqlite3.connect(snapshot) as connection:
        connection.execute("CREATE TABLE prices(symbol TEXT, date TEXT, adj_close REAL)")
        connection.executemany("INSERT INTO prices VALUES ('SPY', ?, ?)", [("2011-07-05", 100.), ("2011-10-03", 110.)])
    sd.save_json(tmp_path / "manifest.json", {"snapshot_sha256": sd.frozen.file_hash(snapshot)})
    before = snapshot.read_bytes()
    result, _ = sd.benchmark(["2011-07-02"])
    assert result.iloc[0].entry == "2011-07-05" and result.iloc[0].exit == "2011-10-03"
    assert result.iloc[0].spy_gross == pytest.approx(.10)
    assert snapshot.read_bytes() == before
    with pytest.raises(ValueError, match="exacto"):
        sd.benchmark(["2011-10-02"])
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    manifest["snapshot_sha256"] = "0" * 64
    sd.save_json(tmp_path / "manifest.json", manifest)
    with pytest.raises(ValueError, match="snapshot"):
        sd.benchmark(["2011-07-02"])


def test_saved_analysis_reproduces_and_refuses_artifact_tampering(tmp_path, monkeypatch):
    monkeypatch.setattr(sd, "OUTPUT", tmp_path)
    (tmp_path / "PROTOCOLO.md").write_text("frozen protocol\n", encoding="utf-8")
    frame = features()
    frame["retorno"] = np.sin(np.arange(len(frame))) * .1
    dates = mock_panel().fecha.unique().tolist()
    monkeypatch.setattr(sd, "inputs", lambda: ({date: frame.copy() for date in dates}, {"fake": "test-only"}))
    spy = pd.DataFrame({"spy_base": .01234, "spy_stress": .009876}, index=dates)
    spy.index.name = "fecha"
    monkeypatch.setattr(sd, "benchmark", lambda dates: (spy.copy(), "test-snapshot"))
    result = sd.analyze(tmp_path)
    assert sd.verify() == result
    other = sd.analyze(tmp_path / "reproduction")
    assert result == other
    path = tmp_path / "decisions.csv"
    path.write_text(path.read_text(encoding="utf-8") + "tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="Artefacto modificado"):
        sd.verify()
