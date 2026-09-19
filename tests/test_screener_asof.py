import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gabi import edgar, entity_master, screener_asof, storage, universe


def _isolate_db(tmp_path, monkeypatch):
    from gabi import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test_gabi.db")


def _price_df(start, n, start_price=100.0, daily_return=0.0005):
    dates = pd.date_range(start, periods=n, freq="B")
    prices = start_price * np.cumprod(1 + np.full(n, daily_return))
    return pd.DataFrame(
        {"Open": prices, "High": prices, "Low": prices, "Close": prices,
         "Adj Close": prices, "Volume": [1_000_000] * n},
        index=dates,
    )


def _seed_edgar_facts(symbol, revenue, net_income, equity, debt, shares, filed_date, end_date="2018-12-31", start_date="2018-01-01"):
    rows = [
        {"tag": "Revenues", "unit": "USD", "start_date": start_date, "end_date": end_date,
         "val": revenue, "form": "10-K", "fp": "FY", "fy": 2018, "filed_date": filed_date, "accn": f"{symbol}-rev"},
        {"tag": "NetIncomeLoss", "unit": "USD", "start_date": start_date, "end_date": end_date,
         "val": net_income, "form": "10-K", "fp": "FY", "fy": 2018, "filed_date": filed_date, "accn": f"{symbol}-ni"},
        {"tag": "StockholdersEquity", "unit": "USD", "start_date": "", "end_date": end_date,
         "val": equity, "form": "10-K", "fp": "FY", "fy": 2018, "filed_date": filed_date, "accn": f"{symbol}-eq"},
        {"tag": "LongTermDebtNoncurrent", "unit": "USD", "start_date": "", "end_date": end_date,
         "val": debt, "form": "10-K", "fp": "FY", "fy": 2018, "filed_date": filed_date, "accn": f"{symbol}-debt"},
        {"tag": "CommonStockSharesOutstanding", "unit": "shares", "start_date": "", "end_date": end_date,
         "val": shares, "form": "10-K", "fp": "FY", "fy": 2018, "filed_date": filed_date, "accn": f"{symbol}-sh"},
    ]
    edgar.upsert_edgar_facts(symbol, rows)


def test_build_ranking_as_of_end_to_end_with_synthetic_data(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    storage.init_db()

    # Dos empresas: AAA barata y rentable, BBB cara y menos rentable.
    _seed_edgar_facts("AAA", revenue=1000, net_income=150, equity=500, debt=100, shares=100,
                       filed_date="2019-02-01")
    _seed_edgar_facts("BBB", revenue=1000, net_income=50, equity=400, debt=300, shares=100,
                       filed_date="2019-02-01")

    storage.upsert_prices("AAA", _price_df("2018-06-01", 250, start_price=20.0))   # cap ~ 20*100=2000 -> PER bajo
    storage.upsert_prices("BBB", _price_df("2018-06-01", 250, start_price=80.0))   # cap ~ 80*100=8000 -> PER alto
    storage.upsert_prices("SPY", _price_df("2018-06-01", 250, start_price=250.0))

    result = screener_asof.build_ranking_as_of(
        "2019-06-01", weights={"value": 1.0, "quality": 0.0, "momentum": 0.0, "risk": 0.0},
        symbols=["AAA", "BBB"],
    )
    df = result["table"]
    assert list(df.index) == ["AAA", "BBB"]  # AAA gana en Value (más barata)
    assert df.loc["AAA", "pe"] < df.loc["BBB", "pe"]
    assert df.loc["AAA", "value_score"] > df.loc["BBB", "value_score"]
    assert result["universe_info"]["note"].startswith("Universo pasado explícitamente")


def test_build_ranking_as_of_avoids_look_ahead_bias_in_fundamentals(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    storage.init_db()

    # NetIncomeLoss real de 2018 = 100, pero se presenta el 2019-02-01.
    _seed_edgar_facts("AAA", revenue=1000, net_income=100, equity=500, debt=100, shares=100,
                       filed_date="2019-02-01")
    # Restatación posterior con un valor MUY distinto, presentada más tarde.
    edgar.upsert_edgar_facts("AAA", [
        {"tag": "NetIncomeLoss", "unit": "USD", "start_date": "2018-01-01", "end_date": "2018-12-31",
         "val": 999_999.0, "form": "10-K", "fp": "FY", "fy": 2019, "filed_date": "2020-02-01", "accn": "AAA-ni-restated"},
    ])
    storage.upsert_prices("AAA", _price_df("2018-06-01", 100, start_price=20.0))

    result = screener_asof.build_ranking_as_of("2019-06-01", symbols=["AAA"])
    df = result["table"]
    # A fecha 2019-06-01 la restatación de 2020 todavía no existía.
    assert df.loc["AAA", "pe"] is not None
    market_cap = df.loc["AAA", "market_cap"]
    assert round(df.loc["AAA", "pe"], 2) == round(market_cap / 100, 2)  # usa 100, no 999999


def test_build_ranking_as_of_handles_symbol_with_no_data_gracefully(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    storage.init_db()
    _seed_edgar_facts("AAA", revenue=1000, net_income=150, equity=500, debt=100, shares=100,
                       filed_date="2019-02-01")
    storage.upsert_prices("AAA", _price_df("2018-06-01", 100, start_price=20.0))

    result = screener_asof.build_ranking_as_of("2019-06-01", symbols=["AAA", "SINDATOS"])
    df = result["table"]
    assert len(df) == 2
    assert pd.isna(df.loc["SINDATOS", "pe"])
    assert pd.isna(df.loc["SINDATOS", "composite_score"])
    assert pd.isna(df.loc["AAA", "composite_score"])  # solo 100 días de precio: cobertura insuficiente
    assert df.loc["AAA", "score_coverage"] < 0.50


def test_build_ranking_as_of_corrects_market_cap_for_later_stock_split(tmp_path, monkeypatch):
    # Caso real detectado con Apple: yfinance siempre devuelve el precio
    # ajustado por splits (haya o no auto_adjust). Sin deshacer un split
    # posterior a as_of_date, la capitalización sale sistemáticamente mal
    # por el factor del split (aquí, 4x por debajo).
    _isolate_db(tmp_path, monkeypatch)
    storage.init_db()

    _seed_edgar_facts("AAA", revenue=1000, net_income=150, equity=500, debt=100,
                       shares=400_000,  # nº de acciones REAL en 2018 (antes del split 4:1)
                       filed_date="2019-02-01")
    price_df = _price_df("2018-06-01", 250, start_price=25.0, daily_return=0.0)
    price_df["Adj Close"] = 20.0  # dividendos posteriores; no deben entrar en la capitalización
    storage.upsert_prices("AAA", price_df)
    storage.upsert_splits("AAA", {"2020-08-31": 4.0})  # split 4:1 ocurrido DESPUÉS de la fecha consultada

    result = screener_asof.build_ranking_as_of("2019-06-01", symbols=["AAA"])
    row = result["table"].loc["AAA"]

    # Precio real esperado ese día: 25 * 4 = 100 (deshaciendo el split futuro).
    assert round(row["price"], 2) == 100.0
    # Capitalización: precio real * acciones reales = 100 * 400_000 = 40_000_000.
    assert round(row["market_cap"], 2) == 40_000_000.0


def test_build_ranking_as_of_uses_historical_universe_when_symbols_not_given(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    storage.init_db()

    cache = tmp_path / "hist.csv"
    pd.DataFrame([
        {"date": "2019-01-01", "tickers": "AAA,BBB"},
        {"date": "2019-12-01", "tickers": "AAA,BBB,CCC"},  # cobertura posterior a la fecha pedida
    ]).to_csv(cache, index=False)
    monkeypatch.setattr(universe, "HISTORICAL_MEMBERSHIP_CACHE", cache)

    _seed_edgar_facts("AAA", revenue=1000, net_income=150, equity=500, debt=100, shares=100,
                       filed_date="2019-02-01")
    storage.upsert_prices("AAA", _price_df("2018-06-01", 100, start_price=20.0))

    result = screener_asof.build_ranking_as_of("2019-06-01")
    assert result["universe_info"]["is_exact"] is True
    assert result["universe_info"]["source_date"] == "2019-01-01"
    assert set(result["table"].index) == {"AAA", "BBB"}  # CCC todavía no había entrado


def test_build_ranking_as_of_uses_entity_master_sector_not_todays_universe(tmp_path, monkeypatch):
    """El sector viene de entity_master.get_sector_asof (point-in-time,
    aunque hoy en día sea aproximado), NUNCA de universe.get_sp500_constituents()
    (el sector ACTUAL) -- el look-ahead señalado por el usuario."""
    _isolate_db(tmp_path, monkeypatch)
    storage.init_db()
    monkeypatch.setattr(edgar, "get_cik_map", lambda: pd.DataFrame(columns=["symbol", "cik", "title"]))
    monkeypatch.setattr(edgar, "get_cik_for_symbol", lambda symbol, cik_map=None: (None, None))
    # Si build_ranking_as_of todavía usara el universo actual, esto rompería
    # (no hay red/caché disponible) -- confirma que ya no se llama en absoluto.
    monkeypatch.delattr(universe, "get_sp500_constituents")

    entity_master.record_snapshot(
        pd.DataFrame([{"symbol": "AAA", "name": "Empresa A", "sector": "Salud", "industry": "Farma"}]),
        effective_date="2019-01-01",
    )
    _seed_edgar_facts("AAA", revenue=1000, net_income=150, equity=500, debt=100, shares=100,
                       filed_date="2019-02-01")
    storage.upsert_prices("AAA", _price_df("2018-06-01", 250, start_price=20.0))

    result = screener_asof.build_ranking_as_of("2019-06-01", symbols=["AAA"])
    df = result["table"]
    assert df.loc["AAA", "sector"] == "Salud"
    assert df.loc["AAA", "name"] == "Empresa A"
    assert not df.loc["AAA", "sector_is_approximate"]  # foto de 2019-01, fecha pedida 2019-06: real
