import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gabi import insider

SAMPLE_XML_BUY = """<?xml version="1.0"?>
<ownershipDocument>
    <issuer>
        <issuerCik>0000320193</issuerCik>
        <issuerName>Acme Inc.</issuerName>
        <issuerTradingSymbol>ACME</issuerTradingSymbol>
    </issuer>
    <reportingOwner>
        <reportingOwnerId>
            <rptOwnerCik>0001111111</rptOwnerCik>
            <rptOwnerName>Doe Jane</rptOwnerName>
        </reportingOwnerId>
        <reportingOwnerRelationship>
            <isDirector>false</isDirector>
            <isOfficer>true</isOfficer>
            <isTenPercentOwner>false</isTenPercentOwner>
            <officerTitle>Chief Executive Officer</officerTitle>
        </reportingOwnerRelationship>
    </reportingOwner>
    <nonDerivativeTable>
        <nonDerivativeTransaction>
            <transactionDate><value>2025-03-10</value></transactionDate>
            <transactionCoding>
                <transactionCode>P</transactionCode>
            </transactionCoding>
            <transactionAmounts>
                <transactionShares><value>5000</value></transactionShares>
                <transactionPricePerShare><value>42.50</value></transactionPricePerShare>
                <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
            </transactionAmounts>
            <postTransactionAmounts>
                <sharesOwnedFollowingTransaction><value>120000</value></sharesOwnedFollowingTransaction>
            </postTransactionAmounts>
        </nonDerivativeTransaction>
    </nonDerivativeTable>
</ownershipDocument>"""

SAMPLE_XML_PLANNED_SALE = """<?xml version="1.0"?>
<ownershipDocument>
    <issuer>
        <issuerCik>0000320193</issuerCik>
        <issuerName>Acme Inc.</issuerName>
        <issuerTradingSymbol>ACME</issuerTradingSymbol>
    </issuer>
    <reportingOwner>
        <reportingOwnerId>
            <rptOwnerCik>0002222222</rptOwnerCik>
            <rptOwnerName>Smith John</rptOwnerName>
        </reportingOwnerId>
        <reportingOwnerRelationship>
            <isDirector>true</isDirector>
            <isOfficer>false</isOfficer>
            <isTenPercentOwner>false</isTenPercentOwner>
        </reportingOwnerRelationship>
    </reportingOwner>
    <nonDerivativeTable>
        <nonDerivativeTransaction>
            <transactionDate><value>2025-03-12</value></transactionDate>
            <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
            <transactionAmounts>
                <transactionShares><value>1000</value></transactionShares>
                <transactionPricePerShare><value>45.00</value></transactionPricePerShare>
                <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
            </transactionAmounts>
            <postTransactionAmounts>
                <sharesOwnedFollowingTransaction><value>9000</value></sharesOwnedFollowingTransaction>
            </postTransactionAmounts>
        </nonDerivativeTransaction>
    </nonDerivativeTable>
    <footnotes>
        <footnote id="F1">Sale made pursuant to a Rule 10b5-1 trading plan adopted on 2024-11-01.</footnote>
    </footnotes>
</ownershipDocument>"""


def test_parse_form4_xml_extracts_buy_transaction():
    parsed = insider.parse_form4_xml(SAMPLE_XML_BUY)
    assert parsed["symbol"] == "ACME"
    assert parsed["owner_name"] == "Doe Jane"
    assert parsed["is_officer"] is True
    assert parsed["is_director"] is False
    assert parsed["owner_title"] == "Chief Executive Officer"
    assert parsed["is_10b5_1_plan"] is False
    assert len(parsed["transactions"]) == 1
    tx = parsed["transactions"][0]
    assert tx["transaction_code"] == "P"
    assert tx["shares"] == 5000.0
    assert tx["price_per_share"] == 42.50
    assert tx["shares_owned_after"] == 120000.0


def test_parse_form4_xml_detects_10b5_1_plan_from_footnote():
    parsed = insider.parse_form4_xml(SAMPLE_XML_PLANNED_SALE)
    assert parsed["is_10b5_1_plan"] is True
    assert parsed["transactions"][0]["transaction_code"] == "S"


def test_parse_form4_xml_handles_malformed_xml_gracefully():
    import xml.etree.ElementTree as ET
    import pytest
    with pytest.raises(ET.ParseError):
        insider.parse_form4_xml("<not valid xml")


def _isolate_db(tmp_path, monkeypatch):
    from gabi import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test_gabi.db")


def _rows_from(symbol, cik, xml, accn):
    parsed = insider.parse_form4_xml(xml)
    return [
        {
            "symbol": symbol, "cik": cik, "accn": accn,
            "owner_name": parsed["owner_name"], "owner_title": parsed["owner_title"],
            "is_officer": parsed["is_officer"], "is_director": parsed["is_director"],
            "is_ten_pct_owner": parsed["is_ten_pct_owner"], "is_10b5_1_plan": parsed["is_10b5_1_plan"],
            "filed_date": "2025-03-11",
            **tx,
        }
        for tx in parsed["transactions"]
    ]


def test_upsert_and_get_insider_transactions_roundtrip(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    rows = _rows_from("ACME", "0000320193", SAMPLE_XML_BUY, "0001-25-000001")
    insider.upsert_insider_transactions("ACME", rows)

    df = insider.get_insider_transactions("ACME")
    assert len(df) == 1
    assert df.iloc[0]["owner_name"] == "Doe Jane"
    assert df.iloc[0]["transaction_code"] == "P"

    fetched_at = insider.get_insider_fetched_at(["ACME"])
    assert "ACME" in fetched_at

    # Re-insertar no debe duplicar (misma symbol/accn/line_no).
    insider.upsert_insider_transactions("ACME", rows)
    assert len(insider.get_insider_transactions("ACME")) == 1


def test_summarize_insider_activity_distinguishes_buys_and_sells(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    today = pd.Timestamp.today()
    recent_buy_xml = SAMPLE_XML_BUY.replace("2025-03-10", (today - pd.Timedelta(days=10)).date().isoformat())
    recent_sale_xml = SAMPLE_XML_PLANNED_SALE.replace("2025-03-12", (today - pd.Timedelta(days=5)).date().isoformat())

    rows = _rows_from("ACME", "0000320193", recent_buy_xml, "0001-25-000001")
    rows += _rows_from("ACME", "0000320193", recent_sale_xml, "0001-25-000002")
    insider.upsert_insider_transactions("ACME", rows)

    summary = insider.summarize_insider_activity("ACME", months=6)
    assert summary["n_buys"] == 1
    assert summary["n_sells"] == 1
    assert summary["distinct_buyers"] == 1
    assert summary["distinct_sellers"] == 1
    assert summary["net_value"] == 5000 * 42.50 - 1000 * 45.00


def test_summarize_insider_activity_empty_symbol_returns_zeros(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    summary = insider.summarize_insider_activity("NADA")
    assert summary["n_buys"] == 0
    assert summary["net_value"] is None


def test_summarize_insider_activity_ignores_old_transactions_outside_window(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    rows = _rows_from("ACME", "0000320193", SAMPLE_XML_BUY, "0001-25-000001")  # fecha 2025-03-10, muy antigua
    insider.upsert_insider_transactions("ACME", rows)
    summary = insider.summarize_insider_activity("ACME", months=6)
    assert summary["n_buys"] == 0
