import json

import numpy as np
import pandas as pd
import pytest

from gabi import repurchase_cash_strategy as rcf


def features(n=80):
    frame = pd.DataFrame(index=[f"S{i:03d}" for i in range(n)])
    frame["entity_id"] = [f"cik:{i:010d}" for i in range(n)]
    frame["division"] = ["D" if i % 2 else "I" for i in range(n)]
    frame["accn"] = [f"filing-{i}" for i in range(n)]
    frame["period"] = "2010-12-31"
    frame["filed_date"] = "2011-02-01"
    frame["accepted"] = "2011-02-01 12:00:00"
    frame["filing_status"] = "current_annual_filing"
    frame["fact_source_status"] = "admitted_source_or_absent"
    frame["fcf_status"] = "paired"
    for name in ("ocf", "capex", "buybacks"):
        frame[name + "_status"] = "reported"
        frame[name + "_start"] = "2010-01-01"
        frame[name + "_end"] = frame.period
    frame["ocf_value"] = 100.
    frame["capex_value"] = 10. + np.arange(n) * .5
    frame["buybacks_value"] = 1. + np.arange(n) * .25
    return frame


def panel():
    dates = pd.date_range("2011-07-01", periods=57, freq="QS").strftime("%Y-%m-%d")
    return pd.DataFrame({"fecha": dates, "ic": .3 + .03 * np.sin(np.arange(57)),
                         "n_scored": 80, "n_selected": 12,
                         "excess_base": .03, "excess_stress": .02,
                         "selection_excess_base": .01, "selection_excess_stress": .009})


def test_score_is_scale_invariant_and_independent_of_future_outcomes():
    frame = features()
    original = rcf.score_frame(frame)
    frame["retorno"] = np.arange(len(frame)) * 1000.
    frame["market_cap"] = -1.
    frame["shares_change_raw"] = np.inf
    frame["common_cash_difference_usd"] = -999999.
    frame.loc[:, [name + "_value" for name in ("ocf", "capex", "buybacks")]] *= 1000
    pd.testing.assert_frame_equal(original.drop(columns="matched_fcf_usd"),
                                  rcf.score_frame(frame).drop(columns="matched_fcf_usd"))
    assert original.eligible.all()
    assert original.repurchase_fraction.le(1).all()


@pytest.mark.parametrize(("column", "value", "reason"), [
    ("division", "H", "financial_division_H"),
    ("filing_status", "stale_annual_filing", "no_current_annual_filing"),
    ("fact_source_status", "quarantined_filing", "source_quarantined"),
    ("buybacks_status", "missing", "missing_or_invalid_component"),
    ("capex_value", np.nan, "missing_or_invalid_component"),
    ("buybacks_start", "2009-01-01", "cashflow_period_mismatch"),
    ("ocf_value", -10., "nonpositive_cash_generation"),
    ("buybacks_value", 0., "zero_reported_repurchase"),
    ("buybacks_value", 999., "repurchases_exceed_fcf"),
])
def test_exclusions_are_explicit_without_imputation(column, value, reason):
    frame = features()
    frame.loc["S000", column] = value
    result = rcf.score_frame(frame)
    assert result.loc["S000", "eligibility_reason"] == reason
    assert not result.loc["S000", "eligible"]
    assert pd.isna(result.loc["S000", rcf.MODEL])
    assert pd.isna(result.loc["S000", "repurchase_fraction"])


def test_deduplicate_cik_before_eligibility_and_never_substitute_a_class():
    frame = features()
    frame.loc["S001", "entity_id"] = frame.loc["S000", "entity_id"]
    frame.loc["S000", "buybacks_status"] = "missing"
    scores = rcf.score_frame(frame.iloc[::-1])
    assert scores.loc["S001", "eligibility_reason"] == "duplicate_share_class"
    assert not scores.loc[["S000", "S001"], "eligible"].any()
    chosen = rcf.parent.decisions(scores, rcf.MODEL).query("reason == 'selected'")
    assert chosen.entity_id.nunique() == len(chosen)
    assert chosen.groupby("division").size().max() == 6
    assert len(chosen) == 12  # remaining slots must stay in cash
    assert chosen.budget_weight.sum() == pytest.approx(.6)


def test_excluded_extreme_does_not_change_eligible_percentiles():
    frame = features()
    scores = rcf.score_frame(frame)
    frame.loc["ZZZ"] = frame.loc["S000"]
    frame.loc["ZZZ", "entity_id"] = "cik:9999999999"
    frame.loc["ZZZ", "buybacks_value"] = 1.e15
    pd.testing.assert_frame_equal(scores, rcf.score_frame(frame).loc[scores.index])


def test_sector_fallback_uses_only_unique_eligible_issuers():
    frame = features(7)
    result = rcf.score_frame(frame)
    assert result.cash_conversion_global_fallback.all()
    expected = result.cash_conversion.rank(method="average", pct=True)
    pd.testing.assert_series_equal(result.cash_conversion_pct, expected, check_names=False)


def test_gate_requires_both_costs_all_windows_and_adequate_issuer_sample():
    data = panel()
    passed = rcf.summarize(data)
    assert passed["audit_daily"] and not passed["demonstrated"]
    assert passed["ic"]["p_known_search_guard"] == min(1., 34 * passed["ic"]["p"])
    data.loc[data.fecha >= "2021", "excess_stress"] = -.01
    failed = rcf.summarize(data)
    assert not failed["audit_daily"]
    assert "stress_2021-25_insufficient_or_nonpositive" in failed["failures"]
    data = panel()
    data.loc[data.fecha < "2016", "n_scored"] = 29
    assert "insufficient_eligible_issuer_sample" in rcf.summarize(data)["failures"]


def test_bootstrap_keeps_missing_calendar_rows_and_shared_cost_indices():
    values = pd.DataFrame({"base": np.sin(np.arange(57)) * .02 + .03})
    values["stress"] = values.base * 2
    bounds = rcf.bootstrap_bounds(values)
    assert bounds == rcf.bootstrap_bounds(values)
    assert bounds["stress"] == pytest.approx(bounds["base"] * 2)
    values.loc[4, "base"] = np.nan
    assert rcf.bootstrap_bounds(values)["base"] is None
    assert rcf.bootstrap_bounds(values)["stress"] == bounds["stress"]
    assert rcf.bootstrap_bounds(values.iloc[:29]) == {"base": None, "stress": None}


def test_preregistration_detects_protocol_and_parent_mutations(tmp_path, monkeypatch):
    monkeypatch.setattr(rcf, "OUTPUT", tmp_path)
    (tmp_path / "PROTOCOLO.md").write_text("fixed\n", encoding="utf-8")
    first = rcf.preregister()
    assert first == rcf.preregister()
    with monkeypatch.context() as context:
        context.setattr(rcf, "PARENT_SHA256", "0" * 64)
        with pytest.raises(ValueError, match="dependiente"):
            rcf.preregister()
    (tmp_path / "PROTOCOLO.md").write_text("changed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Preregistro"):
        rcf.preregister()


def test_end_to_end_missing_selected_return_invalidates_period_and_control(tmp_path, monkeypatch):
    monkeypatch.setattr(rcf, "OUTPUT", tmp_path)
    (tmp_path / "PROTOCOLO.md").write_text("fixed\n", encoding="utf-8")
    frame = features()
    scores = rcf.score_frame(frame)
    chosen = rcf.parent.decisions(scores, rcf.MODEL).query("reason == 'selected'").iloc[0].symbol
    frame["retorno"] = np.sin(np.arange(len(frame))) * .1
    dates = panel().fecha.tolist()
    frames = {date: frame.copy() for date in dates}
    frames[dates[4]].loc[chosen, "retorno"] = np.nan
    monkeypatch.setattr(rcf, "inputs", lambda: (frames, {"snapshot_sha256": "test-only"}))
    spy = pd.DataFrame({"spy_base": .01234, "spy_stress": .009876}, index=dates)
    spy.index.name = "fecha"
    monkeypatch.setattr(rcf.parent, "benchmark", lambda dates: (spy.copy(), "test-only"))
    result = rcf.analyze(tmp_path)
    assert rcf.verify() == result
    other = rcf.analyze(tmp_path / "replay")
    assert other == result
    quarters = pd.read_csv(tmp_path / "quarterly.csv")
    assert pd.isna(quarters.loc[4, "net_base"])
    assert pd.isna(quarters.loc[4, "eligible_net_base"])
    assert quarters.loc[4, "missing_selected"] == chosen
    assert result["summary"]["costs"]["base"]["known_search_lower_bound"] is None
    assert not result["summary"]["audit_daily"]
    with pytest.raises(ValueError, match="congelado"):
        rcf.analyze(tmp_path)
    path = tmp_path / "decisions.csv"
    path.write_text(path.read_text(encoding="utf-8") + "tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="Artefacto"):
        rcf.verify()
    assert json.loads((tmp_path / "resultado.json").read_text())["demonstrated"] is False
