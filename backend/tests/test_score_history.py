"""Puntuación de cada día (#328): what the daily task stores, how a company reads it and «desde ayer»."""

import hashlib
from datetime import date

import pandas as pd
from fastapi.testclient import TestClient
from market_fixture import TODAY, seed_fixture

from gabi.application.administration.periodic import PeriodicTasks
from gabi.domain.market import score_history as rules
from gabi.domain.portfolio import daily_summary
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.score_history import SqliteScoreHistory
from gabi_api.bootstrap import create_app

MODEL = "GABI-MF-v3"


def test_rows_keep_the_ranking_position_and_skip_companies_without_score():
    table = pd.DataFrame({"composite_score": [80.0, 70.0, float("nan")]}, index=["AAA", "BBB", "CCC"])
    assert rules.rows(table) == [("AAA", 80.0, 1), ("BBB", 70.0, 2)]


def test_store_replaces_a_rerun_and_reads_oldest_first_and_the_previous_day(tmp_path):
    store = SqliteScoreHistory(tmp_path)
    assert store.company("AAA") == [] and store.previous_day(MODEL, "2026-11-05") is None
    assert not (tmp_path / "gabi.db").exists()  # Readers never create it.
    store.record("2026-11-03", MODEL, "v2.1", [("AAA", 60.0, 5), ("BBB", 50.0, 9)], 500)
    store.record("2026-11-04", MODEL, "v2.1", [("AAA", 61.0, 4)], 500)
    store.record("2026-11-04", MODEL, "v2.1", [("AAA", 62.0, 3)], 500)  # Rerun the same day: the last one stays.
    store.record("2026-11-04", "GABI-MF-v2", None, [("AAA", 40.0, 30)], 500)
    days = store.company("AAA")
    assert [(row["day"], row["model_id"], row["score"]) for row in days] == [
        ("2026-11-03", MODEL, 60.0), ("2026-11-04", "GABI-MF-v2", 40.0), ("2026-11-04", MODEL, 62.0)]
    assert store.previous_day(MODEL, "2026-11-04") == ("2026-11-03", {"AAA": (60.0, 5), "BBB": (50.0, 9)})


def test_reading_compares_only_days_of_the_active_model():
    assert rules.reading([], MODEL)["text"].startswith("Todavía no hay días guardados")
    one = rules.reading([{"day": "2026-11-04", "model_id": MODEL, "score": 62.0, "rank": 3, "universe": 500}], MODEL)
    assert one["text"].endswith("Hace falta al menos otro día con el mismo modelo para ver cómo cambia.")
    points = [{"day": "2026-11-02", "model_id": "GABI-MF-v2", "score": 40.0, "rank": 30, "universe": 500},
              {"day": "2026-11-03", "model_id": MODEL, "score": 60.0, "rank": 5, "universe": 500},
              {"day": "2026-11-04", "model_id": MODEL, "score": 62.5, "rank": 3, "universe": 500}]
    text = rules.reading(points, MODEL)["text"]
    assert text == ("Datos desde el 2 nov 2026 (3 días guardados). Los días anteriores puntuaba otro modelo y no se "
                    "comparan. Desde el 3 nov 2026, su puntuación ha subido de 60,0 a 62,5 y su puesto ha pasado "
                    "del 5 al 3.")


def test_daily_task_records_after_the_ledger_and_a_failure_does_not_touch_it():
    class Operations:
        def __init__(self, fail):
            self.fail, self.calls = fail, []

        def verify_ledger(self):
            return {"ok": True}

        def capture_ledger(self, error, maintenance):
            self.calls.append("ledger")
            return {"seq": 1, "record_hash": "h", "payload": {"status": "OK"}}

        def capture_active_ledger(self, error, maintenance):
            return None

        def record_scores(self):
            self.calls.append("scores")
            if self.fail:
                raise OSError("disco lleno")
            return {"dia": "2026-11-04", "guardadas": 500}

    class Store:
        def log(self, event):
            pass

    def run(fail):
        operations = Operations(fail)
        tasks = PeriodicTasks(Store(), operations, None, lambda: pd.Timestamp("2026-11-05T05:00Z").to_pydatetime(),
                              lambda: 0.0, lambda: 0.0)
        tasks.status = lambda: {}
        tasks.record_due = lambda: []
        tasks.smallmid_step = lambda: {}
        return operations, tasks.run(refresh=False)

    operations, report = run(False)
    assert operations.calls == ["ledger", "scores"] and report["puntuaciones"]["guardadas"] == 500
    operations, report = run(True)
    assert report["ledger"]["status"] == "OK" and "error" not in report
    assert report["puntuaciones"] == {"error": "OSError: disco lleno"}


def test_api_reads_the_company_days_without_writing(tmp_path):
    seed_fixture(tmp_path, companies=30)
    SqliteScoreHistory(tmp_path).record("2026-09-28", "GABI-MF-v3", None, [("T000", 60.0, 2)], 30)
    before = hashlib.sha256((tmp_path / "gabi.db").read_bytes()).hexdigest()
    with TestClient(create_app(Settings(tmp_path), today=lambda: TODAY)) as api:
        body = api.get("/api/v1/companies/T000/score-history").json()
        empty = api.get("/api/v1/companies/T001/score-history").json()
    assert hashlib.sha256((tmp_path / "gabi.db").read_bytes()).hexdigest() == before
    assert body["points"][0]["score"] == 60.0 and body["reading"]["values"]["days"] == 1
    assert empty["points"] == [] and empty["reading"]["text"].startswith("Todavía no hay días guardados")


def test_summary_measures_since_the_last_stored_day_for_all_your_companies():
    previous = {"day": "2026-11-04", "rows": [
        {"symbol": "AAA", "composite_score": 70.0, "rank": 2, "same_model": True, "score_at_add": 58.0,
         "rank_at_add": 9, "added_at": "2026-11-04", "score_change": 12.0, "rank_change": 7},
        {"symbol": "HELD", "composite_score": 50.0, "rank": 40, "same_model": True, "score_at_add": 49.0,
         "rank_at_add": 41, "added_at": "2026-11-04", "score_change": 1.0, "rank_change": 1}]}
    result = daily_summary.build(watched=[], held=["AAA", "HELD"], target=[], scored={"AAA", "HELD"}, earnings={},
                                 latest_price_date="2026-11-05", target_size=20, today=date(2026, 11, 6),
                                 model_id=MODEL, previous=previous)
    moves = next(item for item in result["sentences"] if item["kind"] == "moves")
    assert moves["text"] == ("Desde el último día guardado (4 nov), 1 de tus empresas ha cambiado mucho: AAA sube "
                             "12,0 puntos (de 58,0 a 70,0).")
    assert moves["values"]["since_day"] == "2026-11-04"
    calm = daily_summary.build(watched=[], held=["HELD"], target=[], scored={"HELD"}, earnings={},
                               latest_price_date="2026-11-05", target_size=20, today=date(2026, 11, 6),
                               model_id=MODEL, previous={"day": "2026-11-04", "rows": previous["rows"][1:]})
    calm_text = next(item for item in calm["sentences"] if item["kind"] == "moves")["text"]
    assert calm_text == ("Tu empresa no ha cambiado mucho desde el último día guardado (4 nov): menos de 10 puntos y "
                         "de 5 puestos.")
