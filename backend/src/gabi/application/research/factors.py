"""Serialize Factor Lab's unchanged calculations as an exploratory job artifact."""

from typing import Protocol

import pandas as pd

from gabi.application.research.historical import _json_value


class FactorRunner(Protocol):
    def __call__(self, start: str, end: str, *, months: int, mode: str,
                 max_symbols: int | None) -> dict: ...


def build_factor_analysis(start: str, end: str, months: int, mode: str,
                          max_symbols: int | None, run: FactorRunner) -> dict:
    result = run(start, end, months=months, mode=mode, max_symbols=max_symbols)
    tables = {}
    for name in ("summary", "ic_series", "quantile_returns", "turnover"):
        table = result[name]
        if not isinstance(table, pd.DataFrame) or len(table) > 20_000:
            raise ValueError("Factor Lab result exceeds the bounded artifact")
        tables[name] = [{str(key): _json_value(value) for key, value in row.items()}
                        for row in table.to_dict(orient="records")]
    return {
        "kind": "factor_analysis", "status": "RETROSPECTIVE_EXPLORATORY",
        "independent_advantage_demonstrated": False,
        "start": start, "end": end, "months": months, "mode": mode,
        "max_symbols": max_symbols,
        **tables,
        "skipped": _json_value(result["skipped"]),
    }
