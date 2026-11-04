"""Mi cartera (#181): explicit writes of real purchase lots and a read-only valuation from the local cache."""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Protocol

import pandas as pd

from gabi.application.errors import QueryError
from gabi.domain.portfolio import holdings as rules
from gabi.domain.portfolio import holdings_basis, holdings_performance
from gabi.domain.portfolio.concentration import sector_breakdown
from gabi.domain.portfolio.selection import target_portfolio
from gabi.domain.portfolio.simulation import fx_symbol

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

    def _prepared(self, lots: list[dict]) -> tuple[list[dict], dict[str, pd.DataFrame], list[dict]]:
        if not lots:
            return [], {}, []
        start = (min(date.fromisoformat(lot['purchase_date']) for lot in lots)
                 - timedelta(days=rules.LOOKBACK_DAYS)).isoformat()
        return holdings_basis.prepare(lots, self.prices(rules.price_symbols(lots), start), self.today())

    def _sequence(self, lots: list[dict]) -> None:
        converted, _, _ = self._prepared(lots)
        rules.check_sequence(converted)

    def _checked(self, lots: list[dict]) -> list[dict]:
        try:
            checked = [rules.validate_lot(lot, self.today()) for lot in lots]
        except ValueError as exc:
            raise QueryError("invalid_holding", str(exc), 422) from exc
        current = self.store.lots()
        try:
            self._sequence([*current, *checked])
        except ValueError as exc:
            raise QueryError("invalid_holding", str(exc), 422) from exc
        held = {lot["symbol"]: lot["currency"] for lot in current}
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
        try:
            self._sequence([*others, {**checked, "id": lot_id}])
        except ValueError as exc:
            raise QueryError("invalid_holding", str(exc), 422) from exc
        if not self.store.update(current["id"], checked, self.now().isoformat()):
            raise QueryError("holding_not_found", "La compra no existe.", 404)
        return self._lot(lot_id)

    def delete(self, lot_id: int) -> bool:
        """A purchase cannot be deleted if a later sale or dividend would be left without shares."""
        try:
            self._sequence([row for row in self.store.lots() if row["id"] != lot_id])
        except ValueError as exc:
            raise QueryError("invalid_holding", "No se puede borrar: " + str(exc), 422) from exc
        if not self.store.delete(lot_id):
            raise QueryError("holding_not_found", "La compra no existe.", 404)
        return True

    def _lot(self, lot_id: int) -> dict:
        lot = self.store.lot(lot_id)
        if lot is None:
            raise QueryError("holding_not_found", "La compra no existe.", 404)
        return lot

    def _valuation(self, lots: list[dict]) -> dict:
        try:
            converted, histories, warnings = self._prepared(lots)
            rules.check_sequence(converted)
            result = holdings_basis.display(rules.value(converted, histories), histories)
            return result | {'warnings': warnings}
        except ValueError as exc:
            raise QueryError("valuation_unavailable", str(exc), 422) from exc

    def positions(self) -> list[dict]:
        """Valued positions from the cache (price return), each with its currency and status."""
        lots = self.store.lots()
        if not lots:
            return []
        valuation = self._valuation(lots)
        unverified = {warning['symbol'] for warning in valuation['warnings']}
        return [row | {'status': 'unverified_actions'} if row['symbol'] in unverified else row
                for row in valuation['positions']]

    def values_eur(self) -> tuple[dict[str, float], list[str]]:
        """Current euro value by symbol for the contribution plan, and the symbols that cannot be valued."""
        lots = self.store.lots()
        if not lots:
            return {}, []
        valuation = self._valuation(lots)
        positions = valuation['positions']
        unverified = {warning['symbol'] for warning in valuation['warnings']}
        return ({row["symbol"]: row["value_eur"] for row in positions
                 if row["status"] == "ok" and row['symbol'] not in unverified},
                [row["symbol"] for row in positions if row["status"] != "ok" or row['symbol'] in unverified])

    def summary(self) -> dict:
        """Read-only: positions, totals against SPY, weights against the frozen target and sectors."""
        lots = self.store.lots()
        today = self.today()
        base = {"as_of": today.isoformat(), "base_currency": rules.BASE_CURRENCY, "lots": lots,
                "price_symbols": rules.price_symbols(lots) if lots else []}
        if not lots:
            return base | {"positions": [], "closed": [], "totals": None, "benchmark_as_of": None, "deviations": [],
                           "sectors": [], "missing": [], "warnings": []}
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

    def performance(self) -> dict:
        """Read-only (#294): daily value, TWR and money-weighted return, risk, attribution and SPY with the
        same flows, from cached closes and rates. Nothing is downloaded and no gap is filled."""
        lots = self.store.lots()
        if not lots:
            raise QueryError("no_holdings", "Mi cartera no tiene movimientos que analizar.", 404)
        try:
            lots, histories, warnings = self._prepared(lots)
            rules.check_sequence(lots)
        except ValueError as exc:
            raise QueryError('valuation_unavailable', str(exc), 422) from exc

        def column(symbol: str | None, name: str) -> pd.Series:
            frame = histories.get(symbol) if symbol else None
            if frame is None or frame.empty or name not in frame:
                return pd.Series(dtype=float, index=pd.DatetimeIndex([]))
            values = frame[name].dropna()
            return values[values > 0]

        closes = {symbol: column(symbol, "close") for symbol in {lot["symbol"] for lot in lots}}
        rates = {currency: column(fx_symbol(currency, rules.BASE_CURRENCY), "close")
                 for currency in {"USD", *(lot["currency"] for lot in lots)} if currency != rules.BASE_CURRENCY}
        table = self.ranking()
        sectors = {} if "sector" not in table else {
            str(symbol): None if pd.isna(sector) else str(sector) for symbol, sector in table["sector"].items()}
        result = holdings_performance.evaluate(lots, closes, rates, column("SPY", "adj_close"),
                                               {lot["symbol"]: sectors.get(lot["symbol"]) for lot in lots},
                                               self.today())
        return {"base_currency": rules.BASE_CURRENCY, **result, 'warnings': warnings}
