import hashlib

import pytest

from gabi.legacy_filings import extract_reviewed, values_after_label


def test_signed_cash_flow_and_ambiguous_labels():
    assert values_after_label("Operating cash $ (45,595 ) $ 5,000", "Operating cash") == [-45595, 5000]
    assert values_after_label("Net income applicable to common stock 50", "Net income") is None
    assert values_after_label("Net income -- 30", "Net income") is None
    assert values_after_label("Net income 20% 30%", "Net income") is None


def test_pinned_filing_units_dates_and_publication_not_retroactive():
    raw = b'<TABLE>\nYear ended June 30     1995 1996\nNet income    12 15\n</TABLE>'
    contract = dict(sha256=hashlib.sha256(raw).hexdigest(), filed_date="1996-09-27", fiscal_year=1996, accn="a",
                    tables=[dict(index=0, scale=1000000, periods=[["1994-07-01", "1995-06-30"], ["1995-07-01", "1996-06-30"]],
                                 concepts=[dict(label="Net income", tag="NetIncomeLoss")])],
                    checks=[dict(tag="NetIncomeLoss", end_date="1996-06-30", value=15000000)])
    rows = extract_reviewed(raw, contract)
    assert rows[0]["val"] == 12000000
    assert rows[0]["filed_date"] == "1996-09-27"
    with pytest.raises(ValueError, match="reviewed document"):
        extract_reviewed(raw + b'changed', contract)
    contract["checks"][0]["value"] = 99
    with pytest.raises(ValueError, match="transcription"):
        extract_reviewed(raw, contract)


def test_balances_must_reconcile_even_when_rows_parse():
    raw = b'<TABLE>\nAssets 100\nLiabilities 90\nEquity 20\n</TABLE>'
    contract = dict(sha256=hashlib.sha256(raw).hexdigest(), filed_date="1996-09-27", fiscal_year=1996, accn="a",
                    tables=[dict(index=0, scale=1000000, periods=[["", "1996-06-30"]],
                                 concepts=[dict(label=a, tag=b) for a, b in [("Assets", "Assets"),
                                           ("Liabilities", "Liabilities"), ("Equity", "StockholdersEquity")]])], checks=[])
    with pytest.raises(ValueError, match="balance sheet"):
        extract_reviewed(raw, contract)
