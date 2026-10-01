"""The old Ficha AI prompt: the same text from the ranking row and score breakdown, read-only."""

import hashlib

import pytest
from fastapi.testclient import TestClient
from market_fixture import TODAY, seed_fixture

from gabi import ai_prompt, app_mode, scoring
from gabi.infrastructure.settings import Settings
from gabi_api.bootstrap import create_app


@pytest.fixture
def market(tmp_path):
    seed_fixture(tmp_path, companies=12)
    app = create_app(Settings(tmp_path), today=lambda: TODAY)
    with TestClient(app) as client:
        yield client, app, tmp_path


def _files(root):
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in root.iterdir() if path.is_file()}


def test_prompt_matches_the_old_ficha_and_writes_nothing(market):
    client, app, root = market
    before = _files(root)
    table = app.state.market.repository.ranking(dict(app_mode.FROZEN_WEIGHTS), TODAY).table
    symbol = str(table.index[0])
    response = client.get(f"/api/v1/companies/{symbol}/analysis-prompt")
    assert response.status_code == 200, response.text
    expected = ai_prompt.build_analysis_prompt(table.loc[symbol], scoring.explain_row(table, symbol), symbol)
    assert response.json()["prompt"] == expected
    assert "No recalcules estos números" in expected and "Configuración" not in expected
    assert _files(root) == before
    assert client.get("/api/v1/companies/ZZZZ/analysis-prompt").status_code == 404
