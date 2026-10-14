"""Price downloads of the simulated portfolios through the Yahoo download bridge."""


def fetch_max_history(symbols: list[str]) -> dict:
    """Worker only (its LegacyExecutor checks the data directory): the full history, as the old buttons."""
    from gabi.infrastructure.legacy import data_fetch

    return data_fetch.fetch_prices_batch(symbols, period="max")
