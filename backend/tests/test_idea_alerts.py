"""Idea alerts (#247): registered conditions, data revision versus deterioration, absence and idempotent runs."""

from datetime import UTC, date, datetime

import pandas as pd
import pytest

from gabi.application.errors import QueryError
from gabi.application.portfolio import idea_alerts as job
from gabi.application.portfolio.ideas import Ideas
from gabi.domain.portfolio import idea_alerts as rules
from gabi.infrastructure.storage.ideas import SqliteIdeas

CONDITION = {"description": "Cae el margen", "metric": "Margen operativo", "source": "10-K", "operator": "<",
             "threshold": 0.12, "persistence": 2, "review_by": "2027-06-30"}


def metrics(value):
    return [{"key": "operating_margin", "label": "Margen operativo", "value": value, "source": "sec_10k"}]


def test_persistence_counts_distinct_fiscal_periods_and_a_restatement_is_not_a_deterioration():
    found, alerts = rules.conditions([CONDITION], metrics(0.10), "2025-12-31", {})
    assert found == [{"condition": 0, "period": "2025-12-31", "value": 0.10}]
    assert alerts == []  # One period below the threshold; the condition asks for two.
    history = {0: found}
    again, alerts = rules.conditions([CONDITION], metrics(0.10), "2025-12-31", history)
    assert again == [] and alerts == []  # Same period, same value: nothing new.
    restated, alerts = rules.conditions([CONDITION], metrics(0.13), "2025-12-31", history)
    assert [alert["kind"] for alert in alerts] == ["revision_dato"]
    history[0] += restated
    _, alerts = rules.conditions([CONDITION], metrics(0.11), "2026-12-31", {0: [{"period": "2025-12-31", "value": 0.10}]})
    assert [alert["kind"] for alert in alerts] == ["invalidacion"] and alerts[0]["evidence"]["streak"] == 2


def test_absence_and_unknown_metrics_are_named_not_treated_as_deterioration():
    _, alerts = rules.conditions([CONDITION], metrics(None), "2025-12-31", {})
    assert [alert["kind"] for alert in alerts] == ["ausencia"] and "no es un deterioro" in alerts[0]["message"]
    _, alerts = rules.conditions([CONDITION | {"metric": "cuota de mercado"}], metrics(0.1), "2025-12-31", {})
    assert [alert["kind"] for alert in alerts] == ["no_evaluable"]
    assert rules.conditions([{"description": "vaga"}], metrics(0.1), "2025-12-31", {}) == ([], [])


def test_other_signals_only_after_publication_and_reviews_due():
    alerts = rules.signals(
        "2026-03-01",
        filings=[{"form": "10-Q", "current": {"filed_date": "2026-05-01", "period_end": "2026-03-31"}},
                 {"form": "10-K", "current": {"filed_date": "2026-02-15", "period_end": "2025-12-31"}}],
        surprises=[{"earnings_date": "2026-04-30", "surprise_pct": -4.2}, {"earnings_date": "2026-01-30",
                                                                          "surprise_pct": -9.0}],
        revision={"change_pct": -0.08, "current_captured_at": "2026-06-01T10:00", "actual_lookback_days": 88},
        insiders={"net_value": -2e6, "distinct_sellers": 3, "months": 6},
        evaluation={"status": "ok", "excess": -0.12, "max_drawdown": -0.08}, month="2026-06")
    assert [alert["kind"] for alert in alerts] == ["filing", "resultados", "estimaciones", "insiders", "tendencia"]
    due = rules.reviews_due({"review_due": "2026-06-01", "invalidation": [CONDITION]}, date(2026, 7, 1))
    assert [alert["key"] for alert in due] == ["revision_vencida:2026-06-01", "revision_vencida:0:2027-06-30"][:1]


def card(content):
    return {"id": 1, "symbol": "ACME", "snapshot_sha256": "a" * 64, "content": content,
            "snapshot": {"decision": {"costs": {"round_trip_share": 0.01}}}}


def test_the_job_is_idempotent_and_alerts_stay_pending_until_reviewed(tmp_path):
    days = pd.bdate_range("2026-01-02", "2026-06-30")
    frame = pd.DataFrame({"adj_close": 100.0, "close": 100.0}, index=days)
    prices = {"ACME": frame, "SPY": frame * 5, "USDEUR=X": frame / 100}
    clock = {"now": datetime(2026, 1, 2, 9, tzinfo=UTC)}
    ideas = Ideas(SqliteIdeas(tmp_path), lambda symbols, start: {s: prices[s] for s in symbols},
                  lambda: date(2026, 6, 30), lambda: clock["now"])
    content = {"review_due": "2026-06-01", "invalidation": [CONDITION | {"persistence": 1}], "position_eur": 1000}
    ideas.record_publication(card(content))
    state = {"margin": 0.10, "period": "2025-12-31"}

    def checklist(symbol):
        return {"fiscal_year_end": state["period"], "criteria": metrics(state["margin"])}

    def unavailable(symbol):
        raise QueryError("missing", "sin datos", 404)

    ports = {"card": lambda card_id: card(content), "checklist": checklist, "filings": unavailable,
             "overview": unavailable, "insiders": unavailable, "today": lambda: date(2026, 6, 30)}
    clock["now"] = datetime(2026, 6, 30, 8, tzinfo=UTC)
    first = job.run(ideas, **ports)
    assert first["new_alerts"] == 2  # The condition and the card's review date.
    assert job.run(ideas, **ports)["new_alerts"] == 0  # Same data: idempotent.
    assert len(ideas.detail(1)["pending_alerts"]) == 2
    clock["now"] = datetime(2026, 6, 30, 9, tzinfo=UTC)
    ideas.append(1, "revisada", {"text": "Revisadas las alertas"})
    assert ideas.detail(1)["pending_alerts"] == []
    state.update(margin=0.14)  # The same fiscal year is restated: a data revision, not another deterioration.
    clock["now"] = datetime(2026, 6, 30, 10, tzinfo=UTC)
    job.run(ideas, **ports)
    pending = ideas.detail(1)["pending_alerts"]
    assert [alert["kind"] for alert in pending] == ["revision_dato"]
    ideas.append(1, "cerrada", {"outcome": "fallida", "cause": "margen", "executed": False})
    assert job.run(ideas, **ports)["ideas"] == 0  # Closed ideas are no longer watched, but stay evaluated.


def test_the_job_is_a_known_explicit_kind():
    from gabi.application.administration.jobs import JobCommand

    assert JobCommand("idea_alerts").kind == "idea_alerts"
    with pytest.raises(QueryError):
        JobCommand("idea_alerts", symbols=("ACME",))
