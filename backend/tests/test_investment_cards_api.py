"""Investment cards (#246) through the API: versions, states, snapshot at publication and GET without effects."""

from datetime import date

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gabi.application.errors import QueryError
from gabi.application.portfolio.investment_cards import InvestmentCards, digest
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.investment_cards import SqliteInvestmentCards
from gabi_api.bootstrap import create_app

COMPLETE = {
    "thesis": ["Recompra con caja libre creciente."],
    "discrepancy": "El precio implica declive del FCF que no aparece en los contratos.",
    "scenarios": {"bear": {"price": 80, "assumptions": "FCF −5 %"}, "base": {"price": 110, "assumptions": "estable"},
                  "bull": {"price": 140, "assumptions": "FCF +5 %"}},
    "catalysts": [{"description": "Resultados", "horizon": "2027-02-15"}],
    "risks": ["Pérdida del contrato principal"],
    "invalidation": [{"description": "Cae el margen", "metric": "margen operativo", "source": "10-K",
                      "operator": "<", "threshold": 0.12, "persistence": 2, "review_by": "2027-03-31"}],
    "confidence": "media", "review_due": "2027-05-01",
}


def service(tmp_path, *, checklist=None, ranking=None):
    table = pd.DataFrame({"price": [100.0], "composite_score": [71.5]}, index=["ACME"])
    table.attrs["sources"] = {"ACME": {"price_date": "2026-10-30"}}

    def no_checklist(symbol):
        raise QueryError("company_not_found", "sin datos", 404)

    return InvestmentCards(
        SqliteInvestmentCards(tmp_path), ranking=ranking or (lambda: table), checklist=checklist or no_checklist,
        evidence=lambda symbol: {"weighted_data_coverage": 0.8, "evidence_stage": "retrospectiva",
                                 "confidence_level": "media", "score_coverage": 0.9},
        identity=lambda symbol: {"entity_id": "cik:0000000001", "cik": "0000000001", "source": "test"},
        model_id="model-x", today=lambda: date(2026, 11, 1))


def test_a_card_moves_from_draft_to_published_with_a_hashed_snapshot_of_its_inputs(tmp_path):
    cards = service(tmp_path, checklist=lambda symbol: {
        "as_of": "2026-10-30", "fiscal_year_end": "2025-12-31", "sector": "Industrials", "financial_sector": False,
        "thresholds_version": 3, "dcf": {"implied_growth": 0.02}, "multiples_history": {"pe": [12, 14]},
        "criteria": [{"key": "roic", "label": "ROIC", "value": 0.15, "unit": "fraction", "source": "sec_10k",
                      "period": "fiscal_year", "verdict": "pass", "reason": None},
                     {"key": "debt", "label": "Deuda", "value": None, "unit": "ratio", "source": "sec_10k",
                      "period": "fiscal_year", "verdict": "missing", "reason": "sin dato"}]})
    draft = cards.create("acme", {"thesis": ["Idea inicial"]})
    assert draft["state"] == "incompleta" and draft["version"] == 1 and "la expectativa discrepante" in draft["missing"]
    saved = cards.save(draft["id"], COMPLETE)
    assert saved["missing"] == []
    published = cards.move(cards.move(draft["id"], "analizada")["id"], "publicada")
    snapshot = published["snapshot"]
    assert published["state"] == "publicada" and published["snapshot_sha256"] == digest(snapshot)
    assert snapshot["price"] == {"value": 100.0, "date": "2026-10-30", "score": 71.5}
    assert snapshot["issuer"]["cik"] == "0000000001" and snapshot["model_id"] == "model-x"
    assert snapshot["checklist"]["metrics"][0]["source"] == "sec_10k" and snapshot["absent"] == ["métrica: Deuda"]
    assert snapshot["evidence"]["data_coverage"] == 0.8
    assert published["scenario_returns"] == {"bear": pytest.approx(-0.2), "base": pytest.approx(0.1),
                                             "bull": pytest.approx(0.4)}


def test_published_versions_are_immutable_and_a_new_version_starts_from_scratch(tmp_path):
    cards = service(tmp_path)
    first = cards.create("ACME", COMPLETE)
    with pytest.raises(QueryError) as opened:
        cards.create("ACME", {})
    assert opened.value.code == "card_open"
    published = cards.move(first["id"], "publicada")
    assert published["snapshot"]["absent"] == ["checklist"]  # Named, never filled in.
    with pytest.raises(QueryError) as closed:
        cards.save(first["id"], COMPLETE)
    assert closed.value.code == "card_closed"
    with pytest.raises(QueryError, match="no se modifica"):
        cards.move(first["id"], "analizada")
    second = cards.create("ACME", COMPLETE)
    assert second["version"] == 2 and second["state"] == "incompleta"
    discarded = cards.move(second["id"], "descartada", "No hay margen frente al índice.")
    assert discarded["state"] == "descartada" and discarded["discard_reason"] == "No hay margen frente al índice."
    assert [row["version"] for row in cards.list("ACME")] == [2, 1]


def test_the_api_validates_and_its_gets_do_not_write(tmp_path):
    with TestClient(create_app(Settings(tmp_path))) as api:
        assert api.get("/api/v1/portfolio/cards").json() == {"items": []}
        assert not (tmp_path / "gabi.db").exists() or "investment_cards" not in (tmp_path / "gabi.db").read_bytes().decode(
            "latin-1")
        created = api.post("/api/v1/portfolio/cards", json={"symbol": "ACME", "content": {"thesis": ["Idea"]}})
        assert created.status_code == 201, created.text
        card_id = created.json()["id"]
        refused = api.post(f"/api/v1/portfolio/cards/{card_id}/state", json={"target": "publicada"})
        assert refused.status_code == 422 and "Falta" in refused.text
        bad = api.post(f"/api/v1/portfolio/cards/{card_id}/save", json={"content": {"confidence": "segura"}})
        assert bad.status_code == 422
        too_long = api.post(f"/api/v1/portfolio/cards/{card_id}/save",
                            json={"content": {"thesis": ["a", "b", "c", "d"]}})
        assert too_long.status_code == 422 and "tres líneas" in too_long.text
        assert api.get(f"/api/v1/portfolio/cards/{card_id}").json()["state"] == "incompleta"
        assert api.get("/api/v1/portfolio/cards/999").status_code == 404
