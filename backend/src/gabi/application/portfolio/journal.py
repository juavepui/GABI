"""Validated diary commands over the existing local journal_entries table."""

import re
from datetime import date
from math import isfinite
from typing import Protocol

from gabi.application.errors import QueryError
from gabi.domain.portfolio.journal import compute_expected_value


class JournalRepository(Protocol):
    def list_entries(self, limit: int, offset: int, only_open: bool = False) -> tuple[list[dict], int]: ...
    def get(self, entry_id: int) -> dict | None: ...
    def create(self, entry: dict) -> int: ...
    def review(self, entry_id: int, review_date: str, review_price: float | None, notes: str) -> bool: ...
    def delete(self, entry_id: int) -> bool: ...


class Journal:
    def __init__(self, repository: JournalRepository):
        self.repository = repository

    @staticmethod
    def present(row: dict) -> dict:
        result = dict(row)
        expected = compute_expected_value(*(row.get(key) for key in (
            "entry_price", "bear_price", "base_price", "bull_price", "bear_prob", "base_prob", "bull_prob")))
        result["expected_value"] = expected
        return result

    def list(self, limit: int, offset: int, only_open: bool = False) -> tuple[list[dict], int]:
        """`only_open`: the old «Mostrar solo entradas abiertas (sin revisar)»."""
        rows, total = self.repository.list_entries(limit, offset, only_open)
        return [self.present(row) for row in rows], total

    def create(self, entry: dict) -> dict:
        symbol = str(entry.get("symbol", "")).strip().upper().replace(".", "-")
        if not re.fullmatch(r"[A-Z0-9^][A-Z0-9^\-]{0,19}", symbol):
            raise QueryError("invalid_symbol", "Indica un símbolo válido.", 422)
        prices = (entry.get("entry_price"), entry.get("bear_price"), entry.get("base_price"), entry.get("bull_price"))
        probabilities = (entry.get("bear_prob"), entry.get("base_prob"), entry.get("bull_prob"))
        size = entry.get("position_size_pct")
        if any(value is not None and (not isfinite(value) or value < 0 or value > 1e9) for value in prices) or any(
            value is not None and (not isfinite(value) or value < 0 or value > 100) for value in probabilities
        ) or size is not None and (not isfinite(size) or size < 0 or size > 100):
            raise QueryError("invalid_journal", "Los precios y porcentajes deben ser finitos y no negativos.", 422)
        entry = entry | {"symbol": symbol}
        entry_id = self.repository.create(entry)
        row = self.repository.get(entry_id)
        assert row is not None
        return self.present(row)

    def review(self, entry_id: int, review_date: date, review_price: float | None, notes: str) -> dict:
        if review_price is not None and (not isfinite(review_price) or review_price < 0 or review_price > 1e9):
            raise QueryError("invalid_review", "El precio de revisión no es válido.", 422)
        if not self.repository.review(entry_id, review_date.isoformat(), review_price, notes):
            raise QueryError("entry_not_open", "No existe una entrada abierta con ese identificador.", 404)
        row = self.repository.get(entry_id)
        assert row is not None
        return self.present(row)

    def delete(self, entry_id: int) -> None:
        if not self.repository.delete(entry_id):
            raise QueryError("entry_not_found", "No existe una entrada con ese identificador.", 404)
