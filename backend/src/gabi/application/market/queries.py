from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

import pandas as pd

from gabi.application.administration.model import ModelQueries, ModelState
from gabi.application.errors import QueryError
from gabi.domain.market.selection import RankingFilter, RankingSort, filter_ranking, sort_ranking


@dataclass
class RankingSnapshot:
    table: pd.DataFrame
    identities: dict[str, dict]
    revision: str
    generated_at: datetime
    universe_cached_at: datetime | None
    cache_hit: bool = False


@dataclass
class DataState:
    status: str
    universe_count: int
    prices_available: int
    fundamentals_available: int
    sec_available: int
    scored_count: int
    latest_price_date: date | None
    warnings: list[str]


@dataclass
class RankingResult:
    snapshot: RankingSnapshot
    model: ModelState
    data: DataState
    rows: pd.DataFrame
    total: int
    offset: int
    limit: int


class MarketRepository(Protocol):
    def ranking(self, weights: dict[str, float], today: date) -> RankingSnapshot: ...
    def price_history(self, symbol: str, limit: int, revision: str) -> pd.DataFrame: ...
    def close(self) -> None: ...


def describe_data(snapshot: RankingSnapshot, today: date) -> DataState:
    table = snapshot.table
    sources = snapshot.table.attrs.get("sources", {})
    dates = [date.fromisoformat(meta["price_date"]) for sym, meta in sources.items()
             if sym in table.index and meta.get("price_date")]
    prices = sum(bool(sources.get(sym, {}).get("price_date")) for sym in table.index)
    fundamentals = sum(bool(sources.get(sym, {}).get("fundamentals_fetched_at")) for sym in table.index)
    sec = sum(bool(sources.get(sym, {}).get("sec_fetched_at")) for sym in table.index)
    scored = int(table["composite_score"].notna().sum()) if "composite_score" in table else 0
    warnings = []
    if prices < len(table) or fundamentals < len(table) or sec < len(table):
        warnings.append("incomplete_coverage")
    if any((today - value).days > 7 for value in dates):
        warnings.append("prices_stale")
    for key, max_age in (("fundamentals_fetched_at", 7), ("sec_fetched_at", 14)):
        if any((today - datetime.fromisoformat(meta[key]).date()).days > max_age
               for sym, meta in sources.items() if sym in table.index and meta.get(key)):
            warnings.append(key.replace("_fetched_at", "_stale"))
    if snapshot.universe_cached_at and (today - snapshot.universe_cached_at.date()).days > 7:
        warnings.append("universe_stale")
    if table.empty or prices + fundamentals == 0:
        status = "empty"
    elif any(item.endswith("stale") for item in warnings):
        status = "stale"
    else:
        status = "ready"
    return DataState(status, len(table), prices, fundamentals, sec, scored, max(dates) if dates else None, warnings)


class MarketQueries:
    def __init__(self, repository: MarketRepository, models: ModelQueries, today: Callable[[], date]):
        self.repository, self.models, self.today = repository, models, today

    def model(self, override: dict[str, float] | None = None) -> ModelState:
        return self.models.model(override)

    def ranking(self, filters: RankingFilter, offset: int = 0, limit: int = 100,
                override: dict[str, float] | None = None, requested_mode: str | None = None,
                order: RankingSort = RankingSort()) -> RankingResult:
        model = self.model(override)
        if requested_mode is not None and requested_mode != model.mode:
            raise QueryError("mode_mismatch", "La URL no puede cambiar el modo configurado localmente.", 403)
        today = self.today()
        snapshot = self.repository.ranking(model.weights, today)
        filtered = sort_ranking(filter_ranking(snapshot.table, filters), order)
        return RankingResult(snapshot, model, describe_data(snapshot, today), filtered.iloc[offset:offset + limit],
                             len(filtered), offset, limit)

    def company(self, symbol: str, bars: int = 252) -> tuple[RankingResult, pd.DataFrame]:
        normalized = symbol.strip().upper().replace(".", "-")
        result = self.ranking(RankingFilter(hide_no_data=False), limit=1000)
        if normalized not in result.snapshot.table.index:
            raise QueryError("company_not_found", "La empresa no está en el universo local cacheado.", 404)
        result.rows = result.snapshot.table.loc[[normalized]]
        result.total = 1
        return result, self.repository.price_history(normalized, bars, result.snapshot.revision)

    def close(self) -> None:
        self.repository.close()
