"""Empresas seguidas (#182): explicit writes of followed companies and a read-only view from the local cache.

The view reads the saved list, the frozen ranking and the journal counts once each; nothing is downloaded.
The checklist summary is computed per company from SQLite, so it is a separate, bounded query.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

import pandas as pd

from gabi.application.errors import QueryError
from gabi.domain.market import watchlist as rules
from gabi.domain.market.identity import normalize_symbol


class WatchlistStore(Protocol):
    def items(self) -> list[dict]: ...
    def item(self, symbol: str) -> dict | None: ...
    def add(self, item: dict, now: str) -> bool: ...
    def update_note(self, symbol: str, note: str | None, now: str) -> bool: ...
    def delete(self, symbol: str) -> bool: ...


class Watchlist:
    def __init__(self, store: WatchlistStore, ranking: Callable[[], pd.DataFrame], model_id: str,
                 theses: Callable[[list[str]], dict[str, dict]], checklist: Callable[[str], dict],
                 now: Callable[[], datetime] = lambda: datetime.now(UTC)):
        """`ranking()` is the frozen ranking table; `checklist(symbol)` the company's checklist summary."""
        self.store, self.ranking, self.model_id, self.theses = store, ranking, model_id, theses
        self.checklist_summary, self.now = checklist, now

    def symbols(self) -> list[str]:
        """The followed symbols alone, for the «Seguir» buttons and the home alerts: no ranking needed."""
        return [item["symbol"] for item in self.store.items()]

    def _item(self, symbol: str) -> dict:
        item = self.store.item(normalize_symbol(symbol))
        if item is None:
            raise QueryError("watchlist_not_found", "No sigues esa empresa.", 404)
        return item

    @staticmethod
    def _note(note: str | None) -> str | None:
        try:
            return rules.clean_note(note)
        except ValueError as exc:
            raise QueryError("invalid_note", str(exc), 422) from exc

    def add(self, symbol: str, note: str | None = None) -> dict:
        """Follows a company of the universe, keeping today's score and position to measure the change."""
        symbol, note = normalize_symbol(symbol), self._note(note)
        table = self.ranking()
        if symbol not in table.index:
            raise QueryError("company_not_found", f"{symbol} no está en el universo del ranking.", 404)
        score, rank = rules.standing(table, symbol)
        self.store.add({"symbol": symbol, "added_at": self.now().isoformat(), "note": note,
                        "model_id": self.model_id, "score_at_add": score, "rank_at_add": rank},
                       self.now().isoformat())
        return self._item(symbol)

    def update(self, symbol: str, note: str | None) -> dict:
        item = self._item(symbol)
        self.store.update_note(item["symbol"], self._note(note), self.now().isoformat())
        return self._item(symbol)

    def delete(self, symbol: str) -> bool:
        if not self.store.delete(normalize_symbol(symbol)):
            raise QueryError("watchlist_not_found", "No sigues esa empresa.", 404)
        return True

    def summary(self) -> dict:
        """Read-only: score and position now and when added, next results and theses in the journal."""
        saved = self.store.items()
        if not saved:
            return {"model_id": self.model_id, "ranking_ready": True, "items": []}
        try:
            table = self.ranking()
        except QueryError:  # No cached data yet: the list and its notes are still shown.
            table = None
        symbols = [item["symbol"] for item in saved]
        return {"model_id": self.model_id, "ranking_ready": table is not None,
                "items": rules.rows(saved, table, self.model_id, self.theses(symbols))}

    def checklists(self) -> dict:
        """Criteria met / evaluable of every followed company; one that cannot be evaluated is left empty."""
        result = {}
        for symbol in self.symbols():
            try:
                result[symbol] = self.checklist_summary(symbol)["summary"]
            except QueryError:
                result[symbol] = None
        return {"items": result}
