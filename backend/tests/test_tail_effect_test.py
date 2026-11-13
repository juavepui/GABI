"""Casos críticos de asignación e inferencia de STAT-4 (#47)."""

import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from gabi import tail_effect_test as tail


def test_preregistration_matches_frozen_specification():
    record = json.loads((tail.OUTPUT / "preregistro.json").read_text(encoding="utf-8"))
    assert record["sha256"] == tail.spec_hash()
    assert record["spec"] == tail.SPEC


def test_quarter_assigns_tied_scores_by_symbol_before_missing_returns(tmp_path, monkeypatch):
    date = "2020-01-02"
    ranking_dir = tmp_path / "rankings"
    forward_dir = tmp_path / "forward"
    ranking_dir.mkdir()
    forward_dir.mkdir()
    symbols = [f"S{i:03d}" for i in range(100)]
    ranking = pd.DataFrame({"composite_score": np.arange(100, 0, -1, dtype=float),
                            "score_coverage": 1.0}, index=symbols)
    ranking.loc["S001", "composite_score"] = ranking.loc["S000", "composite_score"]
    ranking.to_csv(ranking_dir / f"ranking-{date}.csv")
    forward = pd.DataFrame({"retorno": 0.0}, index=symbols)
    forward.loc["S000", "retorno"] = 0.10
    forward.loc["S001", "retorno"] = 0.20
    forward.loc["S002", "retorno"] = np.nan
    forward.iloc[::-1].to_csv(forward_dir / f"forward-{date}.csv")
    monkeypatch.setattr(tail.config, "BASE_DIR", tmp_path)
    monkeypatch.setattr(tail.cs, "WORK", forward_dir)
    monkeypatch.setitem(tail.hr.VARIANTS, tail.cs.SOURCE_VARIANT, SimpleNamespace(cache=ranking_dir))

    row, fingerprints = tail.quarter(date)
    assert row["top_1"] == pytest.approx(0.10)
    assert row["p1_5"] == pytest.approx(0.20 / 3)
    assert row["n_p1_5"] == 4 and row["n_return_p1_5"] == 3
    assert row["top_5"] == pytest.approx(0.30 / 4)
    assert len(fingerprints) == 2

    forward.loc["S000", "retorno"] = np.nan
    forward.to_csv(forward_dir / f"forward-{date}.csv")
    with pytest.raises(ValueError, match="Banda top_1 sin retornos"):
        tail.quarter(date)


def test_holm_adjustment_is_monotone():
    results = {"a": {"p": .04}, "b": {"p": .001}, "c": {"p": .02}}
    tail._holm(results)
    assert results["b"]["p_holm"] == pytest.approx(.003)
    assert results["c"]["p_holm"] == pytest.approx(.04)
    assert results["a"]["p_holm"] == pytest.approx(.04)
