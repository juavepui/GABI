"""The React view uses only copied, sealed, explicitly published artifacts."""

import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from gabi import config, evidence_catalog, factor_sector_stability
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.published_factors import FilePublishedFactors
from gabi_api.bootstrap import create_app

SOURCE_ROOT = Path(__file__).resolve().parents[2]


def copied_publications(root: Path) -> None:
    source = FilePublishedFactors(SOURCE_ROOT)
    for path in source._paths():
        if not path.is_relative_to(SOURCE_ROOT / "docs"):
            continue  # The frozen code is read from the installed backend, not copied as data.
        destination = root / path.relative_to(SOURCE_ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)


def test_published_factors_match_streamlit_artifacts_and_are_cached(tmp_path, monkeypatch):
    copied_publications(tmp_path)
    monkeypatch.setattr(config, "BASE_DIR", tmp_path)
    monkeypatch.setattr(factor_sector_stability, "OUTPUT", tmp_path / "docs" / "factor-zoo-sector")
    legacy = evidence_catalog.load()
    assert legacy["available"], legacy["errors"]
    sector = factor_sector_stability.load_saved(legacy["sources"]["factor-zoo-sector"]["sha256"])

    app = create_app(Settings(tmp_path / "data"))
    source = app.state.published_factors.source
    calls = 0
    original = source._load_verified

    def counted():
        nonlocal calls
        calls += 1
        return original()

    monkeypatch.setattr(source, "_load_verified", counted)
    with TestClient(app) as client:
        response = client.get("/api/v1/research/published-factors")
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["status"] == "RETROSPECTIVE_DESCRIPTIVE"
        assert result["independent_advantage_demonstrated"] is False
        assert result["holm_significant_count"] == 0
        assert result["n_dates"] == sector["n_dates"]
        assert len(result["factors"]) == len(legacy["factors"]) == 13
        for row in result["factors"]:
            expected = legacy["factors"][row["metric"]]
            assert (row["ic_mean"], row["icir"], row["p_holm"], row["classification"],
                    row["n_periods"], row["q_spread"]) == (
                        expected["media"], expected["icir"], expected["p_holm"],
                        expected["classification"], expected["n_periods"], expected["q_spread"])
            assert {part["division"]: part["ic_mean"] for part in row["sic_divisions"]} == {
                name: part["ic_mean"] for name, part in sector["factors"][row["metric"]].items()}
        assert result["n_eligible"] == sum(row["n_eligible"] for row in sector["coverage"]
                                           if row["stratum"] == "all")
        assert result["n_classified"] == sum(row["n_classified"] for row in sector["coverage"]
                                             if row["stratum"] == "all")
        assert len(result["coverage"]) == len(sector["coverage"])
        assert client.get("/api/v1/research/published-factors").status_code == 200
        assert calls == 1  # Stamps only; no repeated full hashes on render.
        export = client.get("/api/v1/research/published-factors/exports/coverage.csv")
        assert export.status_code == 200
        assert export.text == (tmp_path / "docs/factor-zoo-sector/coverage.csv").read_text(encoding="utf-8")
        assert client.get("/api/v1/research/published-factors/exports/assignments.csv").status_code == 404
    assert not (tmp_path / "data").exists()


def test_published_factors_fail_closed_after_artifact_changes(tmp_path):
    copied_publications(tmp_path)
    with TestClient(create_app(Settings(tmp_path / "data"))) as client:
        assert client.get("/api/v1/research/published-factors").status_code == 200
        csv = tmp_path / "docs/factor-zoo-sector/coverage.csv"
        csv.write_text(csv.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")
        failure = client.get("/api/v1/research/published-factors")
        assert failure.status_code == 503
        assert failure.json()["error"]["code"] == "published_factors_unavailable"
        assert client.get("/api/v1/research/published-factors/exports/coverage.csv").status_code == 503
    assert not (tmp_path / "data").exists()
