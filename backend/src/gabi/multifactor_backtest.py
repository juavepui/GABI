"""Backtest multifactor con rebalanceos periódicos, reconstruyendo el ranking
point-in-time en cada fecha con los datos de SEC EDGAR y los precios
ajustados ya cacheados.

Fachada del caso de uso ``application/research/backtest_v1`` (#132): construye en cada
llamada sus entradas explícitas (composición, ranking, precios atribuidos, filings,
calendario NYSE y fecha de hoy) con los módulos de siempre. Los nombres internos
(``_period_returns``, ``_sample_symbols``…) se conservan porque los motores congelados
los envuelven o los leen."""
from datetime import date

import exchange_calendars as xcals
import pandas as pd

from gabi.application.research import backtest_v1
from gabi.application.research.backtest_market import BacktestMarket
from gabi.domain.market import data_quality as quality_rules
from gabi.domain.portfolio import backtest as rules

from . import config, historical_pit, identity, screener_asof, universe

_MAX_DAYS_WITHOUT_FILING = rules.MAX_DAYS_WITHOUT_FILING
_SAMPLE_SEED = rules.SAMPLE_SEED
_sample_symbols = rules.sample_symbols
_apply_holding_buffer = rules.apply_holding_buffer
sharpe_standard_error = rules.sharpe_standard_error


def market(*, issuer_history: bool = False) -> BacktestMarket:
    """The operational inputs, read when called: tests and frozen engines patch these modules.

    ``issuer_history`` (app backtests only) reads each ticker's whole issuer history; frozen
    engines never pass it, so their patched rankings keep the old signature."""
    options = {"issuer_history": True} if issuer_history else {}
    return BacktestMarket(
        membership=lambda as_of: universe.get_sp500_constituents_asof(as_of),
        ranking=lambda as_of, symbols: screener_asof.build_ranking_as_of(as_of, symbols=symbols, **options)["table"],
        quality=lambda ranked: quality_rules.ranking_quality(ranked),
        prices=lambda symbols, as_of, owners=None: identity.backtest_prices(symbols, as_of, owners),
        last_filings=lambda symbols, as_of: identity.last_filings(symbols, as_of=as_of),
        owner=lambda symbol, as_of: identity.resolve(symbol, as_of)["entity_id"],
        exit_value=lambda frame, entity, entry, exit_session: historical_pit.exit_value(frame, entity, entry, exit_session),
        calendar=xcals.get_calendar("XNYS"), today=date.today, risk_free_rate=config.RISK_FREE_RATE)


def required_symbols(start: str, end: str, months: int,
                     max_symbols: int | None = None) -> list[str]:
    return backtest_v1.required_symbols(market(), start, end, months, max_symbols)


def _period_returns(symbols: list[str], as_of: pd.Timestamp, months: int,
                    cost_bps: float, held_symbols: set = None) -> dict:
    """Retorno de un periodo; ver ``backtest_v1.period_returns``."""
    return backtest_v1.period_returns(market(), symbols, as_of, months, cost_bps, held_symbols)


def _risk_metrics(returns: pd.Series, periods_per_year: float, years: float = None) -> dict:
    return rules.risk_metrics(returns, periods_per_year, years, risk_free_rate=config.RISK_FREE_RATE)


def run(start: str, end: str, months: int = 3, top_n: int = 10,
        cost_bps: float = 10, min_coverage: float = .7, min_universe_coverage: float = .5,
        max_symbols: int | None = None, buffer_multiplier: float = 1.0,
        rotation_hurdle_points: float = 0.0, issuer_history: bool = False) -> dict:
    """Backtest V1; ver ``backtest_v1.run``. ``_period_returns`` se resuelve en cada periodo."""
    return backtest_v1.run(market(issuer_history=issuer_history), lambda *args, **kwargs: _period_returns(*args, **kwargs), start, end,
                           months=months, top_n=top_n, cost_bps=cost_bps, min_coverage=min_coverage,
                           min_universe_coverage=min_universe_coverage, max_symbols=max_symbols,
                           buffer_multiplier=buffer_multiplier, rotation_hurdle_points=rotation_hurdle_points)


def daily_capital_curve(periods: pd.DataFrame) -> pd.Series:
    return backtest_v1.daily_capital_curve(market(), periods)


def daily_benchmark_curve(periods: pd.DataFrame, return_column: str = "spy",
                          symbol: str = "SPY") -> pd.Series:
    return backtest_v1.daily_benchmark_curve(market(), periods, return_column, symbol)


def daily_risk_metrics(curve: pd.Series) -> dict:
    return rules.daily_risk_metrics(curve, risk_free_rate=config.RISK_FREE_RATE)
