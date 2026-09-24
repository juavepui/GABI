import numpy as np
import pandas as pd

from gabi import historical_coverage as hc
from gabi import risk, technicals


def test_availability_requires_value_quality_momentum_and_half_metrics():
    assert hc.availability({m: 1 for m in hc.METRICS}) == (13, True)
    assert hc.availability({m: float("inf") for m in hc.METRICS}) == (0, False)
    assert not hc.availability({m: 1 for m in hc.METRICS if m not in ['pe', 'pb', 'ev_ebitda']})[1]


def test_future_filings_excluded_and_price_metrics_match_engine():
    prices = pd.DataFrame({'close': np.arange(1., 301.), 'adj_close': np.arange(1., 301.)},
                           index=pd.bdate_range('2009-01-01', periods=300))
    rows = pd.DataFrame([dict(tag='NetIncomeLoss', unit='USD', start_date='2008-01-01', end_date='2008-12-31',
                              filed_date='2011-01-01', accn='a', form='10-K', fp='FY', fy=2008, val=100)])
    day = '2010-02-24'
    result = hc.metric_row(rows, prices, prices, day, nominal_price=300)
    assert result['pe'] is None
    assert hc.fact_structure(rows, day)['facts']['us-gaap'] == {}
    expected = technicals.compute_technicals(prices.loc[:day], prices.loc[:day])
    assert result['momentum_12m'] == expected['momentum_12m']
    assert result['price_vs_sma200'] == expected['price_vs_sma200']
    assert result['max_drawdown'] == risk._max_drawdown(prices.loc[:day])


def test_price_comparison_ignores_constant_adjustment_levels():
    prices = pd.DataFrame({'adj_close': np.arange(1., 101.)}, index=pd.bdate_range('2009-01-01', periods=100))
    assert hc.compare_prices(prices, prices * 4)['status'] == 'consistent_overlap'
    bad = prices.copy()
    bad.iloc[::5] *= 2
    assert hc.compare_prices(prices, bad)['status'] == 'disagreement'
