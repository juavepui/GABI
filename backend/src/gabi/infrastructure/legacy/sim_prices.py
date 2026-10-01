"""Price downloads of the simulated portfolios through the unchanged sim_portfolios and data_fetch."""


def fx_symbol(quote_currency: str, base_currency: str) -> str | None:
    from gabi import sim_portfolios

    return sim_portfolios.fx_symbol(quote_currency, base_currency)


def fetch_max_history(symbols: list[str]) -> dict:
    """Worker only (its LegacyExecutor checks the data directory): the full history, as the old buttons."""
    from gabi import data_fetch

    return data_fetch.fetch_prices_batch(symbols, period="max")
