import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gabi import data_fetch


def test_classify_rate_limit():
    category, reason = data_fetch._classify_error(Exception("429 Client Error: Too Many Requests"))
    assert category == "rate_limit"
    assert "límite de peticiones" in reason.lower()


def test_classify_not_found():
    category, reason = data_fetch._classify_error(Exception("possibly delisted; no price data found"))
    assert category == "not_found"


def test_classify_timeout():
    category, reason = data_fetch._classify_error(Exception("HTTPSConnectionPool: Read timed out"))
    assert category == "timeout"


def test_classify_connection():
    category, reason = data_fetch._classify_error(Exception("Failed to establish a new connection"))
    assert category == "connection"


def test_classify_invalid_response():
    category, reason = data_fetch._classify_error(Exception("Expecting value: line 1 column 1 (char 0)"))
    assert category == "invalid_response"


def test_classify_other_falls_back_to_message():
    category, reason = data_fetch._classify_error(Exception("algo muy raro pasó"))
    assert category == "other"
    assert reason == "algo muy raro pasó"


def test_normalize_symbol_dots_to_dashes():
    assert data_fetch.normalize_symbol("BRK.B") == "BRK-B"
    assert data_fetch.normalize_symbol("AAPL") == "AAPL"


def test_ensure_price_history_asof_only_fetches_symbols_without_coverage(tmp_path, monkeypatch):
    from gabi import config, storage

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test_gabi.db")
    storage.init_db()

    import pandas as pd
    covered_df = pd.DataFrame(
        {"Open": [10], "High": [10], "Low": [10], "Close": [10], "Volume": [100]},
        index=pd.to_datetime(["2015-01-02"]),
    )
    storage.upsert_prices("COVERED", covered_df)  # ya llega hasta 2015

    calls = []

    def fake_fetch_prices_batch(symbols, period="2y"):
        calls.append((tuple(symbols), period))
        return {}

    monkeypatch.setattr(data_fetch, "fetch_prices_batch", fake_fetch_prices_batch)

    result = data_fetch.ensure_price_history_asof(["COVERED", "NOTCOVERED"], "2019-01-01")

    assert result["already_covered"] == 1
    assert result["deep_fetched"] == 1
    assert len(calls) == 1
    assert calls[0] == (("NOTCOVERED",), "max")  # solo el que falta, con histórico completo


def test_ensure_price_history_asof_skips_network_when_all_covered(tmp_path, monkeypatch):
    from gabi import config, storage

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test_gabi.db")
    storage.init_db()

    import pandas as pd
    df = pd.DataFrame(
        {"Open": [10], "High": [10], "Low": [10], "Close": [10], "Volume": [100]},
        index=pd.to_datetime(["2015-01-02"]),
    )
    storage.upsert_prices("COVERED", df)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("no debería llamar a la red si ya hay cobertura suficiente")

    monkeypatch.setattr(data_fetch, "fetch_prices_batch", fail_if_called)

    result = data_fetch.ensure_price_history_asof(["COVERED"], "2019-01-01")
    assert result == {"deep_fetched": 0, "already_covered": 1, "failed": {}}
