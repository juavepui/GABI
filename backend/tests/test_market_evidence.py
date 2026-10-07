"""Candidate evidence and ranking stability match the Streamlit calls, read-only and cached per revision."""

import hashlib
import json
from datetime import date

import pytest
from fastapi.testclient import TestClient
from market_fixture import TODAY, seed_fixture

from gabi import app_mode, evidence_confidence, rank_stability
from gabi.infrastructure.settings import Settings
from gabi_api.bootstrap import create_app


@pytest.fixture
def market(tmp_path):
    seed_fixture(tmp_path, companies=30)
    app = create_app(Settings(tmp_path), today=lambda: TODAY)
    with TestClient(app) as client:
        yield client, app, tmp_path


def _files(root):
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in root.iterdir() if path.is_file()}


def test_top_twenty_and_detail_match_the_old_screener(market):
    client, app, root = market
    before = _files(root)
    top = client.get("/api/v1/evidence")
    assert top.status_code == 200, top.text
    table = app.state.market.repository.ranking(dict(app_mode.FROZEN_WEIGHTS), TODAY).table
    expected = evidence_confidence.build(table, dict(app_mode.FROZEN_WEIGHTS))
    ordered = sorted(expected, key=lambda s: (-(expected[s]["score"] if expected[s]["score"] is not None else -1), s))
    selected = [s for s in ordered if expected[s]["score"] is not None
                and (expected[s]["score_coverage"] or 0) >= .70][:20]  # evidence_ui.render
    body = top.json()
    assert [row["symbol"] for row in body["rows"]] == selected
    assert [row["confidence_level"] for row in body["rows"]] == [expected[s]["confidence_level"] for s in selected]
    assert [row["top20_persistence"] for row in body["rows"]] == [
        expected[s]["stability"].get("top20_inclusion") for s in selected]
    symbol = selected[0]
    detail = client.get(f"/api/v1/companies/{symbol.lower()}/evidence").json()
    assert (detail["reasons_for"], detail["reasons_against"]) == (expected[symbol]["reasons_for"],
                                                                  expected[symbol]["reasons_against"])
    assert [f["metric"] for f in detail["factors"]] == [f["metric"] for f in expected[symbol]["factors"]]
    assert detail["factors"][0]["percentile"] == expected[symbol]["factors"][0]["percentile"]
    assert detail["research_details"] is None  # Investor: no raw JSON blocks, as the old page.
    download = client.get(f"/api/v1/companies/{symbol}/evidence.json")
    assert json.loads(download.content)["confidence_level"] == expected[symbol]["confidence_level"]
    assert client.get("/api/v1/companies/NOPE/evidence").status_code == 404
    assert _files(root) == before


def test_stability_matches_rank_stability_and_depends_on_mode(market):
    client, app, root = market
    table = app.state.market.repository.ranking(dict(app_mode.FROZEN_WEIGHTS), TODAY).table
    summary, metrics, companies = rank_stability.analyze(table, dict(app_mode.FROZEN_WEIGHTS))
    investor = client.get("/api/v1/ranking/stability").json()
    assert investor["summary"]["stability_score"] == summary["stability_score"]
    assert [row["symbol"] for row in investor["companies"]] == companies[companies.base_rank <= 20].index.tolist()
    assert investor["metrics"] == [] and investor["perturbations"] == []
    (root / "app_mode.json").write_text('{"mode":"RESEARCH"}')
    research = client.get("/api/v1/ranking/stability").json()
    assert len(research["companies"]) == len(companies) and len(research["metrics"]) == len(metrics)
    assert len(research["perturbations"]) == summary["perturbations"]
    detail = client.get(f"/api/v1/companies/{companies.index[0]}/evidence").json()
    assert set(detail["research_details"]) == {"predictive_test", "placebos", "bootstrap", "tail", "stability",
                                               "quality", "rules", "trace"}


def test_the_portfolio_plan_reads_frozen_weight_evidence_in_research(market):
    client, app, root = market
    (root / "app_mode.json").write_text('{"mode":"RESEARCH"}')
    (root / "weights.json").write_text('{"value": 0.7, "quality": 0.1, "momentum": 0.1, "risk": 0.1}')
    experimental = client.get("/api/v1/evidence").json()
    frozen = client.get("/api/v1/evidence", params={"frozen": True}).json()
    assert experimental["weights"] == {"value": 0.7, "quality": 0.1, "momentum": 0.1, "risk": 0.1}
    assert frozen["weights"] == dict(app_mode.FROZEN_WEIGHTS)


def test_evidence_is_computed_once_per_ranking_revision(market, monkeypatch):
    client, app, _ = market
    calls = []
    original = app.state.evidence.math.evidence
    monkeypatch.setattr(app.state.evidence.math, "evidence",
                        lambda table, weights: calls.append(1) or original(table, weights))
    for _ in range(3):
        assert client.get("/api/v1/evidence").status_code == 200
    symbol = client.get("/api/v1/evidence").json()["rows"][0]["symbol"]
    assert client.get(f"/api/v1/companies/{symbol}/evidence").status_code == 200
    assert len(calls) == 1


def test_dates_in_ranking_rows_no_longer_break_the_evidence(market):
    client, app, _ = market
    table = app.state.market.repository.ranking(dict(app_mode.FROZEN_WEIGHTS), TODAY).table
    table.loc[table.index[0], "next_earnings_date"] = date(2026, 10, 28)
    assert evidence_confidence.build(table, dict(app_mode.FROZEN_WEIGHTS))


def test_block_coverage_and_warnings_match_the_old_screener(market):
    from gabi import data_quality

    client, app, root = market
    table = app.state.market.repository.ranking(dict(app_mode.FROZEN_WEIGHTS), TODAY).table
    blocks = data_quality.score_block_coverage(table)
    body = client.get("/api/v1/ranking/coverage", params={"threshold": 0.95}).json()
    assert {row["block"]: row["complete"] for row in body["blocks"]} == {b: v["complete"] for b, v in blocks.items()}
    assert body["warnings"] == data_quality.block_coverage_warnings(blocks, 0.95)
    assert client.get("/api/v1/ranking/coverage", params={"threshold": 2}).status_code == 422
