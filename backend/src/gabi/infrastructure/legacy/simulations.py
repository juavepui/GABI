"""Pure legacy simulation math shared with Streamlit; no global storage calls."""

from gabi import sim_portfolios

MARKETS = sim_portfolios.MARKETS
replay = sim_portfolios.replay
fx_symbol = sim_portfolios.fx_symbol
fx_at = sim_portfolios._fx_at
portfolio_history_from_data = sim_portfolios.portfolio_history_from_data
summarize = sim_portfolios.summarize


class LegacySimulationMath:
    replay = staticmethod(replay)
    fx_symbol = staticmethod(fx_symbol)
    fx_at = staticmethod(fx_at)
    history = staticmethod(portfolio_history_from_data)
    summarize = staticmethod(summarize)
