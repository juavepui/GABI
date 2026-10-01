"""Canonical hashing accepts the values a real ranking row carries."""

from datetime import UTC, date, datetime

from gabi.domain.research.live_ledger import canonical, fingerprint


def test_dates_in_ranking_rows_are_canonical_iso_strings():
    row = {"symbol": "AAA", "next_earnings_date": date(2026, 10, 28),
           "fetched_at": datetime(2026, 10, 1, 9, 30, tzinfo=UTC), "score": float("nan")}
    assert canonical(row) == ('{"fetched_at":"2026-10-01T09:30:00+00:00","next_earnings_date":"2026-10-28",'
                              '"score":null,"symbol":"AAA"}')
    assert fingerprint(row) == fingerprint({**row, "next_earnings_date": "2026-10-28"})
