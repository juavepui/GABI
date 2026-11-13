"""Crecimiento de ingresos a 3 años, regla revenue-growth-v1 (#339).

The V1 rule (``sec_facts.compute_edgar_metrics``) takes the first candidate tag that reports any
annual revenue and joins another one only when a shared year reconciles. When an issuer moves to
another tag with no shared year (GE: ``RevenueFromContractWithCustomer…`` until 2018, ``Revenues``
from 2020), the V1 series stops and its growth describes years long gone. That rule stays as it
is: the sealed hypothesis and the running studies score with it (ADR 0008).

revenue-growth-v1 changes two things and nothing else:

(a) the series starts from the tag with the most recent annual year (ties keep ``REVENUE_TAGS``
    order); the other tags join only when they reconcile, exactly as in V1;
(b) a series that ends before the issuer's latest annual net income (beyond the alignment
    tolerance) is ``stale``: the growth is missing, never an old one. This is the rule SEC metrics
    V2.1 already apply to the components of another fiscal year.

The growth itself is V1's (``_cagr_from_series``: four consecutive annual year-ends, both ends
positive). Only what is stored with the 10-K facts is read; nothing is downloaded.
"""

from gabi.domain.market.sec_facts import (
    ALIGNMENT_TOLERANCE_DAYS,
    NET_INCOME_TAGS,
    REVENUE_TAGS,
    _annual_date,
    _cagr_from_series,
    _extract_annual_values,
)

VERSION = "revenue-growth-v1"
# SEC metrics V2.2 = the V2.1 ROIC (sec_metrics_v2) + the revenue growth of this rule.
METRICS_VERSION = "sec-metrics-v2.2"
TAGS = REVENUE_TAGS + NET_INCOME_TAGS


def snapshot(facts: dict) -> dict:
    """The stored row of an issuer: the growth with its state, the tag it starts from and its years."""
    singles = [(tag, _extract_annual_values(facts, [tag])) for tag in REVENUE_TAGS]
    singles = [(tag, values) for tag, values in singles if values]
    row = {"rule_version": VERSION, "revenue_cagr_3y": None, "tag": None, "first_end": None, "last_end": None}
    if not singles:
        return {**row, "state": "absent", "reason": "no_annual_revenue"}
    latest = max(values[-1][0] for _, values in singles)
    first = next(tag for tag, values in singles if values[-1][0] == latest)
    revenue = _extract_annual_values(facts, [first, *(tag for tag in REVENUE_TAGS if tag != first)])
    row |= {"tag": first, "first_end": revenue[0][0], "last_end": revenue[-1][0]}
    income = _extract_annual_values(facts, NET_INCOME_TAGS)
    if income and (_annual_date(income[-1][0]) - _annual_date(revenue[-1][0])).days > ALIGNMENT_TOLERANCE_DAYS:
        return {**row, "state": "stale", "reason": "revenue_behind_latest_annual_report"}
    growth = _cagr_from_series(revenue, 3)
    if growth is None:
        return {**row, "state": "absent", "reason": "not_four_consecutive_positive_years"}
    return {**row, "revenue_cagr_3y": growth, "state": "computed", "reason": None}


def stored_growth(row: dict | None) -> float | None:
    """The growth a ranking may use from a stored row: computed and of this rule version."""
    if not row or row.get("rule_version") != VERSION or row.get("state") != "computed":
        return None
    return row.get("revenue_cagr_3y")
