import json

import numpy as np
import pandas as pd
import pytest

from gabi import rank_stability as rs
from gabi import scoring


def stable_panel(n=60):
    # All blocks agree, so transferring any mass cannot change ordering.
    scores = np.linspace(100, 1, n)
    return pd.DataFrame({**{f"{b}_score": scores for b in rs.BLOCKS},
                         "composite_score": scores, "score_coverage": 1., "sector": "Tech"},
                        index=[f"F{i:03d}" for i in range(n)])


def fragile_panel():
    data = stable_panel()
    # Two nearly tied firms at the Top-20 boundary have opposing blocks.
    data.loc["F019", [f"{b}_score" for b in rs.BLOCKS]] = [100, 0, 100, 50]
    data.loc["F020", [f"{b}_score" for b in rs.BLOCKS]] = [0, 100, 100, 0]
    data.loc["F019", "composite_score"] = 60
    data.loc["F020", "composite_score"] = 60
    # Exactly 19 names above both, others below.
    data.loc[data.index[:19], [f"{b}_score" for b in rs.BLOCKS]] = 90
    data.loc[data.index[21:], [f"{b}_score" for b in rs.BLOCKS]] = 30
    data.loc["F020", "sector"] = "Health"
    return data


def test_fixed_neighborhood_has_24_sum_preserving_small_transfers():
    weights = rs.perturbations()
    delta = weights.to_numpy() - np.array(list(scoring.DEFAULT_WEIGHTS.values()))
    assert len(weights) == 24
    np.testing.assert_allclose(weights.sum(axis=1), 1)
    assert (np.count_nonzero(np.abs(delta) > 1e-12, axis=1) == 2).all()
    assert np.max(np.abs(delta)) == pytest.approx(.02)
    assert (weights >= 0).all().all()


def test_unanimous_blocks_are_stable_with_known_concentration():
    summary, metrics, firms = rs.analyze(stable_panel())
    assert summary["stability_score"] == 100
    assert (metrics.top20_entries == 0).all()
    np.testing.assert_allclose(metrics.spearman, 1)
    np.testing.assert_allclose(metrics.kendall, 1)
    assert (metrics.top20_sector_hhi == 1).all()
    assert (metrics.top20_sector_max_change == 0).all()
    assert (firms.rank_min == firms.rank_max).all()
    assert (firms.loc[firms.base_rank <= 20, "diagnosis"] == "Persistente (Top-20)").all()


def test_opposing_boundary_candidates_are_fragile_and_sectors_change():
    panel = fragile_panel()
    before = panel.copy(deep=True)
    summary, metrics, firms = rs.analyze(panel)
    assert summary["stability_score"] < 100
    assert firms.loc["F019", "diagnosis"] == "Frágil (Top-20)"
    assert firms.loc["F020", "diagnosis"] == "Cerca del Top-20"
    assert 0 < firms.loc["F019", "top20_inclusion"] < 1
    assert firms.loc["F019", "rank_max"] > 20
    assert metrics.top20_entries.max() == 1
    assert metrics.top20_sector_max_change.max() == pytest.approx(.05)
    changed = metrics.loc[metrics.top20_entries == 1].iloc[0]
    assert changed.top20_jaccard == pytest.approx(19 / 21)
    pd.testing.assert_frame_equal(panel, before)


def test_missing_risk_renormalizes_and_future_data_do_not_change_any_metric():
    data = stable_panel()
    data["risk_score"] = np.nan
    data["sector"] = np.nan
    expected = rs.analyze(data)
    data["forward_return"] = np.random.default_rng(51).normal(size=len(data))
    data.loc[data.index[:30], "forward_return"] = np.nan
    result = rs.analyze(data.sample(frac=1, random_state=4))
    assert result[0] == expected[0]
    pd.testing.assert_frame_equal(result[1], expected[1])
    pd.testing.assert_frame_equal(result[2], expected[2])
    assert not result[0]["sectors_complete"]
    assert not any("sector" in c for c in result[1])


def test_ineligible_and_small_universes_are_reported_without_perfect_top_score():
    data = stable_panel(20)
    data.loc["F000", "score_coverage"] = .69
    data.loc["F001", "quality_score"] = np.nan
    summary, _, firms = rs.analyze(data)
    assert summary["eligible"] == 18
    assert summary["excluded"] == 2
    assert summary["stability_score"] is None
    assert summary["unavailable_tops"] == [20, 30]
    assert "top20_inclusion" not in firms


def test_ties_remain_deterministic_despite_row_order_and_roundoff():
    data = stable_panel()
    data[[f"{b}_score" for b in rs.BLOCKS]] = 10
    summary, _, firms = rs.analyze(data.sample(frac=1, random_state=5))
    assert summary["stability_score"] == 100
    assert list(firms.index) == sorted(data.index)


@pytest.mark.parametrize("weights", [{"value": 1}, dict.fromkeys(rs.BLOCKS, 0),
                                     {**scoring.DEFAULT_WEIGHTS, "risk": -.1},
                                     {**scoring.DEFAULT_WEIGHTS, "risk": np.nan}])
def test_invalid_weights_fail_explicitly(weights):
    with pytest.raises(ValueError):
        rs.analyze(stable_panel(), weights)


def test_boundary_weights_omit_infeasible_transfers_and_report_family():
    summary, _, _ = rs.analyze(stable_panel(), dict(zip(rs.BLOCKS, (1., 0., 0., 0.), strict=True)))
    assert summary["perturbations"] == 6
    assert summary["omitted_infeasible"] == 18


def test_duplicate_names_and_no_eligible_universe_fail():
    data = stable_panel()
    data.index = ["DUP"] * len(data)
    with pytest.raises(ValueError, match="únicos"):
        rs.analyze(data)
    with pytest.raises(ValueError, match="al menos dos"):
        rs.analyze(stable_panel(1))


def test_artifact_tampering_is_detected(tmp_path, monkeypatch):
    monkeypatch.setattr(rs, "OUTPUT", tmp_path)
    (tmp_path / "resultado.json").write_text(json.dumps({"spec_sha256": rs.SPEC_SHA256,
                                                        "artifact_sha256": {"metrics.csv": "invalid"}}))
    (tmp_path / "metrics.csv").write_text("edited")
    with pytest.raises(ValueError, match="alterado"):
        rs.load_saved()
