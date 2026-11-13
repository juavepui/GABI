"""Checklist pass rates and threshold presets (#171): descriptive context, never a verdict."""

import pytest
from fastapi.testclient import TestClient
from market_fixture import TODAY, seed_fixture

from gabi import config
from gabi.application.market.checklist_coverage import checklist_coverage
from gabi.domain.market import checklist, checklist_reference
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.checklist_reference import load_checklist_reference
from gabi_api.bootstrap import create_app

REFERENCE = {"version": 1, "as_of": "2026-10-22", "issuers": 9, "criteria": {
    "interest_coverage": {"Utilities": {"values": [2.0, 3.0, 4.0, 15.0, 20.0], "always_pass": 0},
                          "Information Technology": {"values": [10.0, 30.0], "always_pass": 2}},
    "pe": {"Utilities": {"values": [12.0, 18.0, 25.0, 40.0, 60.0], "always_pass": 0}},
    "revenue_growth_stability": {"Utilities": {"values": [0.1] * 5, "always_pass": 0}},
}}


def test_pass_rates_follow_each_comparison_and_the_threshold_that_applies():
    rates = checklist_reference.pass_rates(REFERENCE, checklist.defaults(), "Utilities")
    # ≥ 15x: 15 and 20 of the utilities; 30 and the two debt-free issuers of IT.
    assert rates["interest_coverage"]["universe"] == {"rate": 5 / 9, "evaluated": 9}
    assert rates["interest_coverage"]["sector"] == {"rate": 2 / 5, "evaluated": 5}
    # ≤ 18x includes 18.
    assert rates["pe"]["universe"] == {"rate": 2 / 5, "evaluated": 5}
    edited = checklist.defaults() | {"pe": 30.0}
    assert checklist_reference.pass_rates(REFERENCE, edited, None)["pe"]["universe"]["rate"] == 3 / 5
    assert "revenue_growth_stability" not in rates  # informative criteria have no threshold
    assert rates["pe"]["sector"]["rate"] == 2 / 5
    # A sector with fewer than five values gives no rate; an absent sector gives none at all.
    small = checklist_reference.pass_rates(REFERENCE, checklist.defaults(), "Information Technology")
    assert small["interest_coverage"]["sector"] == {"rate": None, "evaluated": 4}
    assert small["pe"]["sector"] is None
    assert checklist_reference.pass_rates(REFERENCE | {"version": 2}, checklist.defaults(), None) == {}
    assert checklist_reference.pass_rates(None, checklist.defaults(), None) == {}


def test_presets_are_valid_thresholds_and_excel_is_the_default():
    presets = {preset["key"]: preset for preset in checklist_reference.presets()}
    assert presets["excel"]["values"] == checklist.defaults()
    assert all(preset["version"] == checklist.THRESHOLDS_VERSION for preset in presets.values())
    for key in presets:
        assert checklist.validate_thresholds(checklist_reference.preset_overrides(key)) == \
            checklist_reference.preset_overrides(key)
    with pytest.raises(KeyError):
        checklist_reference.preset_overrides("nope")


def test_large_cap_preset_discriminates_where_the_excel_threshold_almost_never_passes():
    reference = load_checklist_reference()
    assert reference is not None and reference["version"] == checklist_reference.REFERENCE_VERSION
    presets = {preset["key"]: preset["values"] for preset in checklist_reference.presets()}
    excel = checklist_reference.pass_rates(reference, presets["excel"], None)
    large = checklist_reference.pass_rates(reference, presets["large_cap"], None)
    for key in checklist_reference.preset_overrides("large_cap"):
        assert excel[key]["universe"]["rate"] < 0.30, key  # the Excel threshold fails most of the S&P 500
        assert 0.30 <= large[key]["universe"]["rate"] <= 0.70, key  # the preset splits it instead


class _Reader:
    def __init__(self, bodies):
        self.bodies = bodies

    def company(self, symbol):
        return self.bodies[symbol]


def _body(coverage, verdict, reason=None):
    criteria = [{"key": "gross_margin", "verdict": "pass", "value": 0.4, "reason": None},
                {"key": "fcf", "verdict": "pass", "value": 1.0, "reason": None},
                {"key": "interest_coverage", "verdict": verdict, "value": coverage, "reason": reason}]
    return {"as_of": "2026-10-22", "fiscal_year_end": "2025-12-31", "financial_sector": False, "criteria": criteria}


def test_coverage_audit_builds_the_reference_and_pass_rates_per_preset():
    bodies = {"A": _body(20.0, "pass"), "B": _body(5.0, "fail"), "C": _body(None, "pass", "no_debt"),
              "D": _body(None, "missing", "no_interest")}
    report = checklist_coverage(_Reader(bodies), [(symbol, "Utilities") for symbol in bodies])
    group = report["reference"]["criteria"]["interest_coverage"]["Utilities"]
    assert group == {"values": [5.0, 20.0], "always_pass": 1}  # the missing value is not in the reference
    assert report["reference"]["as_of"] == "2026-10-22" and report["reference"]["issuers"] == 4
    excel = report["pass_rates"]["excel"]["interest_coverage"]
    assert excel["threshold"] == 15.0 and excel["rate"] == 2 / 3 and excel["evaluated"] == 3
    assert report["pass_rates"]["large_cap"]["interest_coverage"]["threshold"] == 8.0


@pytest.fixture
def api():
    root = config.DATA_DIR
    seed_fixture(root)
    with TestClient(create_app(Settings(root), today=lambda: TODAY)) as client:
        yield client, root


def test_company_shows_pass_rates_and_presets_are_explicit_commands(api):
    client, root = api
    before = (root / "gabi.db").read_bytes()
    body = client.get("/api/v1/companies/T001/checklist").json()
    reference = load_checklist_reference()
    assert body["pass_rate_reference"] == {"as_of": reference["as_of"], "issuers": reference["issuers"],
                                           "sector": "Information Technology"}
    criteria = {item["key"]: item for item in body["criteria"]}
    assert criteria["revenue_growth_stability"]["pass_rate"] is None
    insiders = criteria["insiders_pct"]["pass_rate"]["universe"]
    expected = checklist_reference.pass_rates(reference, checklist.defaults(), None)["insiders_pct"]["universe"]
    assert insiders == pytest.approx(expected)
    # The sector rate uses the universe's GICS sector, not Yahoo's name for it.
    own = checklist_reference.pass_rates(reference, checklist.defaults(), "Information Technology")
    assert criteria["insiders_pct"]["pass_rate"]["sector"] == pytest.approx(own["insiders_pct"]["sector"])
    assert (root / "gabi.db").read_bytes() == before and not (root / "checklist_thresholds.json").exists()
    thresholds = client.get("/api/v1/checklist/thresholds").json()
    assert thresholds["preset"] == "excel" and {p["key"] for p in thresholds["presets"]} == {"excel", "large_cap"}
    applied = client.post("/api/v1/checklist/thresholds/preset", json={"key": "large_cap"}).json()
    assert applied["preset"] == "large_cap" and applied["values"]["interest_coverage"] == 8.0
    assert sorted(applied["edited"]) == sorted(checklist_reference.preset_overrides("large_cap"))
    relaxed = {item["key"]: item for item in client.get("/api/v1/companies/T001/checklist").json()["criteria"]}
    assert relaxed["insiders_pct"]["threshold"] == 0.01
    assert relaxed["insiders_pct"]["pass_rate"]["universe"]["rate"] > insiders["rate"]
    assert client.post("/api/v1/checklist/thresholds/preset", json={"key": "nope"}).status_code == 422
    edited = client.post("/api/v1/checklist/thresholds", json={"values": {"pe": 30}}).json()
    assert edited["preset"] is None
    assert client.post("/api/v1/checklist/thresholds/preset", json={"key": "excel"}).json()["preset"] == "excel"
    assert not (root / "checklist_thresholds.json").exists()
