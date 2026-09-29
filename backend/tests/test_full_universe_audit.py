import json
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from gabi import full_universe_audit as full


def fixture_cache(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    database = data / "source.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE prices(symbol TEXT, date TEXT, adj_close REAL)")
        connection.execute("INSERT INTO prices VALUES ('SPY', '2016-07-05', 100)")
    for name in ("sp500_historical_membership.csv", "sec_cik_map.csv"):
        (data / name).write_text("frozen input\n", encoding="utf-8")
    monkeypatch.setattr(full.config, "DATA_DIR", data)
    monkeypatch.setattr(full.config, "DB_PATH", database)
    # Source files live outside this fixture directory, so use the actual common
    # ancestor when building the manifest's relative provenance paths.
    monkeypatch.setattr(full.config, "BASE_DIR", Path(Path(full.__file__).anchor))
    dates = pd.DataFrame({"date": ["2016-01-02", "2016-04-02"]})
    symbols = [f"S{i}" for i in range(250)]
    monkeypatch.setattr(full.universe, "get_historical_membership", lambda: dates)
    monkeypatch.setattr(full.universe, "get_sp500_constituents_asof", lambda date: {"is_exact": True, "symbols": symbols})
    calls = []

    def ranking(date, *, symbols, weights):
        calls.append(date)
        assert len(symbols) == 250  # Explicitly more than the old 200 sample.
        return {"table": pd.DataFrame({"composite_score": range(250), "score_coverage": [1.] * 250}, index=symbols)}

    monkeypatch.setattr(full.screener_asof, "build_ranking_as_of", ranking)
    return data / "cache", database, calls


def test_complete_universe_range_and_resumable_rankings(tmp_path, monkeypatch):
    cache, original_db, calls = fixture_cache(tmp_path, monkeypatch)
    manifest = full.prepare(cache)
    assert manifest["dates"] == ["2016-01-02", "2016-04-02"]
    assert manifest["end"] == "2016-07-02"
    assert manifest["max_symbols"] is None
    assert all(r["n_universe"] == r["n_eligible"] == 250 for r in manifest["rankings"].values())
    assert full.config.DB_PATH == original_db
    assert full.prepare(cache) == manifest
    assert len(calls) == 2


def test_changed_snapshot_is_rejected_before_resuming(tmp_path, monkeypatch):
    cache, _, _ = fixture_cache(tmp_path, monkeypatch)
    full.prepare(cache)
    with sqlite3.connect(cache / "snapshot.db") as connection:
        connection.execute("INSERT INTO prices VALUES ('SPY', '2016-07-06', 101)")
    with pytest.raises(ValueError, match="snapshot"):
        full.prepare(cache)


def test_evaluation_uses_same_full_rankings_and_keeps_initial_cost_in_cagr(tmp_path, monkeypatch):
    cache, original_db, _ = fixture_cache(tmp_path, monkeypatch)
    manifest = full.prepare(cache)
    calls = []

    def run_v1(start, end, *, months, top_n, max_symbols):
        assert max_symbols is None and months == 3
        assert (start, end) == (manifest["start"], manifest["end"])
        table = full.screener_asof.build_ranking_as_of(start, symbols=manifest["rankings"][start]["symbols"])["table"]
        assert len(table) == 250
        calls.append(("v1", top_n))
        return {"periods": pd.DataFrame({"fecha": manifest["dates"], "hasta": ["2016-04-04", "2016-07-05"]}),
                "skipped": []}

    def run_v2(start, end, **kwargs):
        assert kwargs["mode"] == "validation" and kwargs["max_symbols"] is None
        assert kwargs["initial_capital"] == 100000
        calls.append(("v2", kwargs["top_n"]))
        # The first NAV already contains an entry cost. CAGR must use initial
        # cash 100000, not this first observation of 99000.
        nav = pd.Series([99000., 110000., 121000.], index=pd.to_datetime(["2016-01-04", "2016-04-04", "2016-07-05"]))
        return {"periods": pd.DataFrame({"fecha": manifest["dates"]}), "nav_curve": nav,
                "nav_curve_spy": nav, "skipped": [], "turnover_medio": 10.,
                "comision_total": 1000., "capital_final": 121000.}

    monkeypatch.setattr(full.v1, "run", run_v1)
    monkeypatch.setattr(full.v2, "run", run_v2)
    output = tmp_path / "output"
    report = full.evaluate(cache, output)
    assert calls == [("v1", 10), ("v2", 10), ("v1", 20), ("v2", 20)]
    metrics = report["results"]["v2_top10"]["metrics"]["strategy"]
    assert metrics["total_return_from_initial_cash"] == pytest.approx(.21)
    years = (pd.Timestamp("2016-07-05") - pd.Timestamp("2016-01-04")).days / 365.25
    assert metrics["cagr_from_initial_cash"] == pytest.approx(1.21 ** (1 / years) - 1)
    assert full.config.DB_PATH == original_db
    saved = json.loads((output / "audit.json").read_text(encoding="utf-8"))
    assert saved["status"] == "complete"
    assert len(saved["artifacts"]) == 7
