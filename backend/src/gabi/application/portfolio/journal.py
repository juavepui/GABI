"""Validated diary commands over the existing local journal_entries table.

A new thesis captures the price, the frozen score and the checklist of that moment (#186), read from the
local cache; «what changed» reads them again on demand. Neither downloads nor writes market data.
"""

import re
from collections.abc import Callable
from datetime import date, timedelta
from math import isfinite
from typing import Protocol

import pandas as pd

from gabi.application.errors import QueryError
from gabi.domain.portfolio import journal as rules
from gabi.domain.portfolio.journal import compute_expected_value

MAX_REVIEW_YEARS = 10


class JournalRepository(Protocol):
    def list_entries(self, limit: int, offset: int, only_open: bool = False,
                     symbol: str | None = None) -> tuple[list[dict], int]: ...
    def thesis_counts(self) -> dict[str, dict]: ...
    def get(self, entry_id: int) -> dict | None: ...
    def create(self, entry: dict) -> int: ...
    def review(self, entry_id: int, review_date: str, review_price: float | None, notes: str) -> bool: ...
    def delete(self, entry_id: int) -> bool: ...


def _finite(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _symbol(value: str) -> str:
    symbol = str(value or "").strip().upper().replace(".", "-")
    if not re.fullmatch(r"[A-Z0-9^][A-Z0-9^\-]{0,19}", symbol):
        raise QueryError("invalid_symbol", "Indica un símbolo válido.", 422)
    return symbol


class Journal:
    def __init__(self, repository: JournalRepository, ranking: Callable[[], pd.DataFrame] | None = None,
                 checklist: Callable[[str], dict] | None = None, model_id: str | None = None,
                 today: Callable[[], date] = date.today):
        """`ranking()` is the frozen ranking table; `checklist(symbol)` the company's checklist (its summary)."""
        self.repository, self.ranking, self.checklist, self.model_id = repository, ranking, checklist, model_id
        self.today = today

    def snapshot(self, symbol: str) -> dict:
        """Price, frozen score and checklist of the company now, from the local cache; absent values are None."""
        result: dict = {"price": None, "price_date": None, "score": None, "model_id": self.model_id,
                        "checklist_passed": None, "checklist_evaluated": None}
        if self.ranking is not None:
            try:
                table = self.ranking()
            except QueryError:  # No cached ranking yet: the thesis is still written.
                table = None
            if table is not None and symbol in table.index:
                source = table.attrs.get("sources", {}).get(symbol, {})
                result |= {"price": _finite(table.at[symbol, "price"]) if "price" in table else None,
                           "price_date": source.get("price_date"),
                           "score": _finite(table.at[symbol, "composite_score"])}
        if self.checklist is not None:
            try:
                summary = self.checklist(symbol)["summary"]
            except QueryError:
                summary = None
            if summary:
                result |= {"checklist_passed": summary.get("passed"), "checklist_evaluated": summary.get("evaluated")}
        return result

    @staticmethod
    def present(row: dict) -> dict:
        result = dict(row)
        expected = compute_expected_value(*(row.get(key) for key in (
            "entry_price", "bear_price", "base_price", "bull_price", "bear_prob", "base_prob", "bull_prob")))
        result["expected_value"] = expected
        return result

    def list(self, limit: int, offset: int, only_open: bool = False,
             symbol: str | None = None) -> tuple[list[dict], int]:
        """`only_open`: the old «Mostrar solo entradas abiertas (sin revisar)»; `symbol`: one company's."""
        rows, total = self.repository.list_entries(limit, offset, only_open, _symbol(symbol) if symbol else None)
        return [self.present(row) for row in rows], total

    def thesis_counts(self) -> dict[str, dict]:
        return self.repository.thesis_counts()

    def changes(self, entry_id: int) -> dict:
        """Read-only: price, score and checklist now against what the thesis captured."""
        row = self.repository.get(entry_id)
        if row is None:
            raise QueryError("entry_not_found", "No existe una entrada con ese identificador.", 404)
        head = {"entry_id": entry_id, "symbol": row["symbol"], "as_of": self.today().isoformat()}
        return head | rules.changes(row, self.snapshot(row["symbol"]))

    def create(self, entry: dict) -> dict:
        symbol = _symbol(entry.get("symbol", ""))
        due = entry.get("review_due")
        if due is not None and not self.today() < due <= self.today() + timedelta(days=366 * MAX_REVIEW_YEARS):
            raise QueryError("invalid_journal", "La fecha de revisión debe ser futura y de los próximos 10 años.",
                             422)
        prices = (entry.get("entry_price"), entry.get("bear_price"), entry.get("base_price"), entry.get("bull_price"))
        probabilities = (entry.get("bear_prob"), entry.get("base_prob"), entry.get("bull_prob"))
        size = entry.get("position_size_pct")
        if any(value is not None and (not isfinite(value) or value < 0 or value > 1e9) for value in prices) or any(
            value is not None and (not isfinite(value) or value < 0 or value > 100) for value in probabilities
        ) or size is not None and (not isfinite(size) or size < 0 or size > 100):
            raise QueryError("invalid_journal", "Los precios y porcentajes deben ser finitos y no negativos.", 422)
        captured = self.snapshot(symbol)
        typed = entry.get("entry_price") is not None
        entry = entry | {
            "symbol": symbol, "review_due": due.isoformat() if due is not None else None,
            # The typed entry price wins; without one, the latest cached close is the entry price.
            "entry_price": entry.get("entry_price") if typed else captured["price"],
            "entry_price_date": None if typed else captured["price_date"],
            "entry_score": captured["score"],
            "model_id": captured["model_id"] if captured["score"] is not None else None,
            "entry_checklist_passed": captured["checklist_passed"],
            "entry_checklist_evaluated": captured["checklist_evaluated"],
        }
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
