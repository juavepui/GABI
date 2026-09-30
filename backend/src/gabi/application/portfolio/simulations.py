"""Local simulated trades, using the same replay and cost rules as Streamlit."""

import re
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from math import isfinite
from typing import Protocol

import pandas as pd

from gabi.application.errors import QueryError
from gabi.domain.portfolio.simulation import MARKETS, execution_quote


class SimulationRepository(Protocol):
    def portfolios(self) -> list[dict]: ...
    def portfolio(self, portfolio_id: int) -> dict | None: ...
    def trades(self, portfolio_id: int) -> list[dict]: ...
    def prices(self, symbols: list[str], start: str) -> dict[str, pd.DataFrame]: ...
    def create(self, portfolio: dict) -> int: ...
    def add_trade(self, trade: dict, previous_id: int) -> int: ...
    def undo_last(self, portfolio_id: int, expected_id: int) -> bool: ...


class SimulationMath(Protocol):
    def replay(self, portfolio: dict, trades: pd.DataFrame, histories: dict) -> tuple[float, dict]: ...
    def fx_symbol(self, quote_currency: str, base_currency: str) -> str | None: ...
    def fx_at(self, histories: dict, quote_currency: str, base_currency: str, day: str) -> float: ...
    def history(self, portfolio: dict, trades: pd.DataFrame, histories: dict) -> dict: ...
    def summarize(self, result: dict) -> dict: ...


class Simulations:
    def __init__(self, repository: SimulationRepository, math: SimulationMath, today: Callable[[], date]):
        self.repository, self.math, self.today = repository, math, today

    def portfolios(self) -> list[dict]:
        return self.repository.portfolios()

    def portfolio(self, portfolio_id: int) -> dict:
        portfolio = self.repository.portfolio(portfolio_id)
        if portfolio is None:
            raise QueryError("portfolio_not_found", "La cartera simulada no existe.", 404)
        return portfolio

    def trades(self, portfolio_id: int) -> list[dict]:
        self.portfolio(portfolio_id)
        return self.repository.trades(portfolio_id)

    def create(self, payload: dict) -> dict:
        name = str(payload["name"]).strip()
        amounts = (payload["initial_cash"], payload["stock_commission"],
                   payload["etf_commission"], payload["spread_bps"])
        if not name or len(name) > 80 or any(not isfinite(value) or value < 0 or value > 1e9 for value in amounts) \
                or payload["initial_cash"] <= 0 or payload["base_currency"] not in ("USD", "EUR"):
            raise QueryError("invalid_portfolio", "Nombre, capital o costes no válidos.", 422)
        record = payload | {"name": name, "created_at": datetime.now(UTC).isoformat()}
        return self.portfolio(self.repository.create(record))

    def trade(self, portfolio_id: int, payload: dict) -> dict:
        portfolio = self.portfolio(portfolio_id)
        symbol = str(payload["symbol"]).strip().upper().replace(".", "-")
        if not re.fullmatch(r"[A-Z0-9^][A-Z0-9^\-]{0,19}", symbol) or payload["asset_type"] not in ("STOCK", "ETF") \
                or payload["side"] not in ("BUY", "SELL") or payload["market"] not in MARKETS:
            raise QueryError("invalid_trade", "Símbolo, instrumento, operación o mercado no válido.", 422)
        notional = payload["notional"]
        commission = payload["commission"]
        if commission is None:
            commission = portfolio["etf_commission"] if payload["asset_type"] == "ETF" else portfolio["stock_commission"]
        spread = payload["spread_bps"] if payload["spread_bps"] is not None else portfolio["spread_bps"]
        fx_fee = payload["fx_fee_bps"]
        if any(not isfinite(value) or value < 0 or value > 1e9 for value in (notional, commission, spread, fx_fee)) \
                or notional <= 0:
            raise QueryError("invalid_trade", "Importe y costes deben ser finitos y no negativos.", 422)
        requested = payload["requested_date"]
        if requested > self.today():
            raise QueryError("invalid_trade", "No se puede simular una operación futura.", 422)
        existing = self.repository.trades(portfolio_id)
        if len(existing) >= 500:
            raise QueryError("resource_limit", "La cartera alcanza el límite de 500 operaciones.", 422)
        currencies = {row["quote_currency"] for row in existing if row["symbol"] == symbol}
        if currencies and currencies != {payload["quote_currency"]}:
            raise QueryError("currency_mismatch", "Un ticker no puede cambiar de divisa en la cartera.", 422)
        history = self.repository.prices([symbol], requested.isoformat()).get(symbol, pd.DataFrame())
        try:
            quote = execution_quote(history, requested.isoformat(), payload["market"], self.today())
            pair = self.math.fx_symbol(payload["quote_currency"], portfolio["base_currency"])
            if pair:
                rate = payload["fx_rate"]
                if rate is None:
                    fx = self.repository.prices([pair], (date.fromisoformat(quote["date"]) - timedelta(days=7)).isoformat())
                    rate = self.math.fx_at(fx, payload["quote_currency"], portfolio["base_currency"], quote["date"])
            else:
                rate, fx_fee = 1.0, 0.0
            if not isfinite(rate) or rate <= 0:
                raise ValueError("El tipo de cambio debe ser positivo.")
            previous_id = max((int(row["id"]) for row in existing), default=0)
            new_trade = {"id": previous_id + 1, "portfolio_id": portfolio_id, "symbol": symbol,
                         "asset_type": payload["asset_type"], "side": payload["side"],
                         "requested_date": requested.isoformat(), "execution_date": quote["date"],
                         "reference_close": quote["close"], "notional": notional, "commission": commission,
                         "spread_bps": spread, "created_at": datetime.now(UTC).isoformat(),
                         "market": payload["market"], "quote_currency": payload["quote_currency"],
                         "fx_rate": rate, "fx_fee_bps": fx_fee}
            combined = pd.DataFrame(existing + [new_trade])
            symbols = combined["symbol"].unique().tolist()
            start = min(combined["execution_date"])
            histories = self.repository.prices(symbols, start)
            self.math.replay(portfolio, combined, histories)
        except (ValueError, KeyError, TypeError) as exc:
            raise QueryError("trade_unavailable", str(exc), 422) from exc
        trade_id = self.repository.add_trade(new_trade, previous_id)
        return new_trade | {"id": trade_id}

    def undo(self, portfolio_id: int) -> bool:
        portfolio = self.portfolio(portfolio_id)
        existing = self.repository.trades(portfolio_id)
        if not existing:
            return False
        last_id = max(int(row["id"]) for row in existing)
        remaining = [row for row in existing if row["id"] != last_id]
        if remaining:
            start = min(row["execution_date"] for row in remaining)
            histories = self.repository.prices(sorted({row["symbol"] for row in remaining}), start)
            try:
                self.math.replay(portfolio, pd.DataFrame(remaining), histories)
            except ValueError as exc:
                raise QueryError("trade_unavailable", str(exc), 422) from exc
        return self.repository.undo_last(portfolio_id, last_id)

    def result(self, portfolio_id: int, *, long: bool = False) -> dict:
        portfolio = self.portfolio(portfolio_id)
        rows = self.repository.trades(portfolio_id)
        if not rows:
            return {"summary": {}, "curve": [], "positions": {}, "cash": portfolio["initial_cash"]}
        trades = pd.DataFrame(rows)
        base = portfolio["base_currency"]
        symbols = trades["symbol"].unique().tolist()
        first = date.fromisoformat(min(trades["execution_date"]))
        if not long and ((self.today() - first).days > 1095 or len(symbols) > 10 or len(rows) > 100):
            raise QueryError("job_required", "El historial requiere un job local; solicítalo desde esta pantalla.", 409)
        try:
            pairs = {self.math.fx_symbol(currency, base) for currency in trades["quote_currency"].unique()}
            pairs.add(self.math.fx_symbol("USD", base))
            start = (date.fromisoformat(min(trades["execution_date"])) - timedelta(days=7)).isoformat()
            histories = self.repository.prices(symbols + ["SPY"] + sorted(pair for pair in pairs if pair), start)
            result = self.math.history(portfolio, trades, histories)
            summary = self.math.summarize(result)
        except (ValueError, KeyError, TypeError) as exc:
            raise QueryError("result_unavailable", str(exc), 422) from exc
        curve = result["curve"].reset_index()
        points = [{"date": row["date"].date().isoformat(), "value": float(row["value"]) if pd.notna(row["value"]) else None,
                   "cash": float(row["cash"])} for _, row in curve.tail(500).iterrows()]
        return {"summary": summary, "curve": points, "positions": result["positions"], "cash": result["cash"]}

    def compare(self) -> dict:
        """Worker-only comparison; each row retains its own investment period."""
        rows = []
        for portfolio in self.repository.portfolios():
            try:
                trades = self.repository.trades(portfolio["id"])
                if not trades:
                    continue
                summary = self.result(portfolio["id"], long=True)["summary"]
                if summary.get("status") != "complete":
                    continue
                rows.append({"id": portfolio["id"], "name": portfolio["name"],
                             "from_date": min(trade["execution_date"] for trade in trades),
                             "to_date": summary.get("as_of"), "return": summary.get("return"),
                             "benchmark_return": summary.get("benchmark_return"),
                             "max_drawdown": summary.get("max_drawdown")})
            except QueryError:
                continue
        return {"items": rows, "status": "EXPERIMENTAL",
                "note": "Cada cartera se compara con SPY en su propio periodo; periodos distintos no son equivalentes."}
