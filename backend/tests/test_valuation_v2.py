"""FCFF-WACC valuation V2 (#245) over hand-built accounting cases; no network or local data."""

import pytest

from gabi.domain.market import valuation_v2 as val

FY24 = ("2024-01-01", "2024-12-31")
ANCHOR = "2024-12-31"
ASSUMPTIONS = val.Assumptions(risk_free_rate=0.04, equity_risk_premium=0.05, beta=1.0,
                              fallback_pretax_cost_of_debt=0.06, terminal_growth=0.025)
PRETAX = "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"


def flow(value, *, accn="0001-24"):
    return {"start": FY24[0], "end": FY24[1], "val": value, "form": "10-K", "fp": "FY", "accn": accn,
            "filed": "2025-02-15"}


def stock(value, *, accn="0001-24"):
    return {"end": ANCHOR, "val": value, "form": "10-K", "fp": "FY", "accn": accn, "filed": "2025-02-15"}


def company(**overrides):
    tags = {
        "NetCashProvidedByUsedInOperatingActivities": [flow(300.0)],
        "PaymentsToAcquirePropertyPlantAndEquipment": [flow(100.0)],
        "InterestPaidNet": [flow(20.0)],
        "InterestExpense": [flow(25.0)],
        "IncomeTaxExpenseBenefit": [flow(50.0)],
        PRETAX: [flow(200.0)],
        "LongTermDebt": [stock(500.0)],
        "CashAndCashEquivalentsAtCarryingValue": [stock(150.0)],
    }
    tags.update(overrides)
    shares = {"WeightedAverageNumberOfDilutedSharesOutstanding": {"units": {"shares": [flow(100.0)]}}}
    gaap = {tag: {"units": {"USD": rows}} for tag, rows in tags.items() if rows is not None}
    return {"facts": {"us-gaap": gaap | shares}}


def test_fcff_adds_back_after_tax_interest_paid_and_subtracts_capex():
    metric = val.fcff(company(), ANCHOR, sic=3571)
    assert metric.state == "computed" and metric.convention == "cfo+interest_paid*(1-t)-capex(effective_tax)"
    assert metric.value == pytest.approx(300 + 20 * 0.75 - 100)
    assert {fact.tag for fact in metric.inputs} >= {"InterestPaidNet", "PaymentsToAcquirePropertyPlantAndEquipment"}


def test_missing_capex_or_interest_is_absent_never_zero():
    no_capex = val.fcff(company(PaymentsToAcquirePropertyPlantAndEquipment=None), ANCHOR, sic=None)
    no_interest = val.fcff(company(InterestPaidNet=None), ANCHOR, sic=None)
    assert (no_capex.value, no_capex.reason) == (None, "capex_absent")
    assert (no_interest.value, no_interest.reason) == (None, "interest_paid_absent")


def test_interest_paid_may_be_omitted_only_with_declared_zero_debt():
    metric = val.fcff(company(InterestPaidNet=None, LongTermDebt=[stock(0.0)]), ANCHOR, sic=None)
    assert metric.state == "computed" and metric.value == pytest.approx(200.0)


def test_wacc_weights_capm_equity_and_after_tax_observed_cost_of_debt():
    metric = val.wacc(company(), ANCHOR, 1500.0, ASSUMPTIONS, sic=None)
    # kd = 25/500; E/(D+E) = 0.75.
    assert metric.convention == "capm_equity+book_debt(kd=interest_expense/closing_debt,effective_tax)"
    assert metric.value == pytest.approx(0.75 * 0.09 + 0.25 * 0.05 * 0.75)


def test_implausible_observed_cost_of_debt_uses_the_declared_fallback():
    metric = val.wacc(company(InterestExpense=[flow(400.0)]), ANCHOR, 1500.0, ASSUMPTIONS, sic=None)
    assert "kd=assumed" in metric.convention
    assert metric.value == pytest.approx(0.75 * 0.09 + 0.25 * 0.06 * 0.75)


def test_zero_debt_wacc_is_the_cost_of_equity():
    facts = company(LongTermDebt=[stock(0.0)], InterestExpense=None)
    assert val.wacc(facts, ANCHOR, 1500.0, ASSUMPTIONS, sic=None).value == pytest.approx(0.09)


def test_valuation_bridges_enterprise_value_to_value_per_diluted_share():
    result = val.valuation(company(), ANCHOR, 1500.0, 0.05, ASSUMPTIONS, sic=None)
    rate = result.wacc.value
    expected = val.present_value(215.0, 0.05, rate, 0.025, 5)
    assert result.enterprise_value.value == pytest.approx(expected)
    assert result.equity_value.value == pytest.approx(expected - 500 + 150)
    assert result.value_per_share.value == pytest.approx((expected - 350) / 100)
    assert result.value_per_share.convention == "equity_value/weighted_average_diluted_shares"


def test_missing_cash_blocks_the_bridge_but_keeps_the_enterprise_value():
    result = val.valuation(company(CashAndCashEquivalentsAtCarryingValue=None), ANCHOR, 1500.0, 0.05,
                           ASSUMPTIONS, sic=None)
    assert result.enterprise_value.state == "computed"
    assert (result.equity_value.reason, result.value_per_share.state) == ("cash_absent", "absent")


def test_debt_larger_than_enterprise_value_is_not_meaningful_per_share():
    result = val.valuation(company(LongTermDebt=[stock(50_000.0)], InterestExpense=None), ANCHOR, 1500.0, 0.0,
                           ASSUMPTIONS, sic=None)
    assert result.equity_value.value < 0
    assert (result.value_per_share.state, result.value_per_share.reason) == ("not_meaningful",
                                                                            "non_positive_equity_value")


def test_negative_fcff_and_terminal_growth_at_wacc_are_not_meaningful():
    negative = val.valuation(company(NetCashProvidedByUsedInOperatingActivities=[flow(10.0)]), ANCHOR, 1500.0,
                             0.05, ASSUMPTIONS, sic=None)
    assert negative.enterprise_value.reason == "non_positive_fcff"
    high_terminal = val.Assumptions(0.04, 0.05, 1.0, 0.06, terminal_growth=0.2)
    blocked = val.valuation(company(), ANCHOR, 1500.0, 0.05, high_terminal, sic=None)
    assert blocked.enterprise_value.reason == "terminal_growth_not_below_wacc"


def test_financial_sector_is_not_applicable():
    result = val.valuation(company(), ANCHOR, 1500.0, 0.05, ASSUMPTIONS, sic=6021)
    assert {result.fcff.state, result.value_per_share.state} == {"not_applicable"}


def test_value_falls_with_the_discount_rate_and_rises_with_growth():
    values = [val.present_value(100.0, 0.05, rate, 0.025, 5) for rate in (0.07, 0.08, 0.09, 0.10)]
    assert values == sorted(values, reverse=True)
    values = [val.present_value(100.0, growth, 0.09, 0.025, 5) for growth in (-0.1, 0.0, 0.05, 0.1)]
    assert values == sorted(values)
    values = [val.present_value(100.0, 0.05, 0.09, terminal, 5) for terminal in (0.0, 0.01, 0.02, 0.03)]
    assert values == sorted(values)


def test_value_per_share_rises_with_cash_and_falls_with_beta():
    # More debt is not monotonic: cheaper capital can raise the enterprise value more than the debt.
    per_share = [val.valuation(company(CashAndCashEquivalentsAtCarryingValue=[stock(cash)]), ANCHOR, 1500.0, 0.05,
                               ASSUMPTIONS, sic=None).value_per_share.value for cash in (0.0, 150.0, 300.0)]
    assert per_share == sorted(per_share)
    betas = [val.valuation(company(), ANCHOR, 1500.0, 0.05,
                           val.Assumptions(0.04, 0.05, beta, 0.06, 0.025), sic=None).value_per_share.value
             for beta in (0.8, 1.0, 1.2)]
    assert betas == sorted(betas, reverse=True)


def test_implied_growth_reproduces_the_observed_enterprise_value_and_rises_with_price():
    metric = val.implied_growth(company(), ANCHOR, 1500.0, ASSUMPTIONS, sic=None)
    rate = val.wacc(company(), ANCHOR, 1500.0, ASSUMPTIONS, sic=None).value
    assert metric.state == "computed"
    assert val.present_value(215.0, metric.value, rate, 0.025, 5) == pytest.approx(1500 + 500 - 150, rel=1e-6)
    growths = [val.implied_growth(company(), ANCHOR, cap, ASSUMPTIONS, sic=None).value for cap in (1500.0, 3000.0)]
    assert growths == sorted(growths)


def test_implied_growth_propagates_absent_debt():
    metric = val.implied_growth(company(LongTermDebt=None), ANCHOR, 1500.0, ASSUMPTIONS, sic=None)
    assert (metric.value, metric.reason) == (None, "debt_absent")
