"""Explicit, idempotent alert job of open ideas (#247), over local data only.

For each open idea it reads its published card, the company's checklist, latest
filings, earnings surprises, consensus revision and insider summary from the local
cache, plus the idea's evaluation, and records the new observations and alerts.
Nothing is downloaded and nothing is traded: an alert asks for a review.
"""

from collections.abc import Callable
from datetime import date

from gabi.application.errors import QueryError
from gabi.application.portfolio.ideas import Ideas
from gabi.domain.portfolio import idea_alerts as rules


def _safe(port: Callable, *args, default=None):
    try:
        return port(*args)
    except QueryError:
        return default


def run(ideas: Ideas, *, card: Callable[[int], dict], checklist: Callable[[str], dict],
        filings: Callable[[str], dict], overview: Callable[[str], dict], insiders: Callable[[str], dict],
        today: Callable[[], date], progress: Callable[[float, str], None] = lambda share, message: None) -> dict:
    listing = ideas.list()
    open_ideas = [row for row in listing["items"] if row["state"]["status"] == "abierta"]
    counts: dict[str, int] = {}
    new_total = 0
    for done, row in enumerate(open_ideas, 1):
        symbol, idea_id = row["symbol"], row["idea_id"]
        content = _safe(card, row["card_id"], default={}).get("content") or {}
        sheet = _safe(checklist, symbol) or {}
        found, alerts = rules.conditions(content.get("invalidation") or [], sheet.get("criteria") or [],
                                         sheet.get("fiscal_year_end"), ideas.observations(idea_id))
        alerts += rules.reviews_due(content, today())
        research = _safe(overview, symbol) or {}
        alerts += rules.signals(row["state"]["published_on"], filings=(_safe(filings, symbol) or {}).get("results", []),
                                surprises=research.get("surprises") or [], revision=research.get("revision_90d"),
                                insiders=_safe(insiders, symbol), evaluation=row["evaluation"],
                                month=today().strftime("%Y-%m"))
        added = ideas.record_alerts(idea_id, found, alerts)
        new_total += added
        for alert in alerts:
            counts[alert["kind"]] = counts.get(alert["kind"], 0) + 1
        progress(done / len(open_ideas), f"Alertas de {symbol}")
    return {"kind": "idea_alerts", "version": rules.VERSION, "as_of": today().isoformat(), "ideas": len(open_ideas),
            "new_alerts": new_total, "checked_by_kind": counts,
            "note": "Las alertas solo piden revisar la idea; GABI nunca opera."}
