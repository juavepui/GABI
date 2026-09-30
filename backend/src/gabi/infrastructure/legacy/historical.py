"""Single F6 bridge to the unchanged point-in-time ranking engine."""


def run_historical(as_of: str) -> dict:
    from gabi import screener_asof

    return screener_asof.build_ranking_as_of(as_of)
