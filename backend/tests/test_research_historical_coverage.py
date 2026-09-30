"""Historical ranking coverage warnings match the Streamlit reconstruction page."""

import pandas as pd
from fastapi.testclient import TestClient

from gabi import data_quality, scoring
from gabi.application.administration.jobs import JobCommand
from gabi.application.research.historical import build_historical_ranking
from gabi.infrastructure.jobs.worker import Worker
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.jobs import SqliteJobs
from gabi_api.bootstrap import create_app


def _table(historical=False):
    rows = []
    for i in range(10):
        row = {"symbol": f"T{i:03d}", "name": f"Empresa {i}", "sector": None if i < 3 else "Industrials",
               "sector_is_approximate": i in (3, 4, 5, 6), "roic": 0.1 if i % 2 else None,
               "market_cap": 1e9 if i < 7 else None, "composite_score": 50.0 + i, "score_coverage": 0.8,
               "identity_status": "ambiguous" if i == 0 else "unresolved" if i in (1, 2) else "resolved"}
        for block, columns in scoring.SCORE_METRICS.items():
            for n, column in enumerate(columns):
                row[f"{column}_pct"] = None if (block == "value" and i < 5 and n == 0) else 0.5
        rows.append(row)
    table = pd.DataFrame(rows).set_index("symbol")
    info = {"is_exact": True, "note": "fixture"}
    if historical:
        info["historical_coverage"] = {"members": 10, "identity_accredited": 7, "accredited_prices": 6,
                                       "scored": 5, "excluded": {"identity_unresolved_or_ambiguous": 3},
                                       "price_sources": {"sec": 6}}
    return {"table": table, "universe_info": info}


def _streamlit_warnings(df, threshold):
    """The exact expressions of app/pages/8_Ranking_Historico.py."""
    messages = []
    bad = float((df["sector"].isna() | df.get("sector_is_approximate", False)).mean()) if len(df) else 0
    if bad > (1 - threshold):
        messages.append(
            f"**Sector**: {bad:.0%} de las empresas de esta tabla tienen sector aproximado o "
            "desconocido para esta fecha -- el color por sector y los percentiles sectoriales de una buena "
            "parte de la tabla no son point-in-time reales.")
    return messages + data_quality.block_coverage_warnings(data_quality.score_block_coverage(df), threshold)


def _job(tmp_path, historical=False):
    store = SqliteJobs(tmp_path)
    job = store.enqueue(JobCommand("historical_ranking", start="2012-06-01"), f"hist-cov-{historical}", "ui")
    assert Worker(store, lambda command: build_historical_ranking(
        command.start, lambda as_of: _table(historical)), tmp_path).run_once()
    return job["id"]


def test_historical_preview_reports_streamlit_coverage_and_warnings(tmp_path):
    job_id = _job(tmp_path)
    df = _table()["table"]
    with TestClient(create_app(Settings(tmp_path))) as api:
        default = api.get(f"/api/v1/research/historical/{job_id}").json()["coverage"]
        strict = api.get(f"/api/v1/research/historical/{job_id}?coverage_threshold=0.95").json()["coverage"]
        assert api.get(f"/api/v1/research/historical/{job_id}?coverage_threshold=2").status_code == 422
    assert default["warnings"] == _streamlit_warnings(df, 0.7)
    assert strict["warnings"] == _streamlit_warnings(df, 0.95)
    assert default["warnings"] and default["warnings"][0].startswith("**Sector**: 70%")
    assert default["identity"] == {"ambiguous": int(df["identity_status"].eq("ambiguous").sum()),
                                   "unresolved": int(df["identity_status"].eq("unresolved").sum())}
    assert default["historical_coverage"] is None
    assert (default["with_fundamentals"], default["with_price"]) == (int(df["roic"].notna().sum()),
                                                                     int(df["market_cap"].notna().sum()))
    assert (default["sector_approximate"], default["no_sector"]) == (int(df["sector_is_approximate"].sum()),
                                                                     int(df["sector"].isna().sum()))


def test_historical_layer_replaces_identity_counts(tmp_path):
    job_id = _job(tmp_path, historical=True)
    with TestClient(create_app(Settings(tmp_path))) as api:
        coverage = api.get(f"/api/v1/research/historical/{job_id}").json()["coverage"]
    assert coverage["identity"] is None
    assert coverage["historical_coverage"]["accredited_prices"] == 6
    assert coverage["historical_coverage"]["excluded"] == {"identity_unresolved_or_ambiguous": 3}
