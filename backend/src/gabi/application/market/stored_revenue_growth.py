"""Stored revenue growth revenue-growth-v1 (#339): one row per issuer, always from its stored facts.

Same life as the SEC metrics V2 rows (``stored_metrics_v2``): the SEC sync recomputes an issuer's
row when its facts change, and :func:`fill` writes the rows that are missing or of another rule
version without downloading. Only a model whose metrics version is ``sec-metrics-v2.2`` reads them.
"""

from collections.abc import Callable
from typing import Protocol

import pandas as pd

from gabi.application.market.stored_metrics_v2 import entity
from gabi.domain.market import revenue_growth
from gabi.domain.market.sec_reads import companyfacts


class RevenueGrowthWriter(Protocol):
    def facts(self, entity: str) -> pd.DataFrame: ...
    def save_revenue_growth(self, symbol: str, cik: str | None, row: dict) -> None: ...


class RevenueGrowthStore(RevenueGrowthWriter, Protocol):
    def revenue_growth_state(self, symbols: list[str]) -> dict[str, tuple[str | None, str | None]]: ...


def from_facts(frame: pd.DataFrame) -> dict:
    return revenue_growth.snapshot(companyfacts(frame))


def refresh(store: RevenueGrowthWriter, symbol: str, cik: str) -> dict:
    row = from_facts(store.facts(entity(cik)))
    store.save_revenue_growth(symbol, cik, row)
    return row


def fill(symbols: list[str], *, store: RevenueGrowthStore,
         progress: Callable[[int, int], None] = lambda done, total: None) -> dict:
    """Write the missing or outdated rows from local facts; one query when all are current."""
    unique = list(dict.fromkeys(symbols))
    state = store.revenue_growth_state(unique)
    current = sum(version == revenue_growth.VERSION for _, version in state.values())
    due = [(symbol, cik) for symbol, (cik, version) in sorted(state.items())
           if version != revenue_growth.VERSION and cik and str(cik).strip().isdigit()]
    for done, (symbol, cik) in enumerate(due, 1):
        refresh(store, symbol, str(cik).strip())
        if done % 25 == 0 or done == len(due):
            progress(done, len(due))
    return {"rule_version": revenue_growth.VERSION, "computed": len(due), "current": current,
            "without_issuer": len(unique) - len(due) - current}
