"""Read-only construction of the frozen portfolio and a capital allocation plan."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from math import isfinite
from typing import Literal, Protocol

import pandas as pd

from gabi.application.administration.model import ModelPolicy
from gabi.application.errors import QueryError
from gabi.application.market.queries import DataState, RankingSnapshot, describe_data
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


class PortfolioQueries:
    def __init__(self, market: PortfolioMarket, policy: ModelPolicy, today: Callable[[], date]):
        self.market, self.policy, self.today = market, policy, today

    def plan(self, n_positions: int, capital_eur: float, holdings_text: str, new_capital_eur: float) -> PortfolioPlan:
        if not 5 <= n_positions <= 30 or any(
            not isfinite(value) or value < 0 or value > 1e9 for value in (capital_eur, new_capital_eur)
        ):
            raise QueryError("invalid_portfolio", "Capital o número de posiciones no válido.", 422)
        try:
            holdings = parse_holdings(holdings_text)
        except ValueError as exc:
            raise QueryError("invalid_holdings", "Usa una línea SÍMBOLO,euros por posición.", 422) from exc
        if len(holdings) > 100 or any(
            not symbol or len(symbol) > 20 or not symbol.replace("-", "").isalnum()
            or not isfinite(amount) or amount < 0 or amount > 1e9 for symbol, amount in holdings.items()
        ):
            raise QueryError("invalid_holdings", "Las posiciones deben tener símbolos e importes válidos.", 422)
        today = self.today()
        snapshot = self.market.ranking(dict(self.policy.frozen_weights), today)
        target = target_portfolio(snapshot.table, n_positions)
        allocation = allocate_new_capital(target, holdings, new_capital_eur)
        frozen = n_positions == 20
        return PortfolioPlan(target, allocation["allocations"], allocation["remaining"],
                             allocation["outside_target"], describe_data(snapshot, today), today,
                             snapshot.revision, n_positions, capital_eur,
                             "FROZEN" if frozen else "EXPERIMENTAL",
                             self.policy.frozen_id if frozen else "EXPERIMENTAL_TOP_N")
