"""SEC metrics V2 (#245) over hand-built accounting cases; no network or local data."""

import pytest

from gabi.domain.market import sec_metrics_v2 as v2

FY24, FY23 = ("2024-01-01", "2024-12-31"), ("2023-01-01", "2023-12-31")


def flow(value, period=FY24, *, accn="0001-24", filed="2025-02-15", form="10-K"):
    return {"start": period[0], "end": period[1], "val": value, "form": form, "fp": "FY",
            "accn": accn, "filed": filed}


def stock(value, end="2024-12-31", *, accn="0001-24", filed="2025-02-15", form="10-K"):
    return {"end": end, "val": value, "form": form, "fp": "FY", "accn": accn, "filed": filed}


def company(**tags):
    return {"facts": {"us-gaap": {tag: {"units": {"USD": rows}} for tag, rows in tags.items()}}}


def base(**overrides):
    tags = {
        "OperatingIncomeLoss": [flow(200.0)],
        "IncomeTaxExpenseBenefit": [flow(45.0)],
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest": [flow(180.0)],
        "StockholdersEquity": [stock(900.0, "2023-12-31"), stock(1100.0)],
        "LongTermDebtNoncurrent": [stock(400.0, "2023-12-31"), stock(380.0)],
        "LongTermDebtCurrent": [stock(50.0, "2023-12-31"), stock(40.0)],
        "CashAndCashEquivalentsAtCarryingValue": [stock(150.0, "2023-12-31"), stock(200.0)],
    }
    tags.update(overrides)
    return company(**{tag: rows for tag, rows in tags.items() if rows is not None})


def test_roic_uses_nopat_with_effective_tax_over_average_invested_capital():
    metric = v2.roic(base(), "2024-12-31", sic=3571)
    # NOPAT = 200 × (1 − 45/180); capital = ((900+450−150) + (1100+420−200)) / 2 = 1260.
    assert metric.state == "computed" and metric.convention == "nopat(effective_tax)/average_invested_capital"
    assert metric.value == pytest.approx(200 * 0.75 / 1260)
    assert {fact.accession for fact in metric.inputs} == {"0001-24"}
    assert all(fact.tag and fact.end and fact.filed for fact in metric.inputs)


def test_loss_before_tax_falls_back_to_the_declared_statutory_rate():
    facts = base(**{"IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest":
                    [flow(-10.0)]})
    metric = v2.roic(facts, "2024-12-31", sic=None)
    assert metric.convention == "nopat(statutory_tax_21)/average_invested_capital"
    assert metric.value == pytest.approx(200 * 0.79 / 1260)


def test_missing_debt_is_absent_never_zero_when_the_issuer_has_reported_debt():
    # DebtCurrent in an old report shows the issuer has debt lines: nothing is assumed.
    facts = base(LongTermDebtNoncurrent=None, LongTermDebtCurrent=None, DebtCurrent=[stock(10.0, "2019-12-31")])
    assert v2.total_debt(facts, "2024-12-31")[0].state == "absent"
    roic = v2.roic(facts, "2024-12-31", sic=None)
    ev = v2.enterprise_value(facts, "2024-12-31", 5000.0, sic=None)
    assert (roic.value, roic.reason) == (None, "debt_absent")
    assert (ev.value, ev.reason) == (None, "debt_absent")


def test_debt_is_assumed_zero_and_declared_only_if_never_reported_in_any_annual_report():
    facts = base(LongTermDebtNoncurrent=None, LongTermDebtCurrent=None)
    debt, parts = v2.total_debt(facts, "2024-12-31")
    assert (debt.state, debt.value) == ("assumed_zero", 0.0) and parts[0].state == "assumed_zero"
    roic = v2.roic(facts, "2024-12-31", sic=None)
    # Capital = ((900 − 150) + (1100 − 200)) / 2 = 825.
    assert roic.value == pytest.approx(200 * 0.75 / 825)
    assert any(fact.state == "assumed_zero" for fact in roic.inputs)
    paying = base(LongTermDebtNoncurrent=None, LongTermDebtCurrent=None, InterestExpense=[flow(12.0)])
    assert v2.total_debt(paying, "2024-12-31")[0].state == "absent"  # It pays interest: it has debt.
    stale = base(LongTermDebtNoncurrent=[stock(400.0, "2022-12-31")], LongTermDebtCurrent=None)
    assert v2.total_debt(stale, "2024-12-31")[0].state == "stale"  # Reported other years: a gap, never zero.


def test_each_component_takes_the_first_tag_reporting_the_anchor_year():
    # The issuer moved from the noncurrent/current split to the LongTermDebt total in 2024.
    facts = base(LongTermDebt=[stock(420.0)], LongTermDebtNoncurrent=[stock(400.0, "2023-12-31")],
                 LongTermDebtCurrent=[stock(50.0, "2023-12-31")])
    debt, parts = v2.total_debt(facts, "2024-12-31")
    assert debt.value == 420.0 and [part.tag for part in parts] == ["LongTermDebt"]
    # Equity reported under one tag for 2023 and another for 2024: each year finds its own.
    renamed = base(StockholdersEquity=[stock(1100.0)],
                   StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest=[stock(900.0, "2023-12-31")])
    assert v2.roic(renamed, "2024-12-31", sic=None).state == "computed"


def test_lease_inclusive_debt_tags_are_read_when_the_plain_ones_stopped():
    facts = base(LongTermDebtNoncurrent=[stock(400.0, "2016-12-31")], LongTermDebtCurrent=None,
                 LongTermDebtAndCapitalLeaseObligations=[stock(380.0, "2023-12-31"), stock(360.0)],
                 LongTermDebtAndCapitalLeaseObligationsCurrent=[stock(30.0)])
    debt, parts = v2.total_debt(facts, "2024-12-31")
    assert debt.value == 390.0 and [part.tag for part in parts] == [
        "LongTermDebtAndCapitalLeaseObligations", "LongTermDebtAndCapitalLeaseObligationsCurrent"]


def test_without_an_operating_income_line_the_declared_ebit_proxy_is_used():
    facts = base(OperatingIncomeLoss=None, InterestExpense=[flow(20.0)])
    metric = v2.roic(facts, "2024-12-31", sic=None)
    # EBIT proxy = pretax 180 + interest 20 = 200, the same NOPAT as the operating line.
    assert metric.value == pytest.approx(200 * 0.75 / 1260)
    assert "ebit_proxy=pretax+interest" in metric.convention
    assert [fact.tag for fact in metric.inputs[:3]] == [
        "ebit_proxy", "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "InterestExpense"]
    no_interest = v2.roic(base(OperatingIncomeLoss=None), "2024-12-31", sic=None)
    assert (no_interest.value, no_interest.reason) == (None, "operating_income_absent")  # Has debt: no zero.
    debt_free = base(OperatingIncomeLoss=None, LongTermDebtNoncurrent=None, LongTermDebtCurrent=None)
    proxy = v2.roic(debt_free, "2024-12-31", sic=None)
    assert proxy.state == "computed" and any(fact.tag == "interest_expense" and fact.state == "assumed_zero"
                                             for fact in proxy.inputs)


def test_cash_falls_back_to_the_line_with_restricted_cash_when_the_plain_one_stopped():
    facts = base(CashAndCashEquivalentsAtCarryingValue=[stock(150.0, "2023-12-31")],
                 CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents=[stock(210.0)])
    cash, parts = v2.cash_and_short_term_investments(facts, "2024-12-31")
    assert cash.value == 210.0 and parts[0].tag == "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"


def test_declared_zero_debt_and_cash_are_used():
    facts = base(LongTermDebtNoncurrent=[stock(0.0, "2023-12-31"), stock(0.0)], LongTermDebtCurrent=None,
                 CashAndCashEquivalentsAtCarryingValue=[stock(0.0, "2023-12-31"), stock(0.0)])
    debt, _ = v2.total_debt(facts, "2024-12-31")
    cash, _ = v2.cash_and_short_term_investments(facts, "2024-12-31")
    assert (debt.state, cash.state) == ("reported_zero", "reported_zero")
    assert v2.enterprise_value(facts, "2024-12-31", 5000.0, sic=None).value == 5000.0


def test_total_long_term_debt_is_not_added_to_its_parts_and_short_term_borrowings_count():
    facts = base(LongTermDebt=[stock(420.0)], ShortTermBorrowings=[stock(30.0)])
    debt, parts = v2.total_debt(facts, "2024-12-31")
    assert debt.value == 450.0 and [part.tag for part in parts] == ["LongTermDebt", "ShortTermBorrowings"]
    ev = v2.enterprise_value(facts, "2024-12-31", 5000.0, sic=None)
    assert ev.value == 5000.0 + 450.0 - 200.0


def test_short_term_investments_reduce_enterprise_value():
    facts = base(ShortTermInvestments=[stock(100.0)])
    assert v2.enterprise_value(facts, "2024-12-31", 5000.0, sic=None).value == 5000.0 + 420.0 - 300.0


def test_a_later_amended_filing_replaces_the_original():
    facts = base(OperatingIncomeLoss=[flow(200.0), flow(260.0, accn="0001-25", filed="2025-06-01", form="10-K/A")])
    metric = v2.roic(facts, "2024-12-31", sic=None)
    assert metric.value == pytest.approx(260 * 0.75 / 1260)
    assert metric.inputs[0].accession == "0001-25"


def test_conflicting_values_in_one_filing_are_dropped():
    facts = base(OperatingIncomeLoss=[flow(200.0), flow(210.0)])
    assert v2.roic(facts, "2024-12-31", sic=None).reason == "operating_income_absent"


def test_a_component_of_another_fiscal_year_is_stale():
    facts = base(CashAndCashEquivalentsAtCarryingValue=[stock(150.0, "2022-12-31")])
    ev = v2.enterprise_value(facts, "2024-12-31", 5000.0, sic=None)
    assert (ev.state, ev.reason) == ("stale", "cash_stale")


def test_negative_invested_capital_is_not_meaningful():
    facts = base(StockholdersEquity=[stock(-2000.0, "2023-12-31"), stock(-1800.0)])
    metric = v2.roic(facts, "2024-12-31", sic=None)
    assert (metric.value, metric.state) == (None, "not_meaningful")


def test_roic_needs_an_opening_balance_sheet():
    facts = base(StockholdersEquity=[stock(1100.0)])
    assert v2.roic(facts, "2024-12-31", sic=None).reason == "no_opening_balance_sheet"


def test_quarterly_rows_are_ignored():
    quarter = {**flow(50.0), "start": "2024-10-01"}
    facts = base(OperatingIncomeLoss=[quarter])
    assert v2.roic(facts, "2024-12-31", sic=None).reason == "operating_income_absent"


@pytest.mark.parametrize("sic", [6021, 6311, 6798])
def test_banks_insurers_and_reits_are_not_applicable(sic):
    assert v2.roic(base(), "2024-12-31", sic=sic).state == "not_applicable"
    assert v2.enterprise_value(base(), "2024-12-31", 5000.0, sic=sic).state == "not_applicable"


def test_enterprise_value_needs_a_market_cap():
    assert v2.enterprise_value(base(), "2024-12-31", None, sic=None).reason == "no_market_cap"


def test_enterprise_value_rises_with_debt_and_falls_with_cash():
    low = v2.enterprise_value(base(), "2024-12-31", 5000.0, sic=None).value
    more_debt = v2.enterprise_value(base(ShortTermBorrowings=[stock(10.0)]), "2024-12-31", 5000.0, sic=None).value
    more_cash = v2.enterprise_value(base(ShortTermInvestments=[stock(10.0)]), "2024-12-31", 5000.0, sic=None).value
    assert more_cash < low < more_debt
