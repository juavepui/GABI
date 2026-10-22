"""Read-only coverage audit of the Checklist (#170): which criteria each issuer can evaluate, and why not.

It evaluates the Checklist of every company in the current universe over the SEC facts already
stored, exactly as the company page does. Nothing is downloaded or written.
"""

from collections import Counter
from collections.abc import Callable
from typing import Protocol

EVALUATED = frozenset({"pass", "fail", "info"})
# Reasons meaning the annual revenue or CAPEX of the fiscal anchor is not in the stored facts.
REVENUE_MISSING = frozenset({"no_revenue"})
CAPEX_MISSING = frozenset({"no_capex", "stale_capex"})


class ChecklistReader(Protocol):
    def company(self, symbol: str) -> dict: ...


def _share(part: int, whole: int) -> float | None:
    return part / whole if whole else None


def checklist_coverage(checklist: ChecklistReader, universe: list[tuple[str, str]],
                       progress: Callable[[int, int], None] | None = None) -> dict:
    """Evaluable share of every criterion, absence reasons by sector and issuers without revenue or CAPEX."""
    applicable: Counter = Counter()
    evaluated: Counter = Counter()
    reasons: dict[str, Counter] = {}
    by_sector: dict[str, dict[str, Counter]] = {}
    sectors: Counter = Counter()
    without_revenue: list[dict] = []
    without_capex: list[dict] = []
    evaluated_counts: dict[str, int] = {}
    as_of = None
    for index, (symbol, sector) in enumerate(universe, start=1):
        body = checklist.company(symbol)
        as_of = body["as_of"]
        sector = sector or "Sin sector"
        sectors[sector] += 1
        criteria = {item["key"]: item for item in body["criteria"]}
        evaluated_counts[symbol] = 0
        for key, item in criteria.items():
            if item["verdict"] == "not_applicable":
                continue
            applicable[key] += 1
            counts = by_sector.setdefault(key, {}).setdefault(sector, Counter())
            counts["applicable"] += 1
            if item["verdict"] in EVALUATED:
                evaluated[key] += 1
                counts["evaluated"] += 1
                evaluated_counts[symbol] += 1
            else:
                reasons.setdefault(key, Counter())[item["reason"] or "unknown"] += 1
        issuer = {"symbol": symbol, "sector": sector, "fiscal_year_end": body["fiscal_year_end"]}
        if not body["financial_sector"]:
            if criteria["gross_margin"]["reason"] in REVENUE_MISSING:
                without_revenue.append(issuer)
            if criteria["fcf"]["reason"] in CAPEX_MISSING:
                without_capex.append(issuer | {"reason": criteria["fcf"]["reason"]})
        if progress:
            progress(index, len(universe))
    return {
        "as_of": as_of,
        "issuers": len(universe),
        "sectors": dict(sorted(sectors.items())),
        "criteria": {key: {
            "applicable": applicable[key], "evaluated": evaluated[key],
            "share": _share(evaluated[key], applicable[key]),
            "reasons": dict(reasons.get(key, Counter()).most_common()),
            "by_sector": {sector: {"applicable": counts["applicable"], "evaluated": counts["evaluated"],
                                   "share": _share(counts["evaluated"], counts["applicable"])}
                          for sector, counts in sorted(by_sector.get(key, {}).items())},
        } for key in applicable},
        "non_financial_issuers": applicable["gross_margin"],
        "revenue_share": _share(applicable["gross_margin"] - len(without_revenue), applicable["gross_margin"]),
        "without_revenue": without_revenue,
        "without_capex": without_capex,
        "evaluated_per_issuer": evaluated_counts,
    }
