"""Portfolio Lab over the unchanged point-in-time ranking, prices, filings and V1/V2 accounting."""

from datetime import date

from gabi.application.research.portfolio_lab_engine import run_portfolio_lab as run_engine
from gabi.domain.research import portfolio_lab as rules


class LegacyPortfolioLabSources:
    """Each method is the call the original module made; nothing is reimplemented."""

    def __init__(self):
        from gabi import multifactor_backtest as v1
        from gabi import portfolio_backtest as v2

        self.valid_modes = tuple(v2.VALID_MODES)
        self.max_days_without_filing = v1._MAX_DAYS_WITHOUT_FILING

    @staticmethod
    def membership(as_of: str) -> dict:
        from gabi import universe

        return universe.get_sp500_constituents_asof(as_of)

    @staticmethod
    def sample(symbols: list[str], max_symbols: int | None) -> list[str]:
        from gabi import multifactor_backtest as v1

        return v1._sample_symbols(symbols, max_symbols)

    @staticmethod
    def ranking(as_of: str, symbols: list[str]):
        from gabi import screener_asof

        return screener_asof.build_ranking_as_of(as_of, symbols=symbols)["table"]

    @staticmethod
    def prices(symbols: list[str]) -> dict:
        from gabi import storage

        return storage.get_prices_multi(symbols)

    @staticmethod
    def last_filed(symbols: list[str], as_of: str) -> dict:
        from gabi import edgar

        return edgar.get_last_filed_dates(symbols, as_of=as_of)

    @staticmethod
    def daily_segment(cash, shares, entry, exit_session, sessions):
        from gabi import portfolio_backtest as v2

        return v2._daily_segment(cash, shares, entry, exit_session, sessions)

    @staticmethod
    def rebalance(cash, shares, weights, prices, commission_usd, spread_bps) -> dict:
        from gabi import portfolio_backtest as v2

        return v2._rebalance_to_weights(cash, shares, weights, prices, commission_usd, spread_bps)

    @staticmethod
    def buy_and_hold(symbol: str, start: str, end: str, *, initial_capital: float, commission_usd: float,
                     spread_bps: float):
        from gabi import portfolio_backtest as v2

        return v2.buy_and_hold_curve(symbol, start, end, initial_capital=initial_capital,
                                     commission_usd=commission_usd, spread_bps=spread_bps)

    @staticmethod
    def daily_risk(nav) -> dict:
        from gabi import multifactor_backtest as v1

        return v1.daily_risk_metrics(nav)

    @staticmethod
    def tracking_error(returns, benchmark):
        from gabi import portfolio_metrics

        return portfolio_metrics.tracking_error(returns, benchmark)

    @staticmethod
    def min_variance(histories: dict, picks: list[str]):
        from gabi import decision_engine

        return decision_engine._risk_weights(histories, picks)

    @staticmethod
    def beta(returns, benchmark):
        from gabi import portfolio_metrics

        return portfolio_metrics.beta_vs_benchmark(returns, benchmark)


def run_portfolio_lab(start: str, end: str, options: dict) -> dict:
    """The Streamlit form's parameters, with the broker's stock fee as the default commission."""
    from gabi import broker_costs

    result = run_engine(
        start, end, LegacyPortfolioLabSources(), date.today(), commission_usd=broker_costs.STOCK_FEE_USD,
        months=options["months"], top_n=options["top_n"], initial_capital=options["initial_capital"],
        max_symbols=options["max_symbols"], mode=options["mode"], schemes=tuple(options["schemes"]),
    )
    return result | {"labels": dict(rules.SCHEME_LABELS), "scenario_labels": dict(rules.SCENARIO_LABELS),
                     "scenario_ground": dict(rules.SCENARIO_GROUND)}
