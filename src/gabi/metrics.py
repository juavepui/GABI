"""Deriva métricas fundamentales a partir de los datos crudos cacheados de yfinance."""


def _positive_or_none(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if x > 0 else None


def _revenue_growth_from_quarterly(quarterly_income: dict):
    """Compara los últimos 4 trimestres (TTM) con los 4 anteriores usando la
    partida 'Total Revenue' del estado de resultados trimestral cacheado.

    Nota: yfinance en el nivel gratuito normalmente solo expone ~4-8 trimestres,
    así que esto da como mucho un crecimiento interanual TTM, no un CAGR a 3
    años real. Se documenta como limitación conocida en el README.
    """
    if not quarterly_income:
        return None
    revenue_key = None
    for row in quarterly_income.values():
        if "Total Revenue" in row:
            revenue_key = "Total Revenue"
            break
    if revenue_key is None:
        return None

    series = {}
    for date_str, row in quarterly_income.items():
        val = row.get(revenue_key)
        if val is not None:
            series[date_str] = val
    if len(series) < 8:
        return None

    dates_sorted = sorted(series.keys())
    values = [series[d] for d in dates_sorted]
    ttm_now = sum(values[-4:])
    ttm_then = sum(values[-8:-4])
    if not ttm_then or ttm_then <= 0:
        return None
    return (ttm_now / ttm_then) - 1


def compute_fundamental_metrics(fundamentals_record: dict) -> dict:
    """fundamentals_record: dict con claves 'info' y 'quarterly_income' tal como
    los devuelve storage.get_fundamentals()."""
    if not fundamentals_record:
        return {}
    info = fundamentals_record.get("info") or {}
    qi = fundamentals_record.get("quarterly_income") or {}

    return {
        "market_cap": info.get("marketCap"),
        "pe": _positive_or_none(info.get("trailingPE")),
        "peg": _positive_or_none(info.get("pegRatio")),
        "pb": info.get("priceToBook"),
        "ps": _positive_or_none(info.get("priceToSalesTrailing12Months")),
        "ev_ebitda": _positive_or_none(info.get("enterpriseToEbitda")),
        "roe": info.get("returnOnEquity"),
        "roa": info.get("returnOnAssets"),
        "operating_margin": info.get("operatingMargins"),
        "gross_margin": info.get("grossMargins"),
        "profit_margin": info.get("profitMargins"),
        "debt_to_equity": info.get("debtToEquity"),
        "current_ratio": info.get("currentRatio"),
        "revenue_growth_yoy": info.get("revenueGrowth"),
        "earnings_growth_yoy": info.get("earningsGrowth"),
        "revenue_growth_ttm_yoy": _revenue_growth_from_quarterly(qi),
        "free_cashflow": info.get("freeCashflow"),
        "beta": info.get("beta"),
        "sector": info.get("sector"),
        "name": info.get("shortName"),
    }
