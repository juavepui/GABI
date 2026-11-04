"""«Datos imposibles o sospechosos» (#295): every mark of ``input-checks-v1`` over the cached universe.

Reads the local cache only. Whether a mark stops a value from scoring depends on the
model version: only a version declared with ``input_checks`` scores it as missing.
"""

from collections import Counter
from collections.abc import Callable

import pandas as pd

from gabi.domain.market import input_checks as checks

VERSION = "input-checks-report-v1"
MAX_LISTED = 300
BATCH = 50


def _last_close(frame: pd.DataFrame | None) -> float | None:
    if frame is None or frame.empty or "close" not in frame:
        return None
    closes = frame["close"].dropna()
    closes = closes[closes > 0]
    return float(closes.iloc[-1]) if len(closes) else None


def report(*, universe: Callable[[], list[str]], fundamentals: Callable[[list[str]], dict],
           compute: Callable[[dict], dict], closes: Callable[[list[str]], dict[str, pd.DataFrame]],
           splits: Callable[[list[str]], dict[str, list[str]]], shares: Callable[[str], float | None],
           model_id: str, applied: bool, progress: Callable[[float, str], None] = lambda share, phase: None) -> dict:
    symbols = universe()
    marks: list[dict] = []
    for start in range(0, len(symbols), BATCH):
        chunk = symbols[start:start + BATCH]
        records, prices, split_days = fundamentals(chunk), closes(chunk), splits(chunk)
        for symbol in chunk:
            record = records.get(symbol)
            metrics = compute(record) if record else {}
            found = checks.check_fields(metrics) + checks.check_jumps(prices.get(symbol), split_days.get(symbol))
            cap = checks.check_market_cap(metrics.get("market_cap"), _last_close(prices.get(symbol)), shares(symbol))
            found += [cap] if cap else []
            marks += [{"symbol": symbol, **mark} for mark in found]
        progress(min(start + BATCH, len(symbols)) / max(len(symbols), 1) * 0.95, "Comprobando datos")
    by_rule = Counter(mark["rule"] for mark in marks)
    by_field = Counter(mark["field"] for mark in marks if mark["rule"] == "range")
    return {"version": VERSION, "policy": checks.VERSION, "model_id": model_id, "applied": applied,
            "companies": len(symbols), "affected": len({mark["symbol"] for mark in marks}),
            "by_rule": dict(by_rule), "by_field": dict(by_field.most_common()),
            "blocks": list(checks.BLOCKS),
            "ranges": {field: list(bounds) for field, bounds in checks.RANGES.items()},
            "jump_threshold": checks.JUMP, "market_cap_tolerance": checks.MARKET_CAP_TOLERANCE,
            "marks": marks[:MAX_LISTED], "total_marks": len(marks)}
