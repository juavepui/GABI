"""Historical identity coverage and the rules of an explicit legacy attribution.

No row is attributed from today's ticker map: coverage separates lexical candidates
from date-valid reviewed aliases, and an attribution needs evidence and a valid window.
"""
from collections.abc import Callable
from datetime import date

import pandas as pd

ATTRIBUTABLE = {"prices", "splits", "fundamentals", "edgar_facts"}


def check_attribution(dataset: str, source: str, start: str | None, end: str | None) -> None:
    if dataset not in ATTRIBUTABLE:
        raise ValueError("Unsupported legacy dataset")
    if not source.strip():
        raise ValueError("Attribution evidence is required")
    if start:
        date.fromisoformat(start)
    if end:
        date.fromisoformat(end)
    if start and end and end <= start:
        raise ValueError("Invalid attribution interval")


def attribution_rows(frame: pd.DataFrame, dataset: str, start: str | None, end: str | None) -> list[dict]:
    """Rows of one symbol inside [start, end), by trading, filing or fetch date; missing values become None."""
    column = "date" if dataset in {"prices", "splits"} else "filed_date" if dataset == "edgar_facts" else "fetched_at"
    if start:
        frame = frame[frame[column] >= start]
    if end:
        frame = frame[frame[column] < end]
    return frame.astype(object).where(frame.notna(), None).to_dict("records")


def coverage(history: pd.DataFrame, current_map: pd.DataFrame, aliases: pd.DataFrame,
             normalize: Callable[[str], str], min_confidence: float) -> dict:
    """Compare lexical legacy lookup with reviewed date-valid identity (different guarantees).

    Count distinct symbol/date membership observations, not duplicate daily rows.
    Also report distinct symbols with any mapping so the legacy ~16% hypothesis
    can be checked against an explicitly stated denominator.
    """
    mapping = {normalize(s) for s in current_map["symbol"] if isinstance(s, str) and s.strip()}
    pairs = {(str(row.date), normalize(s)) for row in history.itertuples()
             for s in str(row.tickers).split(",") if s.strip()}
    symbols = {symbol for _, symbol in pairs}
    by_symbol = {s: group.to_dict("records") for s, group in aliases.groupby("symbol")}
    resolved = ambiguous = 0
    newly_resolved_symbols = set()
    for day, symbol in pairs:
        matches = [r for r in by_symbol.get(symbol, [])
                   if r["valid_from"] <= day and (pd.isna(r["valid_to"]) or day < r["valid_to"])]
        owners = {r["entity_id"] for r in matches}
        if len(owners) > 1:
            ambiguous += 1
        elif len(owners) == 1 and max(r["confidence"] for r in matches) >= min_confidence:
            resolved += 1
            newly_resolved_symbols.add(symbol)
    legacy_unresolved = symbols - mapping
    augmented = legacy_unresolved - newly_resolved_symbols
    return {
        "history_start": str(history["date"].min()), "history_end": str(history["date"].max()),
        "distinct_symbols": len(symbols), "symbol_date_pairs": len(pairs),
        "before_unmapped_symbols": len(legacy_unresolved),
        "before_unmapped_pct": 100 * len(legacy_unresolved) / len(symbols) if symbols else 0,
        "after_unmapped_symbols": len(augmented),
        "after_unmapped_pct": 100 * len(augmented) / len(symbols) if symbols else 0,
        "recovered_symbols": sorted(legacy_unresolved - augmented),
        "verified_symbol_date_pairs": resolved, "ambiguous_symbol_date_pairs": ambiguous,
        "unverified_symbol_date_pct": 100 * (len(pairs) - resolved) / len(pairs) if pairs else 0,
        "warning": "Current-map matches are candidates, NOT verified historical identity or usable data coverage.",
    }
