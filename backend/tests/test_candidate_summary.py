"""«Por qué está aquí» (#184): the fixed wording rules, missing data included, and where the API serves them."""

import pandas as pd
from fastapi.testclient import TestClient
from market_fixture import TODAY, seed_fixture

from gabi.domain.market.candidate_summary import summarize
from gabi.infrastructure.settings import Settings
from gabi_api.bootstrap import create_app

APA = {"value_score": 81.0, "quality_score": 95.0, "momentum_score": 86.0, "risk_score": 22.0,
       "score_coverage": 0.95, "max_drawdown": -0.967, "next_earnings_days": 13}


def test_the_issue_example_names_the_two_best_blocks_the_weak_one_and_the_main_warning():
    summary = summarize(APA)
    assert summary["text"] == "Fuerte en calidad y momentum · Débil en riesgo · Resultados en 13 días"
    assert summary["strengths"] == ["quality", "momentum"] and summary["weakness"] == "risk"
    assert summary["warning"] == "earnings"
    assert summary["blocks"] == {"value": 81.0, "quality": 95.0, "momentum": 86.0, "risk": 22.0}


def test_warnings_follow_their_priority_and_thresholds():
    assert summarize(APA | {"score_coverage": 0.55})["text"].endswith("Datos incompletos (55 % de las métricas)")
    assert summarize(APA | {"next_earnings_days": 15})["text"].endswith("Caída máxima −96,7 %")
    assert summarize(APA | {"next_earnings_days": 0})["text"].endswith("Resultados hoy")
    assert summarize(APA | {"next_earnings_days": 1})["text"].endswith("Resultados mañana")
    # Past results and a moderate drawdown give no warning.
    calm = summarize(APA | {"next_earnings_days": -3, "max_drawdown": -0.30})
    assert calm["warning"] is None and calm["text"] == "Fuerte en calidad y momentum · Débil en riesgo"


def test_the_limits_are_inclusive_and_a_single_strength_reads_alone():
    row = {"value_score": 70.0, "quality_score": 69.9, "momentum_score": 50.0, "risk_score": 30.0}
    assert summarize(row)["text"] == "Fuerte en valoración · Débil en riesgo"
    middle = summarize({"value_score": 60.0, "quality_score": 50.0, "momentum_score": 40.0, "risk_score": 31.0})
    assert middle["text"] == "Sin bloques destacados" and middle["strengths"] == [] and middle["weakness"] is None


def test_missing_values_are_never_strong_weak_or_a_warning():
    row = {"value_score": None, "quality_score": float("nan"), "momentum_score": 90.0, "risk_score": None,
           "score_coverage": None, "max_drawdown": float("nan"), "next_earnings_days": None}
    summary = summarize(row)
    assert summary["text"] == "Fuerte en momentum" and summary["weakness"] is None and summary["warning"] is None
    assert summary["blocks"] == {"value": None, "quality": None, "momentum": 90.0, "risk": None}
    empty = summarize(pd.Series({"score_coverage": 0.2}))
    assert empty["text"] == "Sin bloques del score calculados · Datos incompletos (20 % de las métricas)"
    assert summarize({})["text"] == "Sin bloques del score calculados"


def test_ranking_company_and_target_portfolio_carry_the_same_summary(tmp_path):
    seed_fixture(tmp_path)
    with TestClient(create_app(Settings(tmp_path), today=lambda: TODAY)) as api:
        ranking = api.get("/api/v1/ranking", params={"limit": 5}).json()
        first = ranking["items"][0]
        metrics = {key: first["metrics"][key + "_score"]["value"] for key in ("value", "quality", "momentum", "risk")}
        assert first["summary"]["blocks"] == metrics and first["summary"]["text"]
        company = api.get(f"/api/v1/companies/{first['symbol']}").json()["company"]
        assert company["summary"] == first["summary"]
        plan = api.post("/api/v1/portfolio/plan", json={"n_positions": 5}).json()
        target = {row["symbol"]: row["summary"] for row in plan["target"]}
        assert target.get(first["symbol"], first["summary"]) == first["summary"]
        assert target and all(summary["text"] for summary in target.values())
