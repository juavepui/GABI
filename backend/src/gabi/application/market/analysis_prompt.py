"""The old Ficha «Prompt para analizar con IA»: text to paste into an assistant; GABI never calls an AI API."""

from collections.abc import Callable

import pandas as pd

from gabi.application.errors import QueryError
from gabi.application.market.queries import MarketQueries
from gabi.domain.market.selection import RankingFilter


class AnalysisPrompt:
    def __init__(self, market: MarketQueries, build: Callable[[pd.DataFrame, str], str]):
        self.market, self.build = market, build

    def prompt(self, symbol: str) -> dict:
        normalized = symbol.strip().upper().replace(".", "-")
        result = self.market.ranking(RankingFilter(hide_no_data=False), limit=1000)
        if normalized not in result.snapshot.table.index:
            raise QueryError("company_not_found", "La empresa no está en el universo local cacheado.", 404)
        return {"symbol": normalized, "revision": result.snapshot.revision,
                "prompt": self.build(result.snapshot.table, normalized)}
