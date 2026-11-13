"""Published Research Lab audits are verified, cached by file metadata and shown as Streamlit did."""

import shutil
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from retired_block_bootstrap_ui import fraction_table

from gabi import block_bootstrap, factor_benchmark, factor_stability, overfitting_audit, rank_stability
from gabi.infrastructure.legacy import saved_audits as legacy
from gabi.infrastructure.settings import Settings
from gabi_api.bootstrap import create_app

REPO = Path(__file__).resolve().parents[2]
COPIED = ("overfitting-audit", "factor-benchmark", "factor-stability")


@pytest.fixture
def root(tmp_path):
    """Copies of the small published audits; block bootstrap and rank stability have a fixed location."""
    for name in COPIED:
        shutil.copytree(REPO / "docs" / name, tmp_path / "docs" / name)
    data = tmp_path / "data"
    data.mkdir()
    (data / "app_mode.json").write_text('{"mode":"RESEARCH"}')
    return tmp_path


def _client(root, saved_root=None):
    return TestClient(create_app(Settings(root / "data"), saved_audits_root=saved_root or root))


def test_overfitting_audit_matches_the_streamlit_expander(root):
    audit, _ = overfitting_audit.load_audit(REPO / "docs" / "overfitting-audit")
    with _client(root) as client:
        body = client.get("/api/v1/research/saved-audits/overfitting").json()
        csv = client.get("/api/v1/research/saved-audits/overfitting-audit/files/returns.csv")
    primary = audit["primary"]
    assert (body["pbo"], body["dsr"], body["n_trials"], body["n_obs"]) == (
        primary["pbo"]["pbo"], primary["dsr"]["dsr"], primary["n_trials"], primary["n_obs"])
    assert [row["trial_id"] for row in body["trials"]] == [trial["trial_id"] for trial in audit["catalog"]]
    assert body["trials"][0]["sharpe"] == audit["including_cost_sensitivity"]["trial_statistics"][
        audit["catalog"][0]["trial_id"]]["sharpe_anualizado"]
    assert csv.content == (REPO / "docs" / "overfitting-audit" / "returns.csv").read_bytes()


def test_factor_audits_match_their_loaders(root):
    benchmark = factor_benchmark.load_audit(REPO / "docs" / "factor-benchmark")
    stability = factor_stability.load_audit(REPO / "docs" / "factor-stability")
    with _client(root) as client:
        saved_benchmark = client.get("/api/v1/research/saved-audits/factor-benchmark").json()
        saved_stability = client.get("/api/v1/research/saved-audits/factor-stability").json()
    assert saved_benchmark["expanding"]["n_obs"] == benchmark["expanding"]["n_obs"]
    assert saved_benchmark["in_sample"]["active"] == benchmark["in_sample"]["active"]
    assert saved_stability["full"]["coef"] == stability["full"]["coef"]
    assert len(saved_stability["rolling"]) == len(stability["rolling"])


def test_block_bootstrap_and_rank_stability_match_saved_artifacts(root):
    saved = block_bootstrap.load_saved()
    dataset = next(iter(saved["datasets"]))
    distribution = pd.read_csv(block_bootstrap.OUTPUT / f"{dataset}-distributions.csv")
    result = rank_stability.load_saved()
    date = result["dates"][1]["date"]
    with _client(root, REPO) as client:
        boot = client.get("/api/v1/research/saved-audits/block-bootstrap", params={"dataset": dataset}).json()
        ranks = client.get("/api/v1/research/saved-audits/rank-stability", params={"date": date}).json()
        overview = client.get("/api/v1/research/saved-audits").json()
    audit = saved["datasets"][dataset]
    primary = audit["runs"][str(audit["primary_block"])]
    assert [row["fraction"] for row in boot["view"]["fractions"]] == \
        fraction_table(primary)["Fracción bootstrap"].tolist()
    shown = block_bootstrap.interval_table(audit)
    assert [row["observed"] for row in boot["view"]["intervals"]] == pytest.approx(shown["observed"].tolist(),
                                                                                    nan_ok=True)
    assert boot["view"]["n_boot"] == primary["n_boot"] and len(distribution)
    assert [item["id"] for item in boot["unavailable"]] == list(saved.get("unavailable_datasets", {}))
    companies = pd.read_csv(rank_stability.OUTPUT / "companies.csv")
    expected = companies.loc[companies.date == date]
    assert [row["symbol"] for row in ranks["companies"]] == expected["symbol"].tolist()
    assert ranks["stability_score"] == result["stability_score"] and ranks["n_dates"] == len(result["dates"])
    assert all(overview.values())


def test_verification_is_cached_until_a_file_changes(root, monkeypatch):
    calls = []
    original = legacy.load_factor_stability
    monkeypatch.setattr(legacy, "load_factor_stability", lambda path: calls.append(path) or original(path))
    from gabi.infrastructure.storage import saved_audits as storage
    monkeypatch.setitem(storage.AUDITS, "factor-stability", ("audit.json", legacy.load_factor_stability))
    with _client(root) as client:
        for _ in range(3):
            assert client.get("/api/v1/research/saved-audits/factor-stability").status_code == 200
        assert len(calls) == 1
        path = root / "docs" / "factor-stability" / "coefficients.csv"
        path.write_bytes(path.read_bytes() + b"\n")
        response = client.get("/api/v1/research/saved-audits/factor-stability")
    assert len(calls) == 2
    assert response.status_code == 503 and "coefficients.csv" in response.json()["error"]["message"]


def test_missing_audits_downloads_and_mode(root, tmp_path_factory):
    empty = tmp_path_factory.mktemp("empty")
    (empty / "data").mkdir()
    (empty / "data" / "app_mode.json").write_text('{"mode":"RESEARCH"}')
    with _client(empty) as client:
        assert not any(client.get("/api/v1/research/saved-audits").json().values())
        assert client.get("/api/v1/research/saved-audits/overfitting").status_code == 404
    with _client(root) as client:
        assert client.get("/api/v1/research/saved-audits/overfitting-audit/files/README.md").status_code == 404
        assert client.get("/api/v1/research/saved-audits/data/files/gabi.db").status_code == 404
        (root / "data" / "app_mode.json").write_text('{"mode":"INVESTOR"}')
        assert client.get("/api/v1/research/saved-audits/overfitting").status_code == 403
