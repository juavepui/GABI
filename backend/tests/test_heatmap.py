"""Mapa de calor del universo (#311): the ranking grouped by sector, with bands and reasons; read-only."""

import hashlib

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from market_fixture import TODAY, seed_fixture

from gabi.domain.market import heatmap
from gabi.infrastructure.settings import Settings
from gabi_api.bootstrap import create_app


@pytest.mark.parametrize(("score", "band"), [(80.0, "very_high"), (79.9, "high"), (70.0, "high"),
                                             (69.9, "medium"), (40.0, "medium"), (39.9, "low"), (30.0, "low"),
                                             (29.9, "very_low"), (None, "none")])
def test_bands(score, band):
    assert heatmap.band(score) == band


def test_groups_by_sector_with_reasons_and_the_top_fifth():
    table = pd.DataFrame({
        "name": ["A", "B", "C", "D", "E"], "sector": ["Tech", "Tech", "Health", "Health", None],
        "composite_score": [90.0, 75.0, 50.0, None, 20.0], "market_cap": [3e12, 1e11, 5e10, 2e10, float("nan")],
    }, index=["AAA", "BBB", "CCC", "DDD", "EEE"])
    result = heatmap.build(table)
    companies = {item["symbol"]: item for item in result["companies"]}
    assert companies["AAA"]["rank"] == 1 and companies["AAA"]["band"] == "very_high"
    assert companies["DDD"]["rank"] is None and companies["DDD"]["band"] == "none"
    assert companies["DDD"]["reason"].startswith("Sin puntuación")
    assert companies["EEE"]["sector"] == "Sin sector" and companies["EEE"]["reason"].startswith("Sin valor en bolsa")
    assert result["scored"] == 4 and result["top_count"] == 1  # ceil(4 × 0,20).
    sectors = {item["sector"]: item for item in result["sectors"]}
    assert sectors["Tech"] == {"sector": "Tech", "companies": 2, "scored": 2, "mean_score": 82.5, "in_top": 1,
                               "market_cap": 3.1e12}
    assert sectors["Health"]["scored"] == 1 and sectors["Health"]["mean_score"] == 50.0
    assert [item["sector"] for item in result["sectors"]] == ["Tech", "Health", "Sin sector"]  # Best mean first.
    assert result["bands"][-1] == {"band": "very_low", "min_score": None}


def test_api_returns_the_same_ranking_without_writing(tmp_path):
    seed_fixture(tmp_path, companies=30)
    before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in tmp_path.iterdir()
              if path.is_file()}
    with TestClient(create_app(Settings(tmp_path), today=lambda: TODAY)) as api:
        body = api.get("/api/v1/market/heatmap").json()
        ranking = api.get("/api/v1/ranking", params={"limit": 5}).json()
    after = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in tmp_path.iterdir()
             if path.is_file()}
    assert after == before
    assert len(body["companies"]) == ranking["data"]["universe_count"]
    best = next(item for item in body["companies"] if item["rank"] == 1)
    assert best["symbol"] == ranking["items"][0]["symbol"]
    assert sum(item["companies"] for item in body["sectors"]) == len(body["companies"])
