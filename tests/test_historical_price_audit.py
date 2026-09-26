import pandas as pd

from gabi.historical_issuer_evidence import listing_checks
from gabi.historical_price_audit import (
    archive_adjustment,
    assess_series,
    choose_source,
    overlap_status,
    same_traded_prices,
)

COMPLETE = {"complete": True, "first": "2012-01-03", "last": "2012-12-31"}
MISSING = {"complete": False, "first": "2012-01-03", "last": "2012-12-31"}
PASSING = {"listing": None, "yahoo_level": "passed", "archive_level": "passed",
           "archive_adjustment": "dividends_reconciled"}
PROOF = {"first_trade": "2001-03-01", "last_trade": "2014-02-01",
         "boundary_evidence": [{"kind": "first_trade"}, {"kind": "last_trade"}],
         "adjustment_basis": "split_and_dividend_adjusted",
         "adjustment_evidence": [{"kind": "adjustment"}],
         "corporate_action_evidence": [{"kind": "corporate_actions"}]}


def _frame(values, dates):
    return pd.DataFrame({"close": values, "adj_close": values}, index=pd.to_datetime(dates))


def test_sessions_are_not_forward_filled_and_split_adjustments_can_match():
    sessions = pd.bdate_range("2012-01-02", periods=4)
    frame = _frame([100, 50, 51], sessions[[0, 2, 3]])
    result = assess_series(frame, sessions)
    assert result == {"sessions": 3, "first": "2012-01-02", "last": "2012-01-05", "complete": False,
                      "complete_from_first": False}
    assert choose_source("confirmed_by_multiple_evidence", False, result, result, "consistent_overlap",
                         issuer=PASSING) == (None, "incomplete_prices")
    late = assess_series(frame.iloc[1:], sessions)
    assert late["complete_from_first"] is True and late["first"] == "2012-01-04"


def test_adjusted_returns_detect_divergent_dividend_or_split():
    dates = pd.bdate_range("2012-01-02", periods=80)
    yahoo = _frame([100 + i for i in range(80)], dates)
    same_returns = yahoo * 2  # different level, same total-return sequence
    assert overlap_status(yahoo, same_returns)[0] == "consistent_overlap"
    bad = same_returns.copy()
    bad.iloc[40:, bad.columns.get_loc("adj_close")] *= 0.5
    assert overlap_status(yahoo, bad)[0] == "divergent_overlap"


def test_single_unadjusted_spin_off_day_is_divergent_even_if_p99_matches():
    dates = pd.bdate_range("2012-01-02", periods=300)
    yahoo = _frame([100 + i * 0.1 for i in range(300)], dates)
    archive = yahoo.copy()
    # One source leaves a 30% spin-off distribution unadjusted on one day.
    archive.iloc[150:, archive.columns.get_loc("adj_close")] *= 0.7
    status, count, p99 = overlap_status(yahoo, archive)
    assert p99 is not None and p99 <= 0.005
    assert status == "divergent_event"
    # Yahoo is complete, but a disagreeing archive blocks it (recycled symbol
    # or unreconciled corporate action: it is unknown which source is right).
    assert choose_source("confirmed_by_multiple_evidence", False, COMPLETE, COMPLETE, status,
                         issuer=PASSING) == (None, "sources_divergent_event")


def test_split_in_nominal_close_does_not_break_matching_adjusted_returns():
    dates = pd.bdate_range("2012-01-02", periods=80)
    adjusted = pd.Series([100 + i for i in range(80)], index=dates, dtype=float)
    yahoo = pd.DataFrame({"close": adjusted.where(adjusted.index < dates[40], adjusted / 2),
                          "adj_close": adjusted}, index=dates)
    archive = pd.DataFrame({"close": adjusted, "adj_close": adjusted * 0.25}, index=dates)
    assert overlap_status(yahoo, archive)[0] == "consistent_overlap"


def test_selection_requires_identity_issuer_evidence_and_no_recycling():
    assert choose_source("confirmed_by_multiple_evidence", True, COMPLETE, COMPLETE,
                         "consistent_overlap", issuer=PASSING) == (None, "multiple_ciks_in_window")
    assert choose_source(None, False, COMPLETE, COMPLETE,
                         "consistent_overlap", issuer=PASSING) == (None, "identity_unresolved")
    assert choose_source("corroborated_candidate", False, COMPLETE, COMPLETE,
                         "consistent_overlap") == (None, "issuer_evidence_missing")
    assert choose_source("corroborated_candidate", False, COMPLETE, COMPLETE,
                         "consistent_overlap", issuer=PASSING) == ("yahoo", "complete")
    failed_level = {**PASSING, "yahoo_level": "failed", "archive_level": "failed"}
    assert choose_source("corroborated_candidate", False, COMPLETE, MISSING,
                         "insufficient_overlap", issuer=failed_level) == (None, "price_level_failed")


def test_pre_ipo_or_spin_off_archive_window_is_rejected():
    # ABBV/KHC/QRVO-like: the archive has a full window but the CIK only starts
    # filing periodic reports afterwards, or a succession happens inside it.
    life = {"first_periodic": "2013-02-20", "last_periodic": "2026-01-01", "successions": [],
            "delisting": None, "source_url": "https://data.sec.gov/submissions/CIK0000000001.json"}
    reason, refs = listing_checks(life, "2012-12-28", "2013-12-31")
    assert reason == "listing_starts_after_window"
    issuer = {**PASSING, "listing": reason}
    assert choose_source("confirmed_by_multiple_evidence", False, MISSING, COMPLETE,
                         "insufficient_overlap", issuer=issuer, fallback_proof=PROOF) == (
        None, "listing_starts_after_window")
    successor = {**life, "first_periodic": "2001-01-01",
                 "successions": [{"form": "8-K12B", "filed": "2013-06-03", "accession": "x"}]}
    assert listing_checks(successor, "2012-12-28", "2013-12-31")[0] == "succession_inside_window"
    delisted = {**life, "first_periodic": "2001-01-01",
                "delisting": {"form": "25-NSE", "filed": "2013-07-18", "accession": "y",
                              "basis": "filing_silence"}}
    assert listing_checks(delisted, "2012-12-28", "2013-12-31")[0] == "delisted_before_window_end"


def test_fallback_without_yahoo_overlap_is_accepted_only_with_sec_evidence():
    assert choose_source("confirmed_by_multiple_evidence", False, MISSING, COMPLETE,
                         "insufficient_overlap", issuer=PASSING, fallback_proof=PROOF) == (
        "finsaber", "fallback_accredited")
    for key, value, reason in [("archive_level", "missing", "price_level_missing"),
                               ("archive_adjustment", "dividend_mismatch", "archive_dividend_mismatch"),
                               ("archive_adjustment", "split_unverified", "archive_split_unverified")]:
        assert choose_source("confirmed_by_multiple_evidence", False, MISSING, COMPLETE,
                             "insufficient_overlap", issuer={**PASSING, key: value},
                             fallback_proof=PROOF) == (None, reason)
    assert choose_source("confirmed_by_multiple_evidence", False, MISSING, COMPLETE,
                         "divergent_overlap", issuer=PASSING, fallback_proof=PROOF) == (
        None, "sources_divergent_overlap")


def test_archive_adjustment_blocks_unexplained_distribution_and_unverified_split():
    sessions = pd.bdate_range("2012-01-02", periods=60)
    close = pd.Series(50.0, index=sessions)
    adjusted = close.copy()
    frame = pd.DataFrame({"close": close, "adj_close": adjusted})
    facts = {"public_float": [], "cover_shares": [], "weighted_shares": [],
             "dividends_declared": [{"start": "2011-12-01", "end": "2012-02-29", "val": 0.0}],
             "dividends_paid": []}
    status, _ = archive_adjustment(frame, facts, "2012-01-02", "2012-03-23", frame.iloc[0:0], sessions)
    assert status == "no_dividends_consistent"
    # A spin-off left in the archive: a 40% one-day drop both in close and adj.
    spun = frame.copy()
    spun.iloc[30:] *= 0.6
    assert archive_adjustment(spun, facts, "2012-01-02", "2012-03-23", frame.iloc[0:0], sessions)[0] == \
        "unexplained_jump"
    # A 2:1 split without SEC share-count evidence is not accepted.
    split = frame.copy()
    split.iloc[30:, split.columns.get_loc("close")] = 25.0
    assert archive_adjustment(split, facts, "2012-01-02", "2012-03-23", frame.iloc[0:0], sessions)[0] == \
        "split_unverified"


def test_divergence_is_resolved_by_sec_only_when_both_sources_quote_the_same_prices():
    # APD/KMB-like: identical traded prices, the archive lacks dividend adjustments.
    issuer = {**PASSING, "yahoo_adjustment": "dividends_reconciled", "archive_adjustment": "dividend_mismatch",
              "same_traded_prices": True}
    assert choose_source("confirmed_by_multiple_evidence", False, COMPLETE, COMPLETE, "divergent_overlap",
                         issuer=issuer) == ("yahoo", "complete_divergence_resolved_by_sec")
    # BBT-like: Yahoo's recycled symbol quotes another security; never resolved.
    assert choose_source("confirmed_by_multiple_evidence", False, COMPLETE, COMPLETE, "divergent_overlap",
                         issuer={**issuer, "same_traded_prices": False}) == (None, "sources_divergent_overlap")
    dates = pd.bdate_range("2012-01-02", periods=80)
    prices = _frame([100 + i for i in range(80)], dates)
    assert same_traded_prices(prices, prices, dates) is True
    assert same_traded_prices(prices, _frame([60 + (i % 7) for i in range(80)], dates), dates) is False


def test_holding_period_is_verified_on_the_same_source_until_the_next_rebalance():
    import exchange_calendars as xcals

    from gabi.historical_price_audit import forward_coverage
    calendar = xcals.get_calendar("XNYS", start="2012-01-01", end="2012-12-31")
    sessions = calendar.sessions[(calendar.sessions >= "2012-01-03") & (calendar.sessions <= "2012-07-31")]
    series = pd.DataFrame({"close": 10.0, "adj_close": 9.0}, index=sessions)
    life = {"delisting": None, "successions": []}
    assert forward_coverage(series, calendar, "2012-03-30", "2012-06-30", life, archive=False) == (
        "2012-07-06", "covered")
    # Trading stops at an SEC delisting: the end is terminal, not a gap.
    stopped = series.loc[:"2012-05-10"]
    delisted = {"delisting": {"filed": "2012-05-14"}, "successions": []}
    assert forward_coverage(stopped, calendar, "2012-03-30", "2012-06-30", delisted, archive=False) == (
        "2012-05-10", "terminal")
    gap = series.drop(pd.Timestamp("2012-05-01"))
    assert forward_coverage(gap, calendar, "2012-03-30", "2012-06-30", life, archive=False) == (
        "2012-04-30", "gap")
    # The label passes to another CIK: never extend this issuer's holding past it.
    assert forward_coverage(series, calendar, "2012-03-30", "2012-06-30", life, archive=False,
                            identity_end="2012-05-15") == ("2012-05-14", "identity_boundary")
