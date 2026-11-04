"""The app's ranking against the historical engine's on the same day (#291), over example data only."""

from datetime import date

import pandas as pd
import pytest

from gabi.application.administration.jobs import JobCommand
from gabi.application.errors import QueryError
from gabi.application.market.ranking_parity import compare_rankings
from gabi.domain.market import metrics_comparison as compare
from gabi.domain.market import scoring

WEIGHTS = {"value": 0.5, "quality": 0.5}
METRICS = {"value": ["pe"], "quality": ["roic"]}
SOURCES = {"live": {"pe": ("yahoo", "ttm"), "roic": ("sec_10k", "fiscal_year")},
           "historical": {"pe": ("sec_10k", "fiscal_year"), "roic": ("sec_10k", "fiscal_year")}}


def scored(rows: dict[str, tuple[float | None, float | None]]) -> pd.DataFrame:
    """Already-scored rows: percentiles of PE and ROIC, each block with one metric and half the weight."""
    frame = pd.DataFrame([{"symbol": symbol, "pe": pe, "roic": roic, "pe_pct": pe, "roic_pct": roic,
                           "value_score": pe, "quality_score": roic, "fundamentals_period_end": "2025-12-31"}
                          for symbol, (pe, roic) in rows.items()]).set_index("symbol")
    frame["composite_score"] = frame[["value_score", "quality_score"]].mean(axis=1)
    return frame


def raw(roic_b: float | None = 0.1) -> pd.DataFrame:
    """Raw metrics of five companies, enough of the 13 scored ones for a composite score."""
    return pd.DataFrame({
        "pe": [10.0, 20.0, 15.0, 30.0, 12.0], "pb": [1.0, 3.0, 2.0, 4.0, 1.5],
        "ev_ebitda": [8.0, 12.0, 10.0, 20.0, 9.0], "roic": [0.2, roic_b, 0.15, 0.05, 0.3],
        "operating_margin": [0.2, 0.1, 0.15, 0.05, 0.25], "revenue_cagr_3y": [0.05, 0.1, 0.0, 0.2, 0.08],
        "fcf_cagr_3y": [0.04, 0.12, 0.01, 0.15, 0.07], "momentum_12m": [0.1, 0.2, 0.0, -0.1, 0.05],
        "rel_strength_6m": [0.02, 0.05, -0.01, -0.03, 0.0], "volatility": [0.2, 0.3, 0.25, 0.4, 0.22],
    }, index=list("ABCDE"))


def parity(live, historical, top_n=2):
    return compare.live_vs_historical(live, historical, weights=WEIGHTS, score_metrics=METRICS,
                                      sources=SOURCES, top_n=top_n)


def test_identical_rankings_agree_completely():
    table = scoring.build_scores(raw())
    report = compare.live_vs_historical(table, table.copy(), weights=dict(scoring.DEFAULT_WEIGHTS),
                                        score_metrics=scoring.SCORE_METRICS, sources=SOURCES, top_n=3)
    assert report["spearman"] == pytest.approx(1.0)
    assert report["top_overlap"] == 1.0
    assert report["only_live_top"] == report["only_historical_top"] == []
    assert report["largest_differences"] == []
    assert report["companies"] == {"live": 5, "historical": 5, "universe": 5, "both_scored": 5}


def test_a_known_difference_computed_by_hand():
    # Only C changes: its PE percentile is 90 with Yahoo and 30 with the SEC 10-K.
    # Composite C: 0.5·90 + 0.5·50 = 70 live, 0.5·30 + 0.5·50 = 40 historical.
    live = scored({"A": (80, 80), "B": (60, 60), "C": (90, 50), "D": (20, 20)})
    historical = scored({"A": (80, 80), "B": (60, 60), "C": (30, 50), "D": (20, 20)})
    report = parity(live, historical)
    # Orders A C B D and A B C D: d² = 0 + 1 + 1 + 0 = 2, so 1 − 6·2 / (4·15) = 0.8.
    assert report["spearman"] == pytest.approx(0.8)
    # Top-2 {A, C} against {A, B}: half shared.
    assert report["top_overlap"] == 0.5
    assert report["only_live_top"] == ["C"] and report["only_historical_top"] == ["B"]
    first, second = report["largest_differences"]
    assert (first["symbol"], first["live_rank"], first["historical_rank"], first["rank_change"]) == ("C", 2, 3, 1)
    assert first["composite_difference"] == pytest.approx(30.0)
    assert first["cause"]["metric"] == "pe" and first["cause"]["impact"] == pytest.approx(30.0)
    assert first["cause"]["live_source"] == ("yahoo", "ttm")
    assert first["cause"]["historical_source"] == ("sec_10k", "fiscal_year")
    assert first["cause"]["historical_period_end"] == "2025-12-31"
    # B's own inputs agree: it moved only because C did.
    assert second["symbol"] == "B" and second["rank_change"] == -1 and second["cause"] is None
    assert report["blocks"]["quality"] == pytest.approx(1.0)


def test_contributions_add_up_and_a_missing_metric_shifts_its_weight():
    row = scoring.build_scores(raw(roic_b=None)).loc["B"]
    assert pd.notna(row["composite_score"])
    parts = compare.contributions(row, dict(scoring.DEFAULT_WEIGHTS), scoring.SCORE_METRICS)
    assert sum(parts.values()) == pytest.approx(row["composite_score"])
    assert parts["roic"] == 0.0
    live = scored({"A": (80, 80), "B": (60, 60), "C": (90, None), "D": (20, 20)})
    historical = scored({"A": (80, 80), "B": (60, 60), "C": (90, 10), "D": (20, 20)})
    cause = next(row for row in parity(live, historical)["largest_differences"] if row["symbol"] == "C")["cause"]
    assert cause["metric"] == "pe" and cause["missing"] is None
    # Without ROIC live, C's composite is its PE alone: the PE contribution doubles.
    assert cause["impact"] == pytest.approx(90 - 45)


def test_compare_rankings_uses_the_same_universe_day_and_weights():
    calls = []
    table = scored({"A": (80, 80), "B": (60, 60), "C": (90, 50)})
    report = compare_rankings(universe=lambda: ["A", "B", "C"], live=lambda: table,
                              historical=lambda symbols, day: calls.append((symbols, day)) or table.copy(),
                              weights=WEIGHTS, score_metrics=METRICS, model_id="GABI-MF-v2",
                              metrics_version="sec-metrics-v2.1", today=date(2026, 9, 28))
    assert calls == [(["A", "B", "C"], date(2026, 9, 28))]
    assert report["as_of"] == "2026-09-28" and report["model_id"] == "GABI-MF-v2"
    assert report["spearman"] == pytest.approx(1.0)
    assert {row["metric"]: row["historical_source"] for row in report["metrics"]}["pe"] == ("sec_10k", "fiscal_year")


def test_the_job_takes_no_dates():
    JobCommand("ranking_parity")
    with pytest.raises(QueryError):
        JobCommand("ranking_parity", start="2020-06-30")


def test_the_worker_compares_the_app_ranking_without_writing(tmp_path):
    from market_fixture import TODAY as FIXTURE_TODAY
    from market_fixture import seed_fixture

    from gabi.infrastructure.legacy.jobs import LegacyExecutor
    from gabi.infrastructure.settings import Settings

    seed_fixture(tmp_path)
    stamp = (tmp_path / "gabi.db").stat().st_mtime_ns
    asked, phases = [], []

    def engine(symbols, day, weights):
        """Stands in for screener_asof: the same rows with the first company's PE missing."""
        asked.append((len(symbols), day, weights))
        frame = live_table.copy()
        frame.loc[frame.index[0], "pe"] = None
        return scoring.build_scores(frame.drop(columns=[c for c in frame if c.endswith(("_pct", "_score"))]),
                                    weights=weights)

    executor = LegacyExecutor(Settings(tmp_path), today=lambda: FIXTURE_TODAY, parity_engine=engine)
    from gabi.infrastructure.legacy.market import calculators, model_policy
    from gabi.infrastructure.model_versions import active_model
    from gabi.infrastructure.storage.market import ReadOnlyMarket

    model = active_model()
    market = ReadOnlyMarket(Settings(tmp_path), calculators(model.technical), model_policy(model),
                            model.benchmark_symbol, model.risk_free_rate, metrics_version=model.metrics_version)
    try:
        live_table = market.ranking(dict(model.weights), FIXTURE_TODAY).table
    finally:
        market.close()
    report = executor(JobCommand("ranking_parity"), lambda share, phase: phases.append(share))
    assert asked == [(16, FIXTURE_TODAY, dict(model.weights))]
    assert report["as_of"] == FIXTURE_TODAY.isoformat() and report["model_id"] == model.model_id
    assert report["companies"]["universe"] == 16 and report["spearman"] is not None
    assert phases and phases[-1] < 1.0
    assert (tmp_path / "gabi.db").stat().st_mtime_ns == stamp


def test_the_agreement_level_reads_the_rank_correlation():
    live = scored({"A": (80, 80), "B": (60, 60), "C": (90, 50), "D": (20, 20)})
    historical = scored({"A": (80, 80), "B": (60, 60), "C": (30, 50), "D": (20, 20)})
    assert parity(live, live.copy())["agreement"] == "very_similar"
    assert parity(live, historical)["agreement"] == "similar"  # 0.8
    reversed_order = scored({"A": (20, 20), "B": (60, 60), "C": (70, 70), "D": (90, 90)})
    assert parity(live, reversed_order)["agreement"] == "different"
