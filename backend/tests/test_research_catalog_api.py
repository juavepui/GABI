"""Published research metadata is separate from operational and blind data."""

import json

from fastapi.testclient import TestClient

from gabi.infrastructure.settings import Settings
from gabi_api.bootstrap import create_app


def ledger_fixture(root):
    path = root / "docs" / "search-ledger" / "ledger.json"
    path.parent.mkdir(parents=True)
    row = {
        "id": "trial/failed", "family": "published", "configuration_sha256": "a" * 64,
        "specification_ref": "docs/protocol.json", "result_ref": "docs/result.json",
        "observed_sample": {"start": "2016-01-01"}, "planned_sample": None,
        "state": "observed", "decision": "failed_daily_gate", "failures": ["negative_excess"],
        "demonstrated_superiority": False, "reserved_outcome": "MUST_NOT_LEAK",
    }
    ledger = {
        "as_of": "2026-09-29", "scope": "explicit_published_repository_artifacts_only",
        "counts": {"legacy_guard_entries": 1}, "exhaustive_search_history": False,
        "global_error_control_established": False, "limitations": ["Incomplete searches"],
        "diagnostics": [], "unresolved_groups": [], "legacy_entries": [row],
        "additional_observed_records": [],
    }
    path.write_text(json.dumps(ledger), encoding="utf-8")
    return path


def test_catalog_reads_published_fixture_without_database_or_reserve(tmp_path):
    published = ledger_fixture(tmp_path)
    data = tmp_path / "data"
    with TestClient(create_app(Settings(data), published_ledger=published)) as api:
        overview = api.get("/api/v1/research/overview")
        assert overview.status_code == 200, overview.text
        assert overview.json()["exhaustive_search_history"] is False
        trials = api.get("/api/v1/research/trials?limit=1")
        assert trials.status_code == 200, trials.text
        assert trials.json()["total"] == 1
        assert trials.json()["items"][0]["failures"] == ["negative_excess"]
        assert "MUST_NOT_LEAK" not in trials.text
        assert api.get("/api/v1/research/trials?family=other").json()["total"] == 0
        assert api.get("/api/v1/research/trials?limit=51").status_code == 422
    assert not data.exists()


def test_catalog_absent_and_malformed_fail_closed_without_initializing_data(tmp_path):
    data = tmp_path / "data"
    published = tmp_path / "docs" / "search-ledger" / "ledger.json"
    with TestClient(create_app(Settings(data), published_ledger=published)) as api:
        assert api.get("/api/v1/research/overview").status_code == 503
        path = ledger_fixture(tmp_path)
        path.write_text('{"scope":"unpublished-reserve"}', encoding="utf-8")
        assert api.get("/api/v1/research/trials").status_code == 503
    assert not data.exists()
