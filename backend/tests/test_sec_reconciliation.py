import pandas as pd

from gabi.domain.research.sec_reconciliation import compare


def test_nearest_month_end_and_distinct_durations():
    common = dict(cik='123', accn='a', tag='Revenues', unit='USD')
    exact = pd.DataFrame([{**common, 'start_date': '2008-09-28', 'end_date': '2009-09-26', 'val': 100},
                          {**common, 'start_date': '2009-06-28', 'end_date': '2009-09-26', 'val': 20}])
    bulk = pd.DataFrame([{**common, 'end_month': '2009-09-30', 'qtrs': 4, 'val': 100},
                         {**common, 'end_month': '2009-09-30', 'qtrs': 1, 'val': 100},
                         {**common, 'end_month': '2008-09-30', 'qtrs': 4, 'val': 100}])
    assert compare(bulk, exact).comparison.tolist() == ['matches', 'different_value', 'no_exact_context']


def test_sec_february_midmonth_rounds_back_without_changing_original_date():
    common = dict(cik='123', accn='a', tag='Revenues', unit='USD')
    bulk = pd.DataFrame([{**common, 'end_month': '2009-01-31', 'qtrs': 2, 'val': 100}])
    for day in ['2009-02-14', '2009-02-15']:
        exact = pd.DataFrame([{**common, 'start_date': '2008-08-31', 'end_date': day, 'val': 100}])
        assert compare(bulk, exact).comparison.tolist() == ['matches']
        assert exact.iloc[0].end_date == day


def test_large_dollar_values_do_not_hide_differences():
    common = dict(cik='123', accn='a', tag='Revenues', unit='USD')
    exact = pd.DataFrame([{**common, 'start_date': '2009-01-01', 'end_date': '2009-12-31', 'val': 1e12}])
    bulk = pd.DataFrame([{**common, 'end_month': '2009-12-31', 'qtrs': 4, 'val': 1e12 + 1}])
    assert compare(bulk, exact).comparison.tolist() == ['different_value']


def test_command_writes_unmatched_rows_and_summary(tmp_path):
    import json
    import sqlite3

    from gabi.infrastructure.legacy.sec_validation import directory, run_reconciliation

    with sqlite3.connect(tmp_path / 'gabi.db') as conn:
        conn.executescript("""
            CREATE TABLE entities(entity_id INTEGER, cik TEXT);
            CREATE TABLE entity_observations(entity_id INTEGER, dataset TEXT, payload_json TEXT);
            CREATE TABLE sec_bulk_submissions(accn TEXT, cik TEXT);
            CREATE TABLE sec_bulk_facts(accn TEXT, tag TEXT, unit TEXT, end_month TEXT, qtrs INTEGER, val REAL);
            INSERT INTO entities VALUES (1, '123');
            INSERT INTO sec_bulk_submissions VALUES ('a', '123');
            INSERT INTO sec_bulk_facts VALUES ('a', 'Revenues', 'USD', '2009-09-30', 4, 100), ('a', 'Revenues', 'USD', '2009-09-30', 1, 7);
        """)
        fact = {'tag': 'Revenues', 'unit': 'USD', 'start_date': '2008-09-28', 'end_date': '2009-09-26', 'accn': 'a',
                'val': 100, 'filed_date': '2009-11-01'}
        conn.execute("INSERT INTO entity_observations VALUES (1, 'edgar_facts', ?)", (json.dumps(fact),))
    directory(tmp_path).mkdir(parents=True)
    summary = run_reconciliation(tmp_path)
    assert summary['comparison'] == {'matches': 1, 'no_exact_context': 1}
    assert json.loads((directory(tmp_path) / 'reconciliation.json').read_text()) == summary
    assert pd.read_csv(directory(tmp_path) / 'sec-unmatched.csv').val.tolist() == [7]
