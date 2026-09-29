import zipfile

import pandas as pd
import pytest

from gabi import config, sec_history, storage


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    return tmp_path


def test_bulk_preserves_rounded_dates_and_rejects_subsidiaries(db):
    path = db / "quarter.zip"
    sub = pd.DataFrame([dict(adsh="a", cik="123", name="Issuer", sic="1234", form="10-K", filed="20100201",
                             accepted="2010-02-01 12:00:00", fy="2009", fp="FY", instance="test.xml")])
    base = dict(adsh="a", tag="Revenues", version="us-gaap/2009", ddate="20091231", qtrs="4", uom="USD",
                segments="", coreg="", value="100")
    nums = pd.DataFrame([base, {**base, "value": "101"}, {**base, "value": "999", "segments": "Business=A"},
                         {**base, "value": "888", "coreg": "Subsidiary"},
                         {**base, "tag": "NetIncomeLoss", "value": "NaN"}])
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("sub.txt", sub.to_csv(sep="\t", index=False))
        z.writestr("num.txt", nums.to_csv(sep="\t", index=False))
    for _ in range(2):
        counts = sec_history.import_quarter(path, "source", {"0000000123"})
    assert counts == {"submissions": 1, "facts": 2, "excluded_segment_or_coreg": 2, "invalid": 1}
    with storage.get_connection() as conn:
        assert conn.execute("SELECT end_month,qtrs,val FROM sec_bulk_facts ORDER BY val").fetchall() == [
            ("2009-12-31", 4, 100), ("2009-12-31", 4, 101)]
        assert not conn.execute("SELECT 1 FROM sqlite_master WHERE name='edgar_facts'").fetchone()


def test_bulk_schema_migration_preserves_rows_and_accepts_other_values(db):
    with storage.get_connection() as conn:
        conn.executescript(sec_history.SCHEMA.replace(
            "PRIMARY KEY(accn,tag,version,end_month,qtrs,unit,val)",
            "PRIMARY KEY(accn,tag,version,end_month,qtrs,unit)"))
        row = ('a', 'Revenues', 'us-gaap/2009', '2009-12-31', 4, 'USD', 100)
        conn.execute('INSERT INTO sec_bulk_facts VALUES (?,?,?,?,?,?,?)', row)
        conn.commit()
        sec_history.ensure_schema(conn)
        sec_history.ensure_schema(conn)
        conn.execute('INSERT INTO sec_bulk_facts VALUES (?,?,?,?,?,?,?)', (*row[:-1], 101))
        assert conn.execute('SELECT val FROM sec_bulk_facts ORDER BY val').fetchall() == [(100,), (101,)]


def test_original_xbrl_exact_dates_identity_dimensions_and_conflicts():
    content = b'''<xbrl xmlns="http://www.xbrl.org/2003/instance" xmlns:g="http://fasb.org/us-gaap/2009"
      xmlns:iso="http://www.xbrl.org/2003/iso4217">
      <context id="a"><entity><identifier scheme="sec">123</identifier></entity>
      <period><startDate> 2008-12-28 </startDate><endDate>\n2009-12-26\n</endDate></period></context>
      <context id="b"><entity><identifier scheme="sec">456</identifier></entity>
      <period><instant>2009-12-26</instant></period></context>
      <context id="s"><entity><identifier scheme="sec">123</identifier><segment>division</segment></entity>
      <period><instant>2009-12-26</instant></period></context>
      <unit id="usd"><measure>iso:USD</measure></unit>
      <g:Revenues contextRef="a" unitRef="usd">100</g:Revenues>
      <g:Revenues contextRef="b" unitRef="usd">999</g:Revenues>
      <g:Revenues contextRef="s" unitRef="usd">777</g:Revenues>
      <g:NetIncomeLoss contextRef="a" unitRef="usd">10</g:NetIncomeLoss>
      <g:NetIncomeLoss contextRef="a" unitRef="usd">11</g:NetIncomeLoss>
      </xbrl>'''
    rows = sec_history.parse_instance(content, cik="0000000123", accn="test", filed_date="2010-02-01",
                                      form="10-K", fp="FY", fy="2009")
    assert len(rows) == 1
    assert rows[0]["val"] == 100
    assert rows[0]["start_date"] == "2008-12-28"
    assert rows[0]["end_date"] == "2009-12-26"
    assert rows[0]["filed_date"] == "2010-02-01"
