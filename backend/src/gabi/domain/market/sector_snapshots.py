"""Choose the dated sector snapshot known at a date; earlier dates fall back to an approximate first photo."""

import pandas as pd

FIELDS = ("sector", "industry", "name", "cik", "effective_date")
SNAPSHOT_COLUMNS = ["symbol", "cik", "name", "sector", "industry", "effective_date"]


def unknown() -> dict:
    return {**dict.fromkeys(FIELDS), "is_approximate": True}


def from_observations(frame: pd.DataFrame, as_of: str) -> dict:
    """Entity-attributed snapshots: latest on/before ``as_of``, else the earliest, marked approximate."""
    before = frame[frame["effective_date"] <= as_of]
    chosen = (before.sort_values("effective_date").iloc[-1] if not before.empty
              else frame.sort_values("effective_date").iloc[0])
    return {**{key: chosen.get(key) for key in FIELDS}, "is_approximate": before.empty}


def from_symbol_rows(rows: list[tuple], as_of: str) -> dict[str, dict]:
    """Legacy ticker-keyed snapshots with the same rule; symbols without rows are absent."""
    if not rows:
        return {}
    frame = pd.DataFrame(rows, columns=SNAPSHOT_COLUMNS)
    result = {}
    for symbol, group in frame.groupby("symbol"):
        on_or_before = group[group["effective_date"] <= as_of]
        if not on_or_before.empty:
            chosen, approximate = on_or_before.loc[on_or_before["effective_date"].idxmax()], False
        else:
            chosen, approximate = group.loc[group["effective_date"].idxmin()], True
        result[symbol] = {"sector": chosen["sector"], "industry": chosen["industry"], "name": chosen["name"],
                          "cik": chosen["cik"], "effective_date": chosen["effective_date"],
                          "is_approximate": approximate}
    return result
