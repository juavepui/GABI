from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

import pandas as pd

from gabi.application.administration.model import ModelQueries, ModelState
from gabi.application.errors import QueryError
from gabi.domain.market.freshness import MAX_BEHIND_SHARE, prices_current
from gabi.domain.market.selection import RankingFilter, RankingSort, filter_ranking, sort_ranking

# Sessions of one company read whole for its risk windows (#175): about 80 years of trading days.
HISTORY_ROWS = 20_000


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
    last_session: date | None = None  # last closed NYSE session; None: not checked
    prices_current: bool | None = None
    # Degraded, stale or empty data, a missing last close or a source below 95 % of the universe:
    # the pages show the full data notice instead of the compact chip (#187).
    needs_attention: bool = False


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


def describe_data(snapshot: RankingSnapshot, today: date, last_session: date | None = None) -> DataState:
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
    current = None
    if last_session is not None and not table.empty:
        current = prices_current([date.fromisoformat(value) if (value := sources.get(sym, {}).get("price_date")) else None
                                  for sym in table.index], last_session)
    short = min(prices, fundamentals, sec, scored) < (1 - MAX_BEHIND_SHARE) * len(table)
    return DataState(status, len(table), prices, fundamentals, sec, scored, max(dates) if dates else None, warnings,
                     last_session, current, status != "ready" or current is False or short)


class MarketQueries:
    def __init__(self, repository: MarketRepository, models: ModelQueries, today: Callable[[], date],
                 last_session: Callable[[], date] | None = None):
        self.repository, self.models, self.today, self.last_session = repository, models, today, last_session

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
        session = self.last_session() if self.last_session else None
        return RankingResult(snapshot, model, describe_data(snapshot, today, session), filtered.iloc[offset:offset + limit],
                             len(filtered), offset, limit)

    def _company_ranking(self, symbol: str) -> tuple[str, RankingResult]:
        normalized = symbol.strip().upper().replace(".", "-")
        result = self.ranking(RankingFilter(hide_no_data=False), limit=1000)
        if normalized not in result.snapshot.table.index:
            raise QueryError("company_not_found", "La empresa no está en el universo local cacheado.", 404)
        result.rows = result.snapshot.table.loc[[normalized]]
        result.total = 1
        return normalized, result

    def company(self, symbol: str, bars: int = 252) -> tuple[RankingResult, pd.DataFrame]:
        normalized, result = self._company_ranking(symbol)
        return result, self.repository.price_history(normalized, bars, result.snapshot.revision)

    def company_metrics(self, symbol: str) -> dict:
        """The ranking row of one company, the values its page shows; QueryError outside the universe."""
        return self._company_ranking(symbol)[1].rows.iloc[0].to_dict()

    def compare(self, symbols: list[str]) -> RankingResult:
        normalized = [symbol.strip().upper().replace(".", "-") for symbol in symbols]
        if len(normalized) < 2 or len(normalized) > 5 or len(set(normalized)) != len(normalized):
            raise QueryError("invalid_comparison", "Elige entre dos y cinco empresas distintas.", 422)
        result = self.ranking(RankingFilter(hide_no_data=False), limit=1000)
        missing = [symbol for symbol in normalized if symbol not in result.snapshot.table.index]
        if missing:
            raise QueryError("company_not_found", "Alguna empresa no está en el universo local cacheado.", 404)
        result.rows = result.snapshot.table.loc[normalized]
        result.total = len(normalized)
        result.limit = len(normalized)
        return result

    def histories(self, symbols: list[str]) -> tuple[RankingResult, dict[str, pd.DataFrame]]:
        """Whole cached histories of 1–5 universe companies, as the ranking's risk metrics read them (#175)."""
        normalized = list(dict.fromkeys(symbol.strip().upper().replace(".", "-") for symbol in symbols))
        if not 1 <= len(normalized) <= 5:
            raise QueryError("invalid_symbols", "Elige entre una y cinco empresas.", 422)
        result = self.ranking(RankingFilter(hide_no_data=False), limit=1000)
        if any(symbol not in result.snapshot.table.index for symbol in normalized):
            raise QueryError("company_not_found", "Alguna empresa no está en el universo local cacheado.", 404)
        frames = {}
        for symbol in normalized:
            # One row over the budget tells a long history from a truncated one: never cut silently.
            frame = self.repository.price_history(symbol, HISTORY_ROWS + 1, result.snapshot.revision)
            if len(frame) > HISTORY_ROWS:
                raise QueryError("resource_limit", "El histórico supera el presupuesto de lectura.")
            frames[symbol] = frame
        return result, frames

    def compare_histories(self, symbols: list[str], extra: list[str], bars: int) -> tuple[RankingResult, dict]:
        """The compared companies plus `extra` series (SPY), each its last `bars` cached sessions."""
        result = self.compare(symbols)
        names = list(dict.fromkeys([str(symbol) for symbol in result.rows.index] + extra))
        return result, {symbol: self.repository.price_history(symbol, bars, result.snapshot.revision)
                        for symbol in names}

    def close(self) -> None:
        self.repository.close()
