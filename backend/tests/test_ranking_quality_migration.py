"""Historical ranking and data quality without the storage facade; small aliases retired (#132)."""

import ast
import json
import sqlite3
import sys
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from gabi import config, data_quality, edgar, entity_master, historical_pit, identity, screener_asof, storage
from gabi.domain.market import quality_persistence as domain_quality
from gabi.domain.market import valuation_expectations as domain_valuation
from gabi.domain.portfolio import broker_costs as domain_costs
from gabi.domain.portfolio import capital_allocation as domain_allocation
from gabi.domain.portfolio import rotation as domain_rotation

REFERENCE = json.loads((Path(__file__).parent / "fixtures/ranking_quality_migration.json").read_text(encoding="utf-8"))
NOW = datetime(2024, 3, 1, 12, tzinfo=UTC)
ALIASES = ("capital_allocation", "valuation_expectations", "quality_persistence", "broker_costs", "rotation_policy")


def module(name: str) -> ModuleType:
    """Execute a captured module inside the ``gabi`` package, as it was imported before the migration."""
    captured = ModuleType(f"gabi.{name}")
    captured.__package__ = "gabi"
    captured.__file__ = str(Path(screener_asof.__file__).with_name(f"{name}.py"))
    exec(REFERENCE[name], captured.__dict__)
    return captured


def retired_sources() -> dict[str, ModuleType]:
    """The readers the capture used from the facades retired in F7.25, over the same stores."""
    from gabi import config
    from gabi.domain.market import fred
    from gabi.infrastructure.storage.fred import SqliteFred
    from gabi.infrastructure.storage.insiders import SqliteInsiders

    def series():
        return SqliteFred(config.DB_PATH, lambda: datetime.now(UTC))

    insider, macro = ModuleType("gabi.insider"), ModuleType("gabi.macro")
    insider.get_insider_fetched_at = lambda symbols: SqliteInsiders(
        config.DB_PATH.parent, database=config.DB_PATH).fetched_at(symbols)
    macro.SERIES = {key: dict(value) for key, value in fred.SERIES.items()}
    macro.get_all_fetched_at = lambda: series().fetched_at_all()
    macro.get_series_history = lambda series_id: series().history(series_id)
    return {"insider": insider, "macro": macro}


@pytest.fixture
def old(monkeypatch):
    for name in ALIASES:
        monkeypatch.setitem(sys.modules, f"gabi.{name}", module(name))
    for name, facade in retired_sources().items():
        monkeypatch.setitem(sys.modules, f"gabi.{name}", facade)
    return {name: module(name) for name in ("screener_asof", "data_quality")}


def prices(start, n, price, daily=0.0005, adjusted=True):
    index = pd.bdate_range(start, periods=n)
    close = price * np.cumprod(1 + np.full(n, daily))
    return pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close,
                         "Adj Close": close * 0.98 if adjusted else np.nan, "Volume": 1e6}, index=index)


def facts(symbol, revenue, income, equity, debt, cash, shares, filed, year=2018):
    end, start = f"{year}-12-31", f"{year}-01-01"
    rows = [("Revenues", "USD", start, revenue), ("NetIncomeLoss", "USD", start, income),
            ("StockholdersEquity", "USD", "", equity), ("LongTermDebtNoncurrent", "USD", "", debt),
            ("CashAndCashEquivalentsAtCarryingValue", "USD", "", cash),
            ("NetCashProvidedByUsedInOperatingActivities", "USD", start, income * 1.3),
            ("PaymentsToAcquirePropertyPlantAndEquipment", "USD", start, income * 0.3),
            ("PaymentsForRepurchaseOfCommonStock", "USD", start, income * 0.2),
            ("CommonStockSharesOutstanding", "shares", "", shares)]
    return [{"tag": tag, "unit": unit, "start_date": begin, "end_date": end, "val": value, "form": "10-K",
             "fp": "FY", "fy": year, "filed_date": filed, "accn": f"{symbol}-{year}-{tag}"}
            for tag, unit, begin, value in rows if value is not None]


@pytest.fixture
def market(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    storage.init_db()
    entities = {symbol: identity.ensure_entity(cik) for symbol, cik in (("AAA", "1"), ("BBB", "2"))}
    for symbol, entity in entities.items():
        identity.add_alias(entity, symbol, "2000-01-01", source="synthetic-fixture")
    for symbol, price, daily in (("AAA", 20.0, .0006), ("BBB", 80.0, -.0002)):
        storage.upsert_prices(symbol, prices("2018-01-02", 400, price, daily), entity_id=entities[symbol])
        edgar.upsert_edgar_facts(symbol, facts(symbol, 1000, 150 if symbol == "AAA" else 40, 500, 100, 30, 100,
                                               "2019-02-01"), cik={"AAA": "1", "BBB": "2"}[symbol])
    # Unmigrated issuers read from the ticker-keyed cache; DDD split 4:1 after the date, EEE lacks adj_close.
    storage.upsert_prices("CCC", prices("2018-01-02", 400, 50.0, .0001))
    storage.upsert_prices("DDD", prices("2018-01-02", 400, 25.0, 0.0))
    storage.upsert_splits("DDD", {"2020-08-31": 4.0, "2018-03-01": 2.0})
    storage.upsert_prices("EEE", prices("2018-01-02", 400, 10.0, adjusted=False))
    storage.upsert_prices("SPY", prices("2018-01-02", 400, 250.0, .0003))
    edgar.upsert_edgar_facts("CCC", facts("CCC", 2000, -20, 0, None, 10, 50, "2019-03-01"))
    edgar.upsert_edgar_facts("DDD", facts("DDD", 500, 60, 300, 50, None, 400_000, "2019-02-15"))
    entity_master.record_snapshot(pd.DataFrame([
        {"symbol": "AAA", "cik": "0000000001", "name": "Alpha", "sector": "Salud", "industry": "Farma"},
        {"symbol": "CCC", "cik": "0000000003", "name": "Gamma", "sector": "Energía", "industry": "Petróleo"}]),
        effective_date="2019-01-01")
    return tmp_path


DAYS = ["2019-06-03", "2019-01-15", "2018-02-15"]
SYMBOLS = ["AAA", "BBB", "CCC", "DDD", "EEE", "NODATA"]


@pytest.mark.parametrize("day", DAYS)
@pytest.mark.parametrize("strict", [False, True])
@pytest.mark.parametrize("weights", [None, {"value": 1.0, "quality": 0.0, "momentum": 0.0, "risk": 0.0}])
def test_ranking_matches_capture(market, old, day, strict, weights):
    expected = old["screener_asof"].build_ranking_as_of(day, weights=weights, symbols=SYMBOLS, strict_identity=strict)
    actual = screener_asof.build_ranking_as_of(day, weights=weights, symbols=SYMBOLS, strict_identity=strict)
    assert_frame_equal(actual["table"], expected["table"])
    assert actual["universe_info"] == expected["universe_info"]
    for symbol in SYMBOLS:
        for entity in (None, identity.resolve(symbol, day)["entity_id"]):
            assert screener_asof._classic_metrics_as_of(symbol, day, entity_id=entity) == \
                old["screener_asof"]._classic_metrics_as_of(symbol, day, entity_id=entity)
            assert screener_asof.fundamental_diagnostics(symbol, day, entity_id=entity) == \
                old["screener_asof"].fundamental_diagnostics(symbol, day, entity_id=entity)
            stamp = pd.Timestamp(day)
            assert_frame_equal(screener_asof._price_history_as_of(symbol, stamp, entity_id=entity),
                               old["screener_asof"]._price_history_as_of(symbol, stamp, entity_id=entity))


def test_ranking_values_cover_split_missing_and_ticker_cache(market):
    table = screener_asof.build_ranking_as_of("2019-06-03", symbols=SYMBOLS)["table"]
    assert table.loc["DDD", "price"] == pytest.approx(100.0)  # 25 x 4: only the later split is undone
    assert pd.isna(table.loc["EEE", "price"]) and pd.isna(table.loc["EEE", "market_cap"])  # no verified adj_close
    assert pd.isna(table.loc["NODATA", "pe"]) and pd.isna(table.loc["CCC", "pe"])  # negative income: missing
    assert table.loc["AAA", "sector"] == "Salud" and table.loc["AAA", "entity_id"]


@pytest.mark.parametrize("periods", [(), ("2010-2015",)])
def test_accredited_period_branch_matches_capture(market, old, monkeypatch, periods):
    frame = prices("2014-01-02", 300, 30.0)
    frame.columns = [column.lower().replace(" ", "_") for column in frame.columns]
    frame.attrs.update(source_id=historical_pit.YAHOO_SOURCE, source_symbol="AAA")
    monkeypatch.setattr(identity, "price_history", lambda symbol, as_of, entity_id=None: frame.copy())
    with closing(sqlite3.connect(config.DB_PATH)) as db:
        db.execute("INSERT INTO splits (symbol, date, ratio) VALUES ('AAA', '2015-06-01', 2.0)")
        db.commit()
    with historical_pit.accredited_periods(*periods):
        for symbol, entity in (("AAA", identity.resolve("AAA", "2014-12-31")["entity_id"]), ("CCC", None)):
            assert screener_asof._classic_metrics_as_of(symbol, "2014-12-31", entity_id=entity) == \
                old["screener_asof"]._classic_metrics_as_of(symbol, "2014-12-31", entity_id=entity)
        expected = old["screener_asof"].build_ranking_as_of("2014-12-31", symbols=["AAA", "CCC"])
        actual = screener_asof.build_ranking_as_of("2014-12-31", symbols=["AAA", "CCC"])
    assert_frame_equal(actual["table"], expected["table"])
    assert actual["universe_info"] == expected["universe_info"]


class FrozenClock(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW


def quality_views(module_, symbols):
    return (module_.universe_summary(symbols), module_.symbol_provenance("AAA"), module_.symbol_provenance("DDD", "2019-06-03"),
            module_.local_cik_status(symbols), module_.recent_errors_summary(), module_.recent_errors_summary(1))


def test_data_quality_matches_capture(market, old, monkeypatch):
    storage.record_update_errors("yahoo_precio", {"AAA": "timeout", "ZZZ": "404", "OLD": "stale"})
    storage.upsert_fundamentals("AAA", {"trailingPE": 12.5, "sector": "Salud"}, pd.DataFrame(), pd.DataFrame())
    storage.upsert_fundamentals("DDD", {"trailingPE": None, "marketCap": 1e9}, pd.DataFrame(), pd.DataFrame())
    with closing(sqlite3.connect(config.DB_PATH)) as db:
        # Error ages relative to the frozen clock: inside 1 h, inside 7 days, outside both.
        for symbol, age in (("AAA", "30 minutes"), ("ZZZ", "3 days"), ("OLD", "20 days")):
            db.execute("UPDATE update_errors SET occurred_at=? WHERE symbol=?",
                       ((NOW - pd.Timedelta(age)).isoformat(), symbol))
        db.executescript("CREATE TABLE IF NOT EXISTS cik_resolutions (symbol TEXT PRIMARY KEY, cik TEXT, title TEXT, resolved_at TEXT)")
        db.executemany("INSERT INTO cik_resolutions VALUES (?,?,?,?)",
                       [("CCC", "0000000003", "Gamma", "2024-01-01"), ("OTHER", "9", "x", "2024-01-01")])
        db.commit()
    monkeypatch.setattr(edgar, "CIK_CACHE", market / "sec_cik_map.csv")
    pd.DataFrame({"symbol": ["DDD", "BRK-B"], "cik": ["0000000004", "0000000005"], "title": ["D", "B"]}).to_csv(
        edgar.CIK_CACHE, index=False)
    monkeypatch.setattr(data_quality, "datetime", FrozenClock)
    old["data_quality"].datetime = FrozenClock
    monkeypatch.setattr(storage, "datetime", FrozenClock)  # the captured errors summary read storage's clock
    symbols = SYMBOLS + ["BRK.B", "AAA"]
    for expected, actual in zip(quality_views(old["data_quality"], symbols), quality_views(data_quality, symbols),
                                strict=True):
        if isinstance(expected, pd.DataFrame):
            assert_frame_equal(actual, expected)
        else:
            assert json.dumps(actual, sort_keys=True, default=str) == json.dumps(expected, sort_keys=True, default=str)
    table = screener_asof.build_ranking_as_of("2019-06-03", symbols=SYMBOLS)["table"]
    for name in ("score_block_coverage", "ranking_quality"):
        assert json.dumps(getattr(data_quality, name)(table), default=str) == \
            json.dumps(getattr(old["data_quality"], name)(table), default=str)


@pytest.mark.parametrize("symbols", [None, [], ["AAA"], ["DDD", "AAA", "NODATA"]])
def test_fingerprint_matches_capture_and_never_writes(market, old, symbols):
    pd.DataFrame({"date": ["2019-01-01"], "tickers": ["AAA,BBB"]}).to_csv(market / "sp500_historical_membership.csv", index=False)
    pd.DataFrame({"symbol": ["AAA"], "cik": ["1"]}).to_csv(market / "sec_cik_map.csv", index=False)
    new = data_quality.compute_data_fingerprint(symbols, inputs={"cutoff": "2019-06-03"})
    before = config.DB_PATH.read_bytes()
    assert new == data_quality.compute_data_fingerprint(symbols, inputs={"cutoff": "2019-06-03"})
    assert config.DB_PATH.read_bytes() == before
    assert new == old["data_quality"].compute_data_fingerprint(symbols, inputs={"cutoff": "2019-06-03"})


def test_fingerprint_of_an_absent_database_matches_without_creating_it(tmp_path, monkeypatch, old):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "new")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "new" / "gabi.db")
    new = data_quality.compute_data_fingerprint(["AAA"])
    assert not (tmp_path / "new").exists()
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "old")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "old" / "gabi.db")
    assert new == old["data_quality"].compute_data_fingerprint(["AAA"])


def test_quality_reads_never_create_schema(tmp_path, monkeypatch):
    monkeypatch.setattr(edgar, "CIK_CACHE", tmp_path / "absent.csv")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    monkeypatch.setattr(storage, "get_connection", lambda: pytest.fail("legacy storage connection"))
    assert data_quality.local_cik_status(["AAA"]) == {"AAA": None}
    assert data_quality.recent_errors_summary().empty
    assert screener_asof._ticker_price_as_of("AAA", "2019-06-03") is None
    assert not (tmp_path / "gabi.db").exists()


def test_local_cik_status_reads_more_than_one_batch(market):
    with closing(sqlite3.connect(config.DB_PATH)) as db:
        db.executescript("CREATE TABLE IF NOT EXISTS cik_resolutions (symbol TEXT PRIMARY KEY, cik TEXT, title TEXT, resolved_at TEXT)")
        db.executemany("INSERT INTO cik_resolutions VALUES (?,?,?,?)", [(f"S{i}", str(i), "t", "x") for i in range(1, 2500)])
        db.commit()
    symbols = [f"S{i}" for i in range(2600)]
    assert data_quality.local_cik_status(symbols) == {f"S{i}": (str(i) if 0 < i < 2500 else None) for i in range(2600)}


def test_captured_aliases_were_the_domain_implementations(old):
    pairs = {"capital_allocation": (domain_allocation, ("metrics", "_annual_series", "_instant_series", "BUYBACK_TAGS")),
             "valuation_expectations": (domain_valuation, ("expectations_metrics", "reverse_dcf_growth")),
             "quality_persistence": (domain_quality, ("from_facts", "_annual", "_cagr")),
             "broker_costs": (domain_costs, ("STOCK_FEE_USD", "effective_trade_cost_bps", "position_size_usd")),
             "rotation_policy": (domain_rotation, ("select_with_score_hurdle",))}
    for name, (domain, exports) in pairs.items():
        for export in exports:
            assert getattr(sys.modules[f"gabi.{name}"], export) is getattr(domain, export)
    for name in ("capital_allocation", "valuation_expectations", "quality_persistence", "broker_costs"):
        assert not Path(screener_asof.__file__).with_name(f"{name}.py").exists()


def test_screener_asof_and_data_quality_no_longer_import_storage():
    for module_ in (screener_asof, data_quality):
        tree = ast.parse(Path(module_.__file__).read_text(encoding="utf-8"))
        names = {alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.level
                 for alias in node.names}
        assert not names & {"storage", "historical_pit", "quality_persistence", "capital_allocation",
                            "valuation_expectations"}, module_.__name__
