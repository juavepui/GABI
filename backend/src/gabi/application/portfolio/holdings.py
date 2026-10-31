"""Mi cartera (#181): explicit writes of real purchase lots and a read-only valuation from the local cache."""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Protocol

import pandas as pd

from gabi.application.errors import QueryError
from gabi.domain.portfolio import holdings as rules
from gabi.domain.portfolio.concentration import sector_breakdown
from gabi.domain.portfolio.selection import target_portfolio

TARGET_POSITIONS = 20


class HoldingsStore(Protocol):
    def lots(self) -> list[dict]: ...
    def lot(self, lot_id: int) -> dict | None: ...
    def add(self, lots: list[dict], now: str) -> list[int]: ...
    def update(self, lot_id: int, lot: dict, now: str) -> bool: ...
    def delete(self, lot_id: int) -> bool: ...


def refresh_prices(store: HoldingsStore, fetch: Callable[[list[str]], dict]) -> dict:
    """The explicit download behind «Actualizar precios de mi cartera»: holdings, SPY and the rates."""
    lots = store.lots()
    if not lots:
        raise QueryError("no_holdings", "Mi cartera no tiene compras cuyos precios actualizar.", 409)
    symbols = rules.price_symbols(lots)
    failed = {str(key): str(reason) for key, reason in fetch(symbols).items()}
    return {"kind": "holdings_prices", "symbols": symbols, "updated": len(symbols) - len(failed), "failed": failed}


class Holdings:
    def __init__(self, store: HoldingsStore, prices: Callable[[list[str], str], dict[str, pd.DataFrame]],
                 ranking: Callable[[], pd.DataFrame], today: Callable[[], date],
                 now: Callable[[], datetime] = lambda: datetime.now(UTC)):
        """`prices(symbols, start)` reads cached daily prices; `ranking()` is the frozen ranking table."""
        self.store, self.prices, self.ranking, self.today, self.now = store, prices, ranking, today, now

    def lots(self) -> list[dict]:
        return self.store.lots()

    def _checked(self, lots: list[dict]) -> list[dict]:
        try:
            checked = [rules.validate_lot(lot, self.today()) for lot in lots]
        except ValueError as exc:
            raise QueryError("invalid_holding", str(exc), 422) from exc
        held = {lot["symbol"]: lot["currency"] for lot in self.store.lots()}
        for lot in checked:
            if held.setdefault(lot["symbol"], lot["currency"]) != lot["currency"]:
                raise QueryError("currency_mismatch", f"{lot['symbol']} ya está registrada en otra divisa.", 422)
        if len(held) > rules.MAX_SYMBOLS:
            raise QueryError("resource_limit", f"Mi cartera admite como máximo {rules.MAX_SYMBOLS} empresas.", 422)
        return checked

    def add(self, lot: dict) -> dict:
        lot_id = self.store.add(self._checked([lot]), self.now().isoformat())[0]
        return self._lot(lot_id)

    def import_csv(self, text: str) -> dict:
        """All rows or none: a single wrong row rejects the whole file."""
        try:
            lots = rules.parse_csv(text, self.today())
        except ValueError as exc:
            raise QueryError("invalid_csv", str(exc), 422) from exc
        ids = self.store.add(self._checked(lots), self.now().isoformat())
        return {"imported": len(ids), "ids": ids}

    def update(self, lot_id: int, lot: dict) -> dict:
        current = self._lot(lot_id)
        others = [row for row in self.store.lots() if row["id"] != lot_id]
        try:
            checked = rules.validate_lot(lot, self.today())
        except ValueError as exc:
            raise QueryError("invalid_holding", str(exc), 422) from exc
        if any(row["symbol"] == checked["symbol"] and row["currency"] != checked["currency"] for row in others):
            raise QueryError("currency_mismatch", f"{checked['symbol']} ya está registrada en otra divisa.", 422)
        if not self.store.update(current["id"], checked, self.now().isoformat()):
            raise QueryError("holding_not_found", "La compra no existe.", 404)
        return self._lot(lot_id)

    def delete(self, lot_id: int) -> bool:
        if not self.store.delete(lot_id):
            raise QueryError("holding_not_found", "La compra no existe.", 404)
        return True

    def _lot(self, lot_id: int) -> dict:
        lot = self.store.lot(lot_id)
        if lot is None:
            raise QueryError("holding_not_found", "La compra no existe.", 404)
        return lot

    def _valuation(self, lots: list[dict]) -> dict:
        start = (min(date.fromisoformat(lot["purchase_date"]) for lot in lots)
                 - timedelta(days=rules.LOOKBACK_DAYS)).isoformat()
        try:
            return rules.value(lots, self.prices(rules.price_symbols(lots), start))
        except ValueError as exc:
            raise QueryError("valuation_unavailable", str(exc), 422) from exc

    def positions(self) -> list[dict]:
        """Valued positions from the cache (price return), each with its currency and status."""
        lots = self.store.lots()
        return self._valuation(lots)["positions"] if lots else []

    def values_eur(self) -> tuple[dict[str, float], list[str]]:
        """Current euro value by symbol for the contribution plan, and the symbols that cannot be valued."""
        lots = self.store.lots()
        if not lots:
            return {}, []
        positions = self._valuation(lots)["positions"]
        return ({row["symbol"]: row["value_eur"] for row in positions if row["status"] == "ok"},
                [row["symbol"] for row in positions if row["status"] != "ok"])

    def summary(self) -> dict:
        """Read-only: positions, totals against SPY, weights against the frozen target and sectors."""
        lots = self.store.lots()
        today = self.today()
        base = {"as_of": today.isoformat(), "base_currency": rules.BASE_CURRENCY, "lots": lots,
                "price_symbols": rules.price_symbols(lots) if lots else []}
        if not lots:
            return base | {"positions": [], "totals": None, "benchmark_as_of": None, "deviations": [],
                           "sectors": [], "missing": []}
        valuation = self._valuation(lots)
        table = self.ranking()
        target = target_portfolio(table, TARGET_POSITIONS)
        weights = {str(symbol): float(weight) for symbol, weight in target["weight_pct"].items()}
        sectors = table["sector"] if "sector" in table else pd.Series(dtype="string")
        for row in valuation["positions"]:
            row["sector"] = None if row["symbol"] not in sectors.index or pd.isna(sectors[row["symbol"]]) \
                else str(sectors[row["symbol"]])
            row["in_target"] = row["symbol"] in weights
        valued = pd.DataFrame([{"sector": row["sector"], "weight_pct": row["weight_pct"]}
                               for row in valuation["positions"] if row["status"] == "ok"],
                              columns=["sector", "weight_pct"])
        return base | valuation | {
            "deviations": rules.deviations(valuation["positions"], weights),
            "sectors": sector_breakdown(valued, table) if not valued.empty else [],
            "missing": [row["symbol"] for row in valuation["positions"] if row["status"] != "ok"],
        }
