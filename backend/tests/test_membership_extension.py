import copy
import json
from datetime import UTC, datetime

import pandas as pd
import pytest

from gabi import universe
from gabi.history_refresh import last_completed_session, period_symbols
from gabi.membership_extension import LEDGER_PATH, extend_membership, fingerprint


@pytest.fixture
def reviewed():
    history = pd.DataFrame([("2025-08-23", "AAA,BBB")], columns=["date", "tickers"])
    ledger = {"anchor_date": "2025-08-23", "anchor_sha256": fingerprint({"AAA", "BBB"}),
              "verified_through": "2025-09-24", "endpoint_symbols": ["BBB", "CCC"],
              "events": [{"effective_date": "2025-09-22", "removed": "AAA", "added": "CCC",
                          "source_url": "https://example.com/announcement"}]}
    return history, ledger


def test_extension_effective_date_idempotence_and_preservation(reviewed, tmp_path, monkeypatch):
    history, ledger = reviewed
    extended = extend_membership(history, ledger)
    pd.testing.assert_frame_equal(history, extended.iloc[:1])
    pd.testing.assert_frame_equal(extended, extend_membership(extended, ledger))
    monkeypatch.setattr(universe, "get_historical_membership", lambda: extended)
    assert universe.get_sp500_constituents_asof("2025-09-21")["symbols"] == ["AAA", "BBB"]
    assert universe.get_sp500_constituents_asof("2025-09-22")["symbols"] == ["BBB", "CCC"]
    assert universe.get_sp500_constituents_asof("2025-09-24")["is_exact"]
    assert period_symbols(extended, "2025-09-01", "2025-09-24") == ["AAA", "BBB", "CCC"]


@pytest.mark.parametrize("problem", ["anchor", "removal", "addition", "endpoint", "future", "conflict"])
def test_reject_unverified_extension(reviewed, problem):
    history, ledger = copy.deepcopy(reviewed)
    if problem == "anchor":
        ledger["anchor_sha256"] = "wrong"
    elif problem == "removal":
        ledger["events"][0]["removed"] = "MISSING"
    elif problem == "addition":
        ledger["events"][0]["added"] = "BBB"
    elif problem == "endpoint":
        ledger["endpoint_symbols"] = ["AAA", "BBB"]
    elif problem == "future":
        ledger["events"][0]["effective_date"] = "2025-09-25"
    else:
        history.loc[len(history)] = ["2025-09-23", "AAA,BBB"]
    with pytest.raises(ValueError):
        extend_membership(history, ledger)


def test_refresh_stale_upstream_keeps_local_extension(reviewed, monkeypatch, tmp_path):
    history, ledger = reviewed
    extended = extend_membership(history, ledger)
    cache = tmp_path / "history.csv"
    extended.to_csv(cache, index=False)
    monkeypatch.setattr(universe, "HISTORICAL_MEMBERSHIP_CACHE", cache)
    monkeypatch.setattr(universe, "apply_reviewed_extension", lambda h: extend_membership(h, ledger))

    class Response:
        content = history.to_csv(index=False).encode()

        def raise_for_status(self):
            pass

    monkeypatch.setattr(universe.requests, "get", lambda *args, **kwargs: Response())
    pd.testing.assert_frame_equal(universe.get_historical_membership(force_refresh=True), extended)
    pd.testing.assert_frame_equal(pd.read_csv(cache), extended)


def test_reviewed_ledger_reconciles_and_respects_spinoff_days():
    ledger = json.loads(LEDGER_PATH.read_text())
    # Reverse events solely to create the anchor, then check its independent hash.
    members = set(ledger["endpoint_symbols"])
    for event in reversed(ledger["events"]):
        if event["added"]:
            members.remove(event["added"])
        if event["removed"]:
            members.add(event["removed"])
    assert fingerprint(members) == ledger["anchor_sha256"]
    history = pd.DataFrame([(ledger["anchor_date"], ",".join(sorted(members)))], columns=["date", "tickers"])
    extended = extend_membership(history, ledger).set_index("date")
    assert len(extended.loc["2025-10-30", "tickers"].split(",")) == 504
    assert len(extended.loc["2025-10-31", "tickers"].split(",")) == 503
    assert "MRSH" not in extended.loc["2025-12-22", "tickers"].split(",")
    assert "MRSH" in extended.loc["2026-01-14", "tickers"].split(",")


def test_last_session_excludes_intraday_and_handles_weekends():
    assert last_completed_session(datetime(2026, 9, 23, 15, tzinfo=UTC)) == "2026-09-22"
    assert last_completed_session(datetime(2026, 9, 23, 21, tzinfo=UTC)) == "2026-09-23"
    assert last_completed_session(datetime(2026, 9, 20, 21, tzinfo=UTC)) == "2026-09-18"


def test_legacy_duplicate_dates_are_preserved(reviewed):
    history, ledger = reviewed
    legacy = pd.DataFrame([("2024-01-01", "AAA"), ("2024-01-01", "AAA,BBB")], columns=history.columns)
    original = pd.concat([legacy, history], ignore_index=True)
    extended = extend_membership(original, ledger)
    pd.testing.assert_frame_equal(extended.iloc[:len(original)], original)


def test_renamed_price_series_excludes_later_prices_but_keeps_adjusting_splits(monkeypatch):
    from gabi import history_refresh, identity
    frame = pd.DataFrame({"Close": [20., 21., 11.], "Adj Close": [10., 10.5, 11.],
                          "Stock Splits": [0., 0., 2.]},
                         index=pd.to_datetime(["2025-11-10", "2025-11-11", "2026-01-02"]))

    class Ticker:
        def history(self, **kwargs):
            assert kwargs["auto_adjust"] is False
            assert kwargs["end"] == "2026-01-03"
            return frame

    monkeypatch.setattr(history_refresh.yf, "Ticker", lambda s: Ticker())
    monkeypatch.setattr(identity, "resolve", lambda *a: {"entity_id": None})
    saved = {}
    monkeypatch.setattr(history_refresh.storage, "upsert_prices", lambda s, f, **kw: saved.update(prices=f))
    monkeypatch.setattr(history_refresh.storage, "upsert_splits", lambda s, f, **kw: saved.update(splits=f))
    assert history_refresh.refresh_prices("OLD", "NEW", "2026-01-03", "2025-11-11") == 1
    assert saved["prices"].index.max() == pd.Timestamp("2025-11-10")
    assert saved["splits"] == {"2026-01-02": 2.}


def test_empty_provider_rows_cannot_erase_cached_close(monkeypatch):
    from gabi import history_refresh, identity
    frame = pd.DataFrame({"Close": [10., float("nan")], "Adj Close": [10., float("nan")]},
                         index=pd.to_datetime(["2026-09-21", "2026-09-22"]))

    class Ticker:
        def history(self, **kwargs):
            return frame

    monkeypatch.setattr(history_refresh.yf, "Ticker", lambda s: Ticker())
    monkeypatch.setattr(identity, "resolve", lambda *a: {"entity_id": None})
    saved = {}
    monkeypatch.setattr(history_refresh.storage, "upsert_prices", lambda s, f, **kw: saved.update(prices=f))
    monkeypatch.setattr(history_refresh.storage, "upsert_splits", lambda *a, **kw: None)
    assert history_refresh.refresh_prices("AAA", "AAA", "2026-09-23") == 1
    assert list(saved["prices"].index) == [pd.Timestamp("2026-09-21")]


@pytest.mark.parametrize("different_basis", [False, True])
def test_share_class_cache_requires_matching_adjustments(monkeypatch, different_basis):
    from gabi import history_refresh
    source = pd.DataFrame({"close": [10.] * 7, "adj_close": [10.] * 7},
                          index=pd.date_range("2026-09-17", periods=7))
    target = source.iloc[:5].copy()
    if different_basis:
        target["adj_close"] *= .5
    monkeypatch.setattr(history_refresh.storage, "get_prices", lambda s: source if "." in s else target)
    saved = {}
    monkeypatch.setattr(history_refresh.storage, "upsert_prices", lambda s, f: saved.update({s: f}))
    result = history_refresh.restore_share_class_spelling("2026-09-23")
    if different_basis:
        assert result == saved == {}
    else:
        assert result["BRK-B"]["dates"] == ["2026-09-22"]
        assert len(saved["BF-B"]) == 1
