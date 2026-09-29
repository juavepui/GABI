from dataclasses import dataclass
from typing import Literal

import pandas as pd

SortKey = Literal["composite_score", "market_cap", "pe", "price", "confidence", "name"]


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
    return selected
