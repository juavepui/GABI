"""Batched reads of Comparar (#194) beyond the ranking row: checklist digest and rebased prices, nothing written."""

from gabi.application.market.checklist import CompanyChecklist
from gabi.application.market.queries import MarketQueries
from gabi.domain.market.comparison import rebased

BENCHMARK = "SPY"
# Valuation, quality and health criteria that tell apart two companies of the same sector.
CRITERIA = ("pe", "ev_ebitda", "fcf_yield", "roic", "net_debt_to_ebitda", "interest_coverage")
CRITERION_FIELDS = ("key", "label", "unit", "value", "threshold", "comparison", "verdict", "reason", "source", "period")


def checklists(market: MarketQueries, checklist: CompanyChecklist, symbols: list[str]) -> dict:
    """Checklist summary, alarms and multiples against own history and sector of 2–5 compared companies.

    The values are those of each company page's checklist; sector peers are computed once per sector."""
    result = market.compare(symbols)
    items = []
    for symbol in (str(symbol) for symbol in result.rows.index):
        body = checklist.company(symbol)
        sector = checklist.sector_multiples(symbol)
        criteria = {item["key"]: item for item in body["criteria"]}
        items.append({
            "symbol": symbol, "fiscal_year_end": body["fiscal_year_end"],
            "financial_sector": body["financial_sector"], "summary": body["summary"],
            "criteria": [{field: criteria[key][field] for field in CRITERION_FIELDS} for key in CRITERIA
                         if key in criteria],
            "active_alarms": [alarm["label"] for alarm in body["alarms"] if alarm["status"] == "active"],
            "history_medians": body["multiples_history"]["median"],
            "history_years": body["multiples_history"]["years"],
            "sector": sector["sector"], "sector_peers": sector["peers"], "sector_reason": sector["reason"],
            "sector_medians": sector["medians"],
        })
    return {"items": items, "revision": result.snapshot.revision}


def prices(market: MarketQueries, symbols: list[str], bars: int) -> dict:
    """The last `bars` cached sessions of each company and SPY, as 100 at their first common session."""
    result, frames = market.compare_histories(symbols, [BENCHMARK], bars)
    histories: dict[str, list[tuple[str, float | None]]] = {
        symbol: [] if frame.empty else [(str(day), float(close)) for day, close in
                                        zip(frame["date"], frame["adj_close"], strict=True) if close is not None]
        for symbol, frame in frames.items()}
    base_date, points = rebased(histories)
    return {"symbols": [str(symbol) for symbol in result.rows.index], "benchmark": BENCHMARK,
            "base_date": base_date, "bars": bars, "points": points, "revision": result.snapshot.revision}
