"""Run the unchanged Portfolio Lab engine with the Streamlit form's parameters."""


def run_portfolio_lab(start: str, end: str, options: dict) -> dict:
    from gabi import portfolio_lab

    result = portfolio_lab.run_portfolio_lab(
        start, end, months=options["months"], top_n=options["top_n"],
        initial_capital=options["initial_capital"], max_symbols=options["max_symbols"], mode=options["mode"],
        schemes=tuple(options["schemes"]),
    )
    return result | {"labels": dict(portfolio_lab.SCHEME_LABELS), "scenario_labels": dict(portfolio_lab.SCENARIO_LABELS),
                     "scenario_ground": dict(portfolio_lab.SCENARIO_GROUND)}
