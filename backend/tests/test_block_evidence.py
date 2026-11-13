"""Evidence of the score blocks (#185): grouped from the published Factor Zoo, never recomputed."""

import json

import pytest
from fastapi.testclient import TestClient
from test_published_factors_api import copied_publications

from gabi.domain.market import block_evidence
from gabi.domain.market.model_policy import FROZEN_WEIGHTS
from gabi.domain.market.scoring import SCORE_METRICS
from gabi.infrastructure.settings import Settings
from gabi_api.bootstrap import create_app

FACTORS = {"pe": {"classification": "indicio", "media": 0.03, "p_holm": 0.27},
           "pb": {"classification": "sin_evidencia", "media": -0.01, "p_holm": 1.0},
           "ev_ebitda": {"classification": "requiere_OOS", "media": 0.05, "p_holm": 0.01},
           "momentum_12m": {"classification": "sin_evidencia", "media": -0.014, "p_holm": 1.0}}


def test_a_block_shows_its_strongest_classification_with_how_many_metrics_reached_it():
    value, quality, momentum, risk = block_evidence.blocks(FACTORS)
    assert value["classification"] == "requiere_OOS" and value["metrics_at_classification"] == 1
    assert value["metrics_with_evidence"] == 2 and value["metrics_published"] == 3
    assert value["ic_mean"] == pytest.approx((0.03 - 0.01 + 0.05) / 3) and value["holm_significant"] == 1
    assert value["classification_label"] == "Requiere validación fuera de muestra"
    # Unpublished metrics are listed, never counted as evidence nor as its absence.
    assert momentum["classification"] == "sin_evidencia" and momentum["metrics_published"] == 1
    assert momentum["metrics_with_evidence"] == 0 and momentum["ic_mean"] == pytest.approx(-0.014)
    assert [row["published"] for row in momentum["metrics"]] == [True, False, False]
    assert quality["classification"] is None and quality["ic_mean"] is None and quality["metrics_published"] == 0
    assert [row["metric"] for row in risk["metrics"]] == SCORE_METRICS["risk"]


def test_an_unknown_published_classification_is_rejected():
    with pytest.raises(ValueError, match="desconocida"):
        block_evidence.blocks({"pe": {"classification": "fuerte", "media": 0.1}})


def test_the_contract_exposes_each_block_evidence_and_the_catalog_version(tmp_path):
    copied_publications(tmp_path)
    zoo = tmp_path / "docs" / "factor-zoo" / "resultado.json"
    published = json.loads(zoo.read_text(encoding="utf-8"))["factors"]
    manifest = json.loads((tmp_path / "docs" / "evidence-confidence" / "sources.json").read_text(encoding="utf-8"))
    with TestClient(create_app(Settings(tmp_path / "data"))) as client:  # Investor mode by default.
        response = client.get("/api/v1/score-blocks/evidence")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["catalog"] == "factor-zoo"
        # The version is the seal of the published manifest, the same hash Factor Lab shows.
        assert body["catalog_sha256"] == manifest["artifacts"]["factor-zoo"]["sha256"]
        assert body["catalog_sha256"] == client.get("/api/v1/research/published-factors").json()["factor_zoo_sha256"]
        assert body["status"] == "RETROSPECTIVE_DESCRIPTIVE" and body["independent_advantage_demonstrated"] is False
        assert [row["block"] for row in body["blocks"]] == list(SCORE_METRICS)
        assert {row["block"]: row["frozen_weight"] for row in body["blocks"]} == dict(FROZEN_WEIGHTS)
        for row in body["blocks"]:
            for metric in row["metrics"]:
                assert metric["classification"] == published[metric["metric"]]["classification"]
                assert metric["ic_mean"] == published[metric["metric"]]["media"]
        momentum = next(row for row in body["blocks"] if row["block"] == "momentum")
        assert momentum["classification"] == "sin_evidencia" and momentum["metrics_with_evidence"] == 0
        assert body["holm_significant_count"] == 0
        contract = client.get("/openapi.json").json()
        assert "/api/v1/score-blocks/evidence" in contract["paths"]
    assert not (tmp_path / "data").exists()  # Reading the catalog writes nothing.
