"""Compatibility, missing-data semantics and provenance of the first #90 leaf migration."""

import hashlib
import importlib
import inspect

import pandas as pd
import pytest

from gabi import config, live_ledger, storage
from gabi.domain.market import fundamentals, valuation_expectations
from gabi.domain.portfolio import broker_costs, capital_allocation
from gabi.infrastructure.legacy.market import calculators


@pytest.mark.parametrize(("legacy", "domain", "exports"), [
    ("metrics", "market.fundamentals", ("compute_fundamental_metrics", "_positive_or_none", "_revenue_growth_from_quarterly")),
    ("capital_allocation", "portfolio.capital_allocation", ("metrics", "_annual_series", "_instant_series", "BUYBACK_TAGS")),
    ("valuation_expectations", "market.valuation_expectations", ("expectations_metrics", "reverse_dcf_growth", "_present_value")),
    ("broker_costs", "portfolio.broker_costs", ("effective_trade_cost_bps", "position_size_usd", "STOCK_FEE_USD")),
])
def test_legacy_entry_points_are_the_same_domain_implementation(legacy, domain, exports):
    old = importlib.import_module(f"gabi.{legacy}")
    new = importlib.import_module(f"gabi.domain.{domain}")
    for name in exports:
        assert getattr(old, name) is getattr(new, name)
        if callable(getattr(old, name)):
            assert inspect.signature(getattr(old, name)) == inspect.signature(getattr(new, name))


def test_api_ranking_uses_domain_fundamentals_directly():
    assert calculators().fundamentals is fundamentals.compute_fundamental_metrics


def test_domain_calculations_never_use_a_connection_or_network(monkeypatch):
    monkeypatch.setattr(storage, "get_connection", lambda: pytest.fail("No database in domain calculations"))
    monkeypatch.setattr("requests.sessions.Session.request", lambda *a, **k: pytest.fail("No network"))
    assert fundamentals.compute_fundamental_metrics({"info": {"trailingPE": "20"}})["pe"] == 20
    assert capital_allocation.metrics(pd.DataFrame(), "2024-12-31")["buybacks_latest"] is None
    assert valuation_expectations.reverse_dcf_growth(1000, 0) is None
    assert broker_costs.effective_trade_cost_bps(500) == 20


def test_capital_allocation_preserves_filing_cutoff_revisions_and_partial_coverage():
    facts = pd.DataFrame([
        ("PaymentsForRepurchaseOfCommonStock", "USD", "2023-01-01", "2023-12-31", 10, "10-K", "2024-02-01"),
        ("PaymentsForRepurchaseOfCommonStock", "USD", "2023-01-01", "2023-12-31", 12, "10-K", "2024-03-01"),
        ("PaymentsForRepurchaseOfCommonStock", "USD", "2023-01-01", "2023-12-31", 99, "10-K", "2024-05-01"),
        ("PaymentsForRepurchaseOfCommonStock", "USD", "2023-01-01", "2023-12-31", 999, "10-K", None),
    ], columns=["tag", "unit", "start_date", "end_date", "val", "form", "filed_date"])
    original = facts.copy(deep=True)
    result = capital_allocation.metrics(facts, "2024-04-01", market_cap=100)
    assert result["buybacks_latest"] == 12
    assert result["buyback_yield"] == .12
    assert result["issuance_latest"] is None
    # Preserve the descriptive metric's existing partial-pair convention during this refactor.
    assert result["net_share_issuance_latest"] == -12
    assert result["shares_dilution_yoy"] is None and result["capital_allocation_coverage"] == "1/5"
    pd.testing.assert_frame_equal(facts, original)


def test_current_ledger_provenance_includes_the_actual_fundamentals_code(monkeypatch):
    monkeypatch.setattr("gabi.research_lab._dependency_versions", lambda: {})
    monkeypatch.setattr("gabi.research_lab._env_fingerprint", lambda: "fixture")
    monkeypatch.setattr("gabi.research_lab._current_git_commit", lambda: "fixture")
    record = live_ledger.model_metadata()
    path = config.BASE_DIR / "src/gabi/domain/market/fundamentals.py"
    expected = hashlib.sha256(path.read_text(encoding="utf-8").encode()).hexdigest()
    assert record["code_sha256"]["domain/market/fundamentals.py"] == expected
    assert "metrics.py" in record["code_sha256"]
