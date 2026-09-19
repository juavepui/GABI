import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gabi import macro


def _isolate_db(tmp_path, monkeypatch):
    from gabi import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test_gabi.db")
    monkeypatch.setattr(config, "FRED_KEY_PATH", tmp_path / "fred_api_key.txt")


def test_ensure_macro_data_without_api_key_does_not_hit_network(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    result = macro.ensure_macro_data()
    assert result == {"ok": False, "reason": "no_api_key", "refreshed": 0, "failed": {}}


def test_ensure_macro_data_persists_failures_to_update_errors(tmp_path, monkeypatch):
    from gabi import config, storage
    _isolate_db(tmp_path, monkeypatch)
    config.FRED_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.save_fred_key("fake-key")

    def _boom(series_id, api_key, units="lin"):
        raise RuntimeError("FRED no responde")

    monkeypatch.setattr(macro, "fetch_series", _boom)
    result = macro.ensure_macro_data(force=True)

    assert result["failed"]  # todas las series fallan
    errors = storage.get_recent_update_errors(source="fred_macro")
    assert len(errors) == len(result["failed"])
    assert set(errors["symbol"]) == set(result["failed"])


def test_upsert_and_get_series_history_roundtrip(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    obs = [("2026-09-01", 4.2), ("2026-08-01", 4.1), ("2026-07-01", 4.0)]
    macro.upsert_series("DGS10", obs)

    history = macro.get_series_history("DGS10")
    assert list(history["value"]) == [4.0, 4.1, 4.2]  # ordenado ascendente por fecha

    fetched_at = macro.get_all_fetched_at()
    assert "DGS10" in fetched_at


def test_get_snapshot_handles_missing_series_gracefully(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    snapshot = macro.get_snapshot()
    assert len(snapshot) == len(macro.SERIES)
    assert snapshot["latest_value"].isna().all()


def test_get_snapshot_computes_3m_change(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    # ~4 meses de datos mensuales para que haya una observación a más de 90 días.
    obs = [
        ("2026-05-01", 3.0),
        ("2026-06-01", 3.2),
        ("2026-07-01", 3.4),
        ("2026-08-01", 3.6),
        ("2026-09-01", 4.0),
    ]
    macro.upsert_series("DGS10", obs)
    snapshot = macro.get_snapshot()
    row = snapshot[snapshot["series_id"] == "DGS10"].iloc[0]
    assert row["latest_value"] == 4.0
    assert row["latest_date"] == "2026-09-01"
    assert row["change_3m"] is not None
    assert round(row["change_3m"], 2) == round(4.0 - 3.2, 2)  # frente a ~90 días antes (junio)


def test_fetch_series_parses_observations_and_skips_missing_values():
    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "observations": [
                    {"date": "2026-09-01", "value": "4.20"},
                    {"date": "2026-08-01", "value": "."},  # FRED marca huecos así
                    {"date": "2026-07-01", "value": "4.00"},
                ]
            }

    import gabi.macro as macro_module

    def fake_get(url, params=None, timeout=None):
        return FakeResponse()

    orig_get = macro_module.requests.get
    macro_module.requests.get = fake_get
    try:
        obs = macro.fetch_series("DGS10", api_key="fake-key")
    finally:
        macro_module.requests.get = orig_get

    assert obs == [("2026-09-01", 4.2), ("2026-07-01", 4.0)]
