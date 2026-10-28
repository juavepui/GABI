"""Motor de backtest V2: contabilidad real de cartera (acciones + caja),
turnover y coste real por operación, y curva NAV diaria genuina -- no una
reconstrucción de porcentajes escalada a posteriori como hace
`multifactor_backtest.daily_capital_curve` (V1).

Fachada del caso de uso ``application/research/backtest_v2`` (#132), con las mismas
entradas explícitas que V1 (``multifactor_backtest.market()``). Conserva los nombres
internos que envuelven los motores congelados (``_daily_segment``, ``_rebalance``) y
que usa Portfolio Lab (``_rebalance_to_weights``).

Convención de coste: la MISMA que `sim_portfolios.py` (Carteras Simuladas) —
comisión fija en dólares por operación + spread proporcional que encarece la
compra / reduce lo cobrado en la venta (`_apply_trade`, ver
`sim_portfolios._cash_delta`/`replay`). No se inventa un modelo nuevo."""
import pandas as pd

from gabi.application.research import backtest_v2
from gabi.domain.portfolio import backtest as rules
from gabi.domain.portfolio import broker_costs

from . import multifactor_backtest as v1

_CALENDAR = "XNYS"
VALID_MODES = backtest_v2.VALID_MODES
_apply_trade = rules.apply_trade
_rebalance_to_weights = rules.rebalance_to_weights
_rebalance = rules.rebalance
_settle_exits = rules.settle_exits


def _daily_segment(cash: float, shares: dict, entry_session: pd.Timestamp,
                   exit_session: pd.Timestamp, sessions: pd.DatetimeIndex, *, owners: dict | None = None) -> pd.Series:
    """Valoración diaria de un tramo; ver ``backtest_v2.daily_segment``."""
    return backtest_v2.daily_segment(v1.market(), cash, shares, entry_session, exit_session, sessions, owners=owners)


def _historical_exits(histories: dict, shares: dict, owners: dict | None,
                      entry_session: pd.Timestamp, exit_session: pd.Timestamp) -> dict:
    return backtest_v2.historical_exits(v1.market(), histories, shares, owners, entry_session, exit_session)


def run(start: str, end: str, months: int = 3, top_n: int = 20, max_symbols: int | None = None,
        mode: str = "validation", initial_capital: float = 100_000.0,
        commission_usd: float = broker_costs.STOCK_FEE_USD,
        spread_bps: float = 10.0, min_coverage: float = .7, min_universe_coverage: float = .5,
        rotation_hurdle_points: float = 0.0, issuer_history: bool = False) -> dict:
    """Backtest V2; ver ``backtest_v2.run``. ``_rebalance`` y ``_daily_segment`` se resuelven en cada periodo."""
    return backtest_v2.run(v1.market(issuer_history=issuer_history), lambda *args, **kwargs: _rebalance(*args, **kwargs),
                           lambda *args, **kwargs: _daily_segment(*args, **kwargs), start, end,
                           months=months, top_n=top_n, max_symbols=max_symbols, mode=mode,
                           initial_capital=initial_capital, commission_usd=commission_usd, spread_bps=spread_bps,
                           min_coverage=min_coverage, min_universe_coverage=min_universe_coverage,
                           rotation_hurdle_points=rotation_hurdle_points)


def buy_and_hold_curve(symbol: str, start: str, end: str, initial_capital: float = 100_000.0,
                       commission_usd: float = broker_costs.STOCK_FEE_USD,
                       spread_bps: float = 10.0) -> pd.Series:
    return backtest_v2.buy_and_hold_curve(v1.market(), symbol, start, end, initial_capital=initial_capital,
                                          commission_usd=commission_usd, spread_bps=spread_bps)
