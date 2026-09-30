"""Run the unchanged V1/V2 backtest engines with the metrics Streamlit showed."""


def run_backtest_v1(start: str, end: str, options: dict) -> dict:
    from gabi import multifactor_backtest

    return multifactor_backtest.run(
        start, end, options["months"], options["top_n"], options["cost_bps"],
        max_symbols=options["universe_size"],
        rotation_hurdle_points=options["rotation_hurdle_points"],
    )


def run_backtest_v2(start: str, end: str, options: dict) -> dict:
    from gabi import multifactor_backtest, portfolio_backtest, portfolio_metrics

    result = portfolio_backtest.run(
        start, end, months=options["months"], top_n=options["top_n"],
        max_symbols=options["max_symbols"], mode=options["mode"],
        initial_capital=options["initial_capital"], commission_usd=options["commission_usd"],
        spread_bps=options["spread_bps"], rotation_hurdle_points=options["rotation_hurdle_points"],
    )
    nav, nav_spy = result["nav_curve"], result["nav_curve_spy"]
    daily = multifactor_backtest.daily_risk_metrics(nav)
    returns, returns_spy = nav.pct_change().dropna(), nav_spy.pct_change().dropna()
    result["metrics"] = {
        "estrategia": daily,
        "spy": multifactor_backtest.daily_risk_metrics(nav_spy),
        "calmar": portfolio_metrics.calmar_ratio(daily["anualizado"], daily["max_drawdown"]),
        "recovery_days": portfolio_metrics.recovery_time(nav),
        "beta": portfolio_metrics.beta_vs_benchmark(returns, returns_spy),
        "information_ratio": portfolio_metrics.information_ratio(returns, returns_spy),
        "capture": portfolio_metrics.capture_ratios(returns, returns_spy),
    }
    return result
