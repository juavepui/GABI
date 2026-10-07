"""Six references captured before retiring the original evaluation module."""
import json
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

from gabi.application.market.snapshot_math import SnapshotCalculations
from gabi.domain.portfolio import evaluation
from gabi.infrastructure.storage.signals import SqliteSignals

REFERENCE = json.loads((Path(__file__).parent / "fixtures/evaluation_migration.json").read_text(encoding="utf-8"))


def _equal(actual, expected):
    if isinstance(expected, dict):
        assert actual.keys() == expected.keys()
        for key in expected:
            _equal(actual[key], expected[key])
    elif isinstance(expected, list):
        assert len(actual) == len(expected)
        for a, b in zip(actual, expected, strict=True):
            _equal(a, b)
    elif isinstance(expected, float):
        assert actual == pytest.approx(expected, rel=1e-12, abs=1e-14)
    else:
        assert actual == expected


@pytest.mark.parametrize("case", REFERENCE["cases"], ids=lambda case: case["name"])
def test_progress_horizon_and_curve_match_original(case):
    values, symbols = case["prices"], case["symbols"]
    today = date.fromisoformat(case["today"])
    watermark = pd.Timestamp(case["watermark"]) if case["watermark"] else None
    calls = []

    def price_at(symbol, target, after=False):
        calls.append((symbol, target, after))
        pair = values.get(symbol, [None, None])
        return pair[0 if target == pd.Timestamp("2024-01-02") else 1]

    progress = SnapshotCalculations.progress(symbols, "2024-01-02", data_as_of=watermark,
                                             price_at=price_at, today=today, cost_bps=10)
    progress["detail"] = json.loads(progress["detail"].to_json(orient="split", double_precision=15))
    _equal(progress, case["progress"])
    calls.clear()
    result = SnapshotCalculations.evaluate(symbols, "2024-01-02", 6, cost_bps=10,
                                           price_at=price_at, today=today)
    _equal(result, case["evaluated"])
    if result["status"] == "pending":
        assert calls == []
    else:
        assert calls == [(symbol, target, after) for symbol in [*dict.fromkeys(symbols), "SPY"]
                         for target, after in ((pd.Timestamp("2024-01-02"), False),
                                               (pd.Timestamp("2024-07-02"), True))]
    histories = {symbol: pd.DataFrame({"adj_close": pair}, index=pd.to_datetime(["2024-01-02", "2024-07-02"]))
                 for symbol, pair in values.items()}
    curve = SnapshotCalculations.curve(symbols, "2024-01-02", histories)
    _equal(json.loads(curve.to_json(orient="split", date_format="iso", double_precision=15)), case["curve"])


def test_domain_has_no_reader_or_implicit_clock_and_preserves_inputs(monkeypatch):
    from gabi import storage

    monkeypatch.setattr(storage, "get_connection", lambda: pytest.fail("SQLite accessed"))
    monkeypatch.setattr("requests.sessions.Session.request", lambda *a, **k: pytest.fail("Network accessed"))
    prices = {("AAA", "start"): 100.0, ("AAA", "end"): 150.0,
              ("SPY", "start"): 100.0, ("SPY", "end"): 120.0}
    before = deepcopy(prices)
    result = evaluation.progress_for(["AAA"], "2024-01-02", prices=prices, today=date(2025, 1, 1),
                                     data_as_of=pd.Timestamp("2024-07-02"))
    assert result["portfolio_return"] == .5 and prices == before
    with pytest.raises(TypeError, match="today"):
        evaluation.evaluate(["AAA"], "2024-01-02", prices=prices)
    histories = {"AAA": pd.DataFrame({"adj_close": [100.0, 150.0]},
                                    index=pd.to_datetime(["2024-01-02", "2024-07-02"]))}
    saved = histories["AAA"].copy(deep=True)
    evaluation.price_curve_for(["AAA"], "2024-01-02", histories)
    pd.testing.assert_frame_equal(saved, histories["AAA"])


def test_saved_rankings_use_operation_directory_and_clock(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    now = datetime.fromisoformat("2024-01-02T10:20:30+01:00")
    table = pd.DataFrame({"composite_score": [80.0, None], "score_coverage": [.9, .2]},
                         index=["AAA", "MISSING"])
    repo = SqliteSignals(first, now=lambda: now)
    assert repo.save_snapshot(table, "2024-01-02", "Fixture", 10) == 1
    assert repo.snapshot_meta(1)["created_at"] == now.isoformat()
    assert repo.snapshot(1).index.tolist() == ["AAA"]
    assert SqliteSignals(second).snapshots() == [] and not second.exists()
    before = repo.path.read_bytes()
    repo.snapshots()
    repo.snapshot(1)
    repo.snapshot_meta(1)
    assert repo.path.read_bytes() == before
