"""Cash-based operating profitability, ``CBOP-v1`` (#252, #268 section 6).

Ball, Gerakos, Linnainmaa and Nikolaev (2016): operating profitability
(revenue − cost of revenue − SG&A) minus the increases in receivables,
inventories and prepaid expenses, plus the increases in deferred revenue,
payables and accrued liabilities, over total assets at the fiscal year end.

XBRL reports SG&A without R&D (``ResearchAndDevelopmentExpense`` is its own
line), which is what the paper obtains by subtracting XRD from Compustat's
XSGA; R&D is stored for the audit but never subtracted.

Only annual 10-K facts filed before the signal count. A working-capital line the
issuer never reported in any annual report is taken as zero and declared; one it
reported other years but not for the anchor year leaves the value missing. The
measure is not applicable to financial issuers (SIC 6000–6999, as preregistered).
Nothing here reads prices or returns.
"""

from dataclasses import dataclass
from datetime import date

from gabi.domain.market import sec_metrics_v2 as v2
from gabi.domain.market.sec_metrics_v2 import Fact, Metric

VERSION = "cbop-v1"
CONVENTION = "(revenue-cogs-sga-d_ar-d_inv-d_prepaid+d_deferred_rev+d_ap+d_accrued)/assets"
REVENUE_TAGS = ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet",
                "RevenueFromContractWithCustomerIncludingAssessedTax")
COST_OF_REVENUE_TAGS = ("CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold")
SGA_TAGS = ("SellingGeneralAndAdministrativeExpense",)
RESEARCH_TAGS = ("ResearchAndDevelopmentExpense",)
ASSETS_TAGS = ("Assets",)
# Cash-flow statement lines: a positive value is an increase of the balance.
WORKING_CAPITAL = {
    "d_receivables": (-1, ("IncreaseDecreaseInAccountsReceivable",)),
    "d_inventories": (-1, ("IncreaseDecreaseInInventories",)),
    "d_prepaid": (-1, ("IncreaseDecreaseInPrepaidDeferredExpenseAndOtherAssets", "IncreaseDecreaseInPrepaidExpense")),
    "d_deferred_revenue": (1, ("IncreaseDecreaseInContractWithCustomerLiability",
                               "IncreaseDecreaseInDeferredRevenue")),
    "d_payables": (1, ("IncreaseDecreaseInAccountsPayable",)),
    "d_accrued": (1, ("IncreaseDecreaseInAccruedLiabilities",)),
}
USD_TAGS = tuple(dict.fromkeys(
    REVENUE_TAGS + COST_OF_REVENUE_TAGS + SGA_TAGS + RESEARCH_TAGS + ASSETS_TAGS
    + tuple(tag for _, tags in WORKING_CAPITAL.values() for tag in tags)))
FINANCIAL_SIC = (6000, 6999)
MAX_ANCHOR_AGE_DAYS = 550  # An issuer whose last 10-K is older than this no longer files: stale.
COVERAGE_THRESHOLD = 0.70


@dataclass(frozen=True)
class Value:
    """CbOP of one issuer at a signal, with its anchor fiscal year and the lines taken as zero."""

    metric: Metric
    anchor: str | None
    imputed: tuple[str, ...] = ()


def financial(sic: int | None) -> bool:
    return sic is not None and FINANCIAL_SIC[0] <= sic <= FINANCIAL_SIC[1]


def _filed_before(facts: dict, signal: date) -> dict:
    """Only the facts filed strictly before the signal session."""
    day = signal.isoformat()
    families = {}
    for tag, node in facts.get("facts", {}).get("us-gaap", {}).items():
        units = {unit: [entry for entry in entries if entry.get("filed") and str(entry["filed"]) < day]
                 for unit, entries in node.get("units", {}).items()}
        families[tag] = {"units": units}
    return {"facts": {"us-gaap": families}}


def _line(facts: dict, tags: tuple[str, ...], anchor: str, *, duration: bool) -> Fact:
    """The first tag reported for the anchor year; otherwise ``stale`` if any tag has other years."""
    seen = False
    for tag in tags:
        values = v2.series(facts, (tag,), duration=duration)
        seen = seen or bool(values)
        fact = v2.at(values, anchor)
        if fact.value is not None:
            return fact
    return Fact("stale" if seen else "absent")


def anchor_at(facts: dict, signal: date) -> str | None:
    """The fiscal year end of the latest 10-K balance sheet filed before the signal."""
    ends = v2.series(_filed_before(facts, signal), ASSETS_TAGS, duration=False)
    return max(ends) if ends else None


def cbop(facts: dict, signal: date, *, sic: int | None) -> Value:
    if financial(sic):
        return Value(Metric(None, "not_applicable", "financial_sector", CONVENTION), None)
    known = _filed_before(facts, signal)
    anchor = anchor_at(facts, signal)
    if anchor is None:
        return Value(Metric(None, "absent", "no_annual_report", CONVENTION), None)
    if (signal - date.fromisoformat(anchor)).days > MAX_ANCHOR_AGE_DAYS:
        return Value(Metric(None, "stale", "annual_report_too_old", CONVENTION), anchor)
    assets = _line(known, ASSETS_TAGS, anchor, duration=False)
    parts = {"revenue": _line(known, REVENUE_TAGS, anchor, duration=True),
             "cost_of_revenue": _line(known, COST_OF_REVENUE_TAGS, anchor, duration=True),
             "sga": _line(known, SGA_TAGS, anchor, duration=True)}
    for name, fact in {**parts, "assets": assets}.items():
        if fact.value is None:
            return Value(Metric(None, fact.state, f"{name}_{fact.state}", CONVENTION), anchor)
    total = (parts["revenue"].value or 0.0) - (parts["cost_of_revenue"].value or 0.0) - (parts["sga"].value or 0.0)
    inputs, imputed = [*parts.values(), assets], []
    for name, (sign, tags) in WORKING_CAPITAL.items():
        fact = _line(known, tags, anchor, duration=True)
        if fact.state == "absent":
            imputed.append(name)  # Never reported in any annual report: zero, declared.
            continue
        if fact.value is None:
            return Value(Metric(None, fact.state, f"{name}_{fact.state}", CONVENTION), anchor, tuple(imputed))
        total += sign * fact.value
        inputs.append(fact)
    if (assets.value or 0.0) <= 0:
        return Value(Metric(None, "not_meaningful", "non_positive_assets", CONVENTION, tuple(inputs)), anchor,
                     tuple(imputed))
    return Value(Metric(total / (assets.value or 1.0), "computed", None, CONVENTION, tuple(inputs)), anchor,
                 tuple(imputed))


def coverage(rows: list[dict], *, threshold: float = COVERAGE_THRESHOLD) -> dict:
    """Share of eligible (non-financial) members with a computed CbOP at one signal.

    ``rows`` hold ``state`` and ``reason`` per member; ``not_applicable`` ones are
    not eligible. The gate fails below ``threshold``."""
    eligible = [row for row in rows if row["state"] != "not_applicable"]
    computed = sum(row["state"] == "computed" for row in eligible)
    reasons: dict[str, int] = {}
    for row in eligible:
        if row["state"] != "computed":
            reasons[row["reason"]] = reasons.get(row["reason"], 0) + 1
    share = computed / len(eligible) if eligible else None
    return {"members": len(rows), "eligible": len(eligible), "computed": computed, "coverage": share,
            "passes": share is not None and share >= threshold,
            "imputed_any": sum(bool(row.get("imputed")) for row in eligible if row["state"] == "computed"),
            "missing_reasons": dict(sorted(reasons.items(), key=lambda item: -item[1]))}
