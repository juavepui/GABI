"""Present a legacy point-in-time ranking without changing its calculation."""

import math
from datetime import date, datetime
from typing import Protocol

import numpy as np
import pandas as pd


class HistoricalRunner(Protocol):
    def __call__(self, as_of: str) -> dict: ...


def _json_value(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, (float, np.floating)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if pd.isna(value):
        return None
    return str(value)


def build_historical_ranking(as_of: str, run: HistoricalRunner) -> dict:
    result = run(as_of)
    table = result["table"]
    if not isinstance(table, pd.DataFrame) or len(table) > 1000:
        raise ValueError("Historical result exceeds the bounded universe")
    records = table.reset_index().to_dict(orient="records") if not table.empty else []
    return {
        "as_of": as_of,
        "status": "RETROSPECTIVE_EXPLORATORY",
        "independent_advantage_demonstrated": False,
        "universe_info": _json_value(result["universe_info"]),
        "total": len(records),
        "rows": [{str(key): _json_value(value) for key, value in row.items()} for row in records],
    }
