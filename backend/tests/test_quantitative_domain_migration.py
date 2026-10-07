"""Synthetic reference outputs captured from develop 486942a before relocation."""

import importlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from gabi import config, live_ledger, storage
from gabi.domain.market import risk, technicals
from gabi.domain.portfolio import metrics, rotation
from gabi.domain.research import statistics
from gabi.infrastructure.legacy.market import calculators


def price_inputs(case):
    index = pd.bdate_range("2022-01-03", periods=300)
    t = np.arange(300)
    close = 100 * np.exp(.0004 * t + .03 * np.sin(t / 7))
    stock = pd.DataFrame({"close": close}, index=index)
    benchmark = pd.DataFrame({"close": 200 * np.exp(.0002 * t + .01 * np.cos(t / 9))}, index=index)
    if case == "empty":
        stock = stock.iloc[:0]
    elif case == "short":
        stock = stock.iloc[:12]
    elif case == "constant":
        stock["close"] = 100.
    elif case == "adjusted":
        stock["adj_close"] = close * (1 + t / 3000)
    elif case == "partial_adjusted":
        stock["adj_close"] = close * 1.1
        stock.loc[index[20], "adj_close"] = np.nan
    elif case == "missing_close":
        stock.loc[index[20], "close"] = np.nan
    elif case == "benchmark_gap":
        benchmark = benchmark.drop(index[-127])
    elif case == "loss":
        stock.loc[index[-1], "close"] = 0.
    return stock, benchmark


CASES = ("empty", "short", "constant", "default", "adjusted", "partial_adjusted",
         "missing_close", "benchmark_gap", "loss")


def portfolio_outputs(module):
    stock, benchmark = price_inputs("default")
    returns = module.returns_from_nav(stock["close"])
    bench_returns = module.returns_from_nav(benchmark["close"])
    return {"tail": module.tail_risk_metrics(returns, horizon="una sesión"),
            "calmar": module.calmar_ratio(.08, -.12),
            "recovery": module.recovery_time(stock["close"]),
            "beta": module.beta_vs_benchmark(returns, bench_returns),
            "tracking_error": module.tracking_error(returns, bench_returns),
            "information_ratio": module.information_ratio(returns, bench_returns),
            "capture": module.capture_ratios(returns, bench_returns),
            "rolling": module.rolling_sharpe(returns, 63, .025).tolist()}


def statistics_outputs(module):
    stock, _ = price_inputs("default")
    returns = stock["close"].pct_change().dropna()
    return {"psr": module.probabilistic_sharpe_ratio_from_returns(returns, 252),
            "dsr": module.deflated_sharpe_ratio(.8, [.3, .6, .8, -.2], 299, 252),
            "bootstrap": module.bootstrap_sharpe_ci(returns, 252, n_boot=64, seed=123),
            "pbo": module.pbo_cscv(pd.DataFrame({"a": returns, "b": -returns, "c": returns.shift(1).fillna(.001)}), 4)}


def canonical(value):
    return json.loads(json.dumps(value, default=float))


def assert_reference(actual, expected):
    """Allow only machine rounding across Windows/Linux numeric libraries."""
    if isinstance(expected, dict):
        assert actual.keys() == expected.keys()
        for key in expected:
            assert_reference(actual[key], expected[key])
    elif isinstance(expected, list):
        assert len(actual) == len(expected)
        for observed, reference in zip(actual, expected, strict=True):
            assert_reference(observed, reference)
    elif isinstance(expected, float):
        assert np.isfinite(actual)
        assert actual == pytest.approx(expected, rel=1e-12, abs=1e-14)
    else:
        assert actual == expected


@pytest.fixture(scope="module")
def reference():
    return json.loads((Path(__file__).parent / "fixtures/quantitative_migration.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES)
def test_price_metrics_match_pre_migration_reference(reference, case):
    stock, benchmark = price_inputs(case)
    original = stock.copy(deep=True)
    assert_reference(canonical(technicals.compute_technicals(stock, benchmark)), reference[case]["technicals"])
    assert_reference(canonical(risk.compute_risk_metrics(stock, benchmark, .025)), reference[case]["risk"])
    pd.testing.assert_frame_equal(stock, original)


def test_portfolio_and_statistics_match_pre_migration_reference(reference):
    assert_reference(canonical(portfolio_outputs(metrics)), reference["portfolio"])
    assert_reference(canonical(statistics_outputs(statistics)), reference["statistics"])


def test_explicit_parameters_and_legacy_configuration(reference, monkeypatch):
    stock, benchmark = price_inputs("default")
    parameters = technicals.TechnicalParameters(20, 80, 14, 21, 63)
    assert_reference(canonical(technicals.compute_technicals(stock, benchmark, parameters=parameters)), reference["custom_technicals"])
    for name, value in (("SMA_SHORT", 20), ("SMA_LONG", 80), ("MOMENTUM_SHORT_DAYS", 21), ("MOMENTUM_LONG_DAYS", 63), ("RISK_FREE_RATE", .025)):
        monkeypatch.setattr(config, name, value)
    old_tech = importlib.import_module("gabi.technicals")
    old_risk = importlib.import_module("gabi.risk")
    assert_reference(canonical(old_tech.compute_technicals(stock, benchmark)), reference["custom_technicals"])
    assert_reference(canonical(old_risk.compute_risk_metrics(stock, benchmark)), reference["default"]["risk"])
    # Composition captures the parameters; later global changes do not affect an operation.
    composed = calculators()
    monkeypatch.setattr(config, "SMA_SHORT", 3)
    assert_reference(canonical(composed.technicals(stock, benchmark)), reference["custom_technicals"])
    assert composed.risk is risk.compute_risk_metrics


@pytest.mark.parametrize(("legacy", "domain"), [("rotation_policy", rotation), ("stats_rigor", statistics),
                                                  ("portfolio_metrics", metrics)])
def test_formula_aliases_share_domain_implementation(legacy, domain):
    module = importlib.import_module(f"gabi.{legacy}")
    for name, member in vars(domain).items():
        if callable(member) and getattr(member, "__module__", None) == domain.__name__ and name != "rolling_sharpe":
            assert getattr(module, name) is member


def test_domain_has_no_network_storage_or_global_settings(monkeypatch):
    monkeypatch.setattr(storage, "get_connection", lambda: pytest.fail("Domain accessed SQLite"))
    monkeypatch.setattr("requests.sessions.Session.request", lambda *a, **k: pytest.fail("Domain accessed network"))
    monkeypatch.setattr(config, "SMA_SHORT", 1)
    monkeypatch.setattr(config, "RISK_FREE_RATE", .9)
    stock, benchmark = price_inputs("default")
    assert technicals.compute_technicals(stock, benchmark)["sma50"] != stock["close"].iloc[-1]
    assert risk.compute_risk_metrics(stock, benchmark, .025)["sharpe_ratio"] > 0
    assert portfolio_outputs(metrics)["tracking_error"] > 0
    assert statistics_outputs(statistics)["bootstrap"]["n_boot"] == 64


def test_ledger_tracks_relocated_price_formulas(monkeypatch):
    monkeypatch.setattr("gabi.research_lab._dependency_versions", lambda: {})
    monkeypatch.setattr("gabi.research_lab._env_fingerprint", lambda: "fixture")
    monkeypatch.setattr("gabi.research_lab._current_git_commit", lambda: "fixture")
    hashes = live_ledger.model_metadata()["code_sha256"]
    assert "domain/market/technicals.py" in hashes and "domain/market/risk.py" in hashes
