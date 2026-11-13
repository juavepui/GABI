"""#305: hand-computed split/reverse-split cases; no network, real data or study execution."""

import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gabi.application.portfolio.holdings import Holdings
from gabi.application.portfolio.holdings_prices import refresh
from gabi.domain.portfolio import holdings, holdings_basis, holdings_performance
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.holdings import SqliteHoldings
from gabi.infrastructure.storage.holdings_market import SqliteHoldingsMarket
from gabi_api.bootstrap import create_app

DAYS = pd.to_datetime(['2025-01-06', '2025-01-07', '2025-01-08', '2025-01-09'])
TODAY = date(2025, 1, 9)
NOW = datetime(2025, 1, 10, 23, tzinfo=UTC)


def lot(**changes):
    return holdings.validate_lot(dict(symbol='A', shares=10., price=100., currency='EUR',
                                      purchase_date='2025-01-06', commission=0.) | changes, TODAY)


def raw(price=50., ratio=2.):
    return pd.DataFrame({'Open': price, 'High': price, 'Low': price, 'Close': price,
                         'Adj Close': price, 'Volume': 10000., 'Stock Splits': [0., ratio, 0., 0.]}, index=DAYS)


def setup_market(tmp_path, ratio=2.):
    market = SqliteHoldingsMarket(tmp_path)
    for symbol, frame in [('A', raw(100 / ratio, ratio)), ('SPY', raw(100., 0.)),
                          ('USDEUR=X', raw(1., 0.))]:
        assert refresh([symbol], source=lambda s: frame, save=market.save, now=lambda: NOW) == {}
    return market


def service(tmp_path, market):
    return Holdings(SqliteHoldings(tmp_path), market.prices, pd.DataFrame, lambda: TODAY)


@pytest.mark.parametrize('ratio,shares,price', [(2., 20., 50.), (.1, 1., 1000.)])
def test_split_and_reverse_split_preserve_value_cost_returns_and_attribution(tmp_path, ratio, shares, price):
    market = setup_market(tmp_path, ratio)
    app = service(tmp_path, market)
    original = app.add(lot())
    position, = app.summary()['positions']
    assert position['shares'] == pytest.approx(shares)
    assert position['price'] == pytest.approx(price)
    assert position['average_price'] == pytest.approx(price)
    assert position['value_eur'] == position['cost_eur'] == 1000.
    assert position['return_eur'] == 0.
    result = app.performance()
    assert result['warnings'] == []
    assert result['portfolio']['final_value_eur'] == 1000.
    assert [p['value_eur'] for p in result['portfolio']['series']] == [1000.] * 4
    assert result['portfolio']['twr'] == 0.
    assert result['portfolio']['max_drawdown'] == 0.
    assert result['attribution']['gain_eur'] == 0.
    assert app.values_eur() == ({'A': 1000.}, [])
    assert app.lots() == [original]  # No rewrite of the broker's original movements.


@pytest.mark.parametrize('ratio', [2., .1])
def test_buys_and_sales_on_both_sides_of_the_event_and_deletion_sequence(tmp_path, ratio):
    app = service(tmp_path, setup_market(tmp_path, ratio))
    bought = app.add(lot())
    app.add(lot(kind='sell', shares=2., purchase_date='2025-01-06'))  # Sell before split: 200 EUR.
    app.add(lot(shares=2 * ratio, price=100 / ratio, purchase_date='2025-01-07'))  # Buy on split day.
    app.add(lot(kind='sell', shares=5 * ratio, price=100 / ratio,
                purchase_date='2025-01-08'))  # 500 EUR, even when shares exceed original buy count.
    pos, = app.summary()['positions']
    assert pos['shares'] == pytest.approx(5 * ratio)
    assert pos['cost_eur'] == pytest.approx(500.)
    assert pos['value_eur'] == pytest.approx(500.)
    assert pos['realized_eur'] == pytest.approx(0.)
    result = app.performance()
    assert result['attribution']['gain_eur'] == pytest.approx(0.)
    assert result['portfolio']['twr'] == pytest.approx(0.)
    with pytest.raises(Exception, match='No se puede borrar'):
        app.delete(bought['id'])
    with pytest.raises(Exception, match='No puedes vender'):
        app.add(lot(kind='sell', shares=6 * ratio, price=100 / ratio, purchase_date='2025-01-09'))


def test_restated_broker_csv_preserves_amount_and_does_not_double_adjust(tmp_path):
    app = service(tmp_path, setup_market(tmp_path))
    result = app.import_csv('symbol,shares,price,date,currency,basis_date\n'
                            'A,20,50,2025-01-06,EUR,2025-01-09\n')
    assert result['imported'] == 1
    pos, = app.summary()['positions']
    assert pos['shares'] == 20. and pos['cost_eur'] == pos['value_eur'] == 1000.
    assert app.performance()['attribution']['gain_eur'] == 0.
    assert app.lots()[0]['shares'] == 20. and app.lots()[0]['basis_date'] == '2025-01-09'
    with pytest.raises(ValueError, match='fecha de ajuste'):
        lot(basis_date='2025-01-05')


def test_later_splits_in_current_price_base_do_not_leak_into_historical_display_quantities(tmp_path):
    market = setup_market(tmp_path)
    app = Holdings(SqliteHoldings(tmp_path), market.prices, pd.DataFrame, lambda: DAYS[0].date())
    app.add(lot())
    pos, = app.summary()['positions']
    assert pos['shares'] == 10. and pos['price'] == 100. and pos['value_eur'] == 1000.
    assert app.performance()['portfolio']['final_value_eur'] == 1000.


def test_multiple_events_and_dividends_reconcile_without_changing_cash_amounts():
    # 2:1 then 1:10; final 2 shares @500, plus 10 EUR dividend withdrawn.
    frame = pd.DataFrame({'close': [500., 500., 495., 495.]}, index=DAYS)
    frame.attrs = dict(splits=[('2025-01-07', 2.), ('2025-01-08', .1)],
                       basis='today_splits', actions_verified=True)
    originals = [lot(), lot(kind='dividend', shares=0., price=10., purchase_date='2025-01-08')]
    prepared, frames, warnings = holdings_basis.prepare(originals, {'A': frame}, TODAY)
    assert warnings == []
    assert prepared[0]['shares'] == 2. and prepared[0]['price'] == 500.
    result = holdings_performance.evaluate(prepared, {'A': frames['A'].close}, {},
                                           pd.Series(100., index=DAYS), {}, TODAY)
    assert result['portfolio']['final_value_eur'] == 990.
    assert result['attribution']['gain_eur'] == 0.
    assert result['portfolio']['twr'] == pytest.approx(0.)


@pytest.mark.parametrize('events', [[('2025-01-07', -2.)], [('2025-01-07', float('nan'))],
                                    [('2025-01-07', 2.), ('2025-01-07', 3.)]])
def test_invalid_or_duplicate_event_blocks_calculation(events):
    frame = pd.DataFrame({'close': 50.}, index=DAYS)
    frame.attrs = dict(splits=events, basis='today_splits', actions_verified=True)
    with pytest.raises(ValueError, match='desdoblamiento'):
        holdings_basis.prepare([lot()], {'A': frame}, TODAY)


def test_old_cache_warns_and_is_not_used_silently_by_contribution_plan(tmp_path):
    from market_fixture import seed_fixture

    seed_fixture(tmp_path)
    app = service(tmp_path, SqliteHoldingsMarket(tmp_path))
    app.add(lot(symbol='T000'))
    summary = app.summary()
    assert summary['warnings'][0]['reason'] == 'unverified_actions'
    assert 'Actualizar precios' in summary['warnings'][0]['message']
    assert app.values_eur() == ({}, ['T000'])
    assert app.positions()[0]['status'] == 'unverified_actions'


def test_refresh_missing_actions_or_invalid_prices_keeps_previous_paired_snapshot(tmp_path):
    market = setup_market(tmp_path)
    stamp = NOW.isoformat()
    for broken in [raw().drop(columns='Stock Splits'), raw().assign(Close=-1),
                   raw().assign(**{'Stock Splits': float('nan')})]:
        failures = refresh(['A'], source=lambda _: broken, save=market.save, now=lambda: NOW)
        assert 'A' in failures
        frame = market.prices(['A'], '2025-01-01')['A']
        assert frame.close.tolist() == [50.] * 4
        assert frame.attrs['fetched_at'] == stamp
        assert frame.attrs['splits'] == [('2025-01-07', 2.)]
    # A corrected response with no event replaces, rather than appends to, old events.
    assert refresh(['A'], source=lambda _: raw(100., 0.), save=market.save, now=lambda: NOW) == {}
    assert market.prices(['A'], '2025-01-01')['A'].attrs['splits'] == []


def test_split_on_incomplete_session_is_preserved_for_the_already_adjusted_past_prices(tmp_path):
    market = SqliteHoldingsMarket(tmp_path)
    midday = datetime(2025, 1, 7, 14, tzinfo=UTC)
    response = raw().iloc[:2].copy()
    assert refresh(['A'], source=lambda _: response, save=market.save, now=lambda: midday) == {}
    frame = market.prices(['A'], '2025-01-01')['A']
    assert list(frame.index) == [DAYS[0]]  # Today's unfinished bar must not be valued.
    assert frame.attrs['splits'] == [('2025-01-07', 2.)]
    prepared, histories, warnings = holdings_basis.prepare([lot()], {'A': frame}, DAYS[0].date())
    result = holdings_basis.display(holdings.value(prepared, histories), histories)
    assert result['positions'][0]['shares'] == 10.
    assert result['positions'][0]['price'] == 100.
    assert result['positions'][0]['value'] == 1000.


def test_snapshot_write_rolls_back_prices_and_events_together(tmp_path):
    market = setup_market(tmp_path)
    with closing(sqlite3.connect(tmp_path / 'gabi.db')) as db, db:
        db.execute("CREATE TRIGGER fail_meta BEFORE INSERT ON holdings_market_meta "
                   "WHEN NEW.symbol='A' BEGIN SELECT RAISE(ABORT,'test failure'); END")
    assert 'A' in refresh(['A'], source=lambda _: raw(100., 0.), save=market.save, now=lambda: NOW)
    frame = market.prices(['A'], '2025-01-01')['A']
    assert frame.close.tolist() == [50.] * 4
    assert frame.attrs['splits'] == [('2025-01-07', 2.)]


def test_empty_reader_does_not_create_database_or_schema(tmp_path):
    market = SqliteHoldingsMarket(tmp_path)
    assert market.prices(['A'], '2025-01-01') == {}
    assert not (tmp_path / 'gabi.db').exists()


def test_reader_batches_symbols_in_one_snapshot_with_a_bounded_date_window(tmp_path, monkeypatch):
    market = setup_market(tmp_path)
    original_connect = sqlite3.connect
    queries = []

    def traced(*args, **kwargs):
        db = original_connect(*args, **kwargs)
        db.set_trace_callback(queries.append)
        return db

    monkeypatch.setattr(sqlite3, 'connect', traced)
    frames = market.prices(['A', 'SPY', 'USDEUR=X'], '2025-01-08')
    selects = [sql for sql in queries if sql.startswith('SELECT')]
    assert len(selects) == 4  # Schema inventory plus one batch per metadata/prices/events table.
    assert all(list(frame.index) == list(DAYS[2:]) for frame in frames.values())
    assert frames['A'].attrs['splits'] == [('2025-01-07', 2.)]  # Keep events outside price window.


def test_api_import_sale_summary_performance_and_no_get_side_effects(tmp_path, monkeypatch):
    setup_market(tmp_path)
    # Any accidental transport access from a GET must fail this test.
    from gabi.infrastructure.providers import yahoo

    monkeypatch.setattr(yahoo, 'history', lambda *a, **k: pytest.fail('GET downloaded data'))
    with TestClient(create_app(Settings(tmp_path), today=lambda: TODAY)) as api:
        response = api.post('/api/v1/portfolio/holdings/import', json={'csv':
                            'symbol,shares,price,date,currency\nA,10,100,2025-01-06,EUR\n'})
        assert response.status_code == 201, response.text
        response = api.post('/api/v1/portfolio/holdings', json=lot(kind='sell', shares=12., price=50.,
                                                               purchase_date='2025-01-08'))
        assert response.status_code == 201, response.text
        before = (tmp_path / 'gabi.db').read_bytes()
        with closing(sqlite3.connect(tmp_path / 'gabi.db')) as db:
            schema = db.execute('SELECT sql FROM sqlite_schema ORDER BY name').fetchall()
        summary = api.get('/api/v1/portfolio/holdings').json()
        pos, = summary['positions']
        assert pos['shares'] == 8. and pos['value_eur'] == pos['cost_eur'] == 400.
        assert pos['realized_eur'] == 0. and summary['warnings'] == []
        result = api.get('/api/v1/portfolio/holdings/performance').json()
        assert result['status'] == 'ok' and result['version'] == 'holdings-performance-v2'
        assert result['portfolio']['twr'] == 0. and result['attribution']['gain_eur'] == 0.
        assert (tmp_path / 'gabi.db').read_bytes() == before
        with closing(sqlite3.connect(tmp_path / 'gabi.db')) as db:
            assert db.execute('SELECT sql FROM sqlite_schema ORDER BY name').fetchall() == schema


def test_worker_bootstrap_wires_the_paired_refresh(tmp_path, monkeypatch):
    from gabi.application.administration.jobs import JobCommand
    from gabi_cli import bootstrap

    SqliteHoldings(tmp_path).add([lot()], NOW.isoformat())
    requested = []

    def source(symbol, **options):
        requested.append((symbol, options))
        return raw(50., 2.) if symbol == 'A' else raw(100., 0.)

    monkeypatch.setattr(bootstrap, 'yahoo_history', source)
    result = bootstrap.build_executor(Settings(tmp_path), now=lambda: NOW)(JobCommand(kind='holdings_prices'))
    assert result['failed'] == {}
    assert {symbol for symbol, _ in requested} == {'A', 'SPY', 'USDEUR=X'}
    assert all(options['actions'] and not options['auto_adjust'] for _, options in requested)
    frame = SqliteHoldingsMarket(tmp_path).prices(['A'], '2025-01-01')['A']
    assert frame.attrs['actions_verified'] and frame.attrs['splits'] == [('2025-01-07', 2.)]
