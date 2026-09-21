import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gabi import config, estimates, storage


def _isolate_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")


def _earnings_estimate_df():
    return pd.DataFrame(
        {"avg": [1.98, 2.90], "low": [1.93, 2.56], "high": [2.07, 3.42], "numberOfAnalysts": [27, 21]},
        index=["0q", "+1q"],
    )


def _revenue_estimate_df():
    return pd.DataFrame(
        {"avg": [113_600_000_000.0], "low": [112_200_000_000.0], "high": [117_200_000_000.0]}, index=["0q"],
    )


def _eps_revisions_df():
    return pd.DataFrame(
        {"upLast7days": [1, 0], "upLast30days": [7, 1], "downLast30days": [14, 1], "downLast7Days": [0, 1]},
        index=["0q", "+1q"],
    )


def test_parse_estimate_snapshot_normalizes_real_shape_tables():
    rows = estimates.parse_estimate_snapshot(
        "AAPL", _earnings_estimate_df(), _revenue_estimate_df(), _eps_revisions_df(), "2026-09-21T12:00:00+00:00",
    )
    by_period = {r["period"]: r for r in rows}
    assert set(by_period) == {"0q", "+1q"}
    q0 = by_period["0q"]
    assert q0["eps_avg"] == 1.98
    assert q0["eps_dispersion_pct"] == pytest.approx((2.07 - 1.93) / 1.98)
    assert q0["revenue_avg"] == 113_600_000_000.0
    assert q0["revised_up_30d"] == 7
    assert q0["revised_down_30d"] == 14
    assert q0["source"] == estimates.SOURCE
    # +1q no tiene fila en revenue_estimate_df -- debe quedar en None, no reventar.
    q1 = by_period["+1q"]
    assert q1["revenue_avg"] is None


def test_parse_estimate_snapshot_empty_tables_returns_no_rows():
    empty = pd.DataFrame()
    assert estimates.parse_estimate_snapshot("AAPL", empty, empty, empty, "2026-09-21T12:00:00+00:00") == []


def test_parse_estimate_snapshot_handles_none_tables():
    assert estimates.parse_estimate_snapshot("AAPL", None, None, None, "2026-09-21T12:00:00+00:00") == []


def test_store_and_get_estimate_history_roundtrip(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    rows = estimates.parse_estimate_snapshot(
        "AAPL", _earnings_estimate_df(), _revenue_estimate_df(), _eps_revisions_df(), "2026-09-21T12:00:00+00:00",
    )
    estimates.store_estimate_snapshot(rows)
    history = estimates.get_estimate_history("AAPL", period="0q")
    assert len(history) == 1
    assert history.iloc[0]["eps_avg"] == 1.98


def test_store_estimate_snapshot_is_idempotent_on_reinsert(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    rows = estimates.parse_estimate_snapshot(
        "AAPL", _earnings_estimate_df(), _revenue_estimate_df(), _eps_revisions_df(), "2026-09-21T12:00:00+00:00",
    )
    estimates.store_estimate_snapshot(rows)
    estimates.store_estimate_snapshot(rows)
    assert len(estimates.get_estimate_history("AAPL", period="0q")) == 1


def test_store_estimate_snapshot_empty_list_is_noop(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    estimates.store_estimate_snapshot([])
    assert estimates.get_estimate_history("AAPL").empty


def test_latest_estimate_snapshot_returns_none_without_history(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    assert estimates.latest_estimate_snapshot("AAPL") is None


def test_latest_estimate_snapshot_returns_most_recent_capture(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    old = estimates.parse_estimate_snapshot("AAPL", _earnings_estimate_df(), pd.DataFrame(), pd.DataFrame(),
                                            "2026-08-01T00:00:00+00:00")
    new = estimates.parse_estimate_snapshot("AAPL", _earnings_estimate_df(), pd.DataFrame(), pd.DataFrame(),
                                            "2026-09-21T00:00:00+00:00")
    estimates.store_estimate_snapshot(old + new)
    latest = estimates.latest_estimate_snapshot("AAPL", period="0q")
    assert latest["captured_at"] == "2026-09-21T00:00:00+00:00"


def _seed_history(symbol, capture_dates_eps):
    rows = []
    for captured_at, eps_avg in capture_dates_eps:
        rows.append({
            "symbol": symbol, "captured_at": captured_at, "period": "0q",
            "eps_avg": eps_avg, "eps_low": eps_avg - 0.1, "eps_high": eps_avg + 0.1, "eps_analysts": 20,
            "eps_dispersion_pct": 0.2 / eps_avg, "revenue_avg": None, "revenue_low": None, "revenue_high": None,
            "revised_up_7d": 0, "revised_down_7d": 0, "revised_up_30d": 0, "revised_down_30d": 0,
            "source": estimates.SOURCE,
        })
    estimates.store_estimate_snapshot(rows)


def test_compute_revision_none_without_old_enough_baseline():
    history = pd.DataFrame([{"captured_at": "2026-09-15T00:00:00+00:00", "eps_avg": 2.0}])
    assert estimates.compute_revision(history, lookback_days=30, as_of=date(2026, 9, 21)) is None


def test_compute_revision_none_with_empty_history():
    assert estimates.compute_revision(pd.DataFrame(), lookback_days=30) is None
    assert estimates.compute_revision(None, lookback_days=30) is None


def test_compute_revision_computes_change_from_own_captured_history(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    _seed_history("AAPL", [("2026-06-01T00:00:00+00:00", 2.00), ("2026-09-20T00:00:00+00:00", 2.20)])
    history = estimates.get_estimate_history("AAPL", period="0q")
    result = estimates.compute_revision(history, lookback_days=90, as_of=date(2026, 9, 21))
    assert result is not None
    assert round(result["change"], 4) == 0.20
    assert round(result["change_pct"], 4) == 0.10
    assert result["actual_lookback_days"] == 111


def test_compute_revision_ignores_captures_after_as_of_no_look_ahead(tmp_path, monkeypatch):
    """El propio nucleo de 'no usar el consenso actual para reconstruir el
    pasado': una captura fechada DESPUES de `as_of` no debe usarse como si
    fuera la 'ultima conocida' en ese momento."""
    _isolate_db(tmp_path, monkeypatch)
    _seed_history("AAPL", [
        ("2026-01-01T00:00:00+00:00", 1.50),
        ("2026-04-01T00:00:00+00:00", 1.80),
        ("2026-12-01T00:00:00+00:00", 5.00),  # "futuro" respecto al as_of usado abajo
    ])
    history = estimates.get_estimate_history("AAPL", period="0q")
    result = estimates.compute_revision(history, lookback_days=60, as_of=date(2026, 4, 15))
    assert result is not None
    assert result["current_eps_avg"] == 1.80  # NO 5.00 -- esa captura es "futura" respecto a as_of
    assert result["current_captured_at"] == "2026-04-01T00:00:00+00:00"


def test_revision_since_reads_from_storage(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    _seed_history("MSFT", [("2026-06-01T00:00:00+00:00", 3.00), ("2026-09-20T00:00:00+00:00", 3.30)])
    result = estimates.revision_since("MSFT", lookback_days=90, as_of=date(2026, 9, 21))
    assert result is not None
    assert round(result["change_pct"], 4) == 0.10


def test_evaluate_estimate_revision_signal_insufficient_data_when_empty(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    result = estimates.evaluate_estimate_revision_signal()
    assert result["status"] == "insufficient_data"
    assert result["batches_available"] == 0


def _seed_estimate_batch(captured_at, symbols_ranks):
    rows = []
    for symbol, rank in symbols_ranks:
        rows.append({
            "symbol": symbol, "captured_at": captured_at, "period": "0q",
            "eps_avg": 1.0, "eps_low": 0.9, "eps_high": 1.1, "eps_analysts": 10, "eps_dispersion_pct": 0.2,
            "revenue_avg": None, "revenue_low": None, "revenue_high": None,
            "revised_up_7d": 0, "revised_down_7d": 0, "revised_up_30d": rank, "revised_down_30d": 0,
            "source": estimates.SOURCE,
        })
    estimates.store_estimate_snapshot(rows)


def _seed_growth_prices(symbols_ranks, business_days):
    for symbol, rank in symbols_ranks:
        growth_rate = -0.004 + 0.0015 * rank
        closes = [100.0 * (1 + growth_rate) ** i for i in range(len(business_days))]
        storage.upsert_prices(symbol, pd.DataFrame({
            "Open": closes, "High": closes, "Low": closes, "Close": closes, "Adj Close": closes,
            "Volume": [1] * len(closes),
        }, index=business_days))


def test_evaluate_estimate_revision_signal_detects_monotonic_signal(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    monkeypatch.setattr(estimates, "MIN_SYMBOLS_PER_BATCH", 8)

    symbols_ranks = [(chr(ord("A") + i), i) for i in range(8)]  # A:0 .. H:7, revision creciente con el precio futuro
    business_days = pd.date_range("2024-01-01", periods=110, freq="B")
    _seed_growth_prices(symbols_ranks, business_days)

    captured_dates = ["2024-01-03", "2024-01-18", "2024-02-02", "2024-02-20", "2024-03-06", "2024-03-21"]
    for d in captured_dates:
        _seed_estimate_batch(f"{d}T00:00:00+00:00", symbols_ranks)

    result = estimates.evaluate_estimate_revision_signal(horizons_months=(1,), n_quantiles=2)
    assert result["status"] == "ok"
    row = result["summary"].iloc[0]
    assert row["ic_mean"] == pytest.approx(1.0, rel=0.02)
    assert row["n_periods"] >= 4


def test_evaluate_estimate_revision_signal_insufficient_when_too_few_batches(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    monkeypatch.setattr(estimates, "MIN_SYMBOLS_PER_BATCH", 8)
    symbols_ranks = [(chr(ord("A") + i), i) for i in range(8)]
    business_days = pd.date_range("2024-01-01", periods=60, freq="B")
    _seed_growth_prices(symbols_ranks, business_days)
    _seed_estimate_batch("2024-01-03T00:00:00+00:00", symbols_ranks)
    _seed_estimate_batch("2024-01-18T00:00:00+00:00", symbols_ranks)

    result = estimates.evaluate_estimate_revision_signal(horizons_months=(1,), n_quantiles=2)
    assert result["status"] == "insufficient_data"
    assert result["batches_available"] == 2
