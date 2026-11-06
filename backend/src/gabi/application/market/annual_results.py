"""Ingresos, beneficio neto y caja libre por ejercicio de una empresa (#328, parte B): read-only."""

from typing import Protocol

import pandas as pd

from gabi.domain.market import annual_results
from gabi.domain.market.identity import normalize_symbol
from gabi.domain.market.sec_reads import companyfacts


class AnnualFactReader(Protocol):
    def issuer_facts(self, symbol: str, *, tags: list[str] | None = None, as_of: str | None = None,
                     unit: str | None = None) -> pd.DataFrame: ...


class AnnualResultsQueries:
    """Reads only the SEC facts already stored; never downloads or writes."""

    def __init__(self, reader: AnnualFactReader):
        self.reader = reader

    def company(self, symbol: str) -> dict:
        symbol = normalize_symbol(symbol)
        frame = self.reader.issuer_facts(symbol, tags=annual_results.TAGS, unit="USD")
        points = annual_results.rows(companyfacts(frame))
        return {"symbol": symbol, "currency": "USD", "points": points,
                "reading": annual_results.reading(points, has_facts=not frame.empty)}
