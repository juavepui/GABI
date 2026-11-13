"""SEC filing comparison over explicitly supplied cached facts, with GABI's EDGAR tag lists."""

import pandas as pd

from gabi.domain.market import filings


def tags() -> dict[str, list[str]]:
    from gabi import edgar

    return {"revenue": edgar.REVENUE_TAGS, "operating_income": edgar.OPERATING_INCOME_TAGS,
            "gross_profit": edgar.GROSS_PROFIT_TAGS, "ocf": edgar.OCF_TAGS, "capex": edgar.CAPEX_TAGS,
            "net_income": edgar.NET_INCOME_TAGS, "equity": edgar.EQUITY_TAGS, "debt": edgar.LT_DEBT_TAGS,
            "cash": edgar.CASH_TAGS}


def compare_cached(symbol: str, facts: pd.DataFrame, cik: str | None) -> list[dict]:
    return filings.compare_cached(symbol, facts, cik, tags())
