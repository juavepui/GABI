"""Source and period of the metrics the company page shows (#169).

The same concept can come from Yahoo (its last twelve months or last quarter),
from the latest SEC 10-K or from GABI's cached prices. The backend declares
which one every value is; React only labels it. Nothing here changes a value.
"""

# source: yahoo (Yahoo info record), sec_10k (latest annual SEC filing), prices (GABI on cached prices).
# period: ttm (last twelve months), mrq (latest quarter), snapshot (value at capture),
# 5y_monthly (Yahoo's beta), 3m (three-month average), fiscal_year (latest 10-K),
# fiscal_years_3 (3-year CAGR of 10-Ks), 6m/12m (price window), cached_history (whole cached series).
METRIC_SOURCES: dict[str, tuple[str, str]] = {
    "market_cap": ("yahoo", "snapshot"),
    "pe": ("yahoo", "ttm"),
    "peg": ("yahoo", "snapshot"),
    "pb": ("yahoo", "mrq"),
    "ps": ("yahoo", "ttm"),
    "ev_ebitda": ("yahoo", "ttm"),
    "roe": ("yahoo", "ttm"),
    "roa": ("yahoo", "ttm"),
    "operating_margin": ("yahoo", "ttm"),
    "gross_margin": ("yahoo", "ttm"),
    "profit_margin": ("yahoo", "ttm"),
    "debt_to_equity": ("yahoo", "mrq"),
    "current_ratio": ("yahoo", "mrq"),
    "revenue_growth_yoy": ("yahoo", "mrq"),
    "earnings_growth_yoy": ("yahoo", "mrq"),
    "revenue_growth_ttm_yoy": ("yahoo", "ttm"),
    "free_cashflow": ("yahoo", "ttm"),
    "beta": ("yahoo", "5y_monthly"),
    "dividend_yield": ("yahoo", "ttm"),
    "avg_volume": ("yahoo", "3m"),
    "roic": ("sec_10k", "fiscal_year"),
    "revenue_cagr_3y": ("sec_10k", "fiscal_years_3"),
    "fcf_cagr_3y": ("sec_10k", "fiscal_years_3"),
    "momentum_6m": ("prices", "6m"),
    "momentum_12m": ("prices", "12m"),
    "volatility": ("prices", "cached_history"),
    "max_drawdown": ("prices", "cached_history"),
    "sharpe_ratio": ("prices", "cached_history"),
    "sortino_ratio": ("prices", "cached_history"),
    "beta_calc": ("prices", "cached_history"),
    "alpha": ("prices", "cached_history"),
    "win_rate_monthly": ("prices", "cached_history"),
}
