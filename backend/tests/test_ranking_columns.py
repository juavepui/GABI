"""Ranking (#196): more sortable columns, excluded sectors, earnings window and CSV of the filtered view."""

import csv
import io

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from market_fixture import TODAY, seed_fixture

from gabi.domain.market import model_policy
from gabi.domain.market.selection import RankingFilter, RankingSort, filter_ranking, sort_ranking
from gabi.infrastructure.settings import Settings
from gabi_api.bootstrap import create_app


@pytest.fixture
def api(tmp_path):
    seed_fixture(tmp_path)
    app = create_app(Settings(tmp_path), today=lambda: TODAY)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, app.state.market.repository, tmp_path


def test_earnings_window_keeps_or_drops_companies_reporting_soon():
    table = pd.DataFrame({"sector": ["A", "A", "B", "B"], "next_earnings_days": [0, 7, 8, None]},
                         index=["W", "X", "Y", "Z"])
    assert list(filter_ranking(table, RankingFilter(hide_no_data=False, earnings="only", earnings_days=7)).index) == ["W", "X"]
    # An unknown date is not «soon»: excluding the next 7 days keeps it.
    assert list(filter_ranking(table, RankingFilter(hide_no_data=False, earnings="exclude", earnings_days=7)).index) == ["Y", "Z"]
    assert list(filter_ranking(table, RankingFilter(hide_no_data=False, exclude_sectors=("A",))).index) == ["Y", "Z"]
    no_dates = table.drop(columns="next_earnings_days")
    assert filter_ranking(no_dates, RankingFilter(hide_no_data=False, earnings="only")).empty


def test_excluded_sectors_and_new_sort_keys_match_the_domain(api):
    client, repository, _ = api
    base = repository.ranking(dict(model_policy.FROZEN_WEIGHTS), TODAY).table
    payload = client.get("/api/v1/ranking?exclude_sectors=Financials&hide_no_data=false").json()
    expected = filter_ranking(base, RankingFilter(exclude_sectors=("Financials",), hide_no_data=False))
    assert [item["symbol"] for item in payload["items"]] == list(expected.index)
    assert all(item["sector"] != "Financials" for item in payload["items"])
    for key in ("roe", "volatility", "momentum_12m", "value_score", "next_earnings_days"):
        body = client.get(f"/api/v1/ranking?order_by={key}&direction=asc&hide_no_data=false").json()
        ordered = sort_ranking(filter_ranking(base, RankingFilter(hide_no_data=False)), RankingSort(key, "asc"))
        assert [item["symbol"] for item in body["items"]] == list(ordered.index), key
    assert client.get("/api/v1/ranking?earnings=soon").status_code == 422
    assert client.get("/api/v1/ranking?earnings=only&earnings_days=91").status_code == 422


def _csv(text):
    lines = text.lstrip("﻿").splitlines()
    header = [line for line in lines if line.startswith("#")]
    rows = list(csv.reader(io.StringIO("\n".join(line for line in lines if not line.startswith("#")))))
    return header, rows


def test_csv_has_every_filtered_row_with_the_visible_columns_and_a_header(api):
    client, _, root = api
    before = (root / "gabi.db").read_bytes()
    query = "order_by=market_cap&direction=asc&exclude_sectors=Financials&hide_no_data=false"
    ranking = client.get("/api/v1/ranking?limit=3&" + query).json()
    response = client.get("/api/v1/ranking/export.csv?columns=roe&columns=market_cap&columns=next_earnings_days&"
                          + query)
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"] == f'attachment; filename="gabi_ranking_{ranking['generated_at'][:10]}.csv"'
    header, rows = _csv(response.content.decode("utf-8"))
    assert header[0].startswith("# GABI · Ranking consultado el ")
    assert ranking["model"]["model_id"] in header[1] and "sin ventaja independiente" in header[1]
    assert "exclude_sectors=Financials" in header[2] and "columns" not in header[2]
    assert rows[0] == ["posicion", "simbolo", "nombre", "sector", "roe [fracción (0.05 = 5 %)]", "market_cap [USD]",
                       "next_earnings_days [días]"]
    body = rows[1:]
    assert len(body) == ranking["total"] and f"# Filas: {len(body)} de {ranking['total']}" in header
    # Pagination does not apply: the export keeps the backend order of the whole filtered view.
    assert [row[1] for row in body[:3]] == [item["symbol"] for item in ranking["items"]]
    first = ranking["items"][0]
    assert body[0][0] == str(first["rank"])
    assert float(body[0][4]) == pytest.approx(first["metrics"]["roe"]["value"])
    assert float(body[0][5]) == pytest.approx(first["metrics"]["market_cap"]["value"])
    assert (root / "gabi.db").read_bytes() == before


def test_csv_defaults_and_rejects_unknown_columns(api):
    client, _, _ = api
    _, rows = _csv(client.get("/api/v1/ranking/export.csv").content.decode("utf-8"))
    assert rows[0][4:] == ["price [USD]", "composite_score [puntos 0-100]", "confidence [puntos 0-100]",
                           "market_cap [USD]", "pe [múltiplo]"]
    bad = client.get("/api/v1/ranking/export.csv?columns=roe&columns=secret")
    assert bad.status_code == 422 and "secret" in bad.text
