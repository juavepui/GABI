import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

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
            "volatility": [0.15, 0.25, 0.40],
            "max_drawdown": [-0.10, -0.25, -0.45],
            "sharpe_ratio": [1.5, 0.8, -0.2],
            "sortino_ratio": [2.0, 1.0, -0.3],
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


def test_row_with_no_momentum_data_keeps_nan_composite_not_fake_zero():
    # Una fila sin ningún dato de precio (technicals.compute_technicals no
    # se llegó a ejecutar) no debe recibir momentum_score=0 solo porque
    # golden_cross_recent también sale NaN -> False. Bug real: el bonus de
    # golden cross usaba fillna(0) sin comprobar si había momentum_score.
    df_raw = pd.DataFrame(
        {"pe": [10, np.nan], "golden_cross_recent": [True, np.nan]},
        index=["AAA", "SINDATOS"],
    )
    df = scoring.build_scores(df_raw)
    assert pd.isna(df.loc["SINDATOS", "momentum_score"])
    assert pd.isna(df.loc["SINDATOS", "composite_score"])


def test_explain_row_returns_metric_table():
    df = scoring.build_scores(_sample_df())
    breakdown = scoring.explain_row(df, "AAA")
    assert "pe" in breakdown["metric"].values
    assert "momentum_6m" in breakdown["metric"].values


def test_sector_relative_percentile_compares_within_sector():
    n = 10
    tech_pe = list(range(20, 20 + n))  # sector caro: PER 20-29
    util_pe = list(range(5, 5 + n))    # sector barato: PER 5-14
    df = pd.DataFrame(
        {"pe": tech_pe + util_pe, "sector": ["Tech"] * n + ["Utilities"] * n},
        index=[f"T{i}" for i in range(n)] + [f"U{i}" for i in range(n)],
    )
    df = scoring.add_percentile_columns(df, ["pe"], higher_is_better=False)

    # T0 (PER 20) es la más barata DENTRO de su sector -> percentil alto.
    assert df.loc["T0", "pe_pct"] >= 90
    # U9 (PER 14) es la más cara DENTRO de su sector -> percentil bajo.
    assert df.loc["U9", "pe_pct"] < 20
    # Aunque el PER absoluto de T0 (20) es peor que el de U9 (14), comparar
    # dentro de cada sector la coloca mejor: exactamente lo que se pedía
    # (no comparar el EV/EBITDA de un semiconductor con el de una aseguradora).
    assert df.loc["T0", "pe_pct"] > df.loc["U9", "pe_pct"]


def test_lowest_risk_company_gets_highest_risk_score():
    df = scoring.build_scores(_sample_df())
    assert df.loc["AAA", "risk_score"] > df.loc["CCC", "risk_score"]


def test_debt_to_equity_affects_risk_not_quality():
    assert "debt_to_equity" in scoring.RISK_METRICS_LOWER_BETTER
    assert "debt_to_equity" not in scoring.QUALITY_METRICS_HIGHER_BETTER

    df_raw = _sample_df()
    # AAA y BBB idénticas en todo salvo deuda: AAA con menos deuda.
    df_raw.loc["BBB"] = df_raw.loc["AAA"]
    df_raw.loc["BBB", "debt_to_equity"] = 500.0  # mucha más deuda que AAA (20.0)
    df = scoring.build_scores(df_raw)

    assert df.loc["AAA", "quality_score"] == df.loc["BBB", "quality_score"]
    assert df.loc["AAA", "risk_score"] > df.loc["BBB", "risk_score"]


def test_composite_uses_four_blocks_including_risk():
    df_raw = _sample_df()
    only_risk = scoring.build_scores(
        df_raw, weights={"value": 0.0, "quality": 0.0, "momentum": 0.0, "risk": 1.0},
    )
    assert only_risk.index[0] == "AAA"  # AAA es la de menor riesgo
    assert (only_risk["composite_score"] == only_risk["risk_score"]).all()


def test_small_sector_group_falls_back_to_global_percentile():
    df = pd.DataFrame(
        {"pe": [10, 20, 30, 5, 15, 25], "sector": ["Tech"] * 5 + ["Utilities"] * 1},
        index=["A", "B", "C", "D", "E", "F"],
    )
    within = scoring.add_percentile_columns(df, ["pe"], higher_is_better=False, min_group_size=8)
    global_only = scoring._percentile(df["pe"], higher_is_better=False)
    # F es la única empresa de su sector: por debajo de min_group_size debe
    # caer al percentil global en vez de "ganar" su sector por defecto.
    assert within.loc["F", "pe_pct"] == global_only.loc["F"]


def test_sparse_company_has_no_composite_score():
    df = pd.DataFrame({"pe": [10, 20], "pb": [1, np.nan]}, index=["A", "B"])
    result = scoring.build_scores(df)
    assert result.loc["A", "metrics_available"] == 2
    assert result.loc["A", "metrics_possible"] == 13
    assert pd.isna(result.loc["A", "composite_score"])


def _full_coverage_df():
    """Las 13 métricas de SCORE_METRICS presentes para las 3 filas -- para
    aislar los tests de confidence de qué metricas concretas faltan."""
    return pd.DataFrame(
        {
            "pe": [10, 20, 30], "pb": [1.0, 2.0, 3.0], "ev_ebitda": [8.0, 12.0, 16.0],
            "roic": [0.20, 0.15, 0.10], "operating_margin": [0.30, 0.20, 0.10],
            "revenue_cagr_3y": [0.15, 0.10, 0.05], "fcf_cagr_3y": [0.12, 0.08, 0.04],
            "momentum_12m": [0.25, 0.10, -0.15], "rel_strength_6m": [0.08, 0.0, -0.08],
            "price_vs_sma200": [0.10, 0.02, -0.10],
            "debt_to_equity": [20.0, 60.0, 120.0], "volatility": [0.15, 0.25, 0.40],
            "max_drawdown": [-0.10, -0.25, -0.45],
        },
        index=["AAA", "BBB", "CCC"],
    )


def test_compute_confidence_is_100_with_full_block_coverage():
    df = scoring.build_scores(_full_coverage_df())
    confidence = scoring.compute_confidence(df)
    assert confidence.tolist() == pytest.approx([100.0, 100.0, 100.0])


def test_compute_confidence_matches_the_users_example():
    """Caso exacto senalado por el usuario: una empresa con solo 1 de las 4
    metricas de Quality (aunque ese unico dato sea excelente) debe tener
    confidence mas baja que una con las 4, aunque el quality_score en si
    pueda salir igual de alto para ambas."""
    df_raw = _full_coverage_df()
    # BBB solo conserva roic de Quality; las otras 3 se marcan como no disponibles.
    df_raw.loc["BBB", ["operating_margin", "revenue_cagr_3y", "fcf_cagr_3y"]] = np.nan
    df = scoring.build_scores(df_raw)
    confidence = scoring.compute_confidence(df)

    # Con los pesos por defecto (quality=0.35): BBB pierde 3/4 de la confianza
    # de un bloque que pesa 0.35 -> 100 - 0.35*(3/4)*100 = 73.75
    assert confidence.loc["BBB"] == pytest.approx(73.75)
    assert confidence.loc["AAA"] == pytest.approx(100.0)
    assert confidence.loc["BBB"] < confidence.loc["AAA"]


def test_compute_confidence_zero_when_entire_block_missing():
    df_raw = _full_coverage_df().drop(columns=["roic", "operating_margin", "revenue_cagr_3y", "fcf_cagr_3y"])
    df = scoring.build_scores(df_raw)
    confidence = scoring.compute_confidence(df)
    # Falta el bloque Quality entero (peso 0.35): confidence = 100 * (1 - 0.35) = 65
    assert confidence.tolist() == pytest.approx([65.0, 65.0, 65.0])


def test_compute_confidence_weighs_missing_block_by_its_own_weight():
    """Un bloque de mucho peso que falta debe penalizar mas que uno de poco peso."""
    df_missing_quality = _full_coverage_df().drop(
        columns=["roic", "operating_margin", "revenue_cagr_3y", "fcf_cagr_3y"])
    df_missing_risk = _full_coverage_df().drop(columns=["debt_to_equity", "volatility", "max_drawdown"])
    conf_missing_quality = scoring.compute_confidence(scoring.build_scores(df_missing_quality))
    conf_missing_risk = scoring.compute_confidence(scoring.build_scores(df_missing_risk))
    # quality pesa 0.35 por defecto, risk solo 0.10 -> falta quality duele mas.
    assert (conf_missing_quality < conf_missing_risk).all()


def test_compute_confidence_does_not_change_composite_score():
    """compute_confidence es puramente aditivo -- build_scores (y por tanto
    V1/HIPOTESIS_CONGELADA.md) no cambian en absoluto."""
    df_raw = _full_coverage_df()
    df_raw.loc["BBB", ["operating_margin", "revenue_cagr_3y", "fcf_cagr_3y"]] = np.nan
    before = scoring.build_scores(df_raw.copy())
    scoring.compute_confidence(before)  # no debe mutar `before`
    after = scoring.build_scores(df_raw.copy())
    pd.testing.assert_frame_equal(before, after)
