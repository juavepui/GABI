"""Yahoo calls keep their arguments and results after moving behind the provider (ADR 0004)."""

import ast
import json
import time
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
import yfinance

from gabi import config, data_fetch
from gabi.infrastructure.providers import yahoo

REFERENCE = json.loads((Path(__file__).parent / "fixtures/yahoo_provider_migration.json").read_text(encoding="utf-8"))


class FakeYahoo:
    def __init__(self):
        self.calls = []
        index = pd.to_datetime(["2024-01-02", "2024-01-03"])
        self.panel = pd.DataFrame({("AAA", "Open"): [1., 2.], ("AAA", "High"): [1., 2.], ("AAA", "Low"): [1., 2.],
                                   ("AAA", "Close"): [1., 2.], ("AAA", "Adj Close"): [.9, 1.8],
                                   ("AAA", "Volume"): [10., 20.]}, index=index)
        self.splits = pd.Series([2.0], index=pd.to_datetime(["2020-08-31"]))

    def download(self, tickers, **options):
        self.calls.append(("download", tuple(tickers), tuple(sorted(options.items()))))
        if "FAIL" in tickers:
            raise ValueError("No data found, symbol may be delisted")
        return self.panel

    def Ticker(self, symbol):  # noqa: N802 - yfinance's name
        self.calls.append(("Ticker", symbol))
        if symbol == "EMPTY":
            return SimpleNamespace(info={}, splits=pd.Series(dtype=float))
        return SimpleNamespace(info={"marketCap": 1e9, "sector": "Tech", "unknown": 1}, splits=self.splits,
                               quarterly_income_stmt=pd.DataFrame({"2024-03-31": [1.]}, index=["Revenue"]),
                               quarterly_cashflow=pd.DataFrame(),
                               history=lambda **options: self.calls.append(("history", tuple(sorted(options.items()))))
                               or self.panel["AAA"])

    def set_tz_cache_location(self, path):
        self.calls.append(("cache", path))


def captured(fake) -> dict:
    namespace = {"yf": fake, "pd": pd, "config": config, "time": time, "normalize_symbol": data_fetch.normalize_symbol,
                 "identity": data_fetch.identity, "datetime": data_fetch.datetime, "UTC": data_fetch.UTC,
                 "_classify_error": data_fetch._classify_error, "RETRYABLE_CATEGORIES": data_fetch.RETRYABLE_CATEGORIES,
                 "RETRY_BACKOFF_SECONDS": 0, "storage": SimpleNamespace(upsert_prices=lambda *a, **k: None,
                                                                         upsert_splits=lambda *a, **k: None)}
    for node in ast.parse(REFERENCE["data_fetch"]).body:
        if isinstance(node, ast.FunctionDef) and node.name in {"_fetch_splits_one", "_fetch_fundamentals_attempt",
                                                              "fetch_prices_batch"}:
            exec(ast.get_source_segment(REFERENCE["data_fetch"], node), namespace)
    return namespace


@pytest.mark.parametrize("call", [
    lambda m: m["_fetch_splits_one"]("BRK.B"), lambda m: m["_fetch_splits_one"]("EMPTY"),
    lambda m: m["_fetch_fundamentals_attempt"]("BRK.B"), lambda m: m["_fetch_fundamentals_attempt"]("EMPTY"),
    lambda m: m["fetch_prices_batch"](["AAA"]), lambda m: m["fetch_prices_batch"](["AAA", "FAIL"], period="max"),
])
def test_data_fetch_calls_match_capture(monkeypatch, call):
    monkeypatch.setattr(data_fetch, "_writes", lambda: SimpleNamespace(prices=lambda *a, **k: None,
                                                                        splits=lambda *a, **k: None))
    monkeypatch.setattr(data_fetch.identity, "resolve", lambda *a: {"entity_id": None})
    results = []
    for label in ("old", "new"):
        fake = FakeYahoo()
        if label == "old":
            module = captured(fake)
        else:
            for name in ("download", "Ticker", "set_tz_cache_location"):
                monkeypatch.setattr(yfinance, name, getattr(fake, name))
            module = vars(data_fetch)
        try:
            outcome = call(module)
        except Exception as exc:  # noqa: BLE001
            outcome = (type(exc).__name__, str(exc))
        results.append((repr(outcome), fake.calls))
    assert results[0] == results[1]


def test_provider_resolves_yfinance_at_call_time(monkeypatch, tmp_path):
    fake = FakeYahoo()
    for name in ("download", "Ticker", "set_tz_cache_location"):
        monkeypatch.setattr(yfinance, name, getattr(fake, name))
    yahoo.download(["AAA"], period="2y")
    assert yahoo.splits("AAA").iloc[0] == 2.0
    yahoo.history("AAA", period="max", auto_adjust=False)
    yahoo.use_timezone_cache(tmp_path / "tz")
    assert [call[0] for call in fake.calls] == ["download", "Ticker", "Ticker", "history", "cache"]
    assert fake.calls[-1] == ("cache", str(tmp_path / "tz"))
