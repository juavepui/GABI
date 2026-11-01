"""Investment card domain (#246): validation, completeness, states and scenario moves."""

from datetime import date

import pytest

from gabi.domain.portfolio import investment_card as card

TODAY = date(2026, 11, 1)


def complete(**changes) -> dict:
    raw = {
        "thesis": ["Recompra acciones con caja libre creciente.", "El mercado descuenta un declive que no aparece."],
        "discrepancy": "El precio implica caída del 3 % anual del FCF; los contratos firmados indican estabilidad.",
        "scenarios": {"bear": {"price": 80, "assumptions": "FCF −5 %/año"},
                      "base": {"price": 110, "assumptions": "FCF estable"},
                      "bull": {"price": 140, "assumptions": "FCF +5 %/año"}},
        "catalysts": [{"description": "Resultados anuales", "horizon": "2027-02-15"}],
        "risks": ["Pérdida del contrato principal"],
        "invalidation": [{"description": "El margen cae", "metric": "margen operativo", "source": "10-K",
                          "operator": "<", "threshold": 0.12, "persistence": 2, "review_by": "2027-03-31"}],
        "confidence": "media", "review_due": "2027-05-01",
    }
    return raw | changes


def test_a_complete_card_can_be_analysed_and_published():
    content = card.normalize(complete())
    assert card.missing(content) == []
    assert card.transition("incompleta", "analizada", content, today=TODAY) == "analizada"
    assert card.transition("analizada", "publicada", content, today=TODAY) == "publicada"


def test_publishing_names_every_missing_piece_instead_of_inventing_it():
    content = card.normalize({"thesis": ["Solo una idea"], "scenarios": {"bear": {"price": 90}}})
    gaps = card.missing(content)
    assert "la expectativa discrepante" in gaps and "los tres escenarios con precio y supuestos" in gaps
    assert any(gap.startswith("una condición de invalidación medible") for gap in gaps)
    with pytest.raises(card.CardError, match="Falta la expectativa discrepante"):
        card.transition("incompleta", "publicada", content, today=TODAY)
    unordered = card.normalize(complete(scenarios={"bear": {"price": 150, "assumptions": "a"},
                                                   "base": {"price": 110, "assumptions": "b"},
                                                   "bull": {"price": 140, "assumptions": "c"}}))
    assert card.missing(unordered) == ["escenarios ordenados (bear ≤ base ≤ bull)"]
    vague = card.normalize(complete(invalidation=[{"description": "Si va mal"}]))
    assert card.missing(vague)[0].startswith("una condición de invalidación medible")


def test_validation_rejects_bad_types_and_limits():
    with pytest.raises(card.CardError, match="tres líneas"):
        card.normalize(complete(thesis=["a", "b", "c", "d"]))
    with pytest.raises(card.CardError, match="confianza"):
        card.normalize(complete(confidence="segura"))
    with pytest.raises(card.CardError, match="operador"):
        card.normalize(complete(invalidation=[{"operator": "=="}]))
    with pytest.raises(card.CardError, match="persistencia"):
        card.normalize(complete(invalidation=[{"persistence": 0}]))
    with pytest.raises(card.CardError, match="positivo"):
        card.normalize(complete(scenarios={"bear": {"price": -1}}))
    with pytest.raises(card.CardError, match="fecha"):
        card.normalize(complete(review_due="mañana"))


def test_states_publish_once_and_discarding_needs_a_reason():
    content = card.normalize(complete())
    with pytest.raises(card.CardError, match="no se modifica"):
        card.transition("publicada", "analizada", content, today=TODAY)
    with pytest.raises(card.CardError, match="por qué"):
        card.transition("analizada", "descartada", content, today=TODAY)
    assert card.transition("publicada", "descartada", content, today=TODAY,
                           reason="No hay margen suficiente frente al índice.") == "descartada"
    with pytest.raises(card.CardError, match="versión nueva"):
        card.transition("descartada", "publicada", content, today=TODAY)
    with pytest.raises(card.CardError, match="futura"):
        card.transition("analizada", "publicada", card.normalize(complete(review_due="2026-10-01")), today=TODAY)


def test_scenario_moves_are_relative_to_the_captured_price():
    moves = card.scenario_returns(card.normalize(complete()), 100.0)
    assert moves == {"bear": pytest.approx(-0.2), "base": pytest.approx(0.1), "bull": pytest.approx(0.4)}
    assert card.scenario_returns(card.normalize(complete()), None) == {"bear": None, "base": None, "bull": None}
    assert "probabilidad de beneficio" in card.NOT_A_PROBABILITY
