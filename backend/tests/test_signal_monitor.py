import sqlite3

import numpy as np
import pandas as pd

from gabi.domain.market import signals as signal_monitor
from gabi.infrastructure.storage.signals import SqliteSignals


def _table(rows: dict) -> pd.DataFrame:
    """rows: {symbol: {"rank":.., "composite_score":.., "confidence":.., "sector":..}}"""
    return pd.DataFrame.from_dict(rows, orient="index")


BASE_PREV = _table({
    "AAA": {"rank": 1, "composite_score": 90.0, "confidence": 100.0, "sector": "Tech"},
    "BBB": {"rank": 2, "composite_score": 80.0, "confidence": 90.0, "sector": "Salud"},
    "CCC": {"rank": 3, "composite_score": 70.0, "confidence": 80.0, "sector": "Financiero"},
})


def test_identical_snapshots_produce_no_events():
    events = signal_monitor.compare_snapshots(BASE_PREV, BASE_PREV.copy(), top_n=3)
    assert events == []


def test_top_n_entry_and_exit_are_material():
    current = _table({
        "AAA": {"rank": 1, "composite_score": 90.0, "confidence": 100.0, "sector": "Tech"},
        "BBB": {"rank": 2, "composite_score": 80.0, "confidence": 90.0, "sector": "Salud"},
        "DDD": {"rank": 3, "composite_score": 71.0, "confidence": 80.0, "sector": "Energía"},  # nueva, CCC sale
    })
    events = signal_monitor.compare_snapshots(BASE_PREV, current, top_n=3)
    by_type = {(e["symbol"], e["event_type"]): e for e in events}

    assert ("DDD", "top_n_entry") in by_type
    assert by_type[("DDD", "top_n_entry")]["severity"] == "MATERIAL"
    assert by_type[("DDD", "top_n_entry")]["previous_value"] is None
    assert by_type[("DDD", "top_n_entry")]["new_value"] == 3

    assert ("CCC", "top_n_exit") in by_type
    assert by_type[("CCC", "top_n_exit")]["severity"] == "MATERIAL"
    assert by_type[("CCC", "top_n_exit")]["previous_value"] == 3
    assert by_type[("CCC", "top_n_exit")]["new_value"] is None


def test_rank_change_below_threshold_is_silent():
    current = BASE_PREV.copy()
    current.loc["BBB", "rank"] = 3
    current.loc["CCC", "rank"] = 2  # se cruzan, diferencia de 1 -- por debajo del umbral por defecto (5)
    events = signal_monitor.compare_snapshots(BASE_PREV, current, top_n=3)
    assert events == []


def test_rank_change_above_threshold_is_watch():
    current = BASE_PREV.copy()
    current.loc["CCC", "rank"] = 3 + 5  # diferencia de 5 -- toca el umbral por defecto
    events = signal_monitor.compare_snapshots(BASE_PREV, current, top_n=10)
    rank_events = [e for e in events if e["event_type"] == "rank_change"]
    assert len(rank_events) == 1
    assert rank_events[0]["symbol"] == "CCC"
    assert rank_events[0]["severity"] == "WATCH"
    assert rank_events[0]["previous_value"] == 3
    assert rank_events[0]["new_value"] == 8


def test_score_change_above_threshold_is_material():
    current = BASE_PREV.copy()
    current.loc["AAA", "composite_score"] = 90.0 - 10.0  # toca el umbral por defecto (10)
    events = signal_monitor.compare_snapshots(BASE_PREV, current, top_n=3)
    score_events = [e for e in events if e["event_type"] == "score_change"]
    assert len(score_events) == 1
    assert score_events[0]["symbol"] == "AAA"
    assert score_events[0]["severity"] == "MATERIAL"
    assert score_events[0]["previous_value"] == 90.0
    assert score_events[0]["new_value"] == 80.0


def test_score_change_below_threshold_is_silent():
    current = BASE_PREV.copy()
    current.loc["AAA", "composite_score"] = 90.0 - 9.0  # por debajo del umbral (10)
    events = signal_monitor.compare_snapshots(BASE_PREV, current, top_n=3)
    assert [e for e in events if e["event_type"] == "score_change"] == []


def test_confidence_drop_is_watch_but_confidence_rise_is_silent():
    current = BASE_PREV.copy()
    current.loc["AAA", "confidence"] = 100.0 - 20.0  # toca el umbral por defecto (20)
    current.loc["BBB", "confidence"] = 90.0 + 30.0  # sube mucho -- una subida nunca es evento
    events = signal_monitor.compare_snapshots(BASE_PREV, current, top_n=3)
    conf_events = [e for e in events if e["event_type"] == "confidence_drop"]
    assert len(conf_events) == 1
    assert conf_events[0]["symbol"] == "AAA"
    assert conf_events[0]["severity"] == "WATCH"


def test_sector_change_is_watch():
    current = BASE_PREV.copy()
    current.loc["BBB", "sector"] = "Industrial"
    events = signal_monitor.compare_snapshots(BASE_PREV, current, top_n=3)
    sector_events = [e for e in events if e["event_type"] == "sector_change"]
    assert len(sector_events) == 1
    assert sector_events[0]["symbol"] == "BBB"
    assert sector_events[0]["severity"] == "WATCH"
    assert sector_events[0]["previous_value"] == "Salud"
    assert sector_events[0]["new_value"] == "Industrial"


def test_eligibility_change_is_info():
    current = BASE_PREV.copy()
    current.loc["CCC", "composite_score"] = np.nan
    events = signal_monitor.compare_snapshots(BASE_PREV, current, top_n=3)
    elig_events = [e for e in events if e["event_type"] == "eligibility_change"]
    assert len(elig_events) == 1
    assert elig_events[0]["symbol"] == "CCC"
    assert elig_events[0]["severity"] == "INFO"
    assert elig_events[0]["new_value"] is None
    # No debe generar TAMBIÉN un score_change para la misma fila.
    assert [e for e in events if e["event_type"] == "score_change" and e["symbol"] == "CCC"] == []


def test_missing_columns_do_not_crash():
    previous = _table({"AAA": {"rank": 1}})  # sin composite_score/confidence/sector
    current = _table({"AAA": {"rank": 1}})
    assert signal_monitor.compare_snapshots(previous, current, top_n=1) == []


def test_comparison_is_deterministic_regardless_of_row_order():
    current = BASE_PREV.copy()
    current.loc["AAA", "composite_score"] = 70.0  # dispara score_change
    shuffled = current.loc[["CCC", "AAA", "BBB"]]
    events_a = signal_monitor.compare_snapshots(BASE_PREV, current, top_n=3)
    events_b = signal_monitor.compare_snapshots(BASE_PREV, shuffled, top_n=3)
    assert events_a == events_b


def test_severities_are_only_the_three_allowed_values():
    current = BASE_PREV.copy()
    current.loc["AAA", "composite_score"] = 70.0
    current.loc["BBB", "confidence"] = 50.0
    current.loc["CCC", "composite_score"] = np.nan
    events = signal_monitor.compare_snapshots(BASE_PREV, current, top_n=3)
    assert events  # sanity: de verdad se generaron eventos
    assert {e["severity"] for e in events} <= set(signal_monitor.SEVERITIES)


def _rows(tmp_path):
    with sqlite3.connect(tmp_path / "gabi.db") as db:
        return db.execute("SELECT from_snapshot_id,to_snapshot_id,symbol,event_type FROM signal_events").fetchall()


def test_record_events_is_idempotent_on_repeated_calls(tmp_path):
    events = signal_monitor.compare_snapshots(
        BASE_PREV, BASE_PREV.assign(composite_score=lambda d: d["composite_score"] - 15), top_n=3)
    assert events  # sanity
    store = SqliteSignals(tmp_path)
    store.record(events, 1)
    store.record(events, 1)  # repetido
    assert len(_rows(tmp_path)) == len(events)  # no se duplicó por llamar dos veces


def test_record_events_noop_for_empty_list(tmp_path):
    SqliteSignals(tmp_path).record([], 1)
    assert not (tmp_path / "gabi.db").exists()
    assert SqliteSignals(tmp_path).events(None, 200) == []


def test_list_events_filters_by_severity_and_since(tmp_path):
    events = [
        {"symbol": "AAA", "event_type": "score_change", "severity": "MATERIAL",
         "previous_value": 90.0, "new_value": 70.0, "cause": "test"},
        {"symbol": "BBB", "event_type": "sector_change", "severity": "WATCH",
         "previous_value": "Tech", "new_value": "Salud", "cause": "test"},
    ]
    store = SqliteSignals(tmp_path)
    store.record(events, 1)
    assert len(store.events(None, 200)) == 2
    material_only = store.events("MATERIAL", 200)
    assert [(e["symbol"], e["previous_value"], e["new_value"]) for e in material_only] == [("AAA", 90.0, 70.0)]
    assert store.events(None, 200, since="9999-01-01") == []


def test_stored_no_snapshot_sentinel_reads_back_as_absent(tmp_path):
    event = {"symbol": "AAA", "event_type": "score_change", "severity": "MATERIAL",
             "previous_value": 90.0, "new_value": 70.0, "cause": "test"}
    store = SqliteSignals(tmp_path)
    store.record([event], 4)
    assert _rows(tmp_path) == [(4, 0, "AAA", "score_change")]
    item = store.events(None, 200)[0]
    assert (item["from_snapshot_id"], item["to_snapshot_id"]) == (4, None)
