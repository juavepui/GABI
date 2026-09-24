import pandas as pd

from gabi.sec_reconciliation import compare


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
