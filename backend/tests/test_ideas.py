"""Idea history (#247): additive events, notes apart, evaluation of every idea against the S&P 500 in EUR."""

from datetime import UTC, date, datetime

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gabi.application.errors import QueryError
from gabi.application.portfolio.ideas import Ideas
from gabi.domain.portfolio import ideas as rules
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.ideas import SqliteIdeas
from gabi_api.bootstrap import create_app

DAYS = pd.bdate_range("2026-01-02", "2026-06-30")


def frame(start: float, daily: float, days=DAYS) -> pd.DataFrame:
    values = start * (1 + daily) ** np.arange(len(days))
    return pd.DataFrame({"close": values, "adj_close": values}, index=days)


def market(**frames):
    base = {"SPY": frame(500.0, 0.0005), "USDEUR=X": frame(0.9, 0.0)} | frames
    return lambda symbols, start: {symbol: base[symbol].loc[base[symbol].index >= pd.Timestamp(start)]
                                   for symbol in symbols if symbol in base}


def card(card_id: int, symbol: str, cost: float | None = 0.01) -> dict:
    decision = {"costs": {"round_trip_share": cost}} if cost is not None else {}
    return {"id": card_id, "symbol": symbol, "snapshot_sha256": "a" * 64,
            "content": {"review_due": "2026-12-31", "position_eur": 1000.0}, "snapshot": {"decision": decision}}


def service(tmp_path, prices, *, now=datetime(2026, 1, 2, 9, tzinfo=UTC), today=date(2026, 6, 30)):
    return Ideas(SqliteIdeas(tmp_path), prices, lambda: today, lambda: now)


def test_publication_is_recorded_once_and_survives_a_restart(tmp_path):
    ideas = service(tmp_path, market(ACME=frame(100.0, 0.001)))
    ideas.record_publication(card(1, "ACME"))
    ideas.record_publication(card(1, "ACME"))  # Duplicate call.
    again = service(tmp_path, market(ACME=frame(100.0, 0.001)))  # Restart: a new service on the same store.
    again.record_publication(card(1, "ACME"))
    detail = again.detail(1)
    assert [event["kind"] for event in detail["events"]] == ["publicada"] and detail["chain_ok"]
    assert detail["state"]["published_on"] == "2026-01-02"


def test_returns_reconcile_net_of_costs_against_the_index_in_euros(tmp_path):
    ideas = service(tmp_path, market(ACME=frame(100.0, 0.001)))
    ideas.record_publication(card(1, "ACME", cost=0.01))
    evaluation = ideas.detail(1)["evaluation"]
    gross = (1.001) ** (len(DAYS) - 1) - 1
    index = (1.0005) ** (len(DAYS) - 1) - 1
    assert evaluation["return_net"] == pytest.approx((1 + gross) * 0.99 - 1)
    assert evaluation["index_return"] == pytest.approx(index) and evaluation["costs_included"]
    assert evaluation["excess"] == pytest.approx(evaluation["return_net"] - index)
    assert evaluation["start"] == "2026-01-02" and evaluation["end"] == "2026-06-30"


def test_losing_closed_and_retired_ideas_all_count_in_the_summary(tmp_path):
    prices = market(WIN=frame(100.0, 0.002), LOSS=frame(100.0, -0.002), NOEX=frame(50.0, 0.0))
    ideas = service(tmp_path, prices)
    for idea_id, symbol in ((1, "WIN"), (2, "LOSS"), (3, "NOEX")):
        ideas.record_publication(card(idea_id, symbol))
    ideas = service(tmp_path, prices, now=datetime(2026, 6, 1, 9, tzinfo=UTC))  # Closed months later.
    ideas.append(2, "cerrada", {"outcome": "fallida", "cause": "El margen cayó", "executed": True})
    ideas.append(3, "retirada", {"reason": "No llegué a invertir"})
    listing = ideas.list()
    summary = listing["summary"]
    assert (summary["ideas"], summary["open"], summary["closed"], summary["retired"]) == (3, 1, 1, 1)
    assert summary["evaluated"] == 3 and summary["beat_index"] == 1
    assert summary["thesis_hits"] == {"acertada": 0, "parcial": 0, "fallida": 1}
    loss = next(row for row in listing["items"] if row["symbol"] == "LOSS")
    assert loss["evaluation"]["return_net"] < 0 and loss["evaluation"]["max_drawdown"] < 0


def test_after_closing_only_corrections_are_accepted_and_they_never_rewrite(tmp_path):
    ideas = service(tmp_path, market(ACME=frame(100.0, 0.001)))
    ideas.record_publication(card(1, "ACME"))
    ideas.append(1, "revisada", {"text": "Resultados en línea"})
    ideas.append(1, "cerrada", {"outcome": "acertada", "cause": "Recompras", "executed": True})
    with pytest.raises(QueryError, match="solo admite correcciones"):
        ideas.append(1, "revisada", {"text": "otra"})
    with pytest.raises(QueryError, match="qué evento"):
        ideas.append(1, "corregida", {"corrects": 9, "text": "x"})
    corrected = ideas.append(1, "corregida", {"corrects": 2, "text": "El dato del 10-K se revisó"})
    assert [event["kind"] for event in corrected["events"]] == ["publicada", "revisada", "cerrada", "corregida"]
    assert corrected["events"][1]["payload"]["text"] == "Resultados en línea"  # The original stays.
    assert corrected["state"]["corrections"] == 1 and corrected["chain_ok"]
    with pytest.raises(QueryError, match="La publicación"):
        ideas.append(1, "publicada", {})


def test_a_tampered_chain_is_detected():
    events: list[dict] = []
    events.append(rules.chain(1, events, "publicada", {"card_id": 1, "symbol": "A"}, "2026-01-02T09:00:00+00:00"))
    events.append(rules.chain(1, events, "revisada", {"text": "ok"}, "2026-02-02T09:00:00+00:00"))
    assert rules.verify(events)
    events[1] = events[1] | {"payload": {"text": "reescrito"}}
    assert not rules.verify(events)


def test_late_or_corrected_prices_change_the_evaluation_but_not_the_events(tmp_path):
    early = service(tmp_path, market(ACME=frame(100.0, 0.001, DAYS[:60])), today=date(2026, 6, 30))
    early.record_publication(card(1, "ACME"))
    before = early.detail(1)
    assert before["evaluation"]["end"] == DAYS[59].date().isoformat()  # Only the prices that had arrived.
    later = service(tmp_path, market(ACME=frame(100.0, -0.001)))  # Late and corrected series.
    after = later.detail(1)
    assert after["events"] == before["events"] and after["evaluation"]["end"] == "2026-06-30"
    assert after["evaluation"]["return_net"] < 0 < before["evaluation"]["return_net"]


def test_a_changed_ticker_or_missing_index_is_named_never_estimated(tmp_path):
    ideas = service(tmp_path, market())  # ACME has no cached prices under its old ticker.
    ideas.record_publication(card(1, "ACME"))
    assert ideas.detail(1)["evaluation"] == {"status": "insufficient_prices", "missing": ["ACME"]}
    no_index = service(tmp_path, lambda symbols, start: {"ACME": frame(100.0, 0.0)})
    assert no_index.detail(1)["evaluation"]["missing"] == ["SPY", "USDEUR=X"]


def test_nothing_is_registered_retrospectively(tmp_path):
    # Prices exist since January, but the idea was recorded in March: it is evaluated from March.
    ideas = service(tmp_path, market(ACME=frame(100.0, 0.001)), now=datetime(2026, 3, 2, 10, tzinfo=UTC))
    ideas.record_publication(card(1, "ACME") | {"recorded_at": "2026-01-02"})
    assert ideas.detail(1)["evaluation"]["start"] == "2026-03-02"


def test_notes_are_private_editable_and_deleting_them_keeps_the_events(tmp_path):
    ideas = service(tmp_path, market(ACME=frame(100.0, 0.001)))
    ideas.record_publication(card(1, "ACME"))
    note_id = ideas.add_note(1, "Llamar a relación con inversores")["notes"][0]["id"]
    assert ideas.save_note(1, note_id, "Hecho")["notes"][0]["text"] == "Hecho"
    after = ideas.delete_note(1, note_id)
    assert after["notes"] == [] and [event["kind"] for event in after["events"]] == ["publicada"]


def test_a_published_card_becomes_an_idea_and_discarding_it_retires_the_idea_through_the_api(tmp_path):
    content = {
        "thesis": ["Idea"], "discrepancy": "d",
        "scenarios": {"bear": {"price": 1, "assumptions": "a"}, "base": {"price": 2, "assumptions": "b"},
                      "bull": {"price": 3, "assumptions": "c"}},
        "catalysts": [{"description": "c", "horizon": "2027-01-01"}], "risks": ["r"],
        "invalidation": [{"description": "x", "metric": "m", "source": "10-K", "operator": "<", "threshold": 1,
                          "persistence": 1, "review_by": "2027-01-01"}],
        "confidence": "baja", "review_due": "2099-01-01", "position_eur": 500}
    with TestClient(create_app(Settings(tmp_path))) as api:
        assert api.get("/api/v1/portfolio/ideas").json()["items"] == []
        card_id = api.post("/api/v1/portfolio/cards", json={"symbol": "ACME", "content": content}).json()["id"]
        published = api.post(f"/api/v1/portfolio/cards/{card_id}/state", json={"target": "publicada"})
        assert published.status_code == 200, published.text
        listing = api.get("/api/v1/portfolio/ideas").json()
        assert [row["symbol"] for row in listing["items"]] == ["ACME"]
        assert listing["items"][0]["evaluation"]["status"] == "insufficient_prices"
        api.post(f"/api/v1/portfolio/cards/{card_id}/state", json={"target": "descartada", "reason": "Sin margen"})
        detail = api.get(f"/api/v1/portfolio/ideas/{card_id}").json()
        assert [event["kind"] for event in detail["events"]] == ["publicada", "retirada"]
        refused = api.post(f"/api/v1/portfolio/ideas/{card_id}/events", json={"kind": "revisada", "text": "x"})
        assert refused.status_code == 422
        assert api.get("/api/v1/portfolio/ideas/999").status_code == 404
