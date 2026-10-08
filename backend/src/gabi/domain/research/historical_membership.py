"""Dated snapshots and half-open composition intervals, without I/O."""
from bisect import bisect_right
from datetime import date

import pandas as pd

from gabi.domain.market import identity
from gabi.domain.research.ticker_corrections import WLP_END, correct_symbols


def _members(value: str) -> set[str]:
    result = {identity.normalize_symbol(symbol) for symbol in value.split(",") if symbol.strip()}
    if not result:
        raise ValueError("Empty historical membership snapshot")
    return result


def _snapshots(frame: pd.DataFrame) -> list[tuple[str, set[str]]]:
    rows = [(date.fromisoformat(str(row.date)).isoformat(), _members(str(row.tickers)))
            for row in frame.itertuples(index=False)]
    rows.sort(key=lambda row: row[0])
    by_date: dict[str, set[str]] = {}
    for day, symbols in rows:
        if day in by_date and by_date[day] != symbols:
            raise ValueError(f"Conflicting historical membership snapshots on {day}")
        by_date[day] = symbols
    return list(by_date.items())


def _segment(frame: pd.DataFrame, as_of: str, end_exclusive: str) -> tuple[pd.DataFrame, str, str]:
    """Conflicting same-day snapshots make coverage unknown until the next clean row."""
    grouped = frame.groupby("date", sort=True)["tickers"].apply(lambda values: {
        frozenset(_members(value)) for value in values})
    conflicts = sorted(day for day, variants in grouped.items() if len(variants) > 1)
    if as_of in conflicts:
        raise ValueError(f"Conflicting historical membership snapshots on {as_of}")
    before = [day for day in conflicts if day < as_of]
    after = [day for day in conflicts if day > as_of]
    last = before[-1] if before else None
    upcoming = after[0] if after else None
    selected = frame[frame["date"] > last] if last else frame
    if upcoming:
        selected = selected[selected["date"] < upcoming]
    boundary = min(end_exclusive, upcoming) if upcoming else end_exclusive
    return selected, boundary, "source_gap" if upcoming else "source_boundary"


def intervals(frame: pd.DataFrame, end_exclusive: str, *, boundary_reason: str = "source_boundary") -> list[dict]:
    """Turn snapshots into half-open intervals, retaining exits and reentries.

    A terminal interval ends at the source boundary, *not* an inferred exit.
    """
    boundary = date.fromisoformat(end_exclusive).isoformat()
    rows = _snapshots(frame)
    if not rows or rows[-1][0] >= boundary:
        raise ValueError("Snapshots must precede the source coverage boundary")
    active: dict[str, str] = {}
    result = []
    for day, members in rows:
        for symbol in sorted(active.keys() - members):
            result.append({"symbol": symbol, "valid_from": active.pop(symbol),
                           "valid_to": day, "end_reason": "exit"})
        for symbol in members - active.keys():
            active[symbol] = day
    result.extend({"symbol": symbol, "valid_from": start, "valid_to": boundary,
                   "end_reason": boundary_reason} for symbol, start in active.items())
    return sorted(result, key=lambda row: (row["symbol"], row["valid_from"]))


def composition_at(frame: pd.DataFrame, day: str, end: str, source_id: str):
    source_end = end
    frame, end, boundary_reason = _segment(frame, day, end)
    rows = _snapshots(frame)
    dates = [item[0] for item in rows]
    index = bisect_right(dates, day) - 1
    if index < 0 or day >= end:
        first = dates[0] if dates else "none"
        raise ValueError(f"Date {day} outside {source_id} coverage [{first}, {end})")
    source_date, reported_symbols = rows[index]
    symbols, corrections = correct_symbols(reported_symbols, day)
    active_intervals = {row["symbol"]: row for row in intervals(frame, end, boundary_reason=boundary_reason)
                        if row["valid_from"] <= day < row["valid_to"]}
    corrected_intervals = {}
    for symbol in symbols:
        raw_symbol = "ANTM" if corrections and symbol == "WLP" else symbol
        interval = {**active_intervals[raw_symbol], "symbol": symbol}
        if corrections and symbol == "WLP":
            change = corrections[0]
            interval["valid_from"] = max(interval["valid_from"], change["valid_from"])
            if change["valid_to"] <= interval["valid_to"]:
                interval["valid_to"] = change["valid_to"]
                interval["end_reason"] = "ticker_change"
        elif symbol == "ANTM" and day >= WLP_END:
            interval["valid_from"] = max(interval["valid_from"], WLP_END)
        corrected_intervals[symbol] = interval
    return source_end, end, dates, source_date, symbols, corrections, corrected_intervals


def compare_compositions(primary, primary_end, reference, reference_end, start, end_exclusive,
                         digest, operational_source, reference_source):
    primary_conflicts = sorted(day for day, values in primary.groupby("date")["tickers"]
                               if len({frozenset(_members(value)) for value in values}) > 1)
    equivalent_duplicates = sorted(day for day, values in primary.groupby("date")["tickers"]
                                   if len(values) > 1 and len({frozenset(_members(value)) for value in values}) == 1)
    primary = primary[(primary["date"] < end_exclusive) & (primary["date"] < reference_end)]
    reference = reference[(reference["date"] < end_exclusive) & (reference["date"] < primary_end)]
    left, right = _snapshots(primary), _snapshots(reference)
    left_dates, right_dates = [row[0] for row in left], [row[0] for row in right]
    dates = sorted({day for day in left_dates + right_dates
                    if start <= day < min(end_exclusive, primary_end, reference_end)})
    by_year: dict[str, dict] = {}
    for day in dates:
        li, ri = bisect_right(left_dates, day) - 1, bisect_right(right_dates, day) - 1
        if li < 0 or ri < 0:
            continue
        diff = len(left[li][1] ^ right[ri][1])
        item = by_year.setdefault(day[:4], {"checkpoints": 0, "disagree_checkpoints": 0,
                                             "difference_sum": 0, "max_difference": 0})
        item["checkpoints"] += 1
        item["disagree_checkpoints"] += diff > 0
        item["difference_sum"] += diff
        item["max_difference"] = max(item["max_difference"], diff)
    for item in by_year.values():
        item["mean_difference"] = round(item.pop("difference_sum") / item["checkpoints"], 2)
    return {"primary_source_id": operational_source, "primary_cache_sha256": digest,
            "primary_coverage": [left_dates[0], primary_end],
            "primary_conflict_dates": primary_conflicts,
            "primary_equivalent_duplicate_dates": equivalent_duplicates,
            "reference_source_id": reference_source,
            "reference_coverage": [right_dates[0], reference_end],
            "comparison_window": [start, end_exclusive], "by_year": by_year}
