"""The two "Preparar datos" buttons of the historical ranking page, run as one explicit job."""

from gabi.application.research.preparation import preparation_result


def _merge(failures: dict, stage: str, failed: dict) -> None:
    for symbol, reason in failed.items():
        failures.setdefault(symbol, {})[stage] = reason


def prepare_history(start: str, end: str | None, options: dict) -> dict:
    from gabi import data_fetch, edgar, multifactor_backtest, universe

    failures: dict[str, dict[str, str]] = {}
    if options["scope"] == "date":
        membership = universe.get_sp500_constituents_asof(start)
        symbols = membership["symbols"]
        if options["universe_limit"]:
            symbols = symbols[:options["universe_limit"]]
        edgar_result = edgar.ensure_edgar_data(symbols, as_of=start)
        price_result = data_fetch.ensure_price_history_asof(symbols, start)
        _merge(failures, "edgar", edgar_result["failed"])
        _merge(failures, "precio", price_result["failed"])
        summary = {"symbols": len(symbols), "universe_note": membership["note"],
                   "universe_is_exact": bool(membership["is_exact"]),
                   "edgar_refreshed": edgar_result["edgar_refreshed"],
                   "prices_deep_fetched": price_result["deep_fetched"],
                   "prices_already_covered": price_result["already_covered"]}
        return preparation_result(start, end, options, summary, failures)
    assert end is not None
    symbols = multifactor_backtest.required_symbols(start, end, options["months"], options["max_symbols"])
    edgar_result = edgar.ensure_edgar_data(symbols)
    price_failures: dict[str, str] = {}
    for offset in range(0, len(symbols), 25):
        price_failures.update(data_fetch.fetch_prices_batch(symbols[offset:offset + 25], period="max"))
    price_failures.update(data_fetch.fetch_prices_batch(["SPY"], period="max"))
    _merge(failures, "edgar", edgar_result["failed"])
    _merge(failures, "precio", price_failures)
    summary = {"symbols": len(symbols), "universe_note": None, "universe_is_exact": True,
               "edgar_refreshed": None, "prices_deep_fetched": None, "prices_already_covered": None}
    return preparation_result(start, end, options, summary, failures)
