import json

import pandas as pd
import pytest

from gabi import historical_issuer_evidence as evidence


def _facts(**kinds):
    return {kind: kinds.get(kind, []) for kind in evidence.FRAME_SPECS}


def _float(end, value):
    return {"end": end, "val": value, "accn": "a", "source_url": "https://data.sec.gov/api/xbrl/frames/x"}


def _shares(end, value, start=None):
    return {"start": start, "end": end, "val": value, "accn": "b", "source_url": "https://data.sec.gov/api/xbrl/frames/y"}


def test_level_classification_separates_unit_errors_from_wrong_prices():
    assert evidence.classify_level(0.9) == "passed"
    assert evidence.classify_level(0.9e6) == "inconclusive"  # XBRL scale error
    assert evidence.classify_level(0.9 / 7, restated_shares=True) == "inconclusive"  # restated 7:1 split
    assert evidence.classify_level(0.9 / 7) == "failed"  # cover counts are never restated
    assert evidence.classify_level(2.3) == "failed"  # another security's price level
    assert evidence.level_status([{"outcome": "passed"}, {"outcome": "inconclusive"}]) == "passed"
    assert evidence.level_status([{"outcome": "passed"}, {"outcome": "failed"}]) == "failed"
    assert evidence.level_status([{"outcome": "inconclusive"}]) == "missing"


def test_price_level_uses_unrestated_cover_shares_and_as_traded_close():
    facts = _facts(public_float=[_float("2012-06-29", 9e9)],
                   cover_shares=[_shares("2012-08-01", 100e6)],
                   weighted_shares=[_shares("2012-06-30", 700e6, start="2012-04-01")])
    close = pd.Series([100.0, 100.0], index=pd.to_datetime(["2012-06-28", "2012-06-29"]))
    [check] = evidence.price_level_checks(facts, close, "2012-01-03", "2012-12-31")
    assert check["shares_kind"] == "cover_shares" and check["outcome"] == "passed"
    # A 10:1 split between the float date and the cover date is undone exactly.
    split_cover = _facts(public_float=[_float("2012-06-29", 9e9)], cover_shares=[_shares("2012-08-01", 1e9)])
    assert evidence.price_level_checks(split_cover, close, "2012-01-03", "2012-12-31")[0]["outcome"] == "failed"
    assert evidence.price_level_checks(split_cover, close, "2012-01-03", "2012-12-31", splits=pd.Series(
        [10.0], index=pd.to_datetime(["2012-07-10"])))[0]["outcome"] == "passed"
    wrong_security = close * 0.4
    assert evidence.price_level_checks(facts, wrong_security, "2012-01-03", "2012-12-31")[0]["outcome"] == "failed"
    # A float dated after the window only counts up to the given horizon.
    assert evidence.price_level_checks(facts, close, "2011-01-03", "2011-12-30") == []
    assert len(evidence.price_level_checks(facts, close, "2011-01-03", "2011-12-30", until="2012-12-31")) == 1


@pytest.fixture
def submissions(tmp_path, monkeypatch):
    monkeypatch.setattr(evidence, "SUBMISSIONS_DIR", tmp_path)
    monkeypatch.setattr(evidence, "issuer_facts", lambda cik: _facts(
        public_float=[_float("2011-06-30", 1e9), _float("2012-06-29", 1e9)] +
        ([_float("2013-06-28", 1e9)] if cik == "1" else [])))
    evidence.listing_life.cache_clear()

    def write(cik, filings, name="Issuer Inc"):
        forms, dates, accessions = zip(*filings, strict=True)
        payload = {"cik": cik, "name": name, "tickers": ["NEW"], "formerNames": [],
                   "filings": {"recent": {"form": list(forms), "filingDate": list(dates),
                                          "accessionNumber": list(accessions),
                                          "items": [""] * len(forms),
                                          "primaryDocument": ["doc.htm"] * len(forms)},
                               "files": []}}
        (tmp_path / f"CIK{int(cik):010d}.json").write_text(json.dumps(payload), encoding="utf-8")
        evidence.listing_life.cache_clear()
    yield write
    evidence.listing_life.cache_clear()


def test_listing_life_separates_real_delisting_from_debt_delisting_or_transfer(submissions):
    submissions("1", [("10-K", "2005-03-01", "a1"), ("10-Q", "2012-05-01", "a2"),
                      ("25-NSE", "2012-06-01", "a3"), ("10-Q", "2012-08-01", "a4"),
                      ("25-NSE", "2013-07-18", "a5"), ("15-12B", "2013-07-29", "a6")])
    life = evidence.listing_life("1")
    assert life["first_periodic"] == "2005-03-01"
    # The 2012 Form 25 is followed by more reports and a later float: not the equity.
    assert life["delisting"]["filed"] == "2013-07-18"
    assert evidence.listing_checks(life, "2012-07-02", "2013-06-28")[0] is None
    assert evidence.listing_checks(life, "2012-08-01", "2013-07-31")[0] == "delisted_before_window_end"


def test_debt_registrant_after_buyout_is_delisted_by_missing_float(submissions):
    submissions("2", [("10-K", "2005-03-01", "b1"), ("25-NSE", "2013-06-12", "b2"),
                      ("10-Q", "2013-08-01", "b3"), ("10-K", "2014-02-28", "b4")])
    life = evidence.listing_life("2")
    assert life["delisting"]["basis"] == "no_later_public_float"
    assert evidence.level_horizon(life, "2012-12-31") == "2013-06-11"


def test_listing_start_needs_sec_registration_just_before_first_session(submissions):
    submissions("3", [("10-12B", "2012-11-15", "c1"), ("10-Q", "2013-05-01", "c2")])
    life = evidence.listing_life("3")
    assert evidence.listing_start(life, "2013-01-02")["form"] == "10-12B"
    assert evidence.listing_start(life, "2014-01-02") is None
    assert evidence.listing_checks(life, "2012-12-28", "2013-12-31")[0] == "listing_starts_after_window"


def _series(close, adjusted, start="2012-01-03"):
    index = pd.bdate_range(start, periods=len(close))
    return pd.DataFrame({"close": close, "adj_close": adjusted}, index=index)


def test_implied_events_split_dividend_and_unexplained_distribution():
    close = [100.0, 100.0, 50.0, 50.0, 49.5, 49.5, 30.0]
    # Adjusted closes apply each later event backwards: a 2:1 split on day 2,
    # a 0.50 cash dividend on day 4 and a 40% distribution on day 6.
    split, dividend, spin_off = 0.5, 1 - 0.5 / 50.0, 30.0 / 49.5
    factors = [split * dividend * spin_off] * 2 + [dividend * spin_off] * 2 + [spin_off] * 2 + [1.0]
    frame = _series(close, [price * factor for price, factor in zip(close, factors, strict=True)])
    events = evidence.implied_events(frame)
    assert list(events.kind) == ["split", "dividend", "unexplained"]
    assert events.iloc[0].ratio == 2
    assert events.iloc[1].amount == pytest.approx(0.5, rel=0.02)
    facts = _facts(cover_shares=[_shares("2011-12-31", 100e6), _shares("2012-02-15", 201e6)])
    assert evidence.verify_splits(events, facts)[0] is True
    assert evidence.verify_splits(events, _facts())[0] is False


def test_dividend_reconciliation_detects_archive_without_dividends():
    quarters = [("2012-01-01", "2012-03-31"), ("2012-04-01", "2012-06-30"),
                ("2012-07-01", "2012-09-30"), ("2012-10-01", "2012-12-31")]
    facts = _facts(dividends_declared=[_shares(end, 0.64, start=start) for start, end in quarters])
    paid = pd.DataFrame({"date": pd.to_datetime(["2012-03-29", "2012-06-28", "2012-09-27", "2012-12-28"]),
                         "kind": "dividend", "ratio": None, "amount": 0.64, "factor": 1.007})
    status, detail = evidence.reconcile_dividends(paid, facts, "2012-01-03", "2012-12-31")
    assert status == "dividends_reconciled" and detail["fingerprint"] is True
    none = paid.iloc[0:0]
    assert evidence.reconcile_dividends(none, facts, "2012-01-03", "2012-12-31")[0] == "dividend_mismatch"
    annual_only = _facts(dividends_paid=[_shares("2012-12-31", 2.56, start="2012-01-01")])
    assert evidence.reconcile_dividends(paid, annual_only, "2012-01-03", "2012-12-31")[0] == "dividends_reconciled"
    xbrl_non_payer = _facts(public_float=[_float("2012-06-29", 1e9)])
    assert evidence.reconcile_dividends(none, xbrl_non_payer, "2012-01-03", "2012-12-31")[0] == \
        "no_dividends_consistent"
    assert evidence.reconcile_dividends(none, _facts(), "2012-01-03", "2012-12-31")[0] == \
        "sec_dividends_unavailable"


@pytest.mark.parametrize(("text", "items", "expected"), [
    ("each share was converted into the right to receive $72.50 in cash, without interest", {"2.01"},
     ("cash_acquisition", "terminal_return_confirmed", 72.5)),
    ("the right to receive 0.2240 of a share of Acme Corp. common stock and $10.00 in cash", {"2.01"},
     ("merger", "terminal_return_unknown", None)),
    ("the right to receive 1.0 validly issued, fully paid and nonassessable share of Foo Inc. common stock",
     {"2.01"}, ("stock_acquisition", "terminal_return_unknown", None)),
    ("holders who elected to receive stock; the right to receive $25.00 per share in cash", {"2.01"},
     ("merger", "terminal_return_unknown", None)),
    # Real 8-K phrasings that once passed as pure cash (CBE, CVH, GENZ, BMC).
    ("right to receive (i) $39.15 in cash and (ii) 0.77479 of a New Eaton ordinary share, and", {"2.01"},
     ("merger", "terminal_return_unknown", None)),
    ("right to receive $27.30 in cash, without interest, and 0.3885 of an Aetna common share.", {"2.01"},
     ("merger", "terminal_return_unknown", None)),
    ("right to receive the same $74.00 in cash (the Cash Consideration), and (ii) one contingent value right",
     {"2.01"}, ("merger", "terminal_return_unknown", None)),
    ("right to receive $46.25 in cash, without interest (the Merger Consideration). Each outstanding option to "
     "purchase shares of Common Stock was cancelled", {"2.01", "3.01"},
     ("cash_acquisition", "terminal_return_confirmed", 46.25)),
    ("the Company filed a voluntary petition under chapter 11", {"1.03"},
     ("bankruptcy_liquidation", "terminal_return_unknown", None)),
])
def test_terminal_terms_confirm_only_unconditional_cash(text, items, expected):
    event_type, status, economics = evidence.classify_terminal(items, evidence.extract_terms(text))
    assert (event_type, status, economics.get("cash_per_share") if status.endswith("confirmed") else None) == expected


def test_annual_report_symbol_requires_quoted_uppercase_symbol():
    assert evidence.annual_report_symbols(
        "listed on the New York Stock Exchange under the symbol &#8220;XRX&#8221;.") == {"XRX"}
    assert evidence.annual_report_symbols("traded under the ticker symbol WAG and") == {"WAG"}
    assert evidence.annual_report_symbols("under the symbol of our common stock") == set()
