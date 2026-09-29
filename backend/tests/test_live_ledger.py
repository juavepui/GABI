import json
import sqlite3
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from gabi import app_mode, live_performance, periodic_tasks, screener, storage
from gabi import live_ledger as ledger

NOW = datetime(2024, 1, 10, 22, tzinfo=UTC)


@pytest.fixture(autouse=True)
def clock_and_no_network(monkeypatch):
    monkeypatch.setattr(ledger, "_now", lambda: NOW)
    monkeypatch.setattr("requests.sessions.Session.request", lambda *a, **k: pytest.fail("No network"))


def payload(status="SIGNAL", picks=None, market="2024-01-10", version="model-v1"):
    return {"model_id": app_mode.FROZEN_MODEL_ID, "model_version": version, "config_version": "config-v1",
            "market_date": market, "status": status, "top_n": ["A"] if picks is None else picks,
            "sources": {}, "data_fingerprint": "frozen-inputs", "git_commit": "abc", "configuration": {"weights": app_mode.FROZEN_WEIGHTS}}


def test_append_chain_covers_whole_payload_and_db_rejects_mutation():
    a = ledger.append_decision(payload())
    ledger.append_decision(payload("NO_SIGNAL", []))
    assert ledger.verify_integrity()["seq"] == 2
    assert ledger.events()[0] == a
    with storage.get_connection() as conn:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute("UPDATE live_ledger SET payload_json='{}' WHERE seq=1")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute("DELETE FROM live_ledger WHERE seq=2")


def test_last_record_deletion_is_detected_by_external_anchor():
    ledger.append_decision(payload())
    ledger.append_decision(payload())
    with storage.get_connection() as conn:
        conn.execute("DROP TRIGGER live_ledger_no_delete")
        conn.execute("DELETE FROM live_ledger WHERE seq=2")
        conn.commit()
    assert not ledger.verify_integrity()["ok"]
    with pytest.raises(ValueError):
        ledger.append_decision(payload())
    with pytest.raises(ValueError, match="eliminación"):
        ledger.recover_anchor("not a legitimate recovery")


def test_modifying_any_field_breaks_chain_even_if_rank_and_prices_agree():
    ledger.append_decision(payload())
    with storage.get_connection() as conn:
        conn.execute("DROP TRIGGER live_ledger_no_update")
        changed = payload()
        changed.update(kind="DECISION", stage="LIVE_FORWARD", created_at=NOW.isoformat(), git_commit="rewritten")
        conn.execute("UPDATE live_ledger SET payload_json=? WHERE seq=1", (json.dumps(changed),))
        conn.commit()
    assert not ledger.verify_integrity()["ok"]


def test_correction_adds_event_without_changing_historical_decision():
    original = ledger.append_decision(payload())
    ledger.append_correction(1, "vendor revision", {"score": 99})
    events = ledger.events()
    assert events[0] == original
    assert events[1]["payload"]["kind"] == "CORRECTION"
    assert events[1]["payload"]["original_hash"] == original["record_hash"]


def test_commit_without_anchor_requires_explicit_logged_recovery(monkeypatch):
    writer = ledger._write_anchor
    monkeypatch.setattr(ledger, "_write_anchor", lambda *args: (_ for _ in ()).throw(OSError("interrupted")))
    with pytest.raises(OSError):
        ledger.append_decision(payload())
    assert not ledger.verify_integrity()["ok"]
    monkeypatch.setattr(ledger, "_write_anchor", writer)
    ledger.recover_anchor("Process interrupted after SQLite commit; reviewed committed record")
    assert ledger.verify_integrity()["ok"]
    assert ledger.events()[1]["payload"]["kind"] == "ANCHOR_RECOVERY"


def test_stages_cannot_backdate_live_forward():
    with pytest.raises(ValueError, match="históricas"):
        ledger.append_decision(payload(), created_at="2010-01-01T22:00:00+00:00")
    event = ledger.append_decision(payload(), stage="RETROSPECTIVE", created_at="2010-01-01T22:00:00+00:00")
    assert event["payload"]["stage"] == "RETROSPECTIVE"
    assert live_performance.report(as_of="2024-01-10")["cumulative_return"] is None


def panel():
    frame = pd.DataFrame({**{f"{b}_score": np.linspace(100, 50, 30) for b in app_mode.FROZEN_WEIGHTS},
                          "composite_score": np.linspace(100, 50, 30), "score_coverage": 1., "confidence": 100.},
                         index=[f"A{i:02d}" for i in range(30)])
    frame.attrs["sources"] = {s: {"price_date": "2024-01-10", "close": 10., "adj_close": 10.,
                                  "fundamentals_fetched_at": NOW.isoformat(), "sec_fetched_at": NOW.isoformat()}
                              for s in [*frame.index, "SPY"]}
    return frame


def setup_capture(monkeypatch, frame):
    monkeypatch.setattr(screener, "get_universe", lambda: pd.DataFrame({"symbol": frame.index}))
    monkeypatch.setattr(screener, "build_screener_table", lambda *a, **k: frame.copy(deep=True))


def test_capture_freezes_inputs_exclusions_sources_and_fingerprint(monkeypatch):
    frame = panel()
    frame.loc["A00", "score_coverage"] = .5
    setup_capture(monkeypatch, frame)
    original = ledger.capture_current()
    assert original["payload"]["status"] == "SIGNAL"
    assert len(original["payload"]["top_n"]) == 20
    assert "A00" in original["payload"]["excluded"]
    assert original["payload"]["top_n"][0] == "A01"
    assert original["payload"]["sources"]["A01"]["price_date"] == "2024-01-10"
    assert len(original["payload"]["evidence"]) == 20
    assert original["payload"]["evidence"]["A01"]["confidence_level"] == "BAJA"
    assert original["payload"]["evidence"]["A01"]["trace"]["data_fingerprint"] == original["payload"]["data_fingerprint"]
    frozen = ledger.canonical(original)
    frame.loc["A01", "composite_score"] = 0
    ledger.capture_current()
    assert ledger.canonical(ledger.events()[0]) == frozen
    assert ledger.events()[1]["payload"]["data_fingerprint"] != original["payload"]["data_fingerprint"]
    replay = ledger.reproduce_decision(1)
    assert all(replay[k] for k in ("fingerprint_matches", "scores_match", "ranking_matches"))
    assert replay["replayed_top_n"] == original["payload"]["top_n"]


def test_empty_universe_is_no_signal_instead_of_a_silently_missing_execution(monkeypatch):
    setup_capture(monkeypatch, pd.DataFrame())
    assert ledger.capture_current()["payload"]["status"] == "NO_SIGNAL"


def test_capture_records_degraded_unknown_inputs_and_no_signal(monkeypatch):
    frame = panel()
    frame.attrs["sources"]["A00"]["sec_fetched_at"] = None
    setup_capture(monkeypatch, frame)
    degraded = ledger.capture_current()["payload"]
    assert degraded["status"] == "DEGRADED" and not degraded["top_n"]
    assert len(degraded["proposed_top_n"]) == 20
    frame["composite_score"] = np.nan
    assert ledger.capture_current()["payload"]["status"] == "NO_SIGNAL"


def test_failed_maintenance_is_recorded_and_does_not_rebalance(monkeypatch):
    setup_capture(monkeypatch, panel())
    monkeypatch.setattr(periodic_tasks, "status", lambda: {})
    monkeypatch.setattr(periodic_tasks, "refresh_data", lambda: (_ for _ in ()).throw(RuntimeError("no source")))
    monkeypatch.setattr(periodic_tasks, "record_due", lambda: pytest.fail("No rebalance after failed refresh"))
    report = periodic_tasks.run()
    assert report["ledger"]["status"] == "ERROR"
    assert ledger.events()[0]["payload"]["reason"] == "RuntimeError: no source"
    assert periodic_tasks.log_path().exists()


def test_partial_refresh_failures_are_frozen_as_degraded_even_with_fresh_cache(monkeypatch):
    setup_capture(monkeypatch, panel())
    event = ledger.capture_current(maintenance={"fallos": 1, "sync": {"statuses": {"failed": 1}}})
    assert event["payload"]["status"] == "DEGRADED"
    assert not event["payload"]["top_n"]
    assert event["payload"]["maintenance"]["fallos"] == 1


def test_only_failed_sources_used_in_decision_degrade_it(monkeypatch):
    setup_capture(monkeypatch, panel())
    irrelevant = {"fallos": 1, "failed": {"SPY": {"edgar": "ETF without company facts"}}}
    event = ledger.capture_current(maintenance=irrelevant)
    assert event["payload"]["status"] == "SIGNAL"
    assert event["payload"]["maintenance"]["failed"] == irrelevant["failed"]
    relevant = {"fallos": 1, "failed": {"A00": {"edgar": "failed"}}}
    event = ledger.capture_current(maintenance=relevant)
    assert event["payload"]["status"] == "DEGRADED"
    assert event["payload"]["quality"]["failed_inputs"] == ["A00:edgar"]


def test_cli_keeps_failure_exit_status_for_task_scheduler(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["periodic_tasks", "--run"])
    monkeypatch.setattr(periodic_tasks, "run", lambda **kwargs: {"error": "provider failed", "ledger": {"status": "ERROR"}})
    with pytest.raises(SystemExit) as error:
        periodic_tasks.main()
    assert error.value.code == 1
    assert "provider failed" in capsys.readouterr().out


def seed(symbol, opens, closes):
    dates = pd.to_datetime(["2024-01-09", "2024-01-10"])
    storage.upsert_prices(symbol, pd.DataFrame({"Open": opens, "High": np.maximum(opens, closes),
                                              "Low": np.minimum(opens, closes), "Close": closes,
                                              "Adj Close": closes, "Volume": 100.}, index=dates))


def decisions(monkeypatch, first_status="SIGNAL"):
    monkeypatch.setattr(ledger, "_now", lambda: datetime(2024, 1, 8, 22, tzinfo=UTC))
    ledger.append_decision(payload(first_status, [] if first_status != "SIGNAL" else ["A"], market="2024-01-08"))
    monkeypatch.setattr(ledger, "_now", lambda: datetime(2024, 1, 9, 22, tzinfo=UTC))
    ledger.append_decision(payload(picks=["B"], market="2024-01-09"))
    monkeypatch.setattr(ledger, "_now", lambda: NOW)


def test_prospective_nav_uses_next_open_costs_nonoverlapping_intervals_and_drift(monkeypatch):
    decisions(monkeypatch)
    seed("A", [10, 12], [10, 12])
    seed("B", [12, 12], [12, 15])
    seed("SPY", [100, 105], [100, 110])
    report = live_performance.report(as_of="2024-01-10")
    assert report["complete"]
    assert report["cumulative_return"] == pytest.approx(.999 * 1.2 * .998 * 1.25 - 1)
    assert report["benchmark_return"] == pytest.approx(.999 * 1.1 - 1)
    assert report["intervals"][0]["entry"] == "2024-01-09"
    assert report["intervals"][0]["end"] == "2024-01-10"
    assert report["intervals"][1]["turnover_notional"] == 2
    old = ledger.events()[0]
    ledger.save_evaluation(report)
    assert ledger.events()[0] == old
    assert ledger.events()[-1]["payload"]["kind"] == "EVALUATION"


def test_first_failed_decision_for_entry_session_is_not_replaced_by_favorable_retry(monkeypatch):
    monkeypatch.setattr(ledger, "_now", lambda: datetime(2024, 1, 9, 22, tzinfo=UTC))
    ledger.append_decision(payload("ERROR", [], market="2024-01-09"))
    ledger.append_decision(payload(picks=["B"], market="2024-01-09"))
    monkeypatch.setattr(ledger, "_now", lambda: NOW)
    seed("B", [12, 12], [12, 15])
    report = live_performance.report(as_of="2024-01-10")
    assert len(report["intervals"]) == 1
    assert report["cumulative_return"] == 0
    assert report["intervals"][0]["seq"] == 1


def test_missing_firm_blocks_performance_instead_of_removing_it(monkeypatch):
    decisions(monkeypatch)
    seed("B", [12, 12], [12, 15])
    report = live_performance.report(as_of="2024-01-10")
    assert not report["complete"] and report["cumulative_return"] is None
    assert report["intervals"][0]["missing"] == ["A"]
    assert report["intervals"][1]["nav"] is None


def test_different_models_require_explicit_selection():
    ledger.append_decision(payload(version="a"))
    ledger.append_decision(payload(version="b"))
    with pytest.raises(ValueError, match="varias versiones"):
        live_performance.report()


def test_unknown_issuer_cannot_use_a_recycled_ticker(monkeypatch):
    from gabi import identity

    decisions(monkeypatch)
    seed("A", [10, 12], [10, 12])
    identity.add_alias(identity.ensure_entity("2"), "A", "2024-01-09", source="new issuer")
    report = live_performance.report(as_of="2024-01-10")
    assert report["intervals"][0]["missing"] == ["A"]


def test_entry_calendar_handles_weekend_and_dst():
    assert live_performance.entry_session("2024-03-08T22:00:00+00:00") == "2024-03-11"
    assert live_performance.entry_session("2024-03-11T13:00:00+00:00") == "2024-03-11"
    assert live_performance.entry_session("2024-03-11T13:31:00+00:00") == "2024-03-12"


def test_malformed_payload_is_reported_as_integrity_failure():
    ledger.append_decision(payload())
    with storage.get_connection() as conn:
        conn.execute("DROP TRIGGER live_ledger_no_update")
        conn.execute("UPDATE live_ledger SET payload_json='not json' WHERE seq=1")
        conn.commit()
    assert not ledger.verify_integrity()["ok"]


def test_revised_outcome_prices_change_report_but_not_original_decision(monkeypatch):
    decisions(monkeypatch)
    seed("A", [10, 12], [10, 12])
    seed("B", [12, 12], [12, 15])
    first = ledger.events()[0]
    a = live_performance.report(as_of="2024-01-10")
    seed("B", [12, 12], [12, 18])
    b = live_performance.report(as_of="2024-01-10")
    assert a["outcome_data_fingerprint"] != b["outcome_data_fingerprint"]
    assert a["cumulative_return"] != b["cumulative_return"]
    assert ledger.events()[0] == first
