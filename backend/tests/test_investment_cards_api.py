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
    "confidence": "media", "review_due": "2027-05-01", "position_eur": 2000,
}


def service(tmp_path, *, checklist=None, ranking=None, **ports):
    table = pd.DataFrame({"price": [100.0], "composite_score": [71.5]}, index=["ACME"])
    table.attrs["sources"] = {"ACME": {"price_date": "2026-10-30"}}

    def no_checklist(symbol):
        raise QueryError("company_not_found", "sin datos", 404)

    return InvestmentCards(
        SqliteInvestmentCards(tmp_path), ranking=ranking or (lambda: table), checklist=checklist or no_checklist,
        evidence=lambda symbol: {"weighted_data_coverage": 0.8, "evidence_stage": "retrospectiva",
                                 "confidence_level": "media", "score_coverage": 0.9},
        identity=lambda symbol: {"entity_id": "cik:0000000001", "cik": "0000000001", "source": "test"},
        model_id="model-x", today=lambda: date(2026, 11, 1), **ports)


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
    assert snapshot["checklist"]["metrics"][0]["source"] == "sec_10k"
    assert snapshot["absent"] == ["métrica: Deuda", "comparables sectoriales", "perfil del inversor (costes y benchmark)",
                                  "riesgo de cartera", "rentabilidad del S&P 500 en EUR"]
    assert snapshot["decision"]["costs"] is None and snapshot["decision"]["passive"]["index_annualised_past"] is None
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
    assert published["snapshot"]["absent"][0] == "checklist"  # Named, never filled in.
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


def test_publishing_captures_costs_concentration_comparables_and_the_index_in_euros(tmp_path):
    table = pd.DataFrame({"price": [100.0], "composite_score": [71.5], "sector": ["Industrials"]}, index=["ACME"])
    table.attrs["sources"] = {"ACME": {"price_date": "2026-10-30"}}
    cards = service(
        tmp_path, ranking=lambda: table,
        investor=lambda: {"revision": 3, "profile": {"commission_fixed_eur": 1.0, "commission_pct": 0.0,
                                                     "fx_cost_pct": 0.006}},
        passive=lambda: {"start": "2024-11-01", "as_of": "2026-11-01", "profile_revision": 3,
                         "source": {"symbol": "SPY"}, "performance": {"twr_annualised": 0.12}},
        risk=lambda: {"policy_revision": None, "policy": {"max_issuer_weight": 0.10, "max_sector_weight": 0.30},
                      "exposure": {"total_eur": 18000, "issuers": [], "sectors": [{"name": "Industrials",
                                                                                 "weight": 0.25}]}},
        sector_multiples=lambda symbol: {"sector": "Industrials", "pe_median": 18.0, "peers": 60})
    card = cards.move(cards.create("ACME", COMPLETE)["id"], "publicada")
    decision = card["snapshot"]["decision"]
    assert decision["costs"]["round_trip_eur"] == pytest.approx(26.0) and decision["profile_revision"] == 3
    assert decision["concentration"]["issuer_weight_after"] == pytest.approx(0.10)
    assert decision["concentration"]["sector_weight_after"] == pytest.approx(0.325) and decision["concentration"][
        "sector_exceeds"]
    assert decision["passive"]["index_annualised_past"] == 0.12 and decision["passive"]["costs_included"]
    assert card["snapshot"]["sector_comparables"]["pe_median"] == 18.0
    assert card["snapshot"]["absent"] == ["checklist"]
