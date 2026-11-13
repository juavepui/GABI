from dataclasses import dataclass
from typing import Literal

import pandas as pd

SortKey = Literal["composite_score", "market_cap", "pe", "price", "confidence", "name", "value_score", "quality_score",
                  "momentum_score", "risk_score", "roe", "debt_to_equity", "dividend_yield", "momentum_12m",
                  "volatility", "next_earnings_days"]
EarningsWindow = Literal["only", "exclude"]


@dataclass(frozen=True)
class RankingSort:
    key: SortKey = "composite_score"
    direction: Literal["asc", "desc"] = "desc"


def sort_ranking(table: pd.DataFrame, order: RankingSort) -> pd.DataFrame:
    # Preserve the published ordering, including ties, for the default ranking.
    if table.empty or order == RankingSort():
        return table
    if order.key not in table.columns:
        return table
    return table.sort_values(order.key, ascending=order.direction == "asc", kind="stable", na_position="last")


@dataclass(frozen=True)
class RankingFilter:
    search: str = ""
    sectors: tuple[str, ...] = ()
    min_market_cap: float = 0.0  # USD, not billions
    golden_cross_only: bool = False
    hide_no_data: bool = True
    exclude_sectors: tuple[str, ...] = ()
    # With earnings_days: keep only (or drop) companies reporting within that many days from today.
    earnings: EarningsWindow | None = None
    earnings_days: int = 7


def filter_ranking(table: pd.DataFrame, query: RankingFilter) -> pd.DataFrame:
    """Keep the published score order; filter after computing universe percentiles."""
    if table.empty:
        return table
    selected = table
    if query.search.strip():
        needle = query.search.strip().lower()
        selected = selected[selected.index.to_series().str.lower().str.contains(needle, regex=False)
                            | selected["name"].fillna("").str.lower().str.contains(needle, regex=False)]
    if query.hide_no_data:
        selected = selected[selected.reindex(columns=["price", "pe"]).notna().any(axis=1)]
    if query.min_market_cap > 0:
        selected = selected[selected.reindex(columns=["market_cap"]).fillna(0)["market_cap"] >= query.min_market_cap]
    if query.golden_cross_only:
        selected = selected[selected.reindex(columns=["golden_cross_recent"])["golden_cross_recent"] == True]  # noqa: E712
    if query.sectors:
        selected = selected[selected["sector"].isin(query.sectors)]
    if query.exclude_sectors:
        selected = selected[~selected["sector"].isin(query.exclude_sectors)]
    if query.earnings:
        days = selected.reindex(columns=["next_earnings_days"])["next_earnings_days"]
        soon = days.between(0, query.earnings_days)  # an unknown date is never «soon»
        selected = selected[soon if query.earnings == "only" else ~soon]
    return selected
