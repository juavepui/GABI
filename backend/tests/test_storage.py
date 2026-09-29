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


def test_record_update_errors_is_noop_for_empty_failed(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    storage.record_update_errors("yahoo_precio", {})
    assert storage.get_recent_update_errors().empty


def test_record_and_get_recent_update_errors_roundtrip(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    storage.record_update_errors("yahoo_precio", {"AAA": "timeout", "BBB": "rate limit"})
    storage.record_update_errors("sec_edgar", {"AAA": "404"})

    all_errors = storage.get_recent_update_errors()
    assert len(all_errors) == 3
    assert set(all_errors["source"]) == {"yahoo_precio", "sec_edgar"}

    only_edgar = storage.get_recent_update_errors(source="sec_edgar")
    assert len(only_edgar) == 1
    assert only_edgar.iloc[0]["symbol"] == "AAA"
    assert only_edgar.iloc[0]["reason"] == "404"


def test_get_recent_update_errors_excludes_entries_older_than_window(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    import gabi.storage as storage_mod
    old_iso = (storage_mod.datetime.now(storage_mod.UTC) - storage_mod.timedelta(days=10)).isoformat()
    with storage.get_connection() as conn:
        conn.executescript(storage.SCHEMA)
        conn.execute(
            "INSERT INTO update_errors (source, symbol, reason, occurred_at) VALUES (?,?,?,?)",
            ("yahoo_precio", "OLD", "stale entry", old_iso),
        )
        conn.commit()
    storage.record_update_errors("yahoo_precio", {"NEW": "fresh entry"})

    recent = storage.get_recent_update_errors(since_hours=24)
    assert list(recent["symbol"]) == ["NEW"]  # el viejo de hace 10 días no entra en la ventana de 24h


def test_record_update_errors_prunes_entries_older_than_retention(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    import gabi.storage as storage_mod
    very_old = (storage_mod.datetime.now(storage_mod.UTC)
                - storage_mod.timedelta(days=storage.UPDATE_ERRORS_RETENTION_DAYS + 1)).isoformat()
    with storage.get_connection() as conn:
        conn.executescript(storage.SCHEMA)
        conn.execute(
            "INSERT INTO update_errors (source, symbol, reason, occurred_at) VALUES (?,?,?,?)",
            ("yahoo_precio", "ANCIENT", "muy viejo", very_old),
        )
        conn.commit()

    storage.record_update_errors("yahoo_precio", {"NEW": "dispara la poda"})

    with storage.get_connection() as conn:
        remaining = conn.execute("SELECT symbol FROM update_errors").fetchall()
    assert remaining == [("NEW",)]  # la entrada antigua se podó al insertar la nueva
