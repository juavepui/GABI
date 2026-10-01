"""The old Carteras simuladas price buttons: one ticker (with SPY and FX) or every traded symbol (with SPY)."""

from collections.abc import Callable
from typing import Protocol

from gabi.application.errors import QueryError

CURRENCIES = ("USD", "EUR", "GBP")


class SimulationStore(Protocol):
    def portfolio(self, portfolio_id: int) -> dict | None: ...
    def trades(self, portfolio_id: int) -> list[dict]: ...


def price_symbols(portfolio: dict, trades: list[dict], symbol: str | None,
                  fx_symbol: Callable[[str, str], str | None]) -> list[str]:
    base = portfolio["base_currency"]
    if symbol is not None:  # «Actualizar precios públicos de este ticker»
        return [symbol, "SPY"] + [pair for currency in CURRENCIES if currency != base
                                  if (pair := fx_symbol(currency, base))]
    if not trades:
        raise QueryError("no_trades", "La cartera no tiene operaciones cuyos precios actualizar.", 409)
    # «Actualizar precios de esta cartera y SPY»
    symbols = list(dict.fromkeys(str(trade["symbol"]) for trade in trades)) + ["SPY"]
    quotes = list(dict.fromkeys(str(trade["quote_currency"]) for trade in trades)) + ["USD"]
    return symbols + sorted({pair for currency in quotes if (pair := fx_symbol(currency, base))})


def refresh_prices(store: SimulationStore, portfolio_id: int, symbol: str | None,
                   fx_symbol: Callable[[str, str], str | None], fetch: Callable[[list[str]], dict]) -> dict:
    portfolio = store.portfolio(portfolio_id)
    if portfolio is None:
        raise QueryError("portfolio_not_found", "La cartera no existe.", 404)
    symbols = price_symbols(portfolio, store.trades(portfolio_id), symbol, fx_symbol)
    failed = {str(key): str(reason) for key, reason in fetch(symbols).items()}
    return {"kind": "sim_prices", "portfolio_id": portfolio_id, "symbol": symbol, "symbols": symbols,
            "updated": len(symbols) - len(failed), "failed": failed}
