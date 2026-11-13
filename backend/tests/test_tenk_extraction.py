"""#41: the reviewed-free 10-K table extractor, on synthetic filings only (never the pilot sample)."""
import pandas as pd

from gabi.domain.research import tenk_extraction as pilot
from gabi.infrastructure.legacy.tenk_extraction import extract

INCOME = """<p>(in millions, except per share data)</p><table>
<tr><td></td><td>2008</td><td>2007</td></tr>
<tr><td>Net sales</td><td>$ 1,200</td><td>$ 1,100</td></tr>
<tr><td>Operating income</td><td>300</td><td>250</td></tr>
<tr><td>Net income</td><td>(20)</td><td>180</td></tr>
<tr><td>Earnings per share</td><td>1.10</td><td>0.90</td></tr></table>"""
CASH = """<table><tr><td>(In thousands)</td><td>2007</td><td>2008</td></tr>
<tr><td>Net cash provided by operating activities</td><td>500</td><td>650</td></tr>
<tr><td>Capital expenditures</td><td>(70)</td><td>(80)</td></tr>
<tr><td>Net cash used in investing activities</td><td>(90)</td><td>(95)</td></tr></table>"""


def test_newest_year_scale_and_sign_across_documents():
    found = extract([INCOME, CASH])
    assert found == {"revenue": 1.2e9, "operating_income": 3e8, "net_income": -2e7,
                     "operating_cash_flow": 6.5e5, "capex": 8e4}


def test_first_xbrl_filing_of_the_fiscal_year_and_annual_duration():
    facts = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [
        {"form": "10-K", "start": "2008-01-01", "end": "2008-12-31", "val": 99, "filed": "2010-02-01"},
        {"form": "10-K", "start": "2008-01-01", "end": "2008-12-31", "val": 100, "filed": "2009-02-01"},
        {"form": "10-Q", "start": "2008-10-01", "end": "2008-12-31", "val": 1, "filed": "2009-01-01"},
        {"form": "10-K", "start": "2008-10-01", "end": "2008-12-31", "val": 2, "filed": "2009-01-02"}]}}}}}
    assert pilot.first_xbrl_value(facts, ["Revenues"], "duration", "2008-12-31") == (100.0, "2009-02-01")
    assert pilot.first_xbrl_value(facts, ["Assets"], "instant", "2008-12-31") == (None, None)


def test_split_was_fixed_by_position_and_summary_counts_only_comparable_rows():
    assert pilot.split(list(range(5))) == {"ajuste": [0, 2, 4], "reserva": [1, 3]}
    frame = pd.DataFrame([{"item": "revenue", "extraido": 1.0, "xbrl": 1.0, "error_relativo": 0.0, "coincide": True},
                          {"item": "revenue", "extraido": None, "xbrl": 2.0, "error_relativo": None, "coincide": False},
                          {"item": "capex", "extraido": 3.0, "xbrl": None, "error_relativo": None, "coincide": False}])
    summary = pilot.summary(frame, 1)
    assert summary["global"] == {"comparables": 2, "extraidas": 1, "coinciden": 1, "error_mediano": 0.0}
    assert list(summary["por_partida"]) == ["revenue"]
