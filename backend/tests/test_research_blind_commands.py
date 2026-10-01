"""Blind validations: preregistered disclosure rules and explicit create/break-seal commands."""

import json
import shutil
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gabi import blind_validation as bv
from gabi import config, research_lab
from gabi.domain.research.blind import disclosure
from gabi.infrastructure.settings import Settings
from gabi_api.bootstrap import create_app

REPO = Path(__file__).resolve().parents[2]
FORM = {"name": "Prueba nueva", "weights_pct": {"value": 30, "quality": 35, "momentum": 25, "risk": 10},
        "n_positions": 20, "rebalance_months": 3, "start_date": "2026-10-01", "unlock_date": "2027-10-01"}


@pytest.fixture
def plans_root(tmp_path, monkeypatch):
    for relative in ("docs/prospective-plan/gabi-id1.json", "docs/value-hypothesis/preregistro.json"):
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / relative, tmp_path / relative)
    monkeypatch.setattr(research_lab, "_current_git_commit", lambda: "abc1234")
    monkeypatch.setattr(bv, "_current_git_commit", lambda: "abc1234")
    (config.DATA_DIR / "app_mode.json").write_text('{"mode":"RESEARCH"}')
    return tmp_path


def _client(plans_root, today=date(2026, 10, 1)):
    return TestClient(create_app(Settings(config.DATA_DIR), today=lambda: today, blind_plans_root=plans_root))


def _seed_preregistered():
    """Ids 1 and 2 as in the local database: GABI (#42) and the value hypothesis (#43) is id 3."""
    first = bv.create_validation("GABI", {"value": .3, "quality": .35, "momentum": .25, "risk": .1}, 20, 3,
                                 "2026-09-21", "2029-09-21")
    other = bv.create_validation("Libre", {"value": .3, "quality": .35, "momentum": .25, "risk": .1}, 20, 3,
                                 "2026-09-21", "2026-12-01")
    value = bv.create_validation("Valor", {"value": 1, "quality": 0, "momentum": 0, "risk": 0}, 20, 3,
                                 "2026-12-21", "2029-12-21", model_id="GABI-VALUE-v1")
    assert (first, value) == (1, 3)
    return other


def test_disclosure_follows_each_preregistered_plan():
    looks = ["2029-12-21", "2032-12-21", "2036-12-21"]
    assert disclosure("locked", "2027-01-01", None, "2026-12-31")["revealed"] is False
    assert disclosure("locked", "2027-01-01", None, "2027-01-01") == {"revealed": True, "through": None,
                                                                      "next_look": None}
    assert disclosure("locked", "2029-12-21", looks, "2029-12-20") == {
        "revealed": False, "through": None, "next_look": "2029-12-21"}
    assert disclosure("locked", "2029-12-21", looks, "2031-06-01") == {
        "revealed": True, "through": "2029-12-21", "next_look": "2032-12-21"}
    assert disclosure("locked", "2029-12-21", looks, "2040-01-01")["through"] == "2036-12-21"
    assert disclosure("broken_early", "2029-12-21", looks, "2027-01-01")["revealed"] is True


def test_status_reads_the_published_plans(plans_root):
    _seed_preregistered()
    with _client(plans_root, date(2031, 6, 1)) as client:
        items = {item["id"]: item for item in client.get("/api/v1/research/blind-validations").json()["items"]}
    gabi_plan = json.loads((REPO / "docs/prospective-plan/gabi-id1.json").read_text(encoding="utf-8"))
    assert items[1]["preregistered"] == {"issue": 42, "looks": ["2029-09-21"], "sha256": gabi_plan["sha256"],
                                         "source": "docs/prospective-plan/gabi-id1.json"}
    assert items[3]["preregistered"]["looks"] == ["2029-12-21", "2032-12-21", "2036-12-21"]
    assert (items[3]["revealed"], items[3]["revealed_through"], items[3]["next_look"]) == (
        True, "2029-12-21", "2032-12-21")
    assert items[2]["preregistered"] is None and items[2]["revealed_through"] is None


def test_a_tampered_plan_blocks_blind_operations(plans_root):
    _seed_preregistered()
    path = plans_root / "docs/value-hypothesis/preregistro.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["plan_secuencial"]["looks"][0]["fecha"] = "2027-01-01"  # An earlier look would leak results.
    record["spec"]["rules"] = []
    path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    with _client(plans_root) as client:
        status = client.get("/api/v1/research/blind-validations")
        created = client.post("/api/v1/research/blind-validations", json=FORM)
    assert status.status_code == created.status_code == 503
    assert status.json()["error"]["code"] == "blind_plan_invalid"


def test_create_builds_the_streamlit_validation(plans_root):
    with _client(plans_root) as client:
        response = client.post("/api/v1/research/blind-validations", json=FORM)
    assert response.status_code == 201
    created = bv.list_validations().iloc[0]
    assert json.loads(created["weights_json"]) == {"value": .3, "quality": .35, "momentum": .25, "risk": .1}
    assert (created["n_positions"], created["rebalance_months"], created["status"]) == (20, 3, "locked")
    assert (created["start_date"], created["unlock_date"], created["git_commit_created"]) == (
        "2026-10-01", "2027-10-01", "abc1234")
    assert response.json()["id"] == int(created["id"]) and response.json()["revealed"] is False


@pytest.mark.parametrize("change", [{"unlock_date": "2026-10-01"}, {"rebalance_months": 2},
                                    {"weights_pct": {"value": 101, "quality": 0, "momentum": 0, "risk": 0}},
                                    {"name": " "}])
def test_invalid_creation_writes_nothing(plans_root, change):
    with _client(plans_root) as client:
        assert client.post("/api/v1/research/blind-validations", json=FORM | change).status_code == 422
    assert not (config.DATA_DIR / "gabi.db").exists()


def test_preregistered_seals_cannot_be_broken_but_others_keep_the_streamlit_escape(plans_root):
    other = _seed_preregistered()
    with _client(plans_root) as client:
        refused = client.post("/api/v1/research/blind-validations/1/break-seal", json={"reason": "curiosidad"})
        empty = client.post(f"/api/v1/research/blind-validations/{other}/break-seal", json={"reason": "  "})
        broken = client.post(f"/api/v1/research/blind-validations/{other}/break-seal",
                             json={"reason": "probar la interfaz"})
        again = client.post(f"/api/v1/research/blind-validations/{other}/break-seal", json={"reason": "otra"})
    assert refused.status_code == 403 and refused.json()["error"]["code"] == "preregistered_seal"
    assert bv.list_validations().set_index("id").loc[1, "status"] == "locked"
    assert empty.status_code == 422
    assert broken.status_code == 200 and broken.json()["status"] == "broken_early" and broken.json()["revealed"]
    assert bv.list_validations().set_index("id").loc[other, "broken_early_reason"] == "probar la interfaz"
    assert again.status_code == 409


def test_blind_writes_require_research_mode(plans_root):
    other = _seed_preregistered()
    (config.DATA_DIR / "app_mode.json").write_text('{"mode":"INVESTOR"}')
    with _client(plans_root) as client:
        assert client.post("/api/v1/research/blind-validations", json=FORM).status_code == 403
        assert client.post(f"/api/v1/research/blind-validations/{other}/break-seal",
                           json={"reason": "x"}).status_code == 403
