"""Investor profile and the S&P 500 benchmark in EUR with the profile's contributions (#244).

Reads never download: the benchmark uses the cached adjusted close of SPY and
the cached USDEUR=X rate, which only the explicit ``benchmark_prices`` job
refreshes. A missing series is reported, never filled in.
"""

import dataclasses
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Protocol

import pandas as pd

from gabi.application.errors import QueryError
from gabi.domain.portfolio import contributions as rules
from gabi.domain.portfolio.holdings import price_symbols
from gabi.domain.portfolio.simulation import fx_symbol

BENCHMARK_SYMBOL = "SPY"
FX_SYMBOL = "USDEUR=X"  # Euros per dollar, as cached by the price downloads.
BENCHMARK_SOURCE = {
    "symbol": BENCHMARK_SYMBOL, "series": "adj_close", "provider": "yahoo",
    "vehicle": "SPDR S&P 500 ETF (USD, distribución): el cierre ajustado reinvierte los dividendos brutos, "
               "sin retención en origen; el precio ya descuenta su TER.",
    "fx": FX_SYMBOL,
}
LOOKBACK_DAYS = 7
MAX_YEARS = 30


class ProfileStore(Protocol):
    def latest(self) -> dict | None: ...
    def revisions(self) -> list[dict]: ...
    def save(self, version: str, profile: dict, now: str) -> int: ...


def refresh_prices(fetch: Callable[[list[str]], dict]) -> dict:
    """The explicit download behind «Actualizar benchmark»: SPY and the EUR/USD rate."""
    symbols = [BENCHMARK_SYMBOL, FX_SYMBOL]
    failed = {str(key): str(reason) for key, reason in fetch(symbols).items()}
    return {"kind": "benchmark_prices", "symbols": symbols, "updated": len(symbols) - len(failed), "failed": failed}


def _stored(profile: rules.Profile) -> dict:
    stored = dataclasses.asdict(profile)
    stored.pop("version")
    stored["capital_needed_by"] = profile.capital_needed_by.isoformat() if profile.capital_needed_by else None
    return stored


def _series(frame: pd.DataFrame | None, column: str) -> pd.Series:
    if frame is None or frame.empty or column not in frame:
        return pd.Series(dtype=float)
    values = frame[column].dropna()
    return values[values > 0]


class InvestorBenchmark:
    def __init__(self, store: ProfileStore, prices: Callable[[list[str], str], dict[str, pd.DataFrame]],
                 today: Callable[[], date], now: Callable[[], datetime] = lambda: datetime.now(UTC),
                 lots: Callable[[], list[dict]] = list):
        """`prices(symbols, start)` reads cached daily prices; `lots()` the real purchases of #181."""
        self.store, self.prices, self.today, self.now, self.lots = store, prices, today, now, lots

    def profile(self) -> dict | None:
        return self.store.latest()

    def revisions(self) -> list[dict]:
        return self.store.revisions()

    def save(self, raw: dict) -> dict:
        """Every save is a new revision: earlier ones stay as they were."""
        try:
            profile = rules.validate_profile(raw, self.today())
        except ValueError as exc:
            raise QueryError("invalid_profile", str(exc), 422) from exc
        self.store.save(profile.version, _stored(profile), self.now().isoformat())
        saved = self.store.latest()
        assert saved is not None
        return saved

    def _current(self) -> tuple[rules.Profile, dict]:
        saved = self.store.latest()
        if saved is None:
            raise QueryError("profile_missing", "Guarda primero tu perfil de inversor.", 404)
        stored = saved["profile"]
        needed = stored.get("capital_needed_by")
        profile = rules.Profile(**(stored | {"capital_needed_by": date.fromisoformat(needed) if needed else None}),
                                version=saved["version"])
        return profile, saved

    def _benchmark_series(self, histories: dict[str, pd.DataFrame]) -> tuple[pd.Series, pd.Series]:
        prices = _series(histories.get(BENCHMARK_SYMBOL), "adj_close")
        euros_per_dollar = _series(histories.get(FX_SYMBOL), "close")
        missing = [symbol for symbol, values in ((BENCHMARK_SYMBOL, prices), (FX_SYMBOL, euros_per_dollar))
                   if values.empty]
        if missing:
            raise QueryError("benchmark_prices_missing",
                             f"Faltan precios en caché de {', '.join(missing)}: pulsa «Actualizar benchmark».", 409)
        return prices, euros_per_dollar

    @staticmethod
    def _source(prices: pd.Series, euros_per_dollar: pd.Series) -> dict:
        return BENCHMARK_SOURCE | {
            "first_price": prices.index[0].date().isoformat(), "last_price": prices.index[-1].date().isoformat(),
            "first_fx": euros_per_dollar.index[0].date().isoformat(),
            "last_fx": euros_per_dollar.index[-1].date().isoformat()}

    @staticmethod
    def _points(daily: pd.DataFrame) -> list[dict]:
        return [{"date": day.date().isoformat(), "value_eur": float(row.value_eur),
                 "contributed_eur": float(row.contributed_eur)} for day, row in daily.iterrows()]

    def holdings(self) -> dict:
        """Read-only: the real purchases against SPY bought with the same euros on the same sessions."""
        profile, saved = self._current()
        lots = self.lots()
        if not lots:
            raise QueryError("no_holdings", "Mi cartera no tiene compras que comparar.", 404)
        start = min(date.fromisoformat(lot["purchase_date"]) for lot in lots) - timedelta(days=LOOKBACK_DAYS)
        histories = self.prices(price_symbols(lots), start.isoformat())
        prices, euros_per_dollar = self._benchmark_series(histories)
        euros_per_unit = {currency: _series(histories.get(pair), "close")
                          for currency in {lot["currency"] for lot in lots}
                          if (pair := fx_symbol(currency, "EUR"))}
        adjusted = {lot["symbol"]: _series(histories.get(lot["symbol"]), "adj_close") for lot in lots}
        real = rules.lots_history(lots, adjusted, euros_per_unit, prices.index)
        if not real["flows"]:
            raise QueryError("valuation_unavailable", "Ninguna compra tiene precio y cambio en caché.", 422)
        vehicle = rules.broker_vehicle(profile, BENCHMARK_SYMBOL, "USD")
        try:
            spy = rules.simulate(real["flows"], prices, vehicle, 1 / euros_per_dollar)
        except ValueError as exc:
            raise QueryError("benchmark_unavailable", str(exc), 422) from exc
        portfolio, benchmark = rules.performance(real, profile), rules.performance(spy, profile)
        return {
            "as_of": self.today().isoformat(), "profile_revision": saved["revision"],
            "profile_version": profile.version, "source": self._source(prices, euros_per_dollar),
            "portfolio": portfolio, "benchmark": benchmark, "comparison": rules.compare(portfolio, benchmark),
            "excluded": real["excluded"], "incomplete_sessions": real["incomplete_sessions"],
            "portfolio_series": self._points(real["daily"]), "benchmark_series": self._points(spy["daily"]),
        }

    def benchmark(self, start: date | None = None) -> dict:
        """Read-only: the profile's contributions since ``start`` bought in SPY through the investor's broker."""
        profile, saved = self._current()
        today = self.today()
        start = start or rules.add_months(today, -profile.horizon_months)
        if not today - timedelta(days=365 * MAX_YEARS) <= start < today:
            raise QueryError("invalid_period", f"El inicio debe ser pasado y de los últimos {MAX_YEARS} años.", 422)
        histories = self.prices([BENCHMARK_SYMBOL, FX_SYMBOL], (start - timedelta(days=LOOKBACK_DAYS)).isoformat())
        prices, euros_per_dollar = self._benchmark_series(histories)
        flows = rules.schedule(profile, start, today)
        vehicle = rules.broker_vehicle(profile, BENCHMARK_SYMBOL, "USD")
        try:
            result = rules.simulate(flows, prices[prices.index >= pd.Timestamp(start)], vehicle,
                                    1 / euros_per_dollar)
        except ValueError as exc:
            raise QueryError("benchmark_unavailable", str(exc), 422) from exc
        return {
            "as_of": today.isoformat(), "start": start.isoformat(), "profile_revision": saved["revision"],
            "profile_version": profile.version,
            "capital_need_before_horizon": rules.capital_need_before_horizon(profile, today),
            "source": self._source(prices, euros_per_dollar),
            "performance": rules.performance(result, profile),
            "pending": [{"date": day.isoformat(), "amount_eur": amount} for day, amount in result["pending"]],
            "series": self._points(result["daily"]),
        }
