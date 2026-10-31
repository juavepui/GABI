"""FCFF-WACC valuation V2 (#245) with a bridge to value per share.

Version ``valuation-v2-fcff-wacc``. It does not replace ``valuation_expectations``
(CFO − capex against EV at a fixed 9 %/2.5 %), which the live paths keep using
(ADR 0008). The cash flow and the discount rate are consistent: free cash flow to
the firm is discounted at the weighted cost of capital, and the result is an
enterprise value; equity value subtracts financial debt and adds cash. Market
assumptions (risk-free rate, equity premium, beta, horizon, terminal growth) are
parameters chosen by the active model version, never fixed here.
"""

import math
from dataclasses import dataclass

from gabi.domain.market import sec_metrics_v2 as v2
from gabi.domain.market.sec_metrics_v2 import Fact, Metric

VERSION = "valuation-v2-fcff-wacc"
OPERATING_CASH_FLOW_TAGS = ("NetCashProvidedByUsedInOperatingActivities",)
CAPEX_TAGS = ("PaymentsToAcquirePropertyPlantAndEquipment",)
INTEREST_PAID_TAGS = ("InterestPaidNet", "InterestPaid")
INTEREST_EXPENSE_TAGS = ("InterestExpense", "InterestExpenseDebt")
DILUTED_SHARES_TAGS = ("WeightedAverageNumberOfDilutedSharesOutstanding",)
MAX_OBSERVED_COST_OF_DEBT = 0.25
GROWTH_SEARCH = (-0.50, 1.00)


@dataclass(frozen=True)
class Assumptions:
    """Market assumptions declared by the model version that uses this valuation."""

    risk_free_rate: float
    equity_risk_premium: float
    beta: float
    fallback_pretax_cost_of_debt: float
    terminal_growth: float
    forecast_years: int = 5


@dataclass(frozen=True)
class Valuation:
    fcff: Metric
    wacc: Metric
    enterprise_value: Metric
    equity_value: Metric
    value_per_share: Metric


def _reported(fact: Fact) -> bool:
    return fact.state in {"reported", "reported_zero"}


def _failed(convention: str, reason: str, state: str, inputs: tuple[Fact, ...] = ()) -> Metric:
    return Metric(None, state, reason, convention, inputs)


def fcff(facts: dict, anchor: str, *, sic: int | None) -> Metric:
    """FCFF = operating cash flow + after-tax interest paid − capex.

    US GAAP classifies interest paid inside operating cash flow, so it is added
    back net of tax. Interest paid not reported is accepted as zero only when the
    company declares zero financial debt; otherwise FCFF is absent."""
    if v2.financial_sector(sic):
        return _failed("cfo+interest_paid*(1-t)-capex", "financial_sector", "not_applicable")
    rate, tax_convention, tax_inputs = v2.tax_rate(facts, anchor)
    convention = f"cfo+interest_paid*(1-t)-capex({tax_convention})"
    cfo = v2.at(v2.series(facts, OPERATING_CASH_FLOW_TAGS, duration=True), anchor)
    capex = v2.at(v2.series(facts, CAPEX_TAGS, duration=True), anchor)
    for name, fact in (("operating_cash_flow", cfo), ("capex", capex)):
        if not _reported(fact):
            return _failed(convention, f"{name}_{fact.state}", fact.state)
    interest = v2.at(v2.series(facts, INTEREST_PAID_TAGS, duration=True), anchor)
    inputs: tuple[Fact, ...] = (cfo, capex, *tax_inputs)
    if _reported(interest):
        interest_paid, inputs = interest.value or 0.0, inputs + (interest,)
    else:
        debt, debt_parts = v2.total_debt(facts, anchor)
        if debt.state != "reported_zero":
            return _failed(convention, f"interest_paid_{interest.state}", interest.state)
        interest_paid, inputs = 0.0, inputs + debt_parts
    value = (cfo.value or 0.0) + interest_paid * (1 - rate) - (capex.value or 0.0)
    return Metric(value, "computed", None, convention, inputs)


def wacc(facts: dict, anchor: str, market_cap: float | None, assumptions: Assumptions, *,
         sic: int | None) -> Metric:
    """WACC = E/(D+E)·(rf + β·ERP) + D/(D+E)·kd·(1 − t).

    E is the market capitalisation and D the book financial debt (declared proxy
    for its market value). kd is interest expense over closing debt when it lies in
    (0, 25 %]; otherwise the model's fallback pretax cost of debt is declared."""
    base = "capm_equity+book_debt"
    if v2.financial_sector(sic):
        return _failed(base, "financial_sector", "not_applicable")
    if market_cap is None or market_cap <= 0:
        return _failed(base, "no_market_cap", "absent")
    debt, debt_parts = v2.total_debt(facts, anchor)
    if not _reported(debt):
        return _failed(base, f"debt_{debt.state}", debt.state)
    rate, tax_convention, tax_inputs = v2.tax_rate(facts, anchor)
    debt_value = debt.value or 0.0
    interest = v2.at(v2.series(facts, INTEREST_EXPENSE_TAGS, duration=True), anchor)
    observed = (interest.value / debt_value if _reported(interest) and debt_value > 0 else None)
    if observed is not None and 0 < observed <= MAX_OBSERVED_COST_OF_DEBT:
        cost_of_debt, debt_convention, inputs = observed, "kd=interest_expense/closing_debt", (interest,)
    else:
        cost_of_debt, debt_convention, inputs = assumptions.fallback_pretax_cost_of_debt, "kd=assumed", ()
    cost_of_equity = assumptions.risk_free_rate + assumptions.beta * assumptions.equity_risk_premium
    total = market_cap + debt_value
    value = market_cap / total * cost_of_equity + debt_value / total * cost_of_debt * (1 - rate)
    convention = f"{base}({debt_convention},{tax_convention})"
    return Metric(value, "computed", None, convention, debt_parts + inputs + tax_inputs)


def present_value(cash_flow: float, growth: float, discount_rate: float, terminal_growth: float,
                  years: int) -> float | None:
    """Value of ``years`` of cash flow growing at ``growth`` plus a Gordon terminal value.

    ``None`` when the terminal growth is not below the discount rate."""
    if not terminal_growth < discount_rate or years < 1:
        return None
    value = sum(cash_flow * (1 + growth) ** year / (1 + discount_rate) ** year for year in range(1, years + 1))
    terminal = cash_flow * (1 + growth) ** years * (1 + terminal_growth) / (discount_rate - terminal_growth)
    return value + terminal / (1 + discount_rate) ** years


def valuation(facts: dict, anchor: str, market_cap: float | None, growth: float, assumptions: Assumptions, *,
              sic: int | None) -> Valuation:
    """Enterprise value from FCFF at the WACC and its bridge to value per diluted share."""
    flow = fcff(facts, anchor, sic=sic)
    rate = wacc(facts, anchor, market_cap, assumptions, sic=sic)
    convention = f"dcf(fcff,wacc,years={assumptions.forecast_years},g_terminal={assumptions.terminal_growth})"
    bridge = "dcf_enterprise_value-total_debt+cash_and_short_term_investments"
    per_share_convention = "equity_value/weighted_average_diluted_shares"

    def blocked(metric: Metric) -> Valuation:
        failed = (_failed(convention, metric.reason or metric.state, metric.state),
                  _failed(bridge, metric.reason or metric.state, metric.state),
                  _failed(per_share_convention, metric.reason or metric.state, metric.state))
        return Valuation(flow, rate, *failed)

    for metric in (flow, rate):
        if metric.state != "computed":
            return blocked(metric)
    if (flow.value or 0.0) <= 0:
        return blocked(Metric(None, "not_meaningful", "non_positive_fcff", convention))
    value = present_value(flow.value or 0.0, growth, rate.value or 0.0, assumptions.terminal_growth,
                          assumptions.forecast_years)
    if value is None:
        return blocked(Metric(None, "not_meaningful", "terminal_growth_not_below_wacc", convention))
    enterprise = Metric(value, "computed", None, convention, flow.inputs + rate.inputs)
    debt, debt_parts = v2.total_debt(facts, anchor)
    cash, cash_parts = v2.cash_and_short_term_investments(facts, anchor)
    if not _reported(cash):
        failed = _failed(bridge, f"cash_{cash.state}", cash.state)
        return Valuation(flow, rate, enterprise, failed, _failed(per_share_convention, failed.reason or "", cash.state))
    equity_value = value - (debt.value or 0.0) + (cash.value or 0.0)
    equity = Metric(equity_value, "computed", None, bridge, (Fact("reported", value, "dcf_enterprise_value"), *debt_parts, *cash_parts))
    shares = v2.at(v2.series(facts, DILUTED_SHARES_TAGS, duration=True, unit="shares"), anchor)
    if not _reported(shares) or (shares.value or 0.0) <= 0:
        state = shares.state if not _reported(shares) else "not_meaningful"
        return Valuation(flow, rate, enterprise, equity, _failed(per_share_convention, f"diluted_shares_{state}", state))
    if equity_value <= 0:
        return Valuation(flow, rate, enterprise, equity,
                         _failed(per_share_convention, "non_positive_equity_value", "not_meaningful", (shares,)))
    per_share = Metric(equity_value / (shares.value or 1.0), "computed", None, per_share_convention, (shares,))
    return Valuation(flow, rate, enterprise, equity, per_share)


def implied_growth(facts: dict, anchor: str, market_cap: float | None, assumptions: Assumptions, *,
                   sic: int | None) -> Metric:
    """Constant FCFF growth over the horizon that makes the DCF equal the observed EV.

    The observed EV is ``sec_metrics_v2.enterprise_value``; the search is bounded to
    [−50 %, +100 %] so that an economically absurd root is not reported."""
    convention = f"reverse_dcf(fcff,wacc,years={assumptions.forecast_years},g_terminal={assumptions.terminal_growth})"
    observed = v2.enterprise_value(facts, anchor, market_cap, sic=sic)
    flow = fcff(facts, anchor, sic=sic)
    rate = wacc(facts, anchor, market_cap, assumptions, sic=sic)
    for metric in (observed, flow, rate):
        if metric.state != "computed":
            return _failed(convention, metric.reason or metric.state, metric.state)
    target, cash_flow, discount = observed.value or 0.0, flow.value or 0.0, rate.value or 0.0
    if target <= 0 or cash_flow <= 0:
        return _failed(convention, "non_positive_enterprise_value_or_fcff", "not_meaningful")

    def gap(growth: float) -> float | None:
        value = present_value(cash_flow, growth, discount, assumptions.terminal_growth, assumptions.forecast_years)
        return None if value is None else value - target

    low, high = GROWTH_SEARCH
    f_low, f_high = gap(low), gap(high)
    if (f_low is None or f_high is None or not (math.isfinite(f_low) and math.isfinite(f_high))
            or f_low * f_high > 0):
        return _failed(convention, "no_root_in_search_range", "not_meaningful")
    for _ in range(100):
        middle = (low + high) / 2
        f_middle = gap(middle) or 0.0
        if f_low * f_middle <= 0:
            high = middle
        else:
            low, f_low = middle, f_middle
    inputs = observed.inputs + flow.inputs + rate.inputs
    return Metric((low + high) / 2, "computed", None, convention, inputs)
