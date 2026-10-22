"""Read-only construction of the frozen portfolio and a capital allocation plan."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from math import isfinite
from typing import Literal, Protocol

import pandas as pd

from gabi.application.administration.model import ModelPolicy
from gabi.application.errors import QueryError
from gabi.application.market.queries import DataState, RankingSnapshot, describe_data
from gabi.domain.portfolio.concentration import (
    INDUSTRY_LIMIT_PCT,
    SECTOR_LIMIT_PCT,
    concentration_warnings,
    industry_breakdown,
    sector_breakdown,
)
from gabi.domain.portfolio.selection import allocate_new_capital, parse_holdings, target_portfolio


class PortfolioMarket(Protocol):
    def ranking(self, weights: dict[str, float], today: date) -> RankingSnapshot: ...


@dataclass
class PortfolioPlan:
    target: pd.DataFrame
    allocations: list[dict]
    remaining_eur: float
    outside_target: list[str]
    data: DataState
    generated_at: date
    revision: str
    n_positions: int
    capital_eur: float
    status: Literal["FROZEN", "EXPERIMENTAL"]
    model_id: str
    industries: dict[str, str] = field(default_factory=dict)
    sector_weights: list[dict] = field(default_factory=list)
    industry_weights: list[dict] = field(default_factory=list)
    concentration: list[dict] = field(default_factory=list)
    sector_limit_pct: float = SECTOR_LIMIT_PCT
    industry_limit_pct: float = INDUSTRY_LIMIT_PCT
    holdings_source: Literal["saved", "text", "none"] = "none"
    holdings_unvalued: list[str] = field(default_factory=list)


class PortfolioQueries:
    def __init__(self, market: PortfolioMarket, policy: ModelPolicy, today: Callable[[], date],
                 industries: Callable[[], dict[str, str]] = dict,
                 saved_holdings: Callable[[], tuple[dict[str, float], list[str]]] = lambda: ({}, [])):
        """`saved_holdings()` values Mi cartera in euros from the cache, with the symbols it cannot value."""
        self.market, self.policy, self.today, self.industries = market, policy, today, industries
        self.saved_holdings = saved_holdings

    def plan(self, n_positions: int, capital_eur: float, holdings_text: str, new_capital_eur: float, *,
             sector_limit_pct: float = SECTOR_LIMIT_PCT, industry_limit_pct: float = INDUSTRY_LIMIT_PCT,
             use_saved_holdings: bool = False) -> PortfolioPlan:
        """Typed holdings are a «¿y si…?»; without them the plan starts from Mi cartera when asked (#181)."""
        if not 5 <= n_positions <= 30 or any(
            not isfinite(value) or value < 0 or value > 1e9 for value in (capital_eur, new_capital_eur)
        ):
            raise QueryError("invalid_portfolio", "Capital o número de posiciones no válido.", 422)
        if not all(isfinite(limit) and 0 < limit <= 100 for limit in (sector_limit_pct, industry_limit_pct)):
            raise QueryError("invalid_portfolio", "Los umbrales de concentración deben estar entre 0 y 100 %.", 422)
        try:
            holdings = parse_holdings(holdings_text)
        except ValueError as exc:
            raise QueryError("invalid_holdings", "Usa una línea SÍMBOLO,euros por posición.", 422) from exc
        if len(holdings) > 100 or any(
            not symbol or len(symbol) > 20 or not symbol.replace("-", "").isalnum()
            or not isfinite(amount) or amount < 0 or amount > 1e9 for symbol, amount in holdings.items()
        ):
            raise QueryError("invalid_holdings", "Las posiciones deben tener símbolos e importes válidos.", 422)
        source: Literal["saved", "text", "none"] = "text" if holdings else "none"
        unvalued: list[str] = []
        if not holdings and use_saved_holdings:
            holdings, unvalued = self.saved_holdings()
            source = "saved" if holdings or unvalued else "none"
        today = self.today()
        snapshot = self.market.ranking(dict(self.policy.frozen_weights), today)
        target = target_portfolio(snapshot.table, n_positions)
        allocation = allocate_new_capital(target, holdings, new_capital_eur)
        frozen = n_positions == 20
        # Descriptive only (#180): the breakdown reads the selection, it never changes it.
        industries = self.industries()
        sectors = sector_breakdown(target, snapshot.table)
        held = industry_breakdown(target, industries)
        return PortfolioPlan(target, allocation["allocations"], allocation["remaining"],
                             allocation["outside_target"], describe_data(snapshot, today), today,
                             snapshot.revision, n_positions, capital_eur,
                             "FROZEN" if frozen else "EXPERIMENTAL",
                             self.policy.frozen_id if frozen else "EXPERIMENTAL_TOP_N",
                             industries, sectors, held,
                             concentration_warnings(sectors, held, sector_limit_pct=sector_limit_pct,
                                                    industry_limit_pct=industry_limit_pct),
                             sector_limit_pct, industry_limit_pct, source, unvalued)
