"""Puntuación de cada día de una empresa (#328): read-only, from what the daily task stored."""

from collections.abc import Callable
from typing import Protocol

from gabi.domain.market import score_history
from gabi.domain.market.identity import normalize_symbol


class ScoreHistoryStore(Protocol):
    def company(self, symbol: str) -> list[dict]: ...


class ScoreHistoryQueries:
    def __init__(self, store: ScoreHistoryStore, model_id: Callable[[], str]):
        self.store, self.model_id = store, model_id

    def company(self, symbol: str) -> dict:
        symbol = normalize_symbol(symbol)
        points = self.store.company(symbol)
        model = self.model_id()
        return {"symbol": symbol, "model_id": model, "points": points, "reading": score_history.reading(points, model)}
