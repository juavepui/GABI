from datetime import UTC, date, datetime

from gabi.domain.market import fred
from gabi.infrastructure.legacy.fred import fred_operation
from gabi.infrastructure.providers.fred import FredSource
from gabi.infrastructure.storage.fred import SqliteFred


def _isolate_db(tmp_path, monkeypatch):
    from gabi import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    monkeypatch.setattr(config, "FRED_KEY_PATH", tmp_path / "fred_api_key.txt")


def _series(tmp_path):
    return SqliteFred(tmp_path / "gabi.db", lambda: datetime.now(UTC))


def _snapshot(tmp_path):
    return fred.snapshot(fred.SERIES, {sid: _series(tmp_path).history(sid) for sid in fred.SERIES})


def test_ensure_macro_data_without_api_key_does_not_hit_network(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    result = fred_operation(tmp_path)()
    assert result == {"ok": False, "reason": "no_api_key", "refreshed": 0, "failed": {}}


def test_ensure_macro_data_persists_failures_to_update_errors(tmp_path, monkeypatch):
    from gabi import config, storage
    _isolate_db(tmp_path, monkeypatch)
    config.save_fred_key("fake-key")

    def _boom(self, series_id, api_key, units="lin", limit=260, **options):
        raise RuntimeError("FRED no responde")

    monkeypatch.setattr(FredSource, "fetch", _boom)
    result = fred_operation(tmp_path)(force=True)

    assert result["failed"]  # todas las series fallan
    errors = storage.get_recent_update_errors(source="fred_macro")
    assert len(errors) == len(result["failed"])
    assert set(errors["symbol"]) == set(result["failed"])


def test_upsert_and_get_series_history_roundtrip(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    obs = [("2026-09-01", 4.2), ("2026-08-01", 4.1), ("2026-07-01", 4.0)]
    _series(tmp_path).upsert("DGS10", obs)

    history = _series(tmp_path).history("DGS10")
    assert list(history["value"]) == [4.0, 4.1, 4.2]  # ordenado ascendente por fecha

    fetched_at = _series(tmp_path).fetched_at_all()
    assert "DGS10" in fetched_at


def test_get_snapshot_handles_missing_series_gracefully(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    snapshot = _snapshot(tmp_path)
    assert len(snapshot) == len(fred.SERIES)
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
    _series(tmp_path).upsert("DGS10", obs)
    snapshot = _snapshot(tmp_path)
    row = snapshot[snapshot["series_id"] == "DGS10"].iloc[0]
    assert row["latest_value"] == 4.0
    assert row["latest_date"] == "2026-09-01"
    assert row["change_3m"] is not None
    assert round(row["change_3m"], 2) == round(4.0 - 3.2, 2)  # frente a ~90 días antes (junio)


def test_fetch_series_parses_observations_and_skips_missing_values(monkeypatch):
    import json

    import requests

    body = json.dumps({"count": 900, "observations": [
        {"date": "2026-09-01", "value": "4.20"},
        {"date": "2026-08-01", "value": "."},  # FRED marca huecos así
        {"date": "2026-07-01", "value": "4.00"},
    ]}).encode()

    class FakeResponse:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def iter_content(self, size):
            yield body

    requests_seen = []
    monkeypatch.setattr(requests, "get", lambda url, **kwargs: requests_seen.append(kwargs) or FakeResponse())
    # More observations than the limit keep the historical newest-first truncation.
    assert FredSource().fetch("DGS10", "fake-key", require_complete=False) == [("2026-09-01", 4.2), ("2026-07-01", 4.0)]
    assert requests_seen[0]["params"]["limit"] == 260 and requests_seen[0]["timeout"] == 20


def test_parse_next_release_date_returns_earliest_future_date():
    payload = {"release_dates": [
        {"release_id": 10, "date": "2026-08-14"},  # pasado
        {"release_id": 10, "date": "2026-10-14"},
        {"release_id": 10, "date": "2026-11-10"},
    ]}
    assert fred.parse_next_release_date(payload, date(2026, 9, 20)) == date(2026, 10, 14)


def test_parse_next_release_date_includes_today_as_valid():
    payload = {"release_dates": [{"release_id": 10, "date": "2026-09-20"}]}
    assert fred.parse_next_release_date(payload, date(2026, 9, 20)) == date(2026, 9, 20)


def test_parse_next_release_date_returns_none_when_no_future_dates():
    payload = {"release_dates": [{"release_id": 10, "date": "2026-01-01"}]}
    assert fred.parse_next_release_date(payload, date(2026, 9, 20)) is None


def test_parse_next_release_date_empty_payload_returns_none():
    assert fred.parse_next_release_date({}, date(2026, 9, 20)) is None
    assert fred.parse_next_release_date({"release_dates": []}, date(2026, 9, 20)) is None


def test_fetch_next_release_date_returns_none_for_unmapped_series():
    assert FredSource().next_release("DGS10", "fake-key", date.today()) is None
