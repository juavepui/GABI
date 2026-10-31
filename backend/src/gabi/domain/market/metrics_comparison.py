"""Declared differences between the V1 metrics and SEC metrics V2 (#245).

Pure summaries over rows already computed: coverage by state, rank agreement,
top-quintile overlap and the largest differences. Correcting a definition does
not prove alpha; these numbers only say how much the ranking inputs move.
"""

from collections import Counter

import pandas as pd

TOP_FRACTION = 0.2
LARGEST = 15
EV_TOLERANCE = 0.10


def _spearman(a: pd.Series, b: pd.Series) -> float | None:
    both = pd.concat([a, b], axis=1).dropna()
    if len(both) < 3:
        return None
    value = both.iloc[:, 0].rank().corr(both.iloc[:, 1].rank())
    return None if pd.isna(value) else float(value)


def _top_overlap(a: pd.Series, b: pd.Series, fraction: float = TOP_FRACTION) -> float | None:
    both = pd.concat([a, b], axis=1).dropna()
    size = int(len(both) * fraction)
    if size < 1:
        return None
    first = set(both.iloc[:, 0].nlargest(size).index)
    second = set(both.iloc[:, 1].nlargest(size).index)
    return len(first & second) / size


def roic(rows: list[dict]) -> dict:
    """Rows: symbol, v1 (float | None), v2 (value, state, reason)."""
    frame = pd.DataFrame([{"symbol": row["symbol"], "v1": row["v1"], "v2": row["v2"]["value"],
                           "state": row["v2"]["state"], "reason": row["v2"]["reason"]} for row in rows],
                         columns=["symbol", "v1", "v2", "state", "reason"]).set_index("symbol")
    both = frame.dropna(subset=["v1", "v2"])
    difference = (both["v2"] - both["v1"]).sort_values(key=abs, ascending=False)
    lost = frame[frame["v1"].notna() & frame["v2"].isna()]
    return {
        "companies": len(frame),
        "v1_available": int(frame["v1"].notna().sum()),
        "v2_states": dict(Counter(frame["state"])),
        "v2_reasons": dict(Counter(frame["reason"].dropna())),
        "both_available": len(both),
        "spearman": _spearman(frame["v1"], frame["v2"]),
        "top_quintile_overlap": _top_overlap(frame["v1"], frame["v2"]),
        "median_abs_difference": float(difference.abs().median()) if len(difference) else None,
        # V1 had a number where V2 declares why there is none: the approximations V1 hid.
        "v1_only_reasons": dict(Counter(lost["reason"].dropna())),
        "largest_differences": [{"symbol": symbol, "v1": float(both.at[symbol, "v1"]),
                                 "v2": float(both.at[symbol, "v2"]), "difference": float(value)}
                                for symbol, value in difference.head(LARGEST).items()],
    }


def enterprise_value(rows: list[dict]) -> dict:
    """Rows: symbol, yahoo (float | None), v2 (value, state, reason)."""
    frame = pd.DataFrame([{"symbol": row["symbol"], "yahoo": row["yahoo"], "v2": row["v2"]["value"],
                           "state": row["v2"]["state"], "reason": row["v2"]["reason"]} for row in rows],
                         columns=["symbol", "yahoo", "v2", "state", "reason"]).set_index("symbol")
    both = frame[(frame["yahoo"] > 0) & frame["v2"].notna()]
    relative = (both["v2"] / both["yahoo"] - 1).sort_values(key=abs, ascending=False)
    return {
        "companies": len(frame),
        "yahoo_available": int(frame["yahoo"].notna().sum()),
        "v2_states": dict(Counter(frame["state"])),
        "v2_reasons": dict(Counter(frame["reason"].dropna())),
        "both_available": len(both),
        "median_relative_difference": float(relative.median()) if len(relative) else None,
        "share_beyond_tolerance": float((relative.abs() > EV_TOLERANCE).mean()) if len(relative) else None,
        "tolerance": EV_TOLERANCE,
        "largest_differences": [{"symbol": symbol, "yahoo": float(both.at[symbol, "yahoo"]),
                                 "v2": float(both.at[symbol, "v2"]), "relative": float(value)}
                                for symbol, value in relative.head(LARGEST).items()],
    }


def ranking(v1: pd.Series, v2: pd.Series, top_n: int) -> dict:
    """Composite scores of the same universe with each ROIC: agreement and top-N changes."""
    top_v1 = list(v1.dropna().nlargest(top_n).index)
    top_v2 = list(v2.dropna().nlargest(top_n).index)
    return {"top_n": top_n, "spearman": _spearman(v1, v2),
            "top_overlap": len(set(top_v1) & set(top_v2)) / top_n if top_n else None,
            "entering": [symbol for symbol in top_v2 if symbol not in top_v1],
            "leaving": [symbol for symbol in top_v1 if symbol not in top_v2]}
