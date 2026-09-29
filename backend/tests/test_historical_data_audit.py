import sqlite3

import pandas as pd
import pytest

from gabi import historical_data_audit as audit


def test_snapshot_uses_latest_prior_membership_without_future_lookahead():
    history = pd.DataFrame([{"date": "2020-01-01", "tickers": "AAA,BBB"},
                            {"date": "2020-03-01", "tickers": "CCC"}])
    assert audit.pick_snapshot(history, "2020-02-29") == ("2020-01-01", ["AAA", "BBB"])
    with pytest.raises(ValueError, match="No membership snapshot"):
        audit.pick_snapshot(history, "2019-12-31")


def test_block_counts_require_every_official_metric_and_finite_values():
    full = {metric: 1 for metric in audit.METRICS}
    partial = dict(full, ev_ebitda=None, volatility=float("inf"))
    result = audit.block_counts([full, partial])
    assert result["value_complete"] == 1
    assert result["quality_complete"] == 2
    assert result["momentum_complete"] == 2
    assert result["risk_complete"] == 1
    assert result["all_13"] == 1
    assert result["ranking_minimum"] == 2


def test_old_quarterly_detail_counts_exact_missing_metrics():
    frame = pd.DataFrame([{"date": "2015-12-31", "missing_metrics": ""},
                          {"date": "2015-12-31", "missing_metrics": "pe;pb;ev_ebitda"}])
    result = audit.old_block_counts(frame, "2015-12-31")
    assert result["value_complete"] == 1
    assert result["quality_complete"] == 2
    assert result["all_13"] == 1


def test_annual_metrics_never_uses_future_filing(tmp_path):
    db = tmp_path / "cache.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE prices(symbol,date,close,adj_close)")
        conn.execute("CREATE TABLE splits(symbol,date,ratio)")
        conn.execute("CREATE TABLE edgar_facts(symbol,tag,unit,start_date,end_date,val,form,fp,fy,filed_date,accn)")
        dates = pd.bdate_range("2018-12-31", periods=301)
        conn.executemany("INSERT INTO prices VALUES (?,?,?,?)",
                         [(symbol, day.date().isoformat(), float(i + 100), float(i + 100))
                          for symbol in ["SPY", "AAA"] for i, day in enumerate(dates)])
        conn.execute("INSERT INTO edgar_facts VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     ("AAA", "NetIncomeLoss", "USD", "2019-01-01", "2019-12-31", 100,
                      "10-K", "FY", 2019, "2021-01-01", "future"))
    with audit.connect_readonly(db) as conn:
        result = audit.annual_metrics(conn, ["AAA"], "2019-12-31")
        assert result["pe"] == 0
        assert result["prices_253_recent"] == 1
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("DELETE FROM prices")
