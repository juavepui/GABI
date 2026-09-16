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
