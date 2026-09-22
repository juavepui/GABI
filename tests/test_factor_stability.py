import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from gabi import academic_factors as af
from gabi import factor_stability as fs


def sample(n=36):
    rng = np.random.default_rng(193)
    dates = pd.date_range("2016-07-01", periods=n + 1, freq="3MS")
    frame = pd.DataFrame(rng.normal(0, .05, (n, 6)), columns=af.DEFAULT_FACTOR_COLS)
    frame["fecha"], frame["hasta"] = dates[:-1], dates[1:]
    frame["RF"] = .002
    frame["excess_return"] = .006 + frame["Mkt-RF"] + rng.normal(0, .01, n)
    frame["retorno"] = frame["excess_return"] + frame["RF"]
    return frame


def test_matches_full_hac_and_direct_window_regressions():
    frame = sample()
    audit = fs.analyze(frame)
    assert audit["full"]["coef"] == af._ols(*fs._design(frame), fs.NAMES)["coef"]
    assert [h["n_obs"] for h in audit["halves"]] == [18, 18]
    assert len(audit["rolling"]) == 21 + 17 + 13
    for fit in audit["rolling"]:
        subset = frame.loc[(frame.fecha >= fit["start"]) & (frame.hasta <= fit["end"])]
        expected = af._ols(*fs._design(subset), fs.NAMES)
        assert fit["coef"] == expected["coef"]
        assert fit["se"] == expected["se"]
        assert fit["n_obs"] == fit["window"]
        for name in fs.NAMES:
            np.testing.assert_allclose(fit["ci95_pointwise"][name], [
                expected["coef"][name] - 1.96 * expected["se"][name],
                expected["coef"][name] + 1.96 * expected["se"][name],
            ])


def test_synthetic_step_change_is_recovered_in_disjoint_halves():
    frame = sample()
    frame.loc[:17, "excess_return"] = -.01 + .6 * frame.loc[:17, "Mkt-RF"]
    frame.loc[18:, "excess_return"] = .02 + 1.4 * frame.loc[18:, "Mkt-RF"]
    frame["retorno"] = frame["excess_return"] + frame["RF"]
    halves = fs.analyze(frame)["halves"]
    assert [h["coef"]["alpha"] for h in halves] == pytest.approx([-.01, .02])
    assert [h["coef"]["Mkt-RF"] for h in halves] == pytest.approx([.6, 1.4])


def test_attribution_partitions_sample_and_reconciles_alpha():
    audit = fs.analyze(sample())
    events = audit["events"]
    assert [e["n_obs"] for e in events] == [4, 4, 4, 8, 16]
    dates = [date for e in events for date in e["period_starts"]]
    assert len(dates) == len(set(dates)) == 36
    assert sum(e["attribution"]["contribution_to_full_quarterly_alpha"] for e in events) == pytest.approx(
        audit["full"]["coef"]["alpha"], abs=1e-12,
    )
    assert sum(e["attribution"]["residual_sum"] for e in events) == pytest.approx(0, abs=1e-12)
    assert sum(y["n_obs"] for y in audit["calendar_years"]) == 36
    assert sum(y["contribution_to_full_quarterly_alpha"] for y in audit["calendar_years"]) == pytest.approx(
        audit["full"]["coef"]["alpha"], abs=1e-12,
    )
    for event in events:
        a = event["attribution"]
        assert a["excess_sum"] == pytest.approx(sum(a["factor_contributions"].values()) + a["adjusted_sum"])
        if event["id"] != "other":
            assert event["local_regression"]["status"] == "insufficient_data"
            assert "coef" not in event["local_regression"]
    assert events[-1]["local_regression"]["status"] == "not_contiguous"
    assert all(row["event"] == "selloff_2018" for row in audit["attribution_by_quarter"] if row["fecha"].startswith("2018"))


def test_excluding_episode_refits_without_hac_over_compressed_gaps(monkeypatch):
    frame = sample()
    original = af._ols
    calls = []

    def tracked(y, X, names, **kwargs):
        calls.append(len(y))
        return original(y, X, names, **kwargs)

    monkeypatch.setattr(af, "_ols", tracked)
    audit = fs.analyze(frame)
    assert 32 not in calls and 28 not in calls
    for event in audit["events"][:-1]:
        subset = frame.loc[~frame.fecha.dt.strftime("%Y-%m-%d").isin(event["period_starts"])]
        y, X = fs._design(subset)
        beta = np.linalg.lstsq(X, y, rcond=None)[0]
        fit = event["without_episode"]
        np.testing.assert_allclose(list(fit["coef"].values()), beta)
        assert "se" not in fit and "t_stat" not in fit


@pytest.mark.parametrize("problem", ["gap", "duplicate", "nan", "inf", "excess", "frequency", "nat", "loss"])
def test_rejects_invalid_inputs(problem):
    frame = sample()
    if problem == "gap":
        frame = frame.drop(9)
    elif problem == "duplicate":
        frame = pd.concat([frame, frame.iloc[[9]]])
    elif problem in ("nan", "inf"):
        frame.loc[9, "SMB"] = np.nan if problem == "nan" else np.inf
    elif problem == "excess":
        frame.loc[9, "excess_return"] += .01
    elif problem == "frequency":
        frame.loc[9, "hasta"] += pd.DateOffset(months=3)
    elif problem == "nat":
        frame.loc[9, "fecha"] = pd.NaT
    else:
        frame.loc[9, "retorno"] = -1
    with pytest.raises(ValueError):
        fs.analyze(frame)


def test_sorted_input_same_result_and_small_windows_are_explicit():
    frame = sample(14)
    audit = fs.analyze(frame.sample(frac=1, random_state=4))
    assert audit == fs.analyze(frame)
    assert audit["rolling"] == []
    assert all(h["status"] == "insufficient_data" for h in audit["halves"])
    assert len(fs.coefficient_table(audit)) == 7
    with pytest.raises(ValueError, match="mínimo"):
        fs.analyze(frame.iloc[:13])


def test_singular_full_and_local_designs_are_not_presented_as_estimates():
    frame = sample()
    frame["SMB"] = frame["HML"]
    with pytest.raises(ValueError, match="rank_deficient"):
        fs.analyze(frame)
    frame = sample()
    frame.loc[:17, "SMB"] = frame.loc[:17, "HML"]
    audit = fs.analyze(frame)
    assert audit["halves"][0]["status"] == "rank_deficient"
    assert "coef" not in audit["halves"][0]
    assert audit["halves"][1]["status"] == "ok"


def test_alignment_agrees_with_existing_regression_and_rejects_missing_months_rf():
    rng = np.random.default_rng(71)
    factors = pd.DataFrame(rng.normal(.001, .01, (108, 7)),
                           columns=[*af.DEFAULT_FACTOR_COLS, "RF"],
                           index=pd.date_range("2016-07-01", periods=108, freq="MS"))
    periods = sample()[["fecha", "hasta", "retorno"]]
    inputs = fs.aligned_quarters(periods, factors)
    audit = fs.analyze(inputs)
    reference = af.regress_returns_on_factors(periods, factors)
    assert audit["full"]["coef"] == pytest.approx(reference["coef"], rel=1e-12, abs=1e-14)
    assert audit["full"]["se"] == pytest.approx(reference["se"], rel=1e-12, abs=1e-14)
    with pytest.raises(ValueError, match="Faltan meses"):
        fs.aligned_quarters(periods, factors.drop(factors.index[7]))
    factors.iloc[7, 6] = np.nan
    with pytest.raises(ValueError, match="Faltan meses"):
        fs.aligned_quarters(periods, factors)
    with pytest.raises(ValueError, match="duplicados"):
        fs.aligned_quarters(periods, pd.concat([factors, factors.iloc[[0]]]))
    periods.loc[0, "hasta"] += pd.DateOffset(months=3)
    with pytest.raises(ValueError, match="trimestrales"):
        fs.aligned_quarters(periods, factors)


def test_future_changes_cannot_alter_earlier_rolling_fit():
    frame = sample()
    before = fs.analyze(frame)
    frame.loc[30:, "retorno"] += .2
    frame.loc[30:, "excess_return"] += .2
    after = fs.analyze(frame)
    earlier_before = [r for r in before["rolling"] if r["end"] < "2024-01-01"]
    earlier_after = [r for r in after["rolling"] if r["end"] < "2024-01-01"]
    assert earlier_before == earlier_after


def test_artifacts_reproducible_strict_json_and_tampering_detected(tmp_path):
    inputs = tmp_path / "source.csv"
    sample().to_csv(inputs, index=False)
    output = tmp_path / "audit"
    audit = fs.write_audit(inputs, output)
    assert fs.load_audit(output) == audit
    json_text = (output / "audit.json").read_text(encoding="utf-8")
    assert "NaN" not in json_text and "Infinity" not in json_text
    assert fs.write_audit(inputs, output) == audit
    csv = output / "inputs.csv"
    csv.write_bytes(csv.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    assert fs.load_audit(output) == audit
    csv.write_bytes(csv.read_bytes() + b"bad\n")
    with pytest.raises(ValueError, match="artefacto"):
        fs.load_audit(output)


def test_committed_audit_reproduces_frozen_hac_baseline():
    docs = Path(__file__).resolve().parents[1] / "docs"
    audit = fs.load_audit(docs / "factor-stability")
    original = json.loads((docs / "academic-factors-hac-audit.json").read_text(encoding="utf-8"))
    recomputed = fs.analyze(pd.read_csv(docs / "factor-stability" / "inputs.csv"))
    for field in ("coef", "se", "t_stat"):
        assert audit["full"][field] == pytest.approx(recomputed["full"][field], rel=1e-10, abs=1e-12)
    np.testing.assert_allclose(list(audit["full"]["coef"].values()), list(original["regression"]["coef"].values()),
                               rtol=1e-10, atol=1e-12)
    np.testing.assert_allclose(list(audit["full"]["se"].values()), list(original["regression"]["se"].values()),
                               rtol=1e-10, atol=1e-12)
