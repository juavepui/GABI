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
        {"Open": [10], "High": [10], "Low": [10], "Close": [10], "Adj Close": [10], "Volume": [100]},
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
        {"Open": [10], "High": [10], "Low": [10], "Close": [10], "Adj Close": [10], "Volume": [100]},
        index=pd.to_datetime(["2015-01-02"]),
    )
    storage.upsert_prices("COVERED", df)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("no debería llamar a la red si ya hay cobertura suficiente")

    monkeypatch.setattr(data_fetch, "fetch_prices_batch", fail_if_called)

    result = data_fetch.ensure_price_history_asof(["COVERED"], "2019-01-01")
    assert result == {"deep_fetched": 0, "already_covered": 1, "failed": {}}


def test_decision_prices_migrate_only_missing_adjusted_history(tmp_path, monkeypatch):
    from datetime import date
    import pandas as pd
    from gabi import config, storage

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test_gabi.db")
    dates = pd.bdate_range(end=date.today(), periods=130)
    base = {"Open": [10] * 130, "High": [10] * 130, "Low": [10] * 130,
            "Close": [10] * 130, "Volume": [100] * 130}
    storage.upsert_prices("OLD", pd.DataFrame(base, index=dates))
    storage.upsert_prices("READY", pd.DataFrame({**base, "Adj Close": [10] * 130}, index=dates))
    calls = []

    def fake_fetch(symbols, period="2y"):
        calls.append((symbols, period))
        storage.upsert_prices("OLD", pd.DataFrame({**base, "Adj Close": [10] * 130}, index=dates))
        return {}

    monkeypatch.setattr(data_fetch, "fetch_prices_batch", fake_fetch)
    result = data_fetch.ensure_decision_prices(["OLD", "READY"])
    assert calls == [(["OLD"], "2y")]
    assert result["requested"] == 1
    assert storage.get_price_coverage(["OLD"])["OLD"]["adjusted_count"] == 130


def test_single_ticker_multiindex_download_keeps_adjusted_close(tmp_path, monkeypatch):
    import pandas as pd
    from gabi import config, storage
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test_gabi.db")
    columns = pd.MultiIndex.from_product([["AAA"], ["Open", "High", "Low", "Close", "Adj Close", "Volume"]])
    downloaded = pd.DataFrame([[10, 10, 10, 10, 9, 100]],
                              index=pd.to_datetime(["2026-09-15"]), columns=columns)
    monkeypatch.setattr(data_fetch.yf, "download", lambda *args, **kwargs: downloaded)
    assert data_fetch.fetch_prices_batch(["AAA"]) == {}
    assert storage.get_prices("AAA")["adj_close"].iloc[0] == 9
