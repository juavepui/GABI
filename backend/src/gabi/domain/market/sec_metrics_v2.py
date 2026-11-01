"""SEC metrics V2 (#245): explicit absence, provenance per input and declared conventions.

Version ``sec-metrics-v2``. It does not replace ``sec_facts``: the live paths of the
prospective studies keep using it unchanged (ADR 0008, ``docs/studies``). Every
input carries its tag, unit, period, accession and filing date. A component that
was not reported is ``absent``, never zero; only an explicit ``0`` is
``reported_zero``.
"""

from dataclasses import dataclass
from datetime import date
from types import MappingProxyType

VERSION = "sec-metrics-v2"
ALIGNMENT_TOLERANCE_DAYS = 45
STATUTORY_TAX_RATE = 0.21

OPERATING_INCOME_TAGS = ("OperatingIncomeLoss",)
TAX_EXPENSE_TAGS = ("IncomeTaxExpenseBenefit",)
PRETAX_INCOME_TAGS = (
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
)
EQUITY_TAGS = ("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest")
# Total long-term debt (current portion included) or its two parts.
LONG_TERM_DEBT_TOTAL_TAGS = ("LongTermDebt",)
LONG_TERM_DEBT_NONCURRENT_TAGS = ("LongTermDebtNoncurrent",)
LONG_TERM_DEBT_CURRENT_TAGS = ("LongTermDebtCurrent",)
SHORT_TERM_DEBT_TAGS = ("ShortTermBorrowings", "CommercialPaper")
CASH_TAGS = ("CashAndCashEquivalentsAtCarryingValue",)
SHORT_TERM_INVESTMENT_TAGS = ("ShortTermInvestments", "MarketableSecuritiesCurrent")

# Banks and credit institutions, insurers and REITs: debt is operating, not financing.
FINANCIAL_SIC_RANGES = ((6000, 6199), (6300, 6411), (6798, 6798))
# GICS proxy for those SIC codes when only the universe sector is known (declared in reports).
FINANCIAL_GICS_SECTORS = MappingProxyType({"Financials": 6000, "Real Estate": 6798})


@dataclass(frozen=True)
class Fact:
    """One reported value with its provenance, or the reason it is missing."""

    state: str  # reported | reported_zero | absent | stale
    value: float | None = None
    tag: str | None = None
    unit: str = "USD"
    start: str | None = None
    end: str | None = None
    accession: str | None = None
    filed: str | None = None


@dataclass(frozen=True)
class Metric:
    value: float | None
    state: str  # computed | absent | stale | not_applicable | not_meaningful
    reason: str | None
    convention: str
    inputs: tuple[Fact, ...] = ()


def _day(value: str) -> date:
    return date.fromisoformat(value)


def _entries(facts: dict, tag: str, unit: str) -> list[dict]:
    node = facts.get("facts", {}).get("us-gaap", {}).get(tag) or {}
    return [entry for entry in node.get("units", {}).get(unit, [])
            if entry.get("form") in {"10-K", "10-K/A"} and entry.get("fp") == "FY"
            and entry.get("end") and entry.get("val") is not None]


def _latest_by_end(entries: list[dict], tag: str, unit: str, duration: bool) -> dict[str, Fact]:
    """The latest filing for each period end; a same-filing disagreement drops the period."""
    chosen: dict[str, tuple[tuple[str, str], Fact]] = {}
    conflicts: set[str] = set()
    for entry in entries:
        if duration:
            if not entry.get("start"):
                continue
            try:
                days = (_day(entry["end"]) - _day(entry["start"])).days
            except ValueError:
                continue
            if not 340 <= days <= 380:
                continue
        value = float(entry["val"])
        key = (str(entry.get("filed") or ""), str(entry.get("accn") or ""))
        fact = Fact("reported_zero" if value == 0 else "reported", value, tag, unit, entry.get("start"),
                    entry["end"], entry.get("accn"), entry.get("filed"))
        previous = chosen.get(entry["end"])
        if previous and previous[0] == key and previous[1].value != value:
            conflicts.add(entry["end"])
        elif previous is None or key > previous[0]:
            chosen[entry["end"]] = (key, fact)
    return {end: fact for end, (_, fact) in chosen.items() if end not in conflicts}


def series(facts: dict, tags: tuple[str, ...], *, duration: bool, unit: str = "USD") -> dict[str, Fact]:
    """Annual 10-K values of the first candidate tag that reports any."""
    for tag in tags:
        values = _latest_by_end(_entries(facts, tag, unit), tag, unit, duration)
        if values:
            return values
    return {}


def at(values: dict[str, Fact], anchor: str, *, tolerance_days: int = ALIGNMENT_TOLERANCE_DAYS) -> Fact:
    """The value for the anchor fiscal year: ``stale`` if the series exists but not for that year."""
    if not values:
        return Fact("absent")
    target = _day(anchor)
    close = sorted((abs((_day(end) - target).days), end) for end in values
                   if abs((_day(end) - target).days) <= tolerance_days)
    return values[close[0][1]] if close else Fact("stale")


def _missing(*parts: Fact) -> Fact | None:
    for state in ("stale", "absent"):
        if any(part.state == state for part in parts):
            return Fact(state)
    return None


def _sum(parts: list[Fact]) -> float:
    return sum(part.value or 0.0 for part in parts)


def total_debt(facts: dict, anchor: str) -> tuple[Fact, tuple[Fact, ...]]:
    """Financial debt at the anchor: long-term (with its current portion) plus short-term borrowings.

    Uses ``LongTermDebt`` (which already includes the current portion) or else
    noncurrent plus current. Short-term borrowings are added when reported. If no
    long-term component is reported, debt is ``absent``/``stale``, not zero."""
    total = at(series(facts, LONG_TERM_DEBT_TOTAL_TAGS, duration=False), anchor)
    if total.state in {"reported", "reported_zero"}:
        long_term = [total]
    else:
        noncurrent = at(series(facts, LONG_TERM_DEBT_NONCURRENT_TAGS, duration=False), anchor)
        if noncurrent.state not in {"reported", "reported_zero"}:
            return (Fact("stale") if "stale" in {total.state, noncurrent.state} else Fact("absent")), ()
        current = at(series(facts, LONG_TERM_DEBT_CURRENT_TAGS, duration=False), anchor)
        long_term = [noncurrent] + ([current] if current.value is not None else [])
    short = at(series(facts, SHORT_TERM_DEBT_TAGS, duration=False), anchor)
    parts = tuple(long_term + ([short] if short.value is not None else []))
    value = _sum(list(parts))
    return Fact("reported_zero" if value == 0 else "reported", value, "total_debt", end=parts[0].end), parts


def cash_and_short_term_investments(facts: dict, anchor: str) -> tuple[Fact, tuple[Fact, ...]]:
    cash = at(series(facts, CASH_TAGS, duration=False), anchor)
    if cash.value is None:
        return cash, ()
    investments = at(series(facts, SHORT_TERM_INVESTMENT_TAGS, duration=False), anchor)
    parts = (cash,) + ((investments,) if investments.value is not None else ())
    value = _sum(list(parts))
    return Fact("reported_zero" if value == 0 else "reported", value, "cash_and_short_term_investments",
                end=cash.end), parts


def financial_sector(sic: int | None) -> bool:
    return sic is not None and any(low <= sic <= high for low, high in FINANCIAL_SIC_RANGES)


def enterprise_value(facts: dict, anchor: str, market_cap: float | None, *, sic: int | None) -> Metric:
    """EV = market cap + financial debt − cash and short-term investments."""
    convention = "market_cap+total_debt-cash_and_short_term_investments"
    if financial_sector(sic):
        return Metric(None, "not_applicable", "financial_sector", convention)
    if market_cap is None or market_cap <= 0:
        return Metric(None, "absent", "no_market_cap", convention)
    debt, debt_parts = total_debt(facts, anchor)
    cash, cash_parts = cash_and_short_term_investments(facts, anchor)
    missing = _missing(debt, cash)
    if missing:
        component = "debt" if debt.value is None else "cash"
        return Metric(None, missing.state, f"{component}_{missing.state}", convention)
    return Metric(market_cap + (debt.value or 0.0) - (cash.value or 0.0), "computed", None, convention,
                  debt_parts + cash_parts)


def _previous_year_end(values: dict[str, Fact], anchor: str) -> str | None:
    target = _day(anchor)
    earlier = [end for end in values if 340 <= (target - _day(end)).days <= 380]
    return max(earlier) if earlier else None


def tax_rate(facts: dict, anchor: str) -> tuple[float, str, tuple[Fact, ...]]:
    """Effective tax rate (tax expense / pretax income, bounded to [0, 1)) or the declared statutory 21 %."""
    tax = at(series(facts, TAX_EXPENSE_TAGS, duration=True), anchor)
    pretax = at(series(facts, PRETAX_INCOME_TAGS, duration=True), anchor)
    if tax.value is not None and pretax.value is not None and pretax.value > 0:
        return min(max(tax.value / pretax.value, 0.0), 0.99), "effective_tax", (tax, pretax)
    return STATUTORY_TAX_RATE, "statutory_tax_21", ()


def roic(facts: dict, anchor: str, *, sic: int | None) -> Metric:
    """NOPAT / average invested capital over the anchor year.

    NOPAT = operating income × (1 − effective tax rate). The effective rate is
    tax expense / pretax income, bounded to [0, 1); with no positive pretax
    income or no tax figure the statutory 21 % is used and declared. Invested
    capital = equity + financial debt − cash and short-term investments, averaged
    between the opening and closing balance sheets."""
    if financial_sector(sic):
        return Metric(None, "not_applicable", "financial_sector", "nopat/average_invested_capital")
    operating = at(series(facts, OPERATING_INCOME_TAGS, duration=True), anchor)
    if operating.value is None:
        return Metric(None, operating.state, f"operating_income_{operating.state}", "nopat/average_invested_capital")
    rate, tax_convention, tax_inputs = tax_rate(facts, anchor)
    convention = f"nopat({tax_convention})/average_invested_capital"
    equity_series = series(facts, EQUITY_TAGS, duration=False)
    opening = _previous_year_end(equity_series, anchor) if equity_series else None
    if opening is None:
        return Metric(None, "absent", "no_opening_balance_sheet", convention)
    capitals, inputs = [], [operating, *tax_inputs]
    for end in (opening, anchor):
        equity = at(equity_series, end)
        debt, debt_parts = total_debt(facts, end)
        cash, cash_parts = cash_and_short_term_investments(facts, end)
        missing = _missing(equity, debt, cash)
        if missing:
            component = "equity" if equity.value is None else "debt" if debt.value is None else "cash"
            return Metric(None, missing.state, f"{component}_{missing.state}", convention)
        capitals.append((equity.value or 0.0) + (debt.value or 0.0) - (cash.value or 0.0))
        inputs += [equity, *debt_parts, *cash_parts]
    average = sum(capitals) / 2
    if average <= 0:
        return Metric(None, "not_meaningful", "non_positive_invested_capital", convention, tuple(inputs))
    return Metric(operating.value * (1 - rate) / average, "computed", None, convention, tuple(inputs))


def latest_annual_end(facts: dict) -> str | None:
    """The last fiscal year end with an annual 10-K balance sheet: the anchor of the metrics."""
    ends = series(facts, EQUITY_TAGS, duration=False)
    return max(ends) if ends else None


def _fact_record(fact: Fact) -> dict:
    return {"state": fact.state, "value": fact.value, "tag": fact.tag, "unit": fact.unit, "start": fact.start,
            "end": fact.end, "accession": fact.accession, "filed": fact.filed}


def snapshot(facts: dict) -> dict:
    """The stored V2 row of an issuer at its latest annual report, with the sector rule left to the reader.

    ROIC is computed as for a non-financial issuer (``sic=None``): the stored facts
    carry no SIC, so whoever reads the row applies :func:`stored_roic`. Debt and
    cash keep their state so an EV can be built later with a market cap."""
    anchor = latest_annual_end(facts)
    if anchor is None:
        metric, debt, cash = Metric(None, "absent", "no_annual_report", "nopat/average_invested_capital"), \
            Fact("absent"), Fact("absent")
    else:
        metric = roic(facts, anchor, sic=None)
        debt, _ = total_debt(facts, anchor)
        cash, _ = cash_and_short_term_investments(facts, anchor)
    return {"metrics_version": VERSION, "anchor": anchor, "roic": metric.value, "roic_state": metric.state,
            "roic_reason": metric.reason, "roic_convention": metric.convention,
            "roic_inputs": [_fact_record(fact) for fact in metric.inputs],
            "total_debt": debt.value, "total_debt_state": debt.state,
            "cash": cash.value, "cash_state": cash.state}


def stored_roic(row: dict | None, *, sector: str | None) -> float | None:
    """The ROIC a ranking may use from a stored row: computed, of this version and not a financial issuer."""
    if (sector or "") in FINANCIAL_GICS_SECTORS or not row or row.get("metrics_version") != VERSION or row.get("roic_state") != "computed":
        return None
    return row.get("roic")
