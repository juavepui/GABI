"""Publish only observed, explicit consensus-revision experiments."""

from collections.abc import Callable
from datetime import date

import pandas as pd

from gabi.application.research.historical import _json_value
from gabi.application.research.reservations import OBSERVED_END


def build_estimate_analysis(run: Callable[[date], dict]) -> dict:
    result = run(OBSERVED_END)
    output = {
        "kind": "estimate_analysis", "status": result["status"],
        "observed_cutoff": OBSERVED_END.isoformat(),
        "period": "0q", "horizons_months": [1, 3],
        "batches_available": result["batches_available"],
        "span_days": result["span_days"],
        "independent_advantage_demonstrated": False,
    }
    if result["status"] == "insufficient_data":
        output.update({"reason": result["reason"],
                       "batches_needed": result["batches_needed"],
                       "span_days_needed": result["span_days_needed"],
                       "summary": [], "ic_series": []})
    else:
        for name in ("summary", "ic_series"):
            table = result[name]
            if not isinstance(table, pd.DataFrame) or len(table) > 1_000:
                raise ValueError("El análisis de estimaciones supera el límite de resultado.")
            output[name] = [{str(key): _json_value(value) for key, value in row.items()}
                            for row in table.to_dict(orient="records")]
        output.update({"reason": None, "batches_needed": 6, "span_days_needed": 60})
    return output
