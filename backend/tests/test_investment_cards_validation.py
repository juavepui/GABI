"""#246 validation: 30 fixture cards with reproducible figures, resolvable sources and nothing invented.

Each fixture combines which inputs exist (checklist, evidence, price, investor profile,
portfolio risk, the index in EUR, sector comparables) with a different thesis. For
every one: the card publishes, the snapshot hash reproduces from the same inputs,
every metric names a known source and period, every absent input is named and
leaves its fields empty, and every derived figure recomputes from the snapshot.
"""

from datetime import date

import pandas as pd
import pytest

from gabi.application.errors import QueryError
from gabi.application.portfolio.investment_cards import InvestmentCards, digest
from gabi.domain.portfolio import investment_card as rules
from gabi.infrastructure.storage.investment_cards import SqliteInvestmentCards

SOURCES = {"sec_10k", "price+sec", "yahoo", "price+yahoo", "prices"}
PERIODS = {"fiscal_year", "snapshot", "cached_history"}
INPUTS = ("checklist", "evidence", "price", "investor", "risk", "passive", "comparables")
TODAY = date(2026, 11, 1)


def unavailable(*args):
    raise QueryError("missing", "sin datos", 404)


def fixture(index: int) -> dict:
    """Fixture ``index`` (0–29): a bitmask of available inputs and its own figures."""
    present = {name: bool((index * 37 + 11) >> bit & 1) or index % 7 == 0 for bit, name in enumerate(INPUTS)}
    price = 20.0 + index * 7.5
    return {"symbol": f"FX{index:02d}", "present": present, "price": price,
            "content": {
                "thesis": [f"Tesis de prueba {index}."],
                "discrepancy": f"El mercado descuenta un crecimiento del {index % 5} % que no se sostiene.",
                "scenarios": {"bear": {"price": round(price * 0.7, 2), "assumptions": "margen a la baja"},
                              "base": {"price": round(price * (1 + index / 100), 2), "assumptions": "estable"},
                              "bull": {"price": round(price * 1.6, 2), "assumptions": "expansión"}},
                "catalysts": [{"description": "Resultados", "horizon": f"2027-0{1 + index % 9}-15"}],
                "risks": ["Competencia"],
                "invalidation": [{"description": "Cae el margen", "metric": "margen operativo", "source": "10-K",
                                  "operator": "<", "threshold": 0.1 + index / 1000, "persistence": 1 + index % 3,
                                  "review_by": "2027-06-30"}],
                "confidence": rules.CONFIDENCE[index % 3], "review_due": f"2027-{1 + index % 12:02d}-28",
                "position_eur": 500.0 + 100 * index}}


def service(tmp_path, case: dict) -> InvestmentCards:
    present, symbol = case["present"], case["symbol"]
    table = pd.DataFrame({"price": [case["price"]], "composite_score": [50.0], "sector": ["Energy"]}, index=[symbol])
    table.attrs["sources"] = {symbol: {"price_date": "2026-10-30"}}
    checklist = {"as_of": "2026-10-30", "fiscal_year_end": "2025-12-31", "sector": "Energy",
                 "financial_sector": False, "thresholds_version": 1, "dcf": {"implied_growth": 0.01},
                 "multiples_history": {"pe": [10.0, 12.0]},
                 "criteria": [{"key": "roic", "label": "ROIC", "value": 0.11, "unit": "fraction", "source": "sec_10k",
                               "period": "fiscal_year", "verdict": "pass", "reason": None},
                              {"key": "pe", "label": "PER", "value": None, "unit": "ratio", "source": "price+sec",
                               "period": "snapshot", "verdict": "missing", "reason": "sin beneficio"}]}
    return InvestmentCards(
        SqliteInvestmentCards(tmp_path),
        ranking=(lambda: table) if present["price"] else (lambda: table.iloc[0:0]),
        checklist=(lambda s: checklist) if present["checklist"] else unavailable,
        evidence=(lambda s: {"weighted_data_coverage": 0.7, "evidence_stage": "retrospectiva",
                             "confidence_level": "baja"}) if present["evidence"] else unavailable,
        identity=lambda s: {"entity_id": "cik:0000000099", "cik": "0000000099", "source": "fixture"},
        model_id="model-fixture", today=lambda: TODAY,
        investor=(lambda: {"revision": 1, "profile": {"commission_fixed_eur": 1.0, "commission_pct": 0.001,
                                                      "fx_cost_pct": 0.006}}) if present["investor"] else lambda: None,
        passive=(lambda: {"performance": {"twr_annualised": 0.09}}) if present["passive"] else unavailable,
        risk=(lambda: {"policy": {"max_issuer_weight": 0.10, "max_sector_weight": 0.30},
                       "exposure": {"total_eur": 10000, "issuers": [], "sectors": [{"name": "Energy", "weight": 0.2}]}}
              ) if present["risk"] else unavailable,
        sector_multiples=(lambda s: {"pe_median": 14.0}) if present["comparables"] else unavailable)


@pytest.mark.parametrize("index", range(30))
def test_fixture_card_is_reproducible_resolvable_and_invents_nothing(tmp_path, index):
    case = fixture(index)
    cards = service(tmp_path, case)
    card = cards.move(cards.create(case["symbol"], case["content"])["id"], "publicada")
    snapshot, present = card["snapshot"], case["present"]
    # Reproducible: the hash matches, and the same inputs give the same snapshot again.
    assert card["snapshot_sha256"] == digest(snapshot)
    assert digest(cards.capture(case["symbol"], card["content"])) == card["snapshot_sha256"]
    # Resolvable: every metric names a known source and period, with its checklist date.
    if present["checklist"]:
        assert snapshot["checklist"]["as_of"] == "2026-10-30"
        assert all(item["source"] in SOURCES and item["period"] in PERIODS for item in snapshot["checklist"]["metrics"])
        assert "métrica: PER" in snapshot["absent"]
    # Nothing invented: each absent input is named and leaves its fields empty.
    expected = {"checklist": snapshot["checklist"] is None, "evidence": snapshot["evidence"] is None,
                "price": snapshot["price"]["value"] is None, "comparables": snapshot["sector_comparables"] is None,
                "investor": snapshot["decision"]["costs"] is None, "risk": snapshot["decision"]["concentration"] is None}
    for name, empty in expected.items():
        assert empty is (not present[name]), name
    named = {"checklist": "checklist", "evidence": "evidencia del modelo", "price": "precio",
             "comparables": "comparables sectoriales", "investor": "perfil del inversor (costes y benchmark)",
             "risk": "riesgo de cartera", "passive": "rentabilidad del S&P 500 en EUR"}
    for name, label in named.items():
        assert (label in snapshot["absent"]) is (not present[name]), name
    # Derived figures recompute from the snapshot and the content.
    price = snapshot["price"]["value"]
    for name in rules.SCENARIOS:
        move = card["scenario_returns"][name]
        target = card["content"]["scenarios"][name]["price"]
        assert move is None if price is None else move == pytest.approx(target / price - 1)
    passive = snapshot["decision"]["passive"]
    if price is None:
        assert passive is None
    else:
        recomputed = rules.passive_comparison(card["content"], price, TODAY,
                                              0.09 if present["passive"] else None, snapshot["decision"]["costs"])
        assert passive == recomputed
        assert (passive["index_annualised_past"] is None) is (not present["passive"])


def test_the_fixtures_cover_every_input_both_present_and_absent():
    cases = [fixture(index)["present"] for index in range(30)]
    for name in INPUTS:
        assert any(case[name] for case in cases) and any(not case[name] for case in cases), name
