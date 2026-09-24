import pandas as pd

from gabi.historical_price_audit import assess_series, choose_source, overlap_status


def _frame(values, dates):
    return pd.DataFrame({"close": values, "adj_close": values}, index=pd.to_datetime(dates))


def test_sessions_are_not_forward_filled_and_split_adjustments_can_match():
    sessions = pd.bdate_range("2012-01-02", periods=4)
    frame = _frame([100, 50, 51], sessions[[0, 2, 3]])
    result = assess_series(frame, sessions)
    assert result == {"sessions": 3, "first": "2012-01-02", "last": "2012-01-05", "complete": False}
    assert choose_source("confirmed_by_multiple_evidence", False, result, result, "consistent_overlap") == (
        None, "incomplete_prices")


def test_adjusted_returns_detect_divergent_dividend_or_split():
    dates = pd.bdate_range("2012-01-02", periods=80)
    yahoo = _frame([100 + i for i in range(80)], dates)
    same_returns = yahoo * 2  # different level, same total-return sequence
    assert overlap_status(yahoo, same_returns)[0] == "consistent_overlap"
    bad = same_returns.copy()
    bad.iloc[40:, bad.columns.get_loc("adj_close")] *= 0.5
    assert overlap_status(yahoo, bad)[0] == "divergent_overlap"


def test_split_in_nominal_close_does_not_break_matching_adjusted_returns():
    dates = pd.bdate_range("2012-01-02", periods=80)
    adjusted = pd.Series([100 + i for i in range(80)], index=dates, dtype=float)
    yahoo = pd.DataFrame({"close": adjusted.where(adjusted.index < dates[40], adjusted / 2),
                          "adj_close": adjusted}, index=dates)
    archive = pd.DataFrame({"close": adjusted, "adj_close": adjusted * 0.25}, index=dates)
    assert overlap_status(yahoo, archive)[0] == "consistent_overlap"


def test_no_unverified_archive_fallback_or_recycled_ticker():
    complete = {"complete": True, "first": "2012-01-02", "last": "2012-12-31"}
    missing = {"complete": False, "first": "2012-01-02", "last": "2012-12-31"}
    assert choose_source("corroborated_candidate", False, missing, complete,
                         "insufficient_overlap") == (None, "archive_adjustment_unverified")
    assert choose_source("confirmed_by_multiple_evidence", False, missing, complete,
                         "consistent_overlap") == ("finsaber", "fallback_consistent_overlap")
    assert choose_source("confirmed_by_multiple_evidence", True, complete, complete,
                         "consistent_overlap") == (None, "ticker_recycled")
    assert choose_source(None, False, complete, complete,
                         "consistent_overlap") == (None, "identity_unresolved")


def test_archive_must_not_extend_a_post_ipo_or_merger_series():
    yahoo = {"complete": False, "first": "2013-01-02", "last": "2013-12-31"}
    archive = {"complete": True, "first": "2012-12-31", "last": "2013-12-31"}
    assert choose_source("confirmed_by_multiple_evidence", False, yahoo, archive,
                         "consistent_overlap") == (None, "archive_boundary_unverified")
