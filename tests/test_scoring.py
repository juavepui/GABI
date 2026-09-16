import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gabi import scoring


def _sample_df():
    return pd.DataFrame(
        {
            "pe": [10, 20, 30],
            "peg": [1.0, 1.5, 2.0],
            "pb": [1.0, 3.0, 5.0],
            "ps": [1.0, 2.0, 3.0],
            "ev_ebitda": [8.0, 12.0, 16.0],
            "roe": [0.30, 0.20, 0.10],
            "roa": [0.15, 0.10, 0.05],
            "operating_margin": [0.30, 0.20, 0.10],
            "gross_margin": [0.60, 0.50, 0.40],
            "profit_margin": [0.20, 0.15, 0.10],
            "revenue_growth_yoy": [0.20, 0.10, 0.02],
            "earnings_growth_yoy": [0.25, 0.10, -0.05],
            "revenue_growth_ttm_yoy": [0.18, 0.08, 0.01],
            "current_ratio": [2.0, 1.5, 1.0],
            "debt_to_equity": [20.0, 60.0, 120.0],
            "price_vs_sma50": [0.05, 0.0, -0.05],
            "price_vs_sma200": [0.10, 0.02, -0.10],
            "momentum_6m": [0.15, 0.05, -0.10],
            "momentum_12m": [0.25, 0.10, -0.15],
            "rel_strength_6m": [0.08, 0.0, -0.08],
            "rsi14": [60.0, 55.0, 30.0],
            "golden_cross_recent": [True, False, False],
        },
        index=["AAA", "BBB", "CCC"],
    )


def test_cheapest_company_gets_highest_value_score():
    df = scoring.build_scores(_sample_df())
    assert df.loc["AAA", "value_score"] > df.loc["CCC", "value_score"]


def test_best_fundamentals_get_highest_quality_score():
    df = scoring.build_scores(_sample_df())
    assert df.loc["AAA", "quality_score"] > df.loc["CCC", "quality_score"]


def test_strongest_momentum_gets_highest_momentum_score():
    df = scoring.build_scores(_sample_df())
    assert df.loc["AAA", "momentum_score"] > df.loc["CCC", "momentum_score"]


def test_composite_score_in_range_and_ranked():
    df = scoring.build_scores(_sample_df())
    assert df["composite_score"].between(0, 100).all()
    assert list(df.index) == ["AAA", "BBB", "CCC"]  # ya viene ordenado desc


def test_weights_shift_ranking():
    df_raw = _sample_df()
    # Fuerza a que BBB tenga mejor momentum que AAA mientras mantiene peor value/quality.
    df_raw.loc["BBB", ["momentum_6m", "momentum_12m", "rel_strength_6m"]] = [0.5, 0.6, 0.5]

    only_value = scoring.build_scores(df_raw, weights={"value": 1.0, "quality": 0.0, "momentum": 0.0})
    only_momentum = scoring.build_scores(df_raw, weights={"value": 0.0, "quality": 0.0, "momentum": 1.0})

    assert only_value.index[0] == "AAA"
    assert only_momentum.index[0] == "BBB"


def test_missing_metrics_produce_nan_not_crash():
    df_raw = _sample_df()
    df_raw.loc["AAA", "pe"] = np.nan
    df_raw.loc["AAA", "roe"] = np.nan
    df = scoring.build_scores(df_raw)
    assert df.loc["AAA", "composite_score"] == df.loc["AAA", "composite_score"]  # no es NaN


def test_explain_row_returns_metric_table():
    df = scoring.build_scores(_sample_df())
    breakdown = scoring.explain_row(df, "AAA")
    assert "pe" in breakdown["metric"].values
    assert "momentum_6m" in breakdown["metric"].values
