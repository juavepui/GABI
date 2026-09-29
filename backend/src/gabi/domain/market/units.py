"""Wire units of existing metrics; formatting never changes financial inputs."""

FRACTIONS = frozenset({
    "roe", "roa", "roic", "operating_margin", "gross_margin", "profit_margin",
    "revenue_growth_yoy", "earnings_growth_yoy", "revenue_growth_ttm_yoy",
    "revenue_cagr_3y", "fcf_cagr_3y", "price_vs_sma50", "price_vs_sma200",
    "momentum_6m", "momentum_12m", "rel_strength_6m", "volatility", "max_drawdown",
    "alpha", "win_rate_monthly", "dividend_yield", "score_coverage", "cagr",
})
USD = frozenset({"market_cap", "free_cashflow", "price", "sma50", "sma200"})
BASE_METRICS = (
    "market_cap", "pe", "peg", "pb", "ps", "ev_ebitda", "roe", "roa", "operating_margin", "gross_margin",
    "profit_margin", "debt_to_equity", "current_ratio", "revenue_growth_yoy", "earnings_growth_yoy",
    "revenue_growth_ttm_yoy", "free_cashflow", "beta", "dividend_yield", "avg_volume", "price", "sma50", "sma200",
    "price_vs_sma50", "price_vs_sma200", "rsi14", "momentum_6m", "momentum_12m", "rel_strength_6m", "volatility",
    "max_drawdown", "sharpe_ratio", "sortino_ratio", "beta_calc", "alpha", "win_rate_monthly", "roic",
    "revenue_cagr_3y", "fcf_cagr_3y", "value_score", "quality_score", "momentum_score", "risk_score",
    "metrics_available", "metrics_possible", "score_coverage", "composite_score", "confidence",
)


def metric_unit(name: str) -> str:
    if name in FRACTIONS:
        return "fraction"
    if name in USD:
        return "USD"
    if name.endswith("_pct") or name.endswith("_score") or name in {"confidence", "rsi14"}:
        return "points_0_100"
    if name == "debt_to_equity":
        return "percent"  # Yahoo reports debt/equity * 100; do not scale again.
    if name in {"metrics_available", "metrics_possible", "avg_volume"}:
        return "count"
    return "ratio"
