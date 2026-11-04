"""Declared differences between the V1 metrics and SEC metrics V2 (#245), and between the
app's ranking and the historical engine's on the same day (#291).

Pure summaries over rows already computed: coverage by state, rank agreement,
top-quintile overlap and the largest differences. Correcting a definition does
not prove alpha; these numbers only say how much the ranking inputs move.
"""

from collections import Counter

import pandas as pd

TOP_FRACTION = 0.2
LARGEST = 15
EV_TOLERANCE = 0.10
TOP_N_PARITY = 20
# Reading guide of the rank agreement (#291), not a validation threshold: from 0.9 the two orders
# barely differ; below 0.7 a historical result says little about the app's order.
PARITY_LEVELS = ((0.9, "very_similar"), (0.7, "similar"))


def _spearman(a: pd.Series, b: pd.Series) -> float | None:
    both = pd.concat([a, b], axis=1).dropna()
    if len(both) < 3 or both.iloc[:, 0].nunique() < 2 or both.iloc[:, 1].nunique() < 2:
        return None  # A constant column has no order; pandas would warn and return NaN.
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


def _positions(scores: pd.Series) -> pd.Series:
    """1 = best composite score; companies without a score have no position."""
    ordered = scores.dropna().sort_values(ascending=False, kind="mergesort")
    return pd.Series(range(1, len(ordered) + 1), index=ordered.index, dtype=float)


def _number(value) -> float | None:
    return None if value is None or pd.isna(value) else float(value)


def contributions(row: pd.Series, weights: dict[str, float], score_metrics: dict[str, list[str]]) -> dict[str, float]:
    """Points each scored metric adds to one company's composite score, as ``scoring.build_scores`` combines them.

    The composite is the weighted mean of the available blocks and each block the mean of
    its available percentiles, so a metric adds weight/total × percentile/available. A
    missing metric adds nothing; the sum is the composite itself.
    """
    blocks = {block: [metric for metric in metrics if _number(row.get(f"{metric}_pct")) is not None]
              for block, metrics in score_metrics.items()}
    total = sum(weights.get(block, 0) for block, present in blocks.items() if present)
    result = {}
    for block, metrics in score_metrics.items():
        for metric in metrics:
            pct = _number(row.get(f"{metric}_pct"))
            result[metric] = (weights.get(block, 0) / total * pct / len(blocks[block])
                              if pct is not None and total else 0.0)
    return result


def live_vs_historical(live: pd.DataFrame, historical: pd.DataFrame, *, weights: dict[str, float],
                       score_metrics: dict[str, list[str]], sources: dict[str, dict[str, tuple[str, str]]],
                       top_n: int = TOP_N_PARITY) -> dict:
    """The app's ranking against the historical engine's on the same day and universe (#291).

    ``sources`` maps ``live`` and ``historical`` to metric → (source, period). The cause of a
    company's move is the scored metric whose contribution to its composite changed most;
    when none changed, it moved only because other companies did.
    """
    live_scores, past_scores = live["composite_score"], historical["composite_score"]
    common = live_scores.index.intersection(past_scores.index)
    live_scores, past_scores = live_scores.reindex(common), past_scores.reindex(common)
    scored = live_scores.notna() & past_scores.notna()
    agreement = ranking(live_scores, past_scores, top_n)
    live_rank, past_rank = _positions(live_scores), _positions(past_scores)
    block_of = {metric: block for block, metrics in score_metrics.items() for metric in metrics}
    metrics = []
    for metric, block in block_of.items():
        a, b = (frame[metric].reindex(common) if metric in frame else pd.Series(index=common, dtype=float)
                for frame in (live, historical))
        metrics.append({"metric": metric, "block": block, "live_available": int(a.notna().sum()),
                        "historical_available": int(b.notna().sum()), "spearman": _spearman(a, b),
                        "live_source": sources["live"].get(metric), "historical_source": sources["historical"].get(metric)})
    moves = []
    for symbol in common[scored]:
        live_row, past_row = live.loc[symbol], historical.loc[symbol]
        change = past_rank[symbol] - live_rank[symbol]
        now, then = contributions(live_row, weights, score_metrics), contributions(past_row, weights, score_metrics)
        impact = {metric: now[metric] - then[metric] for metric in now}
        cause = max(impact, key=lambda metric: (abs(impact[metric]), metric)) if impact else None
        if cause is not None and abs(impact[cause]) < 1e-9:
            cause = None  # Its own inputs agree: other companies moved around it.
        detail = None
        if cause is not None:
            live_value, past_value = _number(live_row.get(cause)), _number(past_row.get(cause))
            detail = {"metric": cause, "block": block_of[cause], "impact": impact[cause],
                      "live_value": live_value, "historical_value": past_value,
                      "live_pct": _number(live_row.get(f"{cause}_pct")),
                      "historical_pct": _number(past_row.get(f"{cause}_pct")),
                      "missing": ("live" if live_value is None else "historical" if past_value is None else None),
                      "live_source": sources["live"].get(cause), "historical_source": sources["historical"].get(cause),
                      "historical_period_end": past_row.get("fundamentals_period_end")
                      if sources["historical"].get(cause, ("", ""))[0] == "sec_10k" else None}
        moves.append({"symbol": symbol, "live_rank": int(live_rank[symbol]), "historical_rank": int(past_rank[symbol]),
                      "rank_change": int(change), "composite_difference": float(live_scores[symbol] - past_scores[symbol]),
                      "cause": detail})
    moves.sort(key=lambda row: (-abs(row["rank_change"]), -abs(row["composite_difference"]), row["symbol"]))
    rho = agreement["spearman"]
    level = None if rho is None else next((name for floor, name in PARITY_LEVELS if rho >= floor), "different")
    return {
        "agreement": level,
        "companies": {"live": int(live_scores.notna().sum()), "historical": int(past_scores.notna().sum()),
                      "universe": len(common), "both_scored": int(scored.sum())},
        "spearman": agreement["spearman"], "top_n": top_n, "top_overlap": agreement["top_overlap"],
        "only_live_top": agreement["leaving"], "only_historical_top": agreement["entering"],
        "blocks": {block: _spearman(live.get(f"{block}_score", pd.Series(dtype=float)).reindex(common),
                                    historical.get(f"{block}_score", pd.Series(dtype=float)).reindex(common))
                   for block in score_metrics},
        "metrics": metrics,
        "largest_differences": [row for row in moves if row["rank_change"]][:LARGEST],
    }
