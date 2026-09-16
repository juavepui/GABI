import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gabi import storage


def _isolate_db(tmp_path, monkeypatch):
    from gabi import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test_gabi.db")


def _price_df(dates_prices):
    dates = pd.to_datetime([d for d, _ in dates_prices])
    return pd.DataFrame(
        {
            "Open": [p for _, p in dates_prices], "High": [p for _, p in dates_prices],
            "Low": [p for _, p in dates_prices], "Close": [p for _, p in dates_prices],
            "Volume": [1000] * len(dates_prices),
        },
        index=dates,
    )


def test_get_price_as_of_exact_trading_day(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    storage.upsert_prices("ACME", _price_df([
        ("2019-01-02", 100.0), ("2019-01-03", 101.0), ("2019-01-04", 102.0),
    ]))
    assert storage.get_price_as_of("ACME", "2019-01-03") == 101.0


def test_get_price_as_of_falls_back_to_previous_session(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    storage.upsert_prices("ACME", _price_df([
        ("2019-01-02", 100.0), ("2019-01-04", 102.0),  # sin sesión el 2019-01-03 (festivo/finde)
    ]))
    # Pedir una fecha sin sesión debe devolver la sesión anterior más cercana, no la siguiente.
    assert storage.get_price_as_of("ACME", "2019-01-03") == 100.0


def test_get_price_as_of_returns_none_before_earliest_cached_date(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    storage.upsert_prices("ACME", _price_df([("2019-06-01", 100.0)]))
    assert storage.get_price_as_of("ACME", "2015-01-01") is None


def test_get_price_as_of_missing_symbol_returns_none(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    assert storage.get_price_as_of("NOPE", "2019-01-01") is None


def test_split_factor_since_no_splits_is_one(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    assert storage.get_split_factor_since("ACME", "2019-01-01") == 1.0


def test_split_factor_since_accumulates_only_later_splits(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    storage.upsert_splits("ACME", {"2015-06-09": 7.0, "2020-08-31": 4.0})

    # Antes de 2015 -> deshacer AMBOS splits (7 * 4).
    assert storage.get_split_factor_since("ACME", "2015-01-01") == 28.0
    # Entre los dos splits -> deshacer solo el de 2020.
    assert storage.get_split_factor_since("ACME", "2019-06-01") == 4.0
    # Después de ambos -> no hay nada que deshacer.
    assert storage.get_split_factor_since("ACME", "2021-01-01") == 1.0
