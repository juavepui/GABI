"""A saved decision plan warns when today's ranking no longer supports it (#191)."""

from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient
from market_fixture import TODAY, seed_fixture

from gabi import config
from gabi.domain.portfolio.plan_freshness import SCORE_CHANGE, freshness
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.decisions import SqliteDecisions
from gabi_api.bootstrap import create_app


def row(symbol, score, target=5.0):
    return {"symbol": symbol, "action": "COMPRAR", "current_pct": 0, "target_pct": target,
            "change_pct": target, "reason": "test", "score": score}


def test_small_moves_are_not_material():
    result = freshness("2026-09-16T10:00:00", [row("A", 80.0), row("B", 70.0)],
                       {"A": 80.0 - SCORE_CHANGE + 0.1, "B": 71.0}, 65, date(2026, 10, 21))
    assert result["age_days"] == 35 and result["positions"] == 2
    assert result["material"] is False and result["changes"] == []
    assert freshness("2026-10-22T09:00:00", [], {}, None, date(2026, 10, 21))["age_days"] == 0


def test_score_drop_minimum_and_missing_score_are_material():
    plan = [row("INCY", 80.61), row("LOW", 70.0), row("GONE", 70.0), row("SOLD", 90.0, target=0)]
    result = freshness("2026-09-16", plan, {"INCY": 71.1, "LOW": 60.0, "SOLD": 10.0}, 65,
                       date(2026, 10, 21))
    assert result["material"] is True
    assert result["positions"] == 3  # A sale (target 0) is not a position of the plan.
    by_symbol = {change["symbol"]: change for change in result["changes"]}
    assert by_symbol["INCY"] == {"symbol": "INCY", "saved_score": 80.61, "current_score": 71.1,
                                 "label": "Su score ha cambiado 5 puntos o más"}
    assert by_symbol["LOW"]["label"] == "Por debajo del score mínimo del plan (65)"
    assert by_symbol["GONE"]["current_score"] is None
    assert "SOLD" not in by_symbol


def test_freshness_endpoint_reads_current_ranking_without_writing(tmp_path, monkeypatch):
    seed_fixture(tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    with TestClient(create_app(Settings(tmp_path), today=lambda: TODAY)) as api:
        ranking = api.get("/api/v1/ranking?limit=3&hide_no_data=false").json()["items"]
        current = {item["symbol"]: item["metrics"]["composite_score"]["value"] for item in ranking}
        repo = SqliteDecisions(tmp_path, now=lambda: datetime.combine(
            TODAY - timedelta(days=12), datetime.min.time(), UTC))
        policy = {"min_score": 0}
        same = repo.save({"decisions": [row(symbol, score) for symbol, score in current.items()],
                          "method": "test", "policy": policy, "holdings": {}}, "Al día", "fresh-plan")
        moved = repo.save({"decisions": [row(symbol, score + 10) for symbol, score in current.items()],
                           "method": "test", "policy": policy, "holdings": {}}, "Desfasado", "stale-plan")
        before = sorted(path.name for path in tmp_path.iterdir())
        fresh = api.get(f"/api/v1/portfolio/decisions/{same}/freshness").json()
        assert fresh["material"] is False and fresh["age_days"] == 12 and fresh["positions"] == 3
        stale = api.get(f"/api/v1/portfolio/decisions/{moved}/freshness").json()
        assert stale["material"] is True and len(stale["changes"]) == 3
        assert api.get("/api/v1/portfolio/decisions/999/freshness").status_code == 404
        assert sorted(path.name for path in tmp_path.iterdir()) == before
