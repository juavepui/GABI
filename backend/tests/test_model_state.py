"""Model mode, frozen-weights rules and live-forward tracking through the production API (formerly ``app_mode``).

The flat ``app_mode`` (retired in F7.33) duplicated these rules; the API reads them from
``domain.market.model_policy``, the local files and the ledgers' metadata.
"""

import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from market_fixture import TODAY

from gabi import config, research_lab, screener_asof, storage
from gabi.domain.market import model_policy as policy
from gabi.infrastructure.legacy import blind_validation
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.mode import FileMode
from gabi_api.bootstrap import create_app

FROZEN = dict(policy.FROZEN_WEIGHTS)
CUSTOM = {"value": 0.5, "quality": 0.2, "momentum": 0.2, "risk": 0.1}


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    storage.init_db()  # the model state needs no market data, only the ledgers' metadata
    with TestClient(create_app(Settings(tmp_path), today=lambda: TODAY), raise_server_exceptions=False) as client:
        yield client, tmp_path


def research(root, weights=FROZEN):
    """Research mode with saved weights, so the saved weights (not the Investor default) decide the state."""
    FileMode(root).save_mode("RESEARCH")
    (root / "weights.json").write_text(json.dumps(weights), encoding="utf-8")


def recorded_validation(monkeypatch, weights, *, as_of="2024-01-10", unlock="2099-01-01") -> int:
    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    for symbol, close in (("A", 100.0), ("B", 50.0)):
        storage.upsert_prices(symbol, pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close,
                                                    "Adj Close": close, "Volume": 1}, index=dates))
    monkeypatch.setattr(screener_asof, "build_ranking_as_of", lambda day, symbols=None, weights=None: {
        "table": pd.DataFrame({"composite_score": [90, 80], "score_coverage": [.9, .9]}, index=["A", "B"])})
    validation_id = blind_validation.create_validation("Test", weights, 2, 3, as_of, unlock)
    blind_validation.record_rebalance(validation_id, as_of=as_of)
    return validation_id


def test_mode_defaults_to_investor_and_reads_the_saved_mode(api):
    client, root = api
    assert client.get("/api/v1/model").json()["mode"] == "INVESTOR"
    FileMode(root).save_mode("RESEARCH")
    assert client.get("/api/v1/model").json()["mode"] == "RESEARCH"


def test_corrupt_mode_file_fails_closed(api):
    """The old facade fell back to Investor; the API refuses to guess the local state."""
    client, root = api
    (root / "app_mode.json").write_text("{ esto no es json valido", encoding="utf-8")
    response = client.get("/api/v1/model")
    assert response.status_code == 503 and response.json()["error"]["code"] == "local_state_error"


def test_frozen_weights_rules():
    assert policy.weights_match_frozen(FROZEN) is True
    assert policy.weights_match_frozen({k: v + 1e-9 for k, v in FROZEN.items()}) is True
    assert policy.weights_match_frozen({**FROZEN, "value": FROZEN["value"] + .01}) is False
    assert policy.weights_match_frozen({}) is False
    assert policy.weights_match_frozen({k: v for k, v in FROZEN.items() if k != "risk"}) is False
    assert policy.model_status(FROZEN) == "FROZEN"  # matching weights do not claim a validation
    assert policy.model_status(FROZEN, live_forward_active=True) == "LIVE_FORWARD"
    assert policy.model_status(CUSTOM, live_forward_active=True) == "EXPERIMENTAL"
    assert policy.experimental_banner_message(FROZEN) is None
    message = policy.experimental_banner_message(CUSTOM)
    assert "EXPERIMENTAL" in message and "Research Lab" in message


def test_saved_frozen_weights_are_frozen_and_custom_ones_experimental(api):
    client, root = api
    research(root)
    model = client.get("/api/v1/model").json()
    assert (model["status"], model["matches_frozen"], model["model_id"]) == ("FROZEN", True, policy.FROZEN_MODEL_ID)
    research(root, CUSTOM)
    model = client.get("/api/v1/model").json()
    assert (model["status"], model["matches_frozen"], model["model_id"]) == ("EXPERIMENTAL", False, "EXPERIMENTAL")


def test_research_lab_live_forward_is_the_weak_signal(api):
    client, root = api
    research(root)
    research_lab.log_experiment("GABI-MF-v1", "LIVE_FORWARD", True, sharpe=0.5)
    model = client.get("/api/v1/model").json()
    assert (model["status"], model["live_forward_source"], model["blind_validation_id"]) == \
        ("LIVE_FORWARD", "research_lab", None)


def test_locked_blind_validation_is_the_strong_signal_and_wins(api, monkeypatch):
    client, root = api
    research(root)
    validation_id = recorded_validation(monkeypatch, FROZEN)
    research_lab.log_experiment("GABI-MF-v1", "LIVE_FORWARD", True, sharpe=0.5)
    model = client.get("/api/v1/model").json()
    assert (model["status"], model["live_forward_source"], model["blind_validation_id"]) == \
        ("LIVE_FORWARD", "blind_validation", validation_id)


@pytest.mark.parametrize("case", ["no_periods", "other_weights", "broken_early"])
def test_blind_validations_that_do_not_count(api, monkeypatch, case):
    client, root = api
    research(root)
    if case == "no_periods":
        blind_validation.create_validation("Sin rebalanceos", FROZEN, 2, 3, "2024-01-10", "2099-01-01")
    elif case == "other_weights":
        recorded_validation(monkeypatch, CUSTOM)
    else:
        blind_validation.break_seal_early(recorded_validation(monkeypatch, FROZEN), "prueba de que no cuenta")
    model = client.get("/api/v1/model").json()
    assert (model["status"], model["live_forward_source"], model["blind_validation_id"]) == ("FROZEN", None, None)
