from datetime import UTC, date, datetime

from gabi.domain.market.freshness import last_completed_session, prices_current

SESSION = date(2026, 10, 2)


def test_prices_current_tolerates_five_percent_of_the_universe_behind():
    assert prices_current([SESSION] * 20, SESSION)
    assert prices_current([SESSION] * 19 + [date(2026, 9, 30)], SESSION)  # 1 of 20 = 5 %
    assert not prices_current([SESSION] * 9 + [date(2026, 9, 30)], SESSION)  # 1 of 10
    assert not prices_current([date(2026, 9, 30)] * 20, SESSION)


def test_a_missing_price_counts_as_behind_and_an_empty_universe_is_not_current():
    assert not prices_current([SESSION] * 9 + [None], SESSION)
    assert not prices_current([], SESSION)


def test_last_completed_session_waits_for_the_close():
    assert last_completed_session(datetime(2026, 10, 2, 15, tzinfo=UTC)) == date(2026, 10, 1)
    assert last_completed_session(datetime(2026, 10, 2, 21, tzinfo=UTC)) == SESSION
    assert last_completed_session(datetime(2026, 10, 3, 12, tzinfo=UTC)) == SESSION  # Saturday
