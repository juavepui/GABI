import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gabi import capital_allocation as ca


def _facts(rows):
    return pd.DataFrame(rows, columns=["tag", "unit", "start_date", "end_date", "val", "form", "filed_date"])


def test_metrics_use_only_filed_information_and_report_ratios():
    facts = _facts([
        ("CommonStockSharesOutstanding", "shares", "", "2022-12-31", 100, "10-K", "2023-02-01"),
        ("CommonStockSharesOutstanding", "shares", "", "2023-12-31", 90, "10-K", "2024-02-01"),
        ("PaymentsForRepurchaseOfCommonStock", "USD", "2023-01-01", "2023-12-31", -20, "10-K", "2024-02-01"),
        ("PaymentsForRepurchaseOfCommonStock", "USD", "2024-01-01", "2024-12-31", -99, "10-K", "2025-02-01"),
        ("PaymentsToAcquirePropertyPlantAndEquipment", "USD", "2023-01-01", "2023-12-31", -30, "10-K", "2024-02-01"),
        ("NetCashProvidedByUsedInOperatingActivities", "USD", "2023-01-01", "2023-12-31", 100, "10-K", "2024-02-01"),
        ("PaymentsToAcquireBusinesses", "USD", "2023-01-01", "2023-12-31", -10, "10-K", "2024-02-01"),
    ])
    result = ca.metrics(facts, "2024-12-31", market_cap=1000)
    assert result["shares_dilution_yoy"] == pytest.approx(-.1)
    assert result["buybacks_latest"] == pytest.approx(20)
    assert result["buyback_yield"] == pytest.approx(.02)
    assert result["capex_to_ocf"] == pytest.approx(.3)
    assert result["acquisitions_latest"] == pytest.approx(10)
    assert result["capital_allocation_coverage"] == "4/5"


def test_missing_facts_are_none_not_zero():
    result = ca.metrics(pd.DataFrame(), "2024-12-31")
    assert result["buybacks_latest"] is None
    assert result["shares_dilution_yoy"] is None
    assert result["capital_allocation_coverage"] == "0/5"
