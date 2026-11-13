"""A published trial shows its configuration and its published result, read from verified artifacts."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gabi.application.errors import QueryError
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.published_research import FilePublishedArtifacts, FilePublishedLedger
from gabi_api.bootstrap import create_app

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "docs" / "search-ledger" / "ledger.json"


@pytest.fixture
def api(tmp_path):
    with TestClient(create_app(Settings(tmp_path), published_ledger=LEDGER)) as client:
        yield client


def _rows(rows):
    return {row["key"]: row for row in rows}


def test_v1_trial_shows_its_configuration_returns_and_published_statistics(api):
    body = api.get("/api/v1/research/trial", params={"id": "v1/top10_q"}).json()
    config = _rows(body["configuration"])
    assert config["top_n"]["value"] == 10 and config["cost_bps"]["unit"] == "number"
    assert config["value"]["unit"] == "fraction"  # Weights are shown as percentages.
    assert len(body["series"]) == 36 and body["series"][0]["date"] == "2016-10-03"
    stats = _rows(body["statistics"])
    assert stats["psr"]["unit"] == "fraction" and stats["n"]["value"] == 36
    assert body["result_verified"] is True


def test_json_results_are_flattened_with_units_and_pending_trials_have_none(api):
    rotation = _rows(api.get("/api/v1/research/trial", params={"id": "rotation/hurdle_5"}).json()["result"])
    assert rotation["cagr_net"]["unit"] == "fraction" and rotation["final_value"]["unit"] == "USD"
    pending = api.get("/api/v1/research/trial", params={"id": "value/prospective"}).json()
    assert pending["result"] == [] and pending["series"] is None and pending["result_verified"] is None
    assert pending["result_note"].startswith("Ensayo prospectivo")
    assert api.get("/api/v1/research/trial", params={"id": "nope"}).status_code == 404


@pytest.mark.parametrize("ref", ["docs/../backend/pyproject.toml", "data/gabi.db", "docs/search-ledger/README.md"])
def test_artifacts_outside_published_json_or_csv_are_refused(ref):
    artifacts = FilePublishedArtifacts(ROOT, FilePublishedLedger(LEDGER))
    with pytest.raises(QueryError):
        artifacts.read(ref)
