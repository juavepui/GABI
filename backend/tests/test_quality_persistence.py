import pytest

from gabi.quality_persistence import from_facts


def _facts():
    def duration(tag, values):
        return {"units": {"USD": [
            {"start": f"{year - 1}-01-01", "end": f"{year}-01-01", "val": value,
             "form": "10-K", "fp": "FY"}
            for year, value in values.items()
        ]}}

    def instant(tag, values):
        return {"units": {"shares": [
            {"end": f"{year}-01-01", "val": value, "form": "10-K", "fp": "FY"}
            for year, value in values.items()
        ]}}

    facts = {"facts": {"us-gaap": {
        "RevenueFromContractWithCustomerExcludingAssessedTax": duration("revenue", {2021: 100, 2022: 110, 2023: 121}),
        "NetIncomeLoss": duration("net_income", {2021: 10, 2022: 11, 2023: 12.1}),
        "OperatingIncomeLoss": duration("operating_income", {2021: 20, 2022: 22, 2023: 24.2}),
        "NetCashProvidedByUsedInOperatingActivities": duration("ocf", {2021: 18, 2022: 20, 2023: 22}),
        "PaymentsToAcquirePropertyPlantAndEquipment": duration("capex", {2021: 8, 2022: 9, 2023: 10}),
        "StockholdersEquity": duration("equity", {2021: 50, 2022: 55, 2023: 60}),
        "LongTermDebtNoncurrent": duration("debt", {2021: 20, 2022: 22, 2023: 24}),
        "CommonStockSharesOutstanding": instant("shares", {2021: 10, 2022: 10, 2023: 11}),
    }}}
    return facts


def test_persistence_uses_annual_history_and_per_share_growth():
    result = from_facts(_facts())
    assert result["roic_years"] == 3
    assert result["roic_positive_years"] == 3
    assert result["operating_margin_positive_years"] == 3
    assert result["fcf_positive_years"] == 3
    assert result["quality_persistence_score"] == pytest.approx(1.0)
    assert result["revenue_per_share_cagr"] == pytest.approx((11 / 10) ** .5 - 1, rel=1e-3)


def test_missing_history_does_not_invent_stability():
    facts = _facts()
    del facts["facts"]["us-gaap"]["OperatingIncomeLoss"]
    result = from_facts(facts)
    assert result["operating_margin_years"] == 0
    assert result["operating_margin_positive_years"] == 0
    assert result["quality_persistence_score"] == pytest.approx(1.0)
