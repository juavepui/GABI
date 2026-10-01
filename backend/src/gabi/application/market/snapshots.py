"""Follow-up of saved rankings: progress against SPY until today, curve and fixed 6/12-month results."""

from collections.abc import Callable
from datetime import date
from typing import Protocol

import pandas as pd

from gabi.application.errors import QueryError
from gabi.application.research.historical import _json_value


class SnapshotStore(Protocol):
    def snapshot_meta(self, snapshot_id: int) -> dict | None: ...
    def snapshot(self, snapshot_id: int) -> pd.DataFrame: ...
    def rename(self, snapshot_id: int, name: str) -> bool: ...


class SnapshotPrices(Protocol):
    @property
    def price_at(self) -> Callable[..., float | None]: ...

    def latest_date(self, symbols: list[str]) -> pd.Timestamp | None: ...
    def histories(self, symbols: list[str], as_of_date: str) -> dict[str, pd.DataFrame]: ...


class SnapshotMath(Protocol):
    def progress(self, symbols: list[str], as_of_date: str, *, data_as_of, price_at, today: date) -> dict: ...
    def curve(self, symbols: list[str], as_of_date: str, histories: dict) -> pd.DataFrame: ...
    def evaluate(self, symbols: list[str], as_of_date: str, months: int, *, price_at, today: date) -> dict: ...


def snapshot_name(name: str) -> str:
    """The naming rule of evaluation._snapshot_name."""
    name = (name or "").strip()
    if not name or len(name) > 80:
        raise QueryError("invalid_snapshot", "El nombre del ranking debe tener entre 1 y 80 caracteres.", 422)
    return name


class SnapshotTracking:
    def __init__(self, store: SnapshotStore, prices: Callable[[date], SnapshotPrices], math: SnapshotMath,
                 today: Callable[[], date]):
        self.store, self.prices, self.math, self.today = store, prices, math, today

    def _snapshot(self, snapshot_id: int) -> tuple[dict, list[str]]:
        row = self.store.snapshot_meta(snapshot_id)
        if row is None:
            raise QueryError("snapshot_not_found", "El ranking guardado no existe.", 404)
        return row, self.store.snapshot(snapshot_id).index.astype(str).tolist()

    def progress(self, snapshot_id: int) -> dict:
        """Equal-weight basket of exactly the saved candidates, from the saved date until today."""
        row, symbols = self._snapshot(snapshot_id)
        today = self.today()
        prices = self.prices(today)
        progress = self.math.progress(symbols, row["as_of_date"], data_as_of=prices.latest_date([*symbols, "SPY"]),
                                      price_at=prices.price_at, today=today)
        curve = self.math.curve(symbols, row["as_of_date"], prices.histories([*symbols, "SPY"], row["as_of_date"]))
        horizons = [{"months": months} | {key: _json_value(value) for key, value in self.math.evaluate(
            symbols, row["as_of_date"], months, price_at=prices.price_at, today=today).items()}
            for months in (6, 12)]
        return {"id": snapshot_id, "name": row["name"], "as_of_date": row["as_of_date"],
                "created_at": row["created_at"], "candidates": len(symbols)} | {
            key: _json_value(progress[key]) for key in (
                "today", "data_as_of", "stale", "available", "requested", "portfolio_return",
                "benchmark_return", "excess_return", "missing")} | {
            "detail": [{key: _json_value(value) for key, value in item.items()}
                       for item in progress["detail"].to_dict("records")],
            "curve": [{"date": index.date().isoformat(), "basket": _json_value(item.get("Cartera")),
                       "spy": _json_value(item.get("SPY"))} for index, item in curve.iterrows()],
            "horizons": horizons,
        }

    def rename(self, snapshot_id: int, name: str) -> dict:
        name = snapshot_name(name)
        self._snapshot(snapshot_id)
        if not self.store.rename(snapshot_id, name):
            raise QueryError("snapshot_not_found", "El ranking guardado no existe.", 404)
        return {"id": snapshot_id, "name": name}
