"""When a page keeps the full data notice instead of the compact chip (#187)."""

from datetime import date, datetime

import pandas as pd

from gabi.application.market.queries import RankingSnapshot, describe_data

SESSION = date(2026, 10, 2)


def _snapshot(rows: int, scored: int, price_date: str = "2026-10-02") -> RankingSnapshot:
    symbols = [f"T{index:03d}" for index in range(rows)]
    table = pd.DataFrame({"composite_score": [50.0] * scored + [None] * (rows - scored)}, index=symbols)
    table.attrs["sources"] = {symbol: {"price_date": price_date, "fundamentals_fetched_at": "2026-10-02T08:00:00",
                                       "sec_fetched_at": "2026-10-02T08:00:00"} for symbol in symbols}
    return RankingSnapshot(table, {}, "r", datetime(2026, 10, 2, 8), None)


def test_data_needs_attention_only_when_degraded_stale_behind_or_short():
    today = date(2026, 10, 3)
    assert not describe_data(_snapshot(100, 99), today, SESSION).needs_attention  # 1 % unscored: the chip.
    assert describe_data(_snapshot(100, 90), today, SESSION).needs_attention  # 10 % unscored.
    assert describe_data(_snapshot(20, 20, "2026-09-20"), today).needs_attention  # stale prices
    assert describe_data(_snapshot(20, 20, "2026-10-01"), today, SESSION).needs_attention  # last close missing
